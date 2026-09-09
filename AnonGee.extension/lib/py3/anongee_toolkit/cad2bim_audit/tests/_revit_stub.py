# -*- coding: utf-8 -*-
"""A fake `Autodesk.Revit.DB`, so the stage B and C readers can be tested.

Those two modules are the only ones in the package that import the Revit API,
and until this existed they were the only ones with no tests at all -- they had
never executed anywhere, in any form. That is precisely backwards: the readers
that cannot be run on a developer's machine are the ones most in need of a test,
because the only other way to exercise them is to install Revit, open a model,
and click a button.

This is a STUB, not an emulator. It implements the members the readers actually
touch and nothing else, so a reader reaching for something new fails loudly with
an AttributeError rather than quietly getting a Mock that answers everything.
What it is faithful about is the shapes that matter:

  * geometry objects carry a GraphicsStyleId that resolves through the document
    to a category name -- the null-at-every-step path the real API has, and the
    reason both readers guard each step
  * a GeometryInstance returns nested geometry already in project coordinates,
    which is why the readers never compound a transform by hand
  * parameters answer through StorageType, and a parameter of the wrong storage
    type returns nothing rather than raising
  * lengths and coordinates are in INTERNAL FEET, as Revit's are, so a unit bug
    in a reader shows up as a wrong millimetre value in a test

Builders at the bottom make a fixture readable: `line(...)`, `solid(...)`,
`column(...)` rather than four lines of object construction each.
"""

import math
import sys
import types


# --- geometry primitives ----------------------------------------------------

class XYZ(object):
    """Revit's point. Internal feet."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)

    def __repr__(self):
        return "XYZ({0}, {1}, {2})".format(self.X, self.Y, self.Z)


def _xyz(value):
    return value if isinstance(value, XYZ) else XYZ(*value)


class Collection(list):
    """A .NET collection: iterable, and it knows its own Size."""

    @property
    def Size(self):
        return len(self)


class ElementId(object):
    InvalidElementId = None      # replaced below, once the class exists

    def __init__(self, value):
        self.Value = int(value)
        self.IntegerValue = int(value)

    def __eq__(self, other):
        return isinstance(other, ElementId) and other.Value == self.Value

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.Value)

    def __repr__(self):
        return "ElementId({0})".format(self.Value)


ElementId.InvalidElementId = ElementId(-1)


class ViewDetailLevel(object):
    Coarse, Medium, Fine = "Coarse", "Medium", "Fine"


class Options(object):
    def __init__(self):
        self.IncludeNonVisibleObjects = False
        self.DetailLevel = ViewDetailLevel.Medium
        self.ComputeReferences = False


# --- geometry objects -------------------------------------------------------

class GeometryObject(object):
    """Everything the geometry walk can meet carries a graphics style."""

    def __init__(self, style_id=None):
        self.GraphicsStyleId = style_id or ElementId.InvalidElementId


class Curve(GeometryObject):
    def __init__(self, points, style_id=None, bound=True, closed=False,
                 length=None):
        GeometryObject.__init__(self, style_id)
        self._points = [_xyz(p) for p in points]
        self.IsBound = bound
        self.IsClosed = closed
        self._length = length

    @property
    def Length(self):
        if self._length is not None:
            return self._length
        total = 0.0
        for a, b in zip(self._points, self._points[1:]):
            total += math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2
                               + (a.Z - b.Z) ** 2)
        return total

    def GetEndPoint(self, index):
        if not self.IsBound:
            # The real API raises on an unbound curve's endpoints, and the
            # readers are written to expect that.
            raise Exception("curve is not bound")
        return self._points[0] if index == 0 else self._points[-1]

    def Evaluate(self, parameter, normalized=True):
        if not self._points:
            raise Exception("no points")
        index = int(round(parameter * (len(self._points) - 1)))
        return self._points[max(0, min(index, len(self._points) - 1))]

    def Tessellate(self):
        return list(self._points)


class Line(Curve):
    pass


class Arc(Curve):
    pass


class NurbSpline(Curve):
    pass


class PolyLine(GeometryObject):
    def __init__(self, points, style_id=None):
        GeometryObject.__init__(self, style_id)
        self._points = [_xyz(p) for p in points]

    def GetCoordinates(self):
        return Collection(self._points)


class Edge(object):
    def __init__(self, points):
        self._points = [_xyz(p) for p in points]

    def Tessellate(self):
        return list(self._points)


class CurveLoop(list):
    """A closed ring of curves. Outer loop first, then any holes."""


class Face(object):
    def __init__(self, area=0.0, loops=None):
        self.Area = area
        self._loops = list(loops or [])

    def GetEdgesAsCurveLoops(self):
        return Collection(self._loops)


class PlanarFace(Face):
    """A flat face, which is what an imported hatch becomes."""

    def __init__(self, normal=(0, 0, 1), area=0.0, loops=None, origin=(0, 0, 0)):
        Face.__init__(self, area=area, loops=loops)
        self.FaceNormal = _xyz(normal)
        self.Origin = _xyz(origin)


class Solid(GeometryObject):
    def __init__(self, edges=(), faces=1, volume=0.0, area=0.0, style_id=None,
                 face_objects=None):
        GeometryObject.__init__(self, style_id)
        self.Edges = Collection(edges)
        self.Faces = Collection(face_objects if face_objects is not None
                                else [Face() for _ in range(faces)])
        self.Volume = volume
        self.SurfaceArea = area


class Mesh(GeometryObject):
    def __init__(self, vertices=(), triangles=0, style_id=None):
        GeometryObject.__init__(self, style_id)
        self.Vertices = Collection([_xyz(v) for v in vertices])
        self.NumTriangles = triangles


class Point(GeometryObject):
    def __init__(self, coord, style_id=None):
        GeometryObject.__init__(self, style_id)
        self.Coord = _xyz(coord)


class GeometryElement(list):
    """Revit's geometry container: iterable, nothing more."""


class GeometryInstance(GeometryObject):
    """A block reference. Its instance geometry is already in project coords."""

    def __init__(self, geometry, symbol=None, style_id=None):
        GeometryObject.__init__(self, style_id)
        self._geometry = GeometryElement(geometry)
        self.SymbolGeometry = self._geometry
        self.Symbol = symbol

    def GetInstanceGeometry(self):
        return self._geometry


# --- parameters and elements ------------------------------------------------

class StorageType(object):
    NoneType, Integer, Double, String, ElementId = ("None", "Integer", "Double",
                                                    "String", "ElementId")


class Category(object):
    def __init__(self, name):
        self.Name = name


class BuiltInParameter(object):
    """Only the parameters the readers ask for, as plain sentinel strings."""
    ALL_MODEL_MARK = "ALL_MODEL_MARK"
    FAMILY_TOP_LEVEL_PARAM = "FAMILY_TOP_LEVEL_PARAM"
    FAMILY_BASE_LEVEL_OFFSET_PARAM = "FAMILY_BASE_LEVEL_OFFSET_PARAM"
    FAMILY_TOP_LEVEL_OFFSET_PARAM = "FAMILY_TOP_LEVEL_OFFSET_PARAM"
    WALL_BASE_OFFSET = "WALL_BASE_OFFSET"
    WALL_USER_HEIGHT_PARAM = "WALL_USER_HEIGHT_PARAM"
    INSTANCE_STRUCT_USAGE_PARAM = "INSTANCE_STRUCT_USAGE_PARAM"
    PHASE_CREATED = "PHASE_CREATED"
    FAMILY_LEVEL_PARAM = "FAMILY_LEVEL_PARAM"
    SCHEDULE_LEVEL_PARAM = "SCHEDULE_LEVEL_PARAM"
    FAMILY_BASE_LEVEL_PARAM = "FAMILY_BASE_LEVEL_PARAM"
    WALL_BASE_CONSTRAINT = "WALL_BASE_CONSTRAINT"
    HOST_AREA_COMPUTED = "HOST_AREA_COMPUTED"
    HOST_VOLUME_COMPUTED = "HOST_VOLUME_COMPUTED"


class BuiltInCategory(object):
    """The categories stage C sweeps, plus nothing. A category absent from a
    Revit version is absent here too, which is the case the reader must skip."""
    OST_StructuralColumns = "OST_StructuralColumns"
    OST_Columns = "OST_Columns"
    OST_StructuralFraming = "OST_StructuralFraming"
    OST_Floors = "OST_Floors"
    OST_StructuralFoundation = "OST_StructuralFoundation"
    OST_Walls = "OST_Walls"
    OST_Grids = "OST_Grids"
    OST_Levels = "OST_Levels"
    OST_Stairs = "OST_Stairs"
    OST_GenericModel = "OST_GenericModel"


class Parameter(object):
    def __init__(self, value, storage=StorageType.Double):
        self._value = value
        self.StorageType = storage

    def AsDouble(self):
        if self.StorageType != StorageType.Double:
            return 0.0
        return float(self._value)

    def AsString(self):
        return None if self._value is None else str(self._value)

    def AsElementId(self):
        return self._value


class BoundingBoxXYZ(object):
    def __init__(self, low, high):
        self.Min = _xyz(low)
        self.Max = _xyz(high)


class LocationPoint(object):
    def __init__(self, point, rotation=0.0):
        self.Point = _xyz(point)
        self.Rotation = rotation


class LocationCurve(object):
    def __init__(self, curve):
        self.Curve = curve


class Element(object):
    """Enough of an element for the stage C sweep to describe it."""

    def __init__(self, element_id=1, name=None, category=None, bbox=None,
                 location=None, type_element=None, builtins=None,
                 lookups=None, level_id=None, pinned=False, geometry=None):
        self.Id = ElementId(element_id)
        self.Name = name
        self.Category = Category(category) if isinstance(category, str) else category
        self._geometry = GeometryElement(geometry or [])
        self._bbox = bbox
        self.Location = location
        self._type = type_element
        self._builtins = dict(builtins or {})
        self._lookups = dict(lookups or {})
        self.LevelId = level_id or ElementId.InvalidElementId
        self.Pinned = pinned
        self.GroupId = ElementId.InvalidElementId
        self.WorksetId = ElementId(0)

    def get_BoundingBox(self, _view):
        return self._bbox

    def get_Geometry(self, _options):
        return self._geometry

    def GetTypeId(self):
        return self._type.Id if self._type is not None else ElementId.InvalidElementId

    def get_Parameter(self, builtin):
        return self._builtins.get(builtin)

    def LookupParameter(self, name):
        return self._lookups.get(name)


class ElementType(Element):
    def __init__(self, element_id=100, name=None, family=None, lookups=None):
        Element.__init__(self, element_id=element_id, name=name, lookups=lookups)
        self.Family = family


class Family(object):
    def __init__(self, name):
        self.Name = name


class GraphicsStyleCategory(object):
    def __init__(self, name):
        self.Name = name


class GraphicsStyle(object):
    def __init__(self, name):
        self.GraphicsStyleCategory = GraphicsStyleCategory(name)


class Document(object):
    """A document that can resolve ids and hand back elements per category."""

    def __init__(self, title="stub model", by_category=None, elements=None):
        self.Title = title
        self._by_category = dict(by_category or {})
        self._elements = dict(elements or {})
        self._styles = {}
        # Auto-register every element and its TYPE. A type the document cannot
        # resolve makes every type parameter read as absent, which looks exactly
        # like a family that does not carry them -- a fixture mistake that
        # silently weakens whatever it was meant to prove.
        for elements_of_category in self._by_category.values():
            for element in elements_of_category:
                # Guarded: a fixture may deliberately contain an element that
                # raises on every access, to prove the sweep survives one.
                try:
                    self.register(element)
                    if element._type is not None:
                        self.register(element._type)
                except Exception:
                    continue

    def register_layer(self, name):
        """Create a graphics style for `name`; returns its ElementId."""
        style_id = ElementId(9000 + len(self._styles))
        self._styles[style_id.Value] = GraphicsStyle(name)
        return style_id

    def register(self, element):
        self._elements[element.Id.Value] = element
        return element

    def GetElement(self, element_id):
        if element_id is None or element_id == ElementId.InvalidElementId:
            return None
        if element_id.Value in self._styles:
            return self._styles[element_id.Value]
        return self._elements.get(element_id.Value)

    def elements_of(self, category):
        return self._by_category.get(category, [])


class ImportInstance(object):
    def __init__(self, geometry, transform=None):
        self._geometry = GeometryElement(geometry)
        self._transform = transform
        self.Id = ElementId(500)
        self.IsLinked = True

    def get_Geometry(self, _options):
        return self._geometry

    def GetTotalTransform(self):
        return self._transform

    def GetTypeId(self):
        return ElementId.InvalidElementId


class Transform(object):
    def __init__(self, basis_x=(1, 0, 0), basis_y=(0, 1, 0), basis_z=(0, 0, 1),
                 origin=(0, 0, 0)):
        self.BasisX = _xyz(basis_x)
        self.BasisY = _xyz(basis_y)
        self.BasisZ = _xyz(basis_z)
        self.Origin = _xyz(origin)


class FilteredElementCollector(object):
    """Only the chain the sweep uses: OfCategory / WhereElementIsNotElementType."""

    def __init__(self, document):
        self._document = document
        self._category = None

    def OfCategory(self, category):
        self._category = category
        return self

    def WhereElementIsNotElementType(self):
        return self

    def ToElements(self):
        return list(self._document.elements_of(self._category))


# --- installation -----------------------------------------------------------

_EXPORTS = (
    "XYZ", "ElementId", "Options", "ViewDetailLevel", "GeometryObject", "Curve",
    "Line", "Arc", "NurbSpline", "PolyLine", "Edge", "Face", "Solid", "Mesh",
    "Point", "GeometryElement", "GeometryInstance", "StorageType",
    "PlanarFace", "CurveLoop",
    "BuiltInParameter", "BuiltInCategory", "Parameter", "BoundingBoxXYZ",
    "LocationPoint", "LocationCurve", "Element", "ElementType", "Family",
    "GraphicsStyle", "GraphicsStyleCategory", "Document", "ImportInstance",
    "Category",
    "Transform", "FilteredElementCollector",
)


def install():
    """Put the stub on sys.modules as Autodesk.Revit.DB. Idempotent.

    Must run BEFORE the reader modules are imported, since both do a top-level
    `from Autodesk.Revit.DB import ...`.
    """
    autodesk = sys.modules.get("Autodesk") or types.ModuleType("Autodesk")
    revit = sys.modules.get("Autodesk.Revit") or types.ModuleType("Autodesk.Revit")
    db = sys.modules.get("Autodesk.Revit.DB") or types.ModuleType("Autodesk.Revit.DB")
    here = sys.modules[__name__]
    for name in _EXPORTS:
        setattr(db, name, getattr(here, name))
    revit.DB = db
    autodesk.Revit = revit
    sys.modules["Autodesk"] = autodesk
    sys.modules["Autodesk.Revit"] = revit
    sys.modules["Autodesk.Revit.DB"] = db
    return db


# --- builders ---------------------------------------------------------------
# Fixtures read as drawings rather than as object graphs.

def line(start, end, style_id=None, length=None):
    return Line([start, end], style_id=style_id, length=length)


def arc(start, mid, end, style_id=None):
    return Arc([start, mid, end], style_id=style_id)


def unbound_circle(points, style_id=None):
    """A closed unbound curve: no endpoints, but it tessellates."""
    return Curve(points, style_id=style_id, bound=False, closed=True)


def unbound_line(style_id=None):
    """An infinite construction line: no endpoints and not closed.

    cad2bim's reader skips these, and the audit's raw pass records them with a
    note saying so -- which is a behaviour worth pinning.
    """
    return Curve([(0, 0, 0), (1, 0, 0)], style_id=style_id, bound=False,
                 closed=False)


def polyline(points, style_id=None):
    return PolyLine(points, style_id=style_id)


def ring(points):
    """A CurveLoop around `points`, closing back to the first."""
    closed = list(points) + [points[0]]
    return CurveLoop([Line([a, b]) for a, b in zip(closed, closed[1:])])


def flat_solid(outline, holes=(), style_id=None, volume=0.0, area=None):
    """What an imported hatch becomes: a flat solid with one horizontal face.

    `holes` become inner loops on that face -- the Revit-side counterpart of a
    DXF hatch's islands, and the reason the reader counts loops.
    """
    loops = [ring(outline)] + [ring(hole) for hole in holes]
    footprint = PlanarFace(normal=(0, 0, 1), area=area or 0.0, loops=loops)
    side = PlanarFace(normal=(1, 0, 0), area=0.0, loops=[])
    edges = [Edge([a, b]) for a, b in zip(outline, outline[1:] + outline[:1])]
    return Solid(edges=edges, volume=volume, area=area or 0.0,
                 style_id=style_id, face_objects=[footprint, side])


def solid_box(low, high, style_id=None, volume=1.0, area=6.0, faces=6):
    """A solid outlined by the four edges of its plan footprint."""
    (x0, y0, z0), (x1, y1, z1) = low, high
    edges = [
        Edge([(x0, y0, z0), (x1, y0, z0)]),
        Edge([(x1, y0, z0), (x1, y1, z0)]),
        Edge([(x1, y1, z0), (x0, y1, z0)]),
        Edge([(x0, y1, z0), (x0, y0, z0)]),
        Edge([(x0, y0, z1), (x1, y1, z1)]),
    ]
    return Solid(edges=edges, faces=faces, volume=volume, area=area,
                 style_id=style_id)


def column(element_id, low, high, name="C 400x400", family="Concrete-Rectangular",
           mark=None, level=None, rotation=0.0, b_mm=None, h_mm=None):
    """A structural column: a bounding box, a location point and a type."""
    from_mm = 1.0 / 304.8
    lookups = {}
    if b_mm:
        lookups["b"] = Parameter(b_mm * from_mm)
    if h_mm:
        lookups["h"] = Parameter(h_mm * from_mm)
    element_type = ElementType(element_id=element_id + 1000, name=name,
                               family=Family(family), lookups=lookups)
    centre = ((low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0, low[2])
    return Element(
        element_id=element_id, name=name,
        bbox=BoundingBoxXYZ(low, high),
        location=LocationPoint(centre, rotation),
        type_element=element_type,
        builtins={BuiltInParameter.ALL_MODEL_MARK: Parameter(mark,
                                                             StorageType.String)},
        level_id=level.Id if level is not None else None,
    )


def beam(element_id, start, end, name="B 230x450", family="Concrete-Rectangular",
         mark=None, level=None):
    element_type = ElementType(element_id=element_id + 1000, name=name,
                               family=Family(family))
    low = (min(start[0], end[0]), min(start[1], end[1]), start[2])
    high = (max(start[0], end[0]), max(start[1], end[1]), end[2])
    return Element(
        element_id=element_id, name=name,
        bbox=BoundingBoxXYZ(low, high),
        location=LocationCurve(Line([start, end])),
        type_element=element_type,
        builtins={BuiltInParameter.ALL_MODEL_MARK: Parameter(mark,
                                                             StorageType.String)},
        level_id=level.Id if level is not None else None,
    )


def level(element_id, name):
    return Element(element_id=element_id, name=name)


def _bbox_of(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return BoundingBoxXYZ((min(xs), min(ys), 0.0), (max(xs), max(ys), 0.0))


def shaped_column(element_id, outline, name="C 400x400",
                  family="Concrete-Rectangular", mark=None, level=None,
                  rotation=0.0, b_mm=None, h_mm=None, category="Structural Columns"):
    """A column whose real SECTION is `outline` -- rotated, L-shaped, whatever.

    The bounding box is derived from that outline, so a fixture cannot
    accidentally describe a shape its own box contradicts.
    """
    from_mm = 1.0 / 304.8
    lookups = {}
    if b_mm:
        lookups["b"] = Parameter(b_mm * from_mm)
    if h_mm:
        lookups["h"] = Parameter(h_mm * from_mm)
    element_type = ElementType(element_id=element_id + 1000, name=name,
                               family=Family(family), lookups=lookups)
    centre = (sum(p[0] for p in outline) / len(outline),
              sum(p[1] for p in outline) / len(outline), 0.0)
    return Element(
        element_id=element_id, name=name, category=category,
        bbox=_bbox_of(outline),
        location=LocationPoint(centre, rotation),
        type_element=element_type,
        geometry=[flat_solid(outline, volume=1.0)],
        builtins={BuiltInParameter.ALL_MODEL_MARK: Parameter(mark,
                                                             StorageType.String)},
        level_id=level.Id if level is not None else None,
    )


def floor(element_id, outline, openings=(), name="Slab 200",
          family="Floor", mark=None, level=None, thickness_mm=None,
          area_ft2=None, category="Floors"):
    """A slab with a real -- possibly L-shaped -- outline and real openings."""
    from_mm = 1.0 / 304.8
    lookups = {}
    if thickness_mm:
        lookups["Thickness"] = Parameter(thickness_mm * from_mm)
    element_type = ElementType(element_id=element_id + 1000, name=name,
                               family=Family(family), lookups=lookups)
    builtins = {BuiltInParameter.ALL_MODEL_MARK: Parameter(mark, StorageType.String)}
    if area_ft2 is not None:
        builtins[BuiltInParameter.HOST_AREA_COMPUTED] = Parameter(area_ft2)
    return Element(
        element_id=element_id, name=name, category=category,
        bbox=_bbox_of(outline), type_element=element_type,
        geometry=[flat_solid(outline, holes=list(openings), volume=1.0)],
        builtins=builtins,
        level_id=level.Id if level is not None else None,
    )
