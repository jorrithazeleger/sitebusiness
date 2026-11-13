"""De regie van Notulist: meetings herkennen, opnemen, uitschrijven en samenvatten.

Losgemaakt van de menubalk en het venster, zodat het ook zonder macOS te testen is.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import queue
import threading
import time

import instellingen as inst
import samenvatting
import transcriptie
from detectie import MeetingDetector, actieve_meeting, beschrijf, eigen_pids
from opname import Opname, lees_meta, schrijf_meta

log = logging.getLogger("notulist")


class Kern:
    def __init__(self, config, audio=None, melder=None):
        self.config = config
        self.audio = audio
        self.melder = melder or (lambda titel, tekst: None)
        self.detector = MeetingDetector(config["start_na_seconden"], config["stop_na_seconden"])
        self.opname: Opname | None = None
        self.bezig_met_starten = False
        self.negeer_app = None   # na handmatig stoppen niet meteen opnieuw starten
        self.voortgang = None    # (meeting-id, fractie, wat) tijdens uitschrijven/samenvatten
        self.wachtrij: queue.Queue = queue.Queue()
        self.in_wachtrij: set = set()
        self.laatste_fout = None
        self.gezien: list[str] = []   # apps die nu de microfoon gebruiken
        self.versie = 0               # telt op bij elke wijziging in de bibliotheek
        self._acties = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._slot = threading.Lock()
        self.transcriber = transcriptie.Transcriber(config["model"], config["taal"])
        threading.Thread(target=self._werk_lus, name="verwerken", daemon=True).start()
        for map_ in transcriptie.wachtende_mappen(self.basis()):
            self.plan(map_, "uitschrijven")

    def basis(self):
        return inst.opnamemap(self.config)

    def gewijzigd(self):
        self.versie += 1

    # -- meetings herkennen -------------------------------------------------

    def tik(self, nu=None):
        nu = nu if nu is not None else time.monotonic()
        opname = self.opname
        if opname and opname.duur() > self.config["maximale_duur_minuten"] * 60:
            log.info("maximale duur bereikt, opname stopt")
            self.stop(reden="De maximale opnameduur is bereikt.")
            return
        if opname and opname.automatisch and \
                opname.stil_sinds() > self.config["stilte_stop_minuten"] * 60:
            log.info("al %d minuten stil, opname stopt", self.config["stilte_stop_minuten"])
            self.negeer_app = opname.app
            self.stop(reden="Het was %d minuten stil." % self.config["stilte_stop_minuten"])
            return
        if self.audio is None:
            return
        try:
            gebruikers = self.audio.gebruikers()
        except Exception:  # noqa: BLE001
            log.exception("audio uitlezen")
            return
        gezien = beschrijf(gebruikers, eigen_pids())
        if gezien != self.gezien:
            log.info("microfoon in gebruik door: %s", ", ".join(gezien) or "niemand")
            self.gezien = gezien

        volgt_automatisch = opname is not None and opname.automatisch
        if not self.config["automatisch_opnemen"] and not volgt_automatisch:
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
            log.info("%s gebruikt de microfoon niet meer, opname stopt", actie[1])
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
            opname = Opname(self.basis(), app, automatisch)
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
            self.gewijzigd()

    def stop(self, handmatig=False, reden=None):
        opname = self.opname
        if opname is None:
            return
        self.opname = None
        if handmatig and opname.automatisch:
            self.negeer_app = opname.app
        self.detector.reset()
        if reden:
            self.melder("Opname gestopt", reden)
        self._acties.submit(self._stop, opname)

    def _stop(self, opname):
        try:
            map_ = opname.stop()
            log.info("opname gestopt na %.0f s", opname.duur())
            self.plan(map_, "uitschrijven")
        except Exception:  # noqa: BLE001
            log.exception("opname stoppen")
        self.gewijzigd()

    def afsluiten(self):
        if self.opname:
            opname, self.opname = self.opname, None
            opname.stop()

    # -- uitschrijven en samenvatten ---------------------------------------

    def plan(self, map_, soort="uitschrijven"):
        sleutel = (map_, soort)
        if sleutel in self.in_wachtrij:
            return
        self.in_wachtrij.add(sleutel)
        self.wachtrij.put(sleutel)
        self.gewijzigd()

    def _werk_lus(self):
        while True:
            map_, soort = self.wachtrij.get()
            naam = os.path.basename(map_)
            try:
                if soort == "uitschrijven":
                    self._uitschrijven(map_, naam)
                else:
                    self._samenvatten(map_, naam)
            except Exception as exc:  # noqa: BLE001
                log.exception("%s %s", soort, naam)
                self.melder("Uitschrijven mislukt" if soort == "uitschrijven" else
                            "Samenvatten mislukt", "%s: %s" % (naam, exc))
            finally:
                self.voortgang = None
                self.in_wachtrij.discard((map_, soort))
                self.gewijzigd()

    def _uitschrijven(self, map_, naam):
        self.voortgang = (naam, 0.0, "uitschrijven")

        def bij(f):
            self.voortgang = (naam, f, "uitschrijven")

        uit = transcriptie.verwerk(map_, self.transcriber, self.config, bij)
        log.info("transcript klaar: %s", uit)
        if self.config.get("samenvatten_automatisch") and samenvatting.beschikbaar():
            self.plan(map_, "samenvatten")
        else:
            self.melder("Transcript klaar", naam)

    def _samenvatten(self, map_, naam):
        self.voortgang = (naam, None, "samenvatten")
        meta = lees_meta(map_)
        meta.pop("fout_samenvatting", None)
        schrijf_meta(map_, meta)
        try:
            data = samenvatting.maak(map_, self.config)
        except samenvatting.SamenvattingFout as exc:
            meta = lees_meta(map_)
            meta["fout_samenvatting"] = str(exc)
            schrijf_meta(map_, meta)
            raise
        self.melder("Notulen klaar", data.get("titel") or naam)

    # -- status voor het venster -------------------------------------------

    def status(self):
        opname = self.opname
        stand = {
            "versie": self.versie,
            "automatisch": bool(self.config["automatisch_opnemen"]),
            "herkent": self.audio is not None,
            "starten": self.bezig_met_starten,
            "gezien": self.gezien,
            "laatste_fout": self.laatste_fout,
            "wachtrij": self.wachtrij.qsize(),
            "samenvatten": samenvatting.beschikbaar(),
            "opname": None,
            "voortgang": None,
        }
        if opname:
            stand["opname"] = {
                "id": os.path.basename(opname.map),
                "app": opname.app,
                "automatisch": opname.automatisch,
                "duur": opname.duur(),
                "stil": opname.stil_sinds(),
                "niveaus": opname.niveaus(),
                "systeem": opname.systeem is not None,
                "waarschuwing": opname.waarschuwing,
            }
        if self.voortgang:
            naam, f, wat = self.voortgang
            stand["voortgang"] = {"id": naam, "fractie": f, "wat": wat}
        return stand
