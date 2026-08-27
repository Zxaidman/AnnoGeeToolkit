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

import ast
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
        """Read as a call graph, not as text.

        This test used to assert the literal string
        ``base.Duplicate(name or wanted)``, and moving that line into the
        shared ``typemaker`` — which is exactly the fix BUG-31 called for —
        broke it while the behaviour it names was still true. That is the
        fifth time a check here has matched prose instead of code. So: parse
        it, and assert that ``ensure_symbol`` reaches a duplicate call by
        *some* route.
        """
        for package, name in (("structural", "columns.py"),
                              ("structural", "framing.py")):
            tree = ast.parse(self.source(package, name))
            function = self._function(tree, "ensure_symbol")
            self.assertIsNotNone(function, name)
            called = self._calls(function)
            self.assertTrue(
                any("duplicate" in call.lower() for call in called),
                "{0}: ensure_symbol never duplicates anything".format(name))

    def test_a_type_that_cannot_be_made_carries_revit_s_own_words(self):
        """The whole of BUG-31 in one assertion.

        A hundred and ten beams failed inside ``Duplicate`` and every one of
        them was reported as *no framing type called 'B-230x600'* — the type
        being looked for, never the exception explaining why it could not be
        made. The cause then had to be found by elimination from a spreadsheet
        four days later. Whatever else ``typemaker.duplicate`` does, it must
        put the caught exception into the sentence it returns.
        """
        tree = ast.parse(self.source("structural", "typemaker.py"))
        function = self._function(tree, "duplicate")
        self.assertIsNotNone(function)

        handlers = [node for node in ast.walk(function)
                    if isinstance(node, ast.ExceptHandler)]
        self.assertTrue(handlers, "duplicate() catches nothing")
        for handler in handlers:
            self.assertIsNotNone(
                handler.name,
                "duplicate() catches an exception without binding it, so it "
                "cannot report what Revit said")
            bound = handler.name
            used = any(isinstance(node, ast.Name) and node.id == bound
                       for node in ast.walk(handler))
            self.assertTrue(used, "the caught exception is never reported")

    def _function(self, tree, name):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def _calls(self, function):
        found = []
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if isinstance(target, ast.Attribute):
                found.append(target.attr)
            elif isinstance(target, ast.Name):
                found.append(target.id)
        return found

    def test_a_new_type_is_named_by_the_house_pattern(self):
        """The workbook's TypeMark is what a row *asks for*; the NAMING sheet
        decides what a type is *called* when one has to be made.

        Otherwise a model fills up with names in the workbook's dialect —
        ``C-300x600`` beside the template's own ``300 X 600``, describing the
        same section twice.
        """
        for name, key in (("columns.py", "column"), ("beams.py", "beam")):
            path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                                "anongee_toolkit", "commands", name)
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            self.assertIn('_sheets.type_name(patterns, "{0}"'.format(key),
                          body, name)
            self.assertIn("_sheets.naming(context", body, name)

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

    def marks(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "_marks.py")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_the_key_goes_in_revits_mark_and_the_label_does_not(self):
        body = self.marks()
        self.assertIn("_set_builtin_mark(instance, row.unique_mark)", body)
        self.assertNotIn("_set_builtin_mark(instance, row.mark)", body)

    def test_the_label_goes_where_the_workbook_says(self):
        body = self.marks()
        self.assertIn('LABEL_KEY = "SCHEDULE_MARK_PARAM"', body)
        self.assertIn("def candidates(context)", body)

    def test_a_missing_label_parameter_is_reported_once_not_ninety_times(self):
        body = self.marks()
        self.assertIn('reported.add("unset")', body)
        self.assertIn('reported.add("fell-back")', body)

    def test_every_command_that_places_something_writes_both_marks(self):
        """One rule, four sheets.

        This lived in ``columns.py`` for one release, which meant footings
        wrote Revit's ``Mark`` and nothing else — and the owner found it, in a
        model, after a run. A rule with one home cannot be half-applied.
        """
        for name in ("columns.py", "footings.py", "beams.py", "slabs.py"):
            path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                                "anongee_toolkit", "commands", name)
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            self.assertIn("_marks.write(", body, name)
            self.assertIn("_marks.candidates(context)", body, name)


class BeamGroupParsingTests(unittest.TestCase):
    """Continuity is the layout, and the parser is the only thing that reads it.

    A blank row is what says where one beam ends and the next begins. Every
    other parser here skips blank rows because they mean somebody pressed
    Enter; this one must not, because here they carry the whole meaning.
    """

    def setUp(self):
        self.sample = _sample()
        self.groups, self.issues = placement.parse_beams(
            _grid(self.sample.BEAM_PLACEMENT_HEADERS,
                  self.sample.beam_rows()), units="mm")

    def test_the_groups_come_back_as_groups(self):
        self.assertEqual(len(self.groups), len(self.sample.beam_groups()))
        self.assertEqual(sum(len(group) for group in self.groups), 132)
        self.assertEqual(_errors(self.issues), [])

    def test_a_group_is_one_beam_and_shares_one_mark(self):
        for group in self.groups:
            marks = set(row.mark for row in group)
            self.assertEqual(len(marks), 1, sorted(marks))

    def test_both_kinds_survive_the_round_trip(self):
        sizes = set(len(group) for group in self.groups)
        self.assertIn(1, sizes)
        self.assertTrue(any(size > 1 for size in sizes))

    def test_a_row_knows_both_its_ends(self):
        row = self.groups[0][0]
        self.assertTrue(row.from_grid_x)
        self.assertTrue(row.to_grid_x)
        self.assertTrue(row.level)
        self.assertTrue(row.type_mark)

    def test_a_doubled_blank_row_does_not_make_an_empty_beam(self):
        headers = list(self.sample.BEAM_PLACEMENT_HEADERS)
        blank = [""] * len(headers)
        row = list(self.sample.beam_rows()[0])
        groups, _issues = placement.parse_beams(
            [headers, row, blank, blank, row], units="mm")
        self.assertEqual([len(group) for group in groups], [1, 1])

    def test_a_trailing_blank_row_does_not_make_one_either(self):
        headers = list(self.sample.BEAM_PLACEMENT_HEADERS)
        row = list(self.sample.beam_rows()[0])
        groups, _issues = placement.parse_beams(
            [headers, row, [""] * len(headers)], units="mm")
        self.assertEqual([len(group) for group in groups], [1])


class SpanPlanningTests(unittest.TestCase):
    """A beam and a slab panel are both identified by two grid intersections."""

    def setUp(self):
        self.sample = _sample()

    def beams(self):
        groups, _issues = placement.parse_beams(
            _grid(self.sample.BEAM_PLACEMENT_HEADERS,
                  self.sample.beam_rows()), units="mm")
        rows = [row for group in groups for row in group]
        placement.locate_span(rows, _cross)
        return rows

    def slabs(self):
        rows, _issues = placement.parse_slabs(
            _grid(self.sample.SLAB_PLACEMENT_HEADERS,
                  self.sample.slab_rows()), units="mm")
        placement.locate_span(rows, _cross)
        return rows

    def test_every_beam_finds_both_ends(self):
        rows = self.beams()
        for row in rows:
            self.assertIsNotNone(row.start_mm, row.mark)
            self.assertIsNotNone(row.end_mm, row.mark)

    def test_the_midpoint_is_what_gets_matched(self):
        rows = self.beams()
        row = rows[0]
        self.assertAlmostEqual(row.point_mm[0],
                               (row.start_mm[0] + row.end_mm[0]) / 2.0)

    def test_an_unknown_grid_leaves_the_beam_unplaceable(self):
        row = placement.PlacementRow(row=2, mark="B1", type_mark="B-300x600",
                                     level="01", from_grid_x="Z",
                                     from_grid_y="9", to_grid_x="A",
                                     to_grid_y="1")
        issues = placement.locate_span([row], _cross)
        self.assertEqual(len(_errors(issues)), 1)
        self.assertIsNone(row.start_mm)
        plans, _issues = placement.plan_spans([row], [])
        self.assertEqual(plans[0].action, placement.INVALID)

    def test_132_beams_once_then_matched(self):
        rows = self.beams()
        first, issues = placement.plan_spans(rows, [])
        self.assertEqual(placement.summarise(first)["created"], 132)
        self.assertEqual(_errors(issues), [])
        model = [(index, plan.row.point_mm, plan.row.level, plan.row.type_mark)
                 for index, plan in enumerate(first)]
        second, issues = placement.plan_spans(rows, model)
        counts = placement.summarise(second)
        self.assertEqual(counts["matched"], 132)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(_errors(issues), [])

    def test_40_slabs_once_then_matched(self):
        rows = self.slabs()
        first, _issues = placement.plan_spans(rows, [])
        self.assertEqual(placement.summarise(first)["created"], 40)
        model = [(index, plan.row.point_mm, plan.row.level, plan.row.type_mark)
                 for index, plan in enumerate(first)]
        second, _issues = placement.plan_spans(rows, model)
        self.assertEqual(placement.summarise(second)["matched"], 40)

    def test_two_rows_spanning_the_same_bay_is_a_typo(self):
        rows = self.beams()
        plans, issues = placement.plan_spans(rows + [rows[0]], [])
        self.assertEqual(plans[-1].action, placement.INVALID)
        self.assertEqual(len(_errors(issues)), 1)

    def test_every_mark_is_unique_across_all_four_sheets(self):
        """Revit's ``Mark`` is one namespace for the whole model.

        A beam and a column sharing one would warn exactly as ninety columns
        sharing ``C1`` did, and it would be found the same way — in a dialog,
        after a run.
        """
        sample = self.sample
        marks = [row.unique_mark for row in self.beams()]
        marks += [row.unique_mark for row in self.slabs()]
        columns, _issues = placement.parse_columns(
            _grid(sample.COLUMN_PLACEMENT_HEADERS, sample.column_rows()),
            units="mm")
        marks += [row.unique_mark for row in columns]
        footings, _issues = placement.parse_footings(
            _grid(sample.FOOTING_PLACEMENT_HEADERS, sample.footing_rows()),
            units="mm")
        marks += [row.unique_mark for row in footings]
        self.assertEqual(len(marks), 132 + 40 + 90 + 15)
        self.assertEqual(len(marks), len(set(marks)))

    def test_the_level_is_not_repeated_in_a_mark_that_has_it(self):
        # B01-1-1-A1B1, not B01-1-1-A1B1-01. Unique either way; only one of
        # them is readable.
        rows = self.beams()
        self.assertNotIn("-01-01", rows[0].unique_mark)


class PanelTests(unittest.TestCase):
    """A slab stops at the inner face of its beams, per edge."""

    def test_a_panel_with_no_inset_is_the_bay(self):
        self.assertEqual(placement.rectangle((0.0, 0.0), (6000.0, 6000.0)),
                         [(0.0, 0.0), (6000.0, 0.0), (6000.0, 6000.0),
                          (0.0, 6000.0)])

    def test_each_edge_is_inset_on_its_own(self):
        # A 300 beam one side and a 230 plinth beam another are inset
        # differently, and averaging them puts the edge wrong on both.
        corners = placement.rectangle((0.0, 0.0), (6000.0, 6000.0),
                                      (150.0, 150.0, 115.0, 115.0))
        self.assertEqual(corners[0], (150.0, 115.0))
        self.assertEqual(corners[2], (5850.0, 5885.0))

    def test_a_panel_smaller_than_its_beams_is_refused(self):
        self.assertIsNone(placement.rectangle((0.0, 0.0), (200.0, 200.0),
                                              (150.0, 150.0, 150.0, 150.0)))

    def test_the_corners_come_back_in_order(self):
        # Anticlockwise from the low corner. A CurveLoop built from points in
        # a crossed order is a bow tie, and Revit takes it.
        corners = placement.rectangle((6000.0, 6000.0), (0.0, 0.0))
        self.assertEqual(corners,
                         [(0.0, 0.0), (6000.0, 0.0), (6000.0, 6000.0),
                          (0.0, 6000.0)])


class BeamEndTests(unittest.TestCase):
    """A grid intersection is where a **column** stands, not where a beam ends.

    A beam drawn between two of them runs through both columns: the concrete is
    counted twice at every junction and the shop drawing shows a beam that does
    not exist. Revit's automatic join then extends it further.
    """

    def framing(self):
        import importlib.util
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "structural", "framing.py")
        spec = importlib.util.spec_from_file_location("framing", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_beam_along_x_is_pulled_in_along_x(self):
        trimmed = self.framing()._trim((0.0, 0.0), (6000.0, 0.0),
                                       (150.0, 150.0))
        self.assertEqual(trimmed, ((150.0, 0.0), (5850.0, 0.0)))

    def test_a_beam_along_y_is_pulled_in_along_y(self):
        trimmed = self.framing()._trim((0.0, 0.0), (0.0, 6000.0),
                                       (300.0, 300.0))
        self.assertEqual(trimmed, ((0.0, 300.0), (0.0, 5700.0)))

    def test_the_two_ends_are_cut_back_separately(self):
        # A beam between a 300 column and a 600 one is not symmetrical.
        trimmed = self.framing()._trim((0.0, 0.0), (6000.0, 0.0),
                                       (150.0, 300.0))
        self.assertEqual(trimmed, ((150.0, 0.0), (5700.0, 0.0)))

    def test_a_diagonal_beam_is_cut_along_its_own_direction(self):
        trimmed = self.framing()._trim((0.0, 0.0), (3000.0, 4000.0),
                                       (500.0, 0.0))
        self.assertAlmostEqual(trimmed[0][0], 300.0)
        self.assertAlmostEqual(trimmed[0][1], 400.0)

    def test_a_cutback_longer_than_the_beam_is_refused(self):
        # Better a beam on the grid than a beam inside out.
        start, end = (0.0, 0.0), (200.0, 0.0)
        self.assertEqual(self.framing()._trim(start, end, (150.0, 150.0)),
                         (start, end))

    def test_the_joins_are_disallowed_at_both_ends(self):
        body = _read_source("structural", "framing.py")
        self.assertIn("DisallowJoinAtEnd(instance, end_index)", body)
        self.assertIn("for end_index in (0, 1)", body)

    def test_the_justification_is_stated_rather_than_inherited(self):
        """A real run arrived with ``z Offset Value`` of −1500.

        Nothing set it. ``NewFamilyInstance`` gives a beam whatever the family
        and the **last placement** left behind, and −1500 is the foundation
        level — a number from somewhere else entirely, carried into ninety
        beams because nothing said otherwise.
        """
        body = _read_source("structural", "framing.py")
        for parameter in ("YZ_JUSTIFICATION", "Y_JUSTIFICATION",
                          "Y_OFFSET_VALUE", "Z_JUSTIFICATION",
                          "Z_OFFSET_VALUE"):
            self.assertIn("BuiltInParameter." + parameter, body, parameter)

    def test_the_sheets_offset_drops_the_beam_not_its_section(self):
        # Two different things called offset. The level offsets move the beam;
        # the z offset moves it within its own section.
        body = _read_source("structural", "framing.py")
        self.assertIn("STRUCTURAL_BEAM_END0_ELEVATION", body)
        self.assertIn("mm_to_ft(offset_mm or 0.0)", body)

    def test_the_column_lookup_is_keyed_on_the_level_the_beam_sits_on(self):
        # A column's *top* reaches the level its beam sits on. Keying on the
        # base level would find the column a storey below.
        body = _read_source("commands", "beams.py")
        self.assertIn("_fold(row.top_level)", body)

    def test_a_row_can_ask_to_run_to_the_grid_instead(self):
        body = _read_source("commands", "beams.py")
        self.assertIn('GRID_LINE = "grid line"', body)
        self.assertIn("row.edge_rule", body)

    def test_the_sample_sheet_says_column_face(self):
        sample = _sample()
        groups, _issues = placement.parse_beams(
            _grid(sample.BEAM_PLACEMENT_HEADERS, sample.beam_rows()),
            units="mm")
        for group in groups:
            for row in group:
                self.assertEqual(row.edge_rule, "Column face")


class NamingSheetTests(unittest.TestCase):
    """Type names as patterns, in the workbook, the way cad2bim does it."""

    def naming(self):
        from anongee_toolkit.rc_automation import naming_sheet
        return naming_sheet

    def test_the_defaults_are_the_templates_own_convention(self):
        # `300 X 600`, capital X, spaces — so a workbook that ships agreeing
        # with the model it will meet creates nothing on the first run.
        naming = self.naming()
        self.assertEqual(naming.render(naming.defaults(), "column",
                                       b=300, h=600), "300 X 600")

    def test_a_pattern_from_the_sheet_wins(self):
        naming = self.naming()
        patterns, issues = naming.parse(
            [["Element", "Pattern"], ["column", "S_Col_{b}x{h}"]])
        self.assertEqual(issues, [])
        self.assertEqual(naming.render(patterns, "column", b=300, h=600),
                         "S_Col_300x600")

    def test_a_pattern_that_will_not_render_is_reported_not_obeyed(self):
        """A naming preference must never stop a run.

        Ninety columns refused because somebody typed ``{width}`` for ``{b}``
        would be the tool confusing a preference with a requirement.
        """
        naming = self.naming()
        patterns, issues = naming.parse(
            [["Element", "Pattern"], ["column", "{width} x {h}"]])
        self.assertEqual(len(issues), 1)
        self.assertIn("should not stop a run", issues[0].message)
        self.assertEqual(naming.render(patterns, "column", b=300, h=600),
                         "300 X 600")

    def test_a_key_with_an_underscore_matches_itself(self):
        """``_fold`` drops underscores, and comparing a folded cell against the
        raw keys rejected three of the seven — in the sheet this repository
        writes itself. Caught by the round-trip test below, which is what a
        round-trip test is for.
        """
        naming = self.naming()
        patterns, issues = naming.parse(
            [["Element", "Pattern"], ["column_mark", "COL-{n}"]])
        self.assertEqual([issue for issue in issues
                          if issue.severity != "Info"], [])
        self.assertEqual(naming.render(patterns, "column_mark", n=4), "COL-4")

    def test_beam_mark_takes_the_field_the_sheet_offers(self):
        """The owner wrote ``B{n}`` to match ``C{n}`` and ``F{n}``, and it was
        rejected: ``beam_mark`` declared ``{level}`` and ``{grid}`` and nothing
        else, while the sheet's own *Fields it may use* column offered ``{n}``.
        The workbook advertised a field the code refused, and the refusal was
        silent by design — a naming preference must never stop a run — so 132
        beams were placed with marks nobody asked for. BUG-34.
        """
        naming = self.naming()
        patterns, issues = naming.parse(
            [["Element", "Pattern"], ["beam_mark", "B{n}"]])
        self.assertEqual([issue for issue in issues
                          if issue.severity != "Info"], [])
        self.assertEqual(patterns["beam_mark"], "B{n}")
        self.assertEqual(naming.render(patterns, "beam_mark", n=7), "B7")

    def test_all_three_marks_take_the_same_fields(self):
        """Three separate field lists is how the last one came to disagree with
        the other two. One list, so they cannot drift again."""
        naming = self.naming()
        for key in ("column_mark", "beam_mark", "footing_mark"):
            self.assertEqual(naming.PATTERNS[key][0], naming.MARK_FIELDS, key)

    def test_every_pattern_is_read_by_something_now(self):
        """The three ``*_mark`` keys were read by no command for two releases —
        a placement sheet carried its own Mark column and that went into
        ``S_ScheduleMark``. The owner asked for the schedule mark to be
        generated instead, so all eight are wired and none is reported as
        decoration."""
        naming = self.naming()
        for key in naming.PATTERNS:
            self.assertIn(key, naming.WIRED, key)
        _patterns, issues = naming.parse(
            [["Element", "Pattern"], ["beam_mark", "BM-{n}"]])
        self.assertEqual(issues, [])

    def test_a_mark_pattern_takes_the_prefix_from_the_type(self):
        """``{prefix}`` is the letters the workbook's own TypeMark starts with,
        so a plinth beam schedules as ``PB1`` and a floor beam as ``B1``
        without the distinction being typed a second time."""
        naming = self.naming()
        self.assertIn("prefix", naming.MARK_FIELDS)
        self.assertEqual(
            naming.render(naming.defaults(), "beam_mark", prefix="PB", n=1,
                          level="", grid=""), "PB1")
        self.assertEqual(
            naming.render(naming.defaults(), "beam_mark", prefix="B", n=2,
                          level="", grid=""), "B2")

    def test_a_wired_pattern_is_not_reported(self):
        """The four that *are* read say nothing — otherwise the notice becomes
        noise and stops being read."""
        naming = self.naming()
        _patterns, issues = naming.parse(
            [["Element", "Pattern"], ["beam", "CH-{b} X {h}"]])
        self.assertEqual(issues, [])

    def test_an_unknown_element_says_what_it_does_know(self):
        naming = self.naming()
        _patterns, issues = naming.parse(
            [["Element", "Pattern"], ["girder", "{b} x {h}"]])
        self.assertEqual(len(issues), 1)
        self.assertIn("column", issues[0].message)

    def test_a_missing_sheet_is_not_an_error(self):
        naming = self.naming()
        patterns, issues = naming.parse(None)
        self.assertEqual(issues, [])
        self.assertEqual(patterns, naming.defaults())

    def test_a_whole_number_reads_as_one(self):
        # 600.0 in a type name is 600, not "600.0".
        naming = self.naming()
        self.assertEqual(naming.render(naming.defaults(), "column",
                                       b=300.0, h=600.0), "300 X 600")

    def test_the_example_is_generated_from_the_pattern(self):
        # Typed beside it, it would drift. Generated, it cannot.
        naming = self.naming()
        patterns = {"column": "S_Col_{b}x{h}"}
        self.assertEqual(naming.example(patterns, "column"), "S_Col_300x600")

    def test_a_mark_example_is_a_mark_and_not_a_size(self):
        # The first version sampled by position and gave `C300`.
        naming = self.naming()
        self.assertEqual(naming.example(naming.defaults(), "column_mark"),
                         "C1")

    def test_the_sheet_the_builder_writes_is_the_sheet_the_reader_reads(self):
        """The round trip, and the test that caught ``_fold`` eating the
        underscore out of three keys in the sheet this repository writes."""
        sample = _sample()
        naming = self.naming()
        rows = sample.naming_rows()
        patterns, issues = naming.parse(
            [list(sample.NAMING_HEADERS)] + [list(row) for row in rows])
        self.assertEqual(issues, [])
        self.assertEqual(patterns, dict(sample.HOUSE_PATTERNS))

    def test_the_workbook_ships_the_house_convention(self):
        """The module keeps the neutral default and the workbook carries the
        practice's own — which is the split the NAMING sheet exists to make.

        The module's ``{b} X {h}`` is what a stock Revit template holds, and it
        is the fallback when a pattern will not render, so it stays generic.
        ``CH-{b} X {h}`` is what this practice writes on a drawing.
        """
        sample = _sample()
        naming = self.naming()
        self.assertEqual(naming.defaults()["beam"], "{b} X {h}")
        self.assertEqual(sample.HOUSE_PATTERNS["beam"], "CH-{b} X {h}")
        for key in naming.PATTERNS:
            self.assertIn(key, sample.HOUSE_PATTERNS, key)

    def test_a_hand_edited_pattern_survives_a_rebuild(self):
        """``Pattern`` is the one column on this sheet a person owns.

        A rebuild that reset it would throw the house convention away every
        time the sample data changed — which is exactly what happened the first
        time the stair sheets were added, and the owner's ``CH-`` patterns went
        with it.
        """
        sample = _sample()
        rows = sample.naming_rows({"beam": "PRACTICE-{b}x{h}"})
        found = dict((row[0], row[1]) for row in rows)
        self.assertEqual(found["beam"], "PRACTICE-{b}x{h}")
        self.assertEqual(found["column"], sample.HOUSE_PATTERNS["column"])

    def test_a_preserved_pattern_regenerates_its_example(self):
        """Keeping the pattern and keeping the old example beside it would be
        the disagreement this sheet is meant to stop."""
        sample = _sample()
        rows = sample.naming_rows({"beam": "PRACTICE-{b}x{h}"})
        example = dict((row[0], row[2]) for row in rows)["beam"]
        self.assertEqual(example, "PRACTICE-300x600")


def _read_source(package, name):
    path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                        "anongee_toolkit", package, name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


if __name__ == "__main__":
    unittest.main()


class NamingRefreshTests(unittest.TestCase):
    """``naming.refresh`` — the cells it asks the workbook to write.

    Static, because the command opens a workbook and this cannot. What is
    checked is the part that decides whether the sheet stops disagreeing with
    itself: which columns it touches, which it does not, and that it returns
    nothing when nothing has drifted.
    """

    def module(self):
        import importlib.util
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "naming.py")
        spec = importlib.util.spec_from_file_location("_naming_cmd", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def naming(self):
        return _load_module("rc_automation", "naming_sheet")

    HEADER = ["Element", "Pattern", "Example", "Fields it may use",
              "What it names"]

    def test_the_pattern_column_is_never_written(self):
        """The one column a person owns. A refresh that rewrote it is a
        refresh nobody would press twice."""
        self.assertNotIn("Pattern", self.module().COLUMNS)

    def test_a_stale_example_is_rewritten(self):
        module = self.module()
        grid = [self.HEADER,
                ["beam", "CH-{b} X {h}", "300 X 600", "{b}, {h}", "a beam"]]
        header_at, columns = module._header(grid)
        cells, read, changed = module._cells(
            grid, header_at, columns, {"beam": "CH-{b} X {h}"})
        self.assertEqual(read, 1)
        self.assertTrue(changed)
        examples = [cell for cell in cells if cell["column"] == 3]
        self.assertEqual(examples[0]["value"], "CH-300 X 600")
        self.assertEqual(examples[0]["row"], 2)

    def test_a_sheet_that_already_agrees_asks_for_nothing(self):
        """A refresh that rewrote all sixty cells every time would put an
        unsaved-changes dot on a workbook that had not changed, and would
        report the same number for ever — which stops meaning anything the
        second time it is read."""
        naming = self.naming()
        module = self.module()
        patterns = {"beam": "CH-{b} X {h}"}
        grid = [self.HEADER,
                ["beam", "CH-{b} X {h}", naming.example(patterns, "beam"),
                 "{b}, {h}", naming.PATTERNS["beam"][2]]]
        header_at, columns = module._header(grid)
        cells, read, changed = module._cells(grid, header_at, columns,
                                             patterns)
        self.assertEqual(read, 1)
        self.assertEqual(changed, 0)
        self.assertEqual(cells, [])

    def test_the_fields_column_follows_the_code(self):
        """It is what tells a person which placeholders exist. The owner's
        edited copy of it advertised ``{n}`` for a key that refused it —
        BUG-34 — and this is the column that has to stop being hand-kept."""
        module = self.module()
        self.assertEqual(module._fields("beam"), "{b}, {h}")
        self.assertIn("{n}", module._fields("beam_mark"))

    def test_a_missing_column_is_reported_and_skipped(self):
        module = self.module()
        grid = [["Element", "Pattern"], ["beam", "CH-{b} X {h}"]]
        header_at, columns = module._header(grid)
        cells, read, _changed = module._cells(grid, header_at, columns,
                                              {"beam": "CH-{b} X {h}"})
        self.assertEqual(read, 1)
        self.assertEqual(cells, [])

    def test_an_unknown_element_row_is_left_alone(self):
        module = self.module()
        grid = [self.HEADER,
                ["girder", "{b} x {h}", "", "", ""]]
        header_at, columns = module._header(grid)
        cells, read, _changed = module._cells(grid, header_at, columns, {})
        self.assertEqual(read, 0)
        self.assertEqual(cells, [])

    def test_the_header_is_found_the_way_the_reader_finds_it(self):
        """A sheet this can refresh and a sheet that can be read have to be the
        same sheet, or the button silently does nothing to a workbook that
        works."""
        module = self.module()
        grid = [["AnonGee Bridge - naming", "", "", "", ""],
                self.HEADER,
                ["beam", "CH-{b} X {h}", "", "", ""]]
        header_at, columns = module._header(grid)
        self.assertEqual(header_at, 1)
        self.assertEqual(columns["element"], 0)
        self.assertEqual(columns["pattern"], 1)

    def test_it_writes_nothing_to_revit(self):
        """It needs no document and opens no transaction — the only command
        with an answer that belongs in a sheet."""
        import importlib.util
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", "commands", "naming.py")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for forbidden in ("Transaction", "doc.Create", "ActiveUIDocument"):
            self.assertNotIn(forbidden, body)


def _load_module(package, name):
    import importlib.util
    path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                        "anongee_toolkit", package, name + ".py")
    spec = importlib.util.spec_from_file_location("_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScheduleLabelTests(unittest.TestCase):
    """``S_ScheduleMark`` is generated, not copied off the sheet.

    The project owner's rule, 2026-08-27: a plinth beam should schedule as
    ``PB1`` and a floor beam as ``B1``, from the NAMING convention — not as
    ``B01-1-1``, which is the per-row mark the placement sheet carries so that
    a *person* can find the row again.
    """

    def marks(self):
        return _load_module("commands", "_marks")

    def naming(self):
        return _load_module("rc_automation", "naming_sheet")

    class Row(object):
        def __init__(self, type_mark):
            self.type_mark = type_mark

    def rows(self, *type_marks):
        return [ScheduleLabelTests.Row(mark) for mark in type_marks]

    def test_the_prefix_comes_from_the_type_mark(self):
        marks = self.marks()
        self.assertEqual(marks._prefix("PB-230x450"), "PB")
        self.assertEqual(marks._prefix("B-230x600"), "B")
        self.assertEqual(marks._prefix("F1"), "F")
        self.assertEqual(marks._prefix("C-300x600"), "C")

    def test_a_type_mark_with_no_letters_gives_nothing(self):
        """Wrong-looking enough that somebody fixes the TypeMark, which is the
        right place to fix it."""
        self.assertEqual(self.marks()._prefix("300x600"), "")
        self.assertEqual(self.marks()._prefix(None), "")

    def test_plinth_and_floor_beams_number_separately(self):
        """The whole point. One pattern, two series, and the distinction is the
        one the engineer already made in the TypeMark column."""
        marks, naming = self.marks(), self.naming()
        found = marks.labels(
            self.rows("PB-230x450", "PB-230x450", "B-230x600", "B-230x600"),
            naming.defaults(), "beam_mark")
        self.assertEqual(found["pb230x450"], "PB1")
        self.assertEqual(found["b230x600"], "B1")

    def test_a_second_section_of_the_same_prefix_counts_up(self):
        marks, naming = self.marks(), self.naming()
        found = marks.labels(self.rows("B-230x600", "B-200x400"),
                             naming.defaults(), "beam_mark")
        self.assertEqual(found["b230x600"], "B1")
        self.assertEqual(found["b200x400"], "B2")

    def test_numbering_follows_the_sheet_and_not_the_alphabet(self):
        """Sorting would renumber every beam in the building the day somebody
        adds ``B-200x400`` above the others."""
        marks, naming = self.marks(), self.naming()
        found = marks.labels(self.rows("B-900x900", "B-100x100"),
                             naming.defaults(), "beam_mark")
        self.assertEqual(found["b900x900"], "B1")
        self.assertEqual(found["b100x100"], "B2")

    def test_the_same_type_never_gets_two_labels(self):
        """It is a *repeating* label — that is what makes it schedulable."""
        marks, naming = self.marks(), self.naming()
        found = marks.labels(self.rows(*(["F1"] * 15)), naming.defaults(),
                             "footing_mark")
        self.assertEqual(found, {"f1": "F1"})

    def test_the_owners_footings_keep_the_marks_they_already_have(self):
        """F1, F2, F3 in the sheet must still schedule as F1, F2, F3 — the
        change must not renumber a model that was already right."""
        marks, naming = self.marks(), self.naming()
        found = marks.labels(self.rows("F1", "F2", "F3"), naming.defaults(),
                             "footing_mark")
        self.assertEqual([found["f1"], found["f2"], found["f3"]],
                         ["F1", "F2", "F3"])

    def test_a_hand_written_pattern_still_wins(self):
        marks, naming = self.marks(), self.naming()
        patterns = dict(naming.defaults())
        patterns["beam_mark"] = "BM-{prefix}{n}"
        found = marks.labels(self.rows("B-230x600"), patterns, "beam_mark")
        self.assertEqual(found["b230x600"], "BM-B1")

    def test_no_rows_gives_no_labels(self):
        marks, naming = self.marks(), self.naming()
        self.assertEqual(marks.labels([], naming.defaults(), "beam_mark"), {})
        self.assertEqual(marks.labels(None, naming.defaults(), "beam_mark"),
                         {})
