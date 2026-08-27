# -*- coding: utf-8 -*-
"""``stairs.sync`` — real Revit stairs from the STAIR_PLACEMENT sheet.

**Option A**, chosen by the project owner over the waist-slab version that
shipped in 1.24.0. Their reason, and it is the right one: a stair built out of
beams and slabs is a management nightmare to schedule, and Revit's own stair is
what a stair should be.

A flight is a span between two grid intersections with a level at each end, so
the sheet reads like the beam sheet and is parsed by the same code. **A dog-leg
is two rows sharing a mark with a blank row after them**, the same idiom that
makes a continuous beam a group — and, for now, the same idiom that gets two
separate straight flights, because the landing between them is not placed yet.

**This command holds no transaction while it writes**, which no other command
can say. ``StairsEditScope`` refuses to start inside one. So it is run through
``_placement.outside_a_transaction`` and opens what it needs itself: one
transaction for type work, then a scope per flight.

What that costs: a run that fails on the fourth of five flights leaves three
built. Every other command rolls back whole. It is reported.
"""

__version__ = "0.2.0"

TYPES_SHEET = "STAIR_TYPES"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_STAIRS,
        parse=_parse,
        span=True,
        existing=_existing,
        apply=_apply,
        what="stair flight",
        option=envelope_module.option,
        locate=placement.locate_span,
        plan=placement.plan_spans,
        write=_placement.outside_a_transaction)


def _parse(grid, sheet, units):
    """Groups flattened — a flight is a flight downstream."""
    from anongee_toolkit.rc_automation import placement
    groups, issues = placement.parse_stairs(grid, sheet, units)
    rows = []
    for group in groups:
        for row in group:
            rows.append(row)
    return rows, issues


def _existing(doc):
    from anongee_toolkit.structural import stairs
    return stairs.placed(doc)


def _apply(doc, plans, findings, finding, context):
    """Build each flight. ``written``. **No transaction is open here.**"""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import flight as flight_module
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import stairs

    levels = _sheets.levels(doc)
    sizes = _stair_sizes(context, findings, finding)
    patterns = _sheets.naming(context, findings, finding)
    label_parameters = _marks.candidates(context)
    reported = set()
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            size = sizes.get(_fold(row.type_mark)) or {}
            base = levels.get(_fold(row.level))
            top = levels.get(_fold(row.top_level))
            if base is None or top is None:
                findings.append(finding(
                    "Error", row.row,
                    "no level called {0!r} in this model - a flight needs both "
                    "the level it leaves and the one it arrives at".format(
                        row.level if base is None else row.top_level)))
                continue

            solved, issues = flight_module.solve(
                _rise_mm(base, top), size,
                sheet=(context or {}).get("sheet", ""), row=row.row,
                mark=row.mark, available_mm=_distance(row.start_mm, row.end_mm))
            for issue in issues:
                findings.append(finding(issue.severity, row.row, issue.message))
            if solved is None:
                continue

            # The type is made inside a transaction of its own, which is then
            # committed before the edit scope opens. A scope will not start
            # while a transaction is open, and a type cannot be made without
            # one, so they cannot overlap.
            type_id, note = _ensure_type(doc, row, size, solved, patterns,
                                         cache)
            if type_id is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note and note not in reported:
                reported.add(note)
                findings.append(finding("Info", row.row, note))

            if plan.action == placement.MODIFY:
                written += _retype(doc, plan, row, type_id, findings, finding)
                continue

            direction = _direction(row.start_mm, row.end_mm)
            if direction is None:
                findings.append(finding(
                    "Error", row.row,
                    "{0!r} starts and ends at the same place, so it has no "
                    "direction to climb in".format(row.mark)))
                continue

            built, build_note = stairs.create(
                doc, row.start_mm, direction, base, top, solved, type_id,
                mark=row.unique_mark)
            if build_note:
                findings.append(finding("Info", row.row, build_note))

            _write_mark(doc, built, row, label_parameters, reported, findings,
                        finding)
            _report_quantities(solved, row, findings, finding)
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row,
                "{0!r}: {1}. Flights already built in this run stay built - "
                "a stair commits its own scope, so this one cannot be rolled "
                "back with the others.".format(row.mark, error)))
    return written


def _ensure_type(doc, row, size, solved, patterns, cache):
    """``(ElementId, note)``, inside a transaction opened and closed here."""
    from Autodesk.Revit.DB import Transaction
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.structural import stairs

    key = _fold(row.type_mark)
    if key in cache:
        return cache[key], ""

    transaction = Transaction(doc, "AnonGee stair type")
    try:
        transaction.Start()
        type_id, note = stairs.ensure_type(
            doc, row.type_mark, size, cache,
            name=_sheets.type_name(patterns, "stair", row.type_mark,
                                   w=solved.width_mm, t=solved.waist_mm))
        transaction.Commit()
    except Exception as error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        return None, "could not prepare a stair type: {0}".format(error)
    return type_id, note


def _retype(doc, plan, row, type_id, findings, finding):
    """Change an existing stair's type. ``1`` when it took, else ``0``."""
    from Autodesk.Revit.DB import Transaction
    from anongee_toolkit.structural import stairs

    instance = doc.GetElement(plan.existing)
    if instance is None:
        findings.append(finding(
            "Error", row.row,
            "{0!r} vanished between planning and writing".format(row.mark)))
        return 0

    transaction = Transaction(doc, "AnonGee stair retype")
    try:
        transaction.Start()
        took = stairs.set_type(doc, instance, type_id)
        transaction.Commit()
    except Exception as error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        findings.append(finding("Error", row.row, "{0!r}: {1}".format(
            row.mark, error)))
        return 0

    if not took:
        findings.append(finding(
            "Warning", row.row,
            "{0!r} is there but Revit would not change its type to "
            "{1}".format(row.mark, row.type_mark)))
        return 0
    return 1


def _write_mark(doc, built, row, label_parameters, reported, findings,
                finding):
    """The mark, in its own transaction — the scope has already closed."""
    from Autodesk.Revit.DB import Transaction
    from anongee_toolkit.commands import _marks

    transaction = Transaction(doc, "AnonGee stair mark")
    try:
        transaction.Start()
        _marks.write(built, row, label_parameters, reported, findings, finding)
        transaction.Commit()
    except Exception:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()


def _report_quantities(solved, row, findings, finding):
    """Say what was built, in the numbers a person would check it with.

    A staircase one riser out arrives at the floor looking almost right, so the
    riser count and the pitch are reported for every flight rather than left to
    be measured off the model.
    """
    findings.append(finding(
        "Info", row.row,
        "{0}: {1} risers of {2:.1f} mm, {3} treads of {4:.0f} mm, run "
        "{5:.0f} mm, pitch {6:.1f} deg, waist {7:.0f} mm".format(
            row.mark, solved.risers, solved.riser_mm, solved.treads,
            solved.tread_mm, solved.run_mm, solved.pitch_degrees,
            solved.waist_mm)))


def _stair_sizes(context, findings, finding):
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement

    grid = _sheets.sheet(context, TYPES_SHEET)
    if grid is None:
        findings.append(finding(
            "Warning", "",
            "this workbook has no {0} sheet, so no flight can be sized"
            .format(TYPES_SHEET)))
        return {}
    found, issues = placement.parse_stair_types(
        grid, TYPES_SHEET, (context or {}).get("units", "mm"))
    for item in envelope_module.findings_from_issues(issues):
        findings.append(item)
    return found


def _rise_mm(base_level, top_level):
    from anongee_toolkit.revit.units import ft_to_mm
    return ft_to_mm(top_level.Elevation - base_level.Elevation)


def _direction(start_mm, end_mm):
    """The unit vector a flight climbs along in plan, or ``None``."""
    if not start_mm or not end_mm:
        return None
    dx = end_mm[0] - start_mm[0]
    dy = end_mm[1] - start_mm[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return None
    return (dx / length, dy / length)


def _distance(start_mm, end_mm):
    if not start_mm or not end_mm:
        return None
    dx = end_mm[0] - start_mm[0]
    dy = end_mm[1] - start_mm[1]
    return (dx * dx + dy * dy) ** 0.5


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
