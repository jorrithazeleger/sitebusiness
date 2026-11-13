"""Neemt een meeting op in twee sporen.

- mic.wav: je eigen microfoon (wat jij zegt), via sounddevice.
- systeem.wav: alles wat je Mac afspeelt (wat de anderen zeggen), via het Swift-hulpprogramma
  notulist-audiocap, dat ScreenCaptureKit gebruikt.

Twee aparte sporen maken het transcript duidelijker: zo weet Notulist wie er sprak.
Lukt het systeemgeluid niet (geen toestemming, of het hulpprogramma ontbreekt), dan gaat de
opname door met alleen de microfoon.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import signal
import subprocess
import threading
import time
import wave

from instellingen import SUPPORT

log = logging.getLogger("notulist")

META = "meta.json"
MIC = "mic.wav"
SYSTEEM = "systeem.wav"


def helper_pad():
    """Zoek notulist-audiocap: in de app zelf, of in de map met programmabestanden."""
    kandidaten = [os.environ.get("NOTULIST_HELPER", ""),
                  os.path.join(SUPPORT, "bin", "notulist-audiocap")]
    for pad in kandidaten:
        if pad and os.path.isfile(pad) and os.access(pad, os.X_OK):
            return pad
    return None


def slug(tekst: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", tekst.lower()).strip("-")
    return s or "meeting"


def nieuwe_map(basis: str, app: str, nu: float | None = None) -> str:
    stempel = time.strftime("%Y%m%d-%H%M", time.localtime(nu or time.time()))
    naam = "%s-%s" % (stempel, slug(app))
    pad = os.path.join(basis, naam)
    n = 2
    while os.path.exists(pad):
        pad = os.path.join(basis, "%s-%d" % (naam, n))
        n += 1
    os.makedirs(pad)
    return pad


def lees_meta(map_: str) -> dict:
    try:
        with open(os.path.join(map_, META), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def schrijf_meta(map_: str, meta: dict) -> None:
    pad = os.path.join(map_, META)
    with open(pad + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    os.replace(pad + ".tmp", pad)


class MicOpname:
    """Neemt de standaardmicrofoon op naar een WAV-bestand (mono, 16-bit)."""

    def __init__(self, pad: str):
        self.pad = pad
        self.start_tijd = None
        self.samplerate = None
        self.piek = 0
        self._stream = None
        self._wav = None
        self._wachtrij: queue.Queue = queue.Queue()
        self._schrijver = None

    def _callback(self, data, frames, time_info, status):  # draait in de audio-thread
        self._wachtrij.put(bytes(data))

    def _schrijf(self):
        import array
        while True:
            blok = self._wachtrij.get()
            if blok is None:
                break
            self._wav.writeframes(blok)
            if self.piek < 32767:
                samples = array.array("h", blok)
                if samples:
                    self.piek = max(self.piek, max(abs(min(samples)), max(samples)))

    def start(self):
        import sounddevice as sd
        fout = None
        for rate in (16000, None):
            try:
                if rate is None:
                    rate = int(sd.query_devices(kind="input")["default_samplerate"])
                self._stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16",
                                                 callback=self._callback)
                self.samplerate = rate
                break
            except Exception as exc:  # noqa: BLE001 - PortAudio geeft allerlei fouten
                fout = exc
        if self._stream is None:
            raise RuntimeError("microfoon openen mislukt: %s" % fout)
        self._wav = wave.open(self.pad, "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.samplerate)
        self._schrijver = threading.Thread(target=self._schrijf, name="mic-schrijver", daemon=True)
        self._schrijver.start()
        self.start_tijd = time.time()
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                log.exception("microfoon stoppen")
            self._stream = None
        if self._schrijver is not None:
            self._wachtrij.put(None)
            self._schrijver.join(timeout=10)
            self._schrijver = None
        if self._wav is not None:
            self._wav.close()
            self._wav = None


class SysteemOpname:
    """Stuurt notulist-audiocap aan, dat het systeemgeluid naar een WAV-bestand schrijft."""

    def __init__(self, helper: str, pad: str):
        self.helper = helper
        self.pad = pad
        self.start_tijd = None
        self._proc = None
        self._stderr: list[str] = []

    def start(self, wacht: float = 15.0):
        self._proc = subprocess.Popen([self.helper, self.pad], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True)
        regel: list[str] = []

        def lees_uit():
            regel.append(self._proc.stdout.readline())

        def lees_fouten():
            for r in self._proc.stderr:
                self._stderr.append(r.rstrip())
                del self._stderr[:-20]

        lezer = threading.Thread(target=lees_uit, daemon=True)
        lezer.start()
        threading.Thread(target=lees_fouten, daemon=True).start()
        lezer.join(wacht)
        eerste = regel[0].strip() if regel else ""
        if not eerste.startswith("READY"):
            self._afsluiten()
            reden = "; ".join(self._stderr[-3:]) or "geen antwoord van notulist-audiocap"
            raise RuntimeError(reden)
        try:
            self.start_tijd = float(eerste.split()[1])
        except (IndexError, ValueError):
            self.start_tijd = time.time()

    def _afsluiten(self):
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(5)
        for stroom in (self._proc.stdout, self._proc.stderr):
            try:
                stroom.close()
            except (OSError, ValueError):
                pass
        self._proc = None

    def actief(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self):
        self._afsluiten()


class Opname:
    """Eén meeting: een map met mic.wav, systeem.wav en meta.json."""

    def __init__(self, basis: str, app: str, automatisch: bool = True):
        self.app = app
        self.automatisch = automatisch
        self.map = nieuwe_map(basis, app)
        self.mic = MicOpname(os.path.join(self.map, MIC))
        self.systeem = None
        self.waarschuwing = None
        self.start_tijd = None

    def start(self):
        self.start_tijd = time.time()
        helper = helper_pad()
        if helper:
            try:
                self.systeem = SysteemOpname(helper, os.path.join(self.map, SYSTEEM))
                self.systeem.start()
            except Exception as exc:  # noqa: BLE001
                log.warning("systeemgeluid niet beschikbaar: %s", exc)
                self.waarschuwing = ("Alleen je microfoon wordt opgenomen. Geef Notulist toestemming "
                                     "voor schermopname (Systeeminstellingen > Privacy en "
                                     "beveiliging) om ook de anderen op te nemen.")
                self.systeem = None
        else:
            self.waarschuwing = "Alleen je microfoon wordt opgenomen (notulist-audiocap ontbreekt)."
        try:
            self.mic.start()
        except Exception:
            if self.systeem:
                self.systeem.stop()
            raise
        self._meta("opname")

    def _meta(self, status: str, einde: float | None = None):
        schrijf_meta(self.map, {
            "app": self.app,
            "automatisch": self.automatisch,
            "start": self.start_tijd,
            "einde": einde,
            "mic_start": self.mic.start_tijd,
            "systeem_start": self.systeem.start_tijd if self.systeem else None,
            "status": status,
            "waarschuwing": self.waarschuwing,
        })

    def duur(self) -> float:
        return time.time() - self.start_tijd if self.start_tijd else 0.0

    def stop(self):
        self.mic.stop()
        if self.systeem:
            self.systeem.stop()
        if self.mic.piek == 0:
            log.warning("microfoon gaf alleen stilte; mogelijk geen toestemming")
        self._meta("opgenomen", einde=time.time())
        return self.map
