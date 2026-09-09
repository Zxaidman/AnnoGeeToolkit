# -*- coding: utf-8 -*-
"""Every tunable the audit has, in one place.

Deliberately separate from `cad2bim.config`: these are thresholds for JUDGING a
run, not for building one. Sharing them would mean a loosened build tolerance
silently loosened the audit that is supposed to catch it.

Distances are millimetres and angles are degrees unless a name says otherwise.
"""

MM_PER_FT = 304.8


def ft_to_mm(feet):
    """Revit internal feet -> mm. `None` in, `None` out (a missing length stays missing)."""
    return None if feet is None else float(feet) * MM_PER_FT


def mm_to_ft(mm):
    return None if mm is None else float(mm) / MM_PER_FT


# --- stage names -----------------------------------------------------------
# Used as dict keys, column prefixes and sheet names, so they are stable strings
# rather than an enum (which would not survive the JSON sidecar round-trip).
STAGE_DXF_RAW = "dxf_raw"          # A, this package's full-fidelity ezdxf walker
STAGE_DXF_PARSED = "dxf_parsed"    # A, through cad2bim.readers.dxf_reader
STAGE_LINK_RAW = "link_raw"        # B, this package's full Revit geometry walker
STAGE_LINK_PARSED = "link_parsed"  # B, through cad2bim.readers.geometry_reader
STAGE_MODEL = "model"              # C, the built Revit elements
STAGE_INTENT = "intent"            # D, a cad2bim run's exported JSON

STAGES = (STAGE_DXF_RAW, STAGE_DXF_PARSED, STAGE_LINK_RAW, STAGE_LINK_PARSED,
          STAGE_MODEL, STAGE_INTENT)

#: Which stages describe the same physical source -- used when reporting a
#: reader gap ("the raw pass saw it, the parsed pass did not").
STAGE_PAIRS = ((STAGE_DXF_RAW, STAGE_DXF_PARSED),
               (STAGE_LINK_RAW, STAGE_LINK_PARSED))

STAGE_LABELS = {
    STAGE_DXF_RAW: "A. DXF (raw)",
    STAGE_DXF_PARSED: "A. DXF (cad2bim reader)",
    STAGE_LINK_RAW: "B. Revit link (raw)",
    STAGE_LINK_PARSED: "B. Revit link (cad2bim reader)",
    STAGE_MODEL: "C. Model elements",
    STAGE_INTENT: "D. cad2bim intent",
}


# --- severities ------------------------------------------------------------
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITY_OK = "ok"

#: Sort order for the Findings sheet: worst first.
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2,
                  SEVERITY_OK: 3}


# --- verdicts --------------------------------------------------------------
# What happened to one candidate member across the stages. These are the values
# of the Reconciliation sheet's `verdict` column, and the vocabulary the whole
# report is written in.
VERDICT_OK = "ok"                        # present everywhere it should be, within tolerance
VERDICT_MISSING_IN_LINK = "missing_in_link"      # in the DXF, absent from Revit's import
VERDICT_MISSING_IN_MODEL = "missing_in_model"    # seen, never built
VERDICT_NOT_INTENDED = "not_intended"    # seen, and cad2bim decided not to build it
VERDICT_ORPHAN = "orphan"                # built, with no source in the drawing
VERDICT_SIZE_MISMATCH = "size_mismatch"
VERDICT_POSITION_MISMATCH = "position_mismatch"
VERDICT_ROTATION_MISMATCH = "rotation_mismatch"
VERDICT_CATEGORY_MISMATCH = "category_mismatch"
VERDICT_READER_GAP = "reader_gap"        # the raw pass saw it, cad2bim's reader did not
# Revit's import lost it, and the build recovered it from the DXF anyway. This is
# cad2bim working as designed ("building from the cleaner ezdxf geometry"), so it
# is information, not a defect -- but it is the single most useful thing the audit
# can tell you about a drawing, because it names the geometry Revit cannot be
# trusted with.
VERDICT_LINK_RECOVERED = "link_gap_recovered"
VERDICT_EXPECTED_ABSENT = "expected_absent"      # absent for a documented API reason
VERDICT_UNCLASSIFIED = "unclassified"    # present, but no layer -> category mapping

#: A verdict's severity. Anything not listed is treated as SEVERITY_INFO.
VERDICT_SEVERITY = {
    VERDICT_OK: SEVERITY_OK,
    VERDICT_EXPECTED_ABSENT: SEVERITY_INFO,
    VERDICT_UNCLASSIFIED: SEVERITY_INFO,
    VERDICT_LINK_RECOVERED: SEVERITY_INFO,
    VERDICT_NOT_INTENDED: SEVERITY_WARNING,
    VERDICT_READER_GAP: SEVERITY_WARNING,
    VERDICT_SIZE_MISMATCH: SEVERITY_WARNING,
    VERDICT_ROTATION_MISMATCH: SEVERITY_WARNING,
    VERDICT_POSITION_MISMATCH: SEVERITY_ERROR,
    VERDICT_CATEGORY_MISMATCH: SEVERITY_ERROR,
    VERDICT_MISSING_IN_LINK: SEVERITY_ERROR,
    VERDICT_MISSING_IN_MODEL: SEVERITY_ERROR,
    VERDICT_ORPHAN: SEVERITY_ERROR,
}


DEFAULTS = {
    # --- matching -----------------------------------------------------------
    # A member is "the same member" across stages when its centroid is within
    # this radius. 100 mm is well inside the ~1500 mm cad2bim already assumes
    # between distinct columns, so two real members can never fuse, while the
    # rounding and snapping a build applies stays comfortably inside it.
    "match_radius_mm": 100.0,

    # --- what counts as wrong ----------------------------------------------
    "size_tol_mm": 25.0,        # ~half a cover; a draughtsman would notice more
    "position_tol_mm": 100.0,   # same radius as matching: matched but off-centre
    "rotation_tol_deg": 1.0,
    # A matched pair whose lengths differ by BOTH of these is clipped/merged.
    # Two conditions, because a fractional test alone flags every short stub and
    # an absolute test alone flags every long member.
    "length_mismatch_frac": 0.10,
    "length_mismatch_mm": 50.0,

    # --- report size --------------------------------------------------------
    # Per sheet. A pattern hatch explodes into tens of thousands of strokes in
    # Revit, and a workbook that Excel cannot open reports nothing at all. The
    # cap is per sheet so a flood of hatch strokes cannot push the columns off
    # the Model elements sheet. Rows dropped are counted and stated in the sheet.
    "max_rows_per_sheet": 20000,
    # Geometry is summarised (extent, centroid, length) on every row; the full
    # point list only reaches the JSON sidecar, and only up to this many points
    # per item, so one tessellated spline cannot dominate the file.
    "max_points_per_item": 64,

    # --- capture scope ------------------------------------------------------
    # Depth to explode block INSERTs when reading the DXF. cad2bim's reader
    # stops at 3; the raw pass goes deeper on purpose, so "nested too deep for
    # cad2bim" shows up as a reader gap rather than as a missing member.
    "dxf_block_depth": 8,
}


#: Revit categories stage C sweeps. Names are resolved through BuiltInCategory
#: at read time, so a category absent from a given Revit version is skipped
#: rather than raising.
MODEL_CATEGORIES = (
    "OST_StructuralColumns",
    "OST_Columns",
    "OST_StructuralFraming",
    "OST_Floors",
    "OST_StructuralFoundation",
    "OST_Walls",
    "OST_Grids",
    "OST_Levels",
    "OST_Stairs",
    "OST_GenericModel",
)

#: Which per-category sheet an item belongs on. Keyed by cad2bim's own category
#: strings AND by Revit category names, because the sheet gathers both.
CATEGORY_SHEETS = (
    ("Columns", ("column", "OST_StructuralColumns", "OST_Columns")),
    ("Beams", ("beam", "OST_StructuralFraming")),
    ("Slabs", ("slab_edge", "slab stop", "floor boundary", "OST_Floors")),
    ("Footings", ("foundation", "fold", "sunk", "OST_StructuralFoundation")),
    ("Walls", ("structural wall", "arch wall", "OST_Walls")),
    ("Stairs", ("stair", "OST_Stairs")),
    ("Grids", ("grid", "OST_Grids")),
)


def settings(overrides=None):
    """DEFAULTS with `overrides` applied. Unknown keys raise rather than vanish.

    A typo in a caller's override would otherwise silently leave the default in
    place, and the report would quietly be measured against a threshold nobody
    chose.
    """
    values = dict(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in DEFAULTS:
            raise KeyError("unknown audit setting: {0}".format(key))
        values[key] = value
    return values
