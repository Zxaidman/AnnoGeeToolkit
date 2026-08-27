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

The button opens a **modeless window**, and the window is watching while it is
open. A ``TaskDialog`` reported what was true at the instant it opened, which is
the wrong shape for this entirely: a job arriving thirty seconds later was
invisible, and five rounds of diagnosis went by with no way to see whether a job
had even landed. The dialog is still here as a fallback, because the window is
the interface and not the mechanism.

**Idling is subscribed once per session and never removed.** The button flips
``_state.watching`` instead, which costs one attribute read per tick and removes
the whole question of touching a Revit event from the WPF thread.

**§12.9 applies in full here.** The external event handler is a CLR type: no
``__init__``, ``__namespace__`` set **on the class**, and defined **once per
session** — a second definition raises *"Duplicate type name within an
assembly"*. The Idling delegate is held in session state, or .NET keeps the
subscription and Python garbage-collects the callable behind it. The grid binds
through ``__slots__`` and an ``ArrayList``, because change notification fails
silently across this bridge.
"""

__title__ = "Bridge\nListener"
__author__ = "AnonGee"
__doc__ = """Watch for bridge jobs and run them.

An Excel button writes a job into a folder; this notices and runs it on Revit's
own thread. Opens a small modeless window that shows jobs as they arrive.

  • Idling tells it a job has arrived — the only moment the API may be used.
  • The work happens in an external event, never in the Idling callback, so
    Revit is not held while a job runs.
  • Claiming a job is an atomic rename, so two Revit sessions watching one
    folder never run the same job twice.

Jobs live under %APPDATA%\\AnonGee\\bridge (or ANONGEE_BRIDGE_HOME). Use
Bridge Check to see where this session thinks that is."""

__version__ = "0.4.0"

import datetime
import os
import sys
import time

from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler, TaskDialog
from Autodesk.Revit.UI.Events import IdlingEventArgs
from System import EventHandler, TimeSpan
from System.Collections import ArrayList
from System.IO import FileAccess, FileMode, FileStream
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Threading import DispatcherTimer

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
    _state.subscribed = False   # Idling is subscribed once, on Revit's thread
    _state.watching = False     # ...and this is the switch the button flips
    _state.last_scan = 0.0
    _state.log = []
    _state.window_ref = None
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
        summary, findings, note, cells = envelope_module.unpack(
            command.handler(uiapp, job))
        result = envelope_module.new_result(
            job, envelope_module.STATUS_DONE, summary, findings,
            started, datetime.datetime.now().isoformat(), note)
        result["cells"] = [dict(cell) for cell in cells]
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

    **Subscribed once per session and never removed.** The window's button flips
    ``_state.watching`` instead, which costs one attribute read per tick and
    removes the whole question of touching a Revit event from the WPF thread.
    """
    try:
        if not _state.watching:
            return
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

def ensure_ready(uiapp):
    """Subscribe and bind, once per session. ``[command names]``.

    **Called from Revit's own thread**, never from the window's. Subscribing to
    ``Idling`` is a .NET event add rather than a document operation, but the
    cheapest way to be sure it is safe is not to do it anywhere else.
    """
    if _state.handler is None:
        _state.handler = BridgeJobHandler()
        _state.handler.claimed = None
        _state.event = ExternalEvent.Create(_state.handler)

    bound = commands.register_all()

    if not _state.subscribed:
        # The delegate is kept because .NET holds the subscription and Python
        # holds the callable. Let the second go and the first survives pointing
        # at nothing, which fails silently and looks like jobs being ignored.
        _state.delegate = EventHandler[IdlingEventArgs](_on_idling)
        uiapp.Idling += _state.delegate
        _state.subscribed = True

    jobs_module.ensure()
    return bound


def set_watching(on):
    """The whole of start and stop. Safe from any thread."""
    _state.watching = bool(on)
    _state.last_scan = 0.0
    _note("watching {0}".format(jobs_module.outbox()) if on else "stopped")


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

class JobRow(object):
    """One row of the grid. ``__slots__``, and the names match the XAML.

    A plain object bound through an ``ArrayList`` and ``ItemsSource``. Property
    change notification fails silently across this bridge, so the list is
    rebuilt and reassigned instead of mutated (§12.9.4).
    """

    __slots__ = ("JobId", "Command", "Status", "Summary")

    def __init__(self, job_id, command, status, summary):
        self.JobId = job_id
        self.Command = command
        self.Status = status
        self.Summary = summary


class BridgeListenerApp(object):
    """A window that is watching while it is open.

    A ``TaskDialog`` reports what was true at the instant it opened, which is
    the wrong shape for this entirely: a job arriving thirty seconds later was
    invisible, and five rounds of diagnosis went by with no way to see whether a
    job had even landed.
    """

    #: How often the window re-reads the folder. Cheap — one ``listdir`` and a
    #: handful of small files — and it runs on the WPF thread, touching no Revit
    #: API at all, so it cannot interfere with a job.
    REFRESH_SECONDS = 1.0

    def __init__(self, xaml_path):
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        self.window = XamlReader.Load(stream)
        stream.Close()

        self.Lamp = self.window.FindName("Lamp")
        self.StateText = self.window.FindName("StateText")
        self.FolderText = self.window.FindName("FolderText")
        self.CommandsText = self.window.FindName("CommandsText")
        self.JobsGrid = self.window.FindName("JobsGrid")
        self.LastText = self.window.FindName("LastText")
        self.ToggleBtn = self.window.FindName("ToggleBtn")
        self.CloseBtn = self.window.FindName("CloseBtn")

        self.ToggleBtn.Click += self._on_toggle
        self.CloseBtn.Click += self._on_close
        self.window.Closed += self._on_closed

        self.FolderText.Text = jobs_module.outbox()
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromSeconds(self.REFRESH_SECONDS)
        self.timer.Tick += self._on_tick
        self.timer.Start()

    # -- events ------------------------------------------------------------
    def _on_toggle(self, sender, args):
        set_watching(not _state.watching)
        self.refresh()

    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        """Closing the window stops the watching, and that is deliberate.

        A listener still running behind a closed window is a thing that writes
        to a model with nothing on screen saying so.
        """
        try:
            self.timer.Stop()
        except Exception:
            pass
        set_watching(False)
        if _state.window_ref is self:
            _state.window_ref = None

    def _on_tick(self, sender, args):
        self.refresh()

    # -- painting ----------------------------------------------------------
    def refresh(self):
        """Never raises. A timer that throws throws once a second."""
        try:
            watching = bool(_state.watching)
            self.StateText.Text = "Watching for jobs" if watching else "Stopped"
            self.ToggleBtn.Content = ("Stop watching" if watching
                                      else "Start watching")
            self.Lamp.Fill = _brush("#FF16A34A" if watching else "#FF6B7280")

            ready = sorted(name for name in registry.known()
                           if registry.get(name).bound)
            waiting = registry.unbound()
            self.CommandsText.Text = "ready: {0}\nnot built yet: {1}".format(
                ", ".join(ready) or "none", ", ".join(waiting) or "none")

            rows = ArrayList()
            for found in jobs_module.recent(limit=25):
                summary = found.get("summary") or {}
                rows.Add(JobRow(
                    found.get("jobId", ""),
                    found.get("command", ""),
                    found.get("status", ""),
                    "  ".join("{0}={1}".format(key, summary[key])
                              for key in sorted(summary)) or ""))
            self.JobsGrid.ItemsSource = None
            self.JobsGrid.ItemsSource = rows

            self.LastText.Text = _state.log[-1] if _state.log else ""
        except Exception as error:
            try:
                self.LastText.Text = "refresh failed: {0}".format(error)
            except Exception:
                pass

    def show(self):
        self.window.Show()
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle                # noqa: F821
        self.refresh()


def _brush(hex_colour):
    from System.Windows.Media import BrushConverter
    return BrushConverter().ConvertFrom(hex_colour)


def main():
    uiapp = __revit__                                        # noqa: F821
    bound = ensure_ready(uiapp)

    existing = _state.window_ref
    if existing is not None:
        try:
            existing.window.Activate()
            existing.refresh()
            return
        except Exception:
            _state.window_ref = None

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        app = BridgeListenerApp(os.path.join(here, "ui.xaml"))
        app.show()
        _state.window_ref = app
        return
    except Exception as window_error:
        _note("the window would not open: {0}".format(window_error))

    # The window is the interface, not the mechanism. If it will not build, the
    # listener still has to be usable — so the old dialog is still here, and it
    # says why it is the one that appeared.
    set_watching(not _state.watching)
    dialog = TaskDialog("AnonGee \u00b7 Bridge Listener")
    dialog.MainInstruction = ("Watching for jobs" if _state.watching
                              else "Stopped watching")
    dialog.MainContent = "\n".join([
        jobs_module.outbox(), "",
        "Commands ready: {0}".format(", ".join(bound) or "none"),
        "Declared but not built yet: {0}".format(
            ", ".join(registry.unbound()) or "none"),
        "",
        "The window could not be opened, so this is the fallback. Press the "
        "button again to toggle.",
    ])
    dialog.ExpandedContent = "\n".join(_state.log) or "nothing happened yet"
    dialog.Show()


main()
