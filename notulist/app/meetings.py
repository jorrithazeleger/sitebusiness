"""De bibliotheek met meetings: elke meeting is een map in de opnamemap.

Een map bevat meta.json en, afhankelijk van hoe ver de verwerking is, mic.wav, systeem.wav,
transcript.md, transcript.json, samenvatting.json en opname.m4a (om terug te luisteren).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from opname import META, MIC, SYSTEEM, lees_meta, schrijf_meta
from transcriptie import AFSPEEL_M4A, AFSPEEL_WAV, TRANSCRIPT, TRANSCRIPT_JSON, datum_nl, tijd

GELDIGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def pad_van(basis: str, meeting_id: str) -> str | None:
    """Het pad van een meeting, of None als de id niet bestaat of niet klopt."""
    if not meeting_id or not GELDIGE_ID.match(meeting_id):
        return None
    pad = os.path.join(basis, meeting_id)
    return pad if os.path.isfile(os.path.join(pad, META)) else None


def alle_ids(basis: str):
    if not os.path.isdir(basis):
        return []
    ids = [d for d in os.listdir(basis) if pad_van(basis, d)]
    return sorted(ids, key=lambda d: (lees_meta(os.path.join(basis, d)).get("start") or 0, d),
                  reverse=True)


def titel_van(meta: dict) -> str:
    if meta.get("titel"):
        return meta["titel"]
    if meta.get("ai_titel"):
        return meta["ai_titel"]
    app = meta.get("app") or ""
    if not app or app == "handmatig":
        return "Opname"
    return "Meeting via %s" % app


def _lees_json(pad: str):
    try:
        with open(pad, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def afspeelbestand(map_: str) -> str | None:
    for naam in (AFSPEEL_M4A, AFSPEEL_WAV, MIC, SYSTEEM):
        pad = os.path.join(map_, naam)
        if os.path.exists(pad) and os.path.getsize(pad) > 44:
            return pad
    return None


def overzicht(basis: str, meeting_id: str) -> dict:
    """Wat de lijst in het venster per meeting toont."""
    map_ = os.path.join(basis, meeting_id)
    meta = lees_meta(map_)
    start = meta.get("start") or os.path.getmtime(map_)
    einde = meta.get("einde")
    return {
        "id": meeting_id,
        "titel": titel_van(meta),
        "app": meta.get("app") or "",
        "start": start,
        "duur": (einde - start) if einde else None,
        "status": meta.get("status") or "",
        "transcript": os.path.exists(os.path.join(map_, TRANSCRIPT)),
        "samenvatting": os.path.exists(os.path.join(map_, "samenvatting.json")),
    }


def lijst(basis: str):
    return [overzicht(basis, i) for i in alle_ids(basis)]


def detail(basis: str, meeting_id: str) -> dict | None:
    map_ = pad_van(basis, meeting_id)
    if not map_:
        return None
    meta = lees_meta(map_)
    data = overzicht(basis, meeting_id)
    data["waarschuwing"] = meta.get("waarschuwing")
    data["eigen_titel"] = bool(meta.get("titel"))
    transcript = _lees_json(os.path.join(map_, TRANSCRIPT_JSON))
    if transcript:
        data["segmenten"] = transcript.get("segmenten", [])
        data["model"] = transcript.get("model")
        data["sporen"] = transcript.get("sporen")
    elif data["transcript"]:
        # Ouder transcript zonder JSON: toon de tekst zoals hij is.
        with open(os.path.join(map_, TRANSCRIPT), encoding="utf-8") as fh:
            data["tekst"] = fh.read()
    data["samenvatting_data"] = _lees_json(os.path.join(map_, "samenvatting.json"))
    data["fout_samenvatting"] = meta.get("fout_samenvatting")
    data["gedaan"] = meta.get("gedaan", [])
    data["audio"] = afspeelbestand(map_) is not None
    return data


def _platte_tekst(map_: str) -> str:
    stukken = []
    transcript = _lees_json(os.path.join(map_, TRANSCRIPT_JSON))
    if transcript:
        stukken += [s.get("tekst", "") for s in transcript.get("segmenten", [])]
    elif os.path.exists(os.path.join(map_, TRANSCRIPT)):
        with open(os.path.join(map_, TRANSCRIPT), encoding="utf-8") as fh:
            stukken.append(fh.read())
    samenvatting = _lees_json(os.path.join(map_, "samenvatting.json")) or {}
    stukken.append(samenvatting.get("samenvatting", ""))
    for veld in ("punten", "besluiten", "open_vragen"):
        stukken += samenvatting.get(veld) or []
    stukken += [a.get("wat", "") for a in samenvatting.get("actiepunten") or []]
    return " ".join(stukken)


def zoek(basis: str, vraag: str):
    """Meetings waarin alle woorden van de vraag voorkomen (titel, transcript of samenvatting),
    met een stukje tekst rond de eerste treffer."""
    woorden = [w for w in vraag.lower().split() if w]
    if not woorden:
        return lijst(basis)
    resultaat = []
    for meeting_id in alle_ids(basis):
        item = overzicht(basis, meeting_id)
        tekst = _platte_tekst(os.path.join(basis, meeting_id))
        doorzocht = (item["titel"] + " " + item["app"] + " " + tekst).lower()
        if not all(w in doorzocht for w in woorden):
            continue
        plek = tekst.lower().find(woorden[0])
        if plek >= 0:
            begin = max(0, plek - 50)
            fragment = tekst[begin:plek + 90].strip()
            item["fragment"] = ("…" if begin else "") + fragment + "…"
        resultaat.append(item)
    return resultaat


def wijzig(basis: str, meeting_id: str, titel=None, gedaan=None) -> bool:
    """Titel aanpassen (leeg = terug naar de automatische titel) en/of bijhouden welke
    actiepunten zijn afgevinkt (lijst met nummers)."""
    map_ = pad_van(basis, meeting_id)
    if not map_:
        return False
    meta = lees_meta(map_)
    if titel is not None:
        titel = " ".join(str(titel).split())[:200]
        if titel:
            meta["titel"] = titel
        else:
            meta.pop("titel", None)
    if gedaan is not None:
        meta["gedaan"] = sorted({int(i) for i in gedaan if isinstance(i, int) and i >= 0})
    schrijf_meta(map_, meta)
    return True


def naar_prullenmand(basis: str, meeting_id: str, prullenmand: str | None = None) -> bool:
    """Verplaatst een meeting naar de prullenmand van de Mac (terug te zetten vanuit de Finder)."""
    map_ = pad_van(basis, meeting_id)
    if not map_:
        return False
    prullenmand = prullenmand or os.path.expanduser("~/.Trash")
    os.makedirs(prullenmand, exist_ok=True)
    doel = os.path.join(prullenmand, "Notulist " + meeting_id)
    n = 2
    while os.path.exists(doel):
        doel = os.path.join(prullenmand, "Notulist %s %d" % (meeting_id, n))
        n += 1
    shutil.move(map_, doel)
    return True


def als_tekst(basis: str, meeting_id: str) -> str | None:
    """Samenvatting plus transcript als platte tekst, om te kopiëren of te exporteren."""
    data = detail(basis, meeting_id)
    if not data:
        return None
    regels = [data["titel"], datum_nl(data["start"]), ""]
    s = data.get("samenvatting_data")
    if s:
        regels += [s.get("samenvatting", ""), ""]
        for kop, veld in (("Belangrijkste punten", "punten"), ("Besluiten", "besluiten"),
                          ("Open vragen", "open_vragen")):
            if s.get(veld):
                regels += [kop + ":"] + ["- " + p for p in s[veld]] + [""]
        if s.get("actiepunten"):
            regels.append("Actiepunten:")
            for a in s["actiepunten"]:
                extra = ", ".join(x for x in (a.get("wie"), a.get("wanneer")) if x)
                regels.append("- %s%s" % (a.get("wat", ""), " (%s)" % extra if extra else ""))
            regels.append("")
    if data.get("segmenten"):
        regels += ["Transcript", ""]
        for seg in data["segmenten"]:
            regels += ["%s (%s): %s" % (seg["spreker"], tijd(seg["start"]), seg["tekst"])]
    elif data.get("tekst"):
        regels.append(data["tekst"])
    return "\n".join(regels).strip() + "\n"


def exportnaam(basis: str, meeting_id: str) -> str:
    """Bestandsnaam voor een export: datum, titel, zonder vreemde tekens."""
    data = overzicht(basis, meeting_id)
    datum = time.strftime("%Y%m%d", time.localtime(data["start"]))
    titel = re.sub(r"[^a-z0-9]+", "-", data["titel"].lower()).strip("-")[:40] or "meeting"
    return "%s-notulen-%s.txt" % (datum, titel)
