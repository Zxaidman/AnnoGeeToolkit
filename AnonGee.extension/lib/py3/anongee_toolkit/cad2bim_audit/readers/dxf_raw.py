# -*- coding: utf-8 -*-
"""Stage A, raw: EVERY entity in the DXF, including the ones cad2bim discards.

This is the census the report's "what is missing" column is measured against.
`cad2bim.readers.dxf_reader` returns curves, text and hatch outlines -- which is
the right thing for building a model and the wrong thing for auditing one,
because everything it declines to return leaves no trace. Six specific losses
this pass exists to expose, each confirmed against that module:

  1. `_walk` wraps every entity in a bare `except: continue`. A malformed entity
     vanishes with no record anywhere. Here each failure is a row in `errors`.
  2. Nesting is bounded at depth 3, so geometry inside a fourth-level block is
     silently gone. This pass goes to `dxf_block_depth` (8) and records the depth
     it found each entity at, so "too deep for cad2bim" is visible as such.
  3. Whole entity types return None and disappear: DIMENSION, LEADER, SOLID,
     3DFACE, MESH, REGION, XLINE, WIPEOUT and the rest. Here they are items.
  4. `_lwpolyline_points` reads `get_points("xy")`, which drops BULGE -- an arc
     segment in a polyline becomes a straight chord. This pass flattens through
     `ezdxf.path`, which honours bulges, and flags the entity.
  5. `_outer_boundary` keeps one ring per HATCH and discards the islands.
  6. `_boundary_points` takes an arc edge's CENTRE as a boundary vertex -- a
     point that is not on the boundary at all. `from_hatch_boundary_path`
     resolves edge paths properly.

Nothing here is shared with cad2bim, on purpose: a reader that shared code with
the thing it audits could not detect that code being wrong.

Requires ezdxf. Revit-free -- tested outside Revit against generated fixtures.
"""

import os

from .. import config
from ..model import AuditItem, Capture

ezdxf = None
_ezdxf_path = None
_ezdxf_recover = None
_IMPORT_ERROR = "ezdxf not imported yet"


def _ensure_ezdxf():
    """Import ezdxf on demand, caching only success.

    Lazy for the same reason cad2bim's reader is lazy: the CPython3 engine keeps
    sys.modules across runs, so an import that failed once before ezdxf was
    provisioned would stay failed for the whole Revit session.
    """
    global ezdxf, _ezdxf_path, _ezdxf_recover, _IMPORT_ERROR
    if ezdxf is not None:
        return True
    try:
        import ezdxf as _module
        from ezdxf import path as _path_module
        from ezdxf import recover as _recover_module
        ezdxf = _module
        _ezdxf_path = _path_module
        _ezdxf_recover = _recover_module
        _IMPORT_ERROR = None
        return True
    except Exception as error:
        _IMPORT_ERROR = error
        return False


def available():
    return _ensure_ezdxf()


#: Sag used when flattening a curve to vertices, in DRAWING UNITS. Matches
#: cad2bim's `_FLATTEN_DIST` so a spline's vertex count is comparable between
#: the two passes; a difference in the report then means a real difference.
_FLATTEN_SAG = 0.5

# How each DXF type is normalised. `kind` drives the report's grouping;
# `source_type` always keeps the real name.
_CURVE_TYPES = ("LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE",
                "POLYLINE", "HELIX")
_TEXT_TYPES = ("TEXT", "MTEXT", "ATTRIB", "ATTDEF")
_HATCH_TYPES = ("HATCH", "MPOLYGON")
_ANNOTATION_TYPES = ("DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION",
                     "LEADER", "MULTILEADER", "MLEADER", "TOLERANCE")
_FILLED_TYPES = ("SOLID", "TRACE", "3DFACE")
_MASS_TYPES = ("MESH", "REGION", "BODY", "3DSOLID", "SURFACE", "PLANESURFACE",
               "EXTRUDEDSURFACE", "REVOLVEDSURFACE", "SWEPTSURFACE",
               "LOFTEDSURFACE")
_CONSTRUCTION_TYPES = ("XLINE", "RAY")
_RASTER_TYPES = ("IMAGE", "WIPEOUT", "OLE2FRAME", "VIEWPORT")

#: Types cad2bim's reader turns into records. Anything outside this set is lost
#: by that reader, and this pass says so on the item itself.
_CAD2BIM_TYPES = frozenset(_CURVE_TYPES[:7] + _TEXT_TYPES + _HATCH_TYPES
                           + ("POINT", "INSERT"))

#: cad2bim bounds INSERT recursion here (`_walk(..., depth)` returns at >= 3).
_CAD2BIM_BLOCK_DEPTH = 3

# Boundary-path flags, group code 92.
_PATH_EXTERNAL = 1
_PATH_OUTERMOST = 16
_PATH_TEXTBOX = 8


def read(dxf_path, space, settings=None):
    """Read every modelspace entity of `dxf_path` into a Capture.

    `space` converts DXF drawing units into the report's two coordinate spaces.
    Raises only when the file itself cannot be opened -- a single bad entity is
    recorded as an error row and the read continues, because a drawing with one
    broken entity is exactly the drawing this report is for.
    """
    values = config.settings(settings)
    capture = Capture(config.STAGE_DXF_RAW, os.path.basename(dxf_path or ""))

    if not _ensure_ezdxf():
        raise RuntimeError(
            "ezdxf is not available. Provision it into lib/py3 "
            "(tools/auto_provision.py) and re-run. Import error: {0}".format(
                _IMPORT_ERROR))
    if not dxf_path or not os.path.exists(dxf_path):
        raise IOError("DXF file not found: {0}".format(dxf_path))

    doc, recovered = _open(dxf_path, capture)
    capture.meta.update(_document_meta(doc, recovered))

    context = _Context(space, values, capture)
    _walk(doc.modelspace(), context, depth=0, block=None)

    # Paperspace is counted but not read: cad2bim never looks at it, so entities
    # there are not "missing" from the model -- but a drawing whose structure was
    # laid out in paperspace explains an otherwise baffling empty read.
    capture.meta["paperspace_entities"] = _paperspace_count(doc)
    return capture


class _Context(object):
    """Carries what every entity handler needs, so signatures stay short."""

    def __init__(self, space, values, capture):
        self.space = space
        self.values = values
        self.capture = capture
        self.max_depth = values["dxf_block_depth"]


def _open(path, capture):
    """Open the DXF, falling back to ezdxf's recover mode. Returns (doc, recovered)."""
    try:
        return ezdxf.readfile(path), False
    except Exception as first_error:
        capture.fail("readfile", "{0} -- retrying in recover mode".format(first_error))
        doc, auditor = _ezdxf_recover.readfile(path)
        for error in list(getattr(auditor, "errors", []))[:200]:
            capture.fail("recover", getattr(error, "message", str(error)))
        return doc, True


def _document_meta(doc, recovered):
    """Header facts worth having beside the counts when a read looks wrong."""
    meta = {"recovered": recovered}
    try:
        meta["dxf_version"] = doc.dxfversion
    except Exception:
        pass
    for name, variable in (("insunits", "$INSUNITS"), ("measurement", "$MEASUREMENT")):
        try:
            meta[name] = doc.header.get(variable)
        except Exception:
            meta[name] = None
    try:
        meta["layers"] = sorted(layer.dxf.name for layer in doc.layers)
        meta["layer_count"] = len(meta["layers"])
    except Exception:
        meta["layers"] = []
    try:
        meta["block_count"] = sum(1 for _ in doc.blocks)
    except Exception:
        meta["block_count"] = None
    return meta


def _paperspace_count(doc):
    total = 0
    try:
        for layout in doc.layouts:
            if layout.name.lower() == "model":
                continue
            total += sum(1 for _ in layout)
    except Exception:
        return None
    return total


def _walk(entities, context, depth, block):
    """Process a container, recursing into INSERTs up to the configured depth.

    Every entity is wrapped individually so one malformed entity costs one row,
    not the rest of the drawing -- but unlike cad2bim's reader, the failure is
    RECORDED rather than swallowed.
    """
    for entity in entities:
        dxftype = "?"
        try:
            dxftype = entity.dxftype()
            if dxftype == "INSERT":
                _read_insert(entity, context, depth, block)
            else:
                _read_entity(entity, dxftype, context, depth, block)
        except Exception as error:
            context.capture.fail(
                "{0} handle={1} depth={2}".format(dxftype, _handle(entity), depth),
                error)


def _read_insert(insert, context, depth, block):
    """Record the INSERT itself, its ATTRIBs, and the geometry inside its block.

    The INSERT is recorded as an item in its own right as well as exploded: a
    block that failed to explode is then still visible as a thing that was there.
    """
    name = _safe(lambda: insert.dxf.name)
    item = _item(context, "block", "INSERT", insert, depth, block,
                 points=[_point(_safe(lambda: insert.dxf.insert) or (0, 0, 0))])
    item.type_name = name
    item.extra["block_name"] = name
    item.extra["scale"] = [_safe(lambda: float(insert.dxf.xscale)) or 1.0,
                           _safe(lambda: float(insert.dxf.yscale)) or 1.0,
                           _safe(lambda: float(insert.dxf.zscale)) or 1.0]
    item.extra["rotation_deg"] = _safe(lambda: float(insert.dxf.rotation)) or 0.0

    for attrib in _safe(lambda: list(insert.attribs)) or []:
        _read_entity(attrib, attrib.dxftype(), context, depth, block or name)

    if depth >= context.max_depth:
        item.note("block nesting deeper than dxf_block_depth={0}; contents not "
                  "read".format(context.max_depth))
        return
    virtual = _safe(lambda: list(insert.virtual_entities())) or []
    _walk(virtual, context, depth + 1, block or name)


def _read_entity(entity, dxftype, context, depth, block):
    """Turn one non-INSERT entity into exactly one AuditItem."""
    if dxftype in _TEXT_TYPES:
        _read_text(entity, dxftype, context, depth, block)
    elif dxftype in _HATCH_TYPES:
        _read_hatch(entity, dxftype, context, depth, block)
    elif dxftype in _CURVE_TYPES:
        _read_curve(entity, dxftype, context, depth, block)
    elif dxftype == "POINT":
        _item(context, "point", dxftype, entity, depth, block,
              points=[_point(_safe(lambda: entity.dxf.location) or (0, 0, 0))])
    elif dxftype in _FILLED_TYPES:
        _item(context, "filled", dxftype, entity, depth, block,
              points=_corner_points(entity))
    elif dxftype in _ANNOTATION_TYPES:
        _read_annotation(entity, dxftype, context, depth, block)
    elif dxftype in _MASS_TYPES:
        _item(context, "mass", dxftype, entity, depth, block,
              points=_bbox_points(entity))
    elif dxftype in _CONSTRUCTION_TYPES:
        _item(context, "construction", dxftype, entity, depth, block,
              points=_construction_points(entity))
    elif dxftype in _RASTER_TYPES:
        _item(context, "raster", dxftype, entity, depth, block,
              points=_bbox_points(entity))
    else:
        _item(context, "other", dxftype, entity, depth, block,
              points=_bbox_points(entity))


def _read_curve(entity, dxftype, context, depth, block):
    points, how = _flatten(entity)
    item = _item(context, "curve", dxftype, entity, depth, block, points=points)
    item.extra["flattened_by"] = how
    item.extra["vertex_count"] = len(points)
    if dxftype in ("LWPOLYLINE", "POLYLINE"):
        item.extra["closed"] = bool(_safe(lambda: entity.closed)
                                    or _safe(lambda: entity.is_closed))
        bulges = _bulges(entity)
        if bulges:
            item.extra["bulge_count"] = bulges
            # The finding this whole pass exists for, on the one entity type
            # where it silently changes shape rather than losing it outright.
            item.note("{0} arc segment(s) from bulges; cad2bim's reader uses "
                      "get_points('xy') and reads them as straight chords"
                      .format(bulges))
    if not points:
        item.note("no vertices could be produced from this entity")
    return item


def _read_text(entity, dxftype, context, depth, block):
    if dxftype == "MTEXT":
        value = _safe(entity.plain_text)
    else:
        value = _safe(lambda: entity.dxf.text)
    point = _text_anchor(entity)
    item = _item(context, "text", dxftype, entity, depth, block, points=[point])
    item.text = (value or "").strip()
    item.extra["rotation_deg"] = _text_rotation(entity)
    item.extra["height"] = _safe(lambda: float(entity.dxf.height))
    if dxftype in ("ATTRIB", "ATTDEF"):
        item.extra["tag"] = _safe(lambda: entity.dxf.tag)
    if not item.text:
        # cad2bim drops empty text before it becomes a record; that is correct
        # behaviour, and saying so stops the count difference reading as a bug.
        item.note("empty text; cad2bim's reader discards this (expected)")
    return item


def _read_hatch(entity, dxftype, context, depth, block):
    """One item per HATCH, carrying its outer ring and a record of its islands."""
    rings = _boundary_rings(entity)
    outer = _pick_outer(rings)
    # A textbox path is not an island: it is the hatch being clipped around a
    # label drawn over it. cad2bim skips those deliberately and correctly, so
    # counting them as dropped islands would manufacture a finding.
    textboxes = [ring for ring in rings if ring["textbox"]]
    islands = [ring for ring in rings
               if ring is not outer and not ring["textbox"]]

    item = _item(context, "hatch", dxftype, entity, depth, block,
                 points=outer["points"] if outer else [])
    item.type_name = _safe(lambda: entity.dxf.pattern_name)
    item.extra["pattern"] = item.type_name
    item.extra["solid_fill"] = bool(_safe(lambda: entity.dxf.solid_fill))
    item.extra["path_count"] = len(rings)
    item.extra["island_count"] = len(islands)
    item.extra["textbox_paths"] = len(textboxes)
    item.extra["edge_paths"] = sum(1 for r in rings if r["kind"] == "edge")
    item.extra["islands"] = [
        {"role": ring["role"], "vertices": len(ring["points"])} for ring in islands
    ]
    if islands:
        item.note("{0} island ring(s); cad2bim keeps only the outer boundary"
                  .format(len(islands)))
    if item.extra["edge_paths"]:
        item.note("{0} edge-type boundary path(s); cad2bim reads an arc edge's "
                  "CENTRE as a boundary vertex, which is not on the boundary"
                  .format(item.extra["edge_paths"]))
    if not outer:
        item.note("no usable boundary ring; cad2bim discards this hatch entirely")
    return item


def _read_annotation(entity, dxftype, context, depth, block):
    item = _item(context, "annotation", dxftype, entity, depth, block,
                 points=_bbox_points(entity))
    item.text = _safe(lambda: entity.dxf.text) or None
    measurement = _safe(lambda: entity.get_measurement())
    if isinstance(measurement, (int, float)):
        item.extra["measurement"] = float(measurement)
    return item


# --- item construction ------------------------------------------------------

def _item(context, kind, source_type, entity, depth, block, points):
    """Build, place in both coordinate spaces, and append one item."""
    points = points or []
    points_dxf, points_revit = context.space.from_dxf(points)
    item = AuditItem(
        config.STAGE_DXF_RAW, kind, source_type=source_type,
        layer=_safe(lambda: entity.dxf.layer), handle=_handle(entity),
        points_dxf=points_dxf, points_revit=points_revit, native_space="dxf",
    )
    item.extra["depth"] = depth
    if block:
        item.extra["in_block"] = block
    _mark_reader_gap(item, source_type, depth)
    return context.capture.add(item)


def _mark_reader_gap(item, source_type, depth):
    """Flag, on the item, what cad2bim's reader will do with this entity.

    Decided here from the type and depth rather than by diffing the two captures,
    because a diff can only report a count while this reports a REASON -- and the
    reason is the part that tells you whether to fix the drawing or the reader.
    """
    if source_type not in _CAD2BIM_TYPES:
        item.extra["cad2bim_reads"] = False
        item.note("entity type {0} is not handled by cad2bim's DXF reader; it "
                  "produces no record".format(source_type))
    elif depth > _CAD2BIM_BLOCK_DEPTH:
        item.extra["cad2bim_reads"] = False
        item.note("nested {0} levels deep; cad2bim's reader stops at {1}"
                  .format(depth, _CAD2BIM_BLOCK_DEPTH))
    else:
        item.extra["cad2bim_reads"] = True


# --- geometry extraction ----------------------------------------------------

def _flatten(entity):
    """Vertices for a curve entity, as ([(x, y, z)], how). Never raises.

    `ezdxf.path.make_path` is preferred because it honours LWPOLYLINE bulges and
    resolves OCS properly; the per-type fallbacks cover entities it declines.
    """
    try:
        path = _ezdxf_path.make_path(entity)
        points = [_point(p) for p in path.flattening(_FLATTEN_SAG)]
        if points:
            return points, "ezdxf.path"
    except Exception:
        pass
    try:
        points = [_point(p) for p in entity.flattening(_FLATTEN_SAG)]
        if points:
            return points, "entity.flattening"
    except Exception:
        pass
    for getter, how in ((lambda: [entity.dxf.start, entity.dxf.end], "endpoints"),
                        (lambda: list(entity.vertices_in_wcs()), "vertices_in_wcs")):
        try:
            points = [_point(p) for p in getter()]
            if points:
                return points, how
        except Exception:
            continue
    return [], "none"


def _bulges(entity):
    """How many vertices of a polyline carry a non-zero bulge (an arc segment)."""
    try:
        return sum(1 for point in entity.get_points("xyseb") if abs(point[4]) > 1e-9)
    except Exception:
        pass
    try:
        return sum(1 for v in entity.vertices if abs(float(v.dxf.bulge)) > 1e-9)
    except Exception:
        return 0


def _boundary_rings(hatch):
    """Every boundary path of a hatch, resolved properly, with its role.

    Uses `from_hatch_boundary_path`, which converts arc and spline EDGE paths
    into real vertices. cad2bim's `_boundary_points` cannot: for an edge path it
    collects each edge's start point, and for an arc edge with no start it
    collects the arc's CENTRE -- a point inside the ring, not on it.
    """
    rings = []
    ocs = _safe(hatch.ocs)
    elevation = _safe(lambda: float(hatch.dxf.elevation.z))
    if elevation is None:
        elevation = _safe(lambda: float(hatch.dxf.elevation)) or 0.0
    for index, boundary in enumerate(_safe(lambda: list(hatch.paths)) or []):
        flags = _safe(lambda: boundary.path_type_flags) or 0
        points = []
        try:
            path = _ezdxf_path.from_hatch_boundary_path(boundary, ocs, elevation)
            points = [_point(p) for p in path.flattening(_FLATTEN_SAG)]
        except Exception:
            vertices = _safe(lambda: list(boundary.vertices)) or []
            points = [(float(v[0]), float(v[1]), 0.0) for v in vertices]
        if len(points) < 3:
            continue
        rings.append({
            "index": index,
            "points": points,
            "textbox": bool(flags & _PATH_TEXTBOX),
            "external": bool(flags & _PATH_EXTERNAL),
            "outermost": bool(flags & _PATH_OUTERMOST),
            "kind": "edge" if _safe(lambda: bool(boundary.edges)) else "polyline",
            "role": _ring_role(flags),
        })
    return rings


def _ring_role(flags):
    if flags & _PATH_TEXTBOX:
        return "textbox"
    if flags & _PATH_EXTERNAL:
        return "external"
    if flags & _PATH_OUTERMOST:
        return "outermost"
    return "inner"


def _pick_outer(rings):
    """The ring that bounds the hatch: the external one, else the largest.

    Same rule as cad2bim's `_outer_boundary`, deliberately, so the two passes
    disagree only where the RESOLUTION of the ring differs and not because they
    chose different rings.
    """
    candidates = [ring for ring in rings if not ring["textbox"]]
    if not candidates:
        return None
    external = [ring for ring in candidates if ring["external"]]
    pool = external or candidates
    return max(pool, key=lambda ring: _ring_area(ring["points"]))


def _ring_area(points):
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2.0


def _corner_points(entity):
    """The up-to-four corners of a SOLID / TRACE / 3DFACE."""
    points = []
    for name in ("vtx0", "vtx1", "vtx2", "vtx3"):
        value = _safe(lambda n=name: getattr(entity.dxf, n))
        if value is not None:
            points.append(_point(value))
    # DXF stores SOLID corners in a Z order: 0-1-3-2 walks the outline.
    if len(points) == 4:
        points = [points[0], points[1], points[3], points[2]]
    return points


def _construction_points(entity):
    """Two points along an infinite XLINE / RAY, so it has a position and a heading."""
    start = _safe(lambda: entity.dxf.start) or _safe(lambda: entity.dxf.unit_vector)
    direction = _safe(lambda: entity.dxf.unit_vector)
    if start is None:
        return []
    origin = _point(start)
    if direction is None:
        return [origin]
    step = _point(direction)
    return [origin, (origin[0] + step[0], origin[1] + step[1], origin[2] + step[2])]


def _bbox_points(entity):
    """The entity's bounding box as two corners; [] when ezdxf cannot compute one.

    Enough to place the thing on a plan and match it spatially, without pulling
    a mesh's every vertex into the report.
    """
    try:
        from ezdxf import bbox as _bbox_module
        box = _bbox_module.extents([entity])
        if box.has_data:
            return [_point(box.extmin), _point(box.extmax)]
    except Exception:
        pass
    for name in ("insert", "location", "defpoint", "center"):
        value = _safe(lambda n=name: getattr(entity.dxf, n))
        if value is not None:
            return [_point(value)]
    return []


def _text_anchor(entity):
    point = _safe(lambda: entity.dxf.insert)
    if point is None or (_point(point) == (0.0, 0.0, 0.0)
                         and _safe(lambda: entity.dxf.hasattr("align_point"))):
        point = _safe(lambda: entity.dxf.align_point) or point
    return _point(point or (0.0, 0.0, 0.0))


def _text_rotation(entity):
    """Degrees, 0 = horizontal. MTEXT's direction VECTOR overrides its rotation."""
    try:
        if entity.dxf.hasattr("text_direction"):
            import math
            d = entity.dxf.text_direction
            return math.degrees(math.atan2(d[1], d[0]))
        return float(entity.dxf.rotation) if entity.dxf.hasattr("rotation") else 0.0
    except Exception:
        return 0.0


def _handle(entity):
    value = _safe(lambda: entity.dxf.handle)
    return str(value) if value else None


def _point(value):
    """Normalise an ezdxf Vec3 / sequence to a plain (x, y, z) float tuple."""
    try:
        return (float(value.x), float(value.y), float(value.z))
    except AttributeError:
        pass
    try:
        if len(value) >= 3:
            return (float(value[0]), float(value[1]), float(value[2]))
        return (float(value[0]), float(value[1]), 0.0)
    except Exception:
        return (0.0, 0.0, 0.0)


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None
