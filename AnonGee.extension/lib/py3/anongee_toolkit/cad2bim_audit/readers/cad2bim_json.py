# -*- coding: utf-8 -*-
"""Stage D: what a cad2bim run believed it had built.

Parses the JSON `cad2bim.export` writes. This is the stage that turns "the
column is not in the model" from one fact into three distinguishable ones:

    in A, not in B      Revit's import dropped or merged it
    in B, not in D      classification or a builder gate declined it
    in D, not in C      cad2bim asked Revit to place it and Revit did not

Without it, all three look identical, and they have completely different fixes.

The schema is cad2bim's, read defensively: every field is optional and a shape
that does not parse becomes an error row rather than an exception. This module
is a CONSUMER of that schema and must never constrain it -- if a future cad2bim
adds a key, the audit ignores it; if it drops one, the audit reports a blank
column, and neither outcome may break a run.

Positions in that file are Revit-internal-feet converted to whole millimetres
(`export._mm`), so this stage is native to Revit space and its DXF-space columns
are derived through the inverse link transform.

Revit-free.
"""

import json
import os

from .. import config
from ..model import AuditItem, Capture

#: Where a stage D item came from in the payload. "placed" rows are the ones the
#: reconciliation matches; "builder_input" rows are the geometry the builders were
#: handed, kept for diagnosis but never matched (they are stage B geometry
#: travelling under a stage D passport, and matching them would double-count).
ROLE_PLACED = "placed"
ROLE_BUILDER_INPUT = "builder_input"


def read(json_path, space, settings=None, include_builder_input=True):
    """Parse a cad2bim export into a Capture. Handles single- and multi-storey."""
    values = config.settings(settings)
    capture = Capture(config.STAGE_INTENT, os.path.basename(json_path or ""))

    if not json_path or not os.path.exists(json_path):
        capture.fail("open", "cad2bim JSON not found: {0}".format(json_path))
        return capture
    try:
        with open(json_path) as handle:
            payload = json.load(handle)
    except Exception as error:
        capture.fail("parse", error)
        return capture

    capture.meta["cad2bim_version"] = payload.get("cad2bim_version")
    capture.meta["units"] = payload.get("units")
    capture.source_name = payload.get("source") or capture.source_name

    storeys = payload.get("storeys")
    if isinstance(storeys, list) and storeys:
        capture.meta["storey_count"] = len(storeys)
        for section in storeys:
            _read_storey(section, section.get("storey"), space, capture, values,
                         include_builder_input)
    else:
        _read_storey(payload, None, space, capture, values, include_builder_input)

    capture.meta["placed_items"] = sum(
        1 for item in capture.items if item.extra.get("role") == ROLE_PLACED)
    return capture


def _read_storey(section, storey, space, capture, values, include_builder_input):
    """One storey section (or a whole single-storey payload)."""
    if not isinstance(section, dict):
        capture.fail("storey", "expected an object, got {0}".format(type(section).__name__))
        return

    _read_columns(section.get("columns") or {}, storey, space, capture)
    _read_beams(section.get("beams") or {}, storey, space, capture)
    _read_texts(section.get("texts_sized") or [], storey, space, capture)
    if include_builder_input:
        _read_builder_input((section.get("beams") or {}).get("raw_geometry") or [],
                            storey, space, capture, values)

    # Slabs, footings, stairs and grids are reported by cad2bim as OUTCOME
    # COUNTS, not as per-item geometry -- so they cannot become rows. They are
    # kept as meta and shown on the Summary sheet, where a count that disagrees
    # with stage C is still a finding even though no row can carry it.
    outcomes = {}
    for key in ("grids", "slabs", "stairs", "footings", "walls"):
        value = section.get(key)
        if isinstance(value, dict):
            outcomes[key] = value
    if outcomes:
        capture.meta.setdefault("outcomes", {})[_storey_key(storey)] = outcomes
    comparison = section.get("comparison")
    if isinstance(comparison, dict):
        capture.meta.setdefault("comparison", {})[_storey_key(storey)] = comparison


def _read_columns(columns, storey, space, capture):
    for entry in columns.get("items") or []:
        try:
            capture.add(_column_item(entry, storey, space))
        except Exception as error:
            capture.fail("column {0}".format(entry), error)
    for entry in columns.get("circles") or []:
        try:
            capture.add(_circle_item(entry, storey, space))
        except Exception as error:
            capture.fail("circle {0}".format(entry), error)
    # `dropped_raw` is cad2bim's own record of geometry it looked at and refused.
    # It is the most direct evidence there is of a deliberate non-placement.
    for entry in columns.get("dropped_raw") or []:
        capture.meta.setdefault("dropped_raw", []).append(
            {"storey": storey, "entry": entry})


def _column_item(entry, storey, space):
    b = _number(entry.get("b"))
    h = _number(entry.get("h"))
    x = _number(entry.get("x"))
    y = _number(entry.get("y"))
    angle = _number(entry.get("deg")) or 0.0
    corners_mm = _rectangle_mm(x, y, b, h, angle)
    item = _item("element", "column", storey, space, corners_mm)
    item.mark = entry.get("mark")
    item.extra["b_mm"] = b
    item.extra["h_mm"] = h
    item.extra["rotation_deg"] = angle % 180.0 if angle is not None else None
    item.extra["size_source"] = "cad2bim_rectangle"
    return item


def _circle_item(entry, storey, space):
    diameter = _number(entry.get("dia"))
    x = _number(entry.get("x"))
    y = _number(entry.get("y"))
    corners_mm = _rectangle_mm(x, y, diameter, diameter, 0.0)
    item = _item("element", "column", storey, space, corners_mm)
    item.extra["diameter_mm"] = diameter
    item.extra["b_mm"] = diameter
    item.extra["h_mm"] = diameter
    item.extra["shape"] = "circle"
    item.extra["size_source"] = "cad2bim_circle"
    return item


def _read_beams(beams, storey, space, capture):
    for entry in beams.get("items") or []:
        try:
            points = [(_number(entry.get("x1")), _number(entry.get("y1")), 0.0),
                      (_number(entry.get("x2")), _number(entry.get("y2")), 0.0)]
            item = _item("element", "beam", storey, space, points)
            item.mark = entry.get("mark")
            item.extra["b_mm"] = _number(entry.get("w"))
            item.extra["h_mm"] = _number(entry.get("d"))
            item.extra["length_mm"] = _number(entry.get("len"))
            capture.add(item)
        except Exception as error:
            capture.fail("beam {0}".format(entry), error)


def _read_texts(texts, storey, space, capture):
    for entry in texts:
        try:
            x = _number(entry.get("x"))
            y = _number(entry.get("y"))
            points = [(x, y, 0.0)] if x is not None and y is not None else []
            item = _item("text", None, storey, space, points)
            item.layer = entry.get("layer")
            item.mark = entry.get("mark")
            item.text = entry.get("mark")
            item.extra["b_mm"] = _number(entry.get("b"))
            item.extra["h_mm"] = _number(entry.get("h"))
            item.extra["rotation_deg"] = _number(entry.get("rot"))
            capture.add(item)
        except Exception as error:
            capture.fail("text {0}".format(entry), error)


def _read_builder_input(raw_geometry, storey, space, capture, values):
    """The link geometry the builders were handed, as recorded by the run.

    Not matched by the reconciliation -- these are stage B curves carried inside
    a stage D file, and matching them would count the same geometry twice. They
    earn their place because a member missing from `items` but present here was
    seen and rejected, which is a different bug from one that was never seen.
    """
    limit = values["max_rows_per_sheet"]
    for entry in raw_geometry[:limit]:
        try:
            points = [(_number(p[0]), _number(p[1]), 0.0)
                      for p in entry.get("pts") or [] if len(p) >= 2]
            item = _item("curve", entry.get("cat"), storey, space, points)
            item.layer = entry.get("layer")
            item.source_type = entry.get("kind")
            item.extra["role"] = ROLE_BUILDER_INPUT
            capture.add(item)
        except Exception as error:
            capture.fail("raw_geometry {0}".format(entry.get("layer")), error)
    if len(raw_geometry) > limit:
        capture.meta.setdefault("truncated", {})["builder_input"] = len(raw_geometry)


def _item(kind, category, storey, space, points_mm):
    """Build an intent item from Revit-space millimetres."""
    clean = [p for p in points_mm if None not in p]
    points_ft = [(p[0] / config.MM_PER_FT, p[1] / config.MM_PER_FT,
                  p[2] / config.MM_PER_FT) for p in clean]
    points_dxf, points_revit = space.from_revit(points_ft)
    item = AuditItem(
        config.STAGE_INTENT, kind, source_type="cad2bim_json", category=category,
        points_dxf=points_dxf, points_revit=points_revit, native_space="revit",
        level=storey,
    )
    item.extra["role"] = ROLE_PLACED
    return item


def _rectangle_mm(cx, cy, width, height, angle_deg):
    """The four corners of a centred, rotated rectangle, in mm.

    Corners rather than a centre point so `plan_size_mm` and the centroid work
    off the same geometry as every other stage -- a stage that stored only a
    centre would need its own branch in the matcher and the workbook.
    """
    if None in (cx, cy) or not width or not height:
        return []
    import math
    radians = math.radians(angle_deg or 0.0)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    half_w, half_h = width / 2.0, height / 2.0
    corners = []
    for dx, dy in ((-half_w, -half_h), (half_w, -half_h),
                   (half_w, half_h), (-half_w, half_h)):
        corners.append((cx + dx * cos_a - dy * sin_a,
                        cy + dx * sin_a + dy * cos_a, 0.0))
    return corners


def _storey_key(storey):
    return storey if storey else "<single>"


def _number(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
