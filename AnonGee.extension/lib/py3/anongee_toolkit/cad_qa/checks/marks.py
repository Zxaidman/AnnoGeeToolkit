# -*- coding: utf-8 -*-
"""Marks, labels and sizes -- rules M001-M006.

Geometry says WHERE a member is. The label says WHAT it is, and cad2bim can
recover a position from poor geometry far more often than it can invent a
size -- so a label problem is usually the more expensive of the two. A drawing
that converts with perfect geometry and no sizes produces a model that looks
right in a view and is wrong in every schedule.

The parser is ``cad2bim/classify/marks.py`` and this module never re-implements
it. Where a check needs to know "does this look like a label the parser SHOULD
have read", it uses a deliberately WIDER pattern than the parser's and reports
the difference -- which is the only honest way to find a label the grammar
misses, and it is how the ``400MM X 400MM`` and ``C-1`` forms surfaced.
"""

import re

from ..deps import layers as layer_rules
from .. import rules
from ..findings import SEVERITY_WARNING
from ..spatial import GridIndex, centroid

__version__ = "1.0.0"

#: Categories a size label could plausibly be labelling.
MEMBER_CATEGORIES = frozenset((
    layer_rules.CATEGORY_COLUMN, layer_rules.CATEGORY_BEAM,
    layer_rules.CATEGORY_STRUCT_WALL, layer_rules.CATEGORY_ARCH_WALL,
    layer_rules.CATEGORY_FOUNDATION, layer_rules.CATEGORY_STAIR,
    layer_rules.CATEGORY_SLAB_EDGE,
))

# WIDER THAN THE PARSER, ON PURPOSE. cad2bim's _SIZE_RE is
# (\d+)\s*[x×X*]\s*(\d+) -- so "400MM X 400MM" does not parse (the unit sits
# between the number and the separator) and neither does "400-400". This
# pattern accepts both, and a string that matches here while the parser
# returns nothing is precisely an M001.
_LOOKS_LIKE_SIZE = re.compile(
    r"\d{2,5}\s*(?:MM|mm)?\s*[xX×*\-/]\s*\d{2,5}")

# Same trick for the mark token. The parser requires letters immediately
# followed by digits ("C1"); a drafter writing "C-1" or "C 1" gets no mark at
# all, and the member it labels is sized by nothing.
_LOOKS_LIKE_MARK = re.compile(r"\b[A-Za-z]{1,3}\s*[-_ ]\s*\d{1,3}\b")

#: Text shorter than this is a grid bubble or a callout, not a label worth
#: complaining about.
_MIN_TEXT_LENGTH = 2


def check(context):
    """Every mark/label finding for this drawing."""
    sized = [t for t in context.texts
             if t.b_mm is not None and t.h_mm is not None]
    found = []
    found.extend(_unparsed_labels(context))
    found.extend(_no_sizes_at_all(context, sized))
    found.extend(_implausible_sizes(context, sized))
    found.extend(_conflicting_marks(context, sized))
    found.extend(_orphan_labels(context, sized))
    found.extend(_marks_without_sizes(context))
    return found


def _unparsed_labels(context):
    """M001 -- text the wider pattern reads and the parser does not."""
    size_misses = []
    mark_misses = []
    for text in context.texts:
        raw = (text.text or "").strip()
        if len(raw) < _MIN_TEXT_LENGTH:
            continue
        flat = raw.replace("\n", " ")
        if text.b_mm is None and _LOOKS_LIKE_SIZE.search(flat):
            size_misses.append(text)
        elif text.mark is None and _LOOKS_LIKE_MARK.search(_strip_size(flat)):
            mark_misses.append(text)

    out = []
    if size_misses:
        out.append(rules.finding(
            "M001",
            message=("{0} labels carry a size the parser cannot read"
                     .format(len(size_misses))),
            subject="size", count=len(size_misses),
            examples=_text_examples(size_misses),
            where=context.point_mm(size_misses[0].point)))
    if mark_misses:
        out.append(rules.finding(
            "M001",
            message=("{0} labels carry a mark the parser cannot read "
                     "(a separator between the letters and the number)"
                     .format(len(mark_misses))),
            subject="mark", count=len(mark_misses),
            examples=_text_examples(mark_misses),
            where=context.point_mm(mark_misses[0].point)))
    return out


def _strip_size(flat):
    """The label with its size token removed, so a mark test cannot see it.

    "C_300 X 900" is mark "C" and size 300x900, NOT a mark called "C-300" --
    but a mark pattern looking for letters, a separator and digits finds one in
    the size every time. Removing the size first is what makes the difference
    between reporting a real unreadable mark and reporting every sized label in
    the drawing, which is the false positive this function exists for.
    """
    return _LOOKS_LIKE_SIZE.sub(" ", flat)


def _no_sizes_at_all(context, sized):
    """M002 -- not one usable size in the whole drawing.

    ASKS THE SCHEDULE FIRST. A drawing can carry no sized label at all and
    still size every member, because the sizes live in a mark/size table --
    test15 and StaircasePlan-Test2 are exactly that, 119 schedule rows each
    and not one "C1 400x400" on the plan. Reporting those as "no sizes
    anywhere" is false, so the schedule is consulted and the finding drops to
    a Warning that says where the sizes actually are.
    """
    if sized or not context.records:
        return []
    rows = context.schedule
    if rows:
        return [rules.finding(
            "M002",
            message=("no sized labels on the plan; every size comes from the "
                     "{0}-row schedule table".format(len(rows))),
            count=len(rows), severity=SEVERITY_WARNING)]
    return [rules.finding("M002", count=len(context.texts))]


def _implausible_sizes(context, sized):
    """M003 -- a labelled size outside the acceptance envelope.

    The envelope is the widest span of cad2bim's OWN acceptance limits, so this
    never contradicts what the builder will accept: anything inside these
    bounds is a size some member type would take. The catch it is really for is
    the unit slip -- "0.4 x 0.4" for a 400 mm column.
    """
    lower, upper = _size_envelope(context.tolerances)
    offenders = []
    for text in sized:
        if not (lower <= text.b_mm <= upper) or not (lower <= text.h_mm <= upper):
            offenders.append(text)
    if not offenders:
        return []
    return [rules.finding(
        "M003",
        message=("{0} labelled sizes fall outside {1:g}-{2:g} mm"
                 .format(len(offenders), lower, upper)),
        count=len(offenders), examples=_text_examples(offenders),
        where=context.point_mm(offenders[0].point))]


def _conflicting_marks(context, sized):
    """M004 -- one mark, two sizes."""
    by_mark = {}
    for text in sized:
        if not text.mark:
            continue
        by_mark.setdefault(text.mark, set()).add(
            (round(text.b_mm, 1), round(text.h_mm, 1)))

    out = []
    for mark in sorted(by_mark):
        sizes = by_mark[mark]
        if len(sizes) < 2:
            continue
        shown = ["{0:g}x{1:g}".format(b, h) for b, h in sorted(sizes)]
        out.append(rules.finding(
            "M004",
            message="{0} is labelled at {1} different sizes".format(
                mark, len(sizes)),
            subject=mark, count=len(sizes), examples=shown))
    return out


def _orphan_labels(context, sized):
    """M005 -- a size label with no member inside the matching radius."""
    radius_mm = float(context.tolerances.get("mark_radius_mm") or 0.0)
    if radius_mm <= 0 or not sized:
        return []

    index = GridIndex(radius_mm)
    for record in context.records:
        if record.category not in MEMBER_CATEGORIES:
            continue
        middle = centroid(record.points)
        if middle is None:
            continue
        index.add(context.to_mm(middle[0]), context.to_mm(middle[1]),
                  record.layer_key)
    if not len(index):
        # Nothing to be near. L002/L003 already say the drawing produced no
        # members; every label would be an orphan and saying so adds nothing.
        return []

    orphans = []
    for text in sized:
        if not text.point:
            continue
        point = context.point_mm(text.point)
        if index.nearest(point[0], point[1], radius_mm) is None:
            orphans.append(text)
    if not orphans:
        return []
    return [rules.finding(
        "M005",
        message=("{0} size labels have no member within {1:g} mm"
                 .format(len(orphans), radius_mm)),
        count=len(orphans), examples=_text_examples(orphans),
        where=context.point_mm(orphans[0].point))]


def _marks_without_sizes(context):
    """M006 -- named members whose size must come from a schedule."""
    bare = [t for t in context.texts
            if t.mark and t.b_mm is None and not t.size_key]
    if not bare:
        return []
    names = sorted(set(t.mark for t in bare))
    return [rules.finding(
        "M006",
        message=("{0} labels name a mark without a size ({1} distinct marks)"
                 .format(len(bare), len(names))),
        count=len(bare), examples=names[:5])]


# -- helpers ----------------------------------------------------------------

def _size_envelope(tolerances):
    """(lower, upper) mm, the widest span of cad2bim's acceptance limits."""
    keys_low = ("col_b_min_mm", "col_h_min_mm", "beam_width_min_mm")
    keys_high = ("col_b_max_mm", "col_h_max_mm", "beam_width_max_mm")
    lows = [float(tolerances[k]) for k in keys_low if tolerances.get(k)]
    highs = [float(tolerances[k]) for k in keys_high if tolerances.get(k)]
    return (min(lows) if lows else 50.0, max(highs) if highs else 20000.0)


def _text_examples(texts):
    """Distinct label strings, flattened to one line, shortest first.

    Shortest first because the short ones are the readable ones: a label that
    lost its size reads as "C-1", and burying it under a three-line general
    note helps nobody.
    """
    seen = []
    for text in texts:
        flat = " ".join((text.text or "").split())
        if flat and flat not in seen:
            seen.append(flat)
    seen.sort(key=lambda s: (len(s), s))
    return seen[:5]
