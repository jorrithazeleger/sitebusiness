# Notulist

Neemt je meetings op, schrijft ze uit en maakt er notulen met actiepunten van. Start je een meeting in
Zoom, Teams, Google Meet of een andere app, dan begint Notulist vanzelf met opnemen. Als de meeting
voorbij is stopt de opname en schrijft Notulist hem uit, op je eigen Mac. Er komt geen bot in je
meeting. In het venster van Notulist vind je al je meetings terug, met zoeken, terugluisteren en de
notulen.

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

Bijwerken naar een nieuwe versie gaat op dezelfde manier: draai het installatiescript van de nieuwe
versie. Je meetings en instellingen blijven bewaard.

## Het venster

Open het venster via het microfoontje in de menubalk (**Open Notulist**, of `⌘O` in dat menu), of
dubbelklik op Notulist in Programma's. Zolang het venster open is, staat Notulist ook in het Dock.

- **Links** staan je meetings, nieuwste bovenaan. Bovenin start je zelf een opname (**Neem nu op**) en
  zet je het vanzelf opnemen aan of uit.
- **Zoeken** (`⌘F`) doorzoekt titels, transcripten en notulen van al je meetings.
- **Een meeting** laat zien:
  - **Notulen**: samenvatting, actiepunten (af te vinken), besluiten, belangrijkste punten en open
    vragen. Zie [Notulen met Claude](#notulen-met-claude);
  - **Transcript**: wie wat zei, met tijden. Klik op een tijd om vanaf daar te luisteren; tijdens het
    afspelen licht de zin op die je hoort;
  - een **speler** om terug te luisteren, ook op 1,25 tot 2 keer de snelheid;
  - **Kopieer** zet notulen en transcript op je klembord, **Exporteer** bewaart ze als tekstbestand in
    Downloads. Onder **⋯** vind je Toon in Finder, Opnieuw uitschrijven en Verplaats naar prullenmand.
  - Klik op de titel om hem te veranderen.
- **Tijdens een opname** zie je de tijd meelopen en twee meters: jouw geluid en dat van de anderen.
  Zo zie je meteen of beide sporen binnenkomen.
- **Instellingen** (tandwiel linksonder): alles wat je kunt aanpassen, plus **Controleer
  toestemmingen** en het logboek.

`⌘Q` sluit alleen het venster: Notulist blijft in de menubalk meetings opnemen. Helemaal stoppen doe
je via het microfoontje in de menubalk, **Stop Notulist**.

## Hoe Notulist een meeting herkent

- **Begin**: zodra een meeting-app een paar seconden je microfoon gebruikt, start de opname. Je krijgt
  een melding en het microfoontje in de menubalk krijgt een stip, met de tijd erachter.
- **Einde**: zodra de meeting-app je microfoon loslaat, stopt de opname na 20 seconden. Een app die
  alleen nog geluid afspeelt (Teams en Zoom doen dat na een meeting soms nog lang) telt niet meer mee.
- **Vangnet**: houdt een app je microfoon na de meeting toch vast (dat doen browsers soms), dan stopt
  de opname als het 5 minuten helemaal stil is gebleven. Notulist begint dan pas weer een opname als
  die app de microfoon eerst heeft losgelaten.
- **Zelf stoppen** kan altijd: in het venster of via het menubalk-icoon. Notulist begint dan niet
  opnieuw aan dezelfde meeting.

Herkend worden Zoom, Microsoft Teams, Webex, Slack-huddles, FaceTime, Discord, WhatsApp, Skype en GoTo,
plus meetings in een browser (Chrome, Edge, Safari, Firefox, Arc, Brave, Vivaldi, Opera), zoals Google
Meet of Teams in een tabblad. Een browser telt mee zodra die je microfoon gebruikt; dat kun je
uitzetten bij Instellingen.

Stopt of start een opname niet zoals je verwacht? In het logboek (Instellingen > Logboek) staat bij
elke verandering welke apps je microfoon gebruikten. Stuur die regels mee als je hulp vraagt.

## Notulen met Claude

Notulist kan van elk transcript notulen maken: een samenvatting, actiepunten met wie en wanneer,
besluiten, belangrijkste punten en open vragen. Ook krijgt de meeting dan een titel die zegt waar hij
over ging. Dat doet Claude, het taalmodel van Anthropic.

- Hiervoor heb je een **API-sleutel** van Anthropic nodig. Maak er een op console.anthropic.com en vul
  hem in bij Instellingen > Notulen met Claude. De sleutel komt in de sleutelhanger van je Mac.
- **Privacy**: alleen het transcript gaat naar Anthropic, de opname zelf niet. Zonder sleutel gaat
  er niets van Notulist naar internet.
- **Kosten**: je betaalt Anthropic per gebruik. Voor een meeting van een uur is dat grofweg tien tot
  twintig cent.
- Standaard maakt Notulist de notulen vanzelf na elke meeting. Liever per meeting kiezen? Zet dat uit
  bij Instellingen; dan staat er bij elke meeting een knop **Maak notulen**.
- Claude werkt met wat de spraakherkenning ervan gemaakt heeft. Controleer daarom namen en bedragen.

## Waar alles staat

Elke meeting is een map in `Documenten/Notulist`, bijvoorbeeld `20261113-1430-zoom`:

- `transcript.md` en `samenvatting.md`: transcript en notulen, leesbaar in elke teksteditor;
- `opname.m4a`: de opname om terug te luisteren (beide sporen samen);
- `mic.wav` en `systeem.wav`: de losse sporen van jou en van de anderen;
- `transcript.json`, `samenvatting.json` en `meta.json`: dezelfde gegevens voor het venster.

## Goed om te weten

- **Vertel de anderen dat je opneemt.** Dat is netjes, en voor zakelijke gesprekken vaak ook
  verplicht onder de AVG.
- **Koptelefoon of speakers**: met een koptelefoon zijn jij en de anderen netjes gescheiden. Met
  speakers vangt je microfoon de anderen ook op; Notulist haalt zulke dubbele zinnen er zo goed
  mogelijk uit.
- **Wie er sprak**: Notulist weet alleen of iets via je microfoon of via je speakers binnenkwam. Spreken
  er meerdere anderen, dan staan die allemaal onder **Anderen**. In de notulen gebruikt Claude namen als
  die in het gesprek vallen.
- **Snelheid**: het uitschrijven gebeurt na de meeting, op de achtergrond. Reken bij een meeting van
  een uur op een kwartier of langer, afhankelijk van je Mac. Te traag? Kies een sneller model bij
  Instellingen. Nog een meeting gepland? Die wordt gewoon opgenomen; het transcript volgt daarna.
- **Ruimte**: een uur opname is ongeveer 250 MB. Zet **Opnames bewaren** uit als je alleen de
  transcripten en notulen wilt houden.
- **macOS 15 en nieuwer** vraagt af en toe of Notulist je scherm en systeemaudio mag blijven opnemen.
  Kies dan **Sta toe**.
- **Opnieuw geïnstalleerd?** Dan vraagt macOS de toestemmingen soms opnieuw.
- **Vanzelf opnemen** werkt vanaf macOS 14 (Sonoma). Op macOS 13 kun je alleen zelf opnemen.
- Wissel je midden in een meeting van microfoon (bijvoorbeeld AirPods erbij), dan blijft Notulist de
  microfoon gebruiken waarmee de opname begon.
- Stopt Notulist onverwacht tijdens een meeting, dan schrijft Notulist bij de volgende start alsnog uit
  wat er al was opgenomen.

**Verwijderen**: stop Notulist via het menubalk-icoon, gooi `Notulist.app` uit Programma's weg en
verwijder `~/Library/LaunchAgents/nl.notulist.app.plist` en de map `~/Library/Application Support/Notulist`.
Je meetings in `Documenten/Notulist` blijven bewaard. De API-sleutel wis je bij Instellingen, of in de
app Sleutelhangertoegang (zoek op "Notulist").

## Voor wie wil sleutelen

```
app/notulist.py      start de app: menubalk (rumps), venster en server
app/kern.py          de regie: herkennen, opnemen, uitschrijven, samenvatten
app/detectie.py      welke app gebruikt de microfoon (CoreAudio, macOS 14+) en wanneer telt dat als meeting
app/opname.py        microfoon (sounddevice) en systeemgeluid (via notulist-audiocap) naar WAV
app/transcriptie.py  Whisper (faster-whisper), echo's en verzonnen zinnen eruit, afspeelbestand
app/samenvatting.py  notulen met Claude, API-sleutel in de sleutelhanger
app/meetings.py      de bibliotheek: lijst, zoeken, wijzigen, exporteren, prullenmand
app/server.py        kleine webserver op 127.0.0.1 voor het venster
app/venster.py       het venster (WKWebView) en het menu bovenin het scherm
app/web/             de pagina in het venster (HTML, CSS, JavaScript)
app/instellingen.py  instellingen in ~/Library/Application Support/Notulist/instellingen.json
app/mac/audiocap.swift  systeemgeluid opnemen met ScreenCaptureKit
app/mac/bouw_app.py     bouwt Notulist.app (klein C-startprogramma dat Python laadt, plus audiocap)
app/mac/teken_menubalk_iconen.py  tekent de menubalk-iconen in app/iconen
tests/               python3 -m unittest discover tests
```

Handige commando's (met de Python uit `~/Library/Application Support/Notulist/venv`):

- `python app/notulist.py --diagnose` laat zien welke apps nu audio gebruiken en of Notulist een
  meeting ziet.
- `python app/notulist.py --transcribeer <map>` schrijft een meeting (opnieuw) uit.

Het logboek staat in `~/Library/Logs/Notulist.log`.
