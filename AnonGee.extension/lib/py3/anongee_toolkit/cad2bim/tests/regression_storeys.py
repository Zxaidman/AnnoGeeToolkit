# -*- coding: utf-8 -*-
"""Regression leg 3 of 3: every storey of every multi-storey export, replayed.

Rebuilt from `scratchpad/t10_full.py` and `t10_cols.py`, which were never
committed and are gone. Four exports carry a storey stack: test10 (10 storeys),
test9 (11), test12 (5), test13 (5). Each storey is replayed on its own and its
numbers recorded per storey, in order.

Why this is not covered by the other two legs: they both replay ONE storey, and
almost every storey bug this project has had lived in the storeys the first one
hides. test10's ROOF is the case that named this harness -- it carries no A-FLOR
layer at all, so the drawn-edge source finds nothing there while finding plenty
on the floors below, and the v0.67.2 "note recovery only ran when edges were
found" bug built zero roof slabs while every storey below looked perfect. A
single-storey fingerprint cannot see that. A per-storey one cannot miss it.

The per-storey lists are stored whole rather than summed, so a diff points at
the storey that moved instead of saying a total changed.

The stored numbers were measured at v0.68.1, the release confirmed against
Revit, not recovered from the lost baseline. Drift is what they defend.

A SECOND corpus rides in the same leg, for the same reason the leg exists at
all: `column_extent` decides which storey each column is BUILT on, and nothing
else in the gate could see it. The two other legs replay one plan each, and the
export replay above reads what Revit already placed rather than what the drawing
says -- an export records a column's x, y, b and h, never the layer it was drawn
on, so the `_START`/`_STOP` reading cannot be replayed from one. So the fixture
DXFs that split into a stack are read here and their column extents recorded per
storey (v1.0.2, BUG-37). It is the same question the leg already asks -- what
does each storey produce -- asked of the half the exports cannot answer.

SLOW (~70s), hence `regression_*` and not `test_*`:

    cd cad2bim/tests
    python3 -m unittest regression_storeys
    CAD2BIM_BLESS=1 python3 -m unittest regression_storeys    # re-record
"""

import json
import os
import re
import unittest

import _golden
import _loader
import regression_slab_fingerprints as fingerprints


report, slab_outlines = _loader.load("report", "slab_outlines")
column_extent, dxf_reader, layers, floor_plans = _loader.load(
    "column_extent", "readers.dxf_reader", "classify.layers", "floor_plans")

_BASELINE = "storeys"
_COLUMN_BASELINE = "column_extents"
_CAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cad")
_FT = 1.0 / 304.8


def _multi_storey_corpus():
    """{drawing: path} for the exports that carry more than one storey."""
    corpus = {}
    for drawing, path in fingerprints._corpus().items():
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        if len(document.get("storeys") or []) > 1:
            corpus[drawing] = path
    return corpus


def _label(storey, index):
    """A storey's title, flattened to one line and trimmed.

    test9's titles carry embedded newlines ("GROUND FLOOR FRAMING PLAN \n( TOWER
    AREA )"); a baseline is read in a diff, so they are stored on one line.
    """
    text = " ".join(str(storey.get("storey") or "").split())
    return text or "storey {0}".format(index + 1)


def _measure(path):
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    storeys = document.get("storeys") or []

    labels, beams, edges, graph, placed, areas = [], [], [], [], [], []
    for index, storey in enumerate(storeys):
        records = fingerprints._records(storey)
        sections = fingerprints._sections(storey)
        footprints = report.column_trim_footprints(sections)
        circles = [{"center": c["center"], "diameter_ft": c["diameter_ft"]}
                   for c in sections["circles"]]
        segments = report.build_beam_segments(records, circles, None, None,
                                              texts=[], tolerances={},
                                              schedule=None)
        placed_loops = slab_outlines.slab_loops_from_placed_members(
            records, segments.get("segments") or [], column_rects=footprints)

        labels.append(_label(storey, index))
        beams.append(len(segments.get("segments") or []))
        edges.append(len(slab_outlines.slab_loops_from_edges(records)))
        graph.append(len(slab_outlines.slab_loops_from_beam_graph(
            segments.get("segments") or [])))
        placed.append(len(placed_loops))
        areas.append(round(sum(fingerprints._area_m2(loop[0])
                               for loop in placed_loops), 1))

    roof = _roof_index(storeys)
    return {
        "storeys": len(storeys),
        "labels": labels,
        "beams_per_storey": beams,
        "loops_from_edges_per_storey": edges,
        "loops_from_beam_graph_per_storey": graph,
        "loops_from_placed_members_per_storey": placed,
        "placed_area_m2_per_storey": areas,
        # The roof, called out on its own because it is the storey that has
        # broken before while every floor below stayed right.
        "roof_loops_from_edges": edges[roof] if edges else 0,
        "roof_loops_from_placed_members": placed[roof] if placed else 0,
    }


def _roof_index(storeys):
    """The storey the drawing CALLS the roof, else the top of the stack.

    Pinned by label, not position -- the same lesson the fingerprint leg
    already learned about its main storey. "Terrace" and "Roof" tie in level
    order (both are top-of-building names), so their stored order can flip
    between two runs of the same drawing: the user's 0.69.0 test10 export came
    back [..., Roof, Terrace] where every earlier one was [..., Terrace,
    Roof], and an index of -1 silently re-pointed the roof metrics at the
    terrace -- reporting 7 -> 30 as if the roof had changed, when nothing in
    either storey had moved at all.
    """
    for index in range(len(storeys) - 1, -1, -1):
        if re.search(r"\broof\b", str(storeys[index].get("storey") or ""),
                     re.IGNORECASE):
            return index
    return len(storeys) - 1


def _column_stacks():
    """Every fixture DXF, by name, in a fixed order.

    Discovered, not listed, for the same reason the sweep discovers its own: a
    drawing added to the corpus should appear as a new stack in the diff rather
    than be silently ignored. The one-storey drawings are dropped after they are
    measured, by the measurement itself -- whether a drawing carries a stack is
    something `split_floors` decides, not something a filename says.
    """
    if not os.path.isdir(_CAD):
        return []
    return sorted(name for name in os.listdir(_CAD)
                  if name.lower().endswith(".dxf"))


def _everything_replayed():
    """Everything this leg opens: the export stacks AND the fixture drawings.

    The leg replays two corpora now, and a size that named only the first would
    be the same misreporting the runner's own comment warns about -- it said 4
    stacks while replaying 7. Counted at print time, and counting what is READ:
    a drawing that turns out to carry one storey is dropped from the column
    baseline after it is measured, and the baseline shows which.
    """
    return sorted(_multi_storey_corpus()) + list(_column_stacks())


def _footprints(records):
    """[(centre, layer, (w_mm, h_mm))] for one plan's column outlines."""
    rows = []
    for record in records or []:
        if getattr(record, "category", None) != layers.CATEGORY_COLUMN:
            continue
        points = getattr(record, "points", None) or []
        if len(points) < 3:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rows.append((((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0),
                     getattr(record, "layer", ""),
                     ((max(xs) - min(xs)) * 304.8, (max(ys) - min(ys)) * 304.8)))
    return rows


def _measure_column_extents(path):
    """What `column_extent` makes of one stack, per storey.

    Nothing else in the gate reaches this. The other two legs replay ONE plan
    each, and the export replay above reads what Revit already placed -- neither
    can see the machinery that decides which storey a column is BUILT on, which
    is `plan` reading `_START`/`_STOP` across the whole stack and `plan_storey`
    answering for one of them. That machinery has been wrong twice in ways only
    the owner's eyes caught: FEAT-16's runs, BUG-35's two members on one grid
    point, BUG-37's column built inside the one it stands on.

    `builds_per_storey` is the number that moves when any of it moves, and
    `clashing_pairs_per_storey` is the fault itself: two built rectangles more
    than a third inside each other, which is what the owner photographed. Zero
    is the right answer and the baseline says so out loud.

    The sections are built WITHOUT texts, unlike the run and unlike the sweep
    leg. Deliberately: the size labels are the sweep's subject and are pinned
    there already, and what is being measured here is which STOREY a column is
    built on. Feeding the labels in would make every number in this baseline
    move whenever the label reading moved, for reasons that have nothing to do
    with the question, and a baseline that moves for unrelated reasons is a
    baseline that gets blessed without being read.
    """
    result = dxf_reader.read_dxf(path)
    for record in result.records:
        record.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in record.points]
    for region in result.regions:
        region.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in region.points]
    for text in result.texts:
        text.point_internal = (text.point[0] * _FT, text.point[1] * _FT, 0.0)
    layers.apply_mapping(
        result.records,
        layers.build_default_mapping([r.layer_key for r in result.records]))
    regions, _named = floor_plans.split_floors(result.records, result.texts,
                                               marker_records=result.records,
                                               hatches=result.regions)
    plans = [_footprints(region.records) for region in regions]
    spans, columns = column_extent.plan(plans)

    builds, clashes = [], []
    for index, region in enumerate(regions):
        sections = report.build_column_sections(region.records, None, None,
                                                texts=None, tolerances={})
        report.drop_nested_columns(sections)
        rects, drawn = [], []
        for entry in sections.get("entries") or []:
            for rect in entry.get("rectangles") or []:
                rects.append(rect)
                drawn.append(entry.get("layer") or "")
        keys = [column_extent.assign(columns, rect["center"],
                                     (rect["width_mm"], rect["height_mm"]))
                for rect in rects]
        rows = [(rects[at]["center"], drawn[at],
                 (rects[at]["width_mm"], rects[at]["height_mm"]))
                for at in range(len(rects))]
        built, _skipped = column_extent.plan_storey(
            keys, spans, index, rows=rows, storeys=len(regions))
        boxes = []
        for position in built:
            rect = rects[position]
            cx = rect["center"][0] * 304.8
            cy = rect["center"][1] * 304.8
            half_w = rect["width_mm"] / 2.0
            half_h = rect["height_mm"] / 2.0
            boxes.append((cx - half_w, cy - half_h, cx + half_w, cy + half_h))
        builds.append(len(boxes))
        clashes.append(_clashing_pairs(boxes))
    return {
        "storeys": len(regions),
        "outlines": sum(len(plan) for plan in plans),
        "columns": len(columns),
        "runs": len(spans),
        "builds_per_storey": builds,
        "clashing_pairs_per_storey": clashes,
    }


def _clashing_pairs(boxes):
    """How many pairs stand more than a third inside each other.

    The share is of the SMALLER box, the same reading `_SAME_PLACE_SHARE` is
    measured against, because the members that do this share a face line rather
    than a centre and one is often much the smaller.
    """
    pairs = 0
    for first in range(len(boxes)):
        for second in range(first + 1, len(boxes)):
            if column_extent._shared_share(boxes[first], boxes[second]) > 1.0 / 3.0:
                pairs += 1
    return pairs


class Storeys(unittest.TestCase):
    def test_every_storey_of_every_stack_produces_what_it_used_to(self):
        corpus = _multi_storey_corpus()
        self.assertTrue(corpus, "no multi-storey exports found")

        current = dict((drawing, _measure(corpus[drawing]))
                       for drawing in sorted(corpus))

        path = _golden.baseline_path(_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} stacks) -- rerun to check "
                          "against it".format(_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the storey replay moved:\n  " +
                         "\n  ".join(moved))

    def test_every_stack_builds_its_columns_on_the_storeys_it_used_to(self):
        names = _column_stacks()
        self.assertTrue(names, "no fixture DXFs found under fixtures/cad")

        current = {}
        for name in names:
            measured = _measure_column_extents(os.path.join(_CAD, name))
            if measured["storeys"] > 1:
                current[name] = measured
        self.assertTrue(current, "no fixture DXF split into a stack")

        path = _golden.baseline_path(_COLUMN_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} stacks) -- rerun to check "
                          "against it".format(_COLUMN_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the column extents moved:\n  " +
                         "\n  ".join(moved))


if __name__ == "__main__":
    unittest.main()
