#!/bin/bash
# Installeert Rekenblad als echte Mac-app, zodat je Excel-bestanden uit Downloads,
# de Finder of je mail met een dubbelklik in Rekenblad opent.

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

pauze() { echo ""; read -r -p "  Druk op Enter om dit venster te sluiten." _; }

echo ""
echo "  Rekenblad installeren"
echo "  ---------------------"

if [ "$(uname)" != "Darwin" ]; then
  echo "  Dit installatiescript is voor macOS."
  exit 1
fi
if ! rekenblad_omgeving "$HERE"; then pauze; exit 1; fi

# Waar komt de app: in /Programma's als dat mag, anders in de Programma's-map van je gebruiker.
if [ -w /Applications ]; then DEST_DIR="/Applications"; else DEST_DIR="$HOME/Applications"; fi
mkdir -p "$DEST_DIR"
APP="$DEST_DIR/Rekenblad.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Draait Rekenblad nog? Eerst netjes stoppen.
"$RB_PYTHON" "$HERE/app/server.py" --stop --force >/dev/null 2>&1
osascript -e 'tell application id "nl.rekenblad.app" to quit' >/dev/null 2>&1

# Programmabestanden naar een vaste plek, zodat je de gedownloade map daarna mag weggooien.
INSTALLED="$RB_SUPPORT/app"
rm -rf "$INSTALLED"
cp -R "$HERE/app" "$INSTALLED"
find "$INSTALLED" -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null

echo "  App bouwen..."
"$RB_PYTHON" - "$HERE/app/mac/Rekenblad.applescript" "$TMP/Rekenblad.applescript" "$RB_PYTHON" "$INSTALLED/server.py" <<'PY'
import sys
src, dst, python, server = sys.argv[1:5]
esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
text = open(src, encoding="utf-8").read()
text = text.replace("__PYTHON__", esc(python)).replace("__SERVER__", esc(server))
open(dst, "w", encoding="utf-8").write(text)
PY
rm -rf "$APP"
if ! osacompile -o "$APP" "$TMP/Rekenblad.applescript"; then
  echo "  Het bouwen van de app is mislukt."
  pauze; exit 1
fi

# Vertel macOS welke bestanden Rekenblad kan openen.
PL="$APP/Contents/Info.plist"
PB=/usr/libexec/PlistBuddy
$PB -c "Delete :CFBundleIdentifier" "$PL" >/dev/null 2>&1
$PB -c "Add :CFBundleIdentifier string nl.rekenblad.app" "$PL"
$PB -c "Delete :CFBundleName" "$PL" >/dev/null 2>&1
$PB -c "Add :CFBundleName string Rekenblad" "$PL"
$PB -c "Delete :CFBundleDocumentTypes" "$PL" >/dev/null 2>&1
$PB -c "Add :CFBundleDocumentTypes array" "$PL"
$PB -c "Add :CFBundleDocumentTypes:0 dict" "$PL"
$PB -c "Add :CFBundleDocumentTypes:0:CFBundleTypeName string Spreadsheet" "$PL"
$PB -c "Add :CFBundleDocumentTypes:0:CFBundleTypeRole string Editor" "$PL"
$PB -c "Add :CFBundleDocumentTypes:0:LSHandlerRank string Alternate" "$PL"
$PB -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes array" "$PL"
i=0
for t in org.openxmlformats.spreadsheetml.sheet org.openxmlformats.spreadsheetml.sheet.macroenabled public.comma-separated-values-text; do
  $PB -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes:$i string $t" "$PL"
  i=$((i + 1))
done

# Eigen icoon
if sips -s format icns "$HERE/app/mac/icon.png" --out "$TMP/rekenblad.icns" >/dev/null 2>&1; then
  for name in applet droplet; do cp "$TMP/rekenblad.icns" "$APP/Contents/Resources/$name.icns"; done
  $PB -c "Delete :CFBundleIconName" "$PL" >/dev/null 2>&1
  rm -f "$APP/Contents/Resources/Assets.car"
  $PB -c "Delete :CFBundleIconFile" "$PL" >/dev/null 2>&1
  $PB -c "Add :CFBundleIconFile string applet" "$PL"
fi

# Opnieuw ondertekenen (nodig na het aanpassen, zeker op Macs met Apple-chip) en aanmelden bij macOS.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREG" ] && "$LSREG" -f "$APP" >/dev/null 2>&1
touch "$APP"

echo "  Geinstalleerd in $APP"
echo ""

# Standaardprogramma
read -r -p "  Wil je dat .xlsx-bestanden voortaan met een dubbelklik in Rekenblad openen? (j/n) " antwoord
if [[ "$antwoord" =~ ^[jJyY] ]]; then
  read -r -p "  Ook .csv-bestanden? (j/n) " csv
  extra=""
  [[ "$csv" =~ ^[jJyY] ]] && extra="csv"
  echo "  Even geduld, dit kan een halve minuut duren..."
  if command -v swift >/dev/null 2>&1 && xcode-select -p >/dev/null 2>&1 \
      && swift "$HERE/app/mac/standaard.swift" "$APP" $extra 2>"$TMP/fout.txt"; then
    echo "  Gelukt. Excel-bestanden openen nu in Rekenblad."
  else
    echo "  Dat lukte niet automatisch. Zo stel je het zelf in (eenmalig):"
    echo "    1. Klik in de Finder met de rechtermuisknop op een .xlsx-bestand en kies 'Toon info'."
    echo "    2. Kies bij 'Open met' voor Rekenblad."
    echo "    3. Klik op 'Wijzig alles…' en bevestig."
  fi
else
  echo "  Prima. Je kunt een bestand altijd openen via rechtermuisklik > Open met > Rekenblad."
fi

echo ""
echo "  Klaar! Rekenblad staat bij je Programma's en is te vinden via Spotlight."
echo "  Elk bestand opent in een eigen venster. Stoppen doe je met ⌘Q, zoals elke app."
open "$APP"
pauze
