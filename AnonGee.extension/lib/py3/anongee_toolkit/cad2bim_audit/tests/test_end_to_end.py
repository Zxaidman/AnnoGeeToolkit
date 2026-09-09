# -*- coding: utf-8 -*-
"""All four stages at once -- the run the button actually performs.

Until the Revit stub existed this could not be written at all: two of the four
stages could not be imported outside Revit, so the only integration test
possible was a DXF read talking to itself. Everything downstream of the readers
-- matching, verdicts, checks, the workbook -- had only ever seen stage A and D
data, and the shapes those two produce are the two most alike of the four.

The fixture is deliberately built so each verdict has exactly one cause:

    C1 at (200, 200)      drawn, linked, built correctly      -> ok
    C2 at (5300, 200)     drawn, linked, built 100 mm oversize -> size_mismatch
    C3 at (10200, 200)    drawn and linked, never built        -> missing_in_model
    C4 at (30000, 0)      built, nobody drew it                -> orphan
    the S-FND hatch       drawn, imported as a flat solid      -> a hole to compare

If a change to any stage quietly alters what the pipeline concludes, this fails
and names the verdict that moved.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402
import _revit_stub as R                               # noqa: E402

geometry_reader, elements_reader = _loader.load_revit(
    "readers.revit_geometry", "readers.revit_elements")
config, space, run, classify = _loader.load("config", "space", "run", "classify")
dxf_raw, dxf_parsed = _loader.load("readers.dxf_raw", "readers.dxf_parsed")
cad2bim_dxf_reader = _loader.load_cad2bim("readers.dxf_reader")
cad2bim_layers = _loader.load_cad2bim("classify.layers")
cad2bim_marks = _loader.load_cad2bim("classify.marks")

FT = 1.0 / 304.8
FIXTURE = _loader.fixture("audit_plan.dxf")


def ensure_fixture():
    if not os.path.exists(FIXTURE):
        sys.path.insert(0, _loader.FIXTURES)
        import make_audit_plan
        make_audit_plan.build(FIXTURE)


def link_space():
    """The DXF is in millimetres and the link places it 1:1 in the model.

    Both report spaces then carry the same numbers, which makes a fixture
    readable -- and still exercises the transform, because every Revit-read
    coordinate goes through the inverse to reach DXF space.
    """
    return space.Space(1.0, [[FT, 0, 0, 0], [0, FT, 0, 0], [0, 0, FT, 0]],
                       method="link_transform")


def rect_ft(cx, cy, width, height):
    """A rectangle centred on (cx, cy) mm, returned in internal feet."""
    half_w, half_h = width / 2.0, height / 2.0
    return [((cx - half_w) * FT, (cy - half_h) * FT, 0.0),
            ((cx + half_w) * FT, (cy - half_h) * FT, 0.0),
            ((cx + half_w) * FT, (cy + half_h) * FT, 0.0),
            ((cx - half_w) * FT, (cy + half_h) * FT, 0.0)]


def build_link(document):
    """What Revit made of the DXF: the two main columns, a beam, and the hatch.

    C3's outline is deliberately absent -- Revit's import lost it, which is the
    case cad2bim exists to work around and the audit exists to name.
    """
    columns = document.register_layer("S-COLS")
    beams = document.register_layer("S-BEAM")
    foundations = document.register_layer("S-FND")

    objects = []
    for cx, cy, w, h in ((200, 200, 400, 400), (5300, 200, 600, 400)):
        objects.append(R.polyline(rect_ft(cx, cy, w, h), style_id=columns))
    objects.append(R.line((400 * FT, 150 * FT, 0), (5000 * FT, 150 * FT, 0),
                          style_id=beams))
    objects.append(R.line((400 * FT, 250 * FT, 0), (5000 * FT, 250 * FT, 0),
                          style_id=beams))
    # The hatch, imported as a flat solid with an island preserved as a hole.
    outline = rect_ft(1500, 4500, 3000, 3000)
    hole = rect_ft(1500, 4500, 1000, 1000)
    objects.append(R.flat_solid(outline, holes=[hole], style_id=foundations,
                                volume=0.0))
    return R.ImportInstance(objects, transform=R.Transform())


def build_model(level):
    """What got built. C2 is 100 mm oversize, C3 is missing, C4 is an orphan."""
    return {
        R.BuiltInCategory.OST_StructuralColumns: [
            R.shaped_column(1, rect_ft(200, 200, 400, 400), mark="C1",
                            level=level, b_mm=400, h_mm=400),
            R.shaped_column(2, rect_ft(5300, 200, 600, 500), mark="C2",
                            level=level, b_mm=600, h_mm=500),
            R.shaped_column(4, rect_ft(30000, 0, 300, 300), mark="C4",
                            level=level, b_mm=300, h_mm=300),
        ],
        R.BuiltInCategory.OST_StructuralFraming: [
            R.beam(10, (400 * FT, 200 * FT, 0), (5000 * FT, 200 * FT, 0),
                   mark="B1", level=level),
        ],
    }


def full_report():
    ensure_fixture()
    subject = link_space()
    document = R.Document("audit end-to-end")
    link = build_link(document)
    level = R.level(70, "FIRST FLOOR")
    model_document = R.Document("audit end-to-end", by_category=build_model(level))
    model_document.register(level)
    # The link's graphics styles live on the document the link was built against.
    for style_id, style in document._styles.items():
        model_document._styles[style_id] = style

    captures = {
        config.STAGE_DXF_RAW: dxf_raw.read(FIXTURE, subject),
        config.STAGE_DXF_PARSED: dxf_parsed.read(FIXTURE, subject,
                                                 reader=cad2bim_dxf_reader),
        config.STAGE_LINK_RAW: geometry_reader.read_raw(document, link, subject),
        config.STAGE_MODEL: elements_reader.read(model_document, subject),
    }
    classify.apply(captures, layers=cad2bim_layers, marks=cad2bim_marks)
    return run.build_report(captures, subject), captures


class FourStageTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.report, cls.captures = full_report()
        cls.verdicts = dict()
        for group, verdict in zip(cls.report.groups, cls.report.verdicts):
            cls.verdicts.setdefault(verdict, []).append(group)

    def _at(self, x, y, tolerance=400.0):
        """The group anchored near (x, y) mm, whichever stages it holds."""
        for group, verdict in zip(self.report.groups, self.report.verdicts):
            if (abs(group.anchor[0] - x) <= tolerance
                    and abs(group.anchor[1] - y) <= tolerance):
                return group, verdict
        return None, None

    def test_every_stage_produced_items(self):
        for stage in (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                      config.STAGE_LINK_RAW, config.STAGE_MODEL):
            self.assertTrue(self.captures[stage].items, "empty: " + stage)

    def test_no_stage_recorded_a_read_failure(self):
        for stage, capture in self.captures.items():
            self.assertEqual(capture.errors, [], "{0}: {1}".format(
                stage, capture.errors))

    def test_a_member_drawn_linked_and_built_correctly_is_ok(self):
        _group, verdict = self._at(200, 200)
        self.assertEqual(verdict, config.VERDICT_OK)

    def test_a_member_built_the_wrong_size_says_so(self):
        _group, verdict = self._at(5300, 200)
        self.assertEqual(verdict, config.VERDICT_SIZE_MISMATCH)
        sizes = [f for f in self.report.findings
                 if f.code == config.VERDICT_SIZE_MISMATCH]
        self.assertTrue(sizes)
        self.assertAlmostEqual(sizes[0].detail["delta_mm"], 100.0, delta=1.0)

    def test_a_member_the_link_lost_and_nobody_built_is_missing_in_link(self):
        """The bulged column: drawn, absent from the link, never built."""
        _group, verdict = self._at(10200, 200)
        self.assertEqual(verdict, config.VERDICT_MISSING_IN_LINK)

    def test_an_element_nobody_drew_is_an_orphan(self):
        _group, verdict = self._at(30000, 0)
        self.assertEqual(verdict, config.VERDICT_ORPHAN)

    def test_a_member_is_matched_across_all_three_stages_at_once(self):
        group, _verdict = self._at(200, 200)
        for stage in (config.STAGE_DXF_RAW, config.STAGE_LINK_RAW,
                      config.STAGE_MODEL):
            self.assertTrue(group.has(stage), "not matched in " + stage)

    def test_the_imported_hatch_keeps_its_hole_through_the_link(self):
        """The comparison the two-sided hatch story exists for.

        The drawing shows an island; the import shows a hole. Only having both
        can the report say whether the hole survived.
        """
        solids = [item for item in self.captures[config.STAGE_LINK_RAW].items
                  if item.kind == "solid"]
        self.assertEqual(len(solids), 1)
        self.assertEqual(solids[0].extra["hole_count"], 1)
        hatches = [item for item in self.captures[config.STAGE_DXF_RAW].items
                   if item.kind == "hatch" and item.extra.get("island_count")]
        self.assertTrue(hatches)

    def test_text_is_reported_as_expected_absent_on_the_revit_side(self):
        codes = set(f.code for f in self.report.findings)
        self.assertIn(config.VERDICT_EXPECTED_ABSENT, codes)

    def test_the_workbook_builds_from_a_four_stage_run(self):
        sheets = run.build_sheets(self.report)
        by_name = dict((sheet.name, sheet) for sheet in sheets)
        self.assertTrue(by_name["Columns"].rows)
        self.assertTrue(by_name["Model elements"].rows)
        self.assertTrue(by_name["Revit link geometry"].rows)
        for sheet in sheets:
            for row in sheet.rows:
                self.assertEqual(len(row), len(sheet.columns), sheet.name)

    def test_both_coordinate_spaces_are_populated_on_every_stage(self):
        for stage, capture in self.captures.items():
            positioned = [item for item in capture.items if item.points]
            self.assertTrue(positioned, stage)
            for item in positioned[:20]:
                self.assertIsNotNone(item.centroid_dxf, stage)
                self.assertIsNotNone(item.centroid_revit, stage)


if __name__ == "__main__":
    unittest.main()
