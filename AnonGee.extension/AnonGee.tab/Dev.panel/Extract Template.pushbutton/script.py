#! python3
# -*- coding: utf-8 -*-
"""Write what this model contains to Markdown, so it can be read outside Revit.

A ``.rvt`` cannot be handed to anybody who does not have Revit open. There is no
library that reads one and there will not be. So the model describes itself: one
file, every category, family, type and parameter, sorted, with nothing in it
that changes between two runs over an unchanged model — which makes it
committable and diffable, and means "what changed in the template" becomes a
question with an answer.

**Read-only.** No transaction is opened. Safe to point at the real template.
"""

import os
import sys

__version__ = "0.2.0"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))


def bootstrap_lib_path():
    """Put the engine's ``lib`` subfolder on ``sys.path``.

    **pyRevit adds ``<extension>/lib`` and nothing below it.** The toolkit lives
    in ``lib/py3``, so a script that does not do this cannot import it — which
    is not a shebang problem, however much it looks like one. The first release
    of this tool skipped the call and then blamed the engine in its own error
    message, which would have cost a round if the project owner had believed it.

    Primary: the extension's own ``path_resolver``, which pyRevit makes
    importable. Fallback: climb for ``lib/py3`` directly, so the tool still
    loads when the button is run from an unusual working directory.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    cursor = LOCAL_DIR
    for _ in range(8):
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


bootstrap_lib_path()

#: Where the report lands when the model has never been saved.
FALLBACK_PARTS = ("AnonGee", "bridge")

#: What it is called, beside the model it describes.
FILE_SUFFIX = "-template.md"


def main():
    doc = document()
    if doc is None:
        report("No document is open, so there is nothing to describe.")
        return

    try:
        from anongee_toolkit.structural import inventory
        from anongee_toolkit.rc_automation import template_report
    except Exception as error:
        report("The toolkit would not import: {0}\n\n"
               "The toolkit lives in lib/py3, and pyRevit puts lib on the "
               "path but nothing below it — so a script has to add it. This "
               "one calls path_resolver at import; if that is failing, "
               "reload pyRevit and try again.\n\n"
               "Looked in:\n{1}"
               .format(error, "\n".join(sys.path[:6])))
        return

    print("Reading {0} ...".format(title(doc)))
    data = inventory.gather(doc)
    text = template_report.render(data)

    target = destination(doc)
    try:
        folder = os.path.dirname(target)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except Exception as error:
        report("Could not write the report: {0}\n\nIt would have gone to:\n{1}"
               .format(error, target))
        return

    print(text)
    report(summary(data, target))


def summary(data, target):
    families = data.get("families") or []
    types = sum(len(row.get("types") or []) for row in families
                if isinstance(row, dict))
    parameters = data.get("parameters") or {}
    counted = []
    for scope in ("shared", "project", "global"):
        rows = parameters.get(scope) or []
        if rows:
            counted.append("{0} {1}".format(len(rows), scope))
    family_parameters = sum(len(row.get("parameters") or [])
                            for row in (parameters.get("family") or []))

    lines = ["Written to:", target, ""]
    lines.append("{0} categories, {1} families, {2} types.".format(
        len(data.get("categories") or []), len(families), types))
    if counted:
        lines.append("Parameters: {0}, and {1} across the loaded "
                     "families.".format(", ".join(counted), family_parameters))
    datum = data.get("datum") or {}
    lines.append("{0} levels, {1} grids.".format(
        len(datum.get("levels") or []), len(datum.get("grids") or [])))
    lines.append("")
    lines.append("Nothing in the model was changed. The whole report is also "
                 "in the pyRevit console above — paste that if the file is "
                 "awkward to send.")
    return "\n".join(lines)


def destination(doc):
    """Beside the model, or in the bridge folder when it has never been saved."""
    path = ""
    try:
        path = doc.PathName or ""
    except Exception:
        path = ""

    if path:
        base = os.path.splitext(path)[0]
        return base + FILE_SUFFIX

    home = os.environ.get("ANONGEE_BRIDGE_HOME")
    if not home:
        appdata = os.environ.get("APPDATA")
        if appdata:
            home = os.path.join(appdata, *FALLBACK_PARTS)
        else:
            home = os.path.join(os.path.expanduser("~"), ".anongee", "bridge")
    return os.path.join(home, "unsaved" + FILE_SUFFIX)


def document():
    """The open document, read straight from ``__revit__``.

    Not through a bridge route: a route runs as an External Event and would
    queue behind this script, which is a deadlock a previous release spent a
    round discovering.
    """
    try:
        uiapp = __revit__                                     # noqa: F821
        uidoc = getattr(uiapp, "ActiveUIDocument", None)
        return uidoc.Document if uidoc is not None else None
    except Exception:
        return None


def title(doc):
    try:
        return doc.Title
    except Exception:
        return "this model"


def report(message):
    print(message)
    try:
        from pyrevit import forms
        forms.alert(message, title="Extract Template")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback
        traceback.print_exc()
        report("Extract Template stopped: {0}".format(error))
        sys.exit(0)
