# -*- coding: utf-8 -*-
"""The three Revit API differences this tool has to branch on, isolated here.

Everything else in the package is version-blind because these are not.

  * ``ElementId`` moved from ``Int32`` to ``Int64`` in Revit 2024, and its
    reader from ``IntegerValue`` to ``Value``.
  * ``Element.Name`` resolves differently per subtype;
    ``Element.Name.GetValue(el)`` is the robust idiom.
  * A raw Python list is a **fatal** marshalling fault across the pythonnet
    bridge (brand guidelines S12.9.4), so anything handed to the Revit API has
    to be a ``List[T]`` first.

``anongee_toolkit.revit.compatibility`` does the first of these already, but it
asks ``pyrevit.HOST_APP`` for the version -- and this package may not import
either pyRevit or the toolkit (``ARCHITECTURE.md`` S2.1). ``cad2bim/compat.py``
does it the version-blind way instead, by trying the newer attribute first, and
that is what is mirrored here. A mirror, not an oversight; the precedent is
``bridge/jobs.py``.
"""

from __future__ import division

import clr

clr.AddReference("RevitAPI")

import System                                                    # noqa: E402
from System.Collections.Generic import List                      # noqa: E402
from Autodesk.Revit.DB import Element, ElementId                 # noqa: E402


def id_value(element_id):
    """The integer inside an ``ElementId``, on any supported Revit.

    ``None`` in gives ``None`` out rather than raising -- the callers here are
    reading whatever a model hands them, and an invalid id is a fact about the
    model, not a programming error.
    """
    if element_id is None:
        return None
    try:
        return int(element_id.Value)          # Revit 2024+
    except AttributeError:
        return int(element_id.IntegerValue)   # Revit 2023 and earlier


def element_id(value):
    """An ``ElementId`` from a plain int, across the Int32 / Int64 change.

    The Int64 form is tried first because it is the current one; the older
    hosts raise and take the fallback.
    """
    try:
        return ElementId(System.Int64(int(value)))    # Revit 2024+
    except Exception:                                  # pragma: no cover
        return ElementId(int(value))


def element_name(element):
    """An element's name, or ``None``. Never raises on an odd subtype."""
    if element is None:
        return None
    try:
        return Element.Name.GetValue(element)
    except Exception:
        try:
            return element.Name
        except Exception:
            return None


def id_list(values):
    """``List[ElementId]`` from ints or ``ElementId``s.

    Revit will not take a Python list, and passing one is a **fatal**
    marshalling fault rather than an exception you could catch (S12.9.4). Every
    collection leaving this package for the Revit API goes through here.
    """
    built = List[ElementId]()
    for value in values:
        built.Add(value if isinstance(value, ElementId) else element_id(value))
    return built
