# -*- coding: utf-8 -*-
"""The profile check that stands between a slab loop and Floor.Create.

Revit answers a sketch it cannot compose with one paragraph naming no geometry
-- "the input curve loops cannot compose a valid boundary ... Parameter name:
profile" -- and a stack. The owner got exactly that on a 151-slab run and had
nothing to look for. `builders/slabs.check_profile` asks the question first and
declines by name, so the two things worth pinning here are the RULES it applies
and the WIRING that makes it run before Revit does.

`builders/slabs.py` imports Revit at module level and cannot be imported
offline. The check was written Revit-free for exactly this reason: every
function below is pure arithmetic on (x, y) tuples in internal feet, so the
module's top-level constants and functions can be read out of its source and
exec'd on their own -- the same trick `test_blanket_notes` uses to reach
`run_builders.blanket_mm`. `TheCheckStaysRevitFree` is what keeps that true.
"""

import ast
import os
import unittest

import _loader


config = _loader.load("config")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SLABS = os.path.normpath(os.path.join(_HERE, "..", "builders", "slabs.py"))

_MM = config.MM_PER_FT


def _source():
    with open(_SLABS, "rb") as handle:
        return handle.read().decode("utf-8")


def _pure():
    """Every top-level constant and function of builders/slabs.py, exec'd.

    Defining a function never touches its body, so the ones that DO call Revit
    define perfectly well here; they simply are not called. `config` is seeded
    because `_MM` is read off it, exactly as `builders/footings.py` reads it.
    """
    tree = ast.parse(_source())
    body = [node for node in tree.body
            if isinstance(node, (ast.Assign, ast.FunctionDef))]
    namespace = {"config": config}
    exec(compile(ast.Module(body, []), _SLABS, "exec"), namespace)
    return namespace


def _function(name):
    for node in ast.walk(ast.parse(_source())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("builders/slabs.py has no %s" % name)


def ring(*corners):
    """A ring in internal feet from corners given in millimetres."""
    return [(x / _MM, y / _MM) for x, y in corners]


_SQUARE = ring((0, 0), (5000, 0), (5000, 4000), (0, 4000))
_VOID = ring((1000, 1000), (2000, 1000), (2000, 2000), (1000, 2000))


class TheRulesOneLoopMustKeep(unittest.TestCase):
    """`_ring_faults` -- Revit's refusal list, minus what cannot happen here.

    Revit names six ways a profile fails. Three of them -- non-planar, not
    parallel to XY, helical -- are unreachable from this builder, which lays
    every ring flat on z = 0 out of (x, y) pairs. The other three are emptiness,
    closure and self-intersection, and each has its own sentence so the report
    says which one was broken rather than that something was.
    """

    def setUp(self):
        self.faults = _pure()["_ring_faults"]

    def test_a_loop_of_two_corners_encloses_nothing(self):
        self.assertIn("fewer than three",
                      self.faults(ring((0, 0), (5000, 0))))

    def test_a_rectangle_is_accepted(self):
        self.assertIsNone(self.faults(_SQUARE))

    def test_an_l_shape_is_accepted(self):
        # re-entrant corners are ordinary structural geometry, not a fault
        self.assertIsNone(self.faults(ring(
            (0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000),
            (0, 6000))))

    def test_an_edge_with_no_length_is_refused(self):
        # Revit will not build a curve shorter than its own tolerance, and a
        # loop cannot close through one
        self.assertIn("no length", self.faults(ring(
            (0, 0), (5000, 0), (5000.1, 0.1), (5000, 4000), (0, 4000))))

    def test_a_loop_that_returns_to_a_corner_is_refused(self):
        # the exploded-polyline signature: the walk arrives back at a corner it
        # has already been through, so the "loop" is two loops pinched together
        self.assertIn("already been through", self.faults(ring(
            (0, 0), (5000, 0), (5000, 4000), (2500, 2000), (0, 4000),
            (2500, 2000))))

    def test_a_bow_tie_is_refused(self):
        self.assertIn("crosses or touches itself", self.faults(ring(
            (0, 0), (5000, 4000), (5000, 0), (0, 4000))))

    def test_an_edge_that_lands_on_a_far_edge_is_refused(self):
        # a T-touch crosses nothing, and Revit refuses it all the same: tangency
        # is what `fold_plan.split_profile` was written for
        self.assertIn("crosses or touches itself", self.faults(ring(
            (0, 0), (5000, 0), (5000, 4000), (2500, 4000), (2500, 0),
            (2400, 0), (2400, 4000), (0, 4000))))

    def test_a_bay_edge_drawn_twice_a_millimetre_apart_is_still_a_bay(self):
        """The false positive that decided the within-ring tolerance.

        test14 draws a bay's east edge twice, 1.4 mm apart. `_sanitize_ring`
        merges the sliver and leaves the two runs about 0.9 mm from each other
        -- untidy, and Revit takes it. Judging a ring against itself at the
        millimetre used BETWEEN rings would decline six real slabs.
        """
        self.assertIsNone(self.faults(ring(
            (0, 0), (5000, 0), (5000, 4000), (5000.9, 4000), (5000.9, 8000),
            (0, 8000))))


class TheRulesBetweenLoops(unittest.TestCase):
    """A void has to sit strictly inside its slab, and clear of every other.

    Revit composes a profile out of loops that do not meet. Not "do not cross"
    -- do not MEET: a hole drawn to the slab edge, or two holes drawn to the
    same line, is the refusal `fold_plan.split_profile` documents from the
    user's own one-error run.
    """

    def setUp(self):
        self.check = _pure()["check_profile"]

    def test_a_void_well_inside_is_cut(self):
        self.assertEqual(self.check(_SQUARE, [_VOID], "S1"), (True, [0], None))

    def test_a_void_sharing_an_edge_with_the_slab_is_not_cut(self):
        place_it, kept, report = self.check(
            _SQUARE, [ring((0, 1000), (2000, 1000), (2000, 2000), (0, 2000))],
            "S2")
        self.assertTrue(place_it)
        self.assertEqual(kept, [])
        self.assertIn("shares an edge with the slab's own outline", report)

    def test_a_void_spilling_over_the_slab_edge_is_not_cut(self):
        _p, kept, report = self.check(
            _SQUARE,
            [ring((4000, 1000), (6000, 1000), (6000, 2000), (4000, 2000))],
            "S3")
        self.assertEqual(kept, [])
        self.assertIn("crosses the slab's own outline", report)

    def test_a_void_touching_the_slab_edge_at_one_point_is_not_cut(self):
        # inside everywhere, and its apex lands ON the boundary: no crossing,
        # no shared length, and Revit refuses it all the same
        _p, kept, report = self.check(
            _SQUARE, [ring((5000, 2000), (4000, 1500), (4000, 2500))], "S4")
        self.assertEqual(kept, [])
        self.assertIn("touches the slab's own outline", report)

    def test_a_void_outside_the_slab_altogether_is_not_cut(self):
        _p, kept, report = self.check(
            _SQUARE,
            [ring((9000, 9000), (10000, 9000), (10000, 10000), (9000, 10000))],
            "S5")
        self.assertEqual(kept, [])
        self.assertIn("lies outside the slab's outline", report)

    def test_two_voids_that_overlap_keep_the_first(self):
        overlapping = ring((1500, 1500), (2500, 1500), (2500, 2500),
                           (1500, 2500))
        place_it, kept, report = self.check(_SQUARE, [_VOID, overlapping], "S6")
        self.assertTrue(place_it)
        self.assertEqual(kept, [0])
        self.assertIn("crosses opening 1", report)

    def test_two_voids_drawn_to_the_same_line_keep_the_first(self):
        neighbour = ring((2000, 1000), (3000, 1000), (3000, 2000), (2000, 2000))
        _p, kept, report = self.check(_SQUARE, [_VOID, neighbour], "S7")
        self.assertEqual(kept, [0])
        self.assertIn("shares an edge with opening 1", report)

    def test_a_void_inside_another_void_is_not_cut(self):
        island = ring((1200, 1200), (1800, 1200), (1800, 1800), (1200, 1800))
        _p, kept, report = self.check(_SQUARE, [_VOID, island], "S8")
        self.assertEqual(kept, [0])
        self.assertIn("sits inside opening 1", report)

    def test_a_void_carrying_a_z_is_read_rather_than_crashed_on(self):
        # `fold_plan` can hand an opening the z its hatch was read at, and a
        # verdict is what the caller asked for -- not an unpacking error
        self.assertEqual(
            self.check(_SQUARE, [[(x, y, 0.0) for x, y in _VOID]], "S9Z"),
            (True, [0], None))

    def test_a_void_that_is_itself_malformed_is_not_cut(self):
        _p, kept, report = self.check(
            _SQUARE, [ring((1000, 1000), (2000, 1000))], "S9")
        self.assertEqual(kept, [])
        self.assertIn("fewer than three", report)


class TheOutlineIsPlacedWhenOnlyItsVoidsAreBad(unittest.TestCase):
    """The fallback, and the sentence that is the price of it.

    The outline is the concrete: it carries the mark, the thickness and the
    type, and the schedules count it. A void left uncut is extra concrete over
    a stair -- visible on the first section, one boundary edit to fix -- where a
    refused slab is a floor that simply is not there and that nobody can see is
    missing. So the outline goes in, and the report says which void did not.
    """

    def setUp(self):
        self.check = _pure()["check_profile"]

    def test_the_slab_still_goes_in(self):
        place_it, kept, report = self.check(
            _SQUARE, [ring((0, 1000), (2000, 1000), (2000, 2000), (0, 2000))],
            "S10")
        self.assertTrue(place_it)
        self.assertEqual(kept, [])
        self.assertIn("placed WITHOUT 1 of its 1 opening(s)", report)

    def test_the_good_voids_survive_the_bad_one(self):
        bad = ring((0, 3000), (2000, 3000), (2000, 3500), (0, 3500))
        place_it, kept, report = self.check(_SQUARE, [_VOID, bad], "S11")
        self.assertTrue(place_it)
        self.assertEqual(kept, [0])
        self.assertIn("opening 2 NOT cut", report)
        self.assertNotIn("opening 1 NOT cut", report)

    def test_a_bad_outline_takes_the_whole_slab_with_it(self):
        # nothing to fall back ON: there is no sound concrete here
        place_it, kept, report = self.check(
            ring((0, 0), (5000, 4000), (5000, 0), (0, 4000)), [_VOID], "S12")
        self.assertFalse(place_it)
        self.assertEqual(kept, [])
        self.assertIn("profile DECLINED", report)

    def test_a_clean_profile_says_nothing_at_all(self):
        self.assertEqual(self.check(_SQUARE, [], "S13"), (True, [], None))


class TheReportNamesTheGeometry(unittest.TestCase):
    """"errors: 1" and a stack is what the owner got. This is the difference.

    A message the next Revit run cannot act on is a message worth nothing, so
    every refusal carries the mark (or the ground the bay stands on), how many
    corners the offending ring has, how big it is, where its centre is -- all in
    the millimetres the project is measured in -- and which rule it broke.
    """

    def setUp(self):
        self.check = _pure()["check_profile"]

    def test_a_marked_slab_is_named_by_its_mark(self):
        report = self.check(ring((0, 0), (5000, 0)), [], "S3A")[2]
        self.assertTrue(report.startswith("S3A: "), report)

    def test_an_unmarked_slab_is_named_by_where_it_stands(self):
        report = self.check(ring((10000, 20000), (15000, 20000)), [], None)[2]
        self.assertIn("the unmarked bay at (12500, 20000) mm", report)

    def test_the_offending_ring_is_sized_and_placed_in_millimetres(self):
        report = self.check(
            ring((0, 0), (5000, 4000), (5000, 0), (0, 4000)), [], "S14")[2]
        self.assertIn("4 corner(s), 5000 x 4000 mm, centred at (2500, 2000) mm",
                      report)

    def test_the_rule_that_was_broken_is_spelled_out(self):
        report = self.check(
            ring((0, 0), (5000, 4000), (5000, 0), (0, 4000)), [], "S15")[2]
        self.assertIn("it crosses or touches itself", report)

    def test_the_paragraph_is_line_per_refusal(self):
        # _say_error wraps EACH LINE on its own (v0.81.1), so a paragraph is
        # safe -- and a slab with two bad voids should read as two lines
        bad_one = ring((0, 3000), (2000, 3000), (2000, 3500), (0, 3500))
        bad_two = ring((3000, 0), (4000, 0), (4000, 1000), (3000, 1000))
        report = self.check(_SQUARE, [bad_one, bad_two], "S16")[2]
        lines = report.split("\n")
        self.assertEqual(len(lines), 3, report)
        self.assertTrue(lines[1].startswith("- opening 1 NOT cut:"), report)
        self.assertTrue(lines[2].startswith("- opening 2 NOT cut:"), report)


class TheSliverBayFromTest14(unittest.TestCase):
    """The failure reproduced from a fixture, and why the old guard missed it.

    test14 draws three 700 x 10 mm slivers on its slab-edge layer. Four raw
    corners, so `len(ring) < 3` said nothing; then `_sanitize_ring` merges the
    10 mm sides -- they are under `_MIN_EDGE_FT` -- and hands `_curve_loop` two
    points, which walk out as a line and a line back. That is a profile Revit
    cannot compose, arriving at Floor.Create with the guard satisfied: the
    shape of the owner's one-error run.

    The check therefore reads the SANITIZED ring, because that is the point
    list the builder actually walks.
    """

    def test_the_sliver_is_declined_where_the_length_guard_passed_it(self):
        pure = _pure()
        sliver = ring((127910.1, 39208.9), (128610.1, 39208.9),
                      (128610.1, 39218.9), (127910.1, 39218.9))
        self.assertEqual(len(sliver), 4)            # the old guard's answer
        self.assertEqual(len(pure["_sanitize_ring"](sliver)), 2)
        place_it, _kept, report = pure["check_profile"](sliver, [], None)
        self.assertFalse(place_it)
        self.assertIn("fewer than three distinct corners", report)


class TheCheckRunsBeforeRevitDoes(unittest.TestCase):
    """The wiring, pinned statically: no offline harness can run place_slabs.

    Each link fails QUIETLY if cut. Move the call after Floor.Create and Revit
    throws first, which is the bug. Drop the append and the run goes silent
    about a slab it did not build. Turn the decline into a raise and one bad
    outline costs the storey.
    """

    def setUp(self):
        self.source = _source()
        self.node = _function("place_slabs")

    def _calls(self, name):
        found = []
        for inner in ast.walk(self.node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = (func.id if isinstance(func, ast.Name)
                      else getattr(func, "attr", None))
            if called == name:
                found.append(inner)
        return found

    def test_check_profile_is_called_and_before_every_floor_create(self):
        checks = self._calls("check_profile")
        creates = [call for call in self._calls("Create")
                   if getattr(call.func.value, "id", None) == "Floor"]
        self.assertEqual(len(checks), 1, "one check, at the top of the loop")
        self.assertTrue(creates, "place_slabs no longer calls Floor.Create")
        for create in creates:
            self.assertLess(checks[0].lineno, create.lineno)

    def test_the_report_goes_out_on_the_red_error_channel(self):
        # run_builders calls _say_error for every entry in result["errors"]
        # and _say for every entry in result["skipped"]: only the first is red
        segment = ast.get_source_segment(self.source, self.node)
        self.assertIn('result["errors"].append(report)', segment)

    def test_a_declined_profile_continues_the_loop_rather_than_raising(self):
        guards = [node for node in ast.walk(self.node)
                  if isinstance(node, ast.If)
                  and isinstance(node.test, ast.UnaryOp)
                  and isinstance(node.test.op, ast.Not)
                  and isinstance(node.test.operand, ast.Name)
                  and node.test.operand.id == "place_it"]
        self.assertEqual(len(guards), 1, "no `if not place_it:` guard")
        self.assertEqual([type(stmt) for stmt in guards[0].body],
                         [ast.Continue])

    def test_only_the_openings_the_check_kept_are_cut(self):
        segment = ast.get_source_segment(self.source, self.node)
        self.assertIn("holes = [holes[index] for index in kept]", segment)


class TheCheckStaysRevitFree(unittest.TestCase):
    """Nothing `check_profile` reaches may name a Revit import.

    This is not tidiness. It is the only reason the rules above can be tested
    at all: `builders/slabs.py` imports Autodesk.Revit.DB at module level, so
    the suite reads its functions out of the source and exec's them with
    nothing but `config` in scope. One Revit name inside the call graph and
    every rule test turns into a wiring assertion.
    """

    def _revit_names(self, tree):
        names = set(["mm_to_internal"])
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and (
                    node.module.startswith("Autodesk")
                    or node.module.startswith("System")):
                names.update(alias.asname or alias.name
                             for alias in node.names)
        return names

    def _reached_from(self, tree, start):
        """Every module-level function `start` can reach, by name."""
        functions = dict((node.name, node) for node in tree.body
                         if isinstance(node, ast.FunctionDef))
        seen, pending = set(), [start]
        while pending:
            name = pending.pop()
            if name in seen or name not in functions:
                continue
            seen.add(name)
            for inner in ast.walk(functions[name]):
                if isinstance(inner, ast.Call):
                    called = (inner.func.id if isinstance(inner.func, ast.Name)
                              else getattr(inner.func, "attr", None))
                    if called:
                        pending.append(called)
        return seen

    def test_the_call_graph_names_no_revit_symbol(self):
        tree = ast.parse(_source())
        revit = self._revit_names(tree)
        self.assertIn("Floor", revit, "the Revit import list stopped parsing")
        functions = dict((node.name, node) for node in tree.body
                         if isinstance(node, ast.FunctionDef))
        offenders = []
        for name in sorted(self._reached_from(tree, "check_profile")):
            for inner in ast.walk(functions[name]):
                if isinstance(inner, ast.Name) and inner.id in revit:
                    offenders.append("{0}: {1}".format(name, inner.id))
        self.assertEqual(offenders, [],
                         "the profile check can no longer be tested offline: "
                         "%s" % offenders)

    def test_the_whole_graph_is_reachable_from_check_profile(self):
        # a rule that nothing calls is a rule that does not run
        reached = self._reached_from(ast.parse(_source()), "check_profile")
        for name in ("_ring_faults", "_hole_against_outline", "_contact",
                     "_shared_run_ft", "_segments_cross", "_seg_seg_distance",
                     "_sanitize_ring", "_point_in_ring", "_ring_note",
                     "_slab_name"):
            self.assertIn(name, reached)


if __name__ == "__main__":
    unittest.main()
