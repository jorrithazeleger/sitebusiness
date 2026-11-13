"""Maakt van de opnames een transcript in Markdown.

Beide sporen (microfoon = jij, systeemgeluid = de anderen) gaan apart door Whisper
(faster-whisper, draait lokaal). Daarna worden de stukken op tijd in elkaar geschoven.
Gebruik je speakers in plaats van een koptelefoon, dan vangt je microfoon ook de anderen op;
zulke dubbele zinnen haalt Notulist weg.
"""
from __future__ import annotations

import difflib
import logging
import os
import re
import threading
import time
import wave
from dataclasses import dataclass

from opname import MIC, SYSTEEM, lees_meta, schrijf_meta

log = logging.getLogger("notulist")

RATE = 16000
TRANSCRIPT = "transcript.md"

DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
           "september", "oktober", "november", "december"]


@dataclass
class Segment:
    start: float
    einde: float
    tekst: str
    spreker: str = ""


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def laad_audio(pad: str):
    """Leest een WAV-bestand als mono float32 op 16 kHz (wat Whisper verwacht)."""
    import numpy as np
    with wave.open(pad, "rb") as w:
        kanalen, breedte, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        ruw = w.readframes(n)
    if breedte == 2:
        audio = np.frombuffer(ruw, dtype="<i2").astype(np.float32) / 32768.0
    elif breedte == 4:
        audio = np.frombuffer(ruw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif breedte == 1:
        audio = (np.frombuffer(ruw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError("onbekend WAV-formaat (%d bytes per sample)" % breedte)
    if kanalen > 1:
        audio = audio.reshape(-1, kanalen).mean(axis=1)
    if rate != RATE and len(audio):
        duur = len(audio) / rate
        doel = np.linspace(0, duur, int(round(duur * RATE)), endpoint=False, dtype=np.float64)
        bron = np.arange(len(audio), dtype=np.float64) / rate
        audio = np.interp(doel, bron, audio).astype(np.float32)
    return audio


def herstel_wav(pad: str) -> None:
    """Stopte Notulist midden in een opname, dan staat er in de WAV-kop nog 0 samples.
    Werkt alleen voor de microfoon-WAV's die Python zelf schrijft (kop van 44 bytes)."""
    try:
        with wave.open(pad, "rb") as w:
            if w.getnframes() > 0:
                return
            kanalen, breedte, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
    except (OSError, EOFError, wave.Error):
        return
    grootte = os.path.getsize(pad)
    if grootte <= 44:
        return
    with open(pad, "rb") as fh:
        fh.seek(44)
        ruw = fh.read()
    ruw = ruw[: len(ruw) - len(ruw) % (kanalen * breedte)]
    with wave.open(pad + ".tmp", "wb") as w:
        w.setnchannels(kanalen)
        w.setsampwidth(breedte)
        w.setframerate(rate)
        w.writeframes(ruw)
    os.replace(pad + ".tmp", pad)


def heeft_geluid(audio, drempel: float = 0.01) -> bool:
    """False als een spoor stil is (bijvoorbeeld zonder microfoontoestemming geeft macOS
    alleen nullen), dan hoeft Whisper er niet aan te beginnen."""
    import numpy as np
    return len(audio) > 0 and float(np.max(np.abs(audio))) > drempel


# ---------------------------------------------------------------------------
# Tekst opschonen en samenvoegen
# ---------------------------------------------------------------------------

# Zinnen die Whisper verzint bij stilte of ruis (het is getraind op ondertitels).
_ALTIJD_WEG = ("amara.org", "ondertiteld door", "ondertiteling door", "ondertiteling:",
               "tv gelderland", "subtitles by", "ondertitels ingediend door")
_ALS_ENIGE_TEKST = ("bedankt voor het kijken", "dank u voor het kijken", "dank je voor het kijken",
                    "bedankt voor het luisteren", "thanks for watching", "thank you for watching",
                    "abonneer op het kanaal", "abonneer je op het kanaal", "ondertiteling",
                    "ondertiteld", "you")


def _normaal(tekst: str) -> str:
    return re.sub(r"[^\w\s.]", "", tekst.lower()).strip(" .")


def is_hallucinatie(tekst: str) -> bool:
    n = _normaal(tekst)
    if not n:
        return True
    if any(z in n for z in _ALTIJD_WEG):
        return True
    return n in _ALS_ENIGE_TEKST


def lijkt_op(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normaal(a).split(), _normaal(b).split()).ratio()


def verwijder_echo(ik, anderen, marge: float = 1.5, drempel: float = 0.6):
    """Haalt zinnen uit het microfoonspoor die eigenlijk uit je speakers kwamen."""
    schoon = []
    for s in ik:
        echo = False
        for a in anderen:
            if a.einde + marge < s.start or a.start - marge > s.einde:
                continue
            if lijkt_op(s.tekst, a.tekst) >= drempel or _normaal(s.tekst) in _normaal(a.tekst):
                echo = True
                break
        if not echo:
            schoon.append(s)
    return schoon


def voeg_samen(ik, anderen, naam_ik="Ik", naam_anderen="Anderen", verschuiving=0.0, pauze=2.0):
    """Zet beide sporen op tijd achter elkaar en plakt korte stukken van dezelfde spreker aan
    elkaar. verschuiving = hoeveel seconden het systeemspoor later begon dan de microfoon."""
    alles = [Segment(s.start, s.einde, s.tekst.strip(), naam_ik) for s in ik]
    alles += [Segment(s.start + verschuiving, s.einde + verschuiving, s.tekst.strip(), naam_anderen)
              for s in anderen]
    alles = [s for s in alles if s.tekst]
    alles.sort(key=lambda s: (s.start, s.spreker))
    samen: list[Segment] = []
    for s in alles:
        vorige = samen[-1] if samen else None
        if vorige and vorige.spreker == s.spreker and s.start - vorige.einde <= pauze:
            vorige.tekst = vorige.tekst + " " + s.tekst
            vorige.einde = max(vorige.einde, s.einde)
        else:
            samen.append(Segment(s.start, s.einde, s.tekst, s.spreker))
    return samen


def tijd(seconden: float) -> str:
    s = max(0, int(seconden))
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def datum_nl(ts: float) -> str:
    t = time.localtime(ts)
    return "%s %d %s %d, %02d:%02d" % (DAGEN[t.tm_wday], t.tm_mday, MAANDEN[t.tm_mon - 1],
                                        t.tm_year, t.tm_hour, t.tm_min)


def markdown(meta: dict, segmenten, model: str, sporen: str) -> str:
    start = meta.get("start") or time.time()
    einde = meta.get("einde") or start
    minuten = round((einde - start) / 60)
    duur = "minder dan een minuut" if minuten < 1 else "1 minuut" if minuten == 1 else "%d minuten" % minuten
    app = meta.get("app") or "meeting"
    regels = ["# Meeting via %s, %s" % (app, datum_nl(start)), "",
              "- Duur: %s" % duur,
              "- Opgenomen: %s" % sporen,
              "- Transcriptie: Whisper %s, op deze Mac" % model, ""]
    if meta.get("waarschuwing"):
        regels += ["> %s" % meta["waarschuwing"], ""]
    regels += ["---", ""]
    if not segmenten:
        regels += ["*Er is geen gesproken tekst gevonden in deze opname.*", ""]
    for s in segmenten:
        regels += ["**%s** (%s)  " % (s.spreker, tijd(s.start)), s.tekst, ""]
    return "\n".join(regels)


# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------

class Transcriber:
    """Houdt het Whisper-model vast, zodat het maar één keer geladen hoeft te worden."""

    def __init__(self, model: str = "large-v3-turbo", taal: str = "nl"):
        self.model_naam = model
        self.taal = taal or None
        self._model = None
        self._slot = threading.Lock()

    def model(self):
        with self._slot:
            if self._model is None:
                from faster_whisper import WhisperModel
                threads = max(1, (os.cpu_count() or 4) - 1)
                log.info("Whisper-model %s laden", self.model_naam)
                self._model = WhisperModel(self.model_naam, device="cpu", compute_type="int8",
                                           cpu_threads=threads)
            return self._model

    def spoor(self, audio, voortgang=None):
        segmenten, info = self.model().transcribe(
            audio, language=self.taal, beam_size=5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False)
        resultaat = []
        duur = getattr(info, "duration", 0) or 0
        for seg in segmenten:
            if voortgang and duur:
                voortgang(min(1.0, seg.end / duur))
            if getattr(seg, "no_speech_prob", 0) > 0.8 and getattr(seg, "avg_logprob", 0) < -1.0:
                continue
            if is_hallucinatie(seg.text):
                continue
            resultaat.append(Segment(seg.start, seg.end, seg.text.strip()))
        return resultaat


def verwerk(map_: str, transcriber: Transcriber, instellingen: dict, voortgang=None) -> str:
    """Transcribeert één meetingmap en schrijft transcript.md. Geeft het pad terug."""
    meta = lees_meta(map_)
    meta["status"] = "transcriberen"
    schrijf_meta(map_, meta)

    mic_pad = os.path.join(map_, MIC)
    sys_pad = os.path.join(map_, SYSTEEM)
    sporen = []
    ik: list[Segment] = []
    anderen: list[Segment] = []

    if os.path.exists(mic_pad):
        herstel_wav(mic_pad)
    stappen = [p for p in (mic_pad, sys_pad) if os.path.exists(p) and os.path.getsize(p) > 44]
    for i, pad in enumerate(stappen):
        try:
            audio = laad_audio(pad)
        except (OSError, EOFError, ValueError, wave.Error) as exc:
            log.warning("%s niet leesbaar: %s", os.path.basename(pad), exc)
            continue
        if not heeft_geluid(audio):
            log.info("%s is stil, overgeslagen", os.path.basename(pad))
            continue

        def deel(f, i=i):
            if voortgang:
                voortgang((i + f) / len(stappen))

        segmenten = transcriber.spoor(audio, deel)
        if pad == mic_pad:
            ik, sporen = segmenten, sporen + ["microfoon"]
        else:
            anderen, sporen = segmenten, sporen + ["systeemgeluid"]

    verschuiving = 0.0
    if meta.get("mic_start") and meta.get("systeem_start"):
        verschuiving = float(meta["systeem_start"]) - float(meta["mic_start"])
    # Echo alleen weghalen als er twee sporen zijn; op tijd van de microfoon vergelijken.
    if anderen:
        verschoven = [Segment(a.start + verschuiving, a.einde + verschuiving, a.tekst) for a in anderen]
        ik = verwijder_echo(ik, verschoven)

    segmenten = voeg_samen(ik, anderen, instellingen.get("naam_ik", "Ik"),
                           instellingen.get("naam_anderen", "Anderen"), verschuiving)
    tekst = markdown(meta, segmenten, transcriber.model_naam,
                     " en ".join(sporen) if sporen else "geen geluid")
    uit = os.path.join(map_, TRANSCRIPT)
    with open(uit + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(tekst)
    os.replace(uit + ".tmp", uit)

    if not instellingen.get("audio_bewaren", True):
        for pad in (mic_pad, sys_pad):
            if os.path.exists(pad):
                os.remove(pad)
    meta["status"] = "klaar"
    schrijf_meta(map_, meta)
    return uit


def wachtende_mappen(basis: str):
    """Meetings die wel opgenomen maar nog niet (helemaal) getranscribeerd zijn."""
    if not os.path.isdir(basis):
        return []
    mappen = []
    for naam in sorted(os.listdir(basis)):
        pad = os.path.join(basis, naam)
        if not os.path.isdir(pad) or os.path.exists(os.path.join(pad, TRANSCRIPT)):
            continue
        status = lees_meta(pad).get("status")
        if status in ("opgenomen", "transcriberen") or (
                status == "opname" and os.path.exists(os.path.join(pad, MIC))):
            mappen.append(pad)
    return mappen
