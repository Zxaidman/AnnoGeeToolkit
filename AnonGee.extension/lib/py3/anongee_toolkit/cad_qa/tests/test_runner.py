# -*- coding: utf-8 -*-
"""Running a file or a folder, and every way that can go wrong.

A BATCH MUST SURVIVE ITS WORST FILE. Forty drawings arrive a month; one
corrupt one must not take the other thirty-nine with it. Every failure path
here therefore asserts a Report came back, not that an exception was raised.
"""

import os
import shutil
import tempfile
import unittest

import _support
from _support import context, rect
from cad_qa import runner


class FailurePathTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_test_")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _write(self, name, content=b"x"):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_a_missing_file_is_a_report_not_an_exception(self):
        report = runner.run_file(os.path.join(self.folder, "nope.dxf"))
        self.assertEqual(report.worst, "Error")
        self.assertIn("no such file", report.findings[0].message)

    def test_a_folder_passed_as_a_file_is_reported(self):
        report = runner.run_file(self.folder)
        self.assertIn("not a file", report.findings[0].message)

    def test_an_empty_file_is_reported(self):
        report = runner.run_file(self._write("empty.dxf", b""))
        self.assertIn("empty", report.findings[0].message)

    def test_a_dwg_is_told_how_to_become_a_dxf(self):
        """No write-back to CAD means one reader; the message says so."""
        report = runner.run_file(self._write("plan.dwg"))
        self.assertIn("ODA File Converter", report.findings[0].message)

    def test_a_corrupt_dxf_is_a_report_not_a_crash(self):
        path = self._write("broken.dxf", b"this is not a DXF at all\n" * 50)
        report = runner.run_file(path)
        self.assertEqual(report.worst, "Error")
        self.assertTrue(report.findings)

    def test_a_failed_report_has_the_same_shape_as_any_other(self):
        """The batch JSON has to stay parseable whatever went wrong."""
        payload = runner.run_file(os.path.join(self.folder, "no.dxf")).to_dict()
        for key in ("source", "counts", "stats", "findings", "worst"):
            self.assertIn(key, payload)


class FolderTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_test_")
        self.nested = os.path.join(self.folder, "sub")
        os.makedirs(self.nested)
        for name in ("b.dxf", "a.dxf", "notes.txt"):
            with open(os.path.join(self.folder, name), "wb") as handle:
                handle.write(b"x")
        with open(os.path.join(self.nested, "c.dxf"), "wb") as handle:
            handle.write(b"x")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_only_dxf_files_are_picked_up(self):
        names = [os.path.basename(p) for p in runner.drawings_in(self.folder)]
        self.assertEqual(names, ["a.dxf", "b.dxf"])

    def test_the_order_is_stable_not_filesystem_order(self):
        """A sweep whose order varies cannot be diffed between intakes."""
        self.assertEqual(runner.drawings_in(self.folder),
                         runner.drawings_in(self.folder))

    def test_recursive_descends(self):
        names = sorted(os.path.basename(p) for p in
                       runner.drawings_in(self.folder, recursive=True))
        self.assertEqual(names, ["a.dxf", "b.dxf", "c.dxf"])

    def test_a_sweep_reports_every_drawing_even_when_all_fail(self):
        reports = runner.run_folder(self.folder)
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(r.worst == "Error" for r in reports))


class SummaryTests(unittest.TestCase):

    def test_a_summary_counts_drawings_and_severities(self):
        good = runner.run_context(_support.plan())
        bad = runner.run_context(context([rect("S-COLS", 0, 0, 20, 10)]))
        totals = runner.summarise([good, bad])
        self.assertEqual(totals["drawings"], 2)
        self.assertGreaterEqual(totals["Error"], 1)
        self.assertEqual(totals["with_errors"], 1)

    def test_a_clean_drawing_counts_as_clean(self):
        """plan() trips nothing except the single-plan note, which is Info."""
        report = runner.run_context(_support.plan())
        self.assertEqual(report.counts()["Error"], 0)
        self.assertEqual(report.counts()["Warning"], 0)
        self.assertEqual([f.rule for f in report.findings], ["S006"])


class ContextRunTests(unittest.TestCase):

    def test_running_a_context_carries_the_stats_through(self):
        report = runner.run_context(_support.plan())
        self.assertEqual(report.stats["records"], 7)
        self.assertEqual(report.source, "fake.dxf")

    def test_every_family_contributes(self):
        """A run that silently lost a family would still look like a run."""
        report = runner.run_context(context([rect("S-COLS", 0, 0, 20, 10)]))
        families = set(f.rule[0] for f in report.findings)
        self.assertTrue({"L", "G"}.issubset(families), families)


if __name__ == "__main__":
    unittest.main()
