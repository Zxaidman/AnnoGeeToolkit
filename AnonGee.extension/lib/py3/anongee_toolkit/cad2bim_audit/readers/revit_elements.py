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
    points_ft = _footprint(element, values["max_points_per_item"])
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
    item.extra["size_source"] = "bounding_box"
    item.extra["type_b_mm"] = _length_param_mm(element_type, _WIDTH_PARAMS)
    item.extra["type_h_mm"] = _length_param_mm(element_type, _DEPTH_PARAMS)
    item.extra["instance_b_mm"] = _length_param_mm(element, _WIDTH_PARAMS)
    item.extra["instance_h_mm"] = _length_param_mm(element, _DEPTH_PARAMS)
    item.extra["pinned"] = _safe(lambda: bool(element.Pinned))
    item.extra["group_id"] = _safe(lambda: _id_value(element.GroupId))
    item.extra["workset_id"] = _safe(lambda: _id_value(element.WorksetId))

    _add_location(item, element)
    _add_quantities(item, element)

    rotation = item.extra.get("rotation_deg")
    if rotation is not None and abs(rotation % 90.0) > 0.5:
        item.note("member is rotated {0:.1f} deg; the bounding-box plan size "
                  "over-reports its section -- compare type_b_mm / type_h_mm"
                  .format(rotation))
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


def _add_quantities(item, element):
    for key, builtin, factor in (
            ("area_mm2", BuiltInParameter.HOST_AREA_COMPUTED,
             config.MM_PER_FT ** 2),
            ("volume_mm3", BuiltInParameter.HOST_VOLUME_COMPUTED,
             config.MM_PER_FT ** 3)):
        value = _double_param(element, builtin)
        if value is not None:
            item.extra[key] = value * factor


def _footprint(element, limit):
    """The element's plan footprint as bounding-box corners, in internal feet.

    Four corners rather than eight: the audit matches in plan, and a column's
    top face adds nothing but doubles the point count on every row.
    """
    box = _safe(lambda: element.get_BoundingBox(None))
    if box is None:
        return []
    low, high = box.Min, box.Max
    corners = [(low.X, low.Y, low.Z), (high.X, low.Y, low.Z),
               (high.X, high.Y, low.Z), (low.X, high.Y, low.Z)]
    return corners[:limit]


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
    return str(_id_value(_safe(lambda: element.Id)))


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
