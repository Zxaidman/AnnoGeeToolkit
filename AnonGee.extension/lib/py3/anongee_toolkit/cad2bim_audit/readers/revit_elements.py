# -*- coding: utf-8 -*-
"""Stage C: what is actually in the model.

A whole-document sweep of the structural categories, which is correct when
cad2bim is run into a fresh test model -- the workflow this audit is built for.
It is deliberately NOT filtered to "elements cad2bim made": every filter that
could express that is wrong in a way that hides exactly the bug you are hunting.
Filtering by type name misses anything placed under a pre-existing type;
filtering by an element-id watermark breaks the moment the audit runs in a later
session than the build. An unfiltered sweep can over-report in a populated
model, and over-reporting is visible and correctable, while under-reporting is
neither. Pre-existing content shows up as `orphan` rows and is read as such.

Sizes are reported twice on purpose. `plan_size_mm` comes from the bounding box,
which is axis-aligned and therefore over-reports a rotated member; `type_b_mm` /
`type_h_mm` come from the type's own parameters and do not. The findings prefer
the type parameters and fall back to the box, and the row carries both so a
disagreement between them is visible rather than resolved silently.

Revit-only. Imported from the pushbutton, never from the tests.
"""

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, ElementId,
                               FilteredElementCollector, LocationCurve,
                               LocationPoint, StorageType)

from .. import config
from ..model import AuditItem, Capture
from . import revit_shapes

#: Type parameters that carry a member's cross-section, in the order to try.
_WIDTH_PARAMS = ("b", "Width", "Section Width", "Foundation Thickness")
_DEPTH_PARAMS = ("h", "Height", "Section Depth", "Depth", "Thickness")


def read(doc, space, settings=None, categories=None):
    """Sweep the document's structural categories into a Capture."""
    values = config.settings(settings)
    capture = Capture(config.STAGE_MODEL, _title(doc))
    if doc is None:
        capture.fail("read", "no document")
        return capture

    wanted = categories or config.MODEL_CATEGORIES
    for name in wanted:
        builtin = getattr(BuiltInCategory, name, None)
        if builtin is None:
            # A category absent from this Revit version is not an error; saying
            # so beats a silent gap in the sweep.
            capture.skip(name)
            continue
        try:
            elements = (FilteredElementCollector(doc)
                        .OfCategory(builtin)
                        .WhereElementIsNotElementType()
                        .ToElements())
        except Exception as error:
            capture.fail("collect {0}".format(name), error)
            continue
        for element in elements:
            try:
                capture.add(_element_item(doc, element, name, space, values))
            except Exception as error:
                capture.fail("{0} id={1}".format(name, _id(element)), error)

    capture.meta["categories_swept"] = list(wanted)
    capture.meta["element_count"] = len(capture.items)
    return capture


def _element_item(doc, element, category_name, space, values):
    points_ft, source, found = _footprint(element, values["max_points_per_item"])
    holes = found.holes if found is not None else 0
    points_dxf, points_revit = space.from_revit(points_ft)
    element_type = _type_of(doc, element)

    item = AuditItem(
        config.STAGE_MODEL, _kind_for(category_name), source_type=type(element).__name__,
        layer=category_name, handle=_id(element),
        points_dxf=points_dxf, points_revit=points_revit, native_space="revit",
        category=_audit_category(category_name),
        mark=_string_param(element, BuiltInParameter.ALL_MODEL_MARK),
        level=_level_name(doc, element),
        type_name=_type_label(doc, element, element_type),
    )

    item.extra["family"] = _name_of(_family_of(element_type))
    item.extra["revit_category"] = _safe(lambda: element.Category.Name)
    item.extra["footprint_source"] = source
    item.extra["hole_count"] = holes
    if found is not None and found.hole_rings:
        # Areas in square feet at this point; the item stores millimetres.
        square = config.MM_PER_FT ** 2
        item.extra["gross_area_mm2"] = found.gross_area() * square
        # Set before _add_quantities, which lets Revit's own computed area --
        # authoritative where the model reports one -- override it.
        item.extra["area_mm2"] = found.net_area() * square
    item.extra["type_b_mm"] = _length_param_mm(element_type, _WIDTH_PARAMS)
    item.extra["type_h_mm"] = _length_param_mm(element_type, _DEPTH_PARAMS)
    item.extra["instance_b_mm"] = _length_param_mm(element, _WIDTH_PARAMS)
    item.extra["instance_h_mm"] = _length_param_mm(element, _DEPTH_PARAMS)
    item.extra["pinned"] = _safe(lambda: bool(element.Pinned))
    item.extra["group_id"] = _safe(lambda: _id_value(element.GroupId))
    item.extra["workset_id"] = _safe(lambda: _id_value(element.WorksetId))

    _add_location(item, element)
    _add_quantities(item, element)
    _add_constraints(doc, item, element)

    if item.handle is None:
        item.note("this element's id could not be read, so nothing else on this "
                  "row can be trusted either -- the row exists to say the "
                  "element is there")

    rotation = item.extra.get("rotation_deg")
    if (source == "bounding_box" and rotation is not None
            and abs(rotation % 90.0) > 0.5):
        # Only a fallback box misreports a rotated member now: a real footprint
        # is measured along its own axes, and `plan_size` is oriented.
        item.note("rotated {0:.1f} deg and no geometry could be read, so the "
                  "size comes from an axis-aligned box and over-reports the "
                  "section -- compare type_b_mm / type_h_mm".format(rotation))
    if holes:
        item.note("{0} opening(s) in the footprint".format(holes))
    return item


def _add_location(item, element):
    """Location point or curve, plus the rotation the element itself reports."""
    location = _safe(lambda: element.Location)
    if location is None:
        return
    if isinstance(location, LocationPoint):
        point = _safe(lambda: location.Point)
        if point is not None:
            item.extra["location_point_mm"] = _point_mm(point)
        radians = _safe(lambda: location.Rotation)
        if radians is not None:
            import math
            item.extra["rotation_deg"] = math.degrees(radians) % 180.0
        return
    if isinstance(location, LocationCurve):
        curve = _safe(lambda: location.Curve)
        if curve is None:
            return
        start = _safe(lambda: curve.GetEndPoint(0))
        end = _safe(lambda: curve.GetEndPoint(1))
        if start is not None and end is not None:
            item.extra["location_start_mm"] = _point_mm(start)
            item.extra["location_end_mm"] = _point_mm(end)
        length = _safe(lambda: curve.Length)
        if length is not None:
            item.extra["length_mm"] = length * config.MM_PER_FT
        item.extra["curve_type"] = type(curve).__name__
        # A horizontal beam's bounding box is degenerate in plan, so an angle
        # derived from it is meaningless. The location curve knows the heading.
        if start is not None and end is not None:
            import math
            heading = math.degrees(math.atan2(end.Y - start.Y, end.X - start.X))
            item.extra["rotation_deg"] = heading % 180.0


def _add_quantities(item, element):
    for key, builtin, factor in (
            ("area_mm2", BuiltInParameter.HOST_AREA_COMPUTED,
             config.MM_PER_FT ** 2),
            ("volume_mm3", BuiltInParameter.HOST_VOLUME_COMPUTED,
             config.MM_PER_FT ** 3)):
        value = _double_param(element, builtin)
        if value is not None:
            item.extra[key] = value * factor


def _add_constraints(doc, item, element):
    """How the member is fixed in space: its levels, offsets and usage.

    A member on the right storey with a 3 m base offset is on the wrong storey
    in every way that matters, and nothing in a position-and-size report would
    say so. These are the parameters that decide where a member actually sits.
    """
    top_id = _element_id_param(element, BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
    if top_id is not None and top_id != ElementId.InvalidElementId:
        item.extra["top_level"] = _name_of(_safe(lambda: doc.GetElement(top_id)))
    for key, builtin in (
            ("base_offset_mm", BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM),
            ("top_offset_mm", BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM),
            ("wall_base_offset_mm", BuiltInParameter.WALL_BASE_OFFSET),
            ("wall_height_mm", BuiltInParameter.WALL_USER_HEIGHT_PARAM)):
        value = _double_param(element, builtin)
        if value:
            item.extra[key] = value * config.MM_PER_FT
    usage = _safe(lambda: element.get_Parameter(
        BuiltInParameter.INSTANCE_STRUCT_USAGE_PARAM))
    if usage is not None:
        item.extra["structural_usage"] = _safe(lambda: usage.AsString())
    phase = _element_id_param(element, BuiltInParameter.PHASE_CREATED)
    if phase is not None and phase != ElementId.InvalidElementId:
        item.extra["phase"] = _name_of(_safe(lambda: doc.GetElement(phase)))


def _footprint(element, limit):
    """The element's real plan outline, in internal feet, and where it came from.

    Returns (points, source, holes). The element's own geometry is asked first:
    a bounding box is not a shape, and for anything that is not an
    axis-aligned rectangle it is actively wrong. An L-shaped slab, a lift core,
    a footing with a step all read as their enclosing rectangle, and the AREA --
    the number a slab is argued about in -- comes out as whatever the drawing
    left out. Inner loops come back as `holes`, which for a floor are its
    openings and are directly comparable to the hatch islands in the drawing.

    The box remains the fallback, because an element whose geometry cannot be
    resolved should still have a position and a rough extent rather than no row.
    """
    found = _safe(lambda: revit_shapes.element_footprint(element, limit))
    if found is not None and found.points:
        return found.points[:limit], found.source, found

    box = _safe(lambda: element.get_BoundingBox(None))
    if box is None:
        return [], "none", None
    low, high = box.Min, box.Max
    # Four corners rather than eight: the audit matches in plan, and a column's
    # top face adds nothing but doubles the point count on every row.
    corners = [(low.X, low.Y, low.Z), (high.X, low.Y, low.Z),
               (high.X, high.Y, low.Z), (low.X, high.Y, low.Z)]
    return corners[:limit], "bounding_box", None


# --- naming and parameters --------------------------------------------------

def _kind_for(category_name):
    """The item kind. Grids and levels are datums, not members."""
    if category_name in ("OST_Grids", "OST_Levels"):
        return "datum"
    return "element"


def _audit_category(category_name):
    """cad2bim's category vocabulary for a Revit category, so stages compare.

    Derived from `config.CATEGORY_SHEETS`, which is the single place the mapping
    between the two vocabularies lives.
    """
    for _sheet, keys in config.CATEGORY_SHEETS:
        if category_name in keys:
            return keys[0]
    return None


def _type_of(doc, element):
    type_id = _safe(lambda: element.GetTypeId())
    if type_id is None or type_id == ElementId.InvalidElementId:
        return None
    return _safe(lambda: doc.GetElement(type_id))


def _family_of(element_type):
    return _safe(lambda: element_type.Family) if element_type is not None else None


def _type_label(doc, element, element_type):
    """"Family: Type", falling back to whatever name can be resolved."""
    family = _name_of(_family_of(element_type))
    type_name = _name_of(element_type)
    if family and type_name:
        return "{0}: {1}".format(family, type_name)
    return type_name or _name_of(element)


def _name_of(element):
    if element is None:
        return None
    try:
        from anongee_toolkit.cad2bim.compat import get_element_name
        name = get_element_name(element)
        if name:
            return name
    except Exception:
        pass
    return _safe(lambda: element.Name)


def _level_name(doc, element):
    level_id = _safe(lambda: element.LevelId)
    if level_id is None or level_id == ElementId.InvalidElementId:
        for builtin in (BuiltInParameter.FAMILY_LEVEL_PARAM,
                        BuiltInParameter.SCHEDULE_LEVEL_PARAM,
                        BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                        BuiltInParameter.WALL_BASE_CONSTRAINT):
            level_id = _element_id_param(element, builtin)
            if level_id is not None:
                break
    if level_id is None or level_id == ElementId.InvalidElementId:
        return None
    return _name_of(_safe(lambda: doc.GetElement(level_id)))


def _string_param(element, builtin):
    parameter = _safe(lambda: element.get_Parameter(builtin))
    if parameter is None:
        return None
    return _safe(lambda: parameter.AsString())


def _double_param(element, builtin):
    parameter = _safe(lambda: element.get_Parameter(builtin))
    if parameter is None or _safe(lambda: parameter.StorageType) != StorageType.Double:
        return None
    return _safe(lambda: parameter.AsDouble())


def _element_id_param(element, builtin):
    parameter = _safe(lambda: element.get_Parameter(builtin))
    if parameter is None:
        return None
    return _safe(lambda: parameter.AsElementId())


def _length_param_mm(element, names):
    """First named length parameter that resolves, in mm. None when none do.

    Looked up by NAME because the parameter that carries a section width differs
    per family (`b` in the structural templates, `Width` elsewhere), and a
    built-in lookup would find neither in a user-made family.
    """
    if element is None:
        return None
    for name in names:
        parameter = _safe(lambda n=name: element.LookupParameter(n))
        if parameter is None:
            continue
        if _safe(lambda: parameter.StorageType) != StorageType.Double:
            continue
        value = _safe(lambda: parameter.AsDouble())
        if value:
            return value * config.MM_PER_FT
    return None


def _point_mm(point):
    return [point.X * config.MM_PER_FT, point.Y * config.MM_PER_FT,
            point.Z * config.MM_PER_FT]


def _id(element):
    """The element id as a string, or None when it cannot be read at all.

    None rather than the string "None": every field on this reader is guarded,
    which is right -- one unreadable element must not cost the sweep -- but
    guarded that thoroughly, a total failure produces a row that looks like a
    successful read of an empty element. An unresolvable id is the signal that
    nothing else on the row can be trusted either, and `_element_item` says so.
    """
    value = _id_value(_safe(lambda: element.Id))
    return None if value is None else str(value)


def _id_value(element_id):
    if element_id is None:
        return None
    for attribute in ("Value", "IntegerValue"):
        value = _safe(lambda a=attribute: getattr(element_id, a))
        if value is not None:
            return value
    return str(element_id)


def _title(doc):
    return _safe(lambda: doc.Title) or "model"


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None
