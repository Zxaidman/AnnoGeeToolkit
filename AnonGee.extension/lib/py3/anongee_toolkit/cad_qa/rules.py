# -*- coding: utf-8 -*-
"""THE RULEBOOK. Every check this tool can report, declared once.

A rule is named here and nowhere else, for the same reason a bridge command is
(``bridge/registry.py``): the check that raises it, the report that prints it
and the spreadsheet that tabulates it all read one declaration, so a rule
cannot mean one thing in the JSON and another in the console.

**Ids are permanent.** ``L001`` is ``L001`` for the life of the tool. A rule
that stops being useful is retired -- its id is never reused and never
renumbered -- because a QA report filed against last month's drawing has to
still mean what it said. The families:

    L   layers and classification coverage
    M   marks, labels and sizes
    G   geometry integrity
    S   grid and storey structure

**Severity lives here, not in the check.** Tuning how loudly the tool complains
is then a one-line edit in a table, reviewable in a diff, rather than an
archaeology exercise across four check modules. ``guidance`` is what the
drafter should actually DO about it -- a finding that names a problem without
naming the fix generates a conversation instead of ending one.

WHY THESE RULES AND NOT OTHERS. Every one of them is a way cad2bim is known to
produce a wrong model, drawn from the classifier's own failure modes
(``cad2bim/classify/layers.py``) and the tolerances it builds against
(``cad2bim/config.py``). This is deliberately NOT a drafting-standards
checklist: nothing here says a drawing is badly drafted, only that cad2bim will
misread it. Those are different claims and conflating them makes a QA tool
nobody trusts.
"""

from .findings import (Finding, SEVERITY_ERROR, SEVERITY_WARNING,
                       SEVERITY_INFO)

__version__ = "1.0.0"

FAMILY_LAYERS = "layers"
FAMILY_MARKS = "marks"
FAMILY_GEOMETRY = "geometry"
FAMILY_STRUCTURE = "structure"

FAMILIES = (FAMILY_LAYERS, FAMILY_MARKS, FAMILY_GEOMETRY, FAMILY_STRUCTURE)

#: Human names for the families, for report headings.
FAMILY_TITLES = {
    FAMILY_LAYERS: "Layers and classification",
    FAMILY_MARKS: "Marks, labels and sizes",
    FAMILY_GEOMETRY: "Geometry integrity",
    FAMILY_STRUCTURE: "Grid and storey structure",
}


class Rule(object):
    """One declared check: what it is called, how loud it is, what to do."""

    __slots__ = ("rule_id", "family", "title", "severity", "guidance")

    def __init__(self, rule_id, family, title, severity, guidance):
        self.rule_id = rule_id
        self.family = family
        self.title = title
        self.severity = severity
        self.guidance = guidance

    def to_dict(self):
        return {"rule": self.rule_id, "family": self.family,
                "title": self.title, "severity": self.severity,
                "guidance": self.guidance}

    def __repr__(self):
        return "<Rule {0} {1}>".format(self.rule_id, self.severity)


RULES = {}


def declare(rule_id, family, title, severity, guidance):
    """Add a rule to the catalogue. Returns it."""
    if rule_id in RULES:
        raise ValueError("duplicate rule id: {0}".format(rule_id))
    rule = Rule(rule_id, family, title, severity, guidance)
    RULES[rule_id] = rule
    return rule


# ---------------------------------------------------------------------------
# L — layers and classification coverage
#
# The classifier IS the rulebook for this family: a layer cad2bim cannot place
# in a category is geometry it will silently ignore, and "silently" is the
# problem. These rules make the classifier's own misses visible before a run.
# ---------------------------------------------------------------------------
declare("L001", FAMILY_LAYERS,
        "Layer carries geometry but classifies as unmapped",
        SEVERITY_WARNING,
        "Everything on this layer is ignored by cad2bim. Rename the layer to "
        "carry a recognised token (col / beam / slab / fnd / grid / wall), or "
        "route it by hand in the cad2bim layer table before running.")

# MEASURED, NOT ASSUMED. This began as an Error and 8 of the 23 corpus
# drawings tripped it -- staircase plans, detail plans and one architectural
# layout, none of which carry a setting-out grid and all of which cad2bim
# converts. An Error that fires on a third of a known-good corpus teaches the
# reader to ignore Errors, which costs more than the rule is worth. cad2bim
# still builds without a grid; it sets out from absolute coordinates instead.
declare("L002", FAMILY_LAYERS,
        "No geometry classified as grid",
        SEVERITY_WARNING,
        "Nothing to set the model out from, so every position comes from "
        "absolute coordinates rather than a grid intersection. Expected on a "
        "detail or staircase plan; wrong on a general arrangement.")

declare("L003", FAMILY_LAYERS,
        "No geometry classified as column",
        SEVERITY_ERROR,
        "No columns will be built. Check the column outlines are on a layer "
        "whose name contains 'col' and is not excluded as an annotation layer "
        "(anything containing iden / anno / text / dim is deliberately "
        "ignored).")

declare("L004", FAMILY_LAYERS,
        "No geometry classified as beam",
        SEVERITY_WARNING,
        "No framing will be built. Normal for a foundation-only or column-only "
        "plan; wrong for a framing plan.")

declare("L005", FAMILY_LAYERS,
        "No slab edge or floor layer",
        SEVERITY_INFO,
        "Slabs will be inferred from the placed members rather than read from "
        "a drawn edge. That is the documented fallback, not a fault -- but the "
        "outline it produces follows the framing, not the architect's edge.")

declare("L006", FAMILY_LAYERS,
        "Structural-looking layer suppressed by an annotation exclusion",
        SEVERITY_WARNING,
        "The layer name carries a structural token AND an annotation token "
        "(iden / anno / text / dim / hdln / hidden), so the exclusion wins and "
        "the geometry is dropped. If it really is structural linework, rename "
        "it; if it is a tag or a hidden line, ignore this.")

declare("L007", FAMILY_LAYERS,
        "No text layer routed to column or beam labels",
        SEVERITY_WARNING,
        "Member sizes come from labels like 'C1 400x400'. With no label layer "
        "recognised, every member falls back to a default size and the model "
        "is dimensionally wrong even where it is geometrically right.")

declare("L008", FAMILY_LAYERS,
        "Hatch layer not routed to a meaning",
        SEVERITY_INFO,
        "Filled regions on this layer say nothing to cad2bim. Relevant only if "
        "they mark folds, sunk bays or cutouts; decorative hatching is fine "
        "left unmapped.")

declare("L009", FAMILY_LAYERS,
        "Almost all geometry sits on one layer",
        SEVERITY_ERROR,
        "A drawing drafted onto a single layer (often '0') cannot be "
        "classified at all -- every member would read as the same category. "
        "Separate the linework onto per-element layers before conversion.")


# ---------------------------------------------------------------------------
# M — marks, labels and sizes
#
# Geometry says where a member is; the label says what it is. cad2bim can
# recover a position from bad geometry far more often than it can invent a
# size, so a label problem is usually the more expensive one.
# ---------------------------------------------------------------------------
declare("M001", FAMILY_MARKS,
        "Text looks like a mark or size label but will not parse",
        SEVERITY_WARNING,
        "The mark grammar reads 'C1 400x400', 'B20(c)', '300 X 600'. This text "
        "is close enough to look intentional and does not parse, so the member "
        "it labels will be default-sized. Check for a stray character or a "
        "separator the grammar does not know.")

declare("M002", FAMILY_MARKS,
        "No usable size label anywhere in the drawing",
        SEVERITY_ERROR,
        "Every member will be built at its default size. Either the label "
        "layer is missing, the labels are inside blocks that did not explode, "
        "or the sizes live only in a schedule this drawing does not carry.")

declare("M003", FAMILY_MARKS,
        "Labelled size is outside plausible bounds",
        SEVERITY_WARNING,
        "Checked against the acceptance limits in cad2bim/config.py. Usually a "
        "unit slip (metres typed as millimetres) or a typo. These are sanity "
        "bounds, not a code check -- nothing here says the section is "
        "adequate.")

declare("M004", FAMILY_MARKS,
        "One mark carries conflicting sizes",
        SEVERITY_ERROR,
        "The same mark is labelled at two different sizes in one drawing. "
        "cad2bim resolves a mark to ONE type, so whichever it picks, some "
        "members get the wrong section. Settle the mark before converting.")

declare("M005", FAMILY_MARKS,
        "Size label sits far from any member",
        SEVERITY_WARNING,
        "The label is further from its nearest member than the matching radius "
        "(mark_radius_mm in cad2bim/config.py), so it will size nothing. "
        "Either it is an orphan left from an edit, or the member it belongs to "
        "was not detected.")

declare("M006", FAMILY_MARKS,
        "Mark named with no size given anywhere",
        SEVERITY_INFO,
        "A mark-only label ('C9') is sized from a schedule table. Fine when "
        "the drawing carries one; it means a default size when it does not.")


# ---------------------------------------------------------------------------
# G — geometry integrity
#
# The drafting mess that makes cad2bim underbuild. Nothing in this family is
# about neatness: each one is a shape the geometry passes are known to drop.
# ---------------------------------------------------------------------------
declare("G001", FAMILY_GEOMETRY,
        "Drawing carries no usable geometry",
        SEVERITY_ERROR,
        "Nothing was read from model space. The drawing may be empty, drawn "
        "entirely in paper space, or built from external references that were "
        "not bound.")

declare("G002", FAMILY_GEOMETRY,
        "Zero-length or degenerate geometry",
        SEVERITY_INFO,
        "Dropped harmlessly, but a lot of it usually means the drawing was "
        "exported from another package and is worth purging before it grows.")

declare("G003", FAMILY_GEOMETRY,
        "Duplicate geometry stacked on itself",
        SEVERITY_WARNING,
        "Two identical records in the same place. A doubled column outline can "
        "produce two overlapping members, and doubled edges confuse the slab "
        "outline passes. Purge duplicates before converting.")

declare("G004", FAMILY_GEOMETRY,
        "Structural linework carries a non-zero Z",
        SEVERITY_WARNING,
        "The plan is not flat. cad2bim flattens to the storey it is building, "
        "so the model still lands -- but stray Z is a reliable sign the "
        "drawing has been through an edit that moved geometry off the plane.")

declare("G005", FAMILY_GEOMETRY,
        "Outline does not close",
        SEVERITY_WARNING,
        "A column, footing or region outline that does not close cannot become "
        "a member -- a nearly-closed ring is dropped exactly like an open one. "
        "Close the polyline; a visible gap is not required for this to bite.")

declare("G006", FAMILY_GEOMETRY,
        "Geometry sits far outside the drawing's main extent",
        SEVERITY_WARNING,
        "Stray linework a long way from the plan stretches the extents, which "
        "moves the origin the model is set out from. Usually a leftover from a "
        "copy-paste. Delete it or move it onto a layer that is not converted.")

declare("G007", FAMILY_GEOMETRY,
        "Drawing extent is implausible for a building plan",
        SEVERITY_ERROR,
        "The overall size does not read as a building at the unit the drawing "
        "declares. Almost always the drawing unit: a plan drawn in metres and "
        "read as millimetres comes out a thousand times too small. Fix the "
        "unit in the cad2bim link dialog before running.")


# ---------------------------------------------------------------------------
# S — grid and storey structure
#
# A multi-storey DXF is read by the boundary/origin convention. Get that wrong
# and every floor lands on top of the one below, which looks like a geometry
# bug and is not one.
# ---------------------------------------------------------------------------
declare("S001", FAMILY_STRUCTURE,
        "No grid labels found",
        SEVERITY_WARNING,
        "Grids will be created but numbered by position instead of named from "
        "the drawing's bubbles, so grid names will not match the CAD. Put the "
        "bubble text on a layer recognised as grid text.")

declare("S002", FAMILY_STRUCTURE,
        "Grid lines run in only one direction",
        SEVERITY_WARNING,
        "A setting-out grid needs two directions. With one, nothing can be "
        "located by intersection and every position falls back to absolute "
        "coordinates.")

declare("S003", FAMILY_STRUCTURE,
        "Floor boundaries and origin markers do not pair up",
        SEVERITY_ERROR,
        "The multi-storey convention is one boundary rectangle and exactly one "
        "origin marker per plan. When the counts differ, plans are matched to "
        "the wrong origins and storeys land on top of each other.")

declare("S004", FAMILY_STRUCTURE,
        "Floor boundaries present with no origin markers",
        SEVERITY_ERROR,
        "Every plan will be set out from the same point, stacking the storeys. "
        "Add one origin marker inside each boundary.")

declare("S005", FAMILY_STRUCTURE,
        "Origin markers present with no floor boundaries",
        SEVERITY_WARNING,
        "Without boundaries there is nothing to say which geometry belongs to "
        "which plan, so the whole drawing is read as one storey.")

declare("S006", FAMILY_STRUCTURE,
        "Drawing carries a single plan",
        SEVERITY_INFO,
        "Read as one storey. Expected for a single-plan drawing; wrong if this "
        "sheet was meant to carry a stack of floors.")


def get(rule_id):
    """The declared rule, or KeyError -- an undeclared id is a bug, not data."""
    return RULES[rule_id]


def finding(rule_id, message=None, subject=None, count=None, examples=None,
            where=None, severity=None):
    """Build a :class:`~.findings.Finding` from a declared rule.

    The rule supplies the severity and, when the caller does not override it,
    the message -- so a check states WHAT it found and the catalogue states how
    much it matters. `severity` is overridable for the handful of rules whose
    weight genuinely depends on scale (a single unmapped layer against one that
    swallows the drawing); passing it is deliberate and visible at the call
    site.
    """
    rule = get(rule_id)
    return Finding(rule_id, severity or rule.severity, message or rule.title,
                   subject=subject, count=count, examples=examples,
                   where=where)


def catalogue():
    """Every rule, ordered by id. What the rulebook documentation is built from."""
    return [RULES[key] for key in sorted(RULES)]


def by_family():
    """{family: [Rule, ...]} in declaration order within each family."""
    out = dict((name, []) for name in FAMILIES)
    for rule in catalogue():
        out.setdefault(rule.family, []).append(rule)
    return out
