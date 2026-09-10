# -*- coding: utf-8 -*-
"""Static checks on Filter View Manager's XAML and its Python wiring.

Modelled on ``tests/test_autolevel_ui.py``, which is the template this
repository uses for a tool with a window. Everything here is checked without
Revit and without WPF, because the alternative is finding it by pressing the
button and watching nothing happen.

The failures worth this file are the ones that are **silent**:

* ``XamlReader.Load`` throws and the window never opens -- a `{StaticResource}`
  on the root ``Window``, a literal that starts with ``{``, a resource key that
  is not there, a ``Style`` on the wrong element, a trigger naming an element
  outside its own template;
* a ``{Binding}`` path with no matching ``__slots__`` entry, which renders an
  empty row and reports nothing;
* a ``FindName`` that returns ``None``, which fails much later at the first
  click;
* an ``x:Name`` nothing looks up, which is dead weight pretending to be wired.

The engine rules are here too -- ``re`` is not in this engine's stdlib, and
``pyrevit`` may not be imported from CPython 3 -- along with the four copies of
the version number, held together so the header cannot lie about the build.
"""

import ast
import io
import os
import unittest
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUTTON = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                       "FilterViewManager.pushbutton")
_XAML = os.path.join(_BUTTON, "ui.xaml")
_SCRIPT = os.path.join(_BUTTON, "script.py")

_X = "{http://schemas.microsoft.com/winfx/2006/xaml}"

#: Attribute values that are markup extensions, not literals.
_MARKUP = ("{Binding", "{StaticResource", "{DynamicResource", "{TemplateBinding",
           "{RelativeSource", "{x:", "{}")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _tree():
    return ET.parse(_XAML).getroot()


def _tag(element):
    return element.tag.split("}")[-1]


def _template_scopes(root):
    """Every element that starts its own name scope.

    A ``ControlTemplate`` and a ``DataTemplate`` each get their own scope, so a
    name repeated across templates is legal and ``FindName`` on the window can
    never see it. Both facts matter below.
    """
    return [e for e in root.iter() if _tag(e) in ("ControlTemplate", "DataTemplate")]


def _in_a_template(root, element):
    for scope in _template_scopes(root):
        if element is not scope and element in list(scope.iter()):
            return True
    return False


def window_names():
    """``{x:Name: element}`` for the window's OWN scope, templates excluded."""
    root = _tree()
    found = {}
    for element in root.iter():
        name = element.get(_X + "Name")
        if name and not _in_a_template(root, element):
            found[name] = element
    return found


def resource_keys():
    return [e.get(_X + "Key") for e in _tree().iter() if e.get(_X + "Key")]


def resource_uses():
    """Every ``{StaticResource X}`` / ``{DynamicResource X}`` name used."""
    source = _read(_XAML)
    found = set()
    for token in ("{StaticResource ", "{DynamicResource "):
        index = 0
        while True:
            index = source.find(token, index)
            if index < 0:
                break
            start = index + len(token)
            end = start
            while end < len(source) and source[end] not in "}, \n\r\t":
                end += 1
            found.add(source[start:end])
            index = end
    return found


def binding_paths():
    """Every ``{Binding Foo...}`` path that is NOT relative-source."""
    source = _read(_XAML)
    found = set()
    index = 0
    while True:
        index = source.find("{Binding ", index)
        if index < 0:
            return found
        close = source.find("}", index)
        body = source[index + len("{Binding "):close if close > 0 else None]
        index = index + 9
        if "RelativeSource" in body:
            # Bound to the container (ListBoxItem.IsSelected), not to a row.
            continue
        path = body.split(",")[0].strip()
        if path and path[0].isalpha():
            found.add(path)


def slots_in_script():
    """Every name in every ``__slots__`` in script.py."""
    found = set()
    for node in ast.walk(ast.parse(_read(_SCRIPT))):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "__slots__" not in targets:
            continue
        for element in getattr(node.value, "elts", []):
            if isinstance(element, ast.Constant):
                found.add(element.value)
    return found


def bound_control_names():
    """The name tuple inside ``FilterViewApp._bind_controls``."""
    for node in ast.walk(ast.parse(_read(_SCRIPT))):
        if isinstance(node, ast.FunctionDef) and node.name == "_bind_controls":
            # Only the tuple the `for` loop walks -- taking every string in the
            # function would sweep up its docstring too.
            for inner in ast.walk(node):
                if isinstance(inner, ast.For) and isinstance(inner.iter, ast.Tuple):
                    return set(e.value for e in inner.iter.elts
                               if isinstance(e, ast.Constant))
    return set()


class XamlTests(unittest.TestCase):

    def test_the_file_is_well_formed(self):
        _tree()

    def test_no_literal_value_is_mistaken_for_a_markup_extension(self):
        """A value starting with "{" is parsed as markup, not as text.

        ``XamlReader.Load`` throws and the window never opens. The escape is a
        leading ``{}``.
        """
        problems = []
        for element in _tree().iter():
            for key, value in element.attrib.items():
                if value.startswith("{") and not value.startswith(_MARKUP):
                    problems.append("{0}.{1}={2!r}".format(_tag(element), key, value))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_no_resource_key_is_defined_twice(self):
        keys = resource_keys()
        dupes = sorted(set(key for key in keys if keys.count(key) > 1))
        self.assertEqual(dupes, [])

    def test_every_resource_reference_resolves(self):
        """A {StaticResource} naming a key that is not there throws on load."""
        missing = sorted(resource_uses() - set(resource_keys()))
        self.assertEqual(missing, [])

    def test_the_root_window_uses_literals_only(self):
        """§12.7.A -- XamlReader resolves Window attributes BEFORE Resources."""
        head = _read(_XAML)
        head = head[:head.index(">")]
        self.assertNotIn("StaticResource", head)
        self.assertNotIn("DynamicResource", head)

    def test_every_style_matches_the_element_it_is_applied_to(self):
        """A Style whose TargetType is not the element's type throws at load."""
        root = _tree()
        target = {}
        for element in root.iter():
            if _tag(element) == "Style" and element.get(_X + "Key"):
                target[element.get(_X + "Key")] = element.get("TargetType")
        problems = []
        for element in root.iter():
            value = element.get("Style") or ""
            if not value.startswith("{StaticResource "):
                continue
            key = value[len("{StaticResource "):].rstrip("}").strip()
            wanted = target.get(key)
            if wanted and wanted != _tag(element):
                problems.append("{0} has {1} (TargetType {2})".format(
                    _tag(element), key, wanted))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_every_trigger_targets_an_element_in_its_own_template(self):
        problems = []
        for scope in _template_scopes(_tree()):
            inside = set(e.get(_X + "Name") for e in scope.iter()
                         if e.get(_X + "Name"))
            for element in scope.iter():
                name = element.get("TargetName")
                if name and name not in inside:
                    problems.append(name)
        self.assertEqual(problems, [], "; ".join(problems))

    def test_every_name_in_the_window_scope_is_unique(self):
        """A repeat in the window's own scope makes FindName ambiguous."""
        root = _tree()
        outside = [e.get(_X + "Name") for e in root.iter()
                   if e.get(_X + "Name") and not _in_a_template(root, e)]
        dupes = sorted(set(n for n in outside if outside.count(n) > 1))
        self.assertEqual(dupes, [])

    def test_bindings_resolve_to_row_slots(self):
        """§12.7.G -- a binding path with no slot renders an empty cell."""
        missing = sorted(binding_paths() - slots_in_script())
        self.assertEqual(missing, [], "no __slots__ for: {0}".format(missing))

    def test_the_row_checkbox_binds_the_containers_own_flag(self):
        """§12.7.Q -- a Python bool does not coerce in this engine.

        The tick has to come from the native ``ListBoxItem.IsSelected``, and
        the Python side mirrors ``SelectedItems`` rather than the other way
        round.
        """
        source = _read(_XAML)
        self.assertIn("RelativeSource AncestorType=ListBoxItem", source)
        self.assertIn("SelectedItems", _read(_SCRIPT))

    def test_the_scrollbar_style_covers_both_orientations(self):
        """§12.7.P -- a vertical-only style renders a broken horizontal bar."""
        source = _read(_XAML)
        self.assertIn("Orientation", source)
        self.assertIn("PageLeftCommand", source)
        self.assertIn("PageUpCommand", source)

    def test_the_editable_combobox_part_is_present(self):
        """§12.7.C -- without PART_EditableTextBox, editable mode dies quietly."""
        self.assertIn("PART_EditableTextBox", _read(_XAML))

    def test_every_interactive_control_carries_a_tooltip(self):
        """The window has a lot of switches; each one says what it does."""
        root = _tree()
        problems = []
        for element in root.iter():
            if _tag(element) not in ("Button", "TextBox", "ComboBox", "ListBox",
                                     "CheckBox", "RadioButton"):
                continue
            if _in_a_template(root, element):
                continue
            if not element.get("ToolTip"):
                problems.append("{0} {1}".format(
                    _tag(element), element.get(_X + "Name") or "(unnamed)"))
        self.assertEqual(problems, [], "no tooltip: " + "; ".join(problems))

    def test_a_lists_action_button_sits_beside_the_list(self):
        """A control below the scroll fold is a control that does not exist.

        ``RemoveConditionBtn`` was built, wired and working, and sat UNDER a
        fixed-height list inside a ScrollViewer -- so it was off the bottom of
        the visible area and the project owner reported it as never built.

        The rule that came out of it: an action belongs in the same container
        as the thing it acts on. Then it is on screen exactly when its target
        is, and no amount of scrolling can separate them.
        """
        root = _tree()
        for parent in root.iter():
            children = list(parent)
            tags = [_tag(child) for child in children]
            names = [child.get(_X + "Name") for child in children]
            if "ConditionList" in names:
                self.assertIn("RemoveConditionBtn", names,
                              "Remove is not a sibling of the list it empties")
                return
            del tags
        self.fail("ConditionList is not in the XAML")

    def test_the_conditions_list_offers_more_than_one_way_to_remove(self):
        """The button is the obvious one; double-click is the one a modeller
        reaches for first, and it costs a single wiring line."""
        self.assertIn("ConditionList.MouseDoubleClick", _read(_SCRIPT))

    def test_the_hint_strip_says_what_pressing_a_rule_does(self):
        """The one promise the window must never stop making."""
        source = _read(_XAML)
        self.assertIn("isolates", source)
        self.assertIn("Nothing is written to the project", source)

    def test_the_theme_is_the_sanctioned_inline_copy(self):
        """§12.3 -- an inline theme must be a verbatim copy, never a variant.

        The tool adds no styles of its own, so every keyed style it uses has to
        exist in the Modeless reference. A key here that is not there means the
        copy has been hand-edited, which §12.3 calls a defect.
        """
        reference = _read(os.path.join(
            _ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
            "Testing.stack", "Modeless.pushbutton", "ui.xaml"))
        for key in sorted(resource_uses()):
            self.assertIn('x:Key="{0}"'.format(key), reference,
                          "{0} is not in the sanctioned theme".format(key))


class ScriptWiringTests(unittest.TestCase):

    def test_every_looked_up_control_exists_in_the_xaml(self):
        missing = sorted(bound_control_names() - set(window_names()))
        self.assertEqual(missing, [], "FindName with no control: {0}".format(missing))

    def test_every_named_control_the_xaml_defines_is_bound(self):
        """A name in the window scope that nothing looks up is dead weight."""
        unused = sorted(set(window_names()) - bound_control_names())
        self.assertEqual(unused, [], "never looked up: {0}".format(unused))

    def test_the_handler_follows_the_three_pythonnet_rules(self):
        """§12.8.7.1 -- each of these fails at instantiation or on press two."""
        tree = ast.parse(_read(_SCRIPT))
        handlers = [n for n in ast.walk(tree)
                    if isinstance(n, ast.ClassDef)
                    and any(getattr(b, "id", "") == "IExternalEventHandler"
                            for b in n.bases)]
        self.assertEqual(len(handlers), 1, "exactly one handler class")
        handler = handlers[0]

        assigned = [t.id for node in handler.body
                    if isinstance(node, ast.Assign)
                    for t in node.targets if isinstance(t, ast.Name)]
        self.assertIn("__namespace__", assigned, "rule 1: __namespace__")

        methods = [n.name for n in handler.body if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("__init__", methods, "rule 2: no __init__")

        # rule 3: defined once per session, behind a sys.modules cache
        source = _read(_SCRIPT)
        self.assertIn("_state.handler_cls", source)
        self.assertIn("sys.modules[_STATE_MODULE]", source)

    def test_the_handler_is_defined_inside_the_guard_not_at_module_level(self):
        """Bridge Listener had ``__namespace__`` at module scope, where it does
        nothing. Re-running the class statement is what raises on press two."""
        tree = ast.parse(_read(_SCRIPT))
        top_level = set(id(node) for node in tree.body)
        for node in ast.walk(tree):
            if (isinstance(node, ast.ClassDef)
                    and any(getattr(b, "id", "") == "IExternalEventHandler"
                            for b in node.bases)):
                self.assertNotIn(id(node), top_level,
                                 "the handler class is at module level")

    def test_no_revit_object_is_promised_across_the_thread_boundary(self):
        """§12.8.7.2 -- requests and answers carry plain data only.

        ``serve`` runs on Revit's thread and everything it returns is read on
        the WPF thread, so it may only build dicts of ints and strings.
        """
        tree = ast.parse(_read(_SCRIPT))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "serve":
                returned = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                self.assertTrue(returned)
                for one in returned:
                    self.assertIsInstance(
                        one.value, ast.Dict,
                        "serve() must return a plain dict, not a Revit object")
                return
        self.fail("serve() not found")

    def test_the_selection_lists_are_rebuilt_behind_a_flag_not_a_detach(self):
        """``event -= self._handler`` may remove nothing.

        ``self._handler`` builds a new bound method on every attribute access,
        so pythonnet can wrap a different delegate. A flag cannot be got wrong.
        """
        source = _read(_SCRIPT)
        self.assertNotIn("SelectionChanged -=", source)
        self.assertIn("self.rebuilding", source)

    def test_no_regular_expressions(self):
        """§12.9.3 -- `re` is missing from this engine's stripped stdlib."""
        for node in ast.walk(ast.parse(_read(_SCRIPT))):
            if isinstance(node, ast.Import):
                self.assertNotIn("re", [a.name for a in node.names])
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "re")

    def test_no_pyrevit_import(self):
        """§12.8.4 -- pyRevit's IronPython modules crash the CPython 3 engine."""
        source = _read(_SCRIPT)
        self.assertNotIn("from pyrevit", source)
        self.assertNotIn("import pyrevit", source)

    def test_the_thinking_is_not_in_the_script(self):
        """The window is wiring. The rule engine is tested elsewhere, and it
        stays there -- a comparison written in here would be untested."""
        source = _read(_SCRIPT)
        self.assertIn("from anongee_filterrules import", source)
        self.assertNotIn("def compare(", source)
        self.assertNotIn("def parse_number(", source)

    def test_the_script_selects_the_cpython_engine(self):
        self.assertTrue(_read(_SCRIPT).startswith("#! python3"))


class VersionTests(unittest.TestCase):
    """Four copies of one number, held together so the header cannot lie."""

    def version(self):
        import sys
        lib = os.path.join(_ROOT, "AnonGee.extension", "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import anongee_filterrules
        return anongee_filterrules.VERSION

    def test_the_bundle_agrees(self):
        self.assertIn("Version: {0}".format(self.version()),
                      _read(os.path.join(_BUTTON, "bundle.yaml")))

    def test_the_changelog_leads_with_it(self):
        headings = [line[3:].strip()
                    for line in _read(os.path.join(_BUTTON, "CHANGELOG.md")).splitlines()
                    if line.startswith("## ")]
        self.assertTrue(headings)
        self.assertTrue(headings[0].startswith(self.version()), headings[0])

    def test_the_window_header_shows_it(self):
        """The badge in the header is the build actually running; quote it."""
        self.assertIn('x:Name="VersionText"', _read(_XAML))
        self.assertIn("self.VersionText.Text = VERSION", _read(_SCRIPT))


if __name__ == "__main__":                                    # pragma: no cover
    unittest.main(verbosity=2)
