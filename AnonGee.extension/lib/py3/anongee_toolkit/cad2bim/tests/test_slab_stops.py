# -*- coding: utf-8 -*-
"""slab_stops -- what the drawing says STOPS the slab.

Four readings and one refusal each, pinned twice over: on SYNTHETIC plans
small enough to reason about, and on the REAL coordinates measured out of
StructuralPlan-Test14.dxf, which is the drawing the whole pass was written
for. The real ones are the ones that matter -- a synthetic square proves the
arithmetic, and only the fixture proves the convention was read right -- so
they carry the drawing's own numbers verbatim: the crossed pocket at
(19651, 42594)-(19851, 42944) with its two CUTOUT diagonals, the chajja at
(11051, 37959)-(11801, 38549) under its GOST_GLASS hatch, the 29.13 m2 bay at
(29750, 25894)-(37901, 29467) that carries a `CUTOUT` text and NO diagonals,
and the beams that bound them.

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


class ACrossedBayIsNotAFloorEither(unittest.TestCase):
    """3b. The X over a whole BAY -- the owner's "large portion" cut-outs.

    The same symbol the slab-stop rings carry, asked of a piece 100 times the
    size: on test14 the crossed COVER rings run 0.031 .. 0.227 m2 and the
    crossed BAYS 1.36 .. 19.81, 63.5 m2 in all.
    """

    def _bays(self):
        return [_bay(_box(0, 0, 4000, 4000)), _bay(_box(4000, 0, 8000, 4000))]

    def test_an_X_across_a_bay_withdraws_it(self):
        out = slab_stops.cutout_bays(self._bays(), _cross(0, 0, 4000, 4000))
        self.assertEqual(out["indexes"], set([0]))
        self.assertEqual(out["area_m2"], 16.0)
        self.assertTrue(any("crossed out" in note for note in out["notes"]))

    def test_one_diagonal_alone_is_not_the_symbol(self):
        half = _cross(0, 0, 4000, 4000)[:1]
        self.assertEqual(slab_stops.cutout_bays(self._bays(), half)["indexes"],
                         set())

    def test_two_diagonal_BEAMS_across_a_bay_are_members_not_a_cross(self):
        # test11 draws four 2000x2500 bays with a pair of 3200 mm diagonals on
        # ING-BEAM across each. Reading those as an X deletes 20.0 m2 of real
        # floor; the run places them as beams.
        beams = [
            _Record([(0, 0), (4000, 4000)], layers.CATEGORY_BEAM, kind="line"),
            _Record([(0, 4000), (4000, 0)], layers.CATEGORY_BEAM, kind="line")]
        self.assertEqual(slab_stops.cutout_bays(self._bays(), beams)["indexes"],
                         set())

    def test_a_bay_that_is_both_crossed_and_a_stair_is_counted_once(self):
        stairs = set([0])
        out = slab_stops.cutout_bays(self._bays(), _cross(0, 0, 4000, 4000),
                                     skip=stairs)
        self.assertEqual(out["indexes"], set())
        self.assertEqual(out["area_m2"], 0.0)
        self.assertTrue(any("withdrawn once" in note for note in out["notes"]))

    def test_the_withdrawn_bay_leaves_the_defs_and_is_counted(self):
        defs, report = slab_outlines.apply_slab_stops(
            self._bays(), _cross(4000, 0, 8000, 4000), [])
        self.assertEqual(len(defs), 1)
        self.assertEqual(report["cutout_bays"], 1)
        self.assertEqual(report["cutout_bay_area_m2"], 16.0)
        self.assertEqual(report["stair_bays"], 0)

    def test_the_stair_withdrawal_wins_the_count_when_a_bay_is_both(self):
        defs, report = slab_outlines.apply_slab_stops(
            self._bays(), _cross(0, 0, 4000, 4000),
            [_Text("ST-1", 2000, 2000)])
        self.assertEqual(len(defs), 1)
        self.assertEqual(report["stair_bays"], 1)
        self.assertEqual(report["cutout_bays"], 0)

    def test_test14s_own_19_81_m2_bay_and_its_two_CUTOUT_diagonals(self):
        # the biggest of the six, drawn on every one of the three towers
        bays = [_bay(_box(30551, 31616, 37101, 34641))]
        records = [
            _Record([(30551, 34641), (37101, 31616)],
                    layers.CATEGORY_CUTOUT, kind="line"),
            _Record([(30551, 31616), (37101, 34641)],
                    layers.CATEGORY_CUTOUT, kind="line")]
        out = slab_stops.cutout_bays(bays, records)
        self.assertEqual(out["indexes"], set([0]))
        self.assertEqual(out["area_m2"], 19.8)


class ATextNamingACutoutMarksOne(unittest.TestCase):
    """3c. The WORD is the same instruction as the X (BUG-16).

    The owner, after the v0.86.0 run: "Few large place still are still taking
    the Cutout Cross even when now that i have put the `Cutout, Lift Shaft,
    Duct etc.` text there also." Measured on test14: four bays per plan carry a
    `CUTOUT` text, three of them crossed too and ONE -- the largest, 29.13 m2 --
    crossed by nothing at all.

    The whole risk in this reading is a false positive, so the refusals below
    are not invented: every one of them is a real text out of this corpus.
    """

    def _bays(self):
        return [_bay(_box(0, 0, 4000, 4000)), _bay(_box(4000, 0, 8000, 4000))]

    def test_the_owners_three_words_are_the_vocabulary(self):
        for word in ("CUTOUT", "CUT OUT", "CUT-OUT", "Cutout", "cutouts",
                     "LIFT SHAFT", "DUCT", "SHAFT", "A.C. DUCT",
                     "PLUMBING SHAFT", "OPENING", "OPNG", "VOID",
                     "OPEN TO BELOW", "LIFT WELL"):
            self.assertTrue(slab_stops.names_a_cutout(word), word)

    def test_a_beam_or_slab_LABEL_never_matches(self):
        # every one of these is a text this corpus actually carries
        for label in ("B111", "S1", "S2", "MB", "BKT", "ST-1", "STB",
                      "200X400", "300X1050", "135 THK.", "150 THK.", "C42",
                      "SW4", "DN", "200X675/750"):
            self.assertFalse(slab_stops.names_a_cutout(label), label)

    def test_a_SENTENCE_about_a_cutout_is_not_one(self):
        # test15 keeps four sheet titles on a layer called A-CUTOUT, and test9
        # two legend rows. Read whole, all six are refused; a substring search
        # would have taken every one of them.
        for sentence in ("GROUND FLOOR PLAN", "1ST FLOOR PLAN",
                         "LIFT MACHINE ROOM FLOOR PLAN", "TERRACE FLOOR PLAN",
                         "CUTOUT IN SLAB & NON STR. WALL",
                         "HATCH INDICATE CUTOUT FOR DOOR ABOVE"):
            self.assertFalse(slab_stops.names_a_cutout(sentence), sentence)

    def test_a_bare_WELL_is_an_english_word_and_a_LIFT_WELL_is_not(self):
        self.assertFalse(slab_stops.names_a_cutout("WELL"))
        self.assertTrue(slab_stops.names_a_cutout("LIFT WELL"))

    def test_a_text_in_a_bay_withdraws_it_with_no_X_anywhere(self):
        out = slab_stops.cutout_bays(self._bays(), [],
                                     texts=[_Text("CUTOUT", 2000, 2000)])
        self.assertEqual(out["indexes"], set([0]))
        self.assertEqual(out["by_text"], 1)
        self.assertEqual(out["by_cross"], 0)
        self.assertEqual(out["area_m2"], 16.0)

    def test_a_bay_carrying_both_the_word_and_the_X_is_withdrawn_once(self):
        out = slab_stops.cutout_bays(self._bays(), _cross(0, 0, 4000, 4000),
                                     texts=[_Text("CUTOUT", 2000, 2000)])
        self.assertEqual(out["indexes"], set([0]))
        self.assertEqual(out["by_cross"], 1)
        self.assertEqual(out["by_text"], 1)
        self.assertEqual(out["area_m2"], 16.0)

    def test_a_text_the_layer_would_have_hidden_still_counts(self):
        # test14 writes CUTOUT on a layer called CUTOUT and test16 on
        # G-ANNO-TEXT; test15 writes its sheet titles on A-CUTOUT. The word is
        # asked, never the layer.
        out = slab_stops.cutout_bays(
            self._bays(), [], texts=[_Text("CUTOUT", 2000, 2000,
                                           layer="G-ANNO-TEXT")])
        self.assertEqual(out["indexes"], set([0]))

    def test_a_named_cutout_in_no_bay_is_reported_and_withdraws_nothing(self):
        # test14's 15 LIFT SHAFT texts and test10's 20 SHAFT texts land in no
        # bay at all: the beams never close one round a lift well.
        out = slab_stops.cutout_bays(self._bays(), [],
                                     texts=[_Text("LIFT SHAFT", 9000, 9000)])
        self.assertEqual(out["indexes"], set())
        self.assertTrue(any("inside no slab bay" in note
                            for note in out["notes"]))

    def test_a_named_bay_that_is_already_a_stair_is_counted_once(self):
        out = slab_stops.cutout_bays(self._bays(), [],
                                     texts=[_Text("CUTOUT", 2000, 2000)],
                                     skip=set([0]))
        self.assertEqual(out["indexes"], set())
        self.assertTrue(any("withdrawn once" in note for note in out["notes"]))
        self.assertFalse(any("inside no slab bay" in note
                             for note in out["notes"]))

    def test_test14s_own_29_13_m2_bay_carries_the_word_and_no_diagonals(self):
        # The owner's "large place". Its ring runs along the beam faces in 24
        # steps; the bounding rectangle has the same area to a centimetre.
        bays = [_bay(_box(29750.2, 25893.9, 37901.4, 29467.4))]
        out = slab_stops.cutout_bays(
            bays, [], texts=[_Text("CUTOUT", 33368.8, 27411.5,
                                   layer="CUTOUT")])
        self.assertEqual(out["indexes"], set([0]))
        self.assertEqual(out["by_text"], 1)
        self.assertEqual(out["by_cross"], 0)
        self.assertEqual(out["area_m2"], 29.1)

    def test_the_withdrawn_bay_leaves_the_defs_through_the_sheets_texts(self):
        defs, report = slab_outlines.apply_slab_stops(
            self._bays(), [], [], sheet_texts=[_Text("CUTOUT", 2000, 2000)])
        self.assertEqual(len(defs), 1)
        self.assertEqual(report["cutout_bays"], 1)
        self.assertEqual(report["cutout_bays_by_text"], 1)
        self.assertEqual(report["cutout_bays_by_cross"], 0)
        self.assertEqual(report["cutout_bay_area_m2"], 16.0)


class ASunkHatchOnlySaysWHICHBayAndHOWDEEP(unittest.TestCase):
    """4. The hatch informs the slab; the BAY's own ring is the geometry.

    The owner's rule, stated after the v0.83.0 run: "hatch pattern does should
    not change the slab geometry it should only carries info and details." So
    the hatch is drawn deliberately WRONG in these -- overhanging the bay by
    the beam half-widths, exactly as test14 draws it -- and the dropped floor
    still comes out the bay's own 6 x 4 m.
    """

    def _plan(self):
        return [{"ring": _ft(_box(0, 0, 6000, 4000)), "thickness_mm": 125.0,
                 "mark": "S1", "steps": []}]

    def _region(self, points_mm, pattern="ANGLE"):
        region = _Region(points_mm, pattern)
        region.category = layers.CATEGORY_SUNK
        return region

    def _steps(self, region, loops=None):
        return fold_plan.sunk_bay_steps(loops or self._plan(),
                                        [(region, 150.0)])

    def test_a_hatch_overhanging_the_bay_still_drops_the_BAY(self):
        # drawn 200 outside the bay on every side: the beam half-widths
        steps = self._steps(self._region(_box(-200, -200, 6200, 4200)))
        self.assertEqual(len(steps["steps"]), 1)
        step = steps["steps"][0]
        self.assertAlmostEqual(slab_stops.area_m2(step["dropped"]["ring"]),
                               24.0, places=3)

    def test_the_whole_bay_drops_so_nothing_is_cut_out_of_a_parent(self):
        steps = self._steps(self._region(_box(-200, -200, 6200, 4200)))
        step = steps["steps"][0]
        self.assertIsNone(step["opening"])

    def test_the_flat_floor_is_not_placed_where_the_dropped_one_is(self):
        loops = self._plan()
        steps = self._steps(self._region(_box(-200, -200, 6200, 4200)), loops)
        defs, _notes = fold_plan.slab_defs_with_steps(loops, steps["steps"])
        self.assertEqual([d.get("part") for d in defs], ["sunk"])
        self.assertEqual(defs[0]["offset_mm"], -150.0)
        self.assertEqual(defs[0]["holes"], [])

    def test_a_hatch_over_half_a_bay_sinks_nothing_and_says_so(self):
        # 0.5 of the bay: under _BAY_SINK_COVER, and the measured desert above
        # it is where the threshold sits
        steps = self._steps(self._region(_box(0, 0, 3000, 4000)))
        self.assertEqual(steps["steps"], [])
        self.assertEqual(len(steps["skipped"]), 1)
        self.assertIn("cover no bay", steps["skipped"][0])
        self.assertIn("ANGLE", steps["skipped"][0])

    def test_one_hatch_across_two_bays_sinks_both(self):
        loops = [{"ring": _ft(_box(0, 0, 6000, 4000)), "thickness_mm": 125.0,
                  "mark": "S1", "steps": []},
                 {"ring": _ft(_box(6200, 0, 12200, 4000)),
                  "thickness_mm": 125.0, "mark": "S2", "steps": []}]
        steps = self._steps(self._region(_box(-200, -200, 12400, 4200)), loops)
        self.assertEqual(len(steps["steps"]), 2)
        self.assertEqual(sorted(s["mark"] for s in steps["steps"]),
                         ["S1", "S2"])
        self.assertEqual(len(steps["notes"]), 1)
        self.assertIn("more than one bay", steps["notes"][0])

    def test_two_depths_over_one_bay_is_refused_not_averaged(self):
        loops = self._plan()
        shallow = self._region(_box(-200, -200, 6200, 4200), pattern="HONEY")
        deep = self._region(_box(-200, -200, 6200, 4200))
        steps = fold_plan.sunk_bay_steps(loops, [(shallow, 50.0),
                                                 (deep, 150.0)])
        self.assertEqual(steps["steps"], [])
        self.assertEqual(len(steps["skipped"]), 1)
        self.assertIn("two DIFFERENT depths", steps["skipped"][0])

    def test_the_same_depth_twice_over_one_bay_is_one_step(self):
        loops = self._plan()
        steps = fold_plan.sunk_bay_steps(
            loops, [(self._region(_box(-200, -200, 6200, 4200)), 150.0),
                    (self._region(_box(-100, -100, 6100, 4100)), 150.0)])
        self.assertEqual(len(steps["steps"]), 1)
        self.assertEqual(steps["skipped"], [])

    def test_a_bay_beyond_the_storey_limit_is_left_flat_and_named(self):
        steps = fold_plan.sunk_bay_steps(
            self._plan(), [(self._region(_box(-200, -200, 6200, 4200)),
                            6250.0)])
        self.assertEqual(steps["steps"], [])
        self.assertIn("is a storey", steps["skipped"][0])

    def test_a_re_entrant_hatch_is_measured_exactly_not_as_if_convex(self):
        # 81 of test14's 129 sunk hatches are re-entrant, so this is the normal
        # case rather than the exotic one. This L covers 18 of the bay's 24 m2
        # -- 0.75, over the line, it sinks. Clipping the bay to the ring as if
        # it were CONVEX, which is all `_clipped` alone can do, leaves 6 m2 and
        # would refuse it; `_overlap_area` takes the ring a triangle at a time.
        ell = [(-200, -200), (6200, -200), (6200, 2000), (3000, 2000),
               (3000, 4200), (-200, 4200)]
        bay = _ft(_box(0, 0, 6000, 4000))
        self.assertAlmostEqual(
            fold_plan.area_m2(_ft(ell)) and
            fold_plan._overlap_area(bay, _ft(ell)) * (_MM / 1000.0) ** 2,
            18.0, places=6)
        naive = fold_plan._clipped(bay, _ft(ell))
        self.assertAlmostEqual(
            abs(fold_plan._signed_area(naive)) * (_MM / 1000.0) ** 2,
            6.0, places=6)
        self.assertEqual(len(self._steps(self._region(ell))["steps"]), 1)

    def test_test14s_own_hatch_drops_its_bays_5_77_m2_not_its_own_6_49(self):
        # the ANGLE hatch at (19451..23226, 42594..44409) over the bay at
        # (19650..23226, 42594..44209): 6.49 m2 of hatch, 5.77 m2 of bay,
        # covered 0.9878 -- and 5.77 is what gets cast.
        hatch = [(23226, 44409), (23226, 42594), (19851, 42594),
                 (19851, 42944), (19651, 42944), (19650, 44059),
                 (19450, 44059), (19451, 44409)]
        bay = [(19650, 42594), (23226, 42594), (23226, 44209),
               (19650, 44209), (19650, 44085)]
        loops = [{"ring": _ft(bay), "thickness_mm": 125.0, "mark": "S1",
                  "steps": []}]
        self.assertAlmostEqual(fold_plan.area_m2(_ft(hatch)), 6.49, places=2)
        steps = fold_plan.sunk_bay_steps(loops, [(self._region(hatch), 150.0)])
        self.assertEqual(len(steps["steps"]), 1)
        self.assertAlmostEqual(
            fold_plan.area_m2(steps["steps"][0]["dropped"]["ring"]),
            5.775, places=3)

    def test_test14s_2_56_m2_hatch_in_an_8_66_m2_bay_sinks_nothing(self):
        # the measured minimum, 0.2179 of its bay -- the case the threshold
        # exists for. Reported, never applied.
        hatch = [(29652, 34991), (31051, 34991), (31051, 37144),
                 (30851, 37144), (30851, 36766), (29651, 36765)]
        bay = [(26451, 37144), (26451, 34991), (30851, 34991),
               (30851, 36566), (29451, 36565), (29451, 37144),
               (29301, 37144)]
        loops = [{"ring": _ft(bay), "thickness_mm": 125.0, "mark": "S1",
                  "steps": []}]
        steps = fold_plan.sunk_bay_steps(loops, [(self._region(hatch), 150.0)])
        self.assertEqual(steps["steps"], [])
        self.assertIn("cover no bay", steps["skipped"][0])

    def test_the_bay_is_open_ground_beyond_its_edges_so_no_support(self):
        # what lies beyond a bay's edge is a BEAM, not another floor -- the
        # 84 supports test14 used to build came from probing outside the
        # overhanging HATCH and finding the bay on the far side
        steps = self._steps(self._region(_box(-200, -200, 6200, 4200)))
        step = steps["steps"][0]
        self.assertEqual(step["supports"], [])

    def test_a_neighbouring_bay_that_DOES_abut_still_gets_its_support(self):
        loops = [{"ring": _ft(_box(0, 0, 6000, 4000)), "thickness_mm": 125.0,
                  "mark": "S1", "steps": []},
                 {"ring": _ft(_box(6000, 0, 12000, 4000)),
                  "thickness_mm": 125.0, "mark": "S2", "steps": []}]
        steps = self._steps(self._region(_box(-200, -200, 6200, 4200)), loops)
        step = [s for s in steps["steps"] if s["mark"] == "S1"][0]
        self.assertEqual(len(step["supports"]), 1)
        # the owner's arithmetic, unchanged: 150 > 125, so a void exists
        self.assertEqual(step["supports"][0]["offset_mm"], -125.0)
        self.assertEqual(step["supports"][0]["thickness_mm"],
                         150.0 + 125.0 - 125.0)


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
                    "stair_area_m2", "cutout_bays", "cutout_bays_by_cross",
                    "cutout_bays_by_text", "cutout_bay_area_m2", "chajjas",
                    "notes"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
