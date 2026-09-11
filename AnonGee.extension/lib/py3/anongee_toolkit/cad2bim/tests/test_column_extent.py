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
    """A RUN is a stretch of storeys that is one column, cut by the marks.

    The rows are `(key, mark)`, a key being a column's whole IDENTITY -- its
    place AND its section (see `PlanningTheWholeStack`) -- so everything under
    one key is the same member at the same size and only the marks cut it.
    """

    def spans(self, storeys):
        return column_extent.extents(storeys)

    def test_a_column_drawn_on_one_plan_spans_that_one(self):
        self.assertEqual(self.spans([[("A", None)]]), {("A", 0): (0, 0)})

    def test_with_no_marks_it_runs_through_what_it_is_drawn_on(self):
        self.assertEqual(self.spans([[("A", None)]] * 3), {("A", 0): (0, 2)})

    def test_a_stop_mark_ends_the_run_there(self):
        # Drawn on four floors, marked stop on the third: it exists 0..2.
        got = self.spans([[("A", None)], [("A", None)],
                          [("A", "stop")], [("A", None)]])
        self.assertEqual(got[("A", 0)], (0, 2))

    def test_what_is_drawn_above_a_stop_is_still_built(self):
        # Three of test17's columns contradict their own layer. The storeys
        # above become the next run rather than being dropped.
        got = self.spans([[("A", "stop")], [("A", None)], [("A", None)]])
        self.assertEqual(got, {("A", 0): (0, 0), ("A", 1): (1, 2)})

    def test_a_start_mark_begins_a_run_there(self):
        got = self.spans([[("A", None)], [("A", "start")], [("A", None)]])
        self.assertEqual(got[("A", 1)], (1, 2))

    def test_a_start_and_a_stop_give_the_run_between_them(self):
        got = self.spans([[("A", None)], [("A", "start")], [("A", None)],
                          [("A", "stop")], [("A", None)]])
        self.assertIn((1, 3), got.values())

    def test_columns_are_kept_apart_from_each_other(self):
        got = self.spans([[("A", None), ("B", "start")],
                          [("A", "stop"), ("B", None)]])
        self.assertEqual(got[("A", 0)], (0, 1))
        self.assertEqual(got[("B", 0)], (0, 1))

    def test_an_empty_stack_measures_nothing(self):
        self.assertEqual(column_extent.extents([]), {})
        self.assertEqual(column_extent.extents(None), {})

    def test_a_storey_with_nothing_on_it_is_not_a_gap_in_the_span(self):
        # A column missing from one plan is one column, not two: the drawing
        # skipping a floor is a drafting habit, not a break in the structure.
        got = self.spans([[("A", None)], [], [("A", None)]])
        self.assertEqual(got, {("A", 0): (0, 2)})


class ReadingASection(unittest.TestCase):
    """Whole millimetres, from a band measured on test17's 2344 footprints."""

    def test_noise_below_a_fifth_of_a_millimetre_reads_the_same(self):
        self.assertEqual(column_extent.section_of((200.0, 500.0)),
                         column_extent.section_of((200.195, 499.87)))

    def test_a_real_change_reads_differently(self):
        self.assertNotEqual(column_extent.section_of((200.0, 500.0)),
                            column_extent.section_of((250.0, 500.0)))

    def test_orientation_is_kept(self):
        # 200 x 2150 lying the other way is a different member, not a resize.
        self.assertNotEqual(column_extent.section_of((200.0, 2150.0)),
                            column_extent.section_of((2150.0, 200.0)))

    def test_no_section_at_all_stays_that_way(self):
        self.assertIsNone(column_extent.section_of(None))

    def test_a_caller_s_own_name_for_a_section_is_left_alone(self):
        self.assertEqual(column_extent.section_of("C1"), "C1")


class WhichColumnABuiltRectangleBelongsTo(unittest.TestCase):
    """A column is not always one rectangle, so the box decides, not the centre.

    An L or a C is decomposed into legs, and a leg's centre is nowhere near the
    outline's. Matching by centre gave one leg of an L its column and left the
    others out -- 57 of test17's outlines came back with their legs disagreeing
    -- so the L was carried up a storey as one leg while the rest were rebuilt
    on every floor, putting one column through another.
    """

    def box(self, x, y, width_mm, height_mm):
        return (x, y, width_mm * _FT / 2.0, height_mm * _FT / 2.0)

    def test_a_leg_of_an_l_finds_the_column_it_came_from(self):
        # A 2000 x 2000 L: the long leg's own centre is 750 mm off the middle,
        # far past the 100 mm a centre match would allow.
        boxes = [self.box(0.0, 0.0, 2000.0, 2000.0)]
        leg = (750 * _FT, 0.0)
        self.assertEqual(column_extent.assign(boxes, leg), 0)

    def test_every_leg_of_one_outline_agrees(self):
        boxes = [self.box(0.0, 0.0, 2000.0, 2000.0)]
        legs = [(750 * _FT, 0.0), (0.0, 750 * _FT), (-750 * _FT, 750 * _FT)]
        got = [column_extent.assign(boxes, leg) for leg in legs]
        self.assertEqual(got, [0, 0, 0])

    def test_its_own_section_wins_over_a_tighter_box(self):
        # Two members on one grid point: a 250 x 1200 that stops on this floor
        # and a 200 x 1200 that carries on above, concentric. The 200 box is
        # tighter and contains both centres, so containment alone would give it
        # the 250 rectangle. The rectangle's own size does not.
        stopping = self.box(0.0, 0.0, 250.0, 1200.0) + ((250, 1200),)
        carrying = self.box(0.0, 0.0, 200.0, 1200.0) + ((200, 1200),)
        pair = [stopping, carrying]
        self.assertEqual(column_extent.assign(pair, (0.0, 0.0), (250.0, 1200.0)), 0)
        self.assertEqual(column_extent.assign(pair, (0.0, 0.0), (200.0, 1200.0)), 1)

    def test_a_leg_with_no_matching_section_still_finds_its_outline(self):
        # An L's leg is not the size of the L, so nothing matches exactly and
        # the smallest box holding it decides -- as it did before.
        l_shape = self.box(0.0, 0.0, 2000.0, 2000.0) + ((2000, 2000),)
        leg = (750 * _FT, 0.0)
        self.assertEqual(column_extent.assign([l_shape], leg, (250.0, 900.0)), 0)

    def test_a_neighbour_inside_a_long_box_still_takes_its_own(self):
        # A 200 x 4000 column reaches right over a 300 x 300 beside it. The
        # SMALLEST box containing a rectangle is the one it belongs to.
        long_one = self.box(0.0, 0.0, 200.0, 4000.0)
        small = self.box(0.0, 1000 * _FT, 300.0, 300.0)
        self.assertEqual(column_extent.assign([long_one, small],
                                              (0.0, 1000 * _FT)), 1)

    def test_a_rectangle_just_outside_falls_back_to_the_nearest_centre(self):
        # A recovered rectangle can land a little outside the drawn outline: a
        # 100 mm thick member reaches only 50 mm either side of its own centre.
        boxes = [self.box(0.0, 0.0, 100.0, 4000.0)]
        self.assertEqual(column_extent.assign(boxes, (80 * _FT, 0.0)), 0)

    def test_a_rectangle_belonging_to_no_column_says_so(self):
        boxes = [self.box(0.0, 0.0, 300.0, 300.0)]
        self.assertIsNone(column_extent.assign(boxes, (5000 * _FT, 0.0)))

    def test_a_caller_that_tracked_no_size_still_matches_by_centre(self):
        self.assertEqual(column_extent.assign([(10.0, 20.0)], (10.0, 20.0)), 0)

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertIsNone(column_extent.assign([], (0.0, 0.0)))
        self.assertIsNone(column_extent.assign(None, (0.0, 0.0)))
        self.assertIsNone(column_extent.assign([(0.0, 0.0)], None))


class PlanningTheWholeStack(unittest.TestCase):
    """`plan` is the one call the build makes: cluster, mark, cut, span."""

    def stack(self):
        # Two columns, three floors. A is drawn on all three and stops on the
        # middle one; B appears from the middle up and is marked start there.
        a, b = (10.0, 10.0), (30.0, 10.0)
        size = (300.0, 300.0)
        return [[(a, "S-COLUMN", size)],
                [(a, "S-COLUM_STOP", size), (b, "S-COLUMN_START", size)],
                [(b, "S-COLUMN", size)]]

    def test_it_finds_each_column_s_run(self):
        spans, centres = column_extent.plan(self.stack())
        a = column_extent.assign(centres, (10.0, 10.0))
        b = column_extent.assign(centres, (30.0, 10.0))
        self.assertEqual(spans[column_extent.run_at(spans, a, 0)], (0, 1))
        self.assertEqual(spans[column_extent.run_at(spans, b, 1)], (1, 2))

    def test_the_same_column_keeps_one_id_across_floors(self):
        _spans, centres = column_extent.plan(self.stack())
        # The same footprint on two floors resolves to one column.
        self.assertEqual(column_extent.assign(centres, (10.0, 10.0)),
                         column_extent.assign(centres, (10.0, 10.0)))
        self.assertNotEqual(column_extent.assign(centres, (10.0, 10.0)),
                            column_extent.assign(centres, (30.0, 10.0)))

    def test_clustering_runs_over_the_whole_stack_at_once(self):
        # Per-storey clustering would let each floor start a new id.
        size = (300.0, 300.0)
        drifting = [[((10.0, 10.0), "S-COLUMN", size)],
                    [((10.0 + 30 * _FT, 10.0), "S-COLUMN", size)],
                    [((10.0 + 60 * _FT, 10.0), "S-COLUMN", size)]]
        spans, centres = column_extent.plan(drifting)
        self.assertEqual(len(centres), 1)
        self.assertEqual(list(spans.values()), [(0, 2)])

    def test_a_column_that_reduces_up_the_building_is_two_columns(self):
        # The test17 case, end to end: nothing marks the change but the section
        # says it, and the top half must not be built at the bottom half's size.
        here = (10.0, 10.0)
        spans, columns = column_extent.plan(
            [[(here, "S-COLUMN", (200.0, 2150.0))],
             [(here, "S-COLUMN", (200.0, 2150.0))],
             [(here, "S-COLUMN", (250.0, 2150.0))]])
        self.assertEqual(len(columns), 2)
        self.assertEqual(sorted(spans.values()), [(0, 1), (2, 2)])

    def test_two_concentric_columns_are_told_apart_by_their_size(self):
        # BUG-35, and the measured shape of it: 43 of test17's stop outlines sit
        # exactly on an ordinary column outline at a different size -- a 250
        # ending on this floor, a 200 carrying on above. Position alone made
        # them one column and the wrong one got built.
        here = (10.0, 10.0)
        spans, columns = column_extent.plan(
            [[(here, "S-COLUM_STOP", (250.0, 1200.0)),
              (here, "S-COLUMN", (200.0, 1200.0))],
             [(here, "S-COLUMN", (200.0, 1200.0))],
             [(here, "S-COLUMN", (200.0, 1200.0))]])
        self.assertEqual(len(columns), 2)
        stopping = column_extent.assign(columns, here, (250.0, 1200.0))
        carrying = column_extent.assign(columns, here, (200.0, 1200.0))
        self.assertNotEqual(stopping, carrying)
        # the 250 holds the ground storey alone; the 200 takes it from there up
        self.assertEqual(spans[column_extent.run_at(spans, stopping, 0)], (0, 0))
        self.assertIsNone(column_extent.run_at(spans, carrying, 0))
        self.assertEqual(spans[column_extent.run_at(spans, carrying, 1)], (1, 2))

    def test_the_one_carrying_on_does_not_stand_in_the_one_that_stops(self):
        # BUG-37, photographed by the owner: two members on one grid point, the
        # smaller inside the larger. A plan is a section just over the floor, so
        # where a column changes it shows BOTH -- the one ending there on the
        # `_STOP` layer and the one going up, drawn ordinarily. Built as drawn,
        # they stand in each other.
        here = (10.0, 10.0)
        spans, columns = column_extent.plan(
            [[(here, "S-COLUMN", (200.0, 1200.0)),
              (here, "S-COLUM_STOP", (250.0, 1200.0))],
             [(here, "S-COLUMN", (200.0, 1200.0))]])
        carrying = column_extent.assign(columns, here, (200.0, 1200.0))
        self.assertIsNone(column_extent.run_at(spans, carrying, 0),
                          "the column above must not stand on the stop's floor")
        self.assertEqual(spans[column_extent.run_at(spans, carrying, 1)], (1, 1))

    def test_the_order_the_records_arrive_in_does_not_decide(self):
        here = (10.0, 10.0)
        stop = (here, "S-COLUM_STOP", (250.0, 1200.0))
        plain = (here, "S-COLUMN", (200.0, 1200.0))
        first, second = (column_extent.plan([[stop, plain], [plain]])[0],
                         column_extent.plan([[plain, stop], [plain]])[0])
        self.assertEqual(sorted(first.values()), sorted(second.values()))

    def test_a_column_lifted_off_the_TOP_storey_is_still_built(self):
        # Nothing above it to be lifted to, and what is drawn is always built.
        here = (10.0, 10.0)
        spans, columns = column_extent.plan(
            [[(here, "S-COLUM_STOP", (250.0, 1200.0)),
              (here, "S-COLUMN", (200.0, 1200.0))]])
        carrying = column_extent.assign(columns, here, (200.0, 1200.0))
        self.assertEqual(spans[column_extent.run_at(spans, carrying, 0)], (0, 0))

    def test_a_column_merely_NEAR_a_stop_is_left_where_it_is(self):
        # Two real columns a bay apart: the rule only moves what stands in the
        # same place, which is why it is measured as a share of the smaller
        # outline rather than a distance.
        stop_at = (10.0, 10.0)
        other = (10.0 + 3000 * _FT, 10.0)
        spans, columns = column_extent.plan(
            [[(stop_at, "S-COLUM_STOP", (250.0, 1200.0)),
              (other, "S-COLUMN", (200.0, 1200.0))]])
        near = column_extent.assign(columns, other, (200.0, 1200.0))
        self.assertEqual(spans[column_extent.run_at(spans, near, 0)], (0, 0))

    def test_a_rectangle_near_no_column_belongs_to_none(self):
        _spans, boxes = column_extent.plan(self.stack())
        self.assertIsNone(column_extent.assign(boxes, (900.0, 900.0)))

    def test_a_column_is_boxed_at_its_own_section(self):
        # The box has to hold the rectangles that column is built from, and no
        # more: it is what finds the legs of an L, and what a neighbour must
        # not be swallowed by.
        here = (10.0, 10.0)
        _spans, columns = column_extent.plan(
            [[(here, "S-COLUMN", (250.0, 2150.0))]])
        self.assertAlmostEqual(columns[0][2], 125.0 * _FT)
        self.assertAlmostEqual(columns[0][3], 1075.0 * _FT)
        self.assertEqual(columns[0][4], (250, 2150))

    def test_the_nearest_centre_wins_not_the_first_within_reach(self):
        centres = [(0.0, 0.0), (0.2, 0.0)]
        self.assertEqual(column_extent.assign(centres, (0.19, 0.0)), 1)

    def test_an_empty_stack_plans_nothing(self):
        spans, centres = column_extent.plan([])
        self.assertEqual((spans, centres), ({}, []))


class WhichRunAStoreyBelongsTo(unittest.TestCase):
    """A column is several runs, so the storey has to pick one."""

    SPANS = {("A", 0): (0, 1), ("A", 1): (2, 4), ("B", 0): (0, 4)}

    def test_the_run_covering_the_storey_is_the_one(self):
        self.assertEqual(column_extent.run_at(self.SPANS, "A", 0), ("A", 0))
        self.assertEqual(column_extent.run_at(self.SPANS, "A", 3), ("A", 1))

    def test_a_storey_no_run_covers_has_none(self):
        self.assertIsNone(column_extent.run_at(self.SPANS, "A", 9))

    def test_another_column_s_run_is_never_returned(self):
        self.assertEqual(column_extent.run_at(self.SPANS, "B", 3), ("B", 0))

    def test_a_footprint_that_matched_no_column_has_no_run(self):
        self.assertIsNone(column_extent.run_at(self.SPANS, None, 0))

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertIsNone(column_extent.run_at(None, "A", 0))
        self.assertIsNone(column_extent.run_at({}, "A", 0))


class PlanningOneStorey(unittest.TestCase):

    def test_a_column_that_starts_lower_is_skipped_here(self):
        built, skipped = column_extent.plan_storey(
            ["A"], {("A", 0): (0, 2)}, 1)
        self.assertEqual(built, {})
        self.assertEqual(skipped, [0])

    def test_a_column_that_starts_here_reaches_the_top_of_its_run(self):
        built, skipped = column_extent.plan_storey(
            ["A"], {("A", 0): (1, 3)}, 1)
        self.assertEqual(built, {0: 3})
        self.assertEqual(skipped, [])

    def test_the_storey_a_second_run_begins_on_builds_it_again(self):
        # The column reduces at storey 2: the run below was built at storey 0
        # and this is a new column, at the new section.
        spans = {("A", 0): (0, 1), ("A", 1): (2, 4)}
        self.assertEqual(column_extent.plan_storey(["A"], spans, 1)[1], [0])
        self.assertEqual(column_extent.plan_storey(["A"], spans, 2)[0], {0: 4})

    def test_a_footprint_with_no_span_is_built_exactly_as_before(self):
        built, skipped = column_extent.plan_storey([None], {}, 2)
        self.assertEqual(built, {0: 2})
        self.assertEqual(skipped, [])

    def test_a_one_storey_column_reaches_its_own_top(self):
        built, _skipped = column_extent.plan_storey(
            ["A"], {("A", 0): (2, 2)}, 2)
        self.assertEqual(built, {0: 2})

    def test_several_footprints_are_sorted_into_both_answers(self):
        built, skipped = column_extent.plan_storey(
            ["A", "B", None], {("A", 0): (0, 2), ("B", 0): (1, 4)}, 1)
        self.assertEqual(built, {1: 4, 2: 1})
        self.assertEqual(skipped, [0])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(column_extent.plan_storey([], {}, 0), ({}, []))
        self.assertEqual(column_extent.plan_storey(None, None, 0), ({}, []))


class TheStopRuleAskedOfTheRECTANGLES(unittest.TestCase):
    """`plan_storey` is given the layer each rectangle was drawn on.

    The outlines and the rectangles are not the same list: a leg of an L is
    smaller than the flat outline stopping beside it, so `assign` -- which can
    only measure boxes -- hands the leg to the column that stops. The layer says
    otherwise, and it is the drawing's own word (BUG-37).
    """

    def rows(self, *drawn):
        return [((x * _FT, y * _FT), layer, (w, h)) for x, y, layer, w, h in drawn]

    def test_a_plain_rectangle_inside_a_stopping_one_is_left_to_the_storey_above(self):
        rows = self.rows((0, 0, "S-COLUM_STOP", 1500.0, 250.0),
                         (325, 0, "S-COLUMN", 850.0, 200.0))
        built, skipped = column_extent.plan_storey(
            ["A", "A"], {("A", 0): (0, 3)}, 0, rows=rows, storeys=4)
        self.assertEqual(built, {0: 3}, "the one that stops is still built")
        self.assertEqual(skipped, [1])

    def test_the_top_plan_builds_it_anyway(self):
        # Nowhere above to lift it to, and what is drawn is always built.
        rows = self.rows((0, 0, "S-COLUM_STOP", 1500.0, 250.0),
                         (325, 0, "S-COLUMN", 850.0, 200.0))
        built, skipped = column_extent.plan_storey(
            ["A", "A"], {("A", 0): (3, 3)}, 3, rows=rows, storeys=4)
        self.assertEqual(sorted(built), [0, 1])
        self.assertEqual(skipped, [])

    def test_a_rectangle_standing_clear_of_the_stop_is_untouched(self):
        rows = self.rows((0, 0, "S-COLUM_STOP", 250.0, 250.0),
                         (3000, 0, "S-COLUMN", 250.0, 250.0))
        built, skipped = column_extent.plan_storey(
            ["A", "B"], {("A", 0): (0, 1), ("B", 0): (0, 2)}, 0,
            rows=rows, storeys=4)
        self.assertEqual(built, {0: 1, 1: 2})
        self.assertEqual(skipped, [])

    def test_without_the_rows_it_answers_exactly_as_it_did(self):
        spans = {("A", 0): (0, 3)}
        self.assertEqual(column_extent.plan_storey(["A", "A"], spans, 0),
                         ({0: 3, 1: 3}, []))

    def test_rows_without_a_stack_height_change_nothing(self):
        # Not knowing how tall the stack is, it cannot know this is not the top
        # plan -- and lifting a column off the top plan loses it for good, which
        # is the one failure nobody would see.
        rows = self.rows((0, 0, "S-COLUM_STOP", 1500.0, 250.0),
                         (325, 0, "S-COLUMN", 850.0, 200.0))
        built, skipped = column_extent.plan_storey(
            ["A", "A"], {("A", 0): (0, 3)}, 0, rows=rows)
        self.assertEqual(sorted(built), [0, 1])
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()
