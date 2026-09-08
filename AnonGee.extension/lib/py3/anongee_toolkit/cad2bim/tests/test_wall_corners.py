# -*- coding: utf-8 -*-
"""Wall corners: which member runs through, and the gap that closes when it does.

Revit joins wall ends by default and mitres them, so a corner looks right
whatever centrelines it was handed. Disallow the join -- which is what the
drawing shows -- and the mitre goes with it, leaving whatever the planner
actually cut. The owner's screenshot is that: two 150 walls both stopping at
the junction, and a 150 mm square of nothing between them.

The fixture coordinates below are EXACT record points, probed out of the four
wall-bearing drawings (millimetres as the DXF stores them, scaled to feet the
way the sweep scales every record). They are here because the rule was read off
them rather than chosen:

  * test9's PI_RETAINING WALL corner at (105706.8, 39423.3) -- a 160 wall and a
    240 wall that BOTH stop on the other's near face, leaving a 240 x 160 hole.
    This is the user's own screenshot, in the corpus.
  * test16's S-WALL ring and Project1's PARAPET WALL ring -- rectilinear rings
    whose exact-cover decomposition has ALREADY assigned every corner. Nothing
    here may move them by a millimetre.
  * test8's L-shaped core, drawn as outer and inner faces: the union spans all
    three walls to the outer extent, and the corner pass stands the two short
    legs off the spine -- landing them on the inner-face lengths the drafter
    drew.

The synthetic cases cover what the corpus states only once or not at all: the
tee driven into its host, the crossing, the collinear continuation that is not
a corner at all, and every refusal.
"""

import ast
import math
import os
import unittest

import _loader


wall_plan, layers = _loader.load("wall_plan", "classify.layers")

_MM = 304.8
_HERE = os.path.dirname(os.path.abspath(__file__))
_WALLS = os.path.normpath(os.path.join(_HERE, "..", "builders", "walls.py"))


def _ft(value):
    return value / _MM


def _seg(start, end, width_mm, kind="structural", source="pair",
         layer="S-WALL"):
    """One planned centreline, in the shape `plan_walls` hands on."""
    return {"start": [_ft(start[0]), _ft(start[1]), 0.0],
            "end": [_ft(end[0]), _ft(end[1]), 0.0],
            "width_mm": width_mm,
            "length_mm": math.hypot(end[0] - start[0], end[1] - start[1]),
            "kind": kind, "layer": layer, "source": source}


def _ends(segment):
    """(start, end) of a segment back in millimetres, rounded to 0.1."""
    return tuple((round(segment[key][0] * _MM, 1),
                  round(segment[key][1] * _MM, 1))
                 for key in ("start", "end"))


def _length(segment):
    return round(segment["length_mm"], 1)


class _Record(object):
    """A record as apply_mapping leaves it: points in internal feet."""

    def __init__(self, points_mm, layer, category, kind="polyline"):
        self.points = [(_ft(x), _ft(y), 0.0) for x, y in points_mm]
        self.layer = layer
        self.kind = kind
        self.category = category

    @property
    def layer_key(self):
        return self.layer


def _struct_line(a, b, layer="PI_RETAINING WALL"):
    return _Record([a, b], layer, layers.CATEGORY_STRUCT_WALL, "line")


class TheUsersOwnGap(unittest.TestCase):
    """test9's open corner: both walls stop, and 240 x 160 of nothing is left."""

    # The six PI_RETAINING WALL lines that draw it, verbatim. Two faces make
    # the 160 wall (y 39343.3 / 39503.3, centreline 39423.3), two make the 240
    # wall (x 105586.8 / 105826.8, centreline 105706.8), and two are end caps.
    LINES = [((105586.8, 39503.3), (104881.8, 39503.3)),
             ((105586.8, 39343.3), (104881.8, 39343.3)),
             ((105826.8, 39503.3), (105826.8, 40303.3)),
             ((105586.8, 40303.3), (105826.8, 40303.3)),
             ((104881.8, 39503.3), (104881.8, 39343.3)),
             ((105586.8, 40303.3), (105586.8, 39503.3))]

    def _plan(self):
        return wall_plan.plan_walls([_struct_line(a, b) for a, b in self.LINES])

    def test_the_two_faces_pair_into_the_two_walls_the_drawing_draws(self):
        plan = self._plan()
        self.assertEqual(sorted(round(s["width_mm"]) for s in plan["segments"]),
                         [160, 240])

    def test_the_corner_the_drawing_leaves_open_is_a_junction(self):
        plan = self._plan()
        self.assertEqual(plan["junctions"]["found"], 1)
        self.assertEqual(plan["junctions"]["resolved"], 1)
        self.assertEqual(plan["junctions"]["by_rule"],
                         {"the longer run continues": 1})
        self.assertEqual(plan["junctions"]["unresolved"], [])

    def test_the_longer_run_is_extended_by_the_other_walls_full_width(self):
        # The centrelines cross at (105706.8, 39423.3). Before: the 160 wall
        # stops 120 short of it (half the 240's width -- on its near face) and
        # the 240 wall stops 80 short (half the 160's -- on ITS near face), so
        # NEITHER covers the 240 x 160 cell between them. The 240 wall is the
        # longer run (800 against 705), so it runs through: 80 out to the
        # crossing and 80 more to the far face, an extension of 160 mm -- one
        # whole 160 wall. For the user's 150 walls that same sum reads
        # 75 + 75 = the 150 they measured in the hole.
        segments = self._plan()["segments"]
        thick = [s for s in segments if round(s["width_mm"]) == 240][0]
        thin = [s for s in segments if round(s["width_mm"]) == 160][0]
        self.assertEqual(sorted(_ends(thick)),
                         [(105706.8, 39343.3), (105706.8, 40303.3)])
        self.assertEqual(_length(thick), 960.0)
        # 39343.3 IS the 160 wall's far face, and the 160 wall never moves
        self.assertEqual(sorted(_ends(thin)),
                         [(104881.8, 39423.3), (105586.8, 39423.3)])
        self.assertEqual(_length(thin), 705.0)

    def test_the_thin_wall_still_stops_on_the_thick_ones_face(self):
        # 105586.8 = 105706.8 - 120: hard against the 240's west face, which
        # is where the drawing already had it. A closed corner cuts one wall,
        # not both.
        thin = [s for s in self._plan()["segments"]
                if round(s["width_mm"]) == 160][0]
        self.assertEqual(max(_ends(thin))[0], 105586.8)


class TheRingsThatAlreadyDecided(unittest.TestCase):
    """A rectilinear ring assigns its own corners. Nothing here may move it."""

    TEST16 = [(-52512.0, 13100.0), (-52512.0, 21350.0), (-47362.0, 21350.0),
              (-47362.0, 21050.0), (-52212.0, 21050.0), (-52212.0, 18250.0),
              (-47362.0, 18250.0), (-47362.0, 17950.0), (-52212.0, 17950.0),
              (-52212.0, 13100.0), (-52512.0, 13100.0)]

    PARAPET = [(164036.8, 15716.4), (166746.8, 15716.4), (166746.8, 13916.4),
               (164036.8, 13916.4), (164036.8, 13766.4), (166896.8, 13766.4),
               (166896.8, 15866.4), (164036.8, 15866.4), (164036.8, 15716.4)]

    def _plan(self, points, layer, category):
        return wall_plan.plan_walls(
            [_Record(points, layer, category)])

    def test_test16s_s_wall_ring_is_not_moved_by_a_millimetre(self):
        plan = self._plan(self.TEST16, "S-WALL", layers.CATEGORY_ARCH_WALL)
        self.assertEqual(sorted(_length(s) for s in plan["segments"]),
                         [4850.0, 4850.0, 8250.0])
        # one tee (the middle leg lands in the spine's interior) and one L
        self.assertEqual(plan["junctions"]["found"], 2)
        self.assertEqual(plan["junctions"]["by_rule"],
                         {"a tee: the stem stops on the host's face": 1,
                          "the drawn extent already spans the corner": 1})

    def test_the_spine_still_runs_to_the_far_face_it_was_drawn_to(self):
        plan = self._plan(self.TEST16, "S-WALL", layers.CATEGORY_ARCH_WALL)
        spine = max(plan["segments"], key=lambda s: s["length_mm"])
        # 21350 is the top leg's OUTER face (centreline 21200 + half of 300)
        self.assertEqual(sorted(_ends(spine)),
                         [(-52362.0, 13100.0), (-52362.0, 21350.0)])

    def test_project1s_parapet_ring_is_untouched_too(self):
        plan = self._plan(self.PARAPET, "PARAPET WALL",
                          layers.CATEGORY_ARCH_WALL)
        self.assertEqual(sorted(_length(s) for s in plan["segments"]),
                         [1950.0, 2710.0, 2860.0])
        self.assertEqual(plan["junctions"]["by_rule"],
                         {"the drawn extent already spans the corner": 2})
        self.assertEqual(plan["junctions"]["unresolved"], [])


class TheShapesTwoWallsMake(unittest.TestCase):
    """L, tee, crossing and continuation, each stated on its own."""

    def test_an_l_that_stops_short_on_both_sides_is_filled_by_one_of_them(self):
        # The user's failure, at 150: both centrelines end on the OTHER's near
        # face, so the 150 x 150 cell at (0, 0) is covered by neither.
        across = _seg((-2000.0, 0.0), (-75.0, 0.0), 150.0)
        up = _seg((0.0, 75.0), (0.0, 1000.0), 150.0)
        result = wall_plan.close_wall_corners([across, up])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"the longer run continues": 1})
        long_run, short_run = result["segments"][0], result["segments"][1]
        # 1925 beats 925, so the horizontal runs through to x = +75, the far
        # face of the vertical -- and the vertical stays on the horizontal's
        self.assertEqual(sorted(_ends(long_run)),
                         [(-2000.0, 0.0), (75.0, 0.0)])
        self.assertEqual(sorted(_ends(short_run)),
                         [(0.0, 75.0), (0.0, 1000.0)])

    def test_the_extension_is_half_the_other_walls_width_from_the_crossing(self):
        # -75 to +75 across a 150 wall: the 150 the user measured in the hole,
        # arrived at as 75 out to the crossing plus 75 on to the far face.
        across = _seg((-2000.0, 0.0), (-75.0, 0.0), 150.0)
        up = _seg((0.0, 75.0), (0.0, 1000.0), 150.0)
        before = _length(across)
        after = _length(wall_plan.close_wall_corners([across, up])["segments"][0])
        self.assertEqual(round(after - before, 1), 150.0)

    def test_an_l_where_both_run_through_stops_the_shorter_one(self):
        # test9's 11/18 and Project1's two jamb legs: a doubled corner, which
        # with the join disallowed is two walls standing in each other.
        across = _seg((-2000.0, 0.0), (75.0, 0.0), 150.0)
        up = _seg((0.0, -75.0), (0.0, 1000.0), 150.0)
        result = wall_plan.close_wall_corners([across, up])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"the longer run continues": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(-2000.0, 0.0), (75.0, 0.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(0.0, 75.0), (0.0, 1000.0)])

    def test_a_tee_stem_stops_on_its_hosts_face(self):
        # The stem drawn to the host's CENTRELINE -- image2's failure at a
        # tee: half the host's width of the stem's own end face is missing.
        host = _seg((-2000.0, 0.0), (2000.0, 0.0), 300.0)
        stem = _seg((0.0, 0.0), (0.0, 3000.0), 200.0)
        result = wall_plan.close_wall_corners([host, stem])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"a tee: the stem stops on the host's face": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(-2000.0, 0.0), (2000.0, 0.0)])   # the host never moves
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(0.0, 150.0), (0.0, 3000.0)])     # half of 300

    def test_a_tee_stem_driven_through_its_host_is_pulled_back(self):
        # 15 of test8's tees arrive like this, the stem out past the host's
        # centreline; the wall standing inside another wall is the same defect
        # as the hole, and takes the same repair.
        host = _seg((-2000.0, 0.0), (2000.0, 0.0), 300.0)
        stem = _seg((0.0, -140.0), (0.0, 3000.0), 200.0)
        result = wall_plan.close_wall_corners([host, stem])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(0.0, 150.0), (0.0, 3000.0)])

    def test_two_walls_that_cross_are_reported_and_never_cut(self):
        across = _seg((-2000.0, 0.0), (2000.0, 0.0), 150.0)
        up = _seg((0.0, -2000.0), (0.0, 2000.0), 150.0)
        result = wall_plan.close_wall_corners([across, up])
        self.assertEqual(result["junctions"]["found"], 1)
        self.assertEqual(result["junctions"]["resolved"], 0)
        self.assertEqual([entry["count"]
                          for entry in result["junctions"]["unresolved"]], [1])
        self.assertIn("cross", result["junctions"]["unresolved"][0]["reason"])
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(-2000.0, 0.0), (2000.0, 0.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(0.0, -2000.0), (0.0, 2000.0)])

    def test_collinear_walls_end_to_end_are_not_a_corner(self):
        # One wall continuing into the next -- a door split, a layer change.
        # Nothing crosses, so there is nothing to fill and nothing to say.
        first = _seg((0.0, 0.0), (2000.0, 0.0), 150.0)
        second = _seg((2000.0, 0.0), (5000.0, 0.0), 150.0)
        result = wall_plan.close_wall_corners([first, second])
        self.assertEqual(result["junctions"]["found"], 0)
        self.assertEqual(_length(result["segments"][0]), 2000.0)
        self.assertEqual(_length(result["segments"][1]), 3000.0)

    def test_a_shallow_meeting_is_a_continuation_not_a_corner(self):
        # 10 degrees apart: under the 20-degree floor, so the two are one run
        # bending, not two walls meeting. The corpus's real corners are 79.7
        # and 90; nothing lands between 3 and 79.7.
        first = _seg((-2000.0, 0.0), (0.0, 0.0), 150.0)
        second = _seg((0.0, 0.0), (2000.0, 352.7), 150.0)
        result = wall_plan.close_wall_corners([first, second])
        self.assertEqual(result["junctions"]["found"], 0)

    def test_a_rotated_corner_needs_more_reach_than_a_square_one(self):
        # At 79.7 degrees (Project1 and test8 both carry the 10.3-degree run)
        # the far face is 76.2 along the centreline, not 75 -- half the width
        # over the sine of the angle.
        across = _seg((-3000.0, 0.0), (0.0, 0.0), 150.0)
        up = _seg((0.0, 0.0), (181.4, 1000.0), 150.0)
        result = wall_plan.close_wall_corners([across, up])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"the longer run continues": 1})
        self.assertEqual(_length(result["segments"][0]), 3076.2)


class WhichMemberRunsThrough(unittest.TestCase):
    """The order of the rule, one rule per test."""

    def test_a_column_member_never_moves_and_the_wall_stops_on_it(self):
        # `split_vertical_members` lays a member's centreline down the
        # rectangle the drawing drew, so that extent is the drawing's own.
        column = _seg((0.0, -1000.0), (0.0, 1000.0), 300.0, source="member")
        wall = _seg((-3000.0, 0.0), (0.0, 0.0), 200.0)
        result = wall_plan.close_wall_corners([column, wall])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"a tee: the stem stops on the host's face": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, -1000.0), (0.0, 1000.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(-3000.0, 0.0), (-150.0, 0.0)])

    def test_a_column_at_an_l_runs_through_and_is_still_not_moved(self):
        column = _seg((0.0, 0.0), (0.0, 900.0), 300.0, source="member")
        wall = _seg((-4000.0, 0.0), (0.0, 0.0), 200.0)
        result = wall_plan.close_wall_corners([column, wall])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"a column runs through and the wall stops on it": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, 0.0), (0.0, 900.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(-4000.0, 0.0), (-150.0, 0.0)])

    def test_two_column_members_meeting_are_reported_not_cut(self):
        first = _seg((0.0, 0.0), (0.0, 900.0), 300.0, source="member")
        second = _seg((-900.0, 0.0), (0.0, 0.0), 300.0, source="member")
        result = wall_plan.close_wall_corners([first, second])
        self.assertEqual(result["junctions"]["resolved"], 0)
        self.assertIn("column members",
                      result["junctions"]["unresolved"][0]["reason"])

    def test_the_drawn_extent_beats_the_longer_run(self):
        # The SHORT wall is the one already spanning the corner: re-deciding it
        # by length would churn a corner the drafter had already assigned.
        short = _seg((0.0, -75.0), (0.0, 900.0), 150.0)
        long_run = _seg((-4000.0, 0.0), (-75.0, 0.0), 150.0)
        result = wall_plan.close_wall_corners([short, long_run])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"the drawn extent already spans the corner": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, -75.0), (0.0, 900.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(-4000.0, 0.0), (-75.0, 0.0)])

    def test_a_drawn_outline_beats_a_face_pair(self):
        # Both stop short and both are 900 long, so nothing but the source
        # separates them: a closed ring is measured, a pair is inferred.
        outline = _seg((0.0, -75.0), (0.0, 825.0), 150.0, source="outline")
        pair = _seg((-825.0, 0.0), (75.0, 0.0), 150.0, source="pair")
        result = wall_plan.close_wall_corners([outline, pair])
        self.assertEqual(result["junctions"]["by_rule"],
                         {"the drawn outline runs through": 1})
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, -75.0), (0.0, 825.0)])
        self.assertEqual(sorted(_ends(result["segments"][1])),
                         [(-825.0, 0.0), (-75.0, 0.0)])

    def test_a_structural_and_an_architectural_wall_never_join(self):
        # test8 draws the SAME wall on both conventions (a 250 S-RCC-WALL quad
        # with a 150 arch trace 50 mm off its centreline, findings #12), and
        # the builders pool the two kinds apart anyway.
        struct = _seg((-2000.0, 0.0), (0.0, 0.0), 150.0, kind="structural")
        arch = _seg((0.0, 0.0), (0.0, 3000.0), 150.0, kind="arch")
        result = wall_plan.close_wall_corners([struct, arch])
        self.assertEqual(result["junctions"]["found"], 0)
        self.assertEqual(_length(result["segments"][0]), 2000.0)


class WhatIsReportedRatherThanGuessed(unittest.TestCase):
    """A corner nothing can settle is named, with a count and a reason."""

    def test_two_runs_of_equal_length_are_a_tie(self):
        # test8's shafts are square -- four 3150 x 150 walls to a box, 14 such
        # corners -- and nothing in the drawing says which run carries through.
        first = _seg((0.0, 0.0), (0.0, 3150.0), 150.0)
        second = _seg((0.0, 0.0), (3150.0, 0.0), 150.0)
        result = wall_plan.close_wall_corners([first, second])
        self.assertEqual(result["junctions"]["found"], 1)
        self.assertEqual(result["junctions"]["resolved"], 0)
        self.assertEqual(result["junctions"]["unresolved"],
                         [{"reason": "two walls of equal length meet: neither "
                                     "of them is the longer run", "count": 1}])
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, 0.0), (0.0, 3150.0)])

    def test_three_walls_at_one_point_are_reported_and_left_as_drawn(self):
        # East, north and a 45-degree spur, all ending at (0, 0). Each PAIR of
        # them has an answer and the three answers put the shared ends in
        # different places (75 against 106.1, the same 75 over the sine of 45),
        # so no pair of them is the corner. All three stay as the drawing has
        # them and the count says so. Two segments meeting straight through
        # each other would be a tee, not this.
        east = _seg((0.0, 0.0), (2000.0, 0.0), 150.0)
        north = _seg((0.0, 0.0), (0.0, 3000.0), 150.0)
        spur = _seg((0.0, 0.0), (2000.0, 2000.0), 150.0)
        result = wall_plan.close_wall_corners([east, north, spur])
        self.assertEqual(result["junctions"]["found"], 3)
        self.assertEqual(result["junctions"]["resolved"], 0)
        reasons = [entry["reason"]
                   for entry in result["junctions"]["unresolved"]]
        self.assertEqual(len(reasons), 1)
        self.assertIn("three or more walls", reasons[0])
        self.assertEqual(sum(entry["count"]
                             for entry in result["junctions"]["unresolved"]), 3)
        for index, drawn in enumerate((east, north, spur)):
            self.assertEqual(_ends(result["segments"][index]), _ends(drawn))

    def test_a_cut_that_would_delete_a_wall_is_refused(self):
        # A 200 nib between two 300 walls: standing it off both faces would
        # leave 200 - 150 - 150 of wall, which the builder would skip as a
        # sliver. A corner shaped by deleting one of its two walls is not a
        # shaped corner, so both ends stay where the drawing put them.
        nib = _seg((0.0, 0.0), (200.0, 0.0), 150.0)
        left = _seg((0.0, -2000.0), (0.0, 2000.0), 300.0)
        right = _seg((200.0, -3000.0), (200.0, 3000.0), 300.0)
        result = wall_plan.close_wall_corners([nib, left, right])
        self.assertEqual(result["junctions"]["resolved"], 0)
        self.assertIn("less wall than the builder",
                      " ".join(entry["reason"]
                               for entry in result["junctions"]["unresolved"]))
        self.assertEqual(sorted(_ends(result["segments"][0])),
                         [(0.0, 0.0), (200.0, 0.0)])

    def test_every_junction_is_counted_once_resolved_or_not(self):
        segments = [_seg((0.0, 0.0), (0.0, 3150.0), 150.0),
                    _seg((0.0, 0.0), (3150.0, 0.0), 150.0),
                    _seg((-9000.0, 6000.0), (0.0, 6000.0), 150.0),
                    _seg((0.0, 5925.0), (0.0, 9000.0), 150.0)]
        report = wall_plan.close_wall_corners(segments)["junctions"]
        self.assertEqual(report["found"],
                         report["resolved"]
                         + sum(entry["count"] for entry in report["unresolved"]))

    def test_no_segment_is_ever_added_or_dropped(self):
        segments = [_seg((0.0, 0.0), (0.0, 3150.0), 150.0),
                    _seg((0.0, 0.0), (3150.0, 0.0), 150.0),
                    _seg((-9000.0, 6000.0), (0.0, 6000.0), 150.0)]
        result = wall_plan.close_wall_corners(segments)
        self.assertEqual(len(result["segments"]), 3)
        for before, after in zip(segments, result["segments"]):
            self.assertEqual(before["width_mm"], after["width_mm"])
            self.assertEqual(before["kind"], after["kind"])
            self.assertEqual(before["layer"], after["layer"])
            self.assertEqual(before["source"], after["source"])

    def test_the_planners_own_segments_are_not_mutated(self):
        original = _seg((-2000.0, 0.0), (-75.0, 0.0), 150.0)
        wall_plan.close_wall_corners(
            [original, _seg((0.0, -75.0), (0.0, 1000.0), 150.0)])
        self.assertEqual(sorted(_ends(original)),
                         [(-2000.0, 0.0), (-75.0, 0.0)])


class TheCoreThatTheUnionSpans(unittest.TestCase):
    """test8's L core: the union reaches the outer faces, the corners cut back."""

    def _plan(self):
        outer = _Record([(800.0, 8990.0), (0.0, 8990.0), (0.0, 0.0),
                         (3660.0, 0.0)], "S-RCC-WALL",
                        layers.CATEGORY_STRUCT_WALL)
        inner = _Record([(800.0, 8840.0), (150.0, 8840.0), (150.0, 150.0),
                         (3660.0, 150.0)], "S-RCC-WALL",
                        layers.CATEGORY_STRUCT_WALL)
        return wall_plan.plan_walls([outer, inner])

    def test_the_spine_runs_through_both_corners(self):
        plan = self._plan()
        spine = max(plan["segments"], key=lambda s: s["length_mm"])
        self.assertEqual(sorted(_ends(spine)), [(75.0, 0.0), (75.0, 8990.0)])
        self.assertEqual(_length(spine), 8990.0)

    def test_the_short_legs_land_on_the_inner_face_the_drawing_drew(self):
        # 800 - 150 = 650 and 3660 - 150 = 3510, which are exactly the lengths
        # of the drawn INNER faces. The drawing agrees with the rule.
        plan = self._plan()
        self.assertEqual(sorted(_length(s) for s in plan["segments"]),
                         [650.0, 3510.0, 8990.0])
        self.assertEqual(plan["junctions"]["by_rule"],
                         {"the longer run continues": 2})


class TheBuilderSquaresBothEnds(unittest.TestCase):
    """builders/walls.py imports Revit, so it is pinned by its source."""

    @classmethod
    def setUpClass(cls):
        with open(_WALLS, "rb") as handle:
            cls.source = handle.read().decode("utf-8")
        cls.tree = ast.parse(cls.source)

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError("builders/walls.py has no %s" % name)

    def _calls(self, node):
        names = []
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            names.append(func.id if isinstance(func, ast.Name)
                         else getattr(func, "attr", None))
        return names

    def test_wallutils_is_imported_from_the_revit_api(self):
        self.assertIn("WallUtils", self.source.split("def ", 1)[0])

    def test_the_join_is_disallowed_at_both_of_revits_end_indices(self):
        node = self._function("_disallow_joins")
        self.assertIn("DisallowWallJoinAtEnd", self._calls(node))
        segment = ast.get_source_segment(self.source, node)
        self.assertIn("_WALL_START, _WALL_END", self.source)
        self.assertIn("_WALL_START, _WALL_END = 0, 1", self.source)
        self.assertIn("for end in (_WALL_START, _WALL_END):", segment)

    def test_place_walls_disallows_the_join_on_every_wall_it_creates(self):
        node = self._function("place_walls")
        self.assertIn("_disallow_joins", self._calls(node))

    def test_the_join_is_disallowed_after_the_wall_is_created(self):
        # The end indices belong to a PLACED wall, and squaring an end before
        # the extension the planner cut would be squaring the wrong shape.
        node = self._function("place_walls")
        created = [inner.lineno for inner in ast.walk(node)
                   if isinstance(inner, ast.Call)
                   and getattr(inner.func, "attr", None) == "Create"]
        squared = [inner.lineno for inner in ast.walk(node)
                   if isinstance(inner, ast.Call)
                   and getattr(inner.func, "id", None) == "_disallow_joins"]
        self.assertTrue(created and squared)
        self.assertLess(max(created), min(squared))

    def test_a_refused_join_is_reported_and_never_raised(self):
        node = self._function("_disallow_joins")
        segment = ast.get_source_segment(self.source, node)
        self.assertIn("except Exception:", segment)
        self.assertNotIn("raise", segment)
        place = ast.get_source_segment(self.source,
                                       self._function("place_walls"))
        self.assertIn('result["skipped"].append(problem)', place)

    def test_the_wall_still_lands_in_created_when_the_join_refuses(self):
        # The whole point of returning a sentence: a wall carrying Revit's own
        # mitre is a wall in the right place at the right width.
        place = ast.get_source_segment(self.source, self._function("place_walls"))
        squared = place.index("_disallow_joins(instance)")
        registered = place.index('result["created"].append(instance.Id)')
        self.assertLess(squared, registered)


if __name__ == "__main__":
    unittest.main()
