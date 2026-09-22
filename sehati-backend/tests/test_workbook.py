"""Read-only workbook checks. Run with `python -m unittest discover -s tests`."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path


def test_utf16_entity_declaration_is_rejected():
    from app.workbook import _xml_root, WorkbookValidationError
    import pytest
    payload = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE a [<!ENTITY x "unsafe">]><a>&x;</a>'.encode('utf-16')
    with pytest.raises(WorkbookValidationError):
        _xml_root(payload)
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

import openpyxl

from app.workbook import HEADERS, WorkbookValidationError, analyze_workbook


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "sample.xlsx"

    def tearDown(self):
        self.folder.cleanup()

    def fixture(self):
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Sheet1"
        sheet["C3"] = ": (04 Januari s.d. 24 Januari) 2025"
        sheet["C4"] = "PRIVATE-INVOICE-001"
        for index, header in enumerate(HEADERS, start=1):
            sheet.cell(6, index, header)
        values = [1, "PRIVATE TRANSPORTER", "SECRET-DO-1", "PRIVATE PLATE",
                  datetime(2025, 1, 5), datetime(2025, 1, 6), datetime(2025, 1, 6),
                  "PRIVATE ORIGIN", "PRIVATE DESTINATION", "PRIVATE DISTRIBUTOR",
                  45, "BOX", 100, 23.5, 123456789, None, "=SUM(O7:P7)", None, None]
        for index, item in enumerate(values, start=1):
            sheet.cell(7, index, item)
        book.save(self.path)
        return book

    def test_minimal_report_is_read_only_private_and_preview_only(self):
        self.fixture()
        before = sha256(self.path.read_bytes()).hexdigest()
        report = analyze_workbook(self.path)
        self.assertEqual(report["summary"]["do_rows"], 1)
        self.assertEqual(report["summary"]["distinct_do"], 1)
        self.assertFalse(report["commit_enabled"])
        self.assertEqual(report["status"], "preview_only")
        self.assertEqual(report["periods"][0]["period_start"], "2025-01-04")
        self.assertEqual(report["periods"][0]["period_end"], "2025-01-24")
        self.assertEqual(before, sha256(self.path.read_bytes()).hexdigest())
        text = json.dumps(report)
        for secret in ("SECRET-DO-1", "PRIVATE-INVOICE", "PRIVATE PLATE", "PRIVATE DISTRIBUTOR", "123456789", "SUM(O7"):
            self.assertNotIn(secret, text)

    def test_duplicate_headers_block_interpretation(self):
        book = self.fixture()
        book.active["D6"] = "No. D/O"
        book.save(self.path)
        report = analyze_workbook(self.path)
        codes = {issue["code"] for issue in report["issues"]}
        self.assertTrue({"DUPLICATE_HEADERS", "HEADER_MISMATCH"}.issubset(codes))
        self.assertEqual(report["summary"]["do_rows"], 0)

    def test_missing_transporter_duplicate_id_and_unknown_rows_are_not_lost(self):
        book = self.fixture()
        sheet = book.active
        sheet["B7"] = None
        for col in range(1, 20):
            sheet.cell(8, col, sheet.cell(7, col).value)
        sheet["D8"] = "CHANGED PRIVATE PLATE"
        sheet["P9"] = 100
        sheet["R9"] = "PRIVATE CHARGE NOTE"
        sheet["A10"] = "UNKNOWN PRIVATE NOTE"
        sheet["A11"] = "GRAND TOTAL"
        sheet["Q11"] = 100
        book.save(self.path)
        report = analyze_workbook(self.path)
        self.assertEqual(report["summary"]["do_rows"], 2)
        self.assertEqual(report["summary"]["distinct_do"], 1)
        codes = {issue["code"] for issue in report["issues"]}
        self.assertTrue({"MISSING_TRANSPORTER", "REPEATED_DO", "UNLINKED_CHARGE", "UNCLASSIFIED_ROW", "SUMMARY_ROWS_EXCLUDED"}.issubset(codes))
        self.assertNotIn("UNKNOWN PRIVATE NOTE", json.dumps(report))

    def test_invalid_dates_and_numeric_ids_are_flagged(self):
        book = self.fixture()
        sheet = book.active
        sheet["C7"] = 1234
        sheet["E7"] = "not a date"
        book.save(self.path)
        report = analyze_workbook(self.path)
        codes = {issue["code"] for issue in report["issues"]}
        self.assertTrue({"DATE_TYPE", "NUMERIC_IDENTIFIER"}.issubset(codes))

    def test_not_zip_or_wrong_extension_rejected(self):
        self.path.write_text("not an Excel workbook", encoding="utf-8")
        with self.assertRaises(WorkbookValidationError):
            analyze_workbook(self.path)
        self.fixture()
        with self.assertRaises(WorkbookValidationError):
            analyze_workbook(self.path, "sample.xlsm")

    def test_unsafe_archive_names_rejected(self):
        with ZipFile(self.path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("../escape.xml", "<test/>")
        with self.assertRaisesRegex(WorkbookValidationError, "Unsafe"):
            analyze_workbook(self.path)

    def test_macros_and_external_links_rejected(self):
        for part in ("xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml"):
            with self.subTest(part=part):
                self.fixture()
                with ZipFile(self.path, "a") as archive:
                    archive.writestr(part, "<test/>")
                with self.assertRaises(WorkbookValidationError):
                    analyze_workbook(self.path)

    def test_external_relationship_and_dtd_rejected(self):
        for content in (
            '<Relationships><Relationship TargetMode="External" Target="https://example.com/private"/></Relationships>',
            '<!DOCTYPE foo [<!ENTITY test "expansion">]><foo>&test;</foo>',
        ):
            with self.subTest(content=content[:20]):
                self.fixture()
                with ZipFile(self.path, "a") as archive:
                    archive.writestr("xl/review.rels", content)
                with self.assertRaises(WorkbookValidationError):
                    analyze_workbook(self.path)

    def test_malformed_xml_rejected(self):
        self.fixture()
        with ZipFile(self.path, "a") as archive:
            archive.writestr("xl/malformed.xml", "<broken")
        with self.assertRaises(WorkbookValidationError):
            analyze_workbook(self.path)

    def test_sparse_extreme_dimensions_rejected(self):
        book = self.fixture()
        book.active["A1000000"] = "tail"
        book.save(self.path)
        with self.assertRaises(WorkbookValidationError):
            analyze_workbook(self.path)

    def test_supplied_nine_period_workbook_when_available(self):
        source = Path.home() / "Downloads" / "BRIDGESTONE 2025.xlsx"
        if not source.is_file():
            self.skipTest("User-supplied workbook is not available on this computer.")
        before = sha256(source.read_bytes()).hexdigest()
        report = analyze_workbook(source)
        self.assertEqual(report["summary"]["sheets"], 9)
        self.assertEqual(report["summary"]["do_rows"], 826)
        self.assertEqual(report["summary"]["distinct_do"], 819)
        self.assertEqual([period["do_rows"] for period in report["periods"]], [51, 77, 99, 59, 111, 121, 112, 92, 104])
        self.assertEqual(report["periods"][0]["period_start"], "2025-01-04")
        self.assertEqual(report["periods"][-1]["period_end"], "2025-09-23")
        duplicates = [issue for issue in report["issues"] if issue["code"] == "REPEATED_DO"]
        self.assertEqual(len(duplicates), 6)
        self.assertTrue(any(issue.get("sheet") == "Sheet3" and "B94" in issue.get("cells", []) for issue in report["issues"]))
        self.assertTrue(any(issue.get("sheet") == "Sheet3" and {"N68", "N69"}.issubset(issue.get("cells", [])) for issue in report["issues"]))
        self.assertTrue(any(issue["code"] == "UNLINKED_CHARGE" and issue.get("sheet") == "Sheet5" for issue in report["issues"]))
        self.assertEqual(before, sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
