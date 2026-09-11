# -*- coding: utf-8 -*-
"""Geometry integrity -- rules G001-G007.

NOT A NEATNESS CHECK. Every rule here is a shape cad2bim's geometry passes are
known to drop, so a finding means "you will lose this member", never "this
drawing is untidy". The distinction matters: a QA tool that reports drafting
taste gets switched off, and then it is not there on the day it would have
caught a lost storey.

The expensive rules (duplicates, outliers) are written as single passes with
hashing rather than pairwise comparisons, because the drawings that need them
most are the big ones.
"""

from ..deps import layers as layer_rules
from .. import rules
from ..context import is_closed, bbox_area, MIN_RING_AREA_MM2
from ..findings import SEVERITY_ERROR
from ..spatial import centroid

__version__ = "1.0.0"

#: Categories whose members are built FROM CLOSED RINGS. An open outline on one
#: of these is a member that will not place. Beams are excluded on purpose:
#: they are built from open runs and pairs of edges, so an open beam line is
#: normal rather than a fault.
CLOSED_RING_CATEGORIES = frozenset((
    layer_rules.CATEGORY_COLUMN, layer_rules.CATEGORY_FOUNDATION,
    layer_rules.CATEGORY_STRUCT_WALL,
))

#: Ring kinds that are supposed to close. A 'line' never is.
RING_KINDS = frozenset(("polyline", "lwpolyline", "circle", "ellipse"))

#: A point this many times the drawing's own size away from the middle is a
#: stray, not part of the plan.
OUTLIER_FACTOR = 1.5

#: Plausible overall size of a building plan, in millimetres. A plan outside
#: this is a unit problem, not a very small or very large building: 2 m is
#: smaller than one bay, 2 km is larger than any single plan gets drawn.
MIN_PLAN_MM = 2000.0
MAX_PLAN_MM = 2000000.0

#: Coordinates are rounded to this many millimetres before being hashed for the
#: duplicate check. Two outlines a hundredth of a millimetre apart are the same
#: outline drawn twice, and comparing floats exactly would miss every one.
DUPLICATE_ROUNDING_MM = 1.0

#: Above this, a Z coordinate counts as off-plane rather than as rounding.
FLAT_Z_TOLERANCE_MM = 1.0


def check(context):
    """Every geometry-integrity finding for this drawing."""
    if not context.records:
        return [rules.finding("G001", count=0)]
    found = []
    found.extend(_degenerate(context))
    found.extend(_duplicates(context))
    found.extend(_off_plane(context))
    found.extend(_unclosed_rings(context))
    found.extend(_outliers(context))
    found.extend(_implausible_extent(context))
    return found


def _degenerate(context):
    """G002 -- records too small or too short to be anything."""
    offenders = []
    for record in context.records:
        points = record.points or []
        if len(points) < 2:
            offenders.append(record)
            continue
        if len(set((round(p[0], 6), round(p[1], 6)) for p in points)) < 2:
            offenders.append(record)
    if not offenders:
        return []
    return [rules.finding(
        "G002",
        message="{0} records enclose or span nothing".format(len(offenders)),
        count=len(offenders),
        examples=_layer_examples(offenders))]


def _duplicates(context):
    """G003 -- identical geometry drawn twice in the same place.

    Hashed in one pass: a record's signature is its layer, its kind and its
    rounded point run. Pairwise comparison would be quadratic and this is the
    check most likely to meet a drawing with a hundred thousand records in it.
    """
    seen = {}
    duplicated = {}
    for record in context.records:
        signature = _signature(context, record)
        if signature in seen:
            duplicated[signature] = duplicated.get(signature, 1) + 1
        else:
            seen[signature] = record

    if not duplicated:
        return []
    extra = sum(count - 1 for count in duplicated.values())
    layers_hit = sorted(set(signature[0] for signature in duplicated))
    return [rules.finding(
        "G003",
        message=("{0} records are exact duplicates of another, across {1} "
                 "layers".format(extra, len(layers_hit))),
        count=extra, examples=layers_hit[:5])]


def _off_plane(context):
    """G004 -- structural linework with a non-zero Z."""
    offenders = []
    for record in context.records:
        if record.category == layer_rules.CATEGORY_UNMAPPED:
            continue
        for point in record.points or []:
            if len(point) > 2 and abs(context.to_mm(point[2])) > FLAT_Z_TOLERANCE_MM:
                offenders.append(record)
                break
    if not offenders:
        return []
    return [rules.finding(
        "G004",
        message="{0} classified records sit off the drawing plane".format(
            len(offenders)),
        count=len(offenders), examples=_layer_examples(offenders))]


def _unclosed_rings(context):
    """G005 -- an outline that should close and does not."""
    offenders = []
    for record in context.records:
        if record.category not in CLOSED_RING_CATEGORIES:
            continue
        if record.kind not in RING_KINDS:
            continue
        points = record.points or []
        if len(points) < 3:
            continue
        if bbox_area(points) * (context.unit_mm ** 2) < MIN_RING_AREA_MM2:
            continue                      # too small to be a member anyway
        if not is_closed(points):
            offenders.append(record)
    if not offenders:
        return []
    by_category = {}
    for record in offenders:
        by_category[record.category] = by_category.get(record.category, 0) + 1
    shown = ["{0}x {1}".format(count, name)
             for name, count in sorted(by_category.items())]
    middle = centroid(offenders[0].points)
    return [rules.finding(
        "G005",
        message=("{0} outlines that must close do not, so the members they "
                 "describe will not be built".format(len(offenders))),
        count=len(offenders), examples=shown,
        where=context.point_mm(middle) if middle else None)]


def _outliers(context):
    """G006 -- geometry far outside the body of the drawing.

    Judged against the MEDIAN member position rather than the mean: one stray
    a kilometre away drags a mean far enough to make itself look normal, which
    is the failure this check exists to catch.
    """
    centres = []
    for record in context.records:
        middle = centroid(record.points)
        if middle is not None:
            centres.append((middle[0], middle[1], record))
    if len(centres) < 10:
        return []                          # too few to have a "body"

    median_x = _median([c[0] for c in centres])
    median_y = _median([c[1] for c in centres])
    spreads = sorted(max(abs(c[0] - median_x), abs(c[1] - median_y))
                     for c in centres)
    # The typical distance from the middle: the 90th percentile, so the
    # threshold is set by the plan rather than by the strays it is hunting.
    typical = spreads[int(len(spreads) * 0.9)]
    if typical <= 0:
        return []
    limit = typical * OUTLIER_FACTOR

    offenders = [record for x, y, record in centres
                 if max(abs(x - median_x), abs(y - median_y)) > limit]
    if not offenders:
        return []
    return [rules.finding(
        "G006",
        message=("{0} records sit more than {1:.0f} m from the body of the "
                 "drawing".format(len(offenders),
                                  context.to_mm(limit) / 1000.0)),
        count=len(offenders), examples=_layer_examples(offenders))]


def _implausible_extent(context):
    """G007 -- the whole plan is the wrong size for a building."""
    box = context.extent_mm()
    if box is None:
        return []
    width = box[2] - box[0]
    height = box[3] - box[1]
    size = max(width, height)
    if MIN_PLAN_MM <= size <= MAX_PLAN_MM:
        return []
    return [rules.finding(
        "G007",
        message=("the drawing measures {0:.0f} x {1:.0f} mm, read at "
                 "{2:g} mm per drawing unit".format(width, height,
                                                    context.unit_mm)),
        count=1,
        examples=["expected between {0:.0f} and {1:.0f} mm across".format(
            MIN_PLAN_MM, MAX_PLAN_MM)],
        severity=SEVERITY_ERROR)]


# -- helpers ----------------------------------------------------------------

def _signature(context, record):
    """Layer, kind and rounded point run -- what makes two records the same."""
    step = DUPLICATE_ROUNDING_MM
    points = tuple(
        (int(round(context.to_mm(p[0]) / step)),
         int(round(context.to_mm(p[1]) / step)))
        for p in (record.points or []))
    return (record.layer_key, record.kind, points)


def _layer_examples(records):
    """["412x S-COLS", ...] -- where the offending records actually are."""
    counts = {}
    for record in records:
        counts[record.layer_key] = counts.get(record.layer_key, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ["{0}x {1}".format(count, layer) for layer, count in ordered][:5]


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
