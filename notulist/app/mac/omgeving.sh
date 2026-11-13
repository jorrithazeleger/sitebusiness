# Gebruikt door Installeer Notulist.command.
# Zoekt Python 3 en zet een eigen omgeving met Whisper en de opnamebibliotheken klaar in ~/Library/Application Support/Notulist.
# Na afloop staat het pad naar die Python in $NB_PYTHON.

NB_SUPPORT="$HOME/Library/Application Support/Notulist"
NB_VENV="$NB_SUPPORT/venv"
NB_PYTHON="$NB_VENV/bin/python"

notulist_omgeving() {
  local root="$1" py="" candidate req_hash
  for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      py="$candidate"
      break
    fi
  done
  if [ -z "$py" ]; then
    echo ""
    echo "  Python 3 is nog niet geinstalleerd."
    echo "  Er verschijnt zo een venster van Apple om de 'Command Line Tools' te installeren."
    echo "  Klik op Installeer, wacht tot het klaar is en start dit bestand daarna opnieuw."
    xcode-select --install >/dev/null 2>&1
    return 1
  fi
  req_hash="$(shasum "$root/requirements.txt" | cut -d' ' -f1)-$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if [ -x "$NB_PYTHON" ] && [ "$(cat "$NB_VENV/.notulist-req" 2>/dev/null)" = "$req_hash" ]; then
    return 0
  fi
  echo "  Benodigdheden installeren (eenmalig, een paar minuten)..."
  mkdir -p "$NB_SUPPORT"
  rm -rf "$NB_VENV"
  if ! "$py" -m venv "$NB_VENV"; then
    echo "  Kon geen Python-omgeving maken."
    return 1
  fi
  "$NB_PYTHON" -m pip install --quiet --disable-pip-version-check --upgrade pip >/dev/null 2>&1
  if ! "$NB_PYTHON" -m pip install --quiet --disable-pip-version-check -r "$root/requirements.txt"; then
    echo "  Installeren is niet gelukt. Controleer je internetverbinding en probeer het opnieuw."
    rm -rf "$NB_VENV"
    return 1
  fi
  echo "$req_hash" > "$NB_VENV/.notulist-req"
  echo "  Klaar."
  return 0
}
