# -*- coding: utf-8 -*-
"""Settings that outlive a Revit session, in one small JSON file.

The dialog rebuilds itself from scratch every run, so anything the user is
expected to set ONCE -- their type-naming convention, their standard beam and
column sizes -- has to live outside the session. It goes in

    %APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/cad2bim.json  (Windows/Revit)
    ~/.anongee/cad2bim.json                             (tests/fallback)

Older AnonGee builds stored the Windows file at
``%APPDATA%/AnonGee/cad2bim.json``. On first read, that file is copied to the
canonical location when no new-location file exists. The legacy copy is left
untouched for rollback during the migration period.

One flat file of plain JSON: readable, hand-editable, and easy to delete when
someone wants the defaults back. Nothing here can fail a run -- an unreadable or
half-written file reads as "no preferences", and a save that cannot write says
so through `last_error()` instead of raising into the middle of a build.
"""

import json
import os
import shutil

_FILE_NAME = "cad2bim.json"
_last_error = None


def path():
    """Where the preferences file lives on this machine."""
    override = os.environ.get("ANONGEE_PREFS_DIR")
    if override:
        return os.path.join(override, _FILE_NAME)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(
            appdata, "Zxaidman", "AnonGee", "BIM-Toolkit", _FILE_NAME)
    return os.path.join(os.path.expanduser("~"), ".anongee", _FILE_NAME)


def _legacy_path():
    """Pre-canonical Windows path, or None outside the normal Revit profile."""
    if os.environ.get("ANONGEE_PREFS_DIR"):
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "AnonGee", _FILE_NAME)


def _migrate_legacy_if_needed(target):
    """Copy an old preferences file once; never make migration fatal."""
    if os.path.isfile(target):
        return
    legacy = _legacy_path()
    if not legacy or not os.path.isfile(legacy):
        return
    try:
        folder = os.path.dirname(target)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        shutil.copy2(legacy, target)
    except (IOError, OSError):
        # Preferences migration is best-effort. A later save can still create
        # the new file and the legacy copy remains available for rollback.
        pass


def last_error():
    """Why the last save failed, or None."""
    return _last_error


def load():
    """Everything saved, as a dict. A missing or broken file gives {}."""
    target = path()
    _migrate_legacy_if_needed(target)
    try:
        with open(target, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
    except (IOError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data):
    """Replace the whole file. Returns True when it was written."""
    global _last_error
    target = path()
    try:
        folder = os.path.dirname(target)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        # write beside the target and swap, so an interrupted save never
        # leaves a half-written file that reads back as corrupt
        temporary = target + ".tmp"
        with open(temporary, "wb") as handle:
            handle.write(json.dumps(data, indent=2,
                                    sort_keys=True).encode("utf-8"))
        if os.path.exists(target):
            os.remove(target)
        os.rename(temporary, target)
        _last_error = None
        return True
    except (IOError, OSError, ValueError, TypeError) as error:
        _last_error = str(error)
        return False


def update(changes):
    """Merge `changes` into the saved settings. Returns True when written."""
    data = load()
    data.update(changes or {})
    return save(data)
