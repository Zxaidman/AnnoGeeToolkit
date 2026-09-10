# -*- coding: utf-8 -*-
"""One element family per boundary ZONE, folded back into one plan (FEAT-17).

The owner: "separating column, beam & slab, wall outline to each boundary zone
with proper origin point to eliminate Revit eating Linked Outline merge ...
reason why we need this currently revit link cad eat overlapping outline which
causes our tool to be unreliable with new cad file which is not good for
sellable product."

The sizes and the layout here are his example drawing's, measured: four zone
boxes 101387 x 39923 mm, each with one origin marker at the same offset inside
it. Standalone (no Revit).
"""

import unittest

import _loader


zone_plan = _loader.load("zone_plan")
layers = _loader.load("classify.layers")

_FT = 1.0 / 304.8


class _Rec(object):
    """A curve record, as much of one as the fold touches."""

    def __init__(self, layer, points, category=None, kind="polyline"):
        self.layer = layer
        self.points = [(p[0], p[1], 0.0) for p in points]
        self.category = category
        self.kind = kind

    @property
    def layer_key(self):
        return self.layer


class _Txt(object):
    def __init__(self, layer, x, y, text=""):
        self.layer = layer
        self.text = text
        self.point_internal = (x, y, 0.0)


def _box(layer, x0, y0, width, height, category=None):
    """A closed rectangle, in feet."""
    return _Rec(layer, [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height),
                        (x0, y0 + height), (x0, y0)],
                category or layers.CATEGORY_FLOOR_BOUNDARY)


def _marker(x, y):
    # a bare POINT on the origin layer, which is what the drawings carry
    return _Rec("Origin", [(x, y)], layers.CATEGORY_FLOOR_ORIGIN, kind="point")


def _thing(layer, x, y, category, size=1.0):
    return _Rec(layer, [(x, y), (x + size, y), (x + size, y + size),
                        (x, y + size), (x, y)], category)


class ReadingAZoneLayer(unittest.TestCase):

    def test_the_owner_s_four_names_are_zones(self):
        for name in ("Combine-boundary", "Grid-Column-boundary",
                     "Beam-Slab-boundary", "Wall-boundary"):
            self.assertTrue(zone_plan.is_zone_layer(name, "Boundary"), name)

    def test_the_storey_boundary_itself_is_not_a_zone(self):
        # It ends the same way; it is told apart by being the layer the dialog
        # picked for storeys.
        self.assertFalse(zone_plan.is_zone_layer("Boundary", "Boundary"))
        self.assertFalse(zone_plan.is_zone_layer("boundary", "Boundary"))

    def test_an_ordinary_layer_is_not_a_zone(self):
        for name in ("S-COLUMN", "S-BEAM", "DROP SLAB", "", None):
            self.assertFalse(zone_plan.is_zone_layer(name, "Boundary"), name)

    def test_a_box_holding_the_zones_is_the_storey_boundary(self):
        # The storey layer ends `-boundary` too, and the dialog's picker may be
        # empty. A box that holds other zone boxes is never a zone itself --
        # folding it onto one of its own quarters would build the sheet twice.
        records = [_box("Site-boundary", -10, -10, 400, 100),
                   _box("Grid-Column-boundary", 0, 0, 50, 20),
                   _marker(10, 10),
                   _box("Wall-boundary", 200, 0, 50, 20),
                   _marker(210, 10)]
        found = zone_plan.zones(records)
        self.assertEqual(sorted(zone.layer for zone in found),
                         ["Grid-Column-boundary", "Wall-boundary"])

    def test_the_outer_box_is_not_folded_in_either(self):
        records = [_box("Site-boundary", -10, -10, 400, 100),
                   _box("Grid-Column-boundary", 0, 0, 50, 20),
                   _marker(10, 10),
                   _box("Wall-boundary", 200, 0, 50, 20),
                   _marker(210, 10),
                   _thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN),
                   _thing("S-WALL", 220, 12, layers.CATEGORY_STRUCT_WALL)]
        got, _t, _h, _n = zone_plan.merge_zones(records)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_COLUMN]), 1)
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_STRUCT_WALL]), 1)

    def test_the_combined_copy_is_recognised(self):
        self.assertTrue(zone_plan.is_combine("Combine-boundary"))
        self.assertFalse(zone_plan.is_combine("Wall-boundary"))


class WhatAZoneClaims(unittest.TestCase):
    """Read off the name, which is what fills the dialog's table in."""

    def test_the_column_zone_takes_grids_and_columns(self):
        got = zone_plan.default_categories("Grid-Column-boundary")
        self.assertIn(layers.CATEGORY_COLUMN, got)
        self.assertIn(layers.CATEGORY_GRID, got)
        self.assertNotIn(layers.CATEGORY_BEAM, got)

    def test_the_beam_slab_zone_takes_what_a_floor_is_made_of(self):
        got = zone_plan.default_categories("Beam-Slab-boundary")
        for category in (layers.CATEGORY_BEAM, layers.CATEGORY_SLAB_EDGE,
                         layers.CATEGORY_STAIR, layers.CATEGORY_CUTOUT,
                         layers.CATEGORY_FOLD):
            self.assertIn(category, got)
        self.assertNotIn(layers.CATEGORY_COLUMN, got)

    def test_the_wall_zone_takes_walls(self):
        got = zone_plan.default_categories("Wall-boundary")
        self.assertIn(layers.CATEGORY_STRUCT_WALL, got)
        self.assertNotIn(layers.CATEGORY_COLUMN, got)

    def test_the_combined_copy_claims_everything(self):
        self.assertIsNone(zone_plan.default_categories("Combine-boundary"))

    def test_a_name_that_says_nothing_claims_everything(self):
        # Better than claiming nothing, which would silently drop the zone.
        self.assertIsNone(zone_plan.default_categories("Zone-A-boundary"))


class WhatTheDialogOffersPerZone(unittest.TestCase):
    """A zone holds a FAMILY, so the table names families, not categories."""

    def test_every_zone_in_the_example_lands_on_a_group(self):
        self.assertEqual(zone_plan.default_group("Grid-Column-boundary"),
                         "grids + columns")
        self.assertEqual(zone_plan.default_group("Beam-Slab-boundary"),
                         "beams + slabs + stairs")
        self.assertEqual(zone_plan.default_group("Wall-boundary"), "walls")
        self.assertEqual(zone_plan.default_group("Combine-boundary"),
                         zone_plan.GROUP_EVERYTHING)

    def test_a_name_nobody_recognises_takes_everything(self):
        self.assertEqual(zone_plan.default_group("Zone-A-boundary"),
                         zone_plan.GROUP_EVERYTHING)

    def test_the_groups_are_what_the_dropdown_shows(self):
        names = zone_plan.group_names()
        self.assertEqual(names[0], zone_plan.GROUP_EVERYTHING)
        self.assertIn("walls", names)
        self.assertEqual(names[-1], zone_plan.GROUP_IGNORE)

    def test_a_group_name_resolves_to_its_categories(self):
        got = zone_plan.categories_for("grids + columns")
        self.assertIn(layers.CATEGORY_COLUMN, got)
        self.assertIsNone(zone_plan.categories_for(zone_plan.GROUP_EVERYTHING))
        self.assertEqual(zone_plan.categories_for(zone_plan.GROUP_IGNORE), ())

    def test_the_table_s_answer_beats_the_name(self):
        # The owner renames a zone, or draws walls in the column box on purpose.
        records = [_box("Boundary", -10, -10, 400, 100),
                   _box("Grid-Column-boundary", 0, 0, 50, 20),
                   _marker(10, 10),
                   _box("Wall-boundary", 200, 0, 50, 20),
                   _marker(210, 10),
                   _thing("S-WALL", 20, 12, layers.CATEGORY_STRUCT_WALL),
                   _thing("S-WALL", 220, 12, layers.CATEGORY_STRUCT_WALL)]
        got, _t, _h, _n = zone_plan.merge_zones(
            records, storey_layer="Boundary",
            mapping={"Grid-Column-boundary": "walls"})
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_STRUCT_WALL]), 2)

    def test_skip_this_zone_means_skip_it(self):
        records = [_box("Boundary", -10, -10, 400, 100),
                   _box("Grid-Column-boundary", 0, 0, 50, 20),
                   _marker(10, 10),
                   _box("Wall-boundary", 200, 0, 50, 20),
                   _marker(210, 10),
                   _thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN),
                   _thing("S-WALL", 220, 12, layers.CATEGORY_STRUCT_WALL)]
        got, _t, _h, _n = zone_plan.merge_zones(
            records, storey_layer="Boundary",
            mapping={"Wall-boundary": zone_plan.GROUP_IGNORE})
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_STRUCT_WALL]), 0)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_COLUMN]), 1)


class ADrawingWithNoZones(unittest.TestCase):
    """Every sheet drawn the old way must read exactly as it did."""

    def test_nothing_is_touched(self):
        records = [_thing("S-COLUMN", 0, 0, layers.CATEGORY_COLUMN)]
        texts = [_Txt("COL. SIZE", 0, 0)]
        got, out_texts, out_hatches, notes = zone_plan.merge_zones(
            records, texts, [], storey_layer="Boundary")
        self.assertEqual(got, records)
        self.assertEqual(out_texts, texts)
        self.assertEqual(notes, [])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(zone_plan.merge_zones([], [], []),
                         ([], [], [], []))
        self.assertEqual(zone_plan.merge_zones(None), ([], [], [], []))


class ZonesInsideOneStorey(unittest.TestCase):
    """The owner's example: one storey boundary holding four zone boxes.

    Zones 100 ft apart on the sheet, each 50 x 20 ft, each with its origin 10 ft
    in from its own corner -- the same relative offset his four boxes share to
    the millimetre.
    """

    def build(self, combine=True):
        records = [_box("Boundary", -10, -10, 400, 100)]
        plan = [("Grid-Column-boundary", 0.0),
                ("Beam-Slab-boundary", 100.0),
                ("Wall-boundary", 200.0)]
        if combine:
            plan.append(("Combine-boundary", 300.0))
        for layer, offset in plan:
            records.append(_box(layer, offset, 0, 50, 20))
            records.append(_marker(offset + 10, 10))
        # one member per zone, all at the SAME place inside their own zone
        records.append(_thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN))
        records.append(_thing("S-BEAM", 120, 12, layers.CATEGORY_BEAM))
        records.append(_thing("S-WALL", 220, 12,
                              layers.CATEGORY_STRUCT_WALL))
        if combine:      # the combined copy holds all three again
            records.append(_thing("S-COLUMN", 320, 12, layers.CATEGORY_COLUMN))
            records.append(_thing("S-BEAM", 320, 12, layers.CATEGORY_BEAM))
            records.append(_thing("S-WALL", 320, 12,
                                  layers.CATEGORY_STRUCT_WALL))
        return records

    def folded(self, records, **kwargs):
        return zone_plan.merge_zones(records, storey_layer="Boundary",
                                     **kwargs)

    def test_each_zone_lands_on_the_others(self):
        got, _t, _h, _n = self.folded(self.build(combine=False))
        members = [r for r in got if r.category in (
            layers.CATEGORY_COLUMN, layers.CATEGORY_BEAM,
            layers.CATEGORY_STRUCT_WALL)]
        self.assertEqual(len(members), 3)
        places = set((round(r.points[0][0], 6), round(r.points[0][1], 6))
                     for r in members)
        self.assertEqual(len(places), 1, "the three should be on one point")

    def test_the_combined_copy_is_not_built_a_second_time(self):
        got, _t, _h, notes = self.folded(self.build())
        columns = [r for r in got if r.category == layers.CATEGORY_COLUMN]
        self.assertEqual(len(columns), 1)
        self.assertTrue(any("not built twice" in note for note in notes), notes)

    def test_the_combined_copy_builds_when_it_is_alone(self):
        # A drawing with only the combined zone is an ordinary drawing.
        records = [_box("Boundary", -10, -10, 400, 100),
                   _box("Combine-boundary", 300.0, 0, 50, 20),
                   _marker(310, 10),
                   _thing("S-COLUMN", 320, 12, layers.CATEGORY_COLUMN)]
        got, _t, _h, _n = self.folded(records)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_COLUMN]), 1)

    def test_one_storey_box_and_one_origin_survive(self):
        got, _t, _h, _n = self.folded(self.build())
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_FLOOR_ORIGIN]), 1)
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_FLOOR_BOUNDARY]), 1)

    def test_the_zone_boxes_are_gone(self):
        got, _t, _h, _n = self.folded(self.build())
        self.assertEqual([r for r in got
                          if zone_plan.is_zone_layer(r.layer, "Boundary")], [])

    def test_a_member_in_the_wrong_zone_is_turned_away(self):
        # The example's Wall zone holds two column records -- a copy-paste slip.
        # Built, they would be columns a bay from the real ones.
        records = self.build(combine=False)
        records.append(_thing("S-COLUMN", 225, 12, layers.CATEGORY_COLUMN))
        got, _t, _h, notes = self.folded(records)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_COLUMN]), 1)
        self.assertTrue(any("not what this zone is for" in n for n in notes),
                        notes)

    def test_a_category_no_zone_claims_stays_where_it_is(self):
        # A legend line is nobody's; dropping it because the beam zone did not
        # ask for it would lose the drawing a piece at a time.
        records = self.build(combine=False)
        records.append(_thing("S-LEGEND", 125, 12, layers.CATEGORY_UNMAPPED))
        got, _t, _h, _n = self.folded(records)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_UNMAPPED]), 1)

    def test_what_sits_outside_every_zone_is_kept_and_named(self):
        records = self.build(combine=False)
        records.append(_thing("S-CUT OUT", -5, 60, layers.CATEGORY_CUTOUT))
        got, _t, _h, notes = self.folded(records)
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_CUTOUT]), 1)
        self.assertTrue(any("no zone at all" in note for note in notes), notes)

    def test_texts_and_hatches_travel_with_their_zone(self):
        records = self.build(combine=False)
        texts = [_Txt("COL. SIZE", 20, 12, "250x1200"),
                 _Txt("S-BEAM-IDEN", 120, 12, "B-200x500")]
        hatches = [_thing("S-COLS", 20, 12, layers.CATEGORY_COLUMN)]
        _r, out_texts, out_hatches, _n = zone_plan.merge_zones(
            records, texts, hatches, storey_layer="Boundary")
        self.assertEqual(len(out_texts), 2)
        self.assertEqual(len(out_hatches), 1)
        # the beam label moved onto the column zone with its own zone
        places = set(round(t.point_internal[0], 6) for t in out_texts)
        self.assertEqual(len(places), 1)

    def test_the_dialog_s_mapping_beats_the_name(self):
        records = self.build(combine=False)
        records.append(_thing("S-COLUMN", 225, 12, layers.CATEGORY_COLUMN))
        got, _t, _h, _n = zone_plan.merge_zones(
            records, storey_layer="Boundary",
            mapping={"Wall-boundary": [layers.CATEGORY_STRUCT_WALL,
                                       layers.CATEGORY_COLUMN]})
        self.assertEqual(
            len([r for r in got if r.category == layers.CATEGORY_COLUMN]), 2)

    def test_a_zone_with_no_origin_is_left_alone_and_reported(self):
        records = [_box("Boundary", -10, -10, 400, 100),
                   _box("Grid-Column-boundary", 0, 0, 50, 20),
                   _marker(10, 10),
                   _box("Wall-boundary", 200, 0, 50, 20),
                   _thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN),
                   _thing("S-WALL", 220, 12, layers.CATEGORY_STRUCT_WALL)]
        got, _t, _h, notes = zone_plan.merge_zones(records,
                                                   storey_layer="Boundary")
        self.assertTrue(any("no origin marker" in note for note in notes),
                        notes)
        # and its wall is still in the drawing, at the place it was drawn
        walls = [r for r in got if r.category == layers.CATEGORY_STRUCT_WALL]
        self.assertEqual(len(walls), 1)
        self.assertAlmostEqual(walls[0].points[0][0], 220.0)


class TheMarkersComeFromTheDxf(unittest.TestCase):
    """What the build actually does: fold the LINK's records by the DXF's boxes.

    A plan's origin is a bare POINT and the Revit link does not always import
    one, which is why every marker in this pipeline is read from the DXF and the
    records folded by them are the Revit ones. So the record set being folded
    may hold no boxes and no markers at all.
    """

    def drawing(self):
        markers = [_box("Boundary", -10, -10, 400, 100)]
        for layer, offset in (("Grid-Column-boundary", 0.0),
                              ("Wall-boundary", 200.0)):
            markers.append(_box(layer, offset, 0, 50, 20))
            markers.append(_marker(offset + 10, 10))
        return markers

    def test_the_link_s_records_fold_on_the_dxf_s_boxes(self):
        link = [_thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN),
                _thing("S-WALL", 220, 12, layers.CATEGORY_STRUCT_WALL)]
        got, _t, _h, notes = zone_plan.merge_zones(
            link, storey_layer="Boundary", marker_records=self.drawing())
        members = [r for r in got if r.category in (
            layers.CATEGORY_COLUMN, layers.CATEGORY_STRUCT_WALL)]
        self.assertEqual(len(members), 2)
        self.assertEqual(
            len(set(round(r.points[0][0], 6) for r in members)), 1,
            "the wall should have landed on the column's zone")

    def test_it_folds_when_the_link_dropped_every_marker(self):
        # Nothing in the folded set is a box or a marker; the fold still knows
        # where the zones are, because it was told separately.
        link = [_thing("S-COLUMN", 20, 12, layers.CATEGORY_COLUMN)]
        got, _t, _h, _n = zone_plan.merge_zones(
            link, storey_layer="Boundary", marker_records=self.drawing())
        self.assertEqual(len(got), 1)

    def test_the_origin_layer_can_be_named_before_any_mapping_exists(self):
        # The dialog picks the marker layers BY NAME, and detection runs before
        # any category is stamped on anything.
        raw = []
        for record in self.drawing():
            copy = _Rec(record.layer, [(p[0], p[1]) for p in record.points],
                        None, record.kind)
            raw.append(copy)
        found = zone_plan.zones(raw, "Boundary", origin_layer="Origin")
        self.assertEqual(len(found), 2)
        self.assertTrue(all(zone.origin is not None for zone in found))


class StoreysInsideEachZone(unittest.TestCase):
    """The other layout, which the owner wants for a sheet of twenty floors.

    Four copies of the whole sheet, one per family; each copy holds its own
    storey boxes. A storey is paired with its twin by WHERE IT SITS inside its
    own zone, so a zone missing a floor cannot put the rest out of step.
    """

    def build(self):
        records = []
        for layer, offset in (("Grid-Column-boundary", 0.0),
                              ("Beam-Slab-boundary", 500.0)):
            records.append(_box(layer, offset, 0, 200, 200))
            for storey, y in enumerate((10.0, 110.0)):
                records.append(_box("Boundary", offset + 10, y, 50, 20))
                records.append(_marker(offset + 20, y + 10))
                category = (layers.CATEGORY_COLUMN if "Grid" in layer
                            else layers.CATEGORY_BEAM)
                records.append(_thing("S-X", offset + 30, y + 12, category))
        return records

    def test_each_storey_is_folded_with_its_own_twin(self):
        got, _t, _h, notes = zone_plan.merge_zones(self.build(),
                                                   storey_layer="Boundary")
        columns = [r for r in got if r.category == layers.CATEGORY_COLUMN]
        beams = [r for r in got if r.category == layers.CATEGORY_BEAM]
        self.assertEqual((len(columns), len(beams)), (2, 2))
        # ground column meets ground beam, first-floor column meets first beam
        # -- on the SAME point, not merely the same row: the beam copy is 500 ft
        # away on the sheet and has to land on the column copy exactly.
        pairs = set()
        for column in columns:
            for beam in beams:
                if (abs(column.points[0][0] - beam.points[0][0]) < 1e-6
                        and abs(column.points[0][1] - beam.points[0][1]) < 1e-6):
                    pairs.add((round(column.points[0][0], 6),
                               round(column.points[0][1], 6)))
        self.assertEqual(len(pairs), 2, "each storey's two zones must coincide")

    def test_both_storeys_survive_as_storeys(self):
        got, _t, _h, _n = zone_plan.merge_zones(self.build(),
                                                storey_layer="Boundary")
        boxes = [r for r in got
                 if r.category == layers.CATEGORY_FLOOR_BOUNDARY]
        self.assertEqual(len(boxes), 2)
        self.assertEqual(
            len([r for r in got
                 if r.category == layers.CATEGORY_FLOOR_ORIGIN]), 2)

    def test_the_zone_boxes_do_not_survive_as_storeys(self):
        got, _t, _h, _n = zone_plan.merge_zones(self.build(),
                                                storey_layer="Boundary")
        self.assertEqual([r for r in got
                          if zone_plan.is_zone_layer(r.layer, "Boundary")], [])


if __name__ == "__main__":
    unittest.main()
