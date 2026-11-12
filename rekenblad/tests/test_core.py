import datetime as dt
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import openpyxl  # noqa: E402

import formats as F  # noqa: E402
import refs as R  # noqa: E402
import workbook as W  # noqa: E402

W.DATA_DIR = tempfile.mkdtemp()


def make_book(build):
    wb = openpyxl.Workbook()
    build(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return W.Book().load_bytes(buf.getvalue(), "test.xlsx")


def cell(book, sheet, coord):
    return book.wb[sheet][coord].value


class RefTests(unittest.TestCase):
    def test_shift_interval(self):
        self.assertEqual(R.shift_interval(3, 10, 5, 2), (3, 12))
        self.assertEqual(R.shift_interval(5, 10, 5, 2), (7, 12))
        self.assertEqual(R.shift_interval(3, 10, 5, -2), (3, 8))
        self.assertIsNone(R.shift_interval(5, 6, 5, -2))
        self.assertEqual(R.shift_interval(6, 10, 5, -3), (5, 7))
        self.assertEqual(R.shift_interval(3, 6, 5, -3), (3, 4))

    def test_formula_shift(self):
        fn = R.shift_fn("Blad1", "Blad1", "row", 3, 2)
        self.assertEqual(R.map_range_tokens("=SUM(A1:A10)+$B$5", fn), "=SUM(A1:A12)+$B$7")
        fn = R.shift_fn("Blad2", "Blad1", "row", 3, 2)
        self.assertEqual(R.map_range_tokens("=Blad1!A5+A5", fn), "=Blad1!A7+A5")
        fn = R.shift_fn("Blad1", "Blad1", "row", 5, -1)
        self.assertEqual(R.map_range_tokens("=A5+A6", fn), "=#REF!+A5")
        fn = R.shift_fn("Blad1", "Blad1", "col", 2, 1)
        self.assertEqual(R.map_range_tokens('=SUM(A1:C1)&"B2"', fn), '=SUM(A1:D1)&"B2"')
        self.assertEqual(R.map_range_tokens("=SUM(A:A)", R.shift_fn("Blad1", "Blad1", "row", 1, 5)),
                         "=SUM(A:A)")

    def test_rename(self):
        fn = R.rename_fn("Blad1", "Mijn data")
        self.assertEqual(R.map_range_tokens("=Blad1!A1*2", fn), "='Mijn data'!A1*2")


class FormatTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(F.fmt_number(1234.5, "#,##0.00"), "1.234,50")
        self.assertEqual(F.fmt_number(0.256, "0%"), "26%")
        self.assertEqual(F.fmt_number(0.256, "0.0%"), "25,6%")
        self.assertEqual(F.fmt_number(1234.5, '"€ "#,##0.00'), "€ 1.234,50")
        self.assertEqual(F.fmt_number(1234.5, "[$€-413] #,##0.00"), "€ 1.234,50")
        self.assertEqual(F.fmt_number(-5, "#,##0.00;[Red]-#,##0.00"), "-5,00")
        self.assertEqual(F.fmt_number(-5, "#,##0.00;(#,##0.00)"), "(5,00)")
        self.assertEqual(F.fmt_number(1234.5, "#,##0.00 €"), "1.234,50 €")
        self.assertEqual(F.fmt_number(12, "0"), "12")
        self.assertEqual(F.general_number(0.1 + 0.2), "0,3")
        self.assertEqual(F.general_number(1.5), "1,5")

    def test_dates(self):
        d = dt.datetime(2026, 11, 12, 9, 5)
        self.assertEqual(F.fmt_date(d, "dd-mm-yyyy"), "12-11-2026")
        self.assertEqual(F.fmt_date(d, "d mmmm yyyy"), "12 november 2026")
        self.assertEqual(F.fmt_date(d, "yyyy-mm-dd h:mm"), "2026-11-12 9:05")
        self.assertEqual(F.fmt_date(dt.time(14, 30), "hh:mm"), "14:30")

    def test_parse(self):
        self.assertEqual(F.parse_input("12,5"), (12.5, None))
        self.assertEqual(F.parse_input("1.234,56"), (1234.56, None))
        self.assertEqual(F.parse_input("1.5"), (1.5, None))
        self.assertEqual(F.parse_input("42"), (42, None))
        self.assertEqual(F.parse_input("0612345678"), ("0612345678", None))
        self.assertEqual(F.parse_input("15%"), (0.15, "0%"))
        self.assertEqual(F.parse_input("€ 12,50"), (12.5, F.FMT_EURO))
        self.assertEqual(F.parse_input("12-11-2026"), (dt.datetime(2026, 11, 12), F.FMT_DATE))
        self.assertEqual(F.parse_input("waar"), (True, None))
        self.assertEqual(F.parse_input("'123"), ("123", None))
        self.assertEqual(F.parse_input(""), (None, None))

    def test_formula_input(self):
        self.assertEqual(F.normalize_formula("=SOM(A1:A3;B1)"), "=SUM(A1:A3,B1)")
        self.assertEqual(F.normalize_formula("=ALS(a1>1,5;WAAR;\"x;y\")"), '=IF(A1>1.5,TRUE,"x;y")')
        self.assertEqual(F.normalize_formula("=A1*1,5"), "=A1*1.5")
        self.assertEqual(F.normalize_formula("=round(A1,2)"), "=ROUND(A1,2)")
        self.assertEqual(F.normalize_formula("=X.ZOEKEN(A1;B:B;C:C)"), "=_xlfn.XLOOKUP(A1,B:B,C:C)")
        with self.assertRaises(F.FormulaError):
            F.normalize_formula("=SUM(A1")


class BookTests(unittest.TestCase):
    def build(self, wb):
        ws = wb.active
        ws.title = "Blad1"
        for i in range(1, 6):
            ws.cell(i, 1, i * 10)
        ws["B1"] = "=SUM(A1:A5)"
        ws["B2"] = "=B1*2"
        ws.merge_cells("D1:E1")
        ws["D1"] = "Titel"
        ws.column_dimensions["A"].width = 20
        other = wb.create_sheet("Overzicht")
        other["A1"] = "=Blad1!A3"

    def test_read(self):
        b = make_book(self.build)
        st = b.state()
        self.assertEqual([s["name"] for s in st["sheets"]], ["Blad1", "Overzicht"])
        rows = b.get_rows("Blad1", 1, 10)["rows"]
        self.assertEqual(rows[1][1]["d"], "10")
        self.assertEqual(rows[1][2]["e"], "=SUM(A1:A5)")
        self.assertEqual(rows[1][4]["cs"], 2)
        self.assertEqual(st["sheets"][0]["colw"][0], W.px_from_width(20))

    def test_edit_marks_dependents(self):
        b = make_book(self.build)
        b.vals["Blad1"]["B1"].value = 150
        b.vals["Blad1"]["B2"].value = 300
        b.set_cells("Blad1", [{"r": 1, "c": 1, "v": "99"}])
        self.assertEqual(cell(b, "Blad1", "A1"), 99)
        self.assertEqual(b.vals["Blad1"]["B1"].value, 239)
        self.assertEqual(b.vals["Blad1"]["B2"].value, 478)
        self.assertEqual(b.vals["Overzicht"]["A1"].value, 30)
        b.undo()
        self.assertEqual(cell(b, "Blad1", "A1"), 10)
        self.assertEqual(b.vals["Blad1"]["B1"].value, 150)
        b.redo()
        self.assertEqual(cell(b, "Blad1", "A1"), 99)

    def test_insert_rows_updates_formulas(self):
        b = make_book(self.build)
        b.insert("Blad1", "row", 2, 2)
        self.assertEqual(cell(b, "Blad1", "B1"), "=SUM(A1:A7)")
        self.assertEqual(cell(b, "Blad1", "B4"), "=B1*2")
        self.assertEqual(cell(b, "Overzicht", "A1"), "=Blad1!A5")
        self.assertIn("D1:E1", [str(m) for m in b.wb["Blad1"].merged_cells.ranges])
        b.undo()
        self.assertEqual(cell(b, "Blad1", "B1"), "=SUM(A1:A5)")

    def test_delete_cols(self):
        b = make_book(self.build)
        b.delete("Blad1", "col", 1, 1)
        self.assertEqual(cell(b, "Blad1", "A1"), "=SUM(#REF!)")
        self.assertEqual(cell(b, "Overzicht", "A1"), "=Blad1!#REF!")

    def test_rename_and_delete_sheet(self):
        b = make_book(self.build)
        b.rename_sheet("Blad1", "Data 2026")
        self.assertEqual(cell(b, "Overzicht", "A1"), "='Data 2026'!A3")
        with self.assertRaises(W.UserError):
            b.rename_sheet("Overzicht", "data 2026")
        b.add_sheet()
        self.assertEqual(len(b.wb.worksheets), 3)
        b.delete_sheet("Data 2026")
        self.assertEqual(cell(b, "Overzicht", "A1"), "=#REF!")

    def test_format_and_save_roundtrip(self):
        b = make_book(self.build)
        b.set_format("Blad1", 1, 1, 2, 1, {"bold": True, "fill": "FFF2CC", "numfmt": "#,##0.00"})
        b.set_cells("Blad1", [{"r": 10, "c": 1, "v": "12-11-2026"}, {"r": 11, "c": 1, "v": "=SOM(A1:A5)"}])
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "uit.xlsx")
        b.save(path, sheet="Overzicht")
        wb = openpyxl.load_workbook(path)
        ws = wb["Blad1"]
        self.assertTrue(ws["A1"].font.b)
        self.assertEqual(ws["A1"].number_format, "#,##0.00")
        self.assertEqual(ws["A10"].value, dt.datetime(2026, 11, 12))
        self.assertEqual(ws["A11"].value, "=SUM(A1:A5)")
        self.assertEqual(wb.active.title, "Overzicht")
        self.assertFalse(b.dirty)
        b2 = W.Book().load_path(path)
        self.assertEqual(b2.get_rows("Blad1", 1, 1)["rows"][1][1]["d"], "10,00")

    def test_search_replace(self):
        b = make_book(self.build)
        res = b.search("titel")
        self.assertEqual(res["matches"][0]["r"], 1)
        self.assertEqual(b.replace_all("Titel", "Kop")["count"], 1)
        self.assertEqual(cell(b, "Blad1", "D1"), "Kop")

    def test_csv(self):
        data = "naam;bedrag;datum\nPiet;12,50;01-02-2026\nKlaas;1.234,56;03-04-2026\n".encode("utf-8")
        b = W.Book().load_bytes(data, "lijst.csv")
        ws = b.wb.worksheets[0]
        self.assertEqual(ws["B2"].value, 12.5)
        self.assertEqual(ws["B3"].value, 1234.56)
        self.assertEqual(ws["C2"].value, dt.datetime(2026, 2, 1))
        out = b._csv_bytes().decode("utf-8")
        self.assertIn("Piet;12,5;01-02-2026", out)

    def test_table_guard(self):
        from openpyxl.worksheet.table import Table

        def build(wb):
            ws = wb.active
            ws.title = "Blad1"
            ws.append(["a", "b", "c"])
            ws.append([1, 2, 3])
            ws.append([4, 5, 6])
            ws.add_table(Table(displayName="T1", ref="A1:C3"))

        b = make_book(build)
        with self.assertRaises(W.UserError):
            b.insert("Blad1", "col", 2, 1)
        b.insert("Blad1", "row", 3, 1)
        self.assertEqual(b.wb["Blad1"].tables["T1"].ref, "A1:C4")

    def test_col_width(self):
        b = make_book(self.build)
        b.set_col_width("Blad1", 3, 150)
        self.assertEqual(b.state()["sheets"][0]["colw"][2], 150)
        b.undo()
        self.assertNotEqual(b.state()["sheets"][0]["colw"][2], 150)


class CalcTests(unittest.TestCase):
    def calc(self, formula, extra=None):
        def build(wb):
            ws = wb.active
            ws.title = "Blad1"
            rows = [["naam", "bedrag", "datum"], ["appel", 10, dt.datetime(2026, 1, 15)],
                    ["peer", 20.5, dt.datetime(2026, 2, 1)], ["appel", 5, dt.datetime(2026, 3, 1)],
                    ["kiwi", None, None]]
            for r in rows:
                ws.append(r)
            for coord, v in (extra or {}).items():
                ws[coord] = v
            ws["Z1"] = formula
        b = make_book(build)
        return b.vals["Blad1"]["Z1"].value

    def test_basic(self):
        self.assertEqual(self.calc("=SUM(B2:B5)"), 35.5)
        self.assertEqual(self.calc("=SUM(B:B)"), 35.5)
        self.assertAlmostEqual(self.calc("=AVERAGE(B2:B5)"), 35.5 / 3)
        self.assertEqual(self.calc("=COUNT(B2:B5)"), 3)
        self.assertEqual(self.calc("=COUNTA(A2:A5)"), 4)
        self.assertEqual(self.calc("=-2^2"), 4)
        self.assertEqual(self.calc("=2+3*4"), 14)
        self.assertEqual(self.calc("=10%"), 0.1)
        self.assertEqual(self.calc("=ROUND(2.345,2)"), 2.35)
        self.assertEqual(self.calc("=1/0"), "#DIV/0!")
        self.assertEqual(self.calc("=IFERROR(1/0,\"x\")"), "x")
        self.assertEqual(self.calc("=IF(B2>5,\"hoog\",\"laag\")"), "hoog")
        self.assertEqual(self.calc("=A2&\" \"&B3"), "appel 20,5")

    def test_lookup(self):
        self.assertEqual(self.calc("=SUMIF(A2:A5,\"appel\",B2:B5)"), 15)
        self.assertEqual(self.calc("=COUNTIF(B2:B5,\">8\")"), 2)
        self.assertEqual(self.calc("=SUMIFS(B2:B5,A2:A5,\"appel\",B2:B5,\"<8\")"), 5)
        self.assertEqual(self.calc("=VLOOKUP(\"peer\",A2:C5,2,FALSE)"), 20.5)
        self.assertEqual(self.calc("=INDEX(B2:B5,MATCH(\"kiwi\",A2:A5,0))"), 0)
        self.assertEqual(self.calc("=_xlfn.XLOOKUP(\"appel\",A2:A5,B2:B5)"), 10)
        self.assertEqual(self.calc("=VLOOKUP(\"zzz\",A2:C5,2,FALSE)"), "#N/A")
        self.assertEqual(self.calc("=YEAR(C2)"), 2026)
        self.assertEqual(self.calc("=MONTH(C3)"), 2)

    def test_unsupported_stays_empty(self):
        self.assertIsNone(self.calc("=WEBSERVICE(\"x\")"))

    def test_chain(self):
        extra = {"D1": 1}
        for r in range(2, 3001):
            extra["D%d" % r] = "=D%d+1" % (r - 1)
        extra["E1"] = "=D3000"
        self.assertEqual(self.calc("=E1", extra), 3000)


if __name__ == "__main__":
    unittest.main()
