# Schoonschip

Een programma om je Mac op te ruimen: rommel weg, ruimte terug. Het draait helemaal op je eigen computer:
er gaat niets naar internet.

## Installeren (eenmalig)

1. Pak de zip uit, bijvoorbeeld in je map Downloads.
2. Open de app **Terminal** (via Spotlight: `⌘ spatie`, typ "Terminal").
3. Typ `bash ` (met een spatie erachter), sleep **Installeer Schoonschip.command** uit de Finder in het
   Terminal-venster en druk op Enter.

Het script:
- installeert wat Schoonschip nodig heeft (eenmalig, ongeveer een minuut). Heeft je Mac nog geen Python,
  dan verschijnt een venster van Apple om de "Command Line Tools" te installeren. Klik op Installeer en
  start het script daarna opnieuw;
- zet **Schoonschip.app** bij je Programma's, met een eigen icoon.

Daarna mag je de uitgepakte map weggooien.

### Volledige schijftoegang (aanrader)

Zonder deze toestemming kan Schoonschip niet in Mail en in de Prullenmand kijken. Zo geef je hem:
**Systeeminstellingen > Privacy en beveiliging > Volledige schijftoegang**, klik op **+** en kies
Schoonschip uit Programma's. Stop Schoonschip daarna (`⌘Q`) en open het opnieuw. In de app staat ook een
knop die die instelling voor je opent.

## Wat het kan

| Onderdeel | Wat het doet |
|---|---|
| **Overzicht** | Hoe vol je schijf en geheugen zijn, hoe lang je Mac al aan staat, en welke programma's nu het meeste geheugen gebruiken (met een Stop-knop). **Scan mijn Mac** zoekt alles in één keer en ruimt met één klik de veilige rommel op. |
| **Systeemrommel** | Caches, caches van Slack, Teams, Discord, VS Code en Chrome-profielen, logbestanden, bouwbestanden van Xcode, npm en Gradle, geopende mailbijlagen, oude iPhone- en iPad-reservekopieen en de Prullenmand. |
| **Grote bestanden** | De grootste bestanden in je eigen mappen (vanaf 50 MB tot 1 GB, jij kiest), te filteren op soort. Werkt via Spotlight, dus binnen een paar seconden. |
| **Downloads** | Wat er in Downloads staat, met installatiebestanden (.dmg, .pkg) en alles van langer dan 3 maanden geleden apart. |
| **Dubbele bestanden** | Bestanden met precies dezelfde inhoud, in je thuismap of een map die je kiest. Van elke groep blijft de oudste staan. |
| **Ruimtekaart** | Hoe groot elke map is. Klik door tot je ziet waar je ruimte blijft. |
| **Programma's** | Al je programma's met grootte en wanneer je ze voor het laatst gebruikte. Verwijder een programma helemaal: ook voorkeuren, caches en andere bestanden die het in je bibliotheek achterliet. |
| **Opstarten** | Wat er vanzelf met je Mac meestart. Kapotte onderdelen (van programma's die al weg zijn) staan bovenaan. |
| **Onderhoud** | DNS-cache legen, werkgeheugen vrijmaken, voorvertoningen vernieuwen, de 'Open met'-lijst opschonen, lokale Time Machine-snapshots verwijderen, Spotlight opnieuw indexeren en de schijf controleren. Sommige taken vragen je wachtwoord; dat gaat via het gewone venster van macOS. |

## Hoe veilig is het?

- **Je ziet altijd eerst wat er weggaat**, en kunt elk vinkje weghalen. Met het oogje toon je iets in de Finder.
- **Jouw bestanden gaan naar de Prullenmand**: grote bestanden, downloads, dubbele bestanden, programma's en
  reservekopieen. Je haalt ze terug zolang je de Prullenmand niet leegt.
- **Meteen verwijderd wordt alleen wat je Mac zelf opnieuw maakt**: caches, logbestanden en bouwbestanden.
  Daarbij blijft de map zelf staan, alleen de inhoud gaat weg.
- **Nooit aangeraakt**: je Sleutelhanger, iCloud Drive, Mail-berichten, Berichten, de bibliotheken van Foto's
  en Muziek, de systeemmappen van macOS, en alles buiten je eigen thuismap (behalve programma's die jij kiest).
  Caches van iCloud en downloads die nog bezig zijn worden overgeslagen.
- Caches van macOS zelf en van programma's die open zijn staan standaard **uit**.
- Alleen het Schoonschip-venster kan opdrachten geven: elke sessie heeft een geheim sleutelwoord, zodat een
  website in je browser nooit iets op je Mac kan weggooien.

## Gebruiken

- Open Schoonschip via Programma's, Spotlight of het Dock. Sluit je het venster, dan stopt het.
- De Prullenmand legen vraagt de eerste keer of Schoonschip de Finder mag besturen. Klik op OK: de Finder
  doet het legen.
- Een programma verwijderen lukt alleen als het niet open is. Programma's uit de App Store vragen soms om je
  wachtwoord.
- **Opgeruimd**: linksonder zie je hoeveel je in totaal al hebt opgeruimd.

Liever zonder installatie? Start dan `Schoonschip.command` (op dezelfde manier als stap 3). Schoonschip
opent dan in je browser en draait zolang dat Terminal-venster openstaat.

**Verwijderen:** gooi `Schoonschip.app` uit Programma's weg en verwijder de map
`~/Library/Application Support/Schoonschip`.

## Voor wie wil sleutelen

```
app/server.py     webserver op 127.0.0.1, achtergrondtaken en de API (ook --open, --status, --stop)
app/scans.py      alle scans en het opruimen zelf
app/veilig.py     wat er weg mag en hoe (Prullenmand of meteen), grootte meten
app/venster.py    eigen Mac-venster via pywebview
app/mac/          de Mac-app (AppleScript), installatiehulp en icoon
app/static/       de app (HTML, CSS, JavaScript)
tests/            tests: python3 -m unittest discover tests
```

Handmatig starten: `python3 app/server.py`.
