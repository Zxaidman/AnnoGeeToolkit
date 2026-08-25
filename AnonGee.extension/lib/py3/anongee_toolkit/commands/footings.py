# -*- coding: utf-8 -*-
"""``footings.sync`` — place the pads the FOOTING_PLACEMENT sheet describes.

Mostly already written. RC Automation has been building pads as structural
floors for seven versions and that path is confirmed in a model, so what is new
here is only the front of it: read a placement sheet, resolve a grid
intersection to a point, and hand the rest to
:mod:`anongee_toolkit.structural.footings`.

**A pad is a floor, not a family instance.** That is what lets an arbitrary
outline be drawn — a combined footing, a stepped one, one cut round a pit — and
it is why ``Outline`` exists on the sheet. A blank ``Outline`` means the type is
rectangular and its own Length and Width describe it, which is every footing in
an ordinary job.

Same two promises as every other command: **nothing written unless ``dryRun`` is
off**, and **one undo step**.
"""

__version__ = "0.1.0"

#: Where a pad's size comes from when its row leaves ``Outline`` blank.
TYPES_SHEET = "FOOTING_TYPES"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_FOOTINGS,
        parse=placement.parse_footings,
        span=False,
        existing=_existing,
        apply=_apply,
        what="footing",
        option=envelope_module.option)


def _existing(doc):
    """``[(ElementId, (x, y), level_name, type_name)]`` of the pads already there.

    Foundation slabs only. An ordinary floor is not a footing that somebody
    forgot to mark, and matching against one would have this command decide a
    slab at the same coordinates was the pad it was looking for.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, FilteredElementCollector,
                                   Floor)
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for floor in (FilteredElementCollector(doc)
                  .OfCategory(BuiltInCategory.OST_StructuralFoundation)
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
    """Create pads. ``written``. Inside the caller's transaction."""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import footings

    levels = _levels(doc)
    sizes = _sizes(context, findings, finding)
    label_parameters = _marks.candidates(context)
    reported = set()
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            if plan.action == placement.MODIFY:
                # A pad's outline is its geometry, not a property, so changing
                # its type is the only edit this makes. Anything larger is a
                # delete and a rebuild, and nothing here deletes.
                findings.append(finding(
                    "Info", row.row,
                    "{0!r} is already there as {1}; changing a pad's type is "
                    "not done automatically, because its outline is its "
                    "geometry".format(row.mark, plan.reason)))
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
            if note:
                findings.append(finding("Info", row.row, note))

            points = _outline(row, sizes, findings, finding)
            if points is None:
                continue

            floor, skipped = footings.create(
                doc, points, floor_type.Id, level.Id, origin_mm=row.point_mm,
                rotation_deg=row.rotation_deg or 0.0,
                offset_mm=row.top_offset_mm or 0.0, mark=row.unique_mark)
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


def _outline(row, sizes, findings, finding):
    """The pad's corners in millimetres, local to its own centre.

    An ``Outline`` on the row wins, because a row that bothered to draw one
    means it. Otherwise the type's own Length and Width make a rectangle —
    which is every footing in an ordinary job, and is why the column is blank
    fifteen times out of fifteen in the sample.
    """
    if row.outline:
        points = _parse_outline(row.outline)
        if points is None:
            findings.append(finding(
                "Error", row.row,
                "{0!r} has an outline this cannot read. Corners are "
                "'x,y; x,y; x,y', in the workbook's unit.".format(row.mark)))
            return None
        return points

    size = sizes.get(_fold(row.type_mark))
    if size is None:
        findings.append(finding(
            "Error", row.row,
            "{0!r} has no outline, and {1} does not give {2!r} a Length "
            "and a Width".format(row.mark, TYPES_SHEET, row.type_mark)))
        return None
    half_length = size["length_mm"] / 2.0
    half_width = size["width_mm"] / 2.0
    return [(-half_length, -half_width), (half_length, -half_width),
            (half_length, half_width), (-half_length, half_width)]


def _parse_outline(text):
    """``[(x, y)]`` from ``"0,0; 2400,0; 2400,2400"``, or ``None``."""
    points = []
    for part in str(text).replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.replace("(", "").replace(")", "").split(",")
        if len(bits) != 2:
            return None
        try:
            points.append((float(bits[0]), float(bits[1])))
        except ValueError:
            return None
    return points if len(points) >= 3 else None


def _sizes(context, findings, finding):
    """``{folded type mark: {length_mm, width_mm, thickness_mm}}``.

    From FOOTING_TYPES, read out of the same workbook the placement sheet came
    from. A placement row names a type; the type says how big it is. Fifteen
    footings, three sizes, and a row that stays readable.
    """
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.bridge import envelope as envelope_module

    sheets = (context or {}).get("sheets") or {}
    grid = None
    for name, values in sheets.items():
        if _fold(name) == _fold(TYPES_SHEET):
            grid = values
            break
    if grid is None:
        findings.append(finding(
            "Warning", "",
            "this workbook has no {0} sheet, so a row with no Outline has "
            "nothing to say how big its pad is".format(TYPES_SHEET)))
        return {}

    found, issues = placement.parse_types(
        grid, TYPES_SHEET, (context or {}).get("units", "mm"))
    for item in envelope_module.findings_from_issues(issues):
        findings.append(item)

    usable = {}
    for mark, sizes in found.items():
        if sizes.get("length_mm") and sizes.get("width_mm"):
            usable[mark] = sizes
    return usable


def _levels(doc):
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    found = {}
    for level in FilteredElementCollector(doc).OfClass(Level).ToElements():
        try:
            found[_fold(level.Name)] = level
        except Exception:
            continue
    return found


def _centre(floor, ft_to_mm):
    """The middle of a pad's bounding box, in millimetres, or ``None``."""
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
