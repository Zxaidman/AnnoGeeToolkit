# -*- coding: utf-8 -*-
"""``stairs.sync`` — the RC stairs the STAIR_PLACEMENT sheet describes.

**Option B, for the project owner to look at and judge.** See
:mod:`anongee_toolkit.structural.stairs` for what it builds and what it costs.

A flight is a span between two grid intersections with a level at each end, so
the sheet reads like the beam sheet and is parsed by the same code: one row is
a straight flight, and **a dog-leg is two rows sharing a mark with a blank row
after them** — the same idiom that makes a continuous beam a group.

What is deliberately not here, and would be next if this direction is chosen:

* **the mid-landing slab** between two flights of a group. The two flights are
  placed correctly and the landing between them is not, so a dog-leg comes out
  as two flights with a gap. That is the honest state of it;
* handrails, nosings, finishes;
* rebar.
"""

__version__ = "0.1.0"

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
        plan=placement.plan_spans)


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
    """Build each flight. ``written``. Inside the caller's transaction."""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import flight as flight_module
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import stairs

    levels = _sheets.levels(doc)
    sizes = _stair_sizes(context, findings, finding)
    patterns = _sheets.naming(context, findings, finding)
    label_parameters = _marks.candidates(context)
    already = stairs.steps_by_mark(doc)
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
                    "no level called {0!r} in this model — a flight needs both "
                    "the level it leaves and the one it arrives at".format(
                        row.level if base is None else row.top_level)))
                continue

            rise_mm = _rise_mm(base, top)
            solved, issues = flight_module.solve(
                rise_mm, size, sheet=(context or {}).get("sheet", ""),
                row=row.row, mark=row.mark,
                available_mm=_distance(row.start_mm, row.end_mm))
            for issue in issues:
                findings.append(finding(issue.severity, row.row,
                                        issue.message))
            if solved is None:
                continue

            symbol, note = stairs.ensure_waist_symbol(
                doc, row.type_mark, solved.width_mm, solved.waist_mm, cache,
                name=_sheets.type_name(patterns, "stair", row.type_mark,
                                       w=solved.width_mm, t=solved.waist_mm))
            if symbol is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note and note not in reported:
                reported.add(note)
                findings.append(finding("Info", row.row, note))

            if plan.action == placement.MODIFY:
                instance = doc.GetElement(plan.existing)
                if instance is not None and stairs.set_type(doc, instance,
                                                            symbol):
                    written += 1
                else:
                    findings.append(finding(
                        "Warning", row.row,
                        "{0!r} is there but Revit would not change its waist "
                        "type to {1}".format(row.mark, row.type_mark)))
                continue

            direction = _direction(row.start_mm, row.end_mm)
            if direction is None:
                findings.append(finding(
                    "Error", row.row,
                    "{0!r} starts and ends at the same place, so it has no "
                    "direction to climb in".format(row.mark)))
                continue

            key = "{0}{1}".format(row.unique_mark, stairs.STEPS_SUFFIX)
            if key in already:
                findings.append(finding(
                    "Info", row.row,
                    "the steps for {0!r} were already in the model and were "
                    "left alone; only the waist was rebuilt".format(row.mark)))

            waist, _steps, step_note = stairs.create(
                doc, row.start_mm, direction, base, solved, symbol,
                mark=row.unique_mark, base_offset_mm=row.offset_mm or 0.0)
            if step_note:
                findings.append(finding("Warning", row.row, step_note))

            _marks.write(waist, row, label_parameters, reported, findings,
                         finding)
            _report_quantities(solved, row, findings, finding, reported)
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row, "{0!r}: {1}".format(row.mark, error)))
    return written


def _report_quantities(solved, row, findings, finding, reported):
    """Say what was built, in the numbers a person would check it with.

    A staircase one riser out arrives at the floor looking almost right, so the
    riser count and the pitch are reported for every flight rather than left to
    be measured off the model. This is the *first* thing anybody judging option
    B will want, and reading it off a schedule that does not exist yet is not
    an option.
    """
    findings.append(finding(
        "Info", row.row,
        "{0}: {1} risers of {2:.1f} mm, {3} treads of {4:.0f} mm, run "
        "{5:.0f} mm, pitch {6:.1f}°, concrete {7:.3f} m³ ({8:.3f} waist + "
        "{9:.3f} steps)".format(
            row.mark, solved.risers, solved.riser_mm, solved.treads,
            solved.tread_mm, solved.run_mm, solved.pitch_degrees,
            solved.volume_m3, solved.waist_volume_m3, solved.step_volume_m3)))


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
