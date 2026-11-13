import io
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import docx  # noqa: E402
from docx.oxml import parse_xml  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

import document as D  # noqa: E402
import ooxml as X  # noqa: E402

D.DATA_DIR = tempfile.mkdtemp()
W = X.W


def build(fn):
    d = docx.Document()
    fn(d)
    buf = io.BytesIO()
    d.save(buf)
    doc = D.Doc()
    doc.key = "test"
    doc.load_bytes(buf.getvalue(), "test.docx")
    return doc


def roundtrip(doc):
    data = doc.to_bytes()
    return docx.Document(io.BytesIO(data))


def ids_in(html, tag="p"):
    return re.findall(r'<%s data-id="([^"]+)"' % tag, html)


def first_r(html, text):
    m = re.search(r'data-r="([^"]+)"[^>]*>%s<' % re.escape(text), html)
    return m.group(1) if m else None


class RenderSyncTests(unittest.TestCase):
    def setUp(self):
        def fn(d):
            d.add_heading("Kop", 1)
            p = d.add_paragraph("Dit is ")
            r = p.add_run("vet")
            r.bold = True
            p.add_run(" tekst.")
            d.add_paragraph("Tweede alinea.")
        self.doc = build(fn)
        self.r = self.doc.render_all()
        self.body = next(c for c in self.r["containers"] if c["key"] == "body")["html"]
        self.pids = ids_in(self.body)

    def test_unchanged_sync_keeps_xml(self):
        before = self.doc.to_bytes()
        ids = self.doc.sync(self.r["gen"], {"body": [{"id": i} for i in self.pids]})
        self.assertEqual(ids, {})
        self.assertEqual(roundtrip(self.doc).paragraphs[1].text, "Dit is vet tekst.")
        self.assertTrue(before)

    def test_edit_text_keeps_bold(self):
        rv = first_r(self.body, "vet")
        r0 = first_r(self.body, "Dit is ")
        model = {"t": "p", "id": self.pids[1], "items": [
            {"x": "Dit is heel ", "r": r0, "p": {}},
            {"x": "vet", "r": rv, "p": {"b": True}},
            {"x": " en ", "r": r0, "p": {}},
            {"x": "nieuw", "r": None, "p": {"i": True}},
        ]}
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, model, {"id": self.pids[2]}]})
        d = roundtrip(self.doc)
        p = d.paragraphs[1]
        self.assertEqual(p.text, "Dit is heel vet en nieuw")
        self.assertTrue(p.runs[1].bold)
        self.assertTrue(p.runs[-1].italic)
        self.assertIsNone(p.runs[0].bold)

    def test_unbold(self):
        rv = first_r(self.body, "vet")
        model = {"t": "p", "id": self.pids[1], "items": [{"x": "vet", "r": rv, "p": {"b": False}}]}
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, model, {"id": self.pids[2]}]})
        self.assertFalse(roundtrip(self.doc).paragraphs[1].runs[0].bold)

    def test_split_new_paragraph_and_style(self):
        model_new = {"t": "p", "id": "n1", "from": self.pids[0], "style": "Heading2",
                     "items": [{"x": "Nieuwe kop", "r": None, "p": {}}]}
        ids = self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, model_new, {"id": self.pids[1]},
                                                    {"id": self.pids[2]}]})
        self.assertIn("n1", ids)
        d = roundtrip(self.doc)
        self.assertEqual(d.paragraphs[1].text, "Nieuwe kop")
        self.assertEqual(d.paragraphs[1].style.name, "Heading 2")
        # het nieuwe id is bruikbaar in een volgende sync
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, {"id": ids["n1"]}, {"id": self.pids[2]}]})
        self.assertEqual([p.text for p in roundtrip(self.doc).paragraphs], ["Kop", "Nieuwe kop", "Tweede alinea."])

    def test_delete_and_undo_redo(self):
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}]})
        self.assertEqual(len(roundtrip(self.doc).paragraphs), 1)
        self.doc.undo()
        self.assertEqual(len(roundtrip(self.doc).paragraphs), 3)
        self.doc.redo()
        self.assertEqual(len(roundtrip(self.doc).paragraphs), 1)

    def test_stale_gen(self):
        with self.assertRaises(D.SyncError):
            self.doc.sync(self.r["gen"] + 5, {"body": [{"id": self.pids[0]}]})

    def test_unknown_id_rolls_back(self):
        with self.assertRaises(D.SyncError):
            self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, {"id": "bestaatniet"}]})
        self.assertEqual(len(roundtrip(self.doc).paragraphs), 3)
        self.assertEqual(self.doc.undo_stack, [])

    def test_align_and_link(self):
        model = {"t": "p", "id": self.pids[2], "align": "center", "items": [
            {"x": "Zie ", "r": None, "p": {}},
            {"x": "de site", "r": None, "p": {}, "href": "https://example.com"},
        ]}
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, {"id": self.pids[1]}, model]})
        d = roundtrip(self.doc)
        p = d.paragraphs[2]
        self.assertEqual(p.alignment, 1)
        xml = p._p.xml
        self.assertIn("w:hyperlink", xml)
        rid = p._p.find(qn("w:hyperlink")).get(qn("r:id"))
        self.assertEqual(d.part.rels[rid].target_ref, "https://example.com")

    def test_tabs_and_breaks(self):
        model = {"t": "p", "id": self.pids[2], "items": [{"x": "a\tb\nc", "r": None, "p": {}}]}
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, {"id": self.pids[1]}, model]})
        p = roundtrip(self.doc).paragraphs[2]._p
        self.assertIsNotNone(p.find(".//" + qn("w:tab")))
        self.assertIsNotNone(p.find(".//" + qn("w:br")))

    def test_rpr_order_is_valid(self):
        rv = first_r(self.body, "vet")
        model = {"t": "p", "id": self.pids[1], "items": [
            {"x": "vet", "r": rv, "p": {"b": True, "u": True, "color": "FF0000", "sz": 14, "bg": "FFFF00",
                                       "va": "sup", "s": True, "i": True}}]}
        self.doc.sync(self.r["gen"], {"body": [{"id": self.pids[0]}, model, {"id": self.pids[2]}]})
        rPr = roundtrip(self.doc).paragraphs[1].runs[0]._r.rPr
        names = [X.local(c) for c in rPr]
        self.assertEqual(names, sorted(names, key=X.RPR_ORDER.index))
        self.assertIn("highlight", names)


class MarkerTests(unittest.TestCase):
    def test_bookmark_and_field_survive_edit(self):
        def fn(d):
            p = d.add_paragraph("")
            p._p.append(parse_xml('<w:bookmarkStart xmlns:w="%s" w:id="7" w:name="hier"/>' % W))
            p.add_run("Pagina ")
            p._p.append(parse_xml('<w:r xmlns:w="%s"><w:fldChar w:fldCharType="begin"/></w:r>' % W))
            p._p.append(parse_xml('<w:r xmlns:w="%s"><w:instrText> PAGE </w:instrText></w:r>' % W))
            p._p.append(parse_xml('<w:r xmlns:w="%s"><w:fldChar w:fldCharType="separate"/></w:r>' % W))
            p.add_run("3")
            p._p.append(parse_xml('<w:r xmlns:w="%s"><w:fldChar w:fldCharType="end"/></w:r>' % W))
            p._p.append(parse_xml('<w:bookmarkEnd xmlns:w="%s" w:id="7"/>' % W))
        doc = build(fn)
        r = doc.render_all()
        body = r["containers"][0]["html"]
        self.assertNotIn("fldChar", body)
        pid = ids_in(body)[0]
        r1 = first_r(body, "Pagina ")
        r2 = first_r(body, "3")
        doc.sync(r["gen"], {"body": [{"t": "p", "id": pid, "items": [
            {"x": "Blad ", "r": r1, "p": {}}, {"x": "3", "r": r2, "p": {}}]}]})
        xml = roundtrip(doc).paragraphs[0]._p.xml
        for needle in ("bookmarkStart", "bookmarkEnd", 'fldCharType="begin"', "PAGE", 'fldCharType="end"'):
            self.assertIn(needle, xml)
        self.assertLess(xml.index("Blad"), xml.index('fldCharType="begin"'))

    def test_comment_range_stays_with_its_text(self):
        def fn(d):
            p = d.add_paragraph("Met opmerking ")
            p._p.append(parse_xml('<w:commentRangeStart xmlns:w="%s" w:id="0"/>' % W))
            p.add_run("hier")
            p._p.append(parse_xml('<w:commentRangeEnd xmlns:w="%s" w:id="0"/>' % W))
            p.add_run(" verder.")
        doc = build(fn)
        r = doc.render_all()
        body = r["containers"][0]["html"]
        pid = ids_in(body)[0]
        r0, r1, r2 = first_r(body, "Met opmerking "), first_r(body, "hier"), first_r(body, " verder.")
        for _ in range(2):  # ook na een tweede bewerking zonder nieuwe weergave
            doc.sync(r["gen"], {"body": [{"t": "p", "id": pid, "items": [
                {"x": "Met nog een opmerking ", "r": r0, "p": {}}, {"x": "hier", "r": r1, "p": {}},
                {"x": " verder.", "r": r2, "p": {}}]}]})
            xml = roundtrip(doc).paragraphs[0]._p.xml
            self.assertRegex(xml, r"commentRangeStart[^>]*/>\s*<w:r>\s*<w:t>hier</w:t>")
            self.assertRegex(xml, r"hier</w:t>\s*</w:r>\s*<w:commentRangeEnd")

    def test_orphan_field_is_repaired_on_save(self):
        def fn(d):
            p = d.add_paragraph("x")
            p._p.append(parse_xml('<w:r xmlns:w="%s"><w:fldChar w:fldCharType="begin"/></w:r>' % W))
        doc = build(fn)
        xml = roundtrip(doc).paragraphs[0]._p.xml
        self.assertNotIn("fldChar", xml)


class StructureTests(unittest.TestCase):
    def _doc(self):
        def fn(d):
            d.add_paragraph("Voor")
            t = d.add_table(rows=2, cols=2)
            for i, c in enumerate(t._cells):
                c.text = "c%d" % i
            d.add_paragraph("Na")
        doc = build(fn)
        return doc, doc.render_all()

    def test_table_ops(self):
        doc, r = self._doc()
        body = r["containers"][0]["html"]
        cell = ids_in(body, "td")[0]
        h = doc.table_op(cell, "row_below")
        self.assertEqual(len(roundtrip(doc).tables[0].rows), 3)
        cell = ids_in(h, "td")[0]
        h = doc.table_op(cell, "col_right")
        t = roundtrip(doc).tables[0]
        self.assertEqual(len(t.columns), 3)
        self.assertEqual(len(t._tbl.tblGrid.findall(qn("w:gridCol"))), 3)
        cell = ids_in(h, "td")[1]
        doc.table_op(cell, "col_delete")
        self.assertEqual(len(roundtrip(doc).tables[0].columns), 2)
        self.assertIsNone(doc.table_op(ids_in(doc.render_all()["containers"][0]["html"], "td")[0],
                                       "table_delete"))
        self.assertEqual(len(roundtrip(doc).tables), 0)

    def test_cell_edit_via_sync(self):
        doc, r = self._doc()
        body = r["containers"][0]["html"]
        pids = ids_in(body)
        tid = ids_in(body, "table")[0]
        trs = ids_in(body, "tr")
        tds = ids_in(body, "td")
        cellp = pids[1:5]
        tbl = {"t": "tbl", "id": tid, "rows": [
            {"id": trs[0], "cells": [{"id": tds[0], "blocks": [{"t": "p", "id": cellp[0], "items": [
                {"x": "nieuw", "r": None, "p": {}}]}]}, {"id": tds[1], "blocks": [{"id": cellp[1]}]}]},
            {"id": trs[1], "cells": [{"id": tds[2], "blocks": [{"id": cellp[2]}]},
                                     {"id": tds[3], "blocks": [{"id": cellp[3]}]}]}]}
        doc.sync(r["gen"], {"body": [{"id": pids[0]}, tbl, {"id": pids[5]}]})
        t = roundtrip(doc).tables[0]
        self.assertEqual(t.cell(0, 0).text, "nieuw")
        self.assertEqual(t.cell(1, 1).text, "c3")

    def test_insert_table_and_lists(self):
        doc, r = self._doc()
        pid = ids_in(r["containers"][0]["html"])[0]
        h = doc.insert_table(pid, 2, 3)
        self.assertIn("<table", h)
        self.assertEqual(len(roundtrip(doc).tables), 2)
        nid = doc.ensure_list("bullet")
        nid2 = doc.ensure_list("number", fresh=True)
        self.assertNotEqual(nid, nid2)
        nums = doc.sheet.numbering()
        self.assertEqual(nums[nid]["levels"]["0"]["fmt"], "bullet")
        self.assertEqual(nums[nid2]["levels"]["0"]["fmt"], "decimal")

    def test_list_on_paragraph(self):
        doc, r = self._doc()
        pids = ids_in(r["containers"][0]["html"])
        nid = doc.ensure_list("bullet")
        doc.sync(r["gen"], {"body": [{"t": "p", "id": pids[0], "num": [nid, 1],
                                      "items": [{"x": "Voor", "r": None, "p": {}}]}]
                            + [{"id": i} for i in ids_in(r["containers"][0]["html"], "table")] + [{"id": pids[-1]}]})
        p = roundtrip(doc).paragraphs[0]._p
        self.assertEqual(p.pPr.numPr.numId.val, int(nid))
        self.assertEqual(p.pPr.numPr.ilvl.val, 1)

    def test_image(self):
        from PIL import Image
        doc, r = self._doc()
        buf = io.BytesIO()
        Image.new("RGB", (4000, 1000), (0, 0, 255)).save(buf, "PNG")
        h = doc.new_image(buf.getvalue(), "body")
        aid = re.search(r'data-a="([^"]+)"', h).group(1)
        blob, ctype = doc.media(aid)
        self.assertEqual(ctype, "image/png")
        pid = ids_in(r["containers"][0]["html"])[0]
        body = r["containers"][0]["html"]
        doc.sync(r["gen"], {"body": [{"t": "p", "id": pid, "items": [{"a": aid}]}, {"id": ids_in(body, "table")[0]},
                                     {"id": ids_in(body)[-1]}]})
        d = roundtrip(doc)
        self.assertEqual(len(d.inline_shapes), 1)
        self.assertLessEqual(d.inline_shapes[0].width, doc.content_width_emu())

    def test_tracked_changes(self):
        def fn(d):
            p = d.add_paragraph("Begin ")
            p._p.append(parse_xml('<w:ins xmlns:w="%s" w:id="1" w:author="A"><w:r><w:t>erbij</w:t></w:r></w:ins>' % W))
            p._p.append(parse_xml('<w:del xmlns:w="%s" w:id="2" w:author="A"><w:r><w:delText>weg</w:delText>'
                                  '</w:r></w:del>' % W))
        doc = build(fn)
        r = doc.render_all()
        self.assertTrue(r["tracked"])
        self.assertIn('contenteditable="false"', r["containers"][0]["html"])
        doc.resolve_tracked(True)
        self.assertEqual(roundtrip(doc).paragraphs[0].text, "Begin erbij")
        doc.undo()
        doc.resolve_tracked(False)
        self.assertEqual(roundtrip(doc).paragraphs[0].text, "Begin weg")


class ExportTests(unittest.TestCase):
    def test_markdown_and_text(self):
        def fn(d):
            d.add_heading("Hoofdstuk", 1)
            p = d.add_paragraph("Een ")
            p.add_run("vet").bold = True
            p.add_run(" woord.")
            d.add_paragraph("punt", style="List Bullet")
        doc = build(fn)
        md = doc.to_markdown()
        self.assertIn("# Hoofdstuk", md)
        self.assertIn("Een **vet** woord.", md)
        self.assertIn("- punt", md)
        self.assertIn("Hoofdstuk", doc.to_text())

    def test_save_and_reopen(self):
        doc = build(lambda d: d.add_paragraph("Hallo"))
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "uit.docx")
        doc.save(path)
        self.assertFalse(doc.dirty)
        doc2 = D.Doc().load_path(path)
        self.assertEqual(doc2.to_text().strip(), "Hallo")

    def test_txt_import_and_unsupported(self):
        doc = D.Doc().load_bytes("regel 1\nregel 2".encode("utf-8"), "notities.txt")
        self.assertEqual(doc.filename, "notities.docx")
        self.assertIsNone(doc.path)
        self.assertEqual(doc.to_text().split("\n")[:2], ["regel 1", "regel 2"])
        with self.assertRaises(D.UserError):
            D.Doc().load_bytes(b"xx", "plaatje.png")
        with self.assertRaises(D.UserError):
            D.Doc().load_bytes(b"geen zip", "kapot.docx")

    def test_header_add(self):
        d = docx.Document()
        buf = io.BytesIO()
        d.save(buf)
        doc = D.Doc().load_bytes(buf.getvalue(), "x.docx")
        r = doc.render_all()
        if not r["has"]["hdr"]:
            doc.add_header_footer("hdr")
            self.assertTrue(doc.render_all()["has"]["hdr"])


if __name__ == "__main__":
    unittest.main()
