import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from export import export_quarter


class QuarterlyReportTests(unittest.TestCase):
    def export(self, records, **options):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "report.xlsx"
        export_quarter(records, path, **options)
        with path.open("rb") as file:
            book = load_workbook(file)
        self.addCleanup(book.close)
        return book["月报"]

    def test_finance_keeps_original_layout_and_formulas(self):
        sheet = self.export({3: 0, 1: 120})
        self.assertEqual([sheet[f"B{i}"].value for i in (2, 3, 4)], [120, 0, 0])
        self.assertTrue(all(sheet[f"C{i}"].value is None for i in range(1, 5)))
        self.assertEqual(sheet["D2"].value, "=SUM(B2:B4)")
        self.assertEqual(sheet["D3"].value, "=AVERAGE(B2:B4)")

    def test_leadership_distinguishes_missing_and_reported_zero(self):
        sheet = self.export({3: 0, 1: 120}, show_reporting_status=True)
        self.assertEqual(sheet["C1"].value, "填报状态")
        self.assertEqual([row[:3] for row in list(sheet.values)[1:]],
                         [(1, 120, "已上报"), (2, 0, "未上报"), (3, 0, "已上报")])
        for row in (2, 3, 4):
            self.assertEqual(sheet[f"B{row}"].number_format, "#,##0.00")
        self.assertEqual(sheet["D3"].value, "=AVERAGE(B2:B4)")

    def test_empty_quarter(self):
        sheet = self.export({}, show_reporting_status=True)
        self.assertEqual([row[:3] for row in list(sheet.values)[1:]],
                         [(month, 0, "未上报") for month in (1, 2, 3)])

    def test_outside_quarter_keeps_original_path(self):
        sheet = self.export({4: 80, 2: 25}, show_reporting_status=True)
        self.assertEqual([row[:3] for row in list(sheet.values)[1:]],
                         [(2, 25, None), (4, 80, None)])
