# -*- coding: utf-8 -*-
"""Geometry integrity, G001-G007."""

import unittest

import _support
from _support import context, curve, rect, rule_ids
from cad_qa.checks import geometry


class BaselineTests(unittest.TestCase):

    def test_a_sound_plan_trips_no_geometry_rule(self):
        self.assertEqual(rule_ids(geometry.check(_support.plan())), [])


class EmptyTests(unittest.TestCase):

    def test_a_drawing_with_no_records_is_a_single_error(self):
        found = geometry.check(context([]))
        self.assertEqual(rule_ids(found), ["G001"])
        self.assertEqual(found[0].severity, "Error")


class DegenerateTests(unittest.TestCase):

    def test_a_record_of_one_point_is_reported(self):
        found = geometry.check(_support.plan([curve("S-COLS", [(5, 5)])]))
        self.assertIn("G002", rule_ids(found))

    def test_a_record_whose_points_are_all_identical_is_reported(self):
        found = geometry.check(_support.plan(
            [curve("S-COLS", [(5, 5), (5, 5), (5, 5)])]))
        self.assertIn("G002", rule_ids(found))


class DuplicateTests(unittest.TestCase):

    def test_the_same_outline_drawn_twice_is_reported(self):
        found = [f for f in geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400),
             rect("S-COLS", 5000, 5000, 400, 400)])) if f.rule == "G003"]
        self.assertEqual(found[0].count, 1)

    def test_two_outlines_a_hair_apart_still_count_as_duplicates(self):
        """Exact float comparison would miss every real duplicate."""
        found = geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400),
             rect("S-COLS", 5000.0001, 5000.0001, 400, 400)]))
        self.assertIn("G003", rule_ids(found))

    def test_the_same_shape_on_different_layers_is_not_a_duplicate(self):
        found = geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400),
             rect("S-BEAM", 5000, 5000, 400, 400)]))
        self.assertNotIn("G003", rule_ids(found))


class OffPlaneTests(unittest.TestCase):

    def test_classified_geometry_off_the_plane_is_reported(self):
        found = geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400)]
            + [curve("S-COLS", [(0, 0, 500), (100, 100, 500)], kind="line")]))
        self.assertIn("G004", rule_ids(found))

    def test_unmapped_geometry_off_the_plane_is_ignored(self):
        """It is not being built, so its Z cannot cost anything."""
        found = geometry.check(_support.plan(
            [curve("RANDOM", [(0, 0, 500), (100, 100, 500)], kind="line")]))
        self.assertNotIn("G004", rule_ids(found))


class ClosureTests(unittest.TestCase):

    def test_an_open_column_outline_is_reported(self):
        found = geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400, closed=False)]))
        self.assertIn("G005", rule_ids(found))

    def test_a_closed_column_outline_is_not(self):
        found = geometry.check(_support.plan(
            [rect("S-COLS", 5000, 5000, 400, 400, closed=True)]))
        self.assertNotIn("G005", rule_ids(found))

    def test_an_open_beam_run_is_not_a_closure_fault(self):
        """Beams are built from open runs; closing them is not the convention."""
        found = geometry.check(_support.plan(
            [curve("S-BEAM", [(0, 0), (9000, 0), (9000, 500)])]))
        self.assertNotIn("G005", rule_ids(found))

    def test_a_ring_too_small_to_be_a_member_is_not_reported(self):
        found = geometry.check(_support.plan(
            [rect("S-COLS", 0, 0, 10, 10, closed=False)]))
        self.assertNotIn("G005", rule_ids(found))


class OutlierTests(unittest.TestCase):

    def test_geometry_far_from_the_body_is_reported(self):
        body = [rect("S-COLS", i * 1000, 0, 400, 400) for i in range(20)]
        stray = [curve("S-COLS", [(9000000, 9000000), (9000100, 9000100)],
                       kind="line")]
        found = geometry.check(context(body + stray))
        self.assertIn("G006", rule_ids(found))

    def test_a_tight_plan_has_no_outliers(self):
        body = [rect("S-COLS", i * 1000, 0, 400, 400) for i in range(20)]
        self.assertNotIn("G006", rule_ids(geometry.check(context(body))))


class ExtentTests(unittest.TestCase):

    def test_a_plan_read_at_the_wrong_unit_is_an_error(self):
        """A 20 m plan read as if its units were metres comes out 20 mm."""
        found = [f for f in geometry.check(context(
            [rect("S-COLS", 0, 0, 20, 10)])) if f.rule == "G007"]
        self.assertEqual(found[0].severity, "Error")

    def test_the_same_plan_at_the_right_unit_is_fine(self):
        found = geometry.check(context([rect("S-COLS", 0, 0, 20, 10)],
                                       unit_mm=1000.0))
        self.assertNotIn("G007", rule_ids(found))


if __name__ == "__main__":
    unittest.main()
