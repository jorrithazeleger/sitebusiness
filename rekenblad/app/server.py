"""Rekenblad: start een kleine webserver op deze computer en opent de editor in de browser."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from workbook import Book, UserError, recent_files  # noqa: E402

STATIC = os.path.join(HERE, "static")
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                "/app.css": "app.css", "/favicon.svg": "favicon.svg"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
IS_MAC = sys.platform == "darwin" and shutil.which("osascript") is not None
BOOK = Book()
PORT = 0
MAX_UPLOAD = 300 * 1024 * 1024


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
    if not default_dir or not os.path.isdir(default_dir):
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


# ---------------------------------------------------------------------------
# HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Rekenblad/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # stil, behalve fouten
        pass

    # -- hulpfuncties
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
        host = self.headers.get("Host", "")
        return host in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            self.close_connection = True
            raise UserError("Het bestand is te groot.")
        self._raw = self.rfile.read(n) if n else b""

    def _body(self):
        return self._raw

    def _jbody(self):
        raw = self._body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _state(self, extra=None):
        data = {"state": BOOK.state(IS_MAC)}
        if extra:
            data.update(extra)
        return data

    # -- verzoeken
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
            self._send(403, b"Forbidden", "text/plain")
            return
        url = urlparse(self.path)
        path = url.path
        if method == "GET" and path in STATIC_FILES:
            return self._static(STATIC_FILES[path])
        if not path.startswith("/api/"):
            return self._send(404, b"Niet gevonden", "text/plain")
        name = path[5:]
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if name == "download":
            return self._guarded(lambda: self._download(q))
        if name == "ping":
            return self._json({"app": "rekenblad"})
        # Alles wat iets wijzigt of leest vereist deze header: dat houdt andere websites buiten.
        if self.headers.get("X-Rekenblad") != "1":
            return self._json({"error": "Verboden"}, 403)
        handler = ROUTES.get((method, name))
        if handler is None:
            return self._json({"error": "Onbekende opdracht"}, 404)
        self._guarded(lambda: self._json(handler(self, q)), lock=name not in NO_LOCK)

    def _guarded(self, fn, lock=True):
        try:
            if lock:
                with BOOK.lock:
                    fn()
            else:
                fn()
        except UserError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._json({"error": "Er ging iets mis: %s" % exc}, 500)

    def _static(self, name):
        path = os.path.join(STATIC, name)
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return self._send(404, b"Niet gevonden", "text/plain")
        self._send(200, body, MIME.get(os.path.splitext(name)[1], "application/octet-stream"))

    def _download(self, q):
        fmt = q.get("fmt", "xlsx")
        sheet = q.get("sheet")
        if fmt == "csv":
            data = BOOK._csv_bytes(sheet)
            base = os.path.splitext(BOOK.filename or "export")[0]
            fname = "%s - %s.csv" % (base, sheet) if sheet else base + ".csv"
            ctype = "text/csv; charset=utf-8"
        else:
            BOOK.set_active(sheet)
            data = BOOK.to_bytes("xlsx")
            base = os.path.splitext(BOOK.filename or "werkboek")[0]
            ext = ".xlsm" if BOOK.kind == "xlsm" else ".xlsx"
            fname = base + ext
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        disp = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
            fname.encode("ascii", "replace").decode().replace('"', ""), quote(fname))
        self._send(200, data, ctype, {"Content-Disposition": disp})


# -- API-routes ---------------------------------------------------------------

def r_state(h, q):
    return {"state": BOOK.state(IS_MAC)}


def r_new(h, q):
    BOOK.new()
    return h._state()


def r_upload(h, q):
    name = unquote(h.headers.get("X-Filename") or "bestand.xlsx")
    BOOK.load_bytes(h._body(), os.path.basename(name), None)
    return h._state()


def r_open_dialog(h, q):
    if not IS_MAC:
        raise UserError("Het Mac-bestandsvenster is hier niet beschikbaar.")
    path = mac_choose_open()
    if not path:
        return {"cancelled": True}
    with BOOK.lock:
        BOOK.load_path(path)
        return h._state()


def r_open_recent(h, q):
    path = h._jbody().get("path")
    if path not in recent_files():
        raise UserError("Dit bestand staat niet (meer) in de lijst met recente bestanden.")
    BOOK.load_path(path)
    return h._state()


def r_rows(h, q):
    return BOOK.get_rows(q.get("sheet", ""), int(q.get("start", 1)), int(q.get("count", 100)))


def r_set(h, q):
    b = h._jbody()
    res = BOOK.set_cells(b["sheet"], b.get("cells", []))
    return h._state(res)


def r_clear(h, q):
    b = h._jbody()
    res = BOOK.clear_range(b["sheet"], b["r1"], b["c1"], b["r2"], b["c2"])
    return h._state(res)


def r_format(h, q):
    b = h._jbody()
    res = BOOK.set_format(b["sheet"], b["r1"], b["c1"], b["r2"], b["c2"], b.get("props", {}))
    return h._state(res)


def r_colwidth(h, q):
    b = h._jbody()
    BOOK.set_col_width(b["sheet"], b["c"], b["px"])
    return h._state()


def r_insert(h, q):
    b = h._jbody()
    BOOK.insert(b["sheet"], b["axis"], b["at"], b.get("count", 1))
    return h._state()


def r_delete(h, q):
    b = h._jbody()
    BOOK.delete(b["sheet"], b["axis"], b["at"], b.get("count", 1))
    return h._state()


def r_sheet_add(h, q):
    res = BOOK.add_sheet(h._jbody().get("name"))
    return h._state(res)


def r_sheet_rename(h, q):
    b = h._jbody()
    res = BOOK.rename_sheet(b["old"], b["new"])
    return h._state(res)


def r_sheet_delete(h, q):
    BOOK.delete_sheet(h._jbody()["name"])
    return h._state()


def r_undo(h, q):
    BOOK.undo()
    return h._state()


def r_redo(h, q):
    BOOK.redo()
    return h._state()


def r_search(h, q):
    return BOOK.search(q.get("q", ""), q.get("sheet") or None, q.get("case") == "1")


def r_replace(h, q):
    b = h._jbody()
    res = BOOK.replace_all(b.get("q", ""), b.get("repl", ""), b.get("sheet") or None,
                           bool(b.get("case")))
    return h._state(res)


def r_save(h, q):
    b = h._jbody()
    if not BOOK.path:
        return {"need_path": True}
    res = BOOK.save(None, b.get("sheet"))
    return h._state(res)


def r_save_as(h, q):
    b = h._jbody()
    if not IS_MAC:
        raise UserError("Het Mac-bestandsvenster is hier niet beschikbaar.")
    with BOOK.lock:
        if not BOOK.loaded:
            raise UserError("Er is geen bestand geopend.")
        base = os.path.splitext(BOOK.filename or "Werkboek")[0]
        ext = ".xlsm" if BOOK.kind == "xlsm" else ".xlsx"
        folder = os.path.dirname(BOOK.path) if BOOK.path else None
    path = mac_choose_save(base + ext, folder)
    if not path:
        return {"cancelled": True}
    if not os.path.splitext(path)[1]:
        path += ext
    with BOOK.lock:
        res = BOOK.save(path, b.get("sheet"))
        return h._state(res)


NO_LOCK = {"open_dialog", "save_as"}

ROUTES = {
    ("GET", "state"): r_state,
    ("POST", "new"): r_new,
    ("POST", "upload"): r_upload,
    ("POST", "open_dialog"): r_open_dialog,
    ("POST", "open_recent"): r_open_recent,
    ("GET", "rows"): r_rows,
    ("POST", "set"): r_set,
    ("POST", "clear"): r_clear,
    ("POST", "format"): r_format,
    ("POST", "colwidth"): r_colwidth,
    ("POST", "insert"): r_insert,
    ("POST", "delete"): r_delete,
    ("POST", "sheet_add"): r_sheet_add,
    ("POST", "sheet_rename"): r_sheet_rename,
    ("POST", "sheet_delete"): r_sheet_delete,
    ("POST", "undo"): r_undo,
    ("POST", "redo"): r_redo,
    ("GET", "search"): r_search,
    ("POST", "replace"): r_replace,
    ("POST", "save"): r_save,
    ("POST", "save_as"): r_save_as,
}


# ---------------------------------------------------------------------------
# Starten

def _running_instance(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=0.5) as resp:
            return json.loads(resp.read().decode()).get("app") == "rekenblad"
    except Exception:
        return False


def _free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    global PORT
    # ruimte voor lange rekenketens (bijvoorbeeld een lopend totaal over duizenden rijen)
    threading.stack_size(64 * 1024 * 1024)
    sys.setrecursionlimit(20000)
    ap = argparse.ArgumentParser(description="Rekenblad: Excel-bestanden lezen en bewerken")
    ap.add_argument("bestand", nargs="?", help="optioneel: bestand om meteen te openen")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="open de browser niet automatisch")
    args = ap.parse_args()

    for port in range(args.port, args.port + 20):
        if _running_instance(port):
            url = "http://127.0.0.1:%d/" % port
            print("Rekenblad draait al op %s, ik open dat venster." % url)
            if not args.no_browser:
                webbrowser.open(url)
            return
        if _free(port):
            PORT = port
            break
    else:
        print("Geen vrije poort gevonden.")
        sys.exit(1)

    if args.bestand:
        try:
            BOOK.load_path(os.path.abspath(args.bestand))
        except Exception as exc:
            print("Kon %s niet openen: %s" % (args.bestand, exc))

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    url = "http://127.0.0.1:%d/" % PORT
    print("")
    print("  Rekenblad draait op %s" % url)
    print("  Laat dit venster open zolang je werkt. Sluit het (of druk Ctrl+C) om te stoppen.")
    print("")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRekenblad is gestopt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
