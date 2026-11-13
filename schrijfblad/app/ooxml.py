"""Hulpmiddelen voor Word-XML (WordprocessingML): namen, volgorde van elementen en opmaak.

Word is streng over de volgorde van elementen binnen w:rPr en w:pPr. Alles wat Schrijfblad
toevoegt, gaat daarom via insert_ordered.
"""
from __future__ import annotations

from copy import deepcopy

from docx.oxml import OxmlElement

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V = "urn:schemas-microsoft-com:vml"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def w(tag):
    return "{%s}%s" % (W, tag)


def local(el):
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.split("}", 1)[1] if "}" in tag else tag


def ns_of(el):
    tag = el.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def is_w(el, name):
    return isinstance(el.tag, str) and el.tag == w(name)


def wval(el, default=None):
    if el is None:
        return default
    return el.get(w("val"), default)


def on_off(el):
    """True/False voor een aan/uit-element (w:b, w:i, ...), None als het ontbreekt."""
    if el is None:
        return None
    v = el.get(w("val"))
    return v is None or v.lower() not in ("0", "false", "off", "none")


def new(tag, **attrs):
    el = OxmlElement("w:" + tag)
    for k, v in attrs.items():
        el.set(w(k), str(v))
    return el


RPR_ORDER = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
             "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden",
             "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect",
             "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
             "specVanish", "oMath", "ins", "del", "moveFrom", "moveTo", "rPrChange"]
# w:ins/w:del in een rPr horen alleen in de alineamarkering; daar staan ze vooraan.
MARK_RPR_ORDER = ["ins", "del", "moveFrom", "moveTo"] + [t for t in RPR_ORDER if t not in
                                                          ("ins", "del", "moveFrom", "moveTo")]
PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
             "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
             "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle",
             "rPr", "sectPr", "pPrChange"]
TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
              "textDirection", "tcFitText", "vAlign", "hideMark", "headers", "cellIns", "cellDel",
              "cellMerge", "tcPrChange"]


def insert_ordered(parent, child, order):
    """Voeg child in op de juiste plek volgens de schemavolgorde."""
    name = local(child)
    try:
        idx = order.index(name)
    except ValueError:
        parent.append(child)
        return child
    for i, existing in enumerate(parent):
        en = local(existing)
        if en in order and order.index(en) > idx:
            parent.insert(i, child)
            return child
    parent.append(child)
    return child


def get_or_add(parent, tag, order):
    el = parent.find(w(tag))
    if el is None:
        el = insert_ordered(parent, new(tag), order)
    return el


def remove_all(parent, *tags):
    for tag in tags:
        for el in parent.findall(w(tag)):
            parent.remove(el)


def get_pPr(p, create=False):
    pPr = p.find(w("pPr"))
    if pPr is None and create:
        pPr = new("pPr")
        p.insert(0, pPr)
    return pPr


# ---------------------------------------------------------------------------
# Opmaak van tekst: rPr <-> eenvoudige eigenschappen die de editor kent

HIGHLIGHT = {
    "yellow": "FFFF00", "green": "00FF00", "cyan": "00FFFF", "magenta": "FF00FF", "blue": "0000FF",
    "red": "FF0000", "darkBlue": "000080", "darkCyan": "008080", "darkGreen": "008000",
    "darkMagenta": "800080", "darkRed": "800000", "darkYellow": "808000", "darkGray": "808080",
    "lightGray": "C0C0C0", "black": "000000", "white": "FFFFFF",
}
HIGHLIGHT_BY_HEX = {v: k for k, v in HIGHLIGHT.items()}
PROP_KEYS = ("b", "i", "u", "s", "va", "color", "bg", "sz")


def _hex(v):
    if not v:
        return None
    v = v.strip().lstrip("#").upper()
    if v == "AUTO" or len(v) != 6:
        return None
    try:
        int(v, 16)
    except ValueError:
        return None
    return v


def props_from_rpr(rPr):
    """De eigenschappen zoals de editor ze ziet (None = niet ingesteld)."""
    p = dict.fromkeys(PROP_KEYS)
    if rPr is None:
        return p
    p["b"] = on_off(rPr.find(w("b")))
    p["i"] = on_off(rPr.find(w("i")))
    u = rPr.find(w("u"))
    if u is not None:
        p["u"] = (wval(u, "single") or "single") != "none"
    st, dst = on_off(rPr.find(w("strike"))), on_off(rPr.find(w("dstrike")))
    if st is not None or dst is not None:
        p["s"] = bool(st) or bool(dst)
    va = wval(rPr.find(w("vertAlign")))
    if va:
        p["va"] = {"superscript": "sup", "subscript": "sub"}.get(va, "base")
    p["color"] = _hex(wval(rPr.find(w("color"))))
    hl = wval(rPr.find(w("highlight")))
    if hl and hl != "none":
        p["bg"] = HIGHLIGHT.get(hl)
    if p["bg"] is None:
        shd = rPr.find(w("shd"))
        if shd is not None:
            p["bg"] = _hex(shd.get(w("fill")))
    sz = wval(rPr.find(w("sz")))
    if sz:
        try:
            p["sz"] = round(int(sz) / 2.0, 1)
        except ValueError:
            pass
    return p


def norm_props(p):
    """Waarden uit de editor netjes maken."""
    out = dict.fromkeys(PROP_KEYS)
    if not isinstance(p, dict):
        return out
    for k in ("b", "i", "u", "s"):
        if p.get(k) is not None:
            out[k] = bool(p[k])
    if p.get("va") in ("sup", "sub", "base"):
        out["va"] = p["va"]
    out["color"] = _hex(p.get("color"))
    out["bg"] = _hex(p.get("bg"))
    try:
        if p.get("sz") is not None:
            sz = round(float(p["sz"]) * 2) / 2.0
            if 1 <= sz <= 1638:
                out["sz"] = round(sz, 1)
    except (TypeError, ValueError):
        pass
    return out


def set_prop(rPr, key, value):
    """Zet één eigenschap in rPr (value None = weghalen)."""
    o = RPR_ORDER
    if key in ("b", "i"):
        remove_all(rPr, key)
        if value is not None:
            el = insert_ordered(rPr, new(key), o)
            if not value:
                el.set(w("val"), "0")
    elif key == "u":
        remove_all(rPr, "u")
        if value is not None:
            insert_ordered(rPr, new("u", val="single" if value else "none"), o)
    elif key == "s":
        remove_all(rPr, "strike", "dstrike")
        if value is not None:
            el = insert_ordered(rPr, new("strike"), o)
            if not value:
                el.set(w("val"), "0")
    elif key == "va":
        remove_all(rPr, "vertAlign")
        if value:
            insert_ordered(rPr, new("vertAlign", val={"sup": "superscript", "sub": "subscript"}.get(
                value, "baseline")), o)
    elif key == "color":
        remove_all(rPr, "color")
        if value:
            insert_ordered(rPr, new("color", val=value), o)
    elif key == "bg":
        remove_all(rPr, "highlight", "shd")
        if value:
            if value in HIGHLIGHT_BY_HEX:
                insert_ordered(rPr, new("highlight", val=HIGHLIGHT_BY_HEX[value]), o)
            else:
                insert_ordered(rPr, new("shd", val="clear", color="auto", fill=value), o)
    elif key == "sz":
        remove_all(rPr, "sz", "szCs")
        if value:
            half = str(int(round(value * 2)))
            insert_ordered(rPr, new("sz", val=half), o)
            insert_ordered(rPr, new("szCs", val=half), o)


def apply_props(rPr, base_props, props, only_explicit=False):
    """Pas alleen de eigenschappen aan die in de editor anders zijn dan in het origineel."""
    for k in PROP_KEYS:
        nv = props.get(k)
        if only_explicit and nv is None:
            continue
        if nv != base_props.get(k):
            set_prop(rPr, k, nv)


def clean_rpr_copy(rPr):
    """Kopie van een rPr zonder sporen van bijgehouden wijzigingen."""
    if rPr is None:
        return new("rPr")
    c = deepcopy(rPr)
    remove_all(c, "ins", "del", "moveFrom", "moveTo", "rPrChange")
    return c


def text_of(el):
    """Zichtbare tekst van een element (voor blokken die we alleen tonen)."""
    out = []
    for node in el.iter():
        name = local(node)
        if name in ("t", "delText") and ns_of(node) == W:
            out.append(node.text or "")
        elif name == "t" and ns_of(node) == M:
            out.append(node.text or "")
        elif name == "tab" and ns_of(node) == W:
            out.append("\t")
        elif name in ("br", "cr") and ns_of(node) == W:
            out.append("\n")
        elif name == "p" and ns_of(node) == W and out and out[-1] != "\n":
            out.append("\n")
    return "".join(out).strip("\n")


def set_text(r, text):
    """Vul run r met tekst; tabs, regeleindes en harde koppeltekens worden eigen elementen."""
    buf = []

    def flush():
        if buf:
            t = new("t")
            s = "".join(buf)
            t.text = s
            if s != s.strip() or "  " in s:
                t.set(XML_SPACE, "preserve")
            r.append(t)
            buf.clear()

    for ch in text:
        if ch == "\t":
            flush()
            r.append(new("tab"))
        elif ch == "\n":
            flush()
            r.append(new("br"))
        elif ch == "‑":
            flush()
            r.append(new("noBreakHyphen"))
        elif ch == "­":
            flush()
            r.append(new("softHyphen"))
        elif ch in ("​", "﻿", "\r"):
            continue
        else:
            buf.append(ch)
    flush()
