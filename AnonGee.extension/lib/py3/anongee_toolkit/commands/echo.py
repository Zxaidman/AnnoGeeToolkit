# -*- coding: utf-8 -*-
"""``bridge.echo`` — the job to run first, and the one that changes nothing.

It answers with what it was asked and what the model is. No workbook is opened,
no transaction is started, nothing is written.

That is the point. Every command after this one has two things that can be
wrong: the wire, and the work. This has only the wire, so when ``levels.sync``
misbehaves the question *"did the job even arrive?"* is already answered.

It is also the only command whose output tells you the listener is running on
Revit's own thread — the level and grid counts cannot be read anywhere else.
"""

__version__ = "0.1.0"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module

    summary = {"read": 0, "written": 0}
    findings = []

    uidoc = getattr(uiapp, "ActiveUIDocument", None)
    if uidoc is None:
        return summary, findings, "no document is open — nothing to report on"

    doc = uidoc.Document
    summary["title"] = doc.Title
    summary["path"] = doc.PathName or "(unsaved)"

    from Autodesk.Revit.DB import FilteredElementCollector, Level, Grid
    for label, kind in (("levels", Level), ("grids", Grid)):
        try:
            found = (FilteredElementCollector(doc).OfClass(kind)
                     .WhereElementIsNotElementType().ToElements())
            summary[label] = len(list(found))
            summary["read"] += summary[label]
        except Exception as error:
            findings.append({
                "severity": "Warning", "sheet": "", "row": "", "column": "",
                "message": "could not count {0}: {1}".format(label, error),
            })

    # Echoed back so a caller can see its own options survived the round trip
    # unchanged — which is the other half of what this command is for.
    for name in ("dryRun", "onConflict", "keyParameter"):
        summary["option." + name] = envelope_module.option(envelope, name)

    return summary, findings, "nothing was written; this command never writes"
