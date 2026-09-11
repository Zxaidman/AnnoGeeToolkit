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
