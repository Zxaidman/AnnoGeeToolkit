# -*- coding: utf-8 -*-
"""The ONE place that knows cad2bim can be reached by two different names.

Inside Revit the toolkit is imported as ``anongee_toolkit.cad2bim.*``, and
importing it that way runs ``anongee_toolkit/__init__.py``, which loads Revit
assemblies. Off Revit those assemblies do not exist, so that path raises before
a single check has run -- and an offline QA tool that cannot be imported
offline is not a tool.

Off Revit the package is therefore reached as a TOP-LEVEL ``cad2bim`` instead,
with ``lib/py3/anongee_toolkit`` on ``sys.path``. cad2bim's own modules use
relative imports internally (``from . import config``), so both routes load
exactly the same files and exercise exactly the same import graph. Nothing is
stubbed, and there is no second implementation to drift.

Every other module in this package imports its cad2bim dependencies FROM HERE::

    from .deps import dxf_reader, layers, marks, config

so the fallback is written once, is visible, and cannot quietly spread. If this
module raises, the environment is genuinely wrong and the CLI says so in one
sentence rather than a traceback through six frames.
"""

import os
import sys

__version__ = "1.0.0"

#: ``.../lib/py3/anongee_toolkit`` -- the folder that must be importable for
#: the top-level route to resolve. Computed from this file so it survives the
#: package being installed somewhere unexpected.
TOOLKIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_path():
    """Put the toolkit folder on ``sys.path`` for the top-level route."""
    if TOOLKIT_DIR not in sys.path:
        sys.path.insert(0, TOOLKIT_DIR)


try:                                  # inside Revit: the package route
    from anongee_toolkit.cad2bim.readers import dxf_reader
    from anongee_toolkit.cad2bim.classify import layers, marks
    from anongee_toolkit.cad2bim import config
except ImportError:                   # off Revit: the top-level route
    _ensure_path()
    from cad2bim.readers import dxf_reader      # noqa: F401  (re-exported)
    from cad2bim.classify import layers, marks  # noqa: F401  (re-exported)
    from cad2bim import config                  # noqa: F401  (re-exported)


def ezdxf_available():
    """Whether a DXF can actually be read, without importing ezdxf here.

    The reader imports ezdxf on demand and caches it; asking it is the only
    way to know that is honest, because a vendored Windows build sitting on
    ``sys.path`` imports on Windows and raises everywhere else.
    """
    return dxf_reader.ezdxf_available()


__all__ = ["dxf_reader", "layers", "marks", "config", "ezdxf_available",
           "TOOLKIT_DIR"]
