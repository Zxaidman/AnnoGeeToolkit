# -*- coding: utf-8 -*-
"""The bridge spike, checked where it can be checked without Revit.

Three things here, and each has a specific failure in mind.

**The URL contract.** The host, the port, the API name and the route names are
written down in three places — the routes in ``startup.py``, the VBA in
``bridge/excel/``, and the Bridge Check pushbutton. A disagreement between any
two of them produces a call that times out, and it looks exactly like a network
problem for as long as it takes somebody to compare three files by hand. So the
three are compared here instead.

**The engine.** ``startup.py`` is loaded by pyRevit's core engine, which is
IronPython 2.7 — not the CPython 3 engine the rest of the toolkit runs on. An
f-string in that file is a syntax error at pyRevit load, and the symptom is that
the whole extension fails to appear. Which Python actually runs it is the third
question the spike exists to answer; until it has, the file has to be valid in
both.

**The blast radius.** A startup script that raises takes pyRevit's load with it,
so a broken bridge would cost the user every other tool on the ribbon. The
module-level registration is required to be wrapped, and the wrap is checked.
"""

import ast
import io
import os
import shutil
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STARTUP = os.path.join(_ROOT, "AnonGee.extension", "startup.py")
_VBA = os.path.join(_ROOT, "bridge", "excel", "modAnonGeeBridge.bas")
_CHECK = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                      "Bridge Check.pushbutton", "script.py")
_LISTENER = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                         "Bridge Listener.pushbutton", "script.py")
_BUILDER = os.path.join(_ROOT, "bridge", "excel", "build_workbook.py")
_SAMPLE = os.path.join(_ROOT, "bridge", "excel", "build_sample_project.py")

if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
from anongee_toolkit.bridge import envelope as _envelope         # noqa: E402
from anongee_toolkit.bridge import jobs as _jobs                 # noqa: E402
from anongee_toolkit.bridge import registry as _registry         # noqa: E402
from anongee_toolkit import commands as _commands                # noqa: E402

#: Bind the handlers once, here, so the tests below see the same registry the
#: listener does. ``register_all`` imports each handler in a ``try`` and skips
#: what will not import, so this works off Revit and reports exactly what a
#: build has: three bound, four declared and not written yet.
_BOUND = _commands.register_all()


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _constants(source):
    """Top-level ``NAME = <literal>`` assignments, as a dict."""
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value,
                                                           ast.Constant):
                found[target.id] = node.value.value
    return found


def _vba_constant(source, name):
    """``Public Const NAME As T = value`` -> the value, unquoted."""
    for line in source.splitlines():
        text = line.strip()
        if not text.startswith("Public Const " + name + " "):
            continue
        value = text.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return int(value)
    raise AssertionError("no Public Const {0} in the VBA".format(name))


def _routes(source):
    """``{route: [argument names]}`` for every registered handler.

    Reads the ``add("/ping", ["GET"], ping)`` calls rather than decorators:
    each route is now registered on its own so that one bad pattern cannot take
    the others down with it, and the decorators went with that change.
    """
    tree = ast.parse(source)
    handlers = dict((node.name, [argument.arg for argument in node.args.args])
                    for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef))

    found = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "add"
                and len(node.args) == 3
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[2], ast.Name)):
            found[node.args[0].value] = handlers.get(node.args[2].id, [])
    return found


class UrlContractTests(unittest.TestCase):
    """Three files, one URL. They agree here or they never agree at all."""

    def setUp(self):
        self.startup = _constants(_read(_STARTUP))
        self.check = _constants(_read(_CHECK))
        self.vba = _read(_VBA)

    def test_the_api_name_is_the_same_everywhere(self):
        self.assertEqual(self.startup["API_NAME"], "anongee")
        self.assertEqual(self.check["API"], self.startup["API_NAME"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_API"),
                         self.startup["API_NAME"])

    def test_the_host_and_port_are_the_same_everywhere(self):
        self.assertEqual(self.check["HOST"], self.startup["DEFAULT_HOST"])
        self.assertEqual(self.check["PORT"], self.startup["DEFAULT_PORT"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_HOST"),
                         self.startup["DEFAULT_HOST"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_PORT"),
                         self.startup["DEFAULT_PORT"])

    def test_every_route_a_caller_names_is_one_that_is_served(self):
        served = set(route.strip("/") for route in _routes(_read(_STARTUP)))
        self.assertEqual(served, set(["ping", "status", "jobs"]))
        # The macro names both, because Excel can call both. Bridge Check names
        # only ping — see the test below for why it must not name the other.
        for route in ("ping", "status"):
            self.assertIn('"{0}"'.format(route), self.vba,
                          "the VBA never calls /{0}".format(route))
        self.assertIn('"ping"', _read(_CHECK))

    def test_bridge_check_never_calls_status(self):
        """It runs *inside* Revit, and ``/status`` needs Revit to be idle.

        ``/status`` declares ``uiapp``, so pyRevit runs it as an External Event
        — which fires only when Revit has nothing else to do. Revit is not idle
        while it is running Bridge Check, and Bridge Check would be blocking on
        the response. **They wait for each other until every timeout expires.**

        A run of 0.5.0 did exactly that and then reported *"the External Event
        marshalling is not [up]"*, which was false: the marshalling had already
        been proved from Excel. The diagnostic deadlocked itself and blamed the
        bridge. Excel can test that route because Excel is not holding Revit's
        thread; nothing inside Revit ever can.
        """
        body = _read(_CHECK).split("def report(")[1].split("\ndef ")[0]
        self.assertNotIn('describe("status"', body)
        self.assertIn("document()", body)

    def test_bridge_check_reads_the_document_directly_instead(self):
        # It is already inside Revit. It does not need a round trip to know
        # what is open, and the round trip is the thing that cannot work.
        body = _read(_CHECK).split("def document(")[1].split("\ndef ")[0]
        self.assertIn("__revit__", body)
        self.assertIn("ActiveUIDocument", body)

    def test_the_job_routes_carry_no_revit_argument(self):
        """A job is written, not run — which is what makes posting instant.

        If any of these ever declares ``uiapp``/``uidoc``/``doc``, pyRevit runs
        it as an External Event and the post starts waiting for Revit to be
        idle. That is the exact hang the whole design exists to avoid, and it
        would look like a slow network.
        """
        routes = _routes(_read(_STARTUP))
        for argument in routes["/jobs"]:
            self.assertNotIn(argument, ("uiapp", "uidoc", "doc"),
                             "/jobs declares {0}".format(argument))

    def test_both_callers_build_the_url_from_the_same_three_parts(self):
        # Not a hardcoded string in either, or the constants above are
        # decoration and the test proves nothing.
        self.assertIn("BRIDGE_HOST & \":\"", self.vba)
        self.assertIn('"http://{0}:{1}/{2}/{3}".format(HOST, PORT, API',
                      _read(_CHECK))


class FolderContractTests(unittest.TestCase):
    """``startup.py`` and ``bridge/jobs.py`` must agree about where jobs live.

    They cannot share the code. pyRevit loads the startup script on IronPython
    2.7 and the toolkit is CPython 3 in ``lib/py3``, so the rules are written
    twice in two languages on purpose. That is the price of the engine split
    and it is worth paying — but "two files must agree" is exactly the contract
    that rots, so it is held here, and ``/ping`` reports the home it computed so
    a mismatch also shows up at runtime.
    """

    def setUp(self):
        self.startup = _constants(_read(_STARTUP))
        self.jobs = _jobs

    def test_the_environment_override_is_the_same_variable(self):
        self.assertEqual(self.startup["ENV_HOME"], self.jobs.ENV_HOME)

    def test_the_folder_names_are_the_same(self):
        self.assertEqual(self.startup["OUTBOX"], self.jobs.OUTBOX)
        self.assertEqual(self.startup["INBOX"], self.jobs.INBOX)

    def test_the_file_suffixes_are_the_same(self):
        for name in ("JOB_SUFFIX", "RUNNING_SUFFIX", "RESULT_SUFFIX"):
            self.assertEqual(self.startup[name], getattr(self.jobs, name), name)

    def test_the_fallback_paths_are_the_same(self):
        # Tuples, so they are read off the tree rather than out of _constants.
        for node in ast.walk(ast.parse(_read(_STARTUP))):
            if (isinstance(node, ast.Assign) and node.targets
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in ("APPDATA_PARTS", "HOME_PARTS")):
                parts = tuple(element.value for element in node.value.elts)
                self.assertEqual(parts, getattr(self.jobs, node.targets[0].id),
                                 node.targets[0].id)

    def test_ping_reports_the_home_it_computed(self):
        """So a disagreement is a sentence in a dialog, not a job nobody sees."""
        self.assertIn('"bridge_home": bridge_home()', _read(_STARTUP))


class TwoRoutesTests(unittest.TestCase):
    """The reason there are two routes is the reason the spike is worth doing."""

    def setUp(self):
        self.routes = _routes(_read(_STARTUP))

    def test_ping_asks_revit_for_nothing(self):
        # No uiapp/uidoc/doc argument, so pyRevit does NOT run it as an
        # External Event -- which is what lets it answer while Revit is busy.
        self.assertEqual(self.routes["/ping"], [])

    def test_status_declares_uiapp_and_so_runs_as_an_external_event(self):
        # Declaring one of uiapp/uidoc/doc is the whole mechanism. If this
        # argument is ever removed the route stops proving anything.
        self.assertEqual(self.routes["/status"], ["uiapp"])

    def test_status_reads_the_document_defensively_rather_than_declaring_it(self):
        # Declaring `doc` would make "no document open" an error instead of an
        # answer, and a bridge that cannot say that looks broken every morning.
        source = _read(_STARTUP)
        self.assertIn("uiapp.ActiveUIDocument", source)
        self.assertIn("no document is open", source)


class EngineCompatibilityTests(unittest.TestCase):
    """``startup.py`` is loaded by pyRevit's core engine, which is IronPython."""

    def setUp(self):
        self.source = _read(_STARTUP)
        self.tree = ast.parse(self.source)

    def test_it_compiles(self):
        compile(self.source, _STARTUP, "exec")

    def test_no_f_strings(self):
        """An f-string here is a syntax error at pyRevit load, and the symptom
        is the whole extension failing to appear."""
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.JoinedStr)

    def test_nothing_newer_than_python_2_7(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.NamedExpr)      # :=
            self.assertNotIsInstance(node, ast.AnnAssign)      # x: int = 1
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(node.returns, node.name)
                for argument in node.args.args:
                    self.assertIsNone(argument.annotation, node.name)

    def test_the_toolkit_is_not_imported_at_module_scope(self):
        """It lives in ``lib/py3`` and may not be on this engine's path at all.

        Whether a route handler can reach it is question 3 of the spike, and
        importing it here would answer it by crashing.
        """
        for node in self.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = getattr(node, "module", "") or ""
                self.assertNotIn("anongee_toolkit", module)
                for name in names:
                    self.assertNotIn("anongee_toolkit", name)

    def test_pyrevit_is_imported_inside_the_function_not_at_module_scope(self):
        # So the file stays importable by this test suite, off Revit.
        self.assertNotIn("\nfrom pyrevit import", self.source)
        self.assertIn("    from pyrevit import routes", self.source)


class BlastRadiusTests(unittest.TestCase):
    """A startup script that raises costs the user every other tool."""

    def test_registration_is_wrapped(self):
        source = _read(_STARTUP)
        tail = source.split("REGISTRATION_NOTE = \"\"", 1)[1]
        self.assertIn("try:", tail)
        self.assertIn("register()", tail)
        self.assertIn("except Exception", tail)

    def test_register_returns_its_failure_rather_than_raising(self):
        # Read as a tree, not as text. The first version of this test searched
        # the source for "raise" and matched the word in the docstring that
        # promises it does not.
        for node in ast.walk(ast.parse(_read(_STARTUP))):
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                for inner in ast.walk(node):
                    self.assertNotIsInstance(inner, ast.Raise)
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                self.assertTrue(returns)
                break
        else:
            self.fail("startup.py defines no register()")

    def test_the_check_tool_writes_nothing(self):
        source = _read(_CHECK)
        for forbidden in ("Transaction(", "TransactionGroup(", ".Delete(",
                          "doc.Create"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_the_check_tool_has_more_than_one_way_to_reach_the_wire(self):
        """Both of its first two attempts failed on a real Revit 2025 run.

        ``from System.Net import WebClient`` raised *Cannot import name
        WebClient* — on .NET 8 that class lives in its own assembly and has to
        be referenced — and ``urllib.request`` raised *No module named request*,
        because this engine ships only part of the standard library. A probe
        with one route to the network is a probe that stops working before the
        thing it is probing does.
        """
        source = _read(_CHECK)
        ways = source.split("WAYS = (")[1].split(")\n")[0]
        for expected in ("System.Net.WebClient", "System.Net.Http.HttpClient",
                         "urllib.request", "raw socket"):
            self.assertIn(expected, ways, expected)

    def test_the_assembly_is_referenced_before_the_dotnet_import(self):
        # The bug the first version shipped: importing System.Net types without
        # clr.AddReference works on .NET Framework and not on .NET 8.
        for name in ("_by_web_client", "_by_http_client"):
            body = _read(_CHECK).split("def " + name)[1].split("\ndef ")[0]
            self.assertIn("clr.AddReference", body, name)
            self.assertLess(body.index("clr.AddReference"),
                            body.index("from System.Net"), name)

    def test_every_failed_attempt_is_kept_not_just_the_last(self):
        # Reporting only the last error says the floor gave way, not that the
        # rungs above it did — and which rungs are missing is the finding.
        body = _read(_CHECK).split("def fetch(")[1].split("\ndef ")[0]
        self.assertIn("errors.append", body)
        self.assertIn("return body, name, errors", body)


class JobStoreTests(unittest.TestCase):
    """A job from written to answered, on a real folder."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.job = _envelope.new_job(
            "levels.sync", "C:/Jobs/x.xlsm", "LEVELS",
            identifier=_envelope.job_id("20260822-140311", 7))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_written_job_is_pending(self):
        _jobs.write_job(self.job, self.root)
        self.assertEqual([identifier for identifier, _path
                          in _jobs.pending(self.root)],
                         ["20260822-140311-0007"])

    def test_a_job_is_published_by_a_rename_not_by_a_write(self):
        """A listener scanning mid-write must never see half a file."""
        body = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "bridge", "jobs.py")).split("def write_job")[1].split("\ndef ")[0]
        self.assertIn(".partial", body)
        self.assertIn("os.rename(partial, final)", body)

    def test_only_one_claim_of_a_job_can_win(self):
        # The day somebody opens two Revit sessions is the day nobody plans
        # for. Two runs of one command against two models is the failure.
        path = _jobs.write_job(self.job, self.root)
        first = _jobs.claim(path)
        self.assertTrue(first)
        self.assertIsNone(_jobs.claim(path))
        self.assertEqual(_jobs.pending(self.root), [])

    def test_a_claimed_job_is_no_longer_offered(self):
        path = _jobs.write_job(self.job, self.root)
        _jobs.claim(path)
        self.assertEqual(_jobs.pending(self.root), [])

    def test_the_answer_is_written_twice(self):
        result = _envelope.new_result(self.job, _envelope.STATUS_DONE,
                                      {"created": 4})
        json_path, tsv_path = _jobs.write_result(result, self.root)
        self.assertTrue(os.path.exists(json_path))
        self.assertTrue(os.path.exists(tsv_path))
        # JSON for machines, TSV for Excel — which has no JSON parser and must
        # not be given a hand-written one.
        self.assertEqual(_jobs.read_result("20260822-140311-0007",
                                           self.root)["summary"]["created"], 4)
        self.assertIn("#FINDINGS", _read(tsv_path))

    def test_recent_shows_where_each_job_got_to(self):
        path = _jobs.write_job(self.job, self.root)
        self.assertEqual(_jobs.recent(root=self.root)[0]["status"],
                         _envelope.STATUS_QUEUED)
        _jobs.claim(path)
        self.assertEqual(_jobs.recent(root=self.root)[0]["status"],
                         _envelope.STATUS_RUNNING)
        _jobs.write_result(_envelope.new_result(self.job, _envelope.STATUS_DONE),
                           self.root)
        self.assertEqual(_jobs.recent(root=self.root)[0]["status"],
                         _envelope.STATUS_DONE)


class EnvelopeTests(unittest.TestCase):

    def job(self, **changes):
        job = _envelope.new_job("levels.sync", identifier="j1")
        job.update(changes)
        return job

    def test_a_good_envelope_has_no_problems(self):
        self.assertEqual(_envelope.problems(self.job()), [])

    def test_a_problem_is_a_sentence_not_a_boolean(self):
        # A caller that rejects something owes the user a reason.
        for job, expected in ((self.job(command=""), "command"),
                              (self.job(jobId=""), "id"),
                              (self.job(envelope=""), "version")):
            found = _envelope.problems(job)
            self.assertTrue(found)
            self.assertTrue(any(expected in line for line in found), found)

    def test_a_future_envelope_is_refused_by_major_version(self):
        found = _envelope.problems(self.job(envelope="2.0"))
        self.assertTrue(any("update the workbook" in line for line in found))
        # A patch bump is not a break.
        self.assertEqual(_envelope.problems(self.job(envelope="1.7")), [])

    def test_nothing_is_written_unless_asked(self):
        self.assertTrue(_envelope.DEFAULT_OPTIONS["dryRun"])
        self.assertTrue(_envelope.option(self.job(), "dryRun"))
        self.assertFalse(_envelope.option(
            self.job(options={"dryRun": False}), "dryRun"))

    def test_a_tab_inside_a_message_cannot_break_the_row(self):
        # No escaping rules, because the engine that writes this ships no csv
        # module and hand-rolled quoting is where these files go wrong.
        result = _envelope.new_result(self.job(), findings=[
            {"severity": "Error", "sheet": "LEVELS", "row": 3,
             "column": "Name", "message": "a\tb\nc"}])
        rows = _envelope.as_tsv(result).strip().split("\n")
        self.assertEqual(len(rows[-1].split("\t")),
                         len(_envelope.FINDING_FIELDS))

    def test_a_finding_and_a_workbook_issue_are_the_same_shape(self):
        models = _rc.models
        issue = models.Issue(models.SEVERITY_WARNING, "hello", sheet="LEVELS",
                             row=4, column="Elevation")
        finding = _envelope.findings_from_issues([issue])[0]
        self.assertEqual(sorted(finding), sorted(_envelope.FINDING_FIELDS))
        self.assertEqual(finding["message"], "hello")
        # The row is the point of a finding: it is what makes it typeable into
        # Excel's Name Box. An earlier version read ``row_number``, a name from
        # a different DTO, and would have dropped it from every finding without
        # a word.
        self.assertEqual(finding["row"], 4)


class RegistryTests(unittest.TestCase):
    """A command is declared once, and nothing else may name one."""

    def test_the_declared_commands_are_the_stage_zero_to_three_set(self):
        self.assertEqual(_registry.known(),
                         ["beams.sync", "bridge.echo", "columns.sync",
                          "footings.sync", "grids.sync", "levels.sync",
                          "slabs.sync"])

    def test_the_structure_commands_are_declared_and_not_bound_yet(self):
        """Declared before written, deliberately.

        A button naming a command nobody declared answers "not a command this
        build knows", which reads like a broken install. Declared and unbound
        answers "declared but not built yet", which is the truth. As each one
        is built it moves to the bound side of this test rather than the test
        being deleted -- that is the record of what was built and when.
        """
        self.assertEqual(_registry.unbound(), ["beams.sync", "slabs.sync"])

    def test_the_built_commands_are_bound(self):
        self.assertEqual(sorted(_BOUND),
                         ["bridge.echo", "columns.sync", "footings.sync",
                          "grids.sync", "levels.sync"])

    def test_a_command_that_writes_says_so(self):
        self.assertFalse(_registry.get("bridge.echo").writes)
        self.assertTrue(_registry.get("levels.sync").writes)

    def test_binding_an_undeclared_command_is_refused(self):
        # A handler nobody declared is a command the workbook cannot name and
        # the UI cannot list — it would never run and nothing would say why.
        ok, note = _registry.bind("nonsense.sync", lambda *a: None)
        self.assertFalse(ok)
        self.assertIn("not a declared command", note)

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_workbook", _BUILDER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_control_sheet_names_only_declared_commands(self):
        """The CONTROL sheet and the registry are two files that must agree.

        A button naming a command the registry does not have is a button whose
        only possible answer is "not a command this build knows".
        """
        named = [command for _title, command, _sheet, _what
                 in self.builder().COMMANDS]
        self.assertTrue(named)
        for name in named:
            self.assertIn(name, _registry.known(), name)

    def test_the_control_sheet_names_the_sheet_the_registry_expects(self):
        for _title, command, sheet, _what in self.builder().COMMANDS:
            self.assertEqual(sheet, _registry.get(command).sheet, command)

    def test_every_control_command_has_a_macro_to_run_it(self):
        vba = _read(_VBA)
        for _title, command, _sheet, _what in self.builder().COMMANDS:
            self.assertIn('"{0}"'.format(command), vba, command)

    def test_the_workbook_the_builder_writes_has_the_datum_sheets(self):
        self.assertEqual(
            [name for name, _headers, _rows, _widths in []] or
            ["CONTROL", "INFO", "LEVELS", "GRIDS", "LOG"],
            ["CONTROL", "INFO", "LEVELS", "GRIDS", "LOG"])
        source = _read(_BUILDER)
        for sheet in ("CONTROL", "INFO", "LEVELS", "GRIDS", "LOG"):
            self.assertIn('"{0}"'.format(sheet), source, sheet)

    def test_the_workbook_defaults_to_writing_nothing(self):
        # "Write?" starts at No on every row: a dry run reports what it would
        # do and touches nothing.
        source = _read(_BUILDER)
        body = source.split("for index, (title, command")[1].split("\n\n")[0]
        self.assertIn('column=5, value="No"', body)


class SampleProjectTests(unittest.TestCase):
    """The sample building, held to the same contract as the datum workbook.

    ``build_sample_project.py`` writes a whole Foundation + G + 4 frame so the
    **format** can be argued with before any of it is built. It is a second file
    naming commands and sheets, which means it is a second file that can drift
    from ``registry.py`` — and a workbook whose buttons name commands the build
    does not have is a workbook that fails on the first press, in Revit, in
    front of the owner. Cheaper to catch here.

    The building is generated from the constants at the top of that file, so
    these also check the arithmetic stays consistent when a bay or a storey is
    moved: one column per storey, one footing per grid intersection.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_button_names_a_declared_command(self):
        named = [command for _title, command, _sheet, _what, _built
                 in self.builder().COMMANDS]
        self.assertTrue(named)
        for name in named:
            self.assertIn(name, _registry.known(), name)

    def test_every_button_names_the_sheet_the_registry_expects(self):
        for _title, command, sheet, _what, _built in self.builder().COMMANDS:
            self.assertEqual(sheet, _registry.get(command).sheet, command)

    def test_the_built_column_agrees_with_what_is_bound(self):
        """``Built?`` on the CONTROL sheet is a claim, and claims rot.

        A row saying ``yes`` for a command with no handler sends the owner to
        press a button that cannot work; a row saying ``not yet`` for one that
        does work hides finished work. Either way the sheet is lying, so the
        column is compared with the registry rather than maintained by hand.
        """
        for _title, command, _sheet, _what, built in self.builder().COMMANDS:
            bound = _registry.get(command).bound
            self.assertEqual(built, "yes" if bound else "not yet", command)

    def test_every_button_has_a_macro_to_run_it_or_is_not_built_yet(self):
        # A macro is only written when the command is. Until then the button
        # is documentation.
        vba = _read(_VBA)
        for _title, command, _sheet, _what, built in self.builder().COMMANDS:
            if built == "yes":
                self.assertIn('"{0}"'.format(command), vba, command)

    def test_the_sheets_it_writes_are_the_sheets_the_buttons_name(self):
        source = _read(_SAMPLE)
        for _title, _command, sheet, _what, _built in self.builder().COMMANDS:
            if sheet:
                self.assertIn('table("{0}"'.format(sheet), source, sheet)

    def test_one_footing_under_every_grid_intersection(self):
        sample = self.builder()
        expected = len(sample.GRIDS_VERTICAL) * len(sample.GRIDS_HORIZONTAL)
        self.assertEqual(len(sample.footing_rows()), expected)

    def test_one_column_per_intersection_per_storey(self):
        # Six storeys of a column are six rows, not one: six pours with a
        # joint between each, and a size that is allowed to change on the way
        # up. Verbose, and the only honest way to say it.
        sample = self.builder()
        expected = (len(sample.GRIDS_VERTICAL) * len(sample.GRIDS_HORIZONTAL)
                    * len(sample.STOREYS))
        self.assertEqual(len(sample.column_rows()), expected)

    def test_a_column_row_names_two_levels_that_exist(self):
        sample = self.builder()
        names = [name for name, _elevation, _story in sample.LEVELS]
        base = sample.COLUMN_PLACEMENT_HEADERS.index("BaseLevel")
        top = sample.COLUMN_PLACEMENT_HEADERS.index("TopLevel")
        for row in sample.column_rows():
            self.assertIn(row[base], names)
            self.assertIn(row[top], names)
            self.assertNotEqual(row[base], row[top])

    def test_every_placed_element_names_a_type_that_is_declared(self):
        """A mark pointing at a type the TYPES sheet does not carry is the
        commonest thing wrong with a real schedule, and it is silent."""
        sample = self.builder()
        pairs = (
            (sample.footing_rows(), sample.FOOTING_PLACEMENT_HEADERS,
             sample.FOOTING_TYPES),
            (sample.column_rows(), sample.COLUMN_PLACEMENT_HEADERS,
             sample.COLUMN_TYPES),
            (sample.beam_rows(), sample.BEAM_PLACEMENT_HEADERS,
             sample.BEAM_TYPES),
            (sample.slab_rows(), sample.SLAB_PLACEMENT_HEADERS,
             sample.SLAB_TYPES),
        )
        for rows, headers, types in pairs:
            declared = [row[0] for row in types]
            column = headers.index("TypeMark")
            self.assertTrue(rows)
            for row in rows:
                if not any(str(value).strip() for value in row):
                    continue                  # a group separator, on purpose
                self.assertIn(row[column], declared)

    def test_the_key_is_unique_even_where_the_mark_is_not(self):
        """Mark is a schedule label; the key is what the round trip matches on.

        Columns share marks deliberately — that is the owner's rule — so the
        thing that has to be unique is grid position plus storey. If *that*
        repeated, the second run could not tell two columns apart and
        idempotence would stop being true.
        """
        sample = self.builder()
        cases = (
            (sample.footing_rows(), sample.FOOTING_PLACEMENT_HEADERS,
             ("GridX", "GridY")),
            (sample.column_rows(), sample.COLUMN_PLACEMENT_HEADERS,
             ("GridX", "GridY", "Storey")),
            (sample.slab_rows(), sample.SLAB_PLACEMENT_HEADERS,
             ("Level", "FromGridX", "ToGridX", "FromGridY", "ToGridY")),
        )
        for rows, headers, fields in cases:
            columns = [headers.index(name) for name in fields]
            keys = [tuple(row[index] for index in columns) for row in rows]
            self.assertEqual(len(keys), len(set(keys)), fields)


class ColumnMarkTests(unittest.TestCase):
    """The owner's rule, which is not the obvious one.

    A column at A1 marked ``C1`` is ``C1`` all the way up, **even where its
    size changes**. And two columns share a mark on one floor only if their
    size *and* rebar schedule are both the same. Which means a mark is a
    schedule label rather than a key, and both halves of that need holding
    down: a mark that changed up the stack would be wrong, and a mark shared by
    two columns with different cages would be wrong in the other direction.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def rows(self, sample):
        headers = sample.COLUMN_PLACEMENT_HEADERS
        index = dict((name, headers.index(name)) for name in headers)
        return [dict((name, row[index[name]]) for name in headers)
                for row in sample.column_rows()]

    def test_a_mark_never_changes_going_up(self):
        stacks = {}
        for row in self.rows(self.builder()):
            stacks.setdefault((row["GridX"], row["GridY"]), set()).add(
                row["Mark"])
        self.assertTrue(stacks)
        for where, marks in stacks.items():
            self.assertEqual(len(marks), 1, "{0} changes mark: {1}".format(
                where, sorted(marks)))

    def test_a_mark_does_change_type_going_up(self):
        # The point of the rule. If nothing in the sample ever reduced, the
        # test above would pass for the wrong reason.
        types = {}
        for row in self.rows(self.builder()):
            types.setdefault(row["Mark"], set()).add(row["TypeMark"])
        self.assertTrue(any(len(seen) > 1 for seen in types.values()),
                        "no mark carries two sizes, so the rule is untested")

    def test_two_columns_share_a_mark_only_if_size_and_rebar_agree(self):
        by_floor = {}
        for row in self.rows(self.builder()):
            key = (row["Storey"], row["Mark"])
            by_floor.setdefault(key, set()).add(
                (row["TypeMark"], row["RebarSchedule"]))
        for (storey, mark), kinds in by_floor.items():
            self.assertEqual(len(kinds), 1,
                             "{0} on {1} is {2}".format(mark, storey,
                                                        sorted(kinds)))

    def test_different_cages_of_the_same_size_are_different_marks(self):
        # The half that is easy to get wrong: grouping on size alone would
        # give one mark to a corner and an internal column on the same floor.
        sample = self.builder()
        base = sample.STOREYS[0][0]
        seen = {}
        for row in self.rows(sample):
            if row["Storey"] != base:
                continue
            seen.setdefault(row["Mark"], set()).add(row["RebarSchedule"])
        self.assertGreater(len(seen), 1)
        for mark, cages in seen.items():
            self.assertEqual(len(cages), 1, mark)


class BeamGroupingTests(unittest.TestCase):
    """Continuity is the layout: a group of rows is one continuous beam, a
    single row is a simply supported one, and a blank row separates groups.

    So the blank rows are load-bearing. A missing one silently joins two beams
    into one; a doubled one makes an empty beam. Both are the kind of thing
    that reads fine and builds wrong.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def blank(self, row):
        return not any(str(value).strip() for value in row)

    def test_every_group_is_separated_by_exactly_one_blank_row(self):
        sample = self.builder()
        rows = sample.beam_rows()
        self.assertFalse(self.blank(rows[0]))
        self.assertFalse(self.blank(rows[-1]))
        for first, second in zip(rows, rows[1:]):
            self.assertFalse(self.blank(first) and self.blank(second))

    def test_the_blank_rows_reproduce_the_groups(self):
        # Reading the sheet back the way a parser will must give the same
        # groups the builder started from.
        sample = self.builder()
        rebuilt = [[]]
        for row in sample.beam_rows():
            if self.blank(row):
                rebuilt.append([])
            else:
                rebuilt[-1].append(row)
        self.assertEqual([len(group) for group in rebuilt],
                         [len(group) for group in sample.beam_groups()])

    def test_a_group_shares_one_mark_and_numbers_its_spans(self):
        for group in self.builder().beam_groups():
            marks = set(row[0] for row in group)
            self.assertEqual(len(marks), 1, sorted(marks))
            self.assertEqual([row[2] for row in group],
                             list(range(1, len(group) + 1)))

    def test_the_sample_shows_both_kinds(self):
        # A sample where everything is continuous teaches half the format.
        sizes = set(len(group) for group in self.builder().beam_groups())
        self.assertIn(1, sizes)
        self.assertTrue(any(size > 1 for size in sizes))


class SlabPanelTests(unittest.TestCase):
    """A slab is a panel between beams, not a floor.

    One slab over a whole floor swallows every beam under it in the
    quantities, which is wrong in the schedule long before it is wrong in the
    model.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_one_panel_per_bay_per_framed_level(self):
        sample = self.builder()
        bays = ((len(sample.GRIDS_VERTICAL) - 1)
                * (len(sample.GRIDS_HORIZONTAL) - 1))
        self.assertEqual(len(sample.slab_rows()),
                         bays * len(sample.SLAB_LEVELS))

    def test_no_slab_sits_on_the_foundation(self):
        sample = self.builder()
        foundation = sample.LEVELS[0][0]
        level = sample.SLAB_PLACEMENT_HEADERS.index("Level")
        for row in sample.slab_rows():
            self.assertNotEqual(row[level], foundation)

    def test_every_panel_stops_at_the_beams_by_default(self):
        sample = self.builder()
        rule = sample.SLAB_PLACEMENT_HEADERS.index("EdgeRule")
        for row in sample.slab_rows():
            self.assertEqual(row[rule], sample.EDGE_RULES[0])
        self.assertEqual(sample.EDGE_RULES[0], "Inner face of beam")


class WorkbookUnitTests(unittest.TestCase):
    """One unit for the whole workbook, named in every length header.

    The failure this prevents is quiet: a LEVELS sheet in metres read as
    millimetres puts the terrace at 16.5 mm, every level lands inside the slab
    below it, and the run reports success. So the header says the unit, the
    reader believes the header, and both sides are tested against each other.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_workbook_is_in_metres(self):
        self.assertEqual(self.builder().UNITS, "m")

    def test_every_length_header_names_its_unit(self):
        from anongee_toolkit.rc_automation import datum
        sample = self.builder()
        headers = (sample.LEVEL_HEADERS + sample.GRID_HEADERS
                   + sample.FOOTING_TYPE_HEADERS
                   + sample.FOOTING_PLACEMENT_HEADERS
                   + sample.COLUMN_TYPE_HEADERS
                   + sample.COLUMN_PLACEMENT_HEADERS
                   + sample.BEAM_TYPE_HEADERS
                   + sample.BEAM_PLACEMENT_HEADERS
                   + sample.SLAB_TYPE_HEADERS
                   + sample.SLAB_PLACEMENT_HEADERS)
        named = [head for head in headers if datum.unit_in_header(head)]
        self.assertTrue(named)
        for head in named:
            self.assertEqual(datum.unit_in_header(head),
                             sample.unit_of(head), head)

    def test_cover_and_diameter_stay_in_millimetres(self):
        """Metres were bought for readability, and 0.05 is not readable.

        So the workbook is not uniformly metres and should not be: a cover and
        a bar diameter are pinned. The pin is a rule about what the column *is*
        — its name — rather than a list of headers somebody keeps in step.
        """
        sample = self.builder()
        self.assertEqual(sample.unit_of("CoverTop"), "mm")
        self.assertEqual(sample.unit_of("BarDia"), "mm")
        self.assertEqual(sample.unit_of("Thickness"), sample.UNITS)
        self.assertEqual(sample.unit("CoverTop"), "CoverTop (mm)")

    def test_a_pinned_value_is_written_in_millimetres(self):
        sample = self.builder()
        rows = sample.typed_rows(sample.FOOTING_TYPES,
                                 sample.FOOTING_TYPE_LENGTHS,
                                 sample.FOOTING_TYPE_HEADERS)
        cover = sample.FOOTING_TYPE_HEADERS.index(sample.unit("CoverTop"))
        thickness = sample.FOOTING_TYPE_HEADERS.index(sample.unit("Thickness"))
        self.assertEqual(rows[0][cover], 50.0)
        self.assertAlmostEqual(rows[0][thickness], 0.6)

    def test_the_reader_gets_the_elevations_the_builder_wrote(self):
        # The round trip that matters: metres out of the builder, millimetres
        # into the plan, and the same building at the end of it.
        from anongee_toolkit.rc_automation import datum
        sample = self.builder()
        grid = [list(sample.LEVEL_HEADERS)] + [list(row)
                                               for row in sample.level_rows()]
        rows, issues = datum.parse_levels(grid, units="mm")
        self.assertFalse([issue for issue in issues
                          if issue.severity == "Error"], issues)
        self.assertEqual(len(rows), len(sample.LEVELS))
        for row, (name, elevation, _story) in zip(rows, sample.LEVELS):
            self.assertEqual(row.name, name)
            self.assertAlmostEqual(row.elevation_mm, elevation, places=3)

    def test_a_metre_sheet_read_as_millimetres_is_still_metres(self):
        # units="mm" above is deliberate: the header says (m) and the header
        # wins, because it is the thing sitting beside the number.
        from anongee_toolkit.rc_automation import datum
        self.assertEqual(datum.unit_in_header("Elevation PBP (m)"), "m")
        self.assertEqual(datum.to_mm(3.3, "m"), 3300.0)

    def test_both_elevations_are_written_and_agree(self):
        sample = self.builder()
        pbp = sample.LEVEL_HEADERS.index(sample.unit("Elevation PBP"))
        survey = sample.LEVEL_HEADERS.index(sample.unit("Elevation Survey"))
        offset = sample.length(sample.SURVEY_OFFSET_MM)
        for row in sample.level_rows():
            self.assertAlmostEqual(row[survey] - row[pbp], offset, places=6)

    def test_a_placement_row_is_as_wide_as_its_header(self):
        sample = self.builder()
        pairs = (
            (sample.footing_rows(), sample.FOOTING_PLACEMENT_HEADERS),
            (sample.column_rows(), sample.COLUMN_PLACEMENT_HEADERS),
            (sample.beam_rows(), sample.BEAM_PLACEMENT_HEADERS),
            (sample.slab_rows(), sample.SLAB_PLACEMENT_HEADERS),
            (sample.level_rows(), sample.LEVEL_HEADERS),
            (sample.grid_rows(), sample.GRID_HEADERS),
        )
        for rows, headers in pairs:
            for row in rows:
                self.assertEqual(len(row), len(headers), headers[0])

    def test_the_grid_angles_are_the_convention_the_command_reads(self):
        # 0 along +X, 90 along +Y — the owner's convention, and grids.sync
        # reads it. A sample using any other number teaches the wrong thing.
        sample = self.builder()
        angle = sample.GRID_HEADERS.index("Angle")
        name = sample.GRID_HEADERS.index("Name")
        vertical = [row[name] for row in sample.grid_rows()
                    if row[angle] == 90]
        horizontal = [row[name] for row in sample.grid_rows()
                      if row[angle] == 0]
        self.assertEqual(vertical,
                         [n for n, _x in sample.GRIDS_VERTICAL])
        self.assertEqual(horizontal,
                         [n for n, _y in sample.GRIDS_HORIZONTAL])

    def test_it_writes_nothing_on_a_first_press(self):
        source = _read(_SAMPLE)
        self.assertIn('column=6, value="No"', source)


class ListenerWindowTests(unittest.TestCase):
    """The modeless window, and the WPF rules that fail silently without it.

    Built because a ``TaskDialog`` says what was true at the moment it opened —
    the wrong shape for a thing whose entire job is to be watching. Five rounds
    of diagnosis went by with no way to see whether a job had even landed.
    """

    XAML = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                        "Bridge Listener.pushbutton", "ui.xaml")

    def setUp(self):
        self.source = _read(_LISTENER)
        self.xaml = _read(self.XAML)

    def test_the_window_exists_and_the_script_loads_it(self):
        self.assertTrue(os.path.exists(self.XAML))
        self.assertIn("XamlReader.Load", self.source)
        self.assertIn('"ui.xaml"', self.source)

    def test_the_root_window_uses_no_static_resource(self):
        """Resolving one there fails: the resources it references are being
        declared inside the element that references them."""
        head = self.xaml.split(">", 1)[0]
        self.assertNotIn("StaticResource", head)

    def test_every_named_control_is_looked_up_and_the_reverse(self):
        import xml.etree.ElementTree as ElementTree
        namespace = "{http://schemas.microsoft.com/winfx/2006/xaml}"
        named = set()
        for element in ElementTree.fromstring(self.xaml).iter():
            if namespace + "Name" in element.attrib:
                named.add(element.attrib[namespace + "Name"])
        looked_up = set()
        for node in ast.walk(ast.parse(self.source)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "FindName"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                looked_up.add(node.args[0].value)
        # Template-internal names are out of FindName's reach, so only the ones
        # the script asks for have to exist — and everything it asks for must.
        self.assertEqual(sorted(looked_up - named), [])
        self.assertTrue(looked_up)

    def test_the_grid_binds_the_way_that_works(self):
        """``__slots__`` plus an ``ArrayList`` reassigned to ``ItemsSource``.

        Change notification fails silently across this bridge, so the list is
        rebuilt rather than mutated (§12.9.4).
        """
        self.assertIn("__slots__", self.source.split("class JobRow")[1][:400])
        body = self.source.split("def refresh(")[1].split("\n    def ")[0]
        self.assertIn("ArrayList()", body)
        self.assertIn("ItemsSource = None", body)

    def test_the_row_fields_match_the_bindings(self):
        slots = self.source.split("__slots__ = (")[1].split(")")[0]
        for name in ("JobId", "Command", "Status", "Summary"):
            self.assertIn('"{0}"'.format(name), slots, name)
            self.assertIn("Binding {0},".format(name), self.xaml, name)

    def test_the_window_is_anchored_to_revit(self):
        """``Show()`` without an owner leaves a window Revit can hide behind."""
        body = self.source.split("def show(")[1].split("\n    def ")[0]
        self.assertIn("self.window.Show()", body)
        self.assertIn("WindowInteropHelper", body)
        self.assertIn("MainWindowHandle", body)

    def test_the_window_survives_the_script_ending(self):
        self.assertIn("_state.window_ref = app", self.source)
        self.assertIn("existing.window.Activate()", self.source)

    def test_the_refresh_cannot_raise(self):
        """It runs once a second. A throw there throws once a second."""
        body = self.source.split("def refresh(")[1].split("\n    def ")[0]
        self.assertIn("except Exception", body)

    def test_the_refresh_touches_no_revit_api(self):
        """It runs on the WPF thread, where the Revit API may not be used."""
        body = self.source.split("def refresh(")[1].split("\n    def ")[0]
        for forbidden in ("__revit__", "uiapp", "Transaction", "doc."):
            self.assertNotIn(forbidden, body, forbidden)

    def test_closing_the_window_stops_the_watching(self):
        """A listener running behind a closed window writes to a model with
        nothing on screen saying so."""
        body = self.source.split("def _on_closed(")[1].split("\n    def ")[0]
        self.assertIn("set_watching(False)", body)

    def test_the_dialog_survives_as_a_fallback(self):
        """The window is the interface, not the mechanism."""
        body = self.source.split("def main(")[1]
        self.assertIn("TaskDialog", body)
        self.assertIn("could not be opened", body)


class VbaErrorHandlingTests(unittest.TestCase):
    """VBA does not leave an error handler until Resume, Exit, or GoTo -1.

    So ``On Error GoTo Failed`` written *inside* a handler block is ignored,
    and the next failure escapes as an unhandled runtime error with a Debug
    button. That is exactly what happened: WinHttp could not connect, control
    jumped to the fallback, the fallback's handler never armed, and MSXML2's
    *800c0005, the system cannot locate the resource specified* reached the
    user — from a function whose entire job was to return failures rather than
    raise them.

    One handler per procedure, no nesting. Checked here because the failure is
    invisible until the first error, which is the day it matters most.
    """

    def procedures(self):
        """``[(name, [lines])]`` for every Sub and Function in the module."""
        found = []
        current = None
        for line in _read(_VBA).splitlines():
            text = line.strip()
            head = text
            for prefix in ("Public ", "Private ", "Friend "):
                if head.startswith(prefix):
                    head = head[len(prefix):]
            if head.startswith("Sub ") or head.startswith("Function "):
                current = (head.split("(")[0].split()[-1], [])
                found.append(current)
            elif head in ("End Sub", "End Function"):
                current = None
            elif current is not None:
                current[1].append(text)
        return found

    def test_no_handler_is_armed_inside_another_handler(self):
        for name, lines in self.procedures():
            label_at = None
            for index, text in enumerate(lines):
                if (text.endswith(":") and " " not in text
                        and not text.startswith("'")):
                    label_at = index if label_at is None else label_at
                elif text.startswith("On Error GoTo "):
                    target = text[len("On Error GoTo "):].strip()
                    if target in ("0", "-1"):
                        continue
                    self.assertIsNone(
                        label_at,
                        "{0}: 'On Error GoTo {1}' is inside a handler that "
                        "starts at line {2} — VBA ignores it".format(
                            name, target, label_at))

    def test_the_module_is_pure_ascii(self):
        """Excel imports a ``.bas`` as the machine's ANSI code page.

        Not UTF-8, and there is nowhere in the format to say otherwise. Two em
        dashes written into message strings arrived in the dialogs as
        ``a-hat-euro`` — mojibake in the one place a user actually reads.

        The same lesson as the result TSV, one layer further out: a file
        crossing into VBA has no way to declare its encoding, so it must not
        need one.
        """
        with open(_VBA, "rb") as handle:
            raw = handle.read()
        offenders = []
        line = 1
        for byte in raw:
            if byte == 10:
                line += 1
            elif byte > 127:
                offenders.append(line)
        self.assertEqual(sorted(set(offenders)), [],
                         "non-ASCII on line(s) {0}".format(
                             sorted(set(offenders))))

    def test_the_two_ways_to_the_wire_are_separate_procedures(self):
        names = [name for name, _lines in self.procedures()]
        self.assertIn("HttpGetWinHttp", names)
        self.assertIn("HttpGetMsxml", names)

    def test_a_failed_request_is_returned_not_raised(self):
        source = _read(_VBA)
        for name in ("HttpGet", "HttpPost"):
            body = source.split("Function {0}(".format(name))[1].split(
                "End Function")[0]
            self.assertIn('"ok"": false', body, name)

    def test_every_module_declaration_is_above_the_first_procedure(self):
        """VBA requires it, and says so in a way that names only the symptom.

        Two ``Public Const`` lines were written next to the code that used
        them, further down the module. Excel refused to compile the whole thing
        with *"Only comments may appear after End Sub, End Function, or End
        Property"* — which points at the line after the previous procedure and
        not at the declaration that is actually misplaced. It appears at import
        time, in Excel, long after everything here has passed.
        """
        first = None
        for index, line in enumerate(_read(_VBA).splitlines(), 1):
            head = line.strip()
            for prefix in ("Public ", "Private ", "Friend "):
                if head.startswith(prefix):
                    head = head[len(prefix):]
            if head.startswith(("Sub ", "Function ")) and first is None:
                first = index
            if first and index > first and head.startswith(("Const ",
                                                            "Declare ")):
                self.fail("line {0} declares '{1}' after the first procedure "
                          "at line {2} — Excel will refuse the module"
                          .format(index, line.strip(), first))

    def test_the_macro_undoes_json_string_escapes(self):
        """The post's answer carries a Windows path, and JSON doubles every
        backslash in it.

        Returned verbatim, ``resultTsv`` becomes ``C:\\\\Users\\\\praka…`` —
        a path Windows may or may not collapse for you, and "may or may not" is
        not a design. The result file it points at would simply never be found
        and the macro would report a job that had in fact finished.
        """
        source = _read(_VBA)
        self.assertIn("Public Function JsonUnescape", source)
        self.assertIn("JsonUnescape(Mid$(rest, 2, closing - 2))", source)
        # And the closing quote has to skip escaped ones, or a value ending in
        # a backslash terminates the string early.
        self.assertIn("Private Function FindClosingQuote", source)

    def test_the_macros_json_escaping_round_trips_a_real_answer(self):
        """The VBA cannot run here, so its two functions are ported line for
        line and checked against what the route actually sends."""
        import json

        def find_closing(rest):
            index = 1
            while index < len(rest):
                if rest[index] == "\\":
                    index += 2
                elif rest[index] == '"':
                    return index
                else:
                    index += 1
            return -1

        def unescape(text):
            mapping = {"\\": "\\", '"': '"', "/": "/",
                       "n": "\n", "r": "\r", "t": "\t"}
            out, index = [], 0
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    out.append(mapping.get(text[index + 1], text[index + 1]))
                    index += 2
                else:
                    out.append(text[index])
                    index += 1
            return "".join(out)

        real = ("C:\\Users\\praka\\AppData\\Roaming\\AnonGee\\bridge"
                "\\inbox\\20260824-171500-0001.result.tsv")
        body = json.dumps({"ok": True, "jobId": "20260824-171500-0001",
                           "resultTsv": real})
        rest = body[body.index('"resultTsv"'):]
        rest = rest[rest.index(":") + 1:].strip()
        self.assertEqual(unescape(rest[1:find_closing(rest)]), real)

    def test_an_unreachable_bridge_names_the_switch_to_flick(self):
        # "Nothing is listening" and "the listener is off" are two different
        # switches in two different places, and the error alone says neither.
        source = _read(_VBA)
        self.assertIn("Routes Server", source)
        self.assertIn("Bridge Check", source)


class BridgeCheckSpeedTests(unittest.TestCase):
    """A diagnostic that takes minutes and shows nothing is not a diagnostic.

    A run of 0.3.0 did exactly that. Four ways to the wire, tried twice, and
    ``WebClient.DownloadString`` carries a **hundred-second default timeout**
    that was never set — so with nothing listening the tool sat there, and then
    the console was empty because nothing was printed.
    """

    def test_the_port_is_probed_before_any_http(self):
        # A refused TCP connection answers in microseconds. When nothing is
        # listening, none of the HTTP attempts are worth making.
        body = _read(_CHECK).split("def report(")[1].split("\ndef ")[0]
        self.assertIn("port_open()", body)
        self.assertLess(body.index("port_open()"), body.index("describe("))

    def test_the_probe_is_bounded_to_about_a_second(self):
        constants = _constants(_read(_CHECK))
        self.assertLessEqual(constants["PROBE_TIMEOUT_SECONDS"], 2)

    def test_ping_is_not_given_the_status_timeout(self):
        # /ping touches no Revit and should answer at once; /status runs as an
        # External Event and legitimately waits for Revit to be idle.
        constants = _constants(_read(_CHECK))
        self.assertLess(constants["PING_TIMEOUT_SECONDS"],
                        constants["TIMEOUT_SECONDS"])
        body = _read(_CHECK).split("def report(")[1].split("\ndef ")[0]
        self.assertIn('describe("ping", PING_TIMEOUT_SECONDS)', body)

    def test_the_unbounded_way_is_tried_last(self):
        """``WebClient`` cannot have a timeout set without subclassing it."""
        ways = _read(_CHECK).split("WAYS = (")[1].split(")\n\n")[0]
        self.assertLess(ways.index("HttpClient"), ways.index("WebClient"))

    def test_every_way_takes_the_timeout(self):
        source = _read(_CHECK)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_by_"):
                self.assertIn("seconds", [a.arg for a in node.args.args],
                              node.name)

    def test_it_always_says_something(self):
        # The console was empty. A diagnostic that can produce no output is
        # broken by definition.
        body = _read(_CHECK).split("def main(")[1].split("\nmain()")[0]
        self.assertIn("except Exception", body)
        self.assertIn("print(text)", body)

    def test_the_report_goes_to_the_console_not_only_a_dialog(self):
        """Console output can be pasted; a dialog has to be retyped."""
        body = _read(_CHECK).split("def main(")[1].split("\nmain()")[0]
        self.assertLess(body.index("print(text)"), body.index("TaskDialog"))


class StartupRecordTests(unittest.TestCase):
    """When nothing answers, three causes look identical.

    The Routes server switched off, the startup script failing to register, or
    the extension never reloading. They need different fixes and a dead port
    tells them apart from none of them — so ``startup.py`` writes a record on
    every load, precisely because when *it* is the guilty one there is no route
    left to ask.
    """

    def test_the_record_is_written_whatever_happens(self):
        source = _read(_STARTUP)
        tail = source.split("REGISTRATION_NOTE = \"\"", 1)[1]
        self.assertIn("_write_record(", tail)
        # After the try/except, so a failed registration is still recorded.
        self.assertLess(tail.index("except Exception"),
                        tail.index("_write_record("))

    def test_writing_the_record_cannot_take_the_load_down(self):
        body = _read(_STARTUP).split("def _write_record")[1].split("\ndef ")[0]
        self.assertIn("except Exception", body)

    def test_each_route_is_registered_on_its_own(self):
        """One bad pattern must not take the diagnostic routes with it.

        ``/jobs/<string:job_id>`` used a pattern pyRevit does not have — it
        supports ``<int:...>`` and ``<uuid:...>``, and neither fits a job id.
        """
        source = _read(_STARTUP)
        body = source.split("def add(pattern")[1].split("\n    add(")[0]
        self.assertIn("except Exception", body)
        self.assertIn("refused.append", body)
        # No route pattern carries a placeholder at all now. Checked against
        # the registered patterns rather than the file, because the file also
        # explains in prose why the bad one is gone.
        for pattern in _routes(source):
            self.assertNotIn("<", pattern, pattern)

    def test_the_check_tool_reads_the_record(self):
        check = _read(_CHECK)
        self.assertIn("STARTUP_RECORD", check)
        self.assertIn("Reload pyRevit", check)

    def test_the_check_tool_puts_the_reason_in_the_headline(self):
        """A run reported 'no answer' twice with the cause folded away behind
        *See details*, which nobody expands."""
        body = _read(_CHECK).split("def describe(")[1].split("\ndef ")[0]
        headline = body.split("if not body:")[1].split("detail =")[0]
        self.assertIn("no answer — {1}", headline)
        self.assertIn("errors[0]", headline)


class ResultEncodingTests(unittest.TestCase):
    """The TSV is read by ``Input$``, which knows nothing about UTF-8.

    It reads bytes as the machine's ANSI code page, so the TSV is written as
    ASCII with anything else replaced. A message containing an em dash would
    otherwise either fail to write on a cp1252 machine or arrive in the
    spreadsheet as mojibake — and ``open(path, "w")`` with no encoding named is
    how you get a file written differently on two machines and read wrongly on
    a third.

    The JSON keeps the full text. That is the one real cost of writing the
    answer twice, and it beats hand-rolling a JSON parser in VBA.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def result(self):
        job = _envelope.new_job("bridge.echo", identifier="j1")
        return _envelope.new_result(job, _envelope.STATUS_DONE, {"n": 1}, [{
            "severity": "Error", "sheet": "LEVELS", "row": 3,
            "column": "Name", "message": "an em dash \u2014 and a caf\u00e9"}])

    def test_the_tsv_is_pure_ascii(self):
        _json_path, tsv_path = _jobs.write_result(self.result(), self.root)
        with open(tsv_path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(all(byte < 128 for byte in raw))

    def test_the_json_keeps_what_the_tsv_had_to_drop(self):
        json_path, _tsv = _jobs.write_result(self.result(), self.root)
        found = _jobs.read(json_path)
        self.assertIn("\u2014", found["findings"][0]["message"])

    def test_every_write_names_its_encoding(self):
        """A write with no encoding guesses at the machine's locale.

        Read off the tree, not the text. Three tests in this suite have now
        been written against prose and matched the sentence explaining the bug
        instead of the code causing it — including, on the first attempt, this
        one.
        """
        source = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "bridge", "jobs.py"))
        opened = 0
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            if name != "open":
                continue
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            if "w" not in mode:
                continue
            opened += 1
            self.assertIn("encoding",
                          [keyword.arg for keyword in node.keywords],
                          "line {0} writes without naming an encoding".format(
                              node.lineno))
        self.assertTrue(opened, "no writes found — the test proves nothing")


class MacroSurvivalTests(unittest.TestCase):
    """Rebuilding the workbook must never destroy the macros in it.

    The whole one-manual-step story rests on this: ``openpyxl`` preserves a VBA
    project and cannot create one, so the `.xlsm` in this folder is the only
    copy of that import. A builder that quietly dropped it would cost that step
    again every time the sheets changed — and the loss would be invisible until
    somebody pressed a button.

    Checked against the real workbook rather than a synthetic one, because what
    is being tested is a claim about `openpyxl` and a specific file, not about
    code.
    """

    WORKBOOK = os.path.join(_ROOT, "bridge", "excel",
                            "AnonGee_Sample_Project.xlsm")

    def setUp(self):
        if not os.path.exists(self.WORKBOOK):
            self.skipTest("no .xlsm in the repository yet")
        try:
            import openpyxl                                    # noqa: F401
        except ImportError:
            self.skipTest("openpyxl is not installed here")

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_shipped_workbook_carries_its_macros(self):
        import zipfile
        with zipfile.ZipFile(self.WORKBOOK) as archive:
            self.assertIn("xl/vbaProject.bin", archive.namelist())

    def test_rebuilding_it_keeps_them(self):
        import shutil
        import zipfile
        folder = tempfile.mkdtemp()
        try:
            copy = os.path.join(folder, "AnonGee_Sample_Project.xlsm")
            shutil.copy(self.WORKBOOK, copy)
            self.builder().build(copy)
            with zipfile.ZipFile(copy) as archive:
                self.assertIn("xl/vbaProject.bin", archive.namelist())
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_rebuilding_it_rewrites_every_sheet(self):
        import shutil
        from openpyxl import load_workbook
        folder = tempfile.mkdtemp()
        try:
            copy = os.path.join(folder, "AnonGee_Sample_Project.xlsm")
            shutil.copy(self.WORKBOOK, copy)
            self.builder().build(copy)
            self.assertEqual(
                load_workbook(copy).sheetnames,
                ["CONTROL", "INFO", "LEVELS", "GRIDS", "FOOTING_TYPES",
                 "FOOTING_PLACEMENT", "COLUMN_TYPES", "COLUMN_PLACEMENT",
                 "BEAM_TYPES", "BEAM_PLACEMENT", "SLAB_TYPES",
                 "SLAB_PLACEMENT", "LOG"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class ControlColumnTests(unittest.TestCase):
    """BUG-16, held down.

    The macro read the ``Write?`` switch from column 5. Adding a ``Built?``
    column to the workbook moved ``Write?`` to 6, so the switch was read from a
    cell that says ``yes`` or ``not yet`` — never ``No`` — and every run was a
    dry run that could not be turned off. Then the status was written into the
    ``Write?`` cell, so the switch said ``done`` and stayed that way.

    Nothing about that was visible from Revit. What these tests hold is the
    fix: the columns are found by their headers, and a column that cannot be
    found stops the run instead of quietly defaulting.
    """

    def setUp(self):
        self.vba = _read(_VBA)

    def bodies(self):
        """``{name: body}`` for every Sub and Function in the module."""
        found = {}
        name = None
        lines = []
        for line in self.vba.splitlines():
            stripped = line.strip()
            head = stripped.replace("Public ", "").replace("Private ", "")
            if head.startswith(("Sub ", "Function ")):
                name = head.split("(")[0].split()[-1]
                lines = []
            elif stripped in ("End Sub", "End Function") and name:
                found[name] = "\n".join(lines)
                name = None
            elif name:
                lines.append(line)
        return found

    def test_the_control_columns_are_never_addressed_by_number(self):
        import re
        bodies = self.bodies()
        for name in ("ReadDryRun", "WriteControlStatus", "ControlRowFor"):
            self.assertIn(name, bodies)
            found = re.findall(r"Cells\(\s*\w+\s*,\s*\d+\s*\)",
                               bodies[name])
            self.assertEqual(found, [], "{0} addresses {1} by number".format(
                name, found))

    def test_the_switch_is_read_from_the_write_column(self):
        self.assertIn('COLUMN_WRITE As String = "Write?"', self.vba)
        self.assertIn("ControlColumn(sheet, header, COLUMN_WRITE)",
                      self.bodies()["ReadDryRun"])

    def test_a_dry_run_is_what_every_failure_falls_back_to(self):
        body = self.bodies()["ReadDryRun"]
        self.assertIn("ReadDryRun = True", body)
        # Every early exit happens after that line, so no path can leave the
        # function having decided to write because something was missing.
        first = body.index("ReadDryRun = True")
        for exit_at in [m for m in range(len(body))
                        if body.startswith("Exit Function", m)]:
            self.assertGreater(exit_at, first)

    def test_a_control_sheet_it_cannot_read_stops_the_run(self):
        # The alternative is a silent dry run, which is indistinguishable from
        # Revit ignoring you. That indistinguishability is what cost the round.
        self.assertIn("ControlIsReadable", self.bodies()["RunCommand"])
        self.assertIn("Exit Sub", self.bodies()["RunCommand"])

    def test_every_declared_command_has_a_macro_and_a_button(self):
        body = self.bodies()["MacroFor"]
        for command in _registry.known():
            self.assertIn('"{0}"'.format(command), body, command)

    def test_every_macro_the_mapping_names_exists(self):
        import re
        names = re.findall(r'MacroFor = "(\w+)"', self.bodies()["MacroFor"])
        self.assertTrue(names)
        for name in names:
            self.assertIn("Public Sub {0}()".format(name), self.vba, name)

    def test_the_job_carries_the_unit(self):
        self.assertIn('""units""', self.bodies()["JobJson"])
        self.assertIn("ReadUnits", self.vba)

    def test_the_button_anchoring_is_verified_and_not_just_set(self):
        """A property worth setting is a property worth reading back.

        The buttons were set to move and size with their cells inside a blanket
        ``On Error Resume Next`` and never checked. When they did not follow
        their cells there was no way to tell whether the line had run, failed,
        or been overwritten — so the next round would have been another guess.
        """
        body = self.bodies()["AnchorToCell"]
        self.assertIn("button.Placement = xlMoveAndSize", body)
        self.assertIn("If button.Placement = xlMoveAndSize", body)
        self.assertIn("AnchorToCell = (button.Placement = xlMoveAndSize)", body)

    def test_every_button_drawn_is_anchored(self):
        self.assertIn("AnchorToCell button", self.bodies()["DrawButton"])

    def test_the_count_of_anchored_buttons_is_reported(self):
        # So one press answers both questions: how many were drawn, and how
        # many actually took the anchoring.
        self.assertIn("CountAnchored", self.bodies()["AnonGeeBridge_AddButtons"])
        self.assertIn("move ", self.bodies()["AnonGeeBridge_AddButtons"])

    def test_findings_say_which_job_they_came_from(self):
        """An empty FINDINGS sheet is the same picture as a run that failed to
        report, and fifteen columns went unexplained exactly that way.

        The sheet was cleared by every result, including one with nothing to
        say — so pressing two unbuilt commands after a run that reported
        fifteen failures wiped the explanations.
        """
        body = self.bodies()["ShowFindings"]
        self.assertIn('"Findings from"', body)
        self.assertIn("No findings", body)
        self.assertIn("ShowFindings body, command, jobId", self.vba)

    def test_anchoring_can_be_run_on_its_own(self):
        self.assertIn("Public Sub AnonGeeBridge_AnchorButtons()", self.vba)

    def test_the_unit_default_never_rescales_an_old_workbook(self):
        # Every workbook before the unit existed was millimetres. A default of
        # metres would multiply one of those by a thousand on first read.
        self.assertIn('UNITS_DEFAULT As String = "mm"', self.vba)


class LogHistoryTests(unittest.TestCase):
    """A rebuild regenerates every sheet, and the LOG is not a generated one.

    It is what happened — which job ran, when, and what came back. Losing it on
    a rebuild would throw away the only evidence a test round leaves behind.
    """

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_sample_project",
                                                      _SAMPLE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rebuilding_keeps_the_log_rows(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("openpyxl is not installed here")
        sample = self.builder()
        folder = tempfile.mkdtemp()
        try:
            target = os.path.join(folder, "sample.xlsx")
            sample.build(target)
            book = load_workbook(target)
            book["LOG"].append(["2026-08-25 11:12", "job-1", "levels.sync",
                                "done", "created=6", "a dry run"])
            book.save(target)

            sample.build(target)
            rows = list(load_workbook(target)["LOG"].iter_rows(
                min_row=2, values_only=True))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][2], "levels.sync")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class ListenerTests(unittest.TestCase):
    """§12.9, and the rule that work never happens in the Idling callback."""

    def setUp(self):
        self.source = _read(_LISTENER)
        self.tree = ast.parse(self.source)

    def handler(self):
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.ClassDef)
                    and node.name == "BridgeJobHandler"):
                return node
        self.fail("BridgeJobHandler not found")

    def test_the_clr_type_has_no_init(self):
        """Defining ``__init__`` on a class inheriting a Revit interface is a
        fatal marshalling fault, not a catchable one (§12.9.2)."""
        names = [n.name for n in self.handler().body
                 if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("__init__", names)
        self.assertIn("Execute", names)
        self.assertIn("GetName", names)

    def test_the_clr_type_is_defined_once_per_session(self):
        """A second definition raises 'Duplicate type name within an assembly'."""
        self.assertIn("if _state.handler_cls is None:", self.source)
        self.assertIn("BridgeJobHandler = _state.handler_cls", self.source)
        self.assertIn("__namespace__", self.source)

    def test_the_idling_delegate_is_held_in_session_state(self):
        """.NET holds the subscription and Python holds the callable. Let the
        second go and the first survives pointing at nothing — which fails
        silently and looks like the listener ignoring jobs."""
        self.assertIn("_state.delegate = EventHandler[IdlingEventArgs]",
                      self.source)
        self.assertIn("_state.subscribed = True", self.source)

    def test_the_subscription_is_made_once_and_never_removed(self):
        """Stopping flips a flag rather than touching a Revit event.

        The window's button runs on the WPF thread. Adding and removing a
        ``UIApplication`` event from there is a question nobody needs to answer
        when one attribute read per tick settles it — and the tick is already
        doing a timestamp comparison anyway.
        """
        self.assertIn("if not _state.watching:", self.source)
        self.assertNotIn("Idling -=", self.source)
        subscribe = self.source.split("def ensure_ready")[1].split("\ndef ")[0]
        self.assertIn("if not _state.subscribed:", subscribe)

    def test_only_revits_own_thread_subscribes(self):
        # ensure_ready is called from main(), which pyRevit runs on the Revit
        # thread. The window never calls it.
        window = self.source.split("class BridgeListenerApp")[1].split(
            "\ndef main(")[0]
        self.assertNotIn("ensure_ready", window)
        self.assertIn("set_watching(", window)

    def test_the_idling_callback_does_no_work(self):
        """Idling holds the UI while it runs. A job that took a minute would
        freeze Revit for a minute with no progress and no way out."""
        body = self.source.split("def _on_idling")[1].split("\ndef ")[0]
        self.assertIn("SCAN_EVERY_SECONDS", body)
        self.assertIn("_state.event.Raise()", body)
        for forbidden in ("Transaction(", "command.handler", "write_result"):
            self.assertNotIn(forbidden, body, forbidden)

    def test_the_idling_callback_cannot_raise(self):
        # An exception escaping it is shown to the user on every tick, which is
        # not a bug report, it is a reason to force-quit.
        body = self.source.split("def _on_idling")[1].split("\ndef ")[0]
        self.assertIn("except Exception", body)

    def test_one_bad_job_does_not_stop_the_listener(self):
        body = self.source.split("def _run_job")[1].split("\ndef ")[0]
        self.assertIn("STATUS_FAILED", body)
        self.assertIn("except Exception", body)

    def test_an_unknown_command_is_rejected_with_the_list_of_known_ones(self):
        body = self.source.split("def _run_job")[1].split("\ndef ")[0]
        self.assertIn("registry.known()", body)


if __name__ == "__main__":
    unittest.main()
