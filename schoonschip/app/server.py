"""Schoonschip: een kleine webserver op deze computer, met de app in een eigen venster.

Gebruik:
  server.py                 draait in de voorgrond (Terminal) en opent de browser
  server.py --open          start Schoonschip in een eigen venster, of haalt het naar voren
                            (zo roept Schoonschip.app de server aan)
  server.py --status        exitcode 0 als Schoonschip draait
  server.py --stop          Schoonschip stoppen
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import scans  # noqa: E402
from veilig import IS_MAC, UserError, home  # noqa: E402

APP_ID = "schoonschip"
DATA_DIR = os.path.expanduser("~/Library/Application Support/Schoonschip") if sys.platform == "darwin" \
    else os.path.expanduser("~/.schoonschip")
STATIC = os.path.join(HERE, "static")
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/app.css": "app.css",
                "/icon.png": "icon.png"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
ICON = os.path.join(HERE, "mac", "icon.png")
FIRST_PORT = 8790
PORT = 0
SERVER = None
GUI = None
TOKEN = secrets.token_urlsafe(18)

JOBS = {}
REG = {}          # module -> {id: onderdeel}
REG_LOCK = threading.Lock()
ICONS = {}

# Welke scan vult welke lijst met onderdelen
SCAN_KINDS = {
    "junk": ("junk", lambda job, p: scans.scan_junk(job)),
    "large": ("large", lambda job, p: scans.scan_large(job, p.get("min_mb", 100), bool(p.get("deep")))),
    "downloads": ("downloads", lambda job, p: scans.scan_downloads(job)),
    "dupes": ("dupes", lambda job, p: scans.scan_dupes(job, p.get("folder"), p.get("min_mb", 1))),
    "space": ("space", lambda job, p: scans.scan_space(job, p.get("path"))),
    "apps": (None, lambda job, p: scans.list_apps(job)),
    "leftovers": ("leftovers", lambda job, p: scans.app_leftovers(_known_app(p.get("path")))),
    "startup": ("startup", lambda job, p: scans.list_startup(job)),
    "task": (None, lambda job, p: scans.run_task(job, p.get("key"))),
    "smart": (None, lambda job, p: scans.smart_scan(job)),
}


def _known_app(path):
    if path not in scans.app_paths():
        raise UserError("Onbekend programma.")
    return path


# ---------------------------------------------------------------------------
# Onderdelen een nummer geven

def _register(module, result):
    """Geef elk gevonden onderdeel een nummer en onthoud het. Paden blijven zo aan de serverkant."""
    reg = {}

    def add(it):
        it["id"] = "%s%d" % (module[0], len(reg) + 1)
        reg[it["id"]] = dict(it)

    if "groups" in result:
        for g in result["groups"]:
            for it in g["items"]:
                add(it)
    if "items" in result:
        for it in result["items"]:
            if module == "space" and not it.get("can_trash"):
                it["id"] = None
                continue
            if module == "space":
                it.setdefault("action", "trash")
            add(it)
    with REG_LOCK:
        REG[module] = reg


def _lookup(module, ids):
    with REG_LOCK:
        reg = REG.get(module) or {}
        items = [reg[i] for i in ids if i in reg]
    if len(items) != len(set(ids)):
        raise UserError("De lijst is verouderd. Scan opnieuw.")
    return items


def _forget(module, ids):
    with REG_LOCK:
        reg = REG.get(module) or {}
        for i in ids:
            reg.pop(i, None)


# ---------------------------------------------------------------------------
# Taken op de achtergrond

def start_job(kind, fn, after=None):
    job = scans.Job(kind)
    JOBS[job.id] = job

    def run():
        try:
            res = fn(job)
            if after:
                after(res)
            job.result = res
            job.progress = 1.0
            job.status = "done"
        except scans.Cancelled:
            job.status = "cancelled"
        except UserError as exc:
            job.error = str(exc)
            job.status = "error"
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            job.error = "Er ging iets mis: %s" % exc
            job.status = "error"
    threading.Thread(target=run, daemon=True).start()
    # oude taken opruimen
    for jid, j in list(JOBS.items()):
        if j.status != "running" and time.time() - j.started > 3600:
            JOBS.pop(jid, None)
    return job


def _after_scan(kind, module):
    def after(res):
        if module:
            _register(module, res)
        if kind == "smart":
            _register("junk", res["junk"])
            _register("downloads", res["downloads"])
    return after


# ---------------------------------------------------------------------------
# Wat je al hebt opgeruimd

def history_path():
    return os.path.join(DATA_DIR, "historie.json")


def load_history():
    try:
        with open(history_path(), encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {"total": 0, "runs": []}


def add_history(module, freed, trashed):
    if not freed and not trashed:
        return
    data = load_history()
    data["total"] = int(data.get("total", 0)) + int(freed) + int(trashed)
    data.setdefault("runs", []).append({"date": dt.datetime.now().isoformat(timespec="seconds"),
                                        "module": module, "freed": freed, "trashed": trashed})
    data["runs"] = data["runs"][-200:]
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = history_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, history_path())
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Mac-hulpjes

def _osascript(lines, args=()):
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    proc = subprocess.run(cmd + list(args), capture_output=True, text=True)
    if proc.returncode != 0:
        if "-128" in proc.stderr or "User canceled" in proc.stderr or "geannuleerd" in proc.stderr:
            return None
        raise UserError(proc.stderr.strip() or "Dat lukte niet.")
    return proc.stdout.strip() or None


def choose_folder():
    if not IS_MAC:
        raise UserError("Een map kiezen kan alleen op de Mac.")
    return _osascript([
        "on run argv", "activate",
        'set f to choose folder with prompt "Kies een map om op dubbele bestanden te controleren" '
        "default location (POSIX file (item 1 of argv) as alias)",
        "return POSIX path of f", "end run"], [home()])


def reveal(path):
    if IS_MAC:
        subprocess.run(["open", "-R", path])
    else:
        raise UserError("Tonen in de Finder kan alleen op de Mac.")


SETTINGS = {
    "fda": "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    "login": "x-apple.systempreferences:com.apple.LoginItems-Settings.extension",
    "storage": "x-apple.systempreferences:com.apple.settings.Storage",
}


def app_icon_png(path):
    """PNG van het programma-icoon, via macOS zelf (werkt ook voor nieuwe programma's zonder .icns)."""
    if path in ICONS:
        return ICONS[path]
    data = None
    try:
        from AppKit import NSBitmapImageRep, NSWorkspace
        img = NSWorkspace.sharedWorkspace().iconForFile_(path)
        img.setSize_((64, 64))
        rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
        png = rep.representationUsingType_properties_(4, None)  # 4 = PNG
        data = bytes(png)
    except Exception:
        info = scans.read_info(path)
        icon = info.get("CFBundleIconFile")
        if icon and IS_MAC:
            src = os.path.join(path, "Contents", "Resources", icon if icon.endswith(".icns") else icon + ".icns")
            out = os.path.join(DATA_DIR, "iconen")
            os.makedirs(out, exist_ok=True)
            dst = os.path.join(out, "%s.png" % abs(hash(path)))
            proc = subprocess.run(["sips", "-s", "format", "png", "-Z", "64", src, "--out", dst],
                                  capture_output=True)
            if proc.returncode == 0 and os.path.exists(dst):
                with open(dst, "rb") as fh:
                    data = fh.read()
    ICONS[path] = data
    return data


def open_url(url):
    if sys.platform == "darwin":
        subprocess.run(["open", url])
    else:
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "Schoonschip/1.0"
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

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        body = b""
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1024 * 1024:
                return self._json({"error": "Te groot"}, 413)
            body = self.rfile.read(n) if n else b""
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        url = urlparse(self.path)
        path = url.path
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if method == "GET" and path in STATIC_FILES:
            return self._static(STATIC_FILES[path])
        if not path.startswith("/api/"):
            return self._send(404, b"Niet gevonden", "text/plain")
        name = path[5:]
        if name == "ping":
            return self._json({"app": APP_ID})
        if name == "show" and method == "POST":
            if GUI is not None:
                GUI.show()
            return self._json({"window": GUI is not None})
        # Alles wat iets leest of opruimt vereist het geheime sleutelwoord van deze sessie.
        # Zo kan een website in je browser nooit iets op je Mac weggooien.
        token = self.headers.get("X-Token") or q.get("t")
        if not token or not secrets.compare_digest(token, TOKEN):
            return self._json({"error": "Verboden"}, 403)
        route = ROUTES.get((method, name))
        if route is None:
            return self._json({"error": "Onbekende opdracht"}, 404)
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
            res = route(self, q, data)
            if isinstance(res, tuple):  # (bytes, content-type)
                return self._send(200, res[0], res[1], {"Cache-Control": "max-age=3600"})
            self._json(res)
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


# -- routes ---------------------------------------------------------------------

def r_overview(h, q, d):
    data = scans.overview()
    hist = load_history()
    data["history_total"] = hist.get("total", 0)
    data["window"] = GUI is not None
    data["home"] = home()
    return data


def r_start(h, q, d):
    kind = d.get("kind")
    if kind not in SCAN_KINDS:
        raise UserError("Onbekende scan.")
    module, fn = SCAN_KINDS[kind]
    params = d.get("params") or {}
    # niet twee keer dezelfde scan tegelijk
    for j in JOBS.values():
        if j.kind == kind and j.status == "running" and kind not in ("task", "leftovers"):
            return {"job": j.id}
    job = start_job(kind, lambda job: fn(job, params), _after_scan(kind, module))
    return {"job": job.id}


def r_job(h, q, d):
    job = JOBS.get(q.get("id", ""))
    if job is None:
        raise UserError("Deze taak bestaat niet meer.")
    return job.as_dict()


def r_cancel(h, q, d):
    job = JOBS.get(d.get("id", ""))
    if job is not None:
        job.cancel.set()
    return {"ok": True}


def r_clean(h, q, d):
    module = d.get("module")
    ids = [str(i) for i in d.get("ids") or []]
    if not ids:
        raise UserError("Je hebt niets gekozen.")
    items = _lookup(module, ids)
    if module == "leftovers":
        app = next((i for i in items if i.get("is_app")), None)
        if app is not None:
            bundle = (scans.read_info(app["path"]).get("CFBundleIdentifier") or "").lower()
            if bundle and bundle in scans.running_apps():
                raise UserError("%s is nog open. Stop het programma eerst (⌘Q) en probeer het opnieuw." % app["name"])
    for j in JOBS.values():
        if j.kind == "clean" and j.status == "running":
            raise UserError("Er wordt al opgeruimd. Even geduld.")

    def after(res):
        _forget(module, res["done"])
        add_history(module, res["freed"], res["trashed"])
    job = start_job("clean", lambda job: scans.clean(job, items), after)
    return {"job": job.id}


def r_reveal(h, q, d):
    items = _lookup(d.get("module"), [d.get("id")]) if d.get("id") else []
    path = items[0]["path"] if items else d.get("path")
    if not items:
        # ruimtekaart en programma's: alleen paden die daar horen
        if not path or not (scans.space_root_ok(path) or path in scans.app_paths()
                            or path.startswith(("/Library/LaunchAgents/", "/Library/LaunchDaemons/"))):
            raise UserError("Dat pad kan ik niet tonen.")
    reveal(path)
    return {"ok": True}


def r_choose_folder(h, q, d):
    return {"folder": choose_folder()}


def r_appicon(h, q, d):
    path = q.get("path", "")
    if path not in scans.app_paths():
        raise UserError("Onbekend programma.")
    data = app_icon_png(path)
    if not data:
        raise UserError("Geen icoon.")
    return data, "image/png"


def r_quit_app(h, q, d):
    bundle = d.get("bundle") or ""
    if bundle.lower() not in scans.running_apps():
        raise UserError("Dat programma is niet (meer) open.")
    if bundle.lower() == "nl.schoonschip.app":
        raise UserError("Dat ben ik zelf.")
    return {"ok": scans.quit_app(bundle)}


def r_settings(h, q, d):
    url = SETTINGS.get(d.get("pane"))
    if not url:
        raise UserError("Onbekende instelling.")
    if IS_MAC:
        subprocess.run(["open", url])
    return {"ok": True}


def r_tasks(h, q, d):
    tasks = [{k: v for k, v in t.items() if k != "cmd"} for t in scans.TASKS]
    snaps = scans.snapshot_count()
    for t in tasks:
        if t["key"] == "snapshots":
            t["count"] = snaps
    return {"tasks": tasks, "mac": IS_MAC}


def r_quit(h, q, d):
    def stop():
        time.sleep(0.2)
        os._exit(0)
    threading.Thread(target=stop, daemon=True).start()
    return {"ok": True}


ROUTES = {
    ("GET", "overview"): r_overview, ("POST", "start"): r_start, ("GET", "job"): r_job,
    ("POST", "cancel"): r_cancel, ("POST", "clean"): r_clean, ("POST", "reveal"): r_reveal,
    ("POST", "choose_folder"): r_choose_folder, ("GET", "appicon"): r_appicon,
    ("POST", "quit_app"): r_quit_app, ("POST", "settings"): r_settings, ("GET", "tasks"): r_tasks,
    ("POST", "quit"): r_quit,
}


# ---------------------------------------------------------------------------
# Starten, openen, stoppen

def _ping(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=0.5) as resp:
            return json.loads(resp.read().decode()).get("app") == APP_ID
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


def _post(port, name, body=b"{}"):
    req = urllib.request.Request("http://127.0.0.1:%d/api/%s" % (port, name), data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def gui_available():
    if os.environ.get("SCHOONSCHIP_BROWSER"):
        return False
    return sys.platform == "darwin" and importlib.util.find_spec("webview") is not None


def url_for(port):
    return "http://127.0.0.1:%d/?t=%s" % (port, TOKEN)


def cmd_open():
    port = find_running()
    if port:
        if not _post(port, "show").get("window"):
            sys.stderr.write("Schoonschip draait al in de browser.\n")
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    log = open(os.path.join(DATA_DIR, "schoonschip.log"), "ab")
    mode = "--window" if gui_available() else "--serve"
    subprocess.Popen([sys.executable, os.path.abspath(__file__), mode],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
    for _ in range(100):
        time.sleep(0.1)
        if find_running():
            return
    raise SystemExit("Schoonschip kon niet gestart worden. Zie %s" % os.path.join(DATA_DIR, "schoonschip.log"))


def cmd_stop():
    port = find_running()
    if not port:
        return 0
    req = urllib.request.Request("http://127.0.0.1:%d/api/quit" % port, data=b"{}", method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
    return 0


def _make_server(port):
    global PORT, SERVER
    PORT = port
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    SERVER.daemon_threads = True


def serve_window(port):
    global GUI
    _make_server(port)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    try:
        import venster
        GUI = venster.Native(url_for(PORT), ICON)
    except Exception:
        traceback.print_exc()
        GUI = None
    if GUI is None:
        open_url(url_for(PORT))
        threading.Event().wait()
        return
    try:
        GUI.run()
    except Exception:
        traceback.print_exc()
    os._exit(0)


def serve(port, open_browser):
    _make_server(port)
    url = url_for(PORT)
    print("")
    print("  Schoonschip draait op %s" % url)
    print("  Laat dit venster open zolang je werkt. Sluit het (of druk Ctrl+C) om te stoppen.")
    print("", flush=True)
    if open_browser:
        threading.Timer(0.4, open_url, [url]).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SERVER.server_close()
        print("\nSchoonschip is gestopt.")


def main():
    global FIRST_PORT
    ap = argparse.ArgumentParser(description="Schoonschip: ruim je Mac op")
    ap.add_argument("--port", type=int, default=FIRST_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--window", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    FIRST_PORT = args.port

    if args.status:
        sys.exit(0 if find_running() else 1)
    if args.stop:
        sys.exit(cmd_stop())
    if args.open:
        cmd_open()
        return
    running = find_running()
    if running:
        if not (args.serve or args.window):
            print("Schoonschip draait al.")
            try:
                _post(running, "show")
            except Exception:
                pass
        return
    port = next((p for p in range(FIRST_PORT, FIRST_PORT + 20) if _free(p)), None)
    if port is None:
        print("Geen vrije poort gevonden.")
        sys.exit(1)
    if args.window:
        serve_window(port)
        return
    serve(port, open_browser=not (args.no_browser or args.serve))


if __name__ == "__main__":
    main()
