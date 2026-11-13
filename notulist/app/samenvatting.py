"""Samenvatting, besluiten en actiepunten van een meeting, gemaakt door Claude.

Dit is het enige onderdeel van Notulist dat iets naar internet stuurt: het transcript gaat naar
de Claude API van Anthropic. Het werkt alleen als je zelf een API-sleutel invult (die staat in
de sleutelhanger van je Mac) of als ANTHROPIC_API_KEY is ingesteld.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time

from opname import lees_meta, schrijf_meta

log = logging.getLogger("notulist")

MODEL = "claude-opus-5-5"
SAMENVATTING = "samenvatting.json"
SAMENVATTING_MD = "samenvatting.md"
DIENST = "nl.notulist.anthropic"  # naam in de sleutelhanger
ACCOUNT = "notulist"

SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "samenvatting": {"type": "string"},
        "punten": {"type": "array", "items": {"type": "string"}},
        "besluiten": {"type": "array", "items": {"type": "string"}},
        "actiepunten": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "wat": {"type": "string"},
                    "wie": {"type": "string"},
                    "wanneer": {"type": "string"},
                },
                "required": ["wat", "wie", "wanneer"],
                "additionalProperties": False,
            },
        },
        "open_vragen": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titel", "samenvatting", "punten", "besluiten", "actiepunten", "open_vragen"],
    "additionalProperties": False,
}

SYSTEEM = """Je maakt notulen van een meeting op basis van een automatisch gemaakt transcript.

Het transcript komt uit spraakherkenning en bevat fouten, vooral in namen, vakjargon en
getallen. Herstel die stilzwijgend als duidelijk is wat bedoeld werd, maar voeg niets toe dat
niet gezegd is. Twijfel je over een naam of bedrag, neem het dan over zoals het er staat.

Sprekers: "{ik}" is degene voor wie je de notulen maakt. "{anderen}" zijn alle andere
deelnemers samen; dat kunnen meerdere mensen zijn. Noem mensen bij naam als die naam in het
gesprek valt, en schrijf over "{ik}" in de derde persoon met die naam als die bekend is.

Schrijf in de taal van de meeting, helder en zakelijk, in korte zinnen. Gebruik geen
gedachtestreepjes.

- titel: waar de meeting over ging, hooguit acht woorden, zonder datum.
- samenvatting: twee tot vijf zinnen over doel en uitkomst.
- punten: de belangrijkste onderwerpen en wat erover gezegd is, één zin per punt.
- besluiten: wat er is afgesproken of besloten. Leeg als er niets besloten is.
- actiepunten: concrete taken die iemand op zich neemt. "wie" is de naam, "{ik}" als het de
  gebruiker is, of leeg als onduidelijk. "wanneer" is de genoemde termijn, of leeg.
- open_vragen: wat nog uitgezocht of beantwoord moet worden. Leeg als er niets openstaat.

Is het transcript te kort of te onduidelijk voor notulen, zeg dat dan in de samenvatting en laat
de lijsten leeg."""


class SamenvattingFout(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# API-sleutel in de sleutelhanger
# ---------------------------------------------------------------------------

_bewaard = {"tijd": 0.0, "sleutel": None}


def lees_sleutel(vers: bool = False) -> str | None:
    """De API-sleutel uit de sleutelhanger (een halve minuut onthouden, want het venster vraagt
    elke seconde of samenvatten kan)."""
    if sys.platform != "darwin":
        return None
    if not vers and time.time() - _bewaard["tijd"] < 30:
        return _bewaard["sleutel"]
    r = subprocess.run(["security", "find-generic-password", "-s", DIENST, "-a", ACCOUNT, "-w"],
                       capture_output=True, text=True)
    sleutel = r.stdout.strip()
    _bewaard["sleutel"] = sleutel if r.returncode == 0 and sleutel else None
    _bewaard["tijd"] = time.time()
    return _bewaard["sleutel"]


def bewaar_sleutel(sleutel: str) -> None:
    sleutel = sleutel.strip()
    if not sleutel:
        raise SamenvattingFout("Vul een API-sleutel in.")
    if sys.platform != "darwin":
        raise SamenvattingFout("De sleutelhanger is alleen beschikbaar op macOS.")
    r = subprocess.run(["security", "add-generic-password", "-U", "-s", DIENST, "-a", ACCOUNT,
                        "-l", "Notulist (Anthropic API)", "-w", sleutel],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SamenvattingFout("Bewaren in de sleutelhanger lukte niet: %s" % r.stderr.strip())
    lees_sleutel(vers=True)


def wis_sleutel() -> None:
    if sys.platform == "darwin":
        subprocess.run(["security", "delete-generic-password", "-s", DIENST, "-a", ACCOUNT],
                       capture_output=True)
        lees_sleutel(vers=True)


def beschikbaar() -> bool:
    return bool(lees_sleutel() or os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Samenvatten
# ---------------------------------------------------------------------------

def _tijd(seconden: float) -> str:
    s = max(0, int(seconden))
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def transcript_tekst(segmenten) -> str:
    return "\n".join("[%s] %s: %s" % (_tijd(s["start"]), s["spreker"], s["tekst"]) for s in segmenten)


def lees_segmenten(map_: str):
    pad = os.path.join(map_, "transcript.json")
    try:
        with open(pad, encoding="utf-8") as fh:
            return json.load(fh).get("segmenten", [])
    except (OSError, ValueError):
        return []


def vraag_claude(systeem: str, inhoud: str, client=None) -> dict:
    """Stuurt het transcript naar Claude en geeft de samenvatting terug als dict."""
    import anthropic
    if client is None:
        sleutel = lees_sleutel(vers=True)
        client = anthropic.Anthropic(api_key=sleutel) if sleutel else anthropic.Anthropic()
    try:
        antwoord = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            # Weigert het model om veiligheidsredenen, dan probeert de API het met een ander model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            system=systeem,
            messages=[{"role": "user", "content": inhoud}],
        )
    except anthropic.AuthenticationError:
        raise SamenvattingFout("De API-sleutel klopt niet. Controleer hem bij Instellingen.")
    except anthropic.PermissionDeniedError:
        raise SamenvattingFout("Deze API-sleutel mag Claude niet gebruiken.")
    except anthropic.RateLimitError:
        raise SamenvattingFout("Even te veel verzoeken bij Anthropic. Probeer het over een minuut opnieuw.")
    except anthropic.BadRequestError as exc:
        raise SamenvattingFout("Claude kon dit verzoek niet verwerken: %s" % exc.message)
    except anthropic.APIStatusError as exc:
        raise SamenvattingFout("Anthropic gaf een fout (%s). Probeer het later opnieuw." % exc.status_code)
    except anthropic.APIConnectionError:
        raise SamenvattingFout("Geen verbinding met Anthropic. Controleer je internet.")

    if antwoord.stop_reason == "refusal":
        raise SamenvattingFout("Claude wilde deze meeting niet samenvatten.")
    if antwoord.stop_reason == "max_tokens":
        raise SamenvattingFout("De samenvatting werd te lang. Probeer het opnieuw.")
    tekst = next((b.text for b in antwoord.content if b.type == "text"), "")
    try:
        data = json.loads(tekst)
    except ValueError:
        raise SamenvattingFout("Claude gaf een onleesbaar antwoord. Probeer het opnieuw.")
    log.info("samenvatting gemaakt (request %s)", getattr(antwoord, "_request_id", "?"))
    return data


def markdown(data: dict, titel: str) -> str:
    regels = ["# %s" % titel, "", data.get("samenvatting", ""), ""]

    def lijst(kop, items):
        if items:
            regels.extend(["## %s" % kop, ""] + ["- %s" % i for i in items] + [""])

    lijst("Belangrijkste punten", data.get("punten"))
    lijst("Besluiten", data.get("besluiten"))
    acties = []
    for a in data.get("actiepunten") or []:
        extra = ", ".join(x for x in (a.get("wie"), a.get("wanneer")) if x)
        acties.append("[ ] %s%s" % (a.get("wat", ""), " (%s)" % extra if extra else ""))
    lijst("Actiepunten", acties)
    lijst("Open vragen", data.get("open_vragen"))
    return "\n".join(regels)


def maak(map_: str, config: dict, client=None) -> dict:
    """Maakt de samenvatting van één meeting en bewaart die naast het transcript."""
    segmenten = lees_segmenten(map_)
    if not segmenten:
        raise SamenvattingFout("Er is nog geen transcript om samen te vatten.")
    meta = lees_meta(map_)
    ik = config.get("naam_ik") or "Ik"
    anderen = config.get("naam_anderen") or "Anderen"
    start = meta.get("start") or time.time()
    duur = max(1, round(((meta.get("einde") or start) - start) / 60))
    inhoud = ("Meeting via %s op %s, ongeveer %d minuten.\n\n<transcript>\n%s\n</transcript>" % (
        meta.get("app") or "onbekend", time.strftime("%d-%m-%Y %H:%M", time.localtime(start)),
        duur, transcript_tekst(segmenten)))
    data = vraag_claude(SYSTEEM.format(ik=ik, anderen=anderen), inhoud, client)
    data["model"] = MODEL
    data["gemaakt"] = time.time()
    with open(os.path.join(map_, SAMENVATTING + ".tmp"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(os.path.join(map_, SAMENVATTING + ".tmp"), os.path.join(map_, SAMENVATTING))
    meta = lees_meta(map_)
    if data.get("titel"):
        meta["ai_titel"] = data["titel"].strip()
        schrijf_meta(map_, meta)
    titel = meta.get("titel") or meta.get("ai_titel") or "Meeting"
    with open(os.path.join(map_, SAMENVATTING_MD), "w", encoding="utf-8") as fh:
        fh.write(markdown(data, titel))
    return data
