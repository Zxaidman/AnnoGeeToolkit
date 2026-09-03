# -*- coding: utf-8 -*-
"""``grids.sync`` — make the model's grids agree with the GRIDS sheet.

The same shape as ``levels.sync``, and everything it decides is decided in
:mod:`anongee_toolkit.rc_automation.datum`, which has no Revit in it.

A grid is a line rather than a number, so two things differ from levels.

**Angle: 0 runs along +X, 90 along +Y.** A horizontal grid is 0, a vertical one
is 90, and a skewed one is whatever it is. A row can give both ends, or a start
and an angle — and if it gives both ends *and* an angle, the points win, because
they say more; the disagreement is reported.

**Position is synced; extent is not.** Grid extents are adjusted by hand in
nearly every view of a real project. Comparing endpoints would report every one
of them as needing a change and then undo the work, so two grids on the same
infinite line are the same grid whatever their lengths.

**A grid that runs a different way is left alone.** Revit has no way to change a
grid's direction: it would mean deleting and recreating, which loses anything
dimensioned or constrained to it. That is reported, with both angles, and never
done automatically.
"""

__version__ = "0.1.0"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.rc_automation import datum
    from anongee_toolkit.rc_automation import excel_engine
    from anongee_toolkit.commands import levels as levels_command

    summary = {"created": 0, "modified": 0, "matched": 0, "blocked": 0,
               "invalid": 0, "written": 0}

    uidoc = getattr(uiapp, "ActiveUIDocument", None)
    if uidoc is None:
        return summary, [], "no document is open"
    doc = uidoc.Document
    if doc.IsReadOnly:
        return summary, [], "this model is read-only"

    workbook = (envelope or {}).get("workbook") or ""
    sheet_name = (envelope or {}).get("sheet") or datum.SHEET_GRIDS
    if not workbook:
        return summary, [], "the job names no workbook"

    grids, read_issues = excel_engine.read_grid(workbook)
    findings = envelope_module.findings_from_issues(read_issues)
    grid = levels_command._sheet(grids, sheet_name)
    if grid is None:
        findings.append(levels_command._finding(
            "Error", sheet_name, "",
            "the workbook has no {0} sheet. It has: {1}".format(
                sheet_name, ", ".join(sorted(grids)) or "nothing")))
        return summary, findings, "nothing to read"

    rows, parse_issues = datum.parse_grids(
        grid, sheet_name,
        units=datum.normalise_unit(
            envelope_module.option(envelope, "units", datum.UNITS_MM)))
    findings.extend(envelope_module.findings_from_issues(parse_issues))

    existing = _existing(doc)
    plans, plan_issues = datum.plan_grids(rows, existing, sheet=sheet_name)
    findings.extend(envelope_module.findings_from_issues(plan_issues))
    summary.update(datum.summarise(plans))

    dry_run = envelope_module.option(envelope, "dryRun", True)
    doing = [plan for plan in plans if plan.will_write]
    if dry_run:
        return summary, findings, (
            "dry run: {0} grid(s) would be created or moved, and nothing was "
            "written. Set Write? to Yes to build.".format(len(doing)))
    if not doing:
        return summary, findings, "every grid already agrees with the sheet"

    written, write_findings = _apply(doc, doing)
    summary["written"] = written
    findings.extend(write_findings)
    return summary, findings, (
        "{0} grid(s) written, as one undo step".format(written))


def _existing(doc):
    """``[(name, ElementId, ((x1, y1), (x2, y2)))]`` in millimetres.

    Through ``structural.grids``, which already knows that a grid whose curve is
    an arc has no straight line to compare and returns nothing for it. An arc
    grid is therefore invisible to the plan — so the sheet can create a straight
    grid of the same name and Revit will refuse the duplicate, which is a clear
    failure rather than a silent one.
    """
    from anongee_toolkit.structural import grids as grid_module

    found = []
    for name, grid in grid_module.grids(doc).items():
        segment = grid_module.segment_mm(grid)
        if segment is None:
            continue
        found.append((name, grid.Id, segment))
    return found


def _apply(doc, plans):
    """Create and move grids. ``(written, findings)``. Owns its undo step."""
    from Autodesk.Revit.DB import ElementTransformUtils, Grid, Line
    from Autodesk.Revit.DB import Transaction, TransactionGroup, XYZ
    from anongee_toolkit.rc_automation import datum
    from anongee_toolkit.commands.levels import _finding
    from anongee_toolkit.revit.units import mm_to_ft

    findings = []
    written = 0

    group = TransactionGroup(doc, "AnonGee - grids.sync")
    group.Start()
    try:
        transaction = Transaction(doc, "Sync grids")
        transaction.Start()
        try:
            for plan in plans:
                try:
                    (x1, y1), (x2, y2) = plan.line
                    if plan.action == datum.CREATE:
                        line = Line.CreateBound(
                            XYZ(mm_to_ft(x1), mm_to_ft(y1), 0.0),
                            XYZ(mm_to_ft(x2), mm_to_ft(y2), 0.0))
                        grid = Grid.Create(doc, line)
                        _name(grid, plan.row.name, findings, plan)
                    else:
                        grid = doc.GetElement(plan.key)
                        if grid is None:
                            findings.append(_finding(
                                "Error", "", plan.row.row,
                                "{0!r} vanished between planning and "
                                "writing".format(plan.row.name)))
                            continue
                        # Moved rather than redrawn. The direction is known to
                        # match — datum blocks it otherwise — so a translation
                        # is the whole of the difference, and it keeps every
                        # dimension and constraint attached to this grid.
                        shift = _offset(plan.current_line, plan.line)
                        ElementTransformUtils.MoveElement(
                            doc, grid.Id,
                            XYZ(mm_to_ft(shift[0]), mm_to_ft(shift[1]), 0.0))
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


def _offset(current, wanted):
    """How far to slide *current* so it lies on *wanted*'s line.

    Perpendicular only. The two are known to be parallel by the time this is
    called, so sliding along their shared direction would move the grid without
    changing where it is — and would drag its extents off the building for no
    reason.
    """
    from anongee_toolkit.rc_automation import datum

    (x1, y1), (x2, y2) = current
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return wanted[0][0] - x1, wanted[0][1] - y1

    # The unit normal, and the signed distance from the current line to the
    # wanted one measured along it.
    nx, ny = -dy / length, dx / length
    px, py = wanted[0]
    distance = nx * (px - x1) + ny * (py - y1)
    return nx * distance, ny * distance


def _name(grid, wanted, findings, plan):
    from anongee_toolkit.commands.levels import _finding
    try:
        grid.Name = wanted
    except Exception as error:
        findings.append(_finding(
            "Warning", "", plan.row.row,
            "created but Revit would not take the name {0!r}: {1}".format(
                wanted, error)))
