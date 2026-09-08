# -*- coding: utf-8 -*-
"""Rectilinear fragment-assembly recovery (shapes.recover_rectilinear_columns).

Regression lock for Test10: a long wall fused with its perpendicular legs into one
unclosed "comb" outline (a 12300 base with four 300x3300 teeth, on grids 3-6 of
Grid A / Grid H). Before the fix every piece blobbed into a single oversized
oriented rectangle that was dropped as out-of-range, so the long wall AND all four
legs vanished. The assembly pass rebuilds the implied closed boundary and
decomposes it into the real columns.

Runs standalone (no numpy / no Revit): shapes.py + config.py are loaded by file
path into a synthetic package.
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


shapes = _loader.load("geom.shapes")

_MM = 304.8       # ft -> mm
_FT = 1.0 / _MM   # mm -> ft


def _ring(*pts_mm):
    """Point path (feet, 3D) from (x_mm, y_mm) corners."""
    return [(x * _FT, y * _FT, 0.0) for x, y in pts_mm]


def _wh_c(rect):
    """(width_mm, height_mm, cx_mm, cy_mm) rounded to the nearest mm."""
    cx, cy, _cz = rect.center
    return (round(rect.width_ft * _MM), round(rect.height_ft * _MM),
            round(cx * _MM), round(cy * _MM))


# The real Test10 bottom-comb pieces (Grid A wall + four 300x3300 legs), exactly as
# they arrive from the import: open polyline chains plus the two bare wall lines.
_BASE_LINE = _ring((20150, -450), (7850, -450))                 # 12300 base edge
_RIGHT_EDGE = _ring((20150, 2850), (20150, -150))               # 3000 leg edge
_P1 = _ring((7850, -150), (7850, 2850), (7850, 3150), (8150, 3150), (8150, -150),
            (10850, -150), (10850, 3150), (11150, 3150), (11150, -150), (16850, -150))
_P2 = _ring((16850, -150), (16850, 3150), (17150, 3150), (17150, -150), (19850, -150))
_P3 = _ring((19850, -150), (19850, 3150), (20150, 3150), (20150, 2850))
_COMB_PATHS = [_P1, _P2, _P3, _BASE_LINE, _RIGHT_EDGE]


class CombDecomposition(unittest.TestCase):

    def test_comb_yields_five_columns(self):
        rects, consumed = shapes.recover_rectilinear_columns(_COMB_PATHS)
        got = sorted(_wh_c(r) for r in rects)
        expected = sorted([
            (300, 3300, 8000, 1500),    # grid 3 leg
            (300, 3300, 11000, 1500),   # grid 4 leg
            (300, 3300, 17000, 1500),   # grid 5 leg
            (300, 3300, 20000, 1500),   # grid 6 leg
            (12300, 300, 14000, -300),  # the long Grid A wall
        ])
        self.assertEqual(got, expected)

    def test_all_comb_pieces_consumed(self):
        # Every fused piece is claimed, so the oriented pass cannot re-blob them.
        _rects, consumed = shapes.recover_rectilinear_columns(_COMB_PATHS)
        self.assertEqual(consumed, set(range(len(_COMB_PATHS))))

    def test_legs_pass_column_size_limits(self):
        # 300x3300 legs are within col_b/col_h limits; the 12300 wall fits col_h_max.
        rects, _c = shapes.recover_rectilinear_columns(_COMB_PATHS)
        for r in rects:
            short = min(r.width_ft, r.height_ft) * _MM
            self.assertAlmostEqual(short, 300, delta=1)


class AssemblyGuards(unittest.TestCase):

    def test_lone_bare_line_is_not_a_column(self):
        rects, consumed = shapes.recover_rectilinear_columns([_BASE_LINE])
        self.assertEqual(rects, [])
        self.assertEqual(consumed, set())

    def test_rotated_cluster_left_for_oriented_recovery(self):
        # A tilted (non-axis-aligned) quad must not be consumed here.
        rot = _ring((100, 100), (180, 160), (120, 240), (40, 180))
        rects, consumed = shapes.recover_rectilinear_columns([rot])
        self.assertEqual(rects, [])
        self.assertEqual(consumed, set())

    def test_separate_boxes_not_merged(self):
        # Two distinct closed boxes a bay apart stay two columns, never one blob.
        b1 = _ring((0, 0), (300, 0), (300, 900), (0, 900), (0, 0))
        b2 = _ring((3000, 0), (3300, 0), (3300, 900), (3000, 900), (3000, 0))
        rects, _c = shapes.recover_rectilinear_columns([b1, b2])
        sizes = sorted((round(min(r.width_ft, r.height_ft) * _MM),
                        round(max(r.width_ft, r.height_ft) * _MM)) for r in rects)
        self.assertEqual(sizes, [(300, 900), (300, 900)])

    def test_open_short_side_closes_open_long_side_does_not(self):
        # A U open across its 300 base closes into a column; open across its 3300
        # length stays open (we only bridge wall-thickness gaps, not whole sides).
        u_short = _ring((0, 0), (0, 3300), (300, 3300), (300, 0))      # gap 300
        rects, _c = shapes.recover_rectilinear_columns([u_short])
        self.assertEqual(sorted(_wh_c(r)[:2] for r in rects), [(300, 3300)])

        u_long = _ring((0, 0), (300, 0), (300, 3300), (0, 3300))       # gap 3300
        rects2, _c2 = shapes.recover_rectilinear_columns([u_long])
        self.assertEqual(rects2, [])


class DecomposeSanity(unittest.TestCase):

    def test_closed_comb_ring_decomposes_to_five(self):
        # If the comb ever arrives already closed, decompose still splits it cleanly.
        comb = _ring(
            (7850, -450), (20150, -450), (20150, -150),
            (20150, 3150), (19850, 3150), (19850, -150),
            (17150, -150), (17150, 3150), (16850, 3150), (16850, -150),
            (11150, -150), (11150, 3150), (10850, 3150), (10850, -150),
            (8150, -150), (8150, 3150), (7850, 3150), (7850, -150))
        result = shapes.parse_column_polyline(comb)
        self.assertEqual(result["status"], "composite")
        self.assertEqual(len(result["rectangles"]), 5)


class BboxShellCompletion(unittest.TestCase):
    """A wall whose far end cap was clipped at a junction (the Grid H 12300 wall):
    its outline traces 3 sides + most of the 4th but never closes into a cycle, so
    it is completed to its bounding box -- but only when the shape really is a
    clipped rectangle, never an L / U / partial outline."""

    # Real Test10 Grid H pieces: bottom edge + left cap + top edge (with a gap and a
    # detached top segment); the right cap and top-right corner were never drawn.
    _H_WALL = [
        _ring((20150, 26150), (7850, 26150), (7850, 26450),
              (11150, 26450), (16850, 26450)),
        _ring((17150, 26450), (19850, 26450)),
    ]

    def test_clipped_wall_recovers_to_full_rectangle(self):
        rects, consumed = shapes.recover_rectilinear_columns(self._H_WALL)
        self.assertEqual([_wh_c(r) for r in rects], [(12300, 300, 14000, 26300)])
        self.assertEqual(consumed, {0, 1})

    def test_open_L_is_not_closed(self):
        # Interior (reentrant) edges sit off the bounding box -> rejected.
        open_l = _ring((600, 0), (600, 300), (300, 300), (300, 600), (0, 600))
        self.assertEqual(shapes.recover_rectilinear_columns([open_l])[0], [])

    def test_two_edge_corner_is_not_closed(self):
        # Only two sides covered (< 3) -> never invents a rectangle from a corner.
        corner = _ring((0, 0), (600, 0), (600, 600))
        self.assertEqual(shapes.recover_rectilinear_columns([corner])[0], [])

    def test_three_sided_missing_full_side_is_not_closed(self):
        # Missing an entire long side traces only ~54% of the perimeter -> rejected,
        # so we never fabricate a wall from half an outline.
        three_sided = _ring((0, 0), (300, 0), (300, 3300), (0, 3300))
        self.assertEqual(shapes.recover_rectilinear_columns([three_sided])[0], [])


class IrregularProfiles(unittest.TestCase):
    """parse_column_polyline keeps a triangular column (3 corners) as an oriented
    box instead of dropping it, while degenerate slivers still drop and every other
    shape is unchanged (no regression to placed columns)."""

    def test_triangle_is_kept_as_oriented_box(self):
        tri = _ring((14700, 11700), (15300, 11700), (15000, 12300))
        res = shapes.parse_column_polyline(tri)
        self.assertEqual(res["status"], "oriented_rect")
        self.assertEqual(len(res["rectangles"]), 1)

    def test_trapezoid_still_placed_as_bounding_box(self):
        trap = _ring((19600, 11700), (20400, 11700), (20200, 12300), (19800, 12300))
        res = shapes.parse_column_polyline(trap)
        self.assertEqual(res["status"], "oriented_rect")
        self.assertEqual([_wh_c(r)[:2] for r in res["rectangles"]], [(600, 800)])

    def test_rectangle_and_composite_unchanged(self):
        rect = shapes.parse_column_polyline(_ring((0, 0), (400, 0), (400, 900), (0, 900)))
        self.assertEqual(rect["status"], "rectangle")
        l = shapes.parse_column_polyline(
            _ring((0, 0), (800, 0), (800, 200), (200, 200), (200, 600), (0, 600)))
        self.assertEqual(l["status"], "composite")

    def test_degenerate_slivers_still_drop(self):
        line = shapes.parse_column_polyline(_ring((0, 0), (400, 0)))
        self.assertEqual(line["status"], "degenerate")
        collinear = shapes.parse_column_polyline(_ring((0, 0), (200, 0), (400, 0)))
        self.assertEqual(collinear["status"], "degenerate")


class DraftingNoiseIsNotAnAngle(unittest.TestCase):
    """A ring that MEANT to be rectilinear and missed by a fraction of a
    millimetre is a rectilinear column, not an angled one.

    The case is test14, reported from Revit: six L-shaped columns per storey
    placed as big TILTED blocks. The rings miss is_rectilinear by 0.4 mm of
    drafting noise, and the non-rectilinear branch fits a MINIMUM-AREA box --
    which for an L is both rotated and far bigger than the column
    (1166 x 3905 mm placed where the legs are 300 mm wide).
    """

    def test_the_reported_test14_column_is_an_l_again(self):
        # The ring exactly as the drawing carries it, off-axis where it drifts:
        # x wanders 110960.71 -> 110961.10 over a 1747 mm edge (0.013 deg).
        noisy = _ring((110960.71, 29765.68), (110961.10, 28018.90),
                      (110661.10, 28018.90), (110661.10, 29467.35),
                      (108961.10, 29467.35), (108961.10, 29765.68))
        result = shapes.parse_column_polyline(noisy)
        self.assertEqual(result["status"], "composite")
        self.assertTrue(result["axis_snapped"])
        # The two legs of the L -- a 300-wide upright and a 1700-long arm --
        # never the one 2000 x 1747 block a min-area box makes of them.
        sizes = sorted(_wh_c(r)[:2] for r in result["rectangles"])
        self.assertEqual(sizes, [(300, 1747), (1700, 298)])

    def test_a_genuinely_rotated_column_keeps_its_oriented_box(self):
        # 10 degrees off axis: 400x900 rotated about its centre. Its corners are
        # tens of millimetres from any shared axis, so no snap can reach them.
        import math
        angle = math.radians(10.0)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        corners = [(-200, -450), (200, -450), (200, 450), (-200, 450)]
        turned = [(x * cos_a - y * sin_a + 50000, x * sin_a + y * cos_a + 50000)
                  for x, y in corners]
        result = shapes.parse_column_polyline(_ring(*turned))
        self.assertEqual(result["status"], "oriented_rect")
        self.assertNotIn("axis_snapped", result)

    def test_the_snap_stops_inside_the_measured_empty_band(self):
        # Corpus measurement: noise ends under 1 mm, nothing at all lies between
        # 1 and 2 mm, real angles start at 2 mm. A 3 mm wander is real geometry
        # and must survive as an oriented box.
        noise = _ring((0, 0), (0.4, 3000), (300.4, 3000), (300, 0))
        self.assertEqual(shapes.parse_column_polyline(noise)["status"],
                         "rectangle")
        real = _ring((0, 0), (3.0, 3000), (303.0, 3000), (300, 0))
        self.assertEqual(shapes.parse_column_polyline(real)["status"],
                         "oriented_rect")

    def test_an_exact_ring_is_not_reported_as_snapped(self):
        exact = shapes.parse_column_polyline(
            _ring((0, 0), (800, 0), (800, 200), (200, 200), (200, 600), (0, 600)))
        self.assertEqual(exact["status"], "composite")
        self.assertFalse(exact["axis_snapped"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
