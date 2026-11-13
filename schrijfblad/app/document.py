"""Schrijfblad: het geopende Word-document in het geheugen, met alle bewerkingen.

Werkwijze
- render_all() zet het document om naar HTML voor de editor. Elk blok (alinea, tabel, rij, cel)
  krijgt een id; opmaak van tekst (rPr), afbeeldingen en andere niet-bewerkbare onderdelen ('atomen')
  en koppelingen worden in registers bewaard en in de HTML alleen bij id genoemd.
- sync() krijgt van de editor per gewijzigde alinea de nieuwe inhoud en bouwt alleen die alinea's
  opnieuw op. Ongewijzigde alinea's blijven byte-voor-byte gelijk.
- Onzichtbare onderdelen (bladwijzers, opmerkingbereiken, veldcodes) kent de editor niet. Ze worden
  per alinea bewaard met hun tekstpositie en bij het opnieuw opbouwen op dezelfde plek teruggezet.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import zipfile
import zlib
from copy import deepcopy

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import PartFactory
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.parts.document import DocumentPart
from docx.parts.numbering import NumberingPart
from lxml import etree

import ooxml as X
from ooxml import M, W, WP, local, ns_of, w, wval
from styles import StyleSheet, css_text, props_css, safe_id

DATA_DIR = os.path.join(os.path.expanduser("~"), ".schrijfblad")
MAX_UNDO = 150

CT_MAIN = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    ".docm": "application/vnd.ms-word.document.macroEnabled.main+xml",
    ".dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    ".dotm": "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
}
for _ct in CT_MAIN.values():
    PartFactory.part_type_for.setdefault(_ct, DocumentPart)

# Onderdelen zonder zichtbare tekst die met hun positie mee moeten (zie bovenaan).
MARKERS = {"bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd", "permStart", "permEnd",
           "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
           "customXmlInsRangeStart", "customXmlInsRangeEnd", "customXmlDelRangeStart",
           "customXmlDelRangeEnd", "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
           "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd"}
SKIP_INLINE = {"pPr", "proofErr", "lastRenderedPageBreak", "smartTagPr", "noProof"}
TRACKED = {"ins", "del", "moveFrom", "moveTo"}
ALIGN = {"left", "center", "right", "both", "start", "end", "distribute"}


class UserError(Exception):
    """Fout die als nette melding aan de gebruiker getoond wordt."""


class SyncError(Exception):
    """Editor en server lopen niet meer gelijk: de editor laadt het document opnieuw."""


def esc(s):
    return html.escape(s, quote=True)


def attrs_html(d):
    return "".join(' %s="%s"' % (k, esc(str(v))) for k, v in d.items() if v is not None and v is not False)


def tracked_inside(el):
    """Bevat dit element (buiten de alineamarkering) bijgehouden wijzigingen?"""
    for ch in el:
        if X.is_w(ch, "pPr"):
            continue
        if ns_of(ch) == W and local(ch) in TRACKED:
            return True
        for d in ch.iter(w("ins"), w("del"), w("moveFrom"), w("moveTo")):
            return True
    return False


class Doc:
    def __init__(self):
        self.lock = threading.RLock()
        self.version = 0
        self.attachment = False
        self.key = ""
        self._reset()

    # ------------------------------------------------------------------ basis
    def _reset(self):
        self.document = None
        self.path = None
        self.filename = None
        self.kind = None
        self.dirty = False
        self.warnings = []
        self.backed_up = set()
        self.undo_stack = []
        self.redo_stack = []
        self.containers = {}
        self.sheet = None
        self.gen = 0
        self._clear_registry()

    def _clear_registry(self):
        self.tok = "".join(secrets.choice("abcdefghijkmpqrstuvwxyz") for _ in range(3))
        self.counter = 0
        self.blocks, self.rprs, self.atoms, self.links = {}, {}, {}, {}
        self.atom_part, self.markers, self.prefix, self.suffix = {}, {}, {}, {}
        self._fn_count = 0
        self._comments = None
        self._fresh_links = set()
        self._last_aid = None

    @property
    def loaded(self):
        return self.document is not None

    def _require(self):
        if self.document is None:
            raise UserError("Er is geen bestand geopend.")

    def _touch(self):
        self.dirty = True
        self.version += 1

    def _nid(self, kind):
        self.counter += 1
        return "%s%s%d" % (kind, self.tok, self.counter)

    # ------------------------------------------------------------------ openen
    def new(self):
        self._install(docx.Document(), None, "Naamloos document.docx", "docx", [])
        return self

    def load_bytes(self, data, filename, path=None):
        ext = os.path.splitext(filename)[1].lower()
        warns = []
        if ext in (".doc", ".rtf", ".odt", ".wordml", ".webarchive"):
            data = convert_with_textutil(data, ext)
            filename = os.path.splitext(filename)[0] + ".docx"
            path = None
            warns.append("Dit %s-bestand is omgezet naar het Word-formaat .docx. Controleer de opmaak; "
                         "bij Opslaan kies je een plek voor de .docx-versie." % ext)
            ext = ".docx"
        if ext in (".txt", ".md", ".text"):
            doc = docx.Document()
            text = decode_text(data)
            for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                doc.add_paragraph(line)
            self._install(doc, None, os.path.splitext(filename)[0] + ".docx", "docx",
                          ["Dit tekstbestand is geopend als nieuw Word-document. Bij Opslaan kies je een plek."])
            return self
        if ext not in CT_MAIN:
            raise UserError("Dit bestandstype wordt niet ondersteund. Kies een .docx-, .docm-, .dotx-, "
                            ".doc-, .rtf-, .odt- of .txt-bestand.")
        try:
            pkg = docx.package.Package.open(io.BytesIO(data))
            part = pkg.main_document_part
            if not isinstance(part, DocumentPart):
                raise UserError("Dit bestand is geen Word-document.")
            document = part.document
        except zipfile.BadZipFile:
            raise UserError("Dit bestand is geen geldig Word-document of is beschadigd.")
        except UserError:
            raise
        except Exception as exc:
            raise UserError("Het bestand kon niet geopend worden: %s" % exc)
        kind = ext[1:]
        if kind in ("docm", "dotm"):
            warns.append("Dit document bevat macro's. Die blijven bewaard, maar Schrijfblad voert ze niet uit.")
        self._install(document, path, filename, kind, warns)
        return self

    def load_path(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        self.load_bytes(data, os.path.basename(path), path)
        remember_recent(path)
        return self

    def _install(self, document, path, filename, kind, warns):
        self._reset()
        self.version += 1
        self.attachment = False
        self.document = document
        self.path, self.filename, self.kind = path, filename, kind
        self.sheet = StyleSheet(document)
        self._load_containers()
        self.warnings = warns + self._inspect()

    def _load_containers(self):
        d = self.document
        body = d.element.body
        c = {"body": (body, d.part, "Hoofdtekst")}
        sectPr = body.find(w("sectPr"))
        if sectPr is not None:
            for key, tag, label in (("hdr", "headerReference", "Koptekst"), ("ftr", "footerReference", "Voettekst")):
                for ref in sectPr.findall(w(tag)):
                    if ref.get(w("type"), "default") != "default":
                        continue
                    part = d.part.related_parts.get(ref.get(qn("r:id")))
                    if part is not None and hasattr(part, "element"):
                        c[key] = (part.element, part, label)
        self.containers = c

    def _inspect(self):
        warns = []
        body = self.document.element.body
        if body.find(".//" + w("txbxContent")) is not None:
            warns.append("Tekstvakken en vormen worden als blok getoond en zijn hier niet te bewerken; "
                         "ze blijven wel bewaard.")
        if len(self.document.sections) > 1:
            warns.append("Dit document heeft meerdere secties. Je ziet de kop- en voettekst van de laatste sectie.")
        return warns

    def has_tracked(self):
        for root, _part, _l in self.containers.values():
            for _ in root.iter(w("ins"), w("del"), w("moveFrom"), w("moveTo")):
                return True
        return False

    # ------------------------------------------------------------------ toestand
    def state(self, can_native=False):
        base = {"loaded": self.loaded, "can_native": can_native, "recent": recent_files()}
        if not self.loaded:
            return base
        base.update({
            "filename": self.filename, "path": self.path, "kind": self.kind, "dirty": self.dirty,
            "warnings": self.warnings, "undo": len(self.undo_stack), "redo": len(self.redo_stack),
            "version": self.version, "attachment": self.attachment, "gen": self.gen,
        })
        return base

    # ------------------------------------------------------------------ weergeven
    def page_info(self):
        sectPr = self.document.element.body.find(w("sectPr"))
        info = {"w": 11906, "h": 16838, "top": 1440, "right": 1440, "bottom": 1440, "left": 1440,
                "header": 708, "footer": 708}
        if sectPr is not None:
            sz = sectPr.find(w("pgSz"))
            mar = sectPr.find(w("pgMar"))
            if sz is not None:
                for k in ("w", "h"):
                    try:
                        info[k] = int(float(sz.get(w(k))))
                    except (TypeError, ValueError):
                        pass
            if mar is not None:
                for k in ("top", "right", "bottom", "left", "header", "footer"):
                    try:
                        info[k] = abs(int(float(mar.get(w(k)))))
                    except (TypeError, ValueError):
                        pass
        return info

    def content_width_emu(self):
        p = self.page_info()
        return max(1440, p["w"] - p["left"] - p["right"]) * 635

    def render_all(self):
        self._require()
        self.gen += 1
        self._clear_registry()
        self.sheet = StyleSheet(self.document)
        self._load_containers()
        for root, _p, _l in self.containers.values():
            # een leeg deel krijgt één lege alinea, zodat je erin kunt typen
            if root.find(w("p")) is None and root.find(w("tbl")) is None:
                sect = root.find(w("sectPr"))
                if sect is not None:
                    sect.addprevious(X.new("p"))
                else:
                    root.append(X.new("p"))
        conts = []
        for key in ("hdr", "body", "ftr"):
            if key in self.containers:
                root, part, label = self.containers[key]
                conts.append({"key": key, "label": label, "html": self.render_children(root, part)})
        used = set()
        for root, _p, _l in self.containers.values():
            for ps in root.iter(w("pStyle")):
                used.add(wval(ps))
        sh = self.sheet
        lp = sh.by_name("list paragraph")
        return {
            "gen": self.gen, "containers": conts, "css": sh.css(), "styles": sh.para_list(used),
            "default_style": sh.default_para(), "numbering": sh.numbering(), "page": self.page_info(),
            "list_style": lp, "headings": {str(i): sh.heading_id(i) for i in range(1, 7)},
            "title_style": sh.by_name("title"), "tracked": self.has_tracked(),
            "has": {"hdr": "hdr" in self.containers, "ftr": "ftr" in self.containers},
        }

    def render_children(self, parent, part):
        out, pending, last = [], [], None
        for ch in parent:
            if not isinstance(ch.tag, str):
                continue
            name, isw = local(ch), ns_of(ch) == W
            if isw and name in ("sectPr", "tcPr"):
                continue
            if isw and name in MARKERS:
                pending.append(ch)
                continue
            if isw and name == "p":
                bid, h = self.render_par(ch, part)
            elif isw and name == "tbl":
                bid, h = self.render_table(ch, part)
            else:
                bid = self._nid("b")
                self.blocks[bid] = ch
                txt = X.text_of(ch) or "[%s]" % name
                h = '<div class="xblock" contenteditable="false" data-id="%s" title="%s">%s</div>' % (
                    bid, esc("Dit onderdeel (%s) kun je hier niet bewerken; het blijft bewaard." % name),
                    esc(txt).replace("\n", "<br>"))
            if pending:
                self.prefix[bid] = pending
                pending = []
            out.append(h)
            last = bid
        if pending and last:
            self.suffix[last] = pending
        return "".join(out)

    def render_par(self, p, part):
        pid = self._nid("b")
        self.blocks[pid] = p
        sh = self.sheet
        pPr = p.find(w("pPr"))
        sid = wval(pPr.find(w("pStyle"))) if pPr is not None else None
        eff = sid if sid in sh.styles else sh.default_para()
        cls = ["ps-" + safe_id(eff)] if eff else []
        a = {"data-id": pid}
        if sid:
            a["data-style"] = sid
        if pPr is not None:
            jc = wval(pPr.find(w("jc")))
            if jc:
                a["data-align"] = jc
            np = pPr.find(w("numPr"))
            if np is not None and wval(np.find(w("numId"))) is not None:
                a["data-num"] = wval(np.find(w("numId")))
                a["data-lvl"] = wval(np.find(w("ilvl")), "0")
            if pPr.find(w("sectPr")) is not None:
                cls.append("sect")
        if "data-num" not in a and eff:
            snp = sh.style_numpr(eff)
            if snp:
                a["data-snum"], a["data-slvl"] = snp
        locked = tracked_inside(p)
        if locked:
            cls.append("locked")
            a["contenteditable"] = "false"
            a["title"] = "Deze alinea bevat bijgehouden wijzigingen. Accepteer of wijs ze af om te bewerken."
        css = sh.ppr_css(pPr)
        if css:
            a["style"] = css_text(css)
        if cls:
            a["class"] = " ".join(cls)
        st = {"off": 0, "markers": [], "pending": [], "seen": set(), "nl": False, "part": part,
              "locked": locked}
        out = []
        self._inline(p, out, st, None)
        for m in st["pending"]:
            m[2] = ("end",)
        inner = "".join(out)
        if not inner:
            inner = "<br>"
        elif st["nl"]:
            inner += "<br>"
        if st["markers"]:
            self.markers[pid] = st["markers"]
        return pid, "<p%s>%s</p>" % (attrs_html(a), inner)

    def _inline(self, parent, out, st, link, mode=None):
        for ch in parent:
            if not isinstance(ch.tag, str):
                continue
            name, isw = local(ch), ns_of(ch) == W
            if isw and name in SKIP_INLINE:
                continue
            if isw and name == "r":
                self._run(ch, out, st, link, mode)
            elif isw and name == "hyperlink":
                hid = self._nid("h")
                self.links[hid] = ch
                href = self._href(ch, st["part"])
                out.append('<a%s>' % attrs_html({"data-h": hid, "href": href or "#",
                                                 "title": href if href else None}))
                self._inline(ch, out, st, hid, mode)
                out.append("</a>")
            elif isw and name in MARKERS:
                if not st["locked"]:
                    self._marker(st, ch)
            elif isw and name == "smartTag":
                self._inline(ch, out, st, link, mode)
            elif isw and name in ("ins", "moveTo"):
                out.append('<ins title="%s">' % esc(self._who(ch)))
                self._inline(ch, out, st, link, "ins")
                out.append("</ins>")
            elif isw and name in ("del", "moveFrom"):
                out.append('<del title="%s">' % esc(self._who(ch)))
                self._inline(ch, out, st, link, "del")
                out.append("</del>")
            else:
                out.append(self._atom(ch, st["part"]))
                self._anchor(st, ("a", self._last_aid))
                st["off"] += 1
                st["nl"] = False

    @staticmethod
    def _marker(st, el):
        m = [st["off"], el, None]
        st["markers"].append(m)
        st["pending"].append(m)

    @staticmethod
    def _anchor(st, key):
        """Onzichtbare onderdelen hangen aan het eerstvolgende stukje tekst of atoom."""
        for m in st["pending"]:
            m[2] = key if key not in st["seen"] else None
        st["pending"] = []
        st["seen"].add(key)

    def _who(self, el):
        author = el.get(w("author")) or "Onbekend"
        date = (el.get(w("date")) or "")[:10]
        return "%s %s" % (author, date)

    def _href(self, hl, part):
        rid = hl.get(qn("r:id"))
        anchor = hl.get(w("anchor"))
        if rid:
            try:
                rel = part.rels[rid]
                return rel.target_ref
            except KeyError:
                return None
        if anchor:
            return "#" + anchor
        return None

    def _run(self, r, out, st, link, mode):
        rPr = r.find(w("rPr"))
        rid = self._nid("r")
        self.rprs[rid] = rPr
        css = props_css(X.props_from_rpr(rPr))
        css.update(self.sheet.rpr_css(rPr, inline=True))
        cls = []
        if rPr is not None:
            rs = wval(rPr.find(w("rStyle")))
            if rs:
                cls.append("cs-" + safe_id(rs))
            if X.on_off(rPr.find(w("vanish"))):
                cls.append("hid")
        a = {"data-r": rid, "class": " ".join(cls) or None, "style": css_text(css) or None}
        buf = []

        def flush():
            if buf:
                text = "".join(buf)
                self._anchor(st, ("r", rid))
                out.append("<span%s>%s</span>" % (attrs_html(a), esc(text).replace("\n", "<br>")))
                st["nl"] = text.endswith("\n")
                buf.clear()

        def text(s):
            buf.append(s)
            st["off"] += len(s)

        for ch in r:
            if not isinstance(ch.tag, str):
                continue
            name, isw = local(ch), ns_of(ch) == W
            if not isw:
                flush()
                out.append(self._atom(self._run_clone(r, ch), st["part"]))
                self._anchor(st, ("a", self._last_aid))
                st["off"] += 1
                continue
            if name in ("rPr", "lastRenderedPageBreak"):
                continue
            if name == "t" or (name == "delText" and mode == "del"):
                text(ch.text or "")
            elif name in ("tab", "ptab"):
                text("\t")
            elif name == "br" and ch.get(w("type")) not in ("page", "column"):
                text("\n")
            elif name == "cr":
                text("\n")
            elif name == "noBreakHyphen":
                text("\u2011")
            elif name == "softHyphen":
                text("\u00ad")
            elif name in ("fldChar", "instrText", "delInstrText"):
                flush()
                if not st["locked"]:
                    self._marker(st, self._run_clone(r, ch))
            else:
                flush()
                out.append(self._atom(self._run_clone(r, ch), st["part"]))
                self._anchor(st, ("a", self._last_aid))
                st["off"] += 1
                st["nl"] = False
        flush()

    def _run_clone(self, r, child):
        """Een run met alleen de opmaak en dit ene onderdeel."""
        nr = X.new("r")
        rPr = r.find(w("rPr"))
        if rPr is not None:
            nr.append(deepcopy(rPr))
        nr.append(deepcopy(child))
        return nr

    def _atom(self, el, part):
        aid = self._nid("a")
        self._last_aid = aid
        self.atoms[aid] = el
        self.atom_part[aid] = part
        inner = el[-1] if X.is_w(el, "r") and len(el) else el
        name = local(inner)
        base = {"data-a": aid, "contenteditable": "false"}
        if name in ("drawing", "pict", "object"):
            img = self._image_info(inner)
            if img:
                cls = "atom img" + (" float" if inner.find(".//{%s}anchor" % WP) is not None else "")
                return "<img%s>" % attrs_html(dict(base, **{
                    "class": cls, "alt": "", "src": "api/media?doc=%s&a=%s&g=%d" % (self.key, aid, self.gen),
                    "style": "width:%dpx;height:%dpx" % img if img[0] else None}))
            txt = X.text_of(inner)
            label = txt or ("Grafiek" if inner.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart")
                            is not None else "Vorm")
            return '<span%s>%s</span>' % (attrs_html(dict(base, **{
                "class": "atom shape", "title": "Tekstvak of vorm: blijft bewaard, niet te bewerken"})),
                esc(label).replace("\n", "<br>"))
        if name in ("footnoteReference", "endnoteReference"):
            self._fn_count += 1
            return '<sup%s>%d</sup>' % (attrs_html(dict(base, **{
                "class": "atom fn", "title": "Voetnoot (de tekst staat onderaan in Word)"})), self._fn_count)
        if name == "commentReference":
            return '<span%s>💬</span>' % attrs_html(dict(base, **{
                "class": "atom cm", "title": self._comment_text(inner.get(w("id")))}))
        if name == "br":
            label = "Kolomeinde" if inner.get(w("type")) == "column" else "Pagina-einde"
            return '<span%s>%s</span>' % (attrs_html(dict(base, **{"class": "atom pb"})), label)
        if name == "sym":
            try:
                code = int(inner.get(w("char"), "0"), 16)
                if code >= 0xF000:
                    code -= 0xF000
                ch = chr(code) if code > 31 else "?"
            except ValueError:
                ch = "?"
            return '<span%s>%s</span>' % (attrs_html(dict(base, **{"class": "atom sym"})), esc(ch))
        txt = X.text_of(el)
        cls = "atom math" if ns_of(inner) == M else "atom gen"
        if name == "fldSimple":
            cls = "atom fld"
        title = {"fldSimple": "Veld: %s" % (inner.get(w("instr")) or "").strip(),
                 "sdt": "Inhoudsbesturingselement"}.get(name, name)
        return '<span%s>%s</span>' % (attrs_html(dict(base, **{"class": cls, "title": title})),
                                      esc(txt or "[%s]" % name).replace("\n", "<br>"))

    def _image_info(self, el):
        blip = el.find(".//{%s}blip" % X.A)
        imd = el.find(".//{%s}imagedata" % X.V)
        if blip is None and imd is None:
            return None
        ext = el.find(".//{%s}extent" % WP)
        if ext is not None:
            try:
                return (round(int(ext.get("cx")) / 9525), round(int(ext.get("cy")) / 9525))
            except (TypeError, ValueError):
                pass
        shape = el.find(".//{%s}shape" % X.V)
        if shape is not None:
            m_w = re.search(r"width:\s*([\d.]+)pt", shape.get("style", ""))
            m_h = re.search(r"height:\s*([\d.]+)pt", shape.get("style", ""))
            if m_w and m_h:
                return (round(float(m_w.group(1)) * 4 / 3), round(float(m_h.group(1)) * 4 / 3))
        return (0, 0)

    def media(self, aid):
        el = self.atoms.get(aid)
        part = self.atom_part.get(aid)
        if el is None or part is None:
            raise UserError("Afbeelding niet gevonden.")
        blip = el.find(".//{%s}blip" % X.A)
        rid = None
        if blip is not None:
            rid = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
        else:
            imd = el.find(".//{%s}imagedata" % X.V)
            if imd is not None:
                rid = imd.get(qn("r:id"))
        target = part.related_parts.get(rid) if rid else None
        if target is None:
            raise UserError("Afbeelding niet gevonden.")
        return target.blob, target.content_type

    def _comment_text(self, cid):
        if self._comments is None:
            self._comments = {}
            try:
                for rel in self.document.part.rels.values():
                    if rel.reltype.endswith("/comments") and not rel.is_external:
                        root = etree.fromstring(rel.target_part.blob) if not hasattr(
                            rel.target_part, "element") else rel.target_part.element
                        for c in root.findall(w("comment")):
                            self._comments[c.get(w("id"))] = "%s: %s" % (
                                c.get(w("author")) or "Opmerking", X.text_of(c))
            except Exception:
                pass
        return self._comments.get(cid, "Opmerking")

    def render_table(self, tbl, part):
        tid = self._nid("b")
        self.blocks[tid] = tbl
        locked = any(local(ch) not in ("tblPr", "tblGrid", "tr") for ch in tbl if isinstance(ch.tag, str)) or any(
            local(ch) not in ("trPr", "tblPrEx", "tc") for tr in tbl.findall(w("tr")) for ch in tr
            if isinstance(ch.tag, str))
        if locked:
            txt = X.text_of(tbl)
            return tid, '<div class="xblock" contenteditable="false" data-id="%s">%s</div>' % (
                tid, esc(txt).replace("\n", "<br>"))
        tblPr = tbl.find(w("tblPr"))
        sh = self.sheet
        cls = "tbl " + ("bd" if sh.table_has_borders(tblPr) else "nb")
        style = []
        tw = tblPr.find(w("tblW")) if tblPr is not None else None
        if tw is not None:
            t, v = tw.get(w("type")), tw.get(w("w"), "0")
            try:
                if t == "dxa" and int(float(v)) > 0:
                    style.append("width:%dpx" % round(int(float(v)) / 15))
                elif t == "pct":
                    pct = float(v.rstrip("%")) / (1 if v.endswith("%") else 50)
                    style.append("width:%g%%" % min(100, pct))
            except ValueError:
                pass
        jc = wval(tblPr.find(w("jc"))) if tblPr is not None else None
        if jc == "center":
            style.append("margin-left:auto;margin-right:auto")
        cols = []
        grid = tbl.find(w("tblGrid"))
        if grid is not None:
            for gc in grid.findall(w("gridCol")):
                try:
                    cols.append(round(int(float(gc.get(w("w"), "0"))) / 15))
                except ValueError:
                    cols.append(0)
        rows = []
        for tr in tbl.findall(w("tr")):
            trPr = tr.find(w("trPr"))
            col = 0
            if trPr is not None:
                try:
                    col = int(wval(trPr.find(w("gridBefore")), "0"))
                except ValueError:
                    col = 0
            cells = []
            for tc in tr.findall(w("tc")):
                tcPr = tc.find(w("tcPr"))
                span, vm = 1, None
                if tcPr is not None:
                    try:
                        span = max(1, int(wval(tcPr.find(w("gridSpan")), "1")))
                    except ValueError:
                        span = 1
                    vmel = tcPr.find(w("vMerge"))
                    if vmel is not None:
                        vm = wval(vmel, "continue")
                cells.append([tc, col, span, vm, 1])
                col += span
            rows.append((tr, cells))
        for ri, (tr, cells) in enumerate(rows):
            for cell in cells:
                if cell[3] == "restart":
                    n = 1
                    for tr2, cells2 in rows[ri + 1:]:
                        if any(c[1] == cell[1] and c[3] == "continue" for c in cells2):
                            n += 1
                        else:
                            break
                    cell[4] = n
        out = ['<table%s>' % attrs_html({"data-id": tid, "class": cls, "style": ";".join(style) or None})]
        if cols and any(cols):
            out.append("<colgroup>%s</colgroup>" % "".join('<col style="width:%dpx">' % c for c in cols))
        out.append("<tbody>")
        for tr, cells in rows:
            rid = self._nid("b")
            self.blocks[rid] = tr
            out.append('<tr data-id="%s">' % rid)
            for tc, _col, span, vm, rowspan in cells:
                cid = self._nid("b")
                self.blocks[cid] = tc
                a = {"data-id": cid, "colspan": span if span > 1 else None,
                     "rowspan": rowspan if rowspan > 1 else None}
                cst = []
                tcPr = tc.find(w("tcPr"))
                if tcPr is not None:
                    shd = tcPr.find(w("shd"))
                    fill = shd.get(w("fill")) if shd is not None else None
                    if fill and fill.lower() != "auto" and len(fill) == 6:
                        cst.append("background-color:#" + fill)
                    va = wval(tcPr.find(w("vAlign")))
                    if va in ("center", "bottom"):
                        cst.append("vertical-align:" + ("middle" if va == "center" else "bottom"))
                if cst:
                    a["style"] = ";".join(cst)
                if vm == "continue":
                    a["hidden"] = True
                    a["class"] = "vm"
                inner = self.render_children(tc, part) or "<p><br></p>"
                out.append("<td%s>%s</td>" % (attrs_html(a), inner))
            out.append("</tr>")
        out.append("</tbody></table>")
        return tid, "".join(out)

    # ------------------------------------------------------------------ bewerken vanuit de editor
    def sync(self, gen, containers):
        """Verwerk de wijzigingen uit de editor. Geeft {tijdelijk id: echt id} terug."""
        self._require()
        if gen != self.gen:
            raise SyncError("verouderd")
        if not containers:
            return {}
        self._push_undo()
        ids = {}
        try:
            for key, entries in containers.items():
                if key not in self.containers or not isinstance(entries, list):
                    raise SyncError("onbekend deel")
                root, part, _l = self.containers[key]
                keep = ("sectPr",) if key == "body" else ()
                self._apply_children(root, part, entries, ids, set(), keep)
        except Exception:
            self._restore(self.undo_stack.pop())
            raise
        self.redo_stack.clear()
        self._touch()
        return ids

    def _apply_children(self, parent, part, entries, ids, used, keep=()):
        new_children = []
        for e in entries:
            if not isinstance(e, dict):
                raise SyncError("ongeldig blok")
            eid = e.get("id")
            if eid in self.prefix and eid not in used:
                new_children.extend(self.prefix[eid])
            el = self._build_block(e, part, ids, used)
            new_children.append(el)
            if eid in self.suffix:
                new_children.extend(self.suffix.pop(eid))
        container_like = local(parent) in ("body", "tc", "hdr", "ftr")
        blocks = [c for c in new_children if local(c) in ("p", "tbl", "sdt", "customXml", "altChunk")]
        if container_like and (not blocks or local(blocks[-1]) == "tbl"):
            new_children.append(X.new("p"))
        kept = [c for c in parent if local(c) in keep or local(c) == "tcPr"]
        for c in list(parent):
            parent.remove(c)
        for c in kept:
            if local(c) == "tcPr":
                parent.append(c)
        for c in new_children:
            parent.append(c)
        for c in kept:
            if local(c) != "tcPr":
                parent.append(c)

    def _register(self, eid, el, ids, used):
        if eid and not str(eid).startswith("n") and eid in self.blocks and eid not in used:
            self.blocks[eid] = el
            used.add(eid)
            return eid
        nid = self._nid("b")
        self.blocks[nid] = el
        used.add(nid)
        if eid:
            ids[eid] = nid
        return nid

    def _source(self, e, ids):
        eid = e.get("id")
        if eid and not str(eid).startswith("n") and eid in self.blocks:
            return self.blocks[eid], False
        frm = e.get("from")
        frm = ids.get(frm, frm)
        if frm and frm in self.blocks:
            return self.blocks[frm], True
        return None, True

    def _build_block(self, e, part, ids, used):
        eid, t = e.get("id"), e.get("t")
        if t is None:
            el = self.blocks.get(eid)
            if el is None or eid in used:
                raise SyncError("onbekend blok %s" % eid)
            used.add(eid)
            return el
        if t == "p":
            src, clone = self._source(e, ids)
            el, markers = self._build_par(e, part, src, clone, eid)
            nid = self._register(eid, el, ids, used)
            if markers:
                self.markers[nid] = markers
            else:
                self.markers.pop(nid, None)
            return el
        if t == "tbl":
            el = self._build_tbl(e, part, ids, used)
            self._register(eid, el, ids, used)
            return el
        raise SyncError("onbekend bloktype")

    def _build_par(self, e, part, src, clone, eid):
        p = X.new("p")
        if src is not None and local(src) == "p":
            pPr = src.find(w("pPr"))
            if pPr is not None:
                pPr = deepcopy(pPr)
                if clone:
                    X.remove_all(pPr, "sectPr")
                mrPr = pPr.find(w("rPr"))
                if mrPr is not None:
                    X.remove_all(mrPr, "ins", "del", "moveFrom", "moveTo")
                p.append(pPr)
        self._set_style(p, e.get("style"))
        self._set_align(p, e.get("align"))
        self._set_num(p, e.get("num"))
        pPr = p.find(w("pPr"))
        mark = pPr.find(w("rPr")) if pPr is not None else None
        markers = [] if (clone or src is None) else list(self.markers.get(eid, []))
        seq = self._place_markers(self._items(e.get("items")), markers)

        new_markers, off = [], 0
        holder, cur_key = p, None
        for it in seq:
            if "m" in it:
                new_markers.append([off, it["m"], it.get("anchor")])
                holder.append(it["m"])
                continue
            key = (it.get("h"), it.get("href"))
            if key != cur_key:
                cur_key = key
                holder = p
                link_el = self._link_element(key, part)
                if link_el is not None:
                    p.append(link_el)
                    holder = link_el
            if "x" in it:
                r = X.new("r")
                base = self.rprs.get(it.get("r"), "missing")
                if base != "missing":
                    rPr = X.clean_rpr_copy(base)
                    X.apply_props(rPr, X.props_from_rpr(base), it["p"])
                else:
                    rPr = X.clean_rpr_copy(mark)
                    X.apply_props(rPr, X.props_from_rpr(mark), it["p"], only_explicit=True)
                if holder is not p and holder in self._fresh_links and rPr.find(w("rStyle")) is None:
                    hs = self.sheet.by_name("hyperlink")
                    if hs:
                        X.insert_ordered(rPr, X.new("rStyle", val=hs), X.RPR_ORDER)
                    else:
                        X.set_prop(rPr, "color", "0563C1")
                        X.set_prop(rPr, "u", True)
                if len(rPr):
                    r.append(rPr)
                X.set_text(r, it["x"])
                holder.append(r)
                off += len(it["x"])
            elif "a" in it:
                src_el = self.atoms.get(it["a"])
                if src_el is not None:
                    holder.append(deepcopy(src_el))
                off += 1
            elif "n" in it:
                r = X.new("r")
                if mark is not None and len(X.clean_rpr_copy(mark)):
                    r.append(X.clean_rpr_copy(mark))
                r.append(X.new("br", type="column" if it["n"] == "columnbreak" else "page"))
                holder.append(r)
                off += 1
        return p, new_markers

    def _items(self, raw):
        out = []
        for it in raw or []:
            if not isinstance(it, dict):
                continue
            base = {"h": it.get("h"), "href": it.get("href")}
            if isinstance(it.get("x"), str):
                if not it["x"]:
                    continue
                d = dict(base, x=it["x"], r=it.get("r"), p=X.norm_props(it.get("p")))
                if out and "x" in out[-1] and all(out[-1].get(k) == d.get(k) for k in ("h", "href", "r", "p")):
                    out[-1]["x"] += d["x"]
                else:
                    out.append(d)
            elif it.get("a"):
                out.append(dict(base, a=it["a"]))
            elif it.get("n") in ("pagebreak", "columnbreak"):
                out.append(dict(base, n=it["n"]))
        return out

    @staticmethod
    def _place_markers(seq, markers):
        """Zet onzichtbare onderdelen terug: bij hun stukje tekst als dat er nog is, anders op dezelfde positie."""
        if not markers:
            return seq
        starts, pos = {}, 0
        for item in seq:
            key = ("r", item.get("r")) if "x" in item else ("a", item["a"]) if "a" in item else None
            if key is not None and key[1] is not None and key not in starts:
                starts[key] = pos
            pos += len(item["x"]) if "x" in item else 1
        total = pos
        placed = []
        for idx, m in enumerate(markers):
            off, el = m[0], m[1]
            anchor = m[2] if len(m) > 2 else None
            if anchor == ("end",):
                o = total
            elif anchor in starts:
                o = starts[anchor]
            else:
                o = min(off, total)
            placed.append((o, idx, el, anchor))
        placed.sort(key=lambda t: (t[0], t[1]))
        out, mi, pos = [], 0, 0

        def emit():
            out.append({"m": placed[mi][2], "anchor": placed[mi][3]})

        for item in seq:
            length = len(item["x"]) if "x" in item else 1
            while mi < len(placed) and placed[mi][0] <= pos:
                emit()
                mi += 1
            if "x" in item:
                while mi < len(placed) and pos < placed[mi][0] < pos + length:
                    k = placed[mi][0] - pos
                    out.append(dict(item, x=item["x"][:k]))
                    item = dict(item, x=item["x"][k:])
                    pos += k
                    length -= k
                    while mi < len(placed) and placed[mi][0] <= pos:
                        emit()
                        mi += 1
            out.append(item)
            pos += length
        while mi < len(placed):
            emit()
            mi += 1
        return out

    def _link_element(self, key, part):
        hid, href = key
        if hid is None and href is None:
            return None
        orig = self.links.get(hid) if hid else None
        if orig is not None:
            orig_href = self._href(orig, part)
            if href is None or href == orig_href or href == "#" and orig_href is None:
                el = X.new("hyperlink")
                for k, v in orig.attrib.items():
                    el.set(k, v)
                return el
        if not href or href == "#":
            return None
        el = X.new("hyperlink")
        if href.startswith("#"):
            el.set(w("anchor"), href[1:])
        else:
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
                href = "https://" + href
            el.set(qn("r:id"), part.relate_to(href, RT.HYPERLINK, is_external=True))
        el.set(w("history"), "1")
        self._fresh_links.add(el)
        return el

    def _set_style(self, p, sid):
        pPr = p.find(w("pPr"))
        cur = wval(pPr.find(w("pStyle"))) if pPr is not None else None
        if sid == cur or (sid and sid not in self.sheet.styles):
            return
        pPr = X.get_pPr(p, True)
        X.remove_all(pPr, "pStyle")
        if sid:
            X.insert_ordered(pPr, X.new("pStyle", val=sid), X.PPR_ORDER)

    def _set_align(self, p, align):
        pPr = p.find(w("pPr"))
        cur = wval(pPr.find(w("jc"))) if pPr is not None else None
        if align == cur or (align and align not in ALIGN):
            return
        pPr = X.get_pPr(p, True)
        X.remove_all(pPr, "jc")
        if align:
            X.insert_ordered(pPr, X.new("jc", val=align), X.PPR_ORDER)

    def _set_num(self, p, num):
        pPr = p.find(w("pPr"))
        cur = None
        if pPr is not None:
            np = pPr.find(w("numPr"))
            if np is not None and wval(np.find(w("numId"))) is not None:
                cur = (str(wval(np.find(w("numId")))), str(wval(np.find(w("ilvl")), "0")))
        want = None
        if isinstance(num, (list, tuple)) and len(num) == 2:
            try:
                want = (str(int(num[0])), str(max(0, min(8, int(num[1])))))
            except (TypeError, ValueError):
                want = None
        if want == cur:
            return
        pPr = X.get_pPr(p, True)
        X.remove_all(pPr, "numPr")
        if want:
            np = X.insert_ordered(pPr, X.new("numPr"), X.PPR_ORDER)
            np.append(X.new("ilvl", val=want[1]))
            np.append(X.new("numId", val=want[0]))

    def _build_tbl(self, e, part, ids, used):
        src, _clone = self._source(e, ids)
        tbl = X.new("tbl")
        if src is not None and local(src) == "tbl":
            for ch in src:
                if local(ch) in ("tblPr", "tblGrid"):
                    tbl.append(deepcopy(ch))
        for row in e.get("rows") or []:
            rsrc, _c = self._source(row, ids)
            tr = X.new("tr")
            if rsrc is not None and local(rsrc) == "tr":
                for ch in rsrc:
                    if local(ch) in ("tblPrEx", "trPr"):
                        tr.append(deepcopy(ch))
            for cell in row.get("cells") or []:
                csrc, _c = self._source(cell, ids)
                tc = X.new("tc")
                if csrc is not None and local(csrc) == "tc":
                    tcPr = csrc.find(w("tcPr"))
                    if tcPr is not None:
                        tc.append(deepcopy(tcPr))
                self._apply_children(tc, part, cell.get("blocks") or [], ids, used)
                self._register(cell.get("id"), tc, ids, used)
                tr.append(tc)
            if len(tr.findall(w("tc"))):
                tbl.append(tr)
                self._register(row.get("id"), tr, ids, used)
        if not tbl.findall(w("tr")):
            raise SyncError("lege tabel")
        return tbl

    # ------------------------------------------------------------------ tabellen
    def _grid(self, tbl):
        """Per rij: lijst (tc, startkolom, breedte in kolommen)."""
        rows = []
        for tr in tbl.findall(w("tr")):
            col = 0
            trPr = tr.find(w("trPr"))
            if trPr is not None:
                try:
                    col = int(wval(trPr.find(w("gridBefore")), "0"))
                except ValueError:
                    col = 0
            cells = []
            for tc in tr.findall(w("tc")):
                tcPr = tc.find(w("tcPr"))
                span = 1
                if tcPr is not None:
                    try:
                        span = max(1, int(wval(tcPr.find(w("gridSpan")), "1")))
                    except ValueError:
                        span = 1
                cells.append((tc, col, span))
                col += span
            rows.append((tr, cells))
        return rows

    @staticmethod
    def _empty_cell_content(tc):
        first = tc.find(w("p"))
        for ch in list(tc):
            if local(ch) != "tcPr":
                tc.remove(ch)
        p = X.new("p")
        if first is not None and first.find(w("pPr")) is not None:
            pPr = deepcopy(first.find(w("pPr")))
            X.remove_all(pPr, "sectPr")
            p.append(pPr)
        tc.append(p)

    def table_op(self, cell_id, op):
        self._require()
        tc = self.blocks.get(cell_id)
        if tc is None or local(tc) != "tc":
            raise SyncError("onbekende cel")
        tr = tc.getparent()
        tbl = tr.getparent()
        self._push_undo()
        rows = self._grid(tbl)
        col = next((c for _t, cells in rows for (t, c, _s) in cells if t is tc), 0)
        if op in ("row_above", "row_below"):
            nr = deepcopy(tr)
            for t in nr.findall(w("tc")):
                tcPr = t.find(w("tcPr"))
                if tcPr is not None:
                    X.remove_all(tcPr, "vMerge")
                self._empty_cell_content(t)
            if op == "row_above":
                tr.addprevious(nr)
            else:
                tr.addnext(nr)
        elif op == "row_delete":
            tbl.remove(tr)
        elif op in ("col_left", "col_right"):
            for _tr, cells in rows:
                hit = next(((t, c, s) for (t, c, s) in cells if c <= col < c + s), None)
                if hit is None:
                    continue
                nt = deepcopy(hit[0])
                tcPr = nt.find(w("tcPr"))
                if tcPr is not None:
                    X.remove_all(tcPr, "gridSpan")
                self._empty_cell_content(nt)
                if op == "col_left":
                    hit[0].addprevious(nt)
                else:
                    hit[0].addnext(nt)
            self._regrid(tbl, insert_at=col + (1 if op == "col_right" else 0), ref=col)
        elif op == "col_delete":
            for tr2, cells in rows:
                hit = next(((t, c, s) for (t, c, s) in cells if c <= col < c + s), None)
                if hit is None:
                    continue
                t, _c, s = hit
                if s > 1:
                    gs = t.find(w("tcPr") + "/" + w("gridSpan"))
                    if s - 1 > 1:
                        gs.set(w("val"), str(s - 1))
                    else:
                        gs.getparent().remove(gs)
                else:
                    tr2.remove(t)
            for tr2 in tbl.findall(w("tr")):
                if not tr2.findall(w("tc")):
                    tbl.remove(tr2)
            self._regrid(tbl, delete_at=col)
        elif op == "table_delete":
            pass
        else:
            raise UserError("Onbekende tabelbewerking.")
        parent = tbl.getparent()
        if op == "table_delete" or not tbl.findall(w("tr")):
            idx = list(parent).index(tbl)
            parent.remove(tbl)
            if local(parent) in ("body", "tc") and not parent.findall(w("p")) + parent.findall(w("tbl")):
                parent.insert(idx, X.new("p"))
            self._touch()
            self.redo_stack.clear()
            return None
        self._fix_vmerge(tbl)
        self._touch()
        self.redo_stack.clear()
        part = self._part_of(tbl)
        _tid, h = self.render_table(tbl, part)
        return h

    def _fix_vmerge(self, tbl):
        """Samengevoegde cellen die hun begin kwijt zijn worden weer gewone cellen."""
        prev = {}
        for _tr, cells in self._grid(tbl):
            cur = {}
            for tc, col, _s in cells:
                vm = tc.find(w("tcPr") + "/" + w("vMerge"))
                state = None
                if vm is not None:
                    state = wval(vm, "continue")
                    if state == "continue" and col not in prev:
                        vm.set(w("val"), "restart")
                        state = "restart"
                if state:
                    cur[col] = state
            prev = cur

    def _regrid(self, tbl, insert_at=None, ref=None, delete_at=None):
        grid = tbl.find(w("tblGrid"))
        if grid is None:
            grid = X.new("tblGrid")
            tblPr = tbl.find(w("tblPr"))
            if tblPr is not None:
                tblPr.addnext(grid)
            else:
                tbl.insert(0, grid)
        cols = grid.findall(w("gridCol"))
        widths = []
        for gc in cols:
            try:
                widths.append(int(float(gc.get(w("w"), "0"))))
            except ValueError:
                widths.append(0)
        total = sum(widths) or (self.content_width_emu() // 635)
        if insert_at is not None:
            wref = widths[ref] if ref is not None and ref < len(widths) else (total // max(1, len(widths)))
            widths.insert(min(insert_at, len(widths)), wref)
        if delete_at is not None and delete_at < len(widths):
            widths.pop(delete_at)
        ncols = max([c + s for _tr, cells in self._grid(tbl) for (_t, c, s) in cells] or [len(widths)])
        while len(widths) < ncols:
            widths.append(total // max(1, ncols))
        widths = widths[:ncols]
        scale = total / float(sum(widths) or 1)
        widths = [max(200, int(x * scale)) for x in widths]
        for gc in cols:
            grid.remove(gc)
        for x in widths:
            grid.append(X.new("gridCol", w=x))
        for _tr, cells in self._grid(tbl):
            for tc, c, s in cells:
                tcPr = tc.find(w("tcPr"))
                tcW = tcPr.find(w("tcW")) if tcPr is not None else None
                if tcW is not None:
                    tcW.set(w("w"), str(sum(widths[c:c + s])))
                    tcW.set(w("type"), "dxa")

    def _part_of(self, el):
        root = el.getroottree().getroot()
        for r, part, _l in self.containers.values():
            if r.getroottree().getroot() is root:
                return part
        return self.document.part

    def insert_table(self, after_id, rows, cols):
        self._require()
        ref = self.blocks.get(after_id)
        if ref is None or local(ref) not in ("p", "tbl"):
            raise SyncError("onbekend blok")
        rows = max(1, min(200, int(rows)))
        cols = max(1, min(40, int(cols)))
        self._push_undo()
        width = self.content_width_emu() // 635
        parent = ref.getparent()
        if local(parent) == "tc":
            tcw = parent.find(w("tcPr") + "/" + w("tcW"))
            try:
                width = int(tcw.get(w("w"))) - 220 if tcw is not None and tcw.get(w("type")) == "dxa" else width // 2
            except (TypeError, ValueError):
                width = width // 2
        cw = max(400, width // cols)
        tbl = X.new("tbl")
        tblPr = X.new("tblPr")
        grid_style = self.sheet.by_name("table grid")
        if grid_style:
            tblPr.append(X.new("tblStyle", val=grid_style))
        tblPr.append(X.new("tblW", w=0, type="auto"))
        if not grid_style:
            b = X.new("tblBorders")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                b.append(X.new(side, val="single", sz=4, space=0, color="auto"))
            tblPr.append(b)
        tblPr.append(X.new("tblLook", val="04A0", firstRow=1, lastRow=0, firstColumn=1, lastColumn=0,
                           noHBand=0, noVBand=1))
        tbl.append(tblPr)
        grid = X.new("tblGrid")
        for _ in range(cols):
            grid.append(X.new("gridCol", w=cw))
        tbl.append(grid)
        for _r in range(rows):
            tr = X.new("tr")
            for _c in range(cols):
                tc = X.new("tc")
                tcPr = X.new("tcPr")
                tcPr.append(X.new("tcW", w=cw, type="dxa"))
                tc.append(tcPr)
                tc.append(X.new("p"))
                tr.append(tc)
            tbl.append(tr)
        ref.addnext(tbl)
        part = self._part_of(ref)
        _tid, h = self.render_table(tbl, part)
        nxt = tbl.getnext()
        if nxt is None or local(nxt) not in ("p",):
            p = X.new("p")
            tbl.addnext(p)
            _pid, ph = self.render_par(p, part)
            h += ph
        self._touch()
        self.redo_stack.clear()
        return h

    # ------------------------------------------------------------------ afbeeldingen, lijsten, kop/voet
    def new_image(self, data, container):
        self._require()
        if container not in self.containers:
            raise UserError("Onbekend deel van het document.")
        _root, part, _l = self.containers[container]
        try:
            inline = part.new_pic_inline(io.BytesIO(data))
        except Exception:
            raise UserError("Dit afbeeldingsformaat wordt niet ondersteund. Gebruik PNG, JPEG, GIF of BMP.")
        ext = inline.find(".//{%s}extent" % WP)
        maxw = self.content_width_emu()
        try:
            cx, cy = int(ext.get("cx")), int(ext.get("cy"))
            if cx > maxw:
                cy = int(cy * maxw / cx)
                cx = maxw
                for e2 in inline.iter("{%s}extent" % WP, "{%s}ext" % X.A):
                    e2.set("cx", str(cx))
                    e2.set("cy", str(cy))
        except (TypeError, ValueError, AttributeError):
            pass
        r = X.new("r")
        d = X.new("drawing")
        d.append(inline)
        r.append(d)
        return self._atom(r, part)

    def ensure_list(self, kind, fresh=False):
        """Geef een numId voor opsomming ('bullet') of nummering ('number')."""
        self._require()
        part = self._numbering_part()
        root = part.element
        target = "bullet" if kind == "bullet" else "decimal"
        nums = self.sheet.numbering()
        if not (kind == "number" and fresh):
            for nid, info in nums.items():
                lv = info["levels"].get("0")
                if lv and "1" in info["levels"] and (lv["fmt"] == "bullet") == (target == "bullet") and (
                        target == "bullet" or lv["fmt"] == "decimal"):
                    return nid
        ids = [int(a.get(w("abstractNumId"))) for a in root.findall(w("abstractNum"))
               if (a.get(w("abstractNumId")) or "").isdigit()]
        aid = None
        if kind == "number":
            for nid, info in nums.items():
                lv = info["levels"].get("0")
                if lv and lv["fmt"] == "decimal" and "1" in info["levels"]:
                    aid = info["abs"]
                    break
        if aid is None:
            aid = str(max(ids) + 1 if ids else 0)
            an = X.new("abstractNum", abstractNumId=aid)
            an.append(X.new("multiLevelType", val="hybridMultilevel"))
            bullets = ["\u2022", "o", "\u25aa"]
            fmts = ["decimal", "lowerLetter", "lowerRoman"]
            for lvl in range(9):
                el = X.new("lvl", ilvl=lvl)
                el.append(X.new("start", val=1))
                if kind == "bullet":
                    el.append(X.new("numFmt", val="bullet"))
                    el.append(X.new("lvlText", val=bullets[lvl % 3]))
                else:
                    el.append(X.new("numFmt", val=fmts[lvl % 3]))
                    el.append(X.new("lvlText", val="%%%d." % (lvl + 1)))
                el.append(X.new("lvlJc", val="left"))
                pPr = X.new("pPr")
                pPr.append(X.new("ind", left=720 * (lvl + 1), hanging=360))
                el.append(pPr)
                if kind == "bullet" and lvl % 3 == 1:
                    rPr = X.new("rPr")
                    rPr.append(X.new("rFonts", ascii="Courier New", hAnsi="Courier New", hint="default"))
                    el.append(rPr)
                an.append(el)
            existing = root.findall(w("abstractNum"))
            if existing:
                existing[-1].addnext(an)
            else:
                pics = root.findall(w("numPicBullet"))
                if pics:
                    pics[-1].addnext(an)
                else:
                    root.insert(0, an)
        nid_list = [int(n.get(w("numId"))) for n in root.findall(w("num")) if (n.get(w("numId")) or "").isdigit()]
        nid = str(max(nid_list) + 1 if nid_list else 1)
        num = X.new("num", numId=nid)
        num.append(X.new("abstractNumId", val=aid))
        if kind == "number" and fresh:
            ov = X.new("lvlOverride", ilvl=0)
            ov.append(X.new("startOverride", val=1))
            num.append(ov)
        cleanup = root.find(w("numIdMacAtCleanup"))
        if cleanup is not None:
            cleanup.addprevious(num)
        else:
            root.append(num)
        self._touch()
        return nid

    def _numbering_part(self):
        dp = self.document.part
        try:
            return dp.part_related_by(RT.NUMBERING)
        except KeyError:
            xml = '<w:numbering xmlns:w="%s"/>' % W
            part = NumberingPart(PackURI("/word/numbering.xml"),
                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
                                 parse_xml(xml), dp.package)
            dp.relate_to(part, RT.NUMBERING)
            return part

    def add_header_footer(self, kind):
        self._require()
        self._push_undo()
        sec = self.document.sections[-1]
        hf = sec.header if kind == "hdr" else sec.footer
        hf.is_linked_to_previous = False
        self._load_containers()
        self._touch()
        self.redo_stack.clear()

    # ------------------------------------------------------------------ bijgehouden wijzigingen
    def resolve_tracked(self, accept=True):
        self._require()
        self._push_undo()
        for root, _part, _l in self.containers.values():
            resolve_tracked(root, accept)
        self._touch()
        self.redo_stack.clear()

    # ------------------------------------------------------------------ ongedaan maken
    def _snapshot(self):
        snap = {}
        for key, (root, _part, _l) in self.containers.items():
            snap[key] = zlib.compress(etree.tostring(root), 3)
        try:
            np = self.document.part.part_related_by(RT.NUMBERING)
            snap["__num"] = zlib.compress(etree.tostring(np.element), 3)
        except KeyError:
            pass
        return snap

    def _push_undo(self):
        self.undo_stack.append(self._snapshot())
        if len(self.undo_stack) > MAX_UNDO:
            del self.undo_stack[0]

    def _restore(self, snap):
        targets = {k: v[0] for k, v in self.containers.items()}
        try:
            targets["__num"] = self.document.part.part_related_by(RT.NUMBERING).element
        except KeyError:
            pass
        for key, data in snap.items():
            root = targets.get(key)
            if root is None:
                continue
            fresh = parse_xml(zlib.decompress(data))
            for c in list(root):
                root.remove(c)
            for c in list(fresh):
                root.append(c)
        self._load_containers()

    def undo(self):
        self._require()
        if not self.undo_stack:
            return
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())
        self._touch()

    def redo(self):
        self._require()
        if not self.redo_stack:
            return
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())
        self._touch()

    # ------------------------------------------------------------------ opslaan en exporteren
    def _fixups(self):
        """Kleine reparaties zodat Word het bestand altijd zonder klagen opent."""
        seen, nxt = set(), 1
        roots = [self.document.element] + [r for k, (r, _p, _l) in self.containers.items() if k != "body"]
        for root in roots:
            for dp in root.iter("{%s}docPr" % WP):
                try:
                    v = int(dp.get("id"))
                except (TypeError, ValueError):
                    v = 0
                if v <= 0 or v in seen:
                    while nxt in seen:
                        nxt += 1
                    v = nxt
                    dp.set("id", str(v))
                seen.add(v)
        for root in roots:
            fix_fields(root)
            fix_pairs(root, "bookmarkStart", "bookmarkEnd")
            fix_pairs(root, "commentRangeStart", "commentRangeEnd")

    def to_bytes(self, fmt="docx"):
        self._require()
        if fmt == "txt":
            return self.to_text().encode("utf-8")
        if fmt == "md":
            return self.to_markdown().encode("utf-8")
        self._fixups()
        try:
            self.document.core_properties.modified = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
        buf = io.BytesIO()
        self.document.save(buf)
        return buf.getvalue()

    def save(self, path=None):
        self._require()
        path = path or self.path
        if not path:
            raise UserError("Kies eerst waar je het bestand wilt opslaan.")
        ext = os.path.splitext(path)[1].lower()
        if ext in (".txt", ".md"):
            data = self.to_bytes(ext[1:])
        else:
            if ext == ".docx" and self.kind in ("docm", "dotm"):
                raise UserError("Dit document bevat macro's. Sla het op als .docm.")
            data = self.to_bytes("docx")
        if os.path.exists(path) and path not in self.backed_up:
            backup_file(path)
            self.backed_up.add(path)
        folder = os.path.dirname(path) or "."
        tmp = os.path.join(folder, ".~%s.schrijfblad-tmp" % os.path.basename(path))
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        if ext in CT_MAIN:
            if self.path != path:
                self.path = path
                self.filename = os.path.basename(path)
            self.dirty = False
        self.version += 1
        remember_recent(path)
        return {"path": path}

    # -- tekst en Markdown
    def _paragraphs(self, root):
        for el in root:
            if X.is_w(el, "p"):
                yield "p", el
            elif X.is_w(el, "tbl"):
                yield "tbl", el
            elif X.is_w(el, "sdt"):
                content = el.find(w("sdtContent"))
                if content is not None:
                    yield from self._paragraphs(content)

    def to_text(self):
        out = []
        body = self.containers["body"][0]
        for kind, el in self._paragraphs(body):
            if kind == "p":
                out.append(X.text_of(el))
            else:
                for tr in el.findall(w("tr")):
                    out.append("\t".join(X.text_of(tc).replace("\n", " ") for tc in tr.findall(w("tc"))))
        return "\n".join(out) + "\n"

    def to_markdown(self):
        sh = self.sheet or StyleSheet(self.document)
        nums = sh.numbering()
        body = self.containers["body"][0]
        out, prev_list = [], False
        for kind, el in self._paragraphs(body):
            if kind == "tbl":
                rows = [[md_inline(self, tc).replace("|", "\\|").replace("\n", " ") for tc in tr.findall(w("tc"))]
                        for tr in el.findall(w("tr"))]
                if rows:
                    n = max(len(r) for r in rows)
                    rows = [r + [""] * (n - len(r)) for r in rows]
                    out.append("")
                    out.append("| " + " | ".join(rows[0]) + " |")
                    out.append("|" + "---|" * n)
                    for r in rows[1:]:
                        out.append("| " + " | ".join(r) + " |")
                    out.append("")
                prev_list = False
                continue
            text = md_inline(self, el)
            pPr = el.find(w("pPr"))
            sid = wval(pPr.find(w("pStyle"))) if pPr is not None else None
            raw = ""
            if sid and sid in sh.styles:
                raw = (wval(sh.styles[sid].find(w("name")), "") or "").lower()
            np = pPr.find(w("numPr")) if pPr is not None else None
            numinfo = None
            if np is not None and wval(np.find(w("numId"))) not in (None, "0"):
                numinfo = (wval(np.find(w("numId"))), int(wval(np.find(w("ilvl")), "0") or 0))
            elif sid:
                numinfo = sh.style_numpr(sid)
            m = re.match(r"heading (\d)", raw)
            if m and text.strip():
                out.append("")
                out.append("#" * min(6, int(m.group(1))) + " " + text.strip())
                out.append("")
                prev_list = False
            elif raw == "title" and text.strip():
                out.append("# " + text.strip())
                out.append("")
                prev_list = False
            elif numinfo:
                lvl_info = nums.get(numinfo[0], {}).get("levels", {}).get(str(numinfo[1]), {})
                bullet = lvl_info.get("fmt", "bullet") == "bullet"
                out.append("  " * numinfo[1] + ("- " if bullet else "1. ") + text.strip())
                prev_list = True
            else:
                if prev_list:
                    out.append("")
                out.append(text)
                out.append("")
                prev_list = False
        md = "\n".join(out)
        return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


# ---------------------------------------------------------------------------
# Losse hulpfuncties

def md_inline(doc, el):
    out = []
    link, link_text = None, []

    def close_link():
        nonlocal link
        if link is not None:
            href = doc._href(link, doc.document.part) or ""
            text = "".join(link_text)
            out.append("[%s](%s)" % (text, href) if href and text.strip() else text)
            link_text.clear()
            link = None

    for r in el.iter(w("r")):
        anc = r.getparent()
        if X.is_w(anc, "del") or X.is_w(anc, "moveFrom"):
            continue
        hl = anc if X.is_w(anc, "hyperlink") else None
        if hl is not link:
            close_link()
            link = hl
        txt = "".join((c.text or "") if X.is_w(c, "t") else "\t" if X.is_w(c, "tab") else
                      "\n" if X.is_w(c, "br") else "" for c in r)
        if not txt:
            continue
        p = X.props_from_rpr(r.find(w("rPr")))
        core = txt.strip()
        if core and (p.get("b") or p.get("i")):
            mark = ("**" if p.get("b") else "") + ("*" if p.get("i") else "")
            lead = txt[:len(txt) - len(txt.lstrip())]
            trail = txt[len(txt.rstrip()):]
            txt = "%s%s%s%s%s" % (lead, mark, core, mark[::-1], trail)
        (link_text if link is not None else out).append(txt)
    close_link()
    return "".join(out)


def fix_fields(root):
    stack = []
    for el in list(root.iter(w("fldChar"), w("instrText"))):
        if X.is_w(el, "instrText"):
            if stack:
                stack[-1]["instr"].append(el)
            continue
        t = el.get(w("fldCharType"))
        if t == "begin":
            stack.append({"begin": el, "instr": [], "sep": None})
        elif t == "separate":
            if stack:
                stack[-1]["sep"] = el
            else:
                _drop(el)
        elif t == "end":
            if stack:
                stack.pop()
            else:
                _drop(el)
    for frame in stack:
        for el in [frame["begin"]] + frame["instr"] + ([frame["sep"]] if frame["sep"] is not None else []):
            _drop(el)


def _drop(el):
    parent = el.getparent()
    if parent is None:
        return
    if X.is_w(parent, "r") and all(local(c) in ("rPr",) or c is el for c in parent):
        gp = parent.getparent()
        if gp is not None:
            gp.remove(parent)
    else:
        parent.remove(el)


def fix_pairs(root, start, end):
    starts = {e.get(w("id")): e for e in root.iter(w(start))}
    ends = {e.get(w("id")): e for e in root.iter(w(end))}
    for k, e in starts.items():
        if k not in ends:
            _drop(e)
    for k, e in ends.items():
        if k not in starts:
            _drop(e)


def _unwrap(el):
    parent = el.getparent()
    if parent is None:
        return
    idx = list(parent).index(el)
    for i, c in enumerate(list(el)):
        parent.insert(idx + i, c)
    parent.remove(el)


def _merge_with_next(p):
    nxt = p.getnext()
    if nxt is None or not X.is_w(nxt, "p"):
        return
    for c in list(nxt):
        if not X.is_w(c, "pPr"):
            p.append(c)
    nxt.getparent().remove(nxt)


def resolve_tracked(root, accept=True):
    """Alle bijgehouden wijzigingen accepteren of afwijzen."""
    keep, drop = ("ins", "moveTo"), ("del", "moveFrom")
    if not accept:
        keep, drop = drop, keep
    # alineamarkeringen
    merge = []
    for p in list(root.iter(w("p"))):
        mark = p.find(w("pPr") + "/" + w("rPr"))
        if mark is None:
            continue
        for tag in ("ins", "del", "moveFrom", "moveTo"):
            el = mark.find(w(tag))
            if el is not None:
                mark.remove(el)
                if tag in drop:
                    merge.append(p)
    # rijen
    for tr in list(root.iter(w("tr"))):
        trPr = tr.find(w("trPr"))
        if trPr is None:
            continue
        for tag in ("ins", "del"):
            el = trPr.find(w(tag))
            if el is not None:
                trPr.remove(el)
                if tag in drop and tr.getparent() is not None:
                    tr.getparent().remove(tr)
    # opmaakwijzigingen
    for tag, holder in (("rPrChange", "rPr"), ("pPrChange", "pPr")):
        for ch in list(root.iter(w(tag))):
            parent = ch.getparent()
            if accept:
                parent.remove(ch)
                continue
            old = ch.find(w(holder))
            # bij een alinea horen de markering (rPr) en sectie-instellingen niet bij de oude opmaak
            keep_els = [c for c in parent if holder == "pPr" and local(c) in ("rPr", "sectPr")]
            for c in list(parent):
                parent.remove(c)
            if old is not None:
                for c in list(old):
                    parent.append(c)
            for c in keep_els:
                X.insert_ordered(parent, c, X.PPR_ORDER)
    for tag in ("sectPrChange", "tblPrChange", "trPrChange", "tcPrChange", "tblGridChange", "numberingChange"):
        for ch in list(root.iter(w(tag))):
            ch.getparent().remove(ch)
    for tag in ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd"):
        for ch in list(root.iter(w(tag))):
            ch.getparent().remove(ch)
    # inhoud
    for tag in drop:
        for el in list(root.iter(w(tag))):
            if el.getparent() is not None and not X.is_w(el.getparent(), "rPr"):
                el.getparent().remove(el)
    for tag in keep:
        for el in list(root.iter(w(tag))):
            if el.getparent() is None or X.is_w(el.getparent(), "rPr"):
                continue
            for dt_ in list(el.iter(w("delText"))):
                dt_.tag = w("t")
            for di in list(el.iter(w("delInstrText"))):
                di.tag = w("instrText")
            _unwrap(el)
    for p in merge:
        if p.getparent() is not None:
            _merge_with_next(p)


def convert_with_textutil(data, ext):
    tool = shutil.which("textutil")
    if not tool:
        raise UserError("Een %s-bestand kan Schrijfblad alleen op een Mac omzetten. Open het in Pages en "
                        "bewaar het als Word-document (.docx)." % ext)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "invoer" + ext)
        dst = os.path.join(tmp, "uitvoer.docx")
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.run([tool, "-convert", "docx", src, "-output", dst], capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(dst):
            raise UserError("Dit bestand kon niet omgezet worden: %s" % (proc.stderr.strip() or "onbekende fout"))
        with open(dst, "rb") as fh:
            return fh.read()


def decode_text(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def recent_files():
    try:
        with open(os.path.join(DATA_DIR, "recent.json"), encoding="utf-8") as fh:
            items = json.load(fh)
        return [p for p in items if isinstance(p, str) and os.path.exists(p)][:10]
    except (OSError, ValueError):
        return []


def remember_recent(path):
    try:
        _ensure_data_dir()
        path = os.path.abspath(path)
        items = [p for p in recent_files() if p != path]
        items.insert(0, path)
        with open(os.path.join(DATA_DIR, "recent.json"), "w", encoding="utf-8") as fh:
            json.dump(items[:10], fh)
    except OSError:
        pass


def backup_file(path):
    """Bewaar het origineel voordat we het voor het eerst overschrijven."""
    try:
        folder = os.path.join(DATA_DIR, "reservekopieen")
        os.makedirs(folder, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, os.path.join(folder, "%s-%s" % (stamp, os.path.basename(path))))
        files = sorted(os.listdir(folder))
        for old in files[:-30]:
            os.remove(os.path.join(folder, old))
    except OSError:
        pass
