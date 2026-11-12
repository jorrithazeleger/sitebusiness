#!/bin/bash
# Schoonschip starten in een Terminal-venster (zonder installatie).
# Liever een echte app met icoon? Gebruik dan "Installeer Schoonschip.command".

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
. "$HERE/app/mac/omgeving.sh"

echo ""
echo "  Schoonschip"
echo "  -----------"
if ! schoonschip_omgeving "$HERE"; then
  echo ""
  read -r -p "  Druk op Enter om dit venster te sluiten." _
  exit 1
fi
exec "$SS_PYTHON" "$HERE/app/server.py" "$@"
