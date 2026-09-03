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


def choose(loaded, house, wanted):
    """Which loaded type to use. ``(index into loaded, note)``, or ``(None, note)``.

    ``loaded`` is ``[(label, name, type_mark, id)]``.

    **The house name is the identity.** This is the project owner's rule, given
    on 2026-08-27 and it reverses what this did before:

        tool should able to create duplicate and use naming convention from
        workbook as our Revit template is premature

    So a beam is not *whatever the model happens to call a 230 x 600 section* —
    it is ``CH-230 X 600``, and if the model has no such type one is made. A
    template holding ``PB-230x450`` and ``300 X 600`` is not the authority on
    what things are called; the NAMING sheet is. Adopting the template's names
    was the old behaviour and it is why footings came out ``F3``, beams
    ``PB-230x450`` and slabs ``SL-150`` while the workbook said otherwise.

    The old passes are kept **only as a fallback for when there is no house
    name** — no NAMING pattern, or no sizes to render it from — and every one
    of them is reported, because a type matched by anything other than its name
    is a guess that happened to be right.

    Nothing here touches Revit, so the rule can be argued with off it.
    """
    house_key = _fold(house)
    wanted_key = _fold(wanted)

    if house_key:
        for index, (_label, name, _mark, _id) in enumerate(loaded):
            if _fold(name) == house_key:
                return index, ""
        for index, (label, _name, type_mark, _id) in enumerate(loaded):
            if type_mark and _fold(type_mark) == house_key:
                return index, "matched {0!r} on its Type Mark, in {1}".format(
                    house, label)
        # Deliberately no further passes. A type of the right size under
        # another name is *not* this type — it is the template's name for it,
        # and the house name is what the model should carry.
        return None, ""

    if not wanted_key:
        return None, ""

    for index, (_label, _name, type_mark, _id) in enumerate(loaded):
        if type_mark and _fold(type_mark) == wanted_key:
            return index, ""
    for index, (_label, name, _mark, _id) in enumerate(loaded):
        if _fold(name) == wanted_key:
            return index, ""
    for index, (label, name, _mark, _id) in enumerate(loaded):
        if wanted_key in _fold(name):
            return index, ("matched {0!r} to {1} - the NAMING sheet gave no "
                           "name for it, so the model's own was used".format(
                               wanted, label))
    return None, ""


def fits(symbol, wanted, tolerance_mm=1.0):
    """True when *symbol* already measures what was asked for.

    *wanted* is ``((parameter names, millimetres), ...)``.

    **A name is not a size.** Reusing a type because its *name* matched, without
    checking what it measures, is how a hundred and ten 230 x 600 floor beams
    were quietly given a 230 x 450 plinth section — and the run reported
    ``written=110`` and looked like a success. A same-named type of the wrong
    size is a different type.
    """
    for names, value_mm in wanted:
        if not value_mm:
            continue
        found = reads(symbol, names)
        if found is None or abs(found - value_mm) > tolerance_mm:
            return False
    return True


#: Revit's internal unit is the decimal foot, and a foot is 304.8 mm exactly.
#:
#: Spelled here rather than imported from ``revit.units``, so that :func:`fits`
#: — the check that stops a wrong-sized type being reused — can be exercised
#: off Revit. Importing the units module drags in ``System`` and the whole
#: check would only ever run on somebody's machine.
FEET_TO_MM = 304.8


def reads(symbol, names):
    """The millimetre value of the first of these parameters that exists."""
    for name in names:
        try:
            parameter = symbol.LookupParameter(name)
            if parameter is None or not parameter.HasValue:
                continue
            return float(parameter.AsDouble()) * FEET_TO_MM
        except Exception:
            continue
    return None


def duplicate(doc, base, preferred, fallback=None, accept=None):
    """``(symbol, made, note)`` — a type of *base*'s family, or ``(None, False, why)``.

    *made* is **True only when a new type was created**, and it is the most
    important thing this function returns.

    A caller sizes what it makes. When this hands back a type that already
    existed, sizing it **edits a type other elements are using**: a run asking
    for 230 x 600 was given the existing ``PB-230x450``, set its depth to 600,
    and every plinth beam in the model became 600 deep. The run reported
    success. So the caller has to be able to tell the two cases apart, and a
    boolean is the only way that is not easy to get wrong.

    *why* carries the exception Revit raised, the name that was refused and the
    family it was refused in.

    *accept* decides whether a type that **already carries the wanted name** can
    be used as it is — see :func:`fits`.
    """
    if base is None:
        return None, False, "there is no loaded type to duplicate from"

    family_name = _family_name(base)
    tried = []
    for name, source in _candidates(preferred, fallback):
        if not name:
            continue

        existing = named_sibling(doc, base, name)
        if existing is not None:
            if accept is not None and not accept(existing):
                tried.append("{0!r} (already used by a type of a different "
                             "size)".format(name))
                continue
            return existing, False, (
                "{0!r} already existed in {1} at the right size and was used "
                "as it is - nothing was changed on it".format(name,
                                                              family_name))

        try:
            made = base.Duplicate(name)
        except Exception as error:
            tried.append("{0!r} ({1}: {2})".format(
                name, type(error).__name__, _short(error)))
            continue

        note = ""
        if source != "preferred":
            note = "created {0!r} in {1} - {2}".format(name, family_name,
                                                       source)
        return made, True, note

    return None, False, (
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
