#! python3
# -*- coding: utf-8 -*-
"""
BBS Generator — Bar Bending Schedule Generator
pyRevit CPython 3 push-button script.

Runtime dependencies are loaded only from AnonGee.extension/lib/py3.  The tool
must not depend on a standalone Python installation, pip, PYTHONPATH, or another
pyRevit engine's packages.
"""

import sys
import os
import clr

# ── pyrevit.forms for all dialogs (works in CPython and IronPython) ────────────
# TaskDialog import via Autodesk.Revit.UI fails in CPython (stub shadowing).
from pyrevit import forms as _pf


def show_alert(message, title="AnonGee BIM Tools"):
    """Shows a pyRevit alert dialog."""
    _pf.alert(message, title=title)


def _is_under(path, root):
    """True when *path* is located inside *root* (Windows case-insensitive)."""
    if not path or not root:
        return False
    try:
        path_key = os.path.normcase(os.path.abspath(path))
        root_key = os.path.normcase(os.path.abspath(root))
        return path_key == root_key or path_key.startswith(root_key + os.sep)
    except (TypeError, ValueError, OSError):
        return False


def _bootstrap_bundled_runtime():
    """Put AnonGee's own lib/py3 first on sys.path and return that directory."""
    try:
        import path_resolver
        target = path_resolver.update_paths()
        if target and os.path.isdir(target):
            return os.path.abspath(target)
    except ImportError:
        pass

    # Same bounded fallback used by the proven CAD2BIM bootstrap.  This keeps
    # the button usable even if pyRevit did not add the extension lib/ folder.
    sub = "py3" if sys.version_info[0] == 3 else "py2"
    try:
        cursor = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return None

    for _ in range(8):
        candidate = os.path.abspath(os.path.join(cursor, "lib", sub))
        if os.path.isdir(candidate):
            candidate_key = os.path.normcase(candidate)
            retained = []
            for entry in sys.path:
                try:
                    entry_key = os.path.normcase(os.path.abspath(entry))
                except (TypeError, ValueError, OSError):
                    entry_key = None
                if entry_key != candidate_key:
                    retained.append(entry)
            sys.path[:] = [candidate] + retained
            return candidate

        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent

    return None


def _ensure_bundled_openpyxl():
    """Verify that openpyxl is present and loaded from AnonGee's runtime."""
    runtime_root = _bootstrap_bundled_runtime()
    if not runtime_root:
        return False, (
            "AnonGee's bundled Python runtime could not be found.\n\n"
            "Repair or reinstall AnonGee Toolkit. Standalone Python and pip "
            "are not required."
        )

    try:
        import openpyxl
    except Exception as error:
        return False, (
            "AnonGee's bundled openpyxl could not be loaded.\n\n"
            "Runtime: {}\nError: {}\n\n"
            "Repair or reinstall AnonGee Toolkit. Standalone Python and pip "
            "are not required."
        ).format(runtime_root, error)

    origin = getattr(openpyxl, "__file__", "") or ""
    if not _is_under(origin, runtime_root):
        return False, (
            "A non-AnonGee copy of openpyxl is already loaded in this Revit "
            "session.\n\nLoaded from: {}\nExpected under: {}\n\n"
            "Restart Revit and try again. If the problem remains, repair or "
            "reinstall AnonGee Toolkit."
        ).format(origin or "unknown location", runtime_root)

    return True, ""


def main():
    # ── Ensure all sub-packages are importable ────────────────────────────────
    _TOOL_ROOT = os.path.dirname(os.path.abspath(__file__))
    for _sub in ["core", "standards", "output", "ui", os.path.join("ui", "xaml")]:
        _p = os.path.join(_TOOL_ROOT, _sub)
        if _p not in sys.path:
            sys.path.insert(0, _p)

    # openpyxl is shipped in AnonGee.extension/lib/py3. Never discover or
    # install a workstation-global copy: deployment must be self-contained.
    openpyxl_ok, openpyxl_error = _ensure_bundled_openpyxl()
    if not openpyxl_ok:
        show_alert(openpyxl_error, title="AnonGee Runtime Error")
        return

    # ── Native Revit Document Access (Bypass pyrevit wrapper bug) ────────────
    try:
        # __revit__ is a global variable automatically injected by pyRevit
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document if uidoc else None
    except Exception as e:
        show_alert(f"Could not access Revit application natively.\n\n{e}", title="BBS Generator Error")
        return

    if doc is None:
        show_alert(
            "No active Revit document found.\n"
            "Please open a project before running BBS Generator.",
            title="BBS Generator Notice"
        )
        return

    # ── WinForms for dialogs ─────────────────────────────────────────────────
    clr.AddReference("System.Windows.Forms")
    import System.Windows.Forms  # noqa

    # ── Launch UI ────────────────────────────────────────────────────────────
    from main_window import run_ui
    run_ui(doc, uidoc)


if __name__ == "__main__":
    main()
