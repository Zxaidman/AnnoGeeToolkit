# -*- coding: utf-8 -*-
"""A sheet per structural category, in the units that category is argued about.

The Reconciliation sheet is deliberately uniform: one row shape for every
member, so it can be scanned whole. That uniformity is exactly what makes it the
wrong sheet for chasing one category's bug, because the columns it can afford to
carry are the ones that mean something for all seven -- and almost nothing means
the same thing for a column and a slab.

A column is argued about in b x h and a rotation. A beam is argued about in
width, depth and RUN -- and its bounding box IS its run, so a "size" column for
a beam is a length column wearing the wrong label. A slab is argued about in
area and thickness, and has no b x h at all. Each sheet therefore carries that
category's own measurements, drawing beside built, with the delta already
computed so nobody has to subtract two columns by eye to find the problem.

Spec-driven: a category is a list of (header, extractor) pairs, and an extractor
is a function of one `_Row`. Adding a column is one line, and the shared frame --
identity, per-stage counts, position, notes -- is written once rather than seven
times.

Revit-free.
"""

from . import config, geometry, matching
from .sheets import Sheet

#: Identity and provenance, on every category sheet. Same leading columns as the
#: Reconciliation sheet, so a reader moving between them is not re-learning.
_LEAD = ["verdict", "severity", "level", "layer", "mark",
         "A_dxf_raw", "A_dxf_parsed", "B_link_raw", "B_link_parsed",
         "D_intent", "C_model"]

#: Where to go and look, on every category sheet.
_TAIL = ["offset_mm", "x_dxf_mm", "y_dxf_mm", "x_revit_mm", "y_revit_mm",
         "built_type", "notes"]

_M2 = 1.0e6      # mm^2 in one m^2


class _Row(object):
    """One group, with its stages resolved once so extractors stay one-liners."""

    __slots__ = ("group", "verdict", "space_key", "source", "target",
                 "source_item", "target_item")

    def __init__(self, group, verdict, space_key):
        self.group = group
        self.verdict = verdict
        self.space_key = space_key
        self.source = _first(group, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                                     config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED))
        self.target = _first(group, (config.STAGE_MODEL, config.STAGE_INTENT))
        self.source_item = group.first(self.source) if self.source else None
        self.target_item = group.first(self.target) if self.target else None

    # -- sizes -------------------------------------------------------------
    @property
    def drawing_size(self):
        return self.group.size_mm(self.source) if self.source else None

    @property
    def built_size(self):
        return self.group.size_mm(self.target) if self.target else None

    def size_delta(self):
        drawing, built = self.drawing_size, self.built_size
        if not drawing or not built:
            return None
        return round(max(abs(drawing[0] - built[0]), abs(drawing[1] - built[1])), 1)

    # -- lengths -----------------------------------------------------------
    def drawing_length(self):
        """The run as drawn -- summed, because a drawing can split it too."""
        return _round(self.group.total_length_mm(self.source)
                      if self.source else None)

    def built_length(self):
        """The run as built, SUMMED over its segments.

        cad2bim splits a beam at every column it crosses, so one drawn beam is
        several placed segments. Reporting the first segment's length against
        the drawn run would report every correctly-built beam as badly clipped.
        """
        return _round(self.group.total_length_mm(self.target)
                      if self.target else None)

    def segments(self, stage):
        return self.group.count(stage) if stage else None

    def length_delta(self):
        drawing, built = self.drawing_length(), self.built_length()
        if drawing is None or built is None:
            return None
        return round(abs(drawing - built), 1)

    # -- areas -------------------------------------------------------------
    def drawing_area(self):
        return _round(self.source_item.area_mm2 / _M2 if self.source_item else None, 3)

    def built_area(self):
        item = self.target_item
        if item is None:
            return None
        # A placed floor reports its own area; a cad2bim rectangle does not, so
        # its ring area stands in. Both are m^2 and both are the thing a person
        # compares against the drawing.
        area = item.extra.get("area_mm2")
        return _round((area if area is not None else item.area_mm2) / _M2, 3)

    def area_delta_pct(self):
        drawing, built = self.drawing_area(), self.built_area()
        if not drawing or built is None:
            return None
        return round(abs(drawing - built) / drawing * 100.0, 1)

    # -- other -------------------------------------------------------------
    def thickness(self):
        item = self.target_item
        if item is None:
            return None
        for key in ("type_h_mm", "instance_h_mm", "h_mm"):
            value = item.extra.get(key)
            if value:
                return _round(value)
        return None

    def rotation(self, item):
        return _round(item.rotation_deg if item is not None else None)

    def rotation_delta(self):
        if self.source_item is None or self.target_item is None:
            return None
        return _round(geometry.angle_delta_deg(self.source_item.rotation_deg,
                                               self.target_item.rotation_deg), 2)

    def offset(self):
        if self.source_item is None or self.target_item is None:
            return None
        a = matching.match_point(self.source_item, self.space_key)
        b = matching.match_point(self.target_item, self.space_key)
        if a is None or b is None:
            return None
        return _round(geometry.plan_distance((a[0], a[1], 0.0), (b[0], b[1], 0.0)))

    def extra(self, key):
        for item in (self.target_item, self.source_item):
            if item is not None and item.extra.get(key) is not None:
                return item.extra[key]
        return None


#: The measurements that matter, per category sheet. Order is the order a person
#: reads them in: what the drawing said, what got built, then the difference.
SPECS = {
    "Columns": [
        ("drawing_b_mm", lambda r: _at(r.drawing_size, 0)),
        ("drawing_h_mm", lambda r: _at(r.drawing_size, 1)),
        ("built_b_mm", lambda r: _at(r.built_size, 0)),
        ("built_h_mm", lambda r: _at(r.built_size, 1)),
        ("size_delta_mm", lambda r: r.size_delta()),
        ("rotation_drawing_deg", lambda r: r.rotation(r.source_item)),
        ("rotation_built_deg", lambda r: r.rotation(r.target_item)),
        ("rotation_delta_deg", lambda r: r.rotation_delta()),
        ("shape", lambda r: r.extra("shape") or "rectangular"),
        ("diameter_mm", lambda r: _round(r.extra("diameter_mm"))),
    ],
    "Beams": [
        # Width and depth, never "size": a beam's bounding box is its RUN, so a
        # size column here would be a length column under the wrong heading.
        ("drawing_width_mm", lambda r: _at(r.drawing_size, 0)),
        ("built_width_mm", lambda r: _round(r.extra("b_mm") or r.extra("type_b_mm"))),
        ("built_depth_mm", lambda r: _round(r.extra("h_mm") or r.extra("type_h_mm"))),
        ("drawing_length_mm", lambda r: r.drawing_length()),
        ("built_length_mm", lambda r: r.built_length()),
        ("length_delta_mm", lambda r: r.length_delta()),
        # One drawn beam becomes several placed ones wherever it crosses a
        # column. This column is how "built as 5 pieces" reads as the normal
        # outcome it is, rather than as four beams nobody drew.
        ("built_segments", lambda r: r.segments(r.target)),
        ("angle_drawing_deg", lambda r: r.rotation(r.source_item)),
        ("angle_built_deg", lambda r: r.rotation(r.target_item)),
    ],
    "Slabs": [
        ("drawing_area_m2", lambda r: r.drawing_area()),
        ("built_area_m2", lambda r: r.built_area()),
        ("area_delta_pct", lambda r: r.area_delta_pct()),
        ("thickness_mm", lambda r: r.thickness()),
        ("boundary_vertices", lambda r: (len(r.source_item.points)
                                         if r.source_item else None)),
        ("hatch_islands", lambda r: r.extra("island_count")),
    ],
    "Footings": [
        ("drawing_short_mm", lambda r: _at(r.drawing_size, 0)),
        ("drawing_long_mm", lambda r: _at(r.drawing_size, 1)),
        ("built_short_mm", lambda r: _at(r.built_size, 0)),
        ("built_long_mm", lambda r: _at(r.built_size, 1)),
        ("size_delta_mm", lambda r: r.size_delta()),
        ("thickness_mm", lambda r: r.thickness()),
        ("drawing_area_m2", lambda r: r.drawing_area()),
        ("built_area_m2", lambda r: r.built_area()),
    ],
    "Walls": [
        ("drawing_length_mm", lambda r: r.drawing_length()),
        ("built_length_mm", lambda r: r.built_length()),
        ("length_delta_mm", lambda r: r.length_delta()),
        ("built_segments", lambda r: r.segments(r.target)),
        ("thickness_mm", lambda r: r.thickness()),
        ("angle_drawing_deg", lambda r: r.rotation(r.source_item)),
        ("angle_built_deg", lambda r: r.rotation(r.target_item)),
    ],
    "Stairs": [
        ("drawing_short_mm", lambda r: _at(r.drawing_size, 0)),
        ("drawing_long_mm", lambda r: _at(r.drawing_size, 1)),
        ("built_short_mm", lambda r: _at(r.built_size, 0)),
        ("built_long_mm", lambda r: _at(r.built_size, 1)),
        ("drawing_area_m2", lambda r: r.drawing_area()),
        ("built_area_m2", lambda r: r.built_area()),
    ],
    "Grids": [
        ("name", lambda r: _mark(r.group)),
        ("drawing_length_mm", lambda r: r.drawing_length()),
        ("built_length_mm", lambda r: r.built_length()),
        ("length_delta_mm", lambda r: r.length_delta()),
        ("direction_deg", lambda r: r.rotation(r.source_item or r.target_item)),
        ("orientation", lambda r: _orientation(r)),
    ],
}


def build(report):
    """One Sheet per entry in `config.CATEGORY_SHEETS`, in that order."""
    space_key = report.diagnostics.get("space", "revit")
    sheets = []
    for name, keys in config.CATEGORY_SHEETS:
        spec = SPECS.get(name, [])
        columns = _LEAD + [header for header, _get in spec] + _TAIL
        rows = []
        for group, verdict in zip(report.groups, report.verdicts):
            if group.category not in keys:
                continue
            rows.append(_row(group, verdict, spec, space_key))
        rows.sort(key=lambda row: _sort_key(row, len(_LEAD) + len(spec)))
        sheet = Sheet(name, columns, rows)
        sheet.notes.append(_note(name, keys))
        if not rows:
            sheet.notes.append(
                "No {0} were matched in this run.".format(name.lower()))
        sheets.append(sheet)
    return sheets


def _row(group, verdict, spec, space_key):
    context = _Row(group, verdict, space_key)
    dxf = _centroid(group, "dxf")
    revit = _centroid(group, "revit")
    lead = [
        verdict, config.severity_of(verdict), group.level, _layer(group),
        _mark(group),
        group.count(config.STAGE_DXF_RAW), group.count(config.STAGE_DXF_PARSED),
        group.count(config.STAGE_LINK_RAW), group.count(config.STAGE_LINK_PARSED),
        group.count(config.STAGE_INTENT), group.count(config.STAGE_MODEL),
    ]
    middle = [_safe(get, context) for _header, get in spec]
    tail = [
        context.offset(),
        _coord(dxf, 0), _coord(dxf, 1), _coord(revit, 0), _coord(revit, 1),
        getattr(context.target_item, "type_name", None),
        _notes(group),
    ]
    return lead + middle + tail


def _sort_key(row, tail_start):
    """Worst first, then by position -- so two runs of one drawing diff cleanly.

    Position falls back to DXF space for the same reason the Reconciliation
    sheet's does: a run with no Revit link has no Revit coordinates, and sorting
    on a column of blanks leaves the sheet in read order.
    """
    x_revit, y_revit = row[tail_start + 3], row[tail_start + 4]
    x_dxf, y_dxf = row[tail_start + 1], row[tail_start + 2]
    x = x_revit if x_revit is not None else x_dxf
    y = y_revit if y_revit is not None else y_dxf
    return (config.SEVERITY_ORDER.get(row[1], 9), str(row[0]),
            x if isinstance(x, (int, float)) else 0.0,
            y if isinstance(y, (int, float)) else 0.0)


_NOTES = {
    "Columns": "Sizes prefer the type's own b/h over the bounding box, which "
               "over-reports a rotated member; rotation_delta_deg is folded to "
               "[0, 90] so a member drawn end-for-end is not 180 degrees wrong.",
    "Beams": "A beam's bounding box IS its run, so this sheet reports width and "
             "depth separately from length. Lengths are SUMMED over segments: "
             "cad2bim splits a beam at every column it crosses, so "
             "built_segments above one is normal. length_delta_mm is where a "
             "junction clip or a merge shows up.",
    "Slabs": "hatch_islands above zero means the drawing shows a hole the built "
             "slab may not have: cad2bim keeps only a hatch's outer ring.",
    "Footings": "Thickness comes from the type's Thickness/Depth parameter where "
                "the family carries one.",
    "Walls": "Length is the location curve's, so a wall split into segments "
             "reports each segment rather than the run.",
    "Stairs": "Stairs reconcile as an extent rather than a section; treads and "
              "risers are not read from the drawing.",
    "Grids": "direction_deg is folded to [0, 180); orientation names the axis a "
             "grid line runs along.",
}


def _note(name, keys):
    base = _NOTES.get(name, "")
    return "{0}  Categories on this sheet: {1}.".format(base, ", ".join(keys))


def _orientation(row):
    angle = row.rotation(row.source_item or row.target_item)
    if angle is None:
        return None
    if angle < 15.0 or angle > 165.0:
        return "horizontal"
    if 75.0 < angle < 105.0:
        return "vertical"
    return "skew"


def _safe(get, context):
    """An extractor that raises costs its own cell, never the row.

    A category sheet is a diagnostic like everything else here: one member with
    odd geometry must not take the other four hundred down with it.
    """
    try:
        return get(context)
    except Exception:
        return None


def _first(group, stages):
    for stage in stages:
        if group.has(stage):
            return stage
    return None


def _centroid(group, space):
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is None:
            continue
        point = item.centroid_revit if space == "revit" else item.centroid_dxf
        if point is not None:
            return point
    return None


def _layer(group):
    item = group.any_item()
    return item.layer_key if item is not None else None


def _mark(group):
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is not None and item.mark:
            return item.mark
    return None


def _notes(group):
    seen = []
    for stage in matching.FOLD_ORDER:
        for item in group.by_stage.get(stage, ()):
            for note in item.notes:
                if note not in seen:
                    seen.append(note)
    return "; ".join(seen)


def _at(pair, index):
    return None if not pair else round(float(pair[index]), 1)


def _coord(point, index):
    return None if point is None else round(float(point[index]), 1)


def _round(value, places=1):
    return None if value is None else round(float(value), places)
