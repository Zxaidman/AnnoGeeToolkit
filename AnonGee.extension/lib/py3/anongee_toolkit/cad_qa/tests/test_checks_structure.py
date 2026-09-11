# -*- coding: utf-8 -*-
"""Grid and storey structure, S001-S006."""

import unittest

import _support
from _support import context, curve, rect, text, rule_ids
from cad_qa.checks import structure


def _boundary(x, y, width=20000, height=10000):
    return rect("S-BOUNDARY", x, y, width, height)


def _origin(x, y):
    return rect("S-ORIGIN", x, y, 100, 100)


class GridDirectionTests(unittest.TestCase):

    def test_grids_in_both_directions_are_fine(self):
        self.assertNotIn("S002", rule_ids(structure.check(_support.plan())))

    def test_grids_in_one_direction_only_are_reported(self):
        found = structure.check(context([
            curve("S-GRID", [(0, 0), (20000, 0)], kind="line"),
            curve("S-GRID", [(0, 5000), (20000, 5000)], kind="line")]))
        self.assertIn("S002", rule_ids(found))

    def test_a_drawing_with_no_grid_is_left_to_L002(self):
        self.assertNotIn("S002", rule_ids(structure.check(context([
            rect("S-COLS", 0, 0, 400, 400)]))))

    def test_a_short_tick_is_not_counted_as_a_grid_direction(self):
        found = structure.check(context([
            curve("S-GRID", [(0, 0), (20000, 0)], kind="line"),
            curve("S-GRID", [(0, 0), (0, 50)], kind="line")]))
        self.assertIn("S002", rule_ids(found))


class GridLabelTests(unittest.TestCase):

    def test_grids_with_no_bubble_text_are_reported(self):
        found = structure.check(context(
            [curve("S-GRID", [(0, 0), (20000, 0)], kind="line")],
            [text("RANDOM", "hello", (0, 0))]))
        self.assertIn("S001", rule_ids(found))

    def test_grid_text_on_a_recognised_layer_satisfies_it(self):
        found = structure.check(context(
            [curve("S-GRID", [(0, 0), (20000, 0)], kind="line"),
             curve("S-GRID", [(0, 0), (0, 10000)], kind="line")],
            [text("S-GRID-IDEN", "A", (0, 0))]))
        self.assertNotIn("S001", rule_ids(found))


class StoreyPairingTests(unittest.TestCase):

    def test_a_drawing_with_neither_is_a_single_plan(self):
        found = [f for f in structure.check(_support.plan())
                 if f.rule == "S006"]
        self.assertEqual(found[0].severity, "Info")

    def test_boundaries_with_no_origins_is_an_error(self):
        found = [f for f in structure.check(context(
            [_boundary(0, 0), _boundary(0, 20000)])) if f.rule == "S004"]
        self.assertEqual(found[0].severity, "Error")

    def test_origins_with_no_boundaries_is_a_warning(self):
        found = [f for f in structure.check(context(
            [_origin(100, 100)])) if f.rule == "S005"]
        self.assertEqual(found[0].severity, "Warning")

    def test_mismatched_counts_are_an_error(self):
        found = [f for f in structure.check(context(
            [_boundary(0, 0), _boundary(0, 20000), _origin(100, 100)]))
            if f.rule == "S003"]
        self.assertEqual(found[0].severity, "Error")

    def test_matched_counts_that_pair_up_are_silent(self):
        found = structure.check(context(
            [_boundary(0, 0), _origin(100, 100),
             _boundary(0, 20000), _origin(100, 20100)]))
        self.assertNotIn("S003", rule_ids(found))

    def test_counts_can_agree_while_the_pairing_does_not(self):
        """Two origins in one boundary and none in the other. A count is blind
        to this and it builds two storeys on top of each other."""
        found = [f for f in structure.check(context(
            [_boundary(0, 0), _origin(100, 100),
             _boundary(0, 20000), _origin(200, 200)])) if f.rule == "S003"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "Warning")


if __name__ == "__main__":
    unittest.main()
