# -*- coding: utf-8 -*-
"""Load audit and cad2bim modules by PATH, without importing either package.

`import anongee_toolkit.cad2bim_audit.space` runs `anongee_toolkit/__init__.py`
and `cad2bim/__init__.py`, which pull in Revit assemblies that do not exist
outside Revit. Same problem cad2bim's own `tests/_loader.py` solves, same
solution: build a throwaway package whose `__path__` points at the real folder,
so relative imports between siblings resolve by file exactly as they do in Revit.

    space, matching = load("space", "matching")
    dxf_reader = load_cad2bim("readers.dxf_reader")

Each call gets its own namespace, so one test cannot see another's state.
"""

import importlib
import itertools
import os
import sys
import types

_AUDIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAD2BIM = os.path.join(os.path.dirname(_AUDIT), "cad2bim")
_COUNTER = itertools.count(1)

#: Subpackages that need a namespace of their own for relative imports to work.
_AUDIT_SUBPACKAGES = ("readers",)
_CAD2BIM_SUBPACKAGES = ("readers", "geom", "classify", "builders")

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _namespace(prefix, root, subpackages, run_init=False):
    package = types.ModuleType(prefix)
    package.__path__ = [root]
    sys.modules[prefix] = package
    if run_init:
        # Execute the real __init__.py into the stand-in, so a module doing
        # `from . import __version__` gets the version actually shipped rather
        # than a placeholder. Only safe for packages whose __init__ is pure
        # Python -- which is why cad2bim's, full of Revit imports, is not run.
        init = os.path.join(root, "__init__.py")
        if os.path.isfile(init):
            with open(init) as handle:
                exec(compile(handle.read(), init, "exec"), package.__dict__)
    for name in subpackages:
        child_name = "{0}.{1}".format(prefix, name)
        child = types.ModuleType(child_name)
        child.__path__ = [os.path.join(root, name)]
        sys.modules[child_name] = child
        setattr(package, name, child)
    return package


def load(*names):
    """Load audit modules ("space", "readers.dxf_raw") into a fresh namespace."""
    prefix = "_audit_test_{0}".format(next(_COUNTER))
    _namespace(prefix, _AUDIT, _AUDIT_SUBPACKAGES, run_init=True)
    loaded = [importlib.import_module("{0}.{1}".format(prefix, name))
              for name in names]
    return loaded[0] if len(loaded) == 1 else tuple(loaded)


def load_revit(*names):
    """Load audit modules that import Autodesk.Revit, against the stub.

    The stub goes on sys.modules FIRST, because both Revit-bound readers do a
    top-level `from Autodesk.Revit.DB import ...` -- by the time the module body
    runs it is already too late to substitute anything.

    Returns the modules, and the stub itself is importable as `_revit_stub` for
    building fixtures.
    """
    import _revit_stub
    _revit_stub.install()
    return load(*names)


def load_cad2bim(*names):
    """Load cad2bim modules ("model", "readers.dxf_reader") into a fresh namespace.

    Only modules that are Revit-free can be loaded this way; that is the whole
    set the audit's tests need, because everything Revit-touching lives behind
    the readers the tests do not exercise outside Revit.
    """
    prefix = "_cad2bim_for_audit_{0}".format(next(_COUNTER))
    _namespace(prefix, _CAD2BIM, _CAD2BIM_SUBPACKAGES)
    loaded = [importlib.import_module("{0}.{1}".format(prefix, name))
              for name in names]
    return loaded[0] if len(loaded) == 1 else tuple(loaded)


def fixture(name):
    """Absolute path to a file in tests/fixtures."""
    return os.path.join(FIXTURES, name)
