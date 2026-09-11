# -*- coding: utf-8 -*-
"""FEAT-13 -- create a real ``ParameterFilterElement`` from a saved rule.

The ONLY module in this tool that writes to the project. Everything else is
temporary and leaves no trace; this creates an element that appears in
Manage > Filters, survives a save, prints, and is visible to everyone who
opens the model.

So it is never automatic, never a side effect of Apply, and the window asks
first with ``filters.plan()`` on screen -- the name, the categories and every
rule that is about to be created, spelled out.

Whether a rule MAY be converted is decided in ``filters``, which has no Revit
in it and is tested. This module builds and creates, and does neither unless
that one said yes.
"""

from __future__ import division

import clr

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import (ElementId, ElementParameterFilter,             # noqa: E402
                               FilteredElementCollector, LogicalAndFilter,
                               LogicalOrFilter, ParameterFilterElement,
                               ParameterFilterRuleFactory,
                               ParameterFilterUtilities, Transaction)
from System.Collections.Generic import List                                   # noqa: E402

from . import compat
from . import filters
from . import names

TRANSACTION_NAME = "AnonGee - create view filter"

#: How close two numbers must be for Revit to call them equal. Revit's own
#: numeric filter rules take an epsilon and will not accept zero; this is the
#: same order as the tolerance the rule engine compares with.
EPSILON = 1e-9


def category_ids(doc, wanted):
    """``(List[ElementId], missing names)`` for the categories *wanted*.

    Matched Revit's way -- case and whitespace insensitive -- because a rule
    stores a NAME and this project may spell it differently.
    """
    by_key = {}
    for category in doc.Settings.Categories:
        try:
            by_key[names.key(category.Name)] = category.Id
        except Exception:
            continue
    found = List[ElementId]()
    missing = []
    for name in wanted or []:
        got = by_key.get(names.key(name))
        if got is None:
            missing.append(name)
        else:
            found.Add(got)
    return found, missing


def filterable_names(doc, ids):
    """The parameter names Revit will filter on for these categories."""
    found = []
    try:
        for parameter_id in ParameterFilterUtilities.GetFilterableParametersInCommon(doc, ids):
            try:
                found.append(_parameter_name(doc, parameter_id))
            except Exception:
                continue
    except Exception:
        return []
    return [name for name in found if name]


def _parameter_name(doc, parameter_id):
    from Autodesk.Revit.DB import LabelUtils
    raw = compat.id_value(parameter_id)
    if raw < 0:
        return LabelUtils.GetLabelFor(_builtin(raw))
    element = doc.GetElement(parameter_id)
    return element.Name if element is not None else ""


def _builtin(raw):
    from Autodesk.Revit.DB import BuiltInParameter
    return BuiltInParameter(raw)


def _parameter_id(doc, ids, wanted):
    """The ElementId of the filterable parameter Revit calls *wanted*."""
    for parameter_id in ParameterFilterUtilities.GetFilterableParametersInCommon(doc, ids):
        try:
            if names.same(_parameter_name(doc, parameter_id), wanted):
                return parameter_id
        except Exception:
            continue
    return None


def _rule_for(doc, ids, condition):
    """One ``FilterRule``, or ``(None, why)``.

    The factory method is looked up **by name** from ``filters.FACTORY``
    rather than imported: the set of rules Revit offers has changed across
    releases, and a missing method should read as "this Revit cannot do that
    one" rather than as an import error at load time.
    """
    parameter_id = _parameter_id(doc, ids, condition.parameter)
    if parameter_id is None:
        return None, ("Revit will not filter on {0!r} for these "
                      "categories".format(condition.parameter))

    method_name = filters.FACTORY.get(condition.operator)
    if not method_name:
        return None, "{0!r} has no Revit filter rule".format(condition.operator)
    maker = getattr(ParameterFilterRuleFactory, method_name, None)
    if maker is None:
        return None, ("this Revit has no {0}, so {1!r} cannot be "
                      "converted".format(method_name, condition.operator))

    # What the value IS -- number or text, and in which units -- is decided in
    # ``filters``, which is tested. This module only hands it over.
    try:
        kind, value = filters.rule_value(condition)
    except (ValueError, TypeError) as error:
        # Not Revit refusing: the rule's own value cannot be read. Saying
        # "Revit refused" here would send somebody looking in the wrong place.
        return None, "could not read the value for {0!r}: {1}".format(
            condition.parameter, error)
    try:
        if kind == filters.NO_VALUE:
            return maker(parameter_id), ""
        if kind == filters.NUMBER:
            return maker(parameter_id, value, EPSILON), ""
        return maker(parameter_id, value, False), ""
    except Exception as error:
        return None, "Revit refused {0!r}: {1}".format(condition.parameter,
                                                       error)


def build(doc, rule):
    """``(ElementFilter, ids, why-not)`` for *rule*, without creating anything.

    Separate from ``create`` so the caller can find out that a rule will not
    build **before** opening a transaction. An exception inside a transaction
    is recoverable; it is still better not to have opened one.
    """
    ids, missing = category_ids(doc, rule.categories)
    if missing:
        return None, None, ("this project has no category called {0}".format(
            ", ".join(repr(name) for name in missing)))
    if ids.Count == 0:
        return None, None, "the rule names no categories this project has"

    allowed, reasons = filters.convertible(rule, filterable_names(doc, ids))
    if not allowed:
        return None, None, "; ".join(reasons)

    built = []
    for condition in rule.conditions:
        made, why = _rule_for(doc, ids, condition)
        if made is None:
            return None, None, why
        built.append(ElementParameterFilter(made))

    if not built:
        # A filter with no rules is legal and matches the categories whole,
        # which is exactly what a rule with no conditions means here.
        return None, ids, ""

    if len(built) == 1:
        return built[0], ids, ""

    combined = built[0]
    for extra in built[1:]:
        combined = (LogicalAndFilter(combined, extra)
                    if rule.match == "all"
                    else LogicalOrFilter(combined, extra))
    return combined, ids, ""


def existing(doc, name):
    """The filter already called *name*, or ``None``. Revit's name matching."""
    for element in FilteredElementCollector(doc).OfClass(ParameterFilterElement):
        try:
            if names.same(element.Name, name):
                return element
        except Exception:
            continue
    return None


def create(doc, rule, replace=False):
    """Create the view filter. ``(element id, message)``.

    ``(0, why)`` when nothing was created, and *why* is a sentence.

    **An existing filter of the same name is never overwritten** unless
    *replace* says so. Somebody else's filter with the same label is not this
    rule's to redefine, and a filter is used by views -- replacing one changes
    what those views show, at a distance, with nothing on screen to say so.
    """
    wanted = filters.filter_name(rule)
    already = existing(doc, wanted)
    if already is not None and not replace:
        return (0, "{0!r} already exists in Manage > Filters. Rename the rule, "
                   "or delete that filter first.".format(wanted))

    element_filter, ids, why = build(doc, rule)
    if why:
        return (0, why)

    transaction = Transaction(doc, TRANSACTION_NAME)
    try:
        transaction.Start()
        if already is not None:
            doc.Delete(already.Id)
        made = ParameterFilterElement.Create(doc, wanted, ids)
        if element_filter is not None:
            made.SetElementFilter(element_filter)
        transaction.Commit()
    except Exception as error:
        # S12.9.4: gated rollback, never an orphaned transaction.
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass
        return (0, "Revit refused to create the filter: {0}".format(error))
    return (compat.id_value(made.Id), "")
