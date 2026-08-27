# -*- coding: utf-8 -*-
"""Where a mark goes, for every element the bridge places.

Two parameters, two different jobs, and getting them the wrong way round is
what produced *Elements have duplicate "Mark" values* on the first real run:

**Revit's ``Mark``** is expected to be unique per instance. It gets the key —
``C1-A1-S1``, ``F1-A1``, ``B01-1-AB`` — which is unique by construction because
position and level are what identify an element.

**The schedule mark** is the label a schedule groups by, and it repeats on
purpose: ``C1`` is ``C1`` up a whole stack and across a floor. It goes to a
parameter the workbook names on ``INFO`` under ``SCHEDULE_MARK_PARAM``, as a
list tried in order — ``S_ScheduleMark, ID, Comments``.

This lived in ``columns.py`` for one release, which meant footings wrote
Revit's ``Mark`` and nothing else, and the owner found it. One rule needs one
home.
"""

__version__ = "0.1.0"

#: The INFO key naming the parameter that carries the repeating schedule label.
LABEL_KEY = "SCHEDULE_MARK_PARAM"


def candidates(context):
    """The parameters that may carry the schedule label, in order, from INFO.

    A list rather than one name because the three are not equivalent and the
    order is the point: a shared parameter is the proper home, ``ID`` is an
    existing shared one that will at least schedule, and ``Comments`` is where
    things end up when nothing better exists.
    """
    sheets = (context or {}).get("sheets") or {}
    for name, values in sheets.items():
        if _fold(name) != "info":
            continue
        for row in values or []:
            if not row:
                continue
            key = _fold(str(row[0]).split("(")[0])
            if key == _fold(LABEL_KEY) and len(row) > 1:
                return split(row[1])
    return []


def split(cell):
    """``"S_ScheduleMark, ID, Comments"`` -> the three, in order."""
    found = []
    for part in str(cell or "").replace(";", ",").split(","):
        part = part.strip()
        if part and part not in found:
            found.append(part)
    return found


def labels(rows, patterns, key):
    """``{folded TypeMark: schedule label}`` for one placement sheet.

    The project owner's rule, given 2026-08-27: ``S_ScheduleMark`` should read
    ``PB1``, ``B1``, ``F1`` — a **repeating label per section**, generated from
    the NAMING sheet — rather than the per-row ``Mark`` the sheet happens to
    carry.

    ``{prefix}`` is the letters the workbook's own ``TypeMark`` starts with, and
    ``{n}`` counts distinct TypeMarks **within that prefix**, in the order the
    sheet lists them. So ``PB-230x450`` gives ``PB1`` and ``B-230x600`` gives
    ``B1``, and the plinth/floor distinction the engineer already made in the
    TypeMark column carries through without being typed again.

    Numbered by first appearance rather than sorted, because a schedule read
    top to bottom should count up, and because sorting would renumber every
    beam in the building the day somebody adds ``B-200x400``.

    Pure — rows in, labels out.
    """
    from anongee_toolkit.rc_automation import naming_sheet

    seen = {}
    counts = {}
    for row in rows or ():
        type_mark = getattr(row, "type_mark", "") or ""
        folded = _fold(type_mark)
        if not folded or folded in seen:
            continue
        prefix = _prefix(type_mark)
        counts[prefix] = counts.get(prefix, 0) + 1
        seen[folded] = naming_sheet.render(patterns, key, prefix=prefix,
                                           n=counts[prefix], level="", grid="")
    return seen


def collisions(found):
    """``[(label, [type marks])]`` where one label covers two sections.

    A pattern of ``B{n}`` counts within a prefix but does not *print* it, so a
    230x450 plinth beam and a 230x600 floor beam both come out ``B1`` — two
    different sections sharing a schedule line, which is a bill of quantities
    that is quietly wrong rather than obviously wrong.

    Detected rather than prevented, because the pattern belongs to whoever
    writes the sheet. Reported every run until it is fixed.
    """
    by_label = {}
    for type_mark, label in sorted((found or {}).items()):
        by_label.setdefault(label, []).append(type_mark)
    return [(label, marks) for label, marks in sorted(by_label.items())
            if len(marks) > 1]


def _prefix(type_mark):
    """``PB`` out of ``PB-230x450``; ``F`` out of ``F1``; ``C`` out of
    ``C-300x600``.

    The letters it starts with, and nothing else. A TypeMark with no leading
    letters gives ``""``, which renders as a bare number — wrong-looking enough
    that somebody will fix the TypeMark, which is the right place to fix it.
    """
    found = ""
    for character in str(type_mark or ""):
        if character.isalpha():
            found += character
        else:
            break
    return found.upper()


def write(instance, row, names, reported, findings, finding, label=None):
    """Write both marks on one element.

    Revit's ``Mark`` always; the schedule label into the first of *names* the
    model actually has. **Which one was used is reported, once** — falling back
    silently would leave a schedule reading ``S_ScheduleMark`` empty while the
    values sat in ``Comments``, where nobody looked.
    """
    _set_builtin_mark(instance, row.unique_mark)
    _set_schedule_mark(instance, row, names, reported, findings, finding,
                       label)


def _set_builtin_mark(instance, mark):
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(mark or "")
    except Exception:
        pass


def _set_schedule_mark(instance, row, names, reported, findings, finding,
                       label=None):
    # The generated label when there is one, and the sheet's own Mark when
    # there is not — a workbook with no NAMING sheet still schedules.
    label = label or row.mark
    if not label:
        return

    if not names:
        if "unset" not in reported:
            reported.add("unset")
            findings.append(finding(
                "Info", row.row,
                "the schedule mark ({0!r}) was not written: INFO has no {1} "
                "saying which parameter carries it. Revit's own Mark holds "
                "the unique key instead, because a repeating Mark is what "
                "Revit warns about.".format(label, LABEL_KEY)))
        return

    for index, name in enumerate(names):
        try:
            parameter = instance.LookupParameter(name)
        except Exception:
            parameter = None
        if parameter is None:
            continue
        try:
            if parameter.IsReadOnly:
                continue
            parameter.Set(label)
        except Exception:
            continue
        if index and "fell-back" not in reported:
            reported.add("fell-back")
            findings.append(finding(
                "Warning", row.row,
                "the schedule mark went into {0!r}, not {1!r} — this element's "
                "category has no {1!r} in this model. A schedule reading "
                "{1!r} will be empty.".format(name, names[0])))
        return

    if "none" not in reported:
        reported.add("none")
        findings.append(finding(
            "Warning", row.row,
            "none of {0} exists on this element in this model, so the "
            "schedule mark was not written. Bind one as an instance text "
            "parameter.".format(", ".join(repr(name) for name in names))))


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
