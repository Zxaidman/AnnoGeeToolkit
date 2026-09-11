# -*- coding: utf-8 -*-
"""Layer and classification coverage -- rules L001-L009.

THE CLASSIFIER IS THE RULEBOOK HERE. ``cad2bim/classify/layers.py`` already
encodes, against a measured 99-name corpus, which layer names mean which
element. A layer it cannot place is geometry cad2bim will silently ignore, and
this family's whole job is to make that silence audible before a run rather
than after one.

Nothing in here re-implements the convention or second-guesses it. Every check
asks the real classifier the same question the real run will ask it, and
reports where the answer is going to cost the user a member.
"""

import re

from ..deps import layers as layer_rules
from .. import rules

__version__ = "1.0.0"

#: A single layer holding at least this share of the drawing means the drawing
#: was not layered at all. 0.9 rather than 1.0 because a real one-layer drawing
#: still carries a few strays on Defpoints or a title block.
ONE_LAYER_SHARE = 0.9

# THERE IS NO SHARE ESCALATION, and the reason is worth recording because it
# looks like an obvious feature. L001 was escalated to Error when an unmapped
# layer held more than a quarter of the drawing, and on the corpus that fired
# on four drawings whose biggest unmapped layer is A-DETL-THIN (test6: 579
# records, 64%) -- architectural detail linework that is SUPPOSED to be
# ignored. Record count is a measure of drafting density, not of structural
# importance, so it cannot carry this judgement. Whether the drawing is
# actually unusable is L003's question, and L003 asks it directly.

#: Structural tokens, for L006. Taken from the convention table itself so the
#: two cannot drift: if a token is added to cad2bim's classifier it is a
#: structural token here on the next import, with no edit.
_STRUCTURAL_PATTERNS = tuple(pattern for pattern, _category
                             in layer_rules.DEFAULT_CONVENTION)


def check(context):
    """Every layer-coverage finding for this drawing."""
    found = []
    found.extend(_unmapped_geometry_layers(context))
    found.extend(_single_layer_drawing(context))
    found.extend(_missing_categories(context))
    found.extend(_suppressed_structural_layers(context))
    found.extend(_missing_label_layers(context))
    found.extend(_unmapped_hatch_layers(context))
    return found


def _unmapped_geometry_layers(context):
    """L001 -- layers carrying geometry that classify as unmapped."""
    total = len(context.records)
    out = []
    for layer, records in sorted(context.records_by_layer().items()):
        if context.mapping.get(layer) != layer_rules.CATEGORY_UNMAPPED:
            continue
        if _matches_any(layer, layer_rules.EXCLUSION_PATTERNS):
            # Dropped by an annotation exclusion, not by a missing convention
            # row. Either L006 says so with the reason, or the layer really is
            # a tag layer and is correctly ignored -- saying "unrecognised"
            # about it would be wrong twice over.
            continue
        share = (len(records) / float(total)) if total else 0.0
        out.append(rules.finding(
            "L001",
            message=("{0} records on an unrecognised layer are ignored "
                     "({1:.0%} of the drawing)".format(len(records), share)),
            subject=layer, count=len(records),
            examples=_kind_examples(records)))
    return out


def _single_layer_drawing(context):
    """L009 -- effectively everything on one layer."""
    total = len(context.records)
    if not total:
        return []
    by_layer = context.records_by_layer()
    if len(by_layer) <= 1 and total < 20:
        # A drawing this small is a fixture or a fragment, not a plan drafted
        # onto one layer. Saying "unlayered" about it would be noise.
        return []
    layer, records = max(by_layer.items(), key=lambda item: len(item[1]))
    share = len(records) / float(total)
    if share < ONE_LAYER_SHARE:
        return []
    return [rules.finding(
        "L009",
        message="{0:.0%} of the drawing sits on one layer".format(share),
        subject=layer, count=len(records))]


def _missing_categories(context):
    """L002-L005 -- a category the drawing produced nothing for."""
    checks = (
        ("L002", layer_rules.CATEGORY_GRID),
        ("L003", layer_rules.CATEGORY_COLUMN),
        ("L004", layer_rules.CATEGORY_BEAM),
        ("L005", layer_rules.CATEGORY_SLAB_EDGE),
    )
    out = []
    for rule_id, category in checks:
        if context.count_in(category):
            continue
        out.append(rules.finding(rule_id, subject=category, count=0))
    return out


def _suppressed_structural_layers(context):
    """L006 -- a structural name the annotation exclusions dropped.

    The exclusion is usually right: ``S-GRID-IDEN`` really is bubbles and
    ``S-BEAM-HDLN`` really is hidden lines. It is reported anyway because when
    it is wrong the geometry vanishes without a word, and the drafter is the
    only one who can tell which case this is.
    """
    out = []
    for layer, records in sorted(context.records_by_layer().items()):
        if context.mapping.get(layer) != layer_rules.CATEGORY_UNMAPPED:
            continue
        if not _matches_any(layer, layer_rules.EXCLUSION_PATTERNS):
            continue
        if not _matches_any(layer, _STRUCTURAL_PATTERNS):
            continue
        out.append(rules.finding(
            "L006",
            message=("{0} records dropped: the name reads as both structural "
                     "and annotation".format(len(records))),
            subject=layer, count=len(records),
            examples=_kind_examples(records)))
    return out


def _missing_label_layers(context):
    """L007 -- nothing routed to column or beam label text."""
    wanted = (layer_rules.CATEGORY_COLUMN_TEXT, layer_rules.CATEGORY_BEAM_TEXT)
    if any(category in wanted for category in context.text_mapping.values()):
        return []
    if not context.texts:
        # G001/M002 already say the drawing carries nothing to read. A third
        # voice saying the same thing is noise.
        return []
    return [rules.finding(
        "L007",
        message=("{0} text entities read, none on a layer recognised as "
                 "column or beam labels".format(len(context.texts))),
        count=len(context.texts),
        examples=sorted(set(t.layer_key for t in context.texts))[:5])]


def _unmapped_hatch_layers(context):
    """L008 -- filled regions whose layer says nothing to cad2bim."""
    out = []
    for layer, regions in sorted(context.regions_by_layer().items()):
        if context.hatch_mapping.get(layer) != layer_rules.CATEGORY_UNMAPPED:
            continue
        patterns = sorted(set(r.pattern or "SOLID" for r in regions))
        out.append(rules.finding(
            "L008",
            message="{0} filled regions carry no meaning".format(len(regions)),
            subject=layer, count=len(regions), examples=patterns[:5]))
    return out


# -- helpers ----------------------------------------------------------------

def _matches_any(layer_name, patterns):
    """Whether the layer name matches any regex in `patterns`, case-insensitive."""
    text = (layer_name or "").lower()
    return any(re.search(pattern, text) for pattern in patterns)


def _kind_examples(records):
    """["412x lwpolyline", "18x line"] -- what is actually ON the layer."""
    counts = {}
    for record in records:
        counts[record.kind] = counts.get(record.kind, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ["{0}x {1}".format(count, kind) for kind, count in ordered]
