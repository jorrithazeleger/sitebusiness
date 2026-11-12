#!/bin/bash
# Rekenblad starten in een Terminal-venster.
# Liever een echte app in je Dock die Excel-bestanden opent? Gebruik dan "Installeer Rekenblad.command".

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

echo ""
echo "  Rekenblad"
echo "  ---------"
if ! rekenblad_omgeving "$HERE"; then
  echo ""
  read -r -p "  Druk op Enter om dit venster te sluiten." _
  exit 1
fi
exec "$RB_PYTHON" "$HERE/app/server.py" "$@"
