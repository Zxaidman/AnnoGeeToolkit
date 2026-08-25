# -*- coding: utf-8 -*-
"""``columns.sync`` — place the columns the COLUMN_PLACEMENT sheet describes.

The first command that puts a family instance in a model, and the shape every
structural command after it follows: read the sheet, ask the model where its
grids are, decide in :mod:`rc_automation.placement`, then write.

**A second run must report `matched` and nothing else.** That is the acceptance
test, not the first one — anything can create. The match is on **position and
storey**, never on the mark, because the owner's marking rule repeats a mark up
a stack and across a floor on purpose.

**One undo step**, a ``TransactionGroup`` this command owns. **Nothing written
unless ``dryRun`` is off**, and a dry run reports exactly what a real one would
do.
"""

__version__ = "0.1.0"

#: Where a column's section comes from when the model does not have the type.
TYPES_SHEET = "COLUMN_TYPES"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_COLUMNS,
        parse=placement.parse_columns,
        span=True,
        existing=_existing,
        apply=_apply,
        what="column",
        option=envelope_module.option)


def _existing(doc):
    from anongee_toolkit.structural import columns
    return columns.placed(doc)


def _apply(doc, plans, findings, finding, context):
    """Create and retype columns. ``written``.

    Called inside the transaction :mod:`_placement` owns, so it opens none of
    its own — one undo step is the promise and two transactions would break it.
    """
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import columns

    levels = _levels(doc)
    sizes = _sizes(context, findings, finding)
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            size = sizes.get(_fold(row.type_mark)) or {}
            symbol, note = columns.ensure_symbol(
                doc, row.type_mark, size.get("width_mm"),
                size.get("depth_mm"), cache)
            if symbol is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note:
                findings.append(finding("Info", row.row, note))

            if plan.action == placement.MODIFY:
                instance = doc.GetElement(plan.existing)
                if instance is None:
                    findings.append(finding(
                        "Error", row.row,
                        "{0!r} vanished between planning and writing".format(
                            row.mark)))
                    continue
                if columns.set_type(doc, instance, symbol):
                    written += 1
                else:
                    findings.append(finding(
                        "Warning", row.row,
                        "{0!r} is there but Revit would not change its type "
                        "to {1}".format(row.mark, row.type_mark)))
                continue

            base = levels.get(_fold(row.base_level))
            if base is None:
                findings.append(finding(
                    "Error", row.row,
                    "no level called {0!r} in this model".format(
                        row.base_level)))
                continue
            top = levels.get(_fold(row.top_level)) if row.top_level else None
            if row.top_level and top is None:
                findings.append(finding(
                    "Warning", row.row,
                    "no level called {0!r}; the column was placed on {1} and "
                    "its top was left as the family sets it".format(
                        row.top_level, row.base_level)))

            instance = columns.create(
                doc, row.point_mm, symbol, base, top,
                row.base_offset_mm, row.top_offset_mm)
            _mark(instance, row.mark)
            _rotate(doc, instance, row)
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row, "{0!r}: {1}".format(row.mark, error)))
    return written


def _sizes(context, findings, finding):
    """``{folded type mark: {width_mm, depth_mm}}`` from COLUMN_TYPES.

    A placement row names a type; the type sheet says how big it is. That is
    what lets a missing type be *made* rather than refused — without a size
    there is nothing to make.
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
            "this workbook has no {0} sheet, so a type the model does not "
            "have cannot be created".format(TYPES_SHEET)))
        return {}

    found, issues = placement.parse_types(
        grid, TYPES_SHEET, (context or {}).get("units", "mm"))
    for item in envelope_module.findings_from_issues(issues):
        findings.append(item)
    return found


def _levels(doc):
    """``{folded name: Level}``."""
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    found = {}
    for level in FilteredElementCollector(doc).OfClass(Level).ToElements():
        try:
            found[_fold(level.Name)] = level
        except Exception:
            continue
    return found


def _mark(instance, mark):
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(mark or "")
    except Exception:
        pass


def _rotate(doc, instance, row):
    """Turn a column about its own vertical axis, when the sheet asked."""
    if not row.rotation_deg:
        return
    import math
    from Autodesk.Revit.DB import ElementTransformUtils, Line, XYZ
    from anongee_toolkit.revit.units import mm_to_ft
    try:
        point = XYZ(mm_to_ft(row.point_mm[0]), mm_to_ft(row.point_mm[1]), 0.0)
        axis = Line.CreateUnbound(point, XYZ.BasisZ)
        ElementTransformUtils.RotateElement(
            doc, instance.Id, axis, math.radians(row.rotation_deg))
    except Exception:
        pass


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
