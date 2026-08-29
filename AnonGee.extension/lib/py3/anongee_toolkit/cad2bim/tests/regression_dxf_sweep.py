# -*- coding: utf-8 -*-
"""Regression leg 2 of 3: the whole DXF corpus through the whole offline pipeline.

Every fixture DXF is read, classified, and run through column sectioning, beam
segmentation and both slab-outline sources. The counts are compared against
`baselines/dxf_sweep.json`. Any number that moves stops the run and is named.

This is the leg that catches what unit tests cannot: a change that is correct on
the case it was written for and wrong on the other sixteen drawings. It is the
rebuilt `scratchpad/sweep67.py`, which was never committed and is gone -- so the
numbers here are NOT the v0.67.3 baseline it held. They were re-measured at
v0.68.1, the release the user confirmed against Revit. The value is drift from
here on, not continuity with a baseline nobody can produce any more.

SLOW -- about a minute, most of it in ezdxf parsing Test4/Test5/Test10. That is
why this file is `regression_*` and not `test_*`: the everyday unit suite stays
under a second, and this runs as a release gate.

    cd cad2bim/tests
    python3 -m unittest discover -p "regression_*.py"     # all three legs
    python3 -m unittest regression_dxf_sweep              # just this one
    CAD2BIM_BLESS=1 python3 -m unittest regression_dxf_sweep   # re-record

Needs ezdxf. On Linux `pip install ezdxf` -- the bundled lib/py3 copy is a
Windows build and will not import (see the skip message).
"""

import os
import unittest

import _golden
import _loader


(report, layers, marks, dxf_reader, slab_outlines, slab_stops,
 foundation_plan, fold_plan, legend, wall_plan) = _loader.load(
    "report", "classify.layers", "classify.marks", "readers.dxf_reader",
    "slab_outlines", "slab_stops", "foundation_plan", "fold_plan", "legend",
    "wall_plan")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CAD = os.path.join(_HERE, "fixtures", "cad")
_FT = 1.0 / 304.8
_BASELINE = "dxf_sweep"


def _fixtures():
    """Every fixture DXF, by name, in a fixed order.

    Discovered rather than listed: a DXF added to the corpus should show up as a
    new fixture in the baseline diff, not be silently ignored because nobody
    remembered to add it to a list here.
    """
    if not os.path.isdir(_CAD):
        return []
    return sorted(name for name in os.listdir(_CAD)
                  if name.lower().endswith(".dxf"))


def _measure(path):
    """The fingerprint of one drawing: what the pipeline found in it.

    Counts, not geometry. A count moving is the signal -- WHICH rectangle moved
    is a question for the debugger, and storing every ring would make the
    baseline unreadable and its diffs useless.
    """
    result = dxf_reader.read_dxf(path)
    for record in result.records:
        record.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in record.points]
    # The hatches are scaled with everything else. Leaving them in millimetres
    # while the outlines are in feet puts every region a thousand-fold away from
    # the drawing, so each one lands inside no outline and the whole step pass
    # silently measures zero -- which is exactly how this line came to be added.
    for region in result.regions:
        region.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in region.points]
    layers.apply_mapping(
        result.records,
        layers.build_default_mapping([r.layer_key for r in result.records]))
    for text in result.texts:
        text.point_internal = (text.point[0] * _FT, text.point[1] * _FT, 0.0)
    marks.parse_texts(result.texts)

    sections = report.build_column_sections(result.records, texts=result.texts,
                                            tolerances={})
    entries = sections.get("entries") or []
    footprints = report.column_trim_footprints(sections)
    segments = report.build_beam_segments(result.records, [], None, None,
                                          texts=result.texts, tolerances={},
                                          schedule=None)
    split = report.split_beams_at_columns(segments, sections,
                                          sections.get("circles"))
    beams = segments.get("segments") or []

    # The slab chain EXACTLY as run_builders._create_slabs runs it: drawn edges
    # first, the placed-member faces when there are none, then the bays a
    # thickness note claims that no outline covered, then the labels. This is
    # the half the export replay cannot reach -- an export stores parsed marks,
    # not the text they were parsed from, so only a DXF can drive it.
    edges = slab_outlines.slab_loops_from_edges(result.records)
    loops = edges
    source = "slab_edges"
    if not loops:
        loops = slab_outlines.slab_loops_from_placed_members(
            result.records, beams, column_rects=footprints)
        source = "placed_members"
    recovered = slab_outlines.loops_for_unclaimed_notes(
        loops, result.records, beams, result.texts, column_rects=footprints)
    if recovered:
        loops = list(loops) + list(recovered)
    labelled = slab_outlines.apply_slab_labels(loops, result.texts)

    # FOUNDATIONS, read the way run_builders reads them: the outlines off the
    # foundation layer, sized by the notes routed off the foundation TEXT layer.
    # Two drawings reach this at all -- test10, which carries the convention,
    # and Test0, whose S-FNDN linework closes into faces that nothing labels and
    # which must therefore plan nothing.
    foundation_texts = [t for t in result.texts
                        if layers.classify_text_layer(t.layer_key)
                        == layers.CATEGORY_FOUNDATION_TEXT]
    foundation_outlines = foundation_plan.outlines(result.records)
    # The crossed-out faces: X-marked parts the raft is cast AROUND rather
    # than over. test10 measures 2 -- the corridor's north and south parts.
    foundation_cutouts = foundation_plan.cutouts(result.records)
    foundation_plans = foundation_plan.plan_foundations(result.records,
                                                        foundation_texts)
    regions = _regions_by_category(result.regions)
    # THE LEGEND, read the way the pushbutton reads it before the dialog:
    # swatch pattern -> legend text -> meaning, translated into per-layer
    # proposals. Two fixtures carry one. test9 has 14 rows across three tower
    # legends, and its ambiguity (the same pattern meaning different things
    # per tower) plus the one-layer rule leave exactly ONE proposal standing
    # (ASPHALT -> cutout on PI_SHEAR WALL CUTOUT). test14 has 8 rows drawn
    # three times, agreeing, and leaves one too (HAT -> sunk) plus the three
    # SUNK depths -- which is the number `legend_steps` pins: a row read but
    # stripped of its depth would still show 24 entries and 1 proposal.
    legend_entries = legend.read(result.regions, result.texts)
    legend_proposals = legend.propose(legend_entries, result.regions)
    legend_depths, _legend_depth_notes = legend.legend_steps(legend_entries)
    # FOLDS AND SUNK BAYS. The hatches are classified the way the pipeline
    # classifies them -- through the HATCH mapping's own default, apart from
    # geometry and text -- then stepped against the outlines they sit in.
    # test10 is the case: six folds inside two F3 rafts, and one sunk strip
    # that IS its own F6 outline and therefore needs no support at all.
    layers.apply_mapping(
        result.regions,
        layers.build_default_hatch_mapping(
            [r.layer_key for r in result.regions]))
    steps = fold_plan.plan_steps(foundation_plans, result.regions)
    # WALLS, planned the way the wall pass reads them: the two wall
    # categories only, outlines and face pairs, refusals counted. Three
    # drawings carry wall layers (Project1, test8, test9); every other row
    # measures zeros, which is itself the pin that nothing else leaks in.
    walls = wall_plan.plan_walls(result.records, texts=result.texts)
    # The PROFILES the builder would hand Floor.Create, assembled the same
    # way: step openings and nested outlines as holes, then split wherever an
    # opening reaches its outline's boundary. The corridor block is the case:
    # profile-split is what turned its rejected hole into two placed pieces.
    openings, drops = {}, set()
    for step in steps["steps"]:
        if step["opening"] is None:
            drops.add(step["host_index"])
        else:
            openings.setdefault(step["host_index"], []).append(step["opening"])
    profile_count = 0
    outlines_divided = 0
    for index, plan in enumerate(foundation_plans):
        if index in drops or not plan.get("ring"):
            continue
        holes = list(plan.get("holes") or []) + openings.get(index, [])
        pieces = fold_plan.split_profile(plan["ring"], holes)
        profile_count += len(pieces)
        if len(pieces) > 1:
            outlines_divided += 1

    sunk = _sunk_pass(result, legend_entries, legend_proposals, legend_depths,
                      labelled, beams)
    stops = _stops_pass(result, legend_entries, legend_depths, labelled, beams)

    return {
        "records": len(result.records),
        "texts": len(result.texts),
        "column_entries": len(entries),
        "column_rectangles": sum(len(e.get("rectangles") or []) for e in entries),
        "column_circles": len(sections.get("circles") or []),
        "column_footprints": len(footprints),
        "marked_rectangles": sum(
            1 for e in entries for r in (e.get("rectangles") or [])
            if r.get("mark")),
        "beams": len(beams),
        "beams_split_at_columns": int(split or 0),
        "marked_beams": sum(1 for b in beams if b.get("mark")),
        "sized_beams": sum(1 for b in beams if b.get("depth_mm")),
        "slab_source": source,
        "slab_loops_from_edges": len(edges),
        "slab_loops_from_beam_graph": len(
            slab_outlines.slab_loops_from_beam_graph(beams)),
        "slab_loops_recovered_from_notes": len(recovered or []),
        "slab_loops_total": len(labelled),
        "slab_loops_marked": sum(1 for s in labelled if s.get("mark")),
        "slab_loops_sized": sum(1 for s in labelled
                                if s.get("thickness_mm") is not None),
        "foundation_records": sum(
            1 for r in result.records
            if r.category == layers.CATEGORY_FOUNDATION),
        "foundation_outlines": len(foundation_outlines),
        "foundation_outlines_drawn_closed": sum(
            1 for _r, _z, source in foundation_outlines if source == "drawn"),
        "foundation_cutouts": len(foundation_cutouts),
        "foundation_texts": len(foundation_texts),
        "foundation_planned": len(foundation_plans),
        "foundation_planned_sized": sum(
            1 for p in foundation_plans if p.get("thickness_mm") is not None),
        "foundation_steps": sum(len(p.get("steps") or [])
                                for p in foundation_plans),
        "regions": len(result.regions),
        "fold_regions": regions.get(layers.CATEGORY_FOLD, 0),
        "sunk_regions": regions.get(layers.CATEGORY_SUNK, 0),
        "legend_entries": len(legend_entries),
        "legend_proposals": len(legend_proposals["mapping"]),
        "legend_reports": len(legend_proposals["reports"]),
        "legend_steps": len(legend_depths),
        "legend_step_depth_mm_total": round(sum(legend_depths.values()), 1),
        "steps_planned": len(steps["steps"]),
        "steps_skipped": len(steps["skipped"]),
        "step_supports": sum(len(s["supports"]) for s in steps["steps"]),
        "step_openings": sum(1 for s in steps["steps"]
                             if s["opening"] is not None),
        "step_depth_mm_total": round(sum(s["depth_mm"] for s in steps["steps"]), 1),
        "foundation_profiles": profile_count,
        "foundation_outlines_divided": outlines_divided,
        "sunk_bays": sunk["bays"],
        "sunk_strips": sunk["strips"],
        "sunk_unpriced_patterns": sunk["unpriced"],
        "sunk_slab_steps": sunk["steps"],
        "sunk_slab_step_supports": sunk["supports"],
        "sunk_slab_steps_skipped": sunk["steps_skipped"],
        "sunk_slab_step_depth_mm_total": sunk["depth_total"],
        "sunk_slab_defs": sunk["defs"],
        "sunk_beams_dropped": sunk["dropped"],
        "sunk_beam_drop_mm_total": sunk["drop_total"],
        "sunk_strips_on_no_beam": sunk["strips_skipped"],
        "sunk_dropped_area_m2": sunk["dropped_area_m2"],
        "sunk_slab_step_notes": sunk["notes"],
        "slab_stop_records": sum(
            1 for r in result.records
            if r.category == layers.CATEGORY_SLAB_STOP),
        "slab_stop_rings": stops["rings"],
        "slab_cutouts_crossed": stops["crossed"],
        "slab_cutout_holes": stops["holes"],
        "slab_bays_divided_by_cutouts": stops["divided"],
        "stair_bays_withdrawn": stops["stair_bays"],
        "stair_area_m2": stops["stair_area_m2"],
        "cutout_bays_withdrawn": stops["cutout_bays"],
        "cutout_bay_area_m2": stops["cutout_bay_area_m2"],
        "chajjas": stops["chajjas"],
        "chajja_offset_mm_total": stops["chajja_offset_total"],
        "slab_stop_notes": stops["notes"],
        "slab_defs_built": stops["built"],
        "wall_records": sum(
            1 for r in result.records
            if r.category in (layers.CATEGORY_STRUCT_WALL,
                              layers.CATEGORY_ARCH_WALL)),
        "wall_segments": len(walls["segments"]),
        "wall_struct_segments": sum(1 for s in walls["segments"]
                                    if s["kind"] == "structural"),
        "wall_arch_segments": sum(1 for s in walls["segments"]
                                  if s["kind"] == "arch"),
        "wall_skipped": len(walls["skipped"]),
        "wall_length_m": round(sum(s["length_mm"]
                                   for s in walls["segments"]) / 1000.0, 1),
    }


def _sunk_pass(result, entries, proposals, depths, slab_defs, beams):
    """What the legend's SUNK depths would build, the way the run builds it.

    The hatch routing the dialog carries is the name convention with the
    LEGEND'S proposal laid over it -- that is how the pushbutton seeds the
    window -- so the mapping is rebuilt here that way before anything is
    split. Only then does the pattern price each hatch: test14's one routed
    layer holds three sunk depths and a fourth meaning that is no step at all.

    Applied AFTER the foundation step measurement above, deliberately: that one
    pins what the name convention alone routes, and re-categorising the regions
    first would quietly change the number it reports.
    """
    mapping = layers.build_default_hatch_mapping(
        [region.layer_key for region in result.regions])
    mapping.update(proposals["mapping"])
    layers.apply_mapping(result.regions, mapping)
    swatch_ids = set(id(entry["swatch"]) for entry in entries)
    split = fold_plan.sunk_split(result.regions, depths, swatch_ids)
    drops = fold_plan.beam_drops(beams, split["strips"])
    steps = fold_plan.sunk_bay_steps(slab_defs, split["bays"])
    defs, _notes = fold_plan.slab_defs_with_steps(slab_defs, steps["steps"])
    return {
        "bays": len(split["bays"]),
        "strips": len(split["strips"]),
        "unpriced": len(split["skipped"]),
        "steps": len(steps["steps"]),
        "supports": sum(len(s["supports"]) for s in steps["steps"]),
        "steps_skipped": len(steps["skipped"]),
        "depth_total": round(sum(s["depth_mm"] for s in steps["steps"]), 1),
        "defs": len(defs),
        "dropped": len(drops["drops"]),
        "drop_total": round(sum(drops["drops"].values()), 1),
        "strips_skipped": len(drops["skipped"]),
        # THE GEOMETRY IS THE BAY'S, NOT THE HATCH'S, and this is the number
        # that says so: the concrete the sunk pass actually lays. It is the one
        # metric a hatch outline creeping back in would move, where the counts
        # would not -- test14's hatches are within 14% of their bays by area on
        # the median, so only the total tells them apart.
        "dropped_area_m2": round(sum(fold_plan.area_m2(s["dropped"]["ring"])
                                     for s in steps["steps"]), 1),
        "notes": len(steps["notes"]),
    }


def _stops_pass(result, entries, depths, slab_defs, beams):
    """What the SLAB-STOP pass makes of the drawing, and what the run builds.

    Measured on the same `slab_defs` the sunk pass above is measured on, so the
    two halves are pinned apart and a number that moves says which half moved.
    `built` is the one number that pins the CHAIN the pushbutton runs -- stops
    first, then the steps against what survives -- because the order is a
    decision in its own right (a hole cut into a bay a staircase then withdraws
    is work thrown away, and the console would have reported it).

    The regions arrive already re-categorised by `_sunk_pass`, which is the
    routing the run uses; nothing here re-maps them.
    """
    swatch_ids = set(id(entry["swatch"]) for entry in (entries or []))
    stopped, report = slab_outlines.apply_slab_stops(
        slab_defs, result.records, result.texts, regions=result.regions,
        beam_segments=beams, legend_entries=entries, skip_ids=swatch_ids)
    split = fold_plan.sunk_split(result.regions, depths, swatch_ids)
    steps = fold_plan.sunk_bay_steps(stopped, split["bays"])
    built, _notes = fold_plan.slab_defs_with_steps(stopped, steps["steps"])
    return {
        "rings": len(slab_stops.slab_stop_rings(result.records)),
        "crossed": report["crossed"],
        "holes": report["holes"],
        "divided": report["divided"],
        "stair_bays": report["stair_bays"],
        "stair_area_m2": report["stair_area_m2"],
        "cutout_bays": report["cutout_bays"],
        "cutout_bay_area_m2": report["cutout_bay_area_m2"],
        "chajjas": report["chajjas"],
        "chajja_offset_total": round(sum(
            d["offset_mm"] for d in stopped if d.get("part") == "chajja"), 1),
        "notes": len(report["notes"]),
        "built": len(built),
    }


def _regions_by_category(regions):
    """{category: count} for the hatches the reader kept out of `records`.

    Classified through the HATCH convention (classify_hatch_layer), the way
    the pipeline now routes regions -- hatches map on their own table, apart
    from geometry and text.
    """
    counts = {}
    for region in (regions or []):
        category = layers.classify_hatch_layer(region.layer_key)
        counts[category] = counts.get(category, 0) + 1
    return counts


class DxfSweep(unittest.TestCase):
    def test_every_fixture_dxf_produces_the_numbers_it_used_to(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf` "
                          "(the bundled lib/py3 copy is a Windows build)")
        names = _fixtures()
        self.assertTrue(names, "no fixture DXFs found under fixtures/cad")

        current = {}
        for name in names:
            current[name] = _measure(os.path.join(_CAD, name))

        path = _golden.baseline_path(_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} fixtures) -- rerun to "
                          "check against it".format(_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the DXF sweep moved:\n  " +
                         "\n  ".join(moved))


if __name__ == "__main__":
    unittest.main()
