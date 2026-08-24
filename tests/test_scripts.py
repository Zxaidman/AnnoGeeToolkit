# -*- coding: utf-8 -*-
"""Two things about every pushbutton script, checked without running any of them.

Both exist because both shipped, and neither is catchable by anything else here:
a pyRevit script cannot be imported off Revit, so a name that does not resolve
and an engine that is not selected are invisible until somebody presses the
button.

**The engine line.** pyRevit picks the engine from a ``#! python3`` shebang on
the first line. Without it a script runs on IronPython 2.7, where ``lib/py3`` is
not on the path and the CPython toolkit does not exist. Bridge Listener shipped
without it and appeared to work — the ``bridge`` package happens to be Python
2.7-compatible — so it looked correct right up until the first command that
needed openpyxl. That is the worst kind of missing line: one whose absence
produces a working tool with a fuse in it.

**Names that do not resolve.** Bridge Check used ``os`` in two functions and
never imported it. The failure was a ``NameError`` at the moment somebody
pressed the button, phrased *"global name 'os' is not defined"* — Python 2
wording, which named the missing import and said nothing at all about the
missing engine that made it Python 2 in the first place.
"""

import ast
import builtins
import glob
import io
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TAB = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab")

#: Bound by pyRevit before a script runs, not by the script itself.
INJECTED = set("""
__revit__ __file__ __name__ __doc__ __builtins__ __package__ __spec__
__loader__ __commandbuttonname__ __commanddata__ __elements__
__forceddebugmode__ __shiftclick__ __eventsender__ __eventargs__
__title__ __author__ __version__ __namespace__ __cleanengine__
__persistentengine__ __min_revit_ver__ __max_revit_ver__
""".split())

KNOWN_EVERYWHERE = set(dir(builtins)) | INJECTED


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def scripts():
    """Every pushbutton script on the ribbon, panels and stacks alike."""
    found = glob.glob(os.path.join(_TAB, "*", "*.pushbutton", "script.py"))
    found += glob.glob(os.path.join(_TAB, "*", "*.stack", "*.pushbutton",
                                    "script.py"))
    return sorted(found)


def toolkit_modules():
    base = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                        "anongee_toolkit")
    return sorted(glob.glob(os.path.join(base, "*", "*.py")))


def _bound(node):
    """Every name *node* binds, anywhere inside it.

    Deliberately not scope-aware. A name bound in one function and read in
    another is not an error this test is trying to find, and pretending to
    model Python's scopes would cost far more than it caught — the bug in mind
    is a module that never imports what it uses.
    """
    names = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.alias):
            names.add((inner.asname or inner.name).split(".")[0])
        elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
            names.add(inner.name)
        elif isinstance(inner, ast.Name) and isinstance(inner.ctx,
                                                        (ast.Store, ast.Del)):
            names.add(inner.id)
        elif isinstance(inner, ast.arg):
            names.add(inner.arg)
        elif isinstance(inner, ast.ExceptHandler) and inner.name:
            names.add(inner.name)
        elif isinstance(inner, (ast.Global, ast.Nonlocal)):
            names.update(inner.names)
    return names


def unresolved(path):
    """``[(line, name)]`` read but never bound. ``None`` for a star import."""
    source = _read(path)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                # Nothing can say what a star import brought in. Reported as
                # unknowable rather than clean, so the exemption is visible.
                return None

    known = _bound(tree) | KNOWN_EVERYWHERE
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                and node.id not in known):
            found.add((node.lineno, node.id))
    return sorted(found)


#: Revit and .NET interfaces a Python class can subclass. Doing so has three
#: rules under Python.NET and none under IronPython, which is why this list and
#: the engine test above are the same subject.
REVIT_INTERFACES = ("IExternalEventHandler", "IFailuresPreprocessor", "IUpdater",
                    "ISelectionFilter", "IExternalApplication",
                    "IExternalCommand", "IExternalDBApplication",
                    "IDockablePaneProvider")


def interface_classes(path):
    """``[(ClassDef, guarded)]`` for every Revit-interface subclass in a file."""
    tree = ast.parse(_read(path))
    top_level = set(id(node) for node in tree.body)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
        if any(base in REVIT_INTERFACES for base in bases):
            found.append((node, id(node) not in top_level))
    return found


def runs_on_cpython(path):
    """Whether Python.NET's rules apply to this file at all.

    A toolkit module always: ``lib/py3`` is only ever on a CPython engine's
    path. A script only if it selects the engine — IronPython subclasses .NET
    interfaces without ceremony, and one script in this repository relies on
    that.
    """
    if os.sep + "lib" + os.sep + "py3" + os.sep in path:
        return True
    return _read(path).startswith("#! python3")


class InterfaceSubclassTests(unittest.TestCase):
    """The three Python.NET rules, from the brand guidelines §12.8.7.1.

    Every one of them fails **at instantiation**, in Revit, with an error that
    names the symptom and not the cause:

    ============================== ==========================================
    Missing ``__namespace__``      ``TypeError: interface takes exactly one
                                   argument`` — pythonnet routes the
                                   constructor to the interface's one-argument
                                   cast instead of building a derived CLR type
    An ``__init__``                the same error, even with ``__namespace__``
    Defined more than once         ``Duplicate type name within an assembly``,
                                   on the *second* press
    ============================== ==========================================

    Bridge Listener had ``__namespace__`` at **module** scope, where it does
    nothing. It ran anyway for a release because it was on IronPython, where
    none of this applies — so fixing the engine is what exposed it, and neither
    fault was visible until then.
    """

    def cases(self):
        for path in scripts() + toolkit_modules():
            if not runs_on_cpython(path):
                continue
            for node, guarded in interface_classes(path):
                yield os.path.relpath(path, _ROOT), node, guarded

    def test_every_interface_subclass_declares_its_namespace_on_the_class(self):
        missing = []
        for where, node, _guarded in self.cases():
            declared = any(
                isinstance(statement, ast.Assign)
                and any(isinstance(target, ast.Name)
                        and target.id == "__namespace__"
                        for target in statement.targets)
                for statement in node.body)
            if not declared:
                missing.append("{0}: {1}".format(where, node.name))
        self.assertEqual(missing, [], "; ".join(missing))

    def test_no_interface_subclass_defines_init(self):
        offenders = []
        for where, node, _guarded in self.cases():
            names = [statement.name for statement in node.body
                     if isinstance(statement, ast.FunctionDef)]
            if "__init__" in names:
                offenders.append("{0}: {1}".format(where, node.name))
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_no_interface_subclass_is_emitted_at_module_scope(self):
        """It has to be built once per session, so it cannot be top level.

        A class statement at module scope re-runs on every press under the
        persistent engine, and pythonnet refuses a second CLR type of the same
        name. Guarded means inside an ``if`` that checks a cache, or inside a
        factory the registry calls once — both patterns are in use here.
        """
        offenders = []
        for where, node, guarded in self.cases():
            if not guarded:
                offenders.append("{0}: {1}".format(where, node.name))
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_the_rule_is_not_vacuous(self):
        """Guard against the checks passing because they found nothing."""
        self.assertGreaterEqual(len(list(self.cases())), 6)


class EngineTests(unittest.TestCase):

    def test_every_script_that_uses_the_toolkit_selects_the_engine(self):
        """``lib/py3`` is only on the path for a CPython engine.

        The absence produces a *working* tool with a fuse in it, which is why
        this is worth a test rather than a convention.
        """
        missing = []
        for path in scripts():
            source = _read(path)
            if "anongee_toolkit" not in source:
                continue
            if not source.startswith("#! python3"):
                missing.append(os.path.relpath(path, _ROOT))
        self.assertEqual(missing, [],
                         "these import the toolkit and would run on "
                         "IronPython: " + "; ".join(missing))

    def test_the_shebang_is_the_very_first_line(self):
        """pyRevit reads it from line one. A coding line above it wins."""
        for path in scripts():
            lines = _read(path).splitlines()
            if "#! python3" in "\n".join(lines[:5]):
                self.assertEqual(lines[0].strip(), "#! python3",
                                 os.path.relpath(path, _ROOT))

    def test_the_startup_script_does_not_select_an_engine(self):
        """It must stay valid on pyRevit's core engine, which is IronPython.

        The opposite rule from every other file here, and the reason the bridge
        is a doorbell rather than a worker.
        """
        source = _read(os.path.join(_ROOT, "AnonGee.extension", "startup.py"))
        self.assertFalse(source.startswith("#! python3"))


class NameResolutionTests(unittest.TestCase):

    def test_no_script_reads_a_name_it_never_binds(self):
        broken = []
        for path in scripts():
            found = unresolved(path)
            if found:
                broken.append("{0}: {1}".format(
                    os.path.relpath(path, _ROOT),
                    ", ".join("{0} (line {1})".format(name, line)
                              for line, name in found[:5])))
        self.assertEqual(broken, [], "; ".join(broken))

    def test_no_toolkit_module_reads_a_name_it_never_binds(self):
        broken = []
        for path in toolkit_modules():
            found = unresolved(path)
            if found:
                broken.append("{0}: {1}".format(
                    os.path.relpath(path, _ROOT),
                    ", ".join("{0} (line {1})".format(name, line)
                              for line, name in found[:5])))
        self.assertEqual(broken, [], "; ".join(broken))

    def test_the_startup_script_resolves_too(self):
        path = os.path.join(_ROOT, "AnonGee.extension", "startup.py")
        self.assertEqual(unresolved(path), [])

    def test_a_star_import_is_reported_as_unknowable_not_as_clean(self):
        """One file uses ``from Autodesk.Revit.DB import *``.

        Nothing can say statically what that brought in. It is exempted rather
        than passed, so the exemption stays visible instead of quietly widening
        to cover a real fault.
        """
        exempt = [os.path.relpath(path, _ROOT) for path in scripts()
                  if unresolved(path) is None]
        self.assertEqual(len(exempt), 1, exempt)
        self.assertIn("FramewinToBIM", exempt[0])


if __name__ == "__main__":
    unittest.main()
