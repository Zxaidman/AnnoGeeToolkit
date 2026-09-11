# -*- coding: utf-8 -*-
"""WHERE the Revit link dropped the drawing, not just how much (v1.0.1).

The owner's zoned test17 run reported "737 dxf-only" and "unmapped 529", and
neither number leads anywhere. The layers under them do: the link delivered
`S-BEAM` 213 of the drawing's 877 and not one of its 99 `DROP SLAB` or 41
`SLAB FOLD` records, while columns, walls, cutouts and stairs arrived to the
record. Three layer names say what two totals could not.

Standalone (no Revit).
"""

import unittest

import _loader


compare = _loader.load("geom.compare")
layers = _loader.load("classify.layers")


class _Rec(object):
    def __init__(self, layer, category=None):
        self.layer = layer
        self.category = category

    @property
    def layer_key(self):
        return self.layer


def _many(layer, count, category=None):
    return [_Rec(layer, category) for _ in range(count)]


class WhereTheLinkDroppedIt(unittest.TestCase):

    def drawing(self):
        return (_many("S-BEAM", 877) + _many("DROP SLAB", 99)
                + _many("SLAB FOLD", 41) + _many("S-COL_STOP", 161)
                + _many("S-NON STR RCC WALL", 253))

    def link(self):
        # what Revit actually delivered on his run
        return (_many("S-BEAM", 213) + _many("S-COL_STOP", 161)
                + _many("S-NON STR RCC WALL", 253))

    def test_the_biggest_loss_is_named_first(self):
        got = compare.shortfall_by_layer(self.link(), self.drawing())
        self.assertEqual(got[0], ("S-BEAM", 213, 877))

    def test_a_layer_the_link_lost_whole_is_reported(self):
        got = dict((row[0], row[1:]) for row in
                   compare.shortfall_by_layer(self.link(), self.drawing()))
        self.assertEqual(got["DROP SLAB"], (0, 99))
        self.assertEqual(got["SLAB FOLD"], (0, 41))

    def test_what_came_through_whole_is_not_reported(self):
        got = [row[0] for row in
               compare.shortfall_by_layer(self.link(), self.drawing())]
        self.assertNotIn("S-COL_STOP", got)
        self.assertNotIn("S-NON STR RCC WALL", got)

    def test_a_link_that_lost_nothing_says_nothing(self):
        self.assertEqual(
            compare.shortfall_by_layer(self.drawing(), self.drawing()), [])

    def test_two_runs_of_one_drawing_say_the_same_thing(self):
        # ties broken by name, so the console does not shuffle between runs
        link = _many("A", 1) + _many("B", 1)
        drawn = _many("A", 5) + _many("B", 5)
        self.assertEqual([row[0] for row in
                          compare.shortfall_by_layer(link, drawn)], ["A", "B"])

    def test_it_stops_at_the_limit_rather_than_burying_the_console(self):
        drawn = []
        for index in range(20):
            drawn += _many("L%02d" % index, 10)
        self.assertEqual(len(compare.shortfall_by_layer([], drawn)), 8)

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(compare.shortfall_by_layer(None, None), [])
        self.assertEqual(compare.shortfall_by_layer([], []), [])


class WhichLayersNobodyClaimed(unittest.TestCase):
    """"unmapped 529" is a count; the layer names are a mapping he can fix."""

    def records(self):
        return (_many("G-ANNO-SCHD", 16, layers.CATEGORY_UNMAPPED)
                + _many("DIM", 300, layers.CATEGORY_UNMAPPED)
                + _many("S-BEAM", 213, layers.CATEGORY_BEAM))

    def test_the_unmapped_layers_come_back_biggest_first(self):
        got = compare.unmapped_layers(self.records(),
                                      layers.CATEGORY_UNMAPPED)
        self.assertEqual(got[0], ("DIM", 300))
        self.assertEqual(got[1], ("G-ANNO-SCHD", 16))

    def test_what_was_mapped_is_left_out(self):
        got = [row[0] for row in
               compare.unmapped_layers(self.records(),
                                       layers.CATEGORY_UNMAPPED)]
        self.assertNotIn("S-BEAM", got)

    def test_a_drawing_with_nothing_unmapped_says_nothing(self):
        mapped = _many("S-BEAM", 5, layers.CATEGORY_BEAM)
        self.assertEqual(
            compare.unmapped_layers(mapped, layers.CATEGORY_UNMAPPED), [])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(
            compare.unmapped_layers(None, layers.CATEGORY_UNMAPPED), [])


if __name__ == "__main__":
    unittest.main()
