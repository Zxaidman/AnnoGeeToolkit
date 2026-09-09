# -*- coding: utf-8 -*-
"""Questions a verdict cannot ask.

A verdict answers "did this member survive the pipeline". These answer things
that are true regardless of how any member fared -- and that is exactly why they
need a home of their own. A column drawn twice has a problem even when both
copies build perfectly: there is nothing wrong with either member, so no verdict
can carry it, and every count in the report looks correct.

Three families:

  drawing hygiene   duplicates, rings that do not close, degenerate geometry,
                    stray Z. Faults in the DXF that the pipeline will faithfully
                    reproduce, and that are cheaper to fix in CAD than in Revit.
  labelling         a size label that sizes nothing, one that disagrees with what
                    was built, one mark used for two different sizes.
  model hygiene     elements placed twice, placed on the wrong storey, or whose
                    type name disagrees with their own dimensions.

Every check is a plain function of (groups, captures, values) returning findings,
so one can be added, removed or tested without touching the others.

Cost: the pairwise ones (duplicates, orphan marks, category conflicts) use the
same uniform-grid trick as the matcher. On the 10,195-item export a nested loop
would be tens of millions of comparisons per check; a grid keyed at the search
radius makes each near-linear, because only the nine surrounding cells can hold
a candidate.

Revit-free.
"""

from . import config, geometry, matching, spatial

#: Categories whose members are LINEAR -- their run matters and their bounding
#: box does not describe them. Length is checked for these and not for the rest.
_LINEAR = config.LINEAR_CATEGORIES

#: Categories that can carry a size label. A slab label is a thickness, not a
#: b x h, so it is deliberately not mark-checked here.
_SIZED = frozenset(("column", "beam", "foundation"))


def run_all(groups, captures, values, space_key="revit"):
    """Every check, in one list. Order does not matter -- findings are sorted."""
    findings = []
    for check in (duplicate_geometry, duplicate_elements, open_outlines,
                  degenerate_geometry, non_planar_geometry, label_checks,
                  conflicting_marks, hatch_import, level_mismatches,
                  length_mismatches, category_conflicts, type_name_mismatches):
        try:
            findings.extend(check(groups, captures, values, space_key))
        except Exception as error:
            # A broken check must cost its own findings and nothing else. The
            # report is a diagnostic: losing one column of it beats losing all.
            findings.append(_finding(
                "check_failed", "{0} could not run: {1}".format(
                    check.__name__, error)))
    return findings


# --- drawing hygiene --------------------------------------------------------

def duplicate_geometry(groups, captures, values, space_key="revit"):
    """The same thing drawn twice on the same layer, in one drawing stage.

    Reported per stage rather than per pair: a plan where a whole bay was copied
    over itself has one mistake, and a finding per duplicated line would be
    thousands of rows saying it.
    """
    findings = []
    tolerance = values["duplicate_tol_mm"]
    for stage in (config.STAGE_DXF_RAW, config.STAGE_LINK_RAW):
        capture = captures.get(stage)
        if capture is None:
            continue
        for group in _coincident(capture.items, tolerance, space_key):
            first = group[0]
            findings.append(_finding(
                config.CHECK_DUPLICATE_GEOMETRY,
                "{0} identical {1} entities on layer {2} at the same point. "
                "Drawn on top of each other -- every pass downstream will treat "
                "them as separate members.".format(
                    len(group), first.source_type or first.kind, first.layer_key),
                item=first, stage=stage,
                detail={"count": len(group), "layer": first.layer_key,
                        "type": first.source_type}))
    return findings


def duplicate_elements(groups, captures, values, space_key="revit"):
    """Two placed elements of one category in the same place. Doubled quantities."""
    capture = captures.get(config.STAGE_MODEL)
    if capture is None:
        return []
    findings = []
    for group in _coincident(capture.items, values["duplicate_tol_mm"], space_key,
                             key=lambda item: item.category):
        first = group[0]
        findings.append(_finding(
            config.CHECK_DUPLICATE_ELEMENT,
            "{0} {1} elements occupy the same position (ids {2}). Quantities, "
            "schedules and any joins are doubled.".format(
                len(group), first.category or "model",
                ", ".join(str(item.handle) for item in group[:6])),
            item=first, stage=config.STAGE_MODEL,
            detail={"count": len(group),
                    "ids": [item.handle for item in group]}))
    return findings


def open_outlines(groups, captures, values, space_key="revit"):
    """Rings on a member layer that do not close, so nothing can be made of them.

    This is cad2bim's own `open_path` status, measured independently: a column
    outline left open at a junction cut never becomes a column, and the run
    reports it only as an absence.
    """
    findings = []
    tolerance = values["close_tol_mm"]
    capture = captures.get(config.STAGE_DXF_RAW)
    if capture is None:
        return findings
    for item in capture.items:
        if item.kind != "curve" or item.category not in _SIZED:
            continue
        points = item.points
        if len(points) < 4 or item.extra.get("closed"):
            continue
        gap = geometry.distance(points[0], points[-1])
        if gap is None or gap <= tolerance:
            continue
        # An outline is only "open" if it was trying to be a ring. A gap wider
        # than the shape itself is a polyline, not a broken outline.
        size = item.plan_size_mm
        if size is None or gap > max(size) * 0.9:
            continue
        findings.append(_finding(
            config.CHECK_OPEN_OUTLINE,
            "Outline on layer {0} is open by {1:.0f} mm ({2:.0f}x{3:.0f} mm "
            "shape). cad2bim cannot close it into a member; it will report the "
            "member as absent rather than as broken.".format(
                item.layer_key, gap, size[0], size[1]),
            item=item, stage=config.STAGE_DXF_RAW,
            detail={"gap_mm": round(gap, 1), "size_mm": [round(v, 1) for v in size]}))
    return findings


def degenerate_geometry(groups, captures, values, space_key="revit"):
    """Zero-length curves and zero-area rings: entities that occupy no space."""
    findings = []
    limit = values["degenerate_mm"]
    for stage in (config.STAGE_DXF_RAW, config.STAGE_LINK_RAW):
        capture = captures.get(stage)
        if capture is None:
            continue
        counts = {}
        example = {}
        for item in capture.items:
            if item.kind not in ("curve", "hatch"):
                continue
            if len(item.points) < 2:
                continue
            if item.kind == "hatch":
                bad = item.area_mm2 < limit * limit
            else:
                bad = item.length_mm < limit
            if bad:
                counts[item.layer_key] = counts.get(item.layer_key, 0) + 1
                example.setdefault(item.layer_key, item)
        for layer, count in sorted(counts.items(), key=lambda row: -row[1]):
            findings.append(_finding(
                config.CHECK_DEGENERATE,
                "{0} entity/entities on layer {1} occupy no space (under {2:.0f} "
                "mm). They cost every pass time and can seed spurious "
                "junctions.".format(count, layer, limit),
                item=example[layer], stage=stage,
                detail={"count": count, "layer": layer}))
    return findings


def non_planar_geometry(groups, captures, values, space_key="revit"):
    """Stray Z in a plan drawing, aggregated per layer.

    A plan is flat. Geometry that is not breaks planar operations downstream and
    survives into the Revit link, where it is much harder to see.
    """
    capture = captures.get(config.STAGE_DXF_RAW)
    if capture is None:
        return []
    counts = {}
    example = {}
    worst = {}
    for item in capture.items:
        points = item.points_dxf or []
        if len(points) < 2:
            continue
        zs = [p[2] for p in points]
        spread = max(zs) - min(zs)
        if spread <= values["planarity_tol_mm"]:
            continue
        layer = item.layer_key
        counts[layer] = counts.get(layer, 0) + 1
        example.setdefault(layer, item)
        worst[layer] = max(worst.get(layer, 0.0), spread)
    findings = []
    for layer, count in sorted(counts.items(), key=lambda row: -row[1]):
        findings.append(_finding(
            config.CHECK_NON_PLANAR,
            "{0} entity/entities on layer {1} are not flat (up to {2:.0f} mm of "
            "Z). A plan drawing should be flat; the Z survives into the Revit "
            "link.".format(count, layer, worst[layer]),
            item=example[layer], stage=config.STAGE_DXF_RAW,
            detail={"count": count, "layer": layer,
                    "max_z_spread_mm": round(worst[layer], 1)}))
    return findings


# --- labelling --------------------------------------------------------------

def label_checks(groups, captures, values, space_key="revit"):
    """Everything a size label can tell you, in one pass over one index.

    Orphans and wrong sizes are two halves of the same question -- "which member
    does this label size?" -- separated only by how many answers there are:

        none      the label sizes nothing            -> orphan
        exactly   compare its size against the model -> mark_not_applied
        several   the pairing is a guess             -> counted, not claimed

    They were two functions and each built its own spatial index over the same
    groups from the same texts, which on a 13-storey export cost 2.4 seconds to
    ask one question twice. One pass, one index.

    The "several" case is deliberately not a size claim. "The nearest member" is
    a guess when three are in range, and a guess dressed as a size error sends
    somebody to check a member that was built correctly. The count is reported
    so the silence is accounted for rather than merely quiet.
    """
    texts = _sized_texts(captures)
    if not texts:
        return []
    radius = values["mark_radius_mm"]
    tolerance = values["size_tol_mm"]
    index = _MemberIndex(groups, radius, _SIZED)

    orphans = {}
    ambiguous = 0
    findings = []

    for item in texts:
        point = matching.match_point(item, space_key)
        if point is None:
            continue
        near = index.candidates(point, radius, space_key)
        if not near:
            key = (item.mark or item.text or "?").strip()[:40]
            bucket = orphans.setdefault(key, {"count": 0, "item": item, "where": []})
            bucket["count"] += 1
            bucket["where"].append([round(point[0], 1), round(point[1], 1)])
            continue

        label = _ordered(item.extra.get("b_mm"), item.extra.get("h_mm"))
        if label is None:
            continue                      # a mark with no size cannot be checked
        sized = [row for row in near if _built_size(row[1]) is not None]
        if not sized:
            continue
        if len(sized) > 1:
            ambiguous += 1
            continue

        group = sized[0][1]
        built = _built_size(group)
        delta = max(abs(built[0] - label[0]), abs(built[1] - label[1]))
        if delta <= tolerance:
            continue
        findings.append(_finding(
            config.CHECK_MARK_NOT_APPLIED,
            "Label {0} says {1:.0f}x{2:.0f} mm; the {3} built there is "
            "{4:.0f}x{5:.0f} mm ({6:.0f} mm out). The label did not reach the "
            "model.".format(_label_of(item), label[0], label[1],
                            group.category or "member", built[0], built[1], delta),
            item=item, stage=item.stage, category=group.category,
            detail={"label_mm": list(label), "built_mm": list(built),
                    "delta_mm": round(delta, 1)}))

    # Aggregated by mark: on a real export this fired 2,351 times, and a sheet
    # with 2,351 rows of one sentence hides every other finding in the report.
    # The positions ride in `detail`; the DXF text sheet still lists each label.
    for mark, bucket in sorted(orphans.items(), key=lambda row: -row[1]["count"]):
        findings.append(_finding(
            config.CHECK_ORPHAN_MARK,
            "{0} label(s) reading {1!r} have no member within {2:.0f} mm to "
            "size. Either those members were never read, or the labels sit too "
            "far from them.".format(bucket["count"], mark, radius),
            item=bucket["item"], stage=bucket["item"].stage,
            detail={"mark": mark, "count": bucket["count"],
                    "positions": bucket["where"][:50]}))

    if ambiguous:
        findings.append(_finding(
            config.CHECK_ORPHAN_MARK,
            "{0} label(s) had more than one sized member within {1:.0f} mm, so "
            "which member each sizes cannot be told from position alone. Their "
            "sizes were NOT checked -- move the labels, or tighten "
            "mark_radius_mm.".format(ambiguous, radius),
            item=texts[0], stage=texts[0].stage,
            detail={"ambiguous_labels": ambiguous, "radius_mm": radius}))
    return findings


def conflicting_marks(groups, captures, values, space_key="revit"):
    """One mark string used for two different sizes. The schedule cannot be right."""
    sizes = {}
    example = {}
    for item in _sized_texts(captures):
        mark = (item.mark or "").strip()
        size = _ordered(item.extra.get("b_mm"), item.extra.get("h_mm"))
        if not mark or size is None:
            continue
        sizes.setdefault(mark, set()).add((round(size[0]), round(size[1])))
        example.setdefault(mark, item)

    findings = []
    for mark, distinct in sorted(sizes.items()):
        if len(distinct) < 2:
            continue
        listed = ", ".join("{0}x{1}".format(a, b) for a, b in sorted(distinct))
        findings.append(_finding(
            config.CHECK_CONFLICTING_MARK,
            "Mark {0!r} is used for {1} different sizes: {2}. Whatever is built "
            "under that mark, some of the drawing disagrees with it.".format(
                mark, len(distinct), listed),
            item=example[mark], stage=example[mark].stage,
            detail={"mark": mark, "sizes_mm": sorted(distinct)}))
    return findings


def hatch_import(groups, captures, values, space_key="revit"):
    """What became of the drawing's hatches once Revit imported them.

    Only answerable now that stage B reads solids and resolves their footprints
    into rings with holes. Two questions, both invisible to every other pass:

      * did the hatch arrive at all? A hatch that produced no solid in the link
        is geometry the drawing has and the import dropped -- which happens to
        every consumer of that link, not only to cad2bim.
      * did its HOLES arrive? An island in a hatch is a hole in the thing: a
        lift shaft, a duct, a stair void. A hatch that comes through solid has
        quietly filled it in, and no count anywhere changes -- the region is
        present, the right size, in the right place, and wrong.

    Matched spatially rather than through the reconciliation, because a hatch
    and the solid it became commonly classify differently (or not at all), and
    two items in different category buckets can never meet in a group.
    """
    drawing = captures.get(config.STAGE_DXF_RAW)
    link = captures.get(config.STAGE_LINK_RAW)
    if drawing is None or link is None:
        return []

    hatches = [item for item in drawing.items if item.kind == "hatch"]
    solids = [item for item in link.items if item.kind in ("solid", "mesh")]
    if not hatches:
        return []

    radius = values["match_radius_mm"]
    index = spatial.Grid(radius)
    for item in solids:
        point = matching.match_point(item, space_key)
        if point is not None:
            index.add(point, (point, item))

    findings = []
    for hatch in hatches:
        point = matching.match_point(hatch, space_key)
        if point is None:
            continue
        nearest = _closest(index, point, radius)
        islands = hatch.extra.get("island_count") or 0
        if nearest is None:
            findings.append(_finding(
                config.CHECK_HATCH_NOT_IMPORTED,
                "This hatch produced nothing in the Revit link within {0:.0f} "
                "mm. The region is in the drawing and absent from everything "
                "downstream of the import.".format(radius),
                item=hatch, stage=config.STAGE_DXF_RAW,
                detail={"pattern": hatch.extra.get("pattern"),
                        "islands": islands}))
            continue
        holes = nearest.extra.get("hole_count") or 0
        if islands > holes:
            findings.append(_finding(
                config.CHECK_HOLE_LOST,
                "The drawing shows {0} hole(s) here and the imported region has "
                "{1}. A void that comes through solid is filled in, and nothing "
                "else in the report changes: same place, same size, wrong."
                .format(islands, holes),
                item=hatch, stage=config.STAGE_DXF_RAW,
                detail={"islands": islands, "holes": holes,
                        "pattern": hatch.extra.get("pattern")}))
    return findings


def _closest(index, point, radius):
    """The nearest indexed item within `radius`, or None."""
    best = None
    best_distance = radius
    probe = (point[0], point[1], 0.0)
    for other_point, item in index.near(point):
        distance = geometry.plan_distance(
            probe, (other_point[0], other_point[1], 0.0))
        if distance is not None and distance <= best_distance:
            best = item
            best_distance = distance
    return best


# --- model hygiene ----------------------------------------------------------

def level_mismatches(groups, captures, values, space_key="revit"):
    """Built on a different storey from the one the run assigned it to."""
    if captures.get(config.STAGE_MODEL) is None or \
            captures.get(config.STAGE_INTENT) is None:
        return []
    findings = []
    for group in groups:
        built = group.first(config.STAGE_MODEL)
        intended = group.first(config.STAGE_INTENT)
        if built is None or intended is None:
            continue
        if not built.level or not intended.level:
            continue
        if _same_level(built.level, intended.level):
            continue
        findings.append(_finding(
            config.CHECK_LEVEL_MISMATCH,
            "cad2bim placed this on {0!r}; the element in the model is on "
            "{1!r}.".format(intended.level, built.level),
            item=built, stage=config.STAGE_MODEL, category=group.category,
            detail={"intended": intended.level, "built": built.level}))
    return findings


def length_mismatches(groups, captures, values, space_key="revit"):
    """A linear member whose built run differs from the drawing's.

    Separate from the size check because a beam's bounding box IS its length: a
    single size tolerance either misses a 200 mm clip on a 6 m beam or fires on
    every 20 mm one. Length uses cad2bim's own two-condition rule -- a fraction
    AND an absolute -- so short stubs and long members are both judged fairly.
    """
    findings = []
    fraction = values["length_mismatch_frac"]
    absolute = values["length_mismatch_mm"]
    for group in groups:
        if group.category not in _LINEAR:
            continue
        source = _first(group, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                                config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED))
        target = _first(group, (config.STAGE_MODEL, config.STAGE_INTENT))
        if source is None or target is None:
            continue
        drawn = group.total_length_mm(source)
        built = group.total_length_mm(target)
        if not drawn or not built:
            continue
        delta = abs(drawn - built)
        if delta <= absolute or delta / max(drawn, built) <= fraction:
            continue
        findings.append(_finding(
            config.CHECK_LENGTH_MISMATCH,
            "Runs {0:.0f} mm in the drawing and {1:.0f} mm in the model "
            "({2:.0f} mm out). Typically a junction clip or a merge.".format(
                drawn, built, delta),
            item=group.first(target), stage=target, category=group.category,
            detail={"drawn_mm": round(drawn, 1), "built_mm": round(built, 1),
                    "delta_mm": round(delta, 1)}))
    return findings


def category_conflicts(groups, captures, values, space_key="revit"):
    """A member built as one thing where the drawing shows another.

    Invisible to the reconciliation by construction: the matcher buckets by
    category, so a column drawn and a beam built at the same point land in
    different buckets and each reads as a clean absence. Two innocent-looking
    findings that are really one serious one, and only a cross-bucket pass can
    say so.
    """
    radius = values["match_radius_mm"]
    drawn = spatial.Grid(radius)
    for group in groups:
        if group.category == matching.UNCLASSIFIED:
            continue
        if _has_drawing(group) and not _has_model(group):
            drawn.add(group.anchor, group)

    findings = []
    for group in groups:
        if group.category == matching.UNCLASSIFIED or _has_drawing(group):
            continue
        if not _has_model(group):
            continue
        for other in drawn.near(group.anchor):
            if other.category == group.category:
                continue
            distance = geometry.plan_distance(
                (group.anchor[0], group.anchor[1], 0.0),
                (other.anchor[0], other.anchor[1], 0.0))
            if distance is None or distance > radius:
                continue
            findings.append(_finding(
                config.CHECK_CATEGORY_CONFLICT,
                "The drawing has a {0} here and the model has a {1}, {2:.0f} mm "
                "apart. The reconciliation reports these as two separate "
                "absences; they are one member built as the wrong thing.".format(
                    other.category, group.category, distance),
                item=group.first(config.STAGE_MODEL), stage=config.STAGE_MODEL,
                category=group.category,
                detail={"drawn_as": other.category, "built_as": group.category,
                        "distance_mm": round(distance, 1)}))
            break
    return findings


def type_name_mismatches(groups, captures, values, space_key="revit"):
    """A type called 400x400 whose own dimensions are not 400x400.

    cad2bim names a type after the size it makes, so a type name that disagrees
    with its parameters means an element was placed on a type that already
    existed under that name with different dimensions -- and the schedule will
    read the name, not the geometry.
    """
    capture = captures.get(config.STAGE_MODEL)
    if capture is None:
        return []
    import re
    pattern = re.compile(r"(\d{2,5})\s*[xX×]\s*(\d{2,5})")
    tolerance = values["size_tol_mm"]

    findings = []
    seen = set()
    for item in capture.items:
        name = item.type_name or ""
        match = pattern.search(name)
        if not match:
            continue
        b = item.extra.get("type_b_mm")
        h = item.extra.get("type_h_mm")
        if not b or not h:
            continue
        named = _ordered(float(match.group(1)), float(match.group(2)))
        actual = _ordered(b, h)
        delta = max(abs(named[0] - actual[0]), abs(named[1] - actual[1]))
        if delta <= tolerance or name in seen:
            continue
        seen.add(name)
        findings.append(_finding(
            config.CHECK_TYPE_NAME_MISMATCH,
            "Type {0!r} measures {1:.0f}x{2:.0f} mm ({3:.0f} mm out). Anything "
            "reading the name -- a schedule, a tag -- will report the wrong "
            "size.".format(name[:40], actual[0], actual[1], delta),
            item=item, stage=config.STAGE_MODEL, category=item.category,
            detail={"type_name": name, "named_mm": list(named),
                    "actual_mm": list(actual), "delta_mm": round(delta, 1)}))
    return findings


# --- shared helpers ---------------------------------------------------------

class _MemberIndex(object):
    """Groups indexed by the SPAN they occupy, not by a single anchor point.

    A beam label sits along its beam, frequently nearer an end than the middle,
    so both halves of the lookup have to respect the member's extent: a long
    member is filed into every cell its run passes through, and the distance is
    measured to its geometry rather than to its centroid. Indexing by anchor
    alone reported correctly-placed labels on 6 m beams as orphans, because the
    centroid was 2.8 m from a label 300 mm off the end.
    """

    def __init__(self, groups, radius, categories, require_size=False):
        self.grid = spatial.Grid(radius)
        self.points = {}
        for group in groups:
            if group.category not in categories:
                continue
            if require_size and _built_size(group) is None:
                continue
            points = _group_points(group)
            self.points[id(group)] = points
            if points:
                self.grid.add_span(points, group)
            else:
                self.grid.add(group.anchor, group)

    def candidates(self, point, radius, space_key):
        """[(distance, group)] within `radius`, nearest first, deduplicated."""
        probe = (point[0], point[1], 0.0)
        found = {}
        for group in self.grid.near(point):
            points = self.points.get(id(group))
            if points:
                distance = geometry.path_distance(probe, points)
            else:
                distance = geometry.plan_distance(
                    probe, (group.anchor[0], group.anchor[1], 0.0))
            if distance is None or distance > radius:
                continue
            existing = found.get(id(group))
            if existing is None or distance < existing[0]:
                found[id(group)] = (distance, group)
        return sorted(found.values(), key=lambda row: row[0])


def _group_points(group):
    """The geometry a label should be measured against: the drawing's, if read.

    The drawing is preferred because that is where the label lives -- a label is
    positioned against the linework its author could see, not against whatever
    Revit ended up placing.
    """
    for stage in (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                  config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED,
                  config.STAGE_MODEL, config.STAGE_INTENT):
        item = group.first(stage)
        if item is not None and item.points:
            return item.points
    return []


def _label_of(item):
    """How to name a label in a message; many carry a size but no mark string."""
    name = (item.mark or item.text or "").strip()
    return repr(name[:30]) if name else "(unnamed)"


def _coincident(items, tolerance, space_key, key=None):
    """Groups of two or more items at the same point with the same identity.

    Identity defaults to (layer, type, rounded size): two lines of different
    lengths crossing at a point are not duplicates, and neither is a beam label
    sitting on the beam. `key` overrides it for the model sweep, where the
    category is the identity that matters.
    """
    index = spatial.Grid(max(tolerance, 1.0))
    for item in items:
        point = matching.match_point(item, space_key)
        if point is None:
            continue
        index.add(point, (point, item))

    seen = set()
    groups = []
    for bucket in index.buckets.values():
        for point, item in bucket:
            if id(item) in seen:
                continue
            identity = key(item) if key else _identity(item)
            cluster = [item]
            seen.add(id(item))
            for other_point, other in index.near(point):
                if id(other) in seen:
                    continue
                if (key(other) if key else _identity(other)) != identity:
                    continue
                distance = geometry.plan_distance(
                    (point[0], point[1], 0.0),
                    (other_point[0], other_point[1], 0.0))
                if distance is not None and distance <= tolerance:
                    cluster.append(other)
                    seen.add(id(other))
            if len(cluster) > 1:
                groups.append(cluster)
    return groups


def _identity(item):
    """What makes two entities "the same thing", for duplicate detection.

    Layer, type and size -- two lines of different lengths crossing at a point
    are not duplicates, and neither is a beam label sitting on its beam.

    Block DEPTH is part of it because a nested block chain puts one INSERT at
    each level at the very same point: LEVEL1 containing LEVEL2 containing
    LEVEL3 is one construct, and without depth it reads as four identical
    entities drawn on top of each other. Two blocks inserted twice at the same
    depth still register, which is the case worth reporting.
    """
    size = item.plan_size_mm
    rounded = (round(size[0]), round(size[1])) if size else None
    return (item.layer_key, item.source_type or item.kind, rounded,
            item.extra.get("depth"))


def _sized_texts(captures):
    """Text items from whichever stage read them, without double-counting.

    First stage that has any wins, rather than all of them merged: the same
    label read by two passes is one label, and merging would make every mark
    look like it conflicted with itself. Stage D is the last resort -- when no
    DXF was read, the run's own recorded labels are the only ones there are, and
    a report that ignored them would find nothing to say about labelling on a
    JSON-only audit.
    """
    for stage in (config.STAGE_DXF_PARSED, config.STAGE_DXF_RAW,
                  config.STAGE_INTENT):
        capture = captures.get(stage)
        if capture is None:
            continue
        texts = [item for item in capture.items if item.kind == "text" and
                 (item.mark or item.extra.get("b_mm"))]
        if texts:
            return texts
    return []


def _built_size(group):
    for stage in (config.STAGE_MODEL, config.STAGE_INTENT):
        size = group.size_mm(stage)
        if size:
            return size
    return None


def _first(group, stages):
    for stage in stages:
        if group.has(stage):
            return stage
    return None


def _has_drawing(group):
    return any(group.has(stage) for stage in
               (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED))


def _has_model(group):
    return group.has(config.STAGE_MODEL) or group.has(config.STAGE_INTENT)


def _ordered(a, b):
    if not a or not b:
        return None
    return (min(float(a), float(b)), max(float(a), float(b)))


def _same_level(a, b):
    """Level names, compared forgivingly.

    cad2bim's storey labels come out of the drawing ("%%U(TOWER 1)- GROUND
    FLOOR") while Revit's come from the level element, so an exact comparison
    would report every single element as being on the wrong storey.
    """
    def clean(text):
        return "".join(ch for ch in str(text).lower() if ch.isalnum())
    first, second = clean(a), clean(b)
    return first == second or first in second or second in first


def _finding(code, message, item=None, stage=None, category=None, detail=None):
    from .findings import Finding
    point_dxf = point_revit = None
    layer = level = mark = None
    if item is not None:
        centroid_dxf = item.centroid_dxf
        centroid_revit = item.centroid_revit
        point_dxf = None if centroid_dxf is None else (centroid_dxf[0], centroid_dxf[1])
        point_revit = (None if centroid_revit is None
                       else (centroid_revit[0], centroid_revit[1]))
        layer = item.layer_key
        level = item.level
        mark = item.mark
        category = category or item.category
    return Finding(code, config.severity_of(code), message, category=category,
                   layer=layer, level=level, mark=mark, point_dxf=point_dxf,
                   point_revit=point_revit, stages=[stage] if stage else [],
                   detail=detail)
