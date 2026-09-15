# -*- coding: utf-8 -*-
"""Where saved rules live, and the reading of them.

Two stores, and a rule knows which one it came from.

**The machine store** is the one that matters, and it is what "carries over
sessions and projects" means: the rules follow *the person*, at their desk, into
whatever model they open next.

    %APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json   Windows/Revit
    ~/.anongee/filter_view_rules.json                               fallback
    $ANONGEE_PREFS_DIR/filter_view_rules.json                       override

Same folder and the same environment override as ``cad2bim/prefs.py``, so a
workstation has one AnonGee settings location rather than two, and so this is
testable off Windows.

**The project store** sits in the model's own folder:

    <folder holding the .rvt>/AnonGee/filter_view_rules.json

Chosen over Revit's Extensible Storage on a point of principle, not
convenience: writing Extensible Storage **modifies the model** and needs a
transaction, and PRD S6.1 says this tool writes nothing to the project. A JSON
file beside the model also stays visible, editable, diffable and shareable --
the project folder is already how an office shares anything -- and needs no
schema GUID that can never be changed afterwards.

One file per *folder*, not per model. A job is a folder with ARC, STR and MEP in
it, and a rule about structural columns is about the job.

  *Workshared models:* ``Document.PathName`` on a local file points at the
  user's own copy, not the shared central. The caller passes the **central**
  path when there is one, and ``project_path`` is pure so it neither knows nor
  cares which it was handed.

**Precedence: there is none.** Both stores are shown, each rule marked with
where it came from. Picking a winner loses somebody's rule silently, and for a
tool whose whole job is remembering things that is the worst failure available.

**Nothing here can fail a run.** ``cad2bim/prefs.py``'s rule, unchanged: an
unreadable or half-written file reads as no rules, and a save that cannot write
says so through ``last_error()`` rather than raising into the middle of a
session.
"""

from __future__ import division

import json
import os

from . import rules as _rules

#: What a file may carry. NOT a gate -- every reader here takes what it
#: recognises and ignores the rest, so a file written by a later build still
#: gives up the rules this one understands. ``cad2bim/settings.py``'s rule.
SCHEMA = 1

FILE_NAME = "filter_view_rules.json"

#: The subfolder a project store lives in, beside the .rvt.
PROJECT_DIR_NAME = "AnonGee"

#: Points both stores somewhere harmless. The reason any of this is testable.
ENV_OVERRIDE = "ANONGEE_PREFS_DIR"

#: What ``Rule.source`` is set to, and what the window's badges say.
MACHINE = "machine"
PROJECT = "project"
#: FEAT-19. A file the user points at -- typically on a network share, so an
#: office works from ONE set rather than a copy each. The third candidate from
#: the FEAT-14 decision, and the only one that serves a team rather than a
#: machine or a model.
SHARED = "shared"

#: Where the shared file's location is remembered. Beside the machine rules,
#: because which shared set THIS person uses is a fact about this workstation,
#: not about any model.
SETTINGS_NAME = "filter_view_settings.json"

_last_error = [None]


def last_error():
    """Why the last save failed, or ``None``. Cleared by a save that works."""
    return _last_error[0]


# ---------------------------------------------------------------------------
# Where the files are
# ---------------------------------------------------------------------------

def machine_path():
    """The machine store for this workstation."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return os.path.join(override, FILE_NAME)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "Zxaidman", "AnonGee", "BIM-Toolkit",
                            FILE_NAME)
    return os.path.join(os.path.expanduser("~"), ".anongee", FILE_NAME)


def _folder_of(model_path):
    """The directory part of *model_path*, splitting on BOTH separators.

    ``os.path.dirname`` only knows the separator of the machine it is running
    on, so a Windows path fed to it on POSIX returns ``""`` and the caller
    silently concludes the model has never been saved. In Revit this module
    only ever sees Windows paths, so the bug would never fire in production --
    it would fire in the test suite, on the one function whose whole selling
    point is being testable off Windows.
    """
    body = "{0}".format(model_path).strip()
    cut = max(body.rfind("/"), body.rfind("\\"))
    return body[:cut] if cut > 0 else ""


def project_path(model_path):
    """The project store for the model at *model_path*, or ``None``.

    ``None`` for a model that has never been saved -- it has no folder to put
    anything in, and that is the ordinary case for a new project rather than
    an error.

    Windows and POSIX separators are both understood, so a real
    ``Document.PathName`` can be handed straight in from either side.
    """
    if not model_path or not "{0}".format(model_path).strip():
        return None
    folder = _folder_of(model_path)
    if not folder:
        return None
    return os.path.join(folder, PROJECT_DIR_NAME, FILE_NAME)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_json(path):
    """The parsed contents of *path*, or ``None`` for anything at all wrong.

    Deliberately catches everything a filesystem and a JSON parser can do:
    missing, a directory, no permission, half-written, empty, valid JSON of
    the wrong shape. Every one of them means the same thing here -- no rules.
    """
    try:
        handle = open(path, "rb")
    except (IOError, OSError):
        return None
    try:
        raw = handle.read()
    except (IOError, OSError):
        return None
    finally:
        handle.close()
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load(path, source=""):
    """The rules in *path*, as a ``RuleSet``. Never raises, never empty-fails.

    Every rule is stamped with *source* so the window can say where it came
    from without asking the file again.
    """
    data = _read_json(path)
    if data is None:
        return _rules.RuleSet()
    return _rules.RuleSet.from_list(data.get("rules"), source=source)


def load_all(machine=None, project=None, shared=None):
    """Both stores, machine first, each rule marked with where it came from.

    *project* may be ``None`` -- a model that has never been saved, or one
    whose folder holds no rules -- and that is the ordinary case.

    A rule name appearing in both stores gives **two** rules. They are
    different rules that happen to share a label, and the window shows both
    with their badges rather than pretending one of them is not there.
    """
    if machine is None:
        machine = machine_path()
    built = list(load(machine, source=MACHINE))
    if project:
        built.extend(load(project, source=PROJECT))
    if shared:
        built.extend(load(shared, source=SHARED))
    for position, rule in enumerate(built):
        rule.order = position
    return _rules.RuleSet(built)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _atomic_write(path, text):
    """Write *text* to *path* so a reader never sees it half-done.

    A temp file in the **same directory** -- ``os.rename`` is only atomic
    within one filesystem -- then rename over the target. Windows will not
    rename onto an existing file, so the old one is removed first; the small
    window where neither exists is the price, and it is smaller than the one a
    truncating write leaves open.
    """
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    temporary = path + ".tmp"
    handle = open(temporary, "wb")
    try:
        handle.write(text.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    try:
        if os.path.exists(path):
            os.remove(path)
        os.rename(temporary, path)
    except (IOError, OSError):
        try:
            os.remove(temporary)
        except (IOError, OSError):
            pass
        raise


def settings_path():
    """Where this workstation's own preferences live."""
    return os.path.join(os.path.dirname(machine_path()), SETTINGS_NAME)


def read_settings():
    """This workstation's preferences, as a dict. ``{}`` for anything wrong."""
    data = _read_json(settings_path())
    return data if isinstance(data, dict) else {}


def write_settings(data):
    """Save the preferences. ``True`` on success; ``last_error()`` says why."""
    try:
        _atomic_write(settings_path(),
                      json.dumps(data, indent=2, sort_keys=True))
    except (IOError, OSError, ValueError) as error:
        _last_error[0] = "{0}: {1}".format(settings_path(), error)
        return False
    _last_error[0] = None
    return True


def shared_path():
    """The shared rules file this workstation is pointed at, or ``None``.

    ``None`` when nobody has chosen one, which is the ordinary state and not
    an error. The path is NOT checked for existence here: a network share that
    is down should read as "the file could not be opened" at the moment
    somebody tries, not as "you never chose one".
    """
    chosen = read_settings().get("shared_path")
    if not chosen or not "{0}".format(chosen).strip():
        return None
    return "{0}".format(chosen)


def set_shared_path(path):
    """Point this workstation at *path*, or clear it with ``None``."""
    data = read_settings()
    if path:
        data["shared_path"] = "{0}".format(path)
    else:
        data.pop("shared_path", None)
    return write_settings(data)


def filter_prefix():
    """What a created view filter is called before the rule's own name.

    ``None`` until somebody has chosen, which the caller reads as "use the
    default". An empty string is a real answer and means no prefix at all --
    which is why this cannot just fall back on truthiness.
    """
    data = read_settings()
    if "filter_prefix" not in data:
        return None
    return "{0}".format(data.get("filter_prefix") or "")


def set_filter_prefix(prefix):
    """Remember it. ``None`` forgets, and the default comes back."""
    data = read_settings()
    if prefix is None:
        data.pop("filter_prefix", None)
    else:
        data["filter_prefix"] = "{0}".format(prefix)
    return write_settings(data)


def export_set(rule_set, path, version=None):
    """Write *rule_set* to *path* for somebody else. ``True`` on success.

    The same shape as a store file, deliberately: an exported set IS a store
    file, so it can be dropped straight into a model's ``AnonGee`` folder by
    someone who would rather copy a file than press Import.

    ``source`` is not written -- it never is (see ``Rule``) -- so a set
    exported from a project store does not arrive somewhere else claiming to
    belong to a project it has never seen.
    """
    return save(rule_set, path, version)


def import_set(path):
    """``(RuleSet, problem)`` for the rules in *path*.

    ``(None, why)`` when the file cannot be used, and *why* is a sentence
    rather than an exception type, because it is going in front of somebody
    who chose the wrong file in a dialog -- and "the file you picked is not a
    rules file" is the whole of what they need to know.
    """
    data = _read_json(path)
    if data is None:
        return None, ("{0} could not be read. It is missing, locked, or not a "
                      "rules file at all.".format(path))
    listed = data.get("rules")
    if not isinstance(listed, list):
        return None, ("{0} is readable but has no rules in it. A rules file "
                      "has a \"rules\" list at the top level.".format(path))
    built = _rules.RuleSet.from_list(listed)
    if not len(built):
        return None, "{0} holds no rules.".format(path)
    return built, ""


def destination(wanted, project_available, shared_available=False):
    """Which store a rule actually goes to. Never raises, never returns junk.

    *wanted* is what the window asked for. The two "available" flags say
    whether that store exists to be written to at all: a model that has never
    been saved has no folder, and a workstation nobody has pointed at a shared
    file has no shared file. Both are ordinary states rather than errors, so
    asking for either there is **downgraded to the machine store** rather than
    refused -- the window says so, and nothing is silently lost either way.

    An unrecognised value lands on the machine store, because that is the one
    that always exists.
    """
    if wanted == PROJECT and project_available:
        return PROJECT
    if wanted == SHARED and shared_available:
        return SHARED
    return MACHINE


def partition(rule_set, project_available=True, shared_available=True):
    """``{MACHINE: [], PROJECT: [], SHARED: []}``, by each rule's own source.

    Order within each list is the order of *rule_set*, so writing and reading
    back preserves the sequence the panel draws its buttons in.
    """
    split = {MACHINE: [], PROJECT: [], SHARED: []}
    for rule in rule_set:
        split[destination(rule.source, project_available,
                          shared_available)].append(rule)
    return split


def _why(which, cause, hint=""):
    """Name the store, the cause, and what it usually is.

    The cause alone is an IOError with a path in it, which says what happened
    and nothing about what to do. The hint alone would be a guess. Both, in
    that order, because the reader needs to know which of three files failed
    before anything else is useful.
    """
    said = "{0} would not write".format(which)
    if cause:
        said = "{0}: {1}".format(said, cause)
    return "{0}. {1}".format(said, hint) if hint else "{0}.".format(said)


def save_all(rule_set, machine=None, project=None, shared=None):
    """Write every rule to the store it belongs to. ``(ok, problems)``.

    The whole point of two stores is that a rule can **move** between them, and
    a move is a write to both files: added to one, gone from the other. Saving
    only the store a rule arrived in leaves the old copy on disk, and the next
    load shows the rule twice -- which is what happened before this existed.

    The project file is written when there are project rules **or** when one is
    already there (so emptying it actually empties it), and not otherwise --
    a model whose owner never used the project store does not get an empty
    ``AnonGee`` folder dropped beside it.
    """
    if machine is None:
        machine = machine_path()
    split = partition(rule_set, project_available=bool(project),
                      shared_available=bool(shared))
    problems = []

    if not save(_rules.RuleSet(split[MACHINE]), machine):
        problems.append(_why("the workstation store", last_error()))

    if project and (split[PROJECT] or os.path.exists(project)):
        if not save(_rules.RuleSet(split[PROJECT]), project):
            problems.append(_why(
                "the project store", last_error(),
                "The model's folder is read-only, or somebody else has the "
                "file open."))

    if shared and (split[SHARED] or os.path.exists(shared)):
        # The one store somebody else may be reading at this moment. The write
        # is atomic like the others -- a colleague mid-read sees the old file
        # whole or the new file whole, never half of either.
        if not save(_rules.RuleSet(split[SHARED]), shared):
            problems.append(_why(
                "the shared store", last_error(),
                "It is usually a network share that is down or read-only."))

    return (not problems), problems


def save(rule_set, path=None, version=None):
    """Write *rule_set* to *path*. ``True`` on success.

    On failure: ``False``, ``last_error()`` says why, and **the file that was
    already there is untouched** -- the write goes to a temp file first, so a
    failed save costs the new rule rather than every old one.
    """
    if path is None:
        path = machine_path()
    if version is None:
        from . import VERSION
        version = VERSION
    payload = {"schema": SCHEMA,
               "version": version,
               "rules": rule_set.to_list()}
    try:
        _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True))
    except (IOError, OSError, ValueError) as error:
        _last_error[0] = "{0}: {1}".format(path, error)
        return False
    _last_error[0] = None
    return True
