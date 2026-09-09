# -*- coding: utf-8 -*-
"""The report itself: sheets, the workbook, the sidecar, and stage D.

Stage D is exercised against a REAL cad2bim export -- 13 storeys and 3.7 MB of
it -- rather than a hand-made one, because the thing most likely to break that
parser is the shape of an actual file, and a fixture written from the schema
would only ever confirm the schema I read.
"""

import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402

config, model, run, sheets_module, sidecar = _loader.load(
    "config", "model", "run", "sheets", "sidecar")
space, classify = _loader.load("space", "classify")
cad2bim_json, dxf_raw, dxf_parsed = _loader.load(
    "readers.cad2bim_json", "readers.dxf_raw", "readers.dxf_parsed")
cad2bim_dxf_reader = _loader.load_cad2bim("readers.dxf_reader")
cad2bim_layers = _loader.load_cad2bim("classify.layers")

FIXTURE = _loader.fixture("audit_plan.dxf")

#: A real multi-storey export shipped with cad2bim's own fixtures. Absent from a
#: shallow checkout, so the tests that use it skip rather than fail.
_EXPORTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cad2bim", "tests", "fixtures", "cad", ".json")


def real_export():
    matches = sorted(glob.glob(os.path.join(_EXPORTS, "*_with_textmode.json")))
    return matches[-1] if matches else None


def build_dxf_report():
    if not os.path.exists(FIXTURE):
        sys.path.insert(0, _loader.FIXTURES)
        import make_audit_plan
        make_audit_plan.build(FIXTURE)
    subject = space.Space(1.0)
    captures = {
        config.STAGE_DXF_RAW: dxf_raw.read(FIXTURE, subject),
        config.STAGE_DXF_PARSED: dxf_parsed.read(FIXTURE, subject,
                                                 reader=cad2bim_dxf_reader),
    }
    classify.apply(captures, layers=cad2bim_layers)
    return run.build_report(captures, subject), captures


class ClassificationTests(unittest.TestCase):

    def test_layers_are_routed_by_cad2bim_s_own_classifier(self):
        _report, captures = build_dxf_report()
        found = set()
        for capture in captures.values():
            found.update(item.category for item in capture.items if item.category)
        self.assertIn("column", found)
        self.assertIn("beam", found)
        self.assertIn("grid", found)

    def test_stages_that_bring_their_own_category_are_left_alone(self):
        built = model.Capture(config.STAGE_MODEL, "m")
        built.add(model.AuditItem(config.STAGE_MODEL, "element",
                                  layer="OST_StructuralColumns", category="column"))
        classify.apply({config.STAGE_MODEL: built}, layers=cad2bim_layers)
        self.assertEqual(built.items[0].category, "column")


class SheetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.report, cls.captures = build_dxf_report()
        cls.sheets = run.build_sheets(cls.report)
        cls.by_name = {sheet.name: sheet for sheet in cls.sheets}

    def test_every_promised_sheet_is_present(self):
        for name in ("Summary", "Findings", "Reconciliation", "Layer census",
                     "Columns", "Beams", "Slabs", "Footings", "Walls", "Stairs",
                     "Grids", "DXF entities", "DXF text", "DXF hatches",
                     "Revit link geometry", "Model elements",
                     "Transform & settings"):
            self.assertIn(name, self.by_name, "missing sheet: " + name)

    def test_every_row_matches_its_header_width(self):
        for sheet in self.sheets:
            for index, row in enumerate(sheet.rows):
                self.assertEqual(
                    len(row), len(sheet.columns),
                    "{0} row {1}: {2} cells for {3} columns".format(
                        sheet.name, index, len(row), len(sheet.columns)))

    def test_the_per_category_sheets_share_the_reconciliation_columns(self):
        expected = self.by_name["Reconciliation"].columns
        for name in ("Columns", "Beams", "Grids"):
            self.assertEqual(self.by_name[name].columns, expected)

    def test_the_category_sheets_partition_the_reconciliation(self):
        """Every categorised member appears on exactly one category sheet."""
        counted = sum(len(self.by_name[name].rows)
                      for name, _keys in config.CATEGORY_SHEETS)
        categorised = sum(1 for group in self.report.groups
                          if any(group.category in keys
                                 for _name, keys in config.CATEGORY_SHEETS))
        self.assertEqual(counted, categorised)

    def test_findings_are_listed_worst_first(self):
        severity = self.by_name["Findings"].columns.index("severity")
        ranks = [config.SEVERITY_ORDER[row[severity]]
                 for row in self.by_name["Findings"].rows]
        self.assertEqual(ranks, sorted(ranks))

    def test_a_capped_sheet_says_so_instead_of_truncating_silently(self):
        sheet = sheets_module.Sheet("T", ["a"], [[n] for n in range(50)])
        sheet.cap(10)
        self.assertEqual(len(sheet.rows), 10)
        self.assertEqual(sheet.omitted, 40)
        self.assertTrue(any("omitted" in note for note in sheet.notes))

    def test_the_reconciliation_sorts_by_position_even_without_a_link(self):
        """A DXF-only run has no Revit coordinates; the sheet must still order.

        Without the fallback every row sorts on a column of blanks and the sheet
        keeps read order, which differs between runs and defeats diffing them.
        """
        sheet = self.by_name["Reconciliation"]
        self.assertTrue(sheet.rows)
        x_revit = sheet.columns.index("x_revit_mm")
        x_dxf = sheet.columns.index("x_dxf_mm")
        self.assertTrue(all(row[x_revit] is None for row in sheet.rows))
        severity = sheet.columns.index("severity")
        keys = [(config.SEVERITY_ORDER[row[severity]], row[0], row[2] or "",
                 row[x_dxf] or 0.0) for row in sheet.rows]
        self.assertEqual(keys, sorted(keys))

    def test_the_settings_sheet_records_the_thresholds_used(self):
        text = str(self.by_name["Transform & settings"].rows)
        for key in ("size_tol_mm", "position_tol_mm", "match_radius_mm"):
            self.assertIn(key, text)


class ExportNameTests(unittest.TestCase):

    def test_the_plan_number_is_taken_from_the_drawing_name(self):
        name = run.export_name("C:/x/StructuralPlan-Test17-clean.dxf",
                               {config.STAGE_DXF_RAW: object()})
        self.assertIn("_audit_test17_", name)
        self.assertTrue(name.endswith(".xlsx"))

    def test_the_captured_stages_are_named_in_the_file(self):
        name = run.export_name("plan.dxf", {config.STAGE_DXF_RAW: object(),
                                            config.STAGE_MODEL: object()})
        self.assertIn("_AC.", name)

    def test_a_nameless_drawing_still_produces_a_legal_name(self):
        self.assertTrue(run.export_name("", {}).endswith("_none.xlsx"))


class WorkbookTests(unittest.TestCase):

    def test_the_workbook_writes_and_reads_back(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not importable in this environment")
        report, _captures = build_dxf_report()
        workbook_module = _loader.load("workbook")
        folder = tempfile.mkdtemp()
        target = os.path.join(folder, "audit.xlsx")
        workbook_module.write(target, run.build_sheets(report))
        self.assertTrue(os.path.getsize(target) > 0)

        book = openpyxl.load_workbook(target)
        self.assertIn("Summary", book.sheetnames)
        self.assertIn("Findings", book.sheetnames)
        for name in book.sheetnames:
            self.assertLessEqual(len(name), 31)

    def test_a_leading_equals_sign_can_never_become_a_formula(self):
        workbook_module = _loader.load("workbook")
        self.assertEqual(workbook_module._cell_value("=SUM(A1)"), " =SUM(A1)")

    def test_duplicate_sheet_names_are_made_unique(self):
        workbook_module = _loader.load("workbook")
        used = set()
        first = workbook_module._unique_name("Columns", used)
        second = workbook_module._unique_name("Columns", used)
        self.assertNotEqual(first, second)

    def test_csv_is_written_when_a_workbook_cannot_be(self):
        report, _captures = build_dxf_report()
        workbook_module = _loader.load("workbook")
        folder = os.path.join(tempfile.mkdtemp(), "csv")
        written = workbook_module.write_csv(folder, run.build_sheets(report))
        self.assertTrue(written)
        self.assertTrue(all(os.path.exists(path) for path in written))


class SidecarTests(unittest.TestCase):

    def test_the_sidecar_is_valid_json_and_carries_the_run(self):
        report, _captures = build_dxf_report()
        target = os.path.join(tempfile.mkdtemp(), "audit.json")
        sidecar.write(target, report)
        with open(target) as handle:
            payload = json.load(handle)
        for key in ("audit_version", "findings", "reconciliation", "captures",
                    "settings", "space", "verdict_counts"):
            self.assertIn(key, payload)
        self.assertEqual(payload["audit_version"], report.version)

    def test_an_unserialisable_value_never_costs_a_finished_run_its_report(self):
        class Foreign(object):
            def __repr__(self):
                return "<foreign>"
        report, _captures = build_dxf_report()
        report.diagnostics["leaked"] = Foreign()
        target = os.path.join(tempfile.mkdtemp(), "audit.json")
        sidecar.write(target, report)
        with open(target) as handle:
            self.assertIn("foreign", json.load(handle)["diagnostics"]["leaked"])


class RealExportTests(unittest.TestCase):
    """Stage D against a genuine 13-storey cad2bim export."""

    @classmethod
    def setUpClass(cls):
        cls.path = real_export()
        if not cls.path:
            raise unittest.SkipTest("no cad2bim export fixture in this checkout")
        cls.capture = cad2bim_json.read(cls.path, space.Space(1.0))

    def test_a_real_export_parses_without_a_single_error(self):
        self.assertEqual(self.capture.errors, [])
        self.assertTrue(self.capture.items)

    def test_every_storey_is_read(self):
        self.assertGreater(self.capture.meta["storey_count"], 1)
        levels = set(item.level for item in self.capture.items if item.level)
        self.assertEqual(len(levels), self.capture.meta["storey_count"])

    def test_placed_members_carry_a_size_and_a_position(self):
        placed = [item for item in self.capture.items
                  if item.extra.get("role") == "placed" and item.category == "column"]
        self.assertTrue(placed)
        for item in placed[:50]:
            self.assertIsNotNone(item.centroid_revit)
            self.assertTrue(item.plan_size_mm[1] > 0)

    def test_geometry_handed_to_the_builders_is_kept_apart_from_placed_members(self):
        roles = set(item.extra.get("role") for item in self.capture.items)
        self.assertIn("placed", roles)
        self.assertIn("builder_input", roles)
        self.assertLess(self.capture.meta["placed_items"], len(self.capture.items))

    def test_geometry_the_run_refused_is_kept(self):
        """cad2bim's own record of what it looked at and declined."""
        self.assertTrue(self.capture.meta.get("dropped_raw"))

    def test_a_missing_file_is_a_recorded_error_not_an_exception(self):
        capture = cad2bim_json.read("/no/such/export.json", space.Space(1.0))
        self.assertEqual(capture.items, [])
        self.assertEqual(len(capture.errors), 1)


if __name__ == "__main__":
    unittest.main()
