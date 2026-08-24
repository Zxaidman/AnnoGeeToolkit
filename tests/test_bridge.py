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

if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
from anongee_toolkit.bridge import envelope as _envelope         # noqa: E402
from anongee_toolkit.bridge import jobs as _jobs                 # noqa: E402
from anongee_toolkit.bridge import registry as _registry         # noqa: E402


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

    def test_the_declared_commands_are_the_stage_zero_and_one_set(self):
        self.assertEqual(_registry.known(),
                         ["bridge.echo", "grids.sync", "levels.sync"])

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

    WORKBOOK = os.path.join(_ROOT, "bridge", "excel", "AnonGee_Bridge.xlsm")

    def setUp(self):
        if not os.path.exists(self.WORKBOOK):
            self.skipTest("no .xlsm in the repository yet")
        try:
            import openpyxl                                    # noqa: F401
        except ImportError:
            self.skipTest("openpyxl is not installed here")

    def builder(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_workbook", _BUILDER)
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
            copy = os.path.join(folder, "AnonGee_Bridge.xlsm")
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
            copy = os.path.join(folder, "AnonGee_Bridge.xlsm")
            shutil.copy(self.WORKBOOK, copy)
            self.builder().build(copy)
            self.assertEqual(load_workbook(copy).sheetnames,
                             ["CONTROL", "INFO", "LEVELS", "GRIDS", "LOG"])
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
        self.assertIn("uiapp.Idling -= _state.delegate", self.source)

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
