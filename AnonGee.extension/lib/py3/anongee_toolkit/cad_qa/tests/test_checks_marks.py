# -*- coding: utf-8 -*-
"""Marks, labels and sizes, M001-M006.

The false positive that shaped this module is pinned here: "C_300 X 900" is a
mark and a size, not a mark called C-300, and an earlier build reported 164 of
them on one drawing.
"""

import unittest

import _support
from _support import context, rect, text, rule_ids
from cad_qa.checks import marks


class BaselineTests(unittest.TestCase):

    def test_a_sound_plan_trips_no_mark_rule(self):
        self.assertEqual(rule_ids(marks.check(_support.plan())), [])


class UnparsedLabelTests(unittest.TestCase):

    def test_a_size_the_parser_cannot_read_is_reported(self):
        """400MM X 400MM: the unit sits between the number and the separator."""
        found = marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C2 400MM X 400MM", (5000, 5000))]))
        self.assertIn("M001", rule_ids(found))

    def test_a_dash_separated_size_is_reported(self):
        found = marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "300-600", (5000, 5000))]))
        self.assertIn("M001", rule_ids(found))

    def test_a_mark_with_a_separator_is_reported(self):
        found = [f for f in marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C-1", (1200, 1200))]))
            if f.rule == "M001"]
        self.assertEqual(found[0].subject, "mark")

    def test_a_sized_label_is_not_mistaken_for_an_unreadable_mark(self):
        """THE regression: C_300 X 900 is mark C plus a size, and parses."""
        found = marks.check(context(
            [rect("S-COLS", 1000, 1000, 300, 900)],
            [text("S-COLS-IDEN", "C_300 X 900", (1100, 1100))]))
        self.assertNotIn("M001", rule_ids(found))

    def test_a_bare_grid_bubble_is_not_a_broken_label(self):
        found = marks.check(_support.plan(
            extra_texts=[text("S-GRID-IDEN", "A", (0, 0))]))
        self.assertNotIn("M001", rule_ids(found))


class MissingSizeTests(unittest.TestCase):

    def test_a_drawing_with_no_sizes_at_all_is_an_error(self):
        found = [f for f in marks.check(context(
            [rect("S-COLS", 0, 0, 400, 400)],
            [text("S-COLS-IDEN", "SOME NOTE", (0, 0))])) if f.rule == "M002"]
        self.assertEqual(found[0].severity, "Error")

    def test_sizes_living_in_a_schedule_are_a_warning_not_an_error(self):
        """test15 and StaircasePlan-Test2: 119 schedule rows, no plan labels.

        The schedule is set directly rather than drafted as fake table text.
        A fake table good enough for the real parser has to spell its sizes as
        "400x400" -- which parse_texts then reads as a sized label, so M002
        never fires and the test passes for the wrong reason. The unit under
        test is "M002 consults the schedule", not "the schedule parser reads a
        table I invented"; the real tables are exercised by the corpus leg.
        """
        drawing = context([rect("S-COLS", 0, 0, 400, 400)],
                          [text("S-COLS-IDEN", "SEE SCHEDULE", (0, 0))])
        drawing._schedule = {"C1": {"b_mm": 400.0, "h_mm": 400.0}}
        found = [f for f in marks.check(drawing) if f.rule == "M002"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "Warning")

    def test_a_drawing_with_no_schedule_and_no_labels_stays_an_error(self):
        drawing = context([rect("S-COLS", 0, 0, 400, 400)],
                          [text("S-COLS-IDEN", "SEE SCHEDULE", (0, 0))])
        drawing._schedule = {}
        found = [f for f in marks.check(drawing) if f.rule == "M002"]
        self.assertEqual(found[0].severity, "Error")

    def test_an_empty_drawing_is_not_told_it_has_no_sizes(self):
        """G001 says it once. Saying it twice helps nobody."""
        self.assertNotIn("M002", rule_ids(marks.check(context([]))))


class ImplausibleSizeTests(unittest.TestCase):

    def test_metres_typed_as_millimetres_are_caught(self):
        found = marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C3 0.4x0.4", (5000, 5000))]))
        self.assertIn("M003", rule_ids(found))

    def test_an_ordinary_column_size_is_not_flagged(self):
        found = marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C3 300x600", (1200, 1200))]))
        self.assertNotIn("M003", rule_ids(found))


class ConflictingMarkTests(unittest.TestCase):

    def test_one_mark_at_two_sizes_is_an_error(self):
        found = [f for f in marks.check(context(
            [rect("S-COLS", 1000, 1000, 400, 400)],
            [text("S-COLS-IDEN", "C1 400x400", (1100, 1100)),
             text("S-COLS-IDEN", "C1 300x600", (1200, 1200))]))
            if f.rule == "M004"]
        self.assertEqual(found[0].severity, "Error")
        self.assertEqual(found[0].subject, "C1")

    def test_the_same_mark_at_the_same_size_twice_is_fine(self):
        found = marks.check(context(
            [rect("S-COLS", 1000, 1000, 400, 400)],
            [text("S-COLS-IDEN", "C1 400x400", (1100, 1100)),
             text("S-COLS-IDEN", "C1 400x400", (1200, 1200))]))
        self.assertNotIn("M004", rule_ids(found))


class OrphanLabelTests(unittest.TestCase):

    def test_a_label_far_from_every_member_is_reported(self):
        found = marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C9 400x400", (900000, 900000))]))
        self.assertIn("M005", rule_ids(found))

    def test_a_label_beside_its_column_is_not_an_orphan(self):
        found = marks.check(context(
            [rect("S-COLS", 1000, 1000, 400, 400)],
            [text("S-COLS-IDEN", "C1 400x400", (1200, 1200))]))
        self.assertNotIn("M005", rule_ids(found))

    def test_with_no_members_at_all_nothing_is_called_an_orphan(self):
        """L003 already says there are no columns to be near."""
        found = marks.check(context(
            [], [text("S-COLS-IDEN", "C1 400x400", (0, 0))]))
        self.assertNotIn("M005", rule_ids(found))


class MarkWithoutSizeTests(unittest.TestCase):

    def test_a_mark_only_label_is_information(self):
        found = [f for f in marks.check(_support.plan(
            extra_texts=[text("S-COLS-IDEN", "C9", (1200, 1200))]))
            if f.rule == "M006"]
        self.assertEqual(found[0].severity, "Info")


if __name__ == "__main__":
    unittest.main()
