#!/bin/bash
# Installeert Schoonschip als echte Mac-app in je Programma's, met eigen icoon.

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

pauze() { echo ""; read -r -p "  Druk op Enter om dit venster te sluiten." _; }

echo ""
echo "  Schoonschip installeren"
echo "  -----------------------"

if [ "$(uname)" != "Darwin" ]; then
  echo "  Dit installatiescript is voor macOS."
  exit 1
fi
if ! schoonschip_omgeving "$HERE"; then pauze; exit 1; fi

if [ -w /Applications ]; then DEST_DIR="/Applications"; else DEST_DIR="$HOME/Applications"; fi
mkdir -p "$DEST_DIR"
APP="$DEST_DIR/Schoonschip.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Draait Schoonschip nog? Eerst stoppen.
"$SS_PYTHON" "$HERE/app/server.py" --stop >/dev/null 2>&1

# Programmabestanden naar een vaste plek, zodat je de gedownloade map daarna mag weggooien.
INSTALLED="$SS_SUPPORT/app"
rm -rf "$INSTALLED"
cp -R "$HERE/app" "$INSTALLED"
find "$INSTALLED" -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null

echo "  App bouwen..."
"$SS_PYTHON" - "$HERE/app/mac/Schoonschip.applescript" "$TMP/Schoonschip.applescript" "$SS_PYTHON" "$INSTALLED/server.py" <<'PY'
import sys
src, dst, python, server = sys.argv[1:5]
esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
text = open(src, encoding="utf-8").read()
text = text.replace("__PYTHON__", esc(python)).replace("__SERVER__", esc(server))
open(dst, "w", encoding="utf-8").write(text)
PY
rm -rf "$APP"
if ! osacompile -o "$APP" "$TMP/Schoonschip.applescript"; then
  echo "  Het bouwen van de app is mislukt."
  pauze; exit 1
fi

PL="$APP/Contents/Info.plist"
PB=/usr/libexec/PlistBuddy
$PB -c "Delete :CFBundleIdentifier" "$PL" >/dev/null 2>&1
$PB -c "Add :CFBundleIdentifier string nl.schoonschip.app" "$PL"
$PB -c "Delete :CFBundleName" "$PL" >/dev/null 2>&1
$PB -c "Add :CFBundleName string Schoonschip" "$PL"
# Geen Dock-icoon voor het startertje zelf: het venster heeft er al een.
$PB -c "Delete :LSUIElement" "$PL" >/dev/null 2>&1
$PB -c "Add :LSUIElement bool true" "$PL"

# Eigen icoon
if sips -s format icns "$HERE/app/mac/icon.png" --out "$TMP/schoonschip.icns" >/dev/null 2>&1; then
  cp "$TMP/schoonschip.icns" "$APP/Contents/Resources/applet.icns"
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
echo "  Tip voor een grondige schoonmaak: geef Schoonschip 'Volledige schijftoegang'."
echo "  Systeeminstellingen > Privacy en beveiliging > Volledige schijftoegang > + > kies Schoonschip."
echo "  Zonder die toegang slaat Schoonschip onder meer Mail en de Prullenmand-inhoud over."
echo ""
echo "  Klaar! Schoonschip staat bij je Programma's en is te vinden via Spotlight."
open "$APP"
pauze
