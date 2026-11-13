"""Notulist: neemt je meetings op en maakt er een transcript van, helemaal op je eigen Mac.

Draait als icoon in de menubalk. Zodra een meeting-app (Zoom, Teams, Meet in de browser, ...)
je microfoon gebruikt, start de opname vanzelf; als de meeting voorbij is stopt hij en begint
het transcriberen.

Gebruik:
  python notulist.py                 de menubalk-app starten (ook: --app)
  python notulist.py --diagnose      laten zien welke apps nu audio gebruiken en of alles werkt
  python notulist.py --transcribeer <map>   een opgenomen meeting (opnieuw) transcriberen
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import instellingen as inst  # noqa: E402
import transcriptie  # noqa: E402
from detectie import (CoreAudio, CoreAudioNietBeschikbaar, MeetingDetector,  # noqa: E402
                      actieve_meeting, eigen_pids)
from opname import Opname, helper_pad  # noqa: E402

log = logging.getLogger("notulist")
LOGBESTAND = os.path.expanduser("~/Library/Logs/Notulist.log")
ICONEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iconen")
TIK = 2.0  # seconden tussen twee controles


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


class Kern:
    """Alles behalve de menubalk: meetings herkennen, opnemen en transcriberen."""

    def __init__(self, config, audio=None, melder=melding):
        self.config = config
        self.audio = audio
        self.melder = melder
        self.detector = MeetingDetector(config["start_na_seconden"], config["stop_na_seconden"])
        self.opname: Opname | None = None
        self.bezig_met_starten = False
        self.negeer_app = None  # na handmatig stoppen niet meteen opnieuw starten
        self.voortgang = None   # (mapnaam, fractie) tijdens transcriberen
        self.wachtrij: queue.Queue = queue.Queue()
        self.in_wachtrij: set[str] = set()
        self.laatste_fout = None
        self._acties = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._slot = threading.Lock()
        self.transcriber = transcriptie.Transcriber(config["model"], config["taal"])
        threading.Thread(target=self._transcribeer_lus, name="transcriberen", daemon=True).start()
        for map_ in transcriptie.wachtende_mappen(inst.opnamemap(config)):
            self.plan_transcriptie(map_)

    # -- meetings herkennen -------------------------------------------------

    def tik(self, nu=None):
        nu = nu if nu is not None else time.monotonic()
        opname = self.opname
        if opname and opname.duur() > self.config["maximale_duur_minuten"] * 60:
            log.info("maximale duur bereikt")
            self.stop()
            return
        if opname and opname.systeem and not opname.systeem.actief():
            log.warning("systeemgeluid-opname is onverwacht gestopt")
        if self.audio is None:
            return
        volgt_automatisch = opname is not None and opname.automatisch
        if not self.config["automatisch_opnemen"] and not volgt_automatisch:
            return
        try:
            gebruikers = self.audio.gebruikers()
        except Exception:  # noqa: BLE001
            log.exception("audio uitlezen")
            return
        app = actieve_meeting(gebruikers, eigen_pids(), self.config["browsers_meenemen"],
                              lopend=self.detector.bezig)
        if self.negeer_app:
            if app is None:
                self.negeer_app = None
            else:
                return
        if opname is not None and not opname.automatisch:
            return  # handmatige opname: alleen handmatig stoppen
        actie = self.detector.update(app, nu)
        if actie and actie[0] == "start" and self.opname is None and not self.bezig_met_starten:
            self.start(actie[1], automatisch=True)
        elif actie and actie[0] == "stop" and self.opname is not None:
            self.stop()

    # -- opnemen ------------------------------------------------------------

    def start(self, app="handmatig", automatisch=False):
        with self._slot:
            if self.opname is not None or self.bezig_met_starten:
                return
            self.bezig_met_starten = True
        self._acties.submit(self._start, app, automatisch)

    def _start(self, app, automatisch):
        try:
            opname = Opname(inst.opnamemap(self.config), app, automatisch)
            opname.start()
            self.opname = opname
            self.laatste_fout = None
            log.info("opname gestart: %s (%s)", app, opname.map)
            self.melder("Opname gestart", "%s. Stoppen kan via het menubalk-icoon." % (
                "Meeting in %s herkend" % app if automatisch else "Handmatige opname"))
            if opname.waarschuwing:
                self.melder("Let op", opname.waarschuwing)
        except Exception as exc:  # noqa: BLE001
            log.exception("opname starten")
            self.laatste_fout = str(exc)
            self.detector.reset()
            self.negeer_app = app if automatisch else None
            self.melder("Opnemen lukt niet", str(exc))
        finally:
            self.bezig_met_starten = False

    def stop(self, handmatig=False):
        opname = self.opname
        if opname is None:
            return
        self.opname = None
        if handmatig and opname.automatisch:
            self.negeer_app = opname.app
        self.detector.reset()
        self._acties.submit(self._stop, opname)

    def _stop(self, opname):
        try:
            map_ = opname.stop()
            log.info("opname gestopt na %.0f s", opname.duur())
            self.plan_transcriptie(map_)
        except Exception:  # noqa: BLE001
            log.exception("opname stoppen")

    def afsluiten(self):
        if self.opname:
            opname, self.opname = self.opname, None
            opname.stop()

    # -- transcriberen ------------------------------------------------------

    def plan_transcriptie(self, map_):
        if map_ in self.in_wachtrij:
            return
        self.in_wachtrij.add(map_)
        self.wachtrij.put(map_)

    def _transcribeer_lus(self):
        while True:
            map_ = self.wachtrij.get()
            naam = os.path.basename(map_)
            self.voortgang = (naam, 0.0)
            try:
                def bij(f):
                    self.voortgang = (naam, f)
                uit = transcriptie.verwerk(map_, self.transcriber, self.config, bij)
                log.info("transcript klaar: %s", uit)
                self.melder("Transcript klaar", naam)
            except Exception as exc:  # noqa: BLE001
                log.exception("transcriberen %s", naam)
                self.melder("Transcriberen mislukt", "%s: %s" % (naam, exc))
            finally:
                self.voortgang = None
                self.in_wachtrij.discard(map_)

    # -- overzicht ----------------------------------------------------------

    def recente_meetings(self, aantal=10):
        basis = inst.opnamemap(self.config)
        if not os.path.isdir(basis):
            return []
        mappen = sorted((d for d in os.listdir(basis) if os.path.isdir(os.path.join(basis, d))),
                        reverse=True)
        return [os.path.join(basis, d) for d in mappen[:aantal]]


# ---------------------------------------------------------------------------
# Menubalk
# ---------------------------------------------------------------------------

def start_app():
    import rumps

    config = inst.laad()
    if not os.path.exists(inst.BESTAND):
        inst.bewaar(config)
    try:
        audio = CoreAudio()
    except (CoreAudioNietBeschikbaar, OSError) as exc:
        log.warning("automatisch herkennen niet mogelijk: %s", exc)
        audio = None
    kern = Kern(config, audio)

    class NotulistApp(rumps.App):
        def __init__(self):
            # Effen "template"-icoon: macOS kleurt het zelf, net als de andere menubalk-iconen.
            super().__init__("Notulist", icon=self.icoon_pad("rust"), template=True,
                             quit_button=None)
            self._icoon = "rust"
            self.status = rumps.MenuItem("Notulist start...")
            self.knop = rumps.MenuItem("Neem nu op", callback=self.wissel_opname)
            self.auto = rumps.MenuItem("Automatisch opnemen bij meetings", callback=self.wissel_auto)
            self.auto.state = int(bool(config["automatisch_opnemen"]))
            self.recent = rumps.MenuItem("Recente meetings")
            self.recent.add(rumps.MenuItem("(nog geen)"))
            self.menu = [
                self.status, None, self.knop, self.auto, None, self.recent,
                rumps.MenuItem("Open map met meetings", callback=self.open_map), None,
                rumps.MenuItem("Controleer toestemmingen", callback=self.toestemmingen),
                rumps.MenuItem("Instellingen aanpassen...", callback=self.instellingen),
                rumps.MenuItem("Logboek bekijken", callback=lambda _: open_bestand(LOGBESTAND)),
                None,
                rumps.MenuItem("Stop Notulist", callback=self.stoppen, key="q"),
            ]
            self._recent_lijst = None
            self.timer = rumps.Timer(self.tik, TIK)
            self.timer.start()
            if audio is None:
                self.auto.state = 0
                self.auto.title = "Automatisch opnemen (vraagt macOS 14 of nieuwer)"
            vlag = os.path.join(inst.SUPPORT, ".toestemming-gevraagd")
            if not os.path.exists(vlag):
                os.makedirs(inst.SUPPORT, exist_ok=True)
                open(vlag, "w").close()
                threading.Thread(target=vraag_toestemmingen, daemon=True).start()

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
                    naam, f = kern.voortgang
                    self.toon("uitschrijven", " %d%%" % int(f * 100))
                    self.status.title = "Transcriberen: %s (%d%%)" % (naam, int(f * 100))
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
            self.ververs_recent()

        def ververs_recent(self):
            lijst = kern.recente_meetings()
            klaar = tuple((m, os.path.exists(os.path.join(m, transcriptie.TRANSCRIPT))) for m in lijst)
            if klaar == self._recent_lijst:
                return
            self._recent_lijst = klaar
            self.recent.clear()
            if not lijst:
                self.recent.add(rumps.MenuItem("(nog geen)"))
            for map_, heeft in klaar:
                titel = os.path.basename(map_) + ("" if heeft else "  (bezig)")
                doel = os.path.join(map_, transcriptie.TRANSCRIPT) if heeft else map_
                self.recent.add(rumps.MenuItem(titel, callback=lambda _, d=doel: open_bestand(d)))

        def wissel_opname(self, _):
            if kern.opname:
                kern.stop(handmatig=True)
            else:
                kern.start("handmatig", automatisch=False)
            self.ververs()

        def wissel_auto(self, item):
            if audio is None:
                rumps.alert("Notulist", "Automatisch opnemen werkt vanaf macOS 14 (Sonoma).")
                return
            config["automatisch_opnemen"] = not config["automatisch_opnemen"]
            item.state = int(config["automatisch_opnemen"])
            inst.bewaar(config)
            kern.detector.reset()
            self.ververs()

        def open_map(self, _):
            pad = inst.opnamemap(config)
            os.makedirs(pad, exist_ok=True)
            subprocess.run(["open", pad])

        def instellingen(self, _):
            inst.bewaar(config)
            subprocess.run(["open", "-t", inst.BESTAND])
            rumps.alert("Notulist", "Bewaar je wijzigingen en start Notulist daarna opnieuw.")

        def toestemmingen(self, _):
            rumps.alert("Notulist", controleer_toestemmingen())

        def stoppen(self, _):
            kern.afsluiten()
            rumps.quit_application()

    NotulistApp().run()


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
        print("  pid %-6d %-12s %s  %s" % (g.pid, wat, g.bundel or "-", g.pad))
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
    p = argparse.ArgumentParser(description="Notulist: meetings opnemen en transcriberen")
    p.add_argument("--app", action="store_true", help="menubalk-app starten (standaard)")
    p.add_argument("--diagnose", action="store_true", help="laat zien wat Notulist nu ziet")
    p.add_argument("--transcribeer", metavar="MAP", help="een opgenomen meeting transcriberen")
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
        log.info("Notulist draait al")
        return 0
    log.info("Notulist gestart")
    start_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
