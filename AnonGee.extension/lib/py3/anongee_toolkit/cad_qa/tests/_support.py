# -*- coding: utf-8 -*-
"""Shared test scaffolding: import path, and builders for fake drawings.

THE BUILDERS USE THE REAL RECORD CLASSES. A hand-rolled stub with the same
attribute names would pass these tests and fail in Revit the day one of those
classes grows a field, which is the whole failure mode a fake is supposed to
prevent. ``cad2bim.model`` is pure data with no Revit in it, so there is no
reason to imitate it.

A context built here costs microseconds, which is what lets the check suite run
in well under a second while the corpus leg reads real 30 MB drawings.
"""

import os
import sys

_TOOLKIT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _TOOLKIT not in sys.path:
    sys.path.insert(0, _TOOLKIT)

from cad2bim.model import CurveRecord, TextRecord, RegionRecord, DxfReadResult
from cad_qa.context import DrawingContext

#: Where the real drawings live, for the corpus leg.
FIXTURE_CAD = os.path.join(_TOOLKIT, "cad2bim", "tests", "fixtures", "cad")


def curve(layer, points, kind="lwpolyline", length_ft=None):
    """One CurveRecord. Points may be 2- or 3-tuples."""
    filled = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in points]
    return CurveRecord(kind, filled, layer, length_ft)


def rect(layer, x, y, width, height, kind="lwpolyline", closed=True):
    """An axis-aligned rectangle at (x, y), closed unless told otherwise."""
    points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    if closed:
        points.append((x, y))
    return curve(layer, points, kind=kind)


def text(layer, value, point=(0.0, 0.0), rotation_deg=0.0):
    """One TextRecord in drawing coordinates."""
    filled = (point[0], point[1], point[2] if len(point) > 2 else 0.0)
    return TextRecord(value, layer, filled, rotation_deg)


def region(layer, points, pattern="SOLID", solid=True):
    filled = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in points]
    return RegionRecord(filled, layer, pattern, solid)


def context(records=None, texts=None, regions=None, unit_mm=1.0,
            source="fake.dxf", tolerances=None, layer_overrides=None):
    """A DrawingContext over hand-built geometry."""
    result = DxfReadResult(source, list(records or []), list(texts or []),
                           list(regions or []))
    return DrawingContext(result, unit_mm=unit_mm, tolerances=tolerances,
                          layer_overrides=layer_overrides)


def plan(extra_records=None, extra_texts=None):
    """A minimal drawing that passes the structural checks.

    Four grid lines in two directions, one column, one beam, one slab edge,
    one sized label and one grid bubble -- the baseline a test perturbs to make
    exactly one rule fire. Spread over 20 m so the extent is plausible (G007)
    and the grid runs are long enough to count (S002).

    IT MUST TRIP NOTHING BUT S006 (the single-plan note, which is Info). The
    grid bubble is here because without it the baseline carried a standing
    S001, and a baseline with a finding already in it makes every "exactly one
    rule fires" assertion a half-truth.
    """
    records = [
        curve("S-GRID", [(0, 0), (20000, 0)], kind="line"),
        curve("S-GRID", [(0, 10000), (20000, 10000)], kind="line"),
        curve("S-GRID", [(0, 0), (0, 10000)], kind="line"),
        curve("S-GRID", [(20000, 0), (20000, 10000)], kind="line"),
        rect("S-COLS", 1000, 1000, 400, 400),
        curve("S-BEAM", [(1200, 1200), (9000, 1200)], kind="line"),
        rect("A-FLOR", 0, 0, 20000, 10000),
    ]
    texts = [text("S-COLS-IDEN", "C1 400x400", (1200, 1200)),
             text("S-GRID-IDEN", "A", (0, -500))]
    records.extend(extra_records or [])
    texts.extend(extra_texts or [])
    return context(records, texts)


def rule_ids(findings):
    """Sorted rule ids present -- what most assertions actually care about."""
    return sorted(set(f.rule for f in findings))
