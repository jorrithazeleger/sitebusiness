"""Herkent of er een meeting bezig is.

Vanaf macOS 14 houdt CoreAudio per programma bij of het de microfoon (invoer) of de speakers
(uitvoer) gebruikt. Pakt een meeting-app zoals Zoom, Teams of een browser met Google Meet de
microfoon, dan is er een meeting begonnen. Dat uitlezen gebeurt hieronder met ctypes, zodat er
geen extra pakketten nodig zijn.

De beslislogica (MeetingDetector) staat los van macOS, zodat die ook elders te testen is.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Welke programma's tellen als meeting-app
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeetingApp:
    naam: str
    bundels: tuple = ()  # begin van de bundle-id, bijvoorbeeld "us.zoom."
    paden: tuple = ()    # stukje van het programmapad, voor hulpprocessen zonder bundle-id
    browser: bool = False


MEETING_APPS = (
    MeetingApp("Zoom", ("us.zoom.",), ("/zoom.us.app/",)),
    MeetingApp("Teams", ("com.microsoft.teams",), ("/Microsoft Teams",)),
    MeetingApp("Webex", ("com.cisco.webex", "Cisco-Systems.Spark"), ("/Webex.app/",)),
    MeetingApp("Slack", ("com.tinyspeck.slackmacgap",), ("/Slack.app/",)),
    MeetingApp("FaceTime", ("com.apple.FaceTime",), ("/FaceTime.app/",)),
    MeetingApp("Discord", ("com.hnc.Discord",), ("/Discord.app/",)),
    MeetingApp("WhatsApp", ("net.whatsapp.WhatsApp", "desktop.WhatsApp"), ("/WhatsApp.app/",)),
    MeetingApp("Skype", ("com.skype.",), ("/Skype.app/",)),
    MeetingApp("GoTo", ("com.logmein.", "com.goto."), ("/GoTo",)),
    # Browsers: Google Meet, Teams of Zoom in een tabblad
    MeetingApp("Chrome", ("com.google.Chrome",), ("/Google Chrome",), browser=True),
    MeetingApp("Edge", ("com.microsoft.edgemac",), ("/Microsoft Edge",), browser=True),
    MeetingApp("Brave", ("com.brave.Browser",), ("/Brave Browser",), browser=True),
    MeetingApp("Arc", ("company.thebrowser.",), ("/Arc.app/",), browser=True),
    MeetingApp("Firefox", ("org.mozilla.firefox",), ("/Firefox.app/",), browser=True),
    MeetingApp("Safari", ("com.apple.Safari", "com.apple.WebKit"), ("/Safari.app/",), browser=True),
    MeetingApp("Vivaldi", ("com.vivaldi.",), ("/Vivaldi.app/",), browser=True),
    MeetingApp("Opera", ("com.operasoftware.",), ("/Opera.app/",), browser=True),
)


@dataclass(frozen=True)
class AudioGebruiker:
    """Een programma dat op dit moment audio gebruikt."""
    pid: int
    bundel: str = ""
    pad: str = ""
    invoer: bool = False  # gebruikt de microfoon
    uitvoer: bool = False  # speelt geluid af


def herken_app(gebruiker: AudioGebruiker, browsers: bool = True, extra: tuple = ()):
    """Geeft de MeetingApp terug waar dit programma bij hoort, of None."""
    for app in tuple(extra) + MEETING_APPS:
        if app.browser and not browsers:
            continue
        if gebruiker.bundel and any(gebruiker.bundel.startswith(b) for b in app.bundels):
            return app
        if gebruiker.pad and any(p in gebruiker.pad for p in app.paden):
            return app
    return None


def actieve_meeting(gebruikers, eigen_pids=(), browsers=True, extra=(), lopend=None):
    """Bepaalt welke meeting-app nu een meeting heeft.

    Een meeting loopt zolang een meeting-app de microfoon gebruikt. Alleen geluid afspelen
    telt niet: Teams en Zoom houden de speakers ook na de meeting open (voor beltonen en
    meldingen), waardoor een opname anders nooit zou stoppen. Loopt er al een opname
    (lopend = naam van die app), dan gaat die app voor als er meer apps de microfoon gebruiken.
    """
    eigen = set(eigen_pids)
    kandidaat = None
    for g in gebruikers:
        if g.pid in eigen or not g.invoer:
            continue
        app = herken_app(g, browsers=browsers, extra=extra)
        if not app:
            continue
        if app.naam == lopend:
            return app.naam
        kandidaat = kandidaat or app.naam
    return kandidaat


def beschrijf(gebruikers, eigen_pids=()):
    """Korte, vaste beschrijving van wie de microfoon gebruikt, voor het logboek en het venster."""
    eigen = set(eigen_pids)
    regels = []
    for g in gebruikers:
        if g.pid in eigen or not g.invoer:
            continue
        app = herken_app(g)
        naam = app.naam if app else (g.bundel or os.path.basename(g.pad) or "pid %d" % g.pid)
        regels.append(naam)
    return sorted(set(regels))


@dataclass
class MeetingDetector:
    """Voorkomt dat een korte piek een opname start of een korte stilte er een stopt.

    update() krijgt elke paar seconden de naam van de actieve meeting-app (of None) en geeft
    ("start", app), ("stop", app) of None terug.
    """
    start_na: float = 4.0
    stop_na: float = 20.0
    bezig: str | None = None
    _eerst_gezien: float | None = None
    _laatst_gezien: float | None = None
    _kandidaat: str | None = None

    def update(self, app, nu: float):
        if self.bezig is None:
            if app is None:
                self._eerst_gezien = None
                self._kandidaat = None
                return None
            if app != self._kandidaat:
                self._kandidaat = app
                self._eerst_gezien = nu
            if nu - self._eerst_gezien >= self.start_na:
                self.bezig = app
                self._laatst_gezien = nu
                self._kandidaat = None
                self._eerst_gezien = None
                return ("start", app)
            return None
        if app is not None:
            self._laatst_gezien = nu
            return None
        if nu - self._laatst_gezien >= self.stop_na:
            klaar = self.bezig
            self.reset()
            return ("stop", klaar)
        return None

    def reset(self):
        self.bezig = None
        self._eerst_gezien = None
        self._laatst_gezien = None
        self._kandidaat = None


# ---------------------------------------------------------------------------
# CoreAudio uitlezen (alleen macOS 14 en nieuwer)
# ---------------------------------------------------------------------------

def _fourcc(code: str) -> int:
    return struct.unpack(">I", code.encode("ascii"))[0]


K_SYSTEM_OBJECT = 1
K_SCOPE_GLOBAL = _fourcc("glob")
K_ELEMENT_MAIN = 0
K_PROCESS_OBJECT_LIST = _fourcc("prs#")  # kAudioHardwarePropertyProcessObjectList
K_PROCESS_PID = _fourcc("ppid")          # kAudioProcessPropertyPID
K_PROCESS_BUNDLE_ID = _fourcc("pbid")    # kAudioProcessPropertyBundleID
K_PROCESS_RUNNING_INPUT = _fourcc("piri")   # kAudioProcessPropertyIsRunningInput
K_PROCESS_RUNNING_OUTPUT = _fourcc("piro")  # kAudioProcessPropertyIsRunningOutput
K_CFSTRING_UTF8 = 0x08000100


class _Adres(ctypes.Structure):
    _fields_ = [("mSelector", ctypes.c_uint32), ("mScope", ctypes.c_uint32),
                ("mElement", ctypes.c_uint32)]


class CoreAudioNietBeschikbaar(RuntimeError):
    pass


class CoreAudio:
    """Leest uit welke programma's de microfoon en speakers gebruiken."""

    def __init__(self):
        if sys.platform != "darwin":
            raise CoreAudioNietBeschikbaar("alleen op macOS")
        self.ca = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        p = ctypes.POINTER
        self.ca.AudioObjectGetPropertyDataSize.argtypes = [
            ctypes.c_uint32, p(_Adres), ctypes.c_uint32, ctypes.c_void_p, p(ctypes.c_uint32)]
        self.ca.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32
        self.ca.AudioObjectGetPropertyData.argtypes = [
            ctypes.c_uint32, p(_Adres), ctypes.c_uint32, ctypes.c_void_p, p(ctypes.c_uint32),
            ctypes.c_void_p]
        self.ca.AudioObjectGetPropertyData.restype = ctypes.c_int32
        self.cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long,
                                               ctypes.c_uint32]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.cf.CFRelease.restype = None
        self.libc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.libc.proc_pidpath.restype = ctypes.c_int
        # Bestaat de procesadministratie (macOS 14+)? Zo niet, dan meteen een duidelijke fout.
        if self._grootte(K_SYSTEM_OBJECT, K_PROCESS_OBJECT_LIST) is None:
            raise CoreAudioNietBeschikbaar("macOS 14 (Sonoma) of nieuwer nodig")

    def _adres(self, selector):
        return _Adres(selector, K_SCOPE_GLOBAL, K_ELEMENT_MAIN)

    def _grootte(self, obj, selector):
        adres = self._adres(selector)
        size = ctypes.c_uint32(0)
        status = self.ca.AudioObjectGetPropertyDataSize(obj, ctypes.byref(adres), 0, None,
                                                        ctypes.byref(size))
        return size.value if status == 0 else None

    def _lees(self, obj, selector, ctype):
        adres = self._adres(selector)
        waarde = ctype()
        size = ctypes.c_uint32(ctypes.sizeof(waarde))
        status = self.ca.AudioObjectGetPropertyData(obj, ctypes.byref(adres), 0, None,
                                                    ctypes.byref(size), ctypes.byref(waarde))
        return waarde.value if status == 0 else None

    def _bundel(self, obj):
        ref = self._lees(obj, K_PROCESS_BUNDLE_ID, ctypes.c_void_p)
        if not ref:
            return ""
        try:
            buf = ctypes.create_string_buffer(1024)
            if self.cf.CFStringGetCString(ref, buf, len(buf), K_CFSTRING_UTF8):
                return buf.value.decode("utf-8", "replace")
            return ""
        finally:
            self.cf.CFRelease(ref)

    def _pad(self, pid):
        buf = ctypes.create_string_buffer(4096)
        n = self.libc.proc_pidpath(pid, buf, len(buf))
        return buf.value.decode("utf-8", "replace") if n > 0 else ""

    def gebruikers(self):
        """Alle programma's die nu de microfoon of de speakers gebruiken."""
        size = self._grootte(K_SYSTEM_OBJECT, K_PROCESS_OBJECT_LIST)
        if not size:
            return []
        aantal = size // ctypes.sizeof(ctypes.c_uint32)
        lijst = (ctypes.c_uint32 * aantal)()
        adres = self._adres(K_PROCESS_OBJECT_LIST)
        io = ctypes.c_uint32(size)
        if self.ca.AudioObjectGetPropertyData(K_SYSTEM_OBJECT, ctypes.byref(adres), 0, None,
                                              ctypes.byref(io), lijst) != 0:
            return []
        resultaat = []
        for obj in lijst[: io.value // ctypes.sizeof(ctypes.c_uint32)]:
            invoer = bool(self._lees(obj, K_PROCESS_RUNNING_INPUT, ctypes.c_uint32))
            uitvoer = bool(self._lees(obj, K_PROCESS_RUNNING_OUTPUT, ctypes.c_uint32))
            if not (invoer or uitvoer):
                continue
            pid = self._lees(obj, K_PROCESS_PID, ctypes.c_int32) or 0
            resultaat.append(AudioGebruiker(pid=pid, bundel=self._bundel(obj),
                                            pad=self._pad(pid) if pid > 0 else "",
                                            invoer=invoer, uitvoer=uitvoer))
        return resultaat


def eigen_pids():
    """Dit programma zelf: de opname van de microfoon mag geen meeting lijken."""
    return {os.getpid()}
