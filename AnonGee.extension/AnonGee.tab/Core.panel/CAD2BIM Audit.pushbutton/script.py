#! python3
# -*- coding: utf-8 -*-
"""CAD to BIM -- Audit. Read the job four ways and report where it went wrong.

This is a DEBUG tool and a separate one. It does not import, extend, patch or
modify the cad2bim pushbutton or any cad2bim module: it calls two of that
package's readers read-only, so the "as cad2bim sees it" columns are genuinely
what the real pipeline sees rather than a re-implementation that could drift.

What it does
  A  reads the DXF with ezdxf, twice: a full entity census, and through
     cad2bim's own dxf_reader. The difference is what that reader discards.
  B  reads the same DXF linked into Revit, twice: every GeometryObject the link
     exposes, and through cad2bim's geometry_reader -- which ignores solids,
     meshes and points, and so never sees an imported hatch at all.
  C  sweeps the document for the elements that actually exist.
  D  optionally reads a cad2bim run's JSON: what the run believed it built.

Then it matches them into candidate members and writes a workbook saying, per
member, what each stage had and which stage lost it.

The only thing it writes to the model is the DXF link, in its own transaction,
and only when the user asks for a fresh link. Choosing an existing link makes
the whole run read-only.

CPython3 engine compliance (AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9):
  * `#! python3` shebang on line 1; explicit imports only.
  * NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit) -- they crash
    the CPython3 engine. Windows load via XamlReader from a .xaml file; the
    active document comes from `__revit__`; dialogs use System.Windows.
"""

__title__ = "CAD2BIM\nAudit"
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
import sys
import time
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")

from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
import System.Windows.Forms as WinForms


def _bootstrap_lib_path():
    """Put the engine-appropriate lib subfolder on sys.path.

    Primary: the repo's path_resolver, which pyRevit makes importable. Fallback:
    climb to find `lib/` and inject it directly. Same approach as cad2bim's
    button, for the same reason -- neither can assume the other ran first.
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


def _drop_stale_modules():
    """Forget audit modules the ENGINE is still holding from an earlier click.

    The CPython3 engine outlives a run: this file is re-read every click, but a
    module it imported stays in sys.modules for the whole Revit session, so an
    updated library would otherwise not take effect until Revit restarted.
    cad2bim's own modules are dropped too -- this tool reads through them, and
    auditing a stale copy of the thing under test would be worse than useless.
    """
    stale = [name for name in list(sys.modules)
             if name.startswith("anongee_toolkit")]
    for name in stale:
        del sys.modules[name]


_bootstrap_lib_path()
_drop_stale_modules()

# NOT purged above, and deliberately: it holds the CLR types Python.NET emitted
# for this Revit session. This tool imports cad2bim modules that derive from
# .NET interfaces, and rebuilding one of those types raises "Duplicate type name
# within an assembly" -- so the registry has to outlive the reload. It lives
# outside `anongee_toolkit`, which is why the purge above cannot reach it.
import anongee_clr                      # noqa: F401  (imported for its lifetime)

from anongee_toolkit.cad2bim_audit import (config, revit_capture, run, sidecar,
                                           workbook)
from anongee_toolkit.cad2bim_audit import __version__ as AUDIT_VERSION

_LOG = []


def _say(message):
    """Print to the pyRevit console and keep it for the completion dialog."""
    line = str(message)
    _LOG.append(line)
    print(line)


def _alert(title, message):
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)


def _error(title, message, detail=None):
    body = message
    if detail:
        body += "\n\n--- technical detail ---\n{0}".format(detail)
    print(body)
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)


class AuditDialog(object):
    """The one dialog: pick the DXF, choose the stages, run."""

    def __init__(self, doc):
        from anongee_toolkit.ui.xaml import load_xaml
        from anongee_toolkit.cad2bim.readers import dxf_linker

        self.result = None
        self.window = load_xaml(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ui.xaml"))

        self.links = revit_capture.existing_links(doc)
        combo = self.window.FindName("ExistingLinks")
        for label, _instance in self.links:
            combo.Items.Add(label)
        if self.links:
            combo.SelectedIndex = 0
        else:
            # Nothing to choose: the radio stays available but says why not, so
            # the user is not left clicking an option that silently does nothing.
            self.window.FindName("LinkExisting").IsEnabled = False
            combo.Items.Add("(no CAD links in this model)")
            combo.SelectedIndex = 0

        self._fill(self.window.FindName("Unit"),
                   [label for label, _value in dxf_linker.UNIT_CHOICES])
        self._fill(self.window.FindName("Placement"),
                   [label for label, _value in dxf_linker.PLACEMENT_CHOICES])

        self.window.FindName("BrowseDxf").Click += self._browse_dxf
        self.window.FindName("BrowseJson").Click += self._browse_json
        self.window.FindName("LinkExisting").Checked += self._toggle_links
        self.window.FindName("LinkExisting").Unchecked += self._toggle_links
        self.window.FindName("Run").Click += self._run
        self.window.FindName("Cancel").Click += self._cancel

    @staticmethod
    def _fill(combo, labels):
        for label in labels:
            combo.Items.Add(label)
        if combo.Items.Count:
            combo.SelectedIndex = 0

    def _toggle_links(self, sender, args):
        self.window.FindName("ExistingLinks").IsEnabled = bool(
            self.window.FindName("LinkExisting").IsChecked) and bool(self.links)

    def _browse_dxf(self, sender, args):
        path = _pick_file("Choose the DXF to audit", "DXF drawing (*.dxf)|*.dxf")
        if path:
            self.window.FindName("DxfPath").Text = path

    def _browse_json(self, sender, args):
        path = _pick_file("Choose a cad2bim run's JSON export",
                          "cad2bim export (*.json)|*.json")
        if path:
            self.window.FindName("JsonPath").Text = path

    def _cancel(self, sender, args):
        self.result = None
        self.window.Close()

    def _run(self, sender, args):
        dxf_path = (self.window.FindName("DxfPath").Text or "").strip()
        json_path = (self.window.FindName("JsonPath").Text or "").strip()
        want_dxf = bool(self.window.FindName("WantDxf").IsChecked)
        want_model = bool(self.window.FindName("WantModel").IsChecked)

        if self.window.FindName("LinkNew").IsChecked:
            mode = revit_capture.LINK_NEW
        elif self.window.FindName("LinkExisting").IsChecked:
            mode = revit_capture.LINK_EXISTING
        else:
            mode = revit_capture.LINK_NONE

        if not dxf_path and mode == revit_capture.LINK_NEW:
            _alert("No DXF chosen",
                   "Choose a .dxf to link, or switch to an existing link.")
            return
        if not (want_dxf or want_model or json_path or mode != revit_capture.LINK_NONE):
            _alert("Nothing to read",
                   "Tick at least one stage, or choose a cad2bim JSON.")
            return

        instance = None
        if mode == revit_capture.LINK_EXISTING and self.links:
            index = self.window.FindName("ExistingLinks").SelectedIndex
            if 0 <= index < len(self.links):
                instance = self.links[index][1]

        self.result = {
            "dxf_path": dxf_path,
            "json_path": json_path or None,
            "link_mode": mode,
            "link_instance": instance,
            "unit": str(self.window.FindName("Unit").SelectedItem or "Millimeter"),
            "placement": str(self.window.FindName("Placement").SelectedItem or ""),
            "this_view_only": bool(self.window.FindName("ThisViewOnly").IsChecked),
            "want_dxf": want_dxf and bool(dxf_path),
            "want_link": mode != revit_capture.LINK_NONE,
            "want_model": want_model,
        }
        self.window.Close()

    def show(self):
        self.window.ShowDialog()
        return self.result


def _pick_file(title, filter_text):
    dialog = WinForms.OpenFileDialog()
    dialog.Title = title
    dialog.Filter = filter_text
    dialog.Multiselect = False
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None


def _pick_save(default_name):
    dialog = WinForms.SaveFileDialog()
    dialog.Title = "Save the audit report"
    dialog.Filter = "Excel workbook (*.xlsx)|*.xlsx"
    dialog.FileName = default_name
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None


def main():
    started = time.time()
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None or uidoc.Document is None:
        _alert("No document", "Open a Revit project before running the audit.")
        return
    doc = uidoc.Document

    module_dir = os.path.dirname(os.path.abspath(run.__file__))
    _say("cad2bim_audit {0} loaded from {1}".format(AUDIT_VERSION, module_dir))

    from anongee_toolkit.cad2bim_audit.readers import dxf_raw
    if not dxf_raw.available():
        _error("ezdxf not available",
               "ezdxf could not be imported on this engine. Run "
               "tools/auto_provision.py to install it into lib/py3, then click "
               "the button again.", detail=str(dxf_raw._IMPORT_ERROR))
        return

    options = AuditDialog(doc).show()
    if not options:
        return

    try:
        captures, space, diagnostics = revit_capture.capture(
            doc, options, log=_say)
    except Exception:
        _error("Audit failed while reading",
               "Nothing was written. The model is unchanged apart from the DXF "
               "link, if one was created.", traceback.format_exc())
        return

    if not captures:
        _alert("Nothing was read",
               "No stage produced any data. Check the DXF path and that the "
               "link is visible in the active view.")
        return

    report = run.build_report(captures, space)
    for line in run.console_lines(report):
        _say(line)
    if diagnostics.get("link_error"):
        _say("link: {0}".format(diagnostics["link_error"]))
    _say("read in {0:.1f}s".format(time.time() - started))

    target = _pick_save(run.export_name(options.get("dxf_path"), captures))
    if not target:
        _say("report not saved (cancelled at the save dialog)")
        return

    try:
        sheets = run.build_sheets(report)
        workbook.write(target, sheets)
    except Exception:
        # A workbook that cannot be written must not lose the run: the same
        # tables go out as CSV rather than the user getting nothing.
        folder = os.path.splitext(target)[0] + "_csv"
        try:
            written = workbook.write_csv(folder, run.build_sheets(report))
            _say("xlsx failed; wrote {0} CSV file(s) to {1}".format(
                len(written), folder))
        except Exception:
            _error("Report not written", "Could not write the workbook.",
                   traceback.format_exc())
            return
    else:
        _say("wrote workbook -> {0}".format(target))

    json_target = os.path.splitext(target)[0] + ".json"
    try:
        sidecar.write(json_target, report)
        _say("wrote sidecar  -> {0}".format(json_target))
    except Exception:
        # The sidecar is a convenience; the workbook is the deliverable. Losing
        # it is worth saying and never worth failing a completed run over.
        _say("sidecar not written: {0}".format(traceback.format_exc()))

    severities = report.severity_counts()
    MessageBox.Show(
        "Audit complete in {0:.1f}s.\n\n"
        "{1} candidate member(s) reconciled.\n"
        "{2} error, {3} warning, {4} info finding(s).\n\n"
        "Workbook:\n{5}".format(
            time.time() - started, len(report.groups),
            severities.get(config.SEVERITY_ERROR, 0),
            severities.get(config.SEVERITY_WARNING, 0),
            severities.get(config.SEVERITY_INFO, 0), target),
        "CAD2BIM Audit", MessageBoxButton.OK, MessageBoxImage.Information)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _error("Unexpected error",
               "An unexpected error occurred. The CPython3 engine is still "
               "running -- you do not need to restart Revit.",
               traceback.format_exc())
