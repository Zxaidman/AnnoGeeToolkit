# -*- coding: utf-8 -*-
"""``beams.sync`` — place the framing the BEAM_PLACEMENT sheet describes.

**Continuity is the layout.** A simply supported beam is one row; a continuous
beam is a group of rows, one per span, sharing a mark, with a blank row between
groups. So the parser reads groups, not rows — and the blank rows are the only
thing saying where one beam ends and the next begins.

**One Revit member per span**, which is not a simplification: a four-span
continuous beam *is* four members that join. What the grouping buys is the
schedule mark — all four carry ``B01-1``, and Revit's own ``Mark`` carries the
key that makes each one findable.

Joins and cutbacks are left to Revit. Its automatic joins do most of it and the
rest is a per-project judgement about which member runs through; placing
correctly and leaving the joins alone is honest, and guessing at a corner is
not.
"""

__version__ = "0.1.0"

#: Where a beam's section comes from when the model does not have the type.
TYPES_SHEET = "BEAM_TYPES"


def run(uiapp, envelope):
    """``(summary, findings, note)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _placement
    from anongee_toolkit.rc_automation import placement

    return _placement.run(
        uiapp, envelope,
        sheet_default=placement.SHEET_BEAMS,
        parse=_parse,
        span=True,
        existing=_existing,
        apply=_apply,
        what="beam",
        option=envelope_module.option,
        locate=placement.locate_span,
        plan=placement.plan_spans)


def _parse(grid, sheet, units):
    """``([PlacementRow], [Issue])`` — groups flattened, marks already shared.

    The grouping did its work in the parser: every row in a group carries the
    same mark. Downstream a beam is a beam, so the groups are flattened here
    rather than threaded through everything that does not care.
    """
    from anongee_toolkit.rc_automation import placement
    groups, issues = placement.parse_beams(grid, sheet, units)
    rows = []
    for group in groups:
        for row in group:
            rows.append(row)
    return rows, issues


def _existing(doc):
    from anongee_toolkit.structural import framing
    return framing.placed(doc)


def _apply(doc, plans, findings, finding, context):
    """Create and retype beams. ``written``. Inside the caller's transaction."""
    from anongee_toolkit.commands import _marks
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import placement
    from anongee_toolkit.structural import framing

    levels = _sheets.levels(doc)
    sizes = _sheets.sizes(context, TYPES_SHEET, findings, finding)
    label_parameters = _marks.candidates(context)
    reported = set()
    cache = {}
    written = 0

    for plan in plans:
        row = plan.row
        try:
            size = sizes.get(_fold(row.type_mark)) or {}
            symbol, note = framing.ensure_symbol(
                doc, row.type_mark, size.get("width_mm"),
                size.get("depth_mm"), cache)
            if symbol is None:
                findings.append(finding("Error", row.row, note))
                continue
            if note and note not in reported:
                reported.add(note)
                findings.append(finding("Info", row.row, note))

            if plan.action == placement.MODIFY:
                instance = doc.GetElement(plan.existing)
                if instance is None:
                    findings.append(finding(
                        "Error", row.row,
                        "{0!r} vanished between planning and writing".format(
                            row.mark)))
                    continue
                if framing.set_type(doc, instance, symbol):
                    written += 1
                else:
                    findings.append(finding(
                        "Warning", row.row,
                        "{0!r} is there but Revit would not change its type "
                        "to {1}".format(row.mark, row.type_mark)))
                continue

            level = levels.get(_fold(row.level))
            if level is None:
                findings.append(finding(
                    "Error", row.row,
                    "no level called {0!r} in this model".format(row.level)))
                continue

            instance = framing.create(doc, row.start_mm, row.end_mm, symbol,
                                      level, row.offset_mm or 0.0)
            _marks.write(instance, row, label_parameters, reported, findings,
                         finding)
            written += 1
        except Exception as error:
            findings.append(finding(
                "Error", row.row, "{0!r}: {1}".format(row.mark, error)))
    return written


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
