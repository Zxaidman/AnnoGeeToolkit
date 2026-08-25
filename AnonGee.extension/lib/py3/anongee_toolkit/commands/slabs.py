# -*- coding: utf-8 -*-
"""``slabs.sync`` — one slab per panel, stopping at the inner face of its beams.

**A slab is a panel, not a floor.** One slab over a whole storey swallows every
beam under it in the quantities, and it is wrong in the schedule long before it
is wrong in the model. So each row is one bay, named by the four grids around
it.

**The inset is read, not assumed.** ``EdgeRule = Inner face of beam`` means each
edge comes in by half the width of the beam **actually on that edge** — looked
up in `BEAM_PLACEMENT`, whose type is looked up in `BEAM_TYPES`. A panel with a
300 beam on one side and a 230 plinth beam on another is inset differently on
those two sides, which is the only reading of *inner face* that is true.

An edge with no beam on it is not inset, and that is said once rather than
forty times.
"""

__version__ = "0.1.0"

#: Where a slab's thickness comes from, and where the beam widths come from.
TYPES_SHEET = "SLAB_TYPES"
BEAM_PLACEMENT_SHEET = "BEAM_PLACEMENT"
BEAM_TYPES_SHEET = "BEAM_TYPES"

#: What `EdgeRule` may say, and what each one does to an edge.
INNER_FACE = "inner face of beam"
GRID_LINE = "grid line"
OUTER_FACE = "outer face of beam"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_SLABS,
        parse=placement.parse_slabs,
        span=True,
        existing=_existing,
        apply=_apply,
        what="slab",
        option=envelope_module.option,
        locate=placement.locate_span,
        plan=placement.plan_spans)


def _existing(doc):
    """The floors already there, foundations excluded.

    A pad is a floor too, and matching a slab against one would have this
    command decide a footing at the same coordinates was the panel it was
    looking for. Foundations belong to ``footings.sync``.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, FilteredElementCollector,
                                   Floor)
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for floor in (FilteredElementCollector(doc)
                  .OfCategory(BuiltInCategory.OST_Floors)
                  .OfClass(Floor)
                  .WhereElementIsNotElementType()
                  .ToElements()):
        point = _centre(floor, ft_to_mm)
        if point is None:
            continue
        found.append((floor.Id, point, _level_name(doc, floor),
                      _type_name(doc, floor)))
    return found


def _apply(doc, plans, findings, finding, context):
    """Create slabs. ``written``. Inside the caller's transaction."""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import footings

    levels = _sheets.levels(doc)
    sizes = _sheets.sizes(context, TYPES_SHEET, findings, finding)
    widths = _beam_widths(context, findings, finding)
    label_parameters = _marks.candidates(context)
    reported = set()
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            if plan.action == placement.MODIFY:
                findings.append(finding(
                    "Info", row.row,
                    "{0!r} is already there as {1}; a slab's outline is its "
                    "geometry, so its type is not changed automatically"
                    .format(row.mark, plan.reason)))
                continue

            level = levels.get(_fold(row.level))
            if level is None:
                findings.append(finding(
                    "Error", row.row,
                    "no level called {0!r} in this model".format(row.level)))
                continue

            size = sizes.get(_fold(row.type_mark)) or {}
            floor_type, note = footings.ensure_named_type(
                doc, row.type_mark, size.get("thickness_mm"), cache)
            if floor_type is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note and note not in reported:
                reported.add(note)
                findings.append(finding("Info", row.row, note))

            corners = _panel(row, widths, reported, findings, finding)
            if corners is None:
                continue

            # The outline is in project coordinates already, so the origin is
            # zero rather than the panel's centre — a rectangle built from two
            # grid intersections is not a shape around a point.
            floor, skipped = footings.create(
                doc, corners, floor_type.Id, level.Id, origin_mm=(0.0, 0.0),
                offset_mm=row.offset_mm or 0.0, mark=row.unique_mark)
            _marks.write(floor, row, label_parameters, reported, findings,
                         finding)
            if skipped:
                findings.append(finding(
                    "Warning", row.row,
                    "{0} edge(s) of {1!r} were too short to draw".format(
                        skipped, row.mark)))
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row, "{0!r}: {1}".format(row.mark, error)))
    return written


def _panel(row, widths, reported, findings, finding):
    """The four corners of one panel, inset per its EdgeRule."""
    from anongee_toolkit.rc_automation import placement

    if row.start_mm is None or row.end_mm is None:
        return None

    rule = _fold(row.edge_rule) or _fold(INNER_FACE)
    if rule == _fold(GRID_LINE):
        inset = (0.0, 0.0, 0.0, 0.0)
    else:
        sign = 1.0 if rule == _fold(INNER_FACE) else -1.0
        inset = tuple(sign * half for half in _insets(row, widths, reported,
                                                      findings, finding))

    corners = placement.rectangle(row.start_mm, row.end_mm, inset)
    if corners is None:
        findings.append(finding(
            "Error", row.row,
            "{0!r} is smaller than the beams around it once inset, so there "
            "is no slab left to draw".format(row.mark)))
    return corners


def _insets(row, widths, reported, findings, finding):
    """``(left, right, bottom, top)`` — half the beam width on each edge.

    Each edge is asked separately. A panel with a 300 floor beam on one side
    and a 230 plinth beam on another is inset differently on those two sides,
    and averaging them would put the slab edge in the wrong place on both.
    """
    edges = (
        ("left", (row.from_grid_x, row.from_grid_y, row.from_grid_x,
                  row.to_grid_y)),
        ("right", (row.to_grid_x, row.from_grid_y, row.to_grid_x,
                   row.to_grid_y)),
        ("bottom", (row.from_grid_x, row.from_grid_y, row.to_grid_x,
                    row.from_grid_y)),
        ("top", (row.from_grid_x, row.to_grid_y, row.to_grid_x,
                 row.to_grid_y)),
    )
    found = []
    missing = []
    for name, span in edges:
        width = widths.get((_fold(row.level),) + tuple(_fold(part)
                                                       for part in span))
        if width is None:
            width = widths.get((_fold(row.level),) + tuple(
                _fold(part) for part in (span[2], span[3], span[0], span[1])))
        if width is None:
            missing.append(name)
            found.append(0.0)
        else:
            found.append(width / 2.0)

    if missing and "no-beam" not in reported:
        reported.add("no-beam")
        findings.append(finding(
            "Info", row.row,
            "{0!r} has no beam on its {1} edge in {2}, so that edge is left "
            "on the grid line. Slabs are inset by half the width of the beam "
            "actually there.".format(row.mark, "/".join(missing),
                                     BEAM_PLACEMENT_SHEET)))
    return tuple(found)


def _beam_widths(context, findings, finding):
    """``{(level, fx, fy, tx, ty): width_mm}`` for every beam in the workbook.

    Read once, because forty panels asking four questions each is a hundred
    and sixty lookups over the same two sheets.
    """
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement

    grid = _sheets.sheet(context, BEAM_PLACEMENT_SHEET)
    if grid is None:
        findings.append(finding(
            "Warning", "",
            "this workbook has no {0} sheet, so slab edges cannot be inset "
            "to the beams and are left on the grid lines".format(
                BEAM_PLACEMENT_SHEET)))
        return {}

    units = (context or {}).get("units", "mm")
    sections, _issues = placement.parse_types(
        _sheets.sheet(context, BEAM_TYPES_SHEET) or [], BEAM_TYPES_SHEET,
        units)
    groups, _beam_issues = placement.parse_beams(grid, BEAM_PLACEMENT_SHEET,
                                                 units)

    widths = {}
    for group in groups:
        for row in group:
            section = sections.get(_fold(row.type_mark)) or {}
            width = section.get("width_mm")
            if not width:
                continue
            widths[(_fold(row.level), _fold(row.from_grid_x),
                    _fold(row.from_grid_y), _fold(row.to_grid_x),
                    _fold(row.to_grid_y))] = width
    return widths


def _centre(floor, ft_to_mm):
    try:
        box = floor.get_BoundingBox(None)
        if box is None:
            return None
        return (ft_to_mm((box.Min.X + box.Max.X) / 2.0),
                ft_to_mm((box.Min.Y + box.Max.Y) / 2.0))
    except Exception:
        return None


def _level_name(doc, element):
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        parameter = element.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if parameter is None:
            return ""
        level = doc.GetElement(parameter.AsElementId())
        return level.Name if level is not None else ""
    except Exception:
        return ""


def _type_name(doc, element):
    try:
        return doc.GetElement(element.GetTypeId()).Name
    except Exception:
        return ""


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
