"""Tekent de menubalk-iconen van Notulist als 'template'-afbeeldingen: zwart op transparant, zodat
macOS ze zelf zwart (licht thema) of wit (donker thema) maakt, net als de andere menubalk-iconen.

rumps toont een menubalk-icoon op 20x20 punten; de PNG's zijn 40x40 pixels voor scherpe Retina-schermen.
Gebruik: python teken_menubalk_iconen.py <doelmap>
"""
import os
import sys

from PIL import Image, ImageDraw

PUNTEN = 20
PIXELS = 40
SCHAAL = 16  # eerst groot tekenen, dan verkleinen: gladde randen
Z = PUNTEN * SCHAAL


def p(*waarden):
    return [v * SCHAAL for v in waarden]


def lijn(d, x1, y1, x2, y2, dikte, kleur=255):
    d.line(p(x1, y1, x2, y2), fill=kleur, width=int(dikte * SCHAAL))
    r = dikte / 2
    for x, y in ((x1, y1), (x2, y2)):
        d.ellipse(p(x - r, y - r, x + r, y + r), fill=kleur)


def microfoon(d, kleur=255):
    d.rounded_rectangle(p(7, 1.5, 13, 12), radius=3 * SCHAAL, fill=kleur)   # kop
    d.arc(p(4.25, 4, 15.75, 15), start=0, end=180, fill=kleur, width=int(1.6 * SCHAAL))  # beugel
    for x in (4.25 + 0.8, 15.75 - 0.8):  # ronde uiteinden van de beugel
        d.ellipse(p(x - 0.8, 9.5 - 0.8, x + 0.8, 9.5 + 0.8), fill=kleur)
    lijn(d, 10, 15, 10, 17.6, 1.6, kleur)                                     # steel
    lijn(d, 7.2, 18.2, 12.8, 18.2, 1.6, kleur)                                # voet


def opslaan(masker, pad):
    klein = masker.resize((PIXELS, PIXELS), Image.LANCZOS)
    beeld = Image.new("RGBA", (PIXELS, PIXELS), (0, 0, 0, 0))
    beeld.putalpha(klein)
    beeld.save(pad)


def teken(doel):
    os.makedirs(doel, exist_ok=True)

    rust = Image.new("L", (Z, Z), 0)
    microfoon(ImageDraw.Draw(rust))
    opslaan(rust, os.path.join(doel, "menubalk-rust.png"))

    opname = Image.new("L", (Z, Z), 0)
    d = ImageDraw.Draw(opname)
    microfoon(d)
    cx, cy = 16, 4
    d.ellipse(p(cx - 4.1, cy - 4.1, cx + 4.1, cy + 4.1), fill=0)  # ruimte rond de stip
    d.ellipse(p(cx - 2.8, cy - 2.8, cx + 2.8, cy + 2.8), fill=255)
    opslaan(opname, os.path.join(doel, "menubalk-opname.png"))

    tekst = Image.new("L", (Z, Z), 0)
    d = ImageDraw.Draw(tekst)
    for y, eind in ((4, 17), (8, 17), (12, 17), (16, 11.5)):
        lijn(d, 3, y, eind, y, 2)
    opslaan(tekst, os.path.join(doel, "menubalk-uitschrijven.png"))


if __name__ == "__main__":
    teken(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "iconen"))
