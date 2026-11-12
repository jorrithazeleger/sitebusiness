"""Rekenblad: een kleine webserver op deze computer met de editor in de browser.

Gebruik:
  server.py [bestand]          draait in de voorgrond (Terminal) en opent de browser
  server.py --open [bestand…]  opent de bestanden in Rekenblad; start het zo nodig
                               (op de Mac in eigen vensters, anders in de browser).
                               Zo roept Rekenblad.app de server aan.
  server.py --window [bestand…] start in eigen vensters (wordt door --open gebruikt)
  server.py --status           exitcode 0 als Rekenblad draait
  server.py --stop [--force]   Rekenblad stoppen; exitcode 2 als er niet-opgeslagen wijzigingen zijn
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from workbook import DATA_DIR, Book, UserError, recent_files  # noqa: E402

STATIC = os.path.join(HERE, "static")
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                "/app.css": "app.css", "/favicon.svg": "favicon.svg", "/icon.png": "icon.png"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
IS_MAC = sys.platform == "darwin" and shutil.which("osascript") is not None
FIRST_PORT = 8765
PORT = 0
SERVER = None
GUI = None  # venster.Native als Rekenblad in eigen vensters draait
ICON = os.path.join(HERE, "mac", "icon.png")
MAX_UPLOAD = 300 * 1024 * 1024
DOC_RE = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
EVICT_AFTER = 30 * 60  # niet-gewijzigde bestanden na een half uur zonder gebruik uit het geheugen halen

# Elk browsertabblad heeft een eigen document (?doc=...), zodat je meerdere bestanden tegelijk open hebt.
DOCS = {}
DOC_PATHS = {}
DOCS_LOCK = threading.Lock()


def get_book(doc):
    if not doc or not DOC_RE.match(doc):
        raise UserError("Onbekend document. Ververs de pagina.")
    with DOCS_LOCK:
        book = DOCS.get(doc)
        if book is None:
            book = Book()
            path = DOC_PATHS.get(doc)
            if path and os.path.exists(path):
                try:
                    book.load_path(path)
                except Exception:
                    pass
            DOCS[doc] = book
        book.last_seen = time.time()
        return book


def find_book(doc):
    with DOCS_LOCK:
        return DOCS.get(doc)


def forget_doc(doc):
    """Venster gesloten: niet-gewijzigde documenten uit het geheugen halen."""
    with DOCS_LOCK:
        book = DOCS.get(doc)
        if book is not None and not book.dirty:
            del DOCS[doc]


def new_doc():
    doc = secrets.token_urlsafe(9)
    return doc, get_book(doc)


def rescue_dirty(only=None):
    """Vangnet: bewaar niet-opgeslagen werk als Rekenblad onverwacht stopt."""
    folder = os.path.join(DATA_DIR, "herstel")
    saved = []
    with DOCS_LOCK:
        books = [b for b in DOCS.values() if b.dirty and b.loaded]
    if only is not None:
        books = [only] if only.loaded else []
    for book in books:
        try:
            os.makedirs(folder, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            ext = ".xlsm" if book.kind == "xlsm" else ".xlsx"
            target = os.path.join(folder, "%s-%s%s" % (stamp, os.path.splitext(book.filename or "Werkboek")[0], ext))
            with open(target, "wb") as fh:
                fh.write(book.to_bytes("xlsx"))
            saved.append(target)
        except Exception:
            traceback.print_exc()
    return saved


def janitor():
    while True:
        time.sleep(60)
        now = time.time()
        with DOCS_LOCK:
            for doc, book in list(DOCS.items()):
                if not book.dirty and now - getattr(book, "last_seen", now) > EVICT_AFTER:
                    if book.path:
                        DOC_PATHS[doc] = book.path
                    del DOCS[doc]


def is_attachment(path):
    """Bijlagen uit Mail of Outlook staan in een tijdelijke map; daar wil je niet naartoe opslaan."""
    p = path.replace("\\", "/")
    return "/Library/Containers/" in p or "/Mail Downloads/" in p or \
        p.startswith("/private/var/folders/") or p.startswith("/var/folders/")


# ---------------------------------------------------------------------------
# macOS-bestandsvensters (via AppleScript)

def _osascript(lines, args):
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    proc = subprocess.run(cmd + list(args), capture_output=True, text=True)
    if proc.returncode != 0:
        if "-128" in proc.stderr or "User canceled" in proc.stderr or "geannuleerd" in proc.stderr:
            return None
        raise UserError("Het bestandsvenster kon niet geopend worden: %s" % proc.stderr.strip())
    return proc.stdout.strip() or None


def mac_choose_open():
    return _osascript([
        "on run argv",
        "activate",
        'set f to choose file with prompt "Kies een spreadsheet om te openen" of type '
        '{"xlsx", "xlsm", "csv", "org.openxmlformats.spreadsheetml.sheet", '
        '"org.openxmlformats.spreadsheetml.sheet.macroenabled", "public.comma-separated-values-text"}',
        "return POSIX path of f",
        "end run",
    ], [])


def mac_choose_save(default_name, default_dir):
    if not default_dir or not os.path.isdir(default_dir) or is_attachment(default_dir + "/"):
        default_dir = os.path.expanduser("~/Documents")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
    return _osascript([
        "on run argv",
        "activate",
        'set f to choose file name with prompt "Opslaan als" default name (item 1 of argv) '
        "default location (POSIX file (item 2 of argv) as alias)",
        "return POSIX path of f",
        "end run",
    ], [default_name, default_dir])


def open_url(url):
    if sys.platform == "darwin":
        subprocess.run(["open", url])
    else:
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Rekenblad/1.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200):
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _host_ok(self):
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            self.close_connection = True
            raise UserError("Het bestand is te groot.")
        self._raw = self.rfile.read(n) if n else b""

    def _jbody(self):
        return json.loads(self._raw.decode("utf-8")) if self._raw else {}

    def _state(self, extra=None):
        data = {"state": state_of(self.book)}
        if extra:
            data.update(extra)
        return data

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        self._raw = b""
        if method == "POST":
            try:
                self._read_body()
            except UserError as exc:
                return self._json({"error": str(exc)}, 413)
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        url = urlparse(self.path)
        path = url.path
        if method == "GET" and path in STATIC_FILES:
            return self._static(STATIC_FILES[path])
        if not path.startswith("/api/"):
            return self._send(404, b"Niet gevonden", "text/plain")
        name = path[5:]
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if name == "ping":
            return self._json({"app": "rekenblad"})
        doc = self.headers.get("X-Doc") or q.get("doc")
        if name == "download":
            return self._guarded(doc, lambda: self._download(q))
        # Alles wat iets leest of wijzigt vereist deze header: dat houdt andere websites buiten.
        if self.headers.get("X-Rekenblad") != "1":
            return self._json({"error": "Verboden"}, 403)
        if (method, name) in GLOBAL_ROUTES:
            return self._guarded(None, lambda: self._json(GLOBAL_ROUTES[(method, name)](self, q)), lock=False)
        handler = ROUTES.get((method, name))
        if handler is None:
            return self._json({"error": "Onbekende opdracht"}, 404)
        self._guarded(doc, lambda: self._json(handler(self, q)), lock=name not in NO_LOCK)

    def _guarded(self, doc, fn, lock=True):
        try:
            self.book = get_book(doc) if doc is not None or lock else None
            if self.book is not None and lock:
                with self.book.lock:
                    fn()
            else:
                fn()
        except UserError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._json({"error": "Er ging iets mis: %s" % exc}, 500)

    def _static(self, name):
        try:
            with open(os.path.join(STATIC, name), "rb") as fh:
                body = fh.read()
        except OSError:
            return self._send(404, b"Niet gevonden", "text/plain")
        self._send(200, body, MIME.get(os.path.splitext(name)[1], "application/octet-stream"))

    def _download(self, q):
        book = self.book
        fmt = q.get("fmt", "xlsx")
        sheet = q.get("sheet")
        if fmt == "csv":
            data = book._csv_bytes(sheet)
            base = os.path.splitext(book.filename or "export")[0]
            fname = "%s - %s.csv" % (base, sheet) if sheet else base + ".csv"
            ctype = "text/csv; charset=utf-8"
        else:
            book.set_active(sheet)
            data = book.to_bytes("xlsx")
            base = os.path.splitext(book.filename or "werkboek")[0]
            fname = base + (".xlsm" if book.kind == "xlsm" else ".xlsx")
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        disp = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
            fname.encode("ascii", "replace").decode().replace('"', ""), quote(fname))
        self._send(200, data, ctype, {"Content-Disposition": disp})


def state_of(book):
    st = book.state(IS_MAC)
    st["window"] = GUI is not None
    return st


# -- API-routes per document ----------------------------------------------------

def _target(h, q, body=None):
    """In eigen vensters opent een nieuw bestand in een nieuw venster als dit venster al iets toont."""
    want = q.get("elsewhere") == "1" or bool((body or {}).get("elsewhere"))
    if want and GUI is not None and h.book.loaded:
        return new_doc()
    return None, h.book


def _done(h, doc):
    if doc is None:
        return h._state()
    GUI.open_doc(doc)
    return h._state({"elsewhere": True})


def r_state(h, q):
    return h._state()


def r_new(h, q):
    doc, book = _target(h, q, h._jbody())
    book.new()
    return _done(h, doc)


def r_upload(h, q):
    name = unquote(h.headers.get("X-Filename") or "bestand.xlsx")
    doc, book = _target(h, q)
    with book.lock:
        book.load_bytes(h._raw, os.path.basename(name), None)
    return _done(h, doc)


def r_open_dialog(h, q):
    if not IS_MAC:
        raise UserError("Het Mac-bestandsvenster is hier niet beschikbaar.")
    body = h._jbody()
    path = mac_choose_open()
    if not path:
        return {"cancelled": True}
    doc, book = _target(h, q, body)
    with book.lock:
        load_into(book, path, None)
    with h.book.lock:
        return _done(h, doc)


def r_open_recent(h, q):
    body = h._jbody()
    path = body.get("path")
    if path not in recent_files():
        raise UserError("Dit bestand staat niet (meer) in de lijst met recente bestanden.")
    doc, book = _target(h, q, body)
    with book.lock:
        load_into(book, path, None)
    return _done(h, doc)


def r_rows(h, q):
    return h.book.get_rows(q.get("sheet", ""), int(q.get("start", 1)), int(q.get("count", 100)))


def r_set(h, q):
    b = h._jbody()
    return h._state(h.book.set_cells(b["sheet"], b.get("cells", [])))


def r_clear(h, q):
    b = h._jbody()
    return h._state(h.book.clear_range(b["sheet"], b["r1"], b["c1"], b["r2"], b["c2"]))


def r_format(h, q):
    b = h._jbody()
    return h._state(h.book.set_format(b["sheet"], b["r1"], b["c1"], b["r2"], b["c2"], b.get("props", {})))


def r_colwidth(h, q):
    b = h._jbody()
    h.book.set_col_width(b["sheet"], b["c"], b["px"])
    return h._state()


def r_insert(h, q):
    b = h._jbody()
    h.book.insert(b["sheet"], b["axis"], b["at"], b.get("count", 1))
    return h._state()


def r_delete(h, q):
    b = h._jbody()
    h.book.delete(b["sheet"], b["axis"], b["at"], b.get("count", 1))
    return h._state()


def r_sheet_add(h, q):
    return h._state(h.book.add_sheet(h._jbody().get("name")))


def r_sheet_rename(h, q):
    b = h._jbody()
    return h._state(h.book.rename_sheet(b["old"], b["new"]))


def r_sheet_delete(h, q):
    h.book.delete_sheet(h._jbody()["name"])
    return h._state()


def r_undo(h, q):
    h.book.undo()
    return h._state()


def r_redo(h, q):
    h.book.redo()
    return h._state()


def r_search(h, q):
    return h.book.search(q.get("q", ""), q.get("sheet") or None, q.get("case") == "1")


def r_replace(h, q):
    b = h._jbody()
    return h._state(h.book.replace_all(b.get("q", ""), b.get("repl", ""), b.get("sheet") or None,
                                       bool(b.get("case"))))


def r_save(h, q):
    b = h._jbody()
    if not h.book.path:
        return {"need_path": True}
    return h._state(h.book.save(None, b.get("sheet")))


def r_save_as(h, q):
    b = h._jbody()
    if not IS_MAC:
        raise UserError("Het Mac-bestandsvenster is hier niet beschikbaar.")
    book = h.book
    with book.lock:
        if not book.loaded:
            raise UserError("Er is geen bestand geopend.")
        base = os.path.splitext(book.filename or "Werkboek")[0]
        ext = ".xlsm" if book.kind == "xlsm" else ".xlsx"
        folder = os.path.dirname(book.path) if book.path else None
    path = mac_choose_save(base + ext, folder)
    if not path:
        return {"cancelled": True}
    if not os.path.splitext(path)[1]:
        path += ext
    with book.lock:
        book.attachment = False
        return h._state(book.save(path, b.get("sheet")))


def r_export(h, q):
    """Exporteren via het Mac-bewaarvenster (in eigen vensters kan de browser niet downloaden)."""
    b = h._jbody()
    if not IS_MAC:
        raise UserError("Het Mac-bestandsvenster is hier niet beschikbaar.")
    book, fmt, sheet = h.book, b.get("fmt", "xlsx"), b.get("sheet")
    with book.lock:
        if not book.loaded:
            raise UserError("Er is geen bestand geopend.")
        base = os.path.splitext(book.filename or "Werkboek")[0]
        if fmt == "csv":
            name = "%s - %s.csv" % (base, sheet) if sheet else base + ".csv"
        else:
            name = base + (".xlsm" if book.kind == "xlsm" else ".xlsx")
        folder = os.path.dirname(book.path) if book.path else None
    path = mac_choose_save(name, folder)
    if not path:
        return {"cancelled": True}
    with book.lock:
        if fmt == "csv":
            data = book._csv_bytes(sheet)
        else:
            book.set_active(sheet)
            data = book.to_bytes("xlsx")
        with open(path, "wb") as fh:
            fh.write(data)
    return {"path": path}


def load_into(book, path, data):
    """Open een bestand in dit document. Bijlagen krijgen geen opslagpad."""
    name = os.path.basename(path)
    if data is None:
        with open(path, "rb") as fh:
            data = fh.read()
    if is_attachment(path):
        book.load_bytes(data, name, None)
        book.attachment = True
        book.warnings = ["Dit is een bijlage (uit je mail). Kies bij Opslaan waar je het bestand wilt bewaren."] \
            + book.warnings
    else:
        book.load_bytes(data, name, path)
        book.attachment = False
        from workbook import remember_recent
        remember_recent(path)


# -- algemene routes ---------------------------------------------------------------

def g_open_external(h, q):
    """Rekenblad.app stuurt een bestand dat je in de Finder of Mail opende."""
    path = q.get("path") or ""
    with DOCS_LOCK:
        existing = [(d, b) for d, b in DOCS.items() if path and b.path == path]
    for doc, book in existing:
        with book.lock:
            if not book.dirty:
                load_into(book, path, h._raw)
            return {"doc": doc}
    doc, book = new_doc()
    with book.lock:
        load_into(book, path, h._raw)
    return {"doc": doc}


def g_show(h, q):
    """Toon een document in een eigen venster (doc leeg = nieuw leeg venster)."""
    if GUI is None:
        return {"window": False}
    doc = h._jbody().get("doc")
    if not doc:
        doc, _book = new_doc()
    get_book(doc)
    GUI.open_doc(doc)
    return {"window": True, "doc": doc}


def g_quit(h, q):
    force = bool(h._jbody().get("force"))
    with DOCS_LOCK:
        dirty = [b.filename for b in DOCS.values() if b.dirty]
    if dirty and not force:
        return {"dirty": dirty}
    if GUI is not None:
        def stop():
            time.sleep(0.2)
            rescue_dirty()
            os._exit(0)
        threading.Thread(target=stop, daemon=True).start()
    else:
        threading.Thread(target=SERVER.shutdown, daemon=True).start()
    return {"ok": True}


NO_LOCK = {"open_dialog", "save_as", "export"}

ROUTES = {
    ("GET", "state"): r_state, ("POST", "new"): r_new, ("POST", "upload"): r_upload,
    ("POST", "open_dialog"): r_open_dialog, ("POST", "open_recent"): r_open_recent,
    ("GET", "rows"): r_rows, ("POST", "set"): r_set, ("POST", "clear"): r_clear,
    ("POST", "format"): r_format, ("POST", "colwidth"): r_colwidth,
    ("POST", "insert"): r_insert, ("POST", "delete"): r_delete,
    ("POST", "sheet_add"): r_sheet_add, ("POST", "sheet_rename"): r_sheet_rename,
    ("POST", "sheet_delete"): r_sheet_delete, ("POST", "undo"): r_undo, ("POST", "redo"): r_redo,
    ("GET", "search"): r_search, ("POST", "replace"): r_replace,
    ("POST", "save"): r_save, ("POST", "save_as"): r_save_as, ("POST", "export"): r_export,
}
GLOBAL_ROUTES = {("POST", "open_external"): g_open_external, ("POST", "show"): g_show,
                 ("POST", "quit"): g_quit}


# ---------------------------------------------------------------------------
# Starten, openen, stoppen

def _ping(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=0.5) as resp:
            return json.loads(resp.read().decode()).get("app") == "rekenblad"
    except Exception:
        return False


def find_running():
    for port in range(FIRST_PORT, FIRST_PORT + 20):
        if _ping(port):
            return port
    return None


def _free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _post(port, name, body=b"", query="", ctype="application/json"):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/%s%s" % (port, name, query), data=body, method="POST",
        headers={"X-Rekenblad": "1", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def gui_available():
    if os.environ.get("REKENBLAD_BROWSER"):
        return False
    return sys.platform == "darwin" and importlib.util.find_spec("webview") is not None


def start_background(gui=False, files=()):
    os.makedirs(DATA_DIR, exist_ok=True)
    log = open(os.path.join(DATA_DIR, "rekenblad.log"), "ab")
    mode = "--window" if gui else "--serve"
    subprocess.Popen([sys.executable, os.path.abspath(__file__), mode] + [os.path.abspath(f) for f in files],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                     start_new_session=True, close_fds=True)
    for _ in range(100):
        time.sleep(0.1)
        port = find_running()
        if port:
            return port
    raise SystemExit("Rekenblad kon niet gestart worden. Zie %s" % os.path.join(DATA_DIR, "rekenblad.log"))


def cmd_open(files):
    port = find_running()
    if not port and gui_available():
        for f in files:
            if not os.access(f, os.R_OK):
                sys.stderr.write("Kan %s niet lezen.\n" % os.path.basename(f))
                sys.exit(1)
        start_background(gui=True, files=files)
        return
    port = port or start_background()
    base = "http://127.0.0.1:%d/" % port
    if not files:
        if not _post(port, "show", b"{}").get("window"):
            open_url(base)
        return
    for f in files:
        path = os.path.abspath(f)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            sys.stderr.write("Kan %s niet lezen: %s\n" % (os.path.basename(path), exc.strerror))
            sys.exit(1)
        try:
            res = _post(port, "open_external", data, "?path=" + quote(path), "application/octet-stream")
        except urllib.error.HTTPError as exc:
            msg = json.loads(exc.read().decode() or "{}").get("error", str(exc))
            sys.stderr.write("%s: %s\n" % (os.path.basename(path), msg))
            sys.exit(1)
        shown = _post(port, "show", json.dumps({"doc": res["doc"]}).encode())
        if not shown.get("window"):
            open_url(base + "?doc=" + res["doc"])


def cmd_stop(force):
    port = find_running()
    if not port:
        return 0
    res = _post(port, "quit", json.dumps({"force": force}).encode())
    if res.get("dirty"):
        sys.stderr.write("Niet opgeslagen: %s\n" % ", ".join(res["dirty"]))
        return 2
    return 0


def serve_window(port, files):
    """Eigen vensters: de webserver draait op de achtergrond, de vensters op de hoofdthread."""
    global PORT, SERVER, GUI
    PORT = port
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    SERVER.daemon_threads = True
    threading.Thread(target=janitor, daemon=True).start()
    docs = []
    for f in files:
        doc, book = new_doc()
        try:
            load_into(book, f, None)
        except Exception as exc:
            book.warnings = ["%s kon niet geopend worden: %s" % (os.path.basename(f), exc)]
        docs.append(doc)
    if not docs:
        docs.append(new_doc()[0])
    try:
        import venster
        GUI = venster.Native(PORT, find_book, forget_doc, ICON, rescue=lambda b: rescue_dirty(b))
    except Exception:
        traceback.print_exc()
        GUI = None
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    if GUI is None:
        # terugval: gewoon in de browser
        for doc in docs:
            open_url("http://127.0.0.1:%d/?doc=%s" % (PORT, doc))
        threading.Event().wait()
        return
    try:
        GUI.run(docs)
    except Exception:
        traceback.print_exc()
    saved = rescue_dirty()
    if saved and IS_MAC:
        subprocess.run(["osascript", "-e",
                        'display dialog "Rekenblad is gestopt terwijl er nog niet-opgeslagen wijzigingen waren. '
                        'Die zijn bewaard in de map herstel." buttons {"OK"} default button "OK" with title "Rekenblad"'])
        subprocess.run(["open", os.path.dirname(saved[0])])
    os._exit(0)


def serve(port, open_browser, first_file=None):
    global PORT, SERVER
    PORT = port
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    SERVER.daemon_threads = True
    threading.Thread(target=janitor, daemon=True).start()
    url = "http://127.0.0.1:%d/" % PORT
    print("")
    print("  Rekenblad draait op %s" % url)
    print("  Laat dit venster open zolang je werkt. Sluit het (of druk Ctrl+C) om te stoppen.")
    print("", flush=True)
    if first_file:
        doc = secrets.token_urlsafe(9)
        try:
            load_into(get_book(doc), os.path.abspath(first_file), None)
            url += "?doc=" + doc
        except Exception as exc:
            print("Kon %s niet openen: %s" % (first_file, exc))
    if open_browser:
        threading.Timer(0.4, open_url, [url]).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SERVER.server_close()
        print("\nRekenblad is gestopt.")


def main():
    global FIRST_PORT
    # ruimte voor lange rekenketens (bijvoorbeeld een lopend totaal over duizenden rijen)
    threading.stack_size(64 * 1024 * 1024)
    sys.setrecursionlimit(20000)
    ap = argparse.ArgumentParser(description="Rekenblad: Excel-bestanden lezen en bewerken")
    ap.add_argument("bestanden", nargs="*")
    ap.add_argument("--port", type=int, default=FIRST_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--open", action="store_true", help="op de achtergrond starten en bestanden openen")
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--window", action="store_true", help="in eigen vensters (macOS)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    FIRST_PORT = args.port

    if args.status:
        sys.exit(0 if find_running() else 1)
    if args.stop:
        sys.exit(cmd_stop(args.force))
    if args.open:
        cmd_open(args.bestanden)
        return

    running = find_running()
    if running:
        if args.serve:
            return
        if args.window:
            cmd_open(args.bestanden)
            return
        print("Rekenblad draait al, ik open het venster.")
        if args.bestanden:
            cmd_open(args.bestanden)
        elif not args.no_browser:
            open_url("http://127.0.0.1:%d/" % running)
        return
    port = next((p for p in range(FIRST_PORT, FIRST_PORT + 20) if _free(p)), None)
    if port is None:
        print("Geen vrije poort gevonden.")
        sys.exit(1)
    if args.window:
        serve_window(port, args.bestanden)
        return
    serve(port, open_browser=not (args.no_browser or args.serve),
          first_file=args.bestanden[0] if args.bestanden else None)


if __name__ == "__main__":
    main()
