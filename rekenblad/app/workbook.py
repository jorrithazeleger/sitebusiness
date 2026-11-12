"""Rekenblad: het geopende werkboek in het geheugen, met alle bewerkingen."""
from __future__ import annotations

import colorsys
import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import threading
import warnings
import zipfile
from copy import copy

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.styles import PatternFill
from openpyxl.styles.cell_style import StyleArray
from openpyxl.styles.colors import COLOR_INDEX
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange
from openpyxl.worksheet.formula import ArrayFormula

import calc
import formats as F
import refs as R

warnings.filterwarnings("ignore", module="openpyxl")
warnings.filterwarnings("ignore", category=DeprecationWarning)

DATA_DIR = os.path.join(os.path.expanduser("~"), ".rekenblad")
MAX_UNDO = 100
SNAPSHOT_CELL_LIMIT = 400_000
DEFAULT_THEME = ["FFFFFF", "000000", "E7E6E6", "44546A", "4472C4", "ED7D31",
                 "A5A5A5", "FFC000", "5B9BD5", "70AD47", "0563C1", "954F72"]
SHEET_NAME_BAD = re.compile(r"[\[\]:*?/\\]")


class UserError(Exception):
    """Fout die als nette melding aan de gebruiker getoond wordt."""


def px_from_width(width):
    return int(round(width * 8 + 8))


def width_from_px(px):
    return round(max(0.5, (px - 8) / 8.0), 2)


class Book:
    def __init__(self):
        self.lock = threading.RLock()
        self._reset()

    # ------------------------------------------------------------------ basis
    def _reset(self):
        self.wb = None
        self.vals = None
        self.path = None
        self.filename = None
        self.kind = None
        self.csv_delim = ","
        self.csv_encoding = "utf-8"
        self.dirty = False
        self.warnings = []
        self.backed_up = set()
        self.undo_stack = []
        self.redo_stack = []
        self._extent = {}
        self._fcache = {}
        self._ast = {}
        self._style_cache = {}
        self._theme = DEFAULT_THEME

    @property
    def loaded(self):
        return self.wb is not None

    def _require(self):
        if not self.wb:
            raise UserError("Er is geen bestand geopend.")

    def _pair(self, sheet):
        self._require()
        for ws in self.wb.worksheets:
            if ws.title == sheet:
                return ws, self._vws(ws)
        raise UserError("Blad '%s' bestaat niet (meer)." % sheet)

    def _vws(self, ws):
        if ws.title not in self.vals.sheetnames:
            self.vals.create_sheet(ws.title)
        return self.vals[ws.title]

    def _touch(self, ws=None):
        self.dirty = True
        if ws is None:
            self._extent.clear()
        else:
            self._extent.pop(id(ws), None)

    # ------------------------------------------------------------------ openen
    def new(self):
        wb = openpyxl.Workbook()
        wb.active.title = "Blad1"
        self._install(wb, None, None, "Nieuw werkboek.xlsx", "xlsx", [])
        return self

    def load_bytes(self, data, filename, path=None):
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".xls":
            raise UserError("Oude .xls-bestanden kan Rekenblad niet openen. Open het bestand in "
                            "Numbers of Excel en bewaar het als .xlsx.")
        if ext in (".csv", ".tsv", ".txt"):
            wb, delim, enc = self._csv_workbook(data, filename)
            self._install(wb, None, path, filename, "csv", [])
            self.csv_delim, self.csv_encoding = delim, enc
            return self
        if ext not in (".xlsx", ".xlsm", ".xltx", ".xltm"):
            raise UserError("Dit bestandstype wordt niet ondersteund. Kies een .xlsx-, .xlsm- of .csv-bestand.")
        keep_vba = ext in (".xlsm", ".xltm")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), keep_vba=keep_vba)
            vals = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except zipfile.BadZipFile:
            raise UserError("Dit bestand is geen geldig Excel-bestand of is beschadigd.")
        except Exception as exc:
            raise UserError("Het bestand kon niet geopend worden: %s" % exc)
        warns = self._inspect_zip(data)
        self._install(wb, vals, path, filename, "xlsm" if keep_vba else "xlsx", warns)
        return self

    def load_path(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        self.load_bytes(data, os.path.basename(path), path)
        remember_recent(path)
        return self

    def _install(self, wb, vals, path, filename, kind, warns):
        self._reset()
        if vals is None:
            vals = openpyxl.Workbook()
            vals.remove(vals.active)
        for vws in vals.worksheets:
            for m in list(vws.merged_cells.ranges):
                vws.unmerge_cells(str(m))
            vws._images, vws._charts = [], []
        self.wb, self.vals = wb, vals
        self.path, self.filename, self.kind = path, filename, kind
        self.warnings = warns
        self._theme = self._parse_theme()
        for ws in wb.worksheets:
            self._vws(ws)
        self._recalc_missing()

    def _inspect_zip(self, data):
        found = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                shapes = False
                for n in names:
                    if n.startswith("xl/drawings/drawing") and n.endswith(".xml"):
                        content = z.read(n)
                        if b"<xdr:sp>" in content or b"<xdr:sp " in content:
                            shapes = True
                            break
                if shapes:
                    found.append("vormen of tekstvakken")
                if any(n.startswith("xl/slicer") for n in names):
                    found.append("slicers")
                if any(n.startswith("xl/threadedComments") for n in names):
                    found.append("opmerkingen met antwoorden")
                if any("ctrlProps" in n for n in names):
                    found.append("formulierknoppen")
                if any(n.startswith("xl/diagrams") for n in names):
                    found.append("SmartArt")
                charts = any(n.startswith("xl/charts/") for n in names)
        except zipfile.BadZipFile:
            return []
        out = []
        if found:
            out.append("Dit bestand bevat %s. Die gaan verloren als je hier opslaat. Bij de eerste "
                       "keer opslaan bewaart Rekenblad een reservekopie van het origineel."
                       % _join_nl(found))
        if charts:
            out.append("Dit bestand bevat grafieken. Die blijven bewaard, maar kunnen er na opslaan "
                       "iets eenvoudiger uitzien.")
        return out

    def _csv_workbook(self, data, filename):
        text, encoding = None, "utf-8"
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                encoding = enc
                break
            except UnicodeDecodeError:
                continue
        sample = text[:20000]
        delim = ","
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            counts = {d: sample.count(d) for d in ",;\t"}
            delim = max(counts, key=counts.get) if any(counts.values()) else ","
        wb = openpyxl.Workbook()
        ws = wb.active
        title = SHEET_NAME_BAD.sub("", os.path.splitext(filename)[0])[:31] or "Blad1"
        ws.title = title
        for r, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim), start=1):
            for c, raw in enumerate(row, start=1):
                value, fmt = F.parse_input(raw, allow_formula=False)
                if value is None:
                    continue
                cell = ws.cell(r, c)
                cell.value = value
                if fmt:
                    cell.number_format = fmt
        return wb, delim, encoding

    # ------------------------------------------------------------------ status
    def state(self, can_native=False):
        base = {"loaded": self.loaded, "can_native": can_native, "recent": recent_files()}
        if not self.loaded:
            return base
        sheets = []
        for ws in self.wb.worksheets:
            nr, nc = self.extent(ws)
            ncols = min(max(nc + 3, 26), R.MAX_COL)
            sheets.append({
                "name": ws.title,
                "nrows": min(max(nr + 50, 100), R.MAX_ROW),
                "ncols": ncols,
                "colw": self.col_widths(ws, ncols),
                "hidden": ws.sheet_state != "visible",
            })
        active = 0
        try:
            active = self.wb.worksheets.index(self.wb.active)
        except (ValueError, TypeError):
            pass
        base.update({
            "filename": self.filename, "path": self.path, "kind": self.kind,
            "dirty": self.dirty, "warnings": self.warnings, "sheets": sheets,
            "active": active, "undo": len(self.undo_stack), "redo": len(self.redo_stack),
        })
        return base

    def extent(self, ws):
        key = id(ws)
        if key in self._extent:
            return self._extent[key]
        mr = mc = 0
        for (r, c), cell in ws._cells.items():
            if cell.value is not None:
                if r > mr:
                    mr = r
                if c > mc:
                    mc = c
        for m in ws.merged_cells.ranges:
            mr, mc = max(mr, m.max_row), max(mc, m.max_col)
        self._extent[key] = (mr, mc)
        return mr, mc

    def col_widths(self, ws, ncols):
        default = ws.sheet_format.defaultColWidth or ((ws.sheet_format.baseColWidth or 8) + 0.43)
        out = [px_from_width(default)] * ncols
        for key, d in ws.column_dimensions.items():
            lo = d.min or _col(key)
            hi = d.max or lo
            if lo is None:
                continue
            for c in range(lo, min(hi, ncols) + 1):
                if d.hidden:
                    out[c - 1] = 6
                elif d.width:
                    out[c - 1] = max(20, px_from_width(d.width))
        return out

    # ------------------------------------------------------------------ rijen lezen
    def get_rows(self, sheet, start, count):
        ws, vws = self._pair(sheet)
        start = max(1, int(start))
        end = min(R.MAX_ROW, start + max(1, min(int(count), 1000)) - 1)
        _nr, nc = self.extent(ws)
        ncols = min(max(nc + 3, 26), R.MAX_COL)
        styles, sidx = [], {}
        rows = {}
        cells = ws._cells
        vcells = vws._cells
        for r in range(start, end + 1):
            row = {}
            for c in range(1, ncols + 1):
                cell = cells.get((r, c))
                if cell is None or isinstance(cell, MergedCell):
                    continue
                info = self._cell_info(cell, vcells.get((r, c)), styles, sidx)
                if info:
                    row[c] = info
            if row:
                rows[r] = row
        for m in ws.merged_cells.ranges:
            if m.max_row < start or m.min_row > end:
                continue
            span = m.max_col - m.min_col + 1
            for r in range(max(start, m.min_row), min(end, m.max_row) + 1):
                row = rows.setdefault(r, {})
                first = row.setdefault(m.min_col, {"d": "", "k": "s"})
                if span > 1:
                    first["cs"] = span
                if r > m.min_row:
                    first["m"] = 1
                    first["d"] = ""
                    first.pop("e", None)
                for c in range(m.min_col + 1, m.max_col + 1):
                    row[c] = {"h": 1}
        return {"start": start, "rows": rows, "styles": styles}

    def _cell_info(self, cell, vcell, styles, sidx):
        v = cell.value
        has_style = cell.has_style
        if v is None and not has_style:
            return None
        fmt = cell.number_format
        info = {}
        if cell.data_type == "f":
            text = v.text if isinstance(v, ArrayFormula) else v
            text = text if isinstance(text, str) else str(text)
            if not text.startswith("="):
                text = "=" + text
            info["e"] = F.strip_prefixes(text)
            info["f"] = 1
            cached = vcell.value if vcell is not None else None
            if cached is None:
                info["d"], info["k"], info["st"] = info["e"], "s", 1
            else:
                d, k = F.display(cached, fmt, isinstance(cached, str) and cached in F.ERRORS)
                info["d"], info["k"] = d, k
                if k == "n" and isinstance(cached, (int, float)) and not isinstance(cached, bool):
                    info["v"] = cached
        elif v is not None:
            d, k = F.display(v, fmt, cell.data_type == "e")
            e = F.edit_text(v, fmt)
            info["d"], info["k"] = d, k
            if e != d:
                info["e"] = e
            if k == "n":
                info["v"] = v
        else:
            info["d"], info["k"] = "", "s"
        if fmt and fmt != "General":
            info["nf"] = fmt
        if has_style:
            key = tuple(cell._style)
            st = self._style_cache.get(key)
            if st is None:
                st = self._style_obj(cell)
                self._style_cache[key] = st
            if st is not False:
                skey = st["css"] + "|" + str(st.get("a"))
                if skey not in sidx:
                    sidx[skey] = len(styles)
                    styles.append(st)
                info["s"] = sidx[skey]
        return info

    def _style_obj(self, cell):
        css = []
        st = {}
        font = cell.font
        if font is not None:
            if font.b:
                css.append("font-weight:700")
                st["fw"] = 1
            if font.i:
                css.append("font-style:italic")
                st["fi"] = 1
            deco = []
            if font.u and font.u != "none":
                deco.append("underline")
            if font.strike:
                deco.append("line-through")
            if deco:
                css.append("text-decoration:" + " ".join(deco))
            col = self._color(font.color)
            if col and col != "000000":
                css.append("color:#" + col)
            if font.sz:
                try:
                    sz = float(font.sz)
                    if abs(sz - 11) > 0.5:
                        px = int(round(min(20, max(9, 13 * sz / 11.0))))
                        css.append("font-size:%dpx" % px)
                        st["px"] = px
                except (TypeError, ValueError):
                    pass
        fill = cell.fill
        if getattr(fill, "fill_type", None) and fill.fill_type != "none" and hasattr(fill, "fgColor"):
            col = self._color(fill.fgColor) or self._color(fill.start_color)
            if col:
                css.append("background:#" + col)
        al = cell.alignment
        if al is not None:
            h = al.horizontal
            if h in ("center", "centerContinuous", "distributed"):
                st["a"] = "center"
            elif h in ("right",):
                st["a"] = "right"
            elif h in ("left", "fill", "justify"):
                st["a"] = "left"
            if al.wrap_text:
                st["w"] = 1
        if not css and not st:
            return False
        st["css"] = ";".join(css)
        return st

    def _color(self, color):
        if color is None:
            return None
        try:
            t = color.type
            if t == "rgb":
                rgb = color.rgb
                if not isinstance(rgb, str) or len(rgb) < 6:
                    return None
                return rgb[-6:].upper()
            if t == "indexed":
                idx = color.indexed
                if idx is None or idx >= 64:
                    return None
                return COLOR_INDEX[idx][-6:]
            if t == "theme":
                idx = color.theme
                if idx is None or idx >= len(self._theme):
                    return None
                return _tint(self._theme[idx], color.tint or 0)
        except Exception:
            return None
        return None

    def _parse_theme(self):
        xml = getattr(self.wb, "loaded_theme", None)
        if not xml:
            return DEFAULT_THEME
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8", "ignore")
        order = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4",
                 "accent5", "accent6", "hlink", "folHlink"]
        out = []
        for i, name in enumerate(order):
            m = re.search(r"<a:%s>(.*?)</a:%s>" % (name, name), xml, re.S)
            val = None
            if m:
                m2 = re.search(r'srgbClr val="([0-9A-Fa-f]{6})"', m.group(1)) or \
                    re.search(r'lastClr="([0-9A-Fa-f]{6})"', m.group(1))
                if m2:
                    val = m2.group(1).upper()
            out.append(val or DEFAULT_THEME[i])
        return out

    # ------------------------------------------------------------------ cellen bewerken
    def set_cells(self, sheet, cells):
        ws, vws = self._pair(sheet)
        changes, seeds = [], []
        errors = []
        for item in cells:
            r, c = int(item["r"]), int(item["c"])
            if not (1 <= r <= R.MAX_ROW and 1 <= c <= R.MAX_COL):
                continue
            cur = ws._cells.get((r, c))
            if isinstance(cur, MergedCell):
                continue
            try:
                value, fmt = F.parse_input(item.get("v"))
            except F.FormulaError as exc:
                errors.append(str(exc))
                continue
            if cur is None and value is None:
                continue
            before = _snap(ws, vws, r, c)
            cell = ws.cell(r, c)
            if _same(cell.value, value) and (fmt is None or cell.number_format == fmt):
                continue
            cell.value = value
            if fmt and F.fmt_category(cell.number_format) != F.fmt_category(fmt):
                cell.number_format = fmt
            is_formula = isinstance(value, str) and value.startswith("=")
            vc = vws.cell(r, c)
            vc.value = None if is_formula else value
            changes.append((r, c, before, _snap(ws, vws, r, c)))
            seeds.append((ws.title.lower(), r, c, r, c))
        if changes:
            self._invalidate(seeds)
            self._push({"kind": "cells", "sheet": ws.title, "changes": changes})
            self._touch(ws)
        if errors and not changes:
            raise UserError(errors[0])
        return {"changed": len(changes), "errors": errors}

    def clear_range(self, sheet, r1, c1, r2, c2):
        ws, _ = self._pair(sheet)
        r1, r2 = sorted((int(r1), int(r2)))
        c1, c2 = sorted((int(c1), int(c2)))
        keys = [(r, c) for (r, c), cell in list(ws._cells.items())
                if r1 <= r <= r2 and c1 <= c <= c2 and cell.value is not None
                and not isinstance(cell, MergedCell)]
        if not keys:
            return {"changed": 0}
        return self.set_cells(sheet, [{"r": r, "c": c, "v": None} for r, c in keys])

    def set_format(self, sheet, r1, c1, r2, c2, props):
        ws, vws = self._pair(sheet)
        r1, r2 = sorted((int(r1), int(r2)))
        c1, c2 = sorted((int(c1), int(c2)))
        nr, nc = self.extent(ws)
        r2 = min(r2, max(nr + 50, r1))
        c2 = min(c2, max(nc + 3, c1))
        if (r2 - r1 + 1) * (c2 - c1 + 1) > 200_000:
            raise UserError("De selectie is te groot om in één keer op te maken.")
        changes = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if isinstance(ws._cells.get((r, c)), MergedCell):
                    continue
                before = _snap(ws, vws, r, c)
                cell = ws.cell(r, c)
                if "bold" in props or "italic" in props or "color" in props:
                    f = copy(cell.font)
                    if "bold" in props:
                        f.b = bool(props["bold"])
                    if "italic" in props:
                        f.i = bool(props["italic"])
                    if "color" in props:
                        f.color = props["color"] or None
                    cell.font = f
                if "fill" in props:
                    cell.fill = PatternFill("solid", fgColor=props["fill"]) if props["fill"] \
                        else PatternFill(fill_type=None)
                if "align" in props:
                    a = copy(cell.alignment)
                    a.horizontal = props["align"] or None
                    cell.alignment = a
                if "numfmt" in props:
                    cell.number_format = props["numfmt"] or "General"
                after = _snap(ws, vws, r, c)
                if before != after:
                    changes.append((r, c, before, after))
        if changes:
            self._push({"kind": "cells", "sheet": ws.title, "changes": changes})
            self._touch(ws)
        return {"changed": len(changes)}

    def set_col_width(self, sheet, c, px):
        ws, _ = self._pair(sheet)
        c = int(c)
        self._split_col_group(ws, c)
        cd = ws.column_dimensions[get_column_letter(c)]
        before = cd.width
        cd.width = width_from_px(float(px))
        self._push({"kind": "colw", "sheet": ws.title, "c": c, "before": before,
                    "after": cd.width})
        self._touch(ws)
        return {}

    def _split_col_group(self, ws, c):
        dims = ws.column_dimensions
        for key, d in list(dims.items()):
            lo = d.min or _col(key)
            hi = d.max or lo
            if lo is None or not (lo <= c <= hi) or lo == hi:
                continue
            del dims[key]
            for a, b in ((lo, c - 1), (c, c), (c + 1, hi)):
                if a > b:
                    continue
                nd = copy(d)
                nd.index = get_column_letter(a)
                nd.min, nd.max = a, b
                dims[nd.index] = nd
            return

    # ------------------------------------------------------------------ afhankelijkheden
    def _names_map(self):
        out = {}
        try:
            items = list(self.wb.defined_names.items())
        except Exception:
            items = []
        for ws in self.wb.worksheets:
            try:
                items += list(ws.defined_names.items())
            except Exception:
                pass
        for name, dn in items:
            try:
                areas = []
                for sheet, coord in dn.destinations:
                    area = R.parse_area(coord.replace("$", ""))
                    if area:
                        areas.append((sheet.lower(),) + R.area_bounds(area))
                if areas:
                    out[name.lower()] = areas
            except Exception:
                continue
        return out

    def _dep_index(self):
        names = None
        single, colb, wide = {}, {}, {}
        for ws in self.wb.worksheets:
            home = ws.title
            hl = home.lower()
            for (r, c), cell in ws._cells.items():
                if cell.data_type != "f":
                    continue
                v = cell.value
                text = v.text if isinstance(v, ArrayFormula) else v
                if not isinstance(text, str):
                    continue
                ck = (hl, r, c)
                cached = self._fcache.get(ck)
                if cached is not None and cached[0] == text:
                    areas = cached[1]
                else:
                    if names is None:
                        names = self._names_map()
                    areas = R.formula_areas(text if text.startswith("=") else "=" + text, home, names)
                    self._fcache[ck] = (text, areas)
                for s, r1, c1, r2, c2 in areas:
                    if r1 == r2 and c1 == c2:
                        single.setdefault((s, r1, c1), []).append(ck)
                    elif c2 - c1 < 64:
                        for cc in range(c1, c2 + 1):
                            colb.setdefault((s, cc), []).append((r1, r2, ck))
                    else:
                        wide.setdefault(s, []).append((r1, c1, r2, c2, ck))
        return single, colb, wide

    def _invalidate(self, seeds, recalc=True):
        """Formules die (via via) van deze cellen afhangen opnieuw uitrekenen."""
        seen = set()
        for s, r1, c1, r2, c2 in seeds:
            if r1 == r2 and c1 == c2:
                ws = next((w for w in self.wb.worksheets if w.title.lower() == s), None)
                cell = ws._cells.get((r1, c1)) if ws is not None else None
                if cell is not None and cell.data_type == "f":
                    seen.add((s, r1, c1))
        seen |= self._dependents(seeds)
        if not seen:
            return
        by_lower = {ws.title.lower(): self._vws(ws) for ws in self.wb.worksheets}
        for s, r, c in seen:
            vws = by_lower.get(s)
            if vws is not None:
                vc = vws._cells.get((r, c))
                if vc is not None:
                    vc.value = None
        if recalc:
            self._recalc(seen)

    def _dependents(self, seeds):
        single, colb, wide = self._dep_index()
        if not (single or colb or wide):
            return set()
        seen = set()
        queue = list(seeds)
        while queue:
            s, r1, c1, r2, c2 = queue.pop()
            hits = []
            if (r2 - r1 + 1) * (c2 - c1 + 1) <= 4096:
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        hits.extend(single.get((s, r, c), ()))
            else:
                for (ss, r, c), keys in single.items():
                    if ss == s and r1 <= r <= r2 and c1 <= c <= c2:
                        hits.extend(keys)
            if c2 - c1 < 64:
                for c in range(c1, c2 + 1):
                    for a, b, k in colb.get((s, c), ()):
                        if a <= r2 and b >= r1:
                            hits.append(k)
            else:
                for (ss, c), lst in colb.items():
                    if ss == s and c1 <= c <= c2:
                        hits.extend(k for a, b, k in lst if a <= r2 and b >= r1)
            for a1, b1, a2, b2, k in wide.get(s, ()):
                if a1 <= r2 and a2 >= r1 and b1 <= c2 and b2 >= c1:
                    hits.append(k)
            for k in hits:
                if k not in seen:
                    seen.add(k)
                    queue.append((k[0], k[1], k[2], k[1], k[2]))
        return seen

    def _parse_cache(self, formula):
        hit = self._ast.get(formula)
        if hit is None:
            try:
                hit = calc.parse(formula)
            except RecursionError:
                raise
            except Exception as exc:
                hit = calc.Unsupported(str(exc))
            if len(self._ast) > 200_000:
                self._ast.clear()
            self._ast[formula] = hit
        if isinstance(hit, Exception):
            raise calc.Unsupported(str(hit))
        return hit

    def _recalc(self, keys):
        """Reken deze formulecellen uit en bewaar de uitkomst als 'laatst berekende waarde'."""
        if not keys:
            return
        ev = calc.Evaluator(self, set(keys))
        results = {}
        todo = sorted(keys, key=lambda k: (k[1], k[2], k[0]))
        for _attempt in range(6):
            deep = []
            for key in todo:
                try:
                    results[key] = ev.compute(key)
                except calc.Deep:
                    ev.stack.clear()
                    deep.append(key)
                except calc.Unsupported:
                    results[key] = None
            if not deep or len(deep) == len(todo):
                for key in deep:
                    results[key] = None
                break
            todo = deep
        for key, res in results.items():
            vws = ev.vws.get(key[0])
            if vws is None:
                continue
            if res is None:
                vc = vws._cells.get((key[1], key[2]))
                if vc is not None:
                    vc.value = None
            else:
                vws.cell(key[1], key[2]).value = res

    def _recalc_missing(self, limit=100_000):
        keys = set()
        for ws in self.wb.worksheets:
            vws = self._vws(ws)
            hl = ws.title.lower()
            for (r, c), cell in ws._cells.items():
                if cell.data_type != "f" or not isinstance(cell.value, str):
                    continue
                vc = vws._cells.get((r, c))
                if vc is None or vc.value is None:
                    keys.add((hl, r, c))
                    if len(keys) > limit:
                        return
        self._recalc(keys)

    # ------------------------------------------------------------------ rijen en kolommen
    def insert(self, sheet, axis, at, count):
        return self._structural(sheet, axis, int(at), int(count))

    def delete(self, sheet, axis, at, count):
        return self._structural(sheet, axis, int(at), -int(count))

    def _structural(self, sheet, axis, at, n):
        ws, vws = self._pair(sheet)
        if n == 0:
            return {}
        limit = R.MAX_ROW if axis == "row" else R.MAX_COL
        if not 1 <= at <= limit:
            raise UserError("Ongeldige positie.")
        self._check_tables(ws, axis, at, n)
        self._push_snapshot()
        title = ws.title
        if n < 0:
            k = -n
            if axis == "row":
                seed = (title.lower(), at, 1, at + k - 1, R.MAX_COL)
            else:
                seed = (title.lower(), 1, at, R.MAX_ROW, at + k - 1)
            self._invalidate([seed], recalc=False)
        merged = [str(m) for m in ws.merged_cells.ranges]
        for m in merged:
            try:
                ws.unmerge_cells(m)
            except (KeyError, ValueError):
                pass
        if axis == "row":
            if n > 0:
                ws.insert_rows(at, n)
                vws.insert_rows(at, n)
            else:
                ws.delete_rows(at, -n)
                vws.delete_rows(at, -n)
        else:
            if n > 0:
                ws.insert_cols(at, n)
                vws.insert_cols(at, n)
            else:
                ws.delete_cols(at, -n)
                vws.delete_cols(at, -n)
        for m in merged:
            new = R.shift_range_text(m, axis, at, n)
            if new and ":" in new:
                a, b = new.split(":")
                if a != b:
                    ws.merge_cells(new)
        self._shift_dims(ws, axis, at, n)
        self._shift_features(ws, axis, at, n)
        self._rewrite_formulas(lambda home: R.shift_fn(home, title, axis, at, n), title,
                               array_target=(ws, axis, at, n))
        self._fcache.clear()
        self._touch()
        self._recalc_missing()
        return {}

    def _check_tables(self, ws, axis, at, n):
        for name, table in ws.tables.items():
            ref = table.ref if hasattr(table, "ref") else table
            area = R.parse_area(str(ref).replace("$", ""))
            if not area:
                continue
            r1, c1, r2, c2 = R.area_bounds(area)
            if axis == "col":
                lo, hi = c1, c2
                if n > 0 and lo < at <= hi:
                    raise UserError("Kolommen invoegen midden in tabel '%s' kan hier niet. "
                                    "Doe dat in Excel of Numbers." % name)
                if n < 0 and not (at + (-n) - 1 < lo or at > hi):
                    raise UserError("Kolommen van tabel '%s' verwijderen kan hier niet. "
                                    "Doe dat in Excel of Numbers." % name)
            else:
                if n < 0:
                    d1, d2 = at, at - n - 1
                    if d1 <= r1 <= d2 and d2 < r2:
                        raise UserError("De kopregel van tabel '%s' kan niet los verwijderd worden." % name)
                    res = R.shift_interval(r1, r2, at, n)
                    if res is not None and res[1] <= res[0] and not (d1 <= r1 and d2 >= r2):
                        raise UserError("Tabel '%s' moet minstens één rij overhouden." % name)

    def _shift_dims(self, ws, axis, at, n):
        if axis == "row":
            dims = list(ws.row_dimensions.items())
            ws.row_dimensions.clear()
            for r, d in dims:
                res = R.shift_interval(r, r, at, n)
                if res is None or res[0] > R.MAX_ROW:
                    continue
                d.index = res[0]
                ws.row_dimensions[res[0]] = d
        else:
            dims = list(ws.column_dimensions.items())
            ws.column_dimensions.clear()
            for key, d in dims:
                lo = d.min or _col(key)
                hi = d.max or lo
                if lo is None:
                    continue
                res = R.shift_interval(lo, hi, at, n)
                if res is None or res[0] > R.MAX_COL:
                    continue
                d.min, d.max = res[0], min(res[1], R.MAX_COL)
                d.index = get_column_letter(d.min)
                ws.column_dimensions[d.index] = d

    def _shift_features(self, ws, axis, at, n):
        for table in list(ws.tables.values()):
            new = R.shift_range_text(table.ref, axis, at, n)
            if new:
                table.ref = new
                if table.autoFilter is not None and table.autoFilter.ref:
                    af = R.shift_range_text(table.autoFilter.ref, axis, at, n)
                    table.autoFilter.ref = af or new
            else:
                del ws.tables[table.name]
        if ws.auto_filter is not None and ws.auto_filter.ref:
            ws.auto_filter.ref = R.shift_range_text(ws.auto_filter.ref, axis, at, n)
        try:
            new_cf = ConditionalFormattingList()
            for cf in ws.conditional_formatting:
                rng = R.shift_multi_text(str(cf.sqref), axis, at, n)
                if not rng:
                    continue
                for rule in cf.rules:
                    new_cf.add(rng, rule)
            ws.conditional_formatting = new_cf
        except Exception:
            pass
        try:
            keep = []
            for dv in ws.data_validations.dataValidation:
                rng = R.shift_multi_text(str(dv.sqref), axis, at, n)
                if rng:
                    dv.sqref = MultiCellRange(rng)
                    keep.append(dv)
            ws.data_validations.dataValidation = keep
        except Exception:
            pass

    def _rewrite_formulas(self, factory, needle_sheet, array_target=None):
        needle = needle_sheet.lower()
        for ws in self.wb.worksheets:
            fn = factory(ws.title)
            same = ws.title.lower() == needle
            for cell in list(ws._cells.values()):
                if cell.data_type != "f":
                    continue
                v = cell.value
                if isinstance(v, ArrayFormula):
                    if v.text and (same or needle in v.text.lower()):
                        v.text = R.map_range_tokens(v.text, fn)
                    if array_target and ws is array_target[0] and v.ref:
                        _, axis, at, n = array_target
                        v.ref = R.shift_range_text(v.ref, axis, at, n) or v.ref
                    continue
                if not isinstance(v, str):
                    continue
                if not same and needle not in v.lower():
                    continue
                nv = R.map_range_tokens(v, fn)
                if nv != v:
                    cell.value = nv
        self._rewrite_names(factory, needle)

    def _rewrite_names(self, factory, needle):
        def fix(dn, home):
            text = getattr(dn, "attr_text", None)
            if not text or needle not in text.lower():
                return
            new = R.map_range_tokens("=" + text, factory(home))
            if new != "=" + text:
                dn.attr_text = new[1:]
        try:
            for dn in self.wb.defined_names.values():
                fix(dn, None)
            for ws in self.wb.worksheets:
                for dn in ws.defined_names.values():
                    fix(dn, ws.title)
        except Exception:
            pass

    # ------------------------------------------------------------------ bladen
    def _check_name(self, name, exclude=None):
        name = (name or "").strip()
        if not name:
            raise UserError("Geef het blad een naam.")
        if len(name) > 31:
            raise UserError("Een bladnaam mag maximaal 31 tekens lang zijn.")
        if SHEET_NAME_BAD.search(name) or name.startswith("'") or name.endswith("'"):
            raise UserError("Een bladnaam mag geen van deze tekens bevatten: [ ] : * ? / \\ '")
        for s in self.wb.sheetnames:
            if s.lower() == name.lower() and s != exclude:
                raise UserError("Er is al een blad met de naam '%s'." % s)
        return name

    def add_sheet(self, name=None):
        self._require()
        if not name:
            i = len(self.wb.sheetnames) + 1
            while any(s.lower() == ("blad%d" % i) for s in self.wb.sheetnames):
                i += 1
            name = "Blad%d" % i
        name = self._check_name(name)
        self._push_snapshot()
        self.wb.create_sheet(name)
        self.vals.create_sheet(name)
        self._touch()
        return {"name": name}

    def rename_sheet(self, old, new):
        ws, vws = self._pair(old)
        new = self._check_name(new, exclude=old)
        if new == old:
            return {"name": new}
        self._push_snapshot()
        ws.title = new
        vws.title = new
        self._rewrite_formulas(lambda home: R.rename_fn(old, new), old)
        self._fcache.clear()
        self._touch()
        return {"name": new}

    def delete_sheet(self, name):
        ws, vws = self._pair(name)
        if len(self.wb.worksheets) <= 1:
            raise UserError("Een werkboek heeft minstens één blad nodig.")
        self._push_snapshot()
        self._invalidate([(name.lower(), 1, 1, R.MAX_ROW, R.MAX_COL)], recalc=False)
        self.wb.remove(ws)
        self.vals.remove(vws)
        self._rewrite_formulas(lambda home: R.delete_sheet_fn(name), name)
        self._fcache.clear()
        self._touch()
        self._recalc_missing()
        return {}

    # ------------------------------------------------------------------ ongedaan maken
    def _push(self, entry):
        self.undo_stack.append(entry)
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _total_cells(self):
        return sum(len(ws._cells) for ws in self.wb.worksheets)

    def _prepare_images(self):
        """openpyxl kan een afbeelding maar één keer wegschrijven; bewaar de bytes zelf."""
        for ws in self.wb.worksheets:
            for img in getattr(ws, "_images", []):
                data = getattr(img, "_rekenblad_data", None)
                if data is None:
                    try:
                        data = img._data()
                    except Exception:
                        continue
                    img._rekenblad_data = data
                img.ref = io.BytesIO(data)

    def _snapshot(self):
        a, b = io.BytesIO(), io.BytesIO()
        self._prepare_images()
        self.wb.save(a)
        self.vals.save(b)
        return {"kind": "snap", "wb": a.getvalue(), "vals": b.getvalue()}

    def _push_snapshot(self):
        if self._total_cells() > SNAPSHOT_CELL_LIMIT:
            self.undo_stack.clear()
            self.redo_stack.clear()
            return
        self._push(self._snapshot())
        snaps = [e for e in self.undo_stack if e["kind"] == "snap"]
        if len(snaps) > 15:
            self.undo_stack.remove(snaps[0])

    def _restore_snapshot(self, entry):
        keep_vba = self.kind == "xlsm"
        wb = openpyxl.load_workbook(io.BytesIO(entry["wb"]), keep_vba=keep_vba)
        vals = openpyxl.load_workbook(io.BytesIO(entry["vals"]))
        for vws in vals.worksheets:
            vws._images, vws._charts = [], []
        self.wb, self.vals = wb, vals
        self._extent.clear()
        self._fcache.clear()
        self._style_cache.clear()
        self._recalc_missing()

    def _apply(self, entry, direction):
        kind = entry["kind"]
        if kind == "snap":
            current = self._snapshot()
            self._restore_snapshot(entry)
            return current
        ws, vws = self._pair(entry["sheet"])
        if kind == "cells":
            idx = 2 if direction == "undo" else 3
            for ch in entry["changes"]:
                _restore(ws, vws, ch[0], ch[1], ch[idx])
            self._invalidate([(ws.title.lower(), ch[0], ch[1], ch[0], ch[1])
                              for ch in entry["changes"]])
        elif kind == "colw":
            cd = ws.column_dimensions[get_column_letter(entry["c"])]
            cd.width = entry["before"] if direction == "undo" else entry["after"]
        self._touch(ws)
        return entry

    def undo(self):
        self._require()
        if not self.undo_stack:
            return {}
        entry = self.undo_stack.pop()
        self.redo_stack.append(self._apply(entry, "undo"))
        self.dirty = True
        return {}

    def redo(self):
        self._require()
        if not self.redo_stack:
            return {}
        entry = self.redo_stack.pop()
        self.undo_stack.append(self._apply(entry, "redo"))
        self.dirty = True
        return {}

    # ------------------------------------------------------------------ zoeken
    def search(self, q, sheet=None, match_case=False, limit=2000):
        self._require()
        if not q:
            return {"matches": []}
        needle = q if match_case else q.lower()
        out = []
        for ws in self.wb.worksheets:
            if sheet and ws.title != sheet:
                continue
            vws = self._vws(ws)
            for (r, c) in sorted(ws._cells.keys()):
                cell = ws._cells[(r, c)]
                if cell.value is None or isinstance(cell, MergedCell):
                    continue
                info = self._cell_info(cell, vws._cells.get((r, c)), [], {})
                if not info:
                    continue
                hay = [info.get("d", ""), info.get("e", "")]
                if not match_case:
                    hay = [h.lower() for h in hay]
                if any(needle in h for h in hay):
                    out.append({"sheet": ws.title, "r": r, "c": c, "d": info.get("d", "")})
                    if len(out) >= limit:
                        return {"matches": out, "more": True}
        return {"matches": out}

    def replace_all(self, q, repl, sheet=None, match_case=False):
        self._require()
        if not q:
            raise UserError("Vul in waar je naar zoekt.")
        pattern = re.compile(re.escape(q), 0 if match_case else re.I)
        total = 0
        for ws in self.wb.worksheets:
            if sheet and ws.title != sheet:
                continue
            batch = []
            for (r, c), cell in list(ws._cells.items()):
                if cell.value is None or isinstance(cell, MergedCell):
                    continue
                v = cell.value
                if isinstance(v, ArrayFormula):
                    continue
                if cell.data_type == "f":
                    text = F.strip_prefixes(v)
                else:
                    text = F.edit_text(v, cell.number_format)
                if pattern.search(text):
                    batch.append({"r": r, "c": c, "v": pattern.sub(lambda m: repl, text)})
            if batch:
                total += self.set_cells(ws.title, batch)["changed"]
        return {"count": total}

    # ------------------------------------------------------------------ opslaan
    def set_active(self, sheet):
        if not sheet:
            return
        for ws in self.wb.worksheets:
            if ws.title == sheet:
                self.wb.active = ws
                for other in self.wb.worksheets:
                    for view in other.views.sheetView:
                        view.tabSelected = other is ws
                return

    def to_bytes(self, fmt="xlsx", sheet=None):
        self._require()
        if fmt == "csv":
            return self._csv_bytes(sheet)
        try:
            self.wb.calculation.fullCalcOnLoad = True
        except Exception:
            pass
        buf = io.BytesIO()
        self._prepare_images()
        self.wb.save(buf)
        return buf.getvalue()

    def _csv_bytes(self, sheet=None, delim=None, encoding=None):
        ws, vws = self._pair(sheet or self.wb.active.title)
        delim = delim or (";" if self.kind != "csv" else self.csv_delim)
        nr, nc = self.extent(ws)
        out = io.StringIO()
        w = csv.writer(out, delimiter=delim, lineterminator="\r\n")
        for r in range(1, nr + 1):
            row = []
            for c in range(1, nc + 1):
                cell = ws._cells.get((r, c))
                v = None if cell is None or isinstance(cell, MergedCell) else cell.value
                if cell is not None and cell.data_type == "f":
                    vc = vws._cells.get((r, c))
                    v = vc.value if vc is not None else None
                if v is None:
                    row.append("")
                elif isinstance(v, bool):
                    row.append(F.bool_text(v))
                elif isinstance(v, (int, float)):
                    s = F.general_number(v) if not isinstance(v, int) else str(v)
                    row.append(s if delim == ";" else s.replace(",", "."))
                elif isinstance(v, (dt.datetime, dt.date, dt.time)):
                    row.append(F.edit_text(v, None))
                else:
                    row.append(str(v))
            w.writerow(row)
        return out.getvalue().encode(encoding or ("utf-8-sig" if self.kind != "csv" else self.csv_encoding))

    def save(self, path=None, sheet=None):
        self._require()
        path = path or self.path
        if not path:
            raise UserError("Kies eerst waar je het bestand wilt opslaan.")
        self.set_active(sheet)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            data = self._csv_bytes(sheet)
        else:
            if ext == ".xlsx" and self.kind == "xlsm":
                raise UserError("Dit bestand bevat macro's. Sla het op als .xlsm.")
            data = self.to_bytes("xlsx")
        if os.path.exists(path) and path not in self.backed_up:
            backup_file(path)
            self.backed_up.add(path)
        folder = os.path.dirname(path) or "."
        tmp = os.path.join(folder, ".~%s.rekenblad-tmp" % os.path.basename(path))
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        if self.path != path:
            self.path = path
            self.filename = os.path.basename(path)
            if ext == ".csv":
                self.kind = "csv"
            elif ext in (".xlsx", ".xlsm"):
                self.kind = "xlsm" if ext == ".xlsm" else "xlsx"
        self.dirty = False
        remember_recent(path)
        return {"path": path}


# ---------------------------------------------------------------------------
# Hulpfuncties

def _col(key):
    try:
        return column_index_from_string(key)
    except (ValueError, TypeError):
        return None


def _same(a, b):
    return type(a) is type(b) and a == b


def _snap(ws, vws, r, c):
    cell = ws._cells.get((r, c))
    if cell is None:
        return None
    v = cell.value
    if isinstance(v, ArrayFormula):
        v = ArrayFormula(v.ref, v.text)
    vc = vws._cells.get((r, c))
    style = tuple(cell._style) if cell._style is not None else None
    return (v, style, vc.value if vc is not None else None)


def _restore(ws, vws, r, c, snap):
    if snap is None:
        ws._cells.pop((r, c), None)
        vws._cells.pop((r, c), None)
        return
    value, style, cached = snap
    cell = ws.cell(r, c)
    if isinstance(cell, MergedCell):
        return
    cell.value = value
    cell._style = StyleArray(style) if style is not None else None
    vws.cell(r, c).value = cached


def _tint(hex6, tint):
    if not tint:
        return hex6
    r, g, b = (int(hex6[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), s)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _join_nl(items):
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " en " + items[-1]


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
