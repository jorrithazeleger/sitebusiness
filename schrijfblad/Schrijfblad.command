#!/bin/bash
# Schrijfblad starten in een Terminal-venster.
# Liever een echte app in je Dock die Word-bestanden opent? Gebruik dan "Installeer Schrijfblad.command".

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

echo ""
echo "  Schrijfblad"
echo "  -----------"
if ! schrijfblad_omgeving "$HERE"; then
  echo ""
  read -r -p "  Druk op Enter om dit venster te sluiten." _
  exit 1
fi
exec "$SB_PYTHON" "$HERE/app/server.py" "$@"
