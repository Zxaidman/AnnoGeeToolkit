# -*- coding: utf-8 -*-
"""One function per element kind: take what the readers derived, build it.

Each of these opens its own transaction group, hands the derived geometry to the
matching builder, and comes back with an OUTCOME dict -- created, skipped,
errors, plus the detail the console and the JSON export need. They are the only
place in the run that writes to the model, and they are deliberately uniform:
one kind, one transaction, one outcome, so a failure in slabs cannot leave beams
half-built.

Two conventions matter here:

  * `_IDS` -- the created ElementIds ride along inside the outcome so the
    material pass can reach them, under a PRIVATE key that `_strip_ids` removes
    before anything is written to JSON. An ElementId is not serialisable, and
    letting one reach json.dump once killed a completed run's export.
  * `_skip_details` -- skips are grouped by REASON with the numbers masked, so
    a console line reads "42 x beam shorter than the minimum" instead of
    forty-two nearly identical sentences.

Must run on the Revit API thread, after the modal window has closed.
"""

from Autodesk.Revit.DB import Transaction, TransactionGroup

import re

from . import (config, fold_plan, foundation_plan, legend, naming, report,
               slab_outlines, wall_plan)
from .builders import (columns, beams, footings, grids, materials, slabs,
                       txn_failures, view_filters, walls)
from . import stair_layout
from .classify import layers
from .builders import stairs
from .run_picking import _pick_stair_regions
from .run_console import _say, _say_error, _progress
from .ui_dialogs import _alert, _error, _persisted, _rollback_alert


# The created ElementIds ride along inside `outcomes` for the material pass, but
# outcomes are JSON-exported and an ElementId is not serialisable -- so they go
# under a key that _strip_ids() removes before anything is written.
_IDS = "_element_ids"


_SKIP_DETAIL_KINDS = 12       # distinct reasons kept; the rest are counted


def _strip_ids(outcomes):
    """A copy of `outcomes` with the live ElementId lists taken out."""
    clean = {}
    for key, value in (outcomes or {}).items():
        if isinstance(value, dict):
            clean[key] = dict((k, v) for k, v in value.items() if k != _IDS)
        else:
            clean[key] = value
    return clean


def _skip_details(messages):
    """Skip reasons for the export, GROUPED so a thousand identical ones fit.

    A run that skips 900 members skips them for a handful of reasons; listing
    the first eight verbatim hides the rest, so each distinct reason is kept
    once with its count and one example. Numbers and marks are masked out when
    grouping, so "C12: no symbol" and "C13: no symbol" are one reason.
    """
    groups = {}
    order = []
    for message in messages or []:
        text = str(message)
        key = re.sub(r"\d+(?:\.\d+)?", "#", text)
        if key not in groups:
            groups[key] = {"reason": text[:220], "count": 0}
            order.append(key)
        groups[key]["count"] += 1
    out = [groups[key] for key in order[:_SKIP_DETAIL_KINDS]]
    hidden = sum(groups[key]["count"] for key in order[_SKIP_DETAIL_KINDS:])
    if hidden:
        out.append({"reason": "(and other reasons)", "count": hidden})
    return out


def blanket_mm(selections, key):
    """The blanket-note figure the dialog settled on, in the planners' tri-state.

    `build_beam_segments` and `apply_slab_labels` both read one number:

        None  -- nobody settled it, so read the sheet's own U.N.O. note
        > 0   -- this figure, whatever the sheet says (the user typed it, or
                 the dialog seeded it from the sheet's proposal)
        0     -- no blanket default at all (the tick is off)

    The dialog cannot send None -- an empty box reads as 0 -- so an empty box
    with the tick ON becomes None here, which hands the question back to the
    sheet. That matters for the case the dialog leaves empty ON PURPOSE: a sheet
    whose notes disagree seeds nothing, and the planners must then refuse it
    again rather than inherit a stale figure from somewhere else.
    """
    selections = selections or {}
    if not selections.get("blanket_notes", True):
        return 0.0
    return selections.get(key) or None


def _sunk_depths(selections, regions, texts):
    """({pattern: depth_mm}, {swatch id}, [notes]) -- how deep each hatch sinks.

    THE DIALOG'S HATCH TABLE IS THE AUTHORITY. It is the user's own editable
    view of what the legend proposed, so a figure they corrected there must
    beat the drawing. When there is no table -- an older preset, a run whose
    dialog never offered one -- the legend is read again here, so this pass
    works whether or not the dialog half of it is in place.

    Either way the legend is read for its SWATCHES. The demonstration
    rectangles beside each legend line are hatches like every other one, on the
    routed layer and carrying the routed pattern, and nothing may build a floor
    or drop a beam out of one.
    """
    notes = []
    entries = legend.read(regions or [], texts or [])
    swatch_ids = set(id(entry["swatch"]) for entry in entries)
    table = selections.get("hatch_step_depths")
    if table:
        return dict(table), swatch_ids, notes
    depths, legend_notes = legend.legend_steps(
        entries,
        max_step_mm=(selections.get("tolerances") or {}).get("max_step_mm"))
    notes.extend(legend_notes)
    if depths:
        notes.append(
            "depths read from the drawing's own legend ({0}): {1}".format(
                len(entries),
                ", ".join("{0} {1:+.0f}mm".format(pattern, depths[pattern])
                          for pattern in sorted(depths))))
    return depths, swatch_ids, notes


def _tally(values):
    """{value: count} -- so a console line reads "150mm x31", not x31 lines."""
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _sunk_beam_drops(selections, regions, texts, segments):
    """{segment index: depth_mm} for the beams a sunk strip covers.

    Nothing here is silent. Refusals come back from `sunk_split` (a pattern the
    legend prices at nothing) and from `beam_drops` (a strip lying on no
    member), and both are said before a single beam is placed -- a strip the
    run ignored is a beam sitting a step too high, and that is invisible in
    plan.
    """
    if not regions:
        return {}
    depths, swatch_ids, notes = _sunk_depths(selections, regions, texts)
    for message in notes:
        _say("  sunk (beams): {0}".format(message))
    if not depths:
        _say("  sunk (beams): no hatch depth is known, from the dialog or the "
             "legend: no beam is dropped")
        return {}
    split = fold_plan.sunk_split(regions, depths, swatch_ids)
    drops = fold_plan.beam_drops(segments, split["strips"])
    for message in split["skipped"] + drops["skipped"]:
        _say("  sunk (beams): {0}".format(message))
    return drops["drops"]


def _slab_stops(slab_defs, records, texts, regions, sheet_texts, beam_segments,
                selections, schedule):
    """(slab_defs, [step]) -- what the drawing says STOPS each bay, applied.

    Three readings, all of them the drawing's own marks and all of them
    invisible to a beam graph: a crossed-out ring on the slab-stop layer is a
    HOLE, a bay a staircase stands in is NOT a floor, and a beam-bottom hatch
    is a CHAJJA at its own level. `slab_outlines.apply_slab_stops` does the
    work; this says what happened, grouped, before anything is placed -- a
    hole nobody cut and a stair cast solid both look built and are wrong.
    """
    entries = legend.read(regions or [], sheet_texts or texts or [])
    defs, stopped = slab_outlines.apply_slab_stops(
        slab_defs, records, texts, regions=regions,
        beam_segments=beam_segments, legend_entries=entries,
        skip_ids=set(id(entry["swatch"]) for entry in entries),
        schedule=schedule,
        blanket_thickness_mm=blanket_mm(selections,
                                        "blanket_slab_thickness_mm"))
    if stopped["crossed"]:
        _say("  stops: {0} crossed-out ring(s) read, {1} cut as holes in "
             "{2} bay(s)".format(stopped["crossed"], stopped["holes"],
                                 stopped["holes"] - stopped["divided"]
                                 if stopped["divided"] else stopped["holes"]))
    if stopped["stair_bays"]:
        _say("  stops: {0} staircase bay(s) withdrawn, {1:.1f} m2 of floor the "
             "stair occupies".format(stopped["stair_bays"],
                                     stopped["stair_area_m2"]))
    if stopped["chajjas"]:
        _say("  stops: {0} chajja(s) placed at beam bottom".format(
            stopped["chajjas"]))
    for message in stopped["notes"]:
        _say("  stops: {0}".format(message))
    return defs, stopped


def _sunk_slab_steps(selections, regions, texts, slab_defs,
                     beam_segments=None):
    """(slab_defs with their steps built in, [step]) for the hatched sunk bays.

    The same three-floor arithmetic the footings use, against slab loops
    instead of foundation outlines -- which is what `fold_plan.plan_steps`
    docstring always claimed it could serve, and this is the pass that asks it
    to. Depths come from the PATTERN, so the one routed layer's three sunk
    values stay apart and the meaning on it that is no step at all is refused
    by name.

    `beam_segments` are handed on so a dropped slab STOPS at the beam faces
    the hatch was drawn across -- the sunk beam drops with the slab, it does
    not get a floor cast over it.

    Every refusal is said before anything is placed: a bay that stepped
    nowhere is a floor left flat, which the model shows as correct.
    """
    if not regions:
        return slab_defs, []
    depths, swatch_ids, notes = _sunk_depths(selections, regions, texts)
    for message in notes:
        _say("  sunk (slabs): {0}".format(message))
    if not depths:
        _say("  sunk (slabs): no hatch depth is known, from the dialog or the "
             "legend: no bay is stepped")
        return slab_defs, []
    split = fold_plan.sunk_split(regions, depths, swatch_ids)
    steps = fold_plan.plan_steps(
        slab_defs, split["bays"], depths=depths, skip_ids=swatch_ids,
        max_step_mm=(selections.get("tolerances") or {}).get("max_step_mm"),
        beams=beam_segments)
    stepped, cut = fold_plan.slab_defs_with_steps(slab_defs, steps["steps"])
    for message in split["skipped"] + steps["skipped"] + steps["notes"] + cut:
        _say("  sunk (slabs): {0}".format(message))
    return stepped, steps["steps"]


def _create_grids(doc, records, grid_texts=None):
    """Create grids from classified grid lines, inside a transaction group.

    Names come from grid-text labels (e.g. DWG bubbles 'A','1') when available,
    falling back to the A-Z x 1-9 convention. All Revit writes happen here on the
    API thread after the window closes; both transaction and group roll back on
    any failure.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    grid_records = [r for r in records
                    if r.category == layers.CATEGORY_GRID and r.kind in ("line", "arc")]
    if not grid_records:
        _say("Grids -- no grid-category lines to create.")
        return {"created": 0, "skipped": 0, "errors": 0}

    namer = grids.build_grid_namer(grid_records, grid_texts)
    group = TransactionGroup(doc, "CAD to BIM: Grids")
    transaction = Transaction(doc, "Create grids")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = grids.create_grids(doc, grid_records, namer)
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Grid creation failed", "Grid creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Grids", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Grids -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"]:
        _say_error("  grid: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]),
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"])}


def _create_columns(doc, sections, selections):
    """Place rectangular + circular columns from the decomposed sections, in a group."""
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    family_id = selections.get("column_family_id")
    base_id = selections.get("base_level_id")
    top_id = selections.get("top_level_id")
    if family_id is None or base_id is None or top_id is None:
        _alert("Columns skipped", "Choose a column family and base/top levels.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}
    if not sections.get("entries"):
        _say("Columns -- no column sections to place.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Columns")
    transaction = Transaction(doc, "Create columns")
    region_max = (selections.get("tolerances") or {}).get("col_region_max_side_mm")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = columns.place_columns(doc, sections, family_id, base_id, top_id,
                                       region_max_side_mm=region_max)
        circles = sections.get("circles", [])
        circular_id = selections.get("circular_family_id")
        circular = {"created": [], "errors": []}
        if circles and circular_id is not None:
            circular = columns.place_circular_columns(
                doc, circles, circular_id, base_id, top_id)
        elif circles:
            _say("  circular columns skipped: no circular family selected")
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Column creation failed", "Column creation failed.", str(creation_error))
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Columns", tstatus, gstatus)
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Columns -- rect created: {0}, circular: {1}, skipped: {2}, errors: {3}".format(
        len(result["created"]), len(circular["created"]),
        len(result["skipped"]), len(result["errors"]) + len(circular["errors"])))
    for message in result["errors"] + circular["errors"]:
        _say_error("  column: {0}".format(message))
    for message in (result["skipped"] + result.get("notes", [])
                    + circular.get("notes", [])):
        _say("  column: {0}".format(message))
    return {"rect": len(result["created"]), "circular": len(circular["created"]),
            _IDS: result["created"] + circular["created"],
            "skipped": len(result["skipped"]),
            "errors": len(result["errors"]) + len(circular["errors"]),
            "error_details": [str(e)[:220] for e
                              in (result["errors"] + circular["errors"])[:8]],
            "skip_details": _skip_details(result["skipped"]
                                          + circular.get("skipped", []))}


def _create_beams(doc, beam_segments, selections, regions=None, texts=None):
    """Place beams along derived centerlines at the columns' top level, in a group.

    `regions` are the storey's hatches and `texts` the sheet's own, together
    the sunk half: a hatched strip no wider than a beam, lying on that beam,
    means the whole member hangs lower by the legend's depth -- same section,
    same length, top and soffit down together. Every strip that lands on no
    beam is named rather than dropped quietly.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    beam_id = selections.get("beam_family_id")
    level_id = selections.get("top_level_id")
    if beam_id is None or level_id is None:
        _alert("Beams skipped", "Choose a beam family and a top level.")
        return {"created": 0, "skipped": 0, "errors": 0}
    segments = beam_segments.get("segments", [])
    curved = beam_segments.get("curved_segments", [])
    if not segments and not curved:
        _say("Beams -- no beam segments to place.")
        return {"created": 0, "skipped": 0, "errors": 0}

    drops = _sunk_beam_drops(selections, regions, texts, segments)

    group = TransactionGroup(doc, "CAD to BIM: Beams")
    transaction = Transaction(doc, "Create beams")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = beams.place_beams(doc, segments, beam_id, level_id, drops=drops)
        # Curved beams (concentric arc pairs, e.g. a curved perimeter member) are placed
        # along an Arc; fold their outcome into the same result tallies.
        curved_result = beams.place_curved_beams(doc, curved, beam_id, level_id)
        for key in ("created", "skipped", "errors"):
            result[key] = result[key] + curved_result[key]
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Beam creation failed", "Beam creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Beams", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Beams -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    if drops:
        _say("Beams -- {0} of {1} dropped by a sunk strip ({2}), depth "
             "unchanged.".format(
                 len(drops), len(segments),
                 ", ".join("{0:.0f}mm x{1}".format(depth, count) for depth,
                           count in sorted(_tally(drops.values()).items()))))
    for message in result["errors"]:
        _say_error("  beam: {0}".format(message))
    for message in result["skipped"] + result.get("notes", []):
        _say("  beam: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]),
            "dropped_by_sunk": len(drops),
            # the placed instances (straight and curved -- the curved tallies
            # were folded in above), so the material pass can reach them:
            # without this the beams outcome carried counts only and every run
            # reported "nothing of this kind was built"
            _IDS: result["created"],
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"])}


def _create_footings(doc, sections, selections, records=None, texts=None,
                     regions=None):
    """The foundations, on the columns' BASE level.

    `records` and `texts` are this storey's geometry and its routed foundation
    notes. When they carry the foundation convention the outlines come from the
    drawing; when they do not, the pass derives pads from the columns exactly as
    it always has.

    `regions` are the storey's hatches. A fold or sunk hatch inside an outline
    steps it: the outline is cut, a dropped slab goes in at the step depth, and
    the vertical face between the two soffits is filled.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup
    type_id = selections.get("footing_symbol_id")
    level_id = selections.get("base_level_id")
    if type_id is None or level_id is None:
        _say("Footings -- no foundation type or base level chosen.")
        return {"created": 0, "skipped": 0, "errors": 0}

    # The regions ride along so a hatch the dialog routed to "cutout" (the
    # legend proposal, or a hand pick) holes the plan containing it -- the
    # region-category cousin of the X-marked faces.
    outlines = foundation_plan.plan_foundations(records or [], texts or [],
                                                regions=regions or [])
    if outlines:
        _say("Footings -- {0} outline(s) read from the drawing; the "
             "column-offset derivation is not used.".format(len(outlines)))
    steps = fold_plan.plan_steps(
        outlines, regions or [],
        max_step_mm=(selections.get("tolerances") or {}).get("max_step_mm"))
    for message in steps["skipped"]:
        _say("  step: {0}".format(message))
    if steps["steps"]:
        _say("Footings -- {0} fold/sunk step(s): {1} support(s) between the "
             "soffits.".format(len(steps["steps"]),
                               sum(len(s["supports"]) for s in steps["steps"])))

    group = TransactionGroup(doc, "CAD to BIM: Footings")
    transaction = Transaction(doc, "Create footings")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = footings.place_footings(
            doc, sections, type_id, level_id,
            projection_mm=selections.get("footing_projection_mm") or 0.0,
            thickness_mm=selections.get("footing_thickness_mm") or 0.0,
            # The dialog files this under TOLERANCES, which is where the column
            # pass reads it from; looking in "limits" always found nothing, so
            # the user's setting never reached the footings.
            region_max_side_mm=(selections.get("tolerances") or {}).get(
                "col_region_max_side_mm"),
            outlines=outlines, steps=steps["steps"])
        transaction.Commit()
        group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Footing creation failed", "Footing creation failed.",
               str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    _say("Footings -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"]:
        _say_error("  footing: {0}".format(message))
    for message in result["skipped"] + result.get("notes", []):
        _say("  footing: {0}".format(message))
    return {"created": len(result["created"]),
            "skipped": len(result["skipped"]),
            "errors": len(result["errors"]),
            _IDS: result["created"],
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"])}


def _create_walls(doc, records, selections):
    """The walls, from the centrelines the offline planner reads per storey.

    ONE planning pass feeds BOTH kinds: `wall_plan.plan_walls` is Revit-free,
    splits its segments into "structural" and "arch" by the layer routing, and
    reports everything it declines (door-cutout quads, end caps, faces with no
    partner), so the console can say why a drawn line built nothing. Each kind
    then places against its OWN base type -- a shear wall and a brick
    partition are different assemblies with different names.

    Where the drawing carries the SAME wall on both conventions (test8's 250
    S-RCC-WALL quad with a 150 arch trace 50 mm off its centreline, findings
    #12), both still build: which convention wins is a decision recorded in
    task_plan.md against the user's Revit run of this pass, not guessed here.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup
    want = {"structural": bool(selections.get("create_struct_walls")),
            "arch": bool(selections.get("create_arch_walls"))}
    type_ids = {"structural": selections.get("struct_wall_type_id"),
                "arch": selections.get("arch_wall_type_id")}
    base_id = selections.get("base_level_id")
    if base_id is None:
        _say("Walls -- skipped (no base level chosen).")
        return {"created": 0, "skipped": 0, "errors": 0}

    plan = wall_plan.plan_walls(records or [],
                                tolerances=selections.get("tolerances"))
    pools = {"structural": [], "arch": []}
    for segment in plan["segments"]:
        if segment["kind"] in pools:
            pools[segment["kind"]].append(segment)
    # the planner's refusals, grouped the way the export groups skips -- a
    # drawing with 27 doors declines 27 jamb pairs for one reason, not 27
    planner_skips = ["{0} [{1}]".format(entry.get("reason"),
                                        entry.get("layer"))
                     for entry in plan["skipped"]]
    for detail in _skip_details(planner_skips):
        _say("  wall: {0} x {1}".format(detail["count"], detail["reason"]))
    build = [(kind, pools[kind]) for kind in ("structural", "arch")
             if want[kind] and pools[kind]]
    if not build:
        _say("Walls -- no wall segments planned on the routed wall layers.")
        return {"created": 0, "skipped": len(plan["skipped"]), "errors": 0,
                "skip_details": _skip_details(planner_skips)}

    group = TransactionGroup(doc, "CAD to BIM: Walls")
    transaction = Transaction(doc, "Create walls")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = {"created": [], "skipped": [], "errors": [], "notes": []}
        for kind, segments in build:
            if type_ids[kind] is None:
                _say("  {0} walls skipped: no base wall type selected".format(
                    kind))
                continue
            outcome = walls.place_walls(
                doc, segments, type_ids[kind], base_id,
                top_level_id=selections.get("top_level_id"),
                height_mm=selections.get("storey_height_mm"),
                structural=(kind == "structural"))
            for key in ("created", "skipped", "errors", "notes"):
                result[key] = result[key] + outcome[key]
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Wall creation failed", "Wall creation failed.",
               str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Walls", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Walls -- planned: {0} structural + {1} arch, created: {2}, "
         "skipped: {3}, errors: {4}".format(
             len(pools["structural"]), len(pools["arch"]),
             len(result["created"]),
             len(result["skipped"]) + len(plan["skipped"]),
             len(result["errors"])))
    for message in result["errors"]:
        _say_error("  wall: {0}".format(message))
    for message in result["skipped"] + result.get("notes", []):
        _say("  wall: {0}".format(message))
    return {"created": len(result["created"]),
            "skipped": len(result["skipped"]) + len(plan["skipped"]),
            "errors": len(result["errors"]),
            _IDS: result["created"],
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"] + planner_skips)}


def _colour_open_views(doc, uidoc, selections):
    """Add the colour-coded cad2bim filters to every view the user has open."""
    if not selections.get("view_filters"):
        return
    from Autodesk.Revit.DB import Transaction
    views = view_filters.open_views(uidoc)
    if not views:
        _say("view filters: no open view to colour.")
        return
    transaction = Transaction(doc, "CAD to BIM: View filters")
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = view_filters.apply(
            doc, views,
            transparency=selections.get("filter_transparency") or 0,
            colour_lines=bool(selections.get("filter_colour_lines")))
        transaction.Commit()
    except Exception as filter_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        _say("view filters: not applied ({0})".format(str(filter_error)[:160]))
        return
    _say("view filters: {0} filter(s) on {1} open view(s)".format(
        result["filters"], result["views"]))
    for message in result["skipped"][:8]:
        _say("  filter: {0}".format(message))


def _apply_materials(doc, outcomes, selections):
    """Write the chosen material onto every type this storey created.

    Types, not instances: that is where Revit keeps a structural member's
    material, and every element of one size already shares a duplicated type.
    """
    wanted = dict((kind, material_id) for kind, material_id
                  in (selections.get("materials") or {}).items() if material_id)
    grades = dict((kind, text) for kind, text
                  in (selections.get("grades") or {}).items() if text)
    if not wanted and not grades:
        return None
    from Autodesk.Revit.DB import Transaction
    source = {"column": "columns", "beam": "beams", "slab": "slabs",
              "stair": "stairs", "footing": "footings"}
    transaction = Transaction(doc, "CAD to BIM: Materials")
    transaction.Start()
    summary = {}
    try:
        txn_failures.attach_warning_swallower(transaction)
        for kind in sorted(set(list(wanted) + list(grades))):
            material_id = wanted.get(kind)
            key = source.get(kind)
            ids = (outcomes.get(key) or {}).get(_IDS) if key else None
            elements = materials.elements_of(doc, ids)
            if elements and grades.get(kind):
                stamped, missed = materials.apply_grade(
                    doc, elements, grades[kind],
                    selections.get("grade_parameter"),
                    append_to_name=bool(selections.get("grade_in_mark")))
                _say("grade: {0} -- {1} of {2} element(s) stamped {3}".format(
                    kind, stamped, len(elements), grades[kind]))
                summary.setdefault(kind, {})["graded"] = stamped
                summary[kind]["grade_missed"] = missed
            if material_id is None:
                continue
            if not elements:
                # says WHY nothing happened: nothing built, or the ids were
                # lost -- both looked identical as a silent no-op before
                summary.setdefault(kind, {}).update(
                    {"elements": 0, "skipped": 0, "none_built": True})
                _say("material: {0} -- nothing of this kind was built in this "
                     "run".format(kind))
                continue
            applied, skipped = materials.apply(doc, elements, material_id, kind)
            summary.setdefault(kind, {}).update({"elements": applied,
                                                 "skipped": skipped})
            _say("material: {0} -- {1} of {2} element(s) set".format(
                kind, applied, len(elements)))
        transaction.Commit()
    except Exception as material_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        _say("material: not applied ({0})".format(str(material_error)[:160]))
        return None
    return summary


def _create_slabs(doc, records, beam_segments, texts, selections, schedule=None,
                  column_rects=None, regions=None, sheet_texts=None):
    """Place floor slabs after the beams, in a transaction group.

    Outline sources, in order: (1) closed rings on the slab-edge (A-FLOR) layer;
    (2) faces of the PLACED beam edge lines with the placed column footprints
    trimming the corners (exact boundary, re-derived onto the carrier lines).
    Thickness and mark come from slab notes ("S1 150 THK", "150 THK.") lying
    INSIDE the loop -- content-driven, any text layer -- and, for a bay no note
    reached, from the SHEET's blanket note ("ALL SALB ARE 125MM U.N.O."), which
    the dialog settled before the run. The floor type is the one picked in the
    window, duplicated per thickness; the level is the beams' level.

    `regions` are the storey's hatches and `sheet_texts` the whole sheet's own
    -- the legend lives outside any routed text layer, so the narrowed `texts`
    this pass reads slab notes from cannot be trusted to hold it. A hatched BAY
    steps the slab it sits in: the parent is cut, a floor goes in at the
    legend's depth, and the vertical face between the two soffits is filled
    where -- and only where -- the drop is deeper than the parent is thick.

    A beam graph knows where a bay BEGINS and nothing about what stops it, so
    `_slab_stops` reads that off the drawing before the steps go in: the
    crossed-out rings on the slab-stop layer become holes, the bays a staircase
    stands in are withdrawn, and the beam-bottom hatches come back as chajjas
    at their own level.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup
    level_id = selections.get("top_level_id")
    if level_id is None:
        _say("Slabs -- skipped (no top level chosen).")
        return {"created": 0, "skipped": 0, "errors": 0}
    base_type_id = selections.get("floor_type_id")
    if base_type_id is None:
        _say("Slabs -- skipped (no floor type chosen).")
        return {"created": 0, "skipped": 0, "errors": 0}
    # Outline source chain (user directive: these TWO only): (1) slab-edge layer
    # rings as drawn; (2) faces of the PLACED geometry -- the placed beams' edge
    # lines form the boundary, and the column footprint rings inside it trim the
    # corners. The beams are placed aligned, so the slab edges align with them by
    # construction; the drawn-linework fallbacks are retired.
    loops = slab_outlines.slab_loops_from_edges(records)
    source = "slab_edges"
    if not loops:
        # Column trimming is back ON (the 0.45.1 beam-edges-only isolation proved
        # the misalignment lived in the trim interaction): the exactness pass now
        # picks each vertex's carriers by RING-EDGE DIRECTION, so a diamond
        # column's 45-degree edges can no longer out-crowd the beam edge and weld
        # a long boundary onto the column apex.
        loops = slab_outlines.slab_loops_from_placed_members(
            records, beam_segments.get("segments"), column_rects=column_rects)
        source = "placed_members"
    # A drawing can note "200 THK." over a bay whose slab edge was never drawn
    # (test10's roof: rings on the south bays, one line on the north -- and in
    # the Revit records, no ring at all). Whatever the source found, a note that
    # no outline covers gets its bay recovered from the placed members, where
    # the note itself is the keep_point: a bay whose fourth side is a WALL is
    # otherwise dropped as a shaft, which is why the roof built no slabs.
    extra = slab_outlines.loops_for_unclaimed_notes(
        loops, records, beam_segments.get("segments"), texts,
        column_rects=column_rects,
        min_area_m2=(selections.get("tolerances") or {}).get(
            "slab_note_min_area_m2",
            config.DEFAULTS["slab_note_min_area_m2"]))
    if extra:
        loops = list(loops) + list(extra)
        source = "{0} + beam graph".format(source)
        _say("slabs: {0} bay(s) recovered from the beam graph where a "
             "thickness note had no drawn outline".format(len(extra)))
    if not loops:
        _say("Slabs -- no closed slab outline found (any source).")
        return {"created": 0, "skipped": 0, "errors": 0, "source": source}
    slab_schedule = {m: v for m, v in (schedule or {}).items()
                     if str(m)[:1].upper() == "S" and str(m)[1:2].isdigit()}
    # The sheet's blanket note fills the bays nothing else sized. `texts` here
    # is the SLAB text routing, which falls back to every text in the drawing --
    # so the note is reachable through it; the figure still comes from the
    # dialog, which read it off the whole sheet before any routing narrowed it.
    slab_defs = slab_outlines.apply_slab_labels(
        loops, texts, schedule=slab_schedule,
        blanket_thickness_mm=blanket_mm(selections,
                                        "blanket_slab_thickness_mm"))
    # Counted BEFORE the steps go in: "loops" and "thickness-noted" are about
    # the bays the drawing shows, and a dropped slab or a support is neither.
    loop_count = len(slab_defs)
    sized = sum(1 for sd in slab_defs if sd.get("thickness_mm") is not None)
    blanket = [sd for sd in slab_defs if sd.get("blanket")]
    # WHAT STOPS THE SLAB, before what STEPS it. A hole cut into a bay that is
    # about to be withdrawn for a staircase is work thrown away, and a sunk
    # region hosted in a bay that is not there is a step nobody can build --
    # so the bays are settled first and the steps are worked out against what
    # survives.
    slab_defs, stopped = _slab_stops(
        slab_defs, records, texts, regions, sheet_texts,
        beam_segments.get("segments"), selections, slab_schedule)
    slab_defs, steps = _sunk_slab_steps(selections, regions,
                                        sheet_texts or texts, slab_defs,
                                        beam_segments.get("segments"))

    group = TransactionGroup(doc, "CAD to BIM: Slabs")
    transaction = Transaction(doc, "Create slabs")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = slabs.place_slabs(doc, slab_defs, base_type_id, level_id)
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Slab creation failed", "Slab creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1, "source": source}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Slabs", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True,
                "source": source}

    _say("Slabs -- source: {0}, loops: {1}, thickness-noted: {2}, "
         "created: {3}, skipped: {4}, errors: {5}".format(
             source, loop_count, sized, len(result["created"]),
             len(result["skipped"]), len(result["errors"])))
    # A default the run applied SILENTLY is a default nobody can check: say how
    # many bays took the sheet's word and what that word was.
    if blanket:
        _say("slabs: {0} of {1} bay(s) took the sheet's blanket thickness of "
             "{2:g}mm (no note of their own)".format(
                 len(blanket), loop_count, blanket[0]["thickness_mm"]))
    if steps:
        _say("Slabs -- {0} sunk bay(s) stepped ({1}): {2} support(s) between "
             "the soffits.".format(
                 len(steps),
                 ", ".join("{0:.0f}mm x{1}".format(depth, count)
                           for depth, count in sorted(
                               _tally([s["depth_mm"] for s in steps]).items())),
                 sum(len(s["supports"]) for s in steps)))
    for message in result["errors"]:
        _say_error("  slab: {0}".format(message))
    for message in result["skipped"] + result.get("notes", []):
        _say("  slab: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]), "source": source, "loops": loop_count,
            "sunk_steps": len(steps),
            "sunk_supports": sum(len(s["supports"]) for s in steps),
            "slab_cutouts": stopped["crossed"],
            "slab_cutout_holes": stopped["holes"],
            "stair_bays_withdrawn": stopped["stair_bays"],
            "stair_area_m2": stopped["stair_area_m2"],
            "chajjas": stopped["chajjas"],
            _IDS: result["created"],
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"])}


def _create_stairs(doc, records, beam_segments, texts, selections,
                   column_rects=None):
    """Place generic dog-leg staircases at the plan's STAIRCASE / ST-n texts.

    Option 1 (no stair linework): the bay containing the text is the stair's
    area (placed-members faces with the shaft filter relaxed); riser count,
    tread, run width and landing come from the Staircase tab plus the base-to-
    top storey height. The builder runs its own StairsEditScope per stair --
    NO outer transaction group here (Revit forbids nesting an edit scope).
    """
    base_id = selections.get("base_level_id")
    top_id = selections.get("top_level_id")
    if base_id is None or top_id is None:
        _say("Stairs -- skipped (base and top levels are both required).")
        return {"created": 0, "skipped": 0, "errors": 0}
    base_level = doc.GetElement(base_id)
    top_level = doc.GetElement(top_id)
    storey_mm = (top_level.Elevation - base_level.Elevation) * 304.8
    if storey_mm <= 0:
        _say("Stairs -- skipped (top level is not above the base level).")
        return {"created": 0, "skipped": 0, "errors": 0}

    source = selections.get("stair_source") or "auto"
    regions = list(selections.get("stair_regions") or []) or None
    if regions:
        # outlines the user drew from the Staircase tab win over any source
        source = "region"
    elif source == "region":
        regions = _pick_stair_regions()
        if not regions:
            _say("Stairs -- skipped (no closed outline picked in the view).")
            return {"created": 0, "skipped": 0, "errors": 0}
    plans, notes = stair_layout.plan_stairs(
        records, (beam_segments or {}).get("segments"), column_rects, texts,
        selections.get("stair_params") or {}, storey_mm,
        source=source, regions=regions)
    for note in notes:
        _say("  stair: {0}".format(note))
    if not plans:
        _say("Stairs -- no staircase planned (see notes above).")
        return {"created": 0, "skipped": len(notes), "errors": 0}

    result = stairs.place_stairs(doc, plans, base_id, top_id,
                                 base_type_id=selections.get("stair_type_id"))
    _say("Stairs -- source: {0}, planned: {1}, created: {2}, skipped: {3}, "
         "errors: {4} (storey {5} mm, {6} risers @ {7:.1f} mm)".format(
             plans[0].get("source") or "stair_text", len(plans),
             len(result["created"]), len(result["skipped"]),
             len(result["errors"]), int(storey_mm), plans[0]["risers_total"],
             plans[0]["riser_mm"]))
    for message in result["errors"]:
        _say_error("  stair: {0}".format(message))
    for message in result["skipped"] + result.get("notes", []):
        _say("  stair: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]), "planned": len(plans),
            _IDS: result.get("created_ids") or [],
            "notes": notes[:8],
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": _skip_details(result["skipped"])}
