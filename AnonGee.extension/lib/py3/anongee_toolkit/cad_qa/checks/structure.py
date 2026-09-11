# -*- coding: utf-8 -*-
"""Grid and storey structure -- rules S001-S006.

THE FAILURE THIS FAMILY EXISTS FOR looks like a geometry bug and is not one.
A multi-storey DXF is read by the boundary/origin convention recorded in
``cad2bim/classify/layers.py``: each plan sits inside a rectangle on a BOUNDARY
layer and carries one marker on an ORIGIN layer saying where that plan belongs
in the model. Get the pairing wrong and every floor is set out from the same
point, so the storeys land on top of each other -- and the reported symptom is
"the model is a mess", which sends the next hour into the geometry passes where
the fault is not.

Counting the two layers before a run answers it in milliseconds.
"""

from ..deps import layers as layer_rules
from .. import rules
from ..findings import SEVERITY_WARNING
from ..spatial import centroid

__version__ = "1.0.0"

#: A grid run shorter than this is a bubble or a tick, not a grid line.
MIN_GRID_LENGTH_MM = 1000.0

#: Direction tolerance: within this many units of axis-aligned counts as
#: running in that direction. Generous, because a drawing rotated a fraction
#: of a degree is still a drawing with two grid directions.
_AXIS_RATIO = 0.2


def check(context):
    """Every grid/storey finding for this drawing."""
    found = []
    found.extend(_grid_directions(context))
    found.extend(_grid_labels(context))
    found.extend(_storey_pairing(context))
    return found


def _grid_directions(context):
    """S002 -- grids running in only one direction."""
    grids = [r for r in context.records
             if r.category == layer_rules.CATEGORY_GRID]
    if not grids:
        return []                      # L002 already said there are no grids

    horizontal = vertical = 0
    for record in grids:
        direction = _direction(context, record)
        if direction == "h":
            horizontal += 1
        elif direction == "v":
            vertical += 1

    if horizontal and vertical:
        return []
    if not horizontal and not vertical:
        return []                      # all diagonal or all too short to judge
    present = "horizontal" if horizontal else "vertical"
    return [rules.finding(
        "S002",
        message=("{0} grid lines found, all {1}".format(
            horizontal or vertical, present)),
        subject=present, count=horizontal or vertical)]


def _grid_labels(context):
    """S001 -- no text routed to grid bubbles."""
    grids = [r for r in context.records
             if r.category == layer_rules.CATEGORY_GRID]
    if not grids:
        return []
    labelled = any(category == layer_rules.CATEGORY_GRID_TEXT
                   for category in context.text_mapping.values())
    if labelled:
        return []
    return [rules.finding(
        "S001",
        message=("{0} grid lines will be created with generated names"
                 .format(len(grids))),
        count=len(grids))]


def _storey_pairing(context):
    """S003-S006 -- boundaries and origins, counted and paired."""
    boundaries = [r for r in context.records
                  if r.category == layer_rules.CATEGORY_FLOOR_BOUNDARY]
    origins = [r for r in context.records
               if r.category == layer_rules.CATEGORY_FLOOR_ORIGIN]

    if not boundaries and not origins:
        return [rules.finding("S006", count=1)]

    if boundaries and not origins:
        return [rules.finding(
            "S004",
            message=("{0} floor boundaries and no origin markers: every plan "
                     "is set out from the same point".format(len(boundaries))),
            count=len(boundaries))]

    if origins and not boundaries:
        return [rules.finding(
            "S005",
            message=("{0} origin markers with no floor boundary to belong to"
                     .format(len(origins))),
            count=len(origins))]

    out = []
    if len(boundaries) != len(origins):
        out.append(rules.finding(
            "S003",
            message=("{0} floor boundaries against {1} origin markers"
                     .format(len(boundaries), len(origins))),
            count=abs(len(boundaries) - len(origins))))
        return out

    # Counts agree. They still have to pair up one-to-one in SPACE: two origins
    # inside one boundary and none inside another counts correctly and builds
    # wrongly, which is the case a count alone cannot see.
    unpaired = _unpaired_boundaries(boundaries, origins)
    if unpaired:
        out.append(rules.finding(
            "S003",
            message=("counts agree ({0} each) but {1} boundaries contain no "
                     "origin marker".format(len(boundaries), len(unpaired))),
            count=len(unpaired), severity=SEVERITY_WARNING))
    return out


def _unpaired_boundaries(boundaries, origins):
    """Boundaries with no origin marker inside them."""
    origin_points = []
    for record in origins:
        middle = centroid(record.points)
        if middle is not None:
            origin_points.append(middle)

    unpaired = []
    for boundary in boundaries:
        box = _bbox(boundary.points)
        if box is None:
            continue
        if not any(_inside(box, point) for point in origin_points):
            unpaired.append(boundary)
    return unpaired


# -- helpers ----------------------------------------------------------------

def _direction(context, record):
    """'h', 'v' or None for a record's overall run.

    Measured end to end rather than segment by segment: a grid line drawn as a
    polyline with a kink in it still runs in one direction, and judging each
    segment would count the kink as a second direction.
    """
    points = record.points or []
    if len(points) < 2:
        return None
    dx = abs(points[-1][0] - points[0][0])
    dy = abs(points[-1][1] - points[0][1])
    span = max(dx, dy)
    if context.to_mm(span) < MIN_GRID_LENGTH_MM:
        return None
    if dy <= dx * _AXIS_RATIO:
        return "h"
    if dx <= dy * _AXIS_RATIO:
        return "v"
    return None


def _bbox(points):
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _inside(box, point):
    return (box[0] <= point[0] <= box[2]) and (box[1] <= point[1] <= box[3])
