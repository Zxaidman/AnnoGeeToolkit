# -*- coding: utf-8 -*-
"""Place structural framing — beams. Writes, inside a caller's transaction.

The same shape as :mod:`columns`, and thin for the same reason: where a beam
goes was settled in :mod:`anongee_toolkit.rc_automation.placement`, which has no
Revit in it. What is left is which family type is which, and what
``NewFamilyInstance`` wants from a line.

**A beam is placed per span, and a continuous beam is several of them.** That is
not a simplification — it is how Revit models one. A four-span beam is four
members that join; the workbook's grouping gives them one schedule mark, which
is the thing that was actually missing.

**Joins and cutbacks are not done here.** Revit's automatic joins do most of it,
and the rest is a per-project judgement about which member runs through. Placing
them correctly and leaving the joins alone is honest; guessing at them and being
wrong on a corner is not.
"""

__version__ = "0.1.0"

#: A rectangular beam's two dimensions, across the families a real project has.
WIDTH_NAMES = ("b", "Width", "width", "w", "B", "W")
DEPTH_NAMES = ("h", "Depth", "depth", "d", "H", "D")

#: Which loaded family a new type is duplicated from, preferred in this order.
FAMILY_HINTS = ("concreterectangularbeam", "rectangularbeam", "rectangular",
                "concrete")

#: A beam shorter than this is a mistake in the sheet, not a beam.
MINIMUM_SPAN_MM = 50.0


def symbols(doc):
    """``[(label, name, type_mark, ElementId)]`` of loaded framing types."""
    from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,
                                   FamilySymbol, FilteredElementCollector)
    found = []
    for symbol in (FilteredElementCollector(doc)
                   .OfCategory(BuiltInCategory.OST_StructuralFraming)
                   .OfClass(FamilySymbol)
                   .ToElements()):
        family = ""
        try:
            family = symbol.Family.Name if symbol.Family else ""
        except Exception:
            pass
        name = _name(symbol)
        found.append(("{0} : {1}".format(family, name), name,
                      _parameter(symbol, BuiltInParameter.ALL_MODEL_TYPE_MARK),
                      symbol.Id))
    return sorted(found, key=lambda item: item[0])


def ensure_symbol(doc, wanted, width_mm=None, depth_mm=None, cache=None,
                  name=None):
    """``(FamilySymbol, note)`` — the house type, found or made.

    *name* is the house name the NAMING sheet renders, and **it is the
    identity**: a beam is ``CH-230 X 600``, not whatever the template happens to
    call a 230 x 600 section. See :func:`typemaker.choose` for why that reversed.

    Requires a transaction when it has to create — the caller has one open.
    """
    from anongee_toolkit.structural import typemaker

    if cache is None:
        cache = {}
    key = _fold(name or wanted)
    if key in cache:
        return cache[key], ""

    loaded = symbols(doc)
    if not loaded:
        return None, ("this model has no structural framing family loaded. "
                      "Load one - Concrete-Rectangular Beam is the standard - "
                      "and run this again")

    index, note = typemaker.choose(loaded, name, wanted)
    if index is not None:
        return _activate(doc, loaded[index][3], cache, key), note

    if not width_mm or not depth_mm:
        return None, ("no framing type called {0!r}, and BEAM_TYPES does not "
                      "give it a Width and a Depth, so one cannot be made"
                      .format(name or wanted))

    base = _base_symbol(doc, loaded)
    duplicated, made, note = typemaker.duplicate(
        doc, base, name or wanted, wanted,
        accept=lambda symbol: typemaker.fits(
            symbol, ((WIDTH_NAMES, width_mm), (DEPTH_NAMES, depth_mm))))
    if duplicated is None:
        return None, "no framing type called {0!r}, and {1}".format(
            name or wanted, note)

    cache[key] = duplicated
    typemaker.activate(doc, duplicated)

    # **Only what was created is sized.** Sizing a type that already existed
    # edits a type other elements are using: a run asking for 230 x 600 was
    # handed the existing PB-230x450, set its depth to 600, and every plinth
    # beam in the model became 600 deep. The run reported success.
    if not made:
        return duplicated, note

    set_width, set_depth = typemaker.size(duplicated, WIDTH_NAMES, width_mm,
                                          DEPTH_NAMES, depth_mm)
    typemaker.set_type_mark(duplicated, wanted)

    built = "created {0!r} at {1:g} x {2:g}".format(name or wanted, width_mm,
                                                    depth_mm)
    if note:
        built = "{0} - {1}".format(built, note)
    if not (set_width and set_depth):
        return duplicated, (
            "{0}, but could not set its {1}: the family does not use a "
            "parameter this recognises ({2} / {3}), so the type is the size "
            "the family came at".format(
                built, "size" if not (set_width or set_depth)
                else ("width" if not set_width else "depth"),
                ", ".join(WIDTH_NAMES), ", ".join(DEPTH_NAMES)))
    return duplicated, built


def create(doc, start_mm, end_mm, symbol, level, offset_mm=0.0,
           cutback_mm=(0.0, 0.0), disallow_joins=True):
    """Place one beam between two points. **Requires a transaction.**

    The line is drawn at the level's own elevation and the offset applied
    through the parameter, not by drawing the line higher: a beam drawn high is
    a beam whose reference level is wrong, and every schedule that groups by
    level says so.

    *cutback_mm* is ``(start, end)`` — how far to pull each end back from the
    point given, so the beam stops at the **column face** rather than running
    through the column's centre. A grid intersection is where a column stands,
    not where a beam ends.

    *disallow_joins* is on by default. Revit's automatic join extends a beam
    into whatever it meets, so a beam already cut back to the face would be
    quietly pushed through the column again.
    """
    from Autodesk.Revit.DB import Line, XYZ
    from Autodesk.Revit.DB.Structure import StructuralFramingUtils
    from Autodesk.Revit.DB.Structure import StructuralType
    from anongee_toolkit.revit.units import mm_to_ft

    trimmed_start, trimmed_end = _trim(start_mm, end_mm, cutback_mm)
    elevation = level.Elevation
    start = XYZ(mm_to_ft(trimmed_start[0]), mm_to_ft(trimmed_start[1]),
                elevation)
    end = XYZ(mm_to_ft(trimmed_end[0]), mm_to_ft(trimmed_end[1]), elevation)
    if start.DistanceTo(end) < mm_to_ft(MINIMUM_SPAN_MM):
        raise ValueError("nothing is left of this beam once it is cut back to "
                         "the column faces")

    instance = doc.Create.NewFamilyInstance(
        Line.CreateBound(start, end), symbol, level, StructuralType.Beam)

    _state_the_justification(instance, offset_mm)

    if disallow_joins:
        for end_index in (0, 1):
            try:
                StructuralFramingUtils.DisallowJoinAtEnd(instance, end_index)
            except Exception:
                pass
    return instance


def _trim(start_mm, end_mm, cutback_mm):
    """Pull each end in along the beam's own direction. ``(start, end)``."""
    dx = end_mm[0] - start_mm[0]
    dy = end_mm[1] - start_mm[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return start_mm, end_mm

    unit = (dx / length, dy / length)
    at_start, at_end = cutback_mm[0] or 0.0, cutback_mm[1] or 0.0
    if at_start + at_end >= length:
        return start_mm, end_mm

    return ((start_mm[0] + unit[0] * at_start,
             start_mm[1] + unit[1] * at_start),
            (end_mm[0] - unit[0] * at_end,
             end_mm[1] - unit[1] * at_end))


def _state_the_justification(instance, offset_mm):
    """Say where the beam sits in its own section, rather than inheriting it.

    ``NewFamilyInstance`` gives a beam whatever the family and the **last
    placement** left behind. A real run arrived with ``z Offset Value`` of
    −1500 — the foundation level, from somewhere else entirely in the model,
    carried into ninety beams because nothing said otherwise.

    So every one of these is stated. Anything a run does not set is a value
    somebody else chose, and on a family instance that is most of them.
    """
    from Autodesk.Revit.DB import BuiltInParameter
    from anongee_toolkit.revit.units import mm_to_ft

    _set(instance, BuiltInParameter.YZ_JUSTIFICATION, 0)        # Uniform
    _set(instance, BuiltInParameter.Y_JUSTIFICATION, 2)         # Origin
    _set(instance, BuiltInParameter.Y_OFFSET_VALUE, 0.0)
    _set(instance, BuiltInParameter.Z_JUSTIFICATION, 0)         # Top
    _set(instance, BuiltInParameter.Z_OFFSET_VALUE, 0.0)

    # The sheet's Offset drops the whole beam, which is what the level offsets
    # are for. The z offset above moves it within its own section, which is a
    # different thing and is not what a schedule means by "offset".
    for built_in in (BuiltInParameter.STRUCTURAL_BEAM_END0_ELEVATION,
                     BuiltInParameter.STRUCTURAL_BEAM_END1_ELEVATION):
        _set(instance, built_in, mm_to_ft(offset_mm or 0.0))


def placed(doc):
    """``[(ElementId, (x, y), level_name, type_name)]`` of the beams there now.

    Keyed on the **midpoint**, which is what the planner matches against: two
    beams sharing a midpoint on one level are the same beam, and two that do
    not are not.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, FamilyInstance,
                                   FilteredElementCollector)
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for instance in (FilteredElementCollector(doc)
                     .OfCategory(BuiltInCategory.OST_StructuralFraming)
                     .OfClass(FamilyInstance)
                     .WhereElementIsNotElementType()
                     .ToElements()):
        point = _midpoint(instance, ft_to_mm)
        if point is None:
            continue
        found.append((instance.Id, point, _level_name(doc, instance),
                      _type_name(doc, instance)))
    return found


def set_type(doc, instance, symbol):
    try:
        instance.Symbol = symbol
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The small Revit awkwardnesses
# ---------------------------------------------------------------------------

def _midpoint(instance, ft_to_mm):
    try:
        curve = instance.Location.Curve
        start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
    except Exception:
        return None
    return (ft_to_mm((start.X + end.X) / 2.0),
            ft_to_mm((start.Y + end.Y) / 2.0))


def _base_symbol(doc, loaded):
    for hint in FAMILY_HINTS:
        for label, _name_, _mark, symbol_id in loaded:
            if hint in _fold(label):
                return doc.GetElement(symbol_id)
    return doc.GetElement(loaded[0][3])


def _activate(doc, symbol_id, cache, key):
    symbol = doc.GetElement(symbol_id)
    _activate_symbol(doc, symbol)
    cache[key] = symbol
    return symbol


def _activate_symbol(doc, symbol):
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
    except Exception:
        pass


def _set_dimension(symbol, names, value_mm):
    from anongee_toolkit.revit.units import mm_to_ft
    for name in names:
        try:
            parameter = symbol.LookupParameter(name)
            if parameter is None or parameter.IsReadOnly:
                continue
            if parameter.Set(mm_to_ft(value_mm)):
                return True
        except Exception:
            continue
    return False


def _set_type_mark(symbol, mark):
    from Autodesk.Revit.DB import BuiltInParameter
    _set(symbol, BuiltInParameter.ALL_MODEL_TYPE_MARK, mark)


def _set(element, built_in, value):
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value)
            return True
    except Exception:
        pass
    return False


def _parameter(element, built_in):
    try:
        parameter = element.get_Parameter(built_in)
        return (parameter.AsString() or "") if parameter is not None else ""
    except Exception:
        return ""


def _level_name(doc, instance):
    from Autodesk.Revit.DB import BuiltInParameter
    for built_in in (BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
                     BuiltInParameter.FAMILY_LEVEL_PARAM,
                     BuiltInParameter.SCHEDULE_LEVEL_PARAM):
        try:
            parameter = instance.get_Parameter(built_in)
            if parameter is None:
                continue
            level = doc.GetElement(parameter.AsElementId())
            if level is not None:
                return _name(level)
        except Exception:
            continue
    return ""


def _type_name(doc, instance):
    try:
        return _name(doc.GetElement(instance.GetTypeId()))
    except Exception:
        return ""


def _name(element):
    try:
        return element.Name
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)
    except Exception:
        return ""


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
