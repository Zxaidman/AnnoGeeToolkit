# -*- coding: utf-8 -*-
"""The severity model: aggregation, ordering and the JSON shape."""

import unittest

import _support                                            # noqa: F401
from cad_qa.findings import (Finding, Report, MAX_EXAMPLES, SEVERITY_ERROR,
                             SEVERITY_WARNING, SEVERITY_INFO)


class FindingTests(unittest.TestCase):

    def test_examples_are_capped(self):
        """A layer with a thousand offenders must not carry a thousand rows."""
        finding = Finding("L001", SEVERITY_WARNING, "many",
                          examples=[str(n) for n in range(50)])
        self.assertEqual(len(finding.examples), MAX_EXAMPLES)

    def test_empty_fields_are_left_out_of_the_json(self):
        payload = Finding("L001", SEVERITY_WARNING, "bare").to_dict()
        self.assertEqual(sorted(payload), ["message", "rule", "severity"])

    def test_a_location_is_rounded_to_whole_millimetres(self):
        payload = Finding("G005", SEVERITY_WARNING, "x",
                          where=(1234.6, -99.4)).to_dict()
        self.assertEqual((payload["x"], payload["y"]), (1235, -99))

    def test_a_count_of_zero_survives_into_the_json(self):
        """0 is a real answer ('no columns') and must not be dropped as falsy."""
        payload = Finding("L003", SEVERITY_ERROR, "none", count=0).to_dict()
        self.assertEqual(payload["count"], 0)

    def test_sorting_puts_errors_first_then_rule_then_subject(self):
        findings = [
            Finding("L001", SEVERITY_WARNING, "w", subject="B"),
            Finding("L001", SEVERITY_WARNING, "w", subject="A"),
            Finding("S006", SEVERITY_INFO, "i"),
            Finding("M002", SEVERITY_ERROR, "e"),
        ]
        order = [(f.rule, f.subject) for f in
                 sorted(findings, key=lambda f: f.sort_key())]
        self.assertEqual(order, [("M002", None), ("L001", "A"),
                                 ("L001", "B"), ("S006", None)])

    def test_sorting_survives_a_missing_subject(self):
        """None against a string raises on Python 3 if the key is naive."""
        findings = [Finding("L001", SEVERITY_WARNING, "w", subject=None),
                    Finding("L001", SEVERITY_WARNING, "w", subject="A")]
        sorted(findings, key=lambda f: f.sort_key())      # must not raise


class ReportTests(unittest.TestCase):

    def test_counts_show_every_severity_including_zero(self):
        report = Report("x.dxf")
        report.add(Finding("L001", SEVERITY_WARNING, "w"))
        self.assertEqual(report.counts(),
                         {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1,
                          SEVERITY_INFO: 0})

    def test_worst_is_none_for_a_clean_drawing(self):
        self.assertIsNone(Report("x.dxf").worst)

    def test_worst_is_the_highest_severity_present(self):
        report = Report("x.dxf")
        report.extend([Finding("S006", SEVERITY_INFO, "i"),
                       Finding("M002", SEVERITY_ERROR, "e")])
        self.assertEqual(report.worst, SEVERITY_ERROR)

    def test_the_json_is_ordered_worst_first(self):
        report = Report("x.dxf")
        report.extend([Finding("S006", SEVERITY_INFO, "i"),
                       Finding("M002", SEVERITY_ERROR, "e")])
        rules_out = [f["rule"] for f in report.to_dict()["findings"]]
        self.assertEqual(rules_out, ["M002", "S006"])

    def test_the_json_carries_the_stats_a_reader_needs(self):
        report = Report("x.dxf", stats={"records": 12})
        self.assertEqual(report.to_dict()["stats"]["records"], 12)


if __name__ == "__main__":
    unittest.main()
