# -*- coding: utf-8 -*-
"""Geometry and coordinate mapping: the two things every other number rests on.

Degenerate input gets as much attention as correct input, because a report is a
diagnostic: it is pointed at broken drawings on purpose, and a helper that
raises on an empty point list takes the whole report down with it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                                        # noqa: E402

geometry, space = _loader.load("geometry", "space")

SQUARE = [(0.0, 0.0, 0.0), (400.0, 0.0, 0.0), (400.0, 750.0, 0.0), (0.0, 750.0, 0.0)]


class GeometryTests(unittest.TestCase):

    def test_centroid_of_a_ring_is_its_area_centre(self):
        self.assertEqual(geometry.centroid(SQUARE), (200.0, 375.0, 0.0))

    def test_closing_a_ring_explicitly_does_not_move_its_centroid(self):
        """The bug that reconciled one hatch as two members, 300 mm apart.

        Two passes over the same hatch, one of which repeats the first vertex to
        close the ring, anchored outside the match radius from each other.
        """
        self.assertEqual(geometry.centroid(SQUARE + [SQUARE[0]]),
                         geometry.centroid(SQUARE))

    def test_vertex_density_does_not_move_a_centroid(self):
        """A bulged polyline tessellates densely on its arcs and sparsely
        elsewhere; the anchor must depend on the shape, not the vertex list."""
        square = [(0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (0, 1000, 0)]
        dense_bottom = ([(1000.0 * i / 20.0, 0.0, 0.0) for i in range(21)]
                        + [(1000, 1000, 0), (0, 1000, 0)])
        for value, expected in zip(geometry.centroid(dense_bottom),
                                   geometry.centroid(square)):
            self.assertAlmostEqual(value, expected, places=6)

    def test_shapes_with_no_area_keep_the_vertex_mean(self):
        self.assertEqual(geometry.centroid([(0, 0, 0), (1000, 0, 0)]),
                         (500.0, 0.0, 0.0))
        self.assertEqual(geometry.centroid([(7, 8, 9)]), (7.0, 8.0, 9.0))
        collinear = [(0, 0, 0), (500, 0, 0), (1000, 0, 0)]
        self.assertEqual(geometry.centroid(collinear), (500.0, 0.0, 0.0))

    def test_plan_size_is_ordered_short_then_long(self):
        """A rotated member must not read as a different size from its twin."""
        self.assertEqual(geometry.plan_size(SQUARE), (400.0, 750.0))
        flipped = [(y, x, z) for x, y, z in SQUARE]
        self.assertEqual(geometry.plan_size(flipped), (400.0, 750.0))

    def test_polygon_area_ignores_winding_and_closure(self):
        closed = SQUARE + [SQUARE[0]]
        self.assertAlmostEqual(geometry.polygon_area(SQUARE), 300000.0)
        self.assertAlmostEqual(geometry.polygon_area(closed), 300000.0)
        self.assertAlmostEqual(geometry.polygon_area(list(reversed(SQUARE))),
                               300000.0)

    def test_angles_fold_so_a_beam_has_no_direction(self):
        left = geometry.principal_angle_deg([(0, 0, 0), (1000, 0, 0)])
        right = geometry.principal_angle_deg([(1000, 0, 0), (0, 0, 0)])
        self.assertEqual(geometry.angle_delta_deg(left, right), 0.0)
        self.assertEqual(geometry.angle_delta_deg(179.0, 1.0), 2.0)

    def test_plan_distance_ignores_z(self):
        """A column runs floor to floor; its outline does not. Matching is in plan."""
        self.assertAlmostEqual(
            geometry.plan_distance((0, 0, 0), (300, 400, 99999)), 500.0)

    def test_nothing_raises_on_degenerate_input(self):
        for empty in ([], [(1.0, 2.0, 3.0)]):
            geometry.centroid(empty)
            geometry.bbox(empty)
            geometry.plan_size(empty)
            geometry.path_length(empty)
            geometry.polygon_area(empty)
            geometry.principal_angle_deg(empty)
            geometry.is_closed(empty, 1.0)
        self.assertIsNone(geometry.centroid([]))
        self.assertIsNone(geometry.distance(None, (0, 0, 0)))
        self.assertEqual(geometry.polygon_area([(0, 0, 0), (1, 1, 1)]), 0.0)

    def test_identical_vertices_do_not_produce_an_angle(self):
        self.assertIsNone(geometry.principal_angle_deg([(5, 5, 0)] * 4))


class SpaceTests(unittest.TestCase):

    def _space(self):
        scale = 1.0 / 304.8            # a DXF drawn in mm, linked into feet
        rows = [[scale, 0, 0, 10.0], [0, scale, 0, 20.0], [0, 0, scale, 0.0]]
        return space.Space(1.0, rows, method="link_transform")

    def test_dxf_millimetres_pass_through_unscaled(self):
        dxf_mm, _revit = self._space().from_dxf([(400.0, 750.0, 0.0)])
        self.assertEqual(dxf_mm, [(400.0, 750.0, 0.0)])

    def test_the_forward_map_places_the_drawing_in_the_model(self):
        _dxf, revit_mm = self._space().from_dxf([(0.0, 0.0, 0.0)])
        self.assertAlmostEqual(revit_mm[0][0], 3048.0)      # 10 ft
        self.assertAlmostEqual(revit_mm[0][1], 6096.0)      # 20 ft

    def test_the_inverse_returns_a_revit_point_to_drawing_coordinates(self):
        dxf_mm, _revit = self._space().from_revit([(10.0, 20.0, 0.0)])
        for value in dxf_mm[0]:
            self.assertAlmostEqual(value, 0.0)

    def test_a_round_trip_is_lossless(self):
        subject = self._space()
        _dxf, revit_mm = subject.from_dxf([(1234.5, -678.9, 0.0)])
        feet = [(p[0] / 304.8, p[1] / 304.8, p[2] / 304.8) for p in revit_mm]
        back, _again = subject.from_revit(feet)
        self.assertAlmostEqual(back[0][0], 1234.5, places=6)
        self.assertAlmostEqual(back[0][1], -678.9, places=6)

    def test_without_a_link_the_revit_columns_are_empty_not_wrong(self):
        dxf_mm, revit_mm = space.Space(1.0).from_dxf([(1.0, 2.0, 3.0)])
        self.assertEqual(len(dxf_mm), 1)
        self.assertIsNone(revit_mm)

    def test_a_singular_transform_degrades_instead_of_raising(self):
        subject = space.Space(1.0, [[0, 0, 0, 0]] * 3)
        self.assertIsNotNone(subject.inverse_error)
        dxf_mm, revit_mm = subject.from_revit([(1.0, 1.0, 1.0)])
        self.assertIsNone(dxf_mm)
        self.assertEqual(len(revit_mm), 1)

    def test_drawing_units_other_than_millimetres_scale(self):
        metres = space.Space(space.UNIT_MM["Meter"])
        dxf_mm, _revit = metres.from_dxf([(1.5, 0.0, 0.0)])
        self.assertAlmostEqual(dxf_mm[0][0], 1500.0)


if __name__ == "__main__":
    unittest.main()
