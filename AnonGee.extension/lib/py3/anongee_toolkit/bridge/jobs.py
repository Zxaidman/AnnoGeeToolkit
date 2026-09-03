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

The canonical installed bridge home is now machine-local runtime state:

    %LOCALAPPDATA%\Zxaidman\AnonGee\bridge

``ANONGEE_BRIDGE_HOME`` still overrides everything. On first CPython bridge use,
this module sets that override **for the current Revit process only** when no
explicit override exists. The IronPython startup route reads the same process
environment on every request, so both engines immediately converge on the new
location without coupling either one to the other. Any legacy
``%APPDATA%\AnonGee\bridge`` tree is migrated best-effort into the canonical
home before the listener starts watching it.

The consequence worth stating: the fallback rules below are duplicated in
``AnonGee.extension/startup.py``, on purpose, in another language. Duplication
is the price of the engine split and it is held down by tests. The process-level
override is the compatibility seam that lets an installed build move the bridge
without making the IronPython startup import the CPython toolkit.

Claiming is a rename. ``os.rename`` is atomic on one filesystem, so two
listeners cannot both take the same job: one wins and the other's rename raises.
That matters the day somebody opens two Revit sessions, which is the day nobody
plans for.
"""

import io
import json
import os
import shutil

__version__ = "0.2.0"

#: Overrides everything. Set it and both ends follow — the same variable name is
#: read by the IronPython route.
ENV_HOME = "ANONGEE_BRIDGE_HOME"

#: Canonical installed location for machine-local IPC/runtime state.
LOCALAPPDATA_PARTS = ("Zxaidman", "AnonGee", "bridge")

#: Legacy/fallback path under ``%APPDATA%``. Kept because startup.py has to stay
#: independently importable on IronPython 2.7 and because LOCALAPPDATA can in
#: principle be absent in a non-standard host.
APPDATA_PARTS = ("AnonGee", "bridge")

#: Anywhere else, and on Windows if neither supported AppData variable exists.
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"
TSV_SUFFIX = ".result.tsv"


_AUTO_CANONICAL_HOME = False


def _same_path(left, right):
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
    except Exception:
        return left == right


def _activate_canonical_process_home():
    """Point this Revit process at the canonical local bridge home.

    A user-supplied ``ANONGEE_BRIDGE_HOME`` always wins. Otherwise, when
    ``LOCALAPPDATA`` exists, set the override in the process environment. The
    IronPython startup route reads the environment dynamically, so it follows
    the same value after the CPython listener imports this module.
    """
    global _AUTO_CANONICAL_HOME
    if os.environ.get(ENV_HOME):
        return
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        return
    os.environ[ENV_HOME] = os.path.join(localappdata, *LOCALAPPDATA_PARTS)
    _AUTO_CANONICAL_HOME = True


_activate_canonical_process_home()


def home():
    """The bridge folder. Explicit override, then legacy-compatible fallback."""
    override = os.environ.get(ENV_HOME)
    if override:
        return override
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, *APPDATA_PARTS)
    return os.path.join(os.path.expanduser("~"), *HOME_PARTS)


def _legacy_home():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ""
    return os.path.join(appdata, *APPDATA_PARTS)


def _merge_legacy_tree(source, target):
    """Move what can be moved without overwriting newer canonical state."""
    if not source or not os.path.isdir(source) or _same_path(source, target):
        return

    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError:
            if not os.path.isdir(parent):
                raise

    # The normal upgrade case: the canonical directory does not exist yet.
    # A directory rename preserves timestamps and is atomic on the usual user
    # profile volume.
    if not os.path.exists(target):
        try:
            os.rename(source, target)
            return
        except OSError:
            pass

    if not os.path.isdir(target):
        return

    # Recovery case: something already created the destination. Merge only
    # missing entries. Never overwrite a canonical job/result with a legacy
    # file bearing the same name.
    for name in os.listdir(source):
        old = os.path.join(source, name)
        new = os.path.join(target, name)
        if os.path.isdir(old):
            _merge_legacy_tree(old, new)
            continue
        if os.path.exists(new):
            continue
        try:
            os.rename(old, new)
        except OSError:
            try:
                shutil.copy2(old, new)
                os.remove(old)
            except Exception:
                # Migration is best-effort. Leaving the legacy file is safer
                # than deleting data because a copy did not complete.
                pass

    try:
        os.rmdir(source)
    except OSError:
        pass


def _migrate_legacy_if_needed(root):
    """Migrate only when this module chose the canonical default itself."""
    if not _AUTO_CANONICAL_HOME:
        return
    legacy = _legacy_home()
    if legacy and not _same_path(legacy, root):
        try:
            _merge_legacy_tree(legacy, root)
        except Exception:
            # A bridge migration may never take Revit down. The new folders are
            # still created below and the legacy data remains intact.
            pass


def outbox(root=None):
    return os.path.join(root or home(), OUTBOX)


def inbox(root=None):
    return os.path.join(root or home(), INBOX)


def ensure(root=None):
    """Make both folders and migrate the old roaming bridge once, best-effort."""
    root = root or home()
    _migrate_legacy_if_needed(root)
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


#: The TSV is read by a VBA macro through ``Input$``, which reads bytes as the
#: machine's ANSI code page and knows nothing about UTF-8. So it is written as
#: **ASCII**, with anything else replaced: a message containing an em dash would
#: otherwise either fail to write on a cp1252 machine or arrive as mojibake in a
#: spreadsheet.
#:
#: The JSON keeps the full text — it is the canonical form and is read by
#: programs that can say what encoding they want. This is the one real cost of
#: writing the answer twice, and it is worth it against hand-rolling a JSON
#: parser in VBA.
TSV_ENCODING = "ascii"
JSON_ENCODING = "utf-8"


def _write_text(path, text, encoding=JSON_ENCODING):
    """Write *text*, never guessing at the machine's code page.

    ``open(path, "w")`` with no encoding uses the locale's, which on Windows is
    cp1252 — so the same file would be written differently on two machines and
    read wrongly on a third. Every write here names its encoding.
    """
    handle = io.open(path, "w", encoding=encoding, errors="replace",
                     newline="\n")
    try:
        handle.write(text)
    finally:
        handle.close()