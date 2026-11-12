"""Weergave van celwaarden (Nederlandse notatie) en het omzetten van invoer naar waarden."""
from __future__ import annotations

import datetime as dt
import re

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.styles.numbers import is_date_format
from openpyxl.utils.datetime import from_excel

from refs import parse_area, render_area, split_sheet

ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A",
          "#GETTING_DATA", "#SPILL!", "#CALC!"}

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
          "augustus", "september", "oktober", "november", "december"]
MONTHS_S = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
DAYS_S = ["ma", "di", "wo", "do", "vr", "za", "zo"]

FMT_DATE = "dd-mm-yyyy"
FMT_DATETIME = "dd-mm-yyyy hh:mm"
FMT_EURO = '"€ "#,##0.00'


def bool_text(v):
    return "WAAR" if v else "ONWAAR"


# ---------------------------------------------------------------------------
# Getalnotaties

def _split_sections(fmt):
    out, cur, q, i = [], "", False, 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            q = not q
        elif ch == "\\" and not q and i + 1 < len(fmt):
            cur += fmt[i:i + 2]
            i += 2
            continue
        elif ch == ";" and not q:
            out.append(cur)
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    out.append(cur)
    return out


def _analyse(sec):
    """Splits een notatie in (voorvoegsel, getalpatroon, achtervoegsel, procent)."""
    prefix, spec, suffix = "", "", ""
    seen_digit = False
    pending = ""  # letterlijke tekst na een cijferteken; hoort bij achtervoegsel als er geen cijfers meer volgen
    pct = False
    i = 0
    while i < len(sec):
        ch = sec[i]
        lit = None
        if ch == '"':
            j = sec.find('"', i + 1)
            j = len(sec) if j < 0 else j
            lit = sec[i + 1:j]
            i = j + 1
        elif ch == "\\" and i + 1 < len(sec):
            lit = sec[i + 1]
            i += 2
        elif ch in "_":
            lit = " "
            i += 2
        elif ch == "*":
            i += 2
            continue
        elif ch == "[":
            j = sec.find("]", i)
            j = len(sec) if j < 0 else j
            inner = sec[i + 1:j]
            if inner.startswith("$"):
                lit = inner[1:].split("-")[0]
            i = j + 1
        elif ch in "0#?":
            if pending:
                spec += pending
                pending = ""
            spec += ch
            seen_digit = True
            i += 1
            continue
        elif ch in ".," and seen_digit and i + 1 < len(sec) and sec[i + 1] in "0#?,.":
            spec += ch
            i += 1
            continue
        elif ch in ".," and not seen_digit and i + 1 < len(sec) and sec[i + 1] in "0#?":
            spec += ch
            seen_digit = True
            i += 1
            continue
        elif ch in "Ee" and seen_digit and i + 1 < len(sec) and sec[i + 1] in "+-":
            spec += "E"
            i += 2
            continue
        else:
            if ch == "%":
                pct = True
            lit = ch
            i += 1
        if lit is None:
            continue
        if seen_digit:
            pending += lit
        else:
            prefix += lit
    suffix = pending
    return prefix, spec, suffix, pct


def general_number(v):
    if isinstance(v, int):
        return str(v)
    if v != v or v in (float("inf"), float("-inf")):
        return "#NUM!"
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    s = "%.10g" % v
    if "e" in s:
        mant, exp = s.split("e")
        s = "%sE%s%02d" % (mant, exp[0], int(exp[1:]))
    return s.replace(".", ",")


def _group(int_digits):
    out = ""
    while len(int_digits) > 3:
        out = "." + int_digits[-3:] + out
        int_digits = int_digits[:-3]
    return int_digits + out


def fmt_number(v, fmt):
    if not fmt or fmt == "General":
        return general_number(v)
    try:
        secs = _split_sections(fmt)
        sec = secs[0]
        explicit_neg = False
        if v < 0 and len(secs) >= 2 and secs[1].strip():
            sec, v, explicit_neg = secs[1], -v, True
        elif v == 0 and len(secs) >= 3 and secs[2].strip():
            sec = secs[2]
        if sec.strip().lower() == "general":
            return general_number(v)
        prefix, spec, suffix, pct = _analyse(sec)
        if not spec:
            return (prefix + suffix).strip() or general_number(v)
        if pct:
            v = v * 100
        int_spec, _, dec_spec = spec.partition(".")
        if "E" in spec:
            digits = len(re.findall(r"[0#?]", dec_spec.split("E")[0]))
            s = ("%." + str(digits) + "E") % v
            mant, exp = s.split("E")
            return prefix + mant.replace(".", ",") + "E" + exp[0] + exp[1:].zfill(2) + suffix
        dmin = dec_spec.count("0")
        dmax = len(re.findall(r"[0#?]", dec_spec))
        grouping = "," in int_spec
        rounded = round(abs(v), dmax)
        s = ("%." + str(dmax) + "f") % rounded
        ip, _, fp = s.partition(".")
        if dmax > dmin:
            fp = fp.rstrip("0")
            if len(fp) < dmin:
                fp = fp.ljust(dmin, "0")
        if int_spec.replace(",", "").count("0") == 0 and ip == "0" and fp:
            ip = ""
        if grouping:
            ip = _group(ip)
        text = ip + ("," + fp if fp else "")
        sign = "-" if v < 0 and not explicit_neg and float(rounded) != 0 else ""
        return sign + prefix + text + suffix
    except Exception:
        return general_number(v)


# ---------------------------------------------------------------------------
# Datum en tijd

_DATE_TOKENS = re.compile(
    r'(yyyy|yy|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|am/pm|a/p|"[^"]*"|\\.|\[[^\]]*\]|.)',
    re.I)


def fmt_date(v, fmt):
    if isinstance(v, dt.timedelta):
        total = int(v.total_seconds())
        h, rem = divmod(abs(total), 3600)
        m, s = divmod(rem, 60)
        return "%s%d:%02d:%02d" % ("-" if total < 0 else "", h, m, s)
    clean = fmt or ""
    if not clean or clean == "General" or not is_date_format(clean):
        if isinstance(v, dt.datetime):
            if v.time() == dt.time(0):
                return v.strftime("%d-%m-%Y")
            return v.strftime("%d-%m-%Y %H:%M")
        if isinstance(v, dt.date):
            return v.strftime("%d-%m-%Y")
        if isinstance(v, dt.time):
            return v.strftime("%H:%M")
    clean = _split_sections(clean)[0]
    toks = _DATE_TOKENS.findall(clean)
    kinds = []
    for t in toks:
        tl = t.lower()
        if tl in ("yyyy", "yy", "mmmmm", "mmmm", "mmm", "mm", "m", "dddd", "ddd", "dd", "d",
                  "hh", "h", "ss", "s", "am/pm", "a/p"):
            kinds.append(tl)
        else:
            kinds.append(None)
    # m/mm na uren of voor seconden is minuten
    for i, k in enumerate(kinds):
        if k in ("m", "mm"):
            prev = next((kinds[j] for j in range(i - 1, -1, -1) if kinds[j]), None)
            nxt = next((kinds[j] for j in range(i + 1, len(kinds)) if kinds[j]), None)
            if prev in ("h", "hh") or nxt in ("s", "ss"):
                kinds[i] = "min" + k
    ampm = any(k in ("am/pm", "a/p") for k in kinds)
    if isinstance(v, dt.datetime):
        d, t = v.date(), v.time()
    elif isinstance(v, dt.date):
        d, t = v, dt.time(0)
    else:
        d, t = None, v
    out = []
    for tok, k in zip(toks, kinds):
        if k is None:
            if tok.startswith('"'):
                out.append(tok[1:-1])
            elif tok.startswith("\\"):
                out.append(tok[1:])
            elif tok.startswith("["):
                inner = tok[1:-1].lower()
                if inner in ("h", "hh") and t is not None:
                    out.append(str(t.hour))
            else:
                out.append(tok)
            continue
        if k in ("yyyy", "yy", "mmmmm", "mmmm", "mmm", "mm", "m", "dddd", "ddd", "dd", "d") and d is None:
            continue
        if k == "yyyy":
            out.append("%04d" % d.year)
        elif k == "yy":
            out.append("%02d" % (d.year % 100))
        elif k == "mmmmm":
            out.append(MONTHS[d.month - 1][0])
        elif k == "mmmm":
            out.append(MONTHS[d.month - 1])
        elif k == "mmm":
            out.append(MONTHS_S[d.month - 1])
        elif k == "mm":
            out.append("%02d" % d.month)
        elif k == "m":
            out.append(str(d.month))
        elif k == "dddd":
            out.append(DAYS[d.weekday()])
        elif k == "ddd":
            out.append(DAYS_S[d.weekday()])
        elif k == "dd":
            out.append("%02d" % d.day)
        elif k == "d":
            out.append(str(d.day))
        elif k in ("hh", "h"):
            h = t.hour
            if ampm:
                h = h % 12 or 12
            out.append("%02d" % h if k == "hh" else str(h))
        elif k == "minmm":
            out.append("%02d" % t.minute)
        elif k == "minm":
            out.append(str(t.minute))
        elif k == "ss":
            out.append("%02d" % t.second)
        elif k == "s":
            out.append(str(t.second))
        elif k == "am/pm":
            out.append("AM" if t.hour < 12 else "PM")
        elif k == "a/p":
            out.append("A" if t.hour < 12 else "P")
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# Weergave en bewerktekst

def display(v, fmt, is_error=False):
    """-> (tekst, soort). Soort: n getal, s tekst, b waar/onwaar, d datum, e fout."""
    if v is None:
        return "", "s"
    if isinstance(v, bool):
        return bool_text(v), "b"
    if isinstance(v, (int, float)):
        if fmt and fmt != "General" and is_date_format(fmt):
            try:
                return fmt_date(from_excel(v), fmt), "d"
            except Exception:
                pass
        return fmt_number(v, fmt), "n"
    if isinstance(v, (dt.datetime, dt.date, dt.time, dt.timedelta)):
        return fmt_date(v, fmt), "d"
    s = str(v)
    if is_error or s in ERRORS:
        return s, "e"
    return s, "s"


def _num_edit(v):
    s = "%.15g" % v
    if "e" in s:
        return s
    return s.replace(".", ",")


def edit_text(v, fmt):
    if v is None:
        return ""
    if isinstance(v, bool):
        return bool_text(v)
    if isinstance(v, (int, float)):
        if fmt and fmt != "General" and is_date_format(fmt):
            try:
                return edit_text(from_excel(v), fmt)
            except Exception:
                pass
        if fmt and "%" in fmt and isinstance(v, (int, float)):
            return _num_edit(v * 100) + "%"
        return str(v) if isinstance(v, int) else _num_edit(v)
    if isinstance(v, dt.datetime):
        if v.time() == dt.time(0):
            return v.strftime("%d-%m-%Y")
        return v.strftime("%d-%m-%Y %H:%M:%S" if v.second else "%d-%m-%Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d-%m-%Y")
    if isinstance(v, dt.time):
        return v.strftime("%H:%M:%S" if v.second else "%H:%M")
    if isinstance(v, dt.timedelta):
        return fmt_date(v, fmt)
    s = str(v)
    if s.startswith("="):
        return "'" + s
    return s


def strip_prefixes(formula):
    return re.sub(r"_xlfn\.(_xlws\.)?", "", formula)


# ---------------------------------------------------------------------------
# Invoer omzetten

_NUM_EN = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_NUM_NL = re.compile(r"^[+-]?\d*,\d+$")
_NUM_NL_GROUP = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+(,\d+)?$")
_NUM_EN_GROUP = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_DATE_NL = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def parse_number(s):
    t = s.strip().replace(" ", "").replace(" ", "")
    if not t:
        return None
    try:
        if _NUM_NL_GROUP.match(t) and ("," in t or t.count(".") >= 2):
            return _num(t.replace(".", "").replace(",", "."))
        if _NUM_NL.match(t):
            return _num(t.replace(",", "."))
        if _NUM_EN_GROUP.match(t):
            return _num(t.replace(",", ""))
        if _NUM_EN.match(t):
            return _num(t)
    except ValueError:
        return None
    return None


def _num(t):
    if re.match(r"^[+-]?\d+$", t):
        i = int(t)
        return i if abs(i) < 2 ** 53 else float(i)
    return float(t)


def fmt_category(fmt):
    if not fmt or fmt == "General":
        return "general"
    if is_date_format(fmt):
        return "date"
    if "%" in fmt:
        return "percent"
    if "€" in fmt or "$" in fmt or "£" in fmt:
        return "currency"
    return "number"


def parse_input(raw, allow_formula=True):
    """Tekst van de gebruiker -> (waarde, voorgestelde getalnotatie of None)."""
    if raw is None:
        return None, None
    s = ILLEGAL_CHARACTERS_RE.sub("", str(raw))
    if s.strip() == "":
        return None, None
    if s.startswith("'"):
        return s[1:], None
    if s.startswith("=") and len(s) > 1 and allow_formula:
        return normalize_formula(s), None
    t = s.strip()
    up = t.upper()
    if up in ("WAAR", "TRUE"):
        return True, None
    if up in ("ONWAAR", "FALSE"):
        return False, None
    if re.match(r"^0\d+$", t):
        return s, None  # telefoonnummers, postcodes: voorloopnul behouden
    n = parse_number(t)
    if n is not None:
        return n, None
    if t.endswith("%"):
        n = parse_number(t[:-1])
        if n is not None:
            decimals = len(re.split(r"[.,]", t[:-1])[1]) if re.search(r"[.,]", t[:-1]) else 0
            return n / 100, ("0%" if decimals == 0 else "0." + "0" * min(decimals, 4) + "%")
    for sym in ("€", "$", "£"):
        if t.startswith(sym) or t.endswith(sym) or t.startswith("-" + sym):
            inner = t.replace(sym, "").strip()
            n = parse_number(inner)
            if n is not None:
                fmt = FMT_EURO if sym == "€" else '"%s"#,##0.00' % sym
                return n, fmt
    m = _DATE_NL.match(t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        val = _mk_date(y, mo, d, m.group(4), m.group(5), m.group(6))
        if val is not None:
            return val, (FMT_DATETIME if m.group(4) else FMT_DATE)
    m = _DATE_ISO.match(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        val = _mk_date(y, mo, d, m.group(4), m.group(5), m.group(6))
        if val is not None:
            return val, (FMT_DATETIME if m.group(4) else FMT_DATE)
    m = _TIME.match(t)
    if m:
        try:
            sec = int(m.group(3) or 0)
            return dt.time(int(m.group(1)), int(m.group(2)), sec), ("hh:mm:ss" if m.group(3) else "hh:mm")
        except ValueError:
            pass
    if len(s) > 32767:
        s = s[:32767]
    return s, None


def _mk_date(y, mo, d, hh, mm, ss):
    try:
        if hh is None:
            return dt.datetime(y, mo, d)
        return dt.datetime(y, mo, d, int(hh), int(mm), int(ss or 0))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Formules: Nederlandse invoer omzetten naar wat Excel opslaat

NL_FUNCS = {
    "SOM": "SUM", "GEMIDDELDE": "AVERAGE", "AANTAL": "COUNT", "AANTALARG": "COUNTA",
    "AANTAL.LEGE.CELLEN": "COUNTBLANK", "ALS": "IF", "ALS.FOUT": "IFERROR", "ALS.NB": "IFNA",
    "EN": "AND", "OF": "OR", "NIET": "NOT", "AFRONDEN": "ROUND",
    "AFRONDEN.NAAR.BOVEN": "ROUNDUP", "AFRONDEN.NAAR.BENEDEN": "ROUNDDOWN", "INTEGER": "INT",
    "SOM.ALS": "SUMIF", "SOMMEN.ALS": "SUMIFS", "AANTAL.ALS": "COUNTIF",
    "AANTALLEN.ALS": "COUNTIFS", "GEMIDDELDE.ALS": "AVERAGEIF", "GEMIDDELDEN.ALS": "AVERAGEIFS",
    "VERT.ZOEKEN": "VLOOKUP", "HORIZ.ZOEKEN": "HLOOKUP", "X.ZOEKEN": "XLOOKUP",
    "VERGELIJKEN": "MATCH", "X.VERGELIJKEN": "XMATCH", "ZOEKEN": "LOOKUP",
    "VANDAAG": "TODAY", "NU": "NOW", "DATUM": "DATE", "JAAR": "YEAR", "MAAND": "MONTH",
    "DAG": "DAY", "WEEKDAG": "WEEKDAY", "WEEKNUMMER": "WEEKNUM", "DATUMVERSCHIL": "DATEDIF",
    "NETTO.WERKDAGEN": "NETWORKDAYS", "WERKDAG": "WORKDAY", "LAATSTE.DAG": "EOMONTH",
    "ZELFDE.DAG": "EDATE", "TEKST": "TEXT", "TEKST.SAMENVOEGEN": "CONCATENATE",
    "TEKST.COMBINEREN": "TEXTJOIN", "SAMENVOEGEN": "CONCAT", "LINKS": "LEFT", "RECHTS": "RIGHT",
    "DEEL": "MID", "LENGTE": "LEN", "SPATIES.WISSEN": "TRIM", "HOOFDLETTERS": "UPPER",
    "KLEINE.LETTERS": "LOWER", "BEGINLETTERS": "PROPER", "WAARDE": "VALUE",
    "VIND.ALLES": "FIND", "VIND.SPEC": "SEARCH", "SUBSTITUEREN": "SUBSTITUTE",
    "VERVANGEN": "REPLACE", "SOMPRODUCT": "SUMPRODUCT", "MEDIAAN": "MEDIAN", "REST": "MOD",
    "MACHT": "POWER", "WORTEL": "SQRT", "UNIEK": "UNIQUE", "SORTEREN": "SORT",
    "ALS.VOORWAARDEN": "IFS", "SCHAKELEN": "SWITCH", "MAX.ALS.VOORWAARDEN": "MAXIFS",
    "MIN.ALS.VOORWAARDEN": "MINIFS", "VERSCHUIVING": "OFFSET", "RIJ": "ROW", "KOLOM": "COLUMN",
    "RIJEN": "ROWS", "KOLOMMEN": "COLUMNS", "ISLEEG": "ISBLANK", "ISGETAL": "ISNUMBER",
    "ISTEKST": "ISTEXT", "ISFOUT": "ISERROR", "NB": "NA", "WAAR": "TRUE", "ONWAAR": "FALSE",
    "KIEZEN": "CHOOSE", "AFRONDEN.N.VEELVOUD": "MROUND", "GROOTSTE": "LARGE",
    "KLEINSTE": "SMALL", "RANG": "RANK",
}

XLFN = {"XLOOKUP", "XMATCH", "UNIQUE", "SEQUENCE", "LET", "LAMBDA", "TEXTJOIN", "CONCAT",
        "IFS", "SWITCH", "MAXIFS", "MINIFS", "IFNA", "STDEV.S", "STDEV.P", "VAR.S", "VAR.P",
        "DAYS", "ISOWEEKNUM", "RANDARRAY", "TEXTBEFORE", "TEXTAFTER", "TEXTSPLIT", "VSTACK",
        "HSTACK", "TAKE", "DROP", "CHOOSECOLS", "CHOOSEROWS", "TOCOL", "TOROW", "SORTBY",
        "FORECAST.LINEAR", "CEILING.MATH", "FLOOR.MATH", "AGGREGATE", "PERCENTILE.INC",
        "PERCENTILE.EXC", "QUARTILE.INC", "RANK.EQ", "RANK.AVG", "XOR", "NORM.DIST"}
XLWS = {"FILTER", "SORT"}


def _nl_separators(body):
    """';' als scheidingsteken en ',' als decimaalteken (NL-Excel) omzetten."""
    out = []
    in_str = False
    has_semicolon = False
    for ch in body:
        if ch == '"':
            in_str = not in_str
        elif ch == ";" and not in_str:
            has_semicolon = True
            break
    in_str = False
    depth = 0
    for i, ch in enumerate(body):
        if ch == '"':
            in_str = not in_str
        if in_str:
            out.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if has_semicolon:
            if ch == ",":
                ch = "."
            elif ch == ";":
                ch = ","
        elif ch == "," and depth == 0 and 0 < i < len(body) - 1 \
                and body[i - 1].isdigit() and body[i + 1].isdigit():
            ch = "."
        out.append(ch)
    return "".join(out)


class FormulaError(ValueError):
    pass


def normalize_formula(src):
    body = _nl_separators(src[1:])
    if body.count('"') % 2:
        raise FormulaError("Formule heeft een aanhalingsteken te weinig.")
    try:
        items = Tokenizer("=" + body).items
    except Exception as exc:
        raise FormulaError("Formule kan niet gelezen worden: %s" % exc)
    depth = 0
    parts = []
    for t in items:
        v = t.value
        if t.subtype == Token.OPEN:
            depth += 1
        elif t.subtype == Token.CLOSE:
            depth -= 1
            if depth < 0:
                raise FormulaError("Formule heeft een haakje ')' te veel.")
        if t.type == Token.FUNC and t.subtype == Token.OPEN:
            name = v[:-1].upper()
            if not name.startswith("_XLFN.") and not name.startswith("_XLWS."):
                name = NL_FUNCS.get(name, name)
                if name in XLWS:
                    name = "_xlfn._xlws." + name
                elif name in XLFN:
                    name = "_xlfn." + name
            else:
                name = name.replace("_XLFN.", "_xlfn.").replace("_XLWS.", "_xlws.")
            v = name + "("
        elif t.type == Token.OPERAND and t.subtype == Token.RANGE:
            up = v.upper()
            if up in ("WAAR", "ONWAAR"):
                v = "TRUE" if up == "WAAR" else "FALSE"
            else:
                _name, prefix, rest = split_sheet(v)
                area = parse_area(rest)
                if area:
                    v = prefix + render_area(area)
        elif t.type == Token.OPERAND and t.subtype == Token.LOGICAL:
            v = v.upper()
        parts.append(v)
    if depth != 0:
        raise FormulaError("Formule mist een sluithaakje ')'.")
    return "=" + "".join(parts)
