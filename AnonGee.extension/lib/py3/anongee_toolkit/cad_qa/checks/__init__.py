# -*- coding: utf-8 -*-
"""The check families. Each module exposes ``check(context) -> [Finding]``.

A check is a PURE FUNCTION of a :class:`~cad_qa.context.DrawingContext`. It
reads nothing from disk, writes nothing, and holds no state -- which is what
lets the whole suite be tested against a hand-built context in microseconds
instead of a 33 MB DXF.

Adding a family is: write the module, declare its rules in ``rules.py``, add it
to ``FAMILY_CHECKS`` below. Nothing else knows the list.
"""

from . import layers, marks, geometry, structure

__version__ = "1.0.0"

#: Run in this order. Layers first on purpose: when the classification has
#: failed, most of what the other families would say is a consequence of that
#: and reads better underneath it.
FAMILY_CHECKS = (
    ("layers", layers.check),
    ("marks", marks.check),
    ("geometry", geometry.check),
    ("structure", structure.check),
)

__all__ = ["layers", "marks", "geometry", "structure", "FAMILY_CHECKS"]
