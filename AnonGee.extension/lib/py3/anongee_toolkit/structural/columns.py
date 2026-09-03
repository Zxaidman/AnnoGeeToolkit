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

    # Fourth pass: the same two dimensions, whatever the name around them.
    #
    # A real template holds `300 X 600` and a workbook asks for `S_Col_300x600`.
    # Those are the same section, and duplicating it because the words differ
    # would fill somebody's model with types that already existed. Two numbers
    # matching two numbers is a strong enough claim to make, and it is
    # reported every time it is used so a loose match is never silent.
    wanted_size = _dimensions(wanted)
    if len(wanted_size) == 2:
        for label, name, _type_mark, symbol_id in loaded:
            if _dimensions(name) == wanted_size:
                return (_activate(doc, symbol_id, cache, key),
                        "matched {0!r} to {1} - same section, different "
                        "name".format(wanted, label))

    return None, ("no column type called {0!r}. This model has: {1}".format(
        wanted, ", ".join(label for label, _n, _t, _i in loaded[:8])))


def _dimensions(text):
    """The numbers in a type name, as a tuple. ``"300 X 600"`` -> ``(300, 600)``.

    Order matters and is kept: a 300 x 600 column is not a 600 x 300 one, and
    treating them as the same would turn every column in a frame ninety
    degrees.
    """
    found = []
    digits = ""
    for character in str(text or ""):
        if character.isdigit():
            digits += character
        else:
            if digits:
                found.append(int(digits))
            digits = ""
    if digits:
        found.append(int(digits))
    return tuple(found)


#: What a rectangular column's two dimensions are called, across the families
#: a real project has loaded. Tried in order, and the first that exists and is
#: writable wins.
WIDTH_NAMES = ("b", "Width", "width", "w", "B", "W")
DEPTH_NAMES = ("h", "Depth", "depth", "d", "H", "D")

#: Which loaded family a new type is duplicated from, preferred in this order.
#: A rectangular concrete column is what an RCC schedule means; the standard
#: family is ``M_Concrete-Rectangular-Column`` in a metric template and
#: ``Concrete-Rectangular-Column`` in an imperial one, and both fold to the
#: same thing here.
FAMILY_HINTS = ("concreterectangularcolumn", "rectangularcolumn",
                "concretesquarecolumn", "rectangular", "concrete")


def ensure_symbol(doc, wanted, width_mm=None, depth_mm=None, cache=None,
                  name=None):
    """``(FamilySymbol, note)`` — the house type, found or made.

    *name* is the house name the NAMING sheet renders, and **it is the
    identity** — see :func:`typemaker.choose`. ``find_symbol`` is left as it
    was, because the extraction tool and the diagnostics still ask *does this
    model have a type called X*, which is a different question.

    **Creating a type is not authoring a family.** The family has to be loaded
    already; what this makes is a named, sized type of one that is.

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
        return None, ("this model has no structural column family loaded. "
                      "Load one - Concrete-Rectangular-Column is the standard "
                      "- and run this again")

    index, note = typemaker.choose(loaded, name, wanted)
    if index is not None:
        return _activate(doc, loaded[index][3], cache, key), note

    if not width_mm or not depth_mm:
        return None, ("no column type called {0!r}, and the TYPES sheet does "
                      "not give it a Width and a Depth, so one cannot be "
                      "made".format(name or wanted))

    base, base_note = _base_symbol(doc)
    if base is None:
        return None, base_note

    duplicated, made, note = typemaker.duplicate(
        doc, base, name or wanted, wanted,
        accept=lambda symbol: typemaker.fits(
            symbol, ((WIDTH_NAMES, width_mm), (DEPTH_NAMES, depth_mm))))
    if duplicated is None:
        return None, "no column type called {0!r}, and {1}".format(
            name or wanted, note)

    cache[key] = duplicated
    typemaker.activate(doc, duplicated)

    # Only what was created is sized — sizing a type that already existed edits
    # a type other elements are using. See ``framing.ensure_symbol``.
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


def _base_symbol(doc):
    """The loaded type a new one is duplicated from. ``(symbol, note)``."""
    loaded = symbols(doc)
    if not loaded:
        return None, ("this model has no structural column family loaded. "
                      "Load one — Concrete-Rectangular-Column is the standard "
                      "— and run this again")

    for hint in FAMILY_HINTS:
        for label, _name_, _mark, symbol_id in loaded:
            if hint in _fold(label):
                return doc.GetElement(symbol_id), ""
    return doc.GetElement(loaded[0][3]), ""


def _set_dimension(symbol, names, value_mm):
    """Set the first of these parameters that exists and will take a number."""
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
    try:
        parameter = symbol.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(mark)
    except Exception:
        pass


def _activate_symbol(doc, symbol):
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
    except Exception:
        pass


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
