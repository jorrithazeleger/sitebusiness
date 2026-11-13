"""Notulist: neemt je meetings op en maakt er een transcript en notulen van, op je eigen Mac.

Draait als icoon in de menubalk, met een venster waarin je je meetings terugvindt. Zodra een
meeting-app (Zoom, Teams, Meet in de browser, ...) je microfoon gebruikt, start de opname
vanzelf; als de meeting voorbij is stopt hij en begint het uitschrijven.

Gebruik:
  python notulist.py                 de app starten (ook: --app)
  python notulist.py --diagnose      laten zien welke apps nu audio gebruiken en of alles werkt
  python notulist.py --transcribeer <map>   een opgenomen meeting (opnieuw) uitschrijven
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import instellingen as inst  # noqa: E402
import meetings  # noqa: E402
import transcriptie  # noqa: E402
from detectie import CoreAudio, CoreAudioNietBeschikbaar, actieve_meeting, eigen_pids  # noqa: E402
from kern import Kern  # noqa: E402
from opname import helper_pad  # noqa: E402

log = logging.getLogger("notulist")
LOGBESTAND = os.path.expanduser("~/Library/Logs/Notulist.log")
ICONEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iconen")
VENSTER_INFO = os.path.join(inst.SUPPORT, "venster.json")  # poort en sleutel van de server
TIK = 2.0  # seconden tussen twee controles op meetings


def logging_instellen(naar_scherm=False):
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        os.makedirs(os.path.dirname(LOGBESTAND), exist_ok=True)
        h = logging.handlers.RotatingFileHandler(LOGBESTAND, maxBytes=1_000_000, backupCount=2,
                                                 encoding="utf-8")
        h.setFormatter(fmt)
        log.addHandler(h)
    except OSError:
        pass
    if naar_scherm:
        s = logging.StreamHandler()
        s.setFormatter(fmt)
        log.addHandler(s)


def open_bestand(pad):
    if subprocess.run(["open", pad], capture_output=True).returncode != 0:
        subprocess.run(["open", "-t", pad], capture_output=True)


def melding(titel, tekst):
    try:
        import rumps
        rumps.notification("Notulist", titel, tekst)
    except Exception:  # noqa: BLE001 - dan maar via AppleScript
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        subprocess.run(["osascript", "-e", 'display notification "%s" with title "Notulist" '
                        'subtitle "%s"' % (esc(tekst), esc(titel))], capture_output=True)


def start_app():
    import rumps
    from server import Server
    from venster import Venster

    config = inst.laad()
    if not os.path.exists(inst.BESTAND):
        inst.bewaar(config)
    try:
        audio = CoreAudio()
    except (CoreAudioNietBeschikbaar, OSError) as exc:
        log.warning("automatisch herkennen niet mogelijk: %s", exc)
        audio = None
    kern = Kern(config, audio, melding)

    verzoeken = []  # vensterverzoeken uit andere threads, afgehandeld op de hoofdthread
    server = Server(kern, {
        "toestemmingen": controleer_toestemmingen,
        "logboek": lambda: open_bestand(LOGBESTAND),
        "toon": lambda js=None: verzoeken.append(js),
    })
    server.start()
    try:
        with open(VENSTER_INFO, "w", encoding="utf-8") as fh:
            json.dump({"poort": server.poort, "token": server.token}, fh)
        os.chmod(VENSTER_INFO, 0o600)
    except OSError:
        pass
    venster = Venster(server.url)

    class NotulistApp(rumps.App):
        def __init__(self):
            # Effen "template"-icoon: macOS kleurt het zelf, net als de andere menubalk-iconen.
            super().__init__("Notulist", icon=self.icoon_pad("rust"), template=True,
                             quit_button=None)
            self._icoon = "rust"
            self.status = rumps.MenuItem("Notulist start...")
            self.knop = rumps.MenuItem("Neem nu op", callback=self.wissel_opname)
            self.auto = rumps.MenuItem("Meetings vanzelf opnemen", callback=self.wissel_auto)
            self.auto.state = int(bool(config["automatisch_opnemen"]))
            self.menu = [
                rumps.MenuItem("Open Notulist", callback=lambda _: venster.toon(), key="o"),
                None, self.status, self.knop, self.auto, None,
                rumps.MenuItem("Instellingen...", callback=lambda _: venster.toon("openInstellingen()"), key=","),
                rumps.MenuItem("Open map met meetings", callback=self.open_map),
                None,
                rumps.MenuItem("Stop Notulist", callback=self.stoppen, key="q"),
            ]
            if audio is None:
                self.auto.state = 0
                self.auto.title = "Meetings vanzelf opnemen (vraagt macOS 14)"
            rumps.Timer(self.tik, TIK).start()
            rumps.Timer(self.verwerk_verzoeken, 0.3).start()

            os.makedirs(inst.SUPPORT, exist_ok=True)
            eerste_keer = os.path.join(inst.SUPPORT, ".toestemming-gevraagd")
            if not os.path.exists(eerste_keer):
                open(eerste_keer, "w").close()
                threading.Thread(target=vraag_toestemmingen, daemon=True).start()
            # De eerste keer (ook na de update met het venster) meteen het venster laten zien.
            venster_gezien = os.path.join(inst.SUPPORT, ".venster-getoond")
            if not os.path.exists(venster_gezien):
                open(venster_gezien, "w").close()
                verzoeken.append(None)
            koppel_heropenen(venster)

        @staticmethod
        def icoon_pad(naam):
            return os.path.join(ICONEN, "menubalk-%s.png" % naam)

        def toon(self, icoon, tekst=None):
            """Menubalk: icoon (rust, opname of uitschrijven) met eventueel tekst erachter."""
            if icoon != self._icoon:
                self.icon = self.icoon_pad(icoon)
                self._icoon = icoon
            if tekst != self.title:
                self.title = tekst

        def verwerk_verzoeken(self, _):
            while verzoeken:
                venster.toon(verzoeken.pop(0))

        def tik(self, _):
            kern.tik()
            self.ververs()

        def ververs(self):
            opname = kern.opname
            if opname:
                m, s = divmod(int(opname.duur()), 60)
                self.toon("opname", " %d:%02d" % (m, s))
                self.status.title = "Neemt op: %s" % opname.app
                self.knop.title = "Stop opname"
            elif kern.bezig_met_starten:
                self.toon("opname")
                self.status.title = "Opname starten..."
            else:
                self.knop.title = "Neem nu op"
                if kern.voortgang:
                    naam, f, wat = kern.voortgang
                    if wat == "samenvatten":
                        self.toon("uitschrijven")
                        self.status.title = "Notulen maken: %s" % naam
                    else:
                        self.toon("uitschrijven", " %d%%" % int((f or 0) * 100))
                        self.status.title = "Uitschrijven: %s (%d%%)" % (naam, int((f or 0) * 100))
                else:
                    self.toon("rust")
                    if kern.laatste_fout:
                        self.status.title = "Laatste poging mislukt, zie logboek"
                    elif config["automatisch_opnemen"] and audio is not None:
                        self.status.title = "Wacht op een meeting"
                    else:
                        self.status.title = "Klaar om op te nemen"
            wachtend = kern.wachtrij.qsize()
            if wachtend:
                self.status.title += " (+%d in de wachtrij)" % wachtend
            self.auto.state = int(bool(config["automatisch_opnemen"]) and audio is not None)

        def wissel_opname(self, _):
            if kern.opname:
                kern.stop(handmatig=True)
            else:
                kern.start("handmatig", automatisch=False)
            self.ververs()

        def wissel_auto(self, item):
            if audio is None:
                rumps.alert("Notulist", "Meetings vanzelf opnemen werkt vanaf macOS 14 (Sonoma).")
                return
            config["automatisch_opnemen"] = not config["automatisch_opnemen"]
            inst.bewaar(config)
            kern.detector.reset()
            kern.gewijzigd()
            self.ververs()

        def open_map(self, _):
            pad = inst.opnamemap(config)
            os.makedirs(pad, exist_ok=True)
            subprocess.run(["open", pad])

        def stoppen(self, _):
            kern.afsluiten()
            server.stop()
            rumps.quit_application()

    NotulistApp().run()


def koppel_heropenen(venster):
    """Dubbelklik je op Notulist terwijl het al draait, dan opent het venster."""
    try:
        import objc
        from rumps import rumps as rumps_intern

        def heropen(self, app, zichtbaar):
            venster.toon()
            return True

        objc.classAddMethods(rumps_intern.NSApp, [objc.selector(
            heropen, selector=b"applicationShouldHandleReopen:hasVisibleWindows:", signature=b"Z@:@Z")])
    except Exception:  # noqa: BLE001 - dan opent het venster alleen via het menubalk-icoon
        log.exception("heropenen koppelen")


def toon_bestaand_venster() -> bool:
    """Draait Notulist al? Vraag het dan zijn venster te tonen."""
    try:
        with open(VENSTER_INFO, encoding="utf-8") as fh:
            info = json.load(fh)
        req = urllib.request.Request("http://127.0.0.1:%d/api/venster" % info["poort"], data=b"{}",
                                     headers={"X-Notulist-Token": info["token"],
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False


def vraag_toestemmingen():
    """Laat macOS eenmalig om toestemming vragen, liever nu dan midden in een meeting."""
    try:
        import sounddevice as sd
        sd.rec(int(0.3 * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
    except Exception:  # noqa: BLE001
        log.exception("microfoontoestemming vragen")
    helper = helper_pad()
    if helper:
        subprocess.run([helper, "--check"], capture_output=True, timeout=30)


def controleer_toestemmingen() -> str:
    regels = []
    try:
        import numpy as np
        import sounddevice as sd
        data = sd.rec(int(1.0 * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        if int(np.max(np.abs(data))) == 0:
            regels.append("Microfoon: geen geluid. Zet Notulist aan bij Systeeminstellingen > "
                          "Privacy en beveiliging > Microfoon.")
        else:
            regels.append("Microfoon: in orde.")
    except Exception as exc:  # noqa: BLE001
        regels.append("Microfoon: werkt niet (%s)." % exc)
    helper = helper_pad()
    if not helper:
        regels.append("Systeemgeluid: hulpprogramma ontbreekt, draai het installatiescript opnieuw.")
    else:
        r = subprocess.run([helper, "--check"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            regels.append("Systeemgeluid: in orde.")
        else:
            regels.append("Systeemgeluid: geen toestemming. Zet Notulist aan bij Systeeminstellingen > "
                          "Privacy en beveiliging > Scherm- en systeemaudio-opname, en start "
                          "Notulist opnieuw.")
    try:
        CoreAudio()
        regels.append("Meetings herkennen: in orde.")
    except Exception as exc:  # noqa: BLE001
        regels.append("Meetings herkennen: niet mogelijk (%s)." % exc)
    return "\n\n".join(regels)


def diagnose():
    print("Notulist diagnose\n")
    config = inst.laad()
    print("Instellingen: %s" % inst.BESTAND)
    print("Opnames:      %s" % inst.opnamemap(config))
    print("Hulpprogramma systeemgeluid: %s" % (helper_pad() or "ontbreekt"))
    print("Meetings:     %d" % len(meetings.alle_ids(inst.opnamemap(config))))
    try:
        audio = CoreAudio()
    except Exception as exc:  # noqa: BLE001
        print("\nMeetings herkennen werkt hier niet: %s" % exc)
        return 1
    gebruikers = audio.gebruikers()
    print("\nProgramma's die nu audio gebruiken:")
    if not gebruikers:
        print("  (geen)")
    for g in gebruikers:
        wat = "+".join(w for w, aan in (("microfoon", g.invoer), ("geluid", g.uitvoer)) if aan)
        print("  pid %-6d %-18s %s  %s" % (g.pid, wat, g.bundel or "-", g.pad))
    app = actieve_meeting(gebruikers, eigen_pids(), config["browsers_meenemen"])
    print("\nMeeting herkend: %s" % (app or "nee"))
    return 0


def enkele_instantie():
    """Voorkomt dat Notulist twee keer draait (bijvoorbeeld bij inloggen en met de hand)."""
    os.makedirs(inst.SUPPORT, exist_ok=True)
    fh = open(os.path.join(inst.SUPPORT, "notulist.lock"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return fh


def main(argv=None):
    p = argparse.ArgumentParser(description="Notulist: meetings opnemen en uitschrijven")
    p.add_argument("--app", action="store_true", help="de app starten (standaard)")
    p.add_argument("--diagnose", action="store_true", help="laat zien wat Notulist nu ziet")
    p.add_argument("--transcribeer", metavar="MAP", help="een opgenomen meeting uitschrijven")
    args = p.parse_args(argv)

    if args.diagnose:
        return diagnose()
    if args.transcribeer:
        logging_instellen(naar_scherm=True)
        config = inst.laad()
        t = transcriptie.Transcriber(config["model"], config["taal"])
        print(transcriptie.verwerk(os.path.abspath(args.transcribeer), t, config,
                                   lambda f: print("\r  %d%%" % int(f * 100), end="", flush=True)))
        return 0

    logging_instellen()
    slot = enkele_instantie()
    if slot is None:
        log.info("Notulist draait al; venster van de draaiende Notulist tonen")
        toon_bestaand_venster()
        return 0
    log.info("Notulist gestart")
    start_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
