# -*- coding: utf-8 -*-
"""What a rule is: Category > Family > Type > Parameter conditions.

Three classes, and no Revit in any of them:

    ``Condition``  one parameter test -- "Area is greater than 100 m2"
    ``Rule``       a named, saved narrowing, and the button it becomes
    ``RuleSet``    the ordered list, with add / remove / duplicate / move

**Every reference is a string.** ``"Walls"``, ``"Basic Wall"``,
``"100mm Gypsum Wall"`` -- never an ``ElementId``. ``cad2bim/settings.py``
states the reason: *"ids do not survive a session, let alone another project,
and a label that no longer exists simply leaves that combo alone."* A rule
carrying ids would be worthless the moment it opened in another model, which is
the entire feature.

**Every level below the category is optional.** A rule of ``Walls`` alone
matches every wall; ``Walls > Area > 100 m2`` skips family and type. Making
them mandatory would make "all the structural columns" impossible to say.

**A rule with no conditions matches everything in its cascade**, and that is a
legitimate rule, not an empty one.

**Reading is forgiving; writing is exact.** ``from_dict`` takes what it
recognises and ignores the rest, so a file written by a later build still
loads. Nothing here raises on bad input -- a rules file somebody edited by hand
must not take the window down with it.
"""

from __future__ import division

from . import names
from . import values

#: What a rule's ``match`` may be, and what it means.
MATCH_ALL = "all"
MATCH_ANY = "any"
MATCH_MODES = (MATCH_ALL, MATCH_ANY)

#: Bumped only when a *counter* is needed within the same clock tick. Module
#: state, which is safe here: the window is single-threaded on the WPF side and
#: ids are only ever minted there.
_counter = [0]


#: Where ``RuleSet.reorder`` puts a block of rules. Strings rather than an
#: enum because they cross into the window's own code and into no file --
#: nothing serialises these, so they are named for reading, not for storing.
UP = "up"
DOWN = "down"
TOP = "top"
BOTTOM = "bottom"

#: Every destination, for a caller that wants to check one before using it.
DESTINATIONS = (UP, DOWN, TOP, BOTTOM)


def new_rule_id():
    """A short, stable, sortable id for a rule.

    Stable is the point: it is the key the dockable panel's button is drawn
    from, so it must survive a rename, a reorder and a round trip through the
    file. Made from the clock plus a counter, because two rules made in the
    same tick still have to differ.
    """
    import time                      # local: keeps module import cheap at load
    _counter[0] += 1
    return "r-{0:x}-{1:04x}".format(int(time.time() * 1000), _counter[0] % 0xFFFF)


def _text(value, fallback=""):
    """*value* as stripped text, or *fallback* when there is nothing there."""
    if value is None:
        return fallback
    body = "{0}".format(value).strip()
    return body if body else fallback


class Condition(object):
    """One parameter test inside a rule.

    ``value`` is what the user typed, in ``unit``. It is converted into Revit's
    internal unit at compare time, never at save time -- storing the converted
    number would lose which unit the rule was written in, and that cannot be
    recovered afterwards.

    ``filterable`` records whether Revit would accept this parameter in a
    native ``ParameterFilterElement``. Nothing here uses it: pressing a rule
    isolates. It is carried because it is honest about what Revit can do with
    the rule, and because it is exactly the check FEAT-13 would need.
    """

    __slots__ = ("parameter", "operator", "value", "unit", "filterable")

    def __init__(self, parameter="", operator="equals", value=None, unit="",
                 filterable=True):
        self.parameter = _text(parameter)
        # Kept as given even when unknown, so problems() can name it. matches()
        # answers False for anything it cannot evaluate, so nothing downstream
        # is at risk -- and a typo in a hand-edited file that silently became
        # "equals" would be a rule quietly meaning something else.
        self.operator = _text(operator, "equals")
        self.value = value
        self.unit = _text(unit)
        self.filterable = bool(filterable)

    # -- serialisation ------------------------------------------------------

    def to_dict(self):
        return {"parameter": self.parameter,
                "operator": self.operator,
                "value": list(self.value) if isinstance(self.value, tuple)
                         else self.value,
                "unit": self.unit,
                "filterable": self.filterable}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            data = {}
        value = data.get("value")
        if isinstance(value, list):
            value = tuple(value)
        return cls(parameter=data.get("parameter", ""),
                   operator=data.get("operator", "equals"),
                   value=value,
                   unit=data.get("unit", ""),
                   filterable=data.get("filterable", True))

    # -- behaviour ----------------------------------------------------------

    def expected(self):
        """The rule's value in Revit's internal unit, ready for ``compare``.

        Raises ``ValueError`` for a unit this build does not know -- which
        ``matches`` turns into "does not match" rather than letting it out.
        """
        if self.operator in values.VALUELESS_OPERATORS:
            return None
        if self.operator == "between":
            try:
                low, high = self.value
            except (TypeError, ValueError):
                raise ValueError("'between' needs two numbers")
            return (values.to_internal(low, self.unit),
                    values.to_internal(high, self.unit))
        if self.unit and isinstance(self.value, (int, float)):
            return values.to_internal(self.value, self.unit)
        if self.unit:
            parsed = values.parse_number(self.value)
            if parsed is None:
                raise ValueError("not a number: {0!r}".format(self.value))
            return values.to_internal(parsed[0], self.unit)
        return self.value

    def matches(self, actual):
        """Whether *actual*, straight off the element, satisfies this.

        Never raises. A condition this build cannot evaluate -- an unknown
        unit, a malformed ``between`` -- does not match, and ``problems()``
        says why. The window greys it; the session continues.
        """
        try:
            return values.compare(actual, self.operator, self.expected())
        except (ValueError, TypeError):
            return False

    def problems(self):
        """Sentences for a human. ``[]`` means this condition is usable."""
        found = []
        if not self.parameter:
            found.append("a condition has no parameter")
        if not values.is_operator(self.operator):
            found.append("{0!r} is not an operator this build knows".format(
                self.operator))
            return found
        if not values.is_known_unit(self.unit):
            found.append("{0!r} is not a unit this build knows".format(self.unit))
        if self.operator in values.VALUELESS_OPERATORS:
            return found
        if self.operator == "between":
            pair = self.value
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                found.append("'{0} is between' needs two numbers".format(
                    self.parameter or "a parameter"))
            elif any(values.parse_number(part) is None for part in pair):
                found.append("'{0} is between' needs two numbers".format(
                    self.parameter or "a parameter"))
        elif self.operator in values.NUMERIC_OPERATORS:
            if values.parse_number(self.value) is None:
                found.append("'{0} {1}' needs a number, not {2!r}".format(
                    self.parameter or "a parameter",
                    values.operator_label(self.operator), self.value))
        elif self.value is None or _text(self.value) == "":
            found.append("'{0} {1}' has no value".format(
                self.parameter or "a parameter",
                values.operator_label(self.operator)))
        return found


class Rule(object):
    """A named narrowing, and the button it becomes.

    ``source`` says which store it was loaded from. It is set by ``store`` and
    is deliberately **not** serialised -- where a rule came from is a fact
    about the file it was in, not about the rule, and writing it would make a
    project rule copied to the machine store lie about itself.
    """

    __slots__ = ("id", "name", "order", "categories", "family", "type_name",
                 "match", "conditions", "source")

    def __init__(self, name="", categories=None, family=None, type_name=None,
                 match=MATCH_ALL, conditions=None, id=None, order=0,
                 source=""):
        self.id = id or new_rule_id()
        self.name = _text(name)
        self.order = int(order or 0)
        self.categories = [_text(c) for c in (categories or []) if _text(c)]
        self.family = _text(family) or None
        self.type_name = _text(type_name) or None
        # Unlike the operator above, an unrecognised match mode IS folded to a
        # default: there are only two, every condition stays evaluable either
        # way, and "all" is the narrower reading of an ambiguous file.
        self.match = match if match in MATCH_MODES else MATCH_ALL
        self.conditions = list(conditions or [])
        self.source = source

    # -- serialisation ------------------------------------------------------

    def to_dict(self):
        return {"id": self.id,
                "name": self.name,
                "order": self.order,
                "categories": list(self.categories),
                "family": self.family,
                "type": self.type_name,
                "match": self.match,
                "conditions": [c.to_dict() for c in self.conditions]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("a rule must be an object")
        raw = data.get("conditions")
        conditions = [Condition.from_dict(c) for c in raw
                      if isinstance(c, dict)] if isinstance(raw, list) else []
        categories = data.get("categories")
        if not isinstance(categories, list):
            categories = []
        return cls(id=data.get("id"),
                   name=data.get("name", ""),
                   order=data.get("order", 0),
                   categories=categories,
                   family=data.get("family"),
                   type_name=data.get("type"),
                   match=data.get("match", MATCH_ALL),
                   conditions=conditions)

    # -- behaviour ----------------------------------------------------------

    def matches_values(self, parameter_values):
        """Whether an element whose parameters are *parameter_values* passes.

        *parameter_values* is ``{parameter name: value}`` read off one element
        -- plain data, because a Revit object cannot cross to the WPF thread
        (S12.8.7.2). A parameter the element does not have is simply absent,
        and a condition on it does not match.

        No conditions means yes: the cascade already said which elements these
        are, and "all the structural columns" is a rule worth having.
        """
        if not self.conditions:
            return True
        results = (condition.matches(parameter_values.get(condition.parameter))
                   for condition in self.conditions)
        return all(results) if self.match == MATCH_ALL else any(results)

    def condition_parameters(self):
        """The parameter names this rule needs read off an element, in order.

        The Revit half reads **only** these. Reading every parameter of every
        element is the difference between a live count and a frozen window on
        a real model, and nothing outside a condition is ever looked at.
        """
        seen, wanted = set(), []
        for condition in self.conditions:
            if condition.parameter and condition.parameter not in seen:
                seen.add(condition.parameter)
                wanted.append(condition.parameter)
        return wanted

    def matches_element(self, family=None, type_name=None,
                        parameter_values=None):
        """The whole cascade below the category, against one element's facts.

        The category is settled by the collector before this is reached -- it
        is what a ``FilteredElementCollector`` is for, and re-checking it here
        would be slower and no safer.

        Family and type are compared **Revit's way** (``names.same``), and an
        empty one on the rule means "any", which is how "all the walls" is
        said.
        """
        if self.family and not names.same(self.family, family):
            return False
        if self.type_name and not names.same(self.type_name, type_name):
            return False
        return self.matches_values(parameter_values or {})

    def wants_category(self, category_name):
        return any(names.same(category_name, mine) for mine in self.categories)

    def problems(self):
        """Sentences for a human. ``[]`` means the rule is usable."""
        found = []
        if not self.name:
            found.append("the rule has no name")
        if not self.categories:
            found.append("{0}: no category chosen".format(self.name or "a rule"))
        for condition in self.conditions:
            found.extend(condition.problems())
        return found

    def summary(self):
        """The cascade as one line, for a tooltip or a list row."""
        parts = [" + ".join(self.categories) or "no category"]
        if self.family:
            parts.append(self.family)
        if self.type_name:
            parts.append(self.type_name)
        for condition in self.conditions:
            parts.append("{0} {1} {2}{3}".format(
                condition.parameter,
                values.operator_label(condition.operator),
                "" if condition.operator in values.VALUELESS_OPERATORS
                else condition.value,
                (" " + condition.unit) if condition.unit else "").strip())
        return " > ".join(parts)


class ElementRow(object):
    """One element, reduced to the plain facts a rule is decided on.

    This is the whole reason the matching half is testable. The Revit side
    collects these -- an int id, two names, and only the parameters the rule
    actually asked for -- and everything after it is arithmetic on plain data.

    It is also what has to cross the thread boundary: a Revit ``Element``
    cannot reach the WPF thread (brand guidelines S12.8.7.2), and an int can.
    """

    __slots__ = ("id", "family", "type_name", "values")

    def __init__(self, id=0, family=None, type_name=None, values=None):
        self.id = id
        self.family = family
        self.type_name = type_name
        self.values = values or {}

    def matches(self, rule):
        return rule.matches_element(self.family, self.type_name, self.values)


def select(rows, rule):
    """The ids of the *rows* that *rule* matches, in the order given.

    Pure, and therefore the part of "what does this rule actually match" that
    can be proved before a model ever sees it.
    """
    return [row.id for row in rows if row.matches(rule)]


class RuleSet(object):
    """The saved rules, in the order the panel draws their buttons.

    Names are **not** unique and are not made unique. The id identifies a rule;
    a machine rule and a project rule may legitimately share a name, and both
    are shown with their source marked rather than one quietly winning.
    """

    def __init__(self, rules=None):
        self._rules = list(rules or [])
        self._renumber()

    # -- collection -------------------------------------------------------

    def __iter__(self):
        return iter(self._rules)

    def __len__(self):
        return len(self._rules)

    def __getitem__(self, index):
        return self._rules[index]

    # -- editing ----------------------------------------------------------

    def _renumber(self):
        for position, rule in enumerate(self._rules):
            rule.order = position

    def add(self, rule):
        """Append *rule* and return it."""
        self._rules.append(rule)
        self._renumber()
        return rule

    def find(self, rule_id):
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        return None

    def remove(self, rule_id):
        """``True`` if something was removed."""
        rule = self.find(rule_id)
        if rule is None:
            return False
        self._rules.remove(rule)
        self._renumber()
        return True

    def duplicate(self, rule_id):
        """A copy with a new id and a name that says it is a copy.

        ``None`` if there is nothing to copy. The name is disambiguated by
        counting, so duplicating twice gives "copy" and "copy 2" rather than
        two rules a user cannot tell apart in a list of buttons.
        """
        original = self.find(rule_id)
        if original is None:
            return None
        copy = Rule.from_dict(original.to_dict())
        copy.id = new_rule_id()
        copy.name = self._free_name("{0} copy".format(original.name))
        return self.add(copy)

    def _free_name(self, wanted):
        taken = set(names.key(rule.name) for rule in self._rules)
        if names.key(wanted) not in taken:
            return wanted
        suffix = 2
        while names.key("{0} {1}".format(wanted, suffix)) in taken:
            suffix += 1
        return "{0} {1}".format(wanted, suffix)

    def move(self, rule_id, position):
        """Move a rule to *position*, clamped into range. ``True`` if moved."""
        rule = self.find(rule_id)
        if rule is None:
            return False
        self._rules.remove(rule)
        position = max(0, min(int(position), len(self._rules)))
        self._rules.insert(position, rule)
        self._renumber()
        return True

    def merge(self, incoming, source=""):
        """Add every rule in *incoming*. ``(added, renamed)``.

        **Nothing already here is ever replaced**, and that is the whole
        design. A rule set arriving from someone else is a gift, not an
        instruction: it cannot silently redefine a rule its recipient has been
        using, because the recipient would have no way of noticing.

        So every incoming rule gets:

        * a **new id**, because two people's rule sets are generated
          independently and a collision would make one rule overwrite the
          other on the next save;
        * a **free name** if the name is taken, counted the same way
          ``duplicate`` counts, so the two are distinguishable in a list of
          buttons rather than being two rows reading the same thing.

        Importing the same file twice therefore gives "X" and "X 2" rather
        than one of them winning. That is noisy on purpose: the count comes
        back so the window can say it out loud.
        """
        added = 0
        renamed = 0
        for rule in incoming:
            copy = Rule.from_dict(rule.to_dict())
            copy.id = new_rule_id()
            free = self._free_name(copy.name)
            if names.key(free) != names.key(copy.name):
                renamed += 1
                copy.name = free
            copy.source = source
            self.add(copy)
            added += 1
        return added, renamed

    def reorder(self, rule_ids, where):
        """Move several rules as a block. ``True`` if anything moved.

        *where* is ``UP``, ``DOWN``, ``TOP`` or ``BOTTOM``. The selection keeps
        its own relative order wherever it lands, which is what a person means
        by "move these up" and is not what moving them one at a time does --
        that reverses them, or collapses them onto each other, depending on
        which end you start from.

        A **non-contiguous** selection is the case worth being careful about.
        Stepping is done by swapping each chosen rule with its unchosen
        neighbour, walking top-down to go up and bottom-up to go down, so a
        chosen rule already sitting against another chosen one is not dragged
        through it. Two rules picked from opposite ends of the list travel
        independently and both stop when they reach the edge.

        Ids that are not in the set are ignored rather than refused: the
        window's selection and the rules on disk can disagree for one redraw.
        """
        wanted = set(rule_ids or ())
        chosen = [rule for rule in self._rules if rule.id in wanted]
        if not chosen or len(chosen) == len(self._rules):
            # Everything selected: every destination is the order it is in.
            return False

        if where == TOP:
            rest = [rule for rule in self._rules if rule.id not in wanted]
            ordered = chosen + rest
        elif where == BOTTOM:
            rest = [rule for rule in self._rules if rule.id not in wanted]
            ordered = rest + chosen
        elif where in (UP, DOWN):
            step = -1 if where == UP else 1
            ordered = list(self._rules)
            positions = (range(len(ordered)) if step < 0
                         else range(len(ordered) - 1, -1, -1))
            for index in positions:
                if ordered[index].id not in wanted:
                    continue
                target = index + step
                if target < 0 or target >= len(ordered):
                    continue
                if ordered[target].id in wanted:
                    continue          # blocked by another chosen rule
                ordered[index], ordered[target] = ordered[target], ordered[index]
        else:
            return False

        if [rule.id for rule in ordered] == [rule.id for rule in self._rules]:
            return False
        self._rules = ordered
        self._renumber()
        return True

    def remove_many(self, rule_ids):
        """Remove several rules. Returns how many actually went."""
        wanted = set(rule_ids or ())
        keep = [rule for rule in self._rules if rule.id not in wanted]
        gone = len(self._rules) - len(keep)
        if gone:
            self._rules = keep
            self._renumber()
        return gone

    # -- serialisation ----------------------------------------------------

    def to_list(self):
        return [rule.to_dict() for rule in self._rules]

    @classmethod
    def from_list(cls, data, source=""):
        """Build from a list of dicts, skipping anything unreadable.

        A row that is not a rule is dropped rather than raising: one corrupt
        entry in a hand-edited file must not cost the user the other nine.
        Order comes from each rule's own ``order``, not from the list, so a
        file written by a build that sorted differently still restores the
        order the user arranged.
        """
        built = []
        if isinstance(data, list):
            for row in data:
                try:
                    rule = Rule.from_dict(row)
                except (ValueError, TypeError, AttributeError):
                    continue
                rule.source = source
                built.append(rule)
        built.sort(key=lambda rule: rule.order)
        return cls(built)

    def problems(self):
        found = []
        for rule in self._rules:
            found.extend(rule.problems())
        return found
