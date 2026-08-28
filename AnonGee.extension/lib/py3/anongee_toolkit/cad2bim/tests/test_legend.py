# -*- coding: utf-8 -*-
"""The legend: swatch pattern -> legend text -> meaning, proposed, never applied.

Every number in this file is measured off the two fixtures that carry the
convention, test9 (StructuralPlan-Test9.dxf) and test14.

test9 -- three towers on one sheet, three legend blocks:

  * 14 legend rows, "HATCH INDICATE ...", across THREE tower legends plus one
    standalone cutout entry. Swatches are 807x484, 1001x601 and 1100x400
    rectangles; their texts anchor 657..947 mm from the swatch centre; rows
    stack 617..640 mm apart, so the WRONG row's swatch is 839..1020 mm away.
  * The nearest PLAN hatch to any legend text is 6622 mm out (worst 16140) --
    the measured reason meaning travels by PATTERN, never by proximity.
  * The near-miss "*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM" describes
    a beam and has NO swatch: the nearest swatch-sized region is 1697 mm away
    and already belongs to the row 782 mm from it.
  * The same pattern means different things per tower: ZIGZAG is
    "T.O.S. +50MM." / "COMPENSATORY STRIP." / "TOS. +6250." across the three.
    A whole-sheet read refuses those patterns loudly instead of picking one.
  * What survives on test9: ONE proposal -- ASPHALT -> cutout on
    PI_SHEAR WALL CUTOUT (9 plan hatches, all on that one layer) -- and three
    report-only meanings (AR-CONC, ANSI32, ANSI37).

test14 -- three plans of ONE building, the same legend drawn three times:

  * 8 rows x 3 = 24, every one "INDICATES ..." with no HATCH prefix and an S
    on the verb. Swatches are 1050x500; every text anchors 751 mm from its
    own swatch. This is the drawing the "HATCH INDICATE" rule read as empty.
  * The rows: SUNK BY 75/150/50MM (ANSI37/ANGLE/HONEY, 60+195+18 plan hatches,
    all on HAT), SLAB AT BEAM BOTTOM (GOST_GLASS, 72, also on HAT), 100/150/
    200MM THK. RC PARDI (EARTH/AR-HBONE/TRIANG on their own RC PARDI layers)
    and FLOATING COLUMN (SOLID, on FC + S-Refr-Sect + col solid).
  * Repetition is not ambiguity: all three plans say the identical thing, so
    all eight patterns agree and survive `_agreed`.
  * What survives on test14: ONE proposal -- HAT -> sunk, from three agreeing
    SUNK patterns -- with the depths (-75/-150/-50) carried per pattern by
    `legend_steps`, and five report-only meanings.

The sign question is OPEN where the drawing only signs it: test9's values are
all "+" T.O.S., so fold-up cannot be told from drop and those go to
CATEGORY_FOLD (findings.md records the question). test14 states its direction
in words -- "SUNK BY 75MM." -- so it reads -75 and proposes CATEGORY_SUNK.
"""

import os
import unittest

import _loader

legend, layers, config, dxf_reader = _loader.load(
    "legend", "classify.layers", "config", "readers.dxf_reader")

_MM = 304.8
_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST9 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test9.dxf")
_TEST14 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test14.dxf")


def _mm(value):
    return value / _MM


class _Region(object):
    """A hatch as the reader leaves it: outer ring in internal feet."""

    def __init__(self, x0, y0, x1, y1, pattern, layer):
        self.points = [(_mm(x0), _mm(y0), 0.0), (_mm(x1), _mm(y0), 0.0),
                       (_mm(x1), _mm(y1), 0.0), (_mm(x0), _mm(y1), 0.0)]
        self.pattern = pattern
        self.layer = layer
        self.category = None

    @property
    def layer_key(self):
        return self.layer


class _Text(object):
    def __init__(self, text, point_mm):
        self.text = text
        self.point = (_mm(point_mm[0]), _mm(point_mm[1]), 0.0)
        self.point_internal = None


def _swatch(x, y, pattern, layer="PI_HATCH", w=807, h=484):
    """A legend swatch at test9's size, centred on (x, y)."""
    return _Region(x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0,
                   pattern, layer)


def _row(x, y, pattern, meaning, layer="PI_HATCH"):
    """One legend row at the measured geometry: the text anchors 653 mm right
    and 68 mm below the swatch centre (test9's insertion-point offset)."""
    return (_swatch(x, y, pattern, layer),
            _Text(meaning, (x + 653, y - 68)))


def _row14(x, y, pattern, meaning, layer="HAT"):
    """One test14 legend row: a 1050x500 swatch, its text anchored 744 mm
    right and 100 mm below the centre -- 751 mm out. Rows stack 698 mm apart
    there, so the NEXT row's swatch is 955 mm away: 204 mm of margin, the same
    order as test9's, and the same reason pairing has to be mutual."""
    return (_swatch(x, y, pattern, layer, w=1050, h=500),
            _Text(meaning, (x + 744, y - 100)))


class SwatchPairing(unittest.TestCase):
    def test_a_row_pairs_at_the_measured_geometry(self):
        swatch, text = _row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +50MM.")
        entries = legend.read([swatch], [text])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["pattern"], "ZIGZAG")
        self.assertEqual(entries[0]["layer"], "PI_HATCH")

    def test_a_plan_hatch_distance_never_pairs(self):
        # 6622 mm is the CLOSEST any test9 plan hatch comes to a legend text.
        swatch = _swatch(0, 0, "ZIGZAG")
        text = _Text("HATCH INDICATE T.O.S. +50MM.", (6622, 0))
        self.assertEqual(legend.read([swatch], [text]), [])

    def test_a_missing_swatch_unpairs_its_row_instead_of_stealing(self):
        # Two rows stacked 617 mm apart, the lower swatch not drawn: the lower
        # text's nearest swatch is now the upper one (901 mm, inside reach),
        # but that swatch's own text is closer -- mutual-nearest refuses the
        # theft, so the orphaned row reads as NO entry rather than the wrong
        # meaning.
        upper_swatch, upper_text = _row(0, 617, "STARS",
                                        "HATCH INDICATE T.O.S. +400MM.")
        lower_text = _Text("HATCH INDICATE NON TOWER AREA.", (653, -68))
        entries = legend.read([upper_swatch], [upper_text, lower_text])
        self.assertEqual([e["meaning"] for e in entries],
                         ["HATCH INDICATE T.O.S. +400MM."])

    def test_a_row_without_the_hatch_prefix_pairs_the_same_way(self):
        # test14's whole legend reads "INDICATES ..." -- no HATCH, and an S on
        # the verb. Nothing about the geometry differs, and the geometry is
        # what says this is a row.
        swatch, text = _row14(0, 0, "ANGLE",
                              "INDICATES SLAB/BEAM SUNK BY 150MM.")
        entries = legend.read([swatch], [text])
        self.assertEqual([(e["pattern"], e["layer"]) for e in entries],
                         [("ANGLE", "HAT")])

    def test_neighbouring_rows_keep_their_own_swatches_at_698_spacing(self):
        # Both swatches drawn, 698 mm apart: each text's own is 751 mm away
        # and its neighbour's 955, so mutual-nearest has to hold the 204 mm
        # margin twice over.
        upper = _row14(0, 698, "ANSI37", "INDICATES SLAB/BEAM SUNK BY 75MM.")
        lower = _row14(0, 0, "HONEY", "INDICATES SLAB/BEAM SUNK BY 50MM.")
        entries = legend.read([upper[0], lower[0]], [upper[1], lower[1]])
        self.assertEqual([(e["pattern"], e["value_mm"]) for e in entries],
                         [("ANSI37", -75.0), ("HONEY", -50.0)])

    def test_the_size_band_is_measured_not_guessed(self):
        # Beside a legend text, an 83x83 level marker and a 600x75 wall sliver
        # (test9's smallest non-swatches) are not swatches; the 1100x400
        # cutout swatch -- the band's widest real occupant -- is.
        text = _Text("HATCH INDICATE CUTOUT FOR DOOR ABOVE", (653, -68))
        marker = _Region(-41, -41, 42, 42, "SOLID", "PI_LEVEL")
        sliver = _Region(-300, -37, 300, 38, "ZIGZAG", "PI_HATCH")
        self.assertEqual(legend.read([marker, sliver], [text]), [])
        swatch = _swatch(0, 0, "ASPHALT", "PI_SHEAR WALL CUTOUT",
                         w=1100, h=400)
        entries = legend.read([marker, sliver, swatch], [text])
        self.assertEqual([e["pattern"] for e in entries], ["ASPHALT"])

    def test_the_camber_sentence_has_no_swatch_and_is_not_a_row(self):
        # test9's near-miss: "*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM"
        # describes a beam, not a hatch, and nothing on the sheet demonstrates
        # it. The nearest swatch-sized region is 1697 mm away -- past the
        # reach -- and that swatch is a real row's own (782 mm from its text
        # on the sheet, 657 at the tightest row geometry used here), so the
        # pair is not mutual either. The wording used to do this job ("HATCH
        # INDICATE") and could not, since test14 writes every row without the
        # prefix; the geometry does it, and does it twice.
        swatch, row = _row(0, 0, "SOLID", "HATCH INDICATE COLUMN THROUGH "
                                          "FOUNDATION TO TERMINATION.")
        camber = _Text("*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM",
                       (1697, 0))
        entries = legend.read([swatch], [row, camber])
        self.assertEqual([e["meaning"] for e in entries],
                         ["HATCH INDICATE COLUMN THROUGH FOUNDATION TO "
                          "TERMINATION."])

    def test_mutual_nearest_refuses_the_camber_on_its_own(self):
        # The two locks are independent, and this is the stronger one: widen
        # the reach past the 1697 mm gap and the sentence STILL reads as no
        # row, because the swatch it reaches for calls the real row its own
        # nearest. A drawing whose legend sits further from its texts than
        # this corpus does would lose the reach lock and keep this one.
        swatch, row = _row(0, 0, "SOLID", "HATCH INDICATE COLUMN THROUGH "
                                          "FOUNDATION TO TERMINATION.")
        camber = _Text("*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM",
                       (1697, 0))
        entries = legend.read([swatch], [row, camber], reach_mm=2500.0)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("CAMBER", entries[0]["meaning"])


class MeaningParsing(unittest.TestCase):
    """test9's five meanings, verbatim, plus the sign the drawing never uses."""

    def _kind_of(self, meaning):
        swatch, text = _row(0, 0, "ZIGZAG", meaning)
        entries = legend.read([swatch], [text])
        self.assertEqual(len(entries), 1)
        return entries[0]

    def test_tos_plus_50(self):
        entry = self._kind_of("HATCH INDICATE T.O.S. +50MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 50.0))

    def test_tos_plus_400(self):
        entry = self._kind_of("HATCH INDICATE T.O.S. +400MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 400.0))

    def test_tos_spelled_without_dots_and_without_mm(self):
        entry = self._kind_of("HATCH INDICATE TOS. +6250.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 6250.0))

    def test_cutout(self):
        # The MTEXT arrives with its continuation line; whitespace collapses.
        entry = self._kind_of("HATCH INDICATE CUTOUT FOR DOOR ABOVE\n"
                              "1ST. FLOOR LVL. SLAB AS/ARCH DRAWING")
        self.assertEqual(entry["kind"], "cutout")
        self.assertIsNone(entry["value_mm"])
        self.assertEqual(entry["meaning"],
                         "HATCH INDICATE CUTOUT FOR DOOR ABOVE "
                         "1ST. FLOOR LVL. SLAB AS/ARCH DRAWING")

    def test_anything_else_is_kept_verbatim_as_report_only(self):
        entry = self._kind_of("HATCH INDICATE COLUMN/SHEAR WALL THROUGH "
                              "FOUNDATION TO TERMINATION.")
        self.assertEqual(entry["kind"], "other")
        self.assertEqual(entry["meaning"],
                         "HATCH INDICATE COLUMN/SHEAR WALL THROUGH "
                         "FOUNDATION TO TERMINATION.")

    def test_a_minus_keeps_its_sign(self):
        # No fixture draws one; the parser must still not fold it into "+".
        entry = self._kind_of("HATCH INDICATE T.O.S. -300MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", -300.0))


class SunkMeanings(unittest.TestCase):
    """test14's three depths, verbatim, and the row that must not be read as a
    fourth. The parser anchors on the word SUNK, never on a number, because
    the same legend writes its wall thicknesses the same way."""

    def _kind_of(self, meaning, pattern="ANGLE"):
        swatch, text = _row14(0, 0, pattern, meaning)
        entries = legend.read([swatch], [text])
        self.assertEqual(len(entries), 1)
        return entries[0]

    def test_sunk_by_75(self):
        # Negative: "SUNK" is the drawing saying DOWN. That is not the open
        # sign question -- that one is what a "+" on a T.O.S. note means -- so
        # the direction is recorded rather than left to a later guess.
        entry = self._kind_of("INDICATES SLAB/BEAM SUNK BY 75MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", -75.0))

    def test_sunk_by_150(self):
        entry = self._kind_of("INDICATES SLAB/BEAM SUNK BY 150MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", -150.0))

    def test_sunk_by_50(self):
        entry = self._kind_of("INDICATES SLAB/BEAM SUNK BY 50MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", -50.0))

    def test_a_wall_thickness_is_not_a_depth(self):
        # The trap: "INDICATES 150MM THK. RC PARDI" sits three rows under
        # "SUNK BY 150MM." in the same legend and carries the same number. A
        # rule that grabbed the number would route 132 parapet hatches into
        # the fold machinery as a 150 mm step. This codebase has no pass for
        # a parapet, so the row is kept verbatim and only ever reported.
        entry = self._kind_of("INDICATES 150MM THK. RC PARDI",
                              pattern="AR-HBONE")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("other", None))
        self.assertEqual(entry["meaning"], "INDICATES 150MM THK. RC PARDI")

    def test_the_other_test14_meanings_stay_report_only(self):
        # SLAB AT BEAM BOTTOM and FLOATING COLUMN are real meanings with no
        # pass behind them either -- carried the way test9 carries AR-CONC.
        for meaning in ("INDICATES SLAB AT BEAM BOTTOM",
                        "INDICATES FLOATING COLUMN STARTS FROM 1ST "
                        "HABITABLE LEVEL."):
            entry = self._kind_of(meaning)
            self.assertEqual((entry["kind"], entry["value_mm"]),
                             ("other", None))
            self.assertEqual(entry["meaning"], meaning)


class AmbiguityIsRefused(unittest.TestCase):
    """Two meanings for one pattern -> no proposal, a note. test9's whole-sheet
    read is the case: three towers, three legends, one ZIGZAG."""

    def test_conflicting_meanings_kill_the_pattern_loudly(self):
        rows = [_row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +50MM."),
                _row(50000, 0, "ZIGZAG", "HATCH INDICATE TOS. +6250.")]
        regions = [swatch for swatch, _text in rows]
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        self.assertEqual(len(entries), 2)
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertEqual(len(proposal["notes"]), 1)
        self.assertIn("ZIGZAG", proposal["notes"][0])
        self.assertIn("no proposal", proposal["notes"][0])

    def test_the_same_meaning_twice_is_agreement_not_conflict(self):
        # test9's AR-CONC writes the identical termination note in all three
        # legends; repetition across towers must not read as ambiguity.
        rows = [_row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +400MM."),
                _row(50000, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +400MM.")]
        regions = [swatch for swatch, _text in rows]
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})
        self.assertEqual(proposal["notes"], [])

    def test_the_same_legend_drawn_three_times_is_not_ambiguity(self):
        # test14 is three plans of ONE building, its legend block repeated at
        # x = 29320, 102080 and 182170 -- so every row is read three times and
        # says the identical thing. Nine entries, three patterns, one meaning
        # each: agreement, and the depths survive to the mapping.
        rows = []
        for x in (29320, 102080, 182170):
            rows.append(_row14(x, 0, "ANSI37",
                               "INDICATES SLAB/BEAM SUNK BY 75MM."))
            rows.append(_row14(x, 698, "ANGLE",
                               "INDICATES SLAB/BEAM SUNK BY 150MM."))
            rows.append(_row14(x, 1396, "HONEY",
                               "INDICATES SLAB/BEAM SUNK BY 50MM."))
        regions = [swatch for swatch, _text in rows]
        for pattern in ("ANSI37", "ANGLE", "HONEY"):
            regions.append(_Region(20000, 20000, 21000, 20800, pattern, "HAT"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        self.assertEqual(len(entries), 9)
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"], {"HAT": layers.CATEGORY_SUNK})
        self.assertEqual(proposal["notes"], [])
        steps, notes = legend.legend_steps(entries)
        self.assertEqual(steps, {"ANSI37": -75.0, "ANGLE": -150.0,
                                 "HONEY": -50.0})
        self.assertEqual(notes, [])


class ProposalTranslation(unittest.TestCase):
    """Per-LAYER proposals: that is what the dialog maps, so every plan hatch
    of the pattern must sit on one layer or nothing is proposed."""

    def _one_row(self, meaning, pattern="ZIGZAG"):
        swatch, text = _row(0, 0, pattern, meaning)
        return [swatch], [text]

    def test_a_step_proposes_fold_on_the_one_plan_layer(self):
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +50MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, texts)
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})
        self.assertIn("PI_HATCH", proposal["rows"])
        self.assertIn("T.O.S. +50MM", proposal["rows"]["PI_HATCH"])

    def test_a_negative_step_still_proposes_fold(self):
        # The drawing cannot prove which sign means fold-up (every test9
        # value is "+", and a plan cannot say the parent's own level), so the
        # sign changes nothing here -- the open question lives in findings.md
        # rather than in a silent guess.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. -300MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})

    def test_a_named_direction_proposes_sunk_not_fold(self):
        # "SUNK BY 75MM." says which way, where "T.O.S. +50MM." only says
        # where. The naming convention already sends a layer called "sunk" to
        # CATEGORY_SUNK; a legend using the same word must not disagree.
        swatch, text = _row14(0, 0, "ANSI37",
                              "INDICATES SLAB/BEAM SUNK BY 75MM.")
        regions = [swatch, _Region(20000, 20000, 21000, 20800, "ANSI37",
                                   "HAT")]
        proposal = legend.propose(legend.read(regions, [text]), regions)
        self.assertEqual(proposal["mapping"], {"HAT": layers.CATEGORY_SUNK})
        self.assertIn("SUNK BY 75MM", proposal["rows"]["HAT"])

    def test_three_depths_on_one_layer_agree_on_the_category(self):
        # test14's HAT is claimed by ANSI37 (-75), ANGLE (-150) and HONEY
        # (-50). A per-layer proposal carries only the category, and all three
        # say sunk, so the layer is proposed once. The DEPTHS stay per
        # pattern, which is what legend_steps is for.
        rows = [_row14(0, 0, "ANSI37", "INDICATES SLAB/BEAM SUNK BY 75MM."),
                _row14(0, 698, "ANGLE", "INDICATES SLAB/BEAM SUNK BY 150MM."),
                _row14(0, 1396, "HONEY", "INDICATES SLAB/BEAM SUNK BY 50MM.")]
        regions = [swatch for swatch, _text in rows]
        for index, pattern in enumerate(("ANSI37", "ANGLE", "HONEY")):
            regions.append(_Region(20000 + index * 2000, 20000,
                                   21000 + index * 2000, 20800, pattern,
                                   "HAT"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"], {"HAT": layers.CATEGORY_SUNK})
        self.assertEqual(proposal["notes"], [])

    def test_a_report_only_pattern_on_a_proposed_layer_is_named(self):
        # HAT carries GOST_GLASS's 72 "SLAB AT BEAM BOTTOM" hatches as well as
        # the sunk ones, and a per-layer proposal cannot separate them: the
        # only alternative to routing all of them is routing none, which loses
        # the sunk bays. So the coarseness is said out loud, in the dialog the
        # proposal lands in, rather than hidden.
        rows = [_row14(0, 0, "ANSI37", "INDICATES SLAB/BEAM SUNK BY 75MM."),
                _row14(0, 698, "GOST_GLASS", "INDICATES SLAB AT BEAM BOTTOM")]
        regions = [swatch for swatch, _text in rows]
        regions.append(_Region(20000, 20000, 21000, 20800, "ANSI37", "HAT"))
        regions.append(_Region(24000, 20000, 25000, 20800, "GOST_GLASS",
                               "HAT"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"], {"HAT": layers.CATEGORY_SUNK})
        self.assertEqual(len(proposal["notes"]), 1)
        self.assertIn("GOST_GLASS", proposal["notes"][0])
        self.assertIn("SLAB AT BEAM BOTTOM", proposal["notes"][0])

    def test_a_swatch_on_the_wrong_layer_is_not_a_plan_layer(self):
        # test14's TRIANG row is drawn wrong: its three swatches sit on
        # RC PARDI 75MM while its twelve plan hatches sit on RC PARDI 200MM.
        # A swatch is a demonstration, not an occurrence, so only the plan
        # layer counts -- otherwise the row would read as a two-layer refusal
        # over a drafting slip inside the legend block. (TRIANG is a parapet
        # and therefore report-only either way; the pattern that matters is
        # the rule, which the sunk rows depend on.)
        swatch, text = _row14(0, 0, "TRIANG", "INDICATES SLAB/BEAM SUNK BY "
                              "75MM.", layer="RC PARDI 75MM")
        regions = [swatch, _Region(20000, 20000, 21000, 20800, "TRIANG",
                                   "RC PARDI 200MM")]
        proposal = legend.propose(legend.read(regions, [text]), regions)
        self.assertEqual(proposal["mapping"],
                         {"RC PARDI 200MM": layers.CATEGORY_SUNK})

    def test_a_cutout_proposes_the_cutout_category(self):
        regions, texts = self._one_row("HATCH INDICATE CUTOUT FOR DOOR ABOVE",
                                       pattern="ASPHALT")
        regions[0].layer = "PI_SHEAR WALL CUTOUT"
        regions.append(_Region(20000, 20000, 20900, 20400, "ASPHALT",
                               "PI_SHEAR WALL CUTOUT"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_SHEAR WALL CUTOUT": layers.CATEGORY_CUTOUT})

    def test_two_plan_layers_refuse_the_pattern(self):
        # test9's AR-CONC is the live case: 26 plan hatches on PI_COLUMN
        # HATCH and 8 on PI_RETAINING WALL HATCH -- a per-layer proposal
        # cannot carry one pattern to two layers, so it says so instead.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +50MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        regions.append(_Region(30000, 20000, 31000, 20800, "ZIGZAG",
                               "PI_OTHER"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertTrue(any("2 layers" in note for note in proposal["notes"]))

    def test_a_pattern_nobody_uses_proposes_nothing(self):
        # test9's STARS and ANSI37 exist only as their own swatches.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +400MM.",
                                       pattern="STARS")
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertTrue(any("no plan hatch" in note
                            for note in proposal["notes"]))

    def test_report_only_meanings_never_touch_the_mapping(self):
        regions, texts = self._one_row("HATCH INDICATE STUB SHEAR WALL.",
                                       pattern="ANSI37")
        regions.append(_Region(20000, 20000, 21000, 20800, "ANSI37",
                               "PI_COLUMN HATCH"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertEqual(proposal["reports"],
                         ["pattern ANSI37 notes 'HATCH INDICATE STUB SHEAR "
                          "WALL.' (report only)"])


class StoreyValuesAreRefused(unittest.TestCase):
    """+6250 is the next floor, not a step. The SAME threshold fold_plan
    applies (config's max_step_mm, the dialog's own knob) refuses it wherever
    legend depths flow."""

    def _entries(self, *meanings):
        rows = [_row(index * 50000, 0, "ZIGZAG", meaning)
                for index, meaning in enumerate(meanings)]
        return legend.read([swatch for swatch, _t in rows],
                           [text for _s, text in rows])

    def test_a_step_inside_the_limit_flows(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE T.O.S. +400MM."))
        self.assertEqual(steps, {"ZIGZAG": 400.0})
        self.assertEqual(notes, [])

    def test_6250_is_a_storey_and_says_so(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE TOS. +6250."))
        self.assertEqual(steps, {})
        self.assertEqual(len(notes), 1)
        self.assertIn("6250", notes[0])
        self.assertIn("storey", notes[0])

    def test_the_dialog_knob_is_the_limit(self):
        # Same knob as fold_plan.plan_steps: the default is config's
        # max_step_mm, and an explicit value replaces it.
        self.assertEqual(config.DEFAULTS["max_step_mm"], 3000.0)
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE TOS. +6250."), max_step_mm=7000.0)
        self.assertEqual(steps, {"ZIGZAG": 6250.0})
        self.assertEqual(notes, [])

    def test_an_ambiguous_pattern_never_reaches_the_threshold(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE T.O.S. +50MM.",
                          "HATCH INDICATE TOS. +6250."))
        self.assertEqual(steps, {})
        self.assertEqual(len(notes), 1)
        self.assertIn("no proposal", notes[0])


_FIXTURES = {}


def _read_fixture(path):
    """One fixture DXF, scaled to internal feet the way the pipeline hands it
    to the legend, cached across the classes that read it."""
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


class _FixtureLegend(unittest.TestCase):
    _path = None

    def setUp(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf` "
                          "(the bundled lib/py3 copy is a Windows build)")

    def _read(self):
        return _read_fixture(self._path)


class TheTest9Legend(_FixtureLegend):
    """The fixture itself, end to end -- the numbers the sweep pins forever."""

    _path = _TEST9

    def test_fourteen_rows_across_three_tower_legends(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        self.assertEqual(len(entries), 14)
        by_pattern = {}
        for entry in entries:
            by_pattern[entry["pattern"]] = by_pattern.get(entry["pattern"],
                                                          0) + 1
        self.assertEqual(by_pattern,
                         {"SOLID": 3, "AR-CONC": 3, "ZIGZAG": 3, "STARS": 2,
                          "ANSI32": 1, "ANSI37": 1, "ASPHALT": 1})

    def test_one_proposal_survives_the_whole_sheet(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        proposal = legend.propose(entries, result.regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_SHEAR WALL CUTOUT": layers.CATEGORY_CUTOUT})
        # The proposal seeds the HATCH mapping -- hatches map on their own
        # table -- whose convention already agrees (the cutout token is safe
        # there: routing a hatch layer never moves linework). The GEOMETRY
        # convention still reads "shear" and says structural wall, and the
        # proposal never touches it, so the wall linework stays a wall.
        self.assertEqual(layers.classify_hatch_layer("PI_SHEAR WALL CUTOUT"),
                         layers.CATEGORY_CUTOUT)
        self.assertEqual(layers.classify_layer("PI_SHEAR WALL CUTOUT"),
                         layers.CATEGORY_STRUCT_WALL)
        # Three towers, three legends: ZIGZAG, STARS and SOLID all mean
        # different things per tower, and all three are refused by name.
        refused = " ".join(proposal["notes"])
        for pattern in ("ZIGZAG", "STARS", "SOLID"):
            self.assertIn(pattern, refused)
        self.assertEqual(len(proposal["reports"]), 3)

    def test_no_step_depth_leaves_the_ambiguous_sheet(self):
        # ZIGZAG carries +50 in one tower and +6250 in another; a whole-sheet
        # read must hand the step machinery NOTHING rather than either.
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        steps, _notes = legend.legend_steps(entries)
        self.assertEqual(steps, {})

    def test_the_camber_sentence_is_still_refused_on_the_real_sheet(self):
        # 15 texts on this drawing match the verb; 14 are rows. The one left
        # out is the beam camber note, and it is left out by the geometry --
        # the wording rule that used to exclude it is gone, because it made
        # test14's whole legend unreadable.
        result = self._read()
        matched = [text for text in result.texts
                   if legend._LEGEND_TEXT.search(getattr(text, "text", None)
                                                 or "")]
        self.assertEqual(len(matched), 15)
        entries = legend.read(result.regions, result.texts)
        self.assertEqual(len(entries), 14)
        self.assertEqual([e for e in entries if "CAMBER" in e["meaning"]], [])


class TheTest14Legend(_FixtureLegend):
    """The drawing the "HATCH INDICATE" rule was blind to: eight rows, drawn
    three times, none of them read until the swatch took over from the verb."""

    _path = _TEST14

    def test_eight_rows_read_three_times_each(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        self.assertEqual(len(entries), 24)
        by_pattern = {}
        for entry in entries:
            by_pattern[entry["pattern"]] = by_pattern.get(entry["pattern"],
                                                          0) + 1
        self.assertEqual(by_pattern,
                         {"ANSI37": 3, "ANGLE": 3, "HONEY": 3,
                          "GOST_GLASS": 3, "AR-HBONE": 3, "EARTH": 3,
                          "TRIANG": 3, "SOLID": 3})
        meanings = sorted(set(entry["meaning"] for entry in entries))
        self.assertEqual(meanings, [
            "INDICATES 100MM THK. RC PARDI",
            "INDICATES 150MM THK. RC PARDI",
            "INDICATES 200MM THK. RC PARDI",
            "INDICATES FLOATING COLUMN STARTS FROM 1ST HABITABLE LEVEL.",
            "INDICATES SLAB AT BEAM BOTTOM",
            "INDICATES SLAB/BEAM SUNK BY 150MM.",
            "INDICATES SLAB/BEAM SUNK BY 50MM.",
            "INDICATES SLAB/BEAM SUNK BY 75MM.",
        ])
        # Every text is 751 mm from its own 1050x500 swatch -- one geometry,
        # eight rows, three plans.
        for entry in entries:
            self.assertIn("751 mm from a 1050x500", entry["evidence"])

    def test_the_sunk_rows_reach_the_step_machinery(self):
        # The bug the owner reported: these three depths never left the
        # drawing. All three are inside the storey threshold, so all three
        # come through with the direction the legend states.
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        steps, notes = legend.legend_steps(entries)
        self.assertEqual(steps, {"ANSI37": -75.0, "ANGLE": -150.0,
                                 "HONEY": -50.0})
        self.assertEqual(notes, [])

    def test_one_proposal_survives_and_the_rest_are_reported(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        proposal = legend.propose(entries, result.regions)
        # HAT holds all 273 sunk plan hatches (ANSI37 60, ANGLE 195, HONEY
        # 18) and nothing else that proposes, so one layer is routed.
        self.assertEqual(proposal["mapping"], {"HAT": layers.CATEGORY_SUNK})
        # Nothing in the drawing's own names says so -- the convention reads
        # "HAT" as no category at all, which is exactly why the legend has to.
        self.assertNotEqual(layers.classify_hatch_layer("HAT"),
                            layers.CATEGORY_SUNK)
        # Repetition across the three plans is agreement, so no pattern is
        # refused as ambiguous; the only note is the one naming what else
        # rides on HAT.
        self.assertEqual(len(proposal["notes"]), 1)
        self.assertIn("GOST_GLASS", proposal["notes"][0])
        # The five meanings this codebase has no pass for: three parapet
        # thicknesses, the beam-bottom slab, and the floating column.
        self.assertEqual(len(proposal["reports"]), 5)
        reported = " ".join(proposal["reports"])
        for pattern in ("AR-HBONE", "EARTH", "TRIANG", "GOST_GLASS", "SOLID"):
            self.assertIn(pattern, reported)

    def test_the_parapet_rows_never_become_a_step(self):
        # "150MM THK. RC PARDI" carries the same number as "SUNK BY 150MM."
        # and must stay report-only: 132 AR-HBONE hatches on RC PARDI 150MM,
        # 48 EARTH on RC PARDI 100MM, 12 TRIANG on RC PARDI 200MM, none of
        # them routed anywhere.
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        parapets = [e for e in entries if "RC PARDI" in e["meaning"]]
        self.assertEqual(len(parapets), 9)
        self.assertEqual(set(e["kind"] for e in parapets), {"other"})
        proposal = legend.propose(entries, result.regions)
        for layer in ("RC PARDI 100MM", "RC PARDI 150MM", "RC PARDI 200MM",
                      "RC PARDI 75MM"):
            self.assertNotIn(layer, proposal["mapping"])

    def test_the_200mm_swatch_sits_on_the_wrong_layer_and_is_ignored(self):
        # The drafting slip the one-layer rule has to survive: TRIANG's three
        # swatches are on RC PARDI 75MM (which carries nothing else at all)
        # while its twelve plan hatches are on RC PARDI 200MM.
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        triang = [e for e in entries if e["pattern"] == "TRIANG"]
        self.assertEqual(set(e["layer"] for e in triang), {"RC PARDI 75MM"})
        swatch_ids = set(id(e["swatch"]) for e in entries)
        plan = {}
        for region in result.regions:
            if region.pattern == "TRIANG" and id(region) not in swatch_ids:
                plan[region.layer_key] = plan.get(region.layer_key, 0) + 1
        self.assertEqual(plan, {"RC PARDI 200MM": 12})


if __name__ == "__main__":
    unittest.main()
