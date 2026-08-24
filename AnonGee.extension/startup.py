# -*- coding: utf-8 -*-
"""The bridge's front door: HTTP routes pyRevit serves from inside Revit.

pyRevit runs an HTTP server **in the Revit process**. A route handler that
declares ``uiapp``, ``uidoc`` or ``doc`` is executed by pyRevit as an External
Event — which is the marshalling problem the modeless window solves by hand,
solved by the framework instead. That is the whole reason this is the right
transport for an Excel button rather than merely a clever one.

    http://localhost:48884/anongee/ping      the server, no Revit involved
    http://localhost:48884/anongee/status    the model, through an External Event

**This file is the spike** (`CRIT-1` in the repository's ``todo-list.md``). It
answers four questions that every estimate in the PRD is conditional on, and it
writes nothing to any model:

1. Does the Routes server start, and is the port reachable from Excel?
2. Does a handler declaring ``uiapp`` really get marshalled onto Revit's thread?
3. **Which Python engine runs a startup script**, and can it see the toolkit?
   pyRevit's startup runs on the core engine, which is IronPython; the toolkit
   is CPython 3 and lives in ``lib/py3``. If routes cannot reach it, commands
   have to be dispatched to a CPython script rather than handled here, and that
   is a fork in the architecture worth knowing about before stage 1 rather than
   during it.
4. What happens with no document open, and with a modal dialog up.

``/ping`` deliberately takes **no** Revit argument and ``/status`` does. If
``/ping`` answers and ``/status`` hangs, the server is fine and the marshalling
is not — which is the difference between a spike that answers and one that just
fails.

**Nothing here may raise.** A startup script that throws takes pyRevit's load
with it, and a broken bridge must never cost the user their other tools.

Written for IronPython 2.7 as well as CPython 3: no f-strings, no ``pathlib``,
nothing newer than 2.7, because which one runs this is question 3.
"""

import datetime
import json
import os
import sys

__version__ = "0.3.0"

#: The API name, and therefore the first path segment: ``/anongee/...``.
#: The Excel macro in ``bridge/excel/`` names the same string, and a test holds
#: the two together — a URL that disagrees with its route costs an afternoon and
#: looks like a network problem the whole time.
API_NAME = "anongee"

#: What pyRevit's Routes server listens on by default. Recorded here for the
#: macro and the documentation to agree with; the server decides its own port
#: and ``/ping`` reports the truth rather than this.
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 48884


# ---------------------------------------------------------------------------
# Where a job lives
# ---------------------------------------------------------------------------
# These rules are also in ``anongee_toolkit/bridge/jobs.py``, in CPython 3, and
# they have to agree. **That duplication is deliberate and it is the price of
# the engine split**: this file is loaded by pyRevit's core engine, which is
# IronPython 2.7, and the toolkit lives in ``lib/py3`` where this engine cannot
# reach it. What the two ends share is a folder layout, not a module.
#
# Held down two ways, because "two files must agree" is exactly the contract
# that rots: ``tests/test_bridge.py`` compares the constants, and ``/ping``
# reports the home this file computed so a mismatch shows up as a sentence in a
# dialog rather than as a job nobody ever sees.

ENV_HOME = "ANONGEE_BRIDGE_HOME"
APPDATA_PARTS = ("AnonGee", "bridge")
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"

#: Answered by ``/jobs`` when a caller wants the recent list rather than one
#: job. Twenty is enough to find the one you just posted and short enough that
#: the answer stays a mouthful.
RECENT_LIMIT = 20

#: Two presses in the same second are two jobs. Module scope, because this file
#: is loaded once per session and that is exactly the lifetime wanted.
_counter = [0]


def bridge_home():
    """The bridge folder. Same three rules as ``jobs.home()``, in order."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, *APPDATA_PARTS)
    return os.path.join(os.path.expanduser("~"), *HOME_PARTS)


def _ensure(root):
    for folder in (os.path.join(root, OUTBOX), os.path.join(root, INBOX)):
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder)
            except OSError:
                if not os.path.isdir(folder):
                    raise
    return root


def _next_job_id():
    _counter[0] += 1
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return "{0}-{1:04d}".format(stamp, _counter[0])


def _body(request):
    """The posted envelope as a dict, whatever shape the framework hands over.

    pyRevit has carried the body on more than one attribute across releases and
    may or may not have decoded it. Asking three questions costs nothing; being
    wrong about which one costs a run that fails with "the job is not an
    object" and no clue why.
    """
    for attribute in ("data", "body", "json"):
        raw = getattr(request, attribute, None)
        if raw is None:
            continue
        if isinstance(raw, dict):
            return raw, ""
        try:
            return json.loads(raw), ""
        except Exception as error:
            return None, "the body is not JSON: {0}".format(error)
    return None, "the request carried no body"


def _write_json(path, payload):
    """Written aside and renamed into place, so nothing reads half a file."""
    partial = path + ".partial"
    handle = open(partial, "w")
    try:
        handle.write(json.dumps(payload, indent=2, sort_keys=True))
    finally:
        handle.close()
    if os.path.exists(path):
        os.remove(path)
    os.rename(partial, path)
    return path


def _read_json(path):
    try:
        handle = open(path, "r")
        try:
            return json.loads(handle.read())
        finally:
            handle.close()
    except Exception:
        return None


def _recent(root, limit=RECENT_LIMIT):
    """The last few jobs and where each got to. Mirrors ``jobs.recent``."""
    seen = {}
    outbox = os.path.join(root, OUTBOX)
    if os.path.isdir(outbox):
        for name in os.listdir(outbox):
            for suffix, status in ((JOB_SUFFIX, "queued"),
                                   (RUNNING_SUFFIX, "running")):
                if name.endswith(suffix):
                    seen[name[:-len(suffix)]] = {
                        "jobId": name[:-len(suffix)], "status": status}

    inbox = os.path.join(root, INBOX)
    if os.path.isdir(inbox):
        for name in os.listdir(inbox):
            if not name.endswith(RESULT_SUFFIX):
                continue
            found = _read_json(os.path.join(inbox, name)) or {}
            identifier = name[:-len(RESULT_SUFFIX)]
            seen[identifier] = {
                "jobId": identifier,
                "status": found.get("status", ""),
                "command": found.get("command", ""),
                "summary": found.get("summary", {}),
            }

    ordered = sorted(seen.values(), key=lambda row: row["jobId"], reverse=True)
    return ordered[:limit]


#: Written on every load, whatever happens. **The only way to answer "why is
#: nothing listening?"** — because when the answer is "the routes never
#: registered", there is by definition no route to ask.
#:
#: A run reported both routes dead with no way to tell three cases apart: the
#: Routes server switched off, this script failing to register, or the
#: extension never reloading at all. They need different fixes and looked
#: identical. This file tells them apart.
STARTUP_RECORD = "startup.json"


def _write_record(payload):
    """Drop the startup record beside the job folders. Never raises."""
    try:
        root = _ensure(bridge_home())
        path = os.path.join(root, STARTUP_RECORD)
        handle = open(path, "w")
        try:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
        finally:
            handle.close()
        return path
    except Exception:
        return ""


def _engine():
    """Which Python is running this, in as much detail as it will give.

    Question 3, and the single most valuable thing the spike returns: it decides
    whether a route handler can import the toolkit or has to hand off to a
    CPython script.
    """
    facts = {
        "version": sys.version.replace("\n", " "),
        "platform": sys.platform,
    }
    try:
        import platform
        facts["implementation"] = platform.python_implementation()
    except Exception:
        # IronPython's platform module has been known to be partial. The
        # version string above still names it.
        facts["implementation"] = "unknown"
    return facts


def _toolkit():
    """Whether this engine can see ``anongee_toolkit``, and where from.

    Reported rather than judged. ``lib/py3`` is added to the path for CPython
    engines only, so the honest answer here may well be "no" — which is a
    finding, not a fault.
    """
    found = {"importable": False, "path_entries": [], "error": ""}
    for entry in sys.path:
        try:
            if "lib" in entry and ("py3" in entry or "py2" in entry):
                found["path_entries"].append(entry)
        except Exception:
            continue
    try:
        import anongee_toolkit
        found["importable"] = True
        found["location"] = getattr(anongee_toolkit, "__file__", "")
    except Exception as error:
        found["error"] = "{0}".format(error)
    return found


def _extension_root():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return ""


def register():
    """Register the routes. ``(api, note)`` — never raises.

    Separate from the module body so a test can call it and so the failure has
    somewhere to be reported rather than being swallowed at import.
    """
    try:
        from pyrevit import routes
    except Exception as error:
        return None, "pyrevit.routes is not available: {0}".format(error)

    try:
        api = routes.API(API_NAME)
    except Exception as error:
        return None, "could not create the {0} API: {1}".format(API_NAME, error)

    #: Filled in as each route takes. Reported by ``/ping`` and written to the
    #: startup record, so "which routes exist" is answerable from outside.
    registered = []
    refused = []

    def add(pattern, methods, handler):
        """Register one route, and let a bad one fail alone.

        The first version decorated five routes in a row with nothing between
        them. ``/jobs/<string:job_id>`` used a pattern pyRevit does not have —
        it supports ``<int:...>`` and ``<uuid:...>`` and neither fits a job id —
        so a single bad pattern was in a position to take the diagnostic routes
        down with it. Whether it actually did is a question that should never
        have needed asking.
        """
        try:
            api.route(pattern, methods=methods)(handler)
            registered.append("{0} {1}".format("/".join(methods), pattern))
        except Exception as error:
            refused.append("{0}: {1}".format(pattern, error))

    def ping():
        """The server, with no Revit in the question.

        No ``uiapp`` argument on purpose: this answers whether the server is up
        and reachable **even when Revit is busy**, which is exactly when a user
        will first suspect the bridge is broken.
        """
        return {
            "ok": True,
            "api": API_NAME,
            "bridge": __version__,
            "engine": _engine(),
            "toolkit": _toolkit(),
            "extension": _extension_root(),
            "bridge_home": bridge_home(),
            "commands_endpoint": "/{0}/jobs".format(API_NAME),
            "routes": list(_routes_registered),
            "revit_context": False,
        }

    def status(uiapp):
        """The model, through Revit's own thread.

        Declaring ``uiapp`` is what asks pyRevit to run this as an External
        Event. Everything below touches the API and so could only ever run
        there — if this returns, the marshalling is real.

        ``uidoc`` is read defensively rather than declared, so that *no document
        open* comes back as an answer instead of an error. A bridge that cannot
        say "nothing is open" is a bridge that looks broken every morning.
        """
        answer = {
            "ok": True,
            "api": API_NAME,
            "bridge": __version__,
            "revit_context": True,
            "document": None,
        }
        try:
            answer["revit"] = "{0} {1}".format(
                uiapp.Application.VersionName, uiapp.Application.VersionBuild)
            answer["user"] = uiapp.Application.Username
        except Exception as error:
            answer["revit"] = "could not be read: {0}".format(error)

        try:
            uidoc = uiapp.ActiveUIDocument
        except Exception as error:
            answer["document_error"] = "{0}".format(error)
            return answer

        if uidoc is None:
            answer["note"] = "no document is open"
            return answer

        try:
            doc = uidoc.Document
            answer["document"] = {
                "title": doc.Title,
                "path": doc.PathName,
                "workshared": bool(doc.IsWorkshared),
                "read_only": bool(doc.IsReadOnly),
            }
        except Exception as error:
            answer["document_error"] = "{0}".format(error)
        return answer

    # -- the doorbell ------------------------------------------------------
    # No Revit argument on any of these, deliberately. A job is *written*, not
    # run: the route stamps it, drops it in the outbox and returns. Whatever
    # picks it up runs on Revit's own thread when Revit is idle, which is the
    # only time the API may be used and is not now.
    #
    # It also means posting a job answers instantly even mid-command, which is
    # what stops Excel hanging on a five-thousand-element run.

    def submit(request):
        """Queue a job. Answers with its id and nothing else."""
        envelope, note = _body(request)
        if envelope is None:
            return {"ok": False, "status": "rejected", "note": note}
        if not isinstance(envelope, dict):
            return {"ok": False, "status": "rejected",
                    "note": "the job is not an object"}
        command = "{0}".format(envelope.get("command", "")).strip()
        if not command:
            return {"ok": False, "status": "rejected",
                    "note": "the job names no command"}

        # The id is stamped here rather than by the caller, so two workbooks
        # cannot mint the same one and quietly overwrite each other's job.
        identifier = envelope.get("jobId") or _next_job_id()
        envelope["jobId"] = identifier
        envelope["received"] = datetime.datetime.now().isoformat()
        if not envelope.get("envelope"):
            envelope["envelope"] = "1.0"

        try:
            root = _ensure(bridge_home())
            _write_json(os.path.join(root, OUTBOX, identifier + JOB_SUFFIX),
                        envelope)
        except Exception as error:
            return {"ok": False, "status": "rejected",
                    "note": "the job could not be written: {0}".format(error)}

        # The answer carries **where the result will be**, so no caller has to
        # work the bridge home out for itself. The macro would otherwise be a
        # third implementation of the three rules in `bridge_home` — in VBA,
        # untestable, and wrong the first time somebody sets the environment
        # variable. It waits for this file instead.
        return {
            "ok": True,
            "status": "queued",
            "jobId": identifier,
            "command": command,
            "home": root,
            "resultTsv": os.path.join(root, INBOX,
                                      identifier + ".result.tsv"),
            "resultJson": os.path.join(root, INBOX,
                                       identifier + RESULT_SUFFIX),
        }

    def listing():
        """The recent jobs and where each got to.

        No id in the URL, so it needs no route pattern and no query string —
        which is why the macro polls this rather than addressing one job. A
        caller finds the id it was given in the list.
        """
        try:
            return {"ok": True, "home": bridge_home(),
                    "jobs": _recent(bridge_home())}
        except Exception as error:
            return {"ok": False, "note": "{0}".format(error)}

    # There is no route for one job by id. pyRevit's patterns are
    # ``<int:...>`` and ``<uuid:...>``, and a job id — ``20260822-140311-0007``
    # — is neither. ``GET /jobs`` returns the recent list and a caller finds
    # its own id in it, which is what the macro does anyway and needs no
    # pattern at all.

    add("/ping", ["GET"], ping)
    add("/status", ["GET"], status)
    add("/jobs", ["POST"], submit)
    add("/jobs", ["GET"], listing)

    _routes_registered.extend(registered)
    note = "; ".join(refused)
    if not registered:
        note = note or "no route would register"
    return api, note


#: What happened when this module loaded. Written to the startup record too,
#: because a startup script that fails silently is a startup script nobody can
#: debug — and if it failed there is no route left to ask.
REGISTRATION_NOTE = ""

#: The routes that actually took. Reported by ``/ping`` and recorded on disk.
_routes_registered = []

try:
    _api, REGISTRATION_NOTE = register()
except Exception as _error:            # never take pyRevit's load down with us
    _api = None
    REGISTRATION_NOTE = "the bridge did not register: {0}".format(_error)

_write_record({
    "bridge": __version__,
    "loaded": datetime.datetime.now().isoformat(),
    "engine": _engine(),
    "toolkit": _toolkit(),
    "extension": _extension_root(),
    "api": API_NAME,
    "expect_at": "http://{0}:{1}/{2}".format(DEFAULT_HOST, DEFAULT_PORT,
                                             API_NAME),
    "routes": list(_routes_registered),
    "note": REGISTRATION_NOTE,
    "registered": bool(_routes_registered),
})
