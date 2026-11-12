"""Celverwijzingen in formules lezen, verschuiven en herschrijven.

Excel past formules aan als je rijen of kolommen invoegt of verwijdert,
een blad hernoemt of verwijdert. openpyxl doet dat niet, dus dat regelen we hier.
"""
from __future__ import annotations

import re

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter

MAX_ROW = 1048576
MAX_COL = 16384

_CELL = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)([0-9]+)$")
_COL = re.compile(r"^(\$?)([A-Za-z]{1,3})$")
_ROW = re.compile(r"^(\$?)([0-9]+)$")
_PLAIN_SHEET = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def split_sheet(text):
    """"'Blad 1'!A1:B2" -> ("Blad 1", "'Blad 1'!", "A1:B2")."""
    if "!" not in text:
        return None, "", text
    i = text.rfind("!")
    raw = text[:i]
    name = raw
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        name = raw[1:-1].replace("''", "'")
    return name, text[: i + 1], text[i + 1:]


def quote_sheet(name):
    if _PLAIN_SHEET.match(name) and not _CELL.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _col_index(letters):
    try:
        col = column_index_from_string(letters.upper())
    except ValueError:
        return None
    return col if 1 <= col <= MAX_COL else None


def _endpoint(p):
    """Eén kant van een bereik: [soort, kolom, rij, $kolom, $rij]."""
    m = _CELL.match(p)
    if m:
        col, row = _col_index(m.group(2)), int(m.group(4))
        if col is None or not 1 <= row <= MAX_ROW:
            return None
        return ["cell", col, row, m.group(1), m.group(3)]
    m = _COL.match(p)
    if m:
        col = _col_index(m.group(2))
        return None if col is None else ["col", col, None, m.group(1), ""]
    m = _ROW.match(p)
    if m:
        row = int(m.group(2))
        return ["row", None, row, "", m.group(1)] if 1 <= row <= MAX_ROW else None
    return None


def parse_area(text):
    """'A1', '$A$1:B5', 'A:C' of '3:7' -> lijst met 1 of 2 eindpunten, anders None."""
    parts = text.split(":")
    if len(parts) == 1:
        e = _endpoint(parts[0])
        return [e] if e and e[0] == "cell" else None
    if len(parts) == 2:
        a, b = _endpoint(parts[0]), _endpoint(parts[1])
        if a and b and a[0] == b[0]:
            return [a, b]
    return None


def render_endpoint(e):
    kind, col, row, ac, ar = e
    if kind == "cell":
        return "%s%s%s%d" % (ac, get_column_letter(col), ar, row)
    if kind == "col":
        return ac + get_column_letter(col)
    return "%s%d" % (ar, row)


def render_area(area):
    return ":".join(render_endpoint(e) for e in area)


def area_bounds(area):
    """-> (r1, c1, r2, c2), genormaliseerd."""
    a, b = area[0], area[-1]
    if a[0] == "col":
        r1, r2, c1, c2 = 1, MAX_ROW, a[1], b[1]
    elif a[0] == "row":
        r1, r2, c1, c2 = a[2], b[2], 1, MAX_COL
    else:
        r1, r2, c1, c2 = a[2], b[2], a[1], b[1]
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def shift_interval(lo, hi, at, n):
    """Interval [lo, hi] na invoegen (n > 0) of verwijderen (n < 0) vanaf positie `at`.

    Geeft None als het interval helemaal verdwijnt.
    """
    if n > 0:
        if lo >= at:
            lo += n
        if hi >= at:
            hi += n
        return lo, hi
    k = -n
    d1, d2 = at, at + k - 1
    if hi < d1:
        return lo, hi
    if lo > d2:
        return lo - k, hi - k
    nlo = lo if lo < d1 else d1
    nhi = hi - k if hi > d2 else d1 - 1
    if nhi < nlo:
        return None
    return nlo, nhi


def shift_area(area, axis, at, n):
    """Verschuif een bereik. axis is 'row' of 'col'. None = #VERW!."""
    idx = 2 if axis == "row" else 1
    limit = MAX_ROW if axis == "row" else MAX_COL
    eps = [list(e) for e in area]
    if any(e[idx] is None for e in eps):
        return eps  # hele kolom bij rij-wijziging (of andersom): blijft gelijk
    a, b = eps[0], eps[-1]
    lo, hi = min(a[idx], b[idx]), max(a[idx], b[idx])
    res = shift_interval(lo, hi, at, n)
    if res is None or res[0] > limit:
        return None
    nlo, nhi = res[0], min(res[1], limit)
    if len(eps) == 1:
        a[idx] = nlo
    elif a[idx] <= b[idx]:
        a[idx], b[idx] = nlo, nhi
    else:
        a[idx], b[idx] = nhi, nlo
    return eps


def shift_range_text(text, axis, at, n):
    """'A1:C5' (zonder blad) verschuiven. None als het bereik verdwijnt."""
    area = parse_area(text.replace("$", ""))
    if area is None:
        return text
    new = shift_area(area, axis, at, n)
    return None if new is None else render_area(new)


def shift_multi_text(text, axis, at, n):
    """'A1:A5 C1:C5' verschuiven; lege string als niets overblijft."""
    out = []
    for part in str(text).split():
        new = shift_range_text(part, axis, at, n)
        if new:
            out.append(new)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Formules herschrijven

def map_range_tokens(formula, fn):
    """Roep fn(tekst) aan voor elke bereikverwijzing; fn geeft nieuwe tekst of None."""
    try:
        items = Tokenizer(formula).items
    except Exception:
        return formula
    changed = False
    parts = []
    for t in items:
        v = t.value
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            nv = fn(v)
            if nv is not None and nv != v:
                v, changed = nv, True
        parts.append(v)
    return "=" + "".join(parts) if changed else formula


def shift_fn(home, target, axis, at, n):
    tl = target.lower()

    def fn(text):
        name, prefix, rest = split_sheet(text)
        eff = name if name is not None else home
        if eff is None or eff.lower() != tl:
            return None
        area = parse_area(rest)
        if area is None:
            return None
        new = shift_area(area, axis, at, n)
        return prefix + ("#REF!" if new is None else render_area(new))

    return fn


def rename_fn(old, new):
    ol = old.lower()

    def fn(text):
        name, _prefix, rest = split_sheet(text)
        if name is None or name.lower() != ol:
            return None
        return quote_sheet(new) + "!" + rest

    return fn


def delete_sheet_fn(deleted):
    dl = deleted.lower()

    def fn(text):
        name, _prefix, _rest = split_sheet(text)
        if name is None or name.lower() != dl:
            return None
        return "#REF!"

    return fn


def formula_areas(formula, home, names):
    """Alle bereiken waar een formule naar kijkt: [(blad_lower, r1, c1, r2, c2)]."""
    out = []
    try:
        items = Tokenizer(formula).items
    except Exception:
        return out
    for t in items:
        if t.type != Token.OPERAND or t.subtype != Token.RANGE:
            continue
        name, _prefix, rest = split_sheet(t.value)
        area = parse_area(rest)
        if area is None:
            out.extend(names.get(t.value.lower(), ()))
            continue
        eff = name if name is not None else home
        out.append((eff.lower(),) + area_bounds(area))
    return out
