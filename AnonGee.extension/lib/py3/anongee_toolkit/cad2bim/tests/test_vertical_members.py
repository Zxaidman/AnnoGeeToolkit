# -*- coding: utf-8 -*-
"""Column or shear wall: the mark rule, the L/B rule, and the routing.

Every mark and every section size asserted here was MEASURED off the twenty
fixture drawings, not invented. The two that carry the question outright:

  * StructuralPlan-Test7 marks C1..C18 on seventeen members, three of which
    (C6 5300x300, C8 300x3300, C10 300x5300) have an L/B of 11 to 17.7 -- shear
    walls by the ratio, columns by the drawing. They are why the mark is asked
    FIRST, and they are the case that would silently move seventeen members if
    the order were ever swapped.
  * StaircasePlan-Test1 marks SW1..SW6 on six members, 300x3300 and 6300x300.
    Both rules agree there, which is what a well-drawn plan looks like.

And StructuralPlan-Test5, where 289 BEAM labels land on column rectangles, is
why an unrecognised prefix must abstain rather than vote.

Revit-free: the classifier and the split are both offline, so all of it runs in
the one-second suite.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _loader

marks, wall_plan, shapes = _loader.load("classify.marks", "wall_plan",
                                        "geom.shapes")

_FT = 1.0 / 304.8


def _rect(width_mm, height_mm, cx_mm=0.0, cy_mm=0.0, mark=None):
    """An axis-aligned member the way report.py stores one (a Rectangle dict)."""
    half_w, half_h = width_mm * _FT / 2.0, height_mm * _FT / 2.0
    cx, cy = cx_mm * _FT, cy_mm * _FT
    out = shapes.Rectangle(cx - half_w, cy - half_h,
                           cx + half_w, cy + half_h).to_dict()
    if mark:
        out["mark"] = mark
    return out


def _oriented(short_mm, long_mm, long_axis_deg, cx_mm=0.0, cy_mm=0.0,
              mark=None):
    """A rotated member the way report.py stores one (an OrientedRect dict)."""
    out = shapes.OrientedRect(cx_mm * _FT, cy_mm * _FT, long_mm * _FT,
                              short_mm * _FT, long_axis_deg,
                              0.0, 0.0, 0.0, 0.0).to_dict()
    if mark:
        out["mark"] = mark
    return out


def _sections(rectangles, circles=None):
    """The sections dict shape `build_column_sections` returns."""
    return {"entries": [{"layer": "S-COLS", "status": "rectangle",
                         "approx": False, "rectangles": list(rectangles)}],
            "circles": list(circles or []),
            "status_counts": {}, "total_rectangles": len(rectangles)}


class TheMarkRuleReadsTheCorpusMarks(unittest.TestCase):
    """The noun is the LAST letter of the mark's alphabetic prefix."""

    def test_the_plain_column_marks_are_columns(self):
        # test7's own seventeen, and StaircasePlan-Test2's C1..C18
        for mark in ("C1", "C2", "C6", "C8", "C9", "C10", "C12", "C17", "C18"):
            self.assertEqual(marks.mark_kind(mark), marks.KIND_COLUMN, mark)

    def test_the_corpus_column_numbers_that_are_not_bare_C_are_columns_too(self):
        # Project1 and test8 number their columns AC1..AC18 / BC1..BC28 /
        # ALC1..ALC5 / BLC1..BLC4, every one of them on the layer the drawing
        # itself calls "COLUMN NO._ASC"
        for mark in ("AC1", "AC18", "BC1", "BC20", "ALC1", "ALC5",
                     "BLC1", "BLC4"):
            self.assertEqual(marks.mark_kind(mark), marks.KIND_COLUMN, mark)

    def test_the_shear_wall_marks_are_walls(self):
        # StaircasePlan-Test1's SW1..SW6, and test15/test16's SW9..SW11
        for mark in ("SW1", "SW2", "SW3", "SW4", "SW5", "SW6",
                     "SW9", "SW10", "SW11"):
            self.assertEqual(marks.mark_kind(mark), marks.KIND_WALL, mark)

    def test_the_users_own_W_and_CW_read_as_walls(self):
        # the corpus carries NO bare W mark in twenty drawings, so nothing
        # here is measured -- these are the user's rule, honoured as given,
        # and CW falls out of the same reading that gives SW
        for mark in ("W1", "W12", "CW1"):
            self.assertEqual(marks.mark_kind(mark), marks.KIND_WALL, mark)

    def test_a_beam_or_slab_or_footing_mark_abstains(self):
        # test5 lands 289 of these on column rectangles. Read "starts with B"
        # as a vote and every one of them would re-classify its member.
        for mark in ("B1", "B12", "B520", "B625", "S1", "S12", "F1", "F3",
                     "RF1", "P18", "T1", "BKT1"):
            self.assertIsNone(marks.mark_kind(mark), mark)

    def test_no_mark_at_all_abstains(self):
        for mark in (None, "", "   ", "WALL", "COLUMN"):
            self.assertIsNone(marks.mark_kind(mark), repr(mark))

    def test_separators_and_case_are_forgiven(self):
        # parse_mark only ever yields the tight C1/SW1 form, but a mark from a
        # schedule cell or a settings file need not be that tidy
        self.assertEqual(marks.mark_kind("C-1"), marks.KIND_COLUMN)
        self.assertEqual(marks.mark_kind("c1"), marks.KIND_COLUMN)
        self.assertEqual(marks.mark_kind("sw 1"), marks.KIND_WALL)
        self.assertEqual(marks.mark_kind("SW-11"), marks.KIND_WALL)

    def test_the_NOUN_sits_next_to_the_number_not_at_the_front(self):
        # The owner spelled his convention out: "T1 refer mean Tower-1 and SW as
        # Shearwall and 95 is number". Read on the letters before the FIRST
        # digit this saw only the "T" of the tower and abstained, so every one
        # of his shear walls routed on its L/B ratio instead of on its name.
        # MEASURED over the corpus's 1573 distinct marks: no answer changes, and
        # 410 that abstained are now decided -- every one an SW or CW wall.
        for mark in ("T1SW95", "T1SW1", "T1SW109A", "T2W10A"):
            self.assertEqual(marks.mark_kind(mark), marks.KIND_WALL, mark)
        self.assertEqual(marks.mark_kind("T2CW3B"), marks.KIND_WALL)

    def test_a_tower_prefixed_beam_still_abstains(self):
        # the noun has to BE a noun: "B" is not in the convention either way
        for mark in ("T1B20", "T2RB12"):
            self.assertIsNone(marks.mark_kind(mark), mark)


class TheRatioRuleIsTheCodesRule(unittest.TestCase):
    def test_the_threshold_is_four(self):
        self.assertEqual(marks.WALL_ASPECT_RATIO, 4.0)

    def test_the_codes_are_named_where_the_number_is(self):
        # IS 456 / IS 13920 / ACI 318 all draw the line at 4; an office on a
        # different code edits the constant, and the comment is what tells it
        # which line it is editing
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "classify", "marks.py")
        with open(path, "rb") as handle:
            source = handle.read().decode("utf-8")
        head = source.split("WALL_ASPECT_RATIO = 4.0", 1)[0]
        for code in ("IS 456", "IS 13920", "ACI 318"):
            self.assertIn(code, head, code)

    def test_L_over_B_is_the_long_side_over_the_short_one(self):
        # StaircasePlan-Test1's own two shapes, read both ways round
        self.assertAlmostEqual(marks.aspect_ratio(300.0, 3300.0), 11.0)
        self.assertAlmostEqual(marks.aspect_ratio(6300.0, 300.0), 21.0)
        # ...and test7's, which are columns by the ratio too
        self.assertAlmostEqual(marks.aspect_ratio(600.0, 900.0), 1.5)
        self.assertAlmostEqual(marks.aspect_ratio(3000.0, 900.0), 10.0 / 3.0)

    def test_a_section_with_no_thickness_is_unmeasurable(self):
        for width, height in ((0.0, 900.0), (-1.0, 900.0), (0.0, 0.0)):
            self.assertIsNone(marks.aspect_ratio(width, height))
        self.assertIsNone(marks.aspect_ratio(None, 900.0))

    def test_four_exactly_is_a_wall_and_a_hair_under_is_a_column(self):
        # "L/B >= 4" and "L/B < 4" in the user's own words: the boundary
        # belongs to the wall
        self.assertEqual(marks.vertical_kind(None, 300.0, 1200.0),
                         (marks.KIND_WALL, "ratio"))
        self.assertEqual(marks.vertical_kind(None, 300.0, 1199.0),
                         (marks.KIND_COLUMN, "ratio"))

    def test_an_unmeasurable_section_stays_the_column_it_always_was(self):
        self.assertEqual(marks.vertical_kind(None, 0.0, 900.0),
                         (marks.KIND_COLUMN, "ratio"))


class TheMarkIsAskedBeforeTheRatio(unittest.TestCase):
    """test7 is the whole argument: three members the two rules disagree on."""

    def test_test7s_slender_C_marks_stay_columns(self):
        for mark, width, height, ratio in (("C6", 5300.0, 300.0, 17.667),
                                           ("C8", 300.0, 3300.0, 11.0),
                                           ("C10", 300.0, 5300.0, 17.667)):
            self.assertGreaterEqual(marks.aspect_ratio(width, height),
                                    marks.WALL_ASPECT_RATIO)
            self.assertAlmostEqual(marks.aspect_ratio(width, height), ratio,
                                   places=3)
            self.assertEqual(marks.vertical_kind(mark, width, height),
                             (marks.KIND_COLUMN, "mark"),
                             "%s: the drawing named it a column" % mark)

    def test_staircase_test1s_SW_marks_are_walls_and_the_ratio_agrees(self):
        for mark, width, height in (("SW1", 6300.0, 300.0),
                                    ("SW2", 300.0, 3300.0),
                                    ("SW6", 6300.0, 300.0)):
            self.assertEqual(marks.vertical_kind(mark, width, height),
                             (marks.KIND_WALL, "mark"))
            self.assertGreaterEqual(marks.aspect_ratio(width, height),
                                    marks.WALL_ASPECT_RATIO)

    def test_a_bled_beam_label_leaves_the_decision_to_the_ratio(self):
        # test5's B520 lands on a 300x900 member: ratio 3.0, so a column --
        # decided by the geometry, and credited to the geometry
        self.assertEqual(marks.vertical_kind("B520", 300.0, 900.0),
                         (marks.KIND_COLUMN, "ratio"))
        # and the same label on a slender member does NOT keep it a column
        self.assertEqual(marks.vertical_kind("B520", 300.0, 3300.0),
                         (marks.KIND_WALL, "ratio"))

    def test_an_unmarked_member_is_decided_by_L_over_B_alone(self):
        self.assertEqual(marks.vertical_kind(None, 600.0, 900.0),
                         (marks.KIND_COLUMN, "ratio"))
        self.assertEqual(marks.vertical_kind(None, 300.0, 3300.0),
                         (marks.KIND_WALL, "ratio"))


class ARectangleBecomesAWallCentreline(unittest.TestCase):
    """Along the LONG axis, at the SHORT side's thickness."""

    def _length_mm(self, segment):
        return math.hypot(segment["end"][0] - segment["start"][0],
                          segment["end"][1] - segment["start"][1]) * 304.8

    def test_a_wide_axis_aligned_member_runs_along_X(self):
        # StaircasePlan-Test1's SW1: 6300 wide, 300 deep
        segment = wall_plan.rect_wall_segment(_rect(6300.0, 300.0,
                                                    cx_mm=1000.0, cy_mm=500.0))
        self.assertAlmostEqual(segment["width_mm"], 300.0, places=6)
        self.assertAlmostEqual(segment["length_mm"], 6300.0, places=6)
        self.assertAlmostEqual(self._length_mm(segment), 6300.0, places=3)
        self.assertAlmostEqual(segment["start"][1] * 304.8, 500.0, places=6)
        self.assertAlmostEqual(segment["end"][1] * 304.8, 500.0, places=6)
        self.assertAlmostEqual(segment["start"][0] * 304.8, -2150.0, places=6)
        self.assertAlmostEqual(segment["end"][0] * 304.8, 4150.0, places=6)

    def test_a_tall_axis_aligned_member_runs_along_Y(self):
        # SW2: 300 wide, 3300 deep
        segment = wall_plan.rect_wall_segment(_rect(300.0, 3300.0))
        self.assertAlmostEqual(segment["width_mm"], 300.0, places=6)
        self.assertAlmostEqual(self._length_mm(segment), 3300.0, places=3)
        self.assertAlmostEqual(segment["start"][0], 0.0, places=9)
        self.assertAlmostEqual(segment["start"][1] * 304.8, -1650.0, places=6)
        self.assertAlmostEqual(segment["end"][1] * 304.8, 1650.0, places=6)

    def test_an_oriented_member_runs_along_its_own_long_axis(self):
        # test7's C4: 400 x 900 at 45 degrees. An OrientedRect reports its
        # SHORT side as width, so long_axis_deg IS the centreline's direction.
        segment = wall_plan.rect_wall_segment(_oriented(400.0, 900.0, 45.0))
        self.assertAlmostEqual(segment["width_mm"], 400.0, places=6)
        self.assertAlmostEqual(self._length_mm(segment), 900.0, places=3)
        dx = segment["end"][0] - segment["start"][0]
        dy = segment["end"][1] - segment["start"][1]
        self.assertAlmostEqual(math.degrees(math.atan2(dy, dx)), 45.0,
                               places=6)

    def test_an_oriented_member_at_the_corpus_angles(self):
        # test5 and test7 between them draw 7, 25, 30, 43, 61, 79, 97, 115,
        # 133 and 150 degrees; the centreline must follow every one
        for angle in (7.0, 25.0, 30.0, 43.0, 61.0, 79.0, 97.0, 115.0, 133.0,
                      150.0):
            segment = wall_plan.rect_wall_segment(
                _oriented(300.0, 3300.0, angle, cx_mm=100.0, cy_mm=-200.0))
            dx = segment["end"][0] - segment["start"][0]
            dy = segment["end"][1] - segment["start"][1]
            self.assertAlmostEqual(math.degrees(math.atan2(dy, dx)) % 180.0,
                                   angle % 180.0, places=6)
            self.assertAlmostEqual(self._length_mm(segment), 3300.0, places=3)
            # the centre is still the member's centre
            mid_x = (segment["start"][0] + segment["end"][0]) / 2.0 * 304.8
            mid_y = (segment["start"][1] + segment["end"][1]) / 2.0 * 304.8
            self.assertAlmostEqual(mid_x, 100.0, places=6)
            self.assertAlmostEqual(mid_y, -200.0, places=6)

    def test_a_square_member_picks_X_deterministically(self):
        segment = wall_plan.rect_wall_segment(_rect(600.0, 600.0))
        self.assertAlmostEqual(segment["width_mm"], 600.0, places=6)
        self.assertAlmostEqual(segment["start"][1], 0.0, places=9)
        self.assertAlmostEqual(segment["end"][1], 0.0, places=9)

    def test_the_segment_is_a_structural_wall_and_carries_its_mark(self):
        segment = wall_plan.rect_wall_segment(_rect(300.0, 3300.0, mark="SW2"))
        self.assertEqual(segment["kind"], "structural")
        self.assertEqual(segment["source"], "member")
        self.assertEqual(segment["mark"], "SW2")
        # ...and it is the shape place_walls already takes
        for key in ("start", "end", "width_mm", "length_mm", "kind"):
            self.assertIn(key, segment)

    def test_a_member_with_no_thickness_yields_nothing(self):
        self.assertIsNone(wall_plan.rect_wall_segment(
            {"center": [0.0, 0.0, 0.0], "width_mm": 0.0, "height_mm": 900.0}))


class TheThreeModesRouteTheMembers(unittest.TestCase):

    # StructuralPlan-Test7's seventeen members, exactly as measured
    TEST7 = [("C12", 3000.0, 900.0), ("C10", 300.0, 5300.0),
             ("C9", 600.0, 900.0), ("C8", 300.0, 3300.0),
             ("C6", 5300.0, 300.0), ("C3", 600.0, 750.0),
             ("C2", 500.0, 900.0), ("C11", 600.0, 900.0),
             ("C5", 600.0, 450.0), ("C15", 600.0, 900.0),
             ("C15", 600.0, 900.0), ("C17", 600.0, 900.0),
             ("C17", 600.0, 900.0), ("C14", 300.0, 600.0),
             ("C4", 400.0, 900.0), ("C18", 400.0, 900.0),
             ("C1", 600.0, 900.0)]
    # StaircasePlan-Test1's six
    TEST1 = [("SW2", 300.0, 3300.0), ("SW3", 300.0, 3300.0),
             ("SW1", 6300.0, 300.0), ("SW6", 6300.0, 300.0),
             ("SW4", 300.0, 3300.0), ("SW5", 300.0, 3300.0)]

    def _sections(self, rows):
        return _sections([_rect(w, h, mark=m) for m, w, h in rows])

    def _kept(self, split):
        return sum(len(entry["rectangles"])
                   for entry in split["sections"]["entries"])

    def test_column_mode_moves_nothing(self):
        for rows in (self.TEST7, self.TEST1):
            split = wall_plan.split_vertical_members(self._sections(rows),
                                                     wall_plan.MODE_COLUMN)
            self.assertEqual(split["segments"], [])
            self.assertEqual(self._kept(split), len(rows))
            self.assertEqual(split["counts"]["wall"], 0)
            self.assertEqual(split["counts"]["column"], len(rows))

    def test_wall_mode_moves_everything(self):
        for rows in (self.TEST7, self.TEST1):
            split = wall_plan.split_vertical_members(self._sections(rows),
                                                     wall_plan.MODE_WALL)
            self.assertEqual(len(split["segments"]), len(rows))
            self.assertEqual(self._kept(split), 0)
            self.assertEqual(split["sections"]["entries"], [])

    def test_combine_keeps_test7_whole_because_its_marks_say_column(self):
        # 17 columns, 0 walls -- even though C6, C8 and C10 are 11 to 17.7 by
        # the ratio. This is the number that says the mark is asked first.
        split = wall_plan.split_vertical_members(self._sections(self.TEST7),
                                                 wall_plan.MODE_COMBINE)
        self.assertEqual(split["counts"]["column"], 17)
        self.assertEqual(split["counts"]["wall"], 0)
        self.assertEqual(split["counts"]["column_mark"], 17)
        self.assertEqual(split["counts"]["column_ratio"], 0)

    def test_combine_walls_all_six_of_staircase_test1(self):
        split = wall_plan.split_vertical_members(self._sections(self.TEST1),
                                                 wall_plan.MODE_COMBINE)
        self.assertEqual(split["counts"]["wall"], 6)
        self.assertEqual(split["counts"]["wall_mark"], 6)
        self.assertEqual(split["counts"]["column"], 0)
        self.assertEqual(len(split["segments"]), 6)

    def test_combine_falls_back_to_the_ratio_where_the_marks_are_gone(self):
        # the same seventeen sections with their labels stripped: now the L/B
        # rule alone decides, and the three slender ones become walls
        rows = [(None, w, h) for _m, w, h in self.TEST7]
        split = wall_plan.split_vertical_members(self._sections(rows),
                                                 wall_plan.MODE_COMBINE)
        self.assertEqual(split["counts"]["wall"], 3)
        self.assertEqual(split["counts"]["wall_ratio"], 3)
        self.assertEqual(split["counts"]["wall_mark"], 0)
        self.assertEqual(split["counts"]["column"], 14)
        self.assertEqual(split["counts"]["column_ratio"], 14)

    def test_a_lift_or_stair_region_never_becomes_a_wall(self):
        # a 2700x3300 region is what place_columns already skips as a
        # lift/stair area; wall mode must not cast a 2700 mm thick wall out
        # of a stair void
        sections = _sections([_rect(2700.0, 3300.0), _rect(300.0, 3300.0)])
        for mode in (wall_plan.MODE_WALL, wall_plan.MODE_COMBINE):
            split = wall_plan.split_vertical_members(sections, mode,
                                                     region_max_side_mm=1500.0)
            self.assertEqual(len(split["segments"]), 1, mode)
            self.assertEqual(self._kept(split), 1, mode)
            self.assertEqual(split["counts"]["region"], 1, mode)

    def test_round_columns_are_never_touched(self):
        circles = [{"center": [0.0, 0.0, 0.0], "diameter_mm": 750.0},
                   {"center": [1.0, 0.0, 0.0], "diameter_mm": 900.0}]
        sections = _sections([_rect(300.0, 3300.0)], circles=circles)
        for mode in wall_plan.MODES:
            split = wall_plan.split_vertical_members(sections, mode)
            self.assertEqual(split["sections"]["circles"], circles, mode)
            self.assertEqual(split["counts"]["circles"], 2, mode)

    def test_the_incoming_sections_are_never_mutated(self):
        sections = _sections([_rect(300.0, 3300.0), _rect(600.0, 900.0)])
        before = [len(entry["rectangles"]) for entry in sections["entries"]]
        wall_plan.split_vertical_members(sections, wall_plan.MODE_WALL)
        self.assertEqual([len(entry["rectangles"])
                          for entry in sections["entries"]], before)

    def test_an_unknown_or_missing_mode_is_the_column_default(self):
        # a settings file from before this row, a hand-edited one, or a value
        # from a newer build all land on the run every earlier version gave
        for mode in (None, "", "   ", "shear", "walls", "COLUMNS",
                     7, 0, True, ["wall"], {"mode": "wall"}):
            self.assertEqual(wall_plan.normalise_mode(mode),
                             wall_plan.MODE_COLUMN, repr(mode))
        # ...and the three real ones survive their own casing
        for mode in ("Column", "WALL", " combine "):
            self.assertIn(wall_plan.normalise_mode(mode), wall_plan.MODES)
        split = wall_plan.split_vertical_members(
            self._sections(self.TEST1), "something the dialog never emits")
        self.assertEqual(split["segments"], [])
        self.assertEqual(split["counts"]["column"], 6)


class TheSplitSaysWhatItDid(unittest.TestCase):
    """Nothing silent: the console names both totals and both reasons."""

    def _console(self, rows, mode):
        sections = _sections([_rect(w, h, mark=m) for m, w, h in rows])
        return wall_plan.split_vertical_members(sections, mode)["console"]

    def test_column_mode_still_says_how_many_it_placed(self):
        lines = self._console(TheThreeModesRouteTheMembers.TEST7,
                              wall_plan.MODE_COLUMN)
        self.assertTrue(any("17 placed as columns" in line for line in lines),
                        lines)

    def test_wall_mode_says_how_many_went_over(self):
        lines = self._console(TheThreeModesRouteTheMembers.TEST1,
                              wall_plan.MODE_WALL)
        self.assertTrue(any("6 placed as walls" in line for line in lines),
                        lines)

    def test_combine_groups_the_two_reasons_apart(self):
        rows = [(None, w, h) for _m, w, h
                in TheThreeModesRouteTheMembers.TEST7]
        lines = self._console(rows, wall_plan.MODE_COMBINE)
        text = "\n".join(lines)
        self.assertIn("14 column(s) + 3 wall(s)", text)
        self.assertIn("columns: 0 named by their mark, 14 by L/B < 4.", text)
        self.assertIn("walls: 0 named by their mark, 3 by L/B >= 4.", text)

    def test_the_marks_and_the_ratio_are_counted_apart(self):
        # one marked wall, one marked column, one of each by the ratio
        rows = [("SW1", 6300.0, 300.0), ("C10", 300.0, 5300.0),
                (None, 300.0, 3300.0), (None, 600.0, 900.0)]
        lines = self._console(rows, wall_plan.MODE_COMBINE)
        text = "\n".join(lines)
        self.assertIn("2 column(s) + 2 wall(s)", text)
        self.assertIn("columns: 1 named by their mark, 1 by L/B < 4.", text)
        self.assertIn("walls: 1 named by their mark, 1 by L/B >= 4.", text)

    def test_the_round_columns_are_explained_not_just_left_out(self):
        sections = _sections([_rect(300.0, 3300.0)],
                             circles=[{"center": [0.0, 0.0, 0.0],
                                       "diameter_mm": 750.0}])
        lines = wall_plan.split_vertical_members(
            sections, wall_plan.MODE_COMBINE)["console"]
        self.assertTrue(any("no L/B and no long axis" in line
                            for line in lines), lines)


if __name__ == "__main__":
    unittest.main()
