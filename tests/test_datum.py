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
            self.assertIn('("levels.sync", "levels", "run")', handle.read())


if __name__ == "__main__":
    unittest.main()
