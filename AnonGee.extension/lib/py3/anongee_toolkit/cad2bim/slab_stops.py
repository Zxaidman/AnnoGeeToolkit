# -*- coding: utf-8 -*-
"""Where the slab STOPS -- the holes, the chajjas and the stair bays.

The bays come from the placed beams (`slab_outlines`), and a beam graph has no
opinion about anything drawn inside a bay. So a floor built from it alone is
cast solid over every void the drawing marks, which is what the owner found in
Revit: slab over the cut-outs, slab over the staircase, slab where the drawing
shows a projecting ledge and nothing else. This module reads the three things
the drawing says about that, each from a mark it already carries.

  1. A CROSSED RING IS A HOLE. test14 and test12 both carry a COVER layer --
     CATEGORY_SLAB_STOP -- and its linework is not bays: test14's 303 records
     close into 153 rings whose areas run 0.015 .. 0.227 m2 on a plan 200 m
     across. They are local edges, and the X drawn corner-to-corner over one
     (test14 puts those strokes on CUTOUT, 492 diagonals, no axial segment
     among them) is the same "no concrete here" symbol `foundation_plan`
     already reads over a raft face. The reading is literally the same code --
     `slab_graph.crossed` -- because two readings of one symbol drift apart.
     Measured on test14: 90 of the 153 rings are crossed, 63 are not.

  1b. A CROSSED BAY IS THE SAME STATEMENT ABOUT A BIGGER PIECE. The owner's
     v0.83.0 run: "cutout are still not working in large portion while,
     smaller is working now" -- and the split is exact. Every crossed COVER
     ring is tiny (0.031 .. 0.227 m2 on test14) and not one of them contains or
     spans a bay; those are the small cutouts that work. The large ones are not
     COVER rings at all: 6 slab BAYS are crossed corner-to-corner, 1.36 to
     19.81 m2, 63.5 m2 in all, and nothing ever asked the question, so all of
     it was cast as floor. A bay carrying the X is withdrawn exactly as a
     staircase bay is, and counted the same way.

  1c. A TEXT NAMING A CUTOUT MARKS ONE, X or no X. The owner's v0.86.0 run:
     "Few large place still are still taking the Cutout Cross even when now
     that i have put the `Cutout, Lift Shaft, Duct etc.` text there also." A
     drafter writes CUTOUT in the middle of a void whether or not anyone drew
     the diagonals over it, and the word is the same instruction as the X.
     Measured on test14 -- four bays per plan carry a `CUTOUT` text, three of
     them crossed as well and ONE, the largest at 29.13 m2, crossed by nothing
     at all. That is the "large place" the owner is still seeing, and no
     geometry in the drawing says anything about it. See `_NAMES_A_CUTOUT`
     for what counts as the word and what the corpus does with it.

  2. A BEAM-BOTTOM HATCH IS A CHAJJA. The legend prices its patterns, and one
     of test14's says no depth at all: GOST_GLASS, "INDICATES SLAB AT BEAM
     BOTTOM", 72 plan regions. That is a cantilever slab -- a chajja -- cast
     with its SOFFIT flush with the beam's, not a step in the floor. The
     COVER edge is what draws its free sides (measured: 72 of the 75 hatches
     have COVER on their perimeter, a median half of it), and the hatch region
     is its area. Its level comes from the beam it hangs off: soffit to
     soffit, top at `thickness - depth` below the level -- and since v0.88.0
     that beam may itself have been dropped by a sunk hatch, so the soffit it
     follows is `depth + drop` below the level, not `depth`.

  2b. AND THE BAY UNDER IT IS NOT FLOOR AT LEVEL. A chajja was assumed to lie
     outside every bay; measured, 18 of test14's 72 sit wholly inside one, and
     the bay was cast flat over the ledge as well. That is the owner's v0.89.0
     run: "same place both slab are drawn one is right other is not" -- the
     ledge at the beam's soffit, correct, and over the top of it the whole bay,
     respecting neither the hatch nor the slab-stop lines drawn down either
     side of it. A placed chajja's ring is therefore SUBTRACTED from the bay
     that holds it, through the same `fold_plan.split_profile` a crossed-out
     ring goes through (`chajja_cutouts`).

  3. A STAIRCASE BAY IS NOT A FLOOR. The stair pass already builds a stair in
     the bay under a STAIRCASE / ST-n text; leaving the same bay in the slab
     pass casts a floor through it. test14: 6 stair texts, 6 bays, 85.9 m2.

Nothing here is silent. Every ring that routes nowhere, every chajja whose
beam or thickness could not be had, every bay withdrawn -- all come back on
`notes`, grouped by REASON with a count, the way run_builders groups its skips.

Revit-free, so all of it is unit-testable and replayable offline.
"""

import math
import re

from . import config
from .classify.layers import (CATEGORY_BEAM, CATEGORY_COLUMN,
                              CATEGORY_SLAB_STOP, CATEGORY_STAIR)
from .slab_graph import (_centroid, _dedup_ring, _point_in_ring,
                         _signed_area, cross_strokes, crossed)
# The stair pass's OWN thresholds, borrowed rather than re-argued: what counts
# as a flight of risers, and what size of bay can hold a stair at all. A bay
# withdrawn from the slab pass on a looser rule than the stair pass builds on
# is a floor deleted for a stair that never arrives.
from .stair_runs import _RISER_MIN_LINES
from .stair_text import _MAX_STAIR_AREA_M2, _MIN_STAIR_AREA_M2

_MM = config.MM_PER_FT

# WHAT THE LEGEND CALLS A CHAJJA. `legend.read` hands back a "meaning" it could
# price at nothing (kind "other"), and for this one meaning the words ARE the
# instruction: test14 writes "INDICATES SLAB AT BEAM BOTTOM" three times, once
# per tower legend, and means the cantilever ledge each time. Matched on the
# three words in order, so "SLAB AT BEAM BOTTOM LEVEL" and
# "SLAB IS AT THE BEAM BOTTOM" read the same; a row that merely mentions a
# beam does not.
_BEAM_BOTTOM = re.compile(r"\bSLAB\b.*\bBEAM\b.*\bBOTTOM\b", re.IGNORECASE)

# How far outside a chajja's ring a beam body may sit and still be the beam it
# hangs off. The hatch is drawn to the beam FACE in this corpus -- contact is
# exact -- so this only forgives the drafting slop `_shared_run` measures
# perpendicular to the edge. A millimetre is what fold_plan's own profile work
# calls "drawn to meet" (_TOUCH_TOL_FT); 2 mm here because a hatch boundary is
# a derived polygon, not a drawn line.
_CONTACT_TOL_MM = 2.0

# WHAT NAMES A CUTOUT IN WORDS. The owner's list is "Cutout, Lift Shaft, Duct
# etc.", and the rest of the vocabulary is what an Indian structural drafter
# writes in a void: OPENING / OPNG, VOID, SHAFT, DUCT, LIFT WELL, OPEN TO
# BELOW. The shape of the rule is what the measurement forced, and it is not a
# substring search:
#
#   THE TEXT MUST *BE* THE NAME, not merely contain it. test15 carries four
#   sheet titles on a layer called A-CUTOUT -- "GROUND FLOOR PLAN", "LIFT
#   MACHINE ROOM FLOOR PLAN" -- and test9 two legend rows, "CUTOUT IN SLAB &
#   NON STR. WALL" and "HATCH INDICATE CUTOUT FOR DOOR ABOVE...". Every one of
#   them holds a word from this list, and not one of them marks a void. Read
#   whole, all six are refused, because a sentence about a cutout is not a
#   cutout. The layer is not asked either, for the same reason: A-CUTOUT is
#   where test15 keeps its titles.
#
#   A BEAM OR SLAB LABEL CANNOT MATCH IT. Whole-string matching is what
#   guarantees that: `B111`, `S1`, `MB`, `BKT`, `200X400`, `135 THK.`, `ST-1`
#   are not names on this list and never become them. Measured over every text
#   in the corpus -- 13,415 of them across 20 drawings -- the rule catches 80,
#   on five drawings, and they are listed in the sweep as `cutout_texts` so a
#   future drawing's false positive shows up as a number that moved:
#
#     test14   CUTOUT x15, LIFT SHAFT x15      (the owner's own drawing)
#     test16   CUTOUT x12, SHAFT x6
#     test10   SHAFT x20      test1/2/3  SHAFT x4 each
#
# WELL is the one word that needs a qualifier in front of it. "LIFT WELL" is a
# void; a bare "WELL" is an ordinary English word, and no drawing in the corpus
# writes either. The rest stand alone, because a drafter who writes DUCT in a
# void means the duct's hole and nothing else.
_VOID_NOUN = (r"CUT ?OUTS?|OPENINGS?|OPNGS?|VOIDS?|SHAFTS?|DUCTS?")
_QUALIFIED_NOUN = r"WELLS?"
_VOID_QUALIFIER = (
    r"LIFTS?|ELEVATORS?|STAIRS?|STAIRCASE|PLUMBING|SERVICES?|AC|TOILET|"
    r"ELECT(?:RIC(?:AL)?)?|PIPES?|FIRE|GARBAGE|REFUSE|DRY|WET|WATER|SANITARY|"
    r"VENT(?:ILATION)?|TYP|SMALL|LARGE")
_NAMES_A_CUTOUT = re.compile(
    r"^(?:(?:{q}) )*(?:{n})(?: (?:{n}|{q}|{w}))*$"     # a void noun, on its own
    r"|^(?:(?:{q}) )+(?:{w})(?: (?:{n}|{q}|{w}))*$"    # WELL, only once named
    r"|^OPEN TO (?:BELOW|SKY|ABOVE)$".format(
        n=_VOID_NOUN, q=_VOID_QUALIFIER, w=_QUALIFIED_NOUN))

# A contact shorter than this is a graze, not a bearing. Measured on test14's
# 72 chajjas the winning beam's contact runs 595 .. 2499 mm and the clips it
# beats run 175 .. 598 -- so on this corpus the floor refuses NOTHING, and it
# is set low deliberately rather than tuned into that gap: the rule that does
# the work is "longest contact wins", and all this has to do is keep a beam
# touching a chajja at one point out of the tie-break, where a hair of contact
# could otherwise decide a level.
_MIN_CONTACT_MM = 100.0


# ------------------------------------------------------------------ the rings
def slab_stop_rings(records):
    """[ring] -- every closed ring the slab-stop layer draws.

    Same chaining as `slab_outlines.slab_loops_from_edges`: a closed polyline
    is a ring as drawn, loose pieces are joined end to end and kept only when
    they close. Imported late (this module is imported BY slab_outlines) so the
    two readings of "a drawn ring" cannot drift.
    """
    from . import slab_outlines
    stops = [r for r in (records or [])
             if getattr(r, "category", None) == CATEGORY_SLAB_STOP]
    if not stops:
        return []
    return [ring for ring, _z, _arcs in slab_outlines.slab_loops_from_edges(
        stops, category=CATEGORY_SLAB_STOP)]


def slab_cutouts(loops, records):
    """{"holes": {loop index: [ring]}, "crossed": n, "notes": [...]}.

    A slab-stop ring the drawing crosses out is a hole in whichever bay holds
    it. Rings that no bay holds are counted and named -- on test14 that is 30
    of the 90, every one of them sitting inside a beam body or off the slab
    entirely, and a hole nobody cuts is a hole the model does not have.

    The hole is handed back as a RING, not applied. `fold_plan.split_profile`
    is what subtracts it, and that matters because every one of test14's 60
    hosted rings REACHES its bay's boundary -- none is a hole strictly inside a
    bay, which is the only shape Floor.Create will cut. What the subtraction
    gives back is the bay a notch smaller (all 60 on test14), or two pieces
    where the ring cuts clean across. Doing it here would be a second, worse
    copy of that walk.
    """
    out = {"holes": {}, "crossed": 0, "notes": []}
    rings = slab_stop_rings(records)
    if not rings:
        return out
    strokes = cross_strokes(records)
    homeless = 0
    uncrossed = 0
    for ring in rings:
        if not crossed(ring, strokes):
            uncrossed += 1
            continue
        out["crossed"] += 1
        host = _host_index(ring, loops)
        if host is None:
            homeless += 1
            continue
        out["holes"].setdefault(host, []).append(ring)
    if homeless:
        out["notes"].append(
            "{0} crossed-out slab-stop ring(s) sit inside no slab bay -- under "
            "a beam or off the slab: nothing is cut for them".format(homeless))
    if uncrossed:
        out["notes"].append(
            "{0} slab-stop ring(s) carry no X: they mark an edge, not a hole, "
            "and cut nothing".format(uncrossed))
    return out


def names_a_cutout(text):
    """True when this text IS the name of a void, rather than mentioning one.

    Normalised first: upper case, full stops dropped (so "A.C." is one word and
    "TYP." is TYP), and every other punctuation mark a space (so "CUT-OUT" and
    "CUT OUT" and "CUTOUT" are one thing). Then matched WHOLE -- see
    `_NAMES_A_CUTOUT` for the six sentences in this corpus that hold one of
    these words and mean nothing of the sort.
    """
    words = " ".join(re.findall(
        r"[A-Z0-9]+", (text or "").upper().replace(".", "")))
    return bool(words) and bool(_NAMES_A_CUTOUT.match(words))


def cutout_texts(texts):
    """[(x, y, the name)] for every text in the drawing that names a void.

    Any layer, like every other content-driven reading in this package: the
    word is the instruction, and test15 proves the layer is not (it keeps its
    sheet titles on one called A-CUTOUT). A text the transform never reached
    has no point and cannot be inside anything, so it is dropped here rather
    than crashing a containment test three calls down.
    """
    out = []
    for text in (texts or []):
        point = getattr(text, "point_internal", None)
        if point is None or not names_a_cutout(getattr(text, "text", "")):
            continue
        out.append((point[0], point[1], " ".join(
            (getattr(text, "text", "") or "").split())))
    return out


def cutout_bays(loops, records, texts=None, skip=None):
    """{"indexes": {i}, "area_m2": a, "notes": [...]} -- the bays marked void.

    Two marks, either of which is enough, because the drawing uses them
    interchangeably and often both at once:

      * an X CROSSED corner to corner over the bay, and
      * a TEXT NAMING A CUTOUT sitting inside it -- CUTOUT, LIFT SHAFT, DUCT,
        OPENING, VOID, OPEN TO BELOW (`names_a_cutout`).

    A bay carrying both is withdrawn once and counted once; `by_cross` and
    `by_text` say how many carry each, so the two readings can be told apart in
    a console line and in the sweep. Measured over the corpus, the text is not
    a duplicate of the X in the one place it matters: on test14 nine of the
    twelve bays a `CUTOUT` text names are crossed as well, and THREE -- one per
    plan, 29.13 m2 each, 87.4 m2 in all -- carry the word and no diagonals.
    Those three are the owner's "large place still taking the Cutout Cross".

    The same symbol `slab_cutouts` reads over a slab-stop ring, asked of the
    BAY. It is the same code too -- `slab_graph.crossed` against the same four
    corners -- because the whole point of BUG-13 is that the rule was already
    right and was simply never asked about a piece this big.

    THE STROKES ARE FILTERED HERE, AND ONLY HERE, and the measurement is what
    forced it. `cross_strokes` casts a deliberately wide net: any two-point
    record, whatever layer it is on, because a COVER ring 0.03 .. 0.23 m2
    across is not a shape two members happen to span, and restricting that
    reading by layer was measured to move nothing. A BAY is exactly that shape.
    test11 draws four 2000x2500 bays with a pair of 3200 mm diagonals across
    each, on ING-BEAM -- diagonal BEAMS, which the run places as beams, and
    withdrawing those four bays would delete 20.0 m2 of real floor. Dropping
    the strokes drawn on a beam or column layer takes those four out and moves
    nothing else in the corpus: test12 still reads 21 crossed bays (121.3 m2),
    test13 4 (0.1 m2) and test14 6 (63.5 m2), identical either way.

    `skip` is the set of bays some earlier reading already withdrew -- the
    staircase bays. A bay in both is withdrawn once and counted once, and the
    overlap is named rather than being invisible in a total. The corpus has
    none today; the arithmetic is here because a stair over a cut-out void is a
    drawing anybody could send next.
    """
    out = {"indexes": set(), "by_cross": 0, "by_text": 0, "area_m2": 0.0,
           "notes": []}
    members = set()
    for record in (records or []):
        if getattr(record, "category", None) in (CATEGORY_BEAM,
                                                 CATEGORY_COLUMN):
            points = getattr(record, "points", None) or []
            if len(points) == 2:
                members.add(((points[0][0], points[0][1]),
                             (points[1][0], points[1][1])))
    strokes = [stroke for stroke in cross_strokes(records)
               if stroke not in members]
    names = cutout_texts(texts)
    if not strokes and not names:
        return out
    skip = skip or set()
    shared = 0
    homeless = set(range(len(names)))
    for index, loop in enumerate(loops or []):
        ring = loop.get("ring") if isinstance(loop, dict) else loop
        if not ring or len(ring) < 3:
            continue
        ring = [(p[0], p[1]) for p in ring]
        named = [n for n, (x, y, _word) in enumerate(names)
                 if _point_in_ring((x, y), ring)]
        homeless -= set(named)
        by_cross = bool(strokes) and crossed(ring, strokes)
        if not by_cross and not named:
            continue
        if index in skip:
            shared += 1
            continue
        out["indexes"].add(index)
        out["by_cross"] += 1 if by_cross else 0
        out["by_text"] += 1 if named else 0
        out["area_m2"] += area_m2(ring)
    out["area_m2"] = round(out["area_m2"], 1)
    if out["indexes"]:
        out["notes"].append(
            "{0} slab bay(s) are marked void -- {1} crossed out corner to "
            "corner, {2} named by a text inside them -- {3:.1f} m2 of floor "
            "the drawing says is absent: no slab is cast there".format(
                len(out["indexes"]), out["by_cross"], out["by_text"],
                out["area_m2"]))
    if homeless:
        out["notes"].append(
            "{0} text(s) naming a cutout ({1}) sit inside no slab bay: the "
            "word marks a void the beams never closed a bay around, so "
            "nothing is withdrawn for them".format(
                len(homeless), ", ".join(sorted(set(
                    names[n][2] for n in homeless)))))
    if shared:
        out["notes"].append(
            "{0} of the void bay(s) are already withdrawn for a staircase: "
            "each is withdrawn once and counted once".format(shared))
    return out


def _host_index(ring, loops):
    """Index of the SMALLEST loop whose ring contains this one's centre.

    Smallest wins for the reason `fold_plan._host_for` gives: nested outlines
    make "any ring it sits inside" ambiguous, and the inner one is the one the
    mark describes.
    """
    centre = _centroid(ring)
    best = (None, None)
    for index, loop in enumerate(loops or []):
        outline = loop.get("ring") if isinstance(loop, dict) else loop
        if not outline or len(outline) < 3:
            continue
        if not _point_in_ring(centre, outline):
            continue
        size = abs(_signed_area(outline))
        if best[1] is None or size < best[1]:
            best = (index, size)
    return best[0]


# ---------------------------------------------------------------- the chajjas
def chajja_patterns(legend_entries):
    """The hatch patterns whose legend row means SLAB AT BEAM BOTTOM.

    Read off `legend.read`'s entries, which carry the row's own words. A
    pattern whose rows disagree is not asked about here: the drawing repeats
    its legend once per tower and every copy of this row says the same thing,
    and a disagreement would show up as some rows matching and some not, which
    is exactly the set this returns.
    """
    return set(entry.get("pattern") for entry in (legend_entries or [])
               if entry.get("pattern")
               and _BEAM_BOTTOM.search(entry.get("meaning") or ""))


def chajja_slabs(regions, beam_segments, legend_entries, texts=None,
                 skip_ids=None, schedule=None, blanket_thickness_mm=None,
                 beam_drops=None):
    """{"defs": [...], "notes": [...]} -- the cantilever ledges as slab defs.

    One def per plan region carrying a beam-bottom pattern:

        {"ring", "holes", "arcs", "thickness_mm", "offset_mm", "mark",
         "part": "chajja"}

    `part` keeps it out of the builder's opening nesting, exactly as a step's
    dropped slab is kept out: a chajja mostly lies outside every bay, but a
    ledge in a re-entrant corner can sit inside one, and a floor read as a hole
    is a floor that never gets placed. What the bay under it must NOT do is
    stay whole -- see `chajja_cutouts`.

    THE LEVEL, and the arithmetic behind it. Take the level as 0 and the beam's
    depth D as measured from it (which is what the "200X400" size note means).
    The beam's soffit is then at -D, "slab at beam bottom" puts the chajja's
    soffit there too, and `offset_mm` positions a floor's TOP -- so

        offset = thickness - D

    AND THE BEAM MAY HAVE MOVED. Since v0.88.0 a beam under a sunk hatch is
    dropped by the legend's depth through its `z Offset Value`: its soffit is
    then D + drop below the level, and a ledge hung at the old D would float
    clear of the beam it is cast off. `beam_drops` is `fold_plan.beam_drops`'
    own {segment index: depth_mm} -- the SAME table the beam builder sinks by,
    passed in rather than re-derived, because a chajja and the beam it hangs
    off disagreeing about that number is precisely the failure this fixes. So

        offset = thickness - (D + drop)

    and a beam nothing dropped contributes drop = 0, which is the arithmetic
    above unchanged. Measured on test14: 36 of the 72 chajjas hang off a
    dropped beam -- 24 by 75 mm, 12 by 150 -- and the other 36 do not move.

    The beam is the one the ring shares its longest contact with: measured over
    test14's 72 chajjas the winner runs 595 .. 2499 mm of contact against
    runner-up clips of 175 .. 598, and in the four dumped by hand the winner is
    always the long supported side. 12 of the 72 tie within a millimetre
    between beams of different depth -- a ledge spanning between two beams --
    and there the DEEPER SOFFIT wins: a chajja hung at the shallower would run
    straight through the deeper beam's web, where one at the deeper clears
    both. Deeper by SOFFIT, not by section, because that is what the ledge has
    to clear once the drops are in; on test14 the drops move no tie-break at
    all. Every tie is named on `notes`.

    A chajja whose ring touches no beam, or whose thickness nothing gives, is
    REPORTED and not placed. Both are the same refusal in different words --
    the elevation cannot be derived -- and inventing one puts a ledge at a
    level nobody chose, which reads as built and is wrong.
    """
    from . import slab_outlines
    out = {"defs": [], "notes": []}
    patterns = chajja_patterns(legend_entries)
    if not patterns:
        return out
    skip_ids = skip_ids or set()
    rings = []
    for region in (regions or []):
        if getattr(region, "pattern", None) not in patterns:
            continue
        if id(region) in skip_ids:
            continue                   # the legend's own demonstration swatch
        ring = _dedup_ring([(p[0], p[1]) for p in region.points])
        if len(ring) >= 3:
            rings.append((ring, region.points[0][2]))
    if not rings:
        return out

    bodies = _beam_bodies(beam_segments, beam_drops)
    labelled = slab_outlines.apply_slab_labels(
        [(ring, z, []) for ring, z in rings], texts, schedule=schedule,
        blanket_thickness_mm=blanket_thickness_mm)
    no_beam = 0
    no_thickness = 0
    ties = 0
    dropped = 0
    for (ring, _z), slab in zip(rings, labelled):
        soffit, tied, drop = _carrying_beam(ring, bodies)
        if soffit is None:
            no_beam += 1
            continue
        if tied:
            ties += 1
        thickness = slab.get("thickness_mm")
        if thickness is None:
            no_thickness += 1
            continue
        if drop:
            dropped += 1
        out["defs"].append({
            "ring": ring, "holes": [], "arcs": [],
            "thickness_mm": thickness,
            "offset_mm": thickness - soffit,
            "mark": slab.get("mark"), "part": "chajja"})
    if no_beam:
        out["notes"].append(
            "{0} chajja(s) touch no placed beam: their level hangs off a beam "
            "that is not there, so none is placed".format(no_beam))
    if no_thickness:
        out["notes"].append(
            "{0} chajja(s) carry no thickness, from a note, the schedule or "
            "the sheet: a slab at beam bottom cannot be levelled without one, "
            "so none is placed".format(no_thickness))
    if ties:
        out["notes"].append(
            "{0} chajja(s) hang off two beams of different depth in equal "
            "measure: each takes the DEEPER soffit, which clears both"
            .format(ties))
    if dropped:
        out["notes"].append(
            "{0} chajja(s) hang off a beam a sunk hatch drops: each follows "
            "that soffit down by the beam's own drop, so the ledge stays cast "
            "off the member and not floating below it".format(dropped))
    return out


def chajja_cutouts(loops, chajja_defs, skip=None):
    """{"holes": {loop index: [ring]}, "hosted": n, "notes": [...]}.

    THE GROUND A CHAJJA COVERS IS NOT FLOOR AT LEVEL, and until this ran the
    bay holding one was cast flat as well. The owner's v0.89.0 run, verbatim:
    "same place both slab are drawn one is right other is not" -- the ledge at
    the beam's soffit, shaped by its hatch and stopping where the slab-stop
    lines beside it stop, and over the top of it the whole bay, respecting
    neither. `chajja_slabs` ADDED a floor and nothing SUBTRACTED the ground it
    took, which is the one withdrawal the pass never had: a sunk bay's flat
    parent is withdrawn by `fold_plan.slab_defs_with_steps`, a staircase bay
    and a bay marked void by `apply_slab_stops` itself, and a chajja by
    nothing at all.

    Measured on test14, the only drawing in the corpus whose legend names a
    beam-bottom pattern, and the split is total:

        54 of the 72 chajjas sit inside NO bay -- the cantilever hanging out
           past the building line, which is what the pass was written for
        18 sit inside one ENTIRELY (share of the chajja inside its host: 1.0,
           not one of them between)

    and every one of those 18 reaches its host's boundary, while not one covers
    a host whole. So the subtraction always bites a notch or divides the bay,
    and never deletes a floor outright.

    The hole is handed back as a RING, exactly as `slab_cutouts` hands back a
    crossed one, and for the same reason: `fold_plan.split_profile` is what
    subtracts it, and doing it here would be a second, worse copy of that walk.
    The two hole sets go into ONE call of it, because a bay carrying both a
    crossed ring and a chajja has to lose both in one subtraction -- two
    sequential splits would judge the second against pieces the first invented.

    Only a PLACED chajja cuts. A ledge the pass refused to level -- no beam
    under it, no thickness for it -- is a ledge the model does not have, and
    cutting the floor away for one would leave a hole with nothing in it. The
    addition and the subtraction stay paired.

    `skip` is the bays some earlier reading already withdrew; a chajja hosted
    in one cuts nothing, there being nothing left to cut.
    """
    out = {"holes": {}, "hosted": 0, "notes": []}
    homeless = 0
    for slab in (chajja_defs or []):
        ring = [(p[0], p[1]) for p in (slab.get("ring") or [])]
        if len(ring) < 3:
            continue
        host = _host_index(ring, loops)
        if host is None or host in (skip or set()):
            homeless += 1
            continue
        out["holes"].setdefault(host, []).append(ring)
        out["hosted"] += 1
    if out["hosted"]:
        out["notes"].append(
            "{0} chajja(s) stand inside a slab bay: the ledge hangs at its "
            "beam's soffit and the bay is cut back off it, so the floor is "
            "not cast twice over the same ground".format(out["hosted"]))
    return out


def _beam_bodies(beam_segments, drops=None):
    """[(body ring, depth_mm, drop_mm)] -- footprint, section and drop.

    The DROP is carried beside the depth rather than folded into it, because
    the two answer different questions: depth + drop is where the underside
    is, and the drop on its own is what says a ledge MOVED. `drops` is keyed
    by position in `beam_segments` -- `fold_plan.beam_drops`' own table -- and
    a segment it says nothing about drops nothing, so a drawing with no sunk
    hatch measures exactly what it always did.

    `fold_plan._beam_body` is the one that already widens a centreline by its
    width; imported here rather than copied so a beam has ONE footprint in this
    package.
    """
    from . import fold_plan
    drops = drops or {}
    out = []
    for index, segment in enumerate(beam_segments or []):
        body = fold_plan._beam_body(segment)
        depth = segment.get("depth_mm")
        if body and depth:
            out.append((body, float(depth),
                        float(drops.get(index, 0.0) or 0.0)))
    return out


def _carrying_beam(ring, bodies):
    """(soffit_mm, tied, dropped) of the beam this ring hangs off.

    (None, False, False) when nothing bears it. `soffit_mm` is how far BELOW
    the level the winning beam's underside sits -- depth plus whatever a sunk
    hatch dropped it by -- and the tie between equal contacts is settled on
    that same number, since clearing both beams is what the tie-break is for.
    `dropped` says the winner was moved, which is what the console line counts.
    """
    tol = config.mm_to_ft(_CONTACT_TOL_MM)
    floor = config.mm_to_ft(_MIN_CONTACT_MM)
    best = 0.0
    winners = []
    for body, depth, drop in bodies:
        run = _contact_run(ring, body, tol)
        if run < floor:
            continue
        if run > best + tol:
            best, winners = run, [(depth, drop)]
        elif run > best - tol:
            winners.append((depth, drop))
    if not winners:
        return None, False, False
    soffit, drop = max(winners, key=lambda pair: pair[0] + pair[1])
    return (soffit + drop,
            len(set(depth + own for depth, own in winners)) > 1,
            bool(drop))


def _contact_run(ring, body, tol):
    """How far the two rings run ALONG each other, summed over their edges.

    The same measure `builders/slabs._shared_run_ft` uses to spot two loops
    drawn to one line, and for the same reason: a shared LENGTH means the
    chajja is bearing on that beam, where a shared point means it grazes it.
    """
    total = 0.0
    n, m = len(ring), len(body)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(m):
            total += _shared_run(a, b, body[j], body[(j + 1) % m], tol)
    return total


def _shared_run(a, b, c, d, tol):
    """The length of a-b that c-d lies along, 0 when they are not collinear."""
    ux, uy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(ux, uy)
    if length <= 0.0:
        return 0.0
    ux, uy = ux / length, uy / length
    for point in (c, d):
        if abs((point[0] - a[0]) * uy - (point[1] - a[1]) * ux) > tol:
            return 0.0
    t1 = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
    t2 = (d[0] - a[0]) * ux + (d[1] - a[1]) * uy
    return max(0.0, min(max(t1, t2), length) - max(min(t1, t2), 0.0))


# ------------------------------------------------------------- the stair bays
def stair_bays(loops, records, texts):
    """{"indexes": {i}, "notes": [...]} -- the bays a staircase occupies.

    A bay claims a staircase the two ways the STAIR PASS itself finds one, and
    it is deliberately the same two rather than a third of this module's
    invention -- a bay withdrawn here where no stair is actually built is a
    hole in the floor nobody asked for:

      * a STAIRCASE / ST-n text sits in it (`stair_text.find_stair_texts`, the
        reader the text-mode layout uses), or
      * at least `_RISER_MIN_LINES` stair-layer records lie WHOLLY inside it --
        the linework mode's own "fewer parallel lines than this is not a
        flight", borrowed rather than re-argued.

    WHOLLY inside, and that is the measurement that fixed this rule. Counting a
    record with ANY point in the bay tags every neighbour a riser line
    overshoots into: Project1 gained two bays holding no complete stair record
    at all, test12 four, test16 two, test8 one. Counted whole, the corpus
    splits with nothing in between -- the false bays hold 0, 1 or 2 records and
    the true ones 5, 7, 10, 11, 12, 13, 21 -- and the threshold the stair pass
    already uses sits in that desert.

    The bay must also be a plausible stair bay by AREA, `stair_text`'s own
    4 .. 60 m2 window: outside it that module reports the note and builds no
    stair, so withdrawing the floor there would take out a plate and put
    nothing back. On this corpus the window refuses nothing -- every candidate
    lands between 14.1 and 50.4 m2 -- and it is here for the drawing that puts
    three riser lines on a floor plate.

    test14: 6 texts, 6 bays, and the same six by linework -- 85.9 m2.
    """
    from . import stair_text
    out = {"indexes": set(), "notes": []}
    points = [(x, y) for x, y, _mark in stair_text.find_stair_texts(texts or [])]
    lines = [r for r in (records or [])
             if getattr(r, "category", None) == CATEGORY_STAIR]
    if not points and not lines:
        return out
    by_text = 0
    too_big = 0
    for index, loop in enumerate(loops or []):
        ring = loop.get("ring") if isinstance(loop, dict) else loop
        if not ring or len(ring) < 3:
            continue
        text_hit = any(_point_in_ring(point, ring) for point in points)
        risers = 0
        if not text_hit:
            for record in lines:
                if all(_point_in_ring((p[0], p[1]), ring)
                       for p in record.points):
                    risers += 1
                    if risers >= _RISER_MIN_LINES:
                        break
        if not text_hit and risers < _RISER_MIN_LINES:
            continue
        area = area_m2(ring)
        if area < _MIN_STAIR_AREA_M2 or area > _MAX_STAIR_AREA_M2:
            too_big += 1
            continue
        if text_hit:
            by_text += 1
        out["indexes"].add(index)
    if out["indexes"]:
        out["notes"].append(
            "{0} bay(s) hold a staircase ({1} under a STAIRCASE/ST-n note, the "
            "rest under drawn risers): no flat floor is cast there".format(
                len(out["indexes"]), by_text))
    if too_big:
        out["notes"].append(
            "{0} bay(s) carry stair marks but are outside {1:.0f}..{2:.0f} m2: "
            "the stair pass builds nothing there, so the floor stays".format(
                too_big, _MIN_STAIR_AREA_M2, _MAX_STAIR_AREA_M2))
    return out


def area_m2(ring):
    """A ring's area in square metres -- for the reports and the sweep."""
    return abs(_signed_area(ring)) * (_MM / 1000.0) ** 2
