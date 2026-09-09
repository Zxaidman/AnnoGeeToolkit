#! python3
# -*- coding: utf-8 -*-
"""AnonGee · Filter View Manager — bundle scaffold.

The tool is not built. This script exists so the bundle is a real bundle from
the first commit: it takes the ribbon slot, it carries the version, and it is
covered by ``tests/test_scripts.py`` the same as every other script here.

What it does today is say so, and name the three documents beside it. That is
deliberate — a placeholder that opens an empty window looks like a tool that is
broken, and the first thing anybody presses a new button for is to find out
what it is.

Engine: CPython 3 (``#! python3`` above — without it pyRevit runs this on
IronPython 2.7, where ``lib/py3`` is not on the path; see BUG-9 in the
repository's root ``todo-list.md`` for what that costs).

No pyRevit modules are imported — Autodesk.* and System.* only (§12.8.4).
"""

import os

import clr

clr.AddReference("RevitAPIUI")
from Autodesk.Revit.UI import TaskDialog  # noqa: E402

__title__ = "Filter\nView Manager"
__author__ = "AnonGee"

#: The one place this tool's version is written. ``bundle.yaml``'s "Version:"
#: line and the newest heading in ``CHANGELOG.md`` are held to it once the
#: tool has a window with a header to check (see AutoLevel for the pattern).
#:
#: Semantic versioning, read from the point of view of someone using it:
#:   MAJOR  the tool behaves differently on purpose — a workflow moved, or
#:          what pressing a rule does to the model changed shape.
#:   MINOR  a new capability. Everything already saved still works.
#:   PATCH  a fix. Nothing new to learn.
#:
#: It is also declared in ``anongee_filterrules/__init__.py``, which is the
#: package this tool will import; ``tests/test_filterrules.py`` holds all
#: four copies together.
#:
#: 0.0.3 means the rule core is built and tested and has no window on it.
#: 0.1.0 will be the first build that applies a rule to a view.
VERSION = "0.0.3"

HERE = os.path.dirname(os.path.abspath(__file__))

DOCS = ("PRD.md", "ARCHITECTURE.md", "FOLDER_STRUCTURE.md",
        "METHODOLOGY.md", "todo-list.md", "CHANGELOG.md")


def documents():
    """The documents beside this script that are actually on disk."""
    return [name for name in DOCS if os.path.isfile(os.path.join(HERE, name))]


def run():
    dialog = TaskDialog("Filter View Manager")
    dialog.MainInstruction = "Not built yet — version {0}".format(VERSION)
    dialog.MainContent = (
        "This ribbon slot is a scaffold. The tool it will hold saves "
        "Category › Family › Type › Parameter rules as named "
        "buttons; pressing one temporarily isolates its matches in the "
        "active view.\n\n"
        "What is written down so far lives beside this script:\n  {0}\n\n"
        "Folder:\n  {1}".format("\n  ".join(documents()) or "(nothing yet)",
                                HERE))
    dialog.Show()


# Module-level guard (§12.9.4): a logic error reports cleanly instead of
# leaving the persistent engine in a half-state.
try:
    run()
except Exception as error:                  # noqa: BLE001 — report, never raise
    TaskDialog.Show("Filter View Manager",
                    "The scaffold failed to open:\n\n{0}".format(error))
