# -*- coding: utf-8 -*-
"""Reading the other sheets a placement command needs, and the model's levels.

A placement row names a type; a TYPES sheet says how big it is. Three commands
now need that lookup and one of them needed it twice, so it lives here rather
than being copied a fourth time — which is where the copies start to differ.
"""

__version__ = "0.1.0"


def sizes(context, sheet_name, findings, finding):
    """``{folded type mark: {length_mm, width_mm, depth_mm, thickness_mm}}``.

    From the named TYPES sheet in the same workbook the placement sheet came
    from. This is what lets a type the model does not have be **made** rather
    than refused — without a size there is nothing to make.
    """
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.rc_automation import placement

    grid = sheet(context, sheet_name)
    if grid is None:
        findings.append(finding(
            "Warning", "",
            "this workbook has no {0} sheet, so a type the model does not "
            "have cannot be created".format(sheet_name)))
        return {}

    found, issues = placement.parse_types(
        grid, sheet_name, (context or {}).get("units", "mm"))
    for item in envelope_module.findings_from_issues(issues):
        findings.append(item)
    return found


def sheet(context, wanted):
    """One sheet out of the workbook the job named, matched the way a person
    would spell it. ``None`` when it is not there."""
    sheets = (context or {}).get("sheets") or {}
    for name, values in sheets.items():
        if fold(name) == fold(wanted):
            return values
    return None


def levels(doc):
    """``{folded name: Level}`` — the model's levels, by name.

    Name is what a workbook has to write to reach a level, and matching is
    exact but for case and spacing. Everything upstream refuses to rename one
    without being asked, so the names in the sheet are the names in the model.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    found = {}
    for level in FilteredElementCollector(doc).OfClass(Level).ToElements():
        try:
            found[fold(level.Name)] = level
        except Exception:
            continue
    return found


def fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
