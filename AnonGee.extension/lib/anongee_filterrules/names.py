# -*- coding: utf-8 -*-
"""Revit's idea of "the same name", which is not Python's.

Revit matches element and type names **case-insensitively and with whitespace
collapsed**. A project that already carries ``BASIC WALL`` holds the name as far
as Revit is concerned, and ``"Basic Wall" == "BASIC WALL"`` is ``False`` in
Python -- which is a difference that costs something real.

``task_plan.md`` Phase 0.5 records what it cost the last time: a duplicate-type
check written with ``==`` was stricter than Revit's own rule, reached
``Duplicate()`` anyway, and produced *"The name is already in use for this
element type"* in a live model. ``cad2bim/type_names.py`` was written to fix it.

This is that algorithm again, in a module both engines can import. It is a
deliberate mirror, not an oversight: ``cad2bim`` lives in ``lib/py3`` and
IronPython cannot see it (``ARCHITECTURE.md`` S2.1). The precedent is
``bridge/jobs.py``, which mirrors ``startup.py``'s path rules for the same
reason and says so.

**Why this matters to a saved rule.** A rule stores ``"100mm Gypsum Wall"`` as
text, because an ``ElementId`` does not survive a session let alone another
project. Finding that type again in whatever model is open is exactly this
comparison, and getting it wrong means a rule that quietly matches nothing.
"""

from __future__ import division


def key(name):
    """The comparable form of a Revit name.

    Lower-cased, outer whitespace stripped, inner whitespace collapsed to
    single spaces -- so tabs, double spaces and a trailing space all fall
    together. ``None`` gives ``""``.

        >>> key("Basic  WALL ") == key("basic wall")
        True
    """
    if name is None:
        return ""
    return " ".join("{0}".format(name).split()).lower()


def same(left, right):
    """Whether Revit would call these two the same name.

    ``None`` matches nothing, including another ``None`` -- an element with no
    name is not "the same name" as another element with no name, and treating
    them as equal would make a rule with a missing type match every type.
    """
    if left is None or right is None:
        return False
    return key(left) == key(right)


def find(rows, name):
    """The payload of the first ``(name, payload)`` row matching *name*.

    ``None`` when nothing matches -- which for this tool means the project does
    not have that type, and is a rule to grey out rather than an error.

        >>> find([("Basic Wall", 1), ("Curtain Wall", 2)], "  basic   wall ")
        1
    """
    if name is None:
        return None
    wanted = key(name)
    if not wanted:
        return None
    for row_name, payload in rows:
        if key(row_name) == wanted:
            return payload
    return None


def index(rows):
    """``{key: payload}`` for a set of ``(name, payload)`` rows.

    For when the same list is searched many times -- the type list of a
    category, checked once per element. A later row with a colliding key
    does not displace an earlier one, which matches ``find``'s "first wins".
    """
    built = {}
    for row_name, payload in rows:
        row_key = key(row_name)
        if row_key and row_key not in built:
            built[row_key] = payload
    return built
