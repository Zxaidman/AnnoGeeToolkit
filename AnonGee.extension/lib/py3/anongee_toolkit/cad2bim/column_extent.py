# -*- coding: utf-8 -*-
"""How far up a column runs, from the drawing's `_START` and `_STOP` layers.

The owner, on test17: "in column layers there two new Stop and Start layer which
both should be treated differently stop means that layer column is stop on that
particular floor means it can go above, similarly start means this layer column
is start from this level", and, asked which of two readings he meant:

    A -- the layer names the column's OWN EXTENT: a `_STOP` column drawn on a
    plan is the LAST storey it exists in, and a `_START` column is the FIRST.

    "A is correct, build the start/stop column logic"

WHY THE TOOL NEEDS TELLING. A multi-storey sheet is built one plan per storey,
so a column that runs ten floors is drawn on ten plans and comes out as ten
one-storey columns stacked on each other. The drawing already says where the
real column begins and ends -- that is what these two layers are for -- and with
them a column can be built ONCE, from the level it starts at to the level it
stops at.

MATCHING ACROSS PLANS IS FREE, which is what makes this practical: `floor_plans`
hands each storey's records ALREADY SHIFTED so that plan's origin marker sits at
(0, 0). A column at local (x, y) on one plan is therefore the same column as one
at (x, y) on another, and `key_for` clusters the footprints on that.

Measured on `StructuralPlan-Test17-clean.dxf`: 337 records on `S-COLUM_STOP` and
24 on `S-COLUMN_START`, concentrated where a structure really does change --
148 stopping at the ground plan and 135 at the terrace, starting in twos and
sixes up the tower.

Revit-free on purpose: the arithmetic is testable, and the builder is left with
the placement alone.
"""

import math


# The suffixes a drawing uses for these two layers. test17 writes `S-COLUM_STOP`
# (one M, and that is the drawing's spelling, not a typo here) and
# `S-COLUMN_START`; the separators cover the same names written with a dash or a
# space, which is the sort of thing that differs between offices.
_START_MARKS = ("_START", "-START", " START")
_STOP_MARKS = ("_STOP", "-STOP", " STOP")

# How close two footprints must be to be the same column, in feet. A column is
# drawn on the same grid intersection on every plan it appears on, so this only
# has to absorb drafting noise, not real movement.
_SAME_COLUMN_FT = 100.0 / 304.8


def mark_of(layer):
    """"start", "stop", or None for an ordinary column layer.

    The suffix decides, not the whole name, so an office's own prefix
    (`S-`, `STR-`, none at all) is none of this function's business.
    """
    name = str(layer or "").upper().rstrip()
    for suffix in _STOP_MARKS:
        if name.endswith(suffix):
            return "stop"
    for suffix in _START_MARKS:
        if name.endswith(suffix):
            return "start"
    return None


def key_for(points, tolerance_ft=_SAME_COLUMN_FT):
    """{point index: column id} -- which footprints are the same column.

    CLUSTERED, NOT BINNED. Rounding a position into a cell looks like the same
    thing and is not: two footprints a millimetre apart fall either side of a
    cell edge and become two columns, which is the one job this has. So each
    point joins the first cluster it is within `tolerance_ft` of, and starts its
    own when it is near none.

    Plan-local coordinates, because `floor_plans` hands each storey's records
    already shifted so that plan's origin marker sits at (0, 0). A column at
    (x, y) on one plan is therefore the same column as one at (x, y) on another,
    and the tolerance only has to absorb drafting noise.
    """
    size = float(tolerance_ft or _SAME_COLUMN_FT)
    centres, out = [], {}
    for index, point in enumerate(points or ()):
        if not point:
            continue
        x, y = float(point[0]), float(point[1])
        found = None
        for column, (cx, cy) in enumerate(centres):
            if math.hypot(x - cx, y - cy) <= size:
                found = column
                break
        if found is None:
            found = len(centres)
            centres.append((x, y))
        out[index] = found
    return out


def extents(storeys):
    """{key: (first storey index, last storey index)} for every column drawn.

    `storeys` is bottom-up, one entry per storey, each a list of
    `(key, mark)` -- the mark being "start", "stop" or None. Indices are into
    that list, so the caller keeps its own storey objects.

    The rule is the owner's A, and each half is independent:

      * the FIRST storey is the lowest one marked "start"; with no start mark
        anywhere it is simply the lowest storey the column is drawn on;
      * the LAST storey is the highest one marked "stop", or the highest it is
        drawn on.

    A column marked start ABOVE where it is marked stop would describe a column
    that ends before it begins; the span is clamped to at least its own start
    rather than inverted, because a drawing that says something impossible
    should still produce one column rather than none.
    """
    drawn, started, stopped = {}, {}, {}
    for index, storey in enumerate(storeys or ()):
        for key, mark in storey or ():
            if key is None:
                continue
            drawn.setdefault(key, []).append(index)
            if mark == "start" and key not in started:
                started[key] = index          # the LOWEST start wins
            elif mark == "stop":
                stopped[key] = index          # the HIGHEST stop wins
    out = {}
    for key, levels in drawn.items():
        first = started.get(key, min(levels))
        last = stopped.get(key, max(levels))
        out[key] = (first, max(first, last))
    return out


def spans_one_storey(extent):
    """True when a column begins and ends on the same floor.

    Worth its own name because it is the ordinary case -- most columns carry no
    mark at all and are drawn on one plan -- and the builder can place those
    exactly as it always has.
    """
    return extent is not None and extent[0] == extent[1]


def build_here(extent, storey):
    """Whether THIS storey is the one that places the column.

    A column that spans several floors is built once, at its first storey, and
    skipped on the rest: building it again on each would stack the same column
    on itself, which is the thing the `_START`/`_STOP` layers exist to stop.
    """
    return extent is not None and storey == extent[0]
