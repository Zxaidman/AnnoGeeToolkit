# -*- coding: utf-8 -*-
"""Stage B: what Revit made of the linked DXF -- twice.

`read_raw` walks every GeometryObject the link exposes. `read_parsed` calls
cad2bim's `geometry_reader.read_link` verbatim. The difference between them is
the reader's blind spot, and for this stage that blind spot is large and
documented in cad2bim's own source:

    # Solids, meshes, points and text are intentionally ignored by the reader.

Which means the hatches the user cares about are, today, invisible to cad2bim on
the Revit side -- not lost in classification, not rejected by a builder, simply
never read. A report built only on `geometry_reader` cannot show that, because
the thing it would show is the thing it cannot see.

Both passes use a plain `Options()`, exactly as cad2bim does. That is deliberate:
if the raw pass used a finer detail level or included non-visible objects, the
delta would mix "the walker sees more" with "the options asked for more", and
neither number would mean anything. Non-visible geometry is counted separately
and reported in `meta`, never mixed into the items.

Revit-only. Imported from the pushbutton, never from the tests.
"""

from Autodesk.Revit.DB import (Options, GeometryInstance, PolyLine, Curve, Line,
                               Arc, Solid, Mesh, Point, ElementId, ViewDetailLevel)

from .. import config
from ..model import AuditItem, Capture

_ARC_MID = 0.5   # arcs are kept start / mid / end, as cad2bim keeps them


def read_raw(doc, import_instance, space, settings=None):
    """Walk every GeometryObject of the link into a Capture."""
    values = config.settings(settings)
    capture = Capture(config.STAGE_LINK_RAW, _describe(doc, import_instance))
    if doc is None or import_instance is None:
        capture.fail("read_raw", "no document or import instance")
        return capture

    try:
        geometry = import_instance.get_Geometry(Options())
    except Exception as error:
        capture.fail("get_Geometry", error)
        return capture
    if geometry is None:
        capture.fail("get_Geometry", "the link returned no geometry element")
        return capture

    context = _Context(doc, space, values, capture)
    _walk(geometry, context, depth=0)

    capture.meta["non_visible_objects"] = _count_non_visible(import_instance)
    capture.meta["max_depth_seen"] = context.max_depth_seen
    return capture


def read_parsed(doc, import_instance, space, settings=None, reader=None):
    """Read the link through cad2bim's own geometry_reader into a Capture."""
    config.settings(settings)
    capture = Capture(config.STAGE_LINK_PARSED, _describe(doc, import_instance))

    geometry_reader = reader
    if geometry_reader is None:
        try:
            from anongee_toolkit.cad2bim.readers import geometry_reader
        except ImportError as error:
            capture.fail("import", "cad2bim.readers.geometry_reader "
                                   "unavailable: {0}".format(error))
            return capture
    try:
        result = geometry_reader.read_link(doc, import_instance)
    except Exception as error:
        capture.fail("read_link", error)
        return capture

    capture.source_name = result.source_name
    for record in result.records:
        points_dxf, points_revit = space.from_revit(record.points)
        item = AuditItem(
            config.STAGE_LINK_PARSED, "curve", source_type=record.kind,
            layer=record.layer, points_dxf=points_dxf, points_revit=points_revit,
            native_space="revit",
        )
        if record.length_ft is not None:
            item.extra["length_mm"] = record.length_ft * config.MM_PER_FT
        item.extra["vertex_count"] = len(record.points)
        capture.add(item)
    return capture


class _Context(object):
    def __init__(self, doc, space, values, capture):
        self.doc = doc
        self.space = space
        self.values = values
        self.capture = capture
        self.max_points = values["max_points_per_item"]
        self.max_depth_seen = 0


def _walk(geometry_element, context, depth):
    """Depth-first over a GeometryElement, one try/except per object.

    Recursion mirrors cad2bim's: `GetInstanceGeometry()` returns geometry already
    in project coordinates at every level, so transforms are never compounded by
    hand and can never be applied twice.
    """
    context.max_depth_seen = max(context.max_depth_seen, depth)
    for geom_obj in geometry_element:
        type_name = type(geom_obj).__name__
        try:
            if isinstance(geom_obj, GeometryInstance):
                nested = geom_obj.GetInstanceGeometry()
                if nested is not None:
                    _walk(nested, context, depth + 1)
                continue
            _read_object(geom_obj, type_name, context, depth)
        except Exception as error:
            context.capture.fail("{0} depth={1}".format(type_name, depth), error)


def _read_object(geom_obj, type_name, context, depth):
    if isinstance(geom_obj, PolyLine):
        item = _item(context, "curve", "PolyLine", geom_obj, depth,
                     _polyline_points(geom_obj))
        item.extra["cad2bim_reads"] = True
        return item
    if isinstance(geom_obj, Curve):
        item = _item(context, "curve", _curve_kind(geom_obj), geom_obj, depth,
                     _curve_points(geom_obj))
        item.extra["cad2bim_reads"] = True
        if not item.points_revit:
            item.note("unbound open curve; cad2bim's reader skips these "
                      "(no endpoints to read)")
            item.extra["cad2bim_reads"] = False
        return item
    if isinstance(geom_obj, Solid):
        return _read_solid(geom_obj, context, depth)
    if isinstance(geom_obj, Mesh):
        return _read_mesh(geom_obj, context, depth)
    if isinstance(geom_obj, Point):
        item = _item(context, "point", "Point", geom_obj, depth,
                     [_xyz(geom_obj.Coord)])
        return _lost(item, "Point")
    item = _item(context, "other", type_name, geom_obj, depth, [])
    return _lost(item, type_name)


def _read_solid(solid, context, depth):
    """A solid, outlined by its edges -- this is where an imported hatch lands.

    The edge tessellation is used as the item's points because it is the only
    representation that can be matched against a DXF hatch boundary. Volume and
    face count come along so a zero-volume face-only solid is distinguishable
    from a real extrusion.
    """
    points = _solid_points(solid, context.max_points)
    item = _item(context, "solid", "Solid", solid, depth, points)
    item.extra["face_count"] = _safe(lambda: solid.Faces.Size)
    item.extra["edge_count"] = _safe(lambda: solid.Edges.Size)
    volume_ft3 = _safe(lambda: solid.Volume)
    area_ft2 = _safe(lambda: solid.SurfaceArea)
    if volume_ft3 is not None:
        item.extra["volume_mm3"] = volume_ft3 * (config.MM_PER_FT ** 3)
    if area_ft2 is not None:
        item.extra["surface_area_mm2"] = area_ft2 * (config.MM_PER_FT ** 2)
    return _lost(item, "Solid")


def _read_mesh(mesh, context, depth):
    triangles = _safe(lambda: mesh.NumTriangles) or 0
    points = []
    try:
        vertices = list(mesh.Vertices)
        step = max(1, len(vertices) // context.max_points)
        points = [_xyz(v) for v in vertices[::step]][:context.max_points]
    except Exception:
        points = []
    item = _item(context, "mesh", "Mesh", mesh, depth, points)
    item.extra["triangle_count"] = triangles
    return _lost(item, "Mesh")


def _lost(item, type_name):
    """Mark an object cad2bim's geometry_reader discards, and say so on the row.

    Quoting the reason rather than merely flagging it: a reader that ignores
    solids is a design decision, and the report should read as a measurement of
    that decision rather than as an accusation.
    """
    item.extra["cad2bim_reads"] = False
    item.note("{0} is ignored by cad2bim's geometry_reader (\"Solids, meshes, "
              "points and text are intentionally ignored\"); it reaches no "
              "classification or builder".format(type_name))
    return item


def _item(context, kind, source_type, geom_obj, depth, points_ft):
    points_dxf, points_revit = context.space.from_revit(points_ft or [])
    item = AuditItem(
        config.STAGE_LINK_RAW, kind, source_type=source_type,
        layer=_layer_name(context.doc, geom_obj),
        points_dxf=points_dxf, points_revit=points_revit, native_space="revit",
    )
    item.extra["depth"] = depth
    return context.capture.add(item)


# --- geometry ---------------------------------------------------------------

def _curve_kind(curve):
    name = type(curve).__name__
    return {"Line": "line", "Arc": "arc"}.get(name, name.lower())


def _curve_points(curve):
    """Points for a curve, matching cad2bim's sampling so lengths are comparable."""
    if not curve.IsBound:
        if getattr(curve, "IsClosed", False):
            return _tessellate(curve)
        return []
    if isinstance(curve, Line):
        return [_xyz(curve.GetEndPoint(0)), _xyz(curve.GetEndPoint(1))]
    if isinstance(curve, Arc):
        return [_xyz(curve.GetEndPoint(0)),
                _xyz(curve.Evaluate(_ARC_MID, True)),
                _xyz(curve.GetEndPoint(1))]
    return _tessellate(curve)


def _polyline_points(polyline):
    return [_xyz(p) for p in polyline.GetCoordinates()]


def _tessellate(curve):
    try:
        return [_xyz(p) for p in curve.Tessellate()]
    except Exception:
        return []


def _solid_points(solid, limit):
    """Sampled edge endpoints, enough to bound the solid without dumping a mesh."""
    points = []
    try:
        for edge in solid.Edges:
            for point in edge.Tessellate():
                points.append(_xyz(point))
                if len(points) >= limit:
                    return points
    except Exception:
        pass
    return points


def _count_non_visible(import_instance):
    """How many objects a non-visible read exposes that a plain read does not.

    Reported in `meta` only. Mixing them into the items would make the raw pass
    incomparable with the parsed one, which is the comparison this stage is for.
    """
    try:
        options = Options()
        options.IncludeNonVisibleObjects = True
        options.DetailLevel = ViewDetailLevel.Fine
        geometry = import_instance.get_Geometry(options)
        if geometry is None:
            return 0
        return _count(geometry, 0)
    except Exception:
        return None


def _count(geometry_element, depth):
    total = 0
    if depth > 8:
        return total
    for geom_obj in geometry_element:
        if isinstance(geom_obj, GeometryInstance):
            nested = geom_obj.GetInstanceGeometry()
            if nested is not None:
                total += _count(nested, depth + 1)
            continue
        total += 1
    return total


def _layer_name(doc, geom_obj):
    """CAD layer via GraphicsStyle. Null-guarded at every step, as cad2bim does."""
    try:
        style_id = geom_obj.GraphicsStyleId
        if style_id is None or style_id == ElementId.InvalidElementId:
            return None
        style = doc.GetElement(style_id)
        if style is None:
            return None
        category = style.GraphicsStyleCategory
        return category.Name if category is not None else None
    except Exception:
        return None


def _describe(doc, import_instance):
    try:
        from anongee_toolkit.cad2bim.readers.cad_links import describe_link
        return describe_link(doc, import_instance)
    except Exception:
        return "CAD link"


def _xyz(point):
    return (point.X, point.Y, point.Z)


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None
