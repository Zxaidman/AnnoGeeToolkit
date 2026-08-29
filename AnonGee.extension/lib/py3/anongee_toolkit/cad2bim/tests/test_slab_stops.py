# -*- coding: utf-8 -*-
"""slab_stops -- what the drawing says STOPS the slab.

Three readings and one refusal each, pinned twice over: on SYNTHETIC plans
small enough to reason about, and on the REAL coordinates measured out of
StructuralPlan-Test14.dxf, which is the drawing the whole pass was written
for. The real ones are the ones that matter -- a synthetic square proves the
arithmetic, and only the fixture proves the convention was read right -- so
they carry the drawing's own numbers verbatim: the crossed pocket at
(19651, 42594)-(19851, 42944) with its two CUTOUT diagonals, the chajja at
(11051, 37959)-(11801, 38549) under its GOST_GLASS hatch, and the beams that
bound them.

Standalone (no Revit, no DXF): the coordinates are typed in.
"""

import unittest

import _loader

_MM = 304.8
_FT = 1.0 / _MM


(slab_stops, slab_outlines, slab_graph, fold_plan,
 layers) = _loader.load("slab_stops", "slab_outlines", "slab_graph",
                        "fold_plan", "classify.layers")


def _ft(points_mm):
    return [(x * _FT, y * _FT) for x, y in points_mm]


class _Record(object):
    """A CurveRecord as the readers hand one over: points in internal feet."""

    def __init__(self, points_mm, category, kind="polyline", closed=False):
        pts = list(points_mm)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in pts]
        self.category = category
        self.kind = kind
        self.layer_key = category


class _Region(object):
    """A RegionRecord: the outer ring of one hatch, plus its pattern."""

    def __init__(self, points_mm, pattern, layer="HAT"):
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in points_mm]
        self.pattern = pattern
        self.layer = layer
        self.layer_key = layer
        self.category = layers.CATEGORY_UNMAPPED
        self.solid = False


class _Text(object):
    def __init__(self, text, x_mm, y_mm, layer="TEXT"):
        self.text = text
        self.layer = layer
        self.layer_key = layer
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _beam(x0, y0, x1, y1, width_mm, depth_mm=None):
    return {"start": [x0 * _FT, y0 * _FT, 0.0],
            "end": [x1 * _FT, y1 * _FT, 0.0],
            "width_mm": width_mm, "depth_mm": depth_mm}


def _box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _cross(x0, y0, x1, y1):
    """The two CUTOUT diagonals of a box, as the drawing draws them."""
    return [_Record([(x0, y0), (x1, y1)], layers.CATEGORY_CUTOUT, kind="line"),
            _Record([(x0, y1), (x1, y0)], layers.CATEGORY_CUTOUT, kind="line")]


def _bay(points_mm, thickness_mm=125.0, mark=None):
    return {"ring": _ft(points_mm), "z": 0.0, "holes": [], "arcs": [],
            "thickness_mm": thickness_mm, "mark": mark, "blanket": False}


class CrossedRingsAreHoles(unittest.TestCase):
    """1. A crossed slab-stop ring is a hole in the bay that holds it."""

    def test_the_test14_pocket_at_19651_42594_is_read_as_crossed(self):
        # Verbatim from StructuralPlan-Test14.dxf: a closed 200x350 COVER ring
        # against the column band, with its two CUTOUT diagonals corner to
        # corner. This exact pocket is one of the 90 the sweep counts.
        ring = _Record(_box(19650.8, 42593.9, 19850.8, 42943.9),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        strokes = _cross(19650.8, 42593.9, 19850.8, 42943.9)
        rings = slab_stops.slab_stop_rings([ring] + strokes)
        self.assertEqual(len(rings), 1)
        self.assertTrue(slab_graph.crossed(
            rings[0], slab_graph.cross_strokes([ring] + strokes)))

    def test_one_diagonal_alone_is_not_the_symbol(self):
        ring = _Record(_box(19650.8, 42593.9, 19850.8, 42943.9),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        half = _cross(19650.8, 42593.9, 19850.8, 42943.9)[:1]
        records = [ring] + half
        rings = slab_stops.slab_stop_rings(records)
        self.assertFalse(slab_graph.crossed(
            rings[0], slab_graph.cross_strokes(records)))

    def test_a_crossed_ring_becomes_a_hole_of_the_bay_holding_it(self):
        bay = _bay(_box(0, 0, 6000, 4000))
        ring = _Record(_box(1000, 1000, 2000, 2000),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        records = [ring] + _cross(1000, 1000, 2000, 2000)
        out = slab_stops.slab_cutouts([bay], records)
        self.assertEqual(out["crossed"], 1)
        self.assertEqual(list(out["holes"]), [0])
        self.assertEqual(len(out["holes"][0]), 1)

    def test_a_crossed_ring_in_no_bay_is_counted_and_named(self):
        bay = _bay(_box(0, 0, 6000, 4000))
        ring = _Record(_box(9000, 9000, 10000, 10000),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        records = [ring] + _cross(9000, 9000, 10000, 10000)
        out = slab_stops.slab_cutouts([bay], records)
        self.assertEqual(out["crossed"], 1)
        self.assertEqual(out["holes"], {})
        self.assertTrue(any("no slab bay" in note for note in out["notes"]))

    def test_an_uncrossed_ring_cuts_nothing_and_says_so(self):
        bay = _bay(_box(0, 0, 6000, 4000))
        ring = _Record(_box(1000, 1000, 2000, 2000),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        out = slab_stops.slab_cutouts([bay], [ring])
        self.assertEqual(out["crossed"], 0)
        self.assertEqual(out["holes"], {})
        self.assertTrue(any("carry no X" in note for note in out["notes"]))

    def test_the_smallest_bay_wins_a_ring_two_of_them_hold(self):
        big = _bay(_box(0, 0, 6000, 4000))
        small = _bay(_box(500, 500, 3000, 3000))
        ring = _Record(_box(1000, 1000, 2000, 2000),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        records = [ring] + _cross(1000, 1000, 2000, 2000)
        out = slab_stops.slab_cutouts([big, small], records)
        self.assertEqual(list(out["holes"]), [1])

    def test_a_hole_reaching_the_bay_edge_bites_a_notch_rather_than_failing(self):
        # every one of test14's 60 hosted holes reaches its bay's boundary, so
        # this is the normal case: the bay comes back smaller, not divided and
        # not carrying a hole Revit would refuse.
        bay = _bay(_box(0, 0, 6000, 4000))
        ring = _Record(_box(0, 0, 1000, 1000), layers.CATEGORY_SLAB_STOP,
                       closed=True)
        defs, report = slab_outlines.apply_slab_stops(
            [bay], [ring] + _cross(0, 0, 1000, 1000), [])
        self.assertEqual(report["crossed"], 1)
        self.assertEqual(report["holes"], 1)
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["holes"], [])
        self.assertAlmostEqual(
            slab_stops.area_m2(defs[0]["ring"]), 24.0 - 1.0, places=3)


class ChajjasHangOffTheirBeam(unittest.TestCase):
    """2. A beam-bottom hatch is a cantilever slab at the beam's soffit."""

    def _legend(self, meaning="INDICATES SLAB AT BEAM BOTTOM"):
        return [{"pattern": "GOST_GLASS", "kind": "other", "value_mm": None,
                 "meaning": meaning, "swatch": None}]

    def test_the_legend_row_names_the_pattern(self):
        self.assertEqual(slab_stops.chajja_patterns(self._legend()),
                         set(["GOST_GLASS"]))

    def test_a_row_that_is_not_about_a_slab_names_nothing(self):
        self.assertEqual(
            slab_stops.chajja_patterns(
                [{"pattern": "ZIGZAG", "kind": "other",
                  "meaning": "INDICATES BEAM BELOW"}]),
            set())

    def test_the_test14_chajja_sits_at_its_beams_soffit(self):
        # Verbatim from the fixture: the GOST_GLASS hatch at
        # (11051, 37959)-(11801, 38549), the 200-wide 400-deep beam along its
        # north side and the 300-wide 750-deep edge beam along its west. The
        # bay is 125 THK (the sheet's blanket note), so the ledge's top sits
        # 125 - 750 = -625 below the level: soffit flush with the deeper beam.
        region = _Region(_box(11050.8, 37958.9, 11800.8, 38548.9), "GOST_GLASS")
        beams = [_beam(11050.8, 39108.9, 11800.8, 39108.9, 200.0, 400.0),
                 _beam(10900.8, 37518.9, 10900.8, 40648.9, 300.0, 750.0)]
        out = slab_stops.chajja_slabs([region], beams, self._legend(),
                                      texts=[], blanket_thickness_mm=125.0)
        self.assertEqual(out["notes"], [])
        self.assertEqual(len(out["defs"]), 1)
        chajja = out["defs"][0]
        self.assertEqual(chajja["part"], "chajja")
        self.assertEqual(chajja["thickness_mm"], 125.0)
        self.assertAlmostEqual(chajja["offset_mm"], 125.0 - 750.0, places=6)

    def test_the_longest_contact_wins_over_a_deeper_beam_it_only_grazes(self):
        # The 750 beam runs the ledge's whole 3200 long side; the 1050 one
        # clips 175 mm of its end. Depth follows the support, not the maximum.
        region = _Region(_box(16250.8, 44058.9, 19450.8, 44653.9), "GOST_GLASS")
        beams = [_beam(16250.8, 43883.9, 19450.8, 43883.9, 350.0, 750.0),
                 _beam(19538.3, 44058.9, 19538.3, 44233.9, 175.0, 1050.0)]
        out = slab_stops.chajja_slabs([region], beams, self._legend(),
                                      texts=[], blanket_thickness_mm=125.0)
        self.assertAlmostEqual(out["defs"][0]["offset_mm"], 125.0 - 750.0,
                               places=6)

    def test_a_tie_takes_the_deeper_soffit_and_says_so(self):
        # A ledge spanning between two beams in equal measure -- 12 of
        # test14's 72 do. The deeper soffit clears both; the shallower would
        # run the ledge through the deeper beam's web.
        region = _Region(_box(11050.8, 37958.9, 11800.8, 38548.9), "GOST_GLASS")
        beams = [_beam(11050.8, 37958.9, 11050.8, 38548.9, 0.2, 400.0),
                 _beam(11800.8, 37958.9, 11800.8, 38548.9, 0.2, 750.0)]
        out = slab_stops.chajja_slabs([region], beams, self._legend(),
                                      texts=[], blanket_thickness_mm=125.0)
        self.assertAlmostEqual(out["defs"][0]["offset_mm"], 125.0 - 750.0,
                               places=6)
        self.assertTrue(any("DEEPER" in note for note in out["notes"]))

    def test_a_chajja_touching_no_beam_is_reported_not_guessed(self):
        region = _Region(_box(11050.8, 37958.9, 11800.8, 38548.9), "GOST_GLASS")
        out = slab_stops.chajja_slabs([region], [], self._legend(),
                                      texts=[], blanket_thickness_mm=125.0)
        self.assertEqual(out["defs"], [])
        self.assertTrue(any("no placed beam" in note for note in out["notes"]))

    def test_a_chajja_with_no_thickness_is_reported_not_levelled(self):
        region = _Region(_box(11050.8, 37958.9, 11800.8, 38548.9), "GOST_GLASS")
        beams = [_beam(10900.8, 37518.9, 10900.8, 40648.9, 300.0, 750.0)]
        out = slab_stops.chajja_slabs([region], beams, self._legend(),
                                      texts=[], blanket_thickness_mm=0.0)
        self.assertEqual(out["defs"], [])
        self.assertTrue(any("no thickness" in note for note in out["notes"]))

    def test_a_legend_swatch_is_never_a_chajja(self):
        region = _Region(_box(0, 0, 1050, 500), "GOST_GLASS")
        beams = [_beam(0, -100, 1050, -100, 200.0, 400.0)]
        out = slab_stops.chajja_slabs([region], beams, self._legend(),
                                      texts=[], skip_ids=set([id(region)]),
                                      blanket_thickness_mm=125.0)
        self.assertEqual(out["defs"], [])


class AStaircaseBayIsNotAFloor(unittest.TestCase):
    """3. A bay a staircase stands in is withdrawn from the slab pass."""

    def _bays(self):
        # 4 m x 4 m: 16 m2, inside stair_text's 4..60 m2 window.
        return [_bay(_box(0, 0, 4000, 4000)), _bay(_box(4000, 0, 8000, 4000))]

    def _risers(self, x0, count):
        return [_Record([(x0 + 250 * i, 500), (x0 + 250 * i, 3500)],
                        layers.CATEGORY_STAIR, kind="line")
                for i in range(count)]

    def test_a_staircase_text_withdraws_its_bay(self):
        out = slab_stops.stair_bays(self._bays(), [],
                                    [_Text("STAIRCASE", 2000, 2000)])
        self.assertEqual(out["indexes"], set([0]))
        self.assertTrue(any("staircase" in note for note in out["notes"]))

    def test_three_riser_lines_wholly_inside_withdraw_a_bay(self):
        out = slab_stops.stair_bays(self._bays(), self._risers(1000, 3), [])
        self.assertEqual(out["indexes"], set([0]))

    def test_two_riser_lines_are_not_a_flight(self):
        out = slab_stops.stair_bays(self._bays(), self._risers(1000, 2), [])
        self.assertEqual(out["indexes"], set())

    def test_a_riser_line_straddling_the_edge_does_not_claim_the_neighbour(self):
        # The measurement that fixed the rule: counted by ANY point, Project1
        # gained two bays holding no complete stair record, test12 four,
        # test16 two, test8 one.
        straddling = [_Record([(3800, 500 + 200 * i), (4200, 500 + 200 * i)],
                              layers.CATEGORY_STAIR, kind="line")
                      for i in range(6)]
        out = slab_stops.stair_bays(self._bays(),
                                    self._risers(1000, 3) + straddling, [])
        self.assertEqual(out["indexes"], set([0]))

    def test_a_floor_plate_with_three_stray_riser_lines_keeps_its_floor(self):
        plate = [_bay(_box(0, 0, 20000, 20000))]        # 400 m2
        out = slab_stops.stair_bays(plate, self._risers(1000, 3), [])
        self.assertEqual(out["indexes"], set())
        self.assertTrue(any("m2" in note for note in out["notes"]))

    def test_the_withdrawn_bay_leaves_the_defs_and_is_counted(self):
        defs, report = slab_outlines.apply_slab_stops(
            self._bays(), [], [_Text("ST-1", 2000, 2000)])
        self.assertEqual(len(defs), 1)
        self.assertEqual(report["stair_bays"], 1)
        self.assertEqual(report["stair_area_m2"], 16.0)


class ASunkBayStopsAtTheBeamEdge(unittest.TestCase):
    """4. The dropped slab of a sunk bay is cut back to the beam faces."""

    def _plan(self):
        return [{"ring": _ft(_box(0, 0, 6000, 4000)), "thickness_mm": 125.0,
                 "mark": "S1", "steps": []}]

    def _region(self, points_mm, pattern="ANGLE"):
        region = _Region(points_mm, pattern)
        region.category = layers.CATEGORY_SUNK
        return region

    def test_without_beams_the_drop_is_the_hatch_as_drawn(self):
        region = self._region(_box(1000, 1000, 5000, 3000))
        steps = fold_plan.plan_steps(self._plan(), [region],
                                     depths={"ANGLE": -150.0})
        self.assertEqual(len(steps["steps"]), 1)
        step = steps["steps"][0]
        self.assertFalse(step["trimmed"])
        self.assertEqual(len(step["drops"]), 1)
        self.assertAlmostEqual(slab_stops.area_m2(step["drops"][0]["ring"]),
                               8.0, places=3)

    def test_a_beam_along_one_side_pushes_the_drop_off_it(self):
        # the hatch is drawn from beam face to beam CENTRE on the right: the
        # 200-wide beam's body covers x 4900..5100, so the drop stops at 4900.
        region = self._region(_box(1000, 1000, 5000, 3000))
        beams = [_beam(5000, 0, 5000, 4000, 200.0, 400.0)]
        steps = fold_plan.plan_steps(self._plan(), [region],
                                     depths={"ANGLE": -150.0}, beams=beams)
        step = steps["steps"][0]
        self.assertTrue(step["trimmed"])
        self.assertEqual(len(step["drops"]), 1)
        self.assertAlmostEqual(slab_stops.area_m2(step["drops"][0]["ring"]),
                               3.9 * 2.0, places=3)

    def test_the_opening_cut_in_the_parent_is_still_the_whole_region(self):
        region = self._region(_box(1000, 1000, 5000, 3000))
        beams = [_beam(5000, 0, 5000, 4000, 200.0, 400.0)]
        steps = fold_plan.plan_steps(self._plan(), [region],
                                     depths={"ANGLE": -150.0}, beams=beams)
        self.assertAlmostEqual(
            slab_stops.area_m2(steps["steps"][0]["opening"]), 8.0, places=3)

    def test_a_beam_crossing_the_bay_divides_the_drop_in_two(self):
        region = self._region(_box(1000, 1000, 5000, 3000))
        beams = [_beam(3000, 0, 3000, 4000, 200.0, 400.0)]
        steps = fold_plan.plan_steps(self._plan(), [region],
                                     depths={"ANGLE": -150.0}, beams=beams)
        step = steps["steps"][0]
        self.assertEqual(len(step["drops"]), 2)
        self.assertAlmostEqual(
            sum(slab_stops.area_m2(drop["ring"]) for drop in step["drops"]),
            8.0 - 0.2 * 2.0, places=3)

    def test_every_piece_becomes_a_floor_of_its_own(self):
        region = self._region(_box(1000, 1000, 5000, 3000))
        beams = [_beam(3000, 0, 3000, 4000, 200.0, 400.0)]
        steps = fold_plan.plan_steps(self._plan(), [region],
                                     depths={"ANGLE": -150.0}, beams=beams)
        defs, _notes = fold_plan.slab_defs_with_steps(self._plan(),
                                                     steps["steps"])
        drops = [d for d in defs if d.get("part") == "sunk"]
        self.assertEqual(len(drops), 2)
        for drop in drops:
            self.assertAlmostEqual(drop["offset_mm"], -150.0, places=6)
            self.assertEqual(drop["thickness_mm"], 125.0)

    def test_the_trim_is_reported_grouped_not_one_line_per_bay(self):
        regions = [self._region(_box(500 + 100 * i, 1000, 5000, 3000))
                   for i in range(3)]
        beams = [_beam(5000, 0, 5000, 4000, 200.0, 400.0)]
        steps = fold_plan.plan_steps(self._plan(), regions,
                                     depths={"ANGLE": -150.0}, beams=beams)
        trims = [n for n in steps["notes"] if "stop at the beam faces" in n]
        self.assertEqual(len(trims), 1)
        self.assertIn("3 sunk bay(s)", trims[0])


class TheWholePassTogether(unittest.TestCase):
    """The three readings on one bay, in the order run_builders runs them."""

    def test_stairs_go_before_holes_so_no_hole_is_cut_into_a_withdrawn_bay(self):
        bays = [_bay(_box(0, 0, 4000, 4000)), _bay(_box(4000, 0, 8000, 4000))]
        ring = _Record(_box(1000, 1000, 2000, 2000),
                       layers.CATEGORY_SLAB_STOP, closed=True)
        records = [ring] + _cross(1000, 1000, 2000, 2000)
        defs, report = slab_outlines.apply_slab_stops(
            bays, records, [_Text("ST-1", 2000, 2000)])
        self.assertEqual(report["stair_bays"], 1)
        self.assertEqual(report["crossed"], 1)
        self.assertEqual(len(defs), 1)          # the surviving bay, uncut
        self.assertEqual(defs[0]["holes"], [])

    def test_the_report_carries_a_count_for_every_reading(self):
        defs, report = slab_outlines.apply_slab_stops([], [], [])
        for key in ("crossed", "holes", "divided", "stair_bays",
                    "stair_area_m2", "chajjas", "notes"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
