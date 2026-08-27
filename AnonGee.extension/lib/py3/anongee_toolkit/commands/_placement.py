# -*- coding: utf-8 -*-
"""The half of a placement command that is the same for every element.

Open the workbook, find the sheet, read the unit, ask the model for its grids,
locate every row, plan, and — unless this is a dry run — write it in one undo
step. What is left for a command to supply is the part that differs: how to read
its sheet, what the model already has, and how to place one.

It lives here rather than in each command because the parts that are easy to get
subtly wrong are all in this half. The transaction group that has to be
assimilated, the dry run that has to report exactly what a real run would do, the
document that might not be open, the sheet that might be missing — four commands
each with their own copy is four chances to get one of them wrong, and the third
copy is where it happens.
"""

__version__ = "0.1.0"


def run(uiapp, envelope, sheet_default, parse, span, existing, apply, what,
        option, locate=None, plan=None, write=None):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.rc_automation import datum
    from anongee_toolkit.rc_automation import excel_engine
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.bridge import envelope as envelope_module

    summary = {"created": 0, "modified": 0, "matched": 0, "blocked": 0,
               "invalid": 0, "written": 0}

    uidoc = getattr(uiapp, "ActiveUIDocument", None)
    if uidoc is None:
        return summary, [], "no document is open"
    doc = uidoc.Document
    if doc.IsReadOnly:
        return summary, [], "this model is read-only"

    workbook = (envelope or {}).get("workbook") or ""
    sheet_name = (envelope or {}).get("sheet") or sheet_default
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

    units = datum.normalise_unit(option(envelope, "units", datum.UNITS_MM))
    rows, parse_issues = parse(grid, sheet_name, units)
    findings.extend(envelope_module.findings_from_issues(parse_issues))

    # A column stands at one intersection; a beam runs between two. Same two
    # steps either way, so the caller says which pair to use rather than this
    # growing a branch per element.
    intersection, grid_note = _intersection(doc)
    locate_with = locate or placement.locate
    findings.extend(envelope_module.findings_from_issues(
        locate_with(rows, intersection, sheet=sheet_name)))

    if plan is None:
        plans, plan_issues = placement.plan(rows, existing(doc),
                                            sheet=sheet_name, span=span)
    else:
        plans, plan_issues = plan(rows, existing(doc), sheet=sheet_name)
    findings.extend(envelope_module.findings_from_issues(plan_issues))
    summary.update(placement.summarise(plans))

    doing = [plan for plan in plans if plan.will_write]
    reading = "read as {0}; {1}".format(units, grid_note)
    if option(envelope, "dryRun", True):
        return summary, findings, (
            "dry run: {0} {1}(s) would be placed or changed, and nothing was "
            "written. Set Write? to Yes to build. ({2})".format(
                len(doing), what, reading))
    if not doing:
        return summary, findings, _nothing_to_do(summary, what, reading)

    context = {"sheets": grids, "units": units, "sheet": sheet_name,
               "workbook": workbook}
    written, write_findings = (write or _write)(doc, doing, apply, what,
                                                context)
    summary["written"] = written
    findings.extend(write_findings)
    return summary, findings, _what_happened(written, len(doing), what, reading)


def _nothing_to_do(summary, what, reading):
    """Why there was nothing to do — and they are not the same reason.

    ``doing`` is empty when every row already matches the model, and it is
    **also** empty when not one row could be located. Both used to report
    *every beam the sheet describes is already there*, which in the second case
    is exactly backwards: nothing was there, and nothing could be placed. A run
    that found no grid to stand on said the model was up to date. BUG-33.
    """
    invalid = summary.get("invalid") or 0
    matched = summary.get("matched") or 0
    if invalid and not matched:
        return ("nothing was placed: not one of the {0} row(s) could be "
                "located. Nothing in the model was checked, so this is not a "
                "run that found everything already there. ({1})".format(
                    invalid, reading))
    if invalid:
        return ("every {0} that could be located is already there, but {1} "
                "row(s) could not be located at all — see the findings "
                "({2})".format(what, invalid, reading))
    return "every {0} the sheet describes is already there".format(what)


def _what_happened(written, planned, what, reading):
    """The shortfall first, when there is one.

    ``written=22`` out of ``created=132`` was reported as *"22 beam(s) written,
    as one undo step"*. The number was right and the sentence was reassuring,
    which is the combination that let a hundred and ten missing beams read as a
    success in the log for four days. BUG-33.
    """
    if written >= planned:
        return "{0} {1}(s) written, as one undo step ({2})".format(
            written, what, reading)
    return ("{0} of {1} {2}(s) written — {3} did NOT happen and each one is in "
            "the findings. Read those before running anything else, because "
            "the next command overwrites them. ({4})".format(
                written, planned, what, planned - written, reading))


def _write(doc, plans, apply, what, context):
    """One transaction group, assimilated. ``(written, findings)``.

    A run that throws halfway is rolled back whole. Half a floor of columns is
    worse than none, because none is obvious.

    **Six of the seven commands use this.** Stairs cannot: ``StairsEditScope``
    refuses to start while a transaction is open, and it has to open one of its
    own. So :func:`run` takes a *write* to override this, and
    :mod:`commands.stairs` supplies one that keeps the group — which is what
    gives the single undo step — and leaves the transaction to the scope. See
    :func:`outside_a_transaction`.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup

    findings = []

    def finding(severity, row, message):
        return _finding(severity, "", row, message)

    group = TransactionGroup(doc, "AnonGee - {0}s.sync".format(what))
    group.Start()
    try:
        transaction = Transaction(doc, "Place {0}s".format(what))
        transaction.Start()
        try:
            written = apply(doc, plans, findings, finding, context)
            transaction.Commit()
        except Exception as inner:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            raise inner
        group.Assimilate()
    except Exception as error:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        findings.append(_finding(
            "Error", "", "", "the run was rolled back: {0}".format(error)))
        return 0, findings
    return written, findings


def outside_a_transaction(doc, plans, apply, what, context):
    """The same group, without an open transaction. ``(written, findings)``.

    ``StairsEditScope.Start`` throws if a transaction is open, and there is no
    way to place a Revit stair without one. A ``TransactionGroup`` is not a
    transaction, so the undo behaviour every other command has is kept: one
    group, assimilated, one step in the undo stack.

    What is lost is the all-or-nothing property. Each flight commits its own
    scope, so a run that fails on the fourth of five leaves three built. That is
    reported rather than hidden — and it is the reason this is a separate
    function with its own name rather than a flag on the one above.
    """
    from Autodesk.Revit.DB import TransactionGroup

    findings = []

    def finding(severity, row, message):
        return _finding(severity, "", row, message)

    group = TransactionGroup(doc, "AnonGee - {0}s.sync".format(what))
    group.Start()
    try:
        written = apply(doc, plans, findings, finding, context)
        group.Assimilate()
    except Exception as error:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        findings.append(_finding(
            "Error", "", "", "the run was rolled back: {0}".format(error)))
        return 0, findings
    return written, findings


def _intersection(doc):
    """``(crossing function, one sentence about the grids)``.

    The grids are read **once**, before anything is placed, and the crossing
    function closes over them. Asking Revit per row would be the same answer
    fifteen times over, and ninety times over on the column sheet.
    """
    try:
        from anongee_toolkit.structural import grids as grid_module
        found = grid_module.grids(doc)
    except Exception as error:
        def missing(name_x, name_y):
            return None, "the grids could not be read: {0}".format(error)
        return missing, "no grids could be read"

    def cross(name_x, name_y):
        return grid_module.intersection_mm(found, name_x, name_y)

    return cross, "{0} grid(s) in the model".format(len(found))


def _sheet(grids, wanted):
    """The named sheet, matched the way a person would spell it."""
    folded = "".join(c for c in wanted.lower() if c.isalnum())
    for name, grid in (grids or {}).items():
        if "".join(c for c in name.lower() if c.isalnum()) == folded:
            return grid
    return None


def _finding(severity, sheet, row, message):
    return {"severity": severity, "sheet": sheet, "row": row, "column": "",
            "message": message}
