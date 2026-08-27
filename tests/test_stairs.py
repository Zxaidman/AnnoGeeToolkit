# -*- coding: utf-8 -*-
"""The stair, checked off Revit — option B, for the project owner to judge.

Two halves are testable here and they are the two that matter. The
**arithmetic** decides whether a flight lands on the floor, and a staircase one
riser out arrives looking almost right, which is the worst way for a mistake to
present itself. The **sheet** decides whether a dog-leg can be described at all.

The third half — whether a slanted beam and a stack of triangular prisms look
like a staircase in Revit — is exactly what cannot be tested here, and is why
this is being shipped for review rather than declared finished.
"""

import ast
import io
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_load_rc()
from anongee_toolkit.rc_automation import flight as _flight   # noqa: E402
from anongee_toolkit.rc_automation import placement as _placement  # noqa: E402

#: The sample's stair: 1200 wide, 150 waist, 280 tread, 165 nominal riser.
SIZES = {"width_mm": 1200.0, "waist_mm": 150.0, "tread_mm": 280.0,
         "riser_mm": 165.0}


class FlightArithmeticTests(unittest.TestCase):

    def test_a_storey_divides_into_whole_risers(self):
        flight, _issues = _flight.solve(3300.0, SIZES)
        self.assertEqual(flight.risers, 20)
        self.assertAlmostEqual(flight.riser_mm, 165.0, places=6)

    def test_the_flight_lands_exactly_on_the_floor(self):
        """The rule the whole module turns on. Whatever the nominal riser is,
        ``risers * riser`` must equal the rise to the millimetre — a flight
        that is 8 mm short has a step at the top that nobody drew."""
        for rise in (3300.0, 3320.0, 2850.0, 4200.0, 3175.0):
            flight, _issues = _flight.solve(rise, SIZES)
            self.assertAlmostEqual(flight.risers * flight.riser_mm, rise,
                                   places=6, msg="rise {0}".format(rise))

    def test_an_awkward_storey_changes_the_riser_not_the_count(self):
        """3320 over a 165 nominal is 20 risers of 166, not 20 of 165 and a
        20 mm step at the top."""
        flight, issues = _flight.solve(3320.0, SIZES, mark="S1")
        self.assertEqual(flight.risers, 20)
        self.assertAlmostEqual(flight.riser_mm, 166.0, places=6)
        self.assertTrue(any("has to land exactly on the floor" in issue.message
                            for issue in issues))

    def test_a_riser_that_matches_the_nominal_says_nothing(self):
        _flight_, issues = _flight.solve(3300.0, SIZES, mark="S1")
        self.assertEqual([issue for issue in issues
                          if "land exactly" in issue.message], [])

    def test_there_is_one_fewer_tread_than_riser(self):
        """The last riser lands on the floor slab and has no tread of its own.
        Getting this wrong makes every flight one tread too long, and it fits
        in the bay, so nothing complains."""
        flight, _issues = _flight.solve(3300.0, SIZES)
        self.assertEqual(flight.treads, flight.risers - 1)
        self.assertAlmostEqual(flight.run_mm, 19 * 280.0, places=6)

    def test_the_waist_stops_one_riser_below_the_floor(self):
        flight, _issues = _flight.solve(3300.0, SIZES)
        self.assertAlmostEqual(flight.waist_top_rise_mm,
                               3300.0 - flight.riser_mm, places=6)

    def test_the_corners_climb_one_riser_per_tread(self):
        flight, _issues = _flight.solve(3300.0, SIZES)
        corners = flight.corners_mm()
        self.assertEqual(len(corners), flight.risers)
        self.assertEqual(corners[0], (0.0, 0.0))
        for index in range(1, len(corners)):
            along = corners[index][0] - corners[index - 1][0]
            up = corners[index][1] - corners[index - 1][1]
            self.assertAlmostEqual(along, flight.tread_mm, places=6)
            self.assertAlmostEqual(up, flight.riser_mm, places=6)

    def test_a_step_is_a_triangle_and_not_a_box(self):
        """Half a tread by a riser by the width, per step.

        A step modelled as a box is exactly twice the concrete, on every step
        of every flight in the building — a quantity error that looks entirely
        plausible until somebody prices it.
        """
        flight, _issues = _flight.solve(3300.0, SIZES)
        box = (flight.tread_mm * flight.riser_mm * flight.width_mm
               * flight.treads) / 1.0e9
        self.assertAlmostEqual(flight.step_volume_m3, box / 2.0, places=9)

    def test_the_waist_is_measured_along_the_slope(self):
        """Its thickness is perpendicular to the slope, so the slope length —
        not the run — is what multiplies it. Using the run understates a 30
        degree flight by about 14 per cent."""
        flight, _issues = _flight.solve(3300.0, SIZES)
        by_run = (flight.run_mm * flight.waist_mm * flight.width_mm) / 1.0e9
        self.assertGreater(flight.waist_volume_m3, by_run)
        self.assertAlmostEqual(
            flight.waist_volume_m3,
            (flight.slope_length_mm * flight.waist_mm * flight.width_mm)
            / 1.0e9, places=9)

    def test_the_volume_is_the_two_parts(self):
        flight, _issues = _flight.solve(3300.0, SIZES)
        self.assertAlmostEqual(
            flight.volume_m3,
            flight.waist_volume_m3 + flight.step_volume_m3, places=9)

    def test_the_pitch_is_a_staircase_and_not_a_ladder(self):
        flight, _issues = _flight.solve(3300.0, SIZES)
        self.assertTrue(25.0 < flight.pitch_degrees < 40.0,
                        flight.pitch_degrees)

    def test_a_missing_size_is_named(self):
        for absent in ("width_mm", "waist_mm", "tread_mm", "riser_mm"):
            sizes = dict(SIZES)
            sizes[absent] = None
            flight, issues = _flight.solve(3300.0, sizes, mark="S1")
            self.assertIsNone(flight, absent)
            self.assertTrue(issues)

    def test_two_levels_the_same_height_is_refused(self):
        flight, issues = _flight.solve(0.0, SIZES, mark="S1")
        self.assertIsNone(flight)
        self.assertIn("same height", issues[0].message)

    def test_a_negative_rise_is_refused_rather_than_built_upside_down(self):
        flight, issues = _flight.solve(-3300.0, SIZES, mark="S1")
        self.assertIsNone(flight)
        self.assertTrue(issues)

    def test_too_many_risers_asks_for_a_landing(self):
        flight, issues = _flight.solve(30000.0, SIZES, mark="S1")
        self.assertIsNone(flight)
        self.assertIn("landing", issues[0].message)

    def test_overshooting_the_bay_is_reported_and_still_built(self):
        """A drawing error somebody has to see, not a number to quietly
        honour. The flight is built as described so it can be looked at."""
        flight, issues = _flight.solve(3300.0, SIZES, mark="S1",
                                       available_mm=4000.0)
        self.assertIsNotNone(flight)
        self.assertTrue(any("overshoots" in issue.message
                            for issue in issues))

    def test_fitting_the_bay_says_nothing(self):
        _f, issues = _flight.solve(3300.0, SIZES, mark="S1",
                                   available_mm=6000.0)
        self.assertEqual([issue for issue in issues
                          if "overshoot" in issue.message], [])


class StairSheetTests(unittest.TestCase):

    HEADER = ["Mark", "TypeMark", "FromGridX", "FromGridY", "ToGridX",
              "ToGridY", "Level", "TopLevel", "Offset", "Comments"]

    def rows(self, *body):
        return [self.HEADER] + [list(item) for item in body]

    def test_a_flight_carries_both_of_its_levels(self):
        """The one thing that makes a flight not a beam."""
        groups, issues = _placement.parse_stairs(self.rows(
            ["ST1", "ST-1200", "A", "1", "B", "1", "01 GROUND LVL.",
             "02 FIRST FLOOR LVL.", 0, ""]), units="mm")
        self.assertEqual(issues, [])
        self.assertEqual(len(groups), 1)
        row = groups[0][0]
        self.assertEqual(row.level, "01 GROUND LVL.")
        self.assertEqual(row.top_level, "02 FIRST FLOOR LVL.")

    def test_a_dog_leg_is_a_group_the_way_a_continuous_beam_is(self):
        """Not a coincidence borrowed from the beam sheet — the same fact. A
        continuous beam is several members that make one beam; a dog-leg is two
        flights that make one stair. Both are what the schedule names."""
        groups, _issues = _placement.parse_stairs(self.rows(
            ["ST1", "ST-1200", "A", "1", "B", "1", "01", "MID", 0, "up"],
            ["ST1", "ST-1200", "B", "1", "A", "1", "MID", "02", 0, "back"],
            ["", "", "", "", "", "", "", "", "", ""],
            ["ST2", "ST-1200", "A", "1", "B", "1", "02", "03", 0, ""]),
            units="mm")
        self.assertEqual([len(group) for group in groups], [2, 1])
        self.assertEqual([row.mark for row in groups[0]], ["ST1", "ST1"])

    def test_the_blank_row_is_load_bearing(self):
        """Remove it and two stairs become one, silently."""
        groups, _issues = _placement.parse_stairs(self.rows(
            ["ST1", "ST-1200", "A", "1", "B", "1", "01", "02", 0, ""],
            ["ST2", "ST-1200", "A", "1", "B", "1", "02", "03", 0, ""]),
            units="mm")
        self.assertEqual(len(groups), 1)

    def test_a_stair_type_reads_its_four_numbers(self):
        types, issues = _placement.parse_stair_types(
            [["TypeMark", "Width", "Waist", "Tread", "Riser"],
             ["ST-1200", 1200, 150, 280, 165]], units="mm")
        self.assertEqual(issues, [])
        self.assertEqual(types["st1200"], {"width_mm": 1200.0,
                                           "waist_mm": 150.0,
                                           "tread_mm": 280.0,
                                           "riser_mm": 165.0})

    def test_the_unit_in_the_header_wins(self):
        types, _issues = _placement.parse_stair_types(
            [["TypeMark", "Width (m)", "Waist (m)", "Tread (m)", "Riser (m)"],
             ["ST-1200", 1.2, 0.15, 0.28, 0.165]], units="m")
        self.assertAlmostEqual(types["st1200"]["width_mm"], 1200.0, places=6)
        self.assertAlmostEqual(types["st1200"]["riser_mm"], 165.0, places=6)

    def test_a_stair_type_does_not_borrow_a_columns_vocabulary(self):
        """``Depth`` on a stair sheet means nothing, and reading it as one of
        the four numbers would size a flight off it."""
        self.assertNotIn("depth_mm", _placement.STAIR_SIZES)
        self.assertEqual(set(_placement.STAIR_SIZES),
                         {"width_mm", "waist_mm", "tread_mm", "riser_mm"})


class SampleStairTests(unittest.TestCase):
    """The sample workbook's own stair, solved with its own numbers."""

    def sample(self):
        import importlib.util
        path = os.path.join(_ROOT, "bridge", "excel",
                            "build_sample_project.py")
        spec = importlib.util.spec_from_file_location("_sample_stairs", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_one_flight_per_storey_and_they_stack(self):
        """Which is what a stair core is, and it makes the second run's
        ``matched`` the test that matters."""
        sample = self.sample()
        rows = sample.stair_rows()
        self.assertEqual(len(rows), len(sample.LEVELS) - 2)
        self.assertEqual(len(set((row[2], row[3]) for row in rows)), 1)

    def test_every_flight_names_two_levels_that_exist(self):
        sample = self.sample()
        names = set(name for name, _elevation, _story in sample.LEVELS)
        for row in sample.stair_rows():
            self.assertIn(row[6], names)
            self.assertIn(row[7], names)

    def test_the_sample_flight_fits_the_bay_it_is_put_in(self):
        """Not a coincidence — it is why that bay. If this fails the sample
        ships a stair that reports an overshoot on every run."""
        sample = self.sample()
        sizes = {"width_mm": 1200.0, "waist_mm": 150.0, "tread_mm": 280.0,
                 "riser_mm": 165.0}
        flight, issues = _flight.solve(3300.0, sizes, available_mm=6000.0)
        self.assertLess(flight.run_mm, 6000.0)
        self.assertEqual([issue for issue in issues
                          if "overshoot" in issue.message], [])


class StairModuleTests(unittest.TestCase):
    """Static checks on the Revit half — option A, which cannot be imported
    here because ``Autodesk.Revit.DB.Architecture`` does not exist off Revit.

    What is checked is everything that would otherwise fail only inside Revit,
    and each has a specific failure in mind.
    """

    def source(self, package, name):
        path = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit", package, name)
        with io.open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_it_builds_a_real_revit_stair(self):
        """Option A. The waist-slab version is gone, and nothing should be
        quietly left behind that still places framing for a stair."""
        body = self.source("structural", "stairs.py")
        self.assertIn("StairsEditScope", body)
        self.assertIn("StairsRun.CreateStraightRun", body)
        self.assertNotIn("StructuralType.Beam", body)
        self.assertNotIn("DirectShape", body)

    def test_the_edit_scope_is_not_opened_inside_a_transaction(self):
        """``StairsEditScope.Start`` throws if a transaction is open, and there
        is no way to place a Revit stair without one. So ``create`` must start
        the scope **before** it starts any transaction — reading the two calls
        in source order is exactly what catches this getting reordered.
        """
        tree = ast.parse(self.source("structural", "stairs.py"))
        create = [node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "create"]
        self.assertTrue(create)

        scope_at = transaction_at = None
        for node in ast.walk(create[0]):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name == "StairsEditScope" and scope_at is None:
                scope_at = node.lineno
            if name == "Transaction" and transaction_at is None:
                transaction_at = node.lineno
        self.assertIsNotNone(scope_at)
        self.assertIsNotNone(transaction_at)
        self.assertLess(scope_at, transaction_at,
                        "the edit scope must be started before any "
                        "transaction, or Start() throws")

    def test_the_command_asks_for_a_writer_that_holds_no_transaction(self):
        """Every other command runs inside a transaction the runner opened.
        This one cannot, and says so by passing its own writer."""
        body = self.source("commands", "stairs.py")
        self.assertIn("write=_placement.outside_a_transaction", body)

    def test_the_writer_it_asks_for_opens_no_transaction(self):
        """The whole point of the override. If a transaction crept back into
        it, every stair run would fail at ``scope.Start`` and the reason would
        be nowhere near the change."""
        tree = ast.parse(self.source("commands", "_placement.py"))
        writer = [node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "outside_a_transaction"]
        self.assertTrue(writer)
        called = [getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                  for node in ast.walk(writer[0]) if isinstance(node, ast.Call)]
        self.assertIn("TransactionGroup", called)
        self.assertNotIn("Transaction", called)

    def test_the_default_writer_still_opens_one(self):
        """Six commands depend on it, and the override must not have changed
        what they get."""
        tree = ast.parse(self.source("commands", "_placement.py"))
        writer = [node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_write"]
        called = [getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                  for node in ast.walk(writer[0]) if isinstance(node, ast.Call)]
        self.assertIn("Transaction", called)
        self.assertIn("TransactionGroup", called)

    def test_the_riser_count_is_set_on_the_instance(self):
        """It is what makes a flight land on the floor. Revit divides the rise
        by it exactly as ``flight.solve`` does, so the two agree by
        construction rather than by luck."""
        self.assertIn("DesiredRisersNumber",
                      self.source("structural", "stairs.py"))

    def test_the_type_carries_the_waist_and_the_tread(self):
        """A monolithic stair's structural depth *is* the waist. Setting it
        before ``MonolithicStairs`` silently does nothing, which is why the
        order is pinned here."""
        body = self.source("structural", "stairs.py")
        self.assertIn('MONOLITHIC = "MonolithicStairs"', body)
        self.assertIn('WAIST = "StructuralDepth"', body)
        self.assertIn('TREAD = "MinimumTreadDepth"', body)
        self.assertLess(body.index("MONOLITHIC ="), body.index("WAIST ="))

    def test_the_failure_preprocessor_is_a_clr_class_built_once(self):
        """A class subclassing a Revit interface can only be defined once per
        session — a second definition is a second, incompatible type. It also
        cannot be defined at import, because the interface does not exist off
        Revit. Hence the cache."""
        body = self.source("structural", "stairs.py")
        self.assertIn("IFailuresPreprocessor", body)
        self.assertIn("_CLR", body)
        self.assertIn('__namespace__', body)

    def test_only_warnings_are_swallowed(self):
        """A stair almost always raises one and an unhandled warning aborts the
        scope. Errors must still fail, or a stair that genuinely cannot be
        built reports success."""
        body = self.source("structural", "stairs.py")
        self.assertIn("DeleteAllWarnings", body)
        self.assertNotIn("ResolveFailures", body)

    def test_no_revit_import_at_module_level(self):
        for name in ("stairs.py",):
            tree = ast.parse(self.source("structural", name))
            for node in tree.body:
                self.assertNotIsInstance(node, (ast.Import, ast.ImportFrom))

    def test_a_failed_flight_says_the_others_stay_built(self):
        """The cost of committing a scope per flight, and it must not be
        silent: every other command rolls back whole."""
        self.assertIn("stay built", self.source("commands", "stairs.py"))


if __name__ == "__main__":
    unittest.main()
