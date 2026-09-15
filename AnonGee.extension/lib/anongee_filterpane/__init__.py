# -*- coding: utf-8 -*-
"""The dockable panel that holds the rule buttons -- and the spike proving it.

CRIT-3, and it is the one thing about this tool that could not be answered by
reading: **can a dockable pane actually be registered from pyRevit's
startup.py, in this Revit and this pyRevit?** Nothing in this repository has
ever registered one. ``Resources/Panels.xaml`` ships the template and
``tests/test_scripts.py`` lists the interface; neither has been used.

REGISTRATION AND VISIBILITY ARE DIFFERENT THINGS
------------------------------------------------
``RegisterDockablePane`` must be called during ``OnStartup``, before any
document is open. A pushbutton runs far too late and Revit refuses it. But a
registered pane stays **hidden** until something calls ``Show()`` -- so the
project owner's requirement holds exactly as asked: nothing appears until the
button is pressed, and registration is invisible, costs no UI and needs no
document.

NOTHING HERE MAY RAISE
----------------------
``startup.py`` says it plainly: *"a startup script that throws takes pyRevit's
load with it, and a broken bridge must never cost the user their other tools."*
The same is true of a broken panel, and more so -- this one is not even the
tool, it is a convenience on top of it. Every entry point returns a result and
records what happened; none of them lets an exception out.

**The record is the whole point of the spike.** When registration fails there
is no pane to ask and no route to call, so the outcome is written to disk and
the pushbutton reads it back. That is BUG-5's lesson applied before the bug:
three causes -- no ``UIControlledApplication``, a refused registration, a
control that would not build -- look identical from a ribbon with no panel on
it.

THE ENGINE
----------
pyRevit loads ``startup.py`` on its core engine, **IronPython 2.7**, where
``lib/py3`` is not on the path. So this package obeys the same five rules as
``anongee_filterrules`` (see that package's docstring), and
``tests/test_filterrules.py`` enforces them on both.

It *can* import ``anongee_filterrules``, and that is the architecture paying
off: the rule engine lives in ``lib/``, is written for both engines, and the
panel gets the whole of it -- the store, the queries, the isolate -- without a
line of it being duplicated.
"""

from __future__ import division

import os

#: The pane's identity, forever. Revit remembers a pane by this GUID -- where
#: the user docked it, how wide they left it. Changing it orphans all of that
#: and registers a second, empty pane beside the first, so it is a constant and
#: not a thing to regenerate.
PANE_GUID = "7B3A9C14-5E62-4D18-9F07-2A6C8D3B1E45"

#: What Revit shows on the pane's tab, and in View > User Interface.
PANE_TITLE = "AnonGee Filter Views"

#: Where the outcome is written. Beside the rules themselves, so one folder
#: holds everything this tool owns on a workstation.
RECORD_NAME = "filterpane_startup.json"

#: Moves with the tool (``anongee_filterrules.VERSION``) but is written
#: separately, because this package must stay importable with no Revit and
#: with nothing else on the path -- the startup record is read back by the
#: CPython window, and that read must not depend on the rule engine
#: importing cleanly.
VERSION = "0.7.0"


def record_path():
    """Where the startup record lives. Mirrors ``store.machine_path()``."""
    override = os.environ.get("ANONGEE_PREFS_DIR")
    if override:
        return os.path.join(override, RECORD_NAME)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "Zxaidman", "AnonGee", "BIM-Toolkit",
                            RECORD_NAME)
    return os.path.join(os.path.expanduser("~"), ".anongee", RECORD_NAME)


def write_record(payload):
    """Save what happened at startup. Never raises; returns the path or ``""``."""
    import json
    try:
        path = record_path()
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(path, "w")
        try:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
        finally:
            handle.close()
        return path
    except Exception:
        return ""


def read_record():
    """What startup recorded, as a dict. ``{}`` when there is nothing to read.

    The pushbutton calls this from CPython 3 to report what the IronPython
    half did -- which is the only channel between them, and the reason the
    record exists at all.
    """
    import json
    try:
        handle = open(record_path(), "rb")
        try:
            raw = handle.read()
        finally:
            handle.close()
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def register(controlled_application, found_at=""):
    """Register the pane. Returns the record dict; **never raises**.

    *controlled_application* is whatever the startup script found that can
    register a pane; *found_at* says where it found it, or -- when it found
    nothing -- everywhere it looked and what was there instead.

    That second argument is the lesson of the first spike. It guessed the name
    ``__uicontrolledapplication__``, pyRevit binds ``__revit__``, and the
    record could only say "there was none". Recording **which** name answered
    turns the next surprise into a sentence rather than another guess.
    """
    import datetime
    import sys

    outcome = {
        "version": VERSION,
        "at": datetime.datetime.now().isoformat(),
        "engine": sys.version.replace("\n", " "),
        "guid": PANE_GUID,
        "title": PANE_TITLE,
        "registered": False,
        "shown_by": "the Filter View Manager button",
        "found_at": found_at,
        "note": "",
    }

    if controlled_application is None:
        outcome["note"] = (
            "nothing that can register a pane was found in the startup "
            "script. Looked at: {0}".format(found_at or "nowhere"))
        write_record(outcome)
        return outcome

    try:
        from . import provider
    except Exception as error:
        outcome["note"] = "the provider would not import: {0}".format(error)
        write_record(outcome)
        return outcome

    try:
        outcome.update(provider.register(controlled_application))
        outcome["note"] = "{0}; found at {1}".format(outcome["note"], found_at)
    except Exception as error:
        outcome["note"] = "RegisterDockablePane refused: {0}".format(error)

    write_record(outcome)
    return outcome
