# -*- coding: utf-8 -*-
"""shapes.pair_parallel_lines -- an edge drawn in PIECES still makes its beam.

A pair consumes only the stretch its two lines OVERLAP over, but v0.84.0 retired
both lines whole. Where CAD draws one side of a beam as a single run and the
facing side as several collinear pieces -- it breaks the line wherever another
member frames in -- the first piece to reach the long line took ALL of it, and
every other piece of the SAME edge was orphaned: no beam over that stretch, and
the line counted as "bare, no parallel partner".

Test14 is the drawing: a 3297-long left edge faced by a 1497 piece and an 1800
piece, and only the 1497 half became a beam. The bays the missing halves should
have closed then leaked slab, which is why this was the run's worst defect.

The cure is a SECOND pairing pass over the remnants -- what pass 1 left of each
line -- so pass 1's output cannot move and nothing already placed can be lost.
Standalone (no Revit / no numpy / no ezdxf).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_MM = 304.8
_FT = 1.0 / _MM


shapes = _loader.load("geom.shapes")

_MIN_W = 80.0 * _FT
_MAX_W = 700.0 * _FT
_MIN_OVERLAP = 150.0 * _FT


def _line(x0, y0, x1, y1):
    """A pool line in the (p0, p1, z) shape build_beam_segments hands over."""
    return ((x0 * _FT, y0 * _FT), (x1 * _FT, y1 * _FT), 0.0)


def _pair(lines):
    return shapes.pair_parallel_lines(
        lines, min_width_ft=_MIN_W, max_width_ft=_MAX_W,
        min_overlap_ft=_MIN_OVERLAP, sin_tol=0.0523)


def _members(segments):
    """[(x0, y0, x1, y1, width)] in mm, rounded, ordered -- readable assertions."""
    out = []
    for seg in segments:
        out.append((round(seg["start"][0] * _MM), round(seg["start"][1] * _MM),
                    round(seg["end"][0] * _MM), round(seg["end"][1] * _MM),
                    round(seg["width_ft"] * _MM)))
    return sorted(out)


def _spans(segments, axis=1):
    """The stretch each member covers along one axis, in mm, sorted."""
    out = []
    for seg in segments:
        a, b = seg["start"][axis] * _MM, seg["end"][axis] * _MM
        out.append((round(min(a, b)), round(max(a, b))))
    return sorted(out)


class AnEdgeDrawnInPieces(unittest.TestCase):
    """One whole edge, the facing edge in two abutting pieces: the miniature."""

    # x=0 whole; x=200 broken at y=1500. 200 wide, the width test14 uses most.
    WHOLE = _line(0, 0, 0, 3000)
    LOWER = _line(200, 0, 200, 1500)
    UPPER = _line(200, 1500, 200, 3000)

    def test_both_pieces_get_a_beam_not_just_the_first(self):
        segs, leftover = _pair([self.LOWER, self.WHOLE, self.UPPER])
        self.assertEqual(len(segs), 2)
        self.assertEqual(leftover, [])
        self.assertEqual(_spans(segs), [(0, 1500), (1500, 3000)])
        for seg in segs:
            self.assertAlmostEqual(seg["width_ft"] * _MM, 200.0, places=3)

    def test_the_beam_sits_on_the_midline_of_the_two_edges(self):
        segs, _lo = _pair([self.LOWER, self.WHOLE, self.UPPER])
        for seg in segs:
            self.assertAlmostEqual(seg["start"][0] * _MM, 100.0, places=3)
            self.assertAlmostEqual(seg["end"][0] * _MM, 100.0, places=3)

    def test_which_piece_is_drawn_first_no_longer_decides(self):
        """The defect WAS the input order: whichever piece met the long line
        first consumed all of it. Every ordering must now give the same two."""
        orders = ([self.LOWER, self.UPPER, self.WHOLE],
                  [self.UPPER, self.LOWER, self.WHOLE],
                  [self.WHOLE, self.LOWER, self.UPPER],
                  [self.WHOLE, self.UPPER, self.LOWER],
                  [self.LOWER, self.WHOLE, self.UPPER],
                  [self.UPPER, self.WHOLE, self.LOWER])
        seen = set()
        for order in orders:
            segs, leftover = _pair(list(order))
            self.assertEqual(leftover, [])
            seen.add(tuple(_spans(segs)))
        self.assertEqual(seen, {((0, 1500), (1500, 3000))})

    def test_an_edge_in_three_pieces_makes_three(self):
        pieces = [_line(200, 0, 200, 1000), _line(200, 1000, 200, 2000),
                  _line(200, 2000, 200, 3000)]
        segs, leftover = _pair(pieces + [self.WHOLE])
        self.assertEqual(leftover, [])
        self.assertEqual(_spans(segs),
                         [(0, 1000), (1000, 2000), (2000, 3000)])

    def test_the_whole_run_is_covered_end_to_end(self):
        """What the bay actually needs: no stretch of the member left open."""
        segs, _lo = _pair([self.LOWER, self.WHOLE, self.UPPER])
        covered = sorted(_spans(segs))
        self.assertEqual(covered[0][0], 0)
        self.assertEqual(covered[-1][1], 3000)
        for (_a0, a1), (b0, _b1) in zip(covered, covered[1:]):
            self.assertEqual(a1, b0)          # abutting, no gap left behind


class WhatTheSecondPassMustNotDo(unittest.TestCase):
    """The remnant pass may only ADD members, and only real ones."""

    def test_a_plain_pair_is_still_exactly_one_beam(self):
        segs, leftover = _pair([_line(0, 0, 0, 3000), _line(300, 0, 300, 3000)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(leftover, [])
        self.assertAlmostEqual(segs[0]["width_ft"] * _MM, 300.0, places=3)

    def test_a_piece_shorter_than_the_overlap_floor_makes_nothing(self):
        """A 100 mm stub is a junction fragment, not the rest of an edge."""
        whole = _line(0, 0, 0, 3000)
        segs, leftover = _pair([_line(200, 0, 200, 1500), whole,
                                _line(200, 2000, 200, 2100)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(_spans(segs), [(0, 1500)])
        self.assertEqual(len(leftover), 1)

    def test_the_width_band_still_governs_the_remnant(self):
        """A second piece 40 mm off the long line is drafting noise, not a
        member: below pair_min_width it must stay bare, as before."""
        whole = _line(0, 0, 0, 3000)
        segs, leftover = _pair([_line(200, 0, 200, 1500), whole,
                                _line(40, 1500, 40, 3000)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(leftover), 1)

    def test_a_consumed_stretch_is_never_paired_twice(self):
        """A third piece lying ON the stretch pass 1 already used makes no
        second beam there -- two members on one centreline z-fight in Revit."""
        segs, leftover = _pair([_line(0, 0, 0, 1500), _line(200, 0, 200, 1500),
                                _line(400, 0, 400, 1500)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(len(leftover), 1)

    def test_two_members_either_side_of_a_gap_do_not_fuse(self):
        """The opposite failure: a beam 0..1000 and another 2000..3000 on the
        same centreline stay two, and the void between them stays void."""
        segs, _lo = _pair([_line(0, 0, 0, 1000), _line(200, 0, 200, 1000),
                           _line(0, 2000, 0, 3000), _line(200, 2000, 200, 3000)])
        self.assertEqual(_spans(segs), [(0, 1000), (2000, 3000)])

    def test_a_lone_line_with_no_partner_at_all_is_still_leftover(self):
        segs, leftover = _pair([_line(0, 0, 0, 3000)])
        self.assertEqual(segs, [])
        self.assertEqual(len(leftover), 1)


class TheTest14Geometry(unittest.TestCase):
    """The two shapes read off StructuralPlan-Test14.dxf, at its real coordinates.

    Both are drawn three times on the sheet (one per plan); one copy of each is
    pinned here so the miniatures above are anchored to the drawing that found
    the defect. The DXF itself is exercised by the sweep.
    """

    def test_the_2551_pair_makes_its_350_wide_beam(self):
        """The pair the report opened on: 2551 long, 350 apart, fully
        overlapping. It always paired ALONE; it must pair here too."""
        segs, leftover = _pair([_line(207398, 19869, 204847, 19869),
                                _line(207398, 19519, 204847, 19519)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(leftover, [])
        self.assertEqual(_members(segs),
                         [(207398, 19694, 204847, 19694, 350)])
        self.assertEqual(_spans(segs, axis=0), [(204847, 207398)])

    def test_the_3297_edge_faced_by_a_1497_and_an_1800_piece(self):
        """The 400x750 MB at x=195347: its right edge is broken at y=29766, and
        v0.84.0 placed a beam over the lower 1497 only."""
        segs, leftover = _pair([
            _line(195548, 28269, 195547, 31566),      # left edge, one run
            _line(195148, 28269, 195147, 29766),      # right edge, lower piece
            _line(195147, 29766, 195147, 31566)])     # right edge, upper piece
        self.assertEqual(leftover, [])
        self.assertEqual(len(segs), 2)
        self.assertEqual(_spans(segs), [(28269, 29766), (29766, 31566)])
        for seg in segs:
            self.assertAlmostEqual(seg["width_ft"] * _MM, 400.0, delta=1.0)

    def test_the_2153_edge_faced_by_a_1575_and_a_578_piece(self):
        """The 200x400 at x=189548, where the SHORT piece won pass 1 and the
        1575 remainder was orphaned -- the same fault, the other way round."""
        segs, leftover = _pair([
            _line(189448, 34991, 189448, 37144),      # left edge, one run
            _line(189648, 34991, 189648, 36566),      # right edge, long piece
            _line(189648, 36566, 189648, 37144)])     # right edge, short piece
        self.assertEqual(leftover, [])
        self.assertEqual(_spans(segs), [(34991, 36566), (36566, 37144)])
        for seg in segs:
            self.assertAlmostEqual(seg["width_ft"] * _MM, 200.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
