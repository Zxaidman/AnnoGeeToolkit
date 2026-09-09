# -*- coding: utf-8 -*-
"""How far a column runs, from the `_START` and `_STOP` layers (FEAT-16).

The owner chose reading A of two he was offered: "the layer names the column's
OWN EXTENT: a `_STOP` column drawn on a plan is the LAST storey it exists in,
and a `_START` column is the FIRST."

The point of it is that a multi-storey sheet is built one plan per storey, so a
column running ten floors comes out as ten one-storey columns stacked on each
other. These two layers say where the real column begins and ends.

Standalone (no Revit): the storeys are typed in bottom-up.
"""

import unittest

import _loader


column_extent = _loader.load("column_extent")

_FT = 1.0 / 304.8


class ReadingTheLayerName(unittest.TestCase):
    """The suffix decides; the office's own prefix is nobody's business."""

    def test_test17_writes_these_two(self):
        # `S-COLUM_STOP` is the drawing's spelling, one M, and is not a typo.
        self.assertEqual(column_extent.mark_of("S-COLUM_STOP"), "stop")
        self.assertEqual(column_extent.mark_of("S-COLUMN_START"), "start")

    def test_an_ordinary_column_layer_is_neither(self):
        for name in ("S-COLUMN", "COL", "S.STUB COL", "S-COLUMN_SHEAR WALL"):
            self.assertIsNone(column_extent.mark_of(name), name)

    def test_a_dash_or_a_space_reads_the_same_as_an_underscore(self):
        for name in ("COL-STOP", "COL STOP", "COL_STOP"):
            self.assertEqual(column_extent.mark_of(name), "stop", name)
        for name in ("COL-START", "COL START", "COL_START"):
            self.assertEqual(column_extent.mark_of(name), "start", name)

    def test_case_and_trailing_space_do_not_matter(self):
        self.assertEqual(column_extent.mark_of("s-colum_stop  "), "stop")

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertIsNone(column_extent.mark_of(None))
        self.assertIsNone(column_extent.mark_of(""))

    def test_a_name_that_merely_contains_the_word_is_not_a_mark(self):
        # The suffix, not a substring: a "STOPPING" layer is not a stop layer.
        self.assertIsNone(column_extent.mark_of("S-COLUMN_STOPPING"))


class TellingOneColumnFromAnotherAcrossPlans(unittest.TestCase):
    """The records arrive shifted to each plan's own origin, so position is id.

    CLUSTERED, not binned: rounding into a cell puts two footprints a
    millimetre apart either side of an edge and calls them two columns, which
    is the one job this has.
    """

    def test_the_same_position_on_two_plans_is_one_column(self):
        got = column_extent.key_for([(10.0, 20.0), (10.0, 20.0)])
        self.assertEqual(got[0], got[1])

    def test_drafting_noise_does_not_split_a_column_in_two(self):
        near = (10.0 + 20 * _FT, 20.0 + 20 * _FT)      # 20 mm off
        got = column_extent.key_for([(10.0, 20.0), near])
        self.assertEqual(got[0], got[1])

    def test_noise_across_a_round_number_still_holds_together(self):
        # The case binning gets wrong: either side of a cell edge.
        a = (10.0, 20.0)
        b = (10.0 + 1 * _FT, 20.0)                     # 1 mm off
        got = column_extent.key_for([a, b])
        self.assertEqual(got[0], got[1])

    def test_two_real_columns_stay_apart(self):
        far = (10.0 + 3000 * _FT, 20.0)                # 3 m away
        got = column_extent.key_for([(10.0, 20.0), far])
        self.assertNotEqual(got[0], got[1])

    def test_a_missing_point_takes_no_column_with_it(self):
        got = column_extent.key_for([(10.0, 20.0), None, (10.0, 20.0)])
        self.assertNotIn(1, got)
        self.assertEqual(got[0], got[2])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(column_extent.key_for([]), {})
        self.assertEqual(column_extent.key_for(None), {})


class HowFarTheColumnRuns(unittest.TestCase):

    def test_a_column_drawn_on_one_plan_spans_that_one(self):
        got = column_extent.extents([[("A", None)]])
        self.assertEqual(got["A"], (0, 0))

    def test_with_no_marks_it_spans_what_it_is_drawn_on(self):
        got = column_extent.extents([[("A", None)], [("A", None)],
                                     [("A", None)]])
        self.assertEqual(got["A"], (0, 2))

    def test_a_stop_mark_ends_it_there(self):
        # Drawn on four floors, marked stop on the third: it exists 0..2.
        got = column_extent.extents([[("A", None)], [("A", None)],
                                     [("A", "stop")], [("A", None)]])
        self.assertEqual(got["A"], (0, 2))

    def test_a_start_mark_begins_it_there(self):
        got = column_extent.extents([[("A", None)], [("A", "start")],
                                     [("A", None)]])
        self.assertEqual(got["A"], (1, 2))

    def test_a_start_and_a_stop_give_the_span_between_them(self):
        got = column_extent.extents([[("A", None)], [("A", "start")],
                                     [("A", None)], [("A", "stop")],
                                     [("A", None)]])
        self.assertEqual(got["A"], (1, 3))

    def test_the_lowest_start_wins_and_the_highest_stop(self):
        got = column_extent.extents([[("A", "start")], [("A", "start")],
                                     [("A", "stop")], [("A", "stop")]])
        self.assertEqual(got["A"], (0, 3))

    def test_a_drawing_that_stops_before_it_starts_still_gives_one_column(self):
        # Impossible as written; better one column than none.
        got = column_extent.extents([[("A", "stop")], [("A", "start")]])
        self.assertEqual(got["A"], (1, 1))

    def test_columns_are_kept_apart_from_each_other(self):
        got = column_extent.extents([[("A", None), ("B", "start")],
                                     [("A", "stop"), ("B", None)]])
        self.assertEqual(got["A"], (0, 1))
        self.assertEqual(got["B"], (0, 1))

    def test_an_empty_stack_measures_nothing(self):
        self.assertEqual(column_extent.extents([]), {})
        self.assertEqual(column_extent.extents(None), {})

    def test_a_storey_with_nothing_on_it_is_not_a_gap_in_the_span(self):
        got = column_extent.extents([[("A", None)], [], [("A", None)]])
        self.assertEqual(got["A"], (0, 2))


class WhichStoreyPlacesIt(unittest.TestCase):
    """A column that spans floors is built ONCE, or it stacks on itself."""

    def test_the_first_storey_places_it(self):
        self.assertTrue(column_extent.build_here((1, 3), 1))

    def test_every_storey_above_skips_it(self):
        for storey in (2, 3):
            self.assertFalse(column_extent.build_here((1, 3), storey))

    def test_a_storey_below_its_start_does_not_place_it(self):
        self.assertFalse(column_extent.build_here((1, 3), 0))

    def test_the_ordinary_one_storey_column_is_told_apart(self):
        self.assertTrue(column_extent.spans_one_storey((2, 2)))
        self.assertFalse(column_extent.spans_one_storey((2, 5)))


if __name__ == "__main__":
    unittest.main()
