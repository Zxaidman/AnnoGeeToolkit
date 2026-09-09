# -*- coding: utf-8 -*-
"""The raw DXF census, and what cad2bim's reader does to the same file.

Every assertion here pins one claim the tool makes in its own changelog. If a
future cad2bim reader stops dropping DIMENSIONs, a test fails and the claim gets
corrected -- which is the point. These tests are as much a spec of the reader
being audited as of the auditor.

The fixture is generated, not recorded: `fixtures/make_audit_plan.py` writes a
drawing containing exactly one instance of each known gap, so a failure names
the gap rather than a count that drifted.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402

config, space = _loader.load("config", "space")
dxf_raw, dxf_parsed = _loader.load("readers.dxf_raw", "readers.dxf_parsed")
cad2bim_dxf_reader = _loader.load_cad2bim("readers.dxf_reader")

FIXTURE = _loader.fixture("audit_plan.dxf")


def _ensure_fixture():
    """Generate the fixture if it is not on disk, so a clean checkout can test."""
    if os.path.exists(FIXTURE):
        return
    sys.path.insert(0, _loader.FIXTURES)
    import make_audit_plan
    make_audit_plan.build(FIXTURE)


class RawCensusTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _ensure_fixture()
        cls.capture = dxf_raw.read(FIXTURE, space.Space(1.0))

    def _of_type(self, name):
        return [item for item in self.capture.items if item.source_type == name]

    def _notes(self):
        return [note for item in self.capture.items for note in item.notes]

    def test_the_read_succeeds_without_swallowing_anything(self):
        self.assertEqual(self.capture.errors, [])
        self.assertTrue(self.capture.items)

    def test_types_cad2bim_never_handles_are_still_recorded(self):
        """DIMENSION, SOLID and XLINE produce no cad2bim record at all."""
        for name in ("DIMENSION", "SOLID", "XLINE"):
            items = self._of_type(name)
            self.assertEqual(len(items), 1, "no {0} recorded".format(name))
            self.assertIs(items[0].extra["cad2bim_reads"], False)

    def test_geometry_nested_past_the_depth_limit_is_flagged(self):
        deep = [item for item in self.capture.items
                if item.extra.get("depth", 0) > 3]
        self.assertTrue(deep, "the five-deep block produced nothing")
        for item in deep:
            self.assertIs(item.extra["cad2bim_reads"], False)
            self.assertTrue(any("stops at 3" in note for note in item.notes))

    def test_polyline_bulges_are_detected_and_honoured(self):
        bulged = [item for item in self.capture.items
                  if item.extra.get("bulge_count")]
        self.assertEqual(len(bulged), 1)
        item = bulged[0]
        self.assertEqual(item.extra["bulge_count"], 4)
        # The rounded outline is genuinely larger than its four corners: read as
        # straight chords it measures 400x400, and it is not 400x400.
        short, long_side = item.plan_size_mm
        self.assertGreater(short, 450.0)
        self.assertTrue(any("straight chords" in note for note in item.notes))

    def test_hatch_islands_are_counted_separately_from_textbox_paths(self):
        """A textbox path is the hatch clipped round a label -- not a lost island."""
        patterned = [item for item in self.capture.items
                     if item.kind == "hatch" and item.extra.get("pattern") == "ANSI31"]
        self.assertEqual(len(patterned), 1)
        extra = patterned[0].extra
        self.assertEqual(extra["path_count"], 3)
        self.assertEqual(extra["island_count"], 1)
        self.assertEqual(extra["textbox_paths"], 1)

    def test_an_arc_edge_boundary_resolves_to_real_vertices(self):
        """cad2bim takes the arc's CENTRE, which is not on the boundary at all."""
        edged = [item for item in self.capture.items
                 if item.kind == "hatch" and item.extra.get("edge_paths")]
        self.assertEqual(len(edged), 1)
        # A half-disc of radius 1500: pi*r^2/2 = 3.53e6 mm2. Two points could
        # never produce that, which is the whole difference being tested.
        self.assertAlmostEqual(edged[0].area_mm2, 3534291.0, delta=5000.0)

    def test_empty_text_is_marked_expected_rather_than_lost(self):
        empty = [item for item in self.capture.items
                 if item.kind == "text" and not item.text]
        self.assertEqual(len(empty), 1)
        self.assertTrue(any("expected" in note for note in empty[0].notes))

    def test_header_facts_are_captured_for_context(self):
        self.assertEqual(self.capture.meta["insunits"], 4)      # millimetres
        self.assertFalse(self.capture.meta["recovered"])
        self.assertIn("S-COLS", self.capture.meta["layers"])

    def test_a_missing_file_fails_loudly(self):
        with self.assertRaises(IOError):
            dxf_raw.read(os.path.join(_loader.FIXTURES, "nope.dxf"), space.Space(1.0))


class RawVersusParsedTests(unittest.TestCase):
    """The delta is the measurement. These pin its direction and its causes."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixture()
        subject = space.Space(1.0)
        cls.raw = dxf_raw.read(FIXTURE, subject)
        cls.parsed = dxf_parsed.read(FIXTURE, subject,
                                     reader=cad2bim_dxf_reader)

    def test_the_parsed_pass_reads_the_file_without_error(self):
        self.assertEqual(self.parsed.errors, [])

    def test_the_raw_pass_sees_strictly_more(self):
        self.assertGreater(len(self.raw.items), len(self.parsed.items))

    def test_whole_kinds_of_thing_reach_the_parsed_pass_not_at_all(self):
        parsed_kinds = set(self.parsed.by_kind())
        for kind in ("annotation", "filled", "construction", "block"):
            self.assertIn(kind, self.raw.by_kind())
            self.assertNotIn(kind, parsed_kinds)

    def test_the_solid_filled_hatch_is_lost_entirely_not_merely_reshaped(self):
        """Its only boundary is an edge path, which yields under three points."""
        self.assertEqual(self.raw.by_kind()["hatch"], 2)
        self.assertEqual(self.parsed.by_kind().get("hatch"), 1)

    def test_the_deep_block_costs_the_parsed_pass_a_curve(self):
        self.assertGreater(self.raw.by_kind()["curve"],
                           self.parsed.by_kind()["curve"])

    def test_both_passes_agree_on_the_geometry_they_both_see(self):
        """The baseline must not drift: two plain 400-wide columns, both passes.

        Without this, every other assertion here could be satisfied by a raw
        pass that simply read the file wrongly and generously.
        """
        def plain_columns(capture):
            # Selected by POSITION, not by a raw-only flag: the two plain
            # columns are the ones left of x=6000, and the parsed pass has no
            # bulge_count to filter on -- which is precisely the gap under test
            # elsewhere and must not quietly define the baseline here.
            return sorted(
                round(item.plan_size_mm[0]) for item in capture.items
                if item.layer == "S-COLS" and item.kind == "curve"
                and item.centroid_dxf is not None and item.centroid_dxf[0] < 6000.0)
        self.assertEqual(plain_columns(self.raw), [400, 400])
        self.assertEqual(plain_columns(self.parsed), [400, 400])

    def test_the_bulged_column_is_the_same_entity_at_a_different_size(self):
        """Nothing is lost, so no count shows it -- only the measurement does."""
        def bulged_size(capture):
            for item in capture.items:
                if (item.kind == "curve" and item.centroid_dxf is not None
                        and 9000.0 < item.centroid_dxf[0] < 11000.0):
                    return round(item.plan_size_mm[0])
            return None
        self.assertEqual(bulged_size(self.parsed), 400)
        self.assertGreater(bulged_size(self.raw), 450)


if __name__ == "__main__":
    unittest.main()
