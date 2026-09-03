# -*- coding: utf-8 -*-
"""Static bridge path contract across the IronPython and CPython entry points."""

import ast
import io
import os
import unittest


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STARTUP = os.path.join(_ROOT, "AnonGee.extension", "startup.py")
_CHECK = os.path.join(
    _ROOT,
    "AnonGee.extension",
    "AnonGee.tab",
    "Dev.panel",
    "Bridge Check.pushbutton",
    "script.py",
)
_JOBS = os.path.join(
    _ROOT,
    "AnonGee.extension",
    "lib",
    "py3",
    "anongee_toolkit",
    "bridge",
    "jobs.py",
)


def _read(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _tuple_constant(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name
                   for target in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            break
        return tuple(element.value for element in node.value.elts)
    raise AssertionError("{} is not a top-level tuple constant".format(name))


def _function_source(source, name):
    marker = "def {}(".format(name)
    start = source.index(marker)
    next_function = source.find("\ndef ", start + len(marker))
    return source[start:] if next_function < 0 else source[start:next_function]


class BridgePathSourceContractTests(unittest.TestCase):

    def test_all_three_entry_points_name_the_same_paths(self):
        sources = [_read(_STARTUP), _read(_CHECK), _read(_JOBS)]
        expected = {
            "LOCALAPPDATA_PARTS": ("Zxaidman", "AnonGee", "bridge"),
            "APPDATA_PARTS": ("AnonGee", "bridge"),
            "HOME_PARTS": (".anongee", "bridge"),
        }
        for name, parts in expected.items():
            for source in sources:
                self.assertEqual(_tuple_constant(source, name), parts, name)

    def test_startup_prefers_localappdata_before_appdata(self):
        body = _function_source(_read(_STARTUP), "bridge_home")
        self.assertIn('os.environ.get("LOCALAPPDATA")', body)
        self.assertIn('os.environ.get("APPDATA")', body)
        self.assertLess(body.index('os.environ.get("LOCALAPPDATA")'),
                        body.index('os.environ.get("APPDATA")'))

    def test_bridge_check_prefers_localappdata_before_appdata(self):
        body = _function_source(_read(_CHECK), "bridge_home")
        self.assertIn('os.environ.get("LOCALAPPDATA")', body)
        self.assertIn('os.environ.get("APPDATA")', body)
        self.assertLess(body.index('os.environ.get("LOCALAPPDATA")'),
                        body.index('os.environ.get("APPDATA")'))

    def test_startup_remains_python_2_7_syntax_compatible(self):
        source = _read(_STARTUP)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.JoinedStr)
            self.assertNotIsInstance(node, ast.NamedExpr)
            self.assertNotIsInstance(node, ast.AnnAssign)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(node.returns, node.name)
                for argument in node.args.args:
                    self.assertIsNone(argument.annotation, node.name)


if __name__ == "__main__":
    unittest.main()
