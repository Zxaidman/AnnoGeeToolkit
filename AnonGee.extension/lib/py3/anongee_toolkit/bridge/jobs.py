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
same files by the same rules. What is shared is a folder layout, not a module.

The canonical installed bridge home is machine-local runtime state:

    %LOCALAPPDATA%\Zxaidman\AnonGee\bridge

``ANONGEE_BRIDGE_HOME`` still overrides everything. The normal default is the
canonical ``LOCALAPPDATA`` path; ``%APPDATA%\AnonGee\bridge`` is retained as a
fallback when LOCALAPPDATA is unavailable and as the legacy upgrade source.

Legacy IPC state is migrated conservatively. Completed inbox files may be moved
(or copied then removed when profiles span volumes) because they are passive
records. A queued ``.job.json`` is **never copied**: it is moved by one atomic
rename when that is possible, otherwise it stays in the legacy outbox and the
new listener claims it there in place. A ``.running.json`` is never moved or
copied automatically because another Revit session may still own it. This keeps
an upgrade from manufacturing two runnable copies of one command.

The path rules are duplicated in ``AnonGee.extension/startup.py`` because that
file runs on IronPython 2.7 while this module runs on CPython. Tests hold the two
implementations together.

Claiming is a rename. ``os.rename`` is atomic on one filesystem, so two
listeners cannot both take the same job: one wins and the other's rename raises.
"""

import io
import json
import os
import shutil

__version__ = "0.3.0"

#: Overrides everything. Set it and both engines follow the same process value.
ENV_HOME = "ANONGEE_BRIDGE_HOME"

#: Canonical installed location for machine-local IPC/runtime state.
LOCALAPPDATA_PARTS = ("Zxaidman", "AnonGee", "bridge")

#: Legacy Windows location and fallback when LOCALAPPDATA is unavailable.
APPDATA_PARTS = ("AnonGee", "bridge")

#: Anywhere else, and on Windows if neither supported AppData variable exists.
HOME_PARTS = (".anongee", "bridge")

OUTBOX = "outbox"
INBOX = "inbox"

JOB_SUFFIX = ".job.json"
RUNNING_SUFFIX = ".running.json"
RESULT_SUFFIX = ".result.json"
TSV_SUFFIX = ".result.tsv"
MIGRATION_CONFLICT_SUFFIX = ".migration-conflict"


_AUTO_CANONICAL_HOME = False


def _same_path(left, right):
    try:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
            os.path.abspath(right)
        )
    except Exception:
        return left == right


def _mkdir(path):
    if not path or os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


def _activate_canonical_process_home():
    """Expose the canonical default through the existing process override.

    A user-supplied ``ANONGEE_BRIDGE_HOME`` always wins. Setting the automatically
    selected default in the process environment keeps older IronPython startup
    code and CPython bridge code converged during an in-process upgrade/reload.
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


def _legacy_home():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ""
    return os.path.join(appdata, *APPDATA_PARTS)


def _canonical_has_job(root, identifier):
    """Whether canonical state already accounts for *identifier*."""
    for path in (
        os.path.join(outbox(root), identifier + JOB_SUFFIX),
        os.path.join(outbox(root), identifier + RUNNING_SUFFIX),
        os.path.join(inbox(root), identifier + RESULT_SUFFIX),
        os.path.join(inbox(root), identifier + TSV_SUFFIX),
    ):
        if os.path.exists(path):
            return True
    return False


def _quarantine_legacy_job(path):
    """Make a conflicting legacy queue file non-runnable without deleting it."""
    target = path + MIGRATION_CONFLICT_SUFFIX
    if os.path.exists(target):
        return False
    try:
        os.rename(path, target)
        return True
    except OSError:
        # An older listener may have claimed it between discovery and rename.
        # In that race, never copy or delete what now belongs to that listener.
        return False


def _move_passive_file(source, target):
    """Move one non-runnable record without overwriting canonical state."""
    if os.path.exists(target):
        return False
    _mkdir(os.path.dirname(target))
    try:
        os.rename(source, target)
        return True
    except OSError:
        pass

    # Cross-volume profile redirection can make rename impossible. Copying is
    # allowed only for passive records; runnable queue/running files never call
    # this helper.
    try:
        shutil.copy2(source, target)
        os.remove(source)
        return True
    except Exception:
        # If the copy succeeded but source removal failed, two passive records
        # are harmless. Keeping both is safer than deleting either one.
        return False


def _migrate_legacy_inbox(legacy, root):
    source = os.path.join(legacy, INBOX)
    target = inbox(root)
    if not os.path.isdir(source):
        return
    _mkdir(target)
    for name in os.listdir(source):
        old = os.path.join(source, name)
        if os.path.isfile(old):
            _move_passive_file(old, os.path.join(target, name))
    try:
        os.rmdir(source)
    except OSError:
        pass


def _migrate_legacy_queue(legacy, root):
    """Move queued jobs only by atomic rename; never touch running jobs."""
    source = os.path.join(legacy, OUTBOX)
    target = outbox(root)
    if not os.path.isdir(source):
        return
    _mkdir(target)

    for name in os.listdir(source):
        if not name.endswith(JOB_SUFFIX):
            # Includes .running.json and .partial. They may be owned by a live
            # session or be an interrupted write, so migration leaves them.
            continue
        old = os.path.join(source, name)
        identifier = name[:-len(JOB_SUFFIX)]
        if _canonical_has_job(root, identifier):
            _quarantine_legacy_job(old)
            continue

        new = os.path.join(target, name)
        try:
            os.rename(old, new)
        except OSError:
            # Never copy a runnable job. If APPDATA and LOCALAPPDATA are on
            # different volumes, pending() also scans the legacy outbox and the
            # new listener will claim this source file in place atomically.
            pass

    try:
        os.rmdir(source)
    except OSError:
        pass


def _migrate_legacy_if_needed(root):
    """Best-effort upgrade from the old roaming bridge without duplicate work."""
    if not _AUTO_CANONICAL_HOME:
        return
    legacy = _legacy_home()
    if not legacy or not os.path.isdir(legacy) or _same_path(legacy, root):
        return
    try:
        _mkdir(root)
        _mkdir(outbox(root))
        _mkdir(inbox(root))
        _migrate_legacy_inbox(legacy, root)
        _migrate_legacy_queue(legacy, root)
        try:
            os.rmdir(legacy)
        except OSError:
            # Running, cross-volume queued, partial, conflicting, or otherwise
            # unknown legacy state intentionally keeps the old tree alive.
            pass
    except Exception:
        # A bridge migration may never take Revit/pyRevit down. Whatever could
        # not be moved remains at the legacy location.
        pass


def _legacy_pending_allowed(root):
    if not _AUTO_CANONICAL_HOME:
        return False
    legacy = _legacy_home()
    return bool(legacy and not _same_path(legacy, root))


def outbox(root=None):
    return os.path.join(root or home(), OUTBOX)


def inbox(root=None):
    return os.path.join(root or home(), INBOX)


def ensure(root=None):
    """Make canonical folders and migrate legacy state best-effort."""
    explicit_root = root is not None
    root = root or home()
    for folder in (outbox(root), inbox(root)):
        _mkdir(folder)
    if not explicit_root:
        _migrate_legacy_if_needed(root)
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


def _pending_in(folder):
    found = []
    if not os.path.isdir(folder):
        return found
    for name in sorted(os.listdir(folder)):
        if name.endswith(JOB_SUFFIX):
            found.append((name[:-len(JOB_SUFFIX)], os.path.join(folder, name)))
    return found


def pending(root=None):
    """Pending canonical jobs plus safe legacy carry-over, oldest id first."""
    explicit_root = root is not None
    root = root or home()
    found = _pending_in(outbox(root))

    if not explicit_root and _legacy_pending_allowed(root):
        legacy = _legacy_home()
        for identifier, path in _pending_in(os.path.join(legacy, OUTBOX)):
            if _canonical_has_job(root, identifier):
                _quarantine_legacy_job(path)
                continue
            found.append((identifier, path))

    # A job id is normally unique. Path is the tie-breaker only for defensive
    # determinism if malformed legacy state contains duplicates.
    return sorted(found, key=lambda row: (row[0], row[1]))


def claim(path):
    """Take a job so nothing else can. Returns the new path, or ``None``.

    A rename in the job's current folder is atomic. This remains true for a
    legacy cross-volume carry-over because it is claimed *in place* rather than
    copied into the canonical outbox first.
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
    """Remove a claimed job once its result is written. Never raises."""
    try:
        if running_path and os.path.exists(running_path):
            os.remove(running_path)
    except OSError:
        pass


def recent(limit=20, root=None):
    """The last few canonical jobs and where each got to, newest first."""
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
