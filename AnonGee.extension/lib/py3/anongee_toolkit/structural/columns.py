# -*- coding: utf-8 -*-
"""Place structural columns. Writes — inside a caller's transaction.

Thin on purpose: everything about *where* and *whether* was settled in
:mod:`anongee_toolkit.rc_automation.placement`, which has no Revit in it. What
is left here is the part only Revit can answer — which family type is which, and
what ``NewFamilyInstance`` wants.

**A type is found, never invented.** The workbook names a type mark; this looks
for a loaded symbol whose name or Type Mark matches, and reports what it has if
it cannot find one. Authoring a family from a spreadsheet is not on the table,
and a run that silently placed the wrong section would be worse than one that
stopped.
"""

__version__ = "0.1.0"


def symbols(doc):
    """``[(label, name, type_mark, ElementId)]`` of loaded column types."""
    from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,
                                   FamilySymbol, FilteredElementCollector)
    found = []
    for symbol in (FilteredElementCollector(doc)
                   .OfCategory(BuiltInCategory.OST_StructuralColumns)
                   .OfClass(FamilySymbol)
                   .ToElements()):
        name = _name(symbol)
        family = ""
        try:
            family = symbol.Family.Name if symbol.Family else ""
        except Exception:
            pass
        found.append(("{0} : {1}".format(family, name), name,
                      _parameter(symbol, BuiltInParameter.ALL_MODEL_TYPE_MARK),
                      symbol.Id))
    return sorted(found, key=lambda item: item[0])


def find_symbol(doc, wanted, cache=None):
    """``(FamilySymbol, note)`` for a type mark. ``(None, why not)`` if absent.

    Three passes, narrowest first: the Type Mark parameter, then the type name,
    then the type name containing it. The third is what makes ``C-300x600``
    match a symbol somebody loaded as ``C-300x600 Ground``, and it is reported
    when it happens so a loose match is never silent.
    """
    if cache is None:
        cache = {}
    key = _fold(wanted)
    if key in cache:
        return cache[key], ""

    loaded = symbols(doc)
    if not loaded:
        return None, ("this model has no structural column family loaded, so "
                      "there is nothing to place")

    for _label, _name, type_mark, symbol_id in loaded:
        if type_mark and _fold(type_mark) == key:
            return _activate(doc, symbol_id, cache, key), ""

    for _label, name, _type_mark, symbol_id in loaded:
        if _fold(name) == key:
            return _activate(doc, symbol_id, cache, key), ""

    for label, name, _type_mark, symbol_id in loaded:
        if key and key in _fold(name):
            return (_activate(doc, symbol_id, cache, key),
                    "matched {0!r} to {1}".format(wanted, label))

    return None, ("no column type called {0!r}. This model has: {1}".format(
        wanted, ", ".join(label for label, _n, _t, _i in loaded[:8])))


def create(doc, point_mm, symbol, base_level, top_level=None,
           base_offset_mm=0.0, top_offset_mm=0.0):
    """Place one column. **Requires a transaction the caller opened.**

    The point is where the column stands; its height comes from the two levels,
    never from the point. A column with no top level is left at whatever height
    the family gives it and reported by the caller — silently making one up is
    how a model ends up full of columns that stop halfway.
    """
    from Autodesk.Revit.DB import BuiltInParameter, XYZ
    from Autodesk.Revit.DB.Structure import StructuralType
    from anongee_toolkit.revit.units import mm_to_ft

    point = XYZ(mm_to_ft(point_mm[0]), mm_to_ft(point_mm[1]),
                base_level.Elevation)
    instance = doc.Create.NewFamilyInstance(point, symbol, base_level,
                                            StructuralType.Column)

    if top_level is not None:
        _set(instance, BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, top_level.Id)
    _set(instance, BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
         mm_to_ft(base_offset_mm or 0.0))
    _set(instance, BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM,
         mm_to_ft(top_offset_mm or 0.0))
    return instance


def placed(doc):
    """``[(ElementId, (x, y), level_name, type_name)]`` of what is already there.

    The shape :func:`placement.plan` matches against. Anything whose position
    cannot be read is skipped rather than guessed at — an element with no
    location point is not a column standing somewhere, whatever else it is.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, FilteredElementCollector,
                                   FamilyInstance)
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for instance in (FilteredElementCollector(doc)
                     .OfCategory(BuiltInCategory.OST_StructuralColumns)
                     .OfClass(FamilyInstance)
                     .WhereElementIsNotElementType()
                     .ToElements()):
        try:
            location = instance.Location.Point
        except Exception:
            continue
        found.append((instance.Id,
                      (ft_to_mm(location.X), ft_to_mm(location.Y)),
                      _level_name(doc, instance), _type_name(doc, instance)))
    return found


def set_type(doc, instance, symbol):
    """Change a placed column's type. True when it took."""
    try:
        instance.Symbol = symbol
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The small Revit awkwardnesses, in one place
# ---------------------------------------------------------------------------

def _activate(doc, symbol_id, cache, key):
    symbol = doc.GetElement(symbol_id)
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
    except Exception:
        pass
    cache[key] = symbol
    return symbol


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


def _parameter(element, built_in):
    try:
        parameter = element.get_Parameter(built_in)
        return parameter.AsString() or "" if parameter is not None else ""
    except Exception:
        return ""


def _set(element, built_in, value):
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value)
            return True
    except Exception:
        pass
    return False


def _level_name(doc, instance):
    from Autodesk.Revit.DB import BuiltInParameter
    for built_in in (BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                     BuiltInParameter.SCHEDULE_BASE_LEVEL_PARAM):
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


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
