# Notulist

Neemt je meetings op en schrijft ze uit, helemaal op je eigen Mac. Start je een meeting in Zoom,
Teams, Google Meet of een andere app, dan begint Notulist vanzelf met opnemen. Als de meeting voorbij is
stopt de opname en maakt Notulist er een transcript van. Er gaat niets naar internet en er komt geen bot
in je meeting.

## Installeren (eenmalig)

1. Pak de map uit, bijvoorbeeld in Downloads.
2. Open de app **Terminal** (via Spotlight: `⌘ spatie`, typ "Terminal").
3. Typ `bash ` (met een spatie erachter), sleep **Installeer Notulist.command** uit de Finder in het
   Terminal-venster en druk op Enter.

Het script:
- installeert wat Notulist nodig heeft. Heeft je Mac nog geen "Command Line Tools" van Apple, dan
  verschijnt eerst een venster om die te installeren. Klik op Installeer en start het script daarna opnieuw;
- zet **Notulist.app** bij je Programma's;
- downloadt de spraakherkenning (eenmalig ongeveer 1,5 GB);
- zorgt dat Notulist voortaan vanzelf start als je inlogt.

Daarna vraagt macOS om twee toestemmingen. Klik bij allebei op **Sta toe**:
1. **Microfoon**: om op te nemen wat jij zegt.
2. **Scherm- en systeemaudio-opname**: om op te nemen wat de anderen zeggen. Notulist neemt alleen
   geluid op, geen beeld. Vraagt macOS daarna om Notulist opnieuw te starten, kies dan in het menu
   **Stop Notulist** en open Notulist weer via Spotlight.

Daarna mag je de uitgepakte map weggooien.

## Gebruiken

Rechtsboven in je menubalk staat een microfoontje. Verder hoef je niets te doen.

- **Meeting begint**: zodra een meeting-app een paar seconden je microfoon gebruikt, start de opname.
  Je krijgt een melding, het microfoontje krijgt een stip en de tijd loopt mee (12:34).
- **Meeting klaar**: ongeveer 20 seconden nadat de meeting-app je microfoon loslaat, stopt de opname.
  Het icoon wordt een paar tekstregels met een percentage terwijl Notulist het transcript maakt. Je krijgt een melding
  als het klaar is.
- **Transcripten**: in het menu onder **Recente meetings**, of in de map `Documenten/Notulist`. Elke
  meeting krijgt een eigen map, bijvoorbeeld `20261113-1430-zoom`, met daarin:
  - `transcript.md`: het transcript, met tijden en wie er sprak (**Ik** of **Anderen**);
  - `mic.wav` en `systeem.wav`: de opnames van jou en van de anderen;
  - `meta.json`: gegevens over de opname.
- **Zelf opnemen**: kies **Neem nu op** in het menu, bijvoorbeeld voor een gesprek aan tafel. Zo'n
  opname stopt pas als jij op **Stop opname** klikt.
- **Eerder stoppen**: klik op **Stop opname**. Notulist begint dan niet opnieuw aan dezelfde meeting.
- **Automatisch opnemen uitzetten**: haal het vinkje weg bij **Automatisch opnemen bij meetings**.

Werkt het niet zoals verwacht? Kies **Controleer toestemmingen** in het menu. Notulist laat dan zien
wat in orde is en wat niet.

### Welke meetings herkent Notulist?

Zoom, Microsoft Teams, Webex, Slack-huddles, FaceTime, Discord, WhatsApp, Skype en GoTo, plus meetings
in een browser (Chrome, Edge, Safari, Firefox, Arc, Brave, Vivaldi, Opera), zoals Google Meet of Teams
in een tabblad. Browsers tellen mee zodra ze je microfoon gebruiken. Ook als je bijvoorbeeld een
spraakbericht inspreekt start dan een opname; dat kun je uitzetten met `browsers_meenemen` (zie
Instellingen).

## Instellingen

Kies **Instellingen aanpassen...** in het menu. Er opent een tekstbestand; bewaar het en start
Notulist opnieuw.

| Instelling | Standaard | Betekenis |
|---|---|---|
| `automatisch_opnemen` | `true` | Vanzelf opnemen bij een meeting |
| `browsers_meenemen` | `true` | Ook meetings in de browser opnemen |
| `start_na_seconden` | `4` | Zo lang moet een app je microfoon gebruiken voor de opname start |
| `stop_na_seconden` | `20` | Zo lang na de meeting stopt de opname |
| `maximale_duur_minuten` | `240` | Langer dan dit neemt Notulist niet op |
| `map` | `~/Documents/Notulist` | Waar de meetings komen |
| `model` | `large-v3-turbo` | Spraakherkenning. `small` of `medium` is sneller maar minder nauwkeurig |
| `taal` | `nl` | Taal van je meetings. Leeg (`""`) laat Notulist de taal zelf herkennen |
| `audio_bewaren` | `true` | Op `false` worden de opnames na het transcriberen weggegooid |
| `naam_ik`, `naam_anderen` | `Ik`, `Anderen` | Hoe de sprekers in het transcript heten |

## Goed om te weten

- **Vertel de anderen dat je opneemt.** Dat is netjes, en voor zakelijke gesprekken vaak ook
  verplicht onder de AVG.
- **Koptelefoon of speakers**: met een koptelefoon zijn jij en de anderen netjes gescheiden. Met
  speakers vangt je microfoon de anderen ook op; Notulist haalt zulke dubbele zinnen er zo goed
  mogelijk uit.
- **Wie er sprak**: Notulist weet alleen of iets via je microfoon of via je speakers binnenkwam. Spreken
  er meerdere anderen, dan staan die allemaal onder **Anderen**.
- **Snelheid**: het transcriberen gebeurt na de meeting, op de achtergrond. Reken bij een meeting van
  een uur op een kwartier of langer, afhankelijk van je Mac. Te traag? Zet `model` op `medium` of
  `small`. Nog een meeting gepland? Die wordt gewoon opgenomen; het transcript volgt daarna.
- **Ruimte**: een uur opname is ongeveer 230 MB. Zet `audio_bewaren` op `false` als je alleen de
  transcripten wilt houden.
- **macOS 15 en nieuwer** vraagt af en toe of Notulist je scherm en systeemaudio mag blijven opnemen.
  Kies dan **Sta toe**.
- **Opnieuw geïnstalleerd?** Dan vraagt macOS de toestemmingen soms opnieuw.
- **Automatisch starten** werkt vanaf macOS 14 (Sonoma). Op macOS 13 kun je alleen zelf opnemen.
- Wissel je midden in een meeting van microfoon (bijvoorbeeld AirPods erbij), dan blijft Notulist de
  microfoon gebruiken waarmee de opname begon.
- Stopt Notulist onverwacht tijdens een meeting, dan maakt Notulist bij de volgende start alsnog een
  transcript van wat er al was opgenomen.

**Verwijderen**: stop Notulist via het menu, gooi `Notulist.app` uit Programma's weg en verwijder
`~/Library/LaunchAgents/nl.notulist.app.plist` en de map `~/Library/Application Support/Notulist`.
Je meetings in `Documenten/Notulist` blijven bewaard.

## Voor wie wil sleutelen

```
app/notulist.py      menubalk-app (rumps) en de regie: herkennen, opnemen, transcriberen
app/detectie.py      welke app gebruikt de microfoon (CoreAudio, macOS 14+) en wanneer telt dat als meeting
app/opname.py        microfoon (sounddevice) en systeemgeluid (via notulist-audiocap) naar WAV
app/transcriptie.py  Whisper (faster-whisper), echo's en verzonnen zinnen eruit, Markdown schrijven
app/instellingen.py  instellingen in ~/Library/Application Support/Notulist/instellingen.json
app/mac/audiocap.swift  systeemgeluid opnemen met ScreenCaptureKit
app/mac/bouw_app.py     bouwt Notulist.app (klein C-startprogramma dat Python laadt, plus audiocap)
app/mac/teken_menubalk_iconen.py  tekent de menubalk-iconen in app/iconen
tests/               python3 -m unittest discover tests
```

Handige commando's (met de Python uit `~/Library/Application Support/Notulist/venv`):

- `python app/notulist.py --diagnose` laat zien welke apps nu audio gebruiken en of Notulist een
  meeting ziet.
- `python app/notulist.py --transcribeer <map>` maakt (opnieuw) een transcript van een meeting.

Het logboek staat in `~/Library/Logs/Notulist.log` (ook via het menu).
