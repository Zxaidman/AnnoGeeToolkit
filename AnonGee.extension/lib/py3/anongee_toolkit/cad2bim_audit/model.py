# -*- coding: utf-8 -*-
"""One row shape for all four stages.

The whole report rests on this: a DXF LWPOLYLINE, a Revit link Solid, a placed
structural column and a line in cad2bim's JSON all become an `AuditItem`, so the
matcher, the findings and the workbook are written once instead of four times.
The alternative -- a class per source -- means every new check has to be taught
about four shapes, and the ones it is not taught about are exactly where a bug
hides.

What is deliberately NOT normalised is the native detail: `source_type` keeps
the real type name ("LWPOLYLINE", "Solid", "FamilyInstance") and `extra` keeps
whatever only that source has. A normalisation that discarded them would throw
away the evidence the report exists to show.

Plain classes, no dataclasses, matching the house style in `cad2bim.model` so a
reader moving between the two packages sees the same idiom.
"""

from . import config, geometry

#: Display key for an item whose layer could not be resolved. Same spelling as
#: `cad2bim.model.NO_LAYER`, so the two packages' layer tables line up.
NO_LAYER = "<no layer>"


class AuditItem(object):
    """One thing, as seen by one stage.

    Positions are millimetres. `points_dxf` and `points_revit` hold the SAME
    geometry in the two report spaces; whichever was measured rather than
    derived is named by `native_space` ("dxf" or "revit"). Either may be None
    when no transform was available to derive it -- the report then leaves those
    columns blank rather than inventing a number.
    """

    def __init__(self, stage, kind, source_type=None, layer=None, handle=None,
                 points_dxf=None, points_revit=None, native_space="dxf",
                 category=None, text=None, mark=None, level=None,
                 type_name=None, extra=None, notes=None):
        self.stage = stage              # one of config.STAGES
        self.kind = kind                # normalised: "curve", "text", "hatch", "solid", ...
        self.source_type = source_type  # native type name, verbatim
        self.layer = layer              # CAD layer, or Revit category name
        self.handle = handle            # DXF handle or Revit element id, as a string
        self.points_dxf = points_dxf    # [(x, y, z)] mm in DXF space, or None
        self.points_revit = points_revit
        self.native_space = native_space
        self.category = category        # cad2bim's classified category, or None
        self.text = text                # for text items
        self.mark = mark                # parsed mark ("C1"), where one is known
        self.level = level              # Revit level name, or None
        self.type_name = type_name      # family:type, or DXF pattern name
        self.extra = extra or {}        # anything only this source has
        self.notes = list(notes or [])  # read errors and caveats, shown in the report

    # -- keys ---------------------------------------------------------------
    @property
    def layer_key(self):
        return self.layer if self.layer else NO_LAYER

    @property
    def points(self):
        """The measured points -- the ones to compute geometry from.

        Always prefers the native space, so a derived-coordinate error can never
        propagate into a size or a length the report quotes as measured.
        """
        if self.native_space == "revit":
            return self.points_revit or self.points_dxf or []
        return self.points_dxf or self.points_revit or []

    # -- derived geometry, in the space the item was measured in -------------
    @property
    def centroid(self):
        return geometry.centroid(self.points)

    @property
    def centroid_dxf(self):
        return geometry.centroid(self.points_dxf or [])

    @property
    def centroid_revit(self):
        return geometry.centroid(self.points_revit or [])

    @property
    def plan_size_mm(self):
        """(short, long) plan extent in mm, or None."""
        return geometry.plan_size(self.points)

    @property
    def length_mm(self):
        """Explicit length if the source gave one, else the path length."""
        given = self.extra.get("length_mm")
        return given if given is not None else geometry.path_length(self.points)

    @property
    def area_mm2(self):
        given = self.extra.get("area_mm2")
        return given if given is not None else geometry.polygon_area(self.points)

    @property
    def rotation_deg(self):
        """Explicit rotation if the source gave one, else the principal axis."""
        given = self.extra.get("rotation_deg")
        if given is not None:
            return float(given) % 180.0
        return geometry.principal_angle_deg(self.points)

    def note(self, message):
        """Record a caveat. Returns self so a reader can note-and-append inline."""
        self.notes.append(message)
        return self

    def to_dict(self, max_points=None):
        """Plain data for the JSON sidecar. Point lists are capped by the caller."""
        limit = max_points if max_points is not None else len(self.points)
        return {
            "stage": self.stage,
            "kind": self.kind,
            "source_type": self.source_type,
            "layer": self.layer,
            "handle": self.handle,
            "category": self.category,
            "text": self.text,
            "mark": self.mark,
            "level": self.level,
            "type_name": self.type_name,
            "native_space": self.native_space,
            "centroid_dxf_mm": _round_point(self.centroid_dxf),
            "centroid_revit_mm": _round_point(self.centroid_revit),
            "plan_size_mm": _round_pair(self.plan_size_mm),
            "length_mm": _round(self.length_mm),
            "area_mm2": _round(self.area_mm2),
            "rotation_deg": _round(self.rotation_deg),
            "points_dxf_mm": _round_points(self.points_dxf, limit),
            "points_revit_mm": _round_points(self.points_revit, limit),
            "extra": self.extra,
            "notes": self.notes,
        }

    def __repr__(self):
        return "<AuditItem {0} {1} layer={2!r} pts={3}>".format(
            self.stage, self.kind, self.layer, len(self.points))


class Capture(object):
    """Everything one stage read, plus how the reading went.

    `errors` matters as much as `items`. cad2bim's DXF reader swallows a
    malformed entity in a bare `except: continue`, so a drawing can lose members
    with nothing anywhere saying so. Here a failed read is a recorded row.
    """

    def __init__(self, stage, source_name=None, items=None, errors=None,
                 skipped=None, meta=None):
        self.stage = stage
        self.source_name = source_name or ""
        self.items = list(items or [])
        self.errors = list(errors or [])    # [{"where":..., "detail":...}]
        # Entity types the reader saw and deliberately did not turn into items,
        # as {type_name: count} -- the honest record of what was left behind.
        self.skipped = dict(skipped or {})
        self.meta = dict(meta or {})        # anything stage-specific for the report

    def add(self, item):
        self.items.append(item)
        return item

    def fail(self, where, detail):
        self.errors.append({"where": where, "detail": str(detail)})

    def skip(self, type_name):
        self.skipped[type_name] = self.skipped.get(type_name, 0) + 1

    def by_kind(self):
        counts = {}
        for item in self.items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts

    def by_layer(self):
        counts = {}
        for item in self.items:
            counts[item.layer_key] = counts.get(item.layer_key, 0) + 1
        return counts

    def by_source_type(self):
        counts = {}
        for item in self.items:
            key = item.source_type or item.kind
            counts[key] = counts.get(key, 0) + 1
        return counts

    def is_empty(self):
        return not self.items

    def to_dict(self, max_points=None):
        return {
            "stage": self.stage,
            "label": config.STAGE_LABELS.get(self.stage, self.stage),
            "source_name": self.source_name,
            "item_count": len(self.items),
            "by_kind": self.by_kind(),
            "by_source_type": self.by_source_type(),
            "skipped": self.skipped,
            "errors": self.errors,
            "meta": self.meta,
            "items": [item.to_dict(max_points) for item in self.items],
        }

    def __repr__(self):
        return "<Capture {0} items={1} errors={2}>".format(
            self.stage, len(self.items), len(self.errors))


def _round(value, places=2):
    return None if value is None else round(float(value), places)


def _round_point(point, places=2):
    return None if point is None else [round(float(v), places) for v in point]


def _round_pair(pair, places=2):
    return None if pair is None else [round(float(v), places) for v in pair]


def _round_points(points, limit, places=2):
    if not points:
        return None
    return [[round(float(v), places) for v in p] for p in points[:limit]]
