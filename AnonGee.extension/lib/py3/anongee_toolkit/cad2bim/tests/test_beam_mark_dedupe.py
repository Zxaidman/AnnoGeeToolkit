# -*- coding: utf-8 -*-
"""A LABEL names one beam, not a mark STRING (BUG-42).

The owner, on his 1.0.3 run: "mark and grade is not being assign correctly for
both column and beam".

`_dedupe_marks` exists for a real case -- one label drawn between two parallel
members, both of which take it, where only the nearer should keep the name. But
it grouped the segments by their mark TEXT and measured them all against the
FIRST label carrying it, which quietly assumes the drawing names every beam
differently: B1, B2, B3.

His drawing names beams by TYPE. Measured on it: 822 beam labels carrying **8
distinct marks** between them, every 200x650 member reading "B1". Against the
one B1 label the sweep happened to keep, the other 89 B1 beams are all "further
away" -- so all of them were stripped. 618 segments sized, **5** left named.

Standalone (no Revit).
"""

import unittest

import _loader


beam_segments = _loader.load("beam_segments")

_FT = 1.0 / 304.8


class _Lbl(object):
    def __init__(self, mark, x_mm, y_mm):
        self.mark = mark
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _seg(x1_mm, y1_mm, x2_mm, y2_mm, mark=None):
    return {"start": (x1_mm * _FT, y1_mm * _FT, 0.0),
            "end": (x2_mm * _FT, y2_mm * _FT, 0.0),
            "width_mm": 200.0, "depth_mm": 650.0, "mark": mark}


class TwoBeamsMayCarryTheSameName(unittest.TestCase):

    def test_two_segments_with_their_OWN_B1_labels_both_keep_it(self):
        # The case that cost him 89 of 90: two separate members, each with its
        # own label, and the labels happen to say the same word.
        near = _seg(0, 0, 4000, 0, "B1")
        far = _seg(0, 9000, 4000, 9000, "B1")
        took = [(near, _Lbl("B1", 2000, 300)), (far, _Lbl("B1", 2000, 9300))]
        beam_segments._dedupe_marks(took)
        self.assertEqual(near["mark"], "B1")
        self.assertEqual(far["mark"], "B1")

    def test_two_segments_that_took_ONE_label_keep_only_the_nearer(self):
        # The case the sweep exists for: one label drawn between two members.
        label = _Lbl("B1", 2000, 200)
        near = _seg(0, 0, 4000, 0, "B1")
        far = _seg(0, 3000, 4000, 3000, "B1")
        beam_segments._dedupe_marks([(near, label), (far, label)])
        self.assertEqual(near["mark"], "B1")
        self.assertIsNone(far["mark"])

    def test_the_de_named_segment_keeps_its_size(self):
        label = _Lbl("B1", 2000, 200)
        near = _seg(0, 0, 4000, 0, "B1")
        far = _seg(0, 3000, 4000, 3000, "B1")
        beam_segments._dedupe_marks([(near, label), (far, label)])
        self.assertEqual(far["width_mm"], 200.0)
        self.assertEqual(far["depth_mm"], 650.0)

    def test_one_segment_on_a_label_is_left_alone(self):
        label = _Lbl("B1", 2000, 200)
        only = _seg(0, 0, 4000, 0, "B1")
        beam_segments._dedupe_marks([(only, label)])
        self.assertEqual(only["mark"], "B1")

    def test_a_label_with_no_mark_strips_nothing(self):
        label = _Lbl(None, 2000, 200)
        one = _seg(0, 0, 4000, 0, None)
        two = _seg(0, 3000, 4000, 3000, None)
        beam_segments._dedupe_marks([(one, label), (two, label)])
        self.assertIsNone(one["mark"])
        self.assertIsNone(two["mark"])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertIsNone(beam_segments._dedupe_marks([]))
        self.assertIsNone(beam_segments._dedupe_marks(None))


if __name__ == "__main__":
    unittest.main()
