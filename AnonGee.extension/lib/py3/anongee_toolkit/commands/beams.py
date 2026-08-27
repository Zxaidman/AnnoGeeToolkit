# -*- coding: utf-8 -*-
"""``beams.sync`` — place the framing the BEAM_PLACEMENT sheet describes.

**Continuity is the layout.** A simply supported beam is one row; a continuous
beam is a group of rows, one per span, sharing a mark, with a blank row between
groups. So the parser reads groups, not rows — and the blank rows are the only
thing saying where one beam ends and the next begins.

**One Revit member per span**, which is not a simplification: a four-span
continuous beam *is* four members that join. What the grouping buys is the
schedule mark — all four carry ``B01-1``, and Revit's own ``Mark`` carries the
key that makes each one findable.

Joins and cutbacks are left to Revit. Its automatic joins do most of it and the
rest is a per-project judgement about which member runs through; placing
correctly and leaving the joins alone is honest, and guessing at a corner is
not.
"""

__version__ = "0.1.0"

#: Where a beam's section comes from when the model does not have the type.
TYPES_SHEET = "BEAM_TYPES"

#: Where the columns a beam stops against are described.
COLUMN_PLACEMENT_SHEET = "COLUMN_PLACEMENT"
COLUMN_TYPES_SHEET = "COLUMN_TYPES"

#: What `EndPrep` may say. The first is the default and the BIM-correct one.
COLUMN_FACE = "column face"
GRID_LINE = "grid line"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_BEAMS,
        parse=_parse,
        span=True,
        existing=_existing,
        apply=_apply,
        what="beam",
        option=envelope_module.option,
        locate=placement.locate_span,
        plan=placement.plan_spans)


def _parse(grid, sheet, units):
    """``([PlacementRow], [Issue])`` — groups flattened, marks already shared.

    The grouping did its work in the parser: every row in a group carries the
    same mark. Downstream a beam is a beam, so the groups are flattened here
    rather than threaded through everything that does not care.
    """
    from anongee_toolkit.rc_automation import placement
    groups, issues = placement.parse_beams(grid, sheet, units)
    rows = []
    for group in groups:
        for row in group:
            rows.append(row)
    return rows, issues


def _existing(doc):
    from anongee_toolkit.structural import framing
    return framing.placed(doc)


def _apply(doc, plans, findings, finding, context):
    """Create and retype beams. ``written``. Inside the caller's transaction."""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import framing

    levels = _sheets.levels(doc)
    sizes = _sheets.sizes(context, TYPES_SHEET, findings, finding)
    columns = _column_faces(context)
    patterns = _sheets.naming(context, findings, finding)
    label_parameters = _marks.candidates(context)
    schedule_marks = _marks.labels(
        [item.row for item in plans], patterns, "beam_mark")
    for label, sharing in _marks.collisions(schedule_marks):
        findings.append(finding(
            "Warning", "",
            "{0} sections would all schedule as {1!r}: {2}. The {3} pattern "
            "counts within a prefix but does not print it - use "
            "'{{prefix}}{{n}}' on NAMING so they read PB1 and B1.".format(
                len(sharing), label, ", ".join(sharing), "beam_mark")))
    reported = set()
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            size = sizes.get(_fold(row.type_mark)) or {}
            symbol, note = framing.ensure_symbol(
                doc, row.type_mark, size.get("width_mm"),
                size.get("depth_mm"), cache,
                name=_sheets.type_name(patterns, "beam", row.type_mark,
                                       b=size.get("width_mm"),
                                       h=size.get("depth_mm")))
            if symbol is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note and note not in reported:
                reported.add(note)
                findings.append(finding("Info", row.row, note))

            if plan.action == placement.MODIFY:
                instance = doc.GetElement(plan.existing)
                if instance is None:
                    findings.append(finding(
                        "Error", row.row,
                        "{0!r} vanished between planning and writing".format(
                            row.mark)))
                    continue
                if framing.set_type(doc, instance, symbol):
                    written += 1
                else:
                    findings.append(finding(
                        "Warning", row.row,
                        "{0!r} is there but Revit would not change its type "
                        "to {1}".format(row.mark, row.type_mark)))
                continue

            level = levels.get(_fold(row.level))
            if level is None:
                findings.append(finding(
                    "Error", row.row,
                    "no level called {0!r} in this model".format(row.level)))
                continue

            cutback = _cutback(row, columns, reported, findings, finding)
            instance = framing.create(doc, row.start_mm, row.end_mm, symbol,
                                      level, row.offset_mm or 0.0,
                                      cutback_mm=cutback)
            _marks.write(instance, row, label_parameters, reported, findings,
                         finding,
                         schedule_marks.get(_fold(row.type_mark)))
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row, "{0!r}: {1}".format(row.mark, error)))
    return written


def _cutback(row, columns, reported, findings, finding):
    """``(start, end)`` — how far to pull each end back to reach a column face.

    A grid intersection is where a **column** stands, not where a beam ends. A
    beam drawn between two of them runs through both columns, so the concrete
    is counted twice at every junction and the shop drawing shows a beam that
    does not exist.

    Half the column's dimension **along the beam's own direction** — its Width
    for a beam running along X, its Depth for one running along Y, swapped when
    the column is turned. An end with no column under it is not cut back, and
    that is said once.
    """
    if _fold(row.edge_rule or "") == _fold(GRID_LINE):
        return (0.0, 0.0)

    dx = (row.end_mm[0] - row.start_mm[0]) if row.start_mm and row.end_mm else 0
    dy = (row.end_mm[1] - row.start_mm[1]) if row.start_mm and row.end_mm else 0
    along_x = abs(dx) >= abs(dy)

    found = []
    missing = []
    for name_x, name_y, which in ((row.from_grid_x, row.from_grid_y, "start"),
                                  (row.to_grid_x, row.to_grid_y, "end")):
        column = columns.get((_fold(row.level), _fold(name_x), _fold(name_y)))
        if column is None:
            missing.append(which)
            found.append(0.0)
            continue
        width, depth, rotation = column
        # A column turned 90 degrees presents its other face to the beam.
        turned = abs((rotation or 0.0) % 180.0 - 90.0) < 45.0
        across = (depth if turned else width) if along_x else (
            width if turned else depth)
        found.append((across or 0.0) / 2.0)

    if missing and "no-column" not in reported:
        reported.add("no-column")
        findings.append(finding(
            "Info", row.row,
            "{0!r} has no column under its {1} in {2}, so that end is left on "
            "the grid line. Beams are cut back by half the column's dimension "
            "along their own direction.".format(
                row.mark, " and ".join(missing), COLUMN_PLACEMENT_SHEET)))
    return tuple(found)


def _column_faces(context):
    """``{(level, gx, gy): (width_mm, depth_mm, rotation)}`` for every column.

    Keyed on the level the column's **top** reaches, because that is the level
    the beam sits on. Read once — a hundred and thirty-two beams asking twice
    each is two hundred and sixty-four passes over the same two sheets.
    """
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement

    grid = _sheets.sheet(context, COLUMN_PLACEMENT_SHEET)
    if grid is None:
        return {}

    units = (context or {}).get("units", "mm")
    sections, _issues = placement.parse_types(
        _sheets.sheet(context, COLUMN_TYPES_SHEET) or [], COLUMN_TYPES_SHEET,
        units)
    rows, _row_issues = placement.parse_columns(grid, COLUMN_PLACEMENT_SHEET,
                                                units)

    faces = {}
    for row in rows:
        section = sections.get(_fold(row.type_mark)) or {}
        width = section.get("width_mm")
        depth = section.get("depth_mm")
        if not width and not depth:
            continue
        faces[(_fold(row.top_level), _fold(row.grid_x), _fold(row.grid_y))] = (
            width, depth, row.rotation_deg or 0.0)
    return faces


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
