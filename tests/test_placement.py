# -*- coding: utf-8 -*-
"""Where a column and a footing go, checked off Revit.

``rc_automation.placement`` imports nothing from Revit, so every rule that
decides whether an element is created, matched, modified or refused can be
argued with here — before anybody presses a button at a live model.

The rule the file turns on is the project owner's, and it is not the obvious
one: **a mark is a label, not a key.** ``C1`` at A1 is ``C1`` all the way up the
building even where the column reduces, and two columns on one floor share a
mark when their size and cage agree. So matching on the mark would find the
wrong column, or ninety of them. What identifies a column is where it stands and
which storey it is in.

Which makes the second-run test the one that matters. Anything can create.
"""

import importlib.util
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLE = os.path.join(_ROOT, "bridge", "excel", "build_sample_project.py")

if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
from anongee_toolkit.rc_automation import models                 # noqa: E402
from anongee_toolkit.rc_automation import placement              # noqa: E402


#: A grid that behaves like the sample's: A-E and 1-3, at 6 m, in millimetres.
_GRID_X = {"A": 0.0, "B": 6000.0, "C": 12000.0, "D": 18000.0, "E": 24000.0}
_GRID_Y = {"1": 0.0, "2": 6000.0, "3": 12000.0}


def _cross(name_x, name_y):
    if name_x not in _GRID_X or name_y not in _GRID_Y:
        return None, "no grid named {0!r} or {1!r}".format(name_x, name_y)
    return (_GRID_X[name_x], _GRID_Y[name_y]), ""


def _sample():
    spec = importlib.util.spec_from_file_location("build_sample_project",
                                                  _SAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _grid(headers, rows):
    return [list(headers)] + [list(row) for row in rows]


def _errors(issues):
    return [issue for issue in issues
            if issue.severity == models.SEVERITY_ERROR]


class ReadingTests(unittest.TestCase):
    """The sheet the sample writes is the sheet the reader reads.

    Two files describing the same table is two files that can drift, and the
    drift is silent — a header the reader does not recognise is a column that
    quietly becomes ``None``.
    """

    def setUp(self):
        self.sample = _sample()

    def test_every_column_row_is_read_whole(self):
        rows, issues = placement.parse_columns(
            _grid(self.sample.COLUMN_PLACEMENT_HEADERS,
                  self.sample.column_rows()), units="mm")
        self.assertEqual(_errors(issues), [])
        self.assertEqual(len(rows), len(self.sample.column_rows()))
        first = rows[0]
        self.assertEqual(first.mark, "C1")
        self.assertEqual((first.grid_x, first.grid_y), ("A", "1"))
        self.assertEqual(first.storey, "S1")
        self.assertEqual(first.base_level, self.sample.LEVELS[0][0])
        self.assertEqual(first.top_level, self.sample.LEVELS[1][0])
        self.assertEqual(first.type_mark, "C-300x600")
        self.assertEqual(first.rebar, "CS-1")

    def test_base_offset_is_not_swallowed_by_base_level(self):
        # Both headers start with the word Base. Longest-first ordering is what
        # keeps them apart, and it is the kind of thing that works until
        # somebody adds a field in the wrong place.
        rows, _issues = placement.parse_columns(
            _grid(self.sample.COLUMN_PLACEMENT_HEADERS,
                  self.sample.column_rows()), units="mm")
        self.assertEqual(rows[0].base_offset_mm, 0.0)
        self.assertEqual(rows[0].base_level, self.sample.LEVELS[0][0])

    def test_every_footing_row_is_read_whole(self):
        rows, issues = placement.parse_footings(
            _grid(self.sample.FOOTING_PLACEMENT_HEADERS,
                  self.sample.footing_rows()), units="mm")
        self.assertEqual(_errors(issues), [])
        self.assertEqual(len(rows), len(self.sample.footing_rows()))
        self.assertEqual(rows[0].type_mark, "F3")
        self.assertEqual(rows[0].level, self.sample.LEVELS[0][0])
        self.assertEqual(rows[0].outline, "")

    def test_a_metre_sheet_is_read_as_millimetres(self):
        headers = ["Mark", "TypeMark", "GridX", "GridY", "OffsetX (m)",
                   "OffsetY (m)", "Level", "TopOffset (m)"]
        rows, _issues = placement.parse_footings(
            [headers, ["F-A1", "F1", "A", "1", 0.15, -0.075, "FDN", -0.05]],
            units="mm")
        self.assertAlmostEqual(rows[0].offset_x_mm, 150.0)
        self.assertAlmostEqual(rows[0].offset_y_mm, -75.0)
        self.assertAlmostEqual(rows[0].top_offset_mm, -50.0)

    def test_a_blank_row_is_skipped_rather_than_failed(self):
        headers = list(self.sample.FOOTING_PLACEMENT_HEADERS)
        rows, issues = placement.parse_footings(
            [headers, [""] * len(headers),
             ["F-A1", "F1", "A", "1", None, None, "FDN", 0, 0, "", ""]])
        self.assertEqual(len(rows), 1)
        self.assertEqual(_errors(issues), [])

    def test_a_sheet_with_no_header_says_so(self):
        rows, issues = placement.parse_columns([["nothing", "useful"]])
        self.assertEqual(rows, [])
        self.assertEqual(len(_errors(issues)), 1)

    def test_the_types_sheet_gives_each_mark_a_size(self):
        sizes, _issues = placement.parse_types(
            _grid(self.sample.FOOTING_TYPE_HEADERS,
                  self.sample.typed_rows(self.sample.FOOTING_TYPES,
                                         self.sample.FOOTING_TYPE_LENGTHS,
                                         self.sample.FOOTING_TYPE_HEADERS)),
            units="mm")
        self.assertEqual(sorted(sizes), ["f1", "f2", "f3"])
        self.assertAlmostEqual(sizes["f1"]["length_mm"], 2400.0)
        self.assertAlmostEqual(sizes["f3"]["thickness_mm"], 450.0)


class LocatingTests(unittest.TestCase):
    """The grid is asked first, and the offset is added to what it says."""

    def row(self, **fields):
        fields.setdefault("mark", "C1")
        return placement.PlacementRow(row=2, **fields)

    def test_a_named_intersection_becomes_a_point(self):
        row = self.row(grid_x="B", grid_y="2")
        self.assertEqual(placement.locate([row], _cross), [])
        self.assertEqual(row.point_mm, (6000.0, 6000.0))

    def test_an_offset_is_measured_from_the_intersection(self):
        # Not from the origin. This is the whole reason the column is called
        # OffsetX: a column 150 off the grid stays 150 off it when the grid
        # moves.
        row = self.row(grid_x="B", grid_y="2", offset_x_mm=150.0,
                       offset_y_mm=-75.0)
        placement.locate([row], _cross)
        self.assertEqual(row.point_mm, (6150.0, 5925.0))

    def test_a_grid_the_model_does_not_have_is_refused(self):
        row = self.row(grid_x="Z", grid_y="9")
        issues = placement.locate([row], _cross)
        self.assertEqual(len(_errors(issues)), 1)
        self.assertIsNone(row.point_mm)

    def test_no_grid_falls_back_to_coordinates_and_says_so(self):
        # The fallback exists for a model with no grids in it yet. It is
        # reported because it is unusual enough to be worth seeing in a run
        # that otherwise reads as ordinary.
        row = self.row(offset_x_mm=1000.0, offset_y_mm=2000.0)
        issues = placement.locate([row], _cross)
        self.assertEqual(row.point_mm, (1000.0, 2000.0))
        self.assertEqual([issue.severity for issue in issues],
                         [models.SEVERITY_INFO])

    def test_no_grid_and_no_coordinates_is_nowhere(self):
        row = self.row()
        self.assertEqual(len(_errors(placement.locate([row], _cross))), 1)
        self.assertIsNone(row.point_mm)


class PlanningTests(unittest.TestCase):
    """What a run decides, and what it refuses to decide."""

    def row(self, **fields):
        fields.setdefault("mark", "C1")
        fields.setdefault("type_mark", "C-300x600")
        fields.setdefault("base_level", "01 GROUND LVL.")
        row = placement.PlacementRow(row=fields.pop("row", 2), **fields)
        placement.locate([row], _cross)
        return row

    def test_an_empty_model_is_all_creates(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1")]
        plans, _issues = placement.plan(rows, [])
        self.assertEqual(plans[0].action, placement.CREATE)

    def test_something_already_standing_there_is_matched(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1")]
        existing = [("id-1", (0.0, 0.0), "01 GROUND LVL.", "C-300x600")]
        plans, _issues = placement.plan(rows, existing)
        self.assertEqual(plans[0].action, placement.MATCH)
        self.assertEqual(plans[0].existing, "id-1")

    def test_a_column_a_storey_up_is_a_different_column(self):
        # Same x and y, different base level. If the level were not part of the
        # match, the second storey would be reported as already built.
        rows = [self.row(grid_x="A", grid_y="1", storey="S2",
                         base_level="02 FIRST FLOOR LVL.")]
        existing = [("id-1", (0.0, 0.0), "01 GROUND LVL.", "C-300x600")]
        plans, _issues = placement.plan(rows, existing)
        self.assertEqual(plans[0].action, placement.CREATE)

    def test_the_wrong_section_is_a_modify(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1")]
        existing = [("id-1", (0.0, 0.0), "01 GROUND LVL.", "C-300x450")]
        plans, _issues = placement.plan(rows, existing)
        self.assertEqual(plans[0].action, placement.MODIFY)
        self.assertIn("C-300x450", plans[0].reason)

    def test_a_revit_type_name_containing_the_sheets_is_the_same_type(self):
        # Revit holds "AnonGee Rect Column : C-300x600" where the sheet says
        # "C-300x600". Demanding equality would report every element in the
        # model as needing a change, on every run, for ever.
        rows = [self.row(grid_x="A", grid_y="1", storey="S1")]
        existing = [("id-1", (0.0, 0.0), "01 GROUND LVL.",
                     "AnonGee Rect Column : C-300x600")]
        plans, _issues = placement.plan(rows, existing)
        self.assertEqual(plans[0].action, placement.MATCH)

    def test_a_column_nowhere_near_is_not_this_column(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1")]
        existing = [("id-1", (900.0, 0.0), "01 GROUND LVL.", "C-300x600")]
        plans, issues = placement.plan(rows, existing)
        self.assertEqual(plans[0].action, placement.CREATE)
        self.assertTrue([issue for issue in issues
                         if "does not mention" in issue.message])

    def test_what_the_sheet_does_not_mention_is_reported_never_deleted(self):
        plans, issues = placement.plan(
            [], [("id-9", (0.0, 0.0), "01 GROUND LVL.", "C-300x600")])
        self.assertEqual(plans, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, models.SEVERITY_INFO)
        self.assertIn("Nothing is ever deleted", issues[0].message)

    def test_two_rows_in_the_same_place_is_a_typo_and_is_refused(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1", row=2),
                self.row(grid_x="A", grid_y="1", storey="S1", mark="C9",
                         row=3)]
        plans, issues = placement.plan(rows, [])
        self.assertEqual(plans[1].action, placement.INVALID)
        self.assertEqual(len(_errors(issues)), 1)

    def test_a_row_with_no_type_is_refused(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1", type_mark="")]
        plans, issues = placement.plan(rows, [])
        self.assertEqual(plans[0].action, placement.INVALID)
        self.assertEqual(len(_errors(issues)), 1)

    def test_a_row_with_no_level_is_refused(self):
        rows = [self.row(grid_x="A", grid_y="1", storey="S1", base_level="")]
        plans, issues = placement.plan(rows, [])
        self.assertEqual(plans[0].action, placement.INVALID)
        self.assertEqual(len(_errors(issues)), 1)

    def test_a_row_that_could_not_be_located_never_gets_built(self):
        # The join between locating and planning. It is the only thing standing
        # between an unknown grid and a column at the project origin.
        rows = [self.row(grid_x="Z", grid_y="9", storey="S1")]
        plans, _issues = placement.plan(rows, [])
        self.assertEqual(plans[0].action, placement.INVALID)
        self.assertFalse(plans[0].will_write)

    def test_two_marks_the_same_is_not_an_error(self):
        # The owner's rule: C1 repeats across a floor and up a stack. A
        # duplicate-mark check would reject a correct sheet.
        rows = [self.row(grid_x="A", grid_y="1", storey="S1", row=2),
                self.row(grid_x="E", grid_y="3", storey="S1", row=3)]
        plans, issues = placement.plan(rows, [])
        self.assertEqual([plan.action for plan in plans],
                         [placement.CREATE, placement.CREATE])
        self.assertEqual(_errors(issues), [])


class IdempotenceTests(unittest.TestCase):
    """The acceptance test. Anything can create.

    A run against the sample workbook, then the same run against the model it
    just made. The second must report every element matched and nothing else —
    ninety columns and fifteen footings, no creates, no modifies, no errors.
    """

    def setUp(self):
        self.sample = _sample()

    def rows(self, kind):
        if kind == "columns":
            rows, _issues = placement.parse_columns(
                _grid(self.sample.COLUMN_PLACEMENT_HEADERS,
                      self.sample.column_rows()), units="mm")
        else:
            rows, _issues = placement.parse_footings(
                _grid(self.sample.FOOTING_PLACEMENT_HEADERS,
                      self.sample.footing_rows()), units="mm")
        placement.locate(rows, _cross)
        return rows

    def model_from(self, plans, span):
        """What Revit would hold after those plans were written."""
        return [(index, plan.row.point_mm,
                 plan.row.base_level if span else plan.row.level,
                 plan.row.type_mark)
                for index, plan in enumerate(plans)
                if plan.action == placement.CREATE]

    def check(self, kind, span, expected):
        rows = self.rows(kind)
        first, issues = placement.plan(rows, [], span=span)
        self.assertEqual(_errors(issues), [])
        self.assertEqual(placement.summarise(first)["created"], expected)

        second, issues = placement.plan(rows, self.model_from(first, span),
                                        span=span)
        counts = placement.summarise(second)
        self.assertEqual(counts["matched"], expected)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(counts["modified"], 0)
        self.assertEqual(_errors(issues), [])

    def test_ninety_columns_once_then_matched(self):
        self.check("columns", True, 90)

    def test_fifteen_footings_once_then_matched(self):
        self.check("footings", False, 15)

    def test_a_third_run_is_the_same_as_the_second(self):
        # Two runs can agree by accident — the second could be matching on
        # something the first left behind. A third proves it settled.
        rows = self.rows("columns")
        first, _issues = placement.plan(rows, [], span=True)
        model = self.model_from(first, True)
        for _round in range(2):
            plans, issues = placement.plan(rows, model, span=True)
            self.assertEqual(placement.summarise(plans)["matched"], 90)
            self.assertEqual(_errors(issues), [])


class CommandContractTests(unittest.TestCase):
    """What the two new commands promise, checked without importing Revit.

    They cannot be imported here — they reach for ``Autodesk.Revit.DB`` — so
    what is checked is the source: that the dry run is the default, that the
    write goes through one transaction group, and that neither of them deletes.
    """

    def source(self, name):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", name)
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_nothing_is_written_unless_the_job_says_so(self):
        body = self.source("_placement.py")
        self.assertIn('option(envelope, "dryRun", True)', body)

    def test_one_undo_step(self):
        body = self.source("_placement.py")
        self.assertIn("TransactionGroup", body)
        self.assertIn("group.Assimilate()", body)
        self.assertIn("group.RollBack()", body)

    def test_a_failed_write_is_rolled_back_whole(self):
        # Half a floor of columns is worse than none, because none is obvious.
        body = self.source("_placement.py")
        self.assertIn("transaction.RollBack()", body)

    def test_neither_command_deletes_anything(self):
        for name in ("columns.py", "footings.py", "_placement.py"):
            body = self.source(name)
            self.assertNotIn(".Delete(", body, name)
            self.assertNotIn("doc.Delete", body, name)

    def test_the_grids_are_read_once_rather_than_per_row(self):
        # Ninety rows on the column sheet, one grid table. Asking Revit per row
        # is the same answer ninety times.
        body = self.source("_placement.py")
        self.assertIn("def _intersection(doc)", body)
        self.assertEqual(body.count("grid_module.grids(doc)"), 1)


class TypeCreationTests(unittest.TestCase):
    """A missing type is made, not refused — and the boundary of that.

    The first real run placed nothing: fifteen footings and ninety columns each
    reported *no type called `F1`* and stopped. Correct, and useless. So a type
    the model does not have is now duplicated from a loaded family and sized
    from the TYPES sheet.

    **Creating a type is not authoring a family**, and the distinction is the
    whole reason this is safe. Duplicating a loaded family's type gives a
    section with the right materials, the right subcategories and the right
    behaviour; generating a family from a spreadsheet would give none of those
    and is not on the table. A model with nothing to duplicate is reported.
    """

    def source(self, package, name):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", package, name)
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_a_column_type_is_duplicated_from_a_loaded_family(self):
        body = self.source("structural", "columns.py")
        self.assertIn("def ensure_symbol(", body)
        self.assertIn("base.Duplicate(wanted)", body)

    def test_a_footing_type_is_duplicated_too(self):
        body = self.source("structural", "footings.py")
        self.assertIn("def ensure_named_type(", body)
        self.assertIn("base.Duplicate(wanted)", body)

    def test_neither_tries_to_author_a_family(self):
        # NewFamilyDocument would be the line that turned this from "make a
        # type" into "invent a section", which is the boundary being kept.
        for package, name in (("structural", "columns.py"),
                              ("structural", "footings.py")):
            body = self.source(package, name)
            self.assertNotIn("NewFamilyDocument", body, name)
            self.assertNotIn("LoadFamily", body, name)

    def test_a_model_with_nothing_to_duplicate_is_reported(self):
        body = self.source("structural", "columns.py")
        self.assertIn("no structural column family loaded", body)
        self.assertIn("Concrete-Rectangular-Column", body)

    def test_the_new_type_takes_its_size_from_the_types_sheet(self):
        for package, name, sheet in (("commands", "columns.py",
                                      "COLUMN_TYPES"),
                                     ("commands", "footings.py",
                                      "FOOTING_TYPES")):
            body = self.source(package, name)
            self.assertIn('TYPES_SHEET = "{0}"'.format(sheet), body, name)
            self.assertIn("def _sizes(context", body, name)

    def test_a_type_that_cannot_be_sized_says_so_rather_than_lying(self):
        # A family whose dimensions are not called b/h gets a type of the
        # right name and the wrong size. That has to be reported, because a
        # 300x600 column that is silently 400x400 is worse than none.
        body = self.source("structural", "columns.py")
        self.assertIn("could not set its", body)

    def test_the_sample_gives_every_type_a_size_to_be_made_from(self):
        sample = _sample()
        sizes, _issues = placement.parse_types(
            _grid(sample.COLUMN_TYPE_HEADERS,
                  sample.typed_rows(sample.COLUMN_TYPES,
                                    sample.COLUMN_TYPE_LENGTHS,
                                    sample.COLUMN_TYPE_HEADERS)), units="mm")
        placed, _issues = placement.parse_columns(
            _grid(sample.COLUMN_PLACEMENT_HEADERS, sample.column_rows()),
            units="mm")
        for row in placed:
            key = "".join(c for c in row.type_mark.lower() if c.isalnum())
            self.assertIn(key, sizes, row.type_mark)
            self.assertTrue(sizes[key]["width_mm"], row.type_mark)
            self.assertTrue(sizes[key]["depth_mm"], row.type_mark)

    def test_depth_and_thickness_are_not_the_same_column(self):
        # A column is Width x Depth; a pad is Length x Width x Thickness. A
        # reader that folded them together would size a column off a slab.
        sizes, _issues = placement.parse_types(
            [["TypeMark", "Width (mm)", "Depth (mm)", "Thickness (mm)"],
             ["X1", 300, 600, 150]], units="mm")
        self.assertEqual(sizes["x1"]["width_mm"], 300.0)
        self.assertEqual(sizes["x1"]["depth_mm"], 600.0)
        self.assertEqual(sizes["x1"]["thickness_mm"], 150.0)


class UniqueMarkTests(unittest.TestCase):
    """Revit's ``Mark`` and the schedule's mark are two different things.

    Revit expects ``Mark`` to be unique per instance and warns when it is not.
    The owner's schedule label repeats on purpose — ``C1`` is ``C1`` up a whole
    stack and across a floor — so writing the label there produced *Elements
    have duplicate "Mark" values* on the first real run. The label was right;
    the parameter was wrong.
    """

    def row(self, **fields):
        fields.setdefault("mark", "C1")
        return placement.PlacementRow(row=2, **fields)

    def test_the_key_carries_the_label_the_grid_and_the_storey(self):
        row = self.row(grid_x="A", grid_y="1", storey="S1")
        self.assertEqual(row.unique_mark, "C1-A1-S1")

    def test_a_footing_has_no_storey_and_says_so_by_omission(self):
        row = self.row(mark="F-A1", grid_x="A", grid_y="1")
        self.assertEqual(row.unique_mark, "F-A1-A1")

    def test_every_column_in_the_sample_gets_a_different_one(self):
        # The property that matters. Ninety rows, ninety marks, no warning.
        sample = _sample()
        rows, _issues = placement.parse_columns(
            _grid(sample.COLUMN_PLACEMENT_HEADERS, sample.column_rows()),
            units="mm")
        marks = [row.unique_mark for row in rows]
        self.assertEqual(len(marks), 90)
        self.assertEqual(len(set(marks)), 90)

    def test_the_schedule_label_still_repeats_as_it_should(self):
        # The other half: if the labels had become unique too, the owner's
        # marking rule would have been quietly thrown away to silence a
        # warning.
        sample = _sample()
        rows, _issues = placement.parse_columns(
            _grid(sample.COLUMN_PLACEMENT_HEADERS, sample.column_rows()),
            units="mm")
        labels = set(row.mark for row in rows)
        self.assertEqual(sorted(labels), ["C1", "C2", "C3"])

    def test_the_label_is_readable_inside_the_key(self):
        # So somebody looking at a column in Revit can still see it is a C1.
        row = self.row(grid_x="B", grid_y="2", storey="S4")
        self.assertTrue(row.unique_mark.startswith("C1"))

    def test_the_command_writes_the_key_and_not_the_label(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "columns.py")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("_mark(instance, row.unique_mark)", body)
        self.assertNotIn("_mark(instance, row.mark)", body)

    def test_the_label_goes_where_the_workbook_says(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "columns.py")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn('LABEL_KEY = "SCHEDULE_MARK_PARAM"', body)
        self.assertIn("def _label_parameter(context)", body)

    def test_a_missing_label_parameter_is_reported_once_not_ninety_times(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "columns.py")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("reported", body)
        self.assertIn('reported.add("unset")', body)


if __name__ == "__main__":
    unittest.main()
