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
hands each storey's records ALREADY SHIFTED, every plan's origin marker onto the
base plan's, so all of them share one frame. A column at (x, y) on one plan is
therefore the same column as one at (x, y) on another, and `key_for` clusters the
footprints on that.

THE SECTION SPEAKS TOO, and louder than the layers. A column that reduces higher
up is not one column, and the drawing says so by drawing it thinner rather than
by marking it: 126 of test17's 219 columns change section over their height,
almost none of them marked. So the answer is keyed by `(column, run)` -- a run
being one stretch at one section -- and `extents` says how each run was cut.

Measured on `StructuralPlan-Test17-clean.dxf`: 337 records on `S-COLUM_STOP` and
24 on `S-COLUMN_START`, concentrated where a structure really does change --
148 stopping at the ground plan and 135 at the terrace, starting in twos and
sixes up the tower. 2344 drawn outlines over its 13 floors come to 386 columns,
196 of them running through more than one storey.

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

# The step a drawn section is read to, in millimetres, before two storeys are
# called the same size. MEASURED on test17's 2344 column footprints: within one
# column, two footprints that are the same section differ by at most 0.195 mm
# (99th percentile 0.066), while the smallest REAL change of section anywhere in
# the drawing is 50 mm. A whole millimetre sits in the middle of that band with
# five times the noise below it and fifty times under the smallest real change,
# and the run counts are identical at 1, 5 and 10 mm -- the band is that empty.
_SECTION_STEP_MM = 1.0


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

    One frame for the whole stack, because `floor_plans` has already shifted
    every plan's origin marker onto the base plan's. A column at (x, y) on one
    plan is therefore the same column as one at (x, y) on another, and the
    tolerance only has to absorb drafting noise.
    """
    return clusters(points, tolerance_ft)[0]


def clusters(points, tolerance_ft=_SAME_COLUMN_FT):
    """({point index: column id}, [column centre]) -- `key_for` with the centres.

    The centres are what lets a footprint be matched to a column LATER, without
    the caller having to hand back the points in the same order. That matters:
    the footprints are gathered from the drawing's records, while the columns
    that get built come out of `decompose_to_rectangles`, which splits some and
    drops others -- so the two lists never line up by index and nothing should
    ever assume they do.
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
    return out, centres


def assign(boxes, point, tolerance_ft=_SAME_COLUMN_FT):
    """Which column a built rectangle belongs to, or None when it belongs to none.

    `boxes` is `plan`'s second answer: `(x, y, half width, half height)` per
    column, in feet. A bare `(x, y)` is accepted too, for a caller that tracked
    no sizes.

    INSIDE FIRST, and that is the whole reason this is not a nearest-centre
    match. A column is not always one rectangle: an L or a C is decomposed into
    legs, and a leg's centre is nowhere near the outline's centre. Matching by
    centre gave one leg of an L its column and left the others out -- measured
    on test17, 57 outlines came back with their legs disagreeing -- so the L was
    carried up a storey as one leg while the rest were rebuilt on every floor,
    putting one column straight through another.

    THE SMALLEST BOX WINS among those that contain the point. A long L's box
    reaches over its neighbours, and a neighbour sitting inside it must still
    take its own, tighter box -- which it always does, because a column's own
    box is the smallest one its own rectangles can sit in.

    Nothing containing it falls back to the nearest centre within tolerance,
    which is what a recovered rectangle that landed just outside its outline
    needs; the nearest, not the first, because a rectangle sits between two
    columns often enough that "first" would be a coin toss.
    """
    if not point or not boxes:
        return None
    reach = float(tolerance_ft or _SAME_COLUMN_FT)
    x, y = float(point[0]), float(point[1])
    best, best_area, near, near_gap = None, None, None, None
    for column, box in enumerate(boxes):
        cx, cy = float(box[0]), float(box[1])
        half_x = float(box[2]) if len(box) > 2 else 0.0
        half_y = float(box[3]) if len(box) > 3 else 0.0
        if half_x > 0.0 and half_y > 0.0 \
                and abs(x - cx) <= half_x and abs(y - cy) <= half_y:
            area = half_x * half_y
            if best_area is None or area < best_area:
                best, best_area = column, area
        gap = math.hypot(x - cx, y - cy)
        if gap <= reach and (near_gap is None or gap < near_gap):
            near, near_gap = column, gap
    return best if best is not None else near


def section_of(size):
    """A drawn section read to the nearest millimetre, for comparing storeys.

    Two footprints of the same column are never bit-identical -- the drawing has
    them 0.2 mm apart at worst -- and comparing raw feet would call every storey
    a different section and break every span into single floors, which is the
    one thing this must not do. `None` (a caller that does not track sections)
    stays None, and anything that is not a pair of numbers is handed back
    untouched so a caller may key by its own name for a section if it has one.
    """
    if size is None:
        return None
    try:
        return tuple(int(round(float(value) / _SECTION_STEP_MM))
                     for value in size)
    except (TypeError, ValueError):
        return size


def extents(storeys):
    """{(column, run): (first storey, last storey)} for every column drawn.

    `storeys` is bottom-up, one entry per storey, each a list of
    `(key, mark, size)` -- the mark being "start", "stop" or None, and `size`
    the drawn section (or None where the caller does not track it).

    A RUN is a stretch of consecutive storeys that is ONE column: same section,
    begun by a `_START`, ended by a `_STOP`. The owner's reading A says what the
    two marks mean -- a `_STOP` column is drawn on the LAST storey it exists in,
    a `_START` column on the FIRST -- so a run is cut

      * where the SECTION changes,
      * at a storey marked "start", which begins a column,
      * after a storey marked "stop", which ends one,

    and its span is simply the lowest and highest storey in it.

    THE SECTION CUT IS NOT A REFINEMENT. Measured on test17: 126 of its 219
    columns change section over their height -- 200x2150 becoming 250x2150 part
    way up -- and the drawing marks almost none of those changes. One column
    over the whole height would carry the bottom storey's section through more
    than half of them, which is worse than the stack of one-storey columns this
    exists to replace.

    WHAT IS DRAWN IS ALWAYS BUILT. A column drawn above its own `_STOP` (three
    of test17's 219) contradicts its layer, and the storeys above simply become
    the next run rather than being dropped: a drawing that says two things
    should still put every column it draws in the model.
    """
    seen = {}
    for index, storey in enumerate(storeys or ()):
        for row in storey or ():
            key, mark = row[0], row[1]
            size = section_of(row[2] if len(row) > 2 else None)
            if key is None:
                continue
            seen.setdefault(key, []).append((index, mark, size))

    out = {}
    for key, rows in seen.items():
        rows.sort(key=lambda row: row[0])
        runs, current, ended = [], None, False
        for index, mark, size in rows:
            if current is None or ended or mark == "start" \
                    or current["size"] != size:
                current = {"size": size, "levels": []}
                runs.append(current)
                ended = False
            current["levels"].append(index)
            if mark == "stop":
                ended = True
        for number, run in enumerate(runs):
            out[(key, number)] = (min(run["levels"]), max(run["levels"]))
    return out


def plan(storeys):
    """(spans, boxes) from the whole stack, bottom-up -- the one call to make.

    `storeys` is one entry per storey, each a list of `(centre, layer, size)`
    for the column footprints drawn on that plan; `size` is the drawn section in
    millimetres, which both cuts a run where a column reduces and gives the
    column its box. A caller with no sizes may leave it off.

    The BOXES come back because they are what lets the builder match its own
    rectangles by POSITION rather than trusting two lists to line up by index:
    the footprints are gathered from the drawing's records, the built columns
    come out of `decompose_to_rectangles`, which splits some and drops others,
    so the two never would. Each box is `(x, y, half width, half height)` in
    feet, over the LARGEST section the column is drawn at anywhere -- a column
    that reduces higher up keeps the box that holds every rectangle it will ever
    be built from, and `assign` prefers the tightest box that contains a
    rectangle, so a neighbour inside a long L's box still takes its own.

    The clustering runs over ALL storeys at once on purpose. Doing it per storey
    and matching afterwards would let the same column start a new cluster on
    each floor, which is the failure this exists to prevent.
    """
    flat, where = [], []
    for index, storey in enumerate(storeys or ()):
        for position, row in enumerate(storey or ()):
            flat.append(row[0])
            where.append((index, position))
    columns, centres = clusters(flat)

    marked = [[] for _ in (storeys or ())]
    boxes = [[x, y, 0.0, 0.0] for x, y in centres]
    for flat_index, (index, position) in enumerate(where):
        key = columns.get(flat_index)
        if key is None:
            continue
        row = storeys[index][position]
        size = row[2] if len(row) > 2 else None
        marked[index].append((key, mark_of(row[1]), size))
        if size:
            boxes[key][2] = max(boxes[key][2], float(size[0]) / 304.8 / 2.0)
            boxes[key][3] = max(boxes[key][3], float(size[1]) / 304.8 / 2.0)
    return extents(marked), [tuple(box) for box in boxes]


def run_at(spans, key, storey):
    """The (column, run) whose span covers `storey`, or None.

    A column is several runs when its section changes up the building, so the
    builder has to ask which run a storey belongs to rather than assuming one.
    """
    if key is None:
        return None
    for candidate, span in (spans or {}).items():
        if candidate[0] == key and span[0] <= storey <= span[1]:
            return candidate
    return None


def plan_storey(keys, spans, storey):
    """({footprint: the storey whose TOP it reaches}, [footprints to skip]).

    `keys` is one column id per footprint on THIS storey, `None` where the
    footprint matched nothing. A run that begins lower was already built there
    and is skipped; one that begins here reaches the top of the storey its span
    ends on; a footprint belonging to no run at all is built exactly as it
    always was, on this storey alone.
    """
    built, skipped = {}, []
    for index, key in enumerate(keys or ()):
        run = run_at(spans, key, storey)
        span = (spans or {}).get(run) if run is not None else None
        if span is None:
            built[index] = storey
            continue
        if span[0] != storey:
            skipped.append(index)
            continue
        built[index] = span[1]
    return built, skipped
