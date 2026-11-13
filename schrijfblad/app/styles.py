"""Opmaakprofielen, thema-lettertypen en nummering van een Word-document, omgezet naar CSS."""
from __future__ import annotations

import re

from lxml import etree

from ooxml import A, on_off, w, wval

NAMES_NL = {
    "normal": "Standaard", "title": "Titel", "subtitle": "Ondertitel", "quote": "Citaat",
    "intense quote": "Duidelijk citaat", "list paragraph": "Lijstalinea", "no spacing": "Geen afstand",
    "caption": "Bijschrift", "list bullet": "Opsommingsteken", "list number": "Lijstnummer",
    "header": "Koptekst", "footer": "Voettekst", "toc heading": "Kop van inhoudsopgave",
    "footnote text": "Voetnoottekst", "body text": "Platte tekst", "hyperlink": "Hyperlink",
    "default paragraph font": "Standaardalinea-lettertype", "strong": "Zwaar", "emphasis": "Nadruk",
}
for _i in range(1, 10):
    NAMES_NL["heading %d" % _i] = "Kop %d" % _i
    NAMES_NL["toc %d" % _i] = "Inhopg %d" % _i

SANS = "-apple-system, 'Helvetica Neue', Arial, sans-serif"
SERIF = "Georgia, 'Times New Roman', serif"
FONT_FALLBACK = {
    "calibri": "Calibri, Carlito, " + SANS,
    "calibri light": "'Calibri Light', Calibri, Carlito, " + SANS,
    "aptos": "Aptos, " + SANS,
    "aptos display": "'Aptos Display', Aptos, " + SANS,
    "arial": "Arial, " + SANS,
    "cambria": "Cambria, Caladea, " + SERIF,
    "times new roman": "'Times New Roman', Times, serif",
    "georgia": SERIF,
    "courier new": "'Courier New', Menlo, monospace",
    "consolas": "Consolas, Menlo, monospace",
    "symbol": "Symbol",
}


def css_font(name):
    if not name:
        return None
    key = name.strip().lower()
    if key in FONT_FALLBACK:
        return FONT_FALLBACK[key]
    generic = SERIF if any(s in key for s in ("times", "garamond", "serif", "roman", "book", "minion")) else SANS
    return "'%s', %s" % (name.replace("'", ""), generic)


def safe_id(sid):
    return re.sub(r"[^A-Za-z0-9_-]", "_", sid or "")


def twips_pt(v):
    try:
        return round(int(float(v)) / 20.0, 2)
    except (TypeError, ValueError):
        return None


class StyleSheet:
    def __init__(self, document):
        self.document = document
        part = document.part
        self.major, self.minor = self._theme_fonts(part)
        try:
            self.root = part.styles.element  # styles.xml
        except Exception:
            self.root = None
        self.styles = {}       # id -> element
        self.defaults = {}     # type -> id
        if self.root is not None:
            for st in self.root.findall(w("style")):
                sid = st.get(w("styleId"))
                if not sid:
                    continue
                self.styles[sid] = st
                if on_off_attr(st.get(w("default"))):
                    self.defaults.setdefault(st.get(w("type")), sid)
        self._resolved = {}

    # -- thema
    def _theme_fonts(self, part):
        major = minor = None
        try:
            for rel in part.rels.values():
                if rel.reltype.endswith("/theme") and not rel.is_external:
                    root = etree.fromstring(rel.target_part.blob)
                    mj = root.find(".//{%s}majorFont/{%s}latin" % (A, A))
                    mn = root.find(".//{%s}minorFont/{%s}latin" % (A, A))
                    major = mj.get("typeface") if mj is not None else None
                    minor = mn.get("typeface") if mn is not None else None
                    break
        except Exception:
            pass
        return major, minor

    # -- namen en lijst voor de keuzelijst
    def name(self, sid):
        st = self.styles.get(sid)
        if st is None:
            return sid
        n = wval(st.find(w("name")), sid) or sid
        return NAMES_NL.get(n.lower(), n)

    def default_para(self):
        return self.defaults.get("paragraph") or ("Normal" if "Normal" in self.styles else None)

    def by_name(self, name):
        name = name.lower()
        for sid, st in self.styles.items():
            if (wval(st.find(w("name")), "") or "").lower() == name:
                return sid
        return None

    def heading_id(self, level):
        return self.by_name("heading %d" % level)

    def para_list(self, used):
        out = []
        for sid, st in self.styles.items():
            if st.get(w("type")) != "paragraph":
                continue
            hidden = st.find(w("hidden")) is not None or st.find(w("semiHidden")) is not None
            if hidden and sid not in used and sid != self.default_para():
                continue
            raw = (wval(st.find(w("name")), sid) or sid).lower()
            prio = wval(st.find(w("uiPriority")))
            rank = 99
            if sid == self.default_para():
                rank = 0
            elif raw == "title":
                rank = 1
            elif raw == "subtitle":
                rank = 2
            elif raw.startswith("heading "):
                rank = 3
            elif sid in used:
                rank = 10
            elif prio is not None:
                rank = 20
            nxt = wval(st.find(w("next")))
            out.append({"id": sid, "name": self.name(sid), "next": nxt, "rank": rank, "raw": raw})
        # alleen gangbare en gebruikte profielen tonen, maar nooit een lege lijst
        out.sort(key=lambda s: (s["rank"], s["raw"]))
        short = [s for s in out if s["rank"] < 99]
        return [{k: s[k] for k in ("id", "name", "next")} for s in (short or out)][:60]

    # -- erfenis via basedOn
    def chain(self, sid):
        seen, out = set(), []
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid)
            out.append(self.styles[sid])
            sid = wval(self.styles[sid].find(w("basedOn")))
        return list(reversed(out))

    def style_numpr(self, sid):
        """(numId, ilvl) als een alineaprofiel nummering meebrengt."""
        num, lvl = None, None
        for st in self.chain(sid):
            pPr = st.find(w("pPr"))
            np = pPr.find(w("numPr")) if pPr is not None else None
            if np is not None:
                n = wval(np.find(w("numId")))
                l_ = wval(np.find(w("ilvl")))
                if n is not None:
                    num = n
                if l_ is not None:
                    lvl = l_
        if num is None or num == "0":
            return None
        return num, int(lvl or 0)

    def table_has_borders(self, tblPr):
        def bordered(el):
            if el is None:
                return None
            found = None
            for b in el:
                v = wval(b, "")
                if v in ("nil", "none"):
                    found = found or False
                elif v:
                    return True
            return found

        if tblPr is not None:
            res = bordered(tblPr.find(w("tblBorders")))
            if res is not None:
                return res
            sid = wval(tblPr.find(w("tblStyle")))
            for st in reversed(self.chain(sid)):
                tp = st.find(w("tblPr"))
                res = bordered(tp.find(w("tblBorders")) if tp is not None else None)
                if res is not None:
                    return res
        return False

    # -- CSS
    def font_of(self, rFonts):
        if rFonts is None:
            return None
        name = rFonts.get(w("ascii")) or rFonts.get(w("hAnsi"))
        if not name:
            theme = rFonts.get(w("asciiTheme")) or rFonts.get(w("hAnsiTheme")) or ""
            if theme.startswith("major"):
                name = self.major
            elif theme.startswith("minor"):
                name = self.minor
        return css_font(name)

    def rpr_css(self, rPr, inline=False):
        """CSS voor tekstopmaak. inline=True: alleen wat de editor niet zelf als eigenschap leest."""
        css = {}
        if rPr is None:
            return css
        from ooxml import props_from_rpr
        f = self.font_of(rPr.find(w("rFonts")))
        if f:
            css["font-family"] = f
        if on_off(rPr.find(w("caps"))):
            css["text-transform"] = "uppercase"
        if on_off(rPr.find(w("smallCaps"))):
            css["font-variant"] = "small-caps"
        sp = wval(rPr.find(w("spacing")))
        if sp:
            pt = twips_pt(sp)
            if pt:
                css["letter-spacing"] = "%gpt" % pt
        if inline:
            return css
        p = props_from_rpr(rPr)
        css.update(props_css(p))
        return css

    def ppr_css(self, pPr):
        css = {}
        if pPr is None:
            return css
        jc = wval(pPr.find(w("jc")))
        if jc:
            css["text-align"] = JC_CSS.get(jc, "left")
        sp = pPr.find(w("spacing"))
        if sp is not None:
            b, a = twips_pt(sp.get(w("before"))), twips_pt(sp.get(w("after")))
            if b is not None:
                css["padding-top"] = "%gpt" % b
            if a is not None:
                css["padding-bottom"] = "%gpt" % a
            line, rule = sp.get(w("line")), sp.get(w("lineRule"), "auto")
            if line:
                try:
                    lv = int(float(line))
                    if rule == "auto":
                        css["line-height"] = "%.3g" % max(0.6, lv / 240.0 * 1.17)
                    else:
                        css["line-height"] = "%gpt" % (lv / 20.0)
                except ValueError:
                    pass
        ind = pPr.find(w("ind"))
        if ind is not None:
            left = twips_pt(ind.get(w("left")) or ind.get(w("start")))
            right = twips_pt(ind.get(w("right")) or ind.get(w("end")))
            first = twips_pt(ind.get(w("firstLine")))
            hang = twips_pt(ind.get(w("hanging")))
            if left is not None:
                css["margin-left"] = "%gpt" % left
            if right is not None:
                css["margin-right"] = "%gpt" % right
            if hang:
                css["text-indent"] = "%gpt" % -hang
            elif first is not None:
                css["text-indent"] = "%gpt" % first
        shd = pPr.find(w("shd"))
        if shd is not None:
            fill = shd.get(w("fill"))
            if fill and fill.lower() != "auto" and len(fill) == 6:
                css["background-color"] = "#" + fill
        bdr = pPr.find(w("pBdr"))
        if bdr is not None:
            for side in ("top", "bottom", "left", "right"):
                b = bdr.find(w(side))
                if b is not None and wval(b, "none") not in ("none", "nil"):
                    try:
                        px = max(1, round(int(b.get(w("sz"), "4")) / 8.0 * 1.33))
                    except ValueError:
                        px = 1
                    col = b.get(w("color"), "auto")
                    col = "#" + col if col and col.lower() != "auto" and len(col) == 6 else "currentColor"
                    css["border-" + side] = "%dpx solid %s" % (px, col)
        return css

    def resolved(self, sid):
        """Samengevoegde CSS van een profiel inclusief basedOn."""
        if sid in self._resolved:
            return self._resolved[sid]
        css = {}
        for st in self.chain(sid):
            css.update(self.ppr_css(st.find(w("pPr"))))
            css.update(self.rpr_css(st.find(w("rPr"))))
        self._resolved[sid] = css
        return css

    def css(self):
        lines = []
        base = {"font-family": css_font(self.minor or "Calibri"), "font-size": "10pt", "line-height": "1.17"}
        if self.root is not None:
            dd = self.root.find(w("docDefaults"))
            if dd is not None:
                rp = dd.find(w("rPrDefault") + "/" + w("rPr"))
                pp = dd.find(w("pPrDefault") + "/" + w("pPr"))
                base.update(self.rpr_css(rp))
                base.update(self.ppr_css(pp))
        # pagina-standaard: opmaak van een alinea zonder profiel
        lines.append(".doc .ce { %s }" % css_text({k: v for k, v in base.items()
                                                  if not k.startswith("padding") and not k.startswith("margin")
                                                  and k != "text-indent" and k != "text-align"}))
        para_base = {k: v for k, v in base.items() if k.startswith("padding") or k in ("text-align",)}
        lines.append(".doc .ce p { %s }" % css_text(para_base))
        for sid, st in self.styles.items():
            t = st.get(w("type"))
            if t == "paragraph":
                lines.append(".doc .ce p.ps-%s { %s }" % (safe_id(sid), css_text(self.resolved(sid))))
            elif t == "character":
                css = {}
                for s2 in self.chain(sid):
                    css.update(self.rpr_css(s2.find(w("rPr"))))
                lines.append(".doc .ce .cs-%s { %s }" % (safe_id(sid), css_text(css)))
        return "\n".join(lines)

    # -- nummering
    def numbering(self):
        try:
            part = self.document.part.numbering_part
            root = part.element
        except Exception:
            return {}
        abstracts = {}
        for an in root.findall(w("abstractNum")):
            aid = an.get(w("abstractNumId"))
            abstracts[aid] = (an, self._levels(an))
        out = {}
        for num in root.findall(w("num")):
            nid = num.get(w("numId"))
            aid = wval(num.find(w("abstractNumId")))
            if aid not in abstracts:
                continue
            an, levels = abstracts[aid]
            link = wval(an.find(w("numStyleLink")))
            if link and not levels:
                # nummering via een lijstprofiel
                st = self.styles.get(link)
                if st is not None:
                    np = st.find(w("pPr") + "/" + w("numPr") + "/" + w("numId"))
                    target = wval(np)
                    for n2 in root.findall(w("num")):
                        if n2.get(w("numId")) == target:
                            a2 = wval(n2.find(w("abstractNumId")))
                            if a2 in abstracts:
                                levels = abstracts[a2][1]
            levels = {k: dict(v) for k, v in levels.items()}
            restart = []
            for ov in num.findall(w("lvlOverride")):
                il = ov.get(w("ilvl"))
                so = wval(ov.find(w("startOverride")))
                lvl = ov.find(w("lvl"))
                if lvl is not None:
                    levels[il] = self._level(lvl)
                if so is not None and il in levels:
                    levels[il]["start"] = int(so)
                    restart.append(il)
            out[nid] = {"abs": aid, "levels": levels, "restart": restart}
        return out

    def _levels(self, an):
        return {lvl.get(w("ilvl")): self._level(lvl) for lvl in an.findall(w("lvl"))}

    def _level(self, lvl):
        fmt = wval(lvl.find(w("numFmt")), "decimal")
        text = wval(lvl.find(w("lvlText")), "")
        start = int(wval(lvl.find(w("start")), "1") or 1)
        ind = lvl.find(w("pPr") + "/" + w("ind"))
        left = hang = None
        if ind is not None:
            left = twips_pt(ind.get(w("left")) or ind.get(w("start")))
            hang = twips_pt(ind.get(w("hanging")))
        font = None
        rf = lvl.find(w("rPr") + "/" + w("rFonts"))
        if rf is not None:
            font = rf.get(w("ascii")) or rf.get(w("hAnsi"))
        return {"fmt": fmt, "text": text, "start": start, "left": left, "hang": hang, "font": font}


JC_CSS = {"left": "left", "start": "left", "center": "center", "right": "right", "end": "right",
          "both": "justify", "distribute": "justify", "justify": "justify"}


def on_off_attr(v):
    return v is not None and v.lower() in ("1", "true", "on")


def props_css(p):
    """CSS voor de eigenschappen die de editor terugleest. Moet passen bij parseProps in app.js."""
    css = {}
    if p.get("b") is not None:
        css["font-weight"] = "700" if p["b"] else "400"
    if p.get("i") is not None:
        css["font-style"] = "italic" if p["i"] else "normal"
    u, s = p.get("u"), p.get("s")
    if u or s:
        css["text-decoration"] = " ".join(x for x, on in (("underline", u), ("line-through", s)) if on)
    elif u is False or s is False:
        css["text-decoration"] = "none"
    if p.get("va") == "sup":
        css["vertical-align"] = "super"
    elif p.get("va") == "sub":
        css["vertical-align"] = "sub"
    elif p.get("va") == "base":
        css["vertical-align"] = "baseline"
    if p.get("color"):
        css["color"] = "#" + p["color"]
    if p.get("bg"):
        css["background-color"] = "#" + p["bg"]
    if p.get("sz"):
        css["font-size"] = "%gpt" % p["sz"]
    return css


def css_text(css):
    return "; ".join("%s: %s" % (k, v) for k, v in css.items())

