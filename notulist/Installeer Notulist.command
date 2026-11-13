#!/bin/bash
# Installeert Notulist: een app in je menubalk die je meetings vanzelf opneemt en uitschrijft.

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

pauze() { echo ""; read -r -p "  Druk op Enter om dit venster te sluiten." _; }

echo ""
echo "  Notulist installeren"
echo "  --------------------"

if [ "$(uname)" != "Darwin" ]; then
  echo "  Dit installatiescript is voor macOS."
  exit 1
fi
MACOS_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
if [ "$MACOS_MAJOR" -lt 13 ]; then
  echo "  Notulist heeft macOS 13 (Ventura) of nieuwer nodig. Deze Mac heeft $(sw_vers -productVersion)."
  pauze; exit 1
fi
if [ "$MACOS_MAJOR" -lt 14 ]; then
  echo "  Let op: op macOS 13 kun je wel opnemen, maar start de opname niet vanzelf."
  echo "  Dat werkt vanaf macOS 14 (Sonoma)."
fi

# Command Line Tools (C-compiler en Swift) zijn nodig om de app te bouwen.
if ! xcode-select -p >/dev/null 2>&1; then
  echo ""
  echo "  Eerst zijn de 'Command Line Tools' van Apple nodig."
  echo "  Er verschijnt zo een venster. Klik op Installeer, wacht tot het klaar is"
  echo "  en start dit bestand daarna opnieuw."
  xcode-select --install >/dev/null 2>&1
  pauze; exit 1
fi

if ! notulist_omgeving "$HERE"; then pauze; exit 1; fi

if [ -w /Applications ]; then DEST_DIR="/Applications"; else DEST_DIR="$HOME/Applications"; fi
mkdir -p "$DEST_DIR"
APP="$DEST_DIR/Notulist.app"

# Draait Notulist nog? Eerst stoppen.
osascript -e 'tell application id "nl.notulist.app" to quit' >/dev/null 2>&1
pkill -f "Notulist.app/Contents/MacOS/Notulist" >/dev/null 2>&1
sleep 1

# Programmabestanden naar een vaste plek, zodat je de gedownloade map daarna mag weggooien.
INSTALLED="$NB_SUPPORT/app"
rm -rf "$INSTALLED"
cp -R "$HERE/app" "$INSTALLED"
find "$INSTALLED" -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null

echo "  App bouwen..."
if ! "$NB_PYTHON" "$INSTALLED/mac/bouw_app.py" "$APP" "$INSTALLED/notulist.py" "$INSTALLED/mac/audiocap.swift"; then
  echo "  Het bouwen van de app is mislukt."
  pauze; exit 1
fi
echo "  Geinstalleerd in $APP"

# Whisper-model alvast downloaden, zodat de eerste meeting meteen uitgeschreven kan worden.
MODEL="$("$NB_PYTHON" -c "import sys; sys.path.insert(0, '$INSTALLED'); import instellingen; print(instellingen.laad()['model'])")"
echo ""
echo "  Spraakherkenning ($MODEL) downloaden. Eenmalig, ongeveer 1,5 GB..."
if "$NB_PYTHON" -c "from faster_whisper import WhisperModel; WhisperModel('$MODEL', device='cpu', compute_type='int8')" >/dev/null 2>&1; then
  echo "  Klaar."
else
  echo "  Downloaden lukte nu niet. Notulist probeert het opnieuw bij de eerste meeting."
fi

# Automatisch starten als je inlogt.
AGENT="$HOME/Library/LaunchAgents/nl.notulist.app.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>nl.notulist.app</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-g</string>
    <string>$APP</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
PLIST
echo "  Notulist start voortaan vanzelf als je inlogt."

echo ""
echo "  Klaar! Rechtsboven in je menubalk staat nu een microfoontje."
echo ""
echo "  macOS vraagt zo om twee toestemmingen. Klik bij allebei op Sta toe:"
echo "    1. Microfoon: om jou op te nemen."
echo "    2. Scherm- en systeemaudio-opname: om de anderen in de meeting op te nemen."
echo "       Notulist neemt alleen geluid op, geen beeld. Na deze toestemming vraagt macOS"
echo "       soms om Notulist opnieuw te starten: kies dan in het menu 'Stop Notulist' en open"
echo "       Notulist weer via Spotlight."
open "$APP"
pauze
