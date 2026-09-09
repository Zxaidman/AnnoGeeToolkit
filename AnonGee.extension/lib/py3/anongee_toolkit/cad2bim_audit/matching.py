# -*- coding: utf-8 -*-
"""Pair the same physical member across the four stages.

Layered, in the order a person would do it: bucket by CATEGORY, then match by
CENTROID within a radius, then break ties by SIZE. Category first because it is
the only key that is meaningful in every stage; centroid because it is the only
measurement every stage can produce for every item; size last because it settles
the ambiguous cases without ever being the reason two things pair up.

Chaining rather than pairwise
-----------------------------
Stages are folded in a fixed order (drawing -> link -> intent -> model) and each
item either joins an existing group or starts a new one. A group is therefore
one candidate member seen up to six ways, and a stage missing from a group is a
gap with a direction: "in A, not in C" is a different sentence from "in C, not
in A", and the report needs both.

Why not pairwise diffs: five pairwise comparisons of six stages give ten tables
that disagree with each other at the edges, and no single row you can read
across. One group per member is the thing you actually want to look at.

Cost
----
The obvious nested loop is O(n*m) per category, which on the 10,195-item export
this was built against is tens of millions of distance tests per stage fold. A
uniform grid keyed at the match radius makes it near-linear: only the nine cells
around a point can hold a match, because anything further away is outside the
radius by construction.

Revit-free.
"""

from . import config, geometry, spatial

#: The order stages are folded in. Drawing first, so a group is seeded by what
#: the drawing HAS and later stages attach to it -- which makes an unattached
#: model element (an orphan) fall out naturally as a group with no earlier stage.
FOLD_ORDER = (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
              config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED,
              config.STAGE_INTENT, config.STAGE_MODEL)

#: Bucket for items whose layer never resolved to a category.
UNCLASSIFIED = "(unclassified)"

#: Kinds that are matched as members. Text is reconciled separately (it exists in
#: the DXF and cannot exist in the link, so matching it spatially against
#: geometry would manufacture findings), and annotation/construction geometry is
#: never a member.
MEMBER_KINDS = frozenset(("curve", "hatch", "solid", "mesh", "element",
                          "filled", "point", "block"))


class MatchGroup(object):
    """One candidate member, as seen by each stage that saw it."""

    __slots__ = ("category", "by_stage", "anchor", "level", "points", "angle")

    def __init__(self, category, anchor, level=None):
        self.category = category
        self.anchor = anchor           # (x, y) in the matching space
        self.by_stage = {}             # {stage: [AuditItem]}
        self.level = level
        # The run this group occupies, taken from the FIRST item to join it.
        # Stages fold drawing-first, so that is the drawing's geometry -- which
        # is the right reference: a clipped beam should be measured against what
        # was drawn, not against the clipped result.
        self.points = None
        self.angle = None

    @property
    def is_linear(self):
        return self.category in config.LINEAR_CATEGORIES

    def add(self, item, point):
        bucket = self.by_stage.setdefault(item.stage, [])
        bucket.append(item)
        if self.points is None and item.points:
            self.points = item.points
            self.angle = geometry.principal_angle_deg(item.points)
        # The anchor is the running mean of every member, so a group does not
        # drift toward whichever stage happened to be folded in last.
        count = sum(len(items) for items in self.by_stage.values())
        self.anchor = (((self.anchor[0] * (count - 1)) + point[0]) / count,
                       ((self.anchor[1] * (count - 1)) + point[1]) / count)
        if self.level is None and item.level:
            self.level = item.level

    def total_length_mm(self, stage):
        """Every piece of this run in one stage, summed.

        cad2bim splits a beam at each column it crosses, so one drawn beam
        becomes several placed segments. Comparing the drawn run against the
        first segment would report a correctly-built beam as badly clipped; the
        run is the sum.
        """
        items = self.by_stage.get(stage)
        if not items:
            return None
        total = 0.0
        for item in items:
            length = item.length_mm
            if length:
                total += length
        return total or None

    def has(self, stage):
        return bool(self.by_stage.get(stage))

    def first(self, stage):
        items = self.by_stage.get(stage)
        return items[0] if items else None

    def count(self, stage):
        return len(self.by_stage.get(stage, ()))

    def any_item(self):
        for stage in FOLD_ORDER:
            item = self.first(stage)
            if item is not None:
                return item
        return None

    def stages(self):
        return [stage for stage in FOLD_ORDER if self.has(stage)]

    def size_mm(self, stage):
        """The stage's best plan size: the type/declared size, else the extent.

        A declared size (a type parameter, or cad2bim's own b/h) is preferred
        because a bounding box over-reports a rotated member, and reporting a
        rotated 400x400 column as 566x566 would flag every one of them.
        """
        item = self.first(stage)
        if item is None:
            return None
        b = item.extra.get("type_b_mm") or item.extra.get("b_mm")
        h = item.extra.get("type_h_mm") or item.extra.get("h_mm")
        if b and h:
            return (min(b, h), max(b, h))
        return item.plan_size_mm

    def __repr__(self):
        return "<MatchGroup {0} stages={1}>".format(
            self.category, ",".join(self.stages()))


def match_point(item, space_key):
    """The (x, y) an item is matched on, or None when it has no geometry."""
    centroid = (item.centroid_revit if space_key == "revit" else item.centroid_dxf)
    return None if centroid is None else (centroid[0], centroid[1])


def choose_space(captures):
    """Match in the space the most items actually have coordinates in.

    A run with no Revit link has no Revit coordinates at all; a run whose link
    transform could not be inverted has no DXF coordinates for the Revit-read
    stages. Picking the better-populated space keeps the reconciliation working
    in both cases instead of silently matching nothing.
    """
    revit = dxf = 0
    for capture in captures.values():
        for item in capture.items:
            if item.centroid_revit is not None:
                revit += 1
            if item.centroid_dxf is not None:
                dxf += 1
    return "revit" if revit >= dxf else "dxf"


def is_member(item):
    """Whether an item takes part in the member reconciliation."""
    if item.kind not in MEMBER_KINDS:
        return False
    # Builder-input geometry is stage B curves carried inside a stage D file;
    # matching them would count the same geometry twice.
    return item.extra.get("role") != "builder_input"


def build_groups(captures, settings=None, space_key=None):
    """Fold every capture into MatchGroups. Returns (groups, diagnostics)."""
    values = config.settings(settings)
    radius = values["match_radius_mm"]
    space_key = space_key or choose_space(captures)

    groups = []
    # One grid per category: a beam can never match a column, so they must not
    # even be candidates for each other.
    grids = {}
    unplaced = []

    for stage in FOLD_ORDER:
        capture = captures.get(stage)
        if capture is None:
            continue
        for item in capture.items:
            if not is_member(item):
                continue
            point = match_point(item, space_key)
            if point is None:
                unplaced.append(item)
                continue
            category = item.category or UNCLASSIFIED
            grid = grids.get(category)
            if grid is None:
                grid = grids[category] = spatial.Grid(radius)
            group = _best_group(grid, point, item, radius, values)
            if group is None:
                group = MatchGroup(category, point, item.level)
                groups.append(group)
                group.add(item, point)
                if group.is_linear and group.points:
                    # Filed along its whole run, so a probe anywhere on the beam
                    # finds it -- not only a probe near its midpoint.
                    grid.add_span(group.points, group)
                else:
                    grid.add(point, group)
            else:
                before = group.anchor
                group.add(item, point)
                # A linear group is filed by its span, which is fixed by the
                # first item; re-filing it by a drifting anchor would unfile the
                # run. Point-like groups follow their anchor as before.
                if not group.is_linear:
                    grid.move(before, group.anchor, group)

    diagnostics = {
        "space": space_key,
        "match_radius_mm": radius,
        "groups": len(groups),
        "items_without_position": len(unplaced),
        "categories": sorted(grids.keys()),
    }
    return groups, diagnostics


def _best_group(grid, point, item, radius, values):
    """The best group this item can join, or None to start a new one.

    Two different rules, because two different kinds of thing:

    **Point-like members** (a column, a footing) match on centroid distance, and
    a group may hold at most ONE item per stage. That cap is what stops two
    genuinely distinct columns 60 mm apart from collapsing into one: the second
    cannot join the group the first occupies, so it starts its own.

    **Linear members** (a beam, a grid line, a wall) match on distance to the
    group's RUN, and a group may hold SEVERAL items per stage. Both differences
    are forced by how beams actually behave:

      * clipping moves a centroid. A 1 m clip on a 6 m beam shifts it 500 mm --
        five times the radius -- so centroid matching reports one clipped beam
        as two members, one missing and one orphan. Measured to the run, the
        clipped beam sits on the drawn beam at distance zero.
      * cad2bim splits a beam at every column it crosses, so one drawn beam is
        several placed segments. A one-per-stage cap would admit one segment and
        report the rest as orphans.

    Collinearity is what keeps that safe: without it the span test would pair a
    beam with the beam it meets at a corner, since their runs touch.
    """
    best = None
    best_score = None
    size = item.plan_size_mm
    linear = item.category in config.LINEAR_CATEGORIES
    angle = geometry.principal_angle_deg(item.points) if linear else None
    collinear_tol = values["collinear_tol_deg"]
    lateral = values["linear_lateral_tol_mm"]
    probe = (point[0], point[1], 0.0)
    seen = set()

    for group in grid.near(point):
        if id(group) in seen:
            continue                    # a span-filed group appears in many cells
        seen.add(id(group))

        if linear and group.is_linear:
            # Distance to the RUN, not to its midpoint -- and judged against the
            # lateral tolerance, not the generic radius. The distance from a
            # beam's centroid to a parallel run IS the gap between them, so the
            # generic radius would fuse the two faces of a narrow beam and keep
            # those of a wide one apart.
            distance = (geometry.path_distance(probe, group.points)
                        if group.points else None)
            if distance is None:
                distance = geometry.plan_distance(
                    probe, (group.anchor[0], group.anchor[1], 0.0))
            if distance is None or distance > lateral:
                continue
            drift = geometry.angle_delta_deg(angle, group.angle)
            if drift is not None and drift > collinear_tol:
                continue
        else:
            distance = geometry.plan_distance(
                probe, (group.anchor[0], group.anchor[1], 0.0))
            if distance is None or distance > radius:
                continue
            if group.has(item.stage):
                continue

        score = (distance, _size_penalty(size, group))
        if best_score is None or score < best_score:
            best = group
            best_score = score
    return best


def _size_penalty(size, group):
    """How badly an item's plan size disagrees with the group's, in mm. 0 if unknown."""
    if size is None:
        return 0.0
    for stage in FOLD_ORDER:
        other = group.size_mm(stage)
        if other is None:
            continue
        return abs(size[0] - other[0]) + abs(size[1] - other[1])
    return 0.0
