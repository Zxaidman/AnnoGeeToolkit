# -*- coding: utf-8 -*-
"""FEAT-13 -- can this rule become a real Revit view filter, and what of it?

Everything that DECIDES lives here and nothing that touches Revit does, for
the usual reason: this half can be run by the test suite and the other half
cannot. ``revit_filter`` builds the ``ParameterFilterElement``; this works out
whether it should be allowed to try, and says why not in words a modeller can
act on.

WHY THIS IS OPT-IN AND WILL STAY THAT WAY
-----------------------------------------
Everything else this tool does is temporary and leaves no trace: pressing a
rule isolates in the active view and writes NOTHING to the project. That was
the first decision made about it and it has not moved.

This one writes. It creates a ``ParameterFilterElement`` that appears in
Manage > Filters, survives a save, prints, and is visible to everyone who opens
the model. So it is never automatic, never a side effect of Apply, and the
window asks first with the name of the thing it is about to create.

WHY A RULE CAN BE REFUSED
-------------------------
Revit's own filters are narrower than this tool's rules, and a rule that
cannot be expressed as one has to be refused rather than half-converted:

* **A parameter Revit will not filter on.** The CRIT-2 flag already marks
  these in the window with "(no view filter)" -- they still make a perfectly
  good rule here, because pressing a rule isolates rather than filtering.
* **``between``.** Revit has no between; it is two rules joined by AND, and
  silently splitting one condition into two would make the filter say
  something the rule does not.
* **No categories.** A ``ParameterFilterElement`` is defined over categories
  and cannot exist without at least one.
A family or type narrowing used to be refused for the same reason -- matched
by name here, and a parameter filter cannot narrow by family in general. That
was wrong, and the project owner found the way round it by hand: Revit exposes
**Family Name** and **Type Name** as filterable parameters, so the narrowing
becomes two more conditions rather than an impossibility. ``expand`` does that,
and the conversion is refused only when this project will not filter on those
two parameters for these categories.

Same five rules as the rest of ``lib/``: 2.7 and 3.12 alike, pure ASCII, no
``re``, no ``anongee_toolkit``.
"""

from __future__ import division

from . import names
from . import rules as _rules
from . import values

#: Our operator key to the ``ParameterFilterRuleFactory`` method that makes it.
#: Resolved by NAME at call time in ``revit_filter`` rather than imported here,
#: because this module must import on a machine with no Revit.
FACTORY = {
    "equals": "CreateEqualsRule",
    "not_equals": "CreateNotEqualsRule",
    "contains": "CreateContainsRule",
    "not_contains": "CreateNotContainsRule",
    "begins_with": "CreateBeginsWithRule",
    "ends_with": "CreateEndsWithRule",
    "greater": "CreateGreaterRule",
    "greater_equal": "CreateGreaterOrEqualRule",
    "less": "CreateLessRule",
    "less_equal": "CreateLessOrEqualRule",
    "is_empty": "CreateHasNoValueParameterRule",
    "is_not_empty": "CreateHasValueParameterRule",
}

#: The parameters Revit exposes for what this tool calls a family and a type
#: narrowing. They are ordinary filterable parameters, which is what makes the
#: workaround work: a narrowing becomes two more conditions.
FAMILY_PARAMETER = "Family Name"
TYPE_PARAMETER = "Type Name"

#: What a created filter is called when nobody has said otherwise. It is a
#: DEFAULT and not a rule: a filter lands in a list the whole team shares, so
#: it wants a prefix -- but which prefix is the team's business, not ours.
DEFAULT_PREFIX = "AnonGee - "

#: Operators this tool has and Revit's filters do not. Listed rather than
#: inferred from FACTORY's gaps, so that a typo in FACTORY reads as a missing
#: mapping rather than as a deliberate exclusion.
UNSUPPORTED = ("between",)


def expand(rule):
    """*rule* with its family and type narrowing turned into conditions.

    Revit's filters cannot narrow by family or type directly, but they CAN
    filter on the **Family Name** and **Type Name** parameters -- which is the
    same thing said in the only language a ``ParameterFilterElement`` speaks.

    The narrowing goes on the FRONT, because it is read as the cascade: a
    person looking at the created filter sees family, then type, then their
    own conditions, in the order they built them.

    Returns the rule unchanged when there is nothing to move, so the caller
    never has to ask.
    """
    if not rule.family and not rule.type_name:
        return rule
    added = []
    if rule.family:
        added.append(_rules.Condition(FAMILY_PARAMETER, "equals", rule.family))
    if rule.type_name:
        added.append(_rules.Condition(TYPE_PARAMETER, "equals", rule.type_name))
    grown = _rules.Rule.from_dict(rule.to_dict())
    grown.family = None
    grown.type_name = None
    grown.conditions = added + list(rule.conditions)
    return grown


def convertible(rule, filterable=None):
    """``(True, [])`` if *rule* can become a view filter, else ``(False, why)``.

    *filterable* is the set of parameter names Revit says it will filter on --
    the CRIT-2 answer, gathered from the model. ``None`` means "not checked",
    for the case where the caller only wants the shape of the rule judged.

    Every reason is collected rather than the first one returned. A modeller
    fixing a rule wants to know about all three problems at once, not to
    discover the second after fixing the first.
    """
    reasons = []
    rule = expand(rule)

    if not rule.categories:
        reasons.append("a Revit view filter is defined over categories, and "
                       "this rule has none")

    known = None if filterable is None else set(
        names.key(name) for name in filterable)

    for condition in rule.conditions:
        if condition.operator in UNSUPPORTED:
            reasons.append(
                "Revit has no {0!r} filter rule; it is two rules joined by "
                "AND, and splitting one condition in two would make the "
                "filter say something the rule does not".format(
                    values.operator_label(condition.operator)
                    or condition.operator))
            continue
        if condition.operator not in FACTORY:
            reasons.append("{0!r} has no Revit filter rule behind it".format(
                values.operator_label(condition.operator)
                or condition.operator))
            continue
        if known is not None and names.key(condition.parameter) not in known:
            if condition.parameter in (FAMILY_PARAMETER, TYPE_PARAMETER):
                reasons.append(
                    "this project will not filter on {0!r} for these "
                    "categories, so the family and type narrowing cannot be "
                    "carried over. Remove it, or put the narrowing in as "
                    "conditions Revit does offer".format(condition.parameter))
            else:
                reasons.append(
                    "Revit will not filter on {0!r} -- it is the "
                    "\"(no view filter)\" mark in the parameter list. The rule "
                    "still works here, because pressing it isolates rather "
                    "than filtering".format(condition.parameter))

    return (not reasons), reasons


#: What ``rule_value`` says a condition's value is.
NO_VALUE = "none"
TEXT = "text"
NUMBER = "number"


def rule_value(condition):
    """``(kind, value)`` -- what Revit's rule factory should be handed.

    Here rather than in ``revit_filter`` because it is a **decision**, not a
    Revit call: whether a typed value is a number, and what that number is in
    Revit's internal units. ``tests/test_filterrules.py`` refuses to let a
    Revit module import ``values`` for exactly this reason -- a conversion
    made over there is one no test on this machine can reach, and "100 m2"
    arriving as 100 square FEET is the kind of bug that looks like the filter
    simply matching the wrong things.

    ``(NO_VALUE, None)`` for an operator that takes none, ``(NUMBER, feet)``
    for anything that parses as a number, ``(TEXT, string)`` otherwise.
    """
    if condition.operator in values.VALUELESS_OPERATORS:
        return NO_VALUE, None

    # ``Condition.expected()`` is the ONE place a rule's value is turned into
    # what Revit stores -- units, ``between``, numbers typed as text. Deriving
    # it again here is how the two drift, and the first draft of this function
    # did exactly that: it handed ``parse_number``'s (value, unit) TUPLE
    # straight to ``to_internal``, which the tests caught immediately.
    expected = condition.expected()

    #: A bool is an int in Python, and "yes"/"no" is text to Revit.
    if isinstance(expected, bool):
        return TEXT, "yes" if expected else "no"
    if isinstance(expected, (int, float)):
        return NUMBER, float(expected)

    parsed = values.parse_number(expected)
    if parsed is None:
        return TEXT, "{0}".format(expected)
    return NUMBER, float(parsed[0])


def filter_name(rule, prefix=None):
    """What the created filter is called in Manage > Filters.

    Prefixed by default, because it lands in a list a whole team shares and
    "Columns" on its own tells the next person nothing about where it came
    from or whether deleting it will break something.

    *prefix* is the team's to choose, including choosing none -- pass ``""``
    for the bare rule name. ``None`` means "whatever the default is".
    """
    plain = (rule.name or "unnamed rule").strip()
    if prefix is None:
        prefix = DEFAULT_PREFIX
    return "{0}{1}".format(prefix, plain)


def prefix_of(chosen, rule):
    """The prefix implied by *chosen* being the name for *rule*.

    Typing "STR - Columns" over "AnonGee - Columns" for a rule called
    "Columns" means the prefix is now "STR - ", and the next filter should be
    offered that. Deriving it beats a second control nobody would find.

    ``None`` when the typed name does not end with the rule's name -- they
    renamed this one filter rather than changing a convention, and guessing a
    prefix from it would make every later name wrong.
    """
    plain = (rule.name or "unnamed rule").strip()
    chosen = "{0}".format(chosen or "").strip()
    if not plain or not chosen.endswith(plain):
        return None
    return chosen[:len(chosen) - len(plain)]


def plan(rule, prefix=None):
    """The lines the confirmation dialog shows before anything is created.

    Spelled out per condition rather than summarised, because this is the one
    action in the tool that writes to the model, and "create a filter from
    this rule" is not enough for somebody to say yes to.
    """
    rule = expand(rule)
    lines = ["Name: {0}".format(filter_name(rule, prefix)),
             "Categories: {0}".format(", ".join(sorted(rule.categories))
                                      or "(none)")]
    if not rule.conditions:
        lines.append("Rules: none -- it will match everything in those "
                     "categories")
        return lines
    joiner = "ALL of" if rule.match == "all" else "ANY of"
    lines.append("Rules ({0}):".format(joiner))
    for condition in rule.conditions:
        lines.append("    {0}".format(_condition_line(condition)))
    return lines


def _condition_line(condition):
    label = values.operator_label(condition.operator) or condition.operator
    if condition.operator in values.VALUELESS_OPERATORS:
        return "{0} {1}".format(condition.parameter, label)
    unit = " {0}".format(condition.unit) if condition.unit else ""
    return "{0} {1} {2}{3}".format(condition.parameter, label,
                                   condition.value, unit)
