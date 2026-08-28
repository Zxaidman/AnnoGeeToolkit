# -*- coding: utf-8 -*-
"""Work out the geometry of a FOLD or SUNK step, before Revit is touched.

A step is not one element. The office builds it from THREE floors -- confirmed
against their own Revit detail -- and the middle one is the part a naive
two-floor reading has no answer for:

  1. the PARENT, on its level, with the stepped area cut out of it;
  2. the SUPPORT, hanging under the parent's edge along the step line: the
     vertical concrete between the two soffits;
  3. the DROPPED slab, at the lower level.

Without the support the step is a gap rather than concrete -- a model that looks
right in plan and is hollow in section.

THE SUPPORT'S EXISTENCE AND DEPTH ARE DERIVED, NOT CONFIGURED. Take the
parent's top as 0:

    parent soffit          -T_parent
    dropped slab top       -d                    (d = the fold/sunk value)
    dropped slab soffit    -(d + T_dropped)

A support exists only where there is a VOID to fill -- where the drop is
deeper than the parent is thick (d > T_parent), so the dropped slab's top sits
below the parent's soffit and daylight shows between them. Where d <= T_parent
the dropped slab's own side face already rises past the parent's soffit: the
two faces overlap, the section is solid, and a "support" there is a second
slab buried inside concrete that exists. That is not hypothetical -- the
corridor drawing produced exactly that pair of phantom 250 mm footings before
this condition was tightened from "soffit gap > 0" to "void exists".

Where the void is real, the support is cast full height, soffit to soffit --
the user's own detail shows the 350 drop off a 200 slab cast as one 350-deep
support at -200, overlapping the dropped slab's edge rather than stopping at
its top:

    offset  = -T_parent
    depth   =  d + T_dropped - T_parent
    width   =  T_parent                          (in plan, under the parent)

The sunk cases both land right under this rule, each for its own reason.
test10's original F6 (1000 thick, sunk 1000, between 2000-thick pads):
1000 < 2000, no void, the pad IS the face. The redrawn corridor (sunk 250 in a
500 block): 250 < 500, no void, the dropped slab's edge IS the face. The
first looks like "the soffit gap is zero" -- 1000+1000-2000 -- but that is the
coincidence of its numbers, not the rule; the corridor's gap is 250 and there
is still nothing to fill.

A support is one slab per contiguous stepped RUN, never a strip per edge, and
neighbouring step regions POOL theirs: three folds drawn in a row inside one
footing get one support slab whose outer edge wraps the whole group and whose
hollows are the three folds -- the concrete between them is part of the same
cast. Separate collars would overlap each other in the gaps, which Revit takes
as three intersecting floors.

TWO THINGS ARE STEPPED, NOT ONE, AND THE DRAWING DOES NOT SAY WHICH IN WORDS.
A sheet that hatches everything sunk hatches BAYS of floor, which step by the
three floors above, and STRIPS the width of a beam, which mean that beam hangs
lower -- test14 writes both with one legend line, "INDICATES SLAB/BEAM SUNK BY
150MM.", and one routed layer. `sunk_split` tells them apart on the hatch's
narrow side and `beam_drops` decides which member a strip claims; both
thresholds sit in deserts measured on that drawing and recorded beside them.

A SUNK BEAM KEEPS ITS DEPTH AND ITS WHOLE BODY DROPS -- the user's decision.
Top and soffit move down together with the slab beside them, which is the usual
sunken-slab detail. The beam is not deepened to reach back up to its level, and
it is not cut in two where the strip ends, so a strip covering part of a
member still drops all of it. That makes a dropped beam ONE NUMBER, and there
is no geometry for it here beyond deciding whose number it is.

Revit-free, so all of it is unit-testable and replayable offline. Compare
`footing_plan.py`, which does the same job for the pads.
"""

import math

from . import config
from .classify.layers import CATEGORY_FOLD, CATEGORY_SUNK
from .slab_graph import (_centroid, _dedup_ring, _dist,
                         _point_in_ring, _signed_area)

_MM = config.MM_PER_FT

FOLD = "fold"
SUNK = "sunk"

_CATEGORY_KIND = {CATEGORY_FOLD: FOLD, CATEGORY_SUNK: SUNK}

# A "step" deeper than this is a STOREY, not a step. Test9's legend carries
# `T.O.S. +50MM`, `+400MM` and `+6250` in the same list: the first two are
# steps and the third is a different floor, which must never be built as a fold
# hanging off this one. 2000 is a real fold (test10's F3), so the line sits
# above that and well below a storey height.
_MAX_STEP_MM = 3000.0

# How far outside an edge to look for the concrete the step steps down from.
# Small: the dropped region and its neighbour SHARE the edge in the fixture, so
# anything wider than the neighbour is not a subtler test, just a wrong one.
_PROBE_MM = 10.0

# Two rings are "the same outline" within this much area. test10's sunk hatch
# and its F6 outline are drawn to identical coordinates; the tolerance is for
# arithmetic, not for drafting slop.
_SAME_AREA = 0.01

# THE NARROW SIDE THAT TELLS A SUNK BAY FROM A SUNK STRIP. A drawing that
# hatches everything sunk hatches two different things with one pattern: BAYS
# of floor, which step, and STRIPS the width of a beam, which mean that beam
# hangs lower. Measured on test14's 273 plan sunk hatches, the short side of
# the bounding box runs 99.9 .. 350.0 and then NOTHING until 1007.4, from where
# it runs on to 1665 -- a 657 mm desert, four times the widest gap anywhere
# else in that histogram, with 144 hatches below it and 129 above. The
# threshold is the geometric mean of the two rims (593.7), rounded to 600, the
# way legend's `_REACH_MM` was drawn. It is also comfortably above every beam
# width the drawing carries (150..400, with one 685 that no strip sits on).
_SUNK_BAY_MIN_SIDE_MM = 600.0

# WHEN A STRIP CLAIMS A BEAM, asked from both ends because one end alone has a
# blind spot. Measured over every (strip, beam) pair on test14:
#
#   share of the STRIP lying inside the beam  0.0000..0.1270, then 0.8685..1.0
#   share of the BEAM lying inside the strip  0.0000..0.1933, then 0.4964..1.0
#
# Both histograms are two clusters and a desert, and both deserts mean the same
# thing: below is a junction clip -- a strip running along one beam grazing the
# one it tees into -- and above is a strip drawn along the beam it means. 0.5
# sits in the first desert; the geometric mean of the second's rims is 0.31,
# rounded to 0.3.
#
# The strip's share alone would be blind to ONE case the corpus does not draw
# and a drawing may: a strip running over a member the segmentation cut into
# pieces at its columns. Each piece would then hold half the strip, or a third,
# and the run would drop in parts or not at all -- a beam at two levels, which
# is the failure this whole pass exists to avoid. The beam's own share answers
# that case (each piece is covered end to end) and, on test14, claims not one
# pair the strip's share did not already claim.
_STRIP_CLAIM_SHARE = 0.5
_BEAM_CLAIM_SHARE = 0.3


def step_regions(regions):
    """[(ring, kind)] for the hatched fold/sunk regions, in reading order.

    `regions` are RegionRecords the reader kept out of `records` (a hatch is an
    area, not a curve). Only the two step categories are taken; a column fill
    or a legend swatch on some other layer is not a step.
    """
    return [(ring, kind) for ring, kind, _region in _step_rows(regions)]


def _step_rows(regions):
    """[(ring, kind, region)] -- `step_regions` with the record kept.

    The record is what carries the hatch PATTERN, and a legend prices a step by
    pattern, never by layer: test14 routes ONE layer, HAT, and that layer holds
    three different sunk depths plus a fourth meaning that is not a step at all.
    """
    out = []
    for region in (regions or []):
        kind = _CATEGORY_KIND.get(getattr(region, "category", None))
        if kind is None:
            continue
        ring = _dedup_ring([(p[0], p[1]) for p in region.points])
        if len(ring) >= 3:
            out.append((ring, kind, region))
    return out


def plan_steps(plans, regions, max_step_mm=None, depths=None, skip_ids=None):
    """The three parts of every step, plus what was refused and why.

    `plans` are the outlines `foundation_plan.plan_foundations` read (or any
    dicts shaped {"ring", "thickness_mm", "steps", "mark"} -- slab loops carry
    the same three keys, which is what lets this serve both). `regions` are the
    reader's hatches, already classified.

    Returns {"steps": [...], "skipped": [reasons], "notes": [reasons]}. Each
    step is

        {"kind", "ring", "depth_mm", "mark",
         "dropped": {"ring", "thickness_mm", "offset_mm"},
         "supports": [{"ring", "holes", "thickness_mm", "offset_mm"}],
         "opening": ring or None,
         "host_index": i}

    Neighbouring collars POOL (`_pool_collars`): one slab per touching group,
    carried by the group's first step, every pooled region in its `holes`.

    `opening` is the hole the PARENT needs cut in it, and it is None exactly
    when the region IS its host outline -- test10's sunk strip is its own F6
    foundation, so there is nothing to cut and the host itself is what drops.

    THE DEPTH COMES FROM ONE OF TWO PLACES. Without `depths` it comes from the
    host's own step NOTE, which is how the foundation drawings say it
    ("F6_SUNK 1000"). With `depths` -- {hatch pattern: depth_mm}, the legend's
    table -- it comes from the region's PATTERN, which is how test14 says it:
    one routed layer, ANGLE meaning -150, ANSI37 -75, HONEY -50, and 72
    plan GOST_GLASS hatches on that same layer meaning "SLAB AT BEAM BOTTOM",
    which is no depth at all and is refused by name rather than inheriting a
    neighbour's. The sign is dropped here: fold_plan's depth is a magnitude
    downward, and which way a signed T.O.S. value points is legend.py's open
    question, not this module's.

    `skip_ids` are id()s of regions never to route -- the legend's own
    demonstration swatches, which are hatches like every other one and would
    otherwise be read as a step in the middle of the legend block.
    """
    limit = _MAX_STEP_MM if max_step_mm is None else float(max_step_mm)
    out = {"steps": [], "skipped": [], "notes": []}
    rings = [(index, plan) for index, plan in enumerate(plans or [])
             if plan.get("ring") and len(plan["ring"]) >= 3]
    unpriced = {}
    for ring, kind, region in _step_rows(regions):
        if skip_ids and id(region) in skip_ids:
            continue
        depth = None
        if depths is not None:
            depth = _pattern_depth(region, depths)
            if depth is None:
                _count_by_pattern(region, unpriced)
                continue
        host_index, host = _host_for(ring, rings)
        if host is None:
            out["skipped"].append(
                "a {0} region of {1:.1f} m2 sits inside no outline: nothing to "
                "step".format(kind, area_m2(ring)))
            continue
        note = None
        if depths is None:
            note = _note_for(ring, host, kind)
            depth = None if note is None else float(note["step_mm"])
        if depth is None:
            out["skipped"].append(
                "a {0} region in {1} carries no depth: the note that would "
                "give it is missing".format(kind, host.get("mark") or "an "
                                            "unnamed outline"))
            continue
        if depth > limit:
            # NOT a fold: a different storey. Building it as one would hang a
            # floor a storey below this one off the wrong level.
            out["skipped"].append(
                "{0:.0f} mm is a storey, not a {1} (over {2:.0f} mm): the "
                "region in {3} is left flat".format(
                    depth, kind, limit, host.get("mark") or "an unnamed outline"))
            continue
        out["steps"].append(_parts(ring, kind, depth, note, host, host_index,
                                   rings))
    _report_unpriced(unpriced, out["skipped"])
    _pool_collars(out["steps"], out["notes"])
    return out


def _pattern_depth(region, depths):
    """The depth `depths` prices this region's hatch PATTERN at, a magnitude.

    None means the table says nothing about this pattern, which is a refusal to
    be reported and never a reason to reach for some other region's number.
    """
    value = (depths or {}).get(getattr(region, "pattern", None))
    if value is None:
        return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def _count_by_pattern(region, counts):
    """Tally a refused hatch under its PATTERN, for a one-line report."""
    pattern = getattr(region, "pattern", None) or "an unnamed pattern"
    counts[pattern] = counts.get(pattern, 0) + 1


def _report_unpriced(unpriced, skipped):
    """One line per PATTERN nothing priced, not one per hatch.

    test14 routes 72 GOST_GLASS hatches on the sunk layer and none of them is a
    step; seventy-two identical sentences would bury the eight lines that
    matter, which is the same reason run_builders masks its skip numbers.
    """
    for pattern in sorted(unpriced):
        skipped.append(
            "{0} hatch(es) of pattern {1} carry no depth: the legend prices "
            "the pattern, and this one it does not -- left flat".format(
                unpriced[pattern], pattern))


def sunk_split(regions, depths, swatch_ids=None):
    """Which sunk hatches step a BAY, which drop a BEAM, and which do neither.

    Returns {"bays": [region], "strips": [(region, depth_mm)], "skipped":
    [reasons]}. The split is the narrow side of the hatch against
    `_SUNK_BAY_MIN_SIDE_MM`, whose measured desert is recorded beside it: a
    strip no wider than a beam is a statement about that beam, and a bay of
    floor is a statement about the slab.

    Both sides are priced by PATTERN through `depths`, so a hatch the legend
    says nothing about routes nowhere and is named -- and the legend's own
    demonstration swatches, whose ids arrive in `swatch_ids`, are dropped
    before anything else looks at them. A swatch is 1050x500 on test14, which
    the narrow-side rule would happily call a strip; excluding it by identity
    is the same lock `legend._plan_layers` uses, and it is the first of two.
    The second is arithmetic: a swatch sits inside the legend block, where
    there is no slab loop to host it and no beam to claim, so even an
    unrecognised one builds nothing.
    """
    out = {"bays": [], "strips": [], "skipped": []}
    unpriced = {}
    for ring, _kind, region in _step_rows(regions):
        if swatch_ids and id(region) in swatch_ids:
            continue
        depth = _pattern_depth(region, depths)
        if depth is None:
            _count_by_pattern(region, unpriced)
            continue
        if _narrow_side_mm(ring) > _SUNK_BAY_MIN_SIDE_MM:
            out["bays"].append(region)
        else:
            out["strips"].append((region, depth))
    _report_unpriced(unpriced, out["skipped"])
    return out


def beam_drops(segments, strips):
    """{"drops": {segment index: depth_mm}, "skipped": [reasons]}.

    A SUNK BEAM KEEPS ITS DEPTH AND ITS WHOLE BODY DROPS -- the user's
    decision, and the usual sunken-slab detail: top and soffit move down
    together with the slab beside them. So there is one number per beam here
    and no geometry: nothing is deepened, and nothing is cut in two at the
    strip's ends. A strip covering PART of a beam still drops all of it,
    because the alternative is splitting the member, which the user ruled out.

    A strip claims a beam when half of the STRIP lies inside that beam's body
    (centreline widened by its width), or three tenths of the BEAM lies inside
    the strip -- the two measured rules recorded beside their constants. It may
    claim several: a member the segmentation cut at its columns is several
    segments under one strip, and all of them drop.

    A strip that claims nothing is REPORTED, grouped by pattern. On test14 that
    is half of them: little 150x100 and 250x435 patches of sunk floor left over
    where a strip meets a column, too small to be a bay and lying beside a beam
    rather than on one. Building a floor out of a 150x100 patch is worse than
    saying it was left alone.

    `segments` are the STRAIGHT beams only -- a curved member is driven by an
    arc and placed by a different call. No strip in the corpus lies on one, and
    one that did would report here as claiming nothing rather than silently
    leaving a curved beam up where it was.
    """
    out = {"drops": {}, "skipped": []}
    bodies = []
    for index, segment in enumerate(segments or []):
        body = _beam_body(segment)
        if body:
            bodies.append((index, body))
    orphans = {}
    conflicts = 0
    for region, depth in (strips or []):
        points = getattr(region, "points", None) or []
        ring = _dedup_ring([(p[0], p[1]) for p in points])
        if len(ring) < 3:
            continue
        claimed = _claimed_beams(ring, bodies)
        if not claimed:
            _count_by_pattern(region, orphans)
            continue
        for index in claimed:
            standing = out["drops"].get(index)
            if standing is not None and abs(standing - depth) > 1e-6:
                conflicts += 1
            out["drops"][index] = depth if standing is None else max(standing,
                                                                     depth)
    for pattern in sorted(orphans):
        out["skipped"].append(
            "{0} sunk strip(s) of pattern {1} lie on no beam: too narrow to "
            "be a bay and not over a member, so nothing is dropped for "
            "them".format(orphans[pattern], pattern))
    if conflicts:
        out["skipped"].append(
            "{0} beam(s) are covered by sunk strips of two depths: each takes "
            "the deeper, since one member cannot sit at two levels".format(
                conflicts))
    return out


def slab_defs_with_steps(slab_defs, steps):
    """(defs, notes) -- the slab loops with their steps built into them.

    The parent loop gains the stepped region as a HOLE, and is DIVIDED when
    that hole reaches its boundary, exactly as a footing outline is (a profile
    whose hole shares two edges with its outer ring is one Floor.Create
    refuses). A loop the drawing marks sunk in its entirety is not placed flat
    at all: there the dropped slab IS that loop, so the flat one would be a
    second floor in the same place. Every dropped slab and support then follows
    as a def of its own, carrying the offset that is the only thing telling the
    three floors of a step apart.

    Revit-free, and deliberately so: what comes back is the same list of dicts
    `slab_labels.apply_slab_labels` produced, three keys richer -- `holes`,
    `offset_mm` and `part` -- so the builder has three things to learn and the
    arithmetic stays testable offline.
    """
    notes = []
    openings = {}
    whole = set()
    for step in (steps or []):
        if step.get("opening") is None:
            whole.add(step["host_index"])
        else:
            openings.setdefault(step["host_index"], []).append(step["opening"])
    out = []
    for index, slab in enumerate(slab_defs or []):
        ring = slab.get("ring")
        if not ring or len(ring) < 3:
            out.append(slab)
            continue
        if index in whole:
            continue
        holes = list(slab.get("holes") or []) + openings.get(index, [])
        if not holes:
            out.append(slab)
            continue
        pieces = split_profile([(p[0], p[1]) for p in ring], holes)
        if not pieces:
            # The bay covers the loop end to end -- drawn a shade wider than
            # the outline the beam faces gave it, so `_is_host_itself` read
            # them as two shapes rather than one. Nothing of the parent
            # survives the subtraction, and the dropped slab IS the floor
            # there; the alternative, placing a flat slab of nothing, is not
            # one. Said out loud because a loop that quietly stops being
            # placed is the hardest kind of missing floor to find.
            notes.append(
                "{0} slab loop is wholly covered by its sunk bay: nothing is "
                "placed flat there, the dropped slab is the floor".format(
                    slab.get("mark") or "an unnamed"))
        if len(pieces) > 1:
            notes.append(
                "{0} slab loop divided into {1} piece(s): a sunk bay reaches "
                "its edge".format(slab.get("mark") or "an unnamed",
                                  len(pieces)))
        for piece_ring, piece_holes in pieces:
            piece = dict(slab)
            piece["ring"] = piece_ring
            piece["holes"] = piece_holes
            if len(pieces) > 1:
                # the pieces are not the ring that was drawn, so the arc
                # triples recorded against that ring no longer describe them
                piece["arcs"] = []
            out.append(piece)
    for step in (steps or []):
        out.extend(_step_defs(step))
    return out, notes


def _step_defs(step):
    """[def] -- one step's dropped slab and support(s), as slab loops.

    `part` is what keeps them out of the builder's opening nesting. A dropped
    slab lies wholly inside its parent's outline, which is precisely the shape
    of a stair void, and without the key the floor at the bottom of the step
    would be read as a hole in the floor above it.
    """
    mark = step.get("mark")
    kind = step.get("kind") or "step"
    defs = []
    dropped = step.get("dropped") or {}
    if dropped.get("ring"):
        defs.append({"ring": [(p[0], p[1]) for p in dropped["ring"]],
                     "holes": [], "arcs": [],
                     "thickness_mm": dropped.get("thickness_mm"),
                     "offset_mm": dropped.get("offset_mm"),
                     "mark": _part_mark(mark, kind),
                     "part": kind})
    for support in (step.get("supports") or []):
        defs.append({"ring": [(p[0], p[1]) for p in support["ring"]],
                     "holes": [[(p[0], p[1]) for p in hole]
                               for hole in (support.get("holes") or [])],
                     "arcs": [],
                     "thickness_mm": support.get("thickness_mm"),
                     "offset_mm": support.get("offset_mm"),
                     "mark": _part_mark(mark, "support"),
                     "part": "support"})
    return defs


def _part_mark(mark, part):
    return "{0}-{1}".format(mark, part.upper()) if mark else None


def _narrow_side_mm(ring):
    """The SHORT side of the ring's bounding box, in millimetres."""
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return min(max(xs) - min(xs), max(ys) - min(ys)) * _MM


def _beam_body(segment):
    """A beam segment's plan footprint: its centreline widened by its width.

    None for a segment with no length -- a beam collapsed onto a column centre
    has no body to cover, and dividing by its length would be the only thing
    this function ever raised on.
    """
    start = segment.get("start")
    end = segment.get("end")
    if not start or not end:
        return None
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length <= 0:
        return None
    half = config.mm_to_ft(segment.get("width_mm") or 0.0) / 2.0
    if half <= 0:
        return None
    nx, ny = -dy / length * half, dx / length * half
    return [(start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny),
            (end[0] - nx, end[1] - ny), (start[0] - nx, start[1] - ny)]


def _claimed_beams(ring, bodies):
    """[index] of the beams this strip covers, by the two measured shares."""
    strip = abs(_signed_area(ring))
    if strip <= 0:
        return []
    claimed = []
    for index, body in bodies:
        piece = _clipped(ring, body)
        if len(piece) < 3:
            continue
        overlap = abs(_signed_area(piece))
        beam = abs(_signed_area(body))
        if (overlap / strip >= _STRIP_CLAIM_SHARE
                or (beam > 0 and overlap / beam >= _BEAM_CLAIM_SHARE)):
            claimed.append(index)
    return claimed


def _clipped(subject, window):
    """`subject` clipped to the CONVEX `window` (Sutherland-Hodgman).

    Both shapes here are rectangles -- a hatch as drawn and a beam's body -- so
    a convex clip is exact, and a general polygon intersection would be a
    library this module does not need.
    """
    out = _counter_clockwise(subject)
    window = _counter_clockwise(window)
    count = len(window)
    for index in range(count):
        a = window[index]
        b = window[(index + 1) % count]
        ex, ey = b[0] - a[0], b[1] - a[1]
        source, out = out, []
        for position in range(len(source)):
            p = source[position - 1]
            q = source[position]
            p_in = (ex * (p[1] - a[1]) - ey * (p[0] - a[0])) >= 0.0
            q_in = (ex * (q[1] - a[1]) - ey * (q[0] - a[0])) >= 0.0
            if q_in:
                if not p_in:
                    out.append(_edge_crossing(p, q, a, b))
                out.append(q)
            elif p_in:
                out.append(_edge_crossing(p, q, a, b))
        if not out:
            return []
    return out


def _edge_crossing(p, q, a, b):
    """Where segment p-q crosses the infinite line a-b."""
    rx, ry = q[0] - p[0], q[1] - p[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-15:
        return q
    t = ((a[0] - p[0]) * sy - (a[1] - p[1]) * sx) / denominator
    return (p[0] + t * rx, p[1] + t * ry)


def _counter_clockwise(ring):
    return list(ring) if _signed_area(ring) > 0 else list(reversed(ring))


def _pool_collars(steps, notes):
    """Merge the collars of NEIGHBOURING regions into one slab per group.

    test10 draws three fold rectangles in a row inside each raft, 300 mm
    apart, and a collar reaches one parent-thickness (1500) past its region --
    so the three collars overlap heavily, and Revit reads them as three
    intersecting floors. The cast reality is ONE support: its outer edge wraps
    the whole group, the three folds are its hollows, and the concrete between
    folds belongs to it. So collars in the same host, at the same thickness
    and offset, whose outer rings touch, pool: outer ring = the union outline,
    holes = every region in the group (mutated in place -- the pooled slab
    replaces the first group member's collar and the rest lose theirs).

    Pooling is rectilinear -- the union walks a compressed grid -- so a group
    with a non-rectangular collar is left unpooled and says so. Every hatch in
    this corpus is a rectangle; the note is for the drawing that breaks that.
    """
    collars = []               # (step, support, rect) for every poolable collar
    irregular = 0
    for step in steps:
        for support in step["supports"]:
            if not support["holes"]:
                continue                     # strips and Ls do not pool
            rect = _as_rect(support["ring"])
            if rect is None:
                irregular += 1
                continue
            collars.append((step, support, rect))
    if irregular:
        notes.append("{0} support collar(s) not rectangular: left out of "
                     "pooling, placed on their own".format(irregular))
    groups = _touching_groups(collars)
    for group in groups:
        if len(group) < 2:
            continue
        outer, pockets = _rect_union_outline([rect for _s, _sup, rect in group])
        if outer is None:
            notes.append("{0} overlapping support collars left separate: a "
                         "non-rectangular union".format(len(group)))
            continue
        # A union that NECKS to a point -- an enclosed pocket meeting the
        # outer edge at a shared corner -- is not one castable slab, and
        # Revit rejects loops that touch. Those collars stay separate floors,
        # which is exactly what the drawing shows there: two pieces of
        # concrete meeting at a corner.
        pinch = set(outer) & set(point for pocket in pockets
                                 for point in pocket)
        if pinch:
            notes.append("{0} support collars neck to a point: left "
                         "separate".format(len(group)))
            continue
        first = group[0][1]
        first["ring"] = outer
        holes = []
        for _step, support, _rect in group:
            holes.extend(support["holes"])
        # MERGED, not concatenated. Two folds drawn edge-to-edge arrive as two
        # rings sharing a full segment, and a duplicated hatch as two coincident
        # ones -- either handed to Revit verbatim is a tangent pair of sketch
        # loops that kills the whole support. The union dissolves shared edges
        # and duplicates into one hollow.
        first["holes"] = _merged_holes(holes) + pockets
        for step, support, _rect in group[1:]:
            step["supports"].remove(support)


def _touching_groups(collars):
    """Collars grouped transitively by touching outers, same depth and offset.

    A group never crosses hosts: a support is cast within one footing, so two
    footings' collars stay two slabs even if the drawn rectangles graze.
    """
    groups = []
    for entry in collars:
        step, support, rect = entry
        joined = None
        for group in groups:
            for other_step, other_support, other_rect in group:
                if other_step["host_index"] != step["host_index"]:
                    continue
                if other_support["thickness_mm"] != support["thickness_mm"]:
                    continue
                if other_support["offset_mm"] != support["offset_mm"]:
                    continue
                if not _rects_touch(rect, other_rect):
                    continue
                if joined is None:
                    group.append(entry)
                    joined = group
                else:
                    joined.extend(group)
                    group[:] = []
                break
        if joined is None:
            groups.append([entry])
    return [group for group in groups if group]


_TOUCH_TOL_FT = 1.0 / 304.8    # a millimetre: drawn-to-meet counts as touching


def _rects_touch(a, b):
    """Overlapping or edge-sharing -- corner-to-corner contact is NOT touching.

    Two collars meeting only at a point are two perfectly placeable floors, and
    pooling them buys nothing. It also costs: the union's boundary passes
    through the shared corner TWICE (a pinch), which is where the ring walk
    used to splice two loops into one self-intersecting figure-eight.
    """
    gap_x = min(a[2], b[2]) - max(a[0], b[0])
    gap_y = min(a[3], b[3]) - max(a[1], b[1])
    if gap_x < -_TOUCH_TOL_FT or gap_y < -_TOUCH_TOL_FT:
        return False
    return gap_x > _TOUCH_TOL_FT or gap_y > _TOUCH_TOL_FT


def _as_rect(ring):
    """(x0, y0, x1, y1) when the ring is an axis-aligned rectangle, else None.

    Collinear vertices are dropped first: a CAD polyline routinely lands a
    vertex mid-edge, and a rectangle with five points is still a rectangle.
    Without this the collar built round it was quietly left out of pooling --
    which is the overlapping-floors defect pooling exists to fix.
    """
    cleaned = _collinear_simplified(_dedup_ring(list(ring)))
    if len(cleaned) != 4:
        return None
    tol = _TOUCH_TOL_FT
    for index in range(4):
        a = cleaned[index]
        b = cleaned[(index + 1) % 4]
        if abs(a[0] - b[0]) > tol and abs(a[1] - b[1]) > tol:
            return None                  # a slanted edge
    xs = [p[0] for p in cleaned]
    ys = [p[1] for p in cleaned]
    return (min(xs), min(ys), max(xs), max(ys))


def _rect_union_outline(rects):
    """(outer_ring, pocket_rings) -- the outline of a union of rectangles.

    Walks a coordinate-compressed grid: cells covered by any rectangle are the
    union, and the boundary between covered and uncovered is the outline.
    Exact for axis-aligned input, which is what `_as_rect` guarantees. Returns
    (None, []) if the union is not one connected piece -- the caller grouped
    by touching, so that would mean the grouping and the geometry disagree.

    `pocket_rings` are ENCLOSED uncovered areas -- a courtyard of collars.
    They become holes: the parent above them is full depth, so support
    concrete there would hang below solid slab that needs none.
    """
    # Coordinates within a millimetre are ONE coordinate. The drawn rectangles
    # carry float noise in their last bits, and without this the union outline
    # grows micro-jogs a fraction of a nanometre wide -- sixteen vertices where
    # the shape has four, on edges shorter than Revit's curve tolerance.
    snap_x = _snapped([r[0] for r in rects] + [r[2] for r in rects])
    snap_y = _snapped([r[1] for r in rects] + [r[3] for r in rects])
    rects = [(snap_x[r[0]], snap_y[r[1]], snap_x[r[2]], snap_y[r[3]])
             for r in rects]
    xs = sorted(set(snap_x.values()))
    ys = sorted(set(snap_y.values()))
    covered = {}
    for x0, y0, x1, y1 in rects:
        for column in range(len(xs) - 1):
            if xs[column] < x0 - _TOUCH_TOL_FT or xs[column + 1] > x1 + _TOUCH_TOL_FT:
                continue
            for row in range(len(ys) - 1):
                if ys[row] < y0 - _TOUCH_TOL_FT or ys[row + 1] > y1 + _TOUCH_TOL_FT:
                    continue
                covered[(column, row)] = True

    rings = _grid_rings(xs, ys, covered)
    if rings is None:
        return None, []                  # open boundary: not a clean union
    outers = [ring for ring in rings if _signed_area(ring) > 0]
    if len(outers) != 1:
        return None, []                  # disconnected union, or none at all
    pockets = [ring for ring in rings if _signed_area(ring) < 0]
    return outers[0], pockets


def _grid_rings(xs, ys, covered):
    """Every boundary ring of the covered cells, or None if the walk breaks.

    Boundary segments are oriented with the COVERED side on the left, so an
    outer boundary walks counter-clockwise and an enclosed hole clockwise --
    the sign of the walked area tells the two apart with no containment test.
    """
    segments = {}
    for (column, row) in covered:
        x0, x1 = xs[column], xs[column + 1]
        y0, y1 = ys[row], ys[row + 1]
        if (column, row - 1) not in covered:
            segments[((x0, y0), (x1, y0))] = True    # bottom edge, left-to-right
        if (column, row + 1) not in covered:
            segments[((x1, y1), (x0, y1))] = True    # top edge, right-to-left
        if (column - 1, row) not in covered:
            segments[((x0, y1), (x0, y0))] = True    # left edge, downward
        if (column + 1, row) not in covered:
            segments[((x1, y0), (x1, y1))] = True    # right edge, upward

    starts = {}
    for (a, b) in segments:
        starts.setdefault(a, []).append(b)
    rings = []
    while segments:
        (a, b) = next(iter(segments))
        ring = [a]
        cursor = (a, b)
        while True:
            del segments[cursor]
            starts[cursor[0]].remove(cursor[1])
            ring.append(cursor[1])
            if cursor[1] == a:
                break
            following = starts.get(cursor[1]) or []
            if not following:
                return None
            cursor = (cursor[1], _sharpest_right(cursor[0], cursor[1], following))
        rings.append(_collinear_simplified(ring[:-1]))
    return rings


def _sharpest_right(previous, vertex, following):
    """The continuation turning hardest RIGHT -- the only sound choice at a pinch.

    A vertex where two covered cells meet only diagonally has FOUR boundary
    segments through it, two of them outgoing. A boundary walk traces the
    face on its RIGHT (the uncovered side), and staying on that same face
    means the most clockwise continuation; taking whichever outgoing happened
    to be listed first spliced the outer ring and the enclosed pocket into
    one figure-eight whose net area still read positive -- a self-intersecting
    ring the single-outer guard cannot see and Revit will not take.
    """
    if len(following) == 1:
        return following[0]
    into = math.atan2(vertex[1] - previous[1], vertex[0] - previous[0])
    best, best_turn = following[0], None
    for candidate in following:
        out = math.atan2(candidate[1] - vertex[1], candidate[0] - vertex[0])
        turn = (out - into + math.pi) % (2.0 * math.pi)
        if best_turn is None or turn < best_turn:
            best, best_turn = candidate, turn
    return best


def split_profile(outer, holes):
    """[(ring, holes)] -- the outline's profile as Revit will accept it.

    A hole STRICTLY inside the outline stays a hole. A hole that reaches the
    outline's boundary is not a hole at all -- it DIVIDES the outline. The
    corridor block is the case: its sunk bay spans the block's full width, so
    "the block with a hole" hands Floor.Create two loops sharing two edges,
    which it rejects ("curve loops intersect with each other" -- the user's
    one-error run). The concrete truth is a north piece and a south piece with
    the dropped slab between them, and that is what this returns.

    Holes that TOUCH each other fuse FIRST, before any of that is judged. The
    corridor is why: its two crossed-out parts and the sunk bay between them
    arrive as three rectangles sharing edges, and three tangent loops in one
    profile is a sketch Revit rejects wholesale -- the cast has ONE corridor
    hole, so that is what the profile must carry. Same `_merged_holes` walk the
    collar pooling uses, and the same rectilinear-only stance: a slanted hole
    would come back as a grid staircase, so it passes through untouched.

    Rectilinear, like the union above: cells of a compressed grid are covered
    when inside the outline and not inside a boundary-reaching hole, and each
    connected run of covered cells walks out as one piece. Interior holes are
    handed to whichever piece contains them; a piece can also GAIN a hole the
    subtraction itself created (a U-shaped cut closing round an island).
    """
    inside, touching = [], []
    for hole in _fused(holes or []):
        if _strictly_inside(hole, outer):
            inside.append(hole)
        else:
            touching.append(hole)
    if not touching:
        return [(outer, inside)]

    coords = list(outer)
    for hole in touching:
        coords.extend(hole)
    snap_x = _snapped([p[0] for p in coords])
    snap_y = _snapped([p[1] for p in coords])
    xs = sorted(set(snap_x.values()))
    ys = sorted(set(snap_y.values()))
    covered = {}
    for column in range(len(xs) - 1):
        for row in range(len(ys) - 1):
            centre = ((xs[column] + xs[column + 1]) / 2.0,
                      (ys[row] + ys[row + 1]) / 2.0)
            if not _point_in_ring(centre, outer):
                continue
            if any(_point_in_ring(centre, hole) for hole in touching):
                continue
            covered[(column, row)] = True
    rings = _grid_rings(xs, ys, covered)
    if rings is None:
        return [(outer, inside)]        # a walk that failed changes nothing
    pieces = [(ring, []) for ring in rings if _signed_area(ring) > 0]
    orphans = [ring for ring in rings if _signed_area(ring) < 0]
    for hole in inside + orphans:
        anchor = _centroid(hole)
        for ring, piece_holes in pieces:
            if _point_in_ring(anchor, ring):
                piece_holes.append(hole)
                break
    return pieces


def _fused(holes):
    """The holes with shared edges, overlaps and duplicates dissolved.

    Only the rectilinear ones run through the union -- the grid is exact for
    those and a staircase approximation for anything slanted, so a slanted
    hole is handed back exactly as drawn. Holes that touch nothing come back
    as themselves (each is its own connected piece of the walk).
    """
    straight = [hole for hole in holes if _rectilinear(hole)]
    if len(straight) < 2:
        return list(holes)
    slanted = [hole for hole in holes if not _rectilinear(hole)]
    return _merged_holes(straight) + slanted


def _rectilinear(ring):
    """True when every edge is axis-parallel -- what the grid walk is exact for."""
    cleaned = _collinear_simplified(_dedup_ring(list(ring)))
    count = len(cleaned)
    if count < 3:
        return False
    for index in range(count):
        a = cleaned[index]
        b = cleaned[(index + 1) % count]
        if (abs(a[0] - b[0]) > _TOUCH_TOL_FT
                and abs(a[1] - b[1]) > _TOUCH_TOL_FT):
            return False
    return True


def _strictly_inside(hole, outer):
    """Every vertex inside the outline and clear of its boundary."""
    count = len(outer)
    for point in hole:
        if not _point_in_ring(point, outer):
            return False
        for index in range(count):
            if _point_edge_gap(point, outer[index],
                               outer[(index + 1) % count]) <= _TOUCH_TOL_FT:
                return False
    return True


def _point_edge_gap(point, a, b):
    """Distance from a point to the segment ab."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 <= 0:
        return _dist(point, a)
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2
    t = max(0.0, min(1.0, t))
    return _dist(point, (a[0] + t * dx, a[1] + t * dy))


def _merged_holes(holes):
    """The pooled hollows as ONE ring per connected piece of them.

    Cells covered by any hole ring are the hollow; each connected run walks
    out as one ring. Shared edges and coincident duplicates dissolve. A ring
    of holes enclosing an un-hollowed middle keeps that middle as support --
    only the counter-clockwise outers come back. Falls back to the holes as
    given if the walk cannot close.
    """
    if len(holes) < 2:
        return list(holes)
    coords = [point for hole in holes for point in hole]
    snap_x = _snapped([p[0] for p in coords])
    snap_y = _snapped([p[1] for p in coords])
    xs = sorted(set(snap_x.values()))
    ys = sorted(set(snap_y.values()))
    covered = {}
    for column in range(len(xs) - 1):
        for row in range(len(ys) - 1):
            centre = ((xs[column] + xs[column + 1]) / 2.0,
                      (ys[row] + ys[row + 1]) / 2.0)
            if any(_point_in_ring(centre, hole) for hole in holes):
                covered[(column, row)] = True
    rings = _grid_rings(xs, ys, covered)
    if rings is None:
        return list(holes)
    merged = [ring for ring in rings if _signed_area(ring) > 0]
    return merged if merged else list(holes)


def _snapped(values):
    """{value: cluster representative} -- coordinates within a mm collapse."""
    mapping = {}
    anchor = None
    for value in sorted(set(values)):
        if anchor is None or value - anchor > _TOUCH_TOL_FT:
            anchor = value
        mapping[value] = anchor
    return mapping


def _collinear_simplified(ring):
    """The ring without the vertices the grid compression introduced."""
    out = []
    count = len(ring)
    for index in range(count):
        previous = ring[(index - 1) % count]
        point = ring[index]
        following = ring[(index + 1) % count]
        cross = ((point[0] - previous[0]) * (following[1] - point[1])
                 - (point[1] - previous[1]) * (following[0] - point[0]))
        if abs(cross) > 1e-12:
            out.append(point)
    return out if len(out) >= 3 else ring


def _host_for(ring, rings):
    """(index, plan) of the outline a step region belongs to, else (None, None).

    The SMALLEST outline containing the region's centre wins, so a pad drawn
    inside a raft takes its own step rather than the raft's.
    """
    centre = _centroid(ring)
    best = (None, None, None)
    for index, plan in rings:
        if not _point_in_ring(centre, plan["ring"]):
            continue
        size = abs(_signed_area(plan["ring"]))
        if best[2] is None or size < best[2]:
            best = (index, plan, size)
    return best[0], best[1]


def _note_for(ring, host, kind):
    """The step note paired to this region: the one INSIDE it, else the host's.

    A host can hold several steps -- test10's F3 rings carry three fold notes
    each, one per fold region, and each note sits inside the region it belongs
    to. Containment therefore pairs them exactly, and proximity never has to be
    guessed at. The single-note fallback is for a region whose note was placed
    just outside it. The whole NOTE comes back, not just the depth: its THK
    field is the dropped slab's own thickness, which the sunk bay needs (a 500
    slab dropping out of a 750 raft).
    """
    same_kind = [step for step in (host.get("steps") or [])
                 if step.get("step_kind") == kind and step.get("step_mm")]
    if not same_kind:
        return None
    for step in same_kind:
        point = step.get("point")
        if point and _point_in_ring((point[0], point[1]), ring):
            return step
    if len(same_kind) == 1:
        return same_kind[0]
    return None


def _parts(ring, kind, depth_mm, note, host, host_index, rings):
    """One step's parent opening, support slab(s) and dropped slab.

    The parent is read PER EDGE, from whatever outline abuts it, because the two
    cases disagree about who the parent is. A region cut out of its host steps
    down from that host. A region that IS its host -- an outline the drawing
    marks sunk in its entirety -- steps down from the NEIGHBOURS it abuts, and
    they are a different thickness: reading the host there says the region
    steps down from itself, and invents a support that the drawing's own
    arithmetic says is not there.

    A support is ONE slab per contiguous run of stepped edges, not a strip per
    edge. A fold in the middle of a footing gets a closed band round the whole
    region -- the region itself the hollow in it; a fold in a corner gets one
    L-shaped slab round its two inner edges. Separate strips would meet at the
    corners edge-to-edge, which Revit joins as two butting floors rather than
    the one cast collar the detail shows.
    """
    # The dropped slab's thickness: its own note's THK first (the sunk bay is
    # a 500 slab dropping out of a 750 raft, and only the note says 500), the
    # host it is cut from otherwise.
    dropped_thickness = ((note or {}).get("thickness_mm")
                         or host.get("thickness_mm"))
    coincident = _is_host_itself(ring, host["ring"])
    edges = _outward_edges(ring)
    sides = []                          # per edge: (width_mm, depth_mm) or None
    for edge in edges:
        parent = _neighbour_beyond(edge, rings,
                                   skip=host_index if coincident else None)
        thickness = parent.get("thickness_mm") if parent else None
        if not thickness:
            sides.append(None)         # open ground: nothing to step down from
            continue
        if depth_mm <= thickness:
            # No void. The drop is shallower than the parent is thick, so the
            # dropped slab's own side face rises past the parent's soffit and
            # the section is already solid concrete. A support here is a
            # phantom slab inside it -- the corridor drawing's pair of 250 mm
            # footings at -500 were exactly this.
            sides.append(None)
            continue
        sides.append((thickness,
                      depth_mm + (dropped_thickness or 0.0) - thickness))
    return {"kind": kind, "ring": ring, "depth_mm": depth_mm,
            "mark": host.get("mark"), "host_index": host_index,
            "dropped": {"ring": ring, "thickness_mm": dropped_thickness,
                        "offset_mm": -depth_mm},
            "supports": _support_slabs(edges, sides),
            "opening": None if coincident else ring}


def _support_slabs(edges, sides):
    """[{ring, holes, thickness_mm, offset_mm}] -- one slab per stepped run.

    Every edge is stepped the same way -> ONE closed band: the outer ring is
    the region offset outward by the parent's thickness, and the region itself
    the hollow -- a collar with the drop cut out of it. Otherwise each
    contiguous run of stepped edges (same parent thickness, same remaining
    depth) becomes one polygon: outward offsets along the run, mitred at the
    corners it turns, closed back along the region's own edge -- a single edge
    gives the plain strip, a corner's two edges the L.

    `holes` is a LIST because collars pool: `_pool_collars` merges the collars
    of neighbouring regions into one slab carrying every region as a hollow.
    """
    stepped = [side for side in sides if side]
    if stepped and len(stepped) == len(sides) and len(set(stepped)) == 1:
        width, depth = stepped[0]
        outer = [_miter(edges[index - 1], edges[index], width, width)
                 for index in range(len(edges))]
        return [{"ring": outer, "holes": [[edge[0] for edge in edges]],
                 "thickness_mm": depth, "offset_mm": -width}]
    slabs = []
    for run in _runs(sides):
        width, depth = sides[run[0]]
        outer = [_offset_point(edges[run[0]], 0, width)]
        for position in range(1, len(run)):
            outer.append(_miter(edges[run[position] - 1], edges[run[position]],
                                width, width))
        outer.append(_offset_point(edges[run[-1]], 1, width))
        inner = [edges[index][0] for index in reversed(run)]
        slabs.append({"ring": outer + [edges[run[-1]][1]] + inner,
                      "holes": [],
                      "thickness_mm": depth, "offset_mm": -width})
    return slabs


def _runs(sides):
    """Maximal circular runs of consecutive edges stepped the same way."""
    count = len(sides)
    in_run = [index for index in range(count) if sides[index]]
    if not in_run:
        return []
    runs = []
    current = [in_run[0]]
    for index in in_run[1:]:
        if index == current[-1] + 1 and sides[index] == sides[current[0]]:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)
    # The ring is circular: a run ending at the last edge continues into one
    # starting at the first, so a corner fold's two edges join into one L even
    # when the ring happens to start between them.
    if (len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == count - 1
            and sides[0] == sides[count - 1]):
        runs[0] = runs.pop() + runs[0]
    return runs


def _offset_point(edge, end, width_mm):
    """An edge endpoint pushed straight out by the support's width."""
    point = edge[end]
    normal = edge[2]
    reach = config.mm_to_ft(width_mm)
    return (point[0] + normal[0] * reach, point[1] + normal[1] * reach)


def _miter(edge_a, edge_b, width_a, width_b):
    """Where the two edges' outward offsets MEET at their shared corner.

    The intersection of the two offset lines -- for the right angles the corpus
    draws, the corner pushed out by both normals at once. Parallel edges (a
    straight side arriving as two pieces) have no intersection; either offset
    is already the point.
    """
    shared = edge_b[0]
    na, nb = edge_a[2], edge_b[2]
    wa, wb = config.mm_to_ft(width_a), config.mm_to_ft(width_b)
    cross = na[0] * nb[1] - na[1] * nb[0]
    if abs(cross) < 1e-9:
        return (shared[0] + na[0] * wa, shared[1] + na[1] * wa)
    # Solve (p - shared) . na = wa and (p - shared) . nb = wb.
    dx = (wa * nb[1] - wb * na[1]) / cross
    dy = (wb * na[0] - wa * nb[0]) / cross
    return (shared[0] + dx, shared[1] + dy)


def _is_host_itself(ring, host_ring):
    """True when the region and its host are the same outline, drawn twice.

    test10's sunk hatch is drawn to the same coordinates as its F6 foundation.
    That is not a hole in F6 -- it is the statement that F6 is the sunk one.
    """
    host_area = abs(_signed_area(host_ring))
    if host_area <= 0:
        return False
    return abs(abs(_signed_area(ring)) - host_area) / host_area <= _SAME_AREA


def _outward_edges(ring):
    """[(a, b, normal)] for each edge, `normal` pointing OUT of the ring."""
    ordered = list(ring)
    if _signed_area(ordered) < 0:
        ordered.reverse()               # counter-clockwise: interior on the left
    edges = []
    count = len(ordered)
    for index in range(count):
        a = ordered[index]
        b = ordered[(index + 1) % count]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length <= 0:
            continue
        edges.append((a, b, (dy / length, -dx / length)))
    return edges


def _neighbour_beyond(edge, rings, skip=None):
    """The outline just beyond this edge -- the step's parent there -- else None.

    `skip` drops the host from the search: when the region IS its host, the
    host's own concrete is the thing that dropped, so finding it beyond the edge
    would say the strip steps down from itself. The SMALLEST match wins, for the
    same reason the host does: a pad drawn inside a raft is the nearer parent.
    """
    a, b, normal = edge
    reach = config.mm_to_ft(_PROBE_MM)
    probe = ((a[0] + b[0]) / 2.0 + normal[0] * reach,
             (a[1] + b[1]) / 2.0 + normal[1] * reach)
    best, smallest = None, None
    for index, plan in rings:
        if index == skip:
            continue
        if not _point_in_ring(probe, plan["ring"]):
            continue
        size = abs(_signed_area(plan["ring"]))
        if smallest is None or size < smallest:
            best, smallest = plan, size
    return best


def area_m2(ring):
    """A ring's plan area in square metres, for reporting and thresholds."""
    return abs(_signed_area(ring)) * (_MM / 1000.0) ** 2
