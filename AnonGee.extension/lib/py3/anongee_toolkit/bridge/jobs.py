# -*- coding: utf-8 -*-
"""Where a job lives on disk, from written to answered.

Two folders and a naming rule. That is the whole transport.

    <bridge home>/
        outbox/   <jobId>.job.json        written by whoever asks
                  <jobId>.running.json    claimed, being worked on
        inbox/    <jobId>.result.json     the answer, canonical
                  <jobId>.result.tsv      the same answer, for a macro to read

**The HTTP route and the file drop are the same transport**, and this module is
why. pyRevit loads an extension's ``startup.py`` on IronPython 2.7, which cannot
see this package at all — so the route does not call this code, it writes the
same files by the same rules. What is shared is a folder layout, not a module,
and that turned out to be the simpler thing to share.

The consequence worth stating: **the rules below are duplicated in
``AnonGee.extension/startup.py``, on purpose, in another language.** Duplication
is the price of the engine split and it is a price worth paying, because the
alternative was one engine doing both jobs badly. It is held down two ways —
``tests/test_bridge.py`` compares the constants, and ``/anongee/ping`` reports
the home the route computed so a mismatch shows up as a sentence rather than as
a job nobody ever sees.

Claiming is a rename. ``os.rename`` is atomic on one filesystem, so two
listeners cannot both take the same job: one wins and the other's rename raises.
That matters the day somebody opens two Revit sessions, which is the day nobody
plans for.
"""

import json
import os

__version__ = "0.1.0"

#: Overrides everything. Set it and both ends follow — the same variable name is
#: read by the IronPython route.
ENV_HOME = "ANONGEE_BRIDGE_HOME"

#: Under ``%APPDATA%`` on Windows, which is where Revit already keeps things and
#: what a roaming profile carries between machines.
APPDATA_PARTS = ("AnonGee", "bridge")

#: Anywhere else, and on Windows if ``%APPDATA%`` is somehow unset.
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"
TSV_SUFFIX = ".result.tsv"


def home():
    """The bridge folder. Three rules, in order, and the route uses the same."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, *APPDATA_PARTS)
    return os.path.join(os.path.expanduser("~"), *HOME_PARTS)


def outbox(root=None):
    return os.path.join(root or home(), OUTBOX)


def inbox(root=None):
    return os.path.join(root or home(), INBOX)


def ensure(root=None):
    """Make both folders. Returns the root. Safe to call every time."""
    root = root or home()
    for folder in (outbox(root), inbox(root)):
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder)
            except OSError:
                # Another session made it between the check and the call, which
                # is the normal case rather than the exceptional one.
                if not os.path.isdir(folder):
                    raise
    return root


def write_job(envelope, root=None):
    """Write a job into the outbox. Returns its path.

    Written to a temporary name and renamed into place, so a listener that
    scans mid-write never sees half a file. The rename is the publish.
    """
    root = ensure(root)
    identifier = envelope["jobId"]
    final = os.path.join(outbox(root), identifier + JOB_SUFFIX)
    partial = final + ".partial"
    _write_text(partial, json.dumps(envelope, indent=2, sort_keys=True))
    os.rename(partial, final)
    return final


def pending(root=None):
    """``[(jobId, path)]`` for every unclaimed job, oldest name first."""
    folder = outbox(root)
    if not os.path.isdir(folder):
        return []
    found = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(JOB_SUFFIX):
            found.append((name[:-len(JOB_SUFFIX)], os.path.join(folder, name)))
    return found


def claim(path):
    """Take a job so nothing else can. Returns the new path, or ``None``.

    A rename, because on one filesystem that is atomic: two listeners racing
    for the same job produce one winner and one ``OSError``, rather than two
    runs of the same command against the same model. Returning ``None`` for the
    loser is not an error — it is the mechanism working.
    """
    if not path.endswith(JOB_SUFFIX):
        return None
    running = path[:-len(JOB_SUFFIX)] + RUNNING_SUFFIX
    try:
        os.rename(path, running)
    except OSError:
        return None
    return running


def read(path):
    """A job or result file as a dict, or ``None`` if it will not read."""
    try:
        with open(path, "r") as handle:
            return json.loads(handle.read())
    except Exception:
        return None


def write_result(result, root=None):
    """Write both forms of the answer. ``(json_path, tsv_path)``.

    JSON is canonical and TSV is for Excel, which has no JSON parser and should
    not be given a hand-written one. Both are renamed into place for the same
    reason jobs are: a poller must never read half a file.
    """
    from anongee_toolkit.bridge import envelope as envelope_module

    root = ensure(root)
    identifier = result.get("jobId") or "unknown"
    json_path = os.path.join(inbox(root), identifier + RESULT_SUFFIX)
    tsv_path = os.path.join(inbox(root), identifier + TSV_SUFFIX)

    for path, text in ((json_path, json.dumps(result, indent=2, sort_keys=True)),
                       (tsv_path, envelope_module.as_tsv(result))):
        partial = path + ".partial"
        _write_text(partial, text)
        if os.path.exists(path):
            os.remove(path)
        os.rename(partial, path)
    return json_path, tsv_path


def read_result(identifier, root=None):
    """The answer to one job, or ``None`` if it has not been written."""
    return read(os.path.join(inbox(root), identifier + RESULT_SUFFIX))


def finish(running_path, root=None):
    """Remove a claimed job once its result is written. Never raises.

    The result is the record; a claimed job left behind would be picked up by
    nothing and confuse everybody.
    """
    try:
        if running_path and os.path.exists(running_path):
            os.remove(running_path)
    except OSError:
        pass


def recent(limit=20, root=None):
    """The last few jobs and where each got to, newest first.

    What a macro polls when it cannot address one job by id — which is most
    macros, because a list needs no URL pattern and no query string.
    """
    from anongee_toolkit.bridge import envelope as envelope_module

    root = root or home()
    seen = {}
    for folder, suffix, status in (
            (outbox(root), JOB_SUFFIX, envelope_module.STATUS_QUEUED),
            (outbox(root), RUNNING_SUFFIX, envelope_module.STATUS_RUNNING)):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if name.endswith(suffix):
                identifier = name[:-len(suffix)]
                seen[identifier] = {"jobId": identifier, "status": status}

    folder = inbox(root)
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if not name.endswith(RESULT_SUFFIX):
                continue
            found = read(os.path.join(folder, name)) or {}
            identifier = name[:-len(RESULT_SUFFIX)]
            seen[identifier] = {
                "jobId": identifier,
                "status": found.get("status", ""),
                "command": found.get("command", ""),
                "summary": found.get("summary", {}),
            }

    ordered = sorted(seen.values(), key=lambda row: row["jobId"], reverse=True)
    return ordered[:limit]


def _write_text(path, text):
    with open(path, "w") as handle:
        handle.write(text)
