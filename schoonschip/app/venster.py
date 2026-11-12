"""Schoonschip in een eigen Mac-venster, via pywebview (de WebKit-weergave van Safari).

Eén venster. Sluit je het, dan stopt Schoonschip.
"""
from __future__ import annotations

import os

import webview

NL = {
    "global.quitConfirmation": "Wil je Schoonschip stoppen?",
    "global.ok": "OK",
    "global.quit": "Stop",
    "global.cancel": "Annuleer",
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


def brand_process():
    """Laat de menubalk 'Schoonschip' tonen in plaats van 'Python'. Moet vóór het starten van de app."""
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Schoonschip"
        info["CFBundleDisplayName"] = "Schoonschip"
    except Exception:
        pass


class Native:
    def __init__(self, url, icon):
        self.url = url
        self.icon = icon
        self.window = None

    def show(self):
        """Venster naar voren halen (als je Schoonschip nog een keer opent)."""
        try:
            self.window.restore()
            self.window.show()
        except Exception:
            pass
        try:
            import AppKit
            from PyObjCTools import AppHelper
            AppHelper.callAfter(AppKit.NSApp.activateIgnoringOtherApps_, True)
        except Exception:
            pass

    def run(self):
        brand_process()
        self.window = webview.create_window(
            "Schoonschip", self.url, width=1180, height=780, min_size=(920, 600),
            text_select=False, background_color="#F7F5FB")
        icon = self.icon if self.icon and os.path.exists(self.icon) else None
        webview.start(localization=NL, icon=icon, private_mode=True)
