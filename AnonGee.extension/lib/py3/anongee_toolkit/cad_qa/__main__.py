# -*- coding: utf-8 -*-
"""``python -m cad_qa`` (off Revit) and ``python -m anongee_toolkit.cad_qa``.

Both work: the package is reachable by either name, and ``deps.py`` explains
why that is deliberate rather than accidental.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
