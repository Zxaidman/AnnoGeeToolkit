# -*- coding: utf-8 -*-
r"""Where a job lives on disk, from written to answered.

Two folders and a naming rule. That is the whole transport.

    <bridge home>/
        outbox/   <jobId>.job.json        written by whoever asks
                  <jobId>.running.json    claimed, being worked on
        inbox/    <jobId>.result.json     the answer, canonical
                  <jobId>.result.tsv      the same answer, for a macro to read

**The HTTP route and the file drop are the same transport**, and this module is
why. pyRevit loads an extension's ``startup.py`` on IronPython 2.7, which cannot
see this package at all — so the route does not call this code, it writes the
same files by the same rules. What is shared is a folder layout, not a module.

The canonical installed bridge home is machine-local runtime state:

    %LOCALAPPDATA%\Zxaidman\AnonGee\bridge

``ANONGEE_BRIDGE_HOME`` overrides everything. If ``LOCALAPPDATA`` is not
available, the bridge falls back to ``%APPDATA%\AnonGee\bridge`` and then to
``~/.anongee/bridge``. The normal installed runtime no longer scans or migrates
the old roaming bridge tree when ``LOCALAPPDATA`` is available; the one-user
migration to the canonical local path is complete.

The path rules are duplicated in ``AnonGee.extension/startup.py`` because that
file runs on IronPython 2.7 while this module runs on CPython. Tests hold the two
implementations together.

Claiming is a rename. ``os.rename`` is atomic on one filesystem, so two
listeners cannot both take the same job: one wins and the other's rename raises.
"""

import io
import json
import os

__version__ = "0.4.0"

#: Overrides everything. Set it and both engines follow the same process value.
ENV_HOME = "ANONGEE_BRIDGE_HOME"

#: Canonical installed location for machine-local IPC/runtime state.
LOCALAPPDATA_PARTS = ("Zxaidman", "AnonGee", "bridge")

#: Fallback when LOCALAPPDATA is unavailable.
APPDATA_PARTS = ("AnonGee", "bridge")

#: Anywhere else, and on Windows if neither supported AppData variable exists.
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"
TSV_SUFFIX = ".result.tsv"


def _mkdir(path):
    if not path or os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


def home():
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


def outbox(root=None):
    return os.path.join(root or home(), OUTBOX)


def inbox(root=None):
    return os.path.join(root or home(), INBOX)


def ensure(root=None):
    """Create the selected bridge home and its queue/result folders."""
    root = root or home()
    for folder in (outbox(root), inbox(root)):
        _mkdir(folder)
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
    """Pending jobs from the selected bridge home, oldest id first."""
    folder = outbox(root)
    if not os.path.isdir(folder):
        return []
    found = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(JOB_SUFFIX):
            found.append((name[:-len(JOB_SUFFIX)], os.path.join(folder, name)))
    return found


def claim(path):
    """Take a job so nothing else can. Returns the new path, or ``None``."""
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

    for path, text, encoding in (
            (json_path, json.dumps(result, indent=2, sort_keys=True),
             JSON_ENCODING),
            (tsv_path, envelope_module.as_tsv(result), TSV_ENCODING)):
        partial = path + ".partial"
        _write_text(partial, text, encoding)
        if os.path.exists(path):
            os.remove(path)
        os.rename(partial, path)
    return json_path, tsv_path


def read_result(identifier, root=None):
    """The answer to one job, or ``None`` if it has not been written."""
    return read(os.path.join(inbox(root), identifier + RESULT_SUFFIX))


def finish(running_path, root=None):
    """Remove a claimed job once its result is written. Never raises."""
    try:
        if running_path and os.path.exists(running_path):
            os.remove(running_path)
    except OSError:
        pass


def recent(limit=20, root=None):
    """The last few jobs and where each got to, newest first."""
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


#: The TSV is read by a VBA macro through ``Input$``, which reads bytes as the
#: machine's ANSI code page and knows nothing about UTF-8. So it is written as
#: **ASCII**, with anything else replaced.
TSV_ENCODING = "ascii"
JSON_ENCODING = "utf-8"


def _write_text(path, text, encoding=JSON_ENCODING):
    """Write *text*, never guessing at the machine's code page."""
    handle = io.open(path, "w", encoding=encoding, errors="replace",
                     newline="\n")
    try:
        handle.write(text)
    finally:
        handle.close()
