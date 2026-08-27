# -*- coding: utf-8 -*-
"""Making a family type, and saying exactly what happened when it will not.

Three commands duplicate a loaded type and size it — columns, beams, footings —
and each had its own copy of the four lines that do it. The copies were not the
problem; **the silence was**. Every one of them folded a failure into ``None``
and a sentence that named the *type it was looking for*, never the exception
Revit raised, so a hundred and ten beams went missing and the log said
``written=22`` without comment. Four days later the cause still had to be found
by elimination from a spreadsheet. BUG-31.

So this module exists to make one claim: **a type that cannot be made says why,
in Revit's own words.** Everything else here is the hardening that the same
investigation suggested, and none of it is worth as much as the error text.

It is deliberately not clever. It tries the name the naming sheet asked for,
falls back to the name the workbook asked for, and then to a numbered variant —
reporting which it used every time it is not the first.
"""

__version__ = "0.1.0"

#: Characters Revit refuses in an element name. Typing one into the rename box
#: gets a dialog; passing one to ``Duplicate`` gets an exception, which used to
#: arrive here as ``None``.
FORBIDDEN = "\\:{}[]|;<>?`~"

#: How many numbered variants to try before giving up. Three is enough to get
#: past a clash and small enough that a run does not quietly fill a family with
#: ``CH-230 X 600 (7)``.
VARIANTS = 3


def sanitise(name):
    """A name Revit will accept. ``''`` when nothing usable is left.

    Pure, so the rule can be argued with off Revit — which matters because the
    alternative is arguing with it through a dialog box on somebody's machine.
    """
    text = "".join(" " if character in FORBIDDEN else character
                   for character in str(name or ""))
    return " ".join(text.split()).strip()


def named_sibling(doc, base, name):
    """A type in *base*'s own family already called *name*, or ``None``.

    ``Duplicate`` raises when the name is taken, and *the name being taken means
    the type already exists* — which is the answer, not an error. Worth checking
    first rather than catching, because the exception cannot be told apart from
    the half-dozen other reasons ``Duplicate`` fails.
    """
    wanted = _fold(name)
    if not wanted:
        return None
    try:
        family = base.Family
        identifiers = list(family.GetFamilySymbolIds())
    except Exception:
        return None
    for identifier in identifiers:
        symbol = doc.GetElement(identifier)
        if symbol is None:
            continue
        if _fold(_name(symbol)) == wanted:
            return symbol
    return None


def duplicate(doc, base, preferred, fallback=None):
    """``(symbol, note)`` — a new type of *base*'s family, or ``(None, why)``.

    *why* carries the exception Revit raised, the name that was refused and the
    family it was refused in. That sentence is the entire point of this
    function; the retries below are a convenience.
    """
    if base is None:
        return None, "there is no loaded type to duplicate from"

    family_name = _family_name(base)
    tried = []
    for name, source in _candidates(preferred, fallback):
        if not name:
            continue

        existing = named_sibling(doc, base, name)
        if existing is not None:
            return existing, (
                "{0!r} already existed in {1} and was used rather than "
                "duplicated".format(name, family_name))

        try:
            made = base.Duplicate(name)
        except Exception as error:
            tried.append("{0!r} ({1}: {2})".format(
                name, type(error).__name__, _short(error)))
            continue

        note = ""
        if source != "preferred":
            note = "created {0!r} in {1} — {2}".format(name, family_name,
                                                       source)
        return made, note

    return None, (
        "Revit would not create a type in {0}. Tried {1}. Load a rectangular "
        "family, or give the type a name Revit accepts — no {2} characters, "
        "and not one already in that family.".format(
            family_name, "; ".join(tried) or "nothing usable", FORBIDDEN))


def _candidates(preferred, fallback):
    """The names to try, in order, each with why it is not the first choice."""
    first = sanitise(preferred)
    second = sanitise(fallback)

    found = []
    if first:
        found.append((first, "preferred"))
    if second and _fold(second) != _fold(first):
        found.append((second, "the naming sheet's name was refused, so the "
                              "workbook's TypeMark was used instead"))

    stem = first or second
    for index in range(2, VARIANTS + 2):
        if not stem:
            break
        found.append(("{0} ({1})".format(stem, index),
                      "the name was already taken, so it was numbered"))
    return found


def size(symbol, width_names, width_mm, depth_names, depth_mm):
    """Set two dimensions. ``(set_width, set_depth)``, neither ever raising."""
    return (_set_dimension(symbol, width_names, width_mm),
            _set_dimension(symbol, depth_names, depth_mm))


def _set_dimension(symbol, names, value_mm):
    from anongee_toolkit.revit.units import mm_to_ft
    if not value_mm:
        return False
    for name in names:
        try:
            parameter = symbol.LookupParameter(name)
            if parameter is None or parameter.IsReadOnly:
                continue
            if parameter.Set(mm_to_ft(value_mm)):
                return True
        except Exception:
            continue
    return False


def set_type_mark(symbol, mark):
    """The workbook's ``TypeMark`` onto the type, so the next run finds it.

    **This is what makes a created type idempotent.** The type is named by the
    naming sheet and looked up by the workbook's mark; without this the second
    run does not recognise what the first one made and duplicates it again.
    """
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        parameter = symbol.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            return bool(parameter.Set(mark))
    except Exception:
        pass
    return False


def activate(doc, symbol):
    """A symbol has to be active before it can be placed."""
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        return True
    except Exception:
        return False


def _family_name(symbol):
    try:
        return _name(symbol.Family) or "this family"
    except Exception:
        return "this family"


def _name(element):
    try:
        return element.Name
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)
    except Exception:
        return ""


def _short(error):
    """One line of an exception. Revit's messages run to paragraphs and the
    findings sheet is a cell."""
    text = " ".join("{0}".format(error).split())
    return text[:240] if len(text) > 240 else text


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
