# -*- coding: utf-8 -*-
"""What the user typed, what it means, and whether it matches.

Three jobs, all pure:

  * **parse** a value box -- ``"100"``, ``"100 m2"``, ``"100 m\u00b2"``,
    ``"3000mm"`` -- into a number and a unit token;
  * **convert** that number into Revit's internal unit, which is feet, square
    feet, cubic feet and radians;
  * **compare** an element's value against a rule's, for every operator the
    window offers.

Hand-written, because ``re`` is not in this engine's stdlib (S12.9.3). Every
tool here that reads text does the same -- ``OneFilterParameter._bracket_int``,
``anongee_autolevel.textparse`` -- so this is the house pattern rather than a
workaround.

A comma is refused rather than guessed at. ``1,5`` is one-and-a-half in half of
Europe and fifteen everywhere else, and a rule that silently means something the
user did not type is worse than one that will not save.
"""

from __future__ import division


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
# Revit's internal units: feet, square feet, cubic feet, radians. Every factor
# below converts ONE of the named unit INTO the internal one, and each is
# written as an exact expression rather than a rounded decimal so it can be
# checked by eye -- 1 ft is 0.3048 m exactly, by definition.

_FT_PER_M = 1.0 / 0.3048

#: unit token -> (quantity, factor into Revit's internal unit)
_UNITS = {
    # length -> feet
    "mm": ("length", _FT_PER_M / 1000.0),
    "cm": ("length", _FT_PER_M / 100.0),
    "m": ("length", _FT_PER_M),
    "ft": ("length", 1.0),
    "in": ("length", 1.0 / 12.0),
    # area -> square feet
    "mm2": ("area", (_FT_PER_M / 1000.0) ** 2),
    "cm2": ("area", (_FT_PER_M / 100.0) ** 2),
    "m2": ("area", _FT_PER_M ** 2),
    "ft2": ("area", 1.0),
    "in2": ("area", (1.0 / 12.0) ** 2),
    # volume -> cubic feet
    "mm3": ("volume", (_FT_PER_M / 1000.0) ** 3),
    "m3": ("volume", _FT_PER_M ** 3),
    "ft3": ("volume", 1.0),
    # angle -> radians
    "deg": ("angle", 3.14159265358979323846 / 180.0),
    "rad": ("angle", 1.0),
}

#: What people actually type, mapped onto a token in ``_UNITS``. The superscript
#: forms arrive from Word, from Excel and from Revit's own parameter names.
_UNIT_ALIASES = {
    u"m\u00b2": "m2", u"mm\u00b2": "mm2", u"cm\u00b2": "cm2",
    u"ft\u00b2": "ft2", u"in\u00b2": "in2",
    u"m\u00b3": "m3", u"mm\u00b3": "mm3", u"ft\u00b3": "ft3",
    "sqm": "m2", "sq.m": "m2", "sqmm": "mm2", "sqft": "ft2", "sq.ft": "ft2",
    "sm": "m2", "sf": "ft2", "cum": "m3", "cuft": "ft3", "cf": "ft3",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "foot": "ft", "feet": "ft", "inch": "in", "inches": "in",
    "degree": "deg", "degrees": "deg", u"\u00b0": "deg",
    "millimeter": "mm", "millimeters": "mm",
    "millimetre": "mm", "millimetres": "mm",
}

_DIGITS = "0123456789"


def _normalise_unit(raw):
    """``" SQ M "`` -> ``"m2"``. An unrecognised token is returned as it came.

    Kept rather than rejected so the caller can say *which* unit it did not
    know, which is the difference between a message and a shrug.
    """
    if not raw:
        return ""
    token = " ".join(raw.split()).lower()
    if token in _UNIT_ALIASES:
        return _UNIT_ALIASES[token]
    squashed = token.replace(" ", "").replace(".", "")
    if squashed in _UNIT_ALIASES:
        return _UNIT_ALIASES[squashed]
    if squashed in _UNITS:
        return squashed
    # "sq m" and "sq.m" survive the squash as "sqm"; "cu m" as "cum".
    return squashed


def known_units():
    """Every unit token this module can convert, sorted."""
    return sorted(_UNITS)


def is_known_unit(unit):
    """Whether ``to_internal`` will accept this token. ``""`` is fine."""
    return not unit or unit in _UNITS


def quantity_of(unit):
    """``"length"`` / ``"area"`` / ``"volume"`` / ``"angle"``, or None."""
    row = _UNITS.get(unit)
    return row[0] if row else None


def parse_number(text):
    """``(number, unit_token)`` out of a value box, or ``None``.

    ``None`` means "this is not a number", and the caller shows the box as
    invalid rather than saving a rule that cannot mean anything.

        >>> parse_number("100 m2")
        (100.0, 'm2')
        >>> parse_number("wall") is None
        True
    """
    if text is None:
        return None
    body = "{0}".format(text).strip()
    if not body:
        return None
    if "," in body:
        # Ambiguous by locale. Refused on purpose -- see the module docstring.
        return None

    cut = 0
    if body[0] in "+-":
        cut = 1
    seen_digit = False
    seen_dot = False
    while cut < len(body):
        char = body[cut]
        if char in _DIGITS:
            seen_digit = True
        elif char == "." and not seen_dot:
            seen_dot = True
        elif char in "eE" and seen_digit and cut + 1 < len(body):
            # Scientific notation: float() understands it, so accept the
            # exponent and let float() be the judge of the whole thing.
            rest = body[cut + 1:]
            if rest and (rest[0] in _DIGITS
                         or (rest[0] in "+-" and rest[1:2] and rest[1] in _DIGITS)):
                cut += 2
                while cut < len(body) and body[cut] in _DIGITS:
                    cut += 1
                break
            break
        else:
            break
        cut += 1

    if not seen_digit:
        return None
    try:
        number = float(body[:cut])
    except ValueError:                      # pragma: no cover - guarded above
        return None
    return (number, _normalise_unit(body[cut:]))


def to_internal(number, unit):
    """*number* in *unit*, as the number Revit stores.

    An empty unit passes straight through -- a count, a mark, a plain integer
    parameter has no unit to convert.

    Raises ``ValueError`` for a unit this module does not know, because
    guessing one is how a 100 becomes a 30.48 in somebody's model.
    """
    if not unit:
        return float(number)
    if unit not in _UNITS:
        raise ValueError("unknown unit: {0!r}".format(unit))
    return float(number) * _UNITS[unit][1]


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

#: Every operator, in the order the window's combo shows them.
OPERATORS = (
    "equals", "not_equals", "contains", "not_contains",
    "begins_with", "ends_with",
    "greater", "greater_equal", "less", "less_equal", "between",
    "is_empty", "is_not_empty",
)

#: The words shown for each. Kept apart from OPERATORS so the combo's order is
#: one list rather than a dict nobody can rely on the ordering of -- IronPython
#: 2.7's dict does not preserve insertion order and CPython 3.7's does, which
#: is exactly the kind of difference that shows up only in Revit.
_LABELS = {
    "equals": "equals",
    "not_equals": "does not equal",
    "contains": "contains",
    "not_contains": "does not contain",
    "begins_with": "begins with",
    "ends_with": "ends with",
    "greater": "is greater than",
    "greater_equal": "is at least",
    "less": "is less than",
    "less_equal": "is at most",
    "between": "is between",
    "is_empty": "is empty",
    "is_not_empty": "is not empty",
}

#: Operators whose value box must hold a number. The window uses this to decide
#: whether to offer a unit alongside it.
NUMERIC_OPERATORS = ("greater", "greater_equal", "less", "less_equal", "between")

#: Operators with no value at all. The window hides the box entirely.
VALUELESS_OPERATORS = ("is_empty", "is_not_empty")

#: Relative tolerance on a float comparison. Revit's internal feet carry more
#: precision than any drawing does; two areas that agree to a part in 10^9 are
#: the same area, and refusing to say so is how "equals 100" matches nothing.
_TOLERANCE = 1e-9


def operator_label(key):
    """The words the window shows for an operator key, or ``""``."""
    return _LABELS.get(key, "")


def is_operator(key):
    return key in _LABELS


def _as_number(value):
    """*value* as a float, or ``None`` if it is not one.

    Revit hands back strings for some parameters even when they read as
    numbers, so a rule written as a number still has to work against one.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parsed = parse_number(value)
    return parsed[0] if parsed else None


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "{0}".format(value)


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return False
    return not "{0}".format(value).strip()


def _close(left, right):
    return abs(left - right) <= _TOLERANCE * max(1.0, abs(left), abs(right))


def compare(actual, operator, expected):
    """Whether *actual* satisfies *operator* against *expected*.

    *actual* is what the element holds; *expected* is the rule's value, already
    converted into Revit's internal unit by the caller. ``between`` takes a
    pair.

    A missing *actual* never matches a real comparison -- a wall with no
    Comments is not ``Comments = X``, and it is not ``Comments != X`` either,
    because it has no Comments to disagree with. Only ``is_empty`` says yes.

    Raises ``ValueError`` for an operator it does not know. Everything else
    answers ``False`` rather than raising: a rule read off disk may name a
    parameter whose type has changed since, and that is a rule that does not
    match, not a crash in the middle of somebody's session.
    """
    if not is_operator(operator):
        raise ValueError("unknown operator: {0!r}".format(operator))

    if operator == "is_empty":
        return _is_blank(actual)
    if operator == "is_not_empty":
        return not _is_blank(actual)

    if actual is None:
        return False

    if operator == "between":
        try:
            low, high = expected
        except (TypeError, ValueError):
            return False
        number = _as_number(actual)
        low, high = _as_number(low), _as_number(high)
        if number is None or low is None or high is None:
            return False
        if low > high:
            low, high = high, low
        return low <= number <= high

    if operator in NUMERIC_OPERATORS:
        number = _as_number(actual)
        target = _as_number(expected)
        if number is None or target is None:
            return False
        if operator == "greater":
            return number > target and not _close(number, target)
        if operator == "greater_equal":
            return number >= target or _close(number, target)
        if operator == "less":
            return number < target and not _close(number, target)
        return number <= target or _close(number, target)      # less_equal

    # equals / not_equals compare as numbers when both sides are numbers, so
    # that 100.0 and "100" and 99.9999999999 all agree; as text otherwise.
    if operator in ("equals", "not_equals"):
        number, target = _as_number(actual), _as_number(expected)
        if number is not None and target is not None:
            same = _close(number, target)
        else:
            left, right = _as_text(actual), _as_text(expected)
            same = (left or "").strip().lower() == (right or "").strip().lower()
        return same if operator == "equals" else not same

    left = (_as_text(actual) or "").lower()
    right = (_as_text(expected) or "").lower()
    if operator == "contains":
        return right in left
    if operator == "not_contains":
        return right not in left
    if operator == "begins_with":
        return left.startswith(right)
    return left.endswith(right)                                # ends_with
