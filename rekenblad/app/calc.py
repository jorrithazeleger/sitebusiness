"""Een kleine rekenmachine voor Excel-formules.

openpyxl berekent geen formules. Zonder dit zou je na een wijziging (of na
opslaan en heropenen) formules zien in plaats van uitkomsten. Hier rekenen we
de meest gebruikte functies zelf uit. Kent deze module een functie niet, dan
blijft de cel 'onberekend' en rekent Excel of Numbers hem uit bij openen.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from decimal import ROUND_HALF_UP, Decimal

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils.datetime import from_excel, to_excel

import formats as F
import refs as R


class Unsupported(Exception):
    """Deze formule kunnen we niet zelf uitrekenen."""


class Deep(Unsupported):
    """Te diep genest om nu uit te rekenen; later opnieuw proberen."""


class XLError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Range:
    __slots__ = ("ev", "sheet", "r1", "c1", "r2", "c2")

    def __init__(self, ev, sheet, r1, c1, r2, c2):
        self.ev, self.sheet = ev, sheet
        self.r1, self.c1, self.r2, self.c2 = r1, c1, r2, c2

    def bounded(self):
        """Hele kolommen (A:A) en rijen (1:1) inperken tot het gevulde deel van het blad."""
        r2, c2 = self.r2, self.c2
        if r2 == R.MAX_ROW or c2 == R.MAX_COL:
            mr, mc = self.ev.extent(self.sheet)
            if r2 == R.MAX_ROW:
                r2 = max(mr, self.r1)
            if c2 == R.MAX_COL:
                c2 = max(mc, self.c1)
        return self.r1, self.c1, r2, c2

    @property
    def shape(self):
        r1, c1, r2, c2 = self.bounded()
        return r2 - r1 + 1, c2 - c1 + 1

    def cell(self, i, j):
        """0-gebaseerde positie binnen het bereik."""
        return self.ev.value(self.sheet, self.r1 + i, self.c1 + j)

    def values(self):
        r1, c1, r2, c2 = self.bounded()
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                yield self.ev.value(self.sheet, r, c)

    def rows(self):
        r1, c1, r2, c2 = self.bounded()
        return [[self.ev.value(self.sheet, r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)]

    def is_single(self):
        return self.r1 == self.r2 and self.c1 == self.c2


# ---------------------------------------------------------------------------
# Ontleden

def parse(formula):
    toks = [t for t in Tokenizer(formula).items if t.type != Token.WSPACE]
    p = _Parser(toks)
    node = p.expr(0)
    if p.i != len(toks):
        raise Unsupported("onverwacht teken")
    return node


_INFIX = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3,
          "*": 4, "/": 4, "^": 5}


class _Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def expr(self, min_prec):
        left = self.unary()
        while True:
            t = self.peek()
            if t is None or t.type != Token.OP_IN or t.value not in _INFIX:
                break
            prec = _INFIX[t.value]
            if prec < min_prec:
                break
            self.take()
            right = self.expr(prec + 1 if t.value != "^" else prec + 1)
            left = ("bin", t.value, left, right)
        return left

    def unary(self):
        t = self.peek()
        if t is not None and t.type == Token.OP_PRE:
            self.take()
            inner = self.unary()
            return ("neg", inner) if t.value == "-" else inner
        node = self.primary()
        while True:
            t = self.peek()
            if t is not None and t.type == Token.OP_POST and t.value == "%":
                self.take()
                node = ("pct", node)
            else:
                break
        return node

    def primary(self):
        t = self.take()
        if t is None:
            raise Unsupported("formule eindigt te vroeg")
        if t.type == Token.OPERAND:
            if t.subtype == Token.NUMBER:
                return ("lit", float(t.value) if re.search(r"[.eE]", t.value) else int(t.value))
            if t.subtype == Token.TEXT:
                return ("lit", t.value[1:-1].replace('""', '"'))
            if t.subtype == Token.LOGICAL:
                return ("lit", t.value.upper() == "TRUE")
            if t.subtype == Token.ERROR:
                return ("err", t.value)
            if t.subtype == Token.RANGE:
                return ("ref", t.value)
            raise Unsupported(t.value)
        if t.type == Token.PAREN and t.subtype == Token.OPEN:
            node = self.expr(0)
            close = self.take()
            if close is None or close.type != Token.PAREN:
                raise Unsupported("haakje")
            return node
        if t.type == Token.FUNC and t.subtype == Token.OPEN:
            name = t.value[:-1].upper()
            for pre in ("_XLFN._XLWS.", "_XLFN.", "_XLWS."):
                if name.startswith(pre):
                    name = name[len(pre):]
            args = []
            nxt = self.peek()
            if nxt is not None and nxt.type == Token.FUNC and nxt.subtype == Token.CLOSE:
                self.take()
                return ("fn", name, args)
            while True:
                nxt = self.peek()
                if nxt is not None and ((nxt.type == Token.SEP and nxt.subtype == Token.ARG)
                                        or (nxt.type == Token.FUNC and nxt.subtype == Token.CLOSE)):
                    args.append(("missing",))
                else:
                    args.append(self.expr(0))
                t2 = self.take()
                if t2 is None:
                    raise Unsupported("functie niet afgesloten")
                if t2.type == Token.SEP and t2.subtype == Token.ARG:
                    continue
                if t2.type == Token.FUNC and t2.subtype == Token.CLOSE:
                    break
                raise Unsupported(t2.value)
            return ("fn", name, args)
        raise Unsupported(t.value)


# ---------------------------------------------------------------------------
# Omzetten tussen typen

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def to_serial(v):
    if isinstance(v, dt.datetime):
        return to_excel(v)
    if isinstance(v, dt.date):
        return to_excel(dt.datetime(v.year, v.month, v.day))
    if isinstance(v, dt.time):
        return (v.hour * 3600 + v.minute * 60 + v.second) / 86400.0
    if isinstance(v, dt.timedelta):
        return v.total_seconds() / 86400.0
    return v


def num(v):
    v = to_serial(v)
    if isinstance(v, bool):
        return 1 if v else 0
    if v is None or v == "":
        return 0
    if is_num(v):
        return v
    if isinstance(v, str):
        n = F.parse_number(v)
        if n is not None:
            return n
        val, _fmt = F.parse_input(v, allow_formula=False)
        if is_num(val):
            return val
        if isinstance(val, (dt.datetime, dt.time)):
            return to_serial(val)
    raise XLError("#VALUE!")


def text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return F.bool_text(v)
    v2 = to_serial(v)
    if is_num(v2):
        return F.general_number(v2)
    return str(v)


def truth(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if is_num(v):
        return v != 0
    if isinstance(v, str):
        if v.upper() in ("TRUE", "WAAR"):
            return True
        if v.upper() in ("FALSE", "ONWAAR"):
            return False
    raise XLError("#VALUE!")


def _rank(v):
    if v is None:
        return 0
    if isinstance(v, bool):
        return 3
    if isinstance(v, str):
        return 2
    return 1


def compare(a, b):
    a, b = to_serial(a), to_serial(b)
    if a is None:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0)
    if b is None:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0)
    ra, rb = _rank(a), _rank(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if isinstance(a, str):
        a, b = a.lower(), b.lower()
    return (a > b) - (a < b)


def xl_round(x, digits):
    q = Decimal(1).scaleb(-int(digits))
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def check(v):
    if isinstance(v, XLError):
        raise v
    if isinstance(v, str) and v in F.ERRORS:
        raise XLError(v)
    return v


# ---------------------------------------------------------------------------
# Voorwaarden zoals ">5" of "a*" in SOM.ALS en AANTAL.ALS

def criterion(crit):
    if isinstance(crit, str):
        m = re.match(r"^(<=|>=|<>|=|<|>)?(.*)$", crit, re.S)
        op, rest = m.group(1) or "=", m.group(2)
        n = F.parse_number(rest) if rest != "" else None
        if n is not None:
            target = n
        elif rest.upper() in ("TRUE", "WAAR"):
            target = True
        elif rest.upper() in ("FALSE", "ONWAAR"):
            target = False
        else:
            target = rest
    else:
        op, target = "=", to_serial(crit)
    if isinstance(target, str) and op in ("=", "<>") and ("*" in target or "?" in target):
        pat = re.compile("^" + re.escape(target).replace(r"\*", ".*").replace(r"\?", ".") + "$", re.I | re.S)
        if op == "=":
            return lambda v: isinstance(v, str) and bool(pat.match(v))
        return lambda v: not (isinstance(v, str) and pat.match(v))

    def test(v):
        v = to_serial(v)
        if isinstance(target, str) and target == "":
            empty = v is None or v == ""
            return empty if op == "=" else not empty
        if op in ("=", "<>"):
            if is_num(target):
                eq = is_num(v) and abs(v - target) < 1e-12
            elif isinstance(target, bool):
                eq = isinstance(v, bool) and v == target
            else:
                eq = isinstance(v, str) and v.lower() == target.lower()
            return eq if op == "=" else not eq
        if is_num(target):
            if not is_num(v):
                return False
        elif not isinstance(v, str):
            return False
        c = compare(v, target)
        return {"<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]
    return test


# ---------------------------------------------------------------------------
# Rekenen

class Evaluator:
    def __init__(self, book, targets):
        self.book = book
        self.targets = targets
        self.memo = {}
        self.stack = set()
        self.ws = {ws.title.lower(): ws for ws in book.wb.worksheets}
        self.vws = {ws.title.lower(): book._vws(ws) for ws in book.wb.worksheets}
        self._names = None
        self._ext = {}

    def names(self):
        if self._names is None:
            self._names = self.book._names_map()
        return self._names

    def extent(self, sheet):
        if sheet not in self._ext:
            ws = self.ws.get(sheet)
            self._ext[sheet] = self.book.extent(ws) if ws is not None else (0, 0)
        return self._ext[sheet]

    def value(self, sheet, r, c):
        ws = self.ws.get(sheet)
        if ws is None:
            raise XLError("#REF!")
        cell = ws._cells.get((r, c))
        if cell is None:
            return None
        if cell.data_type != "f":
            v = cell.value
            return v if not hasattr(v, "text") else None
        key = (sheet, r, c)
        if key in self.targets:
            return self.compute(key)
        vc = self.vws[sheet]._cells.get((r, c))
        cached = vc.value if vc is not None else None
        if cached is None:
            return self.compute(key)
        return cached

    def compute(self, key):
        if key in self.memo:
            res = self.memo[key]
            if res is _FAILED:
                raise Unsupported("afhankelijk van onberekende cel")
            return res
        if key in self.stack:
            raise Unsupported("kringverwijzing")
        sheet, r, c = key
        cell = self.ws[sheet]._cells.get((r, c))
        formula = cell.value
        if not isinstance(formula, str):
            self.memo[key] = _FAILED
            raise Unsupported("matrixformule")
        self.stack.add(key)
        try:
            node = self.book._parse_cache(formula)
            res = self.ev(node, self.ws[sheet].title)
            if isinstance(res, Range):
                res = self.scalar(res)
            if res is None:
                res = 0
            check(res)
            if isinstance(res, float) and (math.isnan(res) or math.isinf(res)):
                raise XLError("#NUM!")
        except XLError as e:
            res = e.code
        except Deep:
            raise
        except RecursionError:
            raise Deep("te diep")
        except (Unsupported, ZeroDivisionError, OverflowError, ValueError, TypeError,
                IndexError, KeyError):
            self.memo[key] = _FAILED
            raise Unsupported("niet berekend")
        finally:
            self.stack.discard(key)
        self.memo[key] = res
        return res

    # -- knopen
    def ev(self, node, home):
        kind = node[0]
        if kind == "lit":
            return node[1]
        if kind == "err":
            raise XLError(node[1])
        if kind == "missing":
            return None
        if kind == "ref":
            return self.ref(node[1], home)
        if kind == "neg":
            return -num(self.sv(node[1], home))
        if kind == "pct":
            return num(self.sv(node[1], home)) / 100.0
        if kind == "bin":
            op = node[1]
            a = self.sv(node[2], home)
            b = self.sv(node[3], home)
            check(a)
            check(b)
            if op == "&":
                return text(a) + text(b)
            if op in ("=", "<>", "<", ">", "<=", ">="):
                c = compare(a, b)
                return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]
            x, y = num(a), num(b)
            if op == "+":
                return x + y
            if op == "-":
                return x - y
            if op == "*":
                return x * y
            if op == "/":
                if y == 0:
                    raise XLError("#DIV/0!")
                return x / y
            if op == "^":
                return float(x) ** y
        if kind == "fn":
            return self.call(node[1], node[2], home)
        raise Unsupported(kind)

    def ref(self, text_, home):
        name, _prefix, rest = R.split_sheet(text_)
        area = R.parse_area(rest)
        if area is None:
            if rest.upper().startswith("#REF!"):
                raise XLError("#REF!")
            hits = self.names().get(text_.lower())
            if hits and len(hits) == 1:
                s, r1, c1, r2, c2 = hits[0]
                return Range(self, s, r1, c1, r2, c2)
            raise Unsupported("naam " + text_)
        sheet = (name if name is not None else home).lower()
        if sheet not in self.ws:
            raise XLError("#REF!")
        r1, c1, r2, c2 = R.area_bounds(area)
        return Range(self, sheet, r1, c1, r2, c2)

    def scalar(self, v):
        if isinstance(v, Range):
            if v.is_single():
                return v.cell(0, 0)
            raise XLError("#VALUE!")
        return v

    def sv(self, node, home):
        return self.scalar(self.ev(node, home))

    # -- functies
    def call(self, name, args, home):
        lazy = LAZY.get(name)
        if lazy is not None:
            return lazy(self, args, home)
        fn = FUNCS.get(name)
        if fn is None:
            raise Unsupported(name)
        return fn(self, [self.ev(a, home) for a in args])


_FAILED = object()


# ---------------------------------------------------------------------------
# Functiebibliotheek

def _flat(args, strict_scalars=True):
    """Alle waarden uit argumenten; uit bereiken alleen getallen (zoals Excel)."""
    for a in args:
        if isinstance(a, Range):
            for v in a.values():
                check(v)
                v = to_serial(v)
                if is_num(v):
                    yield v
        else:
            check(a)
            if a is None:
                continue
            yield num(a) if strict_scalars else a


def _all_values(args):
    for a in args:
        if isinstance(a, Range):
            for v in a.values():
                yield v
        else:
            yield a


def _arg(args, i, default=None):
    if i < len(args):
        v = args[i]
        if isinstance(v, Range):
            if v.is_single():
                v = v.cell(0, 0)
            else:
                raise XLError("#VALUE!")
        check(v)
        return default if v is None and default is not None else v
    return default


def _range(a):
    if not isinstance(a, Range):
        raise Unsupported("bereik verwacht")
    return a


def f_sum(ev, args):
    return sum(_flat(args))


def f_average(ev, args):
    vals = list(_flat(args))
    if not vals:
        raise XLError("#DIV/0!")
    return sum(vals) / len(vals)


def f_min(ev, args):
    vals = list(_flat(args))
    return min(vals) if vals else 0


def f_max(ev, args):
    vals = list(_flat(args))
    return max(vals) if vals else 0


def f_count(ev, args):
    n = 0
    for a in args:
        if isinstance(a, Range):
            n += sum(1 for v in a.values() if is_num(to_serial(v)))
        elif a is not None:
            try:
                num(a)
                n += 1
            except XLError:
                pass
    return n


def f_counta(ev, args):
    return sum(1 for v in _all_values(args) if v is not None and v != "")


def f_countblank(ev, args):
    rng = _range(args[0])
    rows, cols = rng.shape
    return sum(1 for i in range(rows) for j in range(cols) if rng.cell(i, j) in (None, ""))


def f_product(ev, args):
    out = 1
    for v in _flat(args):
        out *= v
    return out


def f_median(ev, args):
    vals = sorted(_flat(args))
    if not vals:
        raise XLError("#NUM!")
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2.0


def f_round(ev, args):
    return xl_round(num(_arg(args, 0)), num(_arg(args, 1, 0)))


def f_roundup(ev, args):
    x, d = num(_arg(args, 0)), int(num(_arg(args, 1, 0)))
    f = 10 ** d
    return math.copysign(math.ceil(abs(x) * f - 1e-9) / f, x)


def f_rounddown(ev, args):
    x, d = num(_arg(args, 0)), int(num(_arg(args, 1, 0)))
    f = 10 ** d
    return math.copysign(math.floor(abs(x) * f + 1e-9) / f, x)


def f_int(ev, args):
    return math.floor(num(_arg(args, 0)))


def f_mod(ev, args):
    a, b = num(_arg(args, 0)), num(_arg(args, 1))
    if b == 0:
        raise XLError("#DIV/0!")
    return a - b * math.floor(a / b)


def f_sqrt(ev, args):
    x = num(_arg(args, 0))
    if x < 0:
        raise XLError("#NUM!")
    return math.sqrt(x)


def _ifs_pairs(args, start):
    pairs = []
    for i in range(start, len(args) - 1, 2):
        pairs.append((_range(args[i]), criterion(_arg(args, i + 1))))
    return pairs


def f_sumif(ev, args):
    rng, test = _range(args[0]), criterion(_arg(args, 1))
    tgt = _range(args[2]) if len(args) > 2 else rng
    total = 0
    rows, cols = rng.shape
    for i in range(rows):
        for j in range(cols):
            if test(rng.cell(i, j)):
                v = to_serial(check(tgt.cell(i, j)))
                if is_num(v):
                    total += v
    return total


def f_countif(ev, args):
    rng, test = _range(args[0]), criterion(_arg(args, 1))
    rows, cols = rng.shape
    return sum(1 for i in range(rows) for j in range(cols) if test(rng.cell(i, j)))


def f_averageif(ev, args):
    rng, test = _range(args[0]), criterion(_arg(args, 1))
    tgt = _range(args[2]) if len(args) > 2 else rng
    vals = []
    rows, cols = rng.shape
    for i in range(rows):
        for j in range(cols):
            if test(rng.cell(i, j)):
                v = to_serial(tgt.cell(i, j))
                if is_num(v):
                    vals.append(v)
    if not vals:
        raise XLError("#DIV/0!")
    return sum(vals) / len(vals)


def _multi(args, start):
    pairs = _ifs_pairs(args, start)
    base = pairs[0][0]
    rows, cols = base.shape
    for i in range(rows):
        for j in range(cols):
            if all(test(rng.cell(i, j)) for rng, test in pairs):
                yield i, j


def _target_nums(tgt, idx):
    for i, j in idx:
        v = to_serial(check(tgt.cell(i, j)))
        if is_num(v):
            yield v


def f_sumifs(ev, args):
    return sum(_target_nums(_range(args[0]), _multi(args, 1)))


def f_countifs(ev, args):
    return sum(1 for _ in _multi(args, 0))


def f_averageifs(ev, args):
    vals = list(_target_nums(_range(args[0]), _multi(args, 1)))
    if not vals:
        raise XLError("#DIV/0!")
    return sum(vals) / len(vals)


def f_maxifs(ev, args):
    vals = list(_target_nums(_range(args[0]), _multi(args, 1)))
    return max(vals) if vals else 0


def f_minifs(ev, args):
    vals = list(_target_nums(_range(args[0]), _multi(args, 1)))
    return min(vals) if vals else 0


def f_sumproduct(ev, args):
    ranges = [_range(a) for a in args]
    shape = ranges[0].shape
    if any(r.shape != shape for r in ranges):
        raise XLError("#VALUE!")
    total = 0
    for i in range(shape[0]):
        for j in range(shape[1]):
            p = 1
            for rng in ranges:
                v = to_serial(check(rng.cell(i, j)))
                p *= v if is_num(v) else 0
            total += p
    return total


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        if "*" in a or "?" in a:
            return criterion("=" + a)(b)
        return a.lower() == b.lower()
    a, b = to_serial(a), to_serial(b)
    if is_num(a) and is_num(b):
        return abs(a - b) < 1e-12
    return a == b and type(a) is type(b)


def _lookup_vector(vec, value, mode):
    """mode 0 = exact, 1 = grootste <= waarde (gesorteerd), -1 = kleinste >= waarde."""
    if mode == 0:
        for i, v in enumerate(vec):
            if v is not None and _eq(value, v):
                return i
        return None
    best = None
    for i, v in enumerate(vec):
        if v is None or _rank(to_serial(v)) != _rank(to_serial(value)):
            continue
        c = compare(v, value)
        if mode == 1:
            if c <= 0:
                best = i
            else:
                break
        else:
            if c >= 0:
                best = i
            else:
                break
    return best


def f_vlookup(ev, args):
    value = _arg(args, 0)
    table = _range(args[1])
    col = int(num(_arg(args, 2)))
    approx = truth(_arg(args, 3, True)) if len(args) > 3 and args[3] is not None else True
    rows, cols = table.shape
    if col < 1 or col > cols:
        raise XLError("#REF!")
    vec = [table.cell(i, 0) for i in range(rows)]
    i = _lookup_vector(vec, value, 1 if approx else 0)
    if i is None:
        raise XLError("#N/A")
    return table.cell(i, col - 1)


def f_hlookup(ev, args):
    value = _arg(args, 0)
    table = _range(args[1])
    row = int(num(_arg(args, 2)))
    approx = truth(_arg(args, 3, True)) if len(args) > 3 and args[3] is not None else True
    rows, cols = table.shape
    if row < 1 or row > rows:
        raise XLError("#REF!")
    vec = [table.cell(0, j) for j in range(cols)]
    j = _lookup_vector(vec, value, 1 if approx else 0)
    if j is None:
        raise XLError("#N/A")
    return table.cell(row - 1, j)


def _vector(rng):
    rows, cols = rng.shape
    if rows == 1:
        return [rng.cell(0, j) for j in range(cols)], False
    if cols == 1:
        return [rng.cell(i, 0) for i in range(rows)], True
    raise XLError("#N/A")


def f_match(ev, args):
    value = _arg(args, 0)
    vec, _ = _vector(_range(args[1]))
    mode = int(num(_arg(args, 2, 1))) if len(args) > 2 else 1
    i = _lookup_vector(vec, value, 0 if mode == 0 else (1 if mode > 0 else -1))
    if i is None:
        raise XLError("#N/A")
    return i + 1


def f_xmatch(ev, args):
    value = _arg(args, 0)
    vec, _ = _vector(_range(args[1]))
    i = _lookup_vector(vec, value, 0)
    if i is None:
        raise XLError("#N/A")
    return i + 1


def f_index(ev, args):
    rng = _range(args[0])
    rows, cols = rng.shape
    r = int(num(_arg(args, 1, 0))) if len(args) > 1 else 0
    c = int(num(_arg(args, 2, 0))) if len(args) > 2 else 0
    if rows == 1 and len(args) == 2:
        r, c = 1, r
    if r == 0 and c == 0:
        raise Unsupported("hele rij/kolom")
    r, c = r or 1, c or 1
    if r < 1 or c < 1 or r > rows or c > cols:
        raise XLError("#REF!")
    return rng.cell(r - 1, c - 1)


def f_xlookup(ev, args):
    value = _arg(args, 0)
    vec, vertical = _vector(_range(args[1]))
    ret = _range(args[2])
    i = _lookup_vector(vec, value, 0)
    if i is None:
        if len(args) > 3 and args[3] is not None:
            return _arg(args, 3)
        raise XLError("#N/A")
    rows, cols = ret.shape
    if vertical:
        if cols != 1:
            raise Unsupported("meerdere kolommen")
        return ret.cell(i, 0)
    if rows != 1:
        raise Unsupported("meerdere rijen")
    return ret.cell(0, i)


def f_and(ev, args):
    vals = [truth(v) for v in _all_values(args) if v is not None and not isinstance(v, str)]
    return all(vals) if vals else True


def f_or(ev, args):
    vals = [truth(v) for v in _all_values(args) if v is not None and not isinstance(v, str)]
    return any(vals)


def f_not(ev, args):
    return not truth(_arg(args, 0))


def f_concat(ev, args):
    return "".join(text(check(v)) for v in _all_values(args))


def f_textjoin(ev, args):
    sep = text(_arg(args, 0, ""))
    skip = truth(_arg(args, 1, True))
    parts = [text(check(v)) for v in _all_values(args[2:])]
    if skip:
        parts = [p for p in parts if p != ""]
    return sep.join(parts)


def f_left(ev, args):
    n = int(num(_arg(args, 1, 1))) if len(args) > 1 else 1
    return text(_arg(args, 0))[:max(0, n)]


def f_right(ev, args):
    n = int(num(_arg(args, 1, 1))) if len(args) > 1 else 1
    s = text(_arg(args, 0))
    return s[-n:] if n > 0 else ""


def f_mid(ev, args):
    s = text(_arg(args, 0))
    start, n = int(num(_arg(args, 1))), int(num(_arg(args, 2)))
    if start < 1 or n < 0:
        raise XLError("#VALUE!")
    return s[start - 1:start - 1 + n]


def f_find(ev, args, ci=False):
    needle, hay = text(_arg(args, 0)), text(_arg(args, 1))
    start = int(num(_arg(args, 2, 1))) if len(args) > 2 else 1
    if ci:
        needle, hay = needle.lower(), hay.lower()
    i = hay.find(needle, start - 1)
    if i < 0:
        raise XLError("#VALUE!")
    return i + 1


def f_substitute(ev, args):
    s, old, new = text(_arg(args, 0)), text(_arg(args, 1)), text(_arg(args, 2))
    if len(args) > 3:
        n = int(num(_arg(args, 3)))
        parts = s.split(old)
        if n < 1 or n >= len(parts):
            return s
        return old.join(parts[:n]) + new + old.join(parts[n:])
    return s.replace(old, new) if old else s


def f_text(ev, args):
    v, fmt = _arg(args, 0), text(_arg(args, 1))
    fmt = re.sub(r"j", "y", fmt)  # NL: jjjj -> yyyy
    v = to_serial(v)
    if isinstance(v, str):
        return v
    d, _k = F.display(num(v), fmt)
    return d


def f_value(ev, args):
    return num(_arg(args, 0))


def f_date(ev, args):
    y, m, d = int(num(_arg(args, 0))), int(num(_arg(args, 1))), int(num(_arg(args, 2)))
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    base = dt.datetime(y, m, 1) + dt.timedelta(days=d - 1)
    return to_excel(base)


def _as_date(v):
    v = to_serial(v)
    if isinstance(v, str):
        v = num(v)
    return from_excel(num(v))


def f_today(ev, args):
    return to_excel(dt.datetime.combine(dt.date.today(), dt.time(0)))


def f_now(ev, args):
    return to_excel(dt.datetime.now())


def f_eomonth(ev, args):
    d = _as_date(_arg(args, 0))
    m = int(num(_arg(args, 1)))
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    nxt = dt.datetime(y + (mo // 12), mo % 12 + 1, 1)
    return to_excel(nxt - dt.timedelta(days=1))


def f_edate(ev, args):
    d = _as_date(_arg(args, 0))
    m = int(num(_arg(args, 1)))
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    import calendar
    day = min(d.day, calendar.monthrange(y, mo)[1])
    return to_excel(dt.datetime(y, mo, day))


def f_weekday(ev, args):
    d = _as_date(_arg(args, 0))
    t = int(num(_arg(args, 1, 1))) if len(args) > 1 else 1
    wd = d.weekday()  # ma = 0
    if t == 1:
        return (wd + 1) % 7 + 1
    if t == 2:
        return wd + 1
    if t == 3:
        return wd
    raise Unsupported("weekdagtype")


def f_iserror(ev, args, which=None):
    try:
        v = args[0]
        if isinstance(v, Range):
            v = v.cell(0, 0) if v.is_single() else None
        check(v)
        return False
    except XLError as e:
        return which is None or e.code == which


def _type_test(pred):
    def fn(ev, args):
        v = args[0]
        if isinstance(v, Range):
            v = v.cell(0, 0) if v.is_single() else None
        return pred(v)
    return fn


def _num1(fn):
    return lambda ev, args: fn(num(_arg(args, 0)))


def _rank_fn(ev, args, largest):
    vals = sorted(_flat([args[0]]), reverse=largest)
    k = int(num(_arg(args, 1)))
    if k < 1 or k > len(vals):
        raise XLError("#NUM!")
    return vals[k - 1]


FUNCS = {
    "SUM": f_sum, "AVERAGE": f_average, "MIN": f_min, "MAX": f_max, "COUNT": f_count,
    "COUNTA": f_counta, "COUNTBLANK": f_countblank, "PRODUCT": f_product, "MEDIAN": f_median,
    "ROUND": f_round, "ROUNDUP": f_roundup, "ROUNDDOWN": f_rounddown, "INT": f_int,
    "TRUNC": lambda ev, a: math.trunc(num(_arg(a, 0)) * 10 ** int(num(_arg(a, 1, 0)))) / 10 ** int(num(_arg(a, 1, 0))),
    "ABS": _num1(abs), "SQRT": f_sqrt, "MOD": f_mod,
    "POWER": lambda ev, a: float(num(_arg(a, 0))) ** num(_arg(a, 1)),
    "PI": lambda ev, a: math.pi, "SIGN": _num1(lambda x: (x > 0) - (x < 0)),
    "SUMIF": f_sumif, "COUNTIF": f_countif, "AVERAGEIF": f_averageif,
    "SUMIFS": f_sumifs, "COUNTIFS": f_countifs, "AVERAGEIFS": f_averageifs,
    "MAXIFS": f_maxifs, "MINIFS": f_minifs, "SUMPRODUCT": f_sumproduct,
    "VLOOKUP": f_vlookup, "HLOOKUP": f_hlookup, "MATCH": f_match, "XMATCH": f_xmatch,
    "INDEX": f_index, "XLOOKUP": f_xlookup,
    "AND": f_and, "OR": f_or, "NOT": f_not, "TRUE": lambda ev, a: True, "FALSE": lambda ev, a: False,
    "CONCATENATE": f_concat, "CONCAT": f_concat, "TEXTJOIN": f_textjoin,
    "LEFT": f_left, "RIGHT": f_right, "MID": f_mid,
    "LEN": lambda ev, a: len(text(_arg(a, 0))),
    "UPPER": lambda ev, a: text(_arg(a, 0)).upper(),
    "LOWER": lambda ev, a: text(_arg(a, 0)).lower(),
    "PROPER": lambda ev, a: text(_arg(a, 0)).title(),
    "TRIM": lambda ev, a: " ".join(text(_arg(a, 0)).split()),
    "FIND": f_find, "SEARCH": lambda ev, a: f_find(ev, a, True), "SUBSTITUTE": f_substitute,
    "REPT": lambda ev, a: text(_arg(a, 0)) * int(num(_arg(a, 1))),
    "TEXT": f_text, "VALUE": f_value,
    "DATE": f_date, "TODAY": f_today, "NOW": f_now,
    "YEAR": lambda ev, a: _as_date(_arg(a, 0)).year,
    "MONTH": lambda ev, a: _as_date(_arg(a, 0)).month,
    "DAY": lambda ev, a: _as_date(_arg(a, 0)).day,
    "HOUR": lambda ev, a: _as_date(_arg(a, 0)).hour,
    "MINUTE": lambda ev, a: _as_date(_arg(a, 0)).minute,
    "WEEKDAY": f_weekday, "EOMONTH": f_eomonth, "EDATE": f_edate,
    "DAYS": lambda ev, a: num(_arg(a, 0)) - num(_arg(a, 1)),
    "ISBLANK": _type_test(lambda v: v is None),
    "ISNUMBER": _type_test(lambda v: is_num(to_serial(v))),
    "ISTEXT": _type_test(lambda v: isinstance(v, str) and v not in F.ERRORS),
    "ISERROR": f_iserror, "ISNA": lambda ev, a: f_iserror(ev, a, "#N/A"),
    "NA": lambda ev, a: (_ for _ in ()).throw(XLError("#N/A")),
    "LARGE": lambda ev, a: _rank_fn(ev, a, True), "SMALL": lambda ev, a: _rank_fn(ev, a, False),
}


# -- functies die hun argumenten pas uitrekenen als dat nodig is

def l_if(ev, args, home):
    cond = truth(check(ev.sv(args[0], home)))
    if cond:
        return ev.ev(args[1], home) if len(args) > 1 else True
    if len(args) > 2:
        v = ev.ev(args[2], home)
        return False if args[2][0] == "missing" else v
    return False


def l_iferror(ev, args, home, only=None):
    try:
        v = ev.sv(args[0], home)
        check(v)
        return v
    except XLError as e:
        if only and e.code != only:
            raise
        return ev.ev(args[1], home)


def l_ifs(ev, args, home):
    for i in range(0, len(args) - 1, 2):
        if truth(check(ev.sv(args[i], home))):
            return ev.ev(args[i + 1], home)
    raise XLError("#N/A")


def l_choose(ev, args, home):
    i = int(num(ev.sv(args[0], home)))
    if i < 1 or i >= len(args):
        raise XLError("#VALUE!")
    return ev.ev(args[i], home)


def l_switch(ev, args, home):
    v = ev.sv(args[0], home)
    rest = args[1:]
    for i in range(0, len(rest) - 1, 2):
        if compare(v, ev.sv(rest[i], home)) == 0:
            return ev.ev(rest[i + 1], home)
    if len(rest) % 2:
        return ev.ev(rest[-1], home)
    raise XLError("#N/A")


LAZY = {
    "IF": l_if, "IFERROR": l_iferror, "IFNA": lambda ev, a, h: l_iferror(ev, a, h, "#N/A"),
    "IFS": l_ifs, "CHOOSE": l_choose, "SWITCH": l_switch,
}
