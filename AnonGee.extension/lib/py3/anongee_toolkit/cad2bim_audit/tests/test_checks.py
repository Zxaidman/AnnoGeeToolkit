# -*- coding: utf-8 -*-
"""The finer checks: each fault planted deliberately, each silence too.

Half of these tests assert that a check does NOT fire. That is not padding: the
failure mode of a check is a false positive, and a report that cries wolf on a
healthy drawing gets ignored on the one where it matters. Every check therefore
gets a clean case as well as a faulty one.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402

config, model, matching, checks = _loader.load(
    "config", "model", "matching", "checks")

VALUES = config.settings(None)


def rect(cx, cy, width, height):
    half_w, half_h = width / 2.0, height / 2.0
    return [(cx - half_w, cy - half_h, 0.0), (cx + half_w, cy - half_h, 0.0),
            (cx + half_w, cy + half_h, 0.0), (cx - half_w, cy + half_h, 0.0)]


def item(stage, kind="curve", points=None, **fields):
    extra = fields.pop("extra", {})
    made = model.AuditItem(stage, kind, points_dxf=points, points_revit=points,
                           **fields)
    made.extra.update(extra)
    return made


def capture(stage, items):
    result = model.Capture(stage, "test")
    for one in items:
        result.add(one)
    return result


def run(captures, check):
    groups, diagnostics = matching.build_groups(captures)
    return check(groups, captures, VALUES, diagnostics["space"])


def codes(findings):
    return sorted(finding.code for finding in findings)


class DuplicateTests(unittest.TestCase):

    def test_a_shape_drawn_twice_is_reported_once(self):
        points = rect(0, 0, 400, 400)
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=points, layer="S-COLS",
                 source_type="LWPOLYLINE", category="column"),
            item(config.STAGE_DXF_RAW, points=points, layer="S-COLS",
                 source_type="LWPOLYLINE", category="column"),
        ])}
        found = run(captures, checks.duplicate_geometry)
        self.assertEqual(codes(found), [config.CHECK_DUPLICATE_GEOMETRY])
        self.assertEqual(found[0].detail["count"], 2)

    def test_two_different_shapes_at_one_point_are_not_duplicates(self):
        """A label sitting on its beam is not the beam drawn twice."""
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=rect(0, 0, 400, 400),
                 layer="S-COLS", source_type="LWPOLYLINE"),
            item(config.STAGE_DXF_RAW, points=rect(0, 0, 4000, 200),
                 layer="S-BEAM", source_type="LWPOLYLINE"),
        ])}
        self.assertEqual(run(captures, checks.duplicate_geometry), [])

    def test_a_nested_block_chain_is_not_four_duplicates(self):
        """One INSERT per nesting level sits at the very same point.

        Without block depth in the identity, a five-deep block chain reported as
        four identical entities drawn on top of each other -- a false positive
        on a perfectly ordinary drawing, which is the failure mode that gets a
        whole report ignored.
        """
        point = [(14000.0, 0.0, 0.0)]
        nested = [item(config.STAGE_DXF_RAW, "block", point, layer="0",
                       source_type="INSERT", extra={"depth": depth})
                  for depth in range(4)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, nested)}
        self.assertEqual(run(captures, checks.duplicate_geometry), [])

    def test_the_same_block_inserted_twice_at_one_depth_still_registers(self):
        point = [(14000.0, 0.0, 0.0)]
        twice = [item(config.STAGE_DXF_RAW, "block", point, layer="0",
                      source_type="INSERT", extra={"depth": 0})
                 for _ in range(2)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, twice)}
        self.assertEqual(codes(run(captures, checks.duplicate_geometry)),
                         [config.CHECK_DUPLICATE_GEOMETRY])

    def test_two_elements_in_one_place_double_the_quantities(self):
        points = rect(0, 0, 400, 400)
        captures = {config.STAGE_MODEL: capture(config.STAGE_MODEL, [
            item(config.STAGE_MODEL, "element", points, layer="OST_StructuralColumns",
                 category="column", handle="1001"),
            item(config.STAGE_MODEL, "element", points, layer="OST_StructuralColumns",
                 category="column", handle="1002"),
        ])}
        found = run(captures, checks.duplicate_elements)
        self.assertEqual(codes(found), [config.CHECK_DUPLICATE_ELEMENT])
        self.assertEqual(sorted(found[0].detail["ids"]), ["1001", "1002"])

    def test_a_beam_and_a_column_sharing_a_point_are_not_duplicate_elements(self):
        points = rect(0, 0, 400, 400)
        captures = {config.STAGE_MODEL: capture(config.STAGE_MODEL, [
            item(config.STAGE_MODEL, "element", points, category="column"),
            item(config.STAGE_MODEL, "element", points, category="beam"),
        ])}
        self.assertEqual(run(captures, checks.duplicate_elements), [])


class DrawingHygieneTests(unittest.TestCase):

    def test_an_outline_left_open_is_reported(self):
        gap = [(0, 0, 0), (400, 0, 0), (400, 400, 0), (0, 400, 0), (0, 120, 0)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=gap, layer="S-COLS",
                 category="column")])}
        found = run(captures, checks.open_outlines)
        self.assertEqual(codes(found), [config.CHECK_OPEN_OUTLINE])
        self.assertAlmostEqual(found[0].detail["gap_mm"], 120.0, places=0)

    def test_a_closed_outline_is_silent(self):
        closed = rect(0, 0, 400, 400) + [(-200.0, -200.0, 0.0)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=closed, layer="S-COLS",
                 category="column")])}
        self.assertEqual(run(captures, checks.open_outlines), [])

    def test_a_plain_polyline_is_not_a_broken_outline(self):
        """A run of strokes is open by design; only a would-be ring counts."""
        line = [(0, 0, 0), (4000, 0, 0), (8000, 0, 0)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=line, layer="S-COLS",
                 category="column")])}
        self.assertEqual(run(captures, checks.open_outlines), [])

    def test_zero_length_geometry_is_reported_per_layer(self):
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=[(0, 0, 0), (0.1, 0, 0)],
                 layer="S-COLS"),
            item(config.STAGE_DXF_RAW, points=[(5, 5, 0), (5.2, 5, 0)],
                 layer="S-COLS"),
        ])}
        found = run(captures, checks.degenerate_geometry)
        self.assertEqual(codes(found), [config.CHECK_DEGENERATE])
        self.assertEqual(found[0].detail["count"], 2)

    def test_stray_z_is_reported_with_how_far_out_it_is(self):
        tilted = [(0, 0, 0), (1000, 0, 250.0)]
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=tilted, layer="S-BEAM")])}
        found = run(captures, checks.non_planar_geometry)
        self.assertEqual(codes(found), [config.CHECK_NON_PLANAR])
        self.assertEqual(found[0].detail["max_z_spread_mm"], 250.0)

    def test_a_flat_drawing_is_silent(self):
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=rect(0, 0, 400, 400),
                 layer="S-COLS")])}
        self.assertEqual(run(captures, checks.non_planar_geometry), [])


class LabelTests(unittest.TestCase):

    def _captures(self, label_point, label_size=(400.0, 400.0), built=400.0):
        text = item(config.STAGE_DXF_PARSED, "text", [label_point],
                    layer="S-TEXT", mark="C1", text="C1")
        text.extra["b_mm"], text.extra["h_mm"] = label_size
        return {
            config.STAGE_DXF_PARSED: capture(config.STAGE_DXF_PARSED, [
                item(config.STAGE_DXF_PARSED, points=rect(0, 0, built, built),
                     layer="S-COLS", category="column"),
                text,
            ]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", rect(0, 0, built, built),
                     layer="OST_StructuralColumns", category="column")]),
        }

    def test_a_label_with_no_member_near_it_is_an_orphan(self):
        found = run(self._captures((50000.0, 0.0, 0.0)), checks.label_checks)
        self.assertEqual(codes(found), [config.CHECK_ORPHAN_MARK])
        self.assertEqual(found[0].detail["count"], 1)

    def test_a_label_matching_what_was_built_is_silent(self):
        self.assertEqual(run(self._captures((0.0, 600.0, 0.0)), checks.label_checks), [])

    def test_a_label_the_model_disagrees_with_is_an_error(self):
        found = run(self._captures((0.0, 600.0, 0.0), (600.0, 600.0), built=400.0),
                    checks.label_checks)
        self.assertEqual(codes(found), [config.CHECK_MARK_NOT_APPLIED])
        self.assertEqual(found[0].detail["delta_mm"], 200.0)

    def test_a_label_along_a_long_beam_is_not_an_orphan(self):
        """Measured to the member's SPAN, not its centroid.

        A label 300 mm off the end of a 6 m beam is 2.8 m from its centroid.
        Measuring to the centroid reported every such label as sizing nothing.
        """
        beam = [(0.0, 0.0, 0.0), (6000.0, 0.0, 0.0)]
        text = item(config.STAGE_DXF_PARSED, "text", [(5800.0, 300.0, 0.0)],
                    layer="S-TEXT", mark="B1")
        text.extra["b_mm"], text.extra["h_mm"] = 230.0, 450.0
        captures = {config.STAGE_DXF_PARSED: capture(config.STAGE_DXF_PARSED, [
            item(config.STAGE_DXF_PARSED, points=beam, layer="S-BEAM",
                 category="beam"),
            text,
        ])}
        self.assertEqual(run(captures, checks.label_checks), [])

    def test_an_ambiguous_label_is_counted_rather_than_guessed_at(self):
        """Three members in range: which one the label sizes cannot be known."""
        text = item(config.STAGE_DXF_PARSED, "text", [(500.0, 0.0, 0.0)],
                    layer="S-TEXT", mark="C1")
        text.extra["b_mm"], text.extra["h_mm"] = 900.0, 900.0
        captures = {
            config.STAGE_DXF_PARSED: capture(config.STAGE_DXF_PARSED, [
                item(config.STAGE_DXF_PARSED, points=rect(0, 0, 400, 400),
                     layer="S-COLS", category="column"),
                item(config.STAGE_DXF_PARSED, points=rect(1000, 0, 400, 400),
                     layer="S-COLS", category="column"),
                text,
            ]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", rect(0, 0, 400, 400),
                     category="column"),
                item(config.STAGE_MODEL, "element", rect(1000, 0, 400, 400),
                     category="column"),
            ]),
        }
        found = run(captures, checks.label_checks)
        self.assertEqual(codes(found), [config.CHECK_ORPHAN_MARK])
        self.assertEqual(found[0].detail["ambiguous_labels"], 1)
        # and crucially NOT a size claim about a member it merely guessed at
        self.assertNotIn(config.CHECK_MARK_NOT_APPLIED, codes(found))

    def test_one_mark_used_for_two_sizes_is_an_error(self):
        first = item(config.STAGE_DXF_PARSED, "text", [(0, 0, 0)], mark="C1")
        first.extra["b_mm"], first.extra["h_mm"] = 400.0, 400.0
        second = item(config.STAGE_DXF_PARSED, "text", [(9000, 0, 0)], mark="C1")
        second.extra["b_mm"], second.extra["h_mm"] = 300.0, 300.0
        captures = {config.STAGE_DXF_PARSED:
                    capture(config.STAGE_DXF_PARSED, [first, second])}
        found = run(captures, checks.conflicting_marks)
        self.assertEqual(codes(found), [config.CHECK_CONFLICTING_MARK])
        self.assertEqual(found[0].detail["sizes_mm"], [(300, 300), (400, 400)])

    def test_one_mark_used_consistently_is_silent(self):
        made = []
        for x in (0, 9000):
            text = item(config.STAGE_DXF_PARSED, "text", [(x, 0, 0)], mark="C1")
            text.extra["b_mm"], text.extra["h_mm"] = 400.0, 400.0
            made.append(text)
        captures = {config.STAGE_DXF_PARSED: capture(config.STAGE_DXF_PARSED, made)}
        self.assertEqual(run(captures, checks.conflicting_marks), [])


class HatchImportTests(unittest.TestCase):
    """What Revit's import did to a hatch -- only askable now stage B reads solids."""

    def _captures(self, islands, holes, solid_at=(0.0, 0.0)):
        hatch = item(config.STAGE_DXF_RAW, "hatch", rect(0, 0, 3000, 3000),
                     layer="S-FND", extra={"island_count": islands,
                                           "pattern": "ANSI31"})
        solid = item(config.STAGE_LINK_RAW, "solid",
                     rect(solid_at[0], solid_at[1], 3000, 3000),
                     layer="S-FND", extra={"hole_count": holes})
        return {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [hatch]),
                config.STAGE_LINK_RAW: capture(config.STAGE_LINK_RAW, [solid])}

    def test_a_hole_that_survives_the_import_is_silent(self):
        self.assertEqual(run(self._captures(islands=1, holes=1),
                             checks.hatch_import), [])

    def test_a_void_filled_in_by_the_import_is_an_error(self):
        """Same place, same size, and the lift shaft is now concrete.

        Nothing else in the report changes -- which is exactly why this needs
        its own check.
        """
        found = run(self._captures(islands=1, holes=0), checks.hatch_import)
        self.assertEqual(codes(found), [config.CHECK_HOLE_LOST])
        self.assertEqual(found[0].detail["islands"], 1)
        self.assertEqual(found[0].detail["holes"], 0)
        self.assertEqual(found[0].severity, config.SEVERITY_ERROR)

    def test_a_hatch_that_produced_nothing_in_the_link_is_reported(self):
        found = run(self._captures(islands=0, holes=0, solid_at=(50000.0, 0.0)),
                    checks.hatch_import)
        self.assertEqual(codes(found), [config.CHECK_HATCH_NOT_IMPORTED])

    def test_without_a_link_stage_the_check_stays_silent(self):
        hatch = item(config.STAGE_DXF_RAW, "hatch", rect(0, 0, 3000, 3000),
                     layer="S-FND", extra={"island_count": 1})
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [hatch])}
        self.assertEqual(run(captures, checks.hatch_import), [])


class ModelHygieneTests(unittest.TestCase):

    def _level_captures(self, intended, built):
        points = rect(0, 0, 400, 400)
        return {
            config.STAGE_INTENT: capture(config.STAGE_INTENT, [
                item(config.STAGE_INTENT, "element", points, category="column",
                     level=intended)]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", points, category="column",
                     level=built)]),
        }

    def test_an_element_built_on_the_wrong_storey_is_reported(self):
        found = run(self._level_captures("FIRST FLOOR", "SECOND FLOOR"),
                    checks.level_mismatches)
        self.assertEqual(codes(found), [config.CHECK_LEVEL_MISMATCH])

    def test_level_names_are_compared_forgivingly(self):
        """cad2bim's storey label comes from the drawing, Revit's from the level.

        An exact comparison would report every element in the model as being on
        the wrong storey.
        """
        found = run(self._level_captures("%%U(TOWER 1)- FIRST FLOOR", "First Floor"),
                    checks.level_mismatches)
        self.assertEqual(found, [])

    def test_a_clipped_beam_is_reported_by_length(self):
        drawn = [(0.0, 0.0, 0.0), (6000.0, 0.0, 0.0)]
        built = [(0.0, 0.0, 0.0), (5000.0, 0.0, 0.0)]
        captures = {
            config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
                item(config.STAGE_DXF_RAW, points=drawn, category="beam")]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", built, category="beam")]),
        }
        found = run(captures, checks.length_mismatches)
        self.assertEqual(codes(found), [config.CHECK_LENGTH_MISMATCH])
        self.assertEqual(found[0].detail["delta_mm"], 1000.0)

    def test_a_small_length_difference_on_a_long_beam_is_silent(self):
        """Both a fraction AND an absolute must be exceeded, as cad2bim does."""
        captures = {
            config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
                item(config.STAGE_DXF_RAW, points=[(0, 0, 0), (6000, 0, 0)],
                     category="beam")]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", [(0, 0, 0), (5940, 0, 0)],
                     category="beam")]),
        }
        self.assertEqual(run(captures, checks.length_mismatches), [])

    def test_a_member_built_as_the_wrong_category_is_caught(self):
        """Invisible to the reconciliation: the two land in different buckets."""
        points = rect(0, 0, 400, 400)
        captures = {
            config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
                item(config.STAGE_DXF_RAW, points=points, category="column")]),
            config.STAGE_MODEL: capture(config.STAGE_MODEL, [
                item(config.STAGE_MODEL, "element", points, category="beam")]),
        }
        found = run(captures, checks.category_conflicts)
        self.assertEqual(codes(found), [config.CHECK_CATEGORY_CONFLICT])
        self.assertEqual(found[0].detail["drawn_as"], "column")
        self.assertEqual(found[0].detail["built_as"], "beam")

    def test_a_type_name_that_lies_about_its_own_size_is_reported(self):
        element = item(config.STAGE_MODEL, "element", rect(0, 0, 300, 300),
                       category="column", type_name="Concrete-Rectangular: 400x400")
        element.extra["type_b_mm"], element.extra["type_h_mm"] = 300.0, 300.0
        captures = {config.STAGE_MODEL: capture(config.STAGE_MODEL, [element])}
        found = run(captures, checks.type_name_mismatches)
        self.assertEqual(codes(found), [config.CHECK_TYPE_NAME_MISMATCH])
        self.assertEqual(found[0].detail["delta_mm"], 100.0)

    def test_a_type_name_that_matches_is_silent(self):
        element = item(config.STAGE_MODEL, "element", rect(0, 0, 400, 400),
                       category="column", type_name="Concrete-Rectangular: 400x400")
        element.extra["type_b_mm"], element.extra["type_h_mm"] = 400.0, 400.0
        captures = {config.STAGE_MODEL: capture(config.STAGE_MODEL, [element])}
        self.assertEqual(run(captures, checks.type_name_mismatches), [])


class RobustnessTests(unittest.TestCase):

    def test_a_check_that_raises_costs_its_own_findings_and_no_others(self):
        """A report is a diagnostic: losing one column beats losing all of them."""
        broken = lambda *args, **kwargs: 1 / 0
        broken.__name__ = "broken_check"
        original = checks.duplicate_geometry
        try:
            checks.duplicate_geometry = broken
            found = checks.run_all([], {}, VALUES, "revit")
        finally:
            checks.duplicate_geometry = original
        self.assertIn("check_failed", codes(found))

    def test_every_check_is_silent_on_an_empty_run(self):
        self.assertEqual(checks.run_all([], {}, VALUES, "revit"), [])

    def test_checks_only_judge_stages_that_were_captured(self):
        """A stage that was not read is not evidence of anything."""
        captures = {config.STAGE_DXF_RAW: capture(config.STAGE_DXF_RAW, [
            item(config.STAGE_DXF_RAW, points=rect(0, 0, 400, 400),
                 layer="S-COLS", category="column")])}
        groups, diagnostics = matching.build_groups(captures)
        found = checks.run_all(groups, captures, VALUES, diagnostics["space"])
        for code in (config.CHECK_DUPLICATE_ELEMENT, config.CHECK_LEVEL_MISMATCH,
                     config.CHECK_TYPE_NAME_MISMATCH, config.CHECK_HOLE_LOST,
                     config.CHECK_HATCH_NOT_IMPORTED,
                     config.CHECK_CATEGORY_CONFLICT):
            self.assertNotIn(code, codes(found))


if __name__ == "__main__":
    unittest.main()
