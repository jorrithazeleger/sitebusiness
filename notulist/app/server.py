"""Kleine webserver op 127.0.0.1 voor het venster van Notulist.

Het venster is een webpagina (HTML, CSS, JavaScript in app/web) die via deze server met de
rest van Notulist praat. De server luistert alleen op je eigen Mac en vraagt bij elk verzoek
een geheime sleutel, zodat andere websites in je browser er niet bij kunnen.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import instellingen as inst
import meetings
import samenvatting

log = logging.getLogger("notulist")
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MODELLEN = ["large-v3-turbo", "large-v3", "medium", "small", "base"]
TALEN = {"nl": "Nederlands", "en": "Engels", "de": "Duits", "fr": "Frans", "": "Zelf herkennen"}


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Het venster sluit soms een verbinding halverwege (bijvoorbeeld tijdens het afspelen).
        soort = sys.exc_info()[0]
        if soort and issubclass(soort, (ConnectionError, TimeoutError)):
            return
        log.exception("fout in venster-server")


class Server:
    def __init__(self, kern, acties=None):
        """acties: functies van de app (venster tonen, toestemmingen controleren, ...)."""
        self.kern = kern
        self.acties = acties or {}
        self.token = secrets.token_urlsafe(24)
        self.httpd = _HTTPServer(("127.0.0.1", 0), self._handler())
        self.poort = self.httpd.server_address[1]

    @property
    def url(self):
        return "http://127.0.0.1:%d/?t=%s" % (self.poort, self.token)

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, name="server", daemon=True).start()
        log.info("venster-server op poort %d", self.poort)

    def stop(self):
        self.httpd.shutdown()

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # niet elk verzoek in het logboek
                pass

            # -- hulpjes ----------------------------------------------------

            def _json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _fout(self, status, tekst):
                self._json({"fout": tekst}, status)

            def _body(self):
                lengte = int(self.headers.get("Content-Length") or 0)
                if not lengte:
                    return {}
                try:
                    return json.loads(self.rfile.read(lengte).decode("utf-8"))
                except ValueError:
                    return {}

            def _toegestaan(self, query):
                # Alleen verzoeken voor 127.0.0.1 met de juiste sleutel (tegen DNS-rebinding
                # en tegen andere websites die naar 127.0.0.1 proberen te sturen).
                host = self.headers.get("Host", "")
                if host not in ("127.0.0.1:%d" % server.poort, "localhost:%d" % server.poort):
                    return False
                sleutel = self.headers.get("X-Notulist-Token") or (query.get("t") or [""])[0]
                return secrets.compare_digest(sleutel, server.token)

            def _bestand(self, pad, type_=None):
                type_ = type_ or mimetypes.guess_type(pad)[0] or "application/octet-stream"
                grootte = os.path.getsize(pad)
                bereik = self.headers.get("Range")
                begin, einde = 0, grootte - 1
                status = 200
                if bereik and bereik.startswith("bytes="):
                    try:
                        a, b = bereik[6:].split(",")[0].split("-")
                        if a:
                            begin = int(a)
                            einde = int(b) if b else grootte - 1
                        else:
                            begin = max(0, grootte - int(b))
                        einde = min(einde, grootte - 1)
                        status = 206
                    except ValueError:
                        pass
                    if begin > einde or begin >= grootte:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % grootte)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                self.send_response(status)
                self.send_header("Content-Type", type_)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(einde - begin + 1))
                if status == 206:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (begin, einde, grootte))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if self.command == "HEAD":
                    return
                with open(pad, "rb") as fh:
                    fh.seek(begin)
                    rest = einde - begin + 1
                    while rest > 0:
                        blok = fh.read(min(65536, rest))
                        if not blok:
                            break
                        try:
                            self.wfile.write(blok)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        rest -= len(blok)

            # -- routes -----------------------------------------------------

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                url = urlparse(self.path)
                query = parse_qs(url.query)
                if url.path in ("/", "/index.html"):
                    if not self._toegestaan(query):
                        return self._fout(403, "geen toegang")
                    return self._bestand(os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
                if url.path.startswith("/web/"):
                    naam = os.path.basename(url.path)
                    pad = os.path.join(WEB, naam)
                    if naam and os.path.isfile(pad):
                        return self._bestand(pad)
                    return self._fout(404, "niet gevonden")
                if not self._toegestaan(query):
                    return self._fout(403, "geen toegang")
                delen = [d for d in url.path.split("/") if d]
                basis = server.kern.basis()
                if delen == ["api", "status"]:
                    return self._json(server.kern.status())
                if delen == ["api", "meetings"]:
                    vraag = (query.get("q") or [""])[0]
                    return self._json(meetings.zoek(basis, vraag) if vraag else meetings.lijst(basis))
                if len(delen) == 3 and delen[:2] == ["api", "meetings"]:
                    data = meetings.detail(basis, delen[2])
                    return self._json(data) if data else self._fout(404, "meeting niet gevonden")
                if len(delen) == 4 and delen[:2] == ["api", "meetings"] and delen[3] == "audio":
                    map_ = meetings.pad_van(basis, delen[2])
                    pad = meetings.afspeelbestand(map_) if map_ else None
                    return self._bestand(pad) if pad else self._fout(404, "geen audio")
                if delen == ["api", "instellingen"]:
                    return self._json({"instellingen": server.kern.config,
                                       "sleutel": samenvatting.lees_sleutel() is not None,
                                       "sleutel_omgeving": bool(os.environ.get("ANTHROPIC_API_KEY")),
                                       "modellen": MODELLEN, "talen": TALEN})
                return self._fout(404, "niet gevonden")

            def do_POST(self):
                url = urlparse(self.path)
                if not self._toegestaan(parse_qs(url.query)):
                    return self._fout(403, "geen toegang")
                delen = [d for d in url.path.split("/") if d]
                body = self._body()
                kern = server.kern
                basis = kern.basis()
                if delen == ["api", "opname", "start"]:
                    kern.start("handmatig", automatisch=False)
                    return self._json({"ok": True})
                if delen == ["api", "opname", "stop"]:
                    kern.stop(handmatig=True)
                    return self._json({"ok": True})
                if delen == ["api", "venster"]:
                    toon = server.acties.get("toon")
                    if toon:
                        toon(body.get("js"))
                    return self._json({"ok": True})
                if delen == ["api", "map"]:
                    os.makedirs(basis, exist_ok=True)
                    _open([basis])
                    return self._json({"ok": True})
                if delen == ["api", "toestemmingen"]:
                    controle = server.acties.get("toestemmingen")
                    return self._json({"tekst": controle() if controle else "Niet beschikbaar."})
                if delen == ["api", "logboek"]:
                    actie = server.acties.get("logboek")
                    if actie:
                        actie()
                    return self._json({"ok": True})
                if delen == ["api", "sleutel"]:
                    try:
                        if body.get("sleutel"):
                            samenvatting.bewaar_sleutel(body["sleutel"])
                        else:
                            samenvatting.wis_sleutel()
                    except samenvatting.SamenvattingFout as exc:
                        return self._fout(400, str(exc))
                    kern.gewijzigd()
                    return self._json({"ok": True, "sleutel": samenvatting.lees_sleutel() is not None})
                if len(delen) == 4 and delen[:2] == ["api", "meetings"]:
                    map_ = meetings.pad_van(basis, delen[2])
                    if not map_:
                        return self._fout(404, "meeting niet gevonden")
                    actie = delen[3]
                    if actie == "uitschrijven":
                        kern.plan(map_, "uitschrijven")
                    elif actie == "samenvatten":
                        if not samenvatting.beschikbaar():
                            return self._fout(400, "Vul eerst een API-sleutel in bij Instellingen.")
                        kern.plan(map_, "samenvatten")
                    elif actie == "finder":
                        _open(["-R", map_])
                    elif actie == "kopieer":
                        tekst = meetings.als_tekst(basis, delen[2]) or ""
                        if not _naar_klembord(tekst):
                            return self._json({"ok": False, "tekst": tekst})
                    elif actie == "exporteer":
                        tekst = meetings.als_tekst(basis, delen[2]) or ""
                        map_uit = os.path.expanduser("~/Downloads")
                        os.makedirs(map_uit, exist_ok=True)
                        pad = os.path.join(map_uit, meetings.exportnaam(basis, delen[2]))
                        with open(pad, "w", encoding="utf-8") as fh:
                            fh.write(tekst)
                        _open(["-R", pad])
                        return self._json({"ok": True, "pad": pad})
                    else:
                        return self._fout(404, "onbekende actie")
                    return self._json({"ok": True})
                return self._fout(404, "niet gevonden")

            def do_PATCH(self):
                url = urlparse(self.path)
                if not self._toegestaan(parse_qs(url.query)):
                    return self._fout(403, "geen toegang")
                delen = [d for d in url.path.split("/") if d]
                body = self._body()
                kern = server.kern
                if len(delen) == 3 and delen[:2] == ["api", "meetings"]:
                    gedaan = body.get("gedaan")
                    if gedaan is not None and not isinstance(gedaan, list):
                        return self._fout(400, "gedaan moet een lijst zijn")
                    if not meetings.wijzig(kern.basis(), delen[2], body.get("titel"), gedaan):
                        return self._fout(404, "meeting niet gevonden")
                    kern.gewijzigd()
                    return self._json(meetings.detail(kern.basis(), delen[2]))
                if delen == ["api", "instellingen"]:
                    nieuw = {k: v for k, v in body.items() if k in inst.STANDAARD}
                    fout = _controleer(nieuw)
                    if fout:
                        return self._fout(400, fout)
                    herstart = any(nieuw.get(k, kern.config[k]) != kern.config[k]
                                   for k in ("model", "taal"))
                    kern.config.update(nieuw)
                    inst.bewaar(kern.config)
                    kern.detector.start_na = kern.config["start_na_seconden"]
                    kern.detector.stop_na = kern.config["stop_na_seconden"]
                    if herstart:
                        import transcriptie
                        kern.transcriber = transcriptie.Transcriber(kern.config["model"], kern.config["taal"])
                    kern.gewijzigd()
                    return self._json({"ok": True, "instellingen": kern.config})
                return self._fout(404, "niet gevonden")

            def do_DELETE(self):
                url = urlparse(self.path)
                if not self._toegestaan(parse_qs(url.query)):
                    return self._fout(403, "geen toegang")
                delen = [d for d in url.path.split("/") if d]
                kern = server.kern
                if len(delen) == 3 and delen[:2] == ["api", "meetings"]:
                    lopend = kern.opname and os.path.basename(kern.opname.map) == delen[2]
                    if lopend:
                        return self._fout(409, "Deze meeting wordt nog opgenomen.")
                    if not meetings.naar_prullenmand(kern.basis(), delen[2], server.acties.get("prullenmand")):
                        return self._fout(404, "meeting niet gevonden")
                    kern.gewijzigd()
                    return self._json({"ok": True})
                return self._fout(404, "niet gevonden")

        return Handler


def _open(args):
    if sys.platform == "darwin":
        subprocess.run(["open"] + args, capture_output=True)


def _naar_klembord(tekst: str) -> bool:
    if sys.platform != "darwin":
        return False
    r = subprocess.run(["pbcopy"], input=tekst.encode("utf-8"), capture_output=True)
    return r.returncode == 0


def _controleer(nieuw: dict):
    for sleutel, waarde in nieuw.items():
        standaard = inst.STANDAARD[sleutel]
        if isinstance(standaard, bool):
            if not isinstance(waarde, bool):
                return "%s moet aan of uit zijn" % sleutel
        elif isinstance(standaard, int):
            if not isinstance(waarde, int) or isinstance(waarde, bool) or waarde < 1:
                return "%s moet een positief getal zijn" % sleutel
        elif not isinstance(waarde, str):
            return "%s moet tekst zijn" % sleutel
    if "model" in nieuw and nieuw["model"] not in MODELLEN:
        return "onbekend model"
    return None
