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

from . import (column_extent, config, fold_plan, foundation_plan, legend,
               naming, report, slab_outlines, views, wall_plan)
from .builders import (columns, beams, footings, grids, materials, slabs,
                       txn_failures, view_filters, walls)
from . import stair_layout
from .classify import layers, marks
from .builders import stairs
from .run_picking import _pick_stair_regions
from .run_console import _say, _say_each, _say_error, _progress
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


def storey_blanket_mm(selections, key, note_key, texts):
    """`blanket_mm`, but a storey that the dialog left unsettled reads its OWN note.

    A sheet holds several plans and they need not agree: test14 writes 750 deep
    / 125 thick on its first and refuge floors and 600 / 150 on the typical one,
    and the owner confirmed the difference is deliberate. Read whole-sheet those
    are two conflicting notes and `sheet_defaults` rightly settles nothing; read
    PER PLAN each is unambiguous, which is what a plan's own note means.

    So the order is: the dialog's figure if the user typed one, nothing at all
    if they turned the tick off, and otherwise THIS storey's own note. The
    dialog still overrules every plan at once, which is what a user typing one
    number into one box is asking for.
    """
    settled = blanket_mm(selections, key)
    if settled is not None:
        return settled
    return marks.sheet_defaults(texts or [])[note_key] or 0.0


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


def _sunk_beam_drops(selections, regions, texts, segments, say=True):
    """{segment index: depth_mm} for the beams a sunk hatch covers.

    BOTH halves of the hatch reading are asked, because the legend row is one
    sentence about both: "SLAB/BEAM SUNK BY 150MM". A sunk STRIP names the beam
    under it, and a sunk BAY's hatch is drawn out over the members bounding the
    bay rather than stopping at their faces -- which is the drawing saying they
    go down with the floor. `fold_plan.beam_drops` weighs the two by the same
    measured share of the BEAM.

    Nothing here is silent. Refusals come back from `sunk_split` (a pattern the
    legend prices at nothing) and from `beam_drops` (a strip lying on no
    member), and both are said before a single beam is placed -- a strip the
    run ignored is a beam sitting a step too high, and that is invisible in
    plan.

    `say=False` for the SECOND caller. The slab pass needs the same table -- a
    chajja hangs at the soffit of a beam this may have moved -- and it asks for
    it against its own (pre-split) segment list, so the answer has to be worked
    out twice. Printing it twice would be two identical paragraphs about one
    reading, so the beam pass keeps the reporting and the slab pass takes the
    numbers quietly.
    """
    if not regions:
        return {}
    depths, swatch_ids, notes = _sunk_depths(selections, regions, texts)
    if say:
        for message in notes:
            _say("  sunk (beams): {0}".format(message))
    if not depths:
        if say:
            _say("  sunk (beams): no hatch depth is known, from the dialog or "
                 "the legend: no beam is dropped")
        return {}
    split = fold_plan.sunk_split(regions, depths, swatch_ids)
    drops = fold_plan.beam_drops(segments, split["strips"], split["bays"])
    if say:
        for message in split["skipped"] + drops["skipped"]:
            _say("  sunk (beams): {0}".format(message))
    return drops["drops"]


def _slab_stops(slab_defs, records, texts, regions, sheet_texts, beam_segments,
                selections, schedule, beam_drops=None):
    """(slab_defs, [step]) -- what the drawing says STOPS each bay, applied.

    Five readings, all of them the drawing's own marks and all of them
    invisible to a beam graph: a crossed-out ring on the slab-stop layer is a
    HOLE, a FREE-STANDING X with no ring and no bay drawn round it is a hole of
    the rectangle it spans, a bay the drawing MARKS VOID -- an X over it or a
    CUTOUT / LIFT SHAFT / DUCT text in it -- is NOT a floor either, a bay a
    staircase stands in is NOT a floor, and a beam-bottom hatch is a CHAJJA at
    its own level -- which also cuts the bay it stands in back off it, so the
    ledge and the floor are not cast over one another.
    `slab_outlines.apply_slab_stops` does the work; this says what happened,
    grouped, before anything is placed -- a hole nobody cut and a stair cast
    solid both look built and are wrong.

    `beam_drops` is the beam pass's own {segment index: depth_mm}: a chajja
    hangs at the SOFFIT of the beam it is cast off, and since v0.88.0 a beam
    under a sunk hatch has moved down. Passed in rather than re-derived inside
    the stop pass so the ledge and the member can never disagree about it.

    The SHEET's texts ride along beside the routed ones for the same reason the
    legend does: a CUTOUT label sits on its own layer, and the slab-note
    routing cannot be trusted to still hold it.
    """
    entries = legend.read(regions or [], sheet_texts or texts or [])
    defs, stopped = slab_outlines.apply_slab_stops(
        slab_defs, records, texts, regions=regions,
        beam_segments=beam_segments, legend_entries=entries,
        skip_ids=set(id(entry["swatch"]) for entry in entries),
        schedule=schedule,
        blanket_thickness_mm=storey_blanket_mm(
            selections, "blanket_slab_thickness_mm", "slab_thickness_mm",
            sheet_texts or texts),
        sheet_texts=sheet_texts, beam_drops=beam_drops)
    if stopped["crossed"]:
        _say("  stops: {0} crossed-out ring(s) read, {1} cut as holes in "
             "{2} bay(s)".format(stopped["crossed"], stopped["holes"],
                                 stopped["holes"] - stopped["divided"]
                                 if stopped["divided"] else stopped["holes"]))
    if stopped["free_cutouts"]:
        _say("  stops: {0} cut-out cross(es) of {1} carry no ring and no bay, "
             "{2} cut as holes of the bay over them".format(
                 stopped["free_cutouts"], stopped["cross_marks"],
                 stopped["free_cutout_holes"]))
    # The L and the C, said out loud. Every other counter here is taken BEFORE
    # the merge, so a run where no compound mark formed reported numbers
    # identical to one where they all did -- which is why the fault survived two
    # rounds. This line is the difference, and the drawing's own answer is
    # knowable: test14 merges 48 crosses into 18 voids read from the DXF.
    _say("  stops: {0} cut-out cross(es) are drawn against each other, read as "
         "{1} L/C void(s)".format(stopped.get("cutout_crosses_merged", 0),
                                  stopped.get("cutout_voids_merged", 0)))
    if stopped["cutout_bays"]:
        _say("  stops: {0} bay(s) marked void withdrawn ({1} crossed out, {2} "
             "named by a text), {3:.1f} m2 of floor the drawing marks "
             "absent".format(stopped["cutout_bays"],
                             stopped["cutout_bays_by_cross"],
                             stopped["cutout_bays_by_text"],
                             stopped["cutout_bay_area_m2"]))
    if stopped["stair_bays"]:
        _say("  stops: {0} staircase bay(s) withdrawn, {1:.1f} m2 of floor the "
             "stair occupies".format(stopped["stair_bays"],
                                     stopped["stair_area_m2"]))
    if stopped["chajjas"]:
        _say("  stops: {0} chajja(s) placed at beam bottom, {1} of them cut "
             "out of the bay standing over them".format(
                 stopped["chajjas"], stopped["chajja_holes"]))
    for message in stopped["notes"]:
        _say("  stops: {0}".format(message))
    return defs, stopped


def _sunk_slab_steps(selections, regions, texts, slab_defs):
    """(slab_defs with their steps built in, [step]) for the hatched sunk bays.

    The same three-floor arithmetic the footings use, against slab loops
    instead of foundation outlines. Depths come from the PATTERN, so the one
    routed layer's three sunk values stay apart and the meaning on it that is
    no step at all is refused by name.

    A HATCH ONLY SAYS WHICH BAY AND HOW DEEP. The bay's own ring is the
    dropped slab -- `fold_plan.sunk_bay_steps` -- so nothing here hands the
    hatch's outline to Revit and no beam has to be cut back out of it
    afterwards.

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
    steps = fold_plan.sunk_bay_steps(
        slab_defs, split["bays"],
        max_step_mm=(selections.get("tolerances") or {}).get("max_step_mm"))
    stepped, cut = fold_plan.slab_defs_with_steps(slab_defs, steps["steps"])
    _say_each("  sunk (slabs): ",
              split["skipped"] + steps["skipped"] + steps["notes"] + cut)
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


def _column_groups(sections, selections):
    """[(sections for one top level, that top level's id)], plus a skip count.

    FEAT-16. `column_extent` has already read the whole stack and knows, for
    every column, which storey each RUN of it begins on and which it ends on --
    a run being one stretch at one section, cut where the column reduces, at a
    `_START` and after a `_STOP`. So a member is built ONCE, at the storey its
    run begins on, reaching the top of the storey it ends on, rather than as one
    column per floor stacked on itself.

    `place_vertical_members` takes ONE top level for a whole call, so the
    rectangles are grouped by the level they reach and the builder is called
    once per group. A rectangle belonging to no column at all falls in the group
    whose top is this storey's own, which is exactly what every column did
    before.

    Returns the storey's own single group untouched when there is no plan, so a
    single-storey run and a drawing with neither layer are unchanged. It returns
    NO groups when every member here was built lower down -- test17's terrace is
    58 of 58 -- and that is an answer, not a failure to produce one.
    """
    plan = selections.get("column_extents")
    top_id = selections.get("top_level_id")
    if not plan:
        return [(sections, top_id)], 0
    columns = plan.get("columns") or []
    spans = plan.get("spans") or {}
    storey = plan.get("storey")
    tops = plan.get("top_ids") or {}
    source = sections.get("entries") or []
    rects = [(number, rect) for number, entry in enumerate(source)
             for rect in entry.get("rectangles") or []]
    if not columns or not rects:
        return [(sections, top_id)], 0
    # BY POSITION AND SECTION, not by index. The footprints were gathered from
    # the drawing's records; these rectangles come out of
    # `decompose_to_rectangles`, which splits some and drops others, so the two
    # never line up and nothing here may assume they do. A rectangle takes the
    # column of its own size standing where it stands -- a grid point can hold
    # two, one stopping and one carrying on above -- and failing that the
    # smallest drawn box that holds it, which is what keeps every leg of an L
    # with the L it came from.
    keys = [column_extent.assign(columns, rect["center"],
                                 (rect["width_mm"], rect["height_mm"]))
            for _number, rect in rects]
    built, skipped = column_extent.plan_storey(keys, spans, storey)
    by_top = {}
    for index, reach in built.items():
        number, rect = rects[index]
        by_top.setdefault(tops.get(reach, top_id), {}).setdefault(
            number, []).append(rect)
    # Each group keeps the ENTRIES it came from, holding only the rectangles
    # that reach this top. The entry is what carries the drawing's own layer and
    # whether the outline was approximated, and a group that threw those away to
    # become one nameless entry would take them out of everything downstream
    # that reads them.
    groups = []
    for level_id, chosen in by_top.items():
        entries = [dict(source[number], rectangles=kept)
                   for number, kept in sorted(chosen.items())]
        groups.append((dict(sections, entries=entries, circles=[]), level_id))
    if groups:
        # The circles ride with ONE group, and the storey's own top is where
        # they belong: `_create_columns` places them itself, from the storey's
        # own levels, and a copy on every group would count them again per
        # group in the split's console line.
        own = [index for index, group in enumerate(groups)
               if group[1] == top_id]
        groups[own[0] if own else 0][0]["circles"] = sections.get("circles", [])
    return groups, len(skipped)


def _merge_placed(first, second):
    """Two `place_vertical_members` results as one.

    FEAT-16 calls the builder once per top level, so the storey's outcome is the
    sum of those calls. Lists join and counts add; anything else is taken from
    the FIRST call, which is the storey's own group -- there is nothing sensible
    to add two family ids together into.
    """
    merged = dict(first)
    for key, value in (second or {}).items():
        mine = merged.get(key)
        if isinstance(value, list) and isinstance(mine, list):
            merged[key] = mine + value
        elif isinstance(value, dict) and isinstance(mine, dict):
            joined = dict(mine)
            for name, count in value.items():
                if isinstance(count, int) and isinstance(joined.get(name), int):
                    joined[name] = joined[name] + count
                else:
                    joined.setdefault(name, count)
            merged[key] = joined
        elif isinstance(value, int) and isinstance(mine, int):
            merged[key] = mine + value
        elif key not in merged:
            merged[key] = value
    return merged


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
        # Not place_columns: the owner's three-way says whether each vertical
        # member is a column, a wall, or decided per member by its mark and its
        # L/B ratio. Column mode hands the same rectangles to the same builder
        # in the same order, so the default run is unchanged.
        groups, carried = _column_groups(sections, selections)
        if carried:
            _say("  columns: {0} member(s) already built lower down and carried "
                 "up to this storey -- each runs from where its section and its "
                 "_START/_STOP layers say it begins, so it is not rebuilt here"
                 .format(carried))
        result = None
        for group_sections, group_top in groups:
            placed = columns.place_vertical_members(
                doc, group_sections, selections, family_id, base_id,
                group_top, region_max_side_mm=region_max)
            result = placed if result is None else _merge_placed(result, placed)
        if result is None:
            # NOT a rebuild. A storey can legitimately have nothing of its own
            # left to place -- test17's terrace is 58 members and every one of
            # them was built lower down and carried up here -- and falling back
            # to the whole storey then would put a second column inside each of
            # them. Nothing to place is nothing placed.
            result = {"created": [], "skipped": [], "errors": [], "notes": [],
                      "wall_ids": [], "counts": {}}
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

    _say("Columns -- rect created: {0}, walls: {4}, circular: {1}, skipped: {2}, "
         "errors: {3}".format(
             len(result["created"]), len(circular["created"]),
             len(result["skipped"]),
             len(result["errors"]) + len(circular["errors"]),
             len(result.get("wall_ids") or [])))
    for message in result["errors"] + circular["errors"]:
        _say_error("  column: {0}".format(message))
    for message in (result["skipped"] + result.get("notes", [])
                    + circular.get("notes", [])):
        _say("  column: {0}".format(message))
    return {"rect": len(result["created"]), "circular": len(circular["created"]),
            "walls": len(result.get("wall_ids") or []),
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
    the sunk half: a hatched strip no wider than a beam, and a sunk BAY's own
    hatch drawn out over its beams, both say the member under them hangs lower
    by the legend's depth -- same section, same length, top and soffit down
    together.
    The drop is applied as the beam's `z Offset Value`, never by moving the
    curve, so Start/End Level Offset stay at zero. Every strip that lands on no
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
        _say("Beams -- {0} of {1} sunk by a hatch ({2}) through z Offset "
             "Value, depth and level unchanged.".format(
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
                     regions=None, schedule_texts=None):
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
    outlines = foundation_plan.plan_foundations(
        records or [], texts or [], regions=regions or [],
        # the drawing's own FOUNDATION schedule, the F/RF block test16 draws
        # beside its slab one. Asked last, so a note on the ring itself wins.
        #
        # From `schedule_texts` -- the whole file -- and never from `texts`,
        # which is the routed foundation notes and holds `S-FND-IDEN` alone.
        # test16 draws its table on `G-ANNO-SCHD`, so reading it off the notes
        # returned an empty schedule on every storey and every F-marked ring
        # stayed unsized.
        schedule=marks.parse_thickness_schedule(schedule_texts or texts or []))
    if outlines:
        _say("Footings -- {0} outline(s) read from the drawing; the "
             "column-offset derivation is not used.".format(len(outlines)))
    steps = fold_plan.plan_steps(
        outlines, regions or [],
        max_step_mm=(selections.get("tolerances") or {}).get("max_step_mm"))
    _say_each("  step: ", steps["skipped"])
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
    # The CORNERS. A junction the rule could not resolve is left exactly as
    # drawn -- which is the 150 mm hole the owner photographed -- so it is said
    # in red rather than counted as a success: nothing about the wall looks
    # wrong in plan, and only the corner tells you.
    junctions = plan.get("junctions") or {}
    if junctions.get("found"):
        _say("  wall corners: {0} of {1} shaped, one wall through and one on "
             "its face.".format(junctions["resolved"], junctions["found"]))
        for rule, count in sorted((junctions.get("by_rule") or {}).items()):
            _say("    {0}: {1}".format(rule, count))
        for entry in (junctions.get("unresolved") or []):
            _say_error("    left as drawn x {0}: {1}".format(
                entry["count"], entry["reason"]))
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


def _ensure_link_host_view(doc, uidoc):
    """Put the user in a view `Document.Link` will accept (BUG-25).

    The owner runs this button from a schedule or a sheet, because that is where
    the work is, and `Document.Link` refuses either -- "The view is not
    printable. Parameter name: pDBView" -- before one element is made. His
    instruction was to stop showing him that: the tool knows the view is wrong
    and knows which view is right, so it goes there.

    Returns True when the link can proceed. Only False when the model has no
    view that could host it at all, which is said on the console rather than in
    a dialog, and is the one case a user has to act on.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, View
    active = getattr(doc, "ActiveView", None)
    if active is not None and views.can_host_link(
            getattr(active, "ViewType", ""),
            bool(getattr(active, "IsTemplate", False))):
        return True

    was = getattr(active, "Name", "-")
    candidates = [v for v in FilteredElementCollector(doc).OfClass(View)
                  if v is not None and not v.IsTemplate]
    index = views.choose_host(candidates)
    if index is None:
        _say_error("The active view ({0}) cannot host a linked DXF, and this "
                   "model has no plan or 3D view that can. Open one and run "
                   "again.".format(was))
        return False

    chosen = candidates[index]
    try:
        uidoc.ActiveView = chosen
    except Exception as switch_error:
        _say_error("The active view ({0}) cannot host a linked DXF and Revit "
                   "would not switch to {1}: {2}".format(
                       was, chosen.Name, switch_error))
        return False
    _say("view: {0} cannot host a linked DXF, so the run moved to {1}.".format(
        was, chosen.Name))
    return True


def _show_the_model(doc, uidoc):
    """End in a 3D view, zoomed to the model that was just built (FEAT-11)."""
    from Autodesk.Revit.DB import FilteredElementCollector, View3D
    active = getattr(doc, "ActiveView", None)
    if getattr(active, "ViewType", None) is None or str(
            getattr(active, "ViewType", "")) != "ThreeD":
        candidates = [v for v in FilteredElementCollector(doc).OfClass(View3D)
                      if v is not None and not v.IsTemplate]
        index = views.choose_3d(candidates)
        if index is None:
            _say("view: no 3D view in this model to open at the end.")
            return
        try:
            uidoc.ActiveView = candidates[index]
        except Exception as switch_error:
            _say("view: could not open the 3D view ({0}).".format(switch_error))
            return
    # Zoom whichever 3D view is now in front, whether this pass opened it or the
    # user was already there -- and zoom it to the MODEL, not to everything the
    # view happens to draw.
    _zoom_to_model(doc, uidoc)


def _zoom_to_model(doc, uidoc):
    """Frame the model in the active view, ignoring the CAD link and the datums.

    `ZoomToFit` frames everything the view draws, which after a run is the whole
    linked DXF sheet plus grids and levels running past the building -- the
    owner: "it also takes LinkedCAD and Level or Grid on Zoom to fit, what
    actually want was it should only zoom to fit BIM model". So the box is built
    from the model elements alone (`views.counts_as_model`) and the view is
    zoomed to that rectangle instead.

    Falls back to `ZoomToFit` when no model element has a box to offer -- an
    empty run should still frame something rather than leave the camera where a
    plan left it.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, ImportInstance, XYZ
    view = doc.ActiveView
    box = None
    try:
        boxes = []
        for element in (FilteredElementCollector(doc, view.Id)
                        .WhereElementIsNotElementType()):
            category = getattr(element, "Category", None)
            name = getattr(category, "Name", "")
            if not views.counts_as_model(
                    _category_key(category) or name,
                    isinstance(element, ImportInstance)):
                continue
            boxes.append(element.get_BoundingBox(view))
        # The fold lives in `views` so it can be RUN by a test. Kept here it was
        # only ever pinned by name, and the seeding bug it carried -- the Revit
        # box handed to a union that unpacks a pair -- went unnoticed through
        # every run until the owner's test17 console printed it.
        box = views.model_box(boxes, XYZ)
    except Exception as scan_error:
        _say("view: could not measure the model to zoom to ({0}).".format(
            scan_error))
        box = None

    try:
        for ui_view in uidoc.GetOpenUIViews():
            if ui_view.ViewId != view.Id:
                continue
            if box is None:
                ui_view.ZoomToFit()
                _say("view: nothing but the link and the datums to frame, so "
                     "the view was zoomed to fit everything.")
            else:
                ui_view.ZoomAndCenterRectangle(box[0], box[1])
            break
    except Exception as zoom_error:
        _say("view: could not zoom ({0}).".format(zoom_error))


def _category_key(category):
    """The BuiltInCategory name of a category, or "" when it has none."""
    if category is None:
        return ""
    try:
        from Autodesk.Revit.DB import BuiltInCategory
        return str(BuiltInCategory(category.Id.IntegerValue))
    except Exception:
        return ""


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
                  column_rects=None, regions=None, sheet_texts=None,
                  schedule_texts=None):
    """Place floor slabs after the beams, in a transaction group.

    Outline sources, in order: (1) closed rings on the slab-edge (A-FLOR) layer;
    (2) faces of the PLACED beam edge lines with the placed column footprints
    trimming the corners (exact boundary, re-derived onto the carrier lines).
    Thickness and mark come from slab notes ("S1 150 THK", "150 THK.") lying
    INSIDE the loop -- content-driven, any text layer -- and, for a bay no note
    reached, from the SHEET's blanket note ("ALL SALB ARE 125MM U.N.O."), which
    the dialog settled before the run. The floor type is the one picked in the
    window, duplicated per thickness; the level is the beams' level.

    `regions` are the storey's hatches and `sheet_texts` this PLAN's texts
    unnarrowed -- the legend lives outside any routed text layer, so the
    narrowed `texts` this pass reads slab notes from cannot be trusted to hold
    it, and a multi-storey sheet draws its legend once per plan. `schedule_texts`
    is the whole FILE, because a schedule is drawn once for the sheet and sits
    inside no plan at all: on test16 the sheet reads eleven Mark|Thk rows and
    every one of its five storeys reads none. A hatched BAY
    is sunk: the BAY's own ring drops to the legend's depth -- the hatch says
    which bay and how deep and nothing about the shape -- and the vertical face
    between the two soffits is filled where, and only where, the drop is deeper
    than the parent is thick.

    A beam graph knows where a bay BEGINS and nothing about what stops it, so
    `_slab_stops` reads that off the drawing before the steps go in: the
    crossed-out rings on the slab-stop layer become holes, the bays a staircase
    stands in and the bays an X crosses out are withdrawn, and the beam-bottom
    hatches come back as chajjas at their own level -- each cut out of the bay
    standing over it, so the ledge and the floor are not cast on one another.
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
    # A slab schedule is a Mark|Thk table, not a Mark|W|L one, so it is read by
    # its own pass and it WINS here: a thickness stated against the mark beats
    # the first dimension of any section that happens to share it. test16 draws
    # S1 125 .. S6 250 and 201 labels using those marks; until this ran, every
    # bay fell back to the blanket note and no type was made from the schedule.
    #
    # Read from `schedule_texts`, which is the WHOLE FILE and not this storey.
    # A schedule is drawn once per sheet, beside the plans and inside none of
    # them: measured on test16, the sheet reads all eleven of its rows and, once
    # split into storeys, NOT ONE of the five reads a single row -- while those
    # storeys carry 62, 62, 62 and 15 S-marks on their plans. `sheet_texts`
    # cannot be widened to fix it, because the blanket note is deliberately read
    # per plan at the owner's instruction and shares that list.
    for mark, thickness in marks.parse_thickness_schedule(
            schedule_texts or sheet_texts or texts).items():
        if str(mark)[:1].upper() == "S" and str(mark)[1:2].isdigit():
            slab_schedule[mark] = thickness
    # The sheet's blanket note fills the bays nothing else sized. `texts` here
    # is the SLAB text routing, which falls back to every text in the drawing --
    # so the note is reachable through it; the figure still comes from the
    # dialog, which read it off the whole sheet before any routing narrowed it.
    slab_defs = slab_outlines.apply_slab_labels(
        loops, texts, schedule=slab_schedule,
        blanket_thickness_mm=storey_blanket_mm(
            selections, "blanket_slab_thickness_mm", "slab_thickness_mm",
            sheet_texts or texts))
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
    # The SAME drop table the beam pass sinks its members by, asked again
    # against THIS pass's (pre-split) segment list so the indexes line up. A
    # chajja hangs at its beam's soffit, and a beam under a sunk hatch has
    # moved; asked quietly, because the beam pass has already said all of it.
    beam_drops = _sunk_beam_drops(selections, regions, sheet_texts or texts,
                                  beam_segments.get("segments"), say=False)
    slab_defs, stopped = _slab_stops(
        slab_defs, records, texts, regions, sheet_texts,
        beam_segments.get("segments"), selections, slab_schedule,
        beam_drops=beam_drops)
    slab_defs, steps = _sunk_slab_steps(selections, regions,
                                        sheet_texts or texts, slab_defs)

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
            "cutout_cross_marks": stopped["cross_marks"],
            "free_cutouts": stopped["free_cutouts"],
            "free_cutout_holes": stopped["free_cutout_holes"],
            "cutout_crosses_merged": stopped.get("cutout_crosses_merged", 0),
            "cutout_voids_merged": stopped.get("cutout_voids_merged", 0),
            "stair_bays_withdrawn": stopped["stair_bays"],
            "stair_area_m2": stopped["stair_area_m2"],
            "cutout_bays_withdrawn": stopped["cutout_bays"],
            "cutout_bays_by_cross": stopped["cutout_bays_by_cross"],
            "cutout_bays_by_text": stopped["cutout_bays_by_text"],
            "cutout_bay_area_m2": stopped["cutout_bay_area_m2"],
            "chajjas": stopped["chajjas"],
            "chajja_holes": stopped["chajja_holes"],
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
