# -*- coding: utf-8 -*-
"""Every action this tool takes, written down as it happens.

WHY THIS EXISTS
---------------
Every bug in this tool so far was found by the project owner pressing a button
in Revit and seeing the wrong thing -- a panel that did not appear, a parameter
list that stayed empty, an isolation that was too generous. Each cost a round
trip to work out **which** of several plausible causes it was, because the
window could only say that something had not worked.

0.6.0 answered that with a tagged failure log: every action carries a tag
(``FEAT-11``, ``FEAT-13``), every message starts with it, and the traceback
goes to a file. It worked -- one screenshot carried the whole diagnosis of the
view-picker crash.

What it could not do is explain the failures that **never raise**, and those
turned out to be the expensive half:

* the live count that sat on "counting..." forever. A ``DispatcherTimer`` that
  never ticks throws nothing, so there was no failure to log. What was missing
  was not an error but the *absence of an answer* -- the request went out and
  nothing came back, and nothing in the log said so;
* an isolate that shows fewer elements than the model holds, because
  ``FilteredElementCollector(doc, view.Id)`` only ever returns what the view
  already shows. Not an error either. Just a smaller number than the truth.

So this module now records the WHOLE session, not only its failures:

1. **Every action is a timeline entry** with a sequence number, a clock time
   and the tag that owns it, whether it worked or not;
2. **Round trips are opened and closed.** ``begin()`` stamps a request,
   ``finish()`` closes it with an outcome and how long it took. An entry with
   no close is an action that *went out and never came back* -- the exact
   shape of the count bug -- and the report names it under its own heading;
3. **A finding is recorded without an exception.** ``finding()`` is for the
   thing that is wrong but did not raise, which is how the "some elements are
   hidden" case gets into the report at all;
4. **One file comes out of it.** ``write_report()`` renders the session as a
   single Markdown document that can be attached to a message whole, so the
   next round of bugs arrives together instead of one screenshot at a time.

THE RULES OF THIS MODULE
------------------------
1. **It never raises.** A logger that throws inside an error handler turns a
   bad press into a lost session. Every entry point swallows everything.
2. **It never blocks the UI.** Appends, no locks, no rotation mid-session.
3. **It is bounded.** The timeline stops growing at ``MAX_ACTIONS``; a long
   day of use must not become a memory leak inside Revit.
4. Dual-engine, like the rest of ``lib/``: 2.7 and 3.12, pure ASCII, no ``re``.

The log is APPENDED to across sessions and trimmed at startup, so yesterday's
run is still there when today's goes wrong -- the previous failure is usually
the one that explains this one. The timeline, by contrast, is THIS session
only: it is what the report is built from.
"""

from __future__ import division

import os

#: Beside the rules, so one folder holds everything this tool owns.
LOG_NAME = "filter_view_diagnostics.log"

#: The single file the user attaches to a message. Markdown rather than plain
#: text because the timeline is a table and a table in .txt is unreadable once
#: a family name runs long.
REPORT_NAME = "filter_view_report.md"

#: Lines kept when the log is trimmed at session start. Roughly a week of
#: ordinary use, and small enough to paste into a message.
KEEP_LINES = 4000

#: Timeline entries held in memory. At roughly one per press this is days of
#: use, and the oldest go first so the end of the session -- where the thing
#: being reported almost always is -- survives.
MAX_ACTIONS = 2000

#: Raw log lines carried into the report, so the file explains a session that
#: went wrong YESTERDAY as well as this one.
REPORT_LOG_LINES = 120

#: Tag to what a person calls it. A bare "FEAT-11" in a status bar tells the
#: user nothing; "FEAT-11 apply to views" tells them what they just pressed.
#: Every tag used anywhere in the tool is here, and a test proves it.
FEATURES = {
    "CORE": "the rule engine",
    "UI": "the window",
    "PANEL": "the dockable panel",
    "STORE": "saving and loading rules",
    "FEAT-8": "live match count",
    "FEAT-11": "apply to several views",
    "FEAT-12": "import and export",
    "FEAT-13": "convert to a Revit view filter",
    "FEAT-14": "the project rule store",
    "FEAT-19": "the shared rule store",
    "FEAT-21": "the action tracker and report",
}

#: How an action ended. ``OPEN`` is not an outcome a caller passes -- it is
#: what an entry still says when nothing ever closed it, and finding those is
#: half the reason the timeline exists.
OK = "ok"
FAILED = "failed"
REFUSED = "refused"
EMPTY = "empty"
OPEN = "no answer"
OUTCOMES = (OK, FAILED, REFUSED, EMPTY, OPEN)

_session = [False]
_seq = [0]
_started = [None]
_version = [""]

#: Every action this session, oldest first. Entries are plain dicts so they can
#: be rendered, counted and sliced without a class to keep in step.
_timeline = []

#: Ordered ``(key, value)`` facts about the environment -- Revit's version, the
#: open document, the active view. A list and not a dict because 2.7 does not
#: keep insertion order and the report reads in the order they were learned.
_notes = []

#: Things that are wrong but did not raise. The report leads with these.
_findings = []

#: Open round trips, keyed by ticket (which is the entry's sequence number).
_open = {}


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def log_path():
    """Where the log lives. Mirrors ``store.machine_path()``."""
    return os.path.join(_folder(), LOG_NAME)


def report_path():
    """Where the one uploadable file is written. Beside the log."""
    return os.path.join(_folder(), REPORT_NAME)


def label(tag):
    """``"FEAT-11 apply to several views"``, or the tag alone if unknown."""
    known = FEATURES.get(tag)
    return "{0} {1}".format(tag, known) if known else "{0}".format(tag)


def headline(tag, message):
    """What the user sees: the BARE tag first, so a bug report can be one line.

    The tag alone, not ``label()``. The caller's message already says what was
    being done, and "[FEAT-11 apply to several views] apply to several views
    failed" is the kind of sentence that makes a status bar useless. The long
    form belongs in the log, where there is room for it.
    """
    return "[{0}] {1}".format(tag, message)


def describe(error):
    """A one-line cause from an exception, for a status bar.

    The type is included because ``KeyError: 'families'`` and
    ``AttributeError: 'NoneType'`` are different bugs that read identically
    once the type is dropped -- and the type is usually the half that says
    which.
    """
    try:
        text = "{0}".format(error).strip()
        name = type(error).__name__
        return "{0}: {1}".format(name, text) if text else name
    except Exception:
        return "an error that could not be described"


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record(tag, message, detail=""):
    """Append one entry to the LOG only. Returns the path, or ``""``.

    The timeline is not touched. This is for the running commentary a feature
    writes about itself -- "view 3 of 11 skipped" -- which belongs in the file
    but would bury the presses in the report's table. Never raises.
    """
    import datetime
    try:
        stamp = datetime.datetime.now().isoformat()
        line = "{0} | {1} | {2}".format(stamp, label(tag), message)
        if detail:
            line = "{0}\n{1}".format(line, _indent(detail))
        return _append(line)
    except Exception:
        return ""


def step(tag, action, detail="", outcome=OK, ms=None, **data):
    """Record one completed action, in the log AND on the timeline.

    This is the ordinary case: a button was pressed, something happened, it is
    over. *data* is any number of keyword facts worth keeping beside it --
    ``step("FEAT-8", "counted", matched=12, of=20)`` -- and the names ``tag``,
    ``action``, ``detail``, ``outcome`` and ``ms`` are reserved by the
    signature. Returns the entry's sequence number, or ``0``. Never raises.
    """
    try:
        entry = _entry(tag, action, data)
        entry["outcome"] = outcome if outcome in OUTCOMES else OK
        entry["detail"] = "{0}".format(detail or "")
        entry["ms"] = _ms(ms)
        # The LOG gets every one of them: it is the raw stream and that is its
        # job. The TIMELINE folds a repeat into the row above it, because
        # seventeen keystrokes in the search box are one action a person took
        # and seventeen rows of a report nobody finishes reading.
        record(tag, _sentence(entry), detail)
        folded = _fold(entry)
        if folded is not None:
            return folded["seq"]
        _push(entry)
        return entry["seq"]
    except Exception:
        return 0


def begin(tag, action, **data):
    """Open a round trip. Returns a ticket for ``finish()``, or ``0``.

    Used where the answer arrives somewhere else -- another thread, another
    method, a Revit external event. Until ``finish()`` is called the entry
    reads ``no answer``, and that is deliberate: the live-count bug was an
    action that went out and never came back, and a log that only records
    completions cannot show the shape of it. Never raises.
    """
    try:
        entry = _entry(tag, action, data)
        entry["outcome"] = OPEN
        _push(entry)
        _open[entry["seq"]] = entry
        record(tag, "started: {0}".format(action))
        return entry["seq"]
    except Exception:
        return 0


def finish(ticket, outcome=OK, detail="", **data):
    """Close a round trip opened by ``begin()``. Never raises.

    An unknown or already-closed ticket is ignored rather than an error: a
    reply that arrives twice is a bug worth surviving, not one worth crashing
    the window over.
    """
    try:
        entry = _open.pop(ticket, None)
        if entry is None:
            return False
        entry["outcome"] = outcome if outcome in OUTCOMES else OK
        if detail:
            entry["detail"] = "{0}".format(detail)
        for key in sorted(data.keys()):
            entry["data"].append((key, _plain(data[key])))
        entry["ms"] = _elapsed_ms(entry)
        record(entry["tag"], _sentence(entry), entry["detail"])
        return True
    except Exception:
        return False


def failure(tag, message, error, detail=""):
    """Record a failure and return the sentence to put in front of the user.

    One call does both, because the two drifting apart is how a log ends up
    saying something the user was never told. The timeline gets it too, so the
    report's tally of what went wrong cannot disagree with the log.
    """
    cause = describe(error)
    try:
        entry = _entry(tag, message, {})
        entry["outcome"] = FAILED
        entry["detail"] = "{0}".format(detail or "")
        entry["cause"] = cause
        _push(entry)
    except Exception:
        pass
    record(tag, "FAILED: {0} -- {1}".format(message, cause), detail)
    # The filename, not the path: the path is three lines long in a status bar
    # and the Diagnostics button opens the folder anyway.
    return headline(tag, "{0} failed -- {1}. Full detail in {2}".format(
        message, cause, LOG_NAME))


def finding(tag, message, detail=""):
    """Record something wrong that did not raise. Returns *message*.

    The report leads with these, above the tallies and above the timeline,
    because a session with no exception in it can still be a session where the
    tool did the wrong thing quietly -- which is the harder bug and the one
    that needs to be at the top of the file.
    """
    try:
        text = "{0}".format(message)
        record(tag, "FINDING: {0}".format(text), detail)
        # The same finding twice is not two findings. Counting Phase 1 and
        # then applying it files the identical sentence about the identical
        # view, and a session of thirty presses would open the report with
        # thirty copies of one paragraph -- which buries the ones that differ
        # and is read as thirty problems. It recurred; say so and move on.
        for one in _findings:
            if one["tag"] == tag and one["message"] == text:
                one["seen"] += 1
                return text
        _findings.append({"tag": tag, "message": text,
                          "detail": "{0}".format(detail or ""),
                          "seen": 1, "seq": _seq[0]})
        return text
    except Exception:
        return "{0}".format(message)


def note(key, value):
    """Record one fact about the environment. Last write wins. Never raises.

    Revit's version, the open document, the active view, how many categories
    came back. They are the first questions asked of any report and the ones
    a screenshot never answers.
    """
    try:
        text = _plain(value)
        for index, pair in enumerate(_notes):
            if pair[0] == key:
                _notes[index] = (key, text)
                return
        _notes.append((key, text))
    except Exception:
        return


def banner(version):
    """Mark a new session, and trim what came before. Never raises."""
    if _session[0]:
        return
    _session[0] = True
    try:
        _trim()
    except Exception:
        pass
    import datetime
    import platform
    import sys
    try:
        _started[0] = datetime.datetime.now()
        _version[0] = "{0}".format(version)
        note("tool version", version)
        note("session started", _started[0].isoformat())
        note("engine", sys.version.replace("\n", " "))
        note("platform", platform.platform())
    except Exception:
        pass
    record("UI", "=== session start, Filter View Manager {0} ===".format(version),
           "engine: {0}".format(sys.version.replace("\n", " ")))


# ---------------------------------------------------------------------------
# Reading back
# ---------------------------------------------------------------------------

def timeline(limit=None):
    """This session's actions, oldest first. A copy, so a caller cannot edit."""
    try:
        rows = [dict(entry) for entry in _timeline]
        return rows if limit is None else rows[-int(limit):]
    except Exception:
        return []


def findings():
    """Everything ``finding()`` recorded, oldest first."""
    try:
        return [dict(one) for one in _findings]
    except Exception:
        return []


def unanswered():
    """Actions that were begun and never closed, oldest first.

    The count that never came back, the event that never fired. A session with
    entries here has a silent failure in it whether or not anything raised.
    """
    try:
        return [dict(entry) for entry in _timeline
                if entry.get("outcome") == OPEN]
    except Exception:
        return []


def counters():
    """``[(tag, actions, failures), ...]``, busiest first then by tag.

    Which feature the session was actually spent in, and which of them is
    carrying the failures. Sorted so the answer is the first row.
    """
    try:
        tally = {}
        for entry in _timeline:
            tag = entry.get("tag", "UI")
            actions, failed = tally.get(tag, (0, 0))
            broke = 1 if entry.get("outcome") in (FAILED, OPEN) else 0
            tally[tag] = (actions + 1, failed + broke)
        rows = [(tag, pair[0], pair[1]) for tag, pair in tally.items()]
        rows.sort(key=lambda row: (-row[2], -row[1], row[0]))
        return rows
    except Exception:
        return []


def notes():
    """The environment facts, in the order they were learned."""
    try:
        return list(_notes)
    except Exception:
        return []


def session():
    """``(version, started_iso)`` for this session."""
    try:
        started = _started[0]
        return (_version[0], started.isoformat() if started else "")
    except Exception:
        return ("", "")


def recent(limit=40):
    """The last *limit* LOG lines, newest last. ``[]`` for anything wrong."""
    try:
        handle = open(log_path(), "rb")
        try:
            raw = handle.read()
        finally:
            handle.close()
        lines = raw.decode("utf-8", "replace").split("\n")
        return [line for line in lines if line.strip()][-int(limit):]
    except Exception:
        return []


def clear():
    """Empty the log. ``True`` if it went. Never raises."""
    try:
        path = log_path()
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False


def reset():
    """Forget this session's timeline. For tests, and for a second run."""
    del _timeline[:]
    del _notes[:]
    del _findings[:]
    _open.clear()
    _seq[0] = 0
    _session[0] = False
    _started[0] = None
    _version[0] = ""


# ---------------------------------------------------------------------------
# The gap between the model and the view
# ---------------------------------------------------------------------------

def gap(in_view, in_model):
    """The sentence for "the model holds more of these than the view shows".

    ``""`` when there is nothing to say, so a caller can use it as a test.

    This is the one piece of Revit behaviour that has to be explained rather
    than reported, and it is pure enough to live here where it can be tested:
    ``FilteredElementCollector(doc, view.Id)`` returns what is **visible in
    the view**, so anything the view already hides is invisible to this tool
    too. The rule did not fail and the count is not wrong -- it is the honest
    answer to a question narrower than the one the user was asking. Every
    cause below is something the user can go and look at.
    """
    try:
        shown = int(in_view)
        total = int(in_model)
    except Exception:
        return ""
    missing = total - shown
    if missing <= 0:
        return ""
    return ("{0} more element(s) match this rule in the model than this view "
            "can show it ({1} of {2}). Revit hides them from this tool the "
            "same way it hides them from you, so the isolate cannot bring "
            "them back. Check, in this order: Hide in view on the elements "
            "themselves, the category in Visibility/Graphics, a view filter "
            "already on the view, the view range or the crop, a design "
            "option, and a closed workset.".format(missing, shown, total))


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def report():
    """This session as one Markdown document. Never raises.

    Rendering lives in ``report.py``; this assembles the plain data it needs
    so that the renderer can be tested without a session having happened.
    """
    try:
        from . import report as renderer
        return renderer.render(
            version=_version[0],
            notes=notes(),
            actions=timeline(),
            found=findings(),
            tallies=counters(),
            log_tail=recent(REPORT_LOG_LINES),
            stores=_store_blocks())
    except Exception as error:
        return ("# Filter View Manager -- diagnostic report\n\n"
                "The report could not be built: {0}\n\n"
                "The raw log is at {1}\n".format(describe(error), log_path()))


def write_report(path=None):
    """Write the report. Returns the path written, or ``""``. Never raises."""
    try:
        target = path or report_path()
        folder = os.path.dirname(target)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(target, "wb")
        try:
            handle.write(report().encode("utf-8"))
        finally:
            handle.close()
        record("FEAT-21", "report written to {0}".format(target))
        return target
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _folder():
    override = os.environ.get("ANONGEE_PREFS_DIR")
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "Zxaidman", "AnonGee", "BIM-Toolkit")
    return os.path.join(os.path.expanduser("~"), ".anongee")


def _entry(tag, action, data):
    import datetime
    import time
    _seq[0] += 1
    now = datetime.datetime.now()
    return {"seq": _seq[0],
            "at": now.strftime("%H:%M:%S"),
            "iso": now.isoformat(),
            "started": time.time(),
            "tag": "{0}".format(tag),
            "action": "{0}".format(action),
            "outcome": OK,
            "detail": "",
            "cause": "",
            "ms": None,
            "repeat": 1,
            "data": [(key, _plain(data[key])) for key in sorted(data.keys())]}


def _fold(entry):
    """Merge *entry* into the row above if it repeats it. The row, or ``None``.

    Only an immediately preceding entry of the same feature and action folds,
    and only when BOTH ended plainly ``ok``.

    That one condition is what keeps the rest safe, and it is worth spelling
    out because a second, more obvious-looking guard was written here first
    and turned out to be unreachable. A round trip still open must not fold --
    it is waiting for an answer and its ticket has to stay findable -- but an
    open entry's outcome is ``OPEN``, so the line below has already sent it
    back. A refusal must not fold into the refusal above it, and does not, for
    the same reason. A failure never arrives here at all: ``failure()`` pushes
    its own entry, because two of the same failure is a different report from
    one.
    """
    if not _timeline:
        return None
    last = _timeline[-1]
    if last["outcome"] != entry["outcome"] or entry["outcome"] != OK:
        return None
    if last["tag"] != entry["tag"] or last["action"] != entry["action"]:
        return None
    last["repeat"] += 1
    last["at"] = entry["at"]
    last["iso"] = entry["iso"]
    last["ms"] = entry["ms"]
    # The LAST values, not the first: what somebody finally typed is the
    # interesting half of seventeen keystrokes.
    last["data"] = entry["data"]
    last["detail"] = entry["detail"] or last["detail"]
    return last


def _push(entry):
    _timeline.append(entry)
    while len(_timeline) > MAX_ACTIONS:
        dropped = _timeline.pop(0)
        # The ticket IS the sequence number, so a trimmed entry takes its open
        # ticket with it and a late finish() becomes a no-op instead of
        # resurrecting a row that is no longer in the timeline.
        _open.pop(dropped.get("seq"), None)


def _ms(value):
    try:
        return None if value is None else int(round(float(value)))
    except Exception:
        return None


def _elapsed_ms(entry):
    import time
    try:
        return int(round((time.time() - float(entry["started"])) * 1000.0))
    except Exception:
        return None


def _plain(value):
    """A value as one short line of text, whatever it started as."""
    try:
        text = "{0}".format(value).replace("\r\n", " ").replace("\n", " ")
        text = text.replace("|", "/").strip()
        return text if len(text) <= 160 else "{0}...".format(text[:157])
    except Exception:
        return "?"


def _sentence(entry):
    """One log line for a timeline entry."""
    parts = [entry["action"]]
    if entry["data"]:
        parts.append("({0})".format(", ".join(
            "{0}={1}".format(key, value) for key, value in entry["data"])))
    parts.append("-- {0}".format(entry["outcome"]))
    if entry["ms"] is not None:
        parts.append("in {0} ms".format(entry["ms"]))
    if entry.get("cause"):
        parts.append("-- {0}".format(entry["cause"]))
    return " ".join(parts)


def _store_blocks():
    """What is on disk, for the report. ``[]`` if it cannot be read.

    ``store`` is imported HERE rather than at module scope: this module is
    imported by everything, and a report that needs the rules must not make
    the logger depend on the rule store to start up.
    """
    try:
        from . import store
        blocks = []
        for which in (store.MACHINE, store.PROJECT, store.SHARED):
            try:
                path = _store_path(store, which)
                if not path:
                    continue
                loaded = store.load_all(path)
                blocks.append((which, path, len(loaded.rules)))
            except Exception as error:
                blocks.append((which, "unreadable", describe(error)))
        return blocks
    except Exception:
        return []


def _store_path(store, which):
    if which == store.MACHINE:
        return store.machine_path()
    if which == store.SHARED:
        return store.shared_path()
    # The project store needs a document, which this module does not have. The
    # window records it as a note when the model answers.
    for key, value in _notes:
        if key == "project store":
            return value
    return ""


def _indent(detail):
    """Traceback lines, indented so they are obviously one entry's."""
    out = []
    for line in "{0}".format(detail).replace("\r\n", "\n").split("\n"):
        if line.strip():
            out.append("    {0}".format(line.rstrip()))
    return "\n".join(out)


def _append(line):
    path = log_path()
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    handle = open(path, "ab")
    try:
        handle.write((line + "\n").encode("utf-8"))
    finally:
        handle.close()
    return path


def _trim():
    """Keep the tail. Yesterday's run usually explains today's."""
    path = log_path()
    if not os.path.exists(path):
        return
    handle = open(path, "rb")
    try:
        raw = handle.read()
    finally:
        handle.close()
    lines = raw.decode("utf-8", "replace").split("\n")
    if len(lines) <= KEEP_LINES:
        return
    kept = "\n".join(lines[-KEEP_LINES:])
    handle = open(path, "wb")
    try:
        handle.write(kept.encode("utf-8"))
    finally:
        handle.close()
