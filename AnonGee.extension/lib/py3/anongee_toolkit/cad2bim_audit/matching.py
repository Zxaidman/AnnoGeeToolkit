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

from . import config, geometry

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

    __slots__ = ("category", "by_stage", "anchor", "level")

    def __init__(self, category, anchor, level=None):
        self.category = category
        self.anchor = anchor           # (x, y) in the matching space
        self.by_stage = {}             # {stage: [AuditItem]}
        self.level = level

    def add(self, item, point):
        bucket = self.by_stage.setdefault(item.stage, [])
        bucket.append(item)
        # The anchor is the running mean of every member, so a group does not
        # drift toward whichever stage happened to be folded in last.
        count = sum(len(items) for items in self.by_stage.values())
        self.anchor = (((self.anchor[0] * (count - 1)) + point[0]) / count,
                       ((self.anchor[1] * (count - 1)) + point[1]) / count)
        if self.level is None and item.level:
            self.level = item.level

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


class _Grid(object):
    """Uniform spatial hash at the match radius. Only 9 cells can hold a match."""

    def __init__(self, cell):
        self.cell = float(cell) if cell else 1.0
        self.buckets = {}

    def _key(self, point):
        return (int(point[0] // self.cell), int(point[1] // self.cell))

    def add(self, point, payload):
        self.buckets.setdefault(self._key(point), []).append(payload)

    def near(self, point):
        cx, cy = self._key(point)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found.extend(self.buckets.get((cx + dx, cy + dy), ()))
        return found

    def move(self, old_point, new_point, payload):
        """Re-file a group whose anchor drifted into a different cell."""
        old_key, new_key = self._key(old_point), self._key(new_point)
        if old_key == new_key:
            return
        bucket = self.buckets.get(old_key)
        if bucket and payload in bucket:
            bucket.remove(payload)
        self.buckets.setdefault(new_key, []).append(payload)


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
                grid = grids[category] = _Grid(radius)
            group = _best_group(grid, point, item, radius)
            if group is None:
                group = MatchGroup(category, point, item.level)
                groups.append(group)
                grid.add(point, group)
                group.add(item, point)
            else:
                before = group.anchor
                group.add(item, point)
                grid.move(before, group.anchor, group)

    diagnostics = {
        "space": space_key,
        "match_radius_mm": radius,
        "groups": len(groups),
        "items_without_position": len(unplaced),
        "categories": sorted(grids.keys()),
    }
    return groups, diagnostics


def _best_group(grid, point, item, radius):
    """Nearest group within the radius that does not already hold this stage.

    Excluding groups that already have an item from this stage is what stops two
    genuinely distinct members 60 mm apart from collapsing into one: the second
    cannot join the group the first already occupies, so it starts its own.
    Ties within the radius are broken by SIZE, which is the layer's third step.
    """
    best = None
    best_score = None
    size = item.plan_size_mm
    for group in grid.near(point):
        distance = geometry.plan_distance((point[0], point[1], 0.0),
                                          (group.anchor[0], group.anchor[1], 0.0))
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
