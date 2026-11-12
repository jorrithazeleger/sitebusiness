# Rekenblad

Een eenvoudig programma om Excel-bestanden te lezen en te bewerken op je Mac, zonder Excel.
Het draait helemaal op je eigen computer: er gaat niets naar internet. Het venster opent in je browser
(Safari, Chrome of een andere).

## Installeren (eenmalig)

1. Pak de zip uit, bijvoorbeeld in je map Downloads.
2. Open de app **Terminal** (via Spotlight: `⌘ spatie`, typ "Terminal").
3. Typ `bash ` (met een spatie erachter), sleep **Installeer Rekenblad.command** uit de Finder in het
   Terminal-venster en druk op Enter.

Het script:
- installeert wat Rekenblad nodig heeft (eenmalig, ongeveer een minuut). Heeft je Mac nog geen Python,
  dan verschijnt een venster van Apple om de "Command Line Tools" te installeren. Klik op Installeer en
  start het script daarna opnieuw;
- zet **Rekenblad.app** bij je Programma's, met een eigen icoon;
- vraagt of .xlsx-bestanden (en eventueel .csv) voortaan met een dubbelklik in Rekenblad openen.

Daarna mag je de uitgepakte map weggooien.

## Gebruiken

- Rekenblad opent in **eigen vensters**, net als Excel of Numbers: elk bestand in een eigen venster,
  met het Rekenblad-icoon in het Dock.
- **Dubbelklik op een Excel-bestand** in Downloads, de Finder of als bijlage in Mail om het in Rekenblad
  te openen. Heb je Rekenblad niet als standaard ingesteld, kies dan rechtermuisklik > **Open met > Rekenblad**.
- `⌘N` opent een nieuw leeg venster, `⌘O` opent een bestand (in een nieuw venster als dit venster al
  iets toont), `⌘W` sluit het venster en `⌘Q` stopt Rekenblad. Heb je nog iets niet bewaard, dan vraagt
  Rekenblad eerst: Bewaar, Annuleer of Niet bewaren.
- **Bijlagen uit je mail** zijn tijdelijke kopieën. Daarom vraagt Rekenblad bij Opslaan waar je het
  bestand wilt bewaren.
- **Vangnet**: stopt Rekenblad onverwacht terwijl er nog iets niet bewaard is, dan staat een kopie in
  `~/.rekenblad/herstel`.
- De eerste keer dat je een bestand uit Downloads opent, vraagt macOS of Rekenblad bij die map mag.
  Klik op Sta toe.
- **Dock**: Rekenblad heeft één eigen icoon in het Dock. Je kunt het daar vastzetten zoals elke app.
  (Alleen als je Mac geen Command Line Tools heeft, bouwt het installatiescript een eenvoudigere versie;
  dan staat er tijdens het werken een Python-icoon in het Dock.)
- Lukt het openen van een eigen venster niet, dan opent Rekenblad zichzelf in de browser.

Liever zonder installatie? Start dan `Rekenblad.command` (op dezelfde manier als stap 3). Rekenblad draait
dan zolang dat Terminal-venster openstaat.

**Verwijderen:** gooi `Rekenblad.app` uit Programma's weg en verwijder de map
`~/Library/Application Support/Rekenblad`.

## Wat het kan

- **Openen**: `.xlsx`, `.xlsm` (macro's blijven bewaard) en `.csv`. Via de knop Openen (het gewone
  Mac-bestandsvenster), door een bestand in het venster te slepen, of uit de lijst met recente bestanden.
- **Bewerken**: klik op een cel en typ. Enter of dubbelklik om een cel aan te passen.
  Nederlandse notatie werkt: `12,50`, `1.234,56`, `15%`, `€ 9,95`, `12-11-2026`.
- **Formules**: Engelse en Nederlandse schrijfwijze kunnen allebei, bijvoorbeeld `=SOM(A1:A5;B1)` of
  `=SUM(A1:A5,B1)`. Rekenblad rekent de gangbare functies zelf uit (SOM, GEMIDDELDE, ALS, ALS.FOUT,
  SOM.ALS, AANTAL.ALS, VERT.ZOEKEN, X.ZOEKEN, INDEX, VERGELIJKEN, AFRONDEN, datums, tekstfuncties en meer).
  Een functie die Rekenblad niet kent, zie je schuin en okergeel; die rekent Excel of Numbers uit zodra je
  het bestand daar opent.
- **Rijen en kolommen** invoegen en verwijderen (werkbalk of rechtermuisklik). Formules, samengevoegde
  cellen, tabellen, keuzelijsten en voorwaardelijke opmaak schuiven netjes mee, zoals in Excel.
- **Opmaak**: vet, cursief, vulkleur, tekstkleur, uitlijning, getalnotatie, kolombreedte (sleep de rand
  van een kolomkop).
- **Bladen**: wisselen, toevoegen (+), hernoemen (dubbelklik) en verwijderen (rechtermuisklik).
- **Zoeken en vervangen** in één blad of alle bladen (`⌘F`).
- **Kopiëren en plakken**, ook van en naar Excel, Numbers of Google Sheets.
- **Ongedaan maken** (`⌘Z`) en opnieuw (`⇧⌘Z`).
- **Opslaan** (`⌘S`) overschrijft het bestand; **Opslaan als** kiest een nieuwe plek. Exporteren als
  `.xlsx` of het huidige blad als `.csv`.
- Selecteer cellen met getallen en onderin zie je de som, het gemiddelde en het aantal.

## Sneltoetsen

| Toets | Doet |
|---|---|
| Pijltjes, Tab, Enter | Bewegen en bewerken |
| `⇧` + pijltjes of klik | Selectie uitbreiden |
| `⌘` + pijltje | Naar de rand van de gegevens springen |
| Backspace | Selectie leegmaken |
| `⌘C` / `⌘X` / `⌘V` | Kopiëren, knippen, plakken |
| `⌘Z` / `⇧⌘Z` | Ongedaan maken, opnieuw |
| `⌘B` / `⌘I` | Vet, cursief |
| `⌘S` / `⌘O` / `⌘F` | Opslaan, openen, zoeken |

## Goed om te weten

- **Reservekopie**: de eerste keer dat je een bestaand bestand overschrijft, bewaart Rekenblad het origineel
  in `~/.rekenblad/reservekopieen` (de laatste 30).
- Rekenblad gebruikt de bibliotheek openpyxl. Grafieken en afbeeldingen blijven bewaard. **Vormen,
  tekstvakken, slicers, SmartArt en formulierknoppen gaan verloren bij opslaan**; Rekenblad waarschuwt je
  als een bestand die bevat.
- Oude `.xls`-bestanden worden niet ondersteund. Open ze in Numbers en bewaar ze als `.xlsx`.
- Rijhoogtes worden niet getoond (alle rijen even hoog), maar blijven in het bestand gewoon bewaard.

## Voor wie wil sleutelen

```
app/server.py     webserver op 127.0.0.1 en de API (ook --open, --status, --stop)
app/venster.py    eigen Mac-vensters via pywebview
app/mac/          bouw_app.py bouwt Rekenblad.app (klein C-startprogramma dat Python laadt),
                  plus terugval-app (AppleScript), installatiehulp en icoon
app/workbook.py   openen, bewerken, ongedaan maken, opslaan
app/refs.py       verwijzingen in formules verschuiven
app/calc.py       formules uitrekenen
app/formats.py    Nederlandse weergave en invoer
app/static/       de editor (HTML, CSS, JavaScript)
tests/            tests: python3 -m unittest discover tests
```

Handmatig starten: `python3 app/server.py [bestand.xlsx]` (met openpyxl geïnstalleerd).
