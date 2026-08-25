# -*- coding: utf-8 -*-
"""``levels.sync``, decided without Revit.

Every rule the command follows is decided in ``rc_automation/datum.py``, which
imports nothing from Revit — so the four refusals that make this safe to point
at a live model can be argued with here, in full, before anybody presses a
button.

Those four, and each is a refusal to be clever:

**Never delete.** A level the sheet omits is left alone and reported. Deleting
one takes every view, every sheet reference and every element hosted on it.

**Match by name, and only by name.** ``naming.py`` can match ``Level 1`` to
``01 1st Floor Lvl.`` by storey number, and that is right when a schedule
*refers* to a level somebody else named. Here the sheet **is** the naming
authority, so a fuzzy match would mean silently deciding two differently named
things are the same one.

**Never create a second level at an occupied elevation.** Revit allows it, and
then every plan view has two candidates.

**Never rename.** A rename changes what every view and sheet refers to.
"""

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
from anongee_toolkit.rc_automation import datum                  # noqa: E402
from anongee_toolkit.rc_automation import models                 # noqa: E402


def sheet(*rows):
    """A LEVELS grid with a title block above it, the way a real one grows."""
    return ([["AnonGee Bridge", "", ""], [None, None, None],
             ["Name", "Elevation", "LevelType", "Story", "Comments"]]
            + [list(row) for row in rows])


def model(*levels):
    """``[(name, key, elevation_mm)]`` — keys are strings here on purpose.

    ``plan_levels`` never learns what an ``ElementId`` is, which is the whole
    reason it can be tested at all.
    """
    return [(name, "id-{0}".format(index), float(elevation))
            for index, (name, elevation) in enumerate(levels)]


class ReadingTests(unittest.TestCase):

    def test_the_header_is_found_rather_than_assumed(self):
        # A real workbook grows a title block sooner or later, and a reader
        # that demands row one is a reader somebody works around by deleting
        # their own notes.
        rows, issues = datum.parse_levels(sheet(["01 GROUND LVL.", 0]))
        self.assertEqual([row.name for row in rows], ["01 GROUND LVL."])
        self.assertEqual(rows[0].row, 4)
        self.assertEqual(issues, [])

    def test_a_missing_header_is_an_error_naming_what_it_wanted(self):
        _rows, issues = datum.parse_levels([["a", "b"], [1, 2]])
        self.assertTrue(issues)
        self.assertIn("Name", issues[0].message)
        self.assertIn("Elevation", issues[0].message)

    def test_a_heading_with_a_unit_on_it_still_matches(self):
        """A real sheet writes ``RL (mm)``, not ``Elevation``."""
        grid = [["LEVEL NAME", "RL (mm)", "Storey"],
                ["01 GROUND LVL.", 0, "yes"]]
        rows, _issues = datum.parse_levels(grid)
        self.assertEqual(rows[0].name, "01 GROUND LVL.")
        self.assertEqual(rows[0].elevation_mm, 0.0)
        self.assertTrue(rows[0].story)

    def test_a_column_called_level_is_a_name_and_not_a_height(self):
        # Taking it for a height would put the wrong thing in the wrong column
        # silently, which is the failure mode worth guarding.
        rows, _issues = datum.parse_levels(
            [["Level", "Elevation"], ["01 GROUND LVL.", 0]])
        self.assertEqual(rows[0].name, "01 GROUND LVL.")
        self.assertEqual(rows[0].elevation_mm, 0.0)

    def test_an_elevation_with_a_unit_on_it_still_reads(self):
        rows, _issues = datum.parse_levels(sheet(["L1", "3,300 mm"]))
        self.assertEqual(rows[0].elevation_mm, 3300.0)

    def test_an_unreadable_elevation_names_its_cell(self):
        _rows, issues = datum.parse_levels(sheet(["L1", "about waist height"]))
        self.assertEqual(issues[0].severity, models.SEVERITY_ERROR)
        self.assertEqual(issues[0].row, 4)
        self.assertEqual(issues[0].column, "Elevation")

    def test_a_blank_row_is_not_an_error(self):
        rows, issues = datum.parse_levels(
            sheet(["01 GROUND LVL.", 0], [None, None], ["", ""]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(issues, [])

    def test_silence_about_story_is_not_a_no(self):
        """``None`` means the sheet did not say, and what it did not say is
        what the command does not change."""
        rows, _issues = datum.parse_levels(sheet(["L1", 0, "", "", ""]))
        self.assertIsNone(rows[0].story)


class PlanningTests(unittest.TestCase):

    def plan(self, rows, existing):
        parsed, _issues = datum.parse_levels(sheet(*rows))
        return datum.plan_levels(parsed, existing)

    def test_a_level_the_model_lacks_is_created(self):
        plans, _issues = self.plan([["02 1ST FLOOR LVL.", 3300]], model())
        self.assertEqual(plans[0].action, datum.CREATE)

    def test_a_level_that_agrees_is_left_alone(self):
        plans, _issues = self.plan([["01 GROUND LVL.", 0]],
                                   model(("01 GROUND LVL.", 0)))
        self.assertEqual(plans[0].action, datum.MATCH)
        self.assertFalse(plans[0].will_write)

    def test_a_difference_within_tolerance_is_not_a_difference(self):
        # Revit stores feet. A millimetre round trip never lands exactly, and
        # anything tighter reports a change that would change nothing.
        plans, _issues = self.plan([["01 GROUND LVL.", 0]],
                                   model(("01 GROUND LVL.", 0.2)))
        self.assertEqual(plans[0].action, datum.MATCH)

    def test_a_real_difference_is_a_modification_that_says_both_numbers(self):
        plans, _issues = self.plan([["01 GROUND LVL.", 0]],
                                   model(("01 GROUND LVL.", 100)))
        self.assertEqual(plans[0].action, datum.MODIFY)
        self.assertIn("100", plans[0].reason)
        self.assertIn("0", plans[0].reason)

    def test_case_and_spacing_do_not_make_a_new_level(self):
        plans, _issues = self.plan([["01 ground lvl.", 0]],
                                   model(("01 GROUND LVL.", 0)))
        self.assertEqual(plans[0].action, datum.MATCH)

    def test_a_level_the_sheet_omits_is_reported_and_never_touched(self):
        plans, issues = self.plan([["01 GROUND LVL.", 0]],
                                  model(("01 GROUND LVL.", 0),
                                        ("Site", -2000)))
        self.assertEqual(len(plans), 1)
        left = [issue for issue in issues if "left alone" in issue.message]
        self.assertEqual(len(left), 1)
        self.assertIn("Site", left[0].message)
        self.assertEqual(left[0].severity, models.SEVERITY_INFO)

    def test_a_second_level_is_never_created_at_an_occupied_elevation(self):
        """Revit allows it, and then every plan view has two candidates."""
        plans, issues = self.plan([["01 GROUND LVL.", 0]],
                                  model(("Level 1", 0)))
        self.assertEqual(plans[0].action, datum.BLOCKED)
        self.assertIn("Level 1", plans[0].reason)
        blocked = [issue for issue in issues
                   if issue.severity == models.SEVERITY_ERROR]
        self.assertTrue(blocked)
        self.assertIn("rename", blocked[0].message)

    def test_a_duplicate_in_the_sheet_is_refused_with_the_first_row_number(self):
        plans, issues = self.plan([["L1", 0], ["L1", 3300]], model())
        self.assertEqual(plans[1].action, datum.INVALID)
        self.assertIn("row 4", plans[1].reason)
        self.assertEqual(issues[0].column, "Name")

    def test_a_row_with_no_elevation_plans_nothing(self):
        plans, _issues = self.plan([["L1", "nonsense"]], model())
        self.assertEqual(plans[0].action, datum.INVALID)
        self.assertFalse(plans[0].will_write)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        """Idempotence is the acceptance test, not creation. Anything can
        create; only a tool that can be run twice is one anybody trusts with a
        live model."""
        rows = [["00 FOUNDATION LVL.", -1500], ["01 GROUND LVL.", 0],
                ["02 1ST FLOOR LVL.", 3300]]
        first, _issues = self.plan(rows, model())
        self.assertEqual(datum.summarise(first)["created"], 3)

        # ...and now the model has what the first run would have built.
        after = model(("00 FOUNDATION LVL.", -1500), ("01 GROUND LVL.", 0),
                      ("02 1ST FLOOR LVL.", 3300))
        second, _issues = self.plan(rows, after)
        counts = datum.summarise(second)
        self.assertEqual(counts["matched"], 3)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(counts["modified"], 0)
        self.assertFalse(any(plan.will_write for plan in second))

    def test_changing_one_elevation_moves_exactly_one_level(self):
        rows = [["00 FOUNDATION LVL.", -1500], ["01 GROUND LVL.", 0],
                ["02 1ST FLOOR LVL.", 3600]]
        plans, _issues = self.plan(rows, model(("00 FOUNDATION LVL.", -1500),
                                               ("01 GROUND LVL.", 0),
                                               ("02 1ST FLOOR LVL.", 3300)))
        counts = datum.summarise(plans)
        self.assertEqual(counts["modified"], 1)
        self.assertEqual(counts["matched"], 2)
        moving = [plan for plan in plans if plan.action == datum.MODIFY]
        self.assertEqual(moving[0].row.name, "02 1ST FLOOR LVL.")


def grid_sheet(*rows):
    return ([["Name", "X1", "Y1", "X2", "Y2", "Angle", "Length",
              "BubbleStart", "BubbleEnd", "Comments"]]
            + [list(row) + [None] * (10 - len(row)) for row in rows])


class GridAngleTests(unittest.TestCase):
    """``Angle`` is 0 along +X and 90 along +Y.

    The project owner added the column after meeting a real job with grids at
    30 and 45 degrees, and the convention is theirs: horizontal is 0, vertical
    is 90.
    """

    def line(self, *row):
        rows, _issues = datum.parse_grids(grid_sheet(row))
        return datum.grid_line(rows[0], datum.default_length(rows))

    def test_zero_runs_along_x(self):
        line, note = self.line("1", 0, 0, None, None, 0, 10000)
        self.assertEqual(note, "")
        self.assertAlmostEqual(line[1][0], 10000.0)
        self.assertAlmostEqual(line[1][1], 0.0)

    def test_ninety_runs_along_y(self):
        line, _note = self.line("A", 0, 0, None, None, 90, 10000)
        self.assertAlmostEqual(line[1][0], 0.0)
        self.assertAlmostEqual(line[1][1], 10000.0)

    def test_a_skewed_grid_lands_where_the_trigonometry_says(self):
        import math
        line, _note = self.line("S", 0, 0, None, None, 30, 10000)
        self.assertAlmostEqual(line[1][0], 10000 * math.cos(math.radians(30)))
        self.assertAlmostEqual(line[1][1], 10000 * math.sin(math.radians(30)))
        self.assertAlmostEqual(datum._angle_of(line), 30.0)

    def test_both_ends_win_over_an_angle_that_disagrees(self):
        """The points are the more specific statement, so they decide — and
        the disagreement is said out loud rather than quietly resolved."""
        line, note = self.line("X", 0, 0, 10000, 0, 45)
        self.assertAlmostEqual(datum._angle_of(line), 0.0)
        self.assertIn("45", note)
        self.assertIn("points win", note)

    def test_an_angle_that_agrees_says_nothing(self):
        _line, note = self.line("X", 0, 0, 10000, 0, 0)
        self.assertEqual(note, "")

    def test_a_row_with_neither_an_end_nor_an_angle_is_not_a_grid(self):
        line, note = self.line("X", 0, 0)
        self.assertIsNone(line)
        self.assertIn("angle", note)

    def test_a_length_of_its_own_beats_the_sheet_default(self):
        rows, _issues = datum.parse_grids(grid_sheet(
            ["A", 0, 0, 0, 30000], ["S", 0, 0, None, None, 0, 5000]))
        line, _note = datum.grid_line(rows[1], datum.default_length(rows))
        self.assertAlmostEqual(line[1][0], 5000.0)

    def test_a_row_with_no_length_borrows_the_sheets_extent(self):
        # "Grid A runs north" is a thing real sheets say. Something has to
        # decide how far, and the grids that did say are the honest answer.
        rows, _issues = datum.parse_grids(grid_sheet(
            ["A", 0, 0, 0, 30000], ["S", 0, 0, None, None, 0]))
        line, _note = datum.grid_line(rows[1], datum.default_length(rows))
        self.assertAlmostEqual(line[1][0], 30000.0)


class GridPlanningTests(unittest.TestCase):

    def plan(self, rows, existing):
        parsed, _issues = datum.parse_grids(grid_sheet(*rows))
        return datum.plan_grids(parsed, existing)

    def model(self, *grids):
        return [(name, "id-{0}".format(index), line)
                for index, (name, line) in enumerate(grids)]

    def test_a_grid_the_model_lacks_is_created(self):
        plans, _issues = self.plan([["A", 0, -2000, 0, 14000]], [])
        self.assertEqual(plans[0].action, datum.CREATE)

    def test_the_same_line_drawn_shorter_is_the_same_grid(self):
        """Extents are adjusted by hand in nearly every view. Comparing
        endpoints would report all of them and then undo the work."""
        plans, _issues = self.plan(
            [["A", 0, -2000, 0, 14000]],
            self.model(("A", ((0, 0), (0, 6000)))))
        self.assertEqual(plans[0].action, datum.MATCH)

    def test_the_same_line_drawn_backwards_is_the_same_grid(self):
        plans, _issues = self.plan(
            [["A", 0, -2000, 0, 14000]],
            self.model(("A", ((0, 14000), (0, -2000)))))
        self.assertEqual(plans[0].action, datum.MATCH)

    def test_a_parallel_grid_somewhere_else_is_moved(self):
        plans, _issues = self.plan(
            [["A", 0, -2000, 0, 14000]],
            self.model(("A", ((500, 0), (500, 6000)))))
        self.assertEqual(plans[0].action, datum.MODIFY)

    def test_a_grid_running_a_different_way_is_never_redrawn(self):
        """Revit cannot turn a grid. Recreating it loses anything dimensioned
        or constrained to it, so this is reported and left."""
        plans, issues = self.plan(
            [["A", 0, 0, 0, 14000]],
            self.model(("A", ((0, 0), (14000, 0)))))
        self.assertEqual(plans[0].action, datum.BLOCKED)
        self.assertIn("90", plans[0].reason)
        self.assertIn("0", plans[0].reason)
        errors = [issue for issue in issues
                  if issue.severity == models.SEVERITY_ERROR]
        self.assertIn("dimensioned", errors[0].message)

    def test_a_second_grid_is_never_put_on_an_occupied_line(self):
        plans, issues = self.plan(
            [["B", 0, -2000, 0, 14000]],
            self.model(("A", ((0, 0), (0, 6000)))))
        self.assertEqual(plans[0].action, datum.BLOCKED)
        self.assertIn("A", plans[0].reason)
        self.assertTrue(any("rename" in issue.message for issue in issues))

    def test_a_grid_the_sheet_omits_is_left_alone(self):
        _plans, issues = self.plan(
            [["A", 0, 0, 0, 14000]],
            self.model(("A", ((0, 0), (0, 14000))), ("Z", ((9, 9), (9, 99)))))
        left = [issue for issue in issues if "left alone" in issue.message]
        self.assertEqual(len(left), 1)
        self.assertIn("Z", left[0].message)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        rows = [["A", 0, -2000, 0, 14000], ["1", -2000, 0, 14000, 0],
                ["S1", 12000, 0, None, None, 45, 16000]]
        first, _issues = self.plan(rows, [])
        self.assertEqual(datum.summarise(first)["created"], 3)

        after = self.model(*[(plan.row.name, plan.line) for plan in first])
        second, _issues = self.plan(rows, after)
        counts = datum.summarise(second)
        self.assertEqual(counts["matched"], 3)
        self.assertFalse(any(plan.will_write for plan in second))


class CommandContractTests(unittest.TestCase):
    """What the Revit half is held to, read as source."""

    PATH = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                        "anongee_toolkit", "commands", "levels.py")

    def source(self):
        import io
        with io.open(self.PATH, encoding="utf-8") as handle:
            return handle.read()

    def test_it_decides_nothing_for_itself(self):
        """Every rule is in ``datum``. This file opens a workbook and obeys."""
        source = self.source()
        self.assertIn("datum.plan_levels", source)
        self.assertIn("datum.summarise", source)
        self.assertNotIn("def plan_", source)

    def test_a_dry_run_writes_nothing(self):
        body = self.source().split("def run(")[1].split("\ndef ")[0]
        self.assertIn("dryRun", body)
        self.assertLess(body.index("if dry_run:"), body.index("_apply("))

    def test_it_lands_as_one_undo_step(self):
        body = self.source().split("def _apply(")[1].split("\ndef ")[0]
        self.assertIn("TransactionGroup", body)
        self.assertIn("group.Assimilate()", body)
        self.assertIn("group.RollBack()", body)

    def test_it_refuses_a_read_only_model(self):
        self.assertIn("doc.IsReadOnly", self.source())

    def test_it_never_deletes(self):
        """Deleting a level takes every view and every element hosted on it."""
        source = self.source()
        self.assertNotIn("doc.Delete", source)
        self.assertNotIn(".Delete(", source)

    def test_only_a_new_level_is_ever_named(self):
        """Renaming an existing level changes what every view refers to."""
        body = self.source().split("def _apply(")[1].split("\ndef ")[0]
        create_branch = body.split("datum.CREATE:")[1].split("else:")[0]
        self.assertIn("_name(level", create_branch)
        modify_branch = body.split("else:")[1]
        self.assertNotIn("_name(", modify_branch)

    def test_it_is_registered_under_the_name_the_workbook_uses(self):
        import io
        with io.open(os.path.join(os.path.dirname(self.PATH), "__init__.py"),
                     encoding="utf-8") as handle:
            registered = handle.read()
        self.assertIn('("levels.sync", "levels", "run")', registered)
        self.assertIn('("grids.sync", "grids", "run")', registered)


class GridCommandContractTests(unittest.TestCase):
    """``grids.sync`` is held to the same shape as ``levels.sync``."""

    PATH = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                        "anongee_toolkit", "commands", "grids.py")

    def source(self):
        import io
        with io.open(self.PATH, encoding="utf-8") as handle:
            return handle.read()

    def test_it_decides_nothing_for_itself(self):
        source = self.source()
        self.assertIn("datum.plan_grids", source)
        self.assertNotIn("def plan_", source)

    def test_a_dry_run_writes_nothing(self):
        body = self.source().split("def run(")[1].split("\ndef ")[0]
        self.assertLess(body.index("if dry_run:"), body.index("_apply("))

    def test_it_lands_as_one_undo_step(self):
        body = self.source().split("def _apply(")[1].split("\ndef ")[0]
        self.assertIn("TransactionGroup", body)
        self.assertIn("group.Assimilate()", body)

    def test_it_never_deletes(self):
        self.assertNotIn("doc.Delete", self.source())
        self.assertNotIn(".Delete(", self.source())

    def test_an_existing_grid_is_moved_rather_than_redrawn(self):
        """Redrawing loses every dimension attached to it. The direction is
        known to match by then, so a translation is the whole difference."""
        body = self.source().split("def _apply(")[1].split("\ndef ")[0]
        modify = body.split("else:")[1]
        self.assertIn("MoveElement", modify)
        self.assertNotIn("Grid.Create", modify)

    def test_it_reuses_the_adapter_that_knows_about_arcs(self):
        # structural.grids.segment_mm returns None for a curve that is not a
        # Line, which is the case a hand-written reader gets wrong.
        body = self.source().split("def _existing(")[1].split("\ndef ")[0]
        self.assertIn("grid_module.segment_mm", body)
        self.assertIn("if segment is None:", body)

    def test_the_move_is_perpendicular_only(self):
        """Sliding along the shared direction moves the grid without changing
        where it is, and drags its extents off the building for nothing."""
        body = self.source().split("def _offset(")[1].split("\ndef ")[0]
        self.assertIn("normal", body)
        self.assertIn("Perpendicular only", body)


class UnitTests(unittest.TestCase):
    """Millimetres inside, whatever the sheet is in.

    The failure being prevented is silent and total: a LEVELS sheet in metres
    read as millimetres puts a terrace at 16.5 mm. Every level in the building
    lands inside the slab thickness of the one below, every plan view is
    meaningless, and the run reports success with the right number of levels
    created. Nothing about that looks like a bug until somebody opens a
    section.
    """

    def test_a_header_that_names_its_unit_is_believed(self):
        self.assertEqual(datum.unit_in_header("Elevation PBP (m)"), "m")
        self.assertEqual(datum.unit_in_header("Elevation (mm)"), "mm")
        self.assertEqual(datum.unit_in_header("RL (MM)"), "mm")

    def test_a_header_that_does_not_is_not_guessed_at(self):
        for head in ("Elevation", "Angle", "Mark", "Name", "Comments", ""):
            self.assertIsNone(datum.unit_in_header(head), head)

    def test_a_word_ending_in_m_is_not_a_unit(self):
        # "Datum" and "Beam" end in m. Only a bracketed suffix counts, which is
        # why the check is for "(m)" and not for the letter.
        for head in ("Datum", "Beam", "Diagram", "Room"):
            self.assertIsNone(datum.unit_in_header(head), head)

    def test_the_header_wins_over_the_job(self):
        grid = [["Name", "Elevation (m)"], ["01 GROUND LVL.", 0],
                ["02 FIRST FLOOR LVL.", 3.3]]
        rows, issues = datum.parse_levels(grid, units="mm")
        self.assertFalse([issue for issue in issues
                          if issue.severity == models.SEVERITY_ERROR])
        self.assertAlmostEqual(rows[1].elevation_mm, 3300.0)

    def test_the_job_decides_when_the_header_is_silent(self):
        grid = [["Name", "Elevation"], ["02 FIRST FLOOR LVL.", 3.3]]
        rows, _issues = datum.parse_levels(grid, units="m")
        self.assertAlmostEqual(rows[0].elevation_mm, 3300.0)

    def test_millimetres_are_the_fallback_and_stay_untouched(self):
        # Every workbook written before the unit existed is in millimetres. A
        # default of metres would multiply all of them by a thousand.
        grid = [["Name", "Elevation"], ["02 FIRST FLOOR LVL.", 3300]]
        rows, _issues = datum.parse_levels(grid)
        self.assertAlmostEqual(rows[0].elevation_mm, 3300.0)
        self.assertEqual(datum.normalise_unit(""), "mm")

    def test_an_angle_is_never_scaled(self):
        grid = [["Name", "X1 (m)", "Y1 (m)", "Angle"], ["A", 0, 0, 90]]
        rows, _issues = datum.parse_grids(grid, units="m")
        self.assertEqual(rows[0].angle_deg, 90)
        self.assertAlmostEqual(rows[0].x1, 0.0)

    def test_grid_coordinates_are_scaled(self):
        grid = [["Name", "X1 (m)", "Y1 (m)", "X2 (m)", "Y2 (m)"],
                ["A", 0, -2, 0, 14]]
        rows, _issues = datum.parse_grids(grid, units="m")
        self.assertAlmostEqual(rows[0].y1, -2000.0)
        self.assertAlmostEqual(rows[0].y2, 14000.0)


class SurveyElevationTests(unittest.TestCase):
    """Two elevations, one authority, and no quiet arithmetic.

    A structural drawing says a level is at 3.3 and the site drawing says the
    same level is at 103.3. Both are right; the difference is where the survey
    point was put, which is a property of the model. So the sheet carries both
    and says which one it means, and anything this cannot settle is reported
    rather than approximated.
    """

    def rows(self, base="", pbp=3300.0, survey=None):
        return [datum.LevelRow("02 FIRST FLOOR LVL.", pbp, row=2,
                               elevation_survey_mm=survey,
                               elevation_base=base)]

    def test_a_project_base_row_is_left_alone(self):
        rows = self.rows()
        issues = datum.resolve_elevations(rows, 100000.0)
        self.assertEqual(issues, [])
        self.assertEqual(rows[0].elevation_mm, 3300.0)

    def test_a_survey_row_is_converted_with_the_models_offset(self):
        rows = self.rows(datum.BASE_SURVEY, pbp=None, survey=103300.0)
        issues = datum.resolve_elevations(rows, 100000.0)
        self.assertEqual(issues, [])
        self.assertAlmostEqual(rows[0].elevation_mm, 3300.0)

    def test_a_survey_row_without_a_model_offset_is_refused(self):
        # The alternative is building it at 103.3, which is a hundred metres
        # out and looks deliberate.
        rows = self.rows(datum.BASE_SURVEY, pbp=None, survey=103300.0)
        issues = datum.resolve_elevations(rows, None)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, models.SEVERITY_ERROR)
        self.assertIsNone(rows[0].elevation_mm)

    def test_a_survey_row_with_no_survey_elevation_is_refused(self):
        rows = self.rows(datum.BASE_SURVEY, pbp=3300.0, survey=None)
        issues = datum.resolve_elevations(rows, 100000.0)
        self.assertEqual(len(issues), 1)
        self.assertIsNone(rows[0].elevation_mm)

    def test_two_elevations_that_disagree_are_reported_not_fixed(self):
        rows = self.rows(pbp=3300.0, survey=104000.0)
        issues = datum.resolve_elevations(rows, 100000.0)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, models.SEVERITY_WARNING)
        self.assertEqual(rows[0].elevation_mm, 3300.0)
        self.assertIn("one of the two is wrong", issues[0].message)

    def test_two_elevations_that_agree_say_nothing(self):
        rows = self.rows(pbp=3300.0, survey=103300.0)
        self.assertEqual(datum.resolve_elevations(rows, 100000.0), [])

    def test_a_row_that_is_unresolved_never_gets_built(self):
        # The join between the two halves: an unresolved elevation is None, and
        # plan_levels already refuses None. Worth a test because it is the only
        # thing standing between a bad survey row and Level.Create.
        rows = self.rows(datum.BASE_SURVEY, pbp=None, survey=103300.0)
        datum.resolve_elevations(rows, None)
        plans, _issues = datum.plan_levels(rows, [])
        self.assertEqual(plans[0].action, datum.INVALID)
        self.assertFalse(plans[0].will_write)


def _errors(issues):
    return [issue for issue in issues
            if issue.severity == models.SEVERITY_ERROR]


class RenameTests(unittest.TestCase):
    """One blocked level cost fifteen columns, and this is the way out.

    A template ships with ``Level 0`` at 0.000; a real sheet asks for
    ``01 GROUND LVL.`` at 0.000. The rule *never create a second level at an
    occupied elevation* refused it — correctly — and then every column naming
    the level that was never created failed too. Two symptoms, one cause, and
    both of them a long way from the level sheet.

    So a row can name the level it replaces. Explicitly, in a column, where
    somebody wrote it down — which is what the original refusal was protecting.
    """

    def existing(self):
        return [("Level 0", "id-0", 0.0)]

    def row(self, rename_from=""):
        return datum.LevelRow("01 GROUND LVL.", 0.0, row=2,
                              rename_from=rename_from)

    def test_without_the_column_it_is_still_blocked(self):
        plans, issues = datum.plan_levels([self.row()], self.existing())
        self.assertEqual(plans[0].action, datum.BLOCKED)
        self.assertEqual(len(_errors(issues)), 1)

    def test_the_block_says_how_to_get_past_it(self):
        _plans, issues = datum.plan_levels([self.row()], self.existing())
        self.assertIn("RenameFrom", issues[0].message)
        self.assertIn("Level 0", issues[0].message)

    def test_naming_the_level_renames_it(self):
        plans, issues = datum.plan_levels([self.row("Level 0")],
                                          self.existing())
        self.assertEqual(plans[0].action, datum.RENAME)
        self.assertEqual(plans[0].key, "id-0")
        self.assertTrue(plans[0].will_write)
        self.assertEqual(_errors(issues), [])

    def test_the_rename_is_reported_because_it_is_not_reversible_cheaply(self):
        _plans, issues = datum.plan_levels([self.row("Level 0")],
                                           self.existing())
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, models.SEVERITY_INFO)
        self.assertIn("never renamed on a guess", issues[0].message)

    def test_naming_the_wrong_level_does_not_rename_anything(self):
        # The column is a permission for one named level, not a licence.
        plans, _issues = datum.plan_levels([self.row("Level 42")],
                                           self.existing())
        self.assertEqual(plans[0].action, datum.BLOCKED)

    def test_a_renamed_level_is_counted_separately(self):
        plans, _issues = datum.plan_levels([self.row("Level 0")],
                                           self.existing())
        counts = datum.summarise(plans)
        self.assertEqual(counts["renamed"], 1)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(counts["blocked"], 0)

    def test_the_column_is_read_from_the_sheet(self):
        grid = [["Name", "Elevation", "RenameFrom"],
                ["01 GROUND LVL.", 0, "Level 0"]]
        rows, _issues = datum.parse_levels(grid)
        self.assertEqual(rows[0].rename_from, "Level 0")

    def test_rename_from_is_not_swallowed_by_the_name_column(self):
        # Both are names. A reader that took RenameFrom for the level's own
        # name would rename every level to the one it was replacing.
        grid = [["Name", "Elevation", "RenameFrom"],
                ["01 GROUND LVL.", 0, "Level 0"]]
        rows, _issues = datum.parse_levels(grid)
        self.assertEqual(rows[0].name, "01 GROUND LVL.")

    def test_a_second_run_matches_the_level_it_renamed(self):
        # Idempotence across the rename: once Level 0 is 01 GROUND LVL., the
        # next run must match it by name and do nothing.
        plans, _issues = datum.plan_levels(
            [self.row("Level 0")], [("01 GROUND LVL.", "id-0", 0.0)])
        self.assertEqual(plans[0].action, datum.MATCH)


if __name__ == "__main__":
    unittest.main()
