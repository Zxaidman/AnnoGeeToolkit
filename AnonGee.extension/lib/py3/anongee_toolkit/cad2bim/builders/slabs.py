# -*- coding: utf-8 -*-
"""Place floor slabs from derived slab loops (see slab_outlines.py).

Mirrors the column/beam builders: a base floor type is duplicated per thickness
("150 THK") and cached; a loop with no thickness inherits the picked type. A loop
lying fully INSIDE another becomes that floor's OPENING (a hole), not its own slab.
Runs inside a caller-owned Transaction; one bad loop never fails the batch.

A STEPPED loop arrives already worked out, from `fold_plan.slab_defs_with_steps`
in the Revit-free layer, as three extra keys on the same dicts:

    holes       rings to cut out of this loop -- a sunk bay taken out of the
                slab it steps down from
    offset_mm   how far BELOW the level this floor hangs (0 sits it on the
                level); the only thing telling a step's three floors apart
    part        set on the dropped slab and its support, and read here for one
                reason: they lie inside their parent's outline, which is the
                shape of a stair void, and the opening nesting below would
                otherwise turn the floor at the bottom of a step into a hole

EVERY PROFILE IS CHECKED BEFORE REVIT SEES IT (`check_profile`). Floor.Create
answers a bad sketch with one paragraph that names no geometry -- "the input
curve loops cannot compose a valid boundary ... Parameter name: profile" -- and
a stack; the owner got exactly that on a 151-slab run and had nothing to look
for. This module is the ONLY place that sees the loops as Revit gets them: the
offline passes work from the DXF, while a real run assembles its rings from the
LINK's records, which explode a closed polyline into separate lines. A profile
that will not compose is therefore declined HERE, by name, and the run carries
on with the rest.
"""

from System.Collections.Generic import List

from Autodesk.Revit.DB import (FilteredElementCollector, XYZ, Line, Arc, CurveLoop,
                               Floor, FloorType, BuiltInParameter)

from ..unit_convert import mm_to_internal
from ..compat import get_element_name, set_element_mark
from ..geom.shapes import circle_from_three_points
from .. import config
from .. import naming
from .. import type_names

_MM = config.MM_PER_FT


def floor_types(doc):
    """[(label, ElementId)] of the model's floor types."""
    types = (FilteredElementCollector(doc).OfClass(FloorType).ToElements())
    rows = [(get_element_name(ft), ft.Id) for ft in types]
    return sorted(rows, key=lambda pair: pair[0])


def place_slabs(doc, slabs, base_type_id, level_id):
    """Place one floor per outer slab dict {ring, z, mark, thickness_mm}.

    ring: [(x, y), ...] internal feet, closed implicitly. thickness_mm duplicates
    the base type sized to that thickness; None keeps the base type as-is. A slab
    whose ring lies fully inside another slab's ring is treated as an OPENING of
    the enclosing slab (stair/lift void) and appended as an inner CurveLoop.

    A slab carrying `part` is a piece of a STEP -- the floor at the bottom of a
    sunk bay, or the support between the two soffits. Those are kept out of the
    nesting entirely (module docstring) and placed with the `offset_mm` that
    puts them where the step is; everything else is nested exactly as before.

    Every profile passes `check_profile` first. A profile Revit would refuse is
    declined here instead, named -- mark, ring size, position, and the rule it
    broke -- on `result["errors"]`, where run_builders prints it red; the loop
    then goes round again, so one bad outline costs one slab, not the run.

    Floor.Create requires a .NET IList<CurveLoop> -- a Python list does not
    convert under CPython3/pythonnet ("No method matches given arguments"), so
    the loops are packed into System.Collections.Generic.List[CurveLoop].
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    if base_type is None or level is None:
        raise ValueError("floor type or level could not be resolved")

    outers, openings = _nest_openings([s for s in slabs if not s.get("part")])
    placements = []
    for index, slab in enumerate(outers):
        holes = [(hole["ring"], hole.get("arcs"))
                 for hole in openings.get(index, [])]
        holes += [(hole, None) for hole in (slab.get("holes") or [])]
        placements.append((slab, holes))
    for slab in slabs:
        if slab.get("part"):
            placements.append(
                (slab, [(hole, None) for hole in (slab.get("holes") or [])]))

    cache = {}
    result = {"created": [], "skipped": [], "errors": [], "notes": []}
    for slab, holes in placements:
        try:
            ring = slab["ring"]
            # Ask BEFORE Revit does. A refusal here is a named skip -- the loop
            # goes round again and the rest of the storey still builds -- where
            # the same refusal from Floor.Create is an exception carrying a
            # stack and no geometry. The report goes on `errors` so
            # run_builders prints it red (it calls _say_error per entry);
            # nothing is raised, so the count lands in the outcome the way
            # every other declined loop's does.
            place_it, kept, report = check_profile(
                ring, [hole_ring for hole_ring, _arcs in holes],
                slab.get("mark"))
            if report:
                result["errors"].append(report)
            if not place_it:
                continue
            holes = [holes[index] for index in kept]
            loops = List[CurveLoop]()
            loops.Add(_curve_loop(ring, slab.get("arcs")))
            for hole_ring, hole_arcs in holes:
                loops.Add(_curve_loop(hole_ring, hole_arcs))
            floor_type, note = _resolve_type(doc, base_type,
                                             slab.get("thickness_mm"), cache)
            type_names.record(result, note)
            if floor_type is None:
                result["skipped"].append("no floor type for {0} mm".format(
                    slab.get("thickness_mm")))
                continue
            instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
            _set_structural(instance)
            _set_mark(instance, slab.get("mark"))
            problem = _offset(instance, slab.get("offset_mm"))
            if problem:
                result["skipped"].append(problem)
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


def _offset(instance, offset_mm):
    """Hang the floor `offset_mm` BELOW its level (0 or None sits it on it).

    A step's three floors are told apart by nothing but this number, so a
    parameter that will not take it is REPORTED rather than swallowed: an
    unmoved dropped slab sits flush with the slab it is meant to have stepped
    down from, which looks built and is wrong. The same reasoning, and the same
    single parameter, as `builders/footings._offset` -- HEIGHTABOVELEVEL
    positions the floor's TOP, and the bottom-elevation parameter it might
    otherwise fall back to would place it one thickness out in silence.
    """
    if not offset_mm:
        return None
    try:
        parameter = instance.get_Parameter(
            BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    except Exception:
        parameter = None
    if parameter is not None and not parameter.IsReadOnly:
        try:
            parameter.Set(mm_to_internal(offset_mm))
            return None
        except Exception:
            pass
    return ("could not offset a floor to {0:.0f} mm: it is flush with its "
            "level".format(offset_mm))


_MIN_EDGE_FT = 15.0 / 304.8       # skip sub-tolerance slivers (Revit rejects them)
_COLLINEAR_FT = 1.0 / 304.8       # merge vertices that add no real corner


def _curve_loop(ring, arcs=None):
    """Ring -> CurveLoop with REAL Arc edges where the boundary is curved.

    `arcs` carries (start, mid, end) triples for the ring's curved stretches (the
    outline module tessellated them into chords for the geometry passes). Each registered
    stretch is emitted as ONE Arc.Create(start, end, pointOnArc) and its chord run
    skipped; the straight stretches are sanitized (duplicate points, sub-tolerance
    edges and collinear stops merged) so Floor.Create never sees micro-segments."""
    pts = _sanitize_ring(ring)
    n = len(pts)
    spans = _arc_spans(pts, arcs or [])
    if spans:
        # the ring seam must NOT sit inside an arc's chord run (the walk would emit
        # part of the chords AND the whole arc): rotate the ring to a run START.
        start = min(spans)
        pts = pts[start:] + pts[:start]
        spans = _arc_spans(pts, arcs or [])
    # weld the ring vertices onto the arcs' exact endpoints: sanitation may have
    # nudged them apart, and a CurveLoop must be contiguous to Revit tolerance
    for i_first, (i_last, a, m, b) in list(spans.items()):
        pts[i_first] = a
        pts[i_last] = b
    n = len(pts)
    loop = CurveLoop()
    i = 0
    steps = 0
    while i < n and steps <= 2 * n:
        steps += 1
        span = spans.get(i)
        if span is not None:
            i_last, a, m, b = span
            # endpoints come from the FINAL ring positions, not the span's own
            # triple: two adjacent arcs SHARE a vertex, and whichever welded it
            # last wins -- emitting the stale triple endpoint would leave a gap
            # ("loop discontinuous") between consecutive curves
            pa, pb = pts[i], pts[i_last]
            loop.Append(Arc.Create(XYZ(pa[0], pa[1], 0.0), XYZ(pb[0], pb[1], 0.0),
                                   XYZ(m[0], m[1], 0.0)))
            if i_last <= i:            # the run wraps the ring seam: boundary done
                break
            i = i_last
            continue
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        loop.Append(Line.CreateBound(XYZ(x1, y1, 0.0), XYZ(x2, y2, 0.0)))
        i += 1
    return loop


_ON_CIRCLE_FT = 20.0 / 304.8


def _arc_spans(pts, arcs):
    """{run_first_index: (run_last_index, walk_start, mid, walk_end)} per arc.

    The arc's tessellated CHORD RUN occupies the ring indices between the vertices
    nearest its two endpoints -- on ONE side only. Which side is decided by testing
    whether that side's interior vertices lie on the arc's circle (the other side
    is the panel's straight boundary). The span is keyed at the run's first index
    IN WALK ORDER and oriented so the emitted Arc starts where the walk arrives --
    the ring's traversal direction is independent of how the arc was recorded."""
    spans = {}
    n = len(pts)
    for triple in arcs:
        a, m, b = triple
        fit = circle_from_three_points(a, m, b)
        if not fit:
            continue
        cx, cy, r = fit
        ia = _nearest_index(pts, a)
        ib = _nearest_index(pts, b)
        if ia is None or ib is None or ia == ib:
            continue

        def on_circle(idx):
            x, y = pts[idx]
            return abs(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - r) <= _ON_CIRCLE_FT

        def run_is_arc(start, end):    # forward run start -> end (mod n), interior on circle
            length = (end - start) % n
            if length < 2:
                return True            # adjacent: nothing to test
            probe = (start + length // 2) % n
            return on_circle(probe)

        if run_is_arc(ia, ib) and not run_is_arc(ib, ia):
            first, last = ia, ib       # walk enters at a, leaves at b
            oriented = (a, m, b)
        elif run_is_arc(ib, ia) and not run_is_arc(ia, ib):
            first, last = ib, ia       # walk enters at b, leaves at a
            oriented = (b, m, a)
        else:
            # both or neither side test as arc (tiny ring): take the shorter side
            if (ib - ia) % n <= (ia - ib) % n:
                first, last, oriented = ia, ib, (a, m, b)
            else:
                first, last, oriented = ib, ia, (b, m, a)
        spans[first] = (last, oriented[0], oriented[1], oriented[2])
    return spans


def _nearest_index(pts, p):
    best_i, best_d = None, None
    for i, q in enumerate(pts):
        d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
        if best_d is None or d < best_d:
            best_i, best_d = i, d
    return best_i


# --------------------------------------------------------------------------
# THE PROFILE CHECK. Pure geometry on (x, y) tuples in internal feet: no Revit
# name appears below, so the offline suite can import these functions out of a
# module it cannot otherwise load and pin the RULES rather than the wiring.
# --------------------------------------------------------------------------

_TOUCH_TOL_FT = 1.0 / 304.8       # a millimetre: drawn-to-meet counts as touching

# TWO tolerances, and the difference is not fussiness. BETWEEN rings a
# millimetre is right: a void drawn to its slab's edge is drawn to meet it, the
# same "drawn-to-meet" distance fold_plan judges by, and refusing one costs a
# hole. WITHIN one ring a millimetre is far too wide, and refusing costs the
# whole slab -- test14 draws a bay's east edge twice, 1.4 mm apart; the
# sanitizer merges the sliver between them and leaves the two runs 0.9 mm
# apart, which Revit takes without complaint. What Revit will not take is two
# points it cannot tell apart, and that line sits at its vertex tolerance.
_PINCH_TOL_FT = 0.3 / 304.8


def check_profile(ring, hole_rings, mark=None):
    """What Floor.Create will take of this profile -- and what it will not.

    Returns (place_it, kept_hole_indexes, report):

        place_it            False when the OUTLINE itself is refused
        kept_hole_indexes   the openings that survive, in the order given
        report              None when the profile is clean, else the paragraph
                            for `result["errors"]` -- one line per refusal,
                            each naming the ring's size and where it sits

    Revit's own refusal lists the ways a profile can fail: an empty collection,
    a loop that is not closed, loops that intersect each other, a loop that is
    not planar, one not parallel to XY, a helical curve. The last three cannot
    arise here -- every ring is a list of (x, y) laid flat on z = 0 by
    `_curve_loop` -- so what is left to check is emptiness, closure and
    intersection, which is what `_ring_faults` and `_contact` do between them.
    TOUCHING counts as intersecting: Revit refuses tangency wholesale, which is
    the lesson `fold_plan.split_profile` was written for (a sunk bay spanning
    its block's full width handed Floor.Create two loops sharing two edges).

    Checked on the SANITIZED ring, because that is the point list `_curve_loop`
    actually walks -- duplicate points, sub-tolerance edges and collinear stops
    already merged. On a ring carrying `arcs` the check reads the tessellated
    chords rather than the arc that replaces them; the chords sit within a
    sagitta of the true edge, which is far below anything judged here.
    """
    outer = _sanitize_ring(_flat(ring))
    name = _slab_name(mark, outer or _flat(ring))

    fault = _ring_faults(outer)
    if fault:
        return (False, [],
                "{0}: profile DECLINED, Revit would refuse it -- {1}.\n"
                "- outline: {2}.".format(name, fault,
                                         _ring_note(outer or _flat(ring))))

    kept, kept_rings, lines = [], [], []
    for index, hole in enumerate(hole_rings or []):
        clean = _sanitize_ring(_flat(hole))
        why = _ring_faults(clean)
        if why is None:
            why = _hole_against_outline(clean, outer)
        if why is None:
            for position, other in kept_rings:
                touch = _contact(clean, other)
                if touch:
                    why = "{0} opening {1}".format(touch, position + 1)
                    break
                if _point_in_ring(clean[0][0], clean[0][1], other):
                    why = "it sits inside opening {0}".format(position + 1)
                    break
        if why:
            lines.append("- opening {0} NOT cut: {1} -- {2}.".format(
                index + 1, why, _ring_note(clean or _flat(hole))))
            continue
        kept.append(index)
        kept_rings.append((index, clean))

    if not lines:
        return (True, kept, None)
    # THE FALLBACK, and why it falls this way. A profile that fails only on its
    # openings still has a sound outline, and the outline is the concrete: it
    # carries the mark, the thickness and the type, and it is what the
    # schedules count. Refusing the whole slab to punish one bad void deletes a
    # real floor and leaves a gap nobody can see -- the drawing says slab, the
    # model says nothing. Placing it with the void uncut leaves EXTRA concrete
    # over a stair or a lift, which shows up on the first section and is one
    # boundary edit to fix. The visible mistake is the better one, but only
    # because the lines below say which opening was left out and where it is.
    return (True, kept,
            "{0}: placed WITHOUT {1} of its {2} opening(s) -- the concrete is "
            "as drawn, those voids are not cut.\n{3}".format(
                name, len(lines), len(hole_rings or []), "\n".join(lines)))


def _flat(ring):
    """The ring as (x, y) pairs, whatever shape its points arrived in.

    An opening `fold_plan` planned can still carry the z its hatch was read at,
    and a check that unpacked blindly would answer a three-component point with
    a ValueError where the caller asked for a verdict -- reporting the profile
    as an unpacking error, which tells the next run nothing.
    """
    return [(p[0], p[1]) for p in (ring or [])]


def _ring_faults(pts):
    """The FIRST thing wrong with ONE loop, in words, or None if it composes.

    Order matters for the report: a loop that doubles back through a corner it
    has already visited also crosses itself, and "it comes back to a corner"
    tells the reader where to look, where "it crosses itself" does not.

    CLOSURE is structural here -- `_curve_loop` walks the ring modulo its
    length, so the last corner is always joined to the first -- which leaves
    only the two ways that join can fail to close anything: too few corners to
    enclose an area at all, and an edge (the closing one included) whose two
    ends Revit would read as one point. `_sanitize_ring` has already merged
    everything under 15 mm, so the second only fires on a ring it handed back
    untouched, which is exactly the ring it could not reduce to three corners.
    """
    if len(pts) < 3:
        return "it has fewer than three distinct corners"
    n = len(pts)
    for i in range(n):
        if _distance(pts[i], pts[(i + 1) % n]) <= _PINCH_TOL_FT:
            return "one of its edges has no length"
    for i in range(n):
        for j in range(i + 1, n):
            if _distance(pts[i], pts[j]) <= _PINCH_TOL_FT:
                return "it comes back to a corner it has already been through"
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if (j + 1) % n == i or (i + 1) % n == j:
                continue                      # edges that share a corner
            c, d = pts[j], pts[(j + 1) % n]
            if _apart(a, b, c, d):
                continue
            if _seg_seg_distance(a, b, c, d) <= _PINCH_TOL_FT:
                return "it crosses or touches itself"
    return None


def _apart(a, b, c, d):
    """True when two segments' boxes stand further than the tolerance apart.

    The scans below are one edge against every other edge, and a slab outline
    tessellated round a curve carries hundreds. This is the cheap answer for
    the overwhelming majority of those pairs. Measured at the WIDER of the two
    tolerances, so it is safe for both callers: nothing it rejects can be
    within either, and it only ever saves work.
    """
    return (min(a[0], b[0]) - max(c[0], d[0]) > _TOUCH_TOL_FT
            or min(c[0], d[0]) - max(a[0], b[0]) > _TOUCH_TOL_FT
            or min(a[1], b[1]) - max(c[1], d[1]) > _TOUCH_TOL_FT
            or min(c[1], d[1]) - max(a[1], b[1]) > _TOUCH_TOL_FT)


def _hole_against_outline(hole, outer):
    """Why this opening cannot be cut out of that outline, or None.

    An opening has to be STRICTLY inside: a void that reaches the slab edge is
    not a hole at all but a bite out of the outline, and handing Revit the two
    loops it shares an edge with is the refusal this whole check exists for.
    """
    touch = _contact(hole, outer)
    if touch:
        return "{0} the slab's own outline".format(touch)
    for x, y in hole:
        if not _point_in_ring(x, y, outer):
            return "it lies outside the slab's outline"
    return None


def _contact(a, b):
    """How two rings meet ("it shares an edge with" / "crosses" / "touches"),
    or None when they are clear of one another.

    Every one of the three is a refusal -- Revit will not compose loops that
    meet at all -- but they are three different drawing mistakes, so they are
    reported apart: a shared edge is a bay drawn to its neighbour's line, a
    crossing is a void spilling out of its slab, a touch is a corner clipped.
    """
    shared = 0.0
    crosses = False
    touches = False
    n, m = len(a), len(b)
    for i in range(n):
        p, q = a[i], a[(i + 1) % n]
        for j in range(m):
            r, s = b[j], b[(j + 1) % m]
            if _apart(p, q, r, s):
                continue
            shared = max(shared, _shared_run_ft(p, q, r, s))
            if _segments_cross(p, q, r, s):
                crosses = True
            elif _seg_seg_distance(p, q, r, s) <= _TOUCH_TOL_FT:
                touches = True
    if shared > _TOUCH_TOL_FT:
        return "it shares an edge with"
    if crosses:
        return "it crosses"
    if touches:
        return "it touches"
    return None


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _segments_cross(a, b, c, d):
    """True when two segments cross PROPERLY -- interiors, not endpoints."""
    dx1, dy1 = b[0] - a[0], b[1] - a[1]
    dx2, dy2 = d[0] - c[0], d[1] - c[1]
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < 1e-12:
        return False                          # parallel: `_shared_run_ft` judges it
    t = ((c[0] - a[0]) * dy2 - (c[1] - a[1]) * dx2) / denominator
    u = ((c[0] - a[0]) * dy1 - (c[1] - a[1]) * dx1) / denominator
    eps = 1e-9
    return eps < t < 1.0 - eps and eps < u < 1.0 - eps


def _seg_seg_distance(a, b, c, d):
    """Closest approach of two segments, in feet (0 when they cross)."""
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(_pt_seg_dist(a[0], a[1], c, d), _pt_seg_dist(b[0], b[1], c, d),
               _pt_seg_dist(c[0], c[1], a, b), _pt_seg_dist(d[0], d[1], a, b))


def _shared_run_ft(a, b, c, d):
    """How far two segments run ALONG each other -- 0 when they merely meet.

    A crossing is a point and a shared edge is a length, and only the length
    says "these two loops were drawn to the same line", which is the tangency
    Revit refuses wholesale.
    """
    ux, uy = b[0] - a[0], b[1] - a[1]
    length = (ux * ux + uy * uy) ** 0.5
    if length <= 0.0:
        return 0.0
    ux, uy = ux / length, uy / length
    for p in (c, d):                          # both ends on a-b's infinite line?
        if abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) > _TOUCH_TOL_FT:
            return 0.0
    t1 = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
    t2 = (d[0] - a[0]) * ux + (d[1] - a[1]) * uy
    return max(0.0, min(max(t1, t2), length) - max(min(t1, t2), 0.0))


def _slab_name(mark, ring):
    """How the report calls this slab: its mark, or else where it stands.

    A bay the drawing never marked still has to be findable in Revit, and the
    only handle left is the ground it covers -- so an unmarked one is named by
    its centre, in the millimetres the user's project is measured in.
    """
    if mark:
        return str(mark)
    if not ring:
        return "an unmarked bay with no outline"
    cx, cy = _ring_centre(ring)
    return "the unmarked bay at ({0:.0f}, {1:.0f}) mm".format(cx, cy)


def _ring_note(ring):
    """The ring in the terms the next Revit run can search on: how many
    corners, how big, and where -- all in millimetres."""
    if not ring:
        return "an empty loop"
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    cx, cy = _ring_centre(ring)
    return ("{0} corner(s), {1:.0f} x {2:.0f} mm, centred at "
            "({3:.0f}, {4:.0f}) mm".format(
                len(ring), (max(xs) - min(xs)) * _MM, (max(ys) - min(ys)) * _MM,
                cx, cy))


def _ring_centre(ring):
    """The centre of the ring's bounding box, in millimetres."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return ((max(xs) + min(xs)) / 2.0 * _MM, (max(ys) + min(ys)) / 2.0 * _MM)


def _sanitize_ring(ring):
    pts = []
    for x, y in ring:
        if pts and ((x - pts[-1][0]) ** 2 + (y - pts[-1][1]) ** 2) ** 0.5 < _MIN_EDGE_FT:
            continue
        pts.append((x, y))
    if len(pts) > 1 and ((pts[0][0] - pts[-1][0]) ** 2
                         + (pts[0][1] - pts[-1][1]) ** 2) ** 0.5 < _MIN_EDGE_FT:
        pts.pop()
    out = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        # perpendicular distance of b from segment a-c: a true corner keeps it
        vx, vy = cx - ax, cy - ay
        length = (vx * vx + vy * vy) ** 0.5
        if length > 0 and abs((bx - ax) * vy - (by - ay) * vx) / length < _COLLINEAR_FT:
            continue
        out.append(pts[i])
    return out if len(out) >= 3 else pts


def _nest_openings(slabs):
    """Split loops into (outer slabs, {outer index: [opening slabs]}).

    A loop whose every vertex lies inside another loop is that loop's opening --
    the way a stair/lift void is drawn inside the floor outline. Nesting one level
    deep only (an island inside a void becomes its own slab again is NOT handled;
    none of the fixtures draws one)."""
    outers = []
    openings = {}
    order = sorted(range(len(slabs)),
                   key=lambda i: -abs(_ring_area(slabs[i]["ring"])))
    placed = []                       # indices into `outers`, biggest first
    for i in order:
        ring = slabs[i]["ring"]
        host = None
        for j in placed:
            if _ring_inside(ring, outers[j]["ring"]):
                host = j
                break
        if host is None:
            placed.append(len(outers))
            outers.append(slabs[i])
        else:
            openings.setdefault(host, []).append(slabs[i])
    return outers, openings


def _ring_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


_HOLE_CLEARANCE_FT = 50.0 / 304.8


def _ring_inside(inner, outer):
    """True only when `inner` sits STRICTLY inside `outer`, clear of its boundary.

    Adjacent slab panels SHARE edges; a shared-edge vertex sits ON the boundary,
    where a plain point-in-polygon answer is arbitrary -- that once classified a
    neighbouring panel as this floor's hole, and Floor.Create rejected the
    intersecting loops. A genuine void (stair/lift) is well inside: every vertex
    must be inside AND at least the clearance away from the outer boundary.
    """
    n = len(outer)
    for x, y in inner:
        if not _point_in_ring(x, y, outer):
            return False
        for i in range(n):
            if _pt_seg_dist(x, y, outer[i], outer[(i + 1) % n]) < _HOLE_CLEARANCE_FT:
                return False
    return True


def _pt_seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2)) if l2 else 0.0
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def _set_structural(instance):
    """Flag the floor structural (this is a structural toolkit); best-effort."""
    try:
        parameter = instance.get_Parameter(
            BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(1)
    except Exception:
        pass


def _resolve_type(doc, base_type, thickness_mm, cache):
    """(FloorType, note) of the given thickness, duplicating + caching.

    The thickness is written ONLY onto a type this run created; a type already in
    the model is reused as it stands. A None type means the name could not be
    had -- the caller skips the slab rather than casting it at the base type's
    thickness.
    """
    if thickness_mm is None:
        return base_type, None
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = naming.floor_type_name(key)
    floor_type, created, note = type_names.resolve_type(
        base_type, name, lambda: _sibling_types(doc, base_type))
    if created:
        _set_thickness(floor_type, thickness_mm)
    cache[key] = (floor_type, note)
    return floor_type, note


def _sibling_types(doc, base_type):
    """(name, FloorType) for the types in the SAME system family as base_type.

    Floors and Structural Foundations are both FloorType but they are different
    system families, and Revit scopes a type name's uniqueness to the family.
    Searching every FloorType in the document was therefore too wide in one
    direction -- a Floor type named "PAD 600 THK" could be handed back for a
    foundation pad, putting the pad in the wrong category.
    """
    wanted = _system_family(base_type)
    rows = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        if _system_family(floor_type) != wanted:
            continue
        rows.append((get_element_name(floor_type), floor_type))
    return rows


def _system_family(floor_type):
    """The system family a floor type belongs to ("Floor", "Foundation Slab")."""
    try:
        return floor_type.FamilyName
    except Exception:
        return None


def _set_thickness(floor_type, thickness_mm):
    """Resize the type's structural core layer to the labelled thickness."""
    try:
        structure = floor_type.GetCompoundStructure()
        index = structure.GetFirstCoreLayerIndex()
        structure.SetLayerWidth(index, mm_to_internal(thickness_mm))
        floor_type.SetCompoundStructure(structure)
    except Exception:
        pass   # thickness is best-effort; the loop still places at type default


def _set_mark(instance, mark):
    if not mark:
        return
    try:
        set_element_mark(instance, mark)
    except Exception:
        pass
