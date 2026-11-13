"""Instellingen van Notulist, bewaard als JSON in ~/Library/Application Support/Notulist."""
from __future__ import annotations

import json
import os

SUPPORT = os.path.expanduser("~/Library/Application Support/Notulist")
BESTAND = os.path.join(SUPPORT, "instellingen.json")

STANDAARD = {
    # Start vanzelf een opname zodra een meeting-app je microfoon gebruikt.
    "automatisch_opnemen": True,
    # Ook browsers (Google Meet, Teams of Zoom in een tabblad) als meeting tellen.
    "browsers_meenemen": True,
    # Zoveel seconden moet een meeting-app de microfoon gebruiken voordat de opname start.
    "start_na_seconden": 4,
    # Zoveel seconden na het einde van de meeting stopt de opname.
    "stop_na_seconden": 20,
    # Vangnet: is het zo lang helemaal stil (jij en de anderen), dan stopt de opname ook.
    "stilte_stop_minuten": 5,
    # Veiligheidsgrens: langer dan dit neemt Notulist niet op.
    "maximale_duur_minuten": 240,
    # Waar opnames en transcripties komen.
    "map": "~/Documents/Notulist",
    # Whisper-model: tiny, base, small, medium, large-v3 of large-v3-turbo (beste balans).
    "model": "large-v3-turbo",
    # Taal van de meetings ("nl", "en", ...) of "" om de taal zelf te laten herkennen.
    "taal": "nl",
    # Audiobestanden bewaren na het transcriberen.
    "audio_bewaren": True,
    # Na het uitschrijven vanzelf een samenvatting met actiepunten maken (vraagt een
    # Anthropic API-sleutel; het transcript gaat dan naar Claude).
    "samenvatten_automatisch": True,
    # Hoe jij en de anderen in het transcript heten.
    "naam_ik": "Ik",
    "naam_anderen": "Anderen",
}


def laad(pad: str | None = None) -> dict:
    pad = pad or BESTAND
    data = dict(STANDAARD)
    try:
        with open(pad, encoding="utf-8") as fh:
            eigen = json.load(fh)
        if isinstance(eigen, dict):
            data.update({k: v for k, v in eigen.items() if k in STANDAARD})
    except (OSError, ValueError):
        pass
    return data


def bewaar(data: dict, pad: str | None = None) -> None:
    pad = pad or BESTAND
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    tijdelijk = pad + ".tmp"
    with open(tijdelijk, "w", encoding="utf-8") as fh:
        json.dump({k: data.get(k, v) for k, v in STANDAARD.items()}, fh, indent=2,
                  ensure_ascii=False)
        fh.write("\n")
    os.replace(tijdelijk, pad)


def opnamemap(data: dict) -> str:
    return os.path.expanduser(data.get("map") or STANDAARD["map"])
