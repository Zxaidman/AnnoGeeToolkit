# -*- coding: utf-8 -*-
"""The SLAB schedule: a Mark|Thk table, read apart from the Mark|W|L one.

test16 is the drawing the owner reported. It writes, on G-ANNO-SCHD:

    Mark | Thk        Mark | Thk
    S1   | 125        F1   | 500
    S2   | 150        F2   | 550
    S3   | 175        F3   | 600
    S4   | 200        RF1  | 1200
    S5   | 225        RF2  | 1200
    S6   | 250

and 201 slab labels using those marks (S1 x34, S2 x90, S3 x46, S4 x26, S5 x3,
S6 x2). Until `thk` was a header word, `parse_schedule` returned 220 rows and
every one of them was a BEAM mark: the slab table failed the header test twice
over -- the word was unknown, and the gate demanded two dimension columns or a
Size column, which a Mark|Thk table has no way to satisfy. So no bay was ever
sized from the schedule, and the floor kept its default type while carrying the
right Mark, which is exactly what the owner photographed.

Measured before choosing the vocabulary: "THK" appears in test16 alone, twice,
and those two cells ARE these headers. A bare "T" is deliberately not a header
word -- it appears in test4, test5 and test9 meaning something else.
"""

import os
import unittest

import _loader

marks = _loader.load("classify.marks")
dxf_reader = _loader.load("readers.dxf_reader")

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST16 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test16.dxf")


class _Cell(object):
    """A schedule cell where the reader looks for one: text plus a point."""

    def __init__(self, text, x, y):
        self.text = text
        self.point = (x, y, 0.0)
        self.point_internal = (x, y, 0.0)
        self.layer = "G-ANNO-SCHD"
        self.layer_key = "g-anno-schd"


def _table(rows, x0=0.0, y0=0.0, dx=10.0, dy=-5.0, header=("Mark", "Thk")):
    """A Mark|Thk table as separate TEXT cells, the way DXF stores one."""
    cells = [_Cell(header[0], x0, y0), _Cell(header[1], x0 + dx, y0)]
    for index, (mark, value) in enumerate(rows, start=1):
        y = y0 + dy * index
        cells.append(_Cell(mark, x0, y))
        cells.append(_Cell(value, x0 + dx, y))
    return cells


class TheSlabScheduleIsRead(unittest.TestCase):
    def test_a_mark_thk_table_resolves_every_row(self):
        cells = _table([("S1", "125"), ("S2", "150"), ("S3", "175")])
        self.assertEqual(marks.parse_thickness_schedule(cells),
                         {"S1": 125.0, "S2": 150.0, "S3": 175.0})

    def test_the_header_word_may_be_spelled_out_or_punctuated(self):
        for word in ("Thk", "THK.", "Thick", "THICKNESS", "thk"):
            found = marks.parse_thickness_schedule(
                _table([("S1", "125")], header=("Mark", word)))
            self.assertEqual(found, {"S1": 125.0},
                             "%r did not read as a thickness header" % word)

    def test_a_bare_T_is_not_a_thickness_header(self):
        # Measured: "T" appears in test4, test5 and test9 meaning something
        # else. Reading it here would invent thicknesses in three drawings.
        self.assertEqual(
            marks.parse_thickness_schedule(
                _table([("S1", "125")], header=("Mark", "T"))), {})

    def test_a_cell_may_carry_its_unit(self):
        cells = _table([("S1", "125 THK."), ("S2", "150mm")])
        self.assertEqual(marks.parse_thickness_schedule(cells),
                         {"S1": 125.0, "S2": 150.0})

    def test_a_section_schedule_contributes_no_thickness(self):
        # a Mark|W|L table passes through the thickness reader untouched, which
        # is what keeps the two readings independent
        cells = [_Cell("Mark", 0, 0), _Cell("W", 10, 0), _Cell("L", 20, 0),
                 _Cell("B1", 0, -5), _Cell("230", 10, -5), _Cell("450", 20, -5)]
        self.assertEqual(marks.parse_thickness_schedule(cells), {})

    def test_a_row_with_no_number_is_skipped_not_guessed(self):
        cells = _table([("S1", "125"), ("S2", "-"), ("S3", "175")])
        self.assertEqual(marks.parse_thickness_schedule(cells),
                         {"S1": 125.0, "S3": 175.0})


class TheFixtureItself(unittest.TestCase):
    """The owner's own drawing, end to end."""

    def setUp(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf`")
        self.texts = dxf_reader.read_dxf(_TEST16).texts

    def test_test16s_slab_and_foundation_schedules_both_read(self):
        self.assertEqual(marks.parse_thickness_schedule(self.texts), {
            "S1": 125.0, "S2": 150.0, "S3": 175.0,
            "S4": 200.0, "S5": 225.0, "S6": 250.0,
            "F1": 500.0, "F2": 550.0, "F3": 600.0,
            "RF1": 1200.0, "RF2": 1200.0,
        })

    def test_the_beam_schedule_beside_it_is_unharmed(self):
        # 220 sections, every one a beam mark: reading the slab table must not
        # cost the table it sits next to
        sections = marks.parse_schedule(self.texts)
        self.assertEqual(len(sections), 220)
        self.assertEqual(sections["B1"], (230.0, 450.0))
        self.assertNotIn("S1", sections)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TheFoundationSchedule(unittest.TestCase):
    """The F/RF block beside the slab one, sizing a ring that carries only a mark.

    test16 draws it in the same Mark|Thk shape -- F1 500, F2 550, F3 600,
    RF1 1200, RF2 1200 -- and `plan_foundations` reads it exactly as the slab
    pass reads S1..S6: LAST, so a note written on the ring itself keeps its own
    figure. A schedule is the sheet's general statement; a note on the outline
    is the specific one, and the specific wins.
    """

    def setUp(self):
        self.plan = _loader.load("foundation_plan")

    def _one(self, label, schedule=None):
        record = _FndRecord("polyline",
                            [(0, 0), (4000, 0), (4000, 3000), (0, 3000), (0, 0)])
        note = _FndText(label, (2000, 1500))
        return self.plan.plan_foundations([record], [note], schedule=schedule)

    def test_a_mark_only_ring_takes_its_thickness_from_the_schedule(self):
        found = self._one("F2", schedule={"F2": 550.0})
        self.assertEqual([(p["mark"], p["thickness_mm"]) for p in found],
                         [("F2", 550.0)])

    def test_a_note_on_the_ring_beats_the_schedule(self):
        found = self._one("F2_800MM THK", schedule={"F2": 550.0})
        self.assertEqual([p["thickness_mm"] for p in found], [800.0])

    def test_no_schedule_leaves_it_exactly_as_before(self):
        self.assertEqual([p["thickness_mm"] for p in self._one("F2")], [None])


_FT = 1.0 / 304.8


class _FndRecord(object):
    """A foundation-layer outline in internal feet, closed as test10 draws one."""

    def __init__(self, kind, corners_mm):
        self.kind = kind
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in corners_mm]
        self.layer = "S-FND"
        self.layer_key = "s-fnd"
        self.category = "foundation"


class _FndText(object):
    def __init__(self, text, point_mm):
        self.text = text
        self.point_internal = (point_mm[0] * _FT, point_mm[1] * _FT, 0.0)
