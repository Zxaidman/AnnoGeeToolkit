# -*- coding: utf-8 -*-
"""Getting a real outline out of Revit geometry, for both Revit-side readers.

A bounding box is not a shape. It over-reports every rotated member -- a 400x400
column at 45 degrees measures 566x566, so the audit either flags every rotated
column in the plan as the wrong size or has to look away from all of them -- and
it cannot describe a non-rectangular one at all: an L-shaped slab, a lift core,
a footing with a step all read as the enclosing rectangle, and their AREA, which
is the number a slab is actually argued about in, comes out wrong by whatever
the drawing left out.

The real outline is the outer loop of the largest horizontal planar face. That
is a ring, in order, in project coordinates, and it is directly comparable to
the DXF polyline or hatch boundary that produced it. Inner loops are HOLES --
openings in a slab, islands in an imported hatch -- and counting them lets the
report ask whether a hole in the drawing survived into the model.

Shared by `revit_geometry` (stage B, where a solid is usually an imported hatch)
and `revit_elements` (stage C, where it is a placed member), because it is the
same question about the same kind of object.

Revit-only, and tested against the stub in tests/_revit_stub.py.
"""

from Autodesk.Revit.DB import (GeometryInstance, Options, PlanarFace, Solid,
                               ViewDetailLevel)

#: |normal.Z| above this counts as horizontal. Generous: an imported hatch's
#: face is exactly flat, and a slightly-off one still describes the plan.
HORIZONTAL_DOT = 0.9

#: Below this volume (cubic feet, ~28 cm^3) a solid is a face, not a body.
FLAT_VOLUME_FT3 = 1.0e-3

#: How deep to recurse into nested geometry instances when hunting a footprint.
#: A family instance is commonly one level; three covers nested families without
#: letting a pathological model run away.
MAX_DEPTH = 3


class Footprint(object):
    """A plan outline and what it was worth knowing about."""

    __slots__ = ("points", "hole_rings", "loops", "faces", "source", "area_ft2")

    def __init__(self, points=None, loops=0, faces=0, source="none", area_ft2=None,
                 hole_rings=None):
        self.points = points or []
        self.hole_rings = hole_rings or []   # inner loops: openings, islands
        self.loops = loops
        self.faces = faces
        self.source = source          # planar_face | edge_cloud | bounding_box | none
        self.area_ft2 = area_ft2

    @property
    def holes(self):
        return len(self.hole_rings)

    def gross_area(self):
        """Plan area of the outer ring, in whatever units the points are in."""
        return _area(self.points)

    def net_area(self):
        """Outer ring less its holes -- the area the slab actually has.

        An opening is a hole in the thing, not merely a hole in its hatching, so
        a slab area that ignores it is wrong by the size of the lift shaft. This
        is only used when Revit's own computed area is unavailable; where the
        model reports one, that is authoritative and wins.
        """
        return max(0.0, self.gross_area() - sum(_area(ring)
                                                for ring in self.hole_rings))

    def __repr__(self):
        return "<Footprint {0} pts={1} loops={2}>".format(
            self.source, len(self.points), self.loops)


def solid_footprint(solid, limit):
    """The plan outline of one solid, as a Footprint.

    The LARGEST horizontal face is taken because a solid has at least two, a top
    and a bottom, and may have more where it steps; the largest describes its
    plan. Falls back to the edge cloud, which bounds the thing without
    describing it -- and says so, so nothing downstream mistakes one for the
    other.
    """
    best = None
    best_area = -1.0
    horizontal = 0
    try:
        faces = list(solid.Faces)
    except Exception:
        faces = []

    for face in faces:
        if not isinstance(face, PlanarFace):
            continue
        normal = _safe(lambda f=face: f.FaceNormal)
        if normal is None or abs(normal.Z) < HORIZONTAL_DOT:
            continue
        horizontal += 1
        area = _safe(lambda f=face: f.Area) or 0.0
        if area >= best_area:
            best_area = area
            best = face

    if best is not None:
        loops = _safe(lambda: list(best.GetEdgesAsCurveLoops())) or []
        if loops:
            holes = [loop_points(loop, limit) for loop in loops[1:]]
            return Footprint(loop_points(loops[0], limit), len(loops), horizontal,
                             "planar_face", best_area,
                             hole_rings=[h for h in holes if len(h) >= 3])

    cloud = edge_cloud(solid, limit)
    if cloud:
        return Footprint(cloud, 0, horizontal, "edge_cloud")
    return Footprint(source="none", faces=horizontal)


def element_footprint(element, limit, view=None):
    """The plan outline of a placed element, from its own geometry.

    Walks the element's solids, recursing into geometry instances -- a family
    instance keeps its solids one level down, so a walk that did not recurse
    would find nothing at all for most placed members. The largest footprint
    found wins, which for a column is its section and for a floor its slab.
    """
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    options.ComputeReferences = False
    try:
        geometry = element.get_Geometry(options)
    except Exception:
        return Footprint()
    if geometry is None:
        return Footprint()

    best = Footprint()
    for solid in _solids(geometry, 0):
        found = solid_footprint(solid, limit)
        if found.source != "planar_face":
            continue
        if not best.points or found.gross_area() > best.gross_area():
            best = found
    return best


def is_flat(solid):
    """True when a solid encloses no volume: a face, as an import produces."""
    volume = _safe(lambda: solid.Volume)
    return None if volume is None else abs(volume) < FLAT_VOLUME_FT3


def loop_points(loop, limit):
    """A CurveLoop's vertices in order, as (x, y, z) tuples.

    Each curve's START point only: consecutive curves share an end, so taking
    both would double every vertex and turn a four-sided ring into an eight-point
    one whose area is right and whose vertex count is a lie.
    """
    points = []
    try:
        for curve in loop:
            start = _safe(lambda c=curve: c.GetEndPoint(0))
            if start is not None:
                points.append(xyz(start))
            if len(points) >= limit:
                break
    except Exception:
        pass
    return points


def edge_cloud(solid, limit):
    """Every edge's vertices, in whatever order the faces come.

    Bounds the solid; does not describe it. Only ever a fallback, and callers
    record which they got.
    """
    points = []
    try:
        for edge in solid.Edges:
            for point in edge.Tessellate():
                points.append(xyz(point))
                if len(points) >= limit:
                    return points
    except Exception:
        pass
    return points


def _solids(geometry_element, depth):
    """Every Solid in a geometry element, recursing into instances."""
    found = []
    if depth > MAX_DEPTH:
        return found
    try:
        objects = list(geometry_element)
    except Exception:
        return found
    for geom_obj in objects:
        if isinstance(geom_obj, GeometryInstance):
            nested = _safe(lambda g=geom_obj: g.GetInstanceGeometry())
            if nested is not None:
                found.extend(_solids(nested, depth + 1))
            continue
        if isinstance(geom_obj, Solid):
            found.append(geom_obj)
    return found


def _area(points):
    """Shoelace area in plan; used only to rank candidate footprints."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2.0


def xyz(point):
    return (point.X, point.Y, point.Z)


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None
