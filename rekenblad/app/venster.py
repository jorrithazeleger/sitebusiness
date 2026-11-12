"""Rekenblad in eigen Mac-vensters, via pywebview (de WebKit-weergave van Safari).

Elk geopend bestand krijgt een eigen venster. De editor zelf is dezelfde als in de browser;
dit bestand regelt alleen de vensters, de vraag 'wil je bewaren?' en het Dock-icoon.
"""
from __future__ import annotations

import os
import threading

import webview

NL = {
    "global.quitConfirmation": "Wil je Rekenblad stoppen?",
    "global.ok": "OK",
    "global.quit": "Stop",
    "global.cancel": "Annuleer",
    "global.saveFile": "Bewaar bestand",
    "cocoa.menu.about": "Over",
    "cocoa.menu.services": "Voorzieningen",
    "cocoa.menu.view": "Weergave",
    "cocoa.menu.edit": "Wijzig",
    "cocoa.menu.hide": "Verberg",
    "cocoa.menu.hideOthers": "Verberg andere",
    "cocoa.menu.showAll": "Toon alles",
    "cocoa.menu.quit": "Stop",
    "cocoa.menu.fullscreen": "Schermvullende weergave",
    "cocoa.menu.cut": "Knip",
    "cocoa.menu.copy": "Kopieer",
    "cocoa.menu.paste": "Plak",
    "cocoa.menu.selectAll": "Selecteer alles",
}


def _appkit():
    import AppKit  # noqa: F401  (alleen op de Mac aanwezig)
    from PyObjCTools import AppHelper
    return AppKit, AppHelper


def brand_process():
    """Laat de menubalk 'Rekenblad' tonen in plaats van 'Python'. Moet vóór het starten van de app."""
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Rekenblad"
        info["CFBundleDisplayName"] = "Rekenblad"
    except Exception:
        pass


class Api:
    """Functies die de editor in het venster kan aanroepen (window.pywebview.api)."""

    def __init__(self, native, doc):
        self._native = native
        self._doc = doc

    def set_title(self, title, dirty=False):
        self._native.set_title(self._doc, str(title), bool(dirty))

    def close(self):
        self._native.close(self._doc)

    def quit(self):
        self._native.quit()


class Native:
    def __init__(self, port, find_book, forget_doc, icon, rescue=None):
        self.rescue = rescue or (lambda book: None)
        self.port = port
        self.find_book = find_book      # doc -> Book of None
        self.forget_doc = forget_doc    # doc vergeten na sluiten van het venster
        self.icon = icon
        self.windows = {}
        self.lock = threading.Lock()

    # -- vensters
    def _url(self, doc):
        return "http://127.0.0.1:%d/?doc=%s" % (self.port, doc)

    def _create(self, doc):
        w = webview.create_window(
            "Rekenblad", self._url(doc), js_api=Api(self, doc),
            width=1280, height=820, min_size=(760, 480),
            text_select=True, background_color="#F6F7F8",
        )
        w.events.closing += lambda: self._on_closing(doc)
        w.events.closed += lambda: self._on_closed(doc)
        self.windows[doc] = w
        return w

    def open_doc(self, doc):
        """Venster voor dit document tonen (of maken). Mag vanuit elke thread."""
        with self.lock:
            w = self.windows.get(doc)
            if w is None:
                self._create(doc)
            else:
                try:
                    w.restore()
                    w.show()
                except Exception:
                    pass
        self._activate()

    def _nswindow(self, doc):
        w = self.windows.get(doc)
        if w is None:
            return None
        try:
            from webview.platforms.cocoa import BrowserView
            inst = BrowserView.instances.get(w.uid)
            return inst.window if inst is not None else None
        except Exception:
            return None

    def _activate(self):
        try:
            AppKit, AppHelper = _appkit()
            AppHelper.callAfter(AppKit.NSApp.activateIgnoringOtherApps_, True)
        except Exception:
            pass

    def set_title(self, doc, title, dirty):
        w = self.windows.get(doc)
        if w is None:
            return
        try:
            w.set_title(title)
        except Exception:
            pass
        nsw = self._nswindow(doc)
        if nsw is not None:
            try:
                _AppKit, AppHelper = _appkit()
                AppHelper.callAfter(nsw.setDocumentEdited_, dirty)
            except Exception:
                pass

    def close(self, doc):
        """Zoals de rode knop: eerst vragen of er bewaard moet worden."""
        nsw = self._nswindow(doc)
        if nsw is not None:
            _AppKit, AppHelper = _appkit()
            AppHelper.callAfter(nsw.performClose_, None)
        elif doc in self.windows:
            self.windows[doc].destroy()

    def quit(self):
        """Zoals ⌘Q: macOS vraagt per venster met wijzigingen of je wilt bewaren."""
        AppKit, AppHelper = _appkit()
        AppHelper.callAfter(AppKit.NSApp.terminate_, None)

    # -- sluiten
    def _on_closing(self, doc):
        """Draait op de hoofdthread. False = niet sluiten."""
        book = self.find_book(doc)
        if book is None or not book.dirty:
            return True
        try:
            choice = ask_save(book.filename or "Naamloos")
        except Exception:
            # Geen dialoog mogelijk: bewaar een herstelkopie zodat er nooit werk verloren gaat.
            self.rescue(book)
            book.dirty = False
            return True
        if choice == "cancel":
            return False
        if choice == "discard":
            book.dirty = False
            return True
        try:
            with book.lock:
                if book.path and not getattr(book, "attachment", False):
                    book.save(None)
                else:
                    path = choose_save_path(book)
                    if not path:
                        return False
                    book.attachment = False
                    book.save(path)
            return True
        except Exception as exc:
            show_error("Bewaren is niet gelukt", str(exc))
            return False

    def _on_closed(self, doc):
        with self.lock:
            self.windows.pop(doc, None)
        self.forget_doc(doc)

    # -- starten
    def run(self, docs):
        brand_process()
        for doc in docs:
            self._create(doc)
        icon = self.icon if self.icon and os.path.exists(self.icon) else None
        webview.start(localization=NL, icon=icon, private_mode=True)


# ---------------------------------------------------------------------------
# Mac-dialogen (aanroepen op de hoofdthread)

def ask_save(name):
    AppKit, _ = _appkit()
    AppKit.NSApp.activateIgnoringOtherApps_(True)
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_('Wil je de wijzigingen in "%s" bewaren?' % name)
    alert.setInformativeText_("Als je niet bewaart, gaan je wijzigingen verloren.")
    alert.addButtonWithTitle_("Bewaar")
    alert.addButtonWithTitle_("Annuleer")
    alert.addButtonWithTitle_("Niet bewaren")
    res = alert.runModal()
    return {1000: "save", 1001: "cancel", 1002: "discard"}.get(int(res), "cancel")


def choose_save_path(book):
    AppKit, _ = _appkit()
    from Foundation import NSURL
    panel = AppKit.NSSavePanel.savePanel()
    base = os.path.splitext(book.filename or "Werkboek")[0]
    ext = ".xlsm" if book.kind == "xlsm" else ".xlsx"
    panel.setNameFieldStringValue_(base + ext)
    folder = os.path.expanduser("~/Documents")
    if os.path.isdir(folder):
        panel.setDirectoryURL_(NSURL.fileURLWithPath_(folder))
    if panel.runModal() != 1:
        return None
    path = panel.URL().path()
    if not os.path.splitext(path)[1]:
        path += ext
    return path


def show_error(title, text):
    try:
        AppKit, _ = _appkit()
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(text)
        alert.runModal()
    except Exception:
        pass
