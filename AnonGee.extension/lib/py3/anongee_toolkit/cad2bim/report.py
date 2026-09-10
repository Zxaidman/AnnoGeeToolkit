# -*- coding: utf-8 -*-
"""Reporting: a human summary for the pyRevit output window and a JSON export.

The JSON schema is deliberately the intermediate format the future external
CPython 3 + ezdxf validator will consume, so writing it now is not throwaway --
it is the contract between the in-Revit reader and the out-of-Revit checker.
"""

import json
import math
import re
from collections import defaultdict, Counter

from .geom import shapes
try:
    from . import __version__
except ImportError:                      # test loaders stub the parent package
    __version__ = "?"
from .classify import marks
from . import config
from .classify.layers import (CATEGORY_COLUMN, CATEGORY_BEAM,
                              CATEGORY_SLAB_EDGE, CATEGORY_STAIR,
                              CATEGORY_STRUCT_WALL)

_MM = config.MM_PER_FT

# The console summary and the JSON export moved to export.py; they are re-exported
# here so every caller (and every test) keeps the import it has always used.
from .limits import (DEFAULT_LIMITS, parse_standard_sizes,
                     parse_standard_widths, _standard_dims_mm)  # noqa: E402,F401
from .column_geom import (_ring_closed, _inside_rectangles, _bbox_half,
                          _column_footprints, _distinct_ring_corners, _label_size,
                          column_outline_footprints, column_trim_footprints,
                          _OBSTACLE_SHORT_MIN_MM, _OBSTACLE_SHORT_MAX_MM,
                          _OBSTACLE_LONG_MAX_MM)          # noqa: E402,F401
from .columns_recovery import (recover_core_walls_from_labels,
                               recover_unplaced_labeled_columns,
                               recover_outline_columns, recover_face_columns,
                               drop_nested_columns)        # noqa: E402,F401
from .beam_segments import build_beam_segments        # noqa: E402,F401
from .beam_cleanup import (split_beams_at_columns,
                           snap_beam_ends_to_columns,
                           dedupe_beam_segments)      # noqa: E402,F401
from .export import (build_layer_counts, build_category_counts, format_summary,
                     format_column_sections, format_beam_segments,
                     format_console, build_export_payload, export_json,
                     export_storeys_json)          # noqa: E402,F401


_FRAG_MAX_LINE_MM = 2000.0   # column-layer lines shorter than this are junction bits
_FRAG_GAP_MM = 600.0         # fragments within this gap belong to the same column
#                              (a beam cut across an angled column can leave its two
#                              halves ~450 mm apart; still well under the ~1500 mm
#                              spacing of separate columns, so they do not fuse)
_FRAG_CLOSE_GAP_MM = 900.0   # a LONE outline left open this wide at a junction cut is
#                              still one column (rotated corner columns clip to ~600-800);
#                              recovered rects are deduped so this cannot double a column












_CORE_MIN_BBOX_MM = 1800.0     # smaller side of the outline's bbox; thin strips fall out
_CORE_MIN_AREA_MM2 = 3.0e6     # enclosed area (>= 3 m^2) of a real shaft outline
_CORE_WALL_MAX_MM = 1200.0     # pair faces up to this far apart (a member's depth); below
#                                the ~1500 mm stair opening, so a real opening stays open
_CORE_WALL_OVERLAP_MM = 500.0  # paired faces must share at least this much run
_CORE_WALL_DOOR_MM = 700.0     # merge collinear faces split by a gap this small (a door):
#                                a doorway punched through a wall must not split the member
_CORE_WALL_PAD_MM = 1200.0     # grow the core bbox by one depth so a deep member's outer
#                                face (one column-depth beyond the inner ring) is included


def _find_core_outlines(unplaced_raw):
    """Locate large UNCLOSED outlines (likely fragmented lift/stair cores) among the
    unplaced column-layer geometry. Returns a list of
    {"center_mm": [x, y], "area_m2": a, "bbox_mm": [x0, y0, x1, y1]} -- one per open-path
    polyline whose enclosed area >= _CORE_MIN_AREA_MM2 and whose smaller bbox side
    >= _CORE_MIN_BBOX_MM (a real shaft vs. the thin strips a working plan leaves behind).
    """
    cores = []
    for geom in unplaced_raw:
        if geom.get("kind") != "polyline" or geom.get("status") != "open_path":
            continue
        pts = geom.get("pts") or []
        if len(pts) < 4:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if min(max(xs) - min(xs), max(ys) - min(ys)) < _CORE_MIN_BBOX_MM:
            continue
        area = 0.0   # shoelace, auto-closing the open ring back to its first point
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            area += x0 * y1 - x1 * y0
        area = abs(area) / 2.0
        if area < _CORE_MIN_AREA_MM2:
            continue
        cores.append({
            "center_mm": [int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys)))],
            "area_m2": round(area / 1e6, 1),
            "bbox_mm": [min(xs), min(ys), max(xs), max(ys)],
        })
    return cores


def detect_fragmented_cores(unplaced_raw, placed_rects=None):
    """Flag a likely fragmented lift/stair core: a large UNCLOSED outline left on the
    column layer that never placed -- redraw it as a closed polyline so it places.

    Detection only -- returns advisory warnings, never geometry. `unplaced_raw`: the
    column-layer geometry that produced no rectangle ({kind, status, pts} in mm, exactly
    the JSON's dropped_raw). `placed_rects`: already-placed columns (feet); an outline
    whose centroid sits on one is part of a column that DID place and is skipped. Returns
    a list of {"center_mm": [x, y], "area_m2": a}.
    """
    placed_rects = placed_rects or []
    warnings = []
    for core in _find_core_outlines(unplaced_raw):
        cx, cy = core["center_mm"]
        if _inside_rectangles(cx / _MM, cy / _MM, placed_rects):
            continue   # outline sits on a column that actually placed
        warnings.append({"center_mm": core["center_mm"], "area_m2": core["area_m2"]})
    return warnings


def build_column_sections(records, limits=None, standards=None, texts=None,
                          tolerances=None):
    """Decompose every column-category polyline into rectangular sections, and
    derive spine rectangles from bare column-layer lines.

    When `texts` (sized DXF marks, internal feet) are given, each rectangle is
    refined to the size of the nearest mark (e.g. "C1 400x400"), overriding the
    geometry-derived dimensions before limit/standard filtering. `tolerances`
    (config.DEFAULTS overrides) tunes circle diameter range, snap and mark radius.

    Line-drawn members (e.g. a lift spine) carry no width on their own; where two
    or more legs meet such a line, a spine rectangle is derived (width = measured
    gap to the legs) and added as a placeable 'line_spine' entry. Lines that do
    not resolve to a spine are reported as leftover line_members.
    """
    tol = config.merged(tolerances)
    status_counts = defaultdict(int)
    total_rectangles = 0
    entries = []
    leg_rectangles = []
    line_points = []
    line_members = []
    arc_records = []
    polyline_records = []
    open_paths = []     # unclosed column-layer polylines (a core's inner ring lives here)
    unplaced_raw = []   # debug: column-layer geometry that produced no rectangle
    fragments = []      # small leftover pieces to reassemble into clipped columns
    for record in records:
        if record.category != CATEGORY_COLUMN:
            continue
        if record.kind == "line":
            line_points.append(record.points)
            length_mm = _polyline_length_ft(record.points) * 304.8
            line_members.append({"layer": record.layer, "length_mm": length_mm})
            unplaced_raw.append({"kind": "line", "layer": record.layer,
                                 "pts": _pts_mm(record.points)})
            if length_mm < _FRAG_MAX_LINE_MM:   # short = junction fragment, not a spine
                fragments.append(record.points)
        elif record.kind == "arc":
            arc_records.append(record)
        else:
            polyline_records.append(record)

    # Circles first, so polyline fragments of a circle (arcs captured as polylines)
    # can be discarded instead of becoming spurious little rectangles.
    circles = shapes.build_circular_columns(
        arc_records,
        min_dia_ft=config.mm_to_ft(tol["circle_min_dia_mm"]),
        max_dia_ft=config.mm_to_ft(tol["circle_max_dia_mm"]))

    def _inside_a_circle(rect):
        cx, cy, _z = rect.center
        for circle in circles:
            radius = circle.diameter / 2.0
            if (cx - circle.cx) ** 2 + (cy - circle.cy) ** 2 <= radius * radius:
                return True
        return False

    for record in polyline_records:
        # An OPEN polyline on the column layer is a junction fragment (a partial
        # L/U/-outline left when beams sliced the column), not a closed column.
        # Auto-closing it would forge a wrong, undersized sliver AND steal its
        # segments from recovery; route it to the fragment pool to be reassembled.
        if not _ring_closed(record.points):
            unplaced_raw.append({"kind": record.kind, "layer": record.layer,
                                 "status": "open_path",
                                 "pts": _pts_mm(record.points)})
            open_paths.append(record.points)
            fragments.append(record.points)
            status_counts["open_fragment"] += 1
            continue
        result = shapes.parse_column_polyline(record.points)
        kept = [rect for rect in result["rectangles"] if not _inside_a_circle(rect)]
        dropped = len(result["rectangles"]) - len(kept)
        if dropped:
            status_counts["circle_artifact"] += dropped
        if not kept:
            if result["status"] != "rectangle":   # genuinely lost, not a circle bit
                unplaced_raw.append({"kind": record.kind, "layer": record.layer,
                                     "status": result["status"],
                                     "pts": _pts_mm(record.points)})
                fragments.append(record.points)
            continue   # whole shape was a circle-drawing artifact
        status_counts[result["status"]] += 1
        if result.get("axis_snapped"):
            # The ring only became rectilinear after its drafting noise was
            # closed. It is a real composite column, not an approximation -- but
            # the run says how many it had to straighten rather than doing it
            # silently, because a count that jumps is how a wrong tolerance shows.
            status_counts["axis_snapped"] += 1
        total_rectangles += len(kept)
        leg_rectangles.extend(kept)
        entries.append({
            "layer": record.layer,
            "status": result["status"],
            "approx": result.get("approx", False),
            "rectangles": [rect.to_dict() for rect in kept],
        })

    spines = shapes.build_line_spines(line_points, leg_rectangles)
    if spines:
        status_counts["line_spine"] += len(spines)
        total_rectangles += len(spines)
        entries.append({
            "layer": "(line spine)",
            "status": "line_spine",
            "approx": False,
            "rectangles": [spine.to_dict() for spine in spines],
        })
    status_counts["line_member"] += len(line_members)
    status_counts["circle"] += len(circles)

    # Recover columns from fused/unclosed AXIS-ALIGNED wall outlines first: a long
    # wall drawn as one comb with its perpendicular legs (e.g. a 12300 base + four
    # 300x3300 teeth) never closes into a ring, so each piece would otherwise blob
    # into one oversized oriented rect. Assemble the pieces into closed rectilinear
    # rings and decompose them into their real columns. Feed both the open-path
    # fragments and the bare column lines (the long wall edges live in line_points).
    recl_paths = list(fragments) + list(line_points)
    recl_z = next((p[0][2] for p in recl_paths if p and len(p[0]) > 2), 0.0)
    strip_rects_raw, recl_consumed = shapes.recover_rectilinear_columns(
        recl_paths, z=recl_z)
    strip_rects = []
    for rect in strip_rects_raw:
        cx, cy, _cz = rect.center
        if _inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles):
            continue
        strip_rects.append(rect)
    if strip_rects:
        status_counts["recovered_strip"] += len(strip_rects)
        total_rectangles += len(strip_rects)
        leg_rectangles.extend(strip_rects)
        entries.append({
            "layer": "(recovered)",
            "status": "recovered_strip",
            "approx": True,
            "rectangles": [rect.to_dict() for rect in strip_rects],
        })
    # Drop fragments consumed by the rectilinear assembly so the oriented pass below
    # cannot re-cluster them into a duplicate blob (fragment ids index recl_paths,
    # whose first len(fragments) entries are the fragments themselves).
    fragments = [frag for i, frag in enumerate(fragments) if i not in recl_consumed]

    # Recover columns whose Revit outline was clipped into disconnected fragments
    # at a junction (e.g. angled F9): cluster the leftover pieces and fit an
    # oriented rectangle. Skip any that land inside an already-placed column.
    recovered = shapes.recover_oriented_columns(
        fragments, gap_ft=config.mm_to_ft(_FRAG_GAP_MM),
        close_gap_ft=config.mm_to_ft(_FRAG_CLOSE_GAP_MM))
    recovered_rects = []
    for rect in recovered:
        cx, cy, _cz = rect.center
        if (_inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles)
                or _inside_rectangles(cx, cy, recovered_rects)):
            continue   # already a placed column, or a sibling fragment of one just kept
        recovered_rects.append(rect)
    if recovered_rects:
        status_counts["recovered_rect"] += len(recovered_rects)
        total_rectangles += len(recovered_rects)
        leg_rectangles.extend(recovered_rects)
        entries.append({
            "layer": "(recovered)",
            "status": "recovered_rect",
            "approx": True,
            "rectangles": [rect.to_dict() for rect in recovered_rects],
        })

    # Recover a FRAGMENTED lift/stair core: its walls survive only as loose, never-closed
    # faces, so within each DETECTED core region pair opposing faces into thin wall rects
    # (openings have no opposing face -> no wall, so only solid walls place). Gated to the
    # detected cores, so a working plan -- which has no such region -- is never touched.
    cores = _find_core_outlines(unplaced_raw)
    core_paths = open_paths + line_points
    pad_ft = config.mm_to_ft(_CORE_WALL_PAD_MM)
    for core in cores:
        x0, y0, x1, y1 = (v / _MM for v in core["bbox_mm"])
        walls = shapes.recover_core_walls(
            core_paths, (x0 - pad_ft, y0 - pad_ft, x1 + pad_ft, y1 + pad_ft),
            config.mm_to_ft(tol["pair_min_width_mm"]),
            config.mm_to_ft(_CORE_WALL_MAX_MM),
            config.mm_to_ft(_CORE_WALL_OVERLAP_MM),
            bridge_ft=config.mm_to_ft(_CORE_WALL_DOOR_MM), z=recl_z)
        kept = []
        for rect in walls:
            cx, cy, _cz = rect.center
            if _inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles):
                continue
            kept.append(rect)
        core["recovered_walls"] = len(kept)
        if kept:
            status_counts["recovered_core_wall"] += len(kept)
            total_rectangles += len(kept)
            leg_rectangles.extend(kept)
            entries.append({
                "layer": "(recovered core)",
                "status": "recovered_core_wall",
                "approx": True,
                "rectangles": [rect.to_dict() for rect in kept],
            })

    refined = _apply_column_marks(entries, texts,
                                  config.mm_to_ft(tol["mark_radius_mm"]))
    if refined:
        status_counts["text_sized"] += refined

    dropped = _filter_column_entries(entries, limits or DEFAULT_LIMITS,
                                     standards or {}, tol["snap_tol_mm"])
    if dropped:
        status_counts["out_of_range"] += dropped
    total_rectangles = sum(len(e["rectangles"]) for e in entries)
    entries = [e for e in entries if e["rectangles"]]

    return {
        "status_counts": dict(status_counts),
        "total_rectangles": total_rectangles,
        "entries": entries,
        "warnings": [{"center_mm": c["center_mm"], "area_m2": c["area_m2"],
                      "recovered_walls": c.get("recovered_walls", 0)} for c in cores],
        "line_members": line_members,
        "line_spines": [spine.to_dict() for spine in spines],
        "circles": [circle.to_dict() for circle in circles],
        "dropped_raw": unplaced_raw,
    }


def _pts_mm(points):
    """[(x,y,z) feet ...] -> [[x_mm, y_mm], ...] integer pairs, for debug dumps."""
    return [[int(round(p[0] * _MM)), int(round(p[1] * _MM))] for p in points]


_TEXT_SIZE_OK_MM = 80.0   # a single column already this close to its label is left as-is
_CLIP_TOL_MM = 20.0       # ...unless geometry is shorter than the label by more than this
#                           (a real clip), in which case it is resized up to the label
# What `parse_column_polyline` calls a single closed ring decomposed to ONE
# rectangle -- a column whose size the drawing stated by drawing it. Every other
# status here is a PIECE (a leg, a recovered fragment, a box round a shape that
# would not close), and a piece is what a size label is allowed to correct.
_WHOLE_RING = "rectangle"
_SPLIT_CENTRE_SLACK_MM = 80.0      # split fragments' centres lie within (long side + this)
_SPLIT_NO_SIZE_MAX_CENTRE_MM = 800.0   # no label size: only fuse pieces this close

# --- label-guided core-wall placement --------------------------------------




















def correct_columns_with_text(sections, column_texts, radius_ft, schedule=None,
                              grid_x=None, grid_y=None, grid_snap_ft=None):
    """Use column labels (one per real column) to fix clipped/split geometry and
    to name columns.

    A label supplies a SIZE (inline "600x750"), a MARK ("C1"), or both. The size
    used for a column is resolved: inline label size > schedule[mark] > geometry.
    For each label, gather the placed column rectangles within radius_ft:
      * one rectangle the drawing closed as a WHOLE RING -> kept exactly as drawn,
        mark stamped. Its outline already states its size and a label does not
        overrule it in either direction (BUG-34; see `_whole_rings`);
      * one rectangle already the right size -> left as-is (mark stamped);
      * one clipped PIECE with a known size -> resized + snapped to the grid;
      * two split pieces -> merged into one column (sized to the label/schedule, or
        their combined footprint when no size is known) + snapped to the grid;
      * a single mark-only piece (no size anywhere) -> kept as geometry, mark only.
    Clusters of >2 pieces (multi-leg lift/stair cores) are left as separate legs.
    Returns the count of columns touched (resized/merged/named).
    """
    schedule = schedule or {}
    entries = sections.get("entries", [])
    rects = [rect for entry in entries for rect in entry["rectangles"]]
    whole = _whole_rings(entries)   # the ones the drawing sized by drawing them
    labels = [t for t in (column_texts or []) if t.point_internal and
              ((t.b_mm is not None and t.h_mm is not None) or t.mark)]
    used = set()
    outputs = []
    r2 = radius_ft * radius_ft

    # Each rectangle belongs to its NEAREST label. A long member's label reaches far
    # (radius is fixed at mark_radius_mm), so without this a 300x3300 wall's label would
    # swallow a distinct 600x900 column 465 mm away as a "split pair" -- its merge window
    # is the labelled long side (3300). Ownership lets a closer label keep its own column.
    owner = {}
    for rect in rects:
        rcx, rcy = rect["center"][0], rect["center"][1]
        best, best_d2 = None, r2
        for text in labels:
            d2 = ((text.point_internal[0] - rcx) ** 2
                  + (text.point_internal[1] - rcy) ** 2)
            if d2 < best_d2:
                best, best_d2 = text, d2
        owner[id(rect)] = best

    for text in labels:
        tx, ty = text.point_internal[0], text.point_internal[1]
        near = [rect for rect in rects if id(rect) not in used
                and owner.get(id(rect)) is text
                and (rect["center"][0] - tx) ** 2 + (rect["center"][1] - ty) ** 2 <= r2]
        if not near or len(near) > 2:
            continue   # none, or a multi-leg lift/stair core: leave the geometry
        size = _label_size(text, schedule)   # (small, big) mm, or None

        if len(near) == 2 and not _is_split_pair(near, size):
            # One label per column, but an offset label on a tight grid bay (e.g.
            # grids ~1500mm apart) can reach a NEIGHBOURING column too. These are
            # two complete, separate columns -- bind this label to its OWN
            # (nearest) column and leave the other for its own label, instead of
            # fusing them into one column mid-bay with its orientation lost.
            near = [min(near, key=lambda r:
                        (r["center"][0] - tx) ** 2 + (r["center"][1] - ty) ** 2)]

        if size is None and len(near) == 1:
            # Mark only, single clean piece: name it, keep geometry size+position.
            out = _copy_rect(near[0])
            out["mark"] = text.mark
            used.add(id(near[0]))
            outputs.append(out)
            continue
        if size is not None and len(near) == 1:
            if id(near[0]) in whole or (_fills_size(near[0], size)
                                        and not _is_clipped(near[0], size)):
                out = _copy_rect(near[0])      # keep the geometry: just name it
                out["mark"] = text.mark
                used.add(id(near[0]))
                outputs.append(out)
                continue
            # else fall through: a clipped column (geometry shorter than its known
            # size, e.g. a 270 mm sliver of a scheduled 300 mm column) is resized up
            # to the authoritative label size below, keeping its orientation+centre.
        if size is None:                       # split pieces, no size: use footprint
            size = _union_size(near)

        for rect in near:
            used.add(id(rect))
        rect = _merge_to_label(near, size[0], size[1], text.mark)
        _anchor_growth(rect, near, rects)
        if grid_snap_ft:                       # we moved/resized -> snap onto the grid
            rect["center"][0] = _snap(rect["center"][0], grid_x, grid_snap_ft)
            rect["center"][1] = _snap(rect["center"][1], grid_y, grid_snap_ft)
        # A small column cast hard against a bigger one (C17 beside a 600x900) can
        # survive Revit's import only as a mis-centred sliver. Resizing that sliver to
        # the label size lands the column's CENTRE inside its larger neighbour -- two
        # stacked columns. Don't claim it here: drop the absorbed sliver and leave the
        # mark unplaced so the abutment pass (recover_unplaced_labeled_columns) places
        # it edge-to-edge, exactly as it already does for the same column when the DXF
        # is more fragmented. Only defer a mark the abutment pass can re-place (it needs
        # a schedule size); otherwise keep the placement rather than drop the column.
        if (_center_inside_larger(rect, rects, near) and
                text.mark and text.mark in schedule):
            continue
        outputs.append(rect)
    if not outputs:
        return 0
    leftover = [rect for rect in rects if id(rect) not in used]
    sections["entries"] = [{"layer": "(text-corrected)", "status": "text_corrected",
                            "approx": True, "rectangles": outputs + leftover}]
    counts = sections.setdefault("status_counts", {})
    counts["text_corrected"] = counts.get("text_corrected", 0) + len(outputs)
    sections["total_rectangles"] = len(outputs) + len(leftover)
    return len(outputs)


def apply_circle_marks(sections, column_texts, radius_ft):
    """Stamp the nearest column label's MARK onto each circular column.

    correct_columns_with_text only refines rectangles, so circular columns are
    named here: each circle adopts the mark of the nearest labelled text within
    radius_ft (its size already comes from geometry). Best-effort -- returns the
    count named.
    """
    circles = sections.get("circles") or []
    marks = [t for t in (column_texts or []) if t.mark and t.point_internal]
    if not circles or not marks:
        return 0
    r2 = radius_ft * radius_ft
    count = 0
    for circle in circles:
        cx, cy = circle["center"][0], circle["center"][1]
        best, best_d2 = None, r2
        for text in marks:
            d2 = ((text.point_internal[0] - cx) ** 2
                  + (text.point_internal[1] - cy) ** 2)
            if d2 <= best_d2:
                best, best_d2 = text, d2
        if best is not None:
            circle["mark"] = best.mark
            count += 1
    return count


# A small column cast hard against a bigger one fragments so badly that recovery
# folds its pieces into the neighbour; these tune recovering it from its label.








def _is_split_pair(rects, size):
    """True when two near rectangles are two fragments of ONE clipped column
    (safe to merge), False when they are two complete, separate columns that a
    single offset label happened to reach across a tight grid bay.

    A genuine clip splits one column, so the fragments' centres lie within the
    column's own long dimension; two distinct columns sit a grid bay apart. And
    if BOTH near pieces already fill the labelled size, they cannot be fragments.
    """
    a, b = rects
    centre_mm = math.hypot(a["center"][0] - b["center"][0],
                           a["center"][1] - b["center"][1]) * _MM
    if size is not None:
        if _fills_size(a, size) and _fills_size(b, size):
            return False
        return centre_mm <= size[1] + _SPLIT_CENTRE_SLACK_MM
    return centre_mm <= _SPLIT_NO_SIZE_MAX_CENTRE_MM


def _fills_size(rect, size):
    """True when a rectangle already matches the labelled (small, big) mm size."""
    small_g = min(rect["width_mm"], rect["height_mm"])
    big_g = max(rect["width_mm"], rect["height_mm"])
    return (abs(small_g - size[0]) <= _TEXT_SIZE_OK_MM and
            abs(big_g - size[1]) <= _TEXT_SIZE_OK_MM)


def _whole_rings(entries):
    """The ids of rectangles whose own outline states their size (BUG-34).

    One closed ring, decomposed to one rectangle: the drawing said how big that
    column is by drawing it, so a size label may NAME it but not resize it.
    Every other status here is a piece -- a leg of an L or a C, a fragment the
    recovery reassembled, a box drawn round a shape that would not close -- and
    a piece is exactly what a label is allowed to correct, because a piece
    really is smaller than the column its label states.

    The owner: "in some place column size and its outline is not matching with
    Linked cad." Resizing to a label is deliberate -- DONE-22 built it so a
    CLIPPED column could be snapped up to its authoritative size -- but the
    decision was taken on a flat list of rectangles, so a column the drawing
    closed as ONE complete ring got the same treatment as a sliver.

    MEASURED on `StructuralPlan-Test17-clean.dxf`, first three storeys, texts
    routed as the build routes them:

        the member came from       left as drawn   grown to a label   shrunk
        one closed ring                      496                127       14
        a leg of an L or a C                  58                 31        3

    About 42 whole columns per storey were being inflated past the outline they
    were drawn with -- 250x1200 built as 250x1500 -- and 152 of the 158 grown
    had a drawn size that is a round 25 mm on BOTH sides. A junction clip leaves
    an arbitrary sliver (187, 213); a round number is a section somebody drew on
    purpose. The 31 legs are the case the pass exists for and they still grow:
    a leg really is smaller than the column its label states.

    The mark is stamped either way -- keeping the size must not cost the naming,
    which the schedule, the naming template and the abutment recovery all use.
    """
    return set(id(rect) for entry in entries or ()
               if entry.get("status") == _WHOLE_RING
               for rect in entry.get("rectangles") or ())


def _is_clipped(rect, size):
    """True when geometry is CLIPPED below the labelled size on either dimension.

    A label's size is authoritative, so a clipped column -- e.g. a 270 mm sliver of
    a scheduled 300 mm column, a shortfall that still lands inside the _fills_size
    'close enough' band -- must be resized UP to the label instead of kept as drawn.
    Only a real shortfall past _CLIP_TOL_MM counts, so geometry noise on an already
    correct column does not trigger a needless resize.
    """
    small_g = min(rect["width_mm"], rect["height_mm"])
    big_g = max(rect["width_mm"], rect["height_mm"])
    return (small_g < size[0] - _CLIP_TOL_MM or big_g < size[1] - _CLIP_TOL_MM)




def _union_size(rects):
    """(small, big) mm of the axis-aligned union of the rectangles' footprints."""
    xs, ys = [], []
    for r in rects:
        cx, cy = r["center"][0] * _MM, r["center"][1] * _MM
        xs += [cx - r["width_mm"] / 2.0, cx + r["width_mm"] / 2.0]
        ys += [cy - r["height_mm"] / 2.0, cy + r["height_mm"] / 2.0]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return (min(w, h), max(w, h))


def _copy_rect(rect):
    out = dict(rect)
    out["center"] = list(rect["center"])
    return out


def _center_inside_larger(rect, rects, exclude):
    """True when rect's centre sits INSIDE a strictly larger placed rectangle.

    A real column centre never lies within another column; when it does, rect is a
    sliver of a column absorbed into a bigger neighbour rather than a column of its
    own. `exclude` are the pieces rect was built from (its own geometry), skipped by
    identity so a split-pair never reads as inside one of its own halves.
    """
    cx, cy = rect["center"][0], rect["center"][1]
    area = rect["width_mm"] * rect["height_mm"]
    skip = set(id(r) for r in exclude)
    for other in rects:
        if id(other) in skip or id(other) == id(rect):
            continue
        if other["width_mm"] * other["height_mm"] <= area:
            continue                           # only a LARGER neighbour absorbs
        ohx, ohy = _bbox_half(other)
        if (abs(cx - other["center"][0]) < ohx and
                abs(cy - other["center"][1]) < ohy):
            return True
    return False


def _snap(value, positions, tol_ft):
    """Snap value to the nearest grid position within tol_ft, else return value."""
    if not positions:
        return value
    nearest = min(positions, key=lambda p: abs(p - value))
    return nearest if abs(nearest - value) <= tol_ft else value


_ABUT_TOL_FT = 150.0 / _MM     # a neighbour this close to an end is touching it


def _anchor_growth(rect, near, all_rects):
    """Grow a resized column back over the piece that was CARVED off it.

    A wall crossing another wall is decomposed into pieces, so the drawn piece
    stops at the crossing member's face. Applying the schedule length about the
    PIECE's centre then pushes the wall past its free end -- StaircasePlan-Test2's
    SW10 grew 400mm longer and its centre rose 200mm, off the drawing.

    When the new length exceeds what was drawn and exactly ONE end abuts another
    rectangle, that end is where the carve happened: the FREE end is pinned and
    the column grows inward, back over the piece it lost.
    """
    if not near:
        return
    along_y = (rect.get("long_axis_deg") or 0.0) > 45.0
    axis = 1 if along_y else 0
    cross = 0 if along_y else 1

    def extent(r, index):
        """(lo, hi) of a rect along x (index 0) or y (index 1).

        TWO conventions live in `sections` and they disagree about what
        width_mm/height_mm mean. A plain axis-aligned rectangle (what
        decompose_to_rectangles returns for a rectilinear ring) stores them as
        its X and Y sizes and carries NO long_axis_deg. An ORIENTED rect stores
        them as SHORT and LONG, with long_axis_deg saying which way the long
        side points. Reading the first as if it were the second is what left
        SW10 200mm high: its 7450mm leg measured as the 400mm wall thickness,
        so the growth looked symmetric and no end was pinned.
        """
        deg = r.get("long_axis_deg")
        if deg is None:
            side = r["width_mm"] if index == 0 else r["height_mm"]
        else:
            long_mm = max(r["width_mm"], r["height_mm"])
            short_mm = min(r["width_mm"], r["height_mm"])
            side = long_mm if (index == 1) == (deg > 45.0) else short_mm
        half = (side / _MM) / 2.0
        return (r["center"][index] - half, r["center"][index] + half)

    lo = min(extent(r, axis)[0] for r in near)
    hi = max(extent(r, axis)[1] for r in near)
    new_half = (max(rect["width_mm"], rect["height_mm"]) / _MM) / 2.0
    if 2.0 * new_half <= (hi - lo) + _ABUT_TOL_FT:
        return                              # not growing: nothing to re-anchor

    claimed = set(id(r) for r in near)
    c_lo, c_hi = extent(rect, cross)
    thickness = c_hi - c_lo
    touches_lo = touches_hi = False
    crosses_lo = crosses_hi = False
    for other in all_rects:
        if id(other) in claimed:
            continue
        o_lo, o_hi = extent(other, axis)
        ox_lo, ox_hi = extent(other, cross)
        if ox_hi < c_lo - _ABUT_TOL_FT or ox_lo > c_hi + _ABUT_TOL_FT:
            continue                        # not alongside this column
        # A member that runs ACROSS this wall is what carved it; one that merely
        # butts its end (a column stacked on top) did not. Test2's SW10 has SW9
        # crossing below AND a 900x900 column above, so "exactly one end abuts"
        # was never true and the wall kept its carved centre.
        crossing = (ox_lo < c_lo - thickness or ox_hi > c_hi + thickness)
        if abs(o_hi - lo) <= _ABUT_TOL_FT or (o_lo <= lo <= o_hi):
            touches_lo = True
            crosses_lo = crosses_lo or crossing
        if abs(o_lo - hi) <= _ABUT_TOL_FT or (o_lo <= hi <= o_hi):
            touches_hi = True
            crosses_hi = crosses_hi or crossing
    if crosses_lo != crosses_hi:
        # grow back over the CROSSING member, pinning the other end
        rect["center"][axis] = (hi - new_half) if crosses_lo else (lo + new_half)
        return
    if touches_lo == touches_hi:
        return                              # both ends free (or both blocked)
    rect["center"][axis] = (hi - new_half) if touches_lo else (lo + new_half)


def _merge_to_label(rects, small_mm, big_mm, mark):
    """One column rectangle at the merged centre, sized small x big (short x long)."""
    mcx = sum(r["center"][0] for r in rects) / len(rects)
    mcy = sum(r["center"][1] for r in rects) / len(rects)
    mz = rects[0]["center"][2]
    if len(rects) == 1 and rects[0].get("long_axis_deg") is not None:
        deg = rects[0]["long_axis_deg"]     # keep a clipped oriented column's angle
    else:
        xs = []
        ys = []
        for r in rects:
            hw = (r["width_mm"] / _MM) / 2.0
            hh = (r["height_mm"] / _MM) / 2.0
            xs += [r["center"][0] - hw, r["center"][0] + hw]
            ys += [r["center"][1] - hh, r["center"][1] + hh]
        deg = 90.0 if (max(ys) - min(ys)) >= (max(xs) - min(xs)) else 0.0
    return {"center": [mcx, mcy, mz],
            "width_mm": small_mm, "height_mm": big_mm,
            "width_ft": small_mm / _MM, "height_ft": big_mm / _MM,
            "long_axis_deg": deg, "mark": mark}


def _filter_column_entries(entries, limits, standards, snap_tol_mm):
    """Snap each rectangle's b/h to standard sizes and drop out-of-range ones.

    Snapping preserves which stored dimension (width/height) is the short side, so
    the placement rotation stays correct. Returns the number dropped.

    THE SHARED FACE IS HELD HERE TOO, for the reason spelled out on
    `_apply_column_marks`: this is the second of the two places that rewrite a
    rectangle's size and leave its centre where it was, so a snapped piece of a
    composite column drifted off the piece it was drawn against. Measured on
    test14, this site accounts for the last 3 of the 21 broken columns -- one per
    plan, a 601 x 350 leg snapped 25 mm into its neighbour with no label anywhere
    near it, which is what proves the two sites are separate faults.
    """
    dims = [d / _MM for d in _standard_dims_mm(standards.get("column", []))]
    tol = snap_tol_mm / _MM
    b_min, b_max = limits["col_b_min_mm"], limits["col_b_max_mm"]
    h_min, h_max = limits["col_h_min_mm"], limits["col_h_max_mm"]
    dropped = 0
    for entry in entries:
        kept = []
        anchors = _shared_faces(entry["rectangles"])
        for rect, (x_anchor, y_anchor) in zip(entry["rectangles"], anchors):
            w_mm, h_mm = rect["width_mm"], rect["height_mm"]
            small, big = min(w_mm, h_mm), max(w_mm, h_mm)
            small = shapes.snap_to_standard(small / _MM, dims, tol) * _MM
            big = shapes.snap_to_standard(big / _MM, dims, tol) * _MM
            if not (b_min <= small <= b_max and h_min <= big <= h_max):
                dropped += 1
                continue
            box = _rect_box(rect)
            new_w, new_h = (small, big) if w_mm <= h_mm else (big, small)
            _cx, _cy, cz = rect["center"]
            cx = _resized(rect, box, x_anchor, "width", new_w)
            cy = _resized(rect, box, y_anchor, "height", new_h)
            rect["center"] = [cx, cy, cz]
            kept.append(rect)
        entry["rectangles"] = kept
    return dropped


def _polyline_length_ft(points):
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
    return total



















































































_FACE_TOL_FT = 1.0 / 304.8      # a millimetre: drawn-to-meet counts as meeting


def _rect_box(rect):
    """(x_min, y_min, x_max, y_max) in feet, off a rectangle dict."""
    cx, cy, _cz = rect["center"]
    half_w = rect["width_mm"] / (2.0 * 304.8)
    half_h = rect["height_mm"] / (2.0 * 304.8)
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _shared_faces(rects):
    """[(x_anchor, y_anchor)] per rect -- the face that must not move on resize.

    "min", "max", "both", or None. A piece touching a sibling on ONE side is
    anchored to that side and grows or shrinks away from it. Touching on NEITHER
    it keeps its centre, as it always did.

    "both" means the piece is boxed in, and then the drawn extent WINS over the
    label: no translation can hold two opposite faces still while the distance
    between them changes, so the only ways out are to overlap a neighbour, leave
    a gap, or leave the dimension alone. The drawing decides where concrete meets
    concrete -- the neighbours were drawn against those faces -- so the size is
    left alone on that axis. Measured, this is the last 3 of test14's 21 broken
    columns: a 300 mm blade with a leg drawn on each side, relabelled 350, spread
    25 mm into both of them.

    Read off the ORIGINAL boxes, before anything is resized: the tiling of the
    drawn outline is what says which pieces meet, and a piece already moved is
    no longer evidence of it.
    """
    boxes = [_rect_box(rect) for rect in rects]
    out = []
    for index, box in enumerate(boxes):
        low_x = high_x = low_y = high_y = False
        for other_index, other in enumerate(boxes):
            if other_index == index:
                continue
            overlap_y = min(box[3], other[3]) - max(box[1], other[1])
            overlap_x = min(box[2], other[2]) - max(box[0], other[0])
            if overlap_y > _FACE_TOL_FT:
                low_x = low_x or abs(box[0] - other[2]) <= _FACE_TOL_FT
                high_x = high_x or abs(box[2] - other[0]) <= _FACE_TOL_FT
            if overlap_x > _FACE_TOL_FT:
                low_y = low_y or abs(box[1] - other[3]) <= _FACE_TOL_FT
                high_y = high_y or abs(box[3] - other[1]) <= _FACE_TOL_FT
        out.append((_anchor(low_x, high_x), _anchor(low_y, high_y)))
    return out


def _anchor(low, high):
    """Which face a resize must hold: "min", "max", "both" or None."""
    if low and high:
        return "both"
    if low:
        return "min"
    if high:
        return "max"
    return None


def _resized(rect, box, anchor, key, new_mm):
    """Set one dimension and return the centre coordinate that keeps its faces.

    "both" is the pinned case: the drawn extent stays, because a neighbour is
    drawn against each face and the label cannot move either of them.
    """
    if anchor == "both":
        return (box[0] + box[2]) / 2.0 if key == "width" else (box[1] + box[3]) / 2.0
    rect[key + "_mm"] = new_mm
    rect[key + "_ft"] = new_mm / _MM
    half = rect[key + "_ft"] / 2.0
    if key == "width":
        if anchor == "min":
            return box[0] + half
        if anchor == "max":
            return box[2] - half
        return (box[0] + box[2]) / 2.0
    if anchor == "min":
        return box[1] + half
    if anchor == "max":
        return box[3] - half
    return (box[1] + box[3]) / 2.0


def _apply_column_marks(entries, texts, radius_ft):
    """Refine each column rectangle from the nearest sized DXF mark, in place.

    Adopts the mark's magnitudes but preserves the geometry's orientation (which
    side is short vs long), so placement rotation stays correct. Returns the count
    refined.

    A RESIZED PIECE KEEPS THE FACE IT SHARES WITH ITS NEIGHBOURS. This changed
    the size and left `center` alone, so every piece grew or shrank about its own
    middle and both its faces moved -- which is fine for a column that is one
    rectangle and wrong for every column that is more than one. The pieces of an
    L or a T come out of `decompose_to_rectangles`, which is an exact cover:
    measured, all 111 of test14's composite rings tile perfectly before this runs
    and 21 of them are broken after it. The owner, in Revit: "in some places it
    create perfectly column as per outline but in other places it leaves gap
    between junctions or overlap does not follow outline properly or
    discounted."

    Both his symptoms are this one arithmetic, to the millimetre:

        a 249 x 350 stub sized to 200 x 600 kept its centre, so the face it
        shared with its blade moved 24 mm off it -- a GAP;
        a 399 x 350 stub sized to 600 x 200 kept its centre, so its inner face
        went 101 mm INTO the blade -- an OVERLAP.

    Anchoring the shared face makes the piece grow or shrink away from the
    column it belongs to, which is the only direction with room for it.

    `width_ft`/`height_ft` are updated with the millimetres, which they were not:
    `column_geom._bbox_half` reads the FEET, so a trim footprint was being
    computed from the drawn size while the column was placed at the labelled one.
    """
    candidates = marks.sized_texts(texts or [])
    if not candidates:
        return 0
    count = 0
    for entry in entries:
        rects = entry["rectangles"]
        anchors = _shared_faces(rects)
        for rect, (x_anchor, y_anchor) in zip(rects, anchors):
            cx, cy, cz = rect["center"]
            hit = marks.nearest_sized_text(cx, cy, candidates, radius_ft)
            if hit is None:
                continue
            small_t, big_t = min(hit.b_mm, hit.h_mm), max(hit.b_mm, hit.h_mm)
            box = _rect_box(rect)
            if rect["width_mm"] <= rect["height_mm"]:
                new_w, new_h = small_t, big_t
            else:
                new_w, new_h = big_t, small_t
            cx = _resized(rect, box, x_anchor, "width", new_w)
            cy = _resized(rect, box, y_anchor, "height", new_h)
            rect["center"] = [cx, cy, cz]
            rect["mark"] = hit.mark
            count += 1
    return count




















