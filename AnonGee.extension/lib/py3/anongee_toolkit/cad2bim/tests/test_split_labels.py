# -*- coding: utf-8 -*-
"""A member's NAME and its SIZE written as two separate texts (BUG-41).

The owner, on his 1.0.3 run: "for some reason mark and grade is not being assign
correctly for both column and beam" -- with a wall whose S-ScheduleMark was empty
and the label "T1SW1 250X2750" drawn right beside it.

The drawing writes that label as TWO DXF texts, the name directly above the size:

    T1SW1          a name and no size
    250X2750       a size and no name

Read one at a time neither half is a label. Measured on the drawing he ran, its
S-COL-IDEN layer is an exact 340 / 340 split of the two kinds, and not one of its
346 sized texts carried a mark -- so all 171 members were built unnamed.

Two things had to change, and both were measured across the whole corpus first:
the mark pattern could not reach "T1SW41a" at all, and nothing joined the halves.

Standalone (no Revit).
"""

import unittest

import _loader


marks = _loader.load("classify.marks")

_FT = 1.0 / 304.8


class _Text(object):
    """A TextRecord as the reader hands one over, in mm."""

    def __init__(self, text, x_mm=0.0, y_mm=0.0, layer="S-COL-IDEN"):
        self.text = text
        self.layer = layer
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)
        # as `parse_texts` leaves it, which is what the join reads
        self.mark, self.b_mm, self.h_mm = marks.parse_mark(text)
        self.size_key = marks.size_key(text)


class TheMarkPatternReachesTheOwnersWalls(unittest.TestCase):
    """MEASURED over all 36119 texts in the corpus: 0 answers change, 415 texts
    newly match, every one of the shape T#SW#, T#W#, T#CW#, T#PW# or T#Y#."""

    def mark(self, text):
        return marks.parse_mark(text)[0]

    def test_a_shear_wall_mark_with_two_letter_runs(self):
        self.assertEqual(self.mark("T1SW1"), "T1SW1")
        self.assertEqual(self.mark("T1SW41a"), "T1SW41A")
        self.assertEqual(self.mark("T1SW125a"), "T1SW125A")
        self.assertEqual(self.mark("T2CW3B"), "T2CW3B")

    def test_the_marks_that_already_worked_are_unchanged(self):
        for text, want in (("C1", "C1"), ("RB12", "RB12"), ("C1A", "C1A"),
                           ("B20", "B20"), ("C16_300 X 600", "C16")):
            self.assertEqual(self.mark(text), want, text)

    def test_a_SIZE_never_continues_a_mark(self):
        # "B200x2380" is a beam labelled by its section. Without the `(?![xX]\d)`
        # guard "x2380" is a perfectly good letters-then-digits group and the
        # whole string reads as one long mark.
        name, b_mm, h_mm = marks.parse_mark("B200x2380")
        self.assertIsNone(name)
        self.assertEqual((b_mm, h_mm), (200.0, 2380.0))

    def test_a_size_beside_a_mark_still_gives_both(self):
        self.assertEqual(marks.parse_mark("C1 400x400"), ("C1", 400.0, 400.0))


class TheTwoHalvesOfOneLabelAreJoined(unittest.TestCase):

    def test_the_size_text_takes_the_name_written_above_it(self):
        name = _Text("T1SW1", 0.0, 340.0)
        size = _Text("250X2750", 0.0, 0.0)
        joined = marks.join_split_labels([name, size])
        self.assertEqual(joined, 1)
        self.assertEqual(size.mark, "T1SW1")
        self.assertEqual((size.b_mm, size.h_mm), (250.0, 2750.0))

    def test_the_name_text_is_left_naming_nothing(self):
        # What it names is the member the SIZE text sits on, so giving it a size
        # of its own would invent a second member at the name's position.
        name = _Text("T1SW1", 0.0, 340.0)
        size = _Text("250X2750", 0.0, 0.0)
        marks.join_split_labels([name, size])
        self.assertIsNone(name.b_mm)
        self.assertIsNone(name.h_mm)

    def test_a_name_too_far_off_is_not_taken(self):
        # The band from 411 to 836 mm is empty across the corpus: no label's own
        # name sits beyond 411, no other label's name comes nearer than 836.
        name = _Text("T1SW1", 0.0, 900.0)
        size = _Text("250X2750", 0.0, 0.0)
        self.assertEqual(marks.join_split_labels([name, size]), 0)
        self.assertIsNone(size.mark)

    def test_the_nearer_of_two_names_wins(self):
        near = _Text("T1SW1", 0.0, 300.0)
        far = _Text("T1SW2", 0.0, -560.0)
        size = _Text("250X2750", 0.0, 0.0)
        marks.join_split_labels([near, far, size])
        self.assertEqual(size.mark, "T1SW1")

    def test_a_name_on_ANOTHER_layer_is_never_taken(self):
        # The drawing groups its own labels by layer, and this is what stops a
        # beam's name crossing to a column's size where the two are drawn close.
        name = _Text("B20", 0.0, 300.0, layer="S-BEAM-IDEN")
        size = _Text("250X2750", 0.0, 0.0, layer="S-COL-IDEN")
        self.assertEqual(marks.join_split_labels([name, size]), 0)
        self.assertIsNone(size.mark)

    def test_a_text_that_already_carries_both_is_untouched(self):
        whole = _Text("C1 400x400", 0.0, 0.0)
        name = _Text("T1SW1", 0.0, 300.0)
        marks.join_split_labels([name, whole])
        self.assertEqual(whole.mark, "C1")

    def test_running_it_twice_changes_nothing(self):
        name = _Text("T1SW1", 0.0, 340.0)
        size = _Text("250X2750", 0.0, 0.0)
        marks.join_split_labels([name, size])
        self.assertEqual(marks.join_split_labels([name, size]), 0)
        self.assertEqual(size.mark, "T1SW1")

    def test_parse_texts_does_the_join_itself(self):
        # One call site, so no pipeline can be wired up and quietly miss it.
        name = _Text("T1SW1", 0.0, 340.0)
        size = _Text("250X2750", 0.0, 0.0)
        marks.parse_texts([name, size])
        self.assertEqual(size.mark, "T1SW1")

    def test_texts_without_a_point_are_skipped(self):
        name = _Text("T1SW1", 0.0, 340.0)
        size = _Text("250X2750", 0.0, 0.0)
        size.point_internal = None
        self.assertEqual(marks.join_split_labels([name, size]), 0)

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(marks.join_split_labels([]), 0)
        self.assertEqual(marks.join_split_labels(None), 0)


if __name__ == "__main__":
    unittest.main()
