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

__version__ = "0.4.0"

API_NAME = "anongee"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 48884


# ---------------------------------------------------------------------------
# Where a job lives
# ---------------------------------------------------------------------------
# These rules are also in ``anongee_toolkit/bridge/jobs.py``. Duplication is
# deliberate: startup.py must remain IronPython 2.7 compatible and cannot import
# the CPython toolkit. tests/test_bridge.py holds the two contracts together.

ENV_HOME = "ANONGEE_BRIDGE_HOME"
LOCALAPPDATA_PARTS = ("Zxaidman", "AnonGee", "bridge")
APPDATA_PARTS = ("AnonGee", "bridge")
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"

RECENT_LIMIT = 20
_counter = [0]


def bridge_home():
    """Bridge home: explicit override, local default, roaming fallback, home."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return os.path.join(localappdata, *LOCALAPPDATA_PARTS)
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
    """The posted envelope as a dict, whatever shape the framework hands over."""
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
    """Which Python is running this, in as much detail as it will give."""
    facts = {
        "version": sys.version.replace("\n", " "),
        "platform": sys.platform,
    }
    try:
        import platform
        facts["implementation"] = platform.python_implementation()
    except Exception:
        facts["implementation"] = "unknown"
    return facts


def _toolkit():
    """Whether this engine can see ``anongee_toolkit``, and where from."""
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
    """Register the routes. ``(api, note)`` — never raises."""
    try:
        from pyrevit import routes
    except Exception as error:
        return None, "pyrevit.routes is not available: {0}".format(error)

    try:
        api = routes.API(API_NAME)
    except Exception as error:
        return None, "could not create the {0} API: {1}".format(API_NAME, error)

    registered = []
    refused = []

    def add(pattern, methods, handler):
        try:
            api.route(pattern, methods=methods)(handler)
            registered.append("{0} {1}".format("/".join(methods), pattern))
        except Exception as error:
            refused.append("{0}: {1}".format(pattern, error))

    def ping():
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
        try:
            return {"ok": True, "home": bridge_home(),
                    "jobs": _recent(bridge_home())}
        except Exception as error:
            return {"ok": False, "note": "{0}".format(error)}

    add("/ping", ["GET"], ping)
    add("/status", ["GET"], status)
    add("/jobs", ["POST"], submit)
    add("/jobs", ["GET"], listing)

    _routes_registered.extend(registered)
    note = "; ".join(refused)
    if not registered:
        note = note or "no route would register"
    return api, note


# ---------------------------------------------------------------------------
# The Filter View Manager's dockable pane
# ---------------------------------------------------------------------------
# RegisterDockablePane must be called during OnStartup, before any document is
# open -- a pushbutton runs far too late and Revit refuses it. The pane stays
# HIDDEN until the ribbon button shows it, so this costs no UI and needs no
# document; it is only here because Revit gives it nowhere else to be.
#
# Wrapped to the same standard as everything else in this file: it must never
# raise. A panel is a convenience on top of one tool, and it must not be able
# to cost the user every other tool on the tab. What happened is written to its
# own record, which the pushbutton reads back and reports -- there is no route
# to ask and no pane to look at when registration is the thing that failed.

PANE_NOTE = ""


def _register_pane():
    """``(registered, note)`` -- never raises."""
    try:
        import anongee_filterpane
    except Exception as error:
        return False, "anongee_filterpane is not importable: {0}".format(error)

    controlled = globals().get("__uicontrolledapplication__")
    try:
        outcome = anongee_filterpane.register(controlled)
    except Exception as error:
        return False, "the pane did not register: {0}".format(error)
    return bool(outcome.get("registered")), outcome.get("note", "")


try:
    PANE_REGISTERED, PANE_NOTE = _register_pane()
except Exception as _pane_error:
    PANE_REGISTERED = False
    PANE_NOTE = "the pane did not register: {0}".format(_pane_error)


REGISTRATION_NOTE = ""
_routes_registered = []

try:
    _api, REGISTRATION_NOTE = register()
except Exception as _error:
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
    "bridge_home": bridge_home(),
    "routes": list(_routes_registered),
    "note": REGISTRATION_NOTE,
    "registered": bool(_routes_registered),
    "pane_registered": PANE_REGISTERED,
    "pane_note": PANE_NOTE,
})
