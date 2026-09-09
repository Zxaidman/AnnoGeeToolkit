# -*- coding: utf-8 -*-
"""Matching and judgement: does the report say the right thing about a member?

Built from hand-made captures rather than fixtures, because the cases that
matter are the ones a real drawing gives you only occasionally -- an orphan, a
member two stages disagree about, two distinct columns close enough to be
confused. Constructing them directly is the only way to cover them all.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402

config, model, matching, findings = _loader.load(
    "config", "model", "matching", "findings")


def rect(cx, cy, width, height):
    half_w, half_h = width / 2.0, height / 2.0
    return [(cx - half_w, cy - half_h, 0.0), (cx + half_w, cy - half_h, 0.0),
            (cx + half_w, cy + half_h, 0.0), (cx - half_w, cy + half_h, 0.0)]


def capture(stage, specs, kind="curve", layer="S-COLS"):
    result = model.Capture(stage, "test")
    for cx, cy, width, height, category in specs:
        points = rect(cx, cy, width, height)
        result.add(model.AuditItem(stage, kind, layer=layer, category=category,
                                   points_dxf=points, points_revit=points))
    return result


def judge(captures):
    groups, diagnostics = matching.build_groups(captures)
    verdicts, found = findings.evaluate(groups, captures,
                                        space_key=diagnostics["space"])
    return groups, verdicts, found


def verdict_at(groups, verdicts, x, tolerance=200.0):
    for group, verdict in zip(groups, verdicts):
        if abs(group.anchor[0] - x) <= tolerance:
            return verdict
    return None


class MatchingTests(unittest.TestCase):

    def test_a_member_within_the_radius_is_one_group(self):
        drawing = capture(config.STAGE_DXF_RAW, [(0, 0, 400, 400, "column")])
        built = capture(config.STAGE_MODEL, [(40, 0, 400, 400, "column")], "element")
        groups, _diagnostics = matching.build_groups(
            {config.STAGE_DXF_RAW: drawing, config.STAGE_MODEL: built})
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].stages(),
                         [config.STAGE_DXF_RAW, config.STAGE_MODEL])

    def test_a_member_beyond_the_radius_is_two_groups(self):
        drawing = capture(config.STAGE_DXF_RAW, [(0, 0, 400, 400, "column")])
        built = capture(config.STAGE_MODEL, [(400, 0, 400, 400, "column")], "element")
        groups, _diagnostics = matching.build_groups(
            {config.STAGE_DXF_RAW: drawing, config.STAGE_MODEL: built})
        self.assertEqual(len(groups), 2)

    def test_categories_never_fuse(self):
        """A beam drawn over a column must not absorb it, however close."""
        drawing = capture(config.STAGE_DXF_RAW,
                          [(0, 0, 400, 400, "column"), (0, 0, 200, 4000, "beam")])
        groups, _diagnostics = matching.build_groups(
            {config.STAGE_DXF_RAW: drawing})
        self.assertEqual(len(groups), 2)
        self.assertEqual(sorted(group.category for group in groups),
                         ["beam", "column"])

    def test_two_distinct_members_inside_one_radius_stay_distinct(self):
        """Two items from the SAME stage can never join one group."""
        drawing = capture(config.STAGE_DXF_RAW,
                          [(0, 0, 400, 400, "column"), (60, 0, 400, 400, "column")])
        groups, _diagnostics = matching.build_groups(
            {config.STAGE_DXF_RAW: drawing})
        self.assertEqual(len(groups), 2)

    def test_builder_input_geometry_is_not_matched(self):
        """Stage B curves inside a stage D file would otherwise double-count."""
        intent = model.Capture(config.STAGE_INTENT, "json")
        points = rect(0, 0, 400, 400)
        placed = model.AuditItem(config.STAGE_INTENT, "element", category="column",
                                 points_revit=points, native_space="revit")
        placed.extra["role"] = "placed"
        echo = model.AuditItem(config.STAGE_INTENT, "curve", category="column",
                               points_revit=points, native_space="revit")
        echo.extra["role"] = "builder_input"
        intent.add(placed)
        intent.add(echo)
        groups, _diagnostics = matching.build_groups({config.STAGE_INTENT: intent})
        self.assertEqual(len(groups), 1)

    def test_items_with_no_position_are_counted_not_dropped_silently(self):
        empty = model.Capture(config.STAGE_DXF_RAW, "test")
        empty.add(model.AuditItem(config.STAGE_DXF_RAW, "curve", category="column"))
        _groups, diagnostics = matching.build_groups({config.STAGE_DXF_RAW: empty})
        self.assertEqual(diagnostics["items_without_position"], 1)


class LinearMatchingTests(unittest.TestCase):
    """Beams are runs, not points. Everything here follows from that."""

    @staticmethod
    def line(x1, y1, x2, y2, stage, category="beam"):
        points = [(float(x1), float(y1), 0.0), (float(x2), float(y2), 0.0)]
        result = model.AuditItem(stage, "curve", layer="S-BEAM",
                                 category=category, points_dxf=points,
                                 points_revit=points)
        return result

    def _fold(self, drawing_items, model_items):
        drawing = model.Capture(config.STAGE_DXF_RAW, "d")
        for one in drawing_items:
            drawing.add(one)
        built = model.Capture(config.STAGE_MODEL, "m")
        for one in model_items:
            built.add(one)
        captures = {config.STAGE_DXF_RAW: drawing, config.STAGE_MODEL: built}
        groups, _diagnostics = matching.build_groups(captures)
        return groups

    def test_a_clipped_beam_stays_one_member(self):
        """Clipping moves a centroid far outside the match radius.

        A 1 m clip on a 6 m beam shifts the centroid 500 mm. Matched on
        centroids this reads as two members -- one missing, one orphan -- which
        is two false findings for one real (and minor) fault.
        """
        groups = self._fold(
            [self.line(0, 0, 6000, 0, config.STAGE_DXF_RAW)],
            [self.line(0, 0, 5000, 0, config.STAGE_MODEL)])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].stages(),
                         [config.STAGE_DXF_RAW, config.STAGE_MODEL])

    def test_a_beam_split_at_its_columns_is_one_member_built_in_pieces(self):
        """cad2bim splits at every column crossed; the pieces are not orphans."""
        groups = self._fold(
            [self.line(0, 0, 9000, 0, config.STAGE_DXF_RAW)],
            [self.line(0, 0, 3000, 0, config.STAGE_MODEL),
             self.line(3000, 0, 6000, 0, config.STAGE_MODEL),
             self.line(6000, 0, 9000, 0, config.STAGE_MODEL)])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].count(config.STAGE_MODEL), 3)

    def test_the_run_is_the_sum_of_its_segments(self):
        groups = self._fold(
            [self.line(0, 0, 9000, 0, config.STAGE_DXF_RAW)],
            [self.line(0, 0, 3000, 0, config.STAGE_MODEL),
             self.line(3000, 0, 6000, 0, config.STAGE_MODEL),
             self.line(6000, 0, 9000, 0, config.STAGE_MODEL)])
        self.assertAlmostEqual(groups[0].total_length_mm(config.STAGE_MODEL),
                               9000.0)
        self.assertAlmostEqual(groups[0].total_length_mm(config.STAGE_DXF_RAW),
                               9000.0)

    def test_beams_meeting_at_a_corner_do_not_fuse(self):
        """Their runs touch, so the span test alone would pair them.

        Collinearity is the guard: without it every corner in the plan would
        merge two beams into one member.
        """
        groups = self._fold(
            [self.line(0, 0, 6000, 0, config.STAGE_DXF_RAW),
             self.line(6000, 0, 6000, 6000, config.STAGE_DXF_RAW)],
            [])
        self.assertEqual(len(groups), 2)

    def test_beams_laid_end_to_end_do_not_fuse(self):
        """Collinear and touching, but two members -- not one run in pieces.

        The discriminator is that matching probes from an item's CENTROID: a
        split piece's centroid lies on the drawn run, while an end-to-end
        neighbour's centroid is half its own length away from it.
        """
        groups = self._fold(
            [self.line(0, 0, 6000, 0, config.STAGE_DXF_RAW),
             self.line(6000, 0, 12000, 0, config.STAGE_DXF_RAW)],
            [])
        self.assertEqual(len(groups), 2)

    def test_a_split_piece_joins_the_run_it_was_cut_from(self):
        """The mirror of the case above, to prove the rule is not just strict."""
        groups = self._fold(
            [self.line(0, 0, 6000, 0, config.STAGE_DXF_RAW)],
            [self.line(0, 0, 3000, 0, config.STAGE_MODEL)])
        self.assertEqual(len(groups), 1)

    def test_the_two_faces_of_a_beam_are_two_lines_not_one_run(self):
        """A beam is commonly drawn as two parallel faces, 80-700 mm apart.

        Judged at the generic 100 mm match radius, the faces of a 100 mm beam
        fused and those of a 300 mm beam did not -- behaviour that changed with
        the beam's width, which is no rule at all. Lateral distance has its own
        tolerance, below the narrowest beam cad2bim will pair.
        """
        for width in (100, 300, 600):
            groups = self._fold(
                [self.line(400, 0, 5000, 0, config.STAGE_DXF_RAW),
                 self.line(400, width, 5000, width, config.STAGE_DXF_RAW)], [])
            self.assertEqual(len(groups), 2,
                             "faces {0} mm apart fused".format(width))

    def test_a_run_still_absorbs_a_piece_that_lies_on_it(self):
        """The tightened lateral rule must not cost the split-beam case."""
        groups = self._fold(
            [self.line(0, 0, 9000, 0, config.STAGE_DXF_RAW)],
            [self.line(0, 0, 4500, 0, config.STAGE_MODEL),
             self.line(4500, 0, 9000, 0, config.STAGE_MODEL)])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].count(config.STAGE_MODEL), 2)

    def test_two_distinct_columns_still_cannot_collapse(self):
        """The one-per-stage cap must survive for point-like members."""
        def column(cx):
            points = rect(cx, 0, 400, 400)
            return model.AuditItem(config.STAGE_DXF_RAW, "curve", layer="S-COLS",
                                   category="column", points_dxf=points,
                                   points_revit=points)
        groups = self._fold([column(0), column(60)], [])
        self.assertEqual(len(groups), 2)


class VerdictTests(unittest.TestCase):

    def setUp(self):
        self.drawing = capture(config.STAGE_DXF_RAW, [
            (0, 0, 400, 400, "column"),        # fine everywhere
            (5000, 0, 600, 400, "column"),     # built the wrong size
            (10000, 0, 300, 300, "column"),    # never reaches the model
            (15000, 0, 300, 300, None),        # no layer mapping
        ])
        self.link = capture(config.STAGE_LINK_RAW, [(0, 0, 400, 400, "column")])
        self.built = capture(config.STAGE_MODEL, [
            (40, 0, 400, 400, "column"),
            (5000, 0, 600, 500, "column"),
            (20000, 0, 300, 300, "column"),    # nobody drew this
        ], "element")
        self.captures = {config.STAGE_DXF_RAW: self.drawing,
                         config.STAGE_LINK_RAW: self.link,
                         config.STAGE_MODEL: self.built}
        self.groups, self.verdicts, self.findings = judge(self.captures)

    def test_a_member_present_and_correct_everywhere_is_ok(self):
        self.assertEqual(verdict_at(self.groups, self.verdicts, 0),
                         config.VERDICT_OK)

    def test_a_member_built_the_wrong_size_is_reported_as_such(self):
        self.assertEqual(verdict_at(self.groups, self.verdicts, 5000),
                         config.VERDICT_SIZE_MISMATCH)
        sizes = [f for f in self.findings if f.code == config.VERDICT_SIZE_MISMATCH]
        self.assertEqual(len(sizes), 1)
        self.assertEqual(sizes[0].detail["delta_mm"], 100.0)

    def test_a_member_the_link_lost_and_the_build_recovered_is_not_an_error(self):
        """cad2bim builds from the DXF by design; calling this an error would
        bury the real findings under every healthy run."""
        recovered = [f for f in self.findings
                     if f.code == config.VERDICT_LINK_RECOVERED]
        self.assertTrue(recovered)
        for finding in recovered:
            self.assertEqual(finding.severity, config.SEVERITY_INFO)

    def test_a_member_lost_by_the_link_and_never_built_is_an_error(self):
        self.assertEqual(verdict_at(self.groups, self.verdicts, 10000),
                         config.VERDICT_MISSING_IN_LINK)

    def test_an_element_nobody_drew_is_an_orphan(self):
        self.assertEqual(verdict_at(self.groups, self.verdicts, 20000),
                         config.VERDICT_ORPHAN)

    def test_an_unmapped_layer_is_reported_before_its_consequences(self):
        """The missing mapping explains every absence downstream; report it."""
        self.assertEqual(verdict_at(self.groups, self.verdicts, 15000),
                         config.VERDICT_UNCLASSIFIED)

    def test_text_absence_on_the_revit_side_is_stated_as_expected(self):
        self.drawing.add(model.AuditItem(
            config.STAGE_DXF_RAW, "text", layer="S-TEXT", text="C1 400x400",
            points_dxf=[(0, 600, 0)], points_revit=[(0, 600, 0)]))
        _groups, _verdicts, found = judge(self.captures)
        expected = [f for f in found if f.code == config.VERDICT_EXPECTED_ABSENT]
        self.assertEqual(len(expected), 1)
        self.assertEqual(expected[0].severity, config.SEVERITY_INFO)

    def test_read_failures_are_surfaced_rather_than_swallowed(self):
        self.drawing.fail("entity 4F", "bad OCS")
        _groups, _verdicts, found = judge(self.captures)
        errors = [f for f in found if f.code == "read_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, config.SEVERITY_ERROR)

    def test_findings_are_ordered_worst_first(self):
        ranks = [config.SEVERITY_ORDER[f.severity] for f in self.findings]
        self.assertEqual(ranks, sorted(ranks))


class UncapturedStageTests(unittest.TestCase):
    """A stage that was not read is not evidence of absence."""

    def test_auditing_a_dxf_alone_reports_nothing_missing(self):
        drawing = capture(config.STAGE_DXF_RAW, [(0, 0, 400, 400, "column")])
        captures = {config.STAGE_DXF_RAW: drawing}
        _groups, verdicts, found = judge(captures)
        self.assertEqual(verdicts, [config.VERDICT_OK])
        for finding in found:
            self.assertNotEqual(finding.severity, config.SEVERITY_ERROR)

    def test_without_a_model_sweep_nothing_is_missing_from_the_model(self):
        drawing = capture(config.STAGE_DXF_RAW, [(0, 0, 400, 400, "column")])
        link = capture(config.STAGE_LINK_RAW, [(0, 0, 400, 400, "column")])
        _groups, verdicts, _found = judge({config.STAGE_DXF_RAW: drawing,
                                           config.STAGE_LINK_RAW: link})
        self.assertNotIn(config.VERDICT_MISSING_IN_MODEL, verdicts)


class ShapeDriftTests(unittest.TestCase):

    def test_a_reader_that_changes_shape_is_caught_though_nothing_is_lost(self):
        raw = capture(config.STAGE_DXF_RAW, [(0, 0, 560, 560, "column")])
        parsed = capture(config.STAGE_DXF_PARSED, [(0, 0, 400, 400, "column")])
        _groups, _verdicts, found = judge({config.STAGE_DXF_RAW: raw,
                                           config.STAGE_DXF_PARSED: parsed})
        drift = [f for f in found
                 if f.code == config.VERDICT_READER_GAP and "Shape changes" in f.message]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0].detail["delta_mm"], 160.0)


if __name__ == "__main__":
    unittest.main()
