# -*- coding: utf-8 -*-
"""Asking the model what a rule can be built from, and what it matches.

Deliberately thin. Everything that can be decided without a model lives above
it in ``rules`` and ``values``, and is tested there; this file only fetches
facts and hands them up as plain data.

The pipeline, and the order is a performance decision rather than a style one::

    1. Category    FilteredElementCollector(doc, view.Id) + multicategory filter
    2. Family      by name, on the element's TYPE
    3. Type        by name
    4. Parameters  read ONLY the ones the rule's conditions name

Stages 1-3 are cheap and stage 4 is not -- it costs a parameter read per
surviving element -- so the cascade narrows before it is reached. Collection is
scoped to the **active view** rather than the document: that is what an isolate
operates on anyway, and on a large model it is the difference that matters.

Nothing here writes. ``revit_apply`` is the only module in this package that
opens a transaction.
"""

from __future__ import division

import clr

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,            # noqa: E402
                               CategoryType, ElementId,
                               ElementMulticategoryFilter,
                               FilteredElementCollector, LabelUtils,
                               ParameterFilterUtilities, StorageType, View)
from System.Collections.Generic import List                                  # noqa: E402

from . import compat
from . import names
from . import rules as _rules

#: How many elements are sampled when listing the parameters a category offers.
#: Every element of a category carries the same type parameters, but instance
#: parameters can differ where several families share a category, so a handful
#: are read rather than one. Fifty is enough to catch that and small enough
#: that opening the picker never stalls.
PARAMETER_SAMPLE = 50

#: Elements a model-wide pass will read parameters on before it gives up and
#: reports "not measured". The pass exists to explain the gap between what the
#: model holds and what the view can show (see ``model_count``), and that
#: explanation is not worth stalling Revit for. Ten thousand is roughly a
#: second on a warm model; past it the number would be arriving long after the
#: user had moved on, and a count nobody waited for is worse than no count.
AUDIT_CEILING = 10000


# ---------------------------------------------------------------------------
# What a rule can be built from
# ---------------------------------------------------------------------------

def categories(doc):
    """``[(name, BuiltInCategory)]`` for every model category, name-sorted.

    Model categories only -- annotation and analytical ones cannot usefully be
    isolated -- and only those with a real ``BuiltInCategory``, which excludes
    the subcategories a project invents and that no collector can filter on.

    Nothing narrower than that. An earlier draft also required
    ``AllowsBoundParameters``, which was a guess dressed as a rule: it would
    have hidden any model category that holds elements but takes no bound
    parameters, and a rule can isolate those perfectly well.
    """
    found = []
    for category in doc.Settings.Categories:
        try:
            if category.CategoryType != CategoryType.Model:
                continue
            built_in = _built_in_of(category)
            if built_in is None:
                continue
            found.append((category.Name, built_in))
        except Exception:
            # A category that will not answer is a category no rule can use.
            continue
    found.sort(key=lambda row: names.key(row[0]))
    return found


def _built_in_of(category):
    """The ``BuiltInCategory`` behind a ``Category``, or ``None``."""
    try:
        return BuiltInCategory(compat.id_value(category.Id))
    except Exception:
        return None


def _category_ids(doc, category_names):
    """``List[ElementId]`` for the named categories, matched Revit's way."""
    wanted = [names.key(name) for name in category_names if name]
    built = List[ElementId]()
    for category in doc.Settings.Categories:
        try:
            if names.key(category.Name) in wanted:
                built.Add(category.Id)
        except Exception:
            continue
    return built


def _collector(doc, view, category_names):
    """Every model element of those categories, as the view shows them."""
    ids = _category_ids(doc, category_names)
    if ids.Count == 0:
        return None
    collector = (FilteredElementCollector(doc, view.Id) if view is not None
                 else FilteredElementCollector(doc))
    return (collector.WherePasses(ElementMulticategoryFilter(ids))
            .WhereElementIsNotElementType())


def families(doc, category_names):
    """The family names available under those categories, name-sorted.

    Both shapes answer here, which is the point. A **system** family -- Basic
    Wall, Floor -- has no ``Family`` element at all and its name is reached
    from the type's ``FamilyName``; a **loadable** family has a real ``Family``
    and the same property returns it. One accessor, so the picker never has to
    know which it is looking at, and never shows an empty level for one of
    them (``METHODOLOGY.md`` S13.3).
    """
    return names.dedupe([_family_name(one)
                         for one in _types_of(doc, category_names)])


def _types_of(doc, category_names):
    """Every ``ElementType`` in those categories."""
    ids = _category_ids(doc, category_names)
    if ids.Count == 0:
        return []
    return list(FilteredElementCollector(doc)
                .WherePasses(ElementMulticategoryFilter(ids))
                .WhereElementIsElementType()
                .ToElements())


def _family_name(element_type):
    """``"Basic Wall"`` for a WallType, the family's name for a FamilySymbol."""
    if element_type is None:
        return None
    try:
        return element_type.FamilyName
    except Exception:
        return None


def types(doc, category_names, family=None):
    """The type names under those categories, optionally within one family."""
    return names.dedupe([
        compat.element_name(one) for one in _types_of(doc, category_names)
        if not family or names.same(family, _family_name(one))])


def parameters(doc, category_names):
    """``[(name, filterable)]`` for those categories, name-sorted.

    **Every** parameter these categories can carry is offered, and the ones
    Revit will not accept in a native ``ParameterFilterElement`` are flagged
    rather than hidden. That is CRIT-2's answer: pressing a rule isolates, so a
    flagged parameter still makes a perfectly good button.

    Read from **three** sources, in this order, because no one of them is
    complete:

    1. **What Revit says is filterable for the category.** Needs no elements at
       all, so it answers in a model where nothing has been placed yet, and it
       is the only source whose ``filterable`` flag has actually been asked of
       Revit rather than assumed. It goes first for that reason -- ``dedupe``
       keeps the first entry on a name collision.
    2. **A sample of placed elements**, own parameters and their type's. The
       only source for an instance parameter a project has bound but Revit does
       not consider filterable.
    3. **A sample of the types themselves.** Types exist long before anything
       is placed.

    Source 3 is why this function exists in its current shape. Until
    2026-09-10 it read source 2 alone, so a model with 151 column types loaded
    and no columns placed offered **zero** parameters and the Conditions row
    was simply empty, with nothing said about why.
    """
    filterable = _filterable_parameter_ids(doc, category_names)

    rows = [(name, True) for name in _filterable_parameter_names(doc, filterable)]
    for element in _sample(doc, category_names):
        rows.extend(_named_parameters(doc, element, filterable))
    for element_type in _types_of(doc, category_names)[:PARAMETER_SAMPLE]:
        rows.extend(_named_parameters(doc, element_type, filterable))
    return names.dedupe(rows)


def _named_parameters(doc, element, filterable):
    """``[(name, filterable)]`` off one element, its type included."""
    found = []
    for parameter in _parameters_of(doc, element):
        try:
            name = parameter.Definition.Name
        except Exception:
            continue
        if name:
            found.append((name, compat.id_value(parameter.Id) in filterable))
    return found


def _filterable_parameter_names(doc, filterable_ids):
    """The names behind the filterable ids, for the ones that will give one.

    A **project or shared** parameter is an element, so the document knows its
    name. A **built-in** parameter is not: its id is the negative value of the
    ``BuiltInParameter`` enum member, and only ``LabelUtils`` can turn that
    into the words Revit shows -- localised, which is right, because the rest
    of the window is showing the user their own Revit's labels.

    Anything that will not answer is skipped rather than guessed at. It will
    usually be picked up from a sampled element anyway.
    """
    found = []
    for value in filterable_ids:
        name = None
        try:
            element = doc.GetElement(compat.element_id(value))
            if element is not None:
                name = compat.element_name(element)
        except Exception:
            name = None
        if not name:
            try:
                name = LabelUtils.GetLabelFor(BuiltInParameter(value))
            except Exception:
                name = None
        if name:
            found.append(name)
    return found


def _filterable_parameter_ids(doc, category_names):
    """The id values Revit will accept in a view filter for these categories.

    An empty set when Revit refuses the question -- which is the safe answer,
    because it flags everything as non-filterable rather than promising
    something the model will not honour.
    """
    try:
        ids = ParameterFilterUtilities.GetFilterableParametersInCommon(
            doc, _category_ids(doc, category_names))
        return set(compat.id_value(one) for one in ids)
    except Exception:
        return set()


def _sample(doc, category_names):
    """Up to ``PARAMETER_SAMPLE`` elements of those categories."""
    collector = _collector(doc, None, category_names)
    if collector is None:
        return []
    taken = []
    for element in collector:
        taken.append(element)
        if len(taken) >= PARAMETER_SAMPLE:
            break
    return taken


def _parameters_of(doc, element):
    """An element's own parameters, then its type's."""
    found = []
    try:
        found.extend(list(element.Parameters))
    except Exception:
        pass
    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            element_type = doc.GetElement(type_id)
            if element_type is not None:
                found.extend(list(element_type.Parameters))
    except Exception:
        pass
    return found


# ---------------------------------------------------------------------------
# What a rule matches
# ---------------------------------------------------------------------------

def views(doc, active=None):
    """Every view a rule could be applied to, as plain data.

    ``[(id, label, usable, why-not)]`` -- ids and strings only, because a Revit
    object cannot cross to the WPF thread (S12.8.7.2).

    Views that cannot be isolated are **listed anyway**, marked with the
    reason. Hiding them would leave a modeller hunting for a schedule that is
    simply not in the list, with nothing to say it was excluded on purpose.
    Templates are dropped outright: they are not views a person applies to.
    """
    from . import revit_apply

    found = []
    collector = FilteredElementCollector(doc).OfClass(View)
    for view in collector:
        try:
            if view.IsTemplate:
                continue
        except Exception:
            continue
        usable, why = revit_apply.can_isolate(view)
        found.append((compat.id_value(view.Id), revit_apply.view_label(view),
                      usable, why))
    found.sort(key=lambda row: names.key(row[1]))
    if active is not None:
        # The active view first: it is the one a person means most often, and
        # scrolling a list of two hundred to find it is the whole cost.
        found.sort(key=lambda row: row[0] != active)
    return found


def read_value(doc, element, parameter_name):
    """One parameter off an element, as the plain value a rule compares to.

    Instance first, then the type -- which is the order Revit itself resolves
    them, and the order ``anongee_toolkit.revit.parameters`` uses.

    What comes back, and why:

      * **Double** -- the *internal* number (feet, square feet, radians).
        ``values.to_internal`` converts the rule's side to match, so both are
        in the same unit and the comparison is exact rather than rounded
        through a display string.
      * **Integer** -- the int, except a Yes/No, which comes back as a bool so
        that "equals Yes" reads the way a user writes it. Detected from
        ``AsValueString()`` rather than from the parameter's spec, because the
        spec's API moved in 2021 and this has to run on both sides of that. On
        a localised Revit the check simply misses and the int is returned,
        which is a degraded answer rather than a wrong one.
      * **String** -- the string.
      * **ElementId** -- the referenced element's *name*, so "Level equals
        Level 1" works the way it is written.

    ``None`` when the element has no such parameter, which a rule treats as
    "does not match" rather than as an error.
    """
    parameter = _find_parameter(doc, element, parameter_name)
    if parameter is None:
        return None
    try:
        storage = parameter.StorageType
        if storage == StorageType.Double:
            return parameter.AsDouble()
        if storage == StorageType.Integer:
            shown = None
            try:
                shown = parameter.AsValueString()
            except Exception:
                shown = None
            if shown in ("Yes", "No"):
                return shown == "Yes"
            return parameter.AsInteger()
        if storage == StorageType.String:
            return parameter.AsString()
        if storage == StorageType.ElementId:
            referenced = doc.GetElement(parameter.AsElementId())
            if referenced is not None:
                return compat.element_name(referenced)
            return parameter.AsValueString()
    except Exception:
        return None
    return None


def _find_parameter(doc, element, parameter_name):
    """The named parameter on the element, else on its type. ``None`` if absent."""
    try:
        found = element.LookupParameter(parameter_name)
        if found is not None:
            return found
    except Exception:
        pass
    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            element_type = doc.GetElement(type_id)
            if element_type is not None:
                return element_type.LookupParameter(parameter_name)
    except Exception:
        pass
    return None


def element_rows(doc, view, rule, whole_model=False):
    """Every element in *view* of *rule*'s categories, as ``ElementRow``s.

    Only the parameters ``rule`` names are read, and the type of each element
    is fetched once per type rather than once per element -- on a floor plate
    of two thousand walls that is two lookups instead of two thousand.

    The rows are plain data on purpose: they are what crosses to the WPF
    thread, and a Revit ``Element`` cannot (S12.8.7.2).

    With *whole_model* the collector is the DOCUMENT rather than the view, and
    *view* stops deciding what is collected and starts deciding only what
    counts as comparable: anything owned by a **different** view is dropped.
    Without that filter the two passes are not the same question. A model
    element exists once and appears in every view, but a view-specific one --
    a dimension, a text note, a detail line -- exists once per view, so a
    document-wide count of them is the number of views that have any,
    multiplied. That would read as "the view is hiding forty of these" about a
    view hiding none.
    """
    collector = _collector(doc, None if whole_model else view, rule.categories)
    if collector is None:
        return []

    wanted = rule.condition_parameters()
    type_cache = {}
    rows = []
    for element in collector:
        try:
            if whole_model and _owned_elsewhere(element, view):
                continue
            type_id = element.GetTypeId()
            key = compat.id_value(type_id)
            if key not in type_cache:
                element_type = (doc.GetElement(type_id)
                                if type_id and type_id != ElementId.InvalidElementId
                                else None)
                type_cache[key] = (_family_name(element_type),
                                   compat.element_name(element_type))
            family, type_name = type_cache[key]

            row_values = {}
            for parameter_name in wanted:
                row_values[parameter_name] = read_value(doc, element,
                                                        parameter_name)
            rows.append(_rules.ElementRow(compat.id_value(element.Id),
                                          family, type_name, row_values))
        except Exception:
            # One element that will not answer is one element left out, not a
            # run that stops. A model always has something odd in it.
            continue
    return rows


def matching_ids(doc, view, rule):
    """The int ids in *view* that *rule* matches.

    Ints, not ``ElementId``s, because this result crosses to the WPF thread and
    is written into a report the window shows. ``compat.id_list`` turns them
    back at the last moment, inside ``revit_apply``.
    """
    return _rules.select(element_rows(doc, view, rule), rule)


def count(doc, view, rule):
    """How many elements *rule* matches in *view*.

    The number the window shows before anything is applied -- isolating twelve
    thousand elements by accident is slow to do and slower to undo.
    """
    return len(matching_ids(doc, view, rule))


def _owned_elsewhere(element, view):
    """``True`` for an element that belongs to some OTHER view.

    ``OwnerViewId`` is invalid for a model element -- a column is in every view
    that shows it -- and a real view id for the view-specific ones. Anything
    owned by a view that is not *view* is not a thing *view* could have shown,
    so it is not evidence that *view* is hiding anything.
    """
    try:
        owner = element.OwnerViewId
    except Exception:
        return False
    try:
        if owner is None or owner == ElementId.InvalidElementId:
            return False
        if view is None:
            return True
        return compat.id_value(owner) != compat.id_value(view.Id)
    except Exception:
        return False


def model_count(doc, view, rule):
    """How many elements *rule* matches in the MODEL. ``None`` if not measured.

    The other half of the answer, and the one the tool could not give until
    0.8.0. ``count`` above is scoped to the view because that is what an
    isolate operates on -- but ``FilteredElementCollector(doc, view.Id)``
    returns only what the view is **already showing**, so an element hidden in
    the view is invisible to the rule as well. The rule does not fail and the
    count is not wrong; it is a narrower question than the one being asked,
    and until both numbers were on screen together there was no way to tell
    the two apart from the outside.

    ``None`` rather than a wrong number when the model is too big to sweep
    (``AUDIT_CEILING``) or when Revit refuses part of it: the gap is a
    diagnostic, and a diagnostic that guesses is worse than one that abstains.
    """
    try:
        collector = _collector(doc, None, rule.categories)
        if collector is None:
            return None
        if collector.GetElementCount() > AUDIT_CEILING:
            return None
        return len(_rules.select(
            element_rows(doc, view, rule, whole_model=True), rule))
    except Exception:
        return None


def audit(doc, view, rule):
    """``(in_view, in_model)`` -- what the isolate will show, and what exists.

    ``in_model`` is ``None`` when it was not measured. ``diagnostics.gap``
    turns the pair into the sentence the user reads.
    """
    return (count(doc, view, rule), model_count(doc, view, rule))


def resolve(doc, rule):
    """What of *rule*'s cascade this project actually has.

    ``[]`` means the rule is usable here. Anything else is a sentence naming
    what could not be found, and the window greys the rule and shows it.

    **The rule is never rewritten or deleted.** Losing somebody's rule because
    they opened a different model is the worst thing this tool could do, and a
    rule that does not fit today may fit the next model they open
    (``PRD.md`` S5.1).
    """
    missing = []
    have = dict((names.key(name), name) for name, _ in categories(doc))
    for wanted in rule.categories:
        if names.key(wanted) not in have:
            missing.append("this project has no category {0!r}".format(wanted))
    if missing:
        return missing

    if rule.family:
        if not any(names.same(rule.family, one)
                   for one in families(doc, rule.categories)):
            missing.append("no family {0!r} in {1}".format(
                rule.family, " + ".join(rule.categories)))
    if rule.type_name:
        if not any(names.same(rule.type_name, one)
                   for one in types(doc, rule.categories, rule.family)):
            missing.append("no type {0!r} in {1}".format(
                rule.type_name, rule.family or " + ".join(rule.categories)))
    return missing
