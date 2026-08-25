# -*- coding: utf-8 -*-
"""``levels.sync`` — make the model's levels agree with the LEVELS sheet.

The first command that writes. Everything it decides is decided in
:mod:`anongee_toolkit.rc_automation.datum`, which has no Revit in it and is
tested off Revit; this file opens the workbook, asks the model what it has, and
does what the plan says.

**Nothing is written unless ``dryRun`` is switched off**, and a dry run reports
exactly what a real run would do. That is not a courtesy — it is the only reason
this is safe to point at somebody's live model.

**One undo step.** A ``TransactionGroup`` the command owns, assimilated at the
end, so a user who does not like the result presses Ctrl+Z once.

Four things it will not do, all of them from ``datum``: it never deletes a level
the sheet omits, never renames one, never creates a second level at an occupied
elevation, and never matches names loosely. Each is a refusal to guess about
something that would be expensive to undo.
"""

__version__ = "0.1.0"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.rc_automation import datum
    from anongee_toolkit.rc_automation import excel_engine

    summary = {"created": 0, "modified": 0, "matched": 0, "blocked": 0,
               "invalid": 0, "written": 0}

    uidoc = getattr(uiapp, "ActiveUIDocument", None)
    if uidoc is None:
        return summary, [], "no document is open"
    doc = uidoc.Document
    if doc.IsReadOnly:
        return summary, [], "this model is read-only"

    workbook = (envelope or {}).get("workbook") or ""
    sheet_name = (envelope or {}).get("sheet") or datum.SHEET_LEVELS
    if not workbook:
        return summary, [], "the job names no workbook"

    grids, read_issues = excel_engine.read_grid(workbook)
    findings = envelope_module.findings_from_issues(read_issues)
    grid = _sheet(grids, sheet_name)
    if grid is None:
        findings.append(_finding(
            "Error", sheet_name, "",
            "the workbook has no {0} sheet. It has: {1}".format(
                sheet_name, ", ".join(sorted(grids)) or "nothing")))
        return summary, findings, "nothing to read"

    units = datum.normalise_unit(
        envelope_module.option(envelope, "units", datum.UNITS_MM))
    rows, parse_issues = datum.parse_levels(grid, sheet_name, units=units)
    findings.extend(envelope_module.findings_from_issues(parse_issues))

    # A row measured from the survey point needs the model's own offset, and a
    # row that gives both elevations gets them checked against it. Asked once,
    # here, so the pure half never has to guess at it.
    offset_mm, offset_note = _survey_offset(doc)
    findings.extend(envelope_module.findings_from_issues(
        datum.resolve_elevations(rows, offset_mm, sheet=sheet_name)))

    existing = _existing(doc)
    plans, plan_issues = datum.plan_levels(rows, existing, sheet=sheet_name)
    findings.extend(envelope_module.findings_from_issues(plan_issues))
    summary.update(datum.summarise(plans))

    dry_run = envelope_module.option(envelope, "dryRun", True)
    doing = [plan for plan in plans if plan.will_write]
    reading = "read as {0}; {1}".format(units, offset_note)
    if dry_run:
        return summary, findings, (
            "dry run: {0} level(s) would be created or changed, and nothing "
            "was written. Set Write? to Yes to build. ({1})".format(
                len(doing), reading))
    if not doing:
        return summary, findings, "every level already agrees with the sheet"

    written, write_findings = _apply(doc, doing)
    summary["written"] = written
    findings.extend(write_findings)
    return summary, findings, (
        "{0} level(s) written, as one undo step ({1})".format(written, reading))


def _sheet(grids, wanted):
    """The named sheet, matched the way a person would spell it."""
    folded = "".join(c for c in wanted.lower() if c.isalnum())
    for name, grid in (grids or {}).items():
        if "".join(c for c in name.lower() if c.isalnum()) == folded:
            return grid
    return None


def _survey_offset(doc):
    """``(offset_mm or None, one sentence about it)``."""
    try:
        from anongee_toolkit.structural import coordinates
        return coordinates.survey_offset_mm(doc)
    except Exception as error:
        return None, "the survey offset could not be read: {0}".format(error)


def _existing(doc):
    """``[(name, ElementId, elevation_mm)]`` — what the model has now."""
    from anongee_toolkit.structural import levels as level_module
    return level_module.levels(doc)


def _finding(severity, sheet, row, message):
    return {"severity": severity, "sheet": sheet, "row": row, "column": "",
            "message": message}


def _apply(doc, plans):
    """Create and move levels. ``(written, findings)``. Requires no transaction
    from the caller — this owns the group, because one undo step is the promise.
    """
    from Autodesk.Revit.DB import Level, Transaction, TransactionGroup
    from Autodesk.Revit.DB import BuiltInParameter
    from anongee_toolkit.rc_automation import datum
    from anongee_toolkit.revit.units import mm_to_ft

    findings = []
    written = 0

    group = TransactionGroup(doc, "AnonGee - levels.sync")
    group.Start()
    try:
        transaction = Transaction(doc, "Sync levels")
        transaction.Start()
        try:
            for plan in plans:
                try:
                    if plan.action == datum.CREATE:
                        level = Level.Create(
                            doc, mm_to_ft(plan.row.elevation_mm))
                        _name(level, plan.row.name, findings, plan)
                        _story(level, plan.row.story, BuiltInParameter)
                    else:
                        level = doc.GetElement(plan.key)
                        if level is None:
                            findings.append(_finding(
                                "Error", "", plan.row.row,
                                "{0!r} vanished between planning and "
                                "writing".format(plan.row.name)))
                            continue
                        level.Elevation = mm_to_ft(plan.row.elevation_mm)
                        _story(level, plan.row.story, BuiltInParameter)
                    written += 1
                except Exception as error:
                    findings.append(_finding(
                        "Error", "", plan.row.row,
                        "{0!r}: {1}".format(plan.row.name, error)))
            transaction.Commit()
        except Exception as inner:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            raise inner
        group.Assimilate()
    except Exception as error:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        findings.append(_finding("Error", "", "",
                                 "the run was rolled back: {0}".format(error)))
        return 0, findings
    return written, findings


def _name(level, wanted, findings, plan):
    """Name a new level, and say so plainly if Revit will not take it."""
    try:
        level.Name = wanted
    except Exception as error:
        findings.append(_finding(
            "Warning", "", plan.row.row,
            "created at {0:g} mm but Revit would not take the name {1!r}: "
            "{2}".format(plan.row.elevation_mm, wanted, error)))


def _story(level, story, BuiltInParameter):
    """Set the building-story flag, only when the sheet said something.

    ``None`` means the sheet was silent, and a thing the sheet did not say is a
    thing this does not change.
    """
    if story is None:
        return
    try:
        parameter = level.get_Parameter(
            BuiltInParameter.LEVEL_IS_BUILDING_STORY)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(1 if story else 0)
    except Exception:
        pass
