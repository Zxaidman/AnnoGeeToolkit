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


def ensure_symbol(doc, wanted, width_mm=None, depth_mm=None, cache=None):
    """``(FamilySymbol, note)`` — found, or duplicated and sized to order.

    Four passes, narrowest first — Type Mark, exact name, name containing, and
    finally the **same two dimensions under a different name**, because a
    template holding ``300 X 600`` and a workbook asking for ``B-300x600`` mean
    the same section and duplicating it would fill a model with types that
    already existed.
    """
    from anongee_toolkit.structural import columns

    if cache is None:
        cache = {}
    key = _fold(wanted)
    if key in cache:
        return cache[key], ""

    loaded = symbols(doc)
    if not loaded:
        return None, ("this model has no structural framing family loaded. "
                      "Load one — Concrete-Rectangular Beam is the standard — "
                      "and run this again")

    for _label, _name_, type_mark, symbol_id in loaded:
        if type_mark and _fold(type_mark) == key:
            return _activate(doc, symbol_id, cache, key), ""
    for _label, name, _mark, symbol_id in loaded:
        if _fold(name) == key:
            return _activate(doc, symbol_id, cache, key), ""
    for label, name, _mark, symbol_id in loaded:
        if key and key in _fold(name):
            return (_activate(doc, symbol_id, cache, key),
                    "matched {0!r} to {1}".format(wanted, label))

    size = columns._dimensions(wanted)
    if len(size) == 2:
        for label, name, _mark, symbol_id in loaded:
            if columns._dimensions(name) == size:
                return (_activate(doc, symbol_id, cache, key),
                        "matched {0!r} to {1} - same section, different "
                        "name".format(wanted, label))

    if not width_mm or not depth_mm:
        return None, ("no framing type called {0!r}, and BEAM_TYPES does not "
                      "give it a Width and a Depth, so one cannot be made"
                      .format(wanted))

    base = _base_symbol(doc, loaded)
    try:
        duplicated = base.Duplicate(wanted)
    except Exception as error:
        return None, "could not create a type called {0!r}: {1}".format(
            wanted, error)

    set_width = _set_dimension(duplicated, WIDTH_NAMES, width_mm)
    set_depth = _set_dimension(duplicated, DEPTH_NAMES, depth_mm)
    _set_type_mark(duplicated, wanted)
    _activate_symbol(doc, duplicated)
    cache[key] = duplicated

    if not (set_width and set_depth):
        return duplicated, (
            "created {0!r}, but could not set its size — the family does not "
            "use a parameter this recognises, so it is the size the family "
            "came at".format(wanted))
    return duplicated, "created {0!r} at {1:g} x {2:g}".format(
        wanted, width_mm, depth_mm)


def create(doc, start_mm, end_mm, symbol, level, offset_mm=0.0):
    """Place one beam between two points. **Requires a transaction.**

    The line is drawn at the level's own elevation and the offset is applied
    afterwards through the parameter, rather than by drawing the line higher.
    Revit treats the two differently: a beam drawn high is a beam whose
    reference level is wrong, and every schedule that groups by level says so.
    """
    from Autodesk.Revit.DB import BuiltInParameter, Line, XYZ
    from Autodesk.Revit.DB.Structure import StructuralType
    from anongee_toolkit.revit.units import mm_to_ft

    elevation = level.Elevation
    start = XYZ(mm_to_ft(start_mm[0]), mm_to_ft(start_mm[1]), elevation)
    end = XYZ(mm_to_ft(end_mm[0]), mm_to_ft(end_mm[1]), elevation)
    if start.DistanceTo(end) < mm_to_ft(MINIMUM_SPAN_MM):
        raise ValueError("the two ends are the same point")

    instance = doc.Create.NewFamilyInstance(
        Line.CreateBound(start, end), symbol, level, StructuralType.Beam)

    if offset_mm:
        for built_in in (BuiltInParameter.STRUCTURAL_BEAM_END0_ELEVATION,
                         BuiltInParameter.STRUCTURAL_BEAM_END1_ELEVATION):
            _set(instance, built_in, mm_to_ft(offset_mm))
    return instance


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
