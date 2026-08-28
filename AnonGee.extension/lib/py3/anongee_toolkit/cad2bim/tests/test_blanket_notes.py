# -*- coding: utf-8 -*-
"""The sheet's blanket note ("ALL BEAMS ARE 750MM IN DEPTH U.N.O.").

A note like that is the drawing telling us the DEFAULT size for every member it
did not size individually. The rule it states in its own words -- "unless noted
otherwise" -- is the whole contract: a member that carries a size keeps it, and
only a member with none takes the sheet's figure.

Every string pinned below was MEASURED out of a fixture DXF with the package's
own reader, misspellings and double spaces included. They are quoted verbatim on
purpose: the parser has to cope with the drawings as drawn, and a test that
tidied the strings up would stop proving that.

    test14  NOTE - 1) ALL BEAMS ARE 750MM IN DEPTH U.N.O.
            2) ALL SALB ARE 125MM  U.N.O.
    test12  NOTE:-1) ALL BEAMS 650 DEEP U.N.O.
            NOTE:-1) ALL BEAMS 600 DEEP U.N.O.
            2) ALL INVETED BEAM FOR ELEVATION JALI ARE 800 DEEP.
    test9   * ALL BEAM SIZE SHALL BE 240x600 (U.N.O.)
            * ALL BKT SIZE SHALL BE 240x450 (U.N.O.)
            * ALL SLAB THICKNESS SHALL BE 150MM THK. (U.N.O.)
            *ALL SLAB SHALL BE 175MM THICK (UNLESS MENTIONED)

Standalone (no Revit / no ezdxf): the parser and both planners are Revit-free.
"""

import unittest

import _loader

_MM = 304.8
_FT = 1.0 / _MM

marks, report, slab_outlines = _loader.load("classify.marks", "report",
                                            "slab_outlines")

# ---- the four drawings' own strings, quoted exactly as the reader returns them
T14_BEAM = "NOTE - 1) ALL BEAMS ARE 750MM IN DEPTH U.N.O."
T14_SLAB = "2) ALL SALB ARE 125MM  U.N.O."
T12_BEAM_650 = "NOTE:-1) ALL BEAMS 650 DEEP U.N.O."
T12_BEAM_600 = "NOTE:-1) ALL BEAMS 600 DEEP U.N.O."
T12_INVERTED = "2) ALL INVETED BEAM FOR ELEVATION JALI ARE 800 DEEP."
T9_BEAM = "* ALL BEAM SIZE SHALL BE 240x600 (U.N.O.)"
T9_BRACKET = "* ALL BKT SIZE SHALL BE 240x450 (U.N.O.)"
T9_SLAB_150 = "* ALL SLAB THICKNESS SHALL BE 150MM THK. (U.N.O.)"
T9_SLAB_175 = "*ALL SLAB SHALL BE 175MM THICK (UNLESS MENTIONED)"


class _Note(object):
    """A sheet note, carrying exactly what marks.parse_texts stamps on a text.

    Placed far off the plan, where a general-notes block actually sits, so the
    blanket reading is the ONLY route by which it can reach a member. A note
    that sized a beam by sheer proximity would make these tests pass for the
    wrong reason -- and "ALL BEAM SIZE SHALL BE 240x600" really does parse as a
    240x600 label, so this is not a hypothetical.
    """
    def __init__(self, text, x_mm=500000.0, y_mm=500000.0):
        self.text = text
        self.layer_key = "TEXT"
        self.point = (x_mm, y_mm, 0.0)
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)
        marks.parse_texts([self])


class _Rec(object):
    """Minimal beam CurveRecord stand-in (build_beam_segments reads these only)."""
    def __init__(self, points_mm, kind="polyline"):
        self.kind = kind
        self.category = "beam"
        self.layer = "S-BEAM"
        self.points = [(x * _FT, y * _FT, 0.0) for (x, y) in points_mm]


class _Lbl(object):
    """A sized beam label: the thing a blanket note must never talk over."""
    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark = mark
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.text = "{0} {1:g}x{2:g}".format(mark, b_mm, h_mm)
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


class _SlabNote(object):
    def __init__(self, text, x_mm, y_mm):
        self.text = text
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _beam(points_mm):
    return _Rec(points_mm)


def _one_beam():
    """A 4000 x 300 beam outline -> one centreline, midpoint (2000, 150)."""
    return [_beam([(0, 0), (4000, 0), (4000, 300), (0, 300)])]


def _one_loop():
    ring = [(0.0, 0.0), (5000 * _FT, 0.0), (5000 * _FT, 5000 * _FT),
            (0.0, 5000 * _FT)]
    return [(ring, 0.0)]


class TheDrawingsOwnWords(unittest.TestCase):
    """Each clause, exactly as its sheet writes it."""

    def test_test14_beams(self):
        self.assertEqual(marks.parse_blanket_note(T14_BEAM),
                         {"beam_depth_mm": 750.0})

    def test_test14_slabs_despite_the_misspelling(self):
        # the sheet writes SALB, and the parser reads the drawing as drawn
        self.assertEqual(marks.parse_blanket_note(T14_SLAB),
                         {"slab_thickness_mm": 125.0})

    def test_the_two_clauses_arrive_as_separate_records(self):
        # test14 writes its note as TWO text records: the second does not
        # repeat the word NOTE, and nothing here needs them joined
        found = marks.sheet_defaults([_Note(T14_BEAM), _Note(T14_SLAB)])
        self.assertEqual(found["beam_depth_mm"], 750.0)
        self.assertEqual(found["slab_thickness_mm"], 125.0)
        self.assertEqual(found["conflicts"], [])

    def test_the_word_note_is_never_required(self):
        self.assertEqual(marks.parse_blanket_note(T14_SLAB),
                         {"slab_thickness_mm": 125.0})

    def test_test12_writes_deep_instead_of_in_depth(self):
        self.assertEqual(marks.parse_blanket_note(T12_BEAM_650),
                         {"beam_depth_mm": 650.0})
        self.assertEqual(marks.parse_blanket_note(T12_BEAM_600),
                         {"beam_depth_mm": 600.0})

    def test_test9_writes_a_whole_section_and_only_the_depth_is_taken(self):
        # "240x600" -- the width is DROPPED on purpose: a plan measures a
        # beam's width off its two drawn edges, so a blanket width would
        # overwrite a measurement with an assumption
        self.assertEqual(marks.parse_blanket_note(T9_BEAM),
                         {"beam_depth_mm": 600.0})

    def test_test9_slab_notes_both_parse(self):
        self.assertEqual(marks.parse_blanket_note(T9_SLAB_150),
                         {"slab_thickness_mm": 150.0})
        self.assertEqual(marks.parse_blanket_note(T9_SLAB_175),
                         {"slab_thickness_mm": 175.0})

    def test_the_clause_number_is_never_read_as_the_size(self):
        # "1)" and "2)" open both of test14's clauses; the figure is read from
        # what follows the SUBJECT, so the numbering cannot be mistaken for it
        for clause, expected in ((T14_BEAM, 750.0), (T12_BEAM_650, 650.0)):
            self.assertEqual(marks.parse_blanket_note(clause)["beam_depth_mm"],
                             expected)
        self.assertEqual(
            marks.parse_blanket_note(T14_SLAB)["slab_thickness_mm"], 125.0)


class WhatIsNotABlanketNote(unittest.TestCase):
    """The clauses that look like one and must not be read as one."""

    def test_a_qualified_subject_names_a_subset_not_the_sheet(self):
        # test12: "ALL INVETED BEAM FOR ELEVATION JALI" is a handful of beams
        # around one facade, not every beam on the drawing
        self.assertEqual(marks.parse_blanket_note(T12_INVERTED), {})

    def test_brackets_are_not_beams(self):
        # test9 carries a BKT note in the same list, in the same wording
        self.assertEqual(marks.parse_blanket_note(T9_BRACKET), {})

    def test_a_clause_with_no_unless_marker_sets_no_default(self):
        # without "unless noted otherwise" the clause states a fact about what
        # was drawn; it does not license filling in what was not
        self.assertEqual(marks.parse_blanket_note("ALL BEAMS ARE 750MM DEEP"),
                         {})

    def test_an_ordinary_member_label_is_not_a_note(self):
        for label in ("B1 300x600", "S1 150 THK", "C1 400x400", "", None):
            self.assertEqual(marks.parse_blanket_note(label), {})

    def test_a_figure_outside_the_structural_band_is_refused(self):
        # 8 is not a depth and 45000 is a storey, not a member
        self.assertEqual(marks.parse_blanket_note("ALL BEAMS 8 DEEP U.N.O."),
                         {})
        self.assertEqual(
            marks.parse_blanket_note("ALL SLABS 45000 THICK U.N.O."), {})


class SpellingsOfUnlessNotedOtherwise(unittest.TestCase):
    """The marker is written four ways across the corpus."""

    def test_the_variants_all_read(self):
        for clause in ("ALL BEAMS ARE 750MM IN DEPTH U.N.O.",
                       "ALL BEAMS ARE 750MM IN DEPTH U.N.O",
                       "ALL BEAMS ARE 750MM IN DEPTH UNO",
                       "ALL BEAMS ARE 750MM IN DEPTH (U.N.O.)",
                       "ALL BEAMS 750 MM DEEP UNLESS NOTED OTHERWISE",
                       "all beams 750 mm deep unless mentioned"):
            self.assertEqual(marks.parse_blanket_note(clause),
                             {"beam_depth_mm": 750.0}, clause)

    def test_mm_may_be_joined_or_spaced_or_absent(self):
        for clause, expected in (
                ("ALL BEAMS ARE 750MM IN DEPTH U.N.O.", 750.0),
                ("ALL BEAMS ARE 750 MM IN DEPTH U.N.O.", 750.0),
                ("ALL BEAMS 650 DEEP U.N.O.", 650.0)):
            self.assertEqual(
                marks.parse_blanket_note(clause)["beam_depth_mm"], expected)

    def test_a_word_merely_starting_with_uno_is_not_the_marker(self):
        self.assertEqual(
            marks.parse_blanket_note("ALL BEAMS 750 DEEP UNOCCUPIED BAYS"), {})


class ConflictingNotesAreRefused(unittest.TestCase):
    """Two notes disagreeing is refused out loud, never averaged or voted on.

    test12 is the case, and it is not a close call: twelve of its fifteen note
    blocks say 650 DEEP and three say 600 DEEP. Nothing in the text says which
    beam belongs to which note, so a majority vote would put a wrong depth on
    hundreds of members and say nothing about it.
    """

    def test_test12s_two_beam_notes_settle_nothing(self):
        found = marks.sheet_defaults(
            [_Note(T12_BEAM_650)] * 12 + [_Note(T12_BEAM_600)] * 3)
        self.assertIsNone(found["beam_depth_mm"])
        self.assertEqual(found["conflicts"],
                         [("beam_depth_mm", [600.0, 650.0])])

    def test_the_majority_does_not_win(self):
        found = marks.sheet_defaults(
            [_Note(T12_BEAM_650)] * 99 + [_Note(T12_BEAM_600)])
        self.assertIsNone(found["beam_depth_mm"])

    def test_test9s_two_slab_notes_settle_nothing_but_its_beams_still_do(self):
        # one kind disagreeing must not take the other kind down with it
        found = marks.sheet_defaults([_Note(T9_BEAM), _Note(T9_BRACKET),
                                      _Note(T9_SLAB_150), _Note(T9_SLAB_175)])
        self.assertEqual(found["beam_depth_mm"], 600.0)
        self.assertIsNone(found["slab_thickness_mm"])
        self.assertEqual(found["conflicts"],
                         [("slab_thickness_mm", [150.0, 175.0])])

    def test_the_same_figure_repeated_is_not_a_conflict(self):
        # every fixture repeats its note once per plan on the sheet
        found = marks.sheet_defaults([_Note(T14_BEAM)] * 3
                                     + [_Note(T14_SLAB)] * 3)
        self.assertEqual(found["beam_depth_mm"], 750.0)
        self.assertEqual(found["slab_thickness_mm"], 125.0)
        self.assertEqual(found["conflicts"], [])

    def test_a_sheet_with_no_notes_settles_nothing_and_complains_of_nothing(self):
        for texts in ([], None, [_Note("B1 300x600"), _Note("GRID A")]):
            found = marks.sheet_defaults(texts)
            self.assertIsNone(found["beam_depth_mm"])
            self.assertIsNone(found["slab_thickness_mm"])
            self.assertEqual(found["conflicts"], [])


class TheBeamsTakeItOnlyWhereNothingElseSpoke(unittest.TestCase):

    def test_an_unlabelled_beam_takes_the_sheets_depth(self):
        out = report.build_beam_segments(_one_beam(), None, None, None,
                                         texts=[_Note(T14_BEAM)])
        self.assertEqual(len(out["segments"]), 1)
        self.assertEqual(out["segments"][0]["depth_mm"], 750.0)
        self.assertEqual(out["status_counts"].get("blanket_depth"), 1)
        self.assertEqual(out["blanket_depth_mm"], 750.0)

    def test_a_labelled_beam_keeps_its_own_depth(self):
        # THE rule: "unless noted otherwise" -- the label is the noting
        label = _Lbl("B1", 300.0, 600.0, 2000, 150)
        out = report.build_beam_segments(_one_beam(), None, None, None,
                                         texts=[label, _Note(T14_BEAM)])
        self.assertEqual(out["segments"][0]["mark"], "B1")
        self.assertAlmostEqual(out["segments"][0]["depth_mm"], 600.0, delta=1.0)
        self.assertNotIn("blanket_depth", out["status_counts"])

    def test_the_width_is_never_touched_by_the_note(self):
        # the drawing MEASURES the width; only the depth is missing from a plan
        out = report.build_beam_segments(_one_beam(), None, None, None,
                                         texts=[_Note(T9_BEAM)])
        self.assertAlmostEqual(out["segments"][0]["width_mm"], 300.0, delta=1.0)
        self.assertEqual(out["segments"][0]["depth_mm"], 600.0)

    def test_a_typed_figure_overrules_the_sheet(self):
        out = report.build_beam_segments(_one_beam(), None, None, None,
                                         texts=[_Note(T14_BEAM)],
                                         blanket_depth_mm=800.0)
        self.assertEqual(out["segments"][0]["depth_mm"], 800.0)

    def test_zero_turns_the_whole_thing_off(self):
        out = report.build_beam_segments(_one_beam(), None, None, None,
                                         texts=[_Note(T14_BEAM)],
                                         blanket_depth_mm=0)
        self.assertIsNone(out["segments"][0].get("depth_mm"))
        self.assertEqual(out["blanket_depth_mm"], 0.0)

    def test_conflicting_notes_leave_every_beam_unsized(self):
        out = report.build_beam_segments(
            _one_beam(), None, None, None,
            texts=[_Note(T12_BEAM_650), _Note(T12_BEAM_600)])
        self.assertIsNone(out["segments"][0].get("depth_mm"))
        self.assertNotIn("blanket_depth", out["status_counts"])

    def test_a_drawing_with_no_note_is_completely_unaffected(self):
        plain = report.build_beam_segments(_one_beam(), None, None, None,
                                           texts=[])
        self.assertIsNone(plain["segments"][0].get("depth_mm"))
        self.assertEqual(plain["blanket_depth_mm"], 0.0)
        self.assertNotIn("blanket_depth", plain["status_counts"])


class TheSlabsTakeItOnlyWhereNothingElseSpoke(unittest.TestCase):

    def test_an_unnoted_bay_takes_the_sheets_thickness(self):
        slabs = slab_outlines.apply_slab_labels(_one_loop(),
                                                [_Note(T14_SLAB)])
        self.assertEqual(slabs[0]["thickness_mm"], 125.0)
        self.assertTrue(slabs[0]["blanket"])

    def test_a_noted_bay_keeps_its_own_thickness(self):
        slabs = slab_outlines.apply_slab_labels(
            _one_loop(),
            [_SlabNote("S1 150 THK", 2500, 2500), _Note(T14_SLAB)])
        self.assertEqual(slabs[0]["mark"], "S1")
        self.assertEqual(slabs[0]["thickness_mm"], 150.0)
        self.assertFalse(slabs[0]["blanket"])

    def test_a_schedule_sized_bay_keeps_its_schedule_thickness(self):
        slabs = slab_outlines.apply_slab_labels(
            _one_loop(), [_SlabNote("S3", 2500, 2500), _Note(T14_SLAB)],
            schedule={"S3": 200.0})
        self.assertEqual(slabs[0]["thickness_mm"], 200.0)
        self.assertFalse(slabs[0]["blanket"])

    def test_a_typed_figure_overrules_the_sheet(self):
        slabs = slab_outlines.apply_slab_labels(
            _one_loop(), [_Note(T14_SLAB)], blanket_thickness_mm=180.0)
        self.assertEqual(slabs[0]["thickness_mm"], 180.0)
        self.assertTrue(slabs[0]["blanket"])

    def test_zero_turns_the_whole_thing_off(self):
        slabs = slab_outlines.apply_slab_labels(
            _one_loop(), [_Note(T14_SLAB)], blanket_thickness_mm=0)
        self.assertIsNone(slabs[0]["thickness_mm"])
        self.assertFalse(slabs[0]["blanket"])

    def test_conflicting_notes_leave_every_bay_unsized(self):
        slabs = slab_outlines.apply_slab_labels(
            _one_loop(), [_Note(T9_SLAB_150), _Note(T9_SLAB_175)])
        self.assertIsNone(slabs[0]["thickness_mm"])
        self.assertFalse(slabs[0]["blanket"])

    def test_a_drawing_with_no_note_is_completely_unaffected(self):
        slabs = slab_outlines.apply_slab_labels(_one_loop(), [])
        self.assertIsNone(slabs[0]["thickness_mm"])
        self.assertIsNone(slabs[0]["mark"])
        self.assertFalse(slabs[0]["blanket"])


class TheDialogsThreeStatesAreOneFunction(unittest.TestCase):
    """`blanket_mm` is what turns three dialog controls into one number.

    The dialog cannot send None -- an empty box reads as 0 -- so the mapping
    from (tick, box) to the planners' tri-state lives in one place that both
    the beam and the slab pass call.
    """

    def setUp(self):
        self.run_builders = None

    def _blanket_mm(self):
        # run_builders imports Revit at module level, so read the function out
        # of its source and exec just that -- the same trick the dialog-wiring
        # pins use to reach code no offline harness can import.
        import ast
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(os.path.dirname(here), "run_builders.py")
        with open(path, "rb") as handle:
            tree = ast.parse(handle.read().decode("utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "blanket_mm":
                namespace = {}
                exec(compile(ast.Module([node], []), path, "exec"), namespace)
                return namespace["blanket_mm"]
        self.fail("run_builders has no blanket_mm")

    def test_the_tick_off_is_zero_whatever_the_boxes_say(self):
        blanket_mm = self._blanket_mm()
        selections = {"blanket_notes": False,
                      "blanket_beam_depth_mm": 750.0,
                      "blanket_slab_thickness_mm": 125.0}
        self.assertEqual(blanket_mm(selections, "blanket_beam_depth_mm"), 0.0)
        self.assertEqual(blanket_mm(selections, "blanket_slab_thickness_mm"),
                         0.0)

    def test_a_filled_box_is_the_figure(self):
        blanket_mm = self._blanket_mm()
        selections = {"blanket_notes": True, "blanket_beam_depth_mm": 750.0}
        self.assertEqual(blanket_mm(selections, "blanket_beam_depth_mm"), 750.0)

    def test_an_empty_box_hands_the_question_back_to_the_sheet(self):
        # which is what keeps a REFUSED conflict refused: the dialog seeds
        # nothing, and the planner reads the sheet and refuses it again
        blanket_mm = self._blanket_mm()
        for selections in ({"blanket_notes": True, "blanket_beam_depth_mm": 0.0},
                           {"blanket_notes": True}, {}, None):
            self.assertIsNone(blanket_mm(selections, "blanket_beam_depth_mm"))


if __name__ == "__main__":
    unittest.main()
