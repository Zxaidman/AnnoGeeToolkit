#! python3
# -*- coding: utf-8 -*-
"""AnonGee · Filter View Manager — the Revit probe.

Not the tool. The tool is a modeless window and it is 0.1.0; this is the thing
that proves the half underneath it works in a real model, and it exists because
four questions cannot be answered anywhere else:

  1. Does ``ParameterFilterUtilities.GetFilterableParametersInCommon`` return
     what CRIT-2 assumes? Nothing here has ever run it against a model.
  2. Does the Category > Family > Type cascade answer correctly for a **system**
     family (Basic Wall, reached from the type's ``FamilyName``) as well as a
     loadable one?
  3. Does ``IsolateElementsTemporary`` behave in a view under a **view
     template**, and in a view that is **already** isolated by hand?
  4. Do rules saved on this machine survive a Revit restart and open in a
     different project?

It reads the model, builds a rule from what it finds, says what that rule would
match, and will isolate it if asked. It writes nothing to the project.

**The report is written to a file as well as shown.** Root ``todo-list.md``
BUG-5 is the reason: a dialog has to be retyped and a file can be pasted, and
three rounds of findings arrived as screenshots of a panel that said nothing.

Engine: CPython 3 (``#! python3`` — without it pyRevit runs this on IronPython
2.7 where ``lib/py3`` is off the path; root ``todo-list.md`` BUG-9).
No pyRevit modules — Autodesk.* and System.* only (§12.8.4).
"""

import os
import sys
import tempfile

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.UI import TaskDialog                       # noqa: E402
from Autodesk.Revit.UI import TaskDialogCommandLinkId          # noqa: E402
from Autodesk.Revit.UI import TaskDialogCommonButtons          # noqa: E402
from Autodesk.Revit.UI import TaskDialogResult                 # noqa: E402

__title__ = "Filter\nView Manager"
__author__ = "AnonGee"

#: The one place this tool's version is written -- alongside
#: ``anongee_filterrules/__init__.py``, which ``tests/test_filterrules.py``
#: holds to this file, ``bundle.yaml`` and ``CHANGELOG.md`` so the four cannot
#: drift.
#:
#: MAJOR  the tool behaves differently on purpose.
#: MINOR  a new capability; everything already saved still works.
#: PATCH  a fix.
#:
#: 0.0.4 is the rule engine plus this probe. 0.1.0 is the modeless window --
#: the first build that a person would call the tool.
VERSION = "0.0.4"

HERE = os.path.dirname(os.path.abspath(__file__))

#: The category probed unless the model has none of it. Walls because the
#: project owner's own example is a wall rule, and because Walls is the
#: clearest system-family case there is.
PREFERRED = "Walls"

#: How much of a long list the report prints before saying how many more.
SHOWN = 12


def _lib_on_path():
    """Make ``anongee_filterrules`` importable, whatever pyRevit did.

    pyRevit puts ``<extension>/lib`` on ``sys.path`` -- that is how
    ``path_resolver`` is imported everywhere else here -- so this is normally
    a no-op. It is spelled out anyway because a probe that cannot say *why* it
    failed to import is a probe that answers nothing.
    """
    lib = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "lib"))
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    return lib


_LIB = _lib_on_path()


def _report_path():
    return os.path.join(tempfile.gettempdir(),
                        "anongee-filter-view-probe.txt")


def _write(lines):
    """Save the report so it can be pasted rather than retyped (BUG-5)."""
    path = _report_path()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except (IOError, OSError) as error:
        return "could not be written: {0}".format(error)
    return path


def _listing(label, items):
    """A capped list, with the count of what was left out."""
    lines = ["{0}: {1}".format(label, len(items))]
    for item in items[:SHOWN]:
        lines.append("    {0}".format(item))
    if len(items) > SHOWN:
        lines.append("    ... and {0} more".format(len(items) - SHOWN))
    return lines


def _probe(doc, view):
    """Read the model. Returns ``(lines, rule)`` -- rule may be None."""
    from anongee_filterrules import VERSION as CORE_VERSION
    from anongee_filterrules import revit_apply, revit_query, rules, store

    out = ["AnonGee - Filter View Manager, probe {0}".format(VERSION),
           "rule core {0}".format(CORE_VERSION),
           "python {0}".format(sys.version.split()[0]),
           "lib: {0}".format(_LIB),
           ""]

    out.append("MODEL")
    out.append("  document : {0}".format(doc.Title))
    out.append("  path     : {0}".format(doc.PathName or "(never saved)"))
    out.append("  view     : {0}".format(revit_apply.view_label(view)))
    allowed, why = revit_apply.can_isolate(view)
    out.append("  isolate  : {0}".format("yes" if allowed else "NO - " + why))
    out.append("  already isolated: {0}".format(
        "yes" if revit_apply.is_isolated(view) else "no"))
    out.append("")

    out.append("RULE STORES")
    machine = store.machine_path()
    out.append("  machine  : {0}".format(machine))
    out.append("             {0} rule(s)".format(len(store.load(machine))))
    project = store.project_path(doc.PathName)
    out.append("  project  : {0}".format(project or "(model never saved)"))
    if project:
        out.append("             {0} rule(s)".format(len(store.load(project))))
    out.append("")

    found = revit_query.categories(doc)
    out.extend(_listing("MODEL CATEGORIES", [name for name, _ in found]))
    out.append("")

    chosen = _choose_category(doc, revit_query, found)
    if chosen is None:
        out.append("No category in this model has any elements to probe.")
        return (out, None)

    out.append("PROBING: {0}".format(chosen))
    families = revit_query.families(doc, [chosen])
    out.extend(_listing("  families", families))
    types = revit_query.types(doc, [chosen], families[0] if families else None)
    out.extend(_listing("  types (in {0!r})".format(
        families[0] if families else "any"), types))

    parameters = revit_query.parameters(doc, [chosen])
    filterable = [name for name, ok in parameters if ok]
    blocked = [name for name, ok in parameters if not ok]
    out.append("  parameters: {0} total".format(len(parameters)))
    out.extend(["  " + line for line in
                _listing("  filterable (Revit would take these in a view filter)",
                         filterable)])
    out.extend(["  " + line for line in
                _listing("  NOT filterable (still fine for a rule button)",
                         blocked)])
    out.append("")

    rule = rules.Rule(name="probe: {0}".format(chosen), categories=[chosen],
                      family=families[0] if families else None,
                      type_name=types[0] if types else None)
    out.append("THE RULE THIS PROBE BUILT")
    out.append("  {0}".format(rule.summary()))
    out.append("  resolves : {0}".format(
        "; ".join(revit_query.resolve(doc, rule)) or "yes, everything found"))
    matched = revit_query.matching_ids(doc, view, rule)
    out.append("  matches  : {0} element(s) in this view".format(len(matched)))
    out.append("")

    saved = store.load_all(machine, project)
    if len(saved):
        out.append("YOUR SAVED RULES, AGAINST THIS MODEL")
        for one in saved:
            out.append("  [{0}] {1}".format(one.source, one.name))
            out.append("        {0}".format(one.summary()))
            problems = revit_query.resolve(doc, one)
            out.append("        {0}".format(
                "; ".join(problems) or "resolves; matches {0} here".format(
                    len(revit_query.matching_ids(doc, view, one)))))
        out.append("")

    return (out, (rule, matched))


def _choose_category(doc, revit_query, found):
    """``PREFERRED`` if the model has it, else the first with elements."""
    from anongee_filterrules import names
    for name, _ in found:
        if names.same(name, PREFERRED):
            return name
    for name, _ in found:
        try:
            if revit_query.types(doc, [name]):
                return name
        except Exception:
            continue
    return None


def _ask(lines, saved_to, can_isolate):
    """Show the report and return what the user pressed."""
    dialog = TaskDialog("Filter View Manager - probe {0}".format(VERSION))
    dialog.MainInstruction = "The rule engine, against this model"
    dialog.MainContent = "\n".join(lines[:60])
    dialog.ExpandedContent = "\n".join(lines[60:]) if len(lines) > 60 else ""
    dialog.FooterText = "Full report: {0}".format(saved_to)
    if can_isolate:
        dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1,
                              "Isolate what the probe's rule matched",
                              "Temporary, this view only. Nothing is written "
                              "to the project.")
        dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2,
                              "Clear the temporary isolate",
                              "The same as Revit's Reset Temporary "
                              "Hide/Isolate.")
    dialog.CommonButtons = TaskDialogCommonButtons.Close
    return dialog.Show()


def run():
    uidoc = __revit__.ActiveUIDocument                       # noqa: F821
    if uidoc is None or uidoc.Document is None:
        TaskDialog.Show("Filter View Manager",
                        "Open a project first - the probe reads a model.")
        return
    doc = uidoc.Document
    view = doc.ActiveView

    lines, built = _probe(doc, view)
    saved_to = _write(lines)
    lines.append("Report written to: {0}".format(saved_to))
    print("\n".join(lines))                  # the pyRevit console, pasteable

    answer = _ask(lines, saved_to, built is not None)
    if built is None:
        return

    from anongee_filterrules import revit_apply
    rule, matched = built

    if answer == TaskDialogResult.CommandLink1:
        count, message = revit_apply.isolate(doc, view, matched)
        TaskDialog.Show("Filter View Manager",
                        message or "Isolated {0} element(s) in {1}.\n\n"
                        "Nothing was written to the project. Press the button "
                        "again and choose Clear, or use Revit's own Reset "
                        "Temporary Hide/Isolate.".format(
                            count, revit_apply.view_label(view)))
    elif answer == TaskDialogResult.CommandLink2:
        ok, message = revit_apply.clear(doc, view)
        TaskDialog.Show("Filter View Manager",
                        message or ("The view is back to normal."
                                    if ok else "The view could not be cleared."))


# Module-level guard (§12.9.4): a logic error reports cleanly instead of
# leaving the persistent engine in a half-state.
try:
    run()
except Exception as error:                  # noqa: BLE001 - report, never raise
    import traceback
    detail = traceback.format_exc()
    print(detail)
    dialog = TaskDialog("Filter View Manager")
    dialog.MainInstruction = "The probe failed"
    dialog.MainContent = "{0}".format(error)
    dialog.ExpandedContent = detail
    dialog.Show()
