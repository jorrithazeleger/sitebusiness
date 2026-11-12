#!/bin/bash
# Rekenblad starten: dubbelklik dit bestand in de Finder.
# De eerste keer installeert het de benodigdheden (duurt ongeveer een minuut).

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
SUPPORT="$HOME/Library/Application Support/Rekenblad"
VENV="$SUPPORT/venv"

echo ""
echo "  Rekenblad"
echo "  ---------"

# Python zoeken (macOS heeft python3 na installatie van de Command Line Tools)
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 /usr/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo ""
  echo "  Python 3 is nog niet geinstalleerd."
  echo "  Er verschijnt zo een venster van Apple om de 'Command Line Tools' te installeren."
  echo "  Klik op Installeer, wacht tot het klaar is en dubbelklik daarna opnieuw op Rekenblad.command."
  xcode-select --install >/dev/null 2>&1
  echo ""
  read -r -p "  Druk op Enter om dit venster te sluiten." _
  exit 1
fi

REQ_HASH="$(shasum "$HERE/requirements.txt" | cut -d' ' -f1)-$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ ! -x "$VENV/bin/python" ] || [ "$(cat "$VENV/.rekenblad-req" 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "  Eerste keer opstarten: benodigdheden installeren..."
  mkdir -p "$SUPPORT"
  rm -rf "$VENV"
  if ! "$PY" -m venv "$VENV"; then
    echo "  Kon geen Python-omgeving maken."
    read -r -p "  Druk op Enter om te sluiten." _
    exit 1
  fi
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip >/dev/null 2>&1
  if ! "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r "$HERE/requirements.txt"; then
    echo ""
    echo "  Installeren is niet gelukt. Controleer je internetverbinding en probeer het opnieuw."
    rm -rf "$VENV"
    read -r -p "  Druk op Enter om te sluiten." _
    exit 1
  fi
  echo "$REQ_HASH" > "$VENV/.rekenblad-req"
  echo "  Klaar."
fi

exec "$VENV/bin/python" "$HERE/app/server.py" "$@"
