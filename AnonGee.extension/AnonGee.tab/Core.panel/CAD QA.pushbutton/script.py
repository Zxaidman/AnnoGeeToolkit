#! python3
# -*- coding: utf-8 -*-
"""CAD QA -- check a structural DXF before cad2bim converts it.

NEEDS NO MODEL AND OPENS NO TRANSACTION. Every other tool on this panel builds
something; this one only reads a file and reports. That is why it does not ask
for `__revit__`, does not check for an open document, and has no undo step --
there is nothing in Revit for it to be careful about.

CPython3 engine compliance (AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9):
  * `#! python3` shebang on line 1.
  * NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit) -- they crash
    the CPython3 engine. The file dialog is System.Windows.Forms and the
    summary is System.Windows.MessageBox, as the shipping cad2bim tool does.
  * The lib bootstrap RUNS before anongee_toolkit is imported; below that
    import it would run second and the import would already have failed.

The checking itself lives in `anongee_toolkit/cad_qa`, which is Revit-free and
has its own test suite -- so what this file contains is a file dialog, a call,
and three ways of showing the answer.
"""

__title__ = "CAD QA"
__author__ = "AnonGee"
__doc__ = """Check a structural DXF before converting it with cad2bim.

Reads the drawing the way cad2bim reads it and reports what will go wrong:
layers it cannot classify, size labels it cannot parse, outlines that do not
close, storeys that will land on top of each other.

Advisory. No model is opened, nothing is written, no undo step is left. A JSON
report and an .xlsx workbook are written beside the drawing."""

__version__ = "1.0.0"
__min_revit_ver__ = 2022

import os
import sys
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("System.Windows.Forms")


def _bootstrap_lib_path():
    """Put the engine-appropriate lib subfolder (py2/py3) on sys.path.

    Primary: the repo's own path_resolver, which pyRevit makes importable by
    adding the extension `lib/` folder to sys.path. Fallback: climb from this
    file to find the `lib` dir and inject py2/py3 directly. Mirrors the cad2bim
    button, deliberately -- two bootstraps that differ is two bugs.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    try:
        cursor = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return

    for _ in range(8):  # button -> panel -> tab -> extension -> lib
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


_bootstrap_lib_path()

from anongee_toolkit.cad_qa import report_console      # noqa: E402
from anongee_toolkit.cad_qa import report_excel        # noqa: E402
from anongee_toolkit.cad_qa import report_json         # noqa: E402
from anongee_toolkit.cad_qa import runner              # noqa: E402


def _message_box(text, caption):
    from System.Windows import MessageBox
    MessageBox.Show(text, caption)


def _pick_drawings():
    """The DXF files to check, or [] when the dialog is cancelled."""
    from System.Windows.Forms import DialogResult, OpenFileDialog
    dialog = OpenFileDialog()
    dialog.Title = "Choose the DXF drawings to check"
    dialog.Filter = "DXF drawings (*.dxf)|*.dxf"
    dialog.Multiselect = True
    if dialog.ShowDialog() != DialogResult.OK:
        return []
    return list(dialog.FileNames)


def _write_reports(reports, folder):
    """Write the JSON and the workbook beside the drawings. Returns lines."""
    written = []
    for report in reports:
        stem = os.path.splitext(report.source)[0] or "drawing"
        target = os.path.join(folder, stem + ".qa.json")
        report_json.write_report(target, report)
        written.append(target)

    workbook = os.path.join(folder, "cad_qa.xlsx")
    try:
        report_excel.write_workbook(workbook, reports)
    except report_excel.ExcelUnavailable:
        # The JSON is already on disk. Losing it because the third output
        # format is unavailable would be the wrong trade.
        workbook = None
    lines = ["Written:"]
    lines.extend("  " + path for path in written)
    if workbook:
        lines.append("  " + workbook)
    return lines


def _summary(reports):
    """The one paragraph that goes in the message box."""
    totals = runner.summarise(reports)
    if totals["drawings"] == 1:
        report = reports[0]
        counts = report.counts()
        head = "{0}\n\n{1} Error, {2} Warning, {3} Info".format(
            report.source, counts["Error"], counts["Warning"], counts["Info"])
        if not report.findings:
            return head + "\n\nNothing here will stop cad2bim reading this "\
                          "drawing."
        return head
    return ("{drawings} drawings checked\n\n{clean} clean · {with_errors} with "
            "errors\n{Error} Error, {Warning} Warning, {Info} Info"
            .format(**totals))


def main():
    paths = _pick_drawings()
    if not paths:
        return

    try:
        runner.require_environment()
    except runner.EnvironmentError_ as error:
        _message_box(str(error), "CAD QA")
        return

    reports = [runner.run_file(path) for path in paths]

    # The full report goes to the output window, where it can be selected and
    # pasted; the message box carries only what fits in a glance.
    for report in reports:
        for line in report_console.format_report(report):
            print(line)
        print("")

    folder = os.path.dirname(os.path.abspath(paths[0]))
    try:
        for line in _write_reports(reports, folder):
            print(line)
    except (IOError, OSError) as error:
        print("Reports could not be written to {0}: {1}".format(folder, error))

    _message_box(_summary(reports), "CAD QA {0}".format(__version__))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        _message_box("CAD QA failed. The traceback is in the output window.",
                     "CAD QA")
