# -*- coding: utf-8 -*-
"""The grid index: it must not miss a neighbour, and must say so if it could."""

import unittest

import _support                                            # noqa: F401
from cad_qa.spatial import GridIndex, centroid


class GridIndexTests(unittest.TestCase):

    def test_it_finds_the_closest_point(self):
        index = GridIndex(100.0).extend([(0, 0, "a"), (90, 10, "b")])
        distance, payload = index.nearest(95, 5, 100.0)
        self.assertEqual(payload, "b")
        self.assertAlmostEqual(distance, 7.0710678, places=5)

    def test_it_finds_a_neighbour_across_a_cell_boundary(self):
        """The case a naive single-cell lookup gets wrong every time."""
        index = GridIndex(100.0).extend([(99, 99, "a")])
        self.assertIsNotNone(index.nearest(101, 101, 100.0))

    def test_nothing_within_the_radius_is_none(self):
        index = GridIndex(100.0).extend([(0, 0, "a")])
        self.assertIsNone(index.nearest(80, 80, 10.0))

    def test_a_radius_wider_than_a_cell_is_refused_not_guessed(self):
        """Nine cells cover one cell width. Beyond that it would under-report."""
        index = GridIndex(100.0).extend([(0, 0, "a")])
        with self.assertRaises(ValueError):
            index.nearest(0, 0, 500.0)

    def test_an_empty_index_answers_none(self):
        self.assertIsNone(GridIndex(10.0).nearest(0, 0, 10.0))

    def test_a_zero_cell_size_is_refused(self):
        with self.assertRaises(ValueError):
            GridIndex(0)

    def test_length_counts_every_added_point(self):
        self.assertEqual(len(GridIndex(5.0).extend([(0, 0), (1, 1), (2, 2)])), 3)


class CentroidTests(unittest.TestCase):

    def test_it_is_the_mean_of_the_run(self):
        self.assertEqual(centroid([(0, 0), (10, 0), (10, 10), (0, 10)]),
                         (5.0, 5.0))

    def test_no_points_is_none_not_the_origin(self):
        self.assertIsNone(centroid([]))


if __name__ == "__main__":
    unittest.main()
