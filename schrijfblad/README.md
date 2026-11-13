# Schrijfblad

Een programma om Word-documenten te lezen en te bewerken op je Mac, zonder Word.
Het draait helemaal op je eigen computer: er gaat niets naar internet.
Schrijfblad is de broer van Rekenblad (voor Excel) en werkt op dezelfde manier.

## Installeren (eenmalig)

1. Pak de zip uit, bijvoorbeeld in je map Downloads.
2. Open de app **Terminal** (via Spotlight: `⌘ spatie`, typ "Terminal").
3. Typ `bash ` (met een spatie erachter), sleep **Installeer Schrijfblad.command** uit de Finder in het
   Terminal-venster en druk op Enter.

Het script:
- installeert wat Schrijfblad nodig heeft (eenmalig, ongeveer een minuut). Heeft je Mac nog geen Python,
  dan verschijnt een venster van Apple om de "Command Line Tools" te installeren. Klik op Installeer en
  start het script daarna opnieuw;
- zet **Schrijfblad.app** bij je Programma's, met een eigen icoon;
- vraagt of .docx-bestanden (en eventueel oude .doc-bestanden) voortaan met een dubbelklik in
  Schrijfblad openen.

Daarna mag je de uitgepakte map weggooien.

Liever zonder installatie? Start dan `Schrijfblad.command` (op dezelfde manier als stap 3). Schrijfblad
draait dan in je browser zolang dat Terminal-venster openstaat.

**Verwijderen:** gooi `Schrijfblad.app` uit Programma's weg en verwijder de map
`~/Library/Application Support/Schrijfblad`.

## Gebruiken

- Schrijfblad opent in **eigen vensters**: elk document in een eigen venster, met het Schrijfblad-icoon
  in het Dock.
- **Dubbelklik op een Word-bestand** in Downloads, de Finder of als bijlage in Mail. Heb je Schrijfblad
  niet als standaard ingesteld, kies dan rechtermuisklik > **Open met > Schrijfblad**.
- Je typt gewoon in de pagina. Wijzigingen gaan na een fractie van een seconde naar het document in het
  geheugen; met **Opslaan** (`⌘S`) schrijf je ze naar het bestand.
- `⌘N` nieuw venster, `⌘O` openen, `⌘W` venster sluiten, `⌘Q` stoppen. Heb je nog iets niet bewaard,
  dan vraagt Schrijfblad eerst: Bewaar, Annuleer of Niet bewaren.
- **Bijlagen uit je mail** zijn tijdelijke kopieën. Daarom vraagt Schrijfblad bij Opslaan waar je het
  bestand wilt bewaren.
- **Vangnet**: stopt Schrijfblad onverwacht terwijl er nog iets niet bewaard is, dan staat een kopie in
  `~/.schrijfblad/herstel`.

## Wat het kan

- **Openen**: `.docx`, `.docm` (macro's blijven bewaard, maar worden niet uitgevoerd) en `.dotx`.
  Oude `.doc`-bestanden en `.rtf` en `.odt` zet Schrijfblad om naar `.docx` (met het hulpprogramma
  textutil van macOS); `.txt` opent als nieuw document.
- **Tekst bewerken** met behoud van de opmaak uit Word: lettertype, grootte, kleur, vet, cursief enz.
  Alleen de alinea's die je aanpast worden opnieuw opgebouwd; de rest van het bestand blijft precies
  zoals het was.
- **Opmaak**: vet, cursief, onderstreept, doorgehaald, superscript, subscript, tekstkleur, markeerkleur,
  tekengrootte en opmaak wissen.
- **Opmaakprofielen** uit het document (Standaard, Titel, Kop 1, Kop 2 …). Sneltoetsen: `⌥⌘1` t/m `⌥⌘3`
  voor koppen, `⌥⌘0` voor Standaard. Na Enter in een kop ga je verder met het volgende profiel.
- **Uitlijning**: links, midden, rechts en uitvullen.
- **Opsommingen en nummering**, met niveaus: `Tab` en `⇧Tab` aan het begin van een lijstpunt. Tweemaal
  Enter beëindigt de lijst.
- **Tabellen**: invoegen (kies het formaat in het menu), rijen en kolommen toevoegen of verwijderen
  (werkbalk of rechtermuisklik in een cel). `Tab` springt naar de volgende cel.
- **Afbeeldingen** invoegen via de werkbalk, door te plakken of door een afbeelding in het venster te
  slepen. Bestaande afbeeldingen blijven staan en kun je verwijderen.
- **Links** (`⌘K`). `⌘`-klik opent een link in je browser.
- **Pagina-einde** (`⌘Enter`).
- **Kop- en voettekst** bewerken of toevoegen (boven en onder op de pagina).
- **Bijgehouden wijzigingen**: je ziet ze in groen en rood en kunt ze allemaal accepteren of afwijzen.
- **Zoeken en vervangen** (`⌘F`).
- **Ongedaan maken** (`⌘Z`) en opnieuw (`⇧⌘Z`).
- **Plakken** uit Word, een webpagina of een ander document: koppen, vet, cursief, links en lijsten
  komen mee, de rest wordt netjes gemaakt.
- **Exporteren** als Word-document, Markdown of platte tekst, en **afdrukken of bewaren als PDF**
  (`⌘P`; vanuit een eigen venster opent de afdrukversie in je browser).
- Onderin zie je het aantal woorden en tekens en kun je zoomen.

## Goed om te weten

- **Reservekopie**: de eerste keer dat je een bestaand bestand overschrijft, bewaart Schrijfblad het
  origineel in `~/.schrijfblad/reservekopieen` (de laatste 30).
- Schrijfblad toont het document als één doorlopende pagina; waar Word een nieuwe pagina begint zie je
  hier dus niet (een handmatig pagina-einde wel).
- **Blijft bewaard maar is hier niet te bewerken**: tekstvakken en vormen, grafieken, formules,
  inhoudsopgaven en andere velden, voetnoten (je ziet het nummer), opmerkingen (💬, de tekst staat in
  de tooltip). Bladwijzers en verwijzingen blijven bij hun tekst staan.
- Lettertypen die niet op je Mac staan (zoals Calibri zonder Office) worden vervangen door een gelijkend
  lettertype op het scherm; in het bestand blijft het oorspronkelijke lettertype staan.
- Bij meerdere secties zie je de kop- en voettekst van de laatste sectie.

## Sneltoetsen

| Toets | Doet |
|---|---|
| `⌘B` / `⌘I` / `⌘U` | Vet, cursief, onderstrepen |
| `⌘K` | Link |
| `⌥⌘1` … `⌥⌘3`, `⌥⌘0` | Kop 1 … 3, Standaard |
| `Tab` / `⇧Tab` | Lijstniveau of volgende/vorige tabelcel |
| `⌘Enter` | Pagina-einde |
| `⌘Z` / `⇧⌘Z` | Ongedaan maken, opnieuw |
| `⌘S` / `⇧⌘S` | Opslaan, opslaan als |
| `⌘O` / `⌘N` / `⌘F` / `⌘P` | Openen, nieuw, zoeken, afdrukken |

## Voor wie wil sleutelen

```
app/server.py     webserver op 127.0.0.1 en de API (ook --open, --status, --stop)
app/venster.py    eigen Mac-vensters via pywebview
app/document.py   openen, weergeven als HTML, wijzigingen terugschrijven, ongedaan maken, opslaan
app/styles.py     opmaakprofielen, thema-lettertypen en nummering naar CSS
app/ooxml.py      hulpmiddelen voor Word-XML (volgorde van elementen, tekstopmaak)
app/mac/          bouw_app.py bouwt Schrijfblad.app, plus terugval-app, installatiehulp en icoon
app/static/       de editor (HTML, CSS, JavaScript)
tests/            tests: python3 -m unittest discover tests
```

Hoe het werkt: de editor is een bewerkbare HTML-pagina. Elke alinea en tabel heeft een id die de server
kent; opmaak, afbeeldingen en andere onderdelen worden bij id genoemd. Na het typen stuurt de editor alleen
de gewijzigde alinea's naar de server, die ze in de Word-XML opnieuw opbouwt. Onzichtbare onderdelen
(bladwijzers, opmerkingbereiken, veldcodes) onthoudt de server per alinea met hun tekstpositie en zet ze
daar weer terug.

Handmatig starten: `python3 app/server.py [bestand.docx]` (met python-docx geïnstalleerd).
