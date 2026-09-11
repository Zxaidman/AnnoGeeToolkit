# -*- coding: utf-8 -*-
"""When a size label may overrule the outline a column was drawn with (BUG-34).

The owner: "in some place column size and its outline is not matching with
Linked cad. check if this is dxf cad issue or coding issue."

It is a coding decision. `correct_columns_with_text` was built (DONE-22) so a
CLIPPED column -- a sliver the link cut at a junction, a leg of an L whose label
states the whole -- could be snapped up to its authoritative label size. But it
decides on a flat list of rectangles, so it applies the same rule to a column
the drawing closed as one complete ring, which states its own size by being
drawn.

MEASURED on `StructuralPlan-Test17-clean.dxf`, first three storeys, with the
texts routed the way the build routes them:

    entry the member came from      left as drawn   grown to a label   shrunk
    rectangle -- ONE closed ring              496                127       14
    composite -- a leg of an L or C            58                 31        3

So about 42 whole columns per storey were being inflated past the outline they
were drawn with -- 250x1200 built as 250x1500 -- and 152 of the 158 grown
members had a drawn size that is a round 25 mm on both sides, which is a section
somebody drew on purpose, not a fragment a clip left behind.

The 31 legs are the case the pass exists for and they still grow. Standalone
(no Revit).
"""

import unittest

import _loader


report = _loader.load("report")

_FT = 1.0 / 304.8
_RADIUS = 1300.0 * _FT


class _Lbl(object):
    def __init__(self, mark, x_mm, y_mm, b=None, h=None):
        self.mark = mark
        self.b_mm = b
        self.h_mm = h
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _rect(cx_mm, cy_mm, w_mm, h_mm):
    return {"center": [cx_mm * _FT, cy_mm * _FT, 0.0],
            "width_mm": float(w_mm), "height_mm": float(h_mm),
            "width_ft": w_mm * _FT, "height_ft": h_mm * _FT}


def _run(rects, labels, status, schedule=None):
    sections = {"entries": [{"layer": "S-COLUMN", "status": status,
                             "rectangles": list(rects)}],
                "status_counts": {}}
    report.correct_columns_with_text(sections, labels, _RADIUS,
                                     schedule=schedule or {})
    return sections["entries"][0]["rectangles"] if sections["entries"] else []


def _size(rect):
    return (round(min(rect["width_mm"], rect["height_mm"])),
            round(max(rect["width_mm"], rect["height_mm"])))


class AWholeRingKeepsTheSizeItWasDrawnAt(unittest.TestCase):
    """The measured case, at the sizes it was measured at."""

    def test_a_label_does_not_inflate_a_complete_column(self):
        # test17's commonest: drawn 250x1200, a "250x1500" label 477 mm away.
        drawn = _rect(0, 0, 250, 1200)
        label = _Lbl("C1", 0, 477, b=250, h=1500)
        got = _run([drawn], [label], "rectangle")
        self.assertEqual(len(got), 1)
        self.assertEqual(_size(got[0]), (250, 1200))

    def test_a_label_does_not_shrink_one_either(self):
        # The drawing decides in BOTH directions, or it does not decide.
        drawn = _rect(0, 0, 250, 1500)
        label = _Lbl("C1", 0, 500, b=250, h=1300)
        got = _run([drawn], [label], "rectangle")
        self.assertEqual(_size(got[0]), (250, 1500))

    def test_it_is_still_named(self):
        # Keeping the size must not cost the mark: the schedule, the naming
        # template and the abutment recovery all key off it.
        drawn = _rect(0, 0, 250, 1200)
        got = _run([drawn], [_Lbl("C7", 0, 477, b=250, h=1500)], "rectangle")
        self.assertEqual(got[0].get("mark"), "C7")

    def test_it_does_not_move(self):
        drawn = _rect(1000, 2000, 250, 1200)
        got = _run([drawn], [_Lbl("C1", 1000, 2477, b=250, h=1500)],
                   "rectangle")
        self.assertAlmostEqual(got[0]["center"][0], 1000 * _FT, places=6)
        self.assertAlmostEqual(got[0]["center"][1], 2000 * _FT, places=6)

    def test_a_ring_that_already_agrees_is_untouched_as_before(self):
        drawn = _rect(0, 0, 250, 1500)
        got = _run([drawn], [_Lbl("C1", 0, 500, b=250, h=1500)], "rectangle")
        self.assertEqual(_size(got[0]), (250, 1500))


class ALegOfAClosedOutlineIsNotAPiece(unittest.TestCase):
    """BUG-39. The owner photographed the other reading.

    A closed L is split into legs by `decompose_to_rectangles`, which gives the
    shared corner to ONE of them, so the other stops at its face. The label
    measures the arm to the outer face. Growing the leg to the label puts the
    corner back on and stands the member outside the outline it was drawn with
    -- measured, 11 of the 13 legs a label resized on the drawing he ran grew by
    exactly the other leg's thickness.
    """

    def test_a_leg_of_a_composite_keeps_the_size_it_was_drawn(self):
        leg = _rect(0, 0, 250, 1200)
        got = _run([leg], [_Lbl("C1", 0, 477, b=250, h=1500)], "composite")
        self.assertEqual(_size(got[0]), (250, 1200))

    def test_the_leg_is_still_named(self):
        leg = _rect(0, 0, 250, 1200)
        got = _run([leg], [_Lbl("C7", 0, 477, b=250, h=1500)], "composite")
        self.assertEqual(got[0].get("mark"), "C7")


class APieceIsStillGrownToItsLabel(unittest.TestCase):
    """DONE-22's case, which is why the pass exists at all.

    A piece is what the drawing did NOT close: a fragment reassembled out of a
    column a beam sliced, a spine derived from bare lines, a box round a ring
    that would not lie on the axes. There the label really does know better.
    """

    def test_a_recovered_fragment_takes_it_too(self):
        piece = _rect(0, 0, 270, 300)
        got = _run([piece], [_Lbl("C1", 0, 200, b=300, h=300)],
                   "recovered_rect")
        self.assertEqual(_size(got[0]), (300, 300))

    def test_an_oriented_box_is_a_piece_not_a_ring(self):
        # `oriented_rect` is the tightest box round a shape that would not
        # close rectilinearly -- an approximation, not a size the drawing
        # stated, so a label may still correct it.
        piece = _rect(0, 0, 250, 1200)
        got = _run([piece], [_Lbl("C1", 0, 477, b=250, h=1500)],
                   "oriented_rect")
        self.assertEqual(_size(got[0]), (250, 1500))

    def test_two_split_pieces_still_merge_into_one_column(self):
        # The merge branch is untouched for real pieces: two fragments of one
        # column a beam cut, recovered from open paths, and one label.
        left = _rect(-350, 0, 200, 300)
        right = _rect(350, 0, 200, 300)
        got = _run([left, right], [_Lbl("C1", 0, 200, b=300, h=900)],
                   "recovered_rect")
        self.assertEqual(len(got), 1)
        self.assertEqual(_size(got[0]), (300, 900))

    def test_two_CLOSED_rings_are_never_fused(self):
        # BUG-39: fusing them spans the gap BETWEEN them and builds a member
        # where the drawing has nothing -- the bars with no outline under them
        # in the owner's screenshots. Seven labels did this on the drawing he
        # ran. Each ring keeps itself; the label names its nearest.
        left = _rect(-350, 0, 200, 300)
        right = _rect(350, 0, 200, 300)
        got = _run([left, right], [_Lbl("C1", 0, 200, b=300, h=900)],
                   "rectangle")
        self.assertEqual(len(got), 2)
        self.assertEqual(sorted(_size(rect) for rect in got),
                         [(200, 300), (200, 300)])


if __name__ == "__main__":
    unittest.main()
