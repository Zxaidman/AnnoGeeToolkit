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


if __name__ == "__main__":
    unittest.main()
