# -*- coding: utf-8 -*-
"""The hatch table's rows: one per layer, until a legend says otherwise.

BUG-6 (findings #13) measured the coarseness: test14's layer HAT carries four
patterns -- ANGLE 198 regions, ANSI37 63, HONEY 21 and GOST_GLASS 75 -- and
its legend gives them four different meanings. Three are sunk bays at three
DIFFERENT depths (150, 75 and 50 mm down) and the fourth is "SLAB AT BEAM
BOTTOM", which is not a step at all. A table with one row per layer can only
say HAT -> sunk: it loses the three depths and mislabels the 75 GOST_GLASS
regions.

So a layer becomes one row per PATTERN -- keyed "<layer>|<PATTERN>" -- WHERE
THE LEGEND ITSELF GIVES IT SEVERAL MEANINGS, and only there. The alternative,
splitting every layer by pattern, was measured across the whole corpus and is
worse: 36 rows become 61, and drawings whose patterns all mean the same thing
(test3, test4 and test5 gain three rows each) pay for a distinction nobody
drew. The legend-justified rule moves the two drawings that carry a legend and
leaves the other seventeen alone:

    test14   8 -> 11 rows   (HAT splits four ways)
    test9    5 ->  8 rows   (PI_COLUMN HATCH splits four ways)
    test10   3 ->  3 rows   (three step layers, one pattern each)

Every number here is measured off those fixtures.
"""

import os
import unittest

import _loader

layers, legend, dxf_reader = _loader.load("classify.layers", "legend",
                                          "readers.dxf_reader")

_MM = 304.8
_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST9 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test9.dxf")
_TEST10 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test10.dxf")
_TEST14 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test14.dxf")


class _Region(object):
    """A hatch as the reader leaves it, for the rows that need no geometry."""

    def __init__(self, layer, pattern):
        self.layer_key = layer
        self.pattern = pattern
        self.category = None
        self.points = []


def _regions(*pairs):
    """(layer, pattern, count) triples as regions."""
    out = []
    for layer, pattern, count in pairs:
        out.extend(_Region(layer, pattern) for _ in range(count))
    return out


def _entry(pattern, meaning, kind="other", value=None):
    """One legend row as legend.read leaves it -- plain data, which is how
    the classifier takes it (legend imports classify.layers, never back)."""
    return {"pattern": pattern, "meaning": meaning, "kind": kind,
            "value_mm": value, "layer": "L", "evidence": meaning}


class TheRowKey(unittest.TestCase):
    """Composed, never parsed: an xref layer is legitimately called
    "PLAN|HAT", so a key taken apart on its separator would guess."""

    def test_a_layer_alone_is_its_own_key(self):
        self.assertEqual(layers.hatch_row_key("HAT"), "HAT")
        self.assertEqual(layers.hatch_row_key("HAT", None), "HAT")
        self.assertEqual(layers.hatch_row_key("HAT", ""), "HAT")

    def test_a_pattern_makes_the_split_key(self):
        self.assertEqual(layers.hatch_row_key("HAT", "ANGLE"), "HAT|ANGLE")
        self.assertEqual(layers.HATCH_KEY_SEPARATOR, "|")

    def test_an_xref_layer_keeps_its_own_bar(self):
        # the separator is not unique in a layer name, which is exactly why
        # the key is composed at every call site instead of split apart
        self.assertEqual(layers.hatch_row_key("PLAN|HAT", "ANGLE"),
                         "PLAN|HAT|ANGLE")


class WhatTheLegendMeans(unittest.TestCase):
    """`hatch_meanings` only has to know when two patterns DIFFER."""

    def test_a_pattern_read_once_means_what_it_says(self):
        meanings = layers.hatch_meanings(
            [_entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.",
                    kind="step", value=-150.0)])
        self.assertEqual(list(meanings), ["ANGLE"])

    def test_the_same_row_drawn_three_times_is_agreement(self):
        # test14's legend appears once per plan; repetition is not ambiguity
        entries = [_entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.",
                          kind="step", value=-150.0)] * 3
        self.assertEqual(len(layers.hatch_meanings(entries)), 1)

    def test_two_depths_are_two_meanings(self):
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.",
                   kind="step", value=-150.0),
            _entry("HONEY", "INDICATES SLAB/BEAM SUNK BY 50MM.",
                   kind="step", value=-50.0)])
        self.assertNotEqual(meanings["ANGLE"], meanings["HONEY"])

    def test_a_report_only_meaning_is_its_own_text(self):
        # for a meaning this codebase has no pass for, the words ARE the
        # meaning -- and case, spacing and the full stop are not part of them
        meanings = layers.hatch_meanings([
            _entry("GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM"),
            _entry("GOST_GLASS", "indicates  slab at beam bottom.")])
        self.assertEqual(list(meanings), ["GOST_GLASS"])

    def test_a_pattern_that_says_two_things_says_nothing(self):
        # test9's ZIGZAG across three tower legends: refused, exactly as
        # legend.propose refuses it, so it can never justify a split either
        meanings = layers.hatch_meanings([
            _entry("ZIGZAG", "HATCH INDICATE T.O.S. +50MM.", kind="step",
                   value=50.0),
            _entry("ZIGZAG", "HATCH INDICATE COMPENSATORY STRIP.")])
        self.assertEqual(meanings, {})

    def test_no_legend_means_nothing_at_all(self):
        self.assertEqual(layers.hatch_meanings(None), {})
        self.assertEqual(layers.hatch_meanings([]), {})


class WhenALayerSplits(unittest.TestCase):
    def test_without_a_legend_every_layer_keeps_one_row(self):
        rows = layers.hatch_rows(_regions(("HAT", "ANGLE", 4),
                                          ("HAT", "HONEY", 2)))
        self.assertEqual([(row["key"], row["count"]) for row in rows],
                         [("HAT", 6)])
        self.assertIsNone(rows[0]["pattern"])
        self.assertEqual(rows[0]["patterns"], ("ANGLE", "HONEY"))

    def test_one_meaning_over_two_patterns_keeps_one_row(self):
        # the deliberate limit: patterns that mean the SAME thing are not a
        # distinction the user has to see twice
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 50MM.", kind="step",
                   value=-50.0),
            _entry("HONEY", "INDICATES SLAB/BEAM SUNK BY 50MM.", kind="step",
                   value=-50.0)])
        rows = layers.hatch_rows(_regions(("HAT", "ANGLE", 4),
                                          ("HAT", "HONEY", 2)), meanings)
        self.assertEqual([(row["key"], row["count"]) for row in rows],
                         [("HAT", 6)])

    def test_two_meanings_split_the_layer_by_pattern(self):
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.", kind="step",
                   value=-150.0),
            _entry("GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM")])
        rows = layers.hatch_rows(_regions(("HAT", "ANGLE", 4),
                                          ("HAT", "GOST_GLASS", 2)), meanings)
        self.assertEqual([(row["key"], row["count"]) for row in rows],
                         [("HAT|ANGLE", 4), ("HAT|GOST_GLASS", 2)])
        self.assertEqual([row["pattern"] for row in rows],
                         ["ANGLE", "GOST_GLASS"])

    def test_a_split_layer_splits_whole(self):
        # once the layer is split every region has to land on exactly one
        # row, so a pattern the legend never mentioned gets a row too
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.", kind="step",
                   value=-150.0),
            _entry("GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM")])
        rows = layers.hatch_rows(_regions(("HAT", "ANGLE", 4),
                                          ("HAT", "GOST_GLASS", 2),
                                          ("HAT", "ANSI31", 1)), meanings)
        self.assertEqual([row["key"] for row in rows],
                         ["HAT|ANGLE", "HAT|ANSI31", "HAT|GOST_GLASS"])
        self.assertEqual(sum(row["count"] for row in rows), 7)

    def test_only_the_layer_the_legend_split_is_split(self):
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.", kind="step",
                   value=-150.0),
            _entry("GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM")])
        rows = layers.hatch_rows(_regions(("HAT", "ANGLE", 4),
                                          ("HAT", "GOST_GLASS", 2),
                                          ("S-COLS", "FP_1", 30)), meanings)
        self.assertEqual([row["key"] for row in rows],
                         ["HAT|ANGLE", "HAT|GOST_GLASS", "S-COLS"])

    def test_the_convention_still_reads_the_layer_not_the_pattern(self):
        # a pattern name says nothing about meaning, so split rows all start
        # on the guess the LAYER's name earns
        meanings = layers.hatch_meanings([
            _entry("ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM.", kind="step",
                   value=-150.0),
            _entry("GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM")])
        rows = layers.hatch_rows(_regions(("S-FND-FOLD", "ANGLE", 4),
                                          ("S-FND-FOLD", "GOST_GLASS", 2)),
                                 meanings)
        self.assertEqual(layers.default_hatch_row_mapping(rows),
                         {"S-FND-FOLD|ANGLE": layers.CATEGORY_FOLD,
                          "S-FND-FOLD|GOST_GLASS": layers.CATEGORY_FOLD})


class ReadingAMappingBack(unittest.TestCase):
    """The narrower answer wins, and a mapping written before the split
    still routes every region it recognises."""

    def test_the_split_row_beats_the_layer_row(self):
        mapping = {"HAT": layers.CATEGORY_SUNK,
                   "HAT|GOST_GLASS": layers.CATEGORY_UNMAPPED}
        self.assertEqual(layers.hatch_category(mapping, "HAT", "GOST_GLASS"),
                         layers.CATEGORY_UNMAPPED)
        self.assertEqual(layers.hatch_category(mapping, "HAT", "ANGLE"),
                         layers.CATEGORY_SUNK)

    def test_a_layer_keyed_mapping_still_answers(self):
        mapping = {"S-FND-FOLD": layers.CATEGORY_FOLD}
        self.assertEqual(layers.hatch_category(mapping, "S-FND-FOLD",
                                               "ANSI37"),
                         layers.CATEGORY_FOLD)

    def test_nothing_at_all_is_unmapped(self):
        for mapping in (None, {}, {"OTHER": layers.CATEGORY_FOLD}):
            self.assertEqual(layers.hatch_category(mapping, "HAT", "ANGLE"),
                             layers.CATEGORY_UNMAPPED)

    def test_apply_stamps_each_region_from_its_own_row(self):
        regions = _regions(("HAT", "ANGLE", 2), ("HAT", "GOST_GLASS", 3))
        layers.apply_hatch_mapping(regions, {"HAT|ANGLE": layers.CATEGORY_SUNK,
                                             "HAT|GOST_GLASS":
                                                 layers.CATEGORY_UNMAPPED})
        stamped = {}
        for region in regions:
            stamped[region.category] = stamped.get(region.category, 0) + 1
        self.assertEqual(stamped, {layers.CATEGORY_SUNK: 2,
                                   layers.CATEGORY_UNMAPPED: 3})

    def test_apply_survives_a_region_with_no_pattern(self):
        region = _Region("HAT", None)
        layers.apply_hatch_mapping([region], {"HAT": layers.CATEGORY_SUNK})
        self.assertEqual(region.category, layers.CATEGORY_SUNK)


_FIXTURES = {}


def _read_fixture(path):
    """One fixture DXF in internal feet, the way the pushbutton hands it to
    the legend and the table. Cached across the classes that read it."""
    if path not in _FIXTURES:
        result = dxf_reader.read_dxf(path)
        scale = 1.0 / _MM
        for region in result.regions:
            region.points = [(p[0] * scale, p[1] * scale, 0.0)
                             for p in region.points]
        for text in result.texts:
            text.point_internal = (text.point[0] * scale,
                                   text.point[1] * scale, 0.0)
        _FIXTURES[path] = result
    return _FIXTURES[path]


class _FixtureTable(unittest.TestCase):
    _path = None

    def setUp(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf` "
                          "(the bundled lib/py3 copy is a Windows build)")

    def _table(self):
        """The rows, the seeded defaults and the marks, assembled exactly as
        the pushbutton assembles them before the dialog opens."""
        result = _read_fixture(self._path)
        entries = legend.read(result.regions, result.texts)
        rows = layers.hatch_rows(result.regions,
                                 layers.hatch_meanings(entries))
        default = layers.default_hatch_row_mapping(rows)
        notes = {}
        split = set(row["layer"] for row in rows if row["pattern"])
        proposal = legend.propose(entries, result.regions)
        for layer_name in proposal["mapping"]:
            if layer_name in split:
                continue
            default[layer_name] = proposal["mapping"][layer_name]
            notes[layer_name] = proposal["rows"][layer_name]
        for row in rows:
            if not row["pattern"]:
                continue
            own = legend.propose([entry for entry in entries
                                  if entry["pattern"] == row["pattern"]],
                                 result.regions)
            category = own["mapping"].get(row["layer"])
            if category:
                default[row["key"]] = category
                notes[row["key"]] = own["rows"][row["layer"]]
        return result, rows, default, notes


class TheTest14Table(_FixtureTable):
    """BUG-6's own drawing: four patterns, four meanings, one layer.

    Re-pinned 2026-08-29 against the owner's redrawn fixture (commit 901c8f8):
    the sheet lost its RC PARDI and floating-column legend rows and the layers
    that carried them, so the table is 7 rows where it was 11. HAT still splits
    four ways, which is the rule this class exists to hold.
    """

    _path = _TEST14

    def test_hat_becomes_four_rows_and_the_rest_stay_one(self):
        _result, rows, _default, _notes = self._table()
        self.assertEqual(len(rows), 7)           # 4 layers, HAT four ways
        # counts are every region on the layer, the legend's own three
        # demonstration swatches per pattern included -- the table has always
        # counted what is drawn, and which of them is a swatch is a question
        # for the pass that builds, not for the row that routes
        self.assertEqual([(row["key"], row["count"]) for row in rows
                          if row["layer"] == "HAT"],
                         [("HAT|ANGLE", 168), ("HAT|ANSI37", 51),
                          ("HAT|GOST_GLASS", 75), ("HAT|HONEY", 21)])
        # every other hatch layer on the sheet keeps its single row
        self.assertEqual(sorted(row["key"] for row in rows
                                if row["layer"] != "HAT"),
                         ["FC", "RC PARDI 200MM", "col solid"])
        # and no region is lost or counted twice by the split
        self.assertEqual(sum(row["count"] for row in rows), 549)

    def test_the_three_depths_keep_their_own_rows_and_gost_glass_is_not_sunk(self):
        # the whole point of BUG-6: the per-layer proposal HAT -> sunk swept
        # all 315 regions into one bucket, 75 of them wrongly
        _result, _rows, default, _notes = self._table()
        self.assertEqual(default["HAT|ANGLE"], layers.CATEGORY_SUNK)
        self.assertEqual(default["HAT|ANSI37"], layers.CATEGORY_SUNK)
        self.assertEqual(default["HAT|HONEY"], layers.CATEGORY_SUNK)
        # "INDICATES SLAB AT BEAM BOTTOM" is report-only: it proposes
        # nothing, and the layer's own name proposes nothing either
        self.assertEqual(default["HAT|GOST_GLASS"], layers.CATEGORY_UNMAPPED)
        self.assertEqual(layers.classify_hatch_layer("HAT"),
                         layers.CATEGORY_UNMAPPED)

    def test_the_depths_stay_apart_and_reach_the_dialog_by_pattern(self):
        result = _read_fixture(self._path)
        entries = legend.read(result.regions, result.texts)
        depths, notes = legend.legend_steps(entries)
        self.assertEqual(depths, {"ANSI37": -75.0, "ANGLE": -150.0,
                                  "HONEY": -50.0})
        self.assertEqual(notes, [])
        # one depth per split row, keyed by the pattern the row carries
        _r, rows, _d, _n = self._table()
        carried = dict((row["key"], depths.get(row["pattern"]))
                       for row in rows if row["layer"] == "HAT")
        self.assertEqual(carried, {"HAT|ANGLE": -150.0, "HAT|ANSI37": -75.0,
                                   "HAT|HONEY": -50.0,
                                   "HAT|GOST_GLASS": None})

    def test_each_split_row_is_marked_with_its_own_legend_words(self):
        _result, _rows, _default, notes = self._table()
        self.assertEqual(sorted(notes),
                         ["HAT|ANGLE", "HAT|ANSI37", "HAT|HONEY"])
        self.assertIn("SUNK BY 150MM", notes["HAT|ANGLE"])
        self.assertIn("SUNK BY 75MM", notes["HAT|ANSI37"])
        self.assertIn("SUNK BY 50MM", notes["HAT|HONEY"])
        for note in notes.values():
            self.assertIn("proposed as sunk", note)

    def test_the_regions_land_where_the_rows_say(self):
        result, _rows, default, _notes = self._table()
        layers.apply_hatch_mapping(result.regions, default)
        sunk = [region for region in result.regions
                if region.category == layers.CATEGORY_SUNK]
        self.assertEqual(len(sunk), 240)         # 168 + 51 + 21
        self.assertEqual(set(region.pattern for region in sunk),
                         {"ANGLE", "ANSI37", "HONEY"})
        # the 75 that used to ride along with them
        self.assertEqual([region.category for region in result.regions
                          if region.pattern == "GOST_GLASS"],
                         [layers.CATEGORY_UNMAPPED] * 75)


class TheTest9Table(_FixtureTable):
    """The other drawing with a legend: three towers, three legend blocks."""

    _path = _TEST9

    def test_the_column_hatch_layer_splits_and_nothing_else_does(self):
        _result, rows, _default, _notes = self._table()
        self.assertEqual(len(rows), 8)           # 5 layers, one split four ways
        self.assertEqual([(row["key"], row["count"]) for row in rows
                          if row["layer"] == "PI_COLUMN HATCH"],
                         [("PI_COLUMN HATCH|ANSI32", 10),
                          ("PI_COLUMN HATCH|ANSI37", 1),
                          ("PI_COLUMN HATCH|AR-CONC", 29),
                          ("PI_COLUMN HATCH|SOLID", 66)])
        # PI_HATCH carries three patterns and PI_RETAINING WALL HATCH two,
        # but their legend rows are ambiguous (ZIGZAG, STARS, SOLID mean
        # different things per tower) or absent, so neither splits
        self.assertEqual(sorted(row["key"] for row in rows
                                if row["layer"] != "PI_COLUMN HATCH"),
                         ["PI_HATCH", "PI_LEVEL", "PI_RETAINING WALL HATCH",
                          "PI_SHEAR WALL CUTOUT"])
        self.assertEqual(sum(row["count"] for row in rows), 158)

    def test_the_one_proposal_this_sheet_carries_is_untouched(self):
        # ASPHALT -> cutout on PI_SHEAR WALL CUTOUT: an unsplit layer, so it
        # is still proposed and marked exactly as it was before the split
        _result, _rows, default, notes = self._table()
        self.assertEqual(default["PI_SHEAR WALL CUTOUT"],
                         layers.CATEGORY_CUTOUT)
        self.assertEqual(sorted(notes), ["PI_SHEAR WALL CUTOUT"])

    def test_the_split_rows_keep_the_layer_name_s_own_guess(self):
        # all four meanings on PI_COLUMN HATCH are report-only, so nothing is
        # proposed for them and the convention's "col" token still answers
        _result, rows, default, notes = self._table()
        for row in rows:
            if row["layer"] != "PI_COLUMN HATCH":
                continue
            self.assertEqual(default[row["key"]], layers.CATEGORY_COLUMN)
            self.assertNotIn(row["key"], notes)


class TheTest10Table(_FixtureTable):
    """The drawing that says what a hatch means by LAYER, and is untouched."""

    _path = _TEST10

    def test_three_step_layers_stay_three_rows(self):
        _result, rows, default, notes = self._table()
        self.assertEqual([(row["key"], row["count"]) for row in rows],
                         [("S-COLS", 330), ("S-FND-FOLD", 6),
                          ("S-FND-SUNK", 1)])
        # no legend at all on this sheet: nothing to split by, nothing marked
        self.assertEqual(notes, {})
        self.assertEqual(default, {"S-COLS": layers.CATEGORY_COLUMN,
                                   "S-FND-FOLD": layers.CATEGORY_FOLD,
                                   "S-FND-SUNK": layers.CATEGORY_SUNK})

    def test_the_folds_and_the_sunk_strip_still_classify(self):
        result, _rows, default, _notes = self._table()
        layers.apply_hatch_mapping(result.regions, default)
        tally = {}
        for region in result.regions:
            tally[region.category] = tally.get(region.category, 0) + 1
        self.assertEqual(tally, {layers.CATEGORY_COLUMN: 330,
                                 layers.CATEGORY_FOLD: 6,
                                 layers.CATEGORY_SUNK: 1})


if __name__ == "__main__":
    unittest.main()
