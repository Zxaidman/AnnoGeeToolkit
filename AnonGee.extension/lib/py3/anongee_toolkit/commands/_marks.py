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


def write(instance, row, names, reported, findings, finding):
    """Write both marks on one element.

    Revit's ``Mark`` always; the schedule label into the first of *names* the
    model actually has. **Which one was used is reported, once** — falling back
    silently would leave a schedule reading ``S_ScheduleMark`` empty while the
    values sat in ``Comments``, where nobody looked.
    """
    _set_builtin_mark(instance, row.unique_mark)
    _set_schedule_mark(instance, row, names, reported, findings, finding)


def _set_builtin_mark(instance, mark):
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(mark or "")
    except Exception:
        pass


def _set_schedule_mark(instance, row, names, reported, findings, finding):
    label = row.mark
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
