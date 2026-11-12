# Rekenblad

Een eenvoudig programma om Excel-bestanden te lezen en te bewerken op je Mac, zonder Excel.
Het draait helemaal op je eigen computer: er gaat niets naar internet. Het venster opent in je browser
(Safari, Chrome of een andere).

## Installeren (eenmalig)

1. Download deze map en zet hem ergens neer waar hij kan blijven staan, bijvoorbeeld in `Documenten`.
2. Open de app **Terminal** (via Spotlight: `⌘ spatie`, typ "Terminal").
3. Typ `bash ` (met een spatie erachter), sleep het bestand **Rekenblad.command** uit de Finder
   in het Terminal-venster en druk op Enter.

De eerste keer installeert Rekenblad wat het nodig heeft (ongeveer een minuut). Heeft je Mac nog geen
Python, dan verschijnt een venster van Apple om de "Command Line Tools" te installeren: klik op
Installeer en start Rekenblad daarna opnieuw.

**Daarna:** dubbelklik gewoon op `Rekenblad.command`. Geeft macOS de melding dat het bestand niet
gecontroleerd kan worden, ga dan naar Systeeminstellingen > Privacy en beveiliging en klik onderaan op
"Open toch". Of start het zoals in stap 3; dat werkt altijd.

Laat het Terminal-venster open zolang je werkt. Sluit het om Rekenblad te stoppen.

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
app/server.py     webserver op 127.0.0.1 en de API
app/workbook.py   openen, bewerken, ongedaan maken, opslaan
app/refs.py       verwijzingen in formules verschuiven
app/calc.py       formules uitrekenen
app/formats.py    Nederlandse weergave en invoer
app/static/       de editor (HTML, CSS, JavaScript)
tests/            tests: python3 -m unittest discover tests
```

Handmatig starten: `python3 app/server.py [bestand.xlsx]` (met openpyxl geïnstalleerd).
