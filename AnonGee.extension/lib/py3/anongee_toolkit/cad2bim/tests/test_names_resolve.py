# -*- coding: utf-8 -*-
"""Every name a Revit-importing module calls is a name that exists (BUG-47).

These modules import `Autodesk.Revit.DB` at the top, so nothing offline can
import them and no unit test ever executes a line of them. They are held by
TEXT checks in `test_dialog_wiring.py` -- and a text check asks whether a line
was written, never whether it can run.

That gap cost the owner two releases. v1.0.4 added

    _set_mark(instance, segment.get("mark"))

to `builders/walls.py`, where `_set_mark` is a helper of `builders/columns.py`
and does not exist. The line was there, so the text check passed; every wall
placement raised `NameError`, was caught by the per-segment `except Exception`,
and became an error. His v1.0.4 and v1.0.5 runs both report

    "walls": 0, "errors": 171, "error_details": ["name '_set_mark' is not defined"]

-- 171 members planned and not one placed, on a release that was shipped as a
naming FIX. Python would have said so at the first call; only the swallowing
`except` and the absence of any import made it survive to the owner.

So: resolve every called name statically. Module-level defs, imports, classes,
assignments, builtins, and anything bound locally in the function are fine;
anything else is a call that cannot work.
"""

import ast
import builtins
import os
import unittest


_HERE = os.path.dirname(os.path.abspath(__file__))
_PACKAGE = os.path.normpath(os.path.join(_HERE, ".."))


def _modules():
    """Every .py in the package, so a new Revit-importing file is covered too."""
    found = []
    for folder, folders, files in os.walk(_PACKAGE):
        folders[:] = [f for f in folders
                      if f not in ("tests", "__pycache__")]
        for name in sorted(files):
            if name.endswith(".py"):
                found.append(os.path.join(folder, name))
    return found


def _bound_at_module_level(tree):
    """Every name the module itself defines, imports or assigns."""
    names = set()
    for node in tree.body:
        names |= _bindings(node)
    return names


def _bindings(node):
    """The names one statement binds, without descending into nested scopes."""
    names = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(node.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign,
                           ast.For, ast.AsyncFor, ast.With, ast.AsyncWith,
                           ast.Try, ast.If, ast.While)):
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                names |= _bindings(child)
            elif isinstance(child, ast.ExceptHandler) and child.name:
                names.add(child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
                names.add(child.name)
    return names


def _bound_inside(func):
    """Names bound anywhere inside a function: arguments, assignments, imports.

    Deliberately generous -- a comprehension variable or a nested def counts --
    because this test hunts a name that exists NOWHERE, not a scoping subtlety.
    """
    names = set()
    args = func.args
    for group in (getattr(args, "posonlyargs", []), args.args, args.kwonlyargs):
        for arg in group:
            names.add(arg.arg)
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            names.add(extra.arg)
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= _bindings(node)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)) and node is not func:
            names.add(node.name)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            names |= set(node.names)
    return names


def _nested(node):
    """The functions defined directly in `node`, not deeper."""
    found = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(child)
        else:
            found.extend(_nested(child))
    return found


def _calls_here(func):
    """Plain `name()` calls in this function, NOT inside a nested one.

    A closure's calls are checked with the closure, against a `known` set that
    carries its enclosing scopes -- `pt` defined in a function and called from
    an inner `chain` is perfectly good Python, and reading each function alone
    would report it as missing.
    """
    inner = set()
    for child in _nested(func):
        for node in ast.walk(child):
            inner.add(id(node))
    out = []
    for node in ast.walk(func):
        if id(node) in inner or not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            out.append(node)
    return out


class EveryCalledNameExists(unittest.TestCase):

    def _check(self, func, known, path, missing):
        known = known | _bound_inside(func)
        for node in _calls_here(func):
            if node.func.id not in known:
                missing.append(
                    "%s line %d: %s() is called and defined nowhere"
                    % (os.path.relpath(path, _PACKAGE), node.lineno,
                       node.func.id))
        for child in _nested(func):
            self._check(child, known, path, missing)

    def test_no_module_calls_a_name_that_is_not_there(self):
        missing = []
        for path in _modules():
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as broken:
                missing.append("%s does not parse: %s"
                               % (os.path.basename(path), broken))
                continue
            known = _bound_at_module_level(tree) | set(dir(builtins))
            for func in _nested(tree):
                self._check(func, known, path, missing)
        self.assertEqual(missing, [], "\n  " + "\n  ".join(missing))

    def test_a_closure_calling_its_enclosing_helper_is_fine(self):
        # builders/stairs.py does exactly this: `pt` defined in the function,
        # called from the inner `chain`. Reading each function alone reports it.
        tree = ast.parse("def outer(run):\n"
                         "    def pt(p):\n"
                         "        return p\n"
                         "    def chain(points):\n"
                         "        return [pt(p) for p in points]\n"
                         "    return chain(run)\n")
        missing = []
        known = _bound_at_module_level(tree) | set(dir(builtins))
        for func in _nested(tree):
            self._check(func, known, "x.py", missing)
        self.assertEqual(missing, [])

    def test_the_check_can_actually_see_a_missing_name(self):
        # The guard is only worth having if it fails on the very line that got
        # through. This is that line, out of `builders/walls.py` at v1.0.4.
        tree = ast.parse("from ..compat import set_element_mark\n"
                         "def place(instance, segment):\n"
                         "    _set_mark(instance, segment.get('mark'))\n")
        module_names = _bound_at_module_level(tree)
        func = tree.body[-1]
        known = module_names | _bound_inside(func) | set(dir(builtins))
        self.assertNotIn("_set_mark", known)

    def test_the_check_does_not_cry_wolf_on_a_normal_module(self):
        tree = ast.parse("import os\n"
                         "def _helper(x):\n"
                         "    return x\n"
                         "def use(items):\n"
                         "    total = len(items)\n"
                         "    return _helper(total), os.getcwd()\n")
        module_names = _bound_at_module_level(tree)
        for func in tree.body[1:]:
            known = module_names | _bound_inside(func) | set(dir(builtins))
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertIn(node.func.id, known)


if __name__ == "__main__":
    unittest.main()
