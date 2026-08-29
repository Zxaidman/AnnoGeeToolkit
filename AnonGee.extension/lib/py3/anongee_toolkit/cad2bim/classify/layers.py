# -*- coding: utf-8 -*-
"""Layer -> element-category classification.

Hybrid model (as chosen): a default naming *convention* proposes a category for
every layer, and the override dialog (ui.prompt_mapping_override) can change any
of them before anything is used. Classification logic lives here so it is unit-
testable and reusable; the dialog lives in ui.py.

The convention below is a placeholder ordering of common structural-CAD tokens.
Replace the patterns with your real layer names once you share a sample -- this
is the one spot to edit, and the override dialog covers anything it misses.
"""

import re

CATEGORY_GRID = "grid"
CATEGORY_COLUMN = "column"
CATEGORY_BEAM = "beam"
CATEGORY_SLAB_EDGE = "slab_edge"
# Upcoming layer-driven passes (user roadmap): structural walls rise base-to-top
# like columns; arch walls sit ON beams (to the level above, else free-standing);
# stairs come from the stair-plan linework. Mapped now so real projects
# (LayoutPlan-Project1: A-WALL-CUT-Brick, PARAPET WALL, A-STAIR-Steps;
# StaircasePlan-Test1: S-STRS) can already be routed in the override dialog.
CATEGORY_STRUCT_WALL = "structural wall"
CATEGORY_ARCH_WALL = "arch wall"
CATEGORY_STAIR = "stair"
# MULTI-STOREY from ONE dxf (user convention): each floor plan is enclosed by a
# rectangle on a BOUNDARY layer, and carries a single marker on an ORIGIN layer
# that fixes where that plan sits in the model. Names differ per drawing, so the
# convention below is only a proposal -- the dialog's layer table overrides it.
CATEGORY_FLOOR_BOUNDARY = "floor boundary"
CATEGORY_FLOOR_ORIGIN = "floor origin"
# FOUNDATIONS from the drawing rather than invented from column offsets. The
# outline layer carries footings AND rafts; the step layers carry the hatched
# regions where the foundation drops (test10: S-FND, S-FND-FOLD, S-FND-SUNK).
CATEGORY_FOUNDATION = "foundation"
CATEGORY_FOLD = "fold"
CATEGORY_SUNK = "sunk"
# A CUTOUT region is a hole: no concrete where it sits, never an element of
# its own -- the hatch-region cousin of the X-marked face (foundation_plan).
# The GEOMETRY convention DOES route here now, but only from the very LAST
# row of the table: the fear that put this comment here -- a cutout token
# stealing test9's shear-wall-named layers from the wall passes -- is a fear
# about ORDER, and it is answered by position rather than by silence (see the
# two closing rows of DEFAULT_CONVENTION and the corpus dump recorded beside
# them). What routes here is the X-STROKE linework itself, drafting marks that
# are never an outline. HATCHES have a mapping of their own
# (_HATCH_CONVENTION below), where a cutout token has always been safe because
# routing a hatch layer never moves linework -- and the LEGEND proposal
# (test9's ASPHALT hatches, "HATCH INDICATE CUTOUT FOR DOOR ABOVE", all on
# PI_SHEAR WALL CUTOUT) seeds that hatch mapping too.
CATEGORY_CUTOUT = "cutout"
# WHERE THE SLAB STOPS -- not where a bay is. test14 and test12 both carry a
# COVER layer the user calls "the slab edge", and routing it to
# CATEGORY_SLAB_EDGE would be a disaster: measured, test14's 303 COVER records
# close into 153 rings of 0.015 .. 0.227 m2 (the largest 899x250 mm) on a plan
# 200 m across, so `slab_loops_from_edges` would hand the whole storey those
# 153 pockets and nothing else. They are LOCAL edges -- the rim of a hole, the
# free edge of a chajja, a notch at a duct -- and what they say is "the slab
# ends on this line", which is a different sentence from "this ring is a bay".
# slab_stops.py reads them; the bays keep coming from the placed members.
CATEGORY_SLAB_STOP = "slab stop"
CATEGORY_UNMAPPED = "unmapped"

# Identification / annotation layers must NEVER inherit a structural category,
# even though their names contain a structural token. These run first and win.
# (Fixes e.g. "S-GRID-IDEN" -- grid bubbles drawn as arcs -- being read as grid.)
EXCLUSION_PATTERNS = (
    r"iden",       # S-GRID-IDEN, S-COLS-IDEN, ... (tags/bubbles)
    r"anno",       # S-STRS-ANNO, A-ANNO-*
    r"text",       # G-ANNO-TEXT
    r"dim",        # A-ANNO-DIMS-50
    r"defpoint",   # AutoCAD Defpoints
    r"hdln",       # S-BEAM-HDLN -- hidden lines of beams (ignore)
    r"hidden",     # any explicit "hidden" layer
)

# Order matters: first regex (case-insensitive) to match wins.
# A perimeter beam's inner edge is clipped against the floor/slab outline at import, so the
# floor edge (A-FLOR) IS the surviving partner edge for half the beams. It is routed to
# slab_edge so the beam pass can pair a lone beam line against it (label-confirmed only --
# a slab edge alone never becomes a beam).
DEFAULT_CONVENTION = (
    (r"grid|axis", CATEGORY_GRID),
    # The two STEP layers before the foundation one: "S-FND-FOLD" contains
    # "fnd", so a foundation-first ordering would swallow both of them.
    (r"fold", CATEGORY_FOLD),
    (r"sunk|sink", CATEGORY_SUNK),
    # Foundation before "col": a footing layer never carries a column token, but
    # keeping it early means a "S-FND-COL-PAD" style name reads as foundation.
    # Deliberately NOT matching "step"/"thk"/"drop" -- those live on stair and
    # wall layers in this corpus ("A-STAIR-Steps", "JW_ 150 thk NON-STRU. WALL").
    (r"fnd|found|footing|raft|pcc|pile", CATEGORY_FOUNDATION),
    (r"col", CATEGORY_COLUMN),
    (r"beam|girder|joist", CATEGORY_BEAM),
    (r"slab|flor|floor", CATEGORY_SLAB_EDGE),
    (r"stair|strs|step", CATEGORY_STAIR),
    (r"boundar|bound|extent|sheet.?box", CATEGORY_FLOOR_BOUNDARY),
    (r"origin|basept|base.?point|datum", CATEGORY_FLOOR_ORIGIN),
    # "rcc" = reinforced cement concrete: a wall so named is structural, and
    # test8's S-RCC-WALL used to fall through to the arch row on its "wall"
    # token. Safe at this position -- the corpus's other rcc layers (PI_RCC
    # BEAM, S-RCC-COL) are claimed by the beam and column rows above, and the
    # full 72-layer dump moved exactly one layer when this token was added.
    (r"shear|retain|rcc", CATEGORY_STRUCT_WALL),   # structural walls before plain "wall"
    (r"wall|parapet", CATEGORY_ARCH_WALL),
    # THE LAST TWO ROWS, AND WHY THEY ARE LAST. The comment on CATEGORY_CUTOUT
    # above feared a geometry cutout token: it would pull test9's
    # "PI_SHEAR WALL CUTOUT" out of the wall passes behind the user's back. It
    # would -- ABOVE the wall rows. Below them the wall token has already
    # claimed that layer, and so has "A-WALL-CUT-Brick" (Project1, test8),
    # which the bare `cut` form would otherwise take. The whole 99-name corpus
    # dump was run against these two rows and exactly SIX names move, every one
    # of them from `unmapped`:
    #   COVER          -> slab stop  (test12 1219 records, test14 303)
    #   CUT            -> cutout     (test12 1436)
    #   CUTOUT         -> cutout     (test14 492)
    #   A-CUTOUT       -> cutout     (test10 44, test13 512, test15 12, test16 54)
    #   A-CUTOUT-THIN  -> cutout     (test15 1158, test16 276)
    #   PI_CUTOUT      -> cutout     (test9 174)
    # "A-WALL-CUT-Brick" stays arch wall and "PI_SHEAR WALL CUTOUT" stays
    # structural wall, which is the whole point of the position; and
    # "A-ANNO-Cutline n Arrow" never reaches here at all -- `anno` excludes it.
    # `cover` is bounded by nothing because nothing else in the corpus contains
    # it; `cut` is bounded on both sides so a word merely STARTING with it
    # ("Cutline") is not a cutout.
    (r"cover", CATEGORY_SLAB_STOP),
    (r"cut[\s_-]*out|(?<![a-z])cut(?![a-z])", CATEGORY_CUTOUT),
)

ALL_CATEGORIES = (
    CATEGORY_GRID, CATEGORY_COLUMN, CATEGORY_BEAM,
    CATEGORY_SLAB_EDGE, CATEGORY_STRUCT_WALL, CATEGORY_ARCH_WALL,
    CATEGORY_STAIR, CATEGORY_FOUNDATION, CATEGORY_FOLD, CATEGORY_SUNK,
    CATEGORY_CUTOUT, CATEGORY_SLAB_STOP,
    CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN,
    CATEGORY_UNMAPPED,
)

# Text/label layers carry the size marks (e.g. "S-COLS-IDEN", "S-BEAM-IDEN").
# They are routed separately from geometry: a column-text label refines/merges
# columns, a beam-text label refines beams. The geometry exclusion of "iden"
# does NOT apply here -- these layers are exactly where the marks live.
CATEGORY_COLUMN_TEXT = "column text"
CATEGORY_BEAM_TEXT = "beam text"
CATEGORY_GRID_TEXT = "grid text"
# The column-schedule table: mark<->size rows that size MARK-ONLY plan labels
# (e.g. "C9" on the plan, "C9 400x600" in the table). Routed apart from plan
# column text because the table is a block of cells, not member-adjacent labels.
CATEGORY_COLUMN_SCHEDULE = "schedule (column/beam/slab)"
# Slab notes ("S1 150 THK", "150 THK.") name and size a floor. They are found by
# CONTENT wherever they sit, so routing a layer here is a way to say "the slab
# notes are on THIS layer" -- which narrows the search on a drawing whose other
# text happens to read like a thickness.
CATEGORY_SLAB_TEXT = "slab text"
# Foundation notes name, size and STEP a footing or raft in one label:
# "F3_1500MM THK" and, where it drops, a second paragraph "2000MM FOLD".
CATEGORY_FOUNDATION_TEXT = "foundation text"
CATEGORY_TEXT_IGNORE = "ignore"
TEXT_CATEGORIES = (CATEGORY_COLUMN_TEXT, CATEGORY_BEAM_TEXT,
                   CATEGORY_GRID_TEXT, CATEGORY_SLAB_TEXT,
                   CATEGORY_FOUNDATION_TEXT,
                   CATEGORY_COLUMN_SCHEDULE, CATEGORY_TEXT_IGNORE)


def classify_text_layer(layer_name):
    """Default routing for a TEXT layer: column / beam / grid / schedule, or ignore."""
    if not layer_name:
        return CATEGORY_TEXT_IGNORE
    text = layer_name.lower()
    if "grid" in text or "axis" in text:
        return CATEGORY_GRID_TEXT
    # A schedule layer carries "sched"/"schd"/"table" -- check before plain "col"
    # so a "S-COLS-SCHEDULE" layer routes to the table, not to plan column text.
    if "sched" in text or "schd" in text or "table" in text:
        return CATEGORY_COLUMN_SCHEDULE
    # Before "col": a foundation note layer may well be named "S-FND-COL-IDEN".
    if re.search(r"fnd|found|footing|raft|pcc|pile", text):
        return CATEGORY_FOUNDATION_TEXT
    if "col" in text:
        return CATEGORY_COLUMN_TEXT
    if "beam" in text or "girder" in text or "joist" in text:
        return CATEGORY_BEAM_TEXT
    if "slab" in text or "flor" in text or "floor" in text or "thk" in text:
        return CATEGORY_SLAB_TEXT
    return CATEGORY_TEXT_IGNORE


def build_default_text_mapping(layer_keys):
    """Pre-fill {text_layer: text_category} from the convention for the dialog."""
    return dict((key, classify_text_layer(key)) for key in layer_keys)


# HATCH layers get a mapping OF THEIR OWN, apart from geometry and text (the
# user's explicit instruction). A hatch is a REGION -- a meaning painted over
# an area -- so its categories are the region meanings only: the column fill
# (test10's S-COLS carries 330 of them, test9's PI_COLUMN HATCH 106), the
# fold/sunk step regions, and the cutout hole. Everything else is unmapped.
# Keeping the list this short is the point: routing a hatch layer can never
# re-route the LINEWORK on a like-named layer, which is exactly what the
# geometry table's cutout comment feared -- and why the hatch convention MAY
# carry a cutout token where the geometry convention deliberately does not
# (test9's PI_SHEAR WALL CUTOUT hatches route to cutout by name without
# touching the shear-wall linework passes).
HATCH_CATEGORIES = (
    CATEGORY_COLUMN, CATEGORY_FOLD, CATEGORY_SUNK, CATEGORY_CUTOUT,
    CATEGORY_UNMAPPED,
)

# Order matters, like DEFAULT_CONVENTION: the step tokens go before the
# column-fill token so "S-FND-FOLD"-style names can never be swallowed by a
# broader pattern, and cutout goes before "col" so a "COLUMN CUTOUT" style
# name reads as the hole it marks.
_HATCH_CONVENTION = (
    (r"fold", CATEGORY_FOLD),
    (r"sunk|sink", CATEGORY_SUNK),
    (r"cut[\s_-]*out", CATEGORY_CUTOUT),
    (r"col", CATEGORY_COLUMN),
)


def classify_hatch_layer(layer_name):
    """Default routing for a HATCH layer: column fill / fold / sunk / cutout,
    or unmapped.

    Same precedence stance as classify_layer: the annotation exclusions run
    first (a hatch on an -IDEN or -ANNO layer is decoration, not a region
    meaning), then the hatch convention, then unmapped.
    """
    if not layer_name:
        return CATEGORY_UNMAPPED
    text = layer_name.lower()
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, text):
            return CATEGORY_UNMAPPED
    for pattern, category in _HATCH_CONVENTION:
        if re.search(pattern, text):
            return category
    return CATEGORY_UNMAPPED


def build_default_hatch_mapping(layer_keys):
    """Pre-fill {hatch_layer: region meaning} from the convention for the dialog."""
    return dict((key, classify_hatch_layer(key)) for key in layer_keys)


# A HATCH LAYER CAN CARRY MORE THAN ONE MEANING, and test14 is the drawing
# that says so: layer HAT holds ANGLE (198 regions), ANSI37 (63) and HONEY
# (21) -- three sunk depths, 150, 75 and 50 mm -- and GOST_GLASS (75), which
# the same legend calls "SLAB AT BEAM BOTTOM" and is not a step at all. One
# row per layer cannot say that: the honest proposal HAT -> sunk sweeps all
# 357 regions into one bucket, loses the three depths and mislabels 75
# (BUG-6, findings #13).
#
# So the table splits a layer into one row per PATTERN -- keyed
# "<layer_key>|<PATTERN>" -- WHERE THE LEGEND ITSELF GIVES THAT LAYER SEVERAL
# MEANINGS, and nowhere else. Splitting every layer by pattern was the
# alternative and it is measurably worse: over the corpus it turns 36 rows
# into 61 (test3, test4 and test5 alone gain three each) for drawings whose
# patterns all mean the same thing. The legend-justified rule moves exactly
# the two drawings that carry a legend -- test14 8 -> 11 rows, test9 5 -> 8 --
# and leaves the other seventeen, test10's three step layers included,
# untouched.
HATCH_KEY_SEPARATOR = "|"

# The kinds legend.py reads a VALUE for (legend.KIND_STEP, KIND_CUTOUT).
# Named here because the meaning key below has to agree with
# legend._meaning_key and this module cannot ask: legend imports THIS file,
# so the dependency only ever runs one way and the entries arrive as plain
# dicts instead.
_VALUED_KINDS = ("step", "cutout")


def hatch_row_key(layer_key, pattern=None):
    """The hatch table's row identity: the layer, or "<layer>|<PATTERN>".

    Composed, never parsed. An xref layer is legitimately named "PLAN|HAT",
    so splitting a key back apart guesses; every reader here is handed the
    layer and the pattern it already has and composes the same key instead.
    """
    if not pattern:
        return layer_key
    return "{0}{1}{2}".format(layer_key, HATCH_KEY_SEPARATOR, pattern)


def _meaning_key(entry):
    """What one legend entry MEANS, for comparison only.

    legend._meaning_key's rule restated: (kind, value) where the kind
    carries a number, else the text itself normalised for case, spacing and
    the trailing full stop -- because for a report-only row the text IS the
    meaning ("INDICATES SLAB AT BEAM BOTTOM").
    """
    kind = entry.get("kind")
    if kind in _VALUED_KINDS:
        return (kind, entry.get("value_mm"))
    return (kind, " ".join((entry.get("meaning") or "").upper().split())
            .rstrip("."))


def hatch_meanings(legend_entries):
    """{pattern: meaning} for every pattern the legend says ONE thing about.

    `legend_entries` is legend.read's output -- plain dicts carrying
    "pattern", "kind", "value_mm" and "meaning". A pattern whose rows
    disagree says nothing at all rather than one of them: test9's ZIGZAG
    means three different things across its three tower legends, and a
    pattern nobody can pin cannot justify splitting a layer either.

    The result is what `hatch_rows` compares. It is deliberately NOT a
    category -- translating a meaning into fold/sunk/cutout is legend.propose's
    job, and this only has to know when two patterns differ.
    """
    by_pattern = {}
    for entry in (legend_entries or []):
        pattern = entry.get("pattern")
        if not pattern:
            continue
        by_pattern.setdefault(pattern, set()).add(_meaning_key(entry))
    return dict((pattern, sorted(keys)[0])
                for pattern, keys in by_pattern.items() if len(keys) == 1)


def hatch_patterns(regions):
    """{layer_key: {pattern: region count}} -- the hatch table's raw material."""
    counts = {}
    for region in (regions or []):
        patterns = counts.setdefault(region.layer_key, {})
        pattern = getattr(region, "pattern", None)
        patterns[pattern] = patterns.get(pattern, 0) + 1
    return counts


def hatch_rows(regions, pattern_meanings=None):
    """The hatch table's rows: [{key, layer, pattern, patterns, count}].

    One row per layer, as it always was -- except where `pattern_meanings`
    ({pattern: meaning}, from `hatch_meanings`) shows the drawing's own
    legend giving one layer more than one meaning. That layer becomes one
    row per pattern, so each meaning can be seen, marked and overruled on
    its own (test14's HAT, four rows).

    `pattern` is None on an unsplit row and `patterns` always names every
    pattern the row covers -- which is what lets the depth boxes hang off a
    row without anyone parsing a key apart.
    """
    rows = []
    counts = hatch_patterns(regions)
    for layer in sorted(counts):
        patterns = counts[layer]
        ordered = sorted(patterns, key=lambda name: name or "")
        if _splits(patterns, pattern_meanings):
            for pattern in ordered:
                rows.append({"key": hatch_row_key(layer, pattern),
                             "layer": layer, "pattern": pattern,
                             "patterns": (pattern,),
                             "count": patterns[pattern]})
        else:
            rows.append({"key": layer, "layer": layer, "pattern": None,
                         "patterns": tuple(ordered),
                         "count": sum(patterns.values())})
    return rows


def _splits(patterns, pattern_meanings):
    """True when the legend gives one layer's patterns two meanings or more."""
    if not pattern_meanings or len(patterns) < 2:
        return False
    meanings = set(pattern_meanings[pattern] for pattern in patterns
                   if pattern in pattern_meanings)
    return len(meanings) > 1


def default_hatch_row_mapping(rows):
    """Pre-fill {row key: region meaning} from the convention, for the dialog.

    The CONVENTION still reads the LAYER: a pattern name (ANGLE, GOST_GLASS)
    says nothing about what the region means, so a split layer's rows all
    start on the one guess its name earns, and the legend -- or the user --
    is what tells them apart afterwards.
    """
    return dict((row["key"], classify_hatch_layer(row["layer"]))
                for row in (rows or []))


def hatch_category(mapping, layer_key, pattern=None):
    """The meaning a hatch mapping gives ONE region.

    The split row wins over the layer row: "HAT|ANGLE -> sunk" is an answer
    about this pattern and "HAT -> sunk" an answer about the whole layer, so
    the narrower one is the one to take. Neither present is unmapped, which
    is how a mapping saved before the split (every key a plain layer) still
    routes every region it recognises.
    """
    if mapping:
        if pattern:
            category = mapping.get(hatch_row_key(layer_key, pattern))
            if category:
                return category
        category = mapping.get(layer_key)
        if category:
            return category
    return CATEGORY_UNMAPPED


def apply_hatch_mapping(regions, mapping):
    """Stamp each region's .category from the hatch table's own mapping.

    The region cousin of `apply_mapping`, kept apart because only a hatch
    has a pattern: a mapping keyed by layer alone still works here, which is
    what the offline harnesses hand in.
    """
    for region in (regions or []):
        region.category = hatch_category(mapping, region.layer_key,
                                         getattr(region, "pattern", None))
    return regions


def classify_layer(layer_name, overrides=None):
    """Return a category for one layer.

    Precedence: explicit override > exclusion (annotation/ID) > convention match
    > unmapped. A missing layer name is always unmapped unless overridden.
    """
    if overrides and layer_name in overrides:
        return overrides[layer_name]
    if not layer_name:
        return CATEGORY_UNMAPPED
    text = layer_name.lower()
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, text):
            return CATEGORY_UNMAPPED
    for pattern, category in DEFAULT_CONVENTION:
        if re.search(pattern, text):
            return category
    return CATEGORY_UNMAPPED


def build_default_mapping(layer_keys):
    """Pre-fill {layer_key: category} from the convention for the override dialog."""
    return dict((key, classify_layer(key)) for key in layer_keys)


def apply_mapping(records, mapping):
    """Stamp each record's .category from the (possibly overridden) mapping."""
    for record in records:
        record.category = mapping.get(record.layer_key, CATEGORY_UNMAPPED)
    return records
