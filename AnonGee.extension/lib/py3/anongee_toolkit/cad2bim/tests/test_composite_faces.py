# -*- coding: utf-8 -*-
"""A resized piece of a composite column keeps the face it shares (BUG-27).

Two places rewrite a column rectangle's size -- the label correction and the
standards snap -- and both wrote the new size while leaving `center` alone, so
every piece grew or shrank about its own middle and BOTH its faces moved. For a
column that is one rectangle that is exactly right. For a column that is more
than one it is wrong every time, because the pieces come out of
`decompose_to_rectangles`, which is an exact cover: they tile perfectly and then
this pulled them apart.

The owner, in Revit: "in some places it create perfectly column as per outline
but in other places it leaves gap between junctions or overlap does not follow
outline properly or discounted."

Measured on test14, both of his symptoms are the one arithmetic:

    a 249 x 350 stub sized to 200 x 600 kept its centre, so the face it shared
    with its blade moved 24 mm off it                              -- a GAP
    a 399 x 350 stub sized to 600 x 200 kept its centre, so its inner face went
    101 mm into the blade                                          -- an OVERLAP

Corpus-wide, composite columns whose pieces meet: 651 clean / 29 gaps / 205
overlaps before, 923 / 5 / 3 after.

Standalone (no Revit): the coordinates are typed in.
"""

import unittest

import _loader


report = _loader.load("report")

_MM = 304.8
_FT = 1.0 / _MM


def _rect(x0, y0, x1, y1):
    """A rectangle dict as `decompose_to_rectangles` hands one over, in mm."""
    return {
        "center": [(x0 + x1) / 2.0 * _FT, (y0 + y1) / 2.0 * _FT, 0.0],
        "width_ft": (x1 - x0) * _FT, "height_ft": (y1 - y0) * _FT,
        "width_mm": float(x1 - x0), "height_mm": float(y1 - y0),
    }


def _box(rect):
    """(x0, y0, x1, y1) in MILLIMETRES, off a rectangle dict."""
    cx, cy, _cz = rect["center"]
    half_w = rect["width_mm"] / 2.0
    half_h = rect["height_mm"] / 2.0
    return (cx * _MM - half_w, cy * _MM - half_h,
            cx * _MM + half_w, cy * _MM + half_h)


class _Text(object):
    """A sized label, as `marks.sized_texts` yields one."""

    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark, self.b_mm, self.h_mm = mark, b_mm, h_mm
        self.text = "{0} {1:.0f}X{2:.0f}".format(mark, b_mm, h_mm)
        self.layer = "COL"
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


class WhichFaceIsHeldWhenAPieceIsResized(unittest.TestCase):
    """`_shared_faces` reads the tiling off the ORIGINAL boxes."""

    def test_a_stub_against_a_blade_on_its_left_is_anchored_there(self):
        blade = _rect(1000, 0, 1300, 4000)
        stub = _rect(1300, 1000, 1900, 1350)          # meets the blade's right
        anchors = report._shared_faces([blade, stub])
        self.assertEqual(anchors[1][0], "min")        # the stub's min-x face

    def test_a_stub_on_the_other_side_is_anchored_on_its_max_face(self):
        blade = _rect(1000, 0, 1300, 4000)
        stub = _rect(400, 1000, 1000, 1350)           # meets the blade's left
        anchors = report._shared_faces([blade, stub])
        self.assertEqual(anchors[1][0], "max")

    def test_a_piece_with_a_neighbour_on_each_side_is_pinned_both_ways(self):
        blade = _rect(1000, 0, 1300, 4000)
        left = _rect(400, 1000, 1000, 1350)
        right = _rect(1300, 2000, 1900, 2350)
        anchors = report._shared_faces([blade, left, right])
        self.assertEqual(anchors[0][0], "both")

    def test_a_piece_touching_nothing_keeps_its_centre(self):
        one = _rect(0, 0, 300, 300)
        far = _rect(9000, 9000, 9300, 9300)
        anchors = report._shared_faces([one, far])
        self.assertEqual(anchors[0], (None, None))

    def test_pieces_that_only_share_a_corner_are_not_touching_faces(self):
        # Corner to corner is not a face, and anchoring to it would be a guess.
        one = _rect(0, 0, 300, 300)
        other = _rect(300, 300, 600, 600)
        anchors = report._shared_faces([one, other])
        self.assertEqual(anchors[0], (None, None))


class AResizedStubStaysOnItsBlade(unittest.TestCase):
    """The label correction, end to end, on test14's own two failures.

    The entry is a RECOVERED one, because since v1.0.3 a ring the drawing closed
    is named by a label and not resized by it (BUG-39), so the only multi-piece
    entries this arithmetic still runs on are the ones reassembled out of a
    column a beam cut. The arithmetic is unchanged and so is the case for it:
    a piece that is resized must keep the face it shares with its neighbour.
    """

    def _apply(self, rects, texts):
        report._apply_column_marks(
            [{"status": "recovered_rect", "rectangles": rects}], texts,
            2000.0 * _FT)
        return rects

    def test_a_ring_the_drawing_CLOSED_is_named_but_not_resized(self):
        # BUG-39, at this pass -- which is the one that was doing it. The later
        # pass had the rule already and never got the chance to apply it.
        leg = _rect(0, 0, 250, 1200)
        blade = _rect(0, 1200, 250, 3000)
        report._apply_column_marks(
            [{"status": "composite", "rectangles": [leg, blade]}],
            [_Text("C1", 250.0, 1500.0, 125.0, 600.0)], 2000.0 * _FT)
        self.assertAlmostEqual(leg["width_mm"], 250.0, places=6)
        self.assertAlmostEqual(leg["height_mm"], 1200.0, places=6)
        self.assertEqual(leg.get("mark"), "C1")

    def test_the_gap_case_ends_exactly_on_the_blade(self):
        # test14: a 249 x 350 stub relabelled 200 x 600 used to stop 24 mm short.
        blade = _rect(30100, 39909, 30401, 43759)
        stub = _rect(29851, 43409, 30100, 43759)
        self._apply([blade, stub],
                    [_Text("C1", 200.0, 600.0, 29975.0, 43584.0)])
        self.assertAlmostEqual(_box(stub)[2], 30100.0, places=3)
        self.assertAlmostEqual(stub["width_mm"], 200.0, places=6)

    def test_the_overlap_case_starts_exactly_on_the_blade(self):
        # test14: a 399 x 350 stub relabelled 600 x 200 used to bite 101 mm in.
        blade = _rect(51351, 40209, 51601, 44059)
        stub = _rect(51601, 43169, 52000, 43519)
        self._apply([blade, stub],
                    [_Text("C2", 200.0, 600.0, 51800.0, 43344.0)])
        self.assertAlmostEqual(_box(stub)[0], 51601.0, places=3)
        self.assertAlmostEqual(stub["width_mm"], 600.0, places=6)

    def test_a_boxed_in_blade_keeps_the_width_its_neighbours_are_drawn_to(self):
        # A 300 blade relabelled 350, with a leg drawn on each side: the label
        # cannot move either face, so the drawn extent wins on that axis.
        blade = _rect(48001, 40209, 48301, 44059)
        left = _rect(47400, 42244, 48001, 42594)
        right = _rect(48301, 43709, 48701, 44059)
        self._apply([blade, left, right],
                    [_Text("MB", 350.0, 750.0, 48151.0, 42134.0)])
        self.assertAlmostEqual(blade["width_mm"], 300.0, places=6)
        self.assertAlmostEqual(_box(blade)[0], 48001.0, places=3)
        self.assertAlmostEqual(_box(blade)[2], 48301.0, places=3)

    def test_a_lone_rectangle_still_resizes_about_its_centre(self):
        # Nothing shares a face with it, so the old behaviour is the right one.
        alone = _rect(0, 0, 300, 600)
        self._apply([alone], [_Text("C3", 400.0, 800.0, 150.0, 300.0)])
        self.assertAlmostEqual(alone["width_mm"], 400.0, places=6)
        self.assertAlmostEqual(_box(alone)[0], -50.0, places=3)
        self.assertAlmostEqual(_box(alone)[2], 350.0, places=3)

    def test_the_feet_are_kept_in_step_with_the_millimetres(self):
        # `column_geom._bbox_half` reads the FEET, so a stale value there made a
        # trim footprint from the drawn size while the column was placed at the
        # labelled one.
        alone = _rect(0, 0, 300, 600)
        self._apply([alone], [_Text("C4", 400.0, 800.0, 150.0, 300.0)])
        self.assertAlmostEqual(alone["width_ft"] * _MM, 400.0, places=6)
        self.assertAlmostEqual(alone["height_ft"] * _MM, 800.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
