# -*- coding: utf-8 -*-
"""The three output formats.

THE JSON IS A CONTRACT (utilities 4 and 6 read it), so its tests are about
shape and stability rather than about looking right. The console and the
workbook are for people and are tested for the things people notice: the
denominator being present, and nothing raising on an empty report.
"""

import json
import os
import shutil
import tempfile
import unittest

import _support
from _support import context, rect
from cad_qa import report_console, report_excel, report_json, runner
from cad_qa.findings import Finding, Report, SEVERITY_ERROR, SEVERITY_WARNING


def _report():
    return runner.run_context(context([rect("S-COLS", 0, 0, 20, 10)],
                                      source="broken.dxf"))


class ConsoleTests(unittest.TestCase):

    def test_the_measurements_come_before_the_findings(self):
        """A reader needs the denominator before the numerator."""
        lines = report_console.format_report(runner.run_context(_support.plan()))
        text = "\n".join(lines)
        self.assertLess(text.index("records on"), text.index("S006"))

    def test_a_clean_report_says_so_in_words(self):
        report = Report("clean.dxf", stats={"records": 5, "layers": 1})
        self.assertIn("No findings", "\n".join(
            report_console.format_report(report)))

    def test_guidance_can_be_turned_off(self):
        report = _report()
        with_it = report_console.format_report(report, guidance=True)
        without = report_console.format_report(report, guidance=False)
        self.assertLess(len(without), len(with_it))

    def test_a_report_that_read_nothing_does_not_claim_statistics(self):
        report = Report("gone.dxf", stats={"records": 0})
        self.assertIn("Nothing was read",
                      "\n".join(report_console.format_report(report)))

    def test_the_batch_index_puts_the_worst_drawing_first(self):
        good = runner.run_context(_support.plan())
        bad = _report()
        lines = report_console.format_batch([good, bad])
        text = "\n".join(lines)
        self.assertLess(text.index("broken.dxf"), text.index("fake.dxf"))

    def test_no_line_carries_markup(self):
        """It has to render in a terminal, pyRevit's window and an email."""
        for line in report_console.format_report(_report()):
            self.assertNotIn("\x1b", line)


class JsonTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_json_")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_payload_declares_its_schema_version(self):
        payload = report_json.build_payload(_report())
        self.assertEqual(payload["schema"], report_json.SCHEMA_VERSION)

    def test_there_is_no_timestamp_unless_one_is_asked_for(self):
        """A clock in the payload makes every run differ from every other."""
        self.assertNotIn("generated", report_json.build_payload(_report()))
        self.assertIn("generated",
                      report_json.build_payload(_report(), stamp="2026-09-11"))

    def test_two_runs_of_one_drawing_produce_identical_bytes(self):
        first = os.path.join(self.folder, "a.json")
        second = os.path.join(self.folder, "b.json")
        report_json.write_report(first, _report())
        report_json.write_report(second, _report())
        with open(first, "rb") as a, open(second, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_writing_creates_the_folder_it_needs(self):
        path = os.path.join(self.folder, "deep", "nested", "a.json")
        report_json.write_report(path, _report())
        self.assertTrue(os.path.isfile(path))

    def test_a_batch_file_carries_every_drawing_and_the_summary(self):
        reports = [_report(), runner.run_context(_support.plan())]
        path = os.path.join(self.folder, "batch.json")
        report_json.write_batch(path, reports,
                                summary=runner.summarise(reports))
        with open(path) as handle:
            payload = json.load(handle)
        self.assertEqual(len(payload["drawings"]), 2)
        self.assertEqual(payload["summary"]["drawings"], 2)

    def test_every_finding_field_survives_the_round_trip(self):
        report = Report("x.dxf")
        report.add(Finding("G005", SEVERITY_WARNING, "msg", subject="S-COLS",
                           count=3, examples=["a", "b"], where=(10.0, 20.0)))
        payload = report_json.build_payload(report)["findings"][0]
        self.assertEqual(payload["subject"], "S-COLS")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["examples"], ["a", "b"])
        self.assertEqual((payload["x"], payload["y"]), (10, 20))


class ExcelTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_xlsx_")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _book(self, reports):
        path = os.path.join(self.folder, "qa.xlsx")
        try:
            report_excel.write_workbook(path, reports)
        except report_excel.ExcelUnavailable:                # pragma: no cover
            self.skipTest("openpyxl is not installed in this environment")
        import openpyxl
        return openpyxl.load_workbook(path)

    def test_it_writes_the_three_sheets(self):
        book = self._book([_report()])
        self.assertEqual(book.sheetnames, ["SUMMARY", "FINDINGS", "RULES"])

    def test_the_rules_sheet_carries_the_whole_catalogue(self):
        """So 'what does L006 mean' is answered in the file, not by an email."""
        from cad_qa import rules
        sheet = self._book([_report()])["RULES"]
        self.assertEqual(sheet.max_row, len(rules.RULES) + 1)

    def test_every_finding_gets_a_row(self):
        report = _report()
        sheet = self._book([report])["FINDINGS"]
        self.assertEqual(sheet.max_row, len(report.findings) + 1)

    def test_a_clean_report_still_writes_a_summary_row(self):
        sheet = self._book([Report("clean.dxf", stats={"records": 1})])["SUMMARY"]
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet.cell(row=2, column=2).value, "clean")

    def test_the_summary_counts_match_the_report(self):
        report = _report()
        sheet = self._book([report])["SUMMARY"]
        self.assertEqual(sheet.cell(row=2, column=3).value,
                         report.counts()[SEVERITY_ERROR])


if __name__ == "__main__":
    unittest.main()
