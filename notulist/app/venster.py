"""Het hoofdvenster van Notulist: de pagina uit app/web in een eigen Mac-venster (WKWebView).

Het venster draait in hetzelfde programma als het menubalk-icoon. Zolang het open is, staat
Notulist ook in het Dock (met het eigen icoon); sluit je het, dan blijft alleen het
menubalk-icoon over. Lukt het eigen venster niet, dan opent Notulist zich in de browser.
"""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("notulist")

_DELEGATE = None


def _delegate_klasse():
    """De klasse die hoort wanneer het venster sluit (één keer aanmaken bij Objective-C)."""
    global _DELEGATE
    if _DELEGATE is None:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        from Foundation import NSObject

        class NotulistVensterDelegate(NSObject):
            def windowWillClose_(self, notificatie):
                # Geen venster meer: weer alleen in de menubalk, niet in het Dock.
                NSApplication.sharedApplication().setActivationPolicy_(
                    NSApplicationActivationPolicyAccessory)

        _DELEGATE = NotulistVensterDelegate
    return _DELEGATE


class Venster:
    def __init__(self, url: str):
        self.url = url
        self._venster = None
        self._web = None
        self._delegate = None
        import importlib.util
        self.beschikbaar = all(importlib.util.find_spec(m) is not None for m in ("AppKit", "WebKit"))

    def toon(self, js: str | None = None):
        """Toont het venster (en voert eventueel een stukje JavaScript uit, zoals
        'openInstellingen()'). Moet op de hoofdthread worden aangeroepen."""
        if not self.beschikbaar:
            self._browser()
            return
        try:
            self._toon()
            if js:
                self._web.evaluateJavaScript_completionHandler_(js, None)
        except Exception:  # noqa: BLE001
            log.exception("venster openen")
            self._browser()

    def _browser(self):
        subprocess.run(["open", self.url], capture_output=True)

    def _toon(self):
        from AppKit import (NSApplication, NSApplicationActivationPolicyRegular,
                            NSBackingStoreBuffered, NSMakeRect)
        from AppKit import NSWindow
        from Foundation import NSURL, NSURLRequest
        from WebKit import WKWebView, WKWebViewConfiguration

        app = NSApplication.sharedApplication()
        if self._venster is None:
            stijl = 1 | 2 | 4 | 8  # titelbalk, sluiten, minimaliseren, groter/kleiner maken
            venster = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 1180, 760), stijl, NSBackingStoreBuffered, False)
            venster.setTitle_("Notulist")
            venster.setReleasedWhenClosed_(False)
            venster.setMinSize_((720, 460))
            venster.center()
            venster.setFrameAutosaveName_("NotulistHoofdvenster")  # onthoudt plek en grootte

            web = WKWebView.alloc().initWithFrame_configuration_(
                venster.contentView().bounds(), WKWebViewConfiguration.alloc().init())
            web.setAutoresizingMask_(2 | 16)  # meegroeien in breedte en hoogte
            venster.contentView().addSubview_(web)
            web.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(self.url)))

            self._delegate = _delegate_klasse().alloc().init()
            venster.setDelegate_(self._delegate)
            self._venster, self._web = venster, web
            self._maak_menu(app)

        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._venster.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

    def _maak_menu(self, app):
        """Menubalk bovenin het scherm zolang het venster voorop staat. Nodig voor kopiëren en
        plakken met ⌘C en ⌘V in het venster."""
        from AppKit import NSMenu, NSMenuItem

        hoofd = NSMenu.alloc().initWithTitle_("Notulist")

        def submenu(titel, items):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(titel, None, "")
            menu = NSMenu.alloc().initWithTitle_(titel)
            for naam, actie, toets in items:
                if naam is None:
                    menu.addItem_(NSMenuItem.separatorItem())
                else:
                    menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(naam, actie, toets))
            item.setSubmenu_(menu)
            hoofd.addItem_(item)

        submenu("Notulist", [
            ("Over Notulist", "orderFrontStandardAboutPanel:", ""),
            (None, None, None),
            ("Verberg Notulist", "hide:", "h"),
            # ⌘Q sluit alleen het venster: Notulist blijft in de menubalk meetings opnemen.
            ("Sluit venster", "performClose:", "q"),
        ])
        submenu("Wijzig", [
            ("Herstel", "undo:", "z"),
            ("Opnieuw", "redo:", "Z"),
            (None, None, None),
            ("Knip", "cut:", "x"),
            ("Kopieer", "copy:", "c"),
            ("Plak", "paste:", "v"),
            ("Selecteer alles", "selectAll:", "a"),
        ])
        submenu("Venster", [
            ("Minimaliseer", "performMiniaturize:", "m"),
            ("Sluit", "performClose:", "w"),
        ])
        app.setMainMenu_(hoofd)
