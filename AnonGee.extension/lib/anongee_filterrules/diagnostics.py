# -*- coding: utf-8 -*-
"""One log, one tag per feature, so a failure names itself.

WHY THIS EXISTS
---------------
Every bug in this tool so far was found by the project owner pressing a button
in Revit and seeing the wrong thing -- a panel that did not appear, a parameter
list that stayed empty, an isolation that was too generous. Each cost a round
trip to work out **which** of several plausible causes it was, because the
window could only say that something had not worked.

Seven features land at once for a single test session. Without a way to say
*which* one broke and *why*, one bad press costs the whole session. So:

* every action carries a **tag** -- ``FEAT-11``, ``FEAT-13`` -- and every
  message the user sees starts with it. A bug report can be one line;
* the full traceback goes to a **file**, not to a dialog nobody can copy out
  of, and the window says where that file is;
* a failure is **never** silent and never generic. "Could not apply" is the
  message this module exists to stop.

THE RULES OF THIS MODULE
------------------------
1. **It never raises.** A logger that throws inside an error handler turns a
   bad press into a lost session. Every entry point swallows everything.
2. **It never blocks the UI.** Appends, no locks, no rotation mid-session.
3. Dual-engine, like the rest of ``lib/``: 2.7 and 3.12, pure ASCII, no ``re``.

The log is APPENDED to across sessions and trimmed at startup, so yesterday's
run is still there when today's goes wrong -- the previous failure is usually
the one that explains this one.
"""

from __future__ import division

import os

#: Beside the rules, so one folder holds everything this tool owns.
LOG_NAME = "filter_view_diagnostics.log"

#: Lines kept when the log is trimmed at session start. Roughly a week of
#: ordinary use, and small enough to paste into a message.
KEEP_LINES = 4000

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
}

_session = [False]


def log_path():
    """Where the log lives. Mirrors ``store.machine_path()``."""
    override = os.environ.get("ANONGEE_PREFS_DIR")
    if override:
        return os.path.join(override, LOG_NAME)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "Zxaidman", "AnonGee", "BIM-Toolkit",
                            LOG_NAME)
    return os.path.join(os.path.expanduser("~"), ".anongee", LOG_NAME)


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


def record(tag, message, detail=""):
    """Append one entry. Returns the path written, or ``""``. Never raises."""
    import datetime
    try:
        stamp = datetime.datetime.now().isoformat()
        line = "{0} | {1} | {2}".format(stamp, label(tag), message)
        if detail:
            line = "{0}\n{1}".format(line, _indent(detail))
        return _append(line)
    except Exception:
        return ""


def failure(tag, message, error, detail=""):
    """Record a failure and return the sentence to put in front of the user.

    One call does both, because the two drifting apart is how a log ends up
    saying something the user was never told.
    """
    cause = describe(error)
    record(tag, "FAILED: {0} -- {1}".format(message, cause), detail)
    # The filename, not the path: the path is three lines long in a status bar
    # and the Diagnostics button opens the folder anyway.
    return headline(tag, "{0} failed -- {1}. Full detail in {2}".format(
        message, cause, LOG_NAME))


def banner(version):
    """Mark a new session, and trim what came before. Never raises."""
    if _session[0]:
        return
    _session[0] = True
    try:
        _trim()
    except Exception:
        pass
    import sys
    record("UI", "=== session start, Filter View Manager {0} ===".format(version),
           "engine: {0}".format(sys.version.replace("\n", " ")))


def recent(limit=40):
    """The last *limit* lines, newest last. ``[]`` for anything at all wrong."""
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


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

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
