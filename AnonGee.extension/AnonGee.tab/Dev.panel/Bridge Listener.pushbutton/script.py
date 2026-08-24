#! python3
# -*- coding: utf-8 -*-
"""The half of the bridge that does the work: watch for jobs, run them.

**The first line selects the engine and this tool cannot work without it.** It
imports ``anongee_toolkit`` from ``lib/py3``; on IronPython that path is not
added and openpyxl will not load at all. It ran anyway for one release, because
the ``bridge`` package happens to be Python 2.7-compatible — so it looked
correct right up until the first command that needed to read a workbook.

`CRIT-1` settled that pyRevit loads an extension's ``startup.py`` on IronPython
2.7, where the CPython 3 toolkit does not exist. So the HTTP route only ever
**writes a job into a folder** — and something on this side has to notice.

A pyRevit script runs once and ends, which is the wrong shape for watching. What
outlives a script is an event subscription, and Revit has exactly the right
event: ``UIApplication.Idling`` fires when Revit has nothing else to do, which is
also the only time the API may be used. So:

    Idling  →  is a job waiting?  →  claim it  →  ExternalEvent.Raise()
                                                        ↓
                                          the handler, on Revit's own thread

Two events rather than one, and the reason is worth stating: **work must not
happen in the Idling callback.** Idling fires constantly and holds the UI while
it runs, so a job that takes a minute would freeze Revit for a minute with no
progress and no way out. The callback does the cheapest possible thing — a
timestamp check, then one ``listdir`` — and hands off.

Claiming is a rename, which is atomic on one filesystem. Two Revit sessions
watching the same folder therefore produce one winner per job rather than two
runs of the same command against two models.

This button toggles. Press it to start watching, press it again to stop.

**§12.9 applies in full here.** The external event handler is a CLR type: no
``__init__``, ``__namespace__`` set **on the class**, and defined **once per
session** — a second
definition raises *"Duplicate type name within an assembly"*. The Idling delegate
has to be held in session state too, or .NET keeps the subscription and Python
garbage-collects the callable behind it.
"""

__title__ = "Bridge\nListener"
__author__ = "AnonGee"
__doc__ = """Watch for bridge jobs and run them.

An Excel button writes a job into a folder; this notices and runs it on Revit's
own thread. Toggle: press to start watching, press again to stop.

  • Idling tells it a job has arrived — the only moment the API may be used.
  • The work happens in an external event, never in the Idling callback, so
    Revit is not held while a job runs.
  • Claiming a job is an atomic rename, so two Revit sessions watching one
    folder never run the same job twice.

Jobs live under %APPDATA%\\AnonGee\\bridge (or ANONGEE_BRIDGE_HOME). Use
Bridge Check to see where this session thinks that is."""

__version__ = "0.3.0"

import datetime
import os
import sys
import time

from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler, TaskDialog
from Autodesk.Revit.UI.Events import IdlingEventArgs
from System import EventHandler

#: How often the Idling callback is allowed to touch the disk. Idling fires many
#: times a second; a ``listdir`` on every one of them is a tool that makes Revit
#: feel slow and gets uninstalled.
SCAN_EVERY_SECONDS = 1.5


def _bootstrap_lib_path():
    """Put ``lib/py3`` on the path, the way every tool here does."""
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        here = os.path.dirname(here)
        candidate = os.path.join(here, "lib", "py3")
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.append(candidate)
            return candidate
    return ""


_bootstrap_lib_path()

from anongee_toolkit.bridge import envelope as envelope_module   # noqa: E402
from anongee_toolkit.bridge import jobs as jobs_module           # noqa: E402
from anongee_toolkit.bridge import registry                      # noqa: E402
from anongee_toolkit import commands                             # noqa: E402


# ---------------------------------------------------------------------------
# Session state — everything that has to outlive this script
# ---------------------------------------------------------------------------
# A pyRevit script ends the moment it returns. The subscription must not, and
# neither must the CLR type: re-running the class statement below in the same
# session raises "Duplicate type name within an assembly" (§12.9.2).
_STATE = "anongee_bridge_listener_state"

if _STATE not in sys.modules:
    import types
    _state = types.ModuleType(_STATE)
    _state.handler_cls = None
    _state.handler = None
    _state.event = None
    _state.delegate = None      # held so .NET's subscription is not orphaned
    _state.watching = False
    _state.last_scan = 0.0
    _state.log = []
    sys.modules[_STATE] = _state
else:
    _state = sys.modules[_STATE]


def _note(text):
    """One line of history, capped. What the dialog shows when you toggle off."""
    _state.log.append("{0}  {1}".format(
        datetime.datetime.now().strftime("%H:%M:%S"), text))
    del _state.log[:-40]


# ---------------------------------------------------------------------------
# The worker — runs on Revit's thread
# ---------------------------------------------------------------------------

if _state.handler_cls is None:

    class BridgeJobHandler(IExternalEventHandler):
        """Runs one claimed job.

        Raised by the Idling callback rather than doing the watching itself,
        because this is where Revit lets go of the UI and the Idling callback is
        where it does not.

        **All three Python.NET interface rules apply, and the first one bit.**
        ``__namespace__`` has to be a *class* attribute: without it pythonnet
        routes ``BridgeJobHandler()`` to the interface's one-argument cast
        instead of building a real derived CLR type, and the failure is
        ``TypeError: interface takes exactly one argument``. It was written at
        module scope here, which does nothing at all — and the tool ran anyway
        for a release, because it was on IronPython where none of this applies.
        Fixing the engine is what exposed it.
        """

        __namespace__ = "AnonGee"

        #: Set after construction, but declared here so an instance always has
        #: it — rule 2 forbids the ``__init__`` that would otherwise do it.
        claimed = None

        def GetName(self):
            return "AnonGee Bridge Listener"

        def Execute(self, uiapp):
            claimed = getattr(self, "claimed", None)
            self.claimed = None
            if not claimed:
                return
            _run_job(uiapp, claimed)

    _state.handler_cls = BridgeJobHandler
else:
    BridgeJobHandler = _state.handler_cls


def _run_job(uiapp, claimed_path):
    """Read a claimed job, run it, write both forms of the answer.

    Nothing here may raise. A listener that dies on one bad job stops watching,
    and the user finds out when the next five do nothing — so a failure becomes
    a result file with ``status: failed`` and a sentence, which is a thing they
    can see.
    """
    started = datetime.datetime.now().isoformat()
    job = jobs_module.read(claimed_path) or {}

    problems = envelope_module.problems(job)
    if problems:
        _finish(job, envelope_module.rejected(job, "; ".join(problems)),
                claimed_path)
        return

    command = registry.get(job.get("command"))
    if command is None:
        _finish(job, envelope_module.rejected(
            job, "{0} is not a command this build knows. It has: {1}".format(
                job.get("command"), ", ".join(registry.known()))), claimed_path)
        return
    if not command.bound:
        _finish(job, envelope_module.rejected(
            job, "{0} is declared but not built yet".format(command.name)),
            claimed_path)
        return

    try:
        summary, findings, note = command.handler(uiapp, job)
        result = envelope_module.new_result(
            job, envelope_module.STATUS_DONE, summary, findings,
            started, datetime.datetime.now().isoformat(), note)
    except Exception as error:
        result = envelope_module.new_result(
            job, envelope_module.STATUS_FAILED, None, None,
            started, datetime.datetime.now().isoformat(),
            "{0}".format(error))

    _finish(job, result, claimed_path)


def _finish(job, result, claimed_path):
    try:
        jobs_module.write_result(result)
    except Exception as error:
        _note("could not write the result: {0}".format(error))
    jobs_module.finish(claimed_path)
    _note("{0} {1} — {2}".format(result.get("jobId", "?"),
                                 result.get("command", "?"),
                                 result.get("status", "?")))


# ---------------------------------------------------------------------------
# The watcher — runs on every Idling tick, and must stay cheap
# ---------------------------------------------------------------------------

def _on_idling(sender, args):
    """Cheapest possible check, then hand off. Never raises.

    An exception escaping an Idling handler is an exception Revit shows the user
    on every tick, which is not a bug report, it is a reason to force-quit.
    """
    try:
        now = time.time()
        if now - _state.last_scan < SCAN_EVERY_SECONDS:
            return
        _state.last_scan = now

        if _state.handler is None or getattr(_state.handler, "claimed", None):
            return                      # still working on the last one

        waiting = jobs_module.pending()
        if not waiting:
            return

        _identifier, path = waiting[0]
        claimed = jobs_module.claim(path)
        if claimed is None:
            return                      # another session took it
        _state.handler.claimed = claimed
        _state.event.Raise()
    except Exception as error:
        _note("watcher: {0}".format(error))


# ---------------------------------------------------------------------------
# The button
# ---------------------------------------------------------------------------

def start(uiapp):
    if _state.handler is None:
        _state.handler = BridgeJobHandler()
        _state.handler.claimed = None
        _state.event = ExternalEvent.Create(_state.handler)

    bound = commands.register_all()

    # The delegate is kept because .NET holds the subscription and Python holds
    # the callable. Let the second go and the first survives pointing at
    # nothing, which fails silently and looks like the listener ignoring jobs.
    _state.delegate = EventHandler[IdlingEventArgs](_on_idling)
    uiapp.Idling += _state.delegate
    _state.watching = True
    _state.last_scan = 0.0
    jobs_module.ensure()
    _note("watching {0}".format(jobs_module.outbox()))
    return bound


def stop(uiapp):
    if _state.delegate is not None:
        try:
            uiapp.Idling -= _state.delegate
        except Exception as error:
            _note("could not unsubscribe: {0}".format(error))
    _state.delegate = None
    _state.watching = False
    _note("stopped")


def main():
    uiapp = __revit__                                        # noqa: F821

    if _state.watching:
        stop(uiapp)
        dialog = TaskDialog("AnonGee · Bridge Listener")
        dialog.MainInstruction = "Stopped watching"
        dialog.MainContent = ("Jobs written from now on will sit in the outbox "
                              "until this is switched back on.")
        dialog.ExpandedContent = "\n".join(_state.log) or "nothing happened"
        dialog.Show()
        return

    bound = start(uiapp)
    dialog = TaskDialog("AnonGee · Bridge Listener")
    dialog.MainInstruction = "Watching for jobs"
    dialog.MainContent = "\n".join([
        jobs_module.outbox(),
        "",
        "Commands ready: {0}".format(", ".join(bound) or "none"),
        "Declared but not built yet: {0}".format(
            ", ".join(registry.unbound()) or "none"),
    ])
    dialog.ExpandedContent = (
        "Press this button again to stop.\n\n"
        "A job is picked up within about {0:g} seconds of arriving. The work "
        "runs in an external event rather than in the Idling callback, so "
        "Revit is not held while it happens.\n\n"
        "Claiming a job is an atomic rename, so two Revit sessions watching "
        "this folder cannot both run the same job.".format(SCAN_EVERY_SECONDS))
    dialog.Show()


main()
