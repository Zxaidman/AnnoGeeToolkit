# -*- coding: utf-8 -*-
"""The log that lets a failure be reported in one line.

Seven features land in one release for a single test session. The thing that
makes that survivable is not that they work -- it is that when one does not,
the person pressing the button can say WHICH and the reply can be a fix rather
than a question.

So the checks here are about **loudness**, not about formatting:

* a failure names the feature that owns it, and the tag is one a person can
  quote;
* the full traceback lands in a file, because a traceback in a dialog is one
  nobody can copy out of;
* nothing in this module can itself throw. A logger that raises inside an
  error handler turns a bad press into a lost session.
"""

import ast
import io
import os
import shutil
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "AnonGee.extension", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from anongee_filterrules import diagnostics                       # noqa: E402
from anongee_filterrules import report as renderer                # noqa: E402

_BUTTON = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                       "FilterViewManager.pushbutton")
_SCRIPT = os.path.join(_BUTTON, "script.py")
_PROVIDER = os.path.join(_ROOT, "AnonGee.extension", "lib",
                         "anongee_filterpane", "provider.py")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


class LogTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.previous = os.environ.get("ANONGEE_PREFS_DIR")
        os.environ["ANONGEE_PREFS_DIR"] = self.folder
        diagnostics._session[0] = False

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("ANONGEE_PREFS_DIR", None)
        else:
            os.environ["ANONGEE_PREFS_DIR"] = self.previous
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_log_sits_beside_the_rules(self):
        self.assertEqual(os.path.dirname(diagnostics.log_path()), self.folder)

    def test_an_entry_can_be_read_back(self):
        diagnostics.record("FEAT-11", "applied to 3 views")
        self.assertTrue(any("applied to 3 views" in line
                            for line in diagnostics.recent()))

    def test_a_traceback_is_kept_whole(self):
        """The one thing a status bar cannot hold and a bug report needs."""
        diagnostics.record("UI", "broke", "Traceback:\\n  line 1\\n  line 2")
        text = "\\n".join(diagnostics.recent())
        self.assertIn("line 1", text)
        self.assertIn("line 2", text)

    def test_entries_survive_across_sessions(self):
        """Yesterday's run is usually what explains today's."""
        diagnostics.record("UI", "yesterday")
        diagnostics.banner("9.9.9")
        self.assertTrue(any("yesterday" in line for line in diagnostics.recent()))

    def test_the_banner_is_written_once_per_session(self):
        diagnostics.banner("9.9.9")
        diagnostics.banner("9.9.9")
        starts = [line for line in diagnostics.recent() if "session start" in line]
        self.assertEqual(len(starts), 1)

    def test_a_long_log_is_trimmed_at_the_start_of_a_session(self):
        for index in range(diagnostics.KEEP_LINES + 200):
            diagnostics.record("UI", "line {0}".format(index))
        diagnostics.banner("9.9.9")
        kept = diagnostics.recent(diagnostics.KEEP_LINES * 2)
        self.assertLessEqual(len(kept), diagnostics.KEEP_LINES + 5)
        self.assertTrue(any("line {0}".format(diagnostics.KEEP_LINES + 199) in line
                            for line in kept), "the newest entries were trimmed")

    def test_clear_empties_it(self):
        diagnostics.record("UI", "something")
        self.assertTrue(diagnostics.clear())
        self.assertEqual(diagnostics.recent(), [])

    def test_reading_a_log_that_is_not_there_is_not_an_error(self):
        self.assertEqual(diagnostics.recent(), [])


class LoudnessTests(unittest.TestCase):
    """What the user actually sees."""

    def test_a_failure_names_the_feature_that_owns_it(self):
        try:
            {}["families"]
        except Exception as error:
            said = diagnostics.failure("FEAT-11", "apply to several views", error)
        self.assertIn("[FEAT-11]", said)
        self.assertIn("apply to several views", said)

    def test_a_failure_says_what_went_wrong_and_not_just_that_it_did(self):
        """"Could not apply" is the message this module exists to stop."""
        try:
            {}["families"]
        except Exception as error:
            said = diagnostics.failure("FEAT-11", "apply", error)
        self.assertIn("KeyError", said)
        self.assertIn("families", said)

    def test_a_failure_says_where_the_rest_of_it_is(self):
        try:
            raise ValueError("nope")
        except Exception as error:
            said = diagnostics.failure("UI", "something", error)
        self.assertIn(diagnostics.LOG_NAME, said)

    def test_the_headline_is_short_enough_for_a_status_bar(self):
        """The tag alone, not the tag plus its long name -- "[FEAT-11 apply to
        several views] apply to several views failed" is a sentence that makes
        a status bar useless."""
        said = diagnostics.headline("FEAT-11", "apply to several views failed")
        self.assertTrue(said.startswith("[FEAT-11]"))
        self.assertNotIn("[FEAT-11 ", said)

    def test_the_exception_type_survives(self):
        """``KeyError: 'families'`` and ``AttributeError: 'NoneType'`` read
        identically once the type is dropped, and the type is usually the half
        that says which bug it is."""
        self.assertIn("ValueError", diagnostics.describe(ValueError("x")))
        self.assertIn("AttributeError", diagnostics.describe(AttributeError()))

    def test_every_tag_has_a_name_a_person_would_recognise(self):
        """A bare "FEAT-19" in a log tells the reader nothing."""
        for tag, name in diagnostics.FEATURES.items():
            self.assertTrue(name.strip(), tag)
            self.assertIn(tag, diagnostics.label(tag))
            self.assertIn(name, diagnostics.label(tag))


class NeverRaisesTests(unittest.TestCase):
    """A logger that throws inside an error handler loses the session."""

    def setUp(self):
        self.previous = os.environ.get("ANONGEE_PREFS_DIR")
        # A path whose parent is a regular FILE: makedirs cannot create a
        # directory inside a file, so every write below genuinely fails.
        self.folder = tempfile.mkdtemp()
        blocker = os.path.join(self.folder, "blocker")
        handle = open(blocker, "w")
        handle.write("not a directory")
        handle.close()
        os.environ["ANONGEE_PREFS_DIR"] = os.path.join(blocker, "inside")

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("ANONGEE_PREFS_DIR", None)
        else:
            os.environ["ANONGEE_PREFS_DIR"] = self.previous
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_recording_into_an_unwritable_place_is_silent(self):
        self.assertEqual(diagnostics.record("UI", "anything"), "")

    def test_a_failure_still_returns_something_to_show_the_user(self):
        """The log is the nice-to-have. The sentence in front of the user is
        not, and it must survive the log being unwritable."""
        said = diagnostics.failure("UI", "something", ValueError("nope"))
        self.assertIn("[UI]", said)
        self.assertIn("nope", said)

    def test_reading_and_clearing_are_silent(self):
        self.assertEqual(diagnostics.recent(), [])
        diagnostics.clear()

    def test_describe_survives_an_exception_that_cannot_be_printed(self):
        class Awkward(Exception):
            def __str__(self):
                raise RuntimeError("cannot be printed")
        self.assertTrue(diagnostics.describe(Awkward()))


class TimelineTests(unittest.TestCase):
    """FEAT-21. What happened, not only what raised.

    The two bugs that shipped in 0.6.0 both raised NOTHING. The view picker
    was the loud kind and was fixed from a single screenshot; the live count
    sat on "counting..." for a whole release because a timer that never ticks
    throws nothing at all. A record that holds only exceptions cannot show the
    second kind, and the second kind is the expensive kind.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.previous = os.environ.get("ANONGEE_PREFS_DIR")
        os.environ["ANONGEE_PREFS_DIR"] = self.folder
        diagnostics.reset()

    def tearDown(self):
        diagnostics.reset()
        if self.previous is None:
            os.environ.pop("ANONGEE_PREFS_DIR", None)
        else:
            os.environ["ANONGEE_PREFS_DIR"] = self.previous
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_an_action_lands_with_the_feature_that_owns_it(self):
        diagnostics.step("FEAT-11", "Apply to views")
        rows = diagnostics.timeline()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tag"], "FEAT-11")
        self.assertEqual(rows[0]["action"], "Apply to views")
        self.assertEqual(rows[0]["outcome"], diagnostics.OK)

    def test_facts_travel_beside_the_action(self):
        diagnostics.step("FEAT-8", "counted", matched=18, of_model=24)
        self.assertEqual(diagnostics.timeline()[0]["data"],
                         [("matched", "18"), ("of_model", "24")])

    def test_a_round_trip_is_open_until_it_is_answered(self):
        ticket = diagnostics.begin("UI", "reading the model")
        self.assertEqual(diagnostics.timeline()[0]["outcome"],
                         diagnostics.OPEN)
        self.assertTrue(diagnostics.finish(ticket))
        self.assertEqual(diagnostics.timeline()[0]["outcome"], diagnostics.OK)

    def test_an_answered_round_trip_says_how_long_it_took(self):
        diagnostics.finish(diagnostics.begin("UI", "reading the model"))
        self.assertIsNotNone(diagnostics.timeline()[0]["ms"])

    def test_a_request_that_never_came_back_is_findable(self):
        """THE bug of 0.6.0, in the one shape a log can show it."""
        diagnostics.finish(diagnostics.begin("UI", "answered"))
        diagnostics.begin("FEAT-8", "the live count")
        silent = diagnostics.unanswered()
        self.assertEqual([one["action"] for one in silent], ["the live count"])

    def test_closing_a_ticket_nobody_opened_is_not_an_error(self):
        self.assertFalse(diagnostics.finish(9999))

    def test_an_answer_that_arrives_twice_is_survivable(self):
        """Worth surviving rather than crashing the window over."""
        ticket = diagnostics.begin("UI", "reading the model")
        self.assertTrue(diagnostics.finish(ticket))
        self.assertFalse(diagnostics.finish(ticket))
        self.assertEqual(len(diagnostics.timeline()), 1)

    def test_a_failure_is_on_the_timeline_as_well_as_in_the_log(self):
        diagnostics.failure("FEAT-11", "reading the views",
                            KeyError("families"), "a traceback")
        row = diagnostics.timeline()[0]
        self.assertEqual(row["outcome"], diagnostics.FAILED)
        self.assertIn("families", row["cause"])
        self.assertEqual(row["detail"], "a traceback")

    def test_repeats_fold_into_one_row(self):
        """Seventeen keystrokes are one thing a person did."""
        for text in ("s", "st", "str"):
            diagnostics.step("UI", "Category search", text=text)
        rows = diagnostics.timeline()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["repeat"], 3)

    def test_a_folded_row_keeps_the_LAST_of_the_facts(self):
        for text in ("s", "st", "str"):
            diagnostics.step("UI", "Category search", text=text)
        self.assertEqual(diagnostics.timeline()[0]["data"], [("text", "str")])

    def test_two_of_the_same_failure_are_two_rows(self):
        """One failure and two are different reports."""
        for _ in range(2):
            diagnostics.failure("UI", "saving", IOError("denied"))
        self.assertEqual(len(diagnostics.timeline()), 2)

    def test_two_refusals_in_a_row_stay_two_rows(self):
        """The reachable half of the same rule as the failure above.

        ``failure()`` pushes its own entry and never reaches the folding at
        all, so only a refusal can actually exercise the guard -- which is why
        this test exists beside that one rather than instead of it.
        """
        for _ in range(2):
            diagnostics.step("FEAT-13", "convert", outcome=diagnostics.REFUSED)
        self.assertEqual(len(diagnostics.timeline()), 2)

    def test_an_open_round_trip_never_folds(self):
        """Its ticket has to stay findable, and it is still waiting."""
        diagnostics.begin("FEAT-8", "the live count")
        diagnostics.begin("FEAT-8", "the live count")
        self.assertEqual(len(diagnostics.timeline()), 2)

    def test_a_different_action_does_not_fold_into_the_one_above(self):
        diagnostics.step("UI", "Count")
        diagnostics.step("UI", "Apply")
        self.assertEqual(len(diagnostics.timeline()), 2)

    def test_the_log_still_gets_every_one_of_them(self):
        """The timeline is the readable record. The log is the raw one."""
        for text in ("s", "st", "str"):
            diagnostics.step("UI", "Category search", text=text)
        lines = [line for line in diagnostics.recent()
                 if "Category search" in line]
        self.assertEqual(len(lines), 3)

    def test_the_timeline_cannot_grow_without_end(self):
        """A day inside Revit must not become a memory leak."""
        for index in range(diagnostics.MAX_ACTIONS + 50):
            diagnostics.step("UI", "press {0}".format(index))
        self.assertEqual(len(diagnostics.timeline()),
                         diagnostics.MAX_ACTIONS)

    def test_trimming_keeps_the_NEWEST(self):
        """What is being reported is almost always at the end."""
        for index in range(diagnostics.MAX_ACTIONS + 5):
            diagnostics.step("UI", "press {0}".format(index))
        last = diagnostics.timeline()[-1]["action"]
        self.assertEqual(last, "press {0}".format(
            diagnostics.MAX_ACTIONS + 4))

    def test_a_trimmed_ticket_cannot_resurrect_its_row(self):
        """A late answer to a request that has scrolled off must no-op, not
        put a row back into a timeline that no longer holds it."""
        ticket = diagnostics.begin("UI", "the first one")
        for index in range(diagnostics.MAX_ACTIONS + 5):
            diagnostics.step("UI", "press {0}".format(index))
        self.assertFalse(diagnostics.finish(ticket))
        self.assertEqual(len(diagnostics.timeline()),
                         diagnostics.MAX_ACTIONS)

    def test_the_tallies_lead_with_the_feature_carrying_the_trouble(self):
        for _ in range(5):
            diagnostics.step("UI", "Count")
        diagnostics.failure("FEAT-13", "converting", ValueError("no"))
        self.assertEqual(diagnostics.counters()[0][0], "FEAT-13")

    def test_an_unanswered_request_counts_against_its_feature(self):
        diagnostics.begin("FEAT-8", "the live count")
        self.assertEqual(diagnostics.counters()[0], ("FEAT-8", 1, 1))

    def test_a_note_keeps_the_order_it_was_learned_in(self):
        diagnostics.note("Revit", "2025.3")
        diagnostics.note("document", "CH-Tower.rvt")
        self.assertEqual([key for key, _ in diagnostics.notes()],
                         ["Revit", "document"])

    def test_a_note_written_twice_keeps_the_last_value_in_place(self):
        diagnostics.note("active view", "Level 1")
        diagnostics.note("Revit", "2025.3")
        diagnostics.note("active view", "Level 2")
        self.assertEqual(diagnostics.notes(),
                         [("active view", "Level 2"), ("Revit", "2025.3")])

    def test_a_finding_is_not_a_failure_and_is_kept_apart(self):
        """Nothing raised. The tool just did the wrong thing quietly."""
        diagnostics.finding("FEAT-8", "the view is hiding six of them")
        self.assertEqual(len(diagnostics.findings()), 1)
        self.assertEqual(diagnostics.timeline(), [])

    def test_the_same_finding_twice_is_one_finding_that_recurred(self):
        """Counting a rule and then applying it files the identical sentence
        about the identical view. Thirty presses would open the report with
        thirty copies of one paragraph and read as thirty problems."""
        for _ in range(3):
            diagnostics.finding("UI", "the view is hiding six of them")
        found = diagnostics.findings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["seen"], 3)

    def test_two_findings_that_differ_stay_two(self):
        diagnostics.finding("UI", "the view is hiding six")
        diagnostics.finding("PANEL", "the view is hiding six")
        diagnostics.finding("UI", "the view is hiding nine")
        self.assertEqual(len(diagnostics.findings()), 3)

    def test_a_recurring_finding_is_still_logged_every_time(self):
        """The log is the raw stream. How often it recurred is evidence."""
        for _ in range(3):
            diagnostics.finding("UI", "the view is hiding six")
        self.assertEqual(len([line for line in diagnostics.recent()
                              if "FINDING" in line]), 3)

    def test_the_timeline_handed_out_cannot_be_edited_from_outside(self):
        diagnostics.step("UI", "Count")
        diagnostics.timeline()[0]["action"] = "something else"
        self.assertEqual(diagnostics.timeline()[0]["action"], "Count")

    def test_a_value_with_a_newline_in_it_stays_on_one_line(self):
        diagnostics.step("UI", "saving", path="C:\\one\ntwo")
        self.assertNotIn("\n", diagnostics.timeline()[0]["data"][0][1])

    def test_a_very_long_value_is_clipped_rather_than_carried_whole(self):
        diagnostics.step("UI", "saving", path="x" * 500)
        self.assertLessEqual(len(diagnostics.timeline()[0]["data"][0][1]), 160)


class GapTests(unittest.TestCase):
    """BUG-20. The view hiding elements from the tool as well as from you.

    ``FilteredElementCollector(doc, view.Id)`` returns only what the view is
    already showing. A rule therefore cannot match an element the view hides,
    the count is smaller than the model holds, and NOTHING about that is an
    error -- which is exactly why it needed saying out loud.
    """

    def test_nothing_to_say_when_the_numbers_agree(self):
        self.assertEqual(diagnostics.gap(18, 18), "")

    def test_nothing_to_say_when_the_view_somehow_has_more(self):
        self.assertEqual(diagnostics.gap(20, 18), "")

    def test_nothing_to_say_when_the_model_was_not_measured(self):
        """None is "not measured", and a diagnostic that guesses is worse
        than one that abstains."""
        self.assertEqual(diagnostics.gap(18, None), "")

    def test_a_gap_names_both_numbers_and_the_difference(self):
        said = diagnostics.gap(18, 24)
        self.assertIn("6 more", said)
        self.assertIn("18 of 24", said)

    def test_a_gap_names_causes_the_user_can_go_and_look_at(self):
        """A diagnostic that says only "some are hidden" has moved the
        problem, not explained it."""
        said = diagnostics.gap(18, 24).lower()
        for cause in ("hide in view", "visibility/graphics", "view filter",
                      "crop", "design option", "workset"):
            self.assertIn(cause, said)

    def test_a_gap_says_the_isolate_cannot_bring_them_back(self):
        self.assertIn("cannot bring", diagnostics.gap(1, 2))

    def test_nonsense_says_nothing_rather_than_raising(self):
        self.assertEqual(diagnostics.gap("eighteen", "twenty"), "")
        self.assertEqual(diagnostics.gap(None, None), "")


class ReportFileTests(unittest.TestCase):
    """FEAT-21. One file, written to be attached whole."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.previous = os.environ.get("ANONGEE_PREFS_DIR")
        os.environ["ANONGEE_PREFS_DIR"] = self.folder
        diagnostics.reset()

    def tearDown(self):
        diagnostics.reset()
        if self.previous is None:
            os.environ.pop("ANONGEE_PREFS_DIR", None)
        else:
            os.environ["ANONGEE_PREFS_DIR"] = self.previous
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_report_sits_beside_the_log(self):
        self.assertEqual(os.path.dirname(diagnostics.report_path()),
                         os.path.dirname(diagnostics.log_path()))

    def test_it_is_a_markdown_file(self):
        self.assertTrue(diagnostics.report_path().endswith(".md"))

    def test_writing_it_returns_where_it_went(self):
        written = diagnostics.write_report()
        self.assertEqual(written, diagnostics.report_path())
        self.assertTrue(os.path.exists(written))

    def test_the_file_holds_the_session_and_not_a_summary_of_it(self):
        diagnostics.banner("0.8.0")
        diagnostics.note("document", "CH-Tower.rvt")
        diagnostics.step("FEAT-11", "Apply to views", views=3)
        diagnostics.failure("FEAT-13", "converting", ValueError("no"))
        diagnostics.finding("FEAT-8", "the view is hiding six of them")
        body = _read(diagnostics.write_report())
        for wanted in ("CH-Tower.rvt", "Apply to views", "converting",
                       "hiding six of them", "0.8.0"):
            self.assertIn(wanted, body)

    def test_a_report_from_a_session_where_nothing_happened_still_writes(self):
        """The session most worth a report is the one that broke early."""
        self.assertTrue(os.path.exists(diagnostics.write_report()))

    def test_it_can_be_written_somewhere_the_user_chose(self):
        target = os.path.join(self.folder, "picked", "mine.md")
        self.assertEqual(diagnostics.write_report(target), target)
        self.assertTrue(os.path.exists(target))

    def test_writing_it_is_recorded_so_the_log_says_one_went_out(self):
        diagnostics.write_report()
        self.assertTrue(any("report written" in line
                            for line in diagnostics.recent()))


class TrackerNeverRaisesTests(unittest.TestCase):
    """Every new entry point obeys the rule the old ones do."""

    def setUp(self):
        self.previous = os.environ.get("ANONGEE_PREFS_DIR")
        self.folder = tempfile.mkdtemp()
        blocker = os.path.join(self.folder, "blocker")
        handle = open(blocker, "w")
        handle.write("not a directory")
        handle.close()
        os.environ["ANONGEE_PREFS_DIR"] = os.path.join(blocker, "inside")
        diagnostics.reset()

    def tearDown(self):
        diagnostics.reset()
        if self.previous is None:
            os.environ.pop("ANONGEE_PREFS_DIR", None)
        else:
            os.environ["ANONGEE_PREFS_DIR"] = self.previous
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_recording_an_action_is_silent(self):
        self.assertTrue(diagnostics.step("UI", "Count") > 0)

    def test_opening_and_closing_a_round_trip_is_silent(self):
        diagnostics.finish(diagnostics.begin("UI", "reading"))

    def test_a_finding_still_returns_the_sentence(self):
        said = diagnostics.finding("FEAT-8", "the view hides six")
        self.assertIn("view hides six", said)

    def test_a_note_is_silent(self):
        diagnostics.note("Revit", "2025.3")

    def test_the_report_cannot_be_written_and_says_so_with_an_empty_path(self):
        self.assertEqual(diagnostics.write_report(), "")

    def test_the_report_can_still_be_RENDERED_with_nowhere_to_put_it(self):
        """Somewhere to write it is a separate question from having one."""
        self.assertIn("Filter View Manager", diagnostics.report())

    def test_a_value_that_cannot_be_printed_does_not_stop_the_action(self):
        class Awkward(object):
            def __str__(self):
                raise RuntimeError("cannot be printed")
            __repr__ = __str__
        self.assertTrue(diagnostics.step("UI", "Count", thing=Awkward()) > 0)


class ReportRenderTests(unittest.TestCase):
    """The renderer, fed by hand.

    It is a separate module from ``diagnostics`` so that the awkward inputs
    are ordinary test arguments rather than something that has to be provoked
    inside Revit: no failures at all, a failure with no traceback, a family
    name with a pipe in it, four thousand rows.
    """

    def _row(self, **fields):
        row = {"seq": 1, "at": "10:40:06", "tag": "UI", "action": "Count",
               "outcome": "ok", "detail": "", "cause": "", "ms": 12,
               "repeat": 1, "data": []}
        row.update(fields)
        return row

    def test_an_empty_session_still_renders_a_whole_document(self):
        body = renderer.render()
        for heading in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.",
                        "## 6.", "## 7."):
            self.assertIn(heading, body)

    def test_the_problems_come_before_the_evidence(self):
        """Ordered by what the reader needs, not by what happened first."""
        body = renderer.render(actions=[self._row()])
        self.assertLess(body.index("## 1. What to look at first"),
                        body.index("## 4. Everything that happened"))

    def test_a_clean_session_says_so_rather_than_looking_empty(self):
        body = renderer.render(actions=[self._row()])
        self.assertIn("Nothing in this session raised", body)

    def test_a_failure_is_named_at_the_top_with_its_cause(self):
        body = renderer.render(actions=[self._row(
            seq=5, outcome="failed", tag="FEAT-11",
            action="reading the views", cause="NameError: revit_query")])
        first = body.split("## 2.")[0]
        self.assertIn("FEAT-11", first)
        self.assertIn("NameError: revit_query", first)

    def test_an_unanswered_request_gets_its_own_heading(self):
        """It is a different bug from a failure and reads differently."""
        body = renderer.render(actions=[self._row(
            outcome="no answer", tag="FEAT-8", action="the live count")])
        self.assertIn("never came back", body)
        self.assertIn("the live count", body.split("## 2.")[0])

    def test_a_finding_reaches_the_top_without_anything_having_raised(self):
        body = renderer.render(found=[{"tag": "FEAT-8",
                                       "message": "the view hides six"}])
        self.assertIn("the view hides six", body.split("## 2.")[0])

    def test_a_finding_that_recurred_says_how_many_times(self):
        body = renderer.render(found=[{"tag": "UI", "message": "six hidden",
                                       "seen": 4}])
        self.assertIn("six hidden (seen 4 times)", body)

    def test_a_finding_seen_once_is_not_labelled(self):
        body = renderer.render(found=[{"tag": "UI", "message": "six hidden",
                                       "seen": 1}])
        self.assertNotIn("seen 1", body)

    def test_a_refusal_is_reported_as_the_tools_choice(self):
        body = renderer.render(actions=[self._row(
            outcome="refused", action="convert", detail="no equivalent")])
        self.assertIn("no equivalent", body.split("## 2.")[0])

    def test_a_traceback_is_fenced_so_it_survives_being_pasted(self):
        body = renderer.render(actions=[self._row(
            outcome="failed", detail="Traceback\n  line 1\n  line 2")])
        self.assertIn("```", body)
        self.assertIn("line 2", body)

    def test_a_very_long_traceback_is_clipped_at_the_useful_end(self):
        """The frame that matters is the last one, not the first."""
        lines = ["frame {0}".format(index) for index in range(200)]
        body = renderer.render(actions=[self._row(
            outcome="failed", detail="\n".join(lines))])
        self.assertIn("frame 199", body)
        self.assertNotIn("frame 0\n", body)

    def test_a_failure_with_no_traceback_says_so(self):
        body = renderer.render(actions=[self._row(outcome="failed")])
        self.assertIn("No traceback was captured", body)

    def test_a_pipe_in_a_value_cannot_break_a_table_row(self):
        """A shifted column is a corrupt report that still looks like one."""
        body = renderer.render(actions=[self._row(
            action="picked", data=[("family", "W|Beam")])])
        row = [line for line in body.split("\n") if "W/Beam" in line][0]
        self.assertEqual(row.count("|"), 8)

    def test_a_newline_in_a_value_cannot_break_a_table_row(self):
        body = renderer.render(notes=[("document", "one\ntwo")])
        self.assertIn("| document | one two |", body)

    def test_a_folded_row_shows_how_many_times_it_happened(self):
        body = renderer.render(actions=[self._row(
            action="Category search", repeat=17)])
        self.assertIn("Category search x17", body)

    def test_a_row_that_happened_once_is_not_labelled_x1(self):
        body = renderer.render(actions=[self._row(action="Count")])
        self.assertNotIn("Count x1", body)

    def test_a_huge_timeline_is_clipped_and_says_that_it_was(self):
        rows = [self._row(seq=index, action="press {0}".format(index))
                for index in range(renderer.MAX_ROWS + 20)]
        body = renderer.render(actions=rows)
        self.assertIn("The last {0} of".format(renderer.MAX_ROWS), body)
        self.assertIn("press {0}".format(renderer.MAX_ROWS + 19), body)
        self.assertNotIn("| press 0 |", body)

    def test_the_environment_being_empty_is_itself_reported(self):
        """An empty section 2 means the model never answered, and that is
        worth saying rather than leaving as a blank."""
        self.assertIn("never answered", renderer.render())

    def test_what_is_on_disk_is_in_the_file(self):
        body = renderer.render(stores=[("machine", "C:/rules.json", 5)])
        self.assertIn("C:/rules.json", body)
        self.assertIn("| machine |", body)

    def test_the_log_tail_carries_earlier_sessions_in(self):
        body = renderer.render(log_tail=["yesterday | UI | something"])
        self.assertIn("yesterday | UI | something", body)
        self.assertIn("previous run", body)

    def test_the_reader_is_warned_what_the_file_names(self):
        """It is going to be attached to a message. It carries family names,
        parameter names, view names and paths out of a client's model."""
        body = renderer.render().lower()
        self.assertIn("names things from the open model", body)

    def test_a_broken_input_still_produces_a_document(self):
        """A report is most wanted when something is already wrong."""
        body = renderer.render(actions=[None])
        self.assertIn("Filter View Manager", body)

    def test_the_tallies_are_rendered_in_the_order_they_arrive(self):
        """diagnostics.counters already sorted them; the renderer must not
        re-sort and lose it."""
        body = renderer.render(tallies=[("FEAT-13", 1, 1), ("UI", 9, 0)])
        self.assertLess(body.index("| FEAT-13 |"), body.index("| UI |"))


class WiringTests(unittest.TestCase):
    """Loud everywhere, not only where it was convenient."""

    def test_every_window_handler_is_subscribed_through_the_guard(self):
        """A Python exception inside a WPF handler reaches no caller: it goes
        to the dispatcher's unhandled path, which is at best a Revit crash
        dialog with no stack and at worst nothing at all."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.FunctionDef) and node.name == "_wire"):
                continue
            # The statements, not the text: a first version of this gate read
            # lines containing "+=" and matched the docstring explaining why
            # the subscriptions are written out, which no amount of unguarded
            # wiring would have changed.
            bare = []
            for statement in ast.walk(node):
                if not isinstance(statement, ast.AugAssign):
                    continue
                if not isinstance(statement.target, ast.Attribute):
                    continue
                value = statement.value
                guarded = (isinstance(value, ast.Call)
                           and isinstance(value.func, ast.Attribute)
                           and value.func.attr == "_guard")
                if not guarded:
                    bare.append(ast.get_source_segment(source, statement) or "?")
            self.assertEqual(bare, [], "not guarded: {0}".format(bare))
            return
        self.fail("_wire is not in script.py")

    def test_every_guarded_control_has_an_owning_feature(self):
        """A control wired without an owner reports its failures as "UI",
        which is the generic message the tag system exists to replace."""
        source = _read(_SCRIPT)
        owners = None
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "OWNERS":
                        owners = ast.literal_eval(node.value)
        self.assertIsNotNone(owners, "OWNERS is not in script.py")
        missing = []
        for line in source.split("\n"):
            if "self._guard(\"" not in line:
                continue
            control = line.split("self._guard(\"", 1)[1].split("\"", 1)[0]
            if control not in owners:
                missing.append(control)
        self.assertEqual(missing, [], "no owning feature: {0}".format(missing))

    def test_every_owner_names_a_tag_diagnostics_knows(self):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "OWNERS":
                        for control, (tag, _) in ast.literal_eval(node.value).items():
                            self.assertIn(tag, diagnostics.FEATURES, control)
                        return
        self.fail("OWNERS is not in script.py")

    def test_the_revit_thread_reports_which_feature_asked(self):
        """An error from ``serve`` used to read "something went wrong", which
        costs a round trip to act on. The tag travels with the request."""
        source = _read(_SCRIPT)
        self.assertIn('request["tag"] = tag', source)
        self.assertIn('request.get("tag"', source)

    def test_the_panel_guards_its_presses_too(self):
        source = _read(_PROVIDER)
        self.assertIn("def _guard(", source)
        self.assertIn('self._guard("Refresh"', source)
        self.assertIn('self._guard("Clear"', source)
        self.assertIn("self._guard(\"pressing ", source)

    def test_both_halves_hold_their_guard_closures(self):
        """A Python closure handed to a .NET event is not necessarily kept
        alive by the subscription, and a collected handler is a button that
        silently stops working."""
        self.assertIn("self._handlers.append(", _read(_SCRIPT))
        self.assertIn("self.guards.append(", _read(_PROVIDER))

    def test_the_user_can_get_at_the_log_from_the_window(self):
        source = _read(_SCRIPT)
        self.assertIn("_on_diagnostics", source)
        self.assertIn("diagnostics.recent(", source)

    def test_the_log_is_opened_through_dotnet_and_not_subprocess(self):
        """This engine ships a stripped stdlib (§12.9.3 -- no ``re``, no
        ``csv``). ``Process.Start`` is always there."""
        source = _read(_SCRIPT)
        self.assertIn("from System.Diagnostics import Process", source)
        self.assertNotIn("import subprocess", source)


if __name__ == "__main__":
    unittest.main()
