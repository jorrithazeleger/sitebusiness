"""Veiligheid: wat Schoonschip mag weggooien, en hoe.

Twee manieren van opruimen:
- "trash":  naar de Prullenmand. Terug te halen zolang je de Prullenmand niet leegt.
            Voor alles wat van jou is: bestanden, downloads, programma's, reservekopieen.
- "delete": meteen weg. Alleen voor dingen die macOS en je programma's zelf opnieuw maken:
            caches, logbestanden en bouwbestanden van ontwikkeltools.

De browser stuurt nooit een pad om weg te gooien, alleen het nummer van een gevonden onderdeel.
Toch controleert elk pad hier nog een keer of het binnen de toegestane plekken valt.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time

IS_MAC = sys.platform == "darwin"
SF_DATALESS = 0x40000000  # iCloud-bestand dat alleen in de cloud staat (neemt geen ruimte in)


class UserError(Exception):
    pass


def home():
    return os.path.realpath(os.path.expanduser("~"))


def hp(*parts):
    """Pad binnen de thuismap."""
    return os.path.join(home(), *parts)


def protected_paths():
    """Mappen die zelf nooit weg mogen (wat erin staat soms wel)."""
    h = home()
    names = ["", "Library", "Documents", "Desktop", "Downloads", "Movies", "Music", "Pictures",
             "Public", "Applications", "Sites", ".Trash", ".ssh", ".config", ".local", ".gnupg"]
    lib = ["Caches", "Logs", "Application Support", "Preferences", "Containers", "Group Containers",
           "Mobile Documents", "CloudStorage", "Keychains", "Mail", "Messages", "Photos",
           "Developer", "LaunchAgents", "Saved Application State", "Cookies", "Safari"]
    out = {os.path.join(h, n).rstrip("/") for n in names}
    out |= {os.path.join(h, "Library", n) for n in lib}
    out |= {"/", "/Applications", "/Applications/Utilities", "/System", "/Library", "/Users", "/private"}
    return out


def _clean(path):
    """Absoluut pad, map erboven opgelost, het laatste stuk zelf niet (een snelkoppeling blijft een snelkoppeling)."""
    path = os.path.abspath(path)
    parent, name = os.path.split(path)
    return os.path.join(os.path.realpath(parent), name)


def _inside(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def check_allowed(path, apps=False):
    """Gooi UserError als dit pad niet weg mag. Geeft het opgeschoonde pad terug."""
    if not path or "\x00" in path:
        raise UserError("Ongeldig pad.")
    p = _clean(path)
    if p in protected_paths():
        raise UserError("%s is een vaste map en blijft staan." % p)
    h = home()
    if _inside(p, h):
        rel = os.path.relpath(p, h).split(os.sep)
        # In de bibliotheek pas vanaf ~/Library/Caches/iets, in verborgen mappen vanaf ~/.npm/iets.
        if (rel[0] == "Library" and len(rel) < 3) or (rel[0].startswith(".") and len(rel) < 2):
            raise UserError("%s ligt te dicht bij de basis van je Mac." % p)
        if rel[0] in (".Trash", ".ssh", ".gnupg", ".config", ".local"):
            raise UserError("%s blijft altijd staan." % p)
        for part in rel:
            # Nooit iets in een systeembibliotheek van Foto's, Muziek en dergelijke.
            low = part.lower()
            if low.endswith((".photoslibrary", ".musiclibrary", ".tvlibrary", ".photolibrary")) and part != rel[-1]:
                raise UserError("%s zit in een bibliotheek van Foto's of Muziek." % p)
        if rel[:2] in (["Library", "Keychains"], ["Library", "Mobile Documents"], ["Library", "CloudStorage"],
                       ["Library", "Mail"], ["Library", "Messages"]):
            raise UserError("%s blijft altijd staan." % p)
        return p
    if apps:
        for root in ("/Applications",):
            if _inside(p, root) and p.endswith(".app"):
                return p
    raise UserError("%s valt buiten je eigen mappen." % p)


# ---------------------------------------------------------------------------
# Grootte

def entry_size(st):
    """Werkelijk gebruikte schijfruimte (blokken), zoals de Finder die meetelt."""
    blocks = getattr(st, "st_blocks", None)
    if blocks is not None:
        return blocks * 512
    return st.st_size


def is_dataless(st):
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS)


def tree_size(path, cancel=None):
    """(bytes, aantal bestanden, aantal fouten) zonder snelkoppelingen te volgen."""
    total = files = errors = 0
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0, 1
    if not stat.S_ISDIR(st.st_mode):
        return entry_size(st), 1, 0
    total += entry_size(st)
    stack = [path]
    seen = set()
    while stack:
        if cancel is not None and cancel.is_set():
            break
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            errors += 1
            continue
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    errors += 1
                    continue
                if st.st_nlink > 1 and not stat.S_ISDIR(st.st_mode):
                    key = (st.st_dev, st.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                total += entry_size(st)
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                else:
                    files += 1
    return total, files, errors


def contents_size(path, cancel=None):
    """Grootte van wat in een map zit, zonder de map zelf."""
    size, files, errors = tree_size(path, cancel)
    try:
        size -= entry_size(os.lstat(path))
    except OSError:
        pass
    return max(size, 0), files, errors


# ---------------------------------------------------------------------------
# Weggooien

def _rmtree(path, errors):
    def onerror(func, p, exc_info):
        errors.append(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda f, p, e: errors.append(p))
    else:  # pragma: no cover
        shutil.rmtree(path, onerror=onerror)


def delete_now(path, keep_dir=False):
    """Meteen verwijderen. keep_dir: alleen de inhoud van de map, de map zelf blijft.
    Geeft (vrijgekomen bytes, aantal dingen die niet weg konden)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return 0, 0
    errors = []
    if stat.S_ISDIR(st.st_mode):
        before = contents_size(path)[0] if keep_dir else tree_size(path)[0]
        if keep_dir:
            try:
                with os.scandir(path) as it:
                    entries = list(it)
            except OSError:
                return 0, 1
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        _rmtree(e.path, errors)
                    else:
                        os.unlink(e.path)
                except FileNotFoundError:
                    pass
                except OSError:
                    errors.append(e.path)
            after = contents_size(path)[0] if os.path.lexists(path) else 0
        else:
            _rmtree(path, errors)
            after = tree_size(path)[0] if os.path.lexists(path) else 0
        return max(before - after, 0), len(errors)
    before = entry_size(st)
    try:
        os.unlink(path)
    except FileNotFoundError:
        return 0, 0
    except OSError:
        return 0, 1
    return before, 0


def _unique(folder, name):
    target = os.path.join(folder, name)
    if not os.path.lexists(target):
        return target
    base, ext = os.path.splitext(name)
    stamp = time.strftime("%H.%M.%S")
    n = 0
    while True:
        cand = os.path.join(folder, "%s %s%s%s" % (base, stamp, " %d" % n if n else "", ext))
        if not os.path.lexists(cand):
            return cand
        n += 1


def _trash_cocoa(path):
    try:
        from Foundation import NSFileManager, NSURL
    except Exception:
        return None
    url = NSURL.fileURLWithPath_(path)
    ok, _res, _err = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(url, None, None)
    return bool(ok)


def _trash_finder(path):
    """Via de Finder: vraagt zelf om je wachtwoord als dat nodig is (bijvoorbeeld bij App Store-programma's)."""
    proc = subprocess.run(
        ["osascript", "-e", "on run argv", "-e",
         'tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)', "-e", "end run", path],
        capture_output=True, text=True)
    return proc.returncode == 0


def move_to_trash(path):
    """Naar de Prullenmand. Geeft (bytes, mislukt) terug, net als delete_now."""
    if not os.path.lexists(path):
        return 0, 0
    size = tree_size(path)[0]
    ok = False
    if IS_MAC:
        ok = bool(_trash_cocoa(path))
        if not ok and os.path.lexists(path):
            ok = _trash_finder(path)
    else:
        trash = hp(".Trash")
        os.makedirs(trash, exist_ok=True)
        try:
            shutil.move(path, _unique(trash, os.path.basename(path)))
            ok = True
        except OSError:
            ok = False
    if ok and not os.path.lexists(path):
        return size, 0
    return 0, 1


def remove(path, action, keep_dir=False, apps=False):
    p = check_allowed(path, apps=apps)
    if action == "delete":
        return delete_now(p, keep_dir=keep_dir)
    if action == "trash":
        return move_to_trash(p)
    raise UserError("Onbekende actie.")
