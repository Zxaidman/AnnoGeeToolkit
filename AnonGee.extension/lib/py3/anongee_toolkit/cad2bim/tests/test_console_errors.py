# -*- coding: utf-8 -*-
"""How an error line reaches the console, after the HTML turned out not to work.

The rule (WORK-17) is that an error stands apart from the notes around it, and
for a long time this was done by printing a red-and-bold `<span>` on the belief
that pyRevit's output window renders markup. Under the CPython3 engine it does
not. The owner's console, asked directly whether the line was red or the tag was
showing:

    "about yes bug-24 it shows <span style ..."

-- so every error line on his screen carried the tag instead of the colour, on
exactly the lines that matter most. These hold the plain-text mark that replaced
it, and the escaping that went with it.
"""

import unittest

import _loader


run_console = _loader.load("run_console")


class AnErrorLineIsMarkedNotMarkedUp(unittest.TestCase):

    def setUp(self):
        run_console._OUT._buf = []
        run_console._OUT.live = False
        self.addCleanup(setattr, run_console._OUT, "_buf", [])

    def said(self):
        return list(run_console._OUT._buf)

    def test_no_html_tag_reaches_the_console(self):
        run_console._say_error("slab: profile DECLINED")
        for line in self.said():
            self.assertNotIn("<span", line)
            self.assertNotIn("</span>", line)
            self.assertNotIn("c00000", line)

    def test_the_line_carries_a_mark_so_it_still_stands_apart(self):
        run_console._say_error("slab: profile DECLINED")
        self.assertEqual(self.said(), ["!! slab: profile DECLINED"])

    def test_angle_brackets_in_a_revit_message_survive_intact(self):
        # They were escaped to protect markup that was never interpreted, so a
        # message quoting a Revit string reached the screen as `&lt;`.
        run_console._say_error("Floor.Create failed <null> for A & B > C")
        self.assertEqual(self.said(),
                         ["!! Floor.Create failed <null> for A & B > C"])

    def test_every_line_of_a_paragraph_is_marked_not_only_the_first(self):
        # A Revit exception arrives as message, "Parameter name:", then a stack.
        run_console._say_error("The view is not printable.\n"
                               "Parameter name: pDBView\n"
                               "  at Autodesk.Revit.DB.Document.Link")
        self.assertEqual(self.said(), [
            "!! The view is not printable.",
            "!! Parameter name: pDBView",
            "!!   at Autodesk.Revit.DB.Document.Link"])

    def test_a_blank_line_stays_blank_rather_than_becoming_a_bare_mark(self):
        run_console._say_error("first\n\nsecond")
        self.assertEqual(self.said(), ["!! first", "", "!! second"])

    def test_the_mark_is_one_constant_so_a_reader_can_search_for_it(self):
        run_console._say_error("anything")
        self.assertTrue(self.said()[0].startswith(run_console.ERROR_MARK))

    def test_an_error_is_told_apart_from_an_ordinary_note(self):
        run_console._say_error("errors: 78")
        run_console._say("Slabs -- created: 173")
        marked, plain = self.said()
        self.assertTrue(marked.startswith(run_console.ERROR_MARK))
        self.assertFalse(plain.startswith(run_console.ERROR_MARK))


class ARepeatedSkipIsCountedNotReprinted(unittest.TestCase):
    """test17 printed one sentence about two hundred times in a row.

        step: a fold region of 0.9 m2 sits inside no outline: nothing to step

    -- burying the dozen lines around it that said something different. The
    console is the only account of what a run did, and a page of one repeated
    sentence is not an account.
    """

    def setUp(self):
        run_console._OUT._buf = []
        run_console._OUT.live = False
        self.addCleanup(setattr, run_console._OUT, "_buf", [])

    def said(self):
        return list(run_console._OUT._buf)

    def test_two_hundred_of_one_sentence_become_one_line(self):
        run_console._say_each("  step: ", ["no outline"] * 200)
        self.assertEqual(self.said(), ["  step: no outline  [x200]"])

    def test_a_message_said_once_carries_no_count(self):
        run_console._say_each("  step: ", ["just the one"])
        self.assertEqual(self.said(), ["  step: just the one"])

    def test_distinct_messages_all_survive(self):
        run_console._say_each("  x: ", ["a", "b", "a", "c", "b", "a"])
        self.assertEqual(self.said(),
                         ["  x: a  [x3]", "  x: b  [x2]", "  x: c"])

    def test_the_order_is_the_order_they_happened_in(self):
        # Not sorted by how often: the console is read as the run's story.
        run_console._say_each("", ["rare", "common", "common", "common"])
        self.assertEqual(self.said(), ["rare", "common  [x3]"])

    def test_nothing_to_say_says_nothing(self):
        run_console._say_each("  step: ", [])
        run_console._say_each("  step: ", None)
        self.assertEqual(self.said(), [])

    def test_the_prefix_is_on_every_line(self):
        run_console._say_each("  sunk (slabs): ", ["one", "two"])
        for line in self.said():
            self.assertTrue(line.startswith("  sunk (slabs): "), line)


class ACategoryThatBuiltNothingOpensTheConsole(unittest.TestCase):
    """The rule was in `finish`'s docstring and never in its code.

    It checked errors and rollbacks and nothing else, so the owner's test17
    built ZERO slabs on all sixteen storeys, reported 0 errors and 0 skips, and
    ended in silence. He found it by looking at the model.

    An outcome only exists when the user ticked that category -- `script.py`
    builds each behind `if selections["create_..."]` -- so an outcome that
    created nothing IS one that was asked for and produced nothing.
    """

    def setUp(self):
        out = run_console._OUT
        out._buf, out.live, out.failed, out.empty = [], False, False, []
        self.addCleanup(setattr, out, "_buf", [])
        self.addCleanup(setattr, out, "failed", False)
        self.addCleanup(setattr, out, "empty", [])

    def finish(self, outcomes):
        """`finish`, with the flush caught. Returns what it would have printed.

        A failed run FLUSHES, which prints -- so a test that does not catch it
        writes the run's log into the test output.
        """
        import contextlib, io
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            run_console._OUT.finish(outcomes)
        return printed.getvalue()

    def test_a_category_that_created_nothing_is_a_failed_run(self):
        self.finish({"slabs": {"created": 0, "skipped": 0, "errors": 0}})
        self.assertTrue(run_console._OUT.failed)
        self.assertEqual(run_console._OUT.empty, ["slabs"])

    def test_the_run_that_built_everything_stays_silent(self):
        run_console._OUT.say("a line nobody should see")  # buffered, not printed
        self.finish({"slabs": {"created": 173, "errors": 0},
                     "beams": {"created": 969, "errors": 0}})
        self.assertFalse(run_console._OUT.failed)
        self.assertEqual(run_console._OUT._buf, [])

    def test_it_reaches_into_a_multi_storey_run(self):
        # test17's real shape: the outcomes nest one level per storey.
        self.finish({
            "1ST FLOOR": {"slabs": {"created": 0, "skipped": 0, "errors": 0},
                          "beams": {"created": 104, "errors": 0}}})
        self.assertTrue(run_console._OUT.failed)
        self.assertEqual(run_console._OUT.empty, ["slabs"])

    def test_the_log_names_which_category_was_empty(self):
        # A failed run FLUSHES, so the words land on stdout, not in the buffer.
        printed = self.finish({"slabs": {"created": 0, "errors": 0},
                               "walls": {"created": 0, "errors": 0}})
        self.assertIn("NOTHING WAS BUILT for: slabs, walls", printed)

    def test_a_category_nobody_asked_for_is_not_judged(self):
        # No tick, no outcome, no complaint.
        self.finish({"beams": {"created": 12, "errors": 0}})
        self.assertFalse(run_console._OUT.failed)

    def test_a_dict_that_counts_nothing_is_not_a_category(self):
        # Detail dicts and tallies ride inside outcomes; only `created` counts.
        self.finish({"beams": {"created": 12, "errors": 0,
                               "status_counts": {"rect": 0}}})
        self.assertFalse(run_console._OUT.failed)

    def test_a_count_it_cannot_read_is_not_called_a_failure(self):
        self.finish({"slabs": {"created": None, "errors": 0}})
        self.assertTrue(run_console._OUT.failed)   # None reads as zero built
        run_console._OUT.failed, run_console._OUT.empty = False, []
        self.finish({"slabs": {"created": "many", "errors": 0}})
        self.assertFalse(run_console._OUT.failed)


if __name__ == "__main__":
    unittest.main()
