# -*- coding: utf-8 -*-
"""An RC stair built out of primitives. Writes — inside a caller's transaction.

**This is option B, and it is a proposal rather than a settled design.** The
project owner asked to see it working before choosing between this and a real
Revit ``Stair`` element, so what follows is written to be judged.

The claim it makes: an RCC stair is a **waist slab with triangular steps on
it**, and both of those are shapes this repository can already place, size,
schedule and — later — put rebar in. So:

* the **waist** is a slanted structural framing member whose section is the
  stair's width by the waist thickness. That is not a trick. A beam's section
  is swept perpendicular to its curve, which is exactly how a waist slab's
  thickness is measured, so the volume is right rather than nearly right;
* the **steps** are one ``DirectShape`` per flight holding a triangular prism
  per tread. Triangular, because a step modelled as a box doubles every step in
  the building's concrete.

**What it costs, and the owner should weigh this.** The waist is a structural
framing instance, so it appears in Structural Framing schedules beside the
beams and has to be filtered out of them. It carries ``STAIR WAIST`` in its
comments so that filter is one condition, but the pollution is real and it is
the strongest argument for the other option.

**What it buys.** Exact quantities, a sheet that drives it, idempotence, and a
waist that is a real structural element a rebar run can host on. A Revit
``Stair`` gives none of those without a fight.
"""

__version__ = "0.1.0"

#: What the waist carries so a beam schedule can exclude it in one condition.
WAIST_COMMENT = "STAIR WAIST"
STEPS_COMMENT = "STAIR STEPS"

#: The steps carry the stair's mark with this on the end.
#:
#: The **waist** carries the mark itself, written by ``commands/_marks`` like
#: every other placed element — it is the element a second run matches, so it
#: has to look like one. An earlier version wrote ``-WAIST`` here as well and
#: ``_marks.write`` immediately overwrote it, which left a constant in this
#: file describing something that was never in the model.
STEPS_SUFFIX = "-STEPS"

#: The waist's section, in the parameters the rectangular families use.
WIDTH_NAMES = ("b", "Width", "width", "w", "B", "W")
DEPTH_NAMES = ("h", "Depth", "depth", "d", "H", "D")


def ensure_waist_symbol(doc, wanted, width_mm, waist_mm, cache=None,
                        name=None):
    """The framing type a waist is cut from. ``(FamilySymbol, note)``.

    Deliberately the beam path — a 1200 x 150 section is a 1200 x 150 section,
    and giving stairs their own copy of type-finding is how the copies start to
    differ.
    """
    from anongee_toolkit.structural import framing
    return framing.ensure_symbol(doc, wanted, width_mm, waist_mm, cache,
                                 name=name)


def create(doc, start_mm, direction, base_level, flight, symbol, mark="",
           base_offset_mm=0.0):
    """Build one flight. ``(waist, steps, note)``. **Requires a transaction.**

    *start_mm* is where the bottom of the flight stands, *direction* the unit
    vector it climbs along in plan, and *flight* a solved
    :class:`rc_automation.flight.Flight`.
    """
    from Autodesk.Revit.DB import Line, XYZ
    from Autodesk.Revit.DB.Structure import StructuralFramingUtils
    from Autodesk.Revit.DB.Structure import StructuralType
    from anongee_toolkit.revit.units import mm_to_ft

    base = base_level.Elevation + mm_to_ft(base_offset_mm or 0.0)

    # The waist's top line: from the foot of the first riser to the last
    # internal corner, which is one riser below the floor above. The final
    # riser closes that gap against the slab and has no tread of its own.
    foot = XYZ(mm_to_ft(start_mm[0]), mm_to_ft(start_mm[1]), base)
    head = XYZ(mm_to_ft(start_mm[0] + direction[0] * flight.run_mm),
               mm_to_ft(start_mm[1] + direction[1] * flight.run_mm),
               base + mm_to_ft(flight.waist_top_rise_mm))

    waist = doc.Create.NewFamilyInstance(
        Line.CreateBound(foot, head), symbol, base_level, StructuralType.Beam)
    _state_the_justification(waist)
    for end in (0, 1):
        try:
            StructuralFramingUtils.DisallowJoinAtEnd(waist, end)
        except Exception:
            pass
    _set_string(waist, "ALL_MODEL_INSTANCE_COMMENTS", WAIST_COMMENT)
    # The waist's Mark is written by the caller through ``_marks``, the same
    # way every other placed element's is.

    steps, note = _steps(doc, start_mm, direction, base, flight, mark)
    return waist, steps, note


def _steps(doc, start_mm, direction, base_elevation_ft, flight, mark):
    """One ``DirectShape`` holding a triangular prism per tread.

    A single element rather than nineteen, because nineteen elements per flight
    is a browser nobody can read and nineteen rows in every schedule. The
    volume is written onto it, since a ``DirectShape`` does not compute one.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, CurveLoop, DirectShape,
                                   ElementId, GeometryCreationUtilities, Line,
                                   XYZ)
    from System.Collections.Generic import List
    from anongee_toolkit.revit.units import mm_to_ft

    # Across the flight, in plan. The line runs down the middle of the stair,
    # so the prisms start half a width to one side.
    across = (-direction[1], direction[0])
    half = flight.width_mm / 2.0

    solids = List[object]()
    made = 0
    for along0, up0, along1, up1 in flight.steps_mm():
        try:
            corners = []
            for along, up in ((along0, up0), (along1, up1), (along0, up1)):
                corners.append(XYZ(
                    mm_to_ft(start_mm[0] + direction[0] * along
                             + across[0] * -half),
                    mm_to_ft(start_mm[1] + direction[1] * along
                             + across[1] * -half),
                    base_elevation_ft + mm_to_ft(up)))

            loop = CurveLoop()
            for index in range(3):
                loop.Append(Line.CreateBound(corners[index],
                                             corners[(index + 1) % 3]))

            loops = List[CurveLoop]()
            loops.Add(loop)
            solids.Add(GeometryCreationUtilities.CreateExtrusionGeometry(
                loops, XYZ(across[0], across[1], 0.0),
                mm_to_ft(flight.width_mm)))
            made += 1
        except Exception:
            continue

    if not made:
        return None, "the steps could not be built as geometry"

    shape = DirectShape.CreateElement(
        doc, ElementId(BuiltInCategory.OST_Stairs))
    shape.SetShape(solids)
    _set_string(shape, "ALL_MODEL_INSTANCE_COMMENTS", STEPS_COMMENT)
    _set_string(shape, "ALL_MODEL_MARK", mark + STEPS_SUFFIX if mark else "")

    note = ""
    if made != flight.treads:
        note = "{0} of {1} steps could be built".format(made, flight.treads)
    return shape, note


def _state_the_justification(instance):
    """The section hangs **below** the line, because the line is the waist's
    top — the surface the steps sit on.

    Stated rather than inherited, for the reason BUG-29 established: a family
    instance arrives carrying whatever the family and the last placement left
    behind, and a waist that inherits a −1500 offset is a staircase in the
    basement.
    """
    from Autodesk.Revit.DB import BuiltInParameter
    _set(instance, BuiltInParameter.YZ_JUSTIFICATION, 0)        # Uniform
    _set(instance, BuiltInParameter.Y_JUSTIFICATION, 2)         # Origin
    _set(instance, BuiltInParameter.Y_OFFSET_VALUE, 0.0)
    _set(instance, BuiltInParameter.Z_JUSTIFICATION, 0)         # Top
    _set(instance, BuiltInParameter.Z_OFFSET_VALUE, 0.0)
    for built_in in (BuiltInParameter.STRUCTURAL_BEAM_END0_ELEVATION,
                     BuiltInParameter.STRUCTURAL_BEAM_END1_ELEVATION):
        _set(instance, built_in, 0.0)


def placed(doc):
    """``[(ElementId, (x, y), level_name, type_name)]`` of the waists there now.

    Only the waists. They are what a second run matches against — the steps
    belong to a waist and are found through it, which is why they carry the
    same mark with a different suffix.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,
                                   FamilyInstance, FilteredElementCollector)
    from anongee_toolkit.revit.units import ft_to_mm

    found = []
    for instance in (FilteredElementCollector(doc)
                     .OfCategory(BuiltInCategory.OST_StructuralFraming)
                     .OfClass(FamilyInstance)
                     .WhereElementIsNotElementType()
                     .ToElements()):
        if _string(instance, BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS) \
                != WAIST_COMMENT:
            continue
        try:
            curve = instance.Location.Curve
            start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
        except Exception:
            continue
        found.append((instance.Id,
                      (ft_to_mm((start.X + end.X) / 2.0),
                       ft_to_mm((start.Y + end.Y) / 2.0)),
                      _level_name(doc, instance), _type_name(doc, instance)))
    return found


def steps_by_mark(doc):
    """``{mark: ElementId}`` of the step solids already in the model.

    So a second run recognises the steps it made rather than adding another
    nineteen prisms on top of them. A ``DirectShape`` has no geometry a planner
    can match on, so the mark is the only handle — which is exactly why it is
    written.
    """
    from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,
                                   DirectShape, FilteredElementCollector)
    found = {}
    for shape in (FilteredElementCollector(doc)
                  .OfCategory(BuiltInCategory.OST_Stairs)
                  .OfClass(DirectShape)
                  .WhereElementIsNotElementType()
                  .ToElements()):
        mark = _string(shape, BuiltInParameter.ALL_MODEL_MARK)
        if mark:
            found[mark] = shape.Id
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

def _set(element, built_in, value):
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value)
            return True
    except Exception:
        pass
    return False


def _set_string(element, built_in_name, value):
    from Autodesk.Revit.DB import BuiltInParameter
    built_in = getattr(BuiltInParameter, built_in_name, None)
    if built_in is None or not value:
        return False
    return _set(element, built_in, value)


def _string(element, built_in):
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is None:
            return ""
        return parameter.AsString() or ""
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
