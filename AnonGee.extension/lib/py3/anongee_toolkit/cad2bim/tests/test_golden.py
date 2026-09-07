# -*- coding: utf-8 -*-
"""_golden -- the compare step the regression legs are built on.

Three regression harnesses were lost because they lived in a scratchpad and were
never committed: the stored slab fingerprints, the 17-DXF sweep and the
storey/roof replays. Without them "no regressions" is an assertion, not a
measurement. They are being rebuilt as committed code, and all three reduce to
the same move: compute numbers over a fixed corpus, compare them against a
stored baseline, and say precisely what moved.

That compare is the part with logic in it, so it is the part with tests. A
golden-file harness whose baseline is written by the same run it is checked
against proves nothing on its own -- what has to be proved is that a real change
is CAUGHT, and named well enough to act on. Standalone (no Revit).
"""

import os
import shutil
import tempfile
import unittest

# _golden lives beside the tests, not inside the package, so it is a plain
# import -- _loader is for cad2bim modules, which cannot be imported by name.
import _golden


class Differences(unittest.TestCase):
    def test_identical_numbers_report_nothing(self):
        data = {"Test1": {"rects": 61, "beams": 141}}
        self.assertEqual(_golden.differences(data, dict(data)), [])

    def test_a_moved_number_is_named_with_both_values(self):
        before = {"Test1": {"rects": 61, "beams": 141}}
        after = {"Test1": {"rects": 63, "beams": 141}}
        found = _golden.differences(before, after)
        self.assertEqual(len(found), 1)
        self.assertIn("Test1", found[0])
        self.assertIn("rects", found[0])
        self.assertIn("61", found[0])
        self.assertIn("63", found[0])

    def test_every_moved_number_is_reported_not_just_the_first(self):
        before = {"Test1": {"rects": 61, "beams": 141},
                  "Test2": {"rects": 20, "beams": 30}}
        after = {"Test1": {"rects": 62, "beams": 140},
                 "Test2": {"rects": 20, "beams": 31}}
        self.assertEqual(len(_golden.differences(before, after)), 3)

    def test_a_fixture_that_vanished_is_reported(self):
        found = _golden.differences({"Test1": {"rects": 1}}, {})
        self.assertEqual(len(found), 1)
        self.assertIn("Test1", found[0])

    def test_a_fixture_that_appeared_is_reported(self):
        found = _golden.differences({}, {"Test9": {"rects": 1}})
        self.assertEqual(len(found), 1)
        self.assertIn("Test9", found[0])

    def test_a_metric_that_vanished_is_reported(self):
        found = _golden.differences({"Test1": {"rects": 1, "beams": 2}},
                                    {"Test1": {"rects": 1}})
        self.assertEqual(len(found), 1)
        self.assertIn("beams", found[0])

    def test_the_report_is_ordered_so_two_runs_read_the_same(self):
        before = {"B": {"y": 1, "x": 1}, "A": {"x": 1}}
        after = {"B": {"y": 2, "x": 2}, "A": {"x": 2}}
        self.assertEqual(_golden.differences(before, after),
                         _golden.differences(before, after))
        self.assertTrue(_golden.differences(before, after)[0].startswith("A"))

    def test_a_float_that_only_LOOKS_different_is_not_a_change(self):
        # areas are rounded before they are stored; 9.0 read back from JSON must
        # not read as a move against 9
        self.assertEqual(_golden.differences({"T": {"area": 9.0}},
                                             {"T": {"area": 9}}), [])


class Storing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "sample.json")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_missing_baseline_loads_as_nothing_rather_than_raising(self):
        self.assertIsNone(_golden.load(self.path))

    def test_what_is_saved_is_what_is_loaded(self):
        data = {"Test1": {"rects": 61, "areas": [1.5, 2.5]}}
        _golden.save(self.path, data)
        self.assertEqual(_golden.load(self.path), data)

    def test_a_saved_baseline_is_readable_by_a_human_and_stable_in_git(self):
        _golden.save(self.path, {"B": {"y": 1}, "A": {"x": 2}})
        with open(self.path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("\n", text)                    # indented, not one line
        self.assertLess(text.index('"A"'), text.index('"B"'))   # sorted keys
        self.assertTrue(text.endswith("\n"))         # no no-newline-at-EOF diffs

    def test_saving_creates_the_baselines_folder_if_it_is_not_there_yet(self):
        nested = os.path.join(self.folder, "deeper", "still", "sample.json")
        _golden.save(nested, {"A": {"x": 1}})
        self.assertEqual(_golden.load(nested), {"A": {"x": 1}})


class TheGatePrintsEveryNumberThatMoved(unittest.TestCase):
    """`differences()` naming all eight is no use if the runner shows one.

    It printed the traceback's LAST line, which is the last moved number and
    nothing above it. A sweep run reported `foundation_profiles: 0 -> 73` on its
    own while the failure it came from also held `foundation_planned: 0 -> 73` --
    two changes, one shown, and the hidden one would have been blessed unread.
    """

    def setUp(self):
        import run_regressions
        self.runner = run_regressions

    def _trace(self, *moved):
        # the shape unittest produces for assertEqual(moved, [], msg)
        return ("Traceback (most recent call last):\n"
                "  File \"regression_dxf_sweep.py\", line 446, in test_it\n"
                "    self.assertEqual(moved, [], ...)\n"
                "AssertionError: Lists differ: [...] != []\n"
                "\n+ []\n- [...] : the DXF sweep moved:\n  "
                + "\n  ".join(moved))

    def test_every_moved_number_is_printed_not_only_the_last(self):
        lines = self.runner._moved_lines(self._trace(
            "Test16.foundation_planned: 0 -> 73",
            "Test16.foundation_profiles: 0 -> 73"))
        self.assertEqual(lines, ["Test16.foundation_planned: 0 -> 73",
                                 "Test16.foundation_profiles: 0 -> 73"])

    def test_the_unittest_list_diff_above_the_message_is_left_out(self):
        lines = self.runner._moved_lines(self._trace("Test1.beams: 8 -> 9"))
        self.assertEqual(lines, ["Test1.beams: 8 -> 9"])

    def test_a_very_long_diff_is_capped_and_says_how_many_it_hid(self):
        moved = ["Test{0}.beams: 1 -> 2".format(n) for n in range(70)]
        lines = self.runner._moved_lines(self._trace(*moved), cap=60)
        self.assertEqual(len(lines), 61)
        self.assertEqual(lines[-1], "... and 10 more")

    def test_an_error_with_no_diff_still_shows_its_last_line(self):
        trace = ("Traceback (most recent call last):\n"
                 "  File \"x.py\", line 1, in test_it\n"
                 "ValueError: the reader could not open the fixture")
        self.assertEqual(
            self.runner._moved_lines(trace),
            ["ValueError: the reader could not open the fixture"])


class TheGateSaysHowBigItsCorpusActuallyIs(unittest.TestCase):
    """The leg labels were typed once and then quietly went stale.

    The screen said "29 archived exports", "17 fixture drawings" and "4 storey
    stacks" while the legs were replaying 31, 22 and 7. Nothing failed -- a
    label cannot fail -- which is exactly why it drifted for so long, and a gate
    that misreports the size of its own corpus makes its green line mean less
    than the reader thinks it does. So the size is counted at print time now.
    """

    def setUp(self):
        import run_regressions
        self.runner = run_regressions

    def test_the_size_is_counted_off_the_corpus_not_typed_into_the_label(self):
        import regression_dxf_sweep
        title = self.runner._leg_title(
            "DXF sweep", "regression_dxf_sweep", ("_fixtures", "fixture drawings"))
        self.assertIn("({0} fixture drawings)".format(
            len(regression_dxf_sweep._fixtures())), title)

    def test_every_leg_reports_a_size_so_none_is_silently_uncounted(self):
        for name, module, counts in self.runner.LEGS:
            self.assertIsNotNone(counts, name)
            title = self.runner._leg_title(name, module, counts)
            self.assertRegex(title, r"\(\d+ [a-z ]+\)$", name)

    def test_a_leg_whose_corpus_cannot_be_counted_still_runs_and_reports(self):
        # No archive on this machine, a helper renamed: the leg loses its size,
        # never the run. Dying here would lose the measurement entirely.
        title = self.runner._leg_title(
            "DXF sweep", "regression_dxf_sweep", ("_gone", "fixture drawings"))
        self.assertEqual(title.strip(), "DXF sweep")

    def test_the_labels_line_up_so_the_times_form_a_column(self):
        widths = set()
        for name, module, counts in self.runner.LEGS:
            title = self.runner._leg_title(name, module, counts)
            widths.add(len(title.split("(")[0]))
        self.assertEqual(len(widths), 1, "leg names are not padded alike")


if __name__ == "__main__":
    unittest.main()
