"""Zoeken naar wat er op te ruimen valt, en het opruimen zelf.

Elke scan geeft groepen met onderdelen terug. Een onderdeel is een dict met onder meer:
  path, name, size, action ("delete", "trash", "empty_trash"), keep_dir, selected, note
De server geeft elk onderdeel een nummer; de browser kiest alleen nummers aan.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import plistlib
import re
import shutil
import stat
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from veilig import (IS_MAC, UserError, check_allowed, contents_size, delete_now, entry_size, home, hp,
                    is_dataless, remove, tree_size)

DAY = 86400


class Cancelled(Exception):
    pass


class Job:
    """Een taak die op de achtergrond loopt. De browser vraagt regelmatig hoe ver hij is."""

    def __init__(self, kind):
        self.id = os.urandom(6).hex()
        self.kind = kind
        self.status = "running"
        self.progress = None   # 0..1, of None als dat niet te zeggen is
        self.message = ""
        self.result = None
        self.error = None
        self.cancel = threading.Event()
        self.started = time.time()

    def step(self, progress=None, message=None):
        if self.cancel.is_set():
            raise Cancelled()
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if message is not None:
            self.message = message

    def as_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "progress": self.progress,
                "message": self.message, "error": self.error, "result": self.result if self.status == "done" else None}


def _run(cmd, timeout=60, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _listdir(path):
    try:
        with os.scandir(path) as it:
            return sorted(it, key=lambda e: e.name.lower())
    except OSError:
        return None


def _mtime(path):
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return None


def item(path, size, action, name=None, selected=False, keep_dir=False, note="", **extra):
    d = {"path": path, "name": name or os.path.basename(path), "size": int(size), "action": action,
         "keep_dir": keep_dir, "selected": bool(selected), "note": note}
    d.update(extra)
    return d


def group(key, title, desc, items, icon="", action=None):
    items = sorted(items, key=lambda i: -i["size"])
    return {"key": key, "title": title, "desc": desc, "icon": icon, "items": items,
            "action": action or (items[0]["action"] if items else "delete")}


# ---------------------------------------------------------------------------
# Programma's op deze Mac (naam bij een bundel-id, en wat er nu draait)

APP_DIRS = ["/Applications", "/Applications/Utilities"]
_PLIST_CACHE = {}


def read_info(app):
    if app in _PLIST_CACHE:
        return _PLIST_CACHE[app]
    info = {}
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as fh:
            info = plistlib.load(fh)
    except Exception:
        info = {}
    _PLIST_CACHE[app] = info
    return info


def app_paths():
    found = []
    for d in APP_DIRS + [hp("Applications")]:
        entries = _listdir(d) or []
        for e in entries:
            if e.name.endswith(".app"):
                found.append(e.path)
            elif e.is_dir(follow_symlinks=False) and not e.name.startswith(".") and e.name != "Utilities":
                # programma's in een eigen map, zoals /Applications/Adobe Photoshop/Adobe Photoshop.app
                for sub in _listdir(e.path) or []:
                    if sub.name.endswith(".app"):
                        found.append(sub.path)
    seen, out = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def app_name(app, info=None):
    """De naam zoals je hem in de Finder ziet."""
    return os.path.basename(app)[:-4]


def bundle_names():
    """bundel-id (kleine letters) -> naam van het programma."""
    out = {}
    for app in app_paths():
        bid = read_info(app).get("CFBundleIdentifier")
        if bid:
            out[bid.lower()] = os.path.basename(app)[:-4]
    return out


def running_apps():
    """{bundel-id (kleine letters): pid} van programma's die nu open zijn."""
    out = {}
    proc = _run(["ps", "-x", "-o", "pid=,comm="], timeout=10)
    if proc is None:
        return out
    for line in proc.stdout.splitlines():
        line = line.strip()
        m = re.match(r"(\d+)\s+(.*)", line)
        if not m or ".app/Contents/MacOS/" not in m.group(2):
            continue
        app = m.group(2).split(".app/Contents/MacOS/")[0] + ".app"
        bid = read_info(app).get("CFBundleIdentifier")
        if bid:
            out.setdefault(bid.lower(), int(m.group(1)))
    return out


def _running_match(name, running):
    low = name.lower()
    for bid in running:
        if low == bid or low.startswith(bid + ".") or bid.startswith(low + "."):
            return True
    return False


# ---------------------------------------------------------------------------
# Systeemrommel

CACHE_SKIP = {
    # iCloud, Sleutelhanger, downloads die nog bezig zijn en andere dingen die je beter laat staan
    "com.apple.bird", "cloudkit", "com.apple.nsurlsessiond", "com.apple.containermanagerd", "familycircle",
    "com.apple.akd", "com.apple.icloudhelper", "com.apple.homed", "com.apple.homekit", "com.apple.passd",
    "com.apple.ap.adprivacyd", "com.apple.amsengagementd", "com.apple.appstoreagent",
    "com.apple.commerce", "com.apple.storeuid", "com.apple.findmy.fmipcore", "com.apple.icloud.fmfd",
    "com.apple.findmy", "com.apple.mobileassetd", "com.apple.parsecd",
}

ELECTRON_CACHES = ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
                   "ShaderCache", "GrShaderCache", "CachedData", "CachedExtensionVSIXs")

PRETTY = {
    "diagnosticreports": "Crashrapporten", "homebrew": "Homebrew", "pip": "Python (pip)", "yarn": "Yarn",
    "cocoapods": "CocoaPods", "com.apple.safari": "Safari", "google": "Google (Chrome en meer)",
    "com.spotify.client": "Spotify", "jetbrains": "JetBrains", "typescript": "TypeScript", "node-gyp": "Node",
}


def _pretty(name, names):
    low = name.lower()
    if low in PRETTY:
        return PRETTY[low]
    if low in names:
        return names[low]
    return name


def _size_of(path):
    try:
        st = os.lstat(path)
    except OSError:
        return 0, True
    if stat.S_ISDIR(st.st_mode):
        size, _files, errors = contents_size(path)
        try:
            os.listdir(path)
            denied = False
        except OSError:
            denied = True
        return size, denied
    return entry_size(st), False


def _junk_caches(job, names, running):
    items = []
    entries = _listdir(hp("Library", "Caches")) or []
    for n, e in enumerate(entries):
        job.step(0.05 + 0.35 * n / max(len(entries), 1), "Caches bekijken: %s" % e.name)
        if e.name.lower() in CACHE_SKIP or e.name.startswith("."):
            continue
        size, denied = _size_of(e.path)
        if size < 64 * 1024 or denied:
            continue
        apple = e.name.lower().startswith("com.apple.")
        busy = _running_match(e.name, running)
        note = "Programma is open: sluit het eerst" if busy else ("Van macOS zelf" if apple else "")
        items.append(item(e.path, size, "delete", name=_pretty(e.name, names), keep_dir=e.is_dir(follow_symlinks=False),
                          selected=not apple and not busy, note=note))
    return items


def _junk_app_caches(job, names, running):
    """Caches die programma's als Slack, Teams, Discord en VS Code in Application Support bewaren."""
    items = []
    support = hp("Library", "Application Support")
    apps = _listdir(support) or []
    for n, app in enumerate(apps):
        job.step(0.4 + 0.2 * n / max(len(apps), 1), "Programma-caches bekijken: %s" % app.name)
        if not app.is_dir(follow_symlinks=False) or app.name.startswith("."):
            continue
        found = []
        # tot drie niveaus diep, bijvoorbeeld Google/Chrome/Default/Code Cache
        stack = [(app.path, 0)]
        while stack:
            d, depth = stack.pop()
            for e in _listdir(d) or []:
                if not e.is_dir(follow_symlinks=False):
                    continue
                if e.name in ELECTRON_CACHES:
                    found.append(e.path)
                elif e.name == "Service Worker":
                    cs = os.path.join(e.path, "CacheStorage")
                    if os.path.isdir(cs):
                        found.append(cs)
                elif depth < 2 and not e.name.startswith("."):
                    stack.append((e.path, depth + 1))
        for path in found:
            size, denied = _size_of(path)
            if size < 1024 * 1024 or denied:
                continue
            rel = os.path.relpath(path, support)
            label = _pretty(app.name, names)
            busy = _running_match(app.name, running) or any(label.lower() == v.lower() for v in
                                                           [names.get(b, "") for b in running])
            items.append(item(path, size, "delete", name="%s: %s" % (label, os.path.basename(path)), keep_dir=True,
                              selected=not busy, note="Programma is open: sluit het eerst" if busy else rel))
    return items


def _junk_logs(job):
    items = []
    for e in _listdir(hp("Library", "Logs")) or []:
        size, denied = _size_of(e.path)
        if size < 16 * 1024 or denied:
            continue
        items.append(item(e.path, size, "delete", name=_pretty(e.name, {}), keep_dir=e.is_dir(follow_symlinks=False),
                          selected=True))
    return items


def _junk_dev(job):
    items = []
    dev = hp("Library", "Developer")
    fixed = [
        ("Xcode: DerivedData (bouwbestanden)", os.path.join(dev, "Xcode", "DerivedData"), True, "delete"),
        ("Simulator-caches", os.path.join(dev, "CoreSimulator", "Caches"), True, "delete"),
        ("Xcode: oude previews", os.path.join(dev, "Xcode", "UserData", "Previews"), True, "delete"),
        ("npm-cache", hp(".npm", "_cacache"), True, "delete"),
        ("Gradle-caches", hp(".gradle", "caches"), True, "delete"),
        ("Cargo (Rust) downloads", hp(".cargo", "registry", "cache"), True, "delete"),
        ("pnpm-opslag", hp("Library", "pnpm", "store"), False, "delete"),
        ("Xcode-archieven (je oude app-builds)", os.path.join(dev, "Xcode", "Archives"), False, "trash"),
    ]
    for title, path, sel, action in fixed:
        if not os.path.isdir(path):
            continue
        size, denied = _size_of(path)
        if size < 1024 * 1024 or denied:
            continue
        items.append(item(path, size, action, name=title, keep_dir=action == "delete", selected=sel,
                          note="Gaat naar de Prullenmand" if action == "trash" else ""))
    for sub in ("iOS DeviceSupport", "watchOS DeviceSupport", "tvOS DeviceSupport", "macOS DeviceSupport"):
        for e in _listdir(os.path.join(dev, "Xcode", sub)) or []:
            size, denied = _size_of(e.path)
            if size >= 1024 * 1024 and not denied:
                items.append(item(e.path, size, "delete", name="%s %s" % (sub.replace(" DeviceSupport", ""), e.name),
                                  note="Wordt opnieuw gemaakt als je dat apparaat aansluit"))
    for e in _listdir(hp(".cache")) or []:
        size, denied = _size_of(e.path)
        if size >= 1024 * 1024 and not denied:
            items.append(item(e.path, size, "delete", name="~/.cache/%s" % e.name, keep_dir=e.is_dir(follow_symlinks=False),
                              note="Gedeelde cache van ontwikkeltools"))
    return items


def _plist(path):
    try:
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    except Exception:
        return {}


def _junk_ios(job):
    items = []
    folder = hp("Library", "Application Support", "MobileSync", "Backup")
    for e in _listdir(folder) or []:
        if not e.is_dir(follow_symlinks=False):
            continue
        info = _plist(os.path.join(e.path, "Info.plist"))
        size, _f, _err = tree_size(e.path, job.cancel)
        when = info.get("Last Backup Date")
        label = info.get("Device Name") or "Onbekend apparaat"
        note = "Laatste reservekopie: %s" % when.strftime("%d-%m-%Y") if isinstance(when, dt.datetime) else ""
        items.append(item(e.path, size, "trash", name="Reservekopie van %s" % label, note=note))
    return items


def _junk_mail(job):
    path = hp("Library", "Containers", "com.apple.mail", "Data", "Library", "Mail Downloads")
    if not os.path.isdir(path):
        return []
    size, denied = _size_of(path)
    if size < 64 * 1024 or denied:
        return []
    return [item(path, size, "delete", name="Geopende mailbijlagen", keep_dir=True, selected=True,
                 note="Kopieen: de bijlagen zelf blijven gewoon in je mail")]


def trash_info():
    """(grootte of None als we niet in de Prullenmand mogen kijken, aantal onderdelen of None)."""
    path = hp(".Trash")
    try:
        entries = os.listdir(path)
    except FileNotFoundError:
        return 0, 0
    except OSError:
        return None, None
    entries = [e for e in entries if e != ".DS_Store"]
    size = sum(tree_size(os.path.join(path, e))[0] for e in entries)
    return size, len(entries)


def _junk_trash(job):
    size, count = trash_info()
    if size == 0 and count == 0:
        return []
    note = "%d onderdelen, worden definitief verwijderd" % count if count is not None else \
        "Schoonschip mag niet in de Prullenmand kijken; de Finder leegt hem"
    return [item(hp(".Trash"), size or 0, "empty_trash", name="Prullenmand", selected=True, note=note,
                 unknown=size is None)]


def full_disk_access():
    """True als Schoonschip overal in je bibliotheek mag kijken (Volledige schijftoegang)."""
    if not IS_MAC:
        return True
    for probe in (hp("Library", "Safari"), hp("Library", "Mail"), hp(".Trash")):
        if os.path.exists(probe):
            try:
                os.listdir(probe)
            except PermissionError:
                return False
            except OSError:
                continue
    return True


def scan_junk(job):
    job.step(0.01, "Programma's bekijken")
    names = bundle_names()
    running = running_apps()
    groups = [
        group("caches", "Gebruikerscaches", "Tijdelijke bestanden die programma's bewaren om sneller te werken. "
              "Ze maken ze vanzelf opnieuw aan.", _junk_caches(job, names, running), "box"),
        group("appcaches", "Caches van programma's", "Caches van onder meer Slack, Teams, Discord, VS Code en "
              "Chrome-profielen.", _junk_app_caches(job, names, running), "layers"),
    ]
    job.step(0.62, "Logbestanden bekijken")
    groups.append(group("logs", "Logbestanden", "Verslagen die programma's bijhouden, vooral handig voor "
                        "ontwikkelaars.", _junk_logs(job), "doc"))
    job.step(0.7, "Ontwikkeltools bekijken")
    groups.append(group("dev", "Ontwikkeltools", "Bouwbestanden en downloads van Xcode, npm, Gradle en andere "
                        "tools. Worden opnieuw gemaakt als je ze nodig hebt.", _junk_dev(job), "code"))
    job.step(0.8, "Mailbijlagen bekijken")
    groups.append(group("mail", "Mailbijlagen", "Kopieen van bijlagen die je in Mail hebt geopend.",
                        _junk_mail(job), "mail"))
    job.step(0.85, "Reservekopieen van iPhone en iPad bekijken")
    groups.append(group("ios", "Reservekopieen van iPhone en iPad", "Oude reservekopieen in de Finder. "
                        "Gaan naar de Prullenmand. Controleer eerst of je ze echt niet meer nodig hebt.",
                        _junk_ios(job), "phone"))
    job.step(0.95, "Prullenmand bekijken")
    groups.append(group("trash", "Prullenmand", "Alles wat je al hebt weggegooid.", _junk_trash(job), "trash"))
    groups = [g for g in groups if g["items"]]
    return {"groups": groups, "full_disk_access": full_disk_access()}


# ---------------------------------------------------------------------------
# Grote bestanden

PACKAGE_EXT = (".app", ".photoslibrary", ".musiclibrary", ".tvlibrary", ".imovielibrary", ".fcpbundle",
               ".logicx", ".band", ".aplibrary", ".photolibrary", ".lrdata", ".bundle", ".framework",
               ".sparsebundle", ".vmwarevm", ".pvm", ".utm", ".xcarchive", ".xcodeproj", ".xcworkspace",
               ".plugin", ".kext", ".pkg", ".rtfd", ".pages", ".numbers", ".key", ".git", ".dtBase2")

KINDS = [
    ("Video", {"mp4", "mov", "m4v", "mkv", "avi", "wmv", "mts", "m2ts", "webm", "flv", "mpg", "mpeg", "3gp"}),
    ("Audio", {"mp3", "wav", "aiff", "aif", "flac", "m4a", "aac", "ogg", "alac"}),
    ("Afbeelding", {"jpg", "jpeg", "png", "heic", "tif", "tiff", "psd", "raw", "cr2", "cr3", "nef", "arw", "dng", "gif", "svg", "ai"}),
    ("Archief", {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz", "zst"}),
    ("Schijfkopie", {"dmg", "iso", "img", "sparseimage", "vdi", "vmdk", "qcow2", "ova"}),
    ("Installatie", {"pkg", "mpkg", "xip", "ipsw", "exe", "msi"}),
    ("Document", {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "key", "pages", "numbers", "indd", "epub"}),
]


def kind_of(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    for label, exts in KINDS:
        if ext in exts:
            return label
    return "Overig"


def _skip_part(name):
    low = name.lower()
    return name.startswith(".") or low.endswith(PACKAGE_EXT) or name in ("node_modules",)


def skip_path(path, root=None):
    """True voor paden die we bij grote en dubbele bestanden overslaan."""
    h = home()
    if not (path == h or path.startswith(h + "/")):
        return True
    rel = os.path.relpath(path, h).split(os.sep)
    if rel[0] == "Library":
        return True
    return any(_skip_part(p) for p in rel)


def walk_files(root, job=None, min_size=0):
    """Alle gewone bestanden onder root (zonder bibliotheek, verborgen mappen en pakketten)."""
    stack = [root]
    dirs = 0
    while stack:
        d = stack.pop()
        dirs += 1
        if job is not None and dirs % 200 == 0:
            job.step(None, "Bekijken: %s" % d.replace(home(), "~"))
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                if _skip_part(e.name):
                    continue
                if d == home() and e.name == "Library":
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                elif stat.S_ISREG(st.st_mode) and st.st_size >= min_size and not is_dataless(st):
                    yield e.path, st


def _mdfind_large(min_bytes):
    if not IS_MAC or not shutil.which("mdfind"):
        return None
    proc = _run(["mdfind", "-onlyin", home(), "kMDItemFSSize >= %d" % int(min_bytes)], timeout=60)
    if proc is None or proc.returncode != 0:
        return None
    return [p for p in proc.stdout.splitlines() if p]


def scan_large(job, min_mb=100, deep=False):
    min_bytes = int(float(min_mb) * 1024 * 1024)
    job.step(None, "Zoeken naar bestanden van %s MB of groter" % min_mb)
    found = []
    paths = None if deep else _mdfind_large(min_bytes)
    if paths is not None and paths:
        for n, p in enumerate(paths):
            if n % 50 == 0:
                job.step(n / max(len(paths), 1))
            if skip_path(p):
                continue
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and not is_dataless(st) and entry_size(st) >= min_bytes:
                found.append((p, st))
    else:
        deep = True
        found = [(p, st) for p, st in walk_files(home(), job, min_bytes) if entry_size(st) >= min_bytes]
    items = []
    now = time.time()
    for p, st in found:
        age = int((now - st.st_mtime) / DAY)
        items.append(item(p, entry_size(st), "trash", kind=kind_of(p), mtime=st.st_mtime, age_days=age,
                          where=os.path.dirname(p).replace(home(), "~")))
    items.sort(key=lambda i: -i["size"])
    return {"items": items, "deep": deep, "min_mb": min_mb}


# ---------------------------------------------------------------------------
# Downloads

INSTALLERS = {"dmg", "pkg", "mpkg", "iso", "xip", "ipsw"}


def _parse_md_date(s):
    s = (s or "").strip()
    if not s or s == "(null)":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z",):
        try:
            return dt.datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    return None


def md_dates(paths, attr):
    """Spotlight-datum (bijv. kMDItemDateAdded) voor veel bestanden tegelijk. {pad: timestamp}."""
    out = {}
    if not IS_MAC or not paths or not shutil.which("mdls"):
        return out
    for i in range(0, len(paths), 200):
        chunk = paths[i:i + 200]
        proc = _run(["mdls", "-name", attr, "-raw", "-nullMarker", "(null)"] + chunk, timeout=60)
        if proc is None or proc.returncode != 0:
            continue
        values = proc.stdout.split("\x00")
        for p, v in zip(chunk, values):
            ts = _parse_md_date(v)
            if ts:
                out[p] = ts
    return out


def scan_downloads(job):
    folder = hp("Downloads")
    entries = [e for e in (_listdir(folder) or []) if e.name not in (".DS_Store", ".localized")]
    added = md_dates([e.path for e in entries], "kMDItemDateAdded")
    now = time.time()
    installers, old, rest = [], [], []
    for n, e in enumerate(entries):
        job.step(n / max(len(entries), 1), "Bekijken: %s" % e.name)
        size = tree_size(e.path, job.cancel)[0]
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        when = added.get(e.path) or getattr(st, "st_birthtime", None) or st.st_mtime
        age = int((now - when) / DAY)
        ext = os.path.splitext(e.name)[1].lower().lstrip(".")
        is_installer = ext in INSTALLERS
        it = item(e.path, size, "trash", added=when, age_days=age, kind=kind_of(e.path) if not e.is_dir() else "Map",
                  selected=is_installer)
        if is_installer:
            it["note"] = "Installatiebestand: niet meer nodig als het programma eenmaal staat"
            installers.append(it)
        elif age >= 90:
            old.append(it)
        else:
            rest.append(it)
    groups = [
        group("installers", "Installatiebestanden", ".dmg- en .pkg-bestanden waarmee je ooit iets installeerde.",
              installers, "package", "trash"),
        group("old", "Langer dan 3 maanden geleden gedownload", "Vaak vergeten. Kijk even of er iets tussen zit dat "
              "je wilt bewaren.", old, "clock", "trash"),
        group("recent", "Recent gedownload", "De afgelopen 3 maanden.", rest, "download", "trash"),
    ]
    return {"groups": [g for g in groups if g["items"]]}


# ---------------------------------------------------------------------------
# Dubbele bestanden

def _hash(path, limit=None, job=None):
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as fh:
            remaining = limit
            while True:
                if job is not None and job.cancel.is_set():
                    raise Cancelled()
                chunk = fh.read(1024 * 1024 if remaining is None else min(remaining, 1024 * 1024))
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break
    except OSError:
        return None
    return h.hexdigest()


def scan_dupes(job, folder=None, min_mb=1):
    root = os.path.realpath(folder or home())
    if skip_path(root) and root != home():
        raise UserError("Kies een map in je eigen thuismap (niet in de bibliotheek of een verborgen map).")
    min_bytes = max(1, int(float(min_mb) * 1024 * 1024))
    by_size = {}
    seen_inodes = set()
    count = 0
    for p, st in walk_files(root, job, min_bytes):
        key = (st.st_dev, st.st_ino)
        if key in seen_inodes:
            continue  # harde koppeling: zelfde bestand, neemt geen extra ruimte in
        seen_inodes.add(key)
        by_size.setdefault(st.st_size, []).append((p, st))
        count += 1
        if count % 500 == 0:
            job.step(None, "%d bestanden gevonden" % count)
    candidates = [v for v in by_size.values() if len(v) > 1]
    total = sum(len(v) for v in candidates)
    done = 0
    groups = []
    for files in candidates:
        partial = {}
        for p, st in files:
            done += 1
            job.step(done / max(total, 1), "Vergelijken: %s" % os.path.basename(p))
            h = _hash(p, 64 * 1024, job)
            if h:
                partial.setdefault(h, []).append((p, st))
        for same in partial.values():
            if len(same) < 2:
                continue
            full = {}
            for p, st in same:
                h = _hash(p, None, job) if st.st_size > 64 * 1024 else "klein"
                if h:
                    full.setdefault(h, []).append((p, st))
            for dupes in full.values():
                if len(dupes) < 2:
                    continue
                dupes.sort(key=lambda x: (getattr(x[1], "st_birthtime", x[1].st_mtime), len(x[0])))
                items = []
                for i, (p, st) in enumerate(dupes):
                    items.append(item(p, entry_size(st), "trash", selected=i > 0, mtime=st.st_mtime,
                                      where=os.path.dirname(p).replace(home(), "~"),
                                      note="Origineel (oudste): blijft staan" if i == 0 else ""))
                groups.append({"key": "d%d" % len(groups), "title": os.path.basename(dupes[0][0]),
                               "size": entry_size(dupes[0][1]), "items": items, "kind": kind_of(dupes[0][0])})
    groups.sort(key=lambda g: -g["size"] * (len(g["items"]) - 1))
    wasted = sum(g["size"] * (len(g["items"]) - 1) for g in groups)
    return {"groups": groups, "folder": root.replace(home(), "~"), "wasted": wasted, "files": count}


# ---------------------------------------------------------------------------
# Ruimtekaart

def _du(path, cancel):
    if shutil.which("du"):
        proc = _run(["du", "-skx", path], timeout=600)
        if proc is not None and proc.stdout.strip():
            try:
                return int(proc.stdout.split()[0]) * 1024
            except ValueError:
                pass
    return tree_size(path, cancel)[0]


def space_root_ok(path):
    p = os.path.realpath(path)
    h = home()
    return p == h or p.startswith(h + "/") or p == "/Applications" or p.startswith("/Applications/")


def scan_space(job, path=None):
    path = os.path.realpath(path or home())
    if not space_root_ok(path):
        raise UserError("De ruimtekaart werkt in je thuismap en in Programma's.")
    entries = [e for e in (_listdir(path) or []) if e.name not in (".DS_Store",)]
    h = home()
    results = []
    loose = 0
    dirs = []
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            dirs.append(e)
        else:
            sz = entry_size(st)
            results.append({"name": e.name, "path": e.path, "size": sz, "dir": False})
    done = [0]
    lock = threading.Lock()

    def measure(e):
        if job.cancel.is_set():
            return None
        size = _du(e.path, job.cancel)
        with lock:
            done[0] += 1
            job.progress = done[0] / max(len(dirs), 1)
            job.message = "Meten: %s" % e.name
        return {"name": e.name, "path": e.path, "size": size,
                "dir": not e.name.lower().endswith(PACKAGE_EXT)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(measure, dirs):
            if r:
                results.append(r)
    job.step(1.0)
    for r in results:
        r["can_trash"] = _space_trashable(r["path"])
    results.sort(key=lambda r: -r["size"])
    total = sum(r["size"] for r in results)
    parent = os.path.dirname(path)
    return {"path": path, "label": path.replace(h, "~") if path.startswith(h) else path,
            "parent": parent if space_root_ok(parent) and path != h else None,
            "items": results, "total": total, "loose": loose}


def _space_trashable(path):
    h = home()
    if path.startswith(h + "/"):
        rel = os.path.relpath(path, h).split(os.sep)
        if rel[0] == "Library" or rel[0].startswith("."):
            return False
    try:
        check_allowed(path, apps=True)
        return True
    except UserError:
        return False


# ---------------------------------------------------------------------------
# Programma's verwijderen

PROTECTED_APPS = {"com.apple.safari", "com.apple.finder", "com.apple.systempreferences", "com.apple.appstore"}


def list_apps(job, with_sizes=True):
    running = running_apps()
    apps = []
    paths = app_paths()
    for n, app in enumerate(paths):
        job.step(0.05 + 0.6 * n / max(len(paths), 1), "Bekijken: %s" % os.path.basename(app))
        info = read_info(app)
        bid = (info.get("CFBundleIdentifier") or "").lower()
        real = os.path.realpath(app)
        if not bid or bid in PROTECTED_APPS or real.startswith("/System/"):
            continue
        size = _du(app, job.cancel) if with_sizes else 0
        apps.append({
            "path": app, "name": app_name(app, info), "bundle": info.get("CFBundleIdentifier"),
            "version": str(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or ""),
            "size": size, "apple": bid.startswith("com.apple."), "running": bid in running,
            "appstore": os.path.exists(os.path.join(app, "Contents", "_MASReceipt", "receipt")),
        })
    job.step(0.7, "Kijken wanneer je ze voor het laatst gebruikte")
    used = md_dates([a["path"] for a in apps], "kMDItemLastUsedDate")
    now = time.time()
    for a in apps:
        ts = used.get(a["path"])
        a["last_used"] = ts
        a["unused_days"] = int((now - ts) / DAY) if ts else None
    apps.sort(key=lambda a: a["name"].lower())
    return {"apps": apps}


def _leftover_candidates(bundle, name):
    lib = hp("Library")
    b = bundle
    out = [
        os.path.join(lib, "Application Support", b), os.path.join(lib, "Caches", b),
        os.path.join(lib, "Containers", b), os.path.join(lib, "Saved Application State", b + ".savedState"),
        os.path.join(lib, "Preferences", b + ".plist"), os.path.join(lib, "Logs", b),
        os.path.join(lib, "HTTPStorages", b), os.path.join(lib, "HTTPStorages", b + ".binarycookies"),
        os.path.join(lib, "WebKit", b), os.path.join(lib, "Cookies", b + ".binarycookies"),
        os.path.join(lib, "Application Scripts", b),
    ]
    if name and len(name) >= 4:
        for sub in ("Application Support", "Caches", "Logs"):
            out.append(os.path.join(lib, sub, name))
    # helpers en uitbreidingen: com.voorbeeld.app.helper
    for sub, suffix in (("Preferences", ".plist"), ("Containers", ""), ("Application Scripts", ""),
                        ("LaunchAgents", ".plist"), ("Caches", "")):
        for e in _listdir(os.path.join(lib, sub)) or []:
            if e.name.lower().startswith(b.lower() + ".") and e.name.endswith(suffix):
                out.append(e.path)
    for e in _listdir(os.path.join(lib, "Preferences", "ByHost")) or []:
        if e.name.lower().startswith(b.lower() + "."):
            out.append(e.path)
    for e in _listdir(os.path.join(lib, "Group Containers")) or []:
        low = e.name.lower()
        if low.endswith("." + b.lower()) or low == b.lower():
            out.append(e.path)
    return out


LEFTOVER_LABELS = {
    "Application Support": "Programmagegevens", "Caches": "Cache", "Containers": "Programmagegevens (sandbox)",
    "Group Containers": "Gedeelde gegevens", "Saved Application State": "Vensterstatus",
    "Preferences": "Voorkeuren", "Logs": "Logbestanden", "HTTPStorages": "Webgegevens", "WebKit": "Webgegevens",
    "Cookies": "Cookies", "Application Scripts": "Scripts", "LaunchAgents": "Start automatisch",
}


def app_leftovers(app_path):
    info = read_info(app_path)
    bundle = info.get("CFBundleIdentifier")
    if not bundle:
        raise UserError("Dit programma heeft geen herkenbare naam (bundel-id).")
    name = os.path.basename(app_path)[:-4]
    items = [item(app_path, _du(app_path, None), "trash", name=name + ".app", selected=True, note="Het programma zelf",
                  is_app=True)]
    seen = {app_path}
    lib = hp("Library")
    for p in _leftover_candidates(bundle, name):
        if p in seen or not os.path.lexists(p):
            continue
        seen.add(p)
        try:
            check_allowed(p)
        except UserError:
            continue
        sub = os.path.relpath(p, lib).split(os.sep)[0]
        size = tree_size(p)[0]
        items.append(item(p, size, "trash", name=p.replace(home(), "~"), selected=True,
                          note=LEFTOVER_LABELS.get(sub, sub)))
    return {"bundle": bundle, "name": name, "items": items,
            "running": bundle.lower() in running_apps(),
            "appstore": os.path.exists(os.path.join(app_path, "Contents", "_MASReceipt", "receipt"))}


# ---------------------------------------------------------------------------
# Opstarten

def _launchctl_labels():
    proc = _run(["launchctl", "list"], timeout=10)
    labels = set()
    if proc is not None:
        for line in proc.stdout.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) == 3:
                labels.add(parts[2])
    return labels


def list_startup(job):
    loaded = _launchctl_labels() if IS_MAC else set()
    groups = []
    for key, folder, editable, title in (
            ("user", hp("Library", "LaunchAgents"), True, "Starten als jij inlogt (van jou)"),
            ("agents", "/Library/LaunchAgents", False, "Starten als iemand inlogt (voor iedereen)"),
            ("daemons", "/Library/LaunchDaemons", False, "Achtergronddiensten (voor iedereen)")):
        items = []
        for e in _listdir(folder) or []:
            if not e.name.endswith(".plist"):
                continue
            data = _plist(e.path)
            label = data.get("Label") or e.name[:-6]
            prog = data.get("Program") or (data.get("ProgramArguments") or [None])[0]
            broken = bool(prog) and prog.startswith("/") and not os.path.exists(prog)
            note = "Kapot: het programma bestaat niet meer" if broken else (prog or "")
            items.append(item(e.path, entry_size(e.stat(follow_symlinks=False)), "trash", name=label,
                              selected=False, note=note, broken=broken, editable=editable,
                              active=label in loaded, label=label))
        items.sort(key=lambda i: (not i["broken"], i["name"].lower()))
        groups.append({"key": key, "title": title, "items": items, "editable": editable})
    return {"groups": groups}


def unload_agent(path, label):
    if IS_MAC:
        _run(["launchctl", "bootout", "gui/%d" % os.getuid(), path], timeout=15)


# ---------------------------------------------------------------------------
# Onderhoud

LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")

TASKS = [
    {"key": "dns", "title": "DNS-cache legen", "admin": True,
     "desc": "Helpt als websites niet laden of naar een oud adres gaan.",
     "cmd": "dscacheutil -flushcache; killall -HUP mDNSResponder"},
    {"key": "ram", "title": "Werkgeheugen vrijmaken", "admin": True,
     "desc": "Maakt geheugen vrij dat macOS als buffer vasthoudt. Het effect is tijdelijk.",
     "cmd": "purge"},
    {"key": "quicklook", "title": "Voorvertoningen vernieuwen", "admin": False,
     "desc": "Wist de cache van Snelle weergave (spatiebalk) en miniaturen. Helpt bij verkeerde voorbeelden.",
     "cmd": "qlmanage -r cache >/dev/null 2>&1; qlmanage -r >/dev/null 2>&1; echo klaar"},
    {"key": "launchservices", "title": "'Open met'-lijst opschonen", "admin": False,
     "desc": "Bouwt de lijst opnieuw op waarmee macOS weet welk programma wat opent. Haalt dubbele "
             "en verdwenen programma's uit 'Open met'.",
     "cmd": LSREGISTER + " -kill -r -domain local -domain system -domain user; echo klaar"},
    {"key": "snapshots", "title": "Lokale Time Machine-snapshots verwijderen", "admin": True,
     "desc": "Time Machine bewaart tijdelijk kopieen op je Mac zelf. Je reservekopieen op je externe schijf "
             "blijven gewoon staan.",
     "cmd": "for d in $(tmutil listlocalsnapshotdates / | grep -E '^[0-9]'); do tmutil deletelocalsnapshots $d; done; "
            "echo klaar"},
    {"key": "spotlight", "title": "Spotlight opnieuw indexeren", "admin": True,
     "desc": "Helpt als Spotlight dingen niet meer vindt. Je Mac is daarna een paar uur wat drukker.",
     "cmd": "mdutil -E /"},
    {"key": "verify", "title": "Schijf controleren", "admin": False,
     "desc": "Controleert of het bestandssysteem in orde is (alleen kijken, er verandert niets).",
     "cmd": "diskutil verifyVolume /"},
]


def snapshot_count():
    if not IS_MAC:
        return 0
    proc = _run(["tmutil", "listlocalsnapshotdates", "/"], timeout=20)
    if proc is None:
        return None
    return len([l for l in proc.stdout.splitlines() if re.match(r"^\d", l)])


def run_task(job, key):
    task = next((t for t in TASKS if t["key"] == key), None)
    if task is None:
        raise UserError("Onbekende taak.")
    if not IS_MAC:
        raise UserError("Onderhoudstaken werken alleen op een Mac.")
    job.step(None, task["title"] + "...")
    if task["admin"]:
        script = 'do shell script "%s" with administrator privileges' % task["cmd"].replace("\\", "\\\\").replace('"', '\\"')
        proc = _run(["osascript", "-e", script], timeout=3600)
    else:
        proc = _run(["/bin/sh", "-c", task["cmd"]], timeout=3600)
    if proc is None:
        raise UserError("De taak duurde te lang of kon niet starten.")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        if "-128" in err or "User canceled" in err or "geannuleerd" in err.lower():
            raise UserError("Geannuleerd.")
        raise UserError(err or "De taak is mislukt.")
    out = (proc.stdout or "").strip()
    return {"title": task["title"], "output": out[-2000:]}


# ---------------------------------------------------------------------------
# Overzicht

def disk_info():
    path = "/System/Volumes/Data" if os.path.isdir("/System/Volumes/Data") else "/"
    du = shutil.disk_usage(path)
    info = {"total": du.total, "free": du.free, "used": du.total - du.free, "purgeable": None}
    try:
        from Foundation import NSURL
        url = NSURL.fileURLWithPath_(path)
        ok, val, _err = url.getResourceValue_forKey_error_(None, "NSURLVolumeAvailableCapacityForImportantUsageKey", None)
        if ok and val is not None and int(val) > du.free:
            info["purgeable"] = int(val) - du.free
    except Exception:
        pass
    return info


def memory_info():
    if IS_MAC:
        total = _run(["sysctl", "-n", "hw.memsize"], timeout=5)
        vm = _run(["vm_stat"], timeout=5)
        try:
            total_b = int(total.stdout.strip())
            page = int(re.search(r"page size of (\d+)", vm.stdout).group(1))
            vals = {}
            for line in vm.stdout.splitlines()[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    vals[k.strip().strip('"')] = int(v.strip().rstrip(".") or 0)
            app = vals.get("Anonymous pages", 0) - vals.get("Pages purgeable", 0)
            used = (app + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)) * page
            return {"total": total_b, "used": min(used, total_b)}
        except Exception:
            return None
    try:
        vals = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, v = line.split(":", 1)
                vals[k] = int(v.split()[0]) * 1024
        return {"total": vals["MemTotal"], "used": vals["MemTotal"] - vals.get("MemAvailable", 0)}
    except Exception:
        return None


def uptime_days():
    try:
        if IS_MAC:
            proc = _run(["sysctl", "-n", "kern.boottime"], timeout=5)
            sec = int(re.search(r"sec = (\d+)", proc.stdout).group(1))
            return (time.time() - sec) / DAY
        with open("/proc/uptime") as fh:
            return float(fh.read().split()[0]) / DAY
    except Exception:
        return None


def top_apps(limit=8):
    """Programma's en processen die het meeste geheugen gebruiken (per programma opgeteld)."""
    proc = _run(["ps", "-axo", "pid=,rss=,pcpu=,uid=,comm="], timeout=10)
    if proc is None:
        return []
    me = os.getuid()
    groups = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+([\d.,]+)\s+(\d+)\s+(.*)", line)
        if not m:
            continue
        pid, rss, cpu, uid, comm = int(m.group(1)), int(m.group(2)) * 1024, float(m.group(3).replace(",", ".")), \
            int(m.group(4)), m.group(5)
        if ".app/" in comm:
            app = comm.split(".app/")[0] + ".app"
            key = app
            name = os.path.basename(app)[:-4]
        else:
            key = comm
            name = os.path.basename(comm)
            app = None
        g = groups.setdefault(key, {"name": name, "memory": 0, "cpu": 0.0, "app": app, "pids": [], "mine": True})
        g["memory"] += rss
        g["cpu"] += cpu
        g["pids"].append(pid)
        if uid != me:
            g["mine"] = False
    out = sorted(groups.values(), key=lambda g: -g["memory"])[:limit]
    for g in out:
        info = read_info(g["app"]) if g["app"] else {}
        g["bundle"] = info.get("CFBundleIdentifier")
        g["can_quit"] = bool(g["bundle"]) and g["mine"] and g["bundle"] != "nl.schoonschip.app" and IS_MAC
        g["cpu"] = round(g["cpu"], 1)
        del g["pids"]
    return out


def quit_app(bundle):
    try:
        from AppKit import NSRunningApplication
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle)
        if apps and len(apps):
            for a in apps:
                a.terminate()
            return True
    except Exception:
        pass
    proc = _run(["osascript", "-e", 'tell application id "%s" to quit' % bundle.replace('"', "")], timeout=30)
    return proc is not None and proc.returncode == 0


def overview():
    return {"disk": disk_info(), "memory": memory_info(), "uptime_days": uptime_days(),
            "load": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
            "cpus": os.cpu_count(), "top": top_apps(), "full_disk_access": full_disk_access(),
            "mac": IS_MAC}


def smart_scan(job):
    """Alles in een keer: rommel, downloads, grote bestanden en ongebruikte programma's."""
    sub = _SubJob(job, 0.0, 0.6)
    junk = scan_junk(sub)
    sub = _SubJob(job, 0.6, 0.75)
    downloads = scan_downloads(sub)
    job.step(0.78, "Grote bestanden zoeken")
    large = _mdfind_large(1024 ** 3)
    large_count = None
    large_size = None
    if large is not None:
        files = []
        for p in large:
            if skip_path(p):
                continue
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and not is_dataless(st):
                files.append(entry_size(st))
        large_count, large_size = len(files), sum(files)
    sub = _SubJob(job, 0.82, 0.98)
    apps = list_apps(sub, with_sizes=False)["apps"]
    unused = [a for a in apps if a["unused_days"] is not None and a["unused_days"] > 180 and not a["apple"]]
    return {"junk": junk, "downloads": downloads, "large_count": large_count, "large_size": large_size,
            "unused_apps": len(unused), "uptime_days": uptime_days()}


class _SubJob:
    """Laat een deelscan een stukje van de voortgangsbalk vullen."""

    def __init__(self, job, start, end):
        self.job, self.start, self.end = job, start, end
        self.cancel = job.cancel

    def step(self, progress=None, message=None):
        if progress is not None:
            progress = self.start + (self.end - self.start) * progress
        self.job.step(progress, message)

    @property
    def progress(self):
        return self.job.progress

    @progress.setter
    def progress(self, v):
        self.job.progress = self.start + (self.end - self.start) * v

    @property
    def message(self):
        return self.job.message

    @message.setter
    def message(self, v):
        self.job.message = v


# ---------------------------------------------------------------------------
# Opruimen

def empty_trash(it):
    size = it.get("size", 0)
    if IS_MAC:
        proc = _run(["osascript", "-e", 'tell application "Finder" to empty trash'], timeout=600)
        if proc is None or proc.returncode != 0:
            return 0, 1
        return size, 0
    freed = 0
    errors = 0
    for e in _listdir(hp(".Trash")) or []:
        f, err = delete_now(e.path)
        freed += f
        errors += err
    return freed, errors


def clean(job, items):
    """Ruim de gekozen onderdelen op. Geeft per onderdeel terug wat er gebeurde."""
    freed = 0
    trashed = 0
    failed = []
    done = []
    for n, it in enumerate(items):
        job.step(n / max(len(items), 1), "Opruimen: %s" % it["name"])
        try:
            if it["action"] == "empty_trash":
                f, err = empty_trash(it)
            else:
                if it.get("label") and it.get("editable"):
                    unload_agent(it["path"], it["label"])
                f, err = remove(it["path"], it["action"], keep_dir=it.get("keep_dir", False),
                                apps=bool(it.get("is_app")))
        except UserError as exc:
            failed.append({"name": it["name"], "reason": str(exc)})
            continue
        if it["action"] == "trash":
            trashed += f
        else:
            freed += f
        if err:
            failed.append({"name": it["name"], "reason": "Niet alles kon weg (in gebruik of geen toegang)"
                           if f else "Kon niet worden verwijderd (in gebruik of geen toegang)"})
        if f or not err:
            done.append(it["id"])
    job.step(1.0, "Klaar")
    # freed: meteen vrij. trashed: in de Prullenmand, vrij zodra je die leegt.
    return {"freed": freed, "trashed": trashed, "failed": failed, "done": done}
