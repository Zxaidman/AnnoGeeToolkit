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
import sys
import unittest
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "AnonGee.extension", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from anongee_filterrules import store                              # noqa: E402
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


def _own_returns(node):
    """Every ``return`` belonging to *node* itself, nested defs excluded."""
    found = []
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.Lambda, ast.ClassDef)):
            continue                      # its returns are its own
        if isinstance(current, ast.Return):
            found.append(current)
        stack.extend(ast.iter_child_nodes(current))
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

    def test_every_filter_rule_row_carries_its_own_remove(self):
        """BUG-3 was a Remove button below the fold of the list it emptied.
        The answer then was to move it beside the list; the answer now is
        better -- Revit edits each rule in place, so each row removes itself
        and there is no shared button to misplace.
        """
        source = _read(_SCRIPT)
        self.assertIn("def _remove_button(", source)
        self.assertIn("self.owner._remove_row(self)", source)
        for gone in ("RemoveConditionBtn", "ConditionList"):
            self.assertNotIn('x:Name="{0}"'.format(gone), _read(_XAML), gone)

    def test_the_three_columns_are_laid_out_like_revits_own_dialog(self):
        """Revit's Filters dialog is Filters | Categories | Filter Rules, and
        a modeller already knows where to look. The SHAPE is Revit's; every
        control, colour and type style in it is ours."""
        source = _read(_XAML)
        for heading in ("Saved rules", "Categories", "Filter rules"):
            self.assertIn('Text="{0}"'.format(heading), source)
        for native in ("AND (all rules must be true)",
                       "OR (any rule may be true)",
                       "Hide un-ticked categories"):
            self.assertIn(native, source)
        names = set(window_names())
        for control in ("CheckAllBtn", "CheckNoneBtn", "HideUnpicked",
                        "ConditionRows"):
            self.assertIn(control, names)

    def test_the_cascade_survived_the_relayout(self):
        """Revit's dialog has no family or type. Ours does, it is worth
        keeping, and it belongs under the categories because it answers the
        same question -- what the rule looks in."""
        names = set(window_names())
        self.assertIn("FamilyCombo", names)
        self.assertIn("TypeCombo", names)

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


def methods_assigning(attribute):
    """``{method name: source}`` for every method that assigns ``self.<attr>``."""
    source = _read(_SCRIPT)
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Assign):
                continue
            for target in inner.targets:
                if (isinstance(target, ast.Attribute)
                        and target.attr == attribute
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    found[node.name] = ast.get_source_segment(source, node) or ""
    return found


_VIEWS_XAML = os.path.join(_BUTTON, "views.xaml")


class MultiViewTests(unittest.TestCase):
    """FEAT-11 -- one rule, several views, one Undo."""

    def _body(self, name):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(source, node) or ""
        self.fail("{0} is not in script.py".format(name))

    def test_the_picker_xaml_is_well_formed(self):
        ET.parse(_VIEWS_XAML)

    def test_every_control_the_picker_looks_up_exists_in_its_xaml(self):
        names_in_xaml = set()
        for element in ET.parse(_VIEWS_XAML).getroot().iter():
            name = element.get(_X + "Name")
            if name:
                names_in_xaml.add(name)
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == "ViewPicker":
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Assign)
                            and any(getattr(t, "id", "") == "NAMES"
                                    for t in inner.targets)):
                        wanted = set(ast.literal_eval(inner.value))
                        missing = sorted(wanted - names_in_xaml)
                        self.assertEqual(missing, [], missing)
                        return
        self.fail("ViewPicker.NAMES is not in script.py")

    def test_the_picker_uses_the_same_theme_as_the_window_it_opens_from(self):
        """The two sit side by side on screen; any difference would show."""
        picker = _read(_VIEWS_XAML)
        window = _read(_XAML)
        for key in ("ButtonPrimary", "ButtonGhost", "InputTextBox",
                    "GridCheckBox", "TextCaption"):
            self.assertIn('x:Key="{0}"'.format(key), picker)
            self.assertIn('x:Key="{0}"'.format(key), window)

    def test_the_picker_touches_no_revit_api(self):
        """It is handed plain rows and hands back plain ids, so it can be
        opened straight from the WPF thread without an external event
        (§12.8.7.2). A Revit object here would be a crash, not a bug."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == "ViewPicker":
                body = ast.get_source_segment(source, node) or ""
                for banned in ("revit_query", "revit_apply", "Transaction",
                               "doc.", "uidoc"):
                    self.assertNotIn(banned, body, banned)
                return
        self.fail("ViewPicker is not in script.py")

    def test_views_that_cannot_be_isolated_are_listed_with_the_reason(self):
        """Hiding them leaves a modeller hunting for a schedule that is simply
        not there, with nothing to say it was excluded on purpose."""
        self.assertIn("cannot be isolated", _read(_SCRIPT))

    def test_select_all_leaves_the_unusable_ones_alone(self):
        """Ticking something that will be refused is a promise the picker
        cannot keep."""
        self.assertIn("if row.Usable", self._body("_on_all"))

    def test_a_ticked_view_that_cannot_be_isolated_is_dropped_and_recorded(self):
        """Otherwise the count on the next screen is lower than the tick count
        with nothing to explain the difference."""
        body = self._body("_on_apply")
        self.assertIn("refused", body)
        self.assertIn("diagnostics.record(", body)

    def test_a_search_does_not_untick_what_it_filters_out(self):
        body = self._body("_rebuild")
        self.assertIn("self.rebuilding = True", body)
        self.assertIn("SelectedItems.Add(row)", body)

    def test_the_rule_is_asked_for_before_the_views_are(self):
        """No point listing two hundred views for a rule that will not pass
        validation."""
        body = self._body("_on_views")
        self.assertLess(body.index("_guard_rule()"), body.index('kind="views"'))
        # And it must actually STOP on a bad rule, not merely ask first.
        self.assertIn("if payload is None:", body)
        self.assertLess(body.index("if payload is None:"),
                        body.index('kind="views"'))

    def test_every_view_is_reported_including_the_skipped_ones(self):
        """A multi-view apply that says "done" while quietly doing nothing in
        four of eleven views is the failure this is written against."""
        body = self._body("_report_many")
        self.assertIn("skipped", body)
        self.assertIn("diagnostics.record(", body)


_DIALOG_XAML = os.path.join(_BUTTON, "dialog.xaml")


class BrandedDialogTests(unittest.TestCase):
    """Every question this tool asks, in our own chrome."""

    def test_the_dialog_xaml_is_well_formed(self):
        ET.parse(_DIALOG_XAML)

    def test_every_control_the_dialog_looks_up_exists_in_its_xaml(self):
        present = set()
        for element in ET.parse(_DIALOG_XAML).getroot().iter():
            name = element.get(_X + "Name")
            if name:
                present.add(name)
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == "Ask":
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Assign)
                            and any(getattr(t, "id", "") == "NAMES"
                                    for t in inner.targets)):
                        missing = sorted(set(ast.literal_eval(inner.value))
                                         - present)
                        self.assertEqual(missing, [], missing)
                        return
        self.fail("Ask.NAMES is not in script.py")

    def test_it_wears_the_same_theme_as_the_window_behind_it(self):
        dialog = _read(_DIALOG_XAML)
        window = _read(_XAML)
        for key in ("ButtonPrimary", "ButtonGhost", "InputTextBox",
                    "TextH2OnDark", "CardBorder"):
            self.assertIn('x:Key="{0}"'.format(key), dialog)
            self.assertIn('x:Key="{0}"'.format(key), window)

    def test_revit_task_dialogs_are_gone_from_the_window(self):
        """Two are left on purpose and both run BEFORE the window exists: no
        window to parent to, and if XAML loading is what broke then reporting
        it through more XAML reports nothing."""
        source = _read(_SCRIPT)
        uses = []
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.FunctionDef)
                    and node.name.startswith("_on_")):
                continue
            body = ast.get_source_segment(source, node) or ""
            if "TaskDialog" in body:
                uses.append(node.name)
        self.assertEqual(uses, [], "still using Revit's dialog: {0}".format(uses))

    def test_a_refusal_offers_no_choice_it_cannot_honour(self):
        """One button. Offering a Cancel where there is nothing to cancel is
        how a Cancel gets pressed out of habit."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "tell":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("no=None", body)
                return
        self.fail("Ask.tell is not in script.py")

    def test_the_dialog_touches_no_revit_api(self):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == "Ask":
                body = ast.get_source_segment(source, node) or ""
                for banned in ("revit_query", "revit_apply", "Transaction",
                               "uidoc", "TaskDialog"):
                    self.assertNotIn(banned, body.replace(
                        "It replaces Revit's ``TaskDialog``", ""), banned)
                return
        self.fail("Ask is not in script.py")


class FilterNameTests(unittest.TestCase):
    """FEAT-13 -- the name is the team's to choose."""

    def _body(self, name):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(source, node) or ""
        self.fail("{0} is not in script.py".format(name))

    def test_the_name_is_editable_before_anything_is_created(self):
        body = self._body("_on_make_filter")
        self.assertIn("Ask.edit(", body)
        self.assertIn('field="Filter name"', body)

    def test_the_typed_name_is_what_gets_created(self):
        self.assertIn('request.get("filter_name")', _read(_SCRIPT))

    def test_the_prefix_is_remembered_from_what_they_typed(self):
        body = self._body("_on_make_filter")
        self.assertIn("filters.prefix_of(", body)
        self.assertIn("store.set_filter_prefix(", body)

    def test_a_duplicate_name_is_refused_in_a_dialog(self):
        """A refusal that only reaches the status bar is one somebody presses
        through twice before reading it -- and this action writes to the model
        when it succeeds."""
        self.assertIn('Ask.tell(self.window, "No filter was created"',
                      _read(_SCRIPT))


class ToggleSelectionTests(unittest.TestCase):
    """A click ticks; the same click again unticks. Both lists, same way."""

    def _body(self, name, inside="FilterViewApp"):
        """A method of *inside*. There are three ``_wire`` methods in this
        file now -- the window's, the view picker's and the dialog's -- and
        walking the whole tree for a name finds whichever was written first."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.ClassDef) and node.name == inside):
                continue
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef) and inner.name == name:
                    return ast.get_source_segment(source, inner) or ""
        self.fail("{0}.{1} is not in script.py".format(inside, name))

    def test_both_lists_toggle_on_a_plain_click(self):
        """Extended's own plain click REPLACES the selection, so clicking a
        ticked row leaves it ticked and clears everything else -- which makes
        the tick look like it is not really a tick."""
        wiring = self._body("_wire")
        self.assertIn("self.RuleList.PreviewMouseLeftButtonDown", wiring)
        self.assertIn("self.CategoryList.PreviewMouseLeftButtonDown", wiring)

    def test_the_two_lists_share_one_handler(self):
        """Two handlers would drift, and the whole complaint was that the two
        lists did not behave the same."""
        wiring = self._body("_wire")
        self.assertEqual(wiring.count("self._toggle_click"), 2)

    def test_ctrl_and_shift_are_left_entirely_alone(self):
        """They mean what they mean everywhere in Windows, and
        re-implementing them here would only get them subtly wrong."""
        body = self._body("_toggle_click")
        self.assertIn("if Keyboard.Modifiers != NO_MODIFIER:", body)
        self.assertLess(body.index("NO_MODIFIER"), body.index("IsSelected"))

    def test_the_click_toggles_rather_than_merely_selecting(self):
        """The whole complaint: a plain click on a ticked row has to UNTICK
        it. Setting IsSelected = True does everything this handler does except
        the one thing it exists for."""
        body = self._body("_toggle_click")
        self.assertIn("item.IsSelected = not item.IsSelected", body)

    def test_the_default_click_is_suppressed_after_a_toggle(self):
        """Or WPF's own click runs afterwards and replaces what was toggled."""
        self.assertIn("args.Handled = True", self._body("_toggle_click"))

    def test_both_category_buttons_act_on_what_is_shown(self):
        """With a search in the box, "check all" means the search results --
        not all 137 categories, which nobody has ever meant."""
        for name in ("_on_check_all", "_on_check_none"):
            body = self._body(name)
            self.assertIn("self.CategoryList.Items", body)
            self.assertIn("self._refresh_cascade()", body)

    def test_the_category_list_takes_a_multiple_selection(self):
        for element in _tree().iter():
            if element.get(_X + "Name") == "CategoryList":
                self.assertEqual(element.get("SelectionMode"), "Extended")
                return
        self.fail("CategoryList is not in the XAML")


class ConditionRowTests(unittest.TestCase):
    """Revit edits each rule in place, on its own row."""

    def _class_body(self, name):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name == name:
                return ast.get_source_segment(source, node) or ""
        self.fail("{0} is not in script.py".format(name))

    def test_rows_are_built_in_python_and_not_from_a_datatemplate(self):
        """§12.7.G -- a DataTemplate binding to a Python property fails
        SILENTLY in this engine: blank cells, no error. Real controls, added
        and read back directly, cannot fail that way."""
        body = self._class_body("ConditionEditor")
        self.assertIn("ComboBox()", body)
        self.assertIn("TextBox()", body)
        self.assertNotIn("ItemsSource", body)

    def test_a_row_keeps_its_parameter_across_a_cascade(self):
        """Ticking another category must not silently re-point a rule row at
        whatever happens to be first in the new list.

        Scoped to ``fill_parameters``: ``pending_parameter`` is set in
        ``__init__`` too, so looking for it anywhere in the class passes even
        when the refill throws it away.
        """
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.ClassDef)
                    and node.name == "ConditionEditor"):
                continue
            for inner in node.body:
                if (isinstance(inner, ast.FunctionDef)
                        and inner.name == "fill_parameters"):
                    body = ast.get_source_segment(source, inner) or ""
                    self.assertIn("self.pending_parameter", body)
                    self.assertIn("self.parameter_name()", body)
                    return
        self.fail("ConditionEditor.fill_parameters is not in script.py")

    def test_the_rule_is_read_from_the_rows(self):
        """The rows are the truth once the editor is open; ``self.conditions``
        is only what was loaded."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "current_rule":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("row.read() for row in self.rows", body)
                return
        self.fail("current_rule is not in script.py")

    def test_an_empty_row_is_allowed_to_exist(self):
        """An empty row IS the thing being added. Refusing to add one until it
        is already correct is the opposite of editing in place."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_on_add_condition":
                body = ast.get_source_segment(source, node) or ""
                self.assertNotIn("problems", body)
                return
        self.fail("_on_add_condition is not in script.py")

    def test_every_row_handler_is_guarded(self):
        body = self._class_body("ConditionEditor")
        bare = [line.strip() for line in body.split("\n")
                if "+=" in line and "self._guard(" not in line]
        self.assertEqual(bare, [], "not guarded: {0}".format(bare))


class ServeHelperTests(unittest.TestCase):
    """The crash that shipped in 0.6.0, and the gate that now refuses it.

    ``serve`` imports the Revit modules as **locals**. A ``_serve_*`` helper is
    a different function and cannot see them, so ``_serve_views`` raised
    ``NameError: name 'revit_query' is not defined`` on every press of Views.

    The diagnostics named it exactly -- tag, cause and file -- which is why it
    took one screenshot rather than a round trip. This gate is so the next one
    does not need the screenshot either.
    """

    #: The modules ``serve`` imports locally. Any of these used in a helper
    #: must be imported by that helper.
    ENGINE = ("revit_query", "revit_apply", "revit_filter", "compat")

    def test_every_serve_helper_imports_what_it_uses(self):
        source = _read(_SCRIPT)
        tree = ast.parse(source)
        problems = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef)
                    and node.name.startswith("_serve_")):
                continue
            imported = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom):
                    imported.update(alias.name for alias in inner.names)
            used = set()
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Attribute)
                        and isinstance(inner.value, ast.Name)
                        and inner.value.id in self.ENGINE):
                    used.add(inner.value.id)
            for name in sorted(used - imported):
                problems.append("{0} uses {1} without importing it".format(
                    node.name, name))
        self.assertEqual(problems, [], "; ".join(problems))


class LiveCountTests(unittest.TestCase):
    """FEAT-8 -- the number follows the rule instead of waiting to be asked.

    0.6.0 debounced with a ``DispatcherTimer`` and the count never arrived: it
    sat on "counting..." for a whole session in Revit. A timer that does not
    tick fails **silently** -- no exception, no answer, nothing to tell it
    apart from a slow model -- so 0.7.0 has no timer. It clocks itself off the
    answers, which is a thing the suite can actually reason about.
    """

    def _body(self, name):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(source, node) or ""
        self.fail("{0} is not in script.py".format(name))

    def test_the_count_hangs_off_the_one_call_every_change_already_makes(self):
        """A category ticked, a family chosen, a condition added, a rule
        loaded -- all of them end at ``_validate``. Hooking the count to a
        list of controls instead would be forgotten the next time one is
        added, which is exactly how BUG-13 happened."""
        self.assertIn("self._bump_count(", self._body("_validate"))

    def test_there_is_no_timer_left_anywhere(self):
        """The whole class of failure 0.6.0 hit. A DispatcherTimer that never
        ticks cannot be distinguished from a model that never answers."""
        source = _read(_SCRIPT)
        for banned in ("DispatcherTimer", "Debounce", "count_timer"):
            self.assertNotIn(banned, source.replace("``DispatcherTimer``", ""),
                             banned)

    def test_a_stale_number_is_withdrawn_before_the_new_one_arrives(self):
        """A number left sitting there while a new one is computed is worse
        than no number: it looks settled."""
        body = self._body("_bump_count")
        self.assertIn('self.LiveCount.Text = "counting..."', body)
        self.assertIn("self._pump_count()", body)

    def test_an_invalid_rule_shows_no_count_at_all(self):
        body = self._body("_bump_count")
        self.assertIn("if problems:", body)
        self.assertIn("self.count_wanted = False", body)

    def test_counts_cannot_stack_on_a_slow_model(self):
        """A change while one is in flight only sets the flag."""
        self.assertIn("if self.counting or not self.count_wanted:",
                      self._body("_pump_count"))

    def test_the_answer_is_what_clocks_the_next_one(self):
        """This is what replaces the timer: every answer pumps, so the rate is
        whatever Revit can manage and a request can never be left unasked."""
        body = self._body("_receive")
        self.assertGreaterEqual(body.count("self._pump_count()"), 2,
                                "both the answer and the error path must pump")

    def test_a_failed_count_does_not_stop_the_live_count(self):
        """The two flags must not be able to wedge: one bad answer stopping
        the count for the rest of the session is the 0.6.0 failure again."""
        body = self._body("_receive")
        # Unlatched before the error check, so a failed count unlatches too...
        self.assertLess(body.index("self.counting = False"),
                        body.index('problem = answer.get("error")'))
        # ...and the error path pumps, so the NEXT count is still asked for.
        self.assertIn('self._status(problem, "error")\n'
                      '            if kind == "count":\n'
                      '                self._pump_count()', body)

    def test_the_live_count_does_not_talk_over_the_status_bar(self):
        """It writes the same label as the Count button and says nothing else,
        or it would overwrite whatever the user was being told."""
        self.assertIn('if answer.get("tag") != "FEAT-8":', self._body("_receive"))

    def test_the_tag_comes_back_with_the_answer(self):
        """Without it every answer looks untagged and the suppression above
        never fires -- which is exactly what shipped in 0.6.0."""
        self.assertIn('answer.setdefault("tag", request.get("tag", "UI"))',
                      _read(_SCRIPT))


class RuleStoreTests(unittest.TestCase):
    """FEAT-14 -- a rule can live beside the model, and can move there."""

    def _radios(self):
        found = {}
        for element in _tree().iter():
            name = element.get(_X + "Name") or ""
            if name.startswith("Store") and _tag(element) == "RadioButton":
                found[name] = element
        return found

    def test_the_editor_offers_every_store_the_engine_knows(self):
        """Three now (FEAT-19). Checked against the engine rather than a
        hardcoded list, so adding a fourth store without a radio for it fails
        here rather than being a destination nobody can pick."""
        self.assertEqual(
            sorted(self._radios()),
            ["StoreMachineRadio", "StoreProjectRadio", "StoreSharedRadio"])
        self.assertEqual(
            sorted((store.MACHINE, store.PROJECT, store.SHARED)),
            sorted(("machine", "project", "shared")))

    def test_the_two_stores_are_one_choice_and_not_two_switches(self):
        """Without a shared GroupName both can be on at once, and a rule would
        be marked for two files."""
        groups = set(radio.get("GroupName") for radio in self._radios().values())
        self.assertEqual(len(groups), 1, "the store radios are not one group")
        self.assertNotIn(None, groups)

    def test_it_is_radios_and_not_the_toggle_switch(self):
        """§9.9 reserves the toggle for a binary on/off. This is a choice
        between two NAMED places, and a toggle cannot label either side."""
        for radio in self._radios().values():
            self.assertNotEqual(radio.get("Style"),
                                "{StaticResource ToggleSwitch}")

    def test_a_saved_rule_carries_the_store_it_was_marked_for(self):
        """``current_rule()`` is what Save writes. Without the source on it the
        rule is written wherever the default happens to land, and the radio is
        decoration."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "current_rule":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("source=", body)
                return
        self.fail("current_rule is not in script.py")

    def test_saving_writes_both_stores(self):
        """A move is a write to BOTH files -- added to one, gone from the
        other. Writing only the store a rule arrived in leaves the old copy on
        disk and the next load shows it twice."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_write":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("store.save_all(", body)
                return
        self.fail("_write is not in script.py")

    def test_the_store_is_asked_for_rather_than_read_off_the_radio(self):
        """An unsaved model has no folder, so a rule can never be marked for a
        project file that does not exist."""
        self.assertIn("store.destination(", _read(_SCRIPT))

    def test_loading_a_rule_points_the_radios_at_where_it_came_from(self):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_on_rule_selected":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("_show_store(rule.source)", body)
                return
        self.fail("_on_rule_selected is not in script.py")

    def test_the_disabled_store_says_why_it_is_disabled(self):
        """§8.2 and §10.3 -- a greyed control with no sentence beside it reads
        as the tool being broken rather than as the model needing a save."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_show_store_hint":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("StoreProjectRadio.IsEnabled", body)
                self.assertIn("never been saved", body)
                return
        self.fail("_show_store_hint is not in script.py")

    def test_the_hint_is_bound_and_shown(self):
        self.assertIn("StoreHint", window_names())


class CascadeTests(unittest.TestCase):
    """BUG-13 -- what the editor shows must follow what is picked.

    Loading a saved rule set ``self.picked`` and redrew the category list, and
    stopped there. ``_rebuild_categories`` raises the ``rebuilding`` flag
    around its own selection loop -- rightly, or a search would re-ask Revit
    on every keystroke -- so ``_on_category_selected`` never ran and nothing
    ever asked Revit for the families, types and parameters.

    The editor therefore showed the rule's name, categories and conditions and
    nothing else. And because ``current_rule()`` reads the family and type off
    those two empty combos, **Apply, Count and Select built a rule with no
    family and no type** and isolated a broader set than the rule named. A
    silent wrong answer, not a blank box.
    """

    EXEMPT = ("__init__",)      # runs before there is a model to ask about

    def test_every_path_that_changes_the_categories_refreshes_the_cascade(self):
        """The invariant, stated once and checked everywhere.

        Naming the three methods individually would pass the day a fourth is
        written, which is precisely how BUG-13 arrived.
        """
        missing = []
        for name, body in sorted(methods_assigning("picked").items()):
            if name in self.EXEMPT or name == "_refresh_cascade":
                continue
            if "_refresh_cascade()" not in body:
                missing.append(name)
        self.assertEqual(
            missing, [],
            "these change self.picked without re-reading the cascade, so the "
            "Family, Type and Parameter lists go stale: {0}".format(missing))

    def test_loading_a_rule_asks_revit_for_its_family_and_type(self):
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_on_rule_selected":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("_refresh_cascade()", body)
                # Order matters: _receive consumes the pendings when the answer
                # lands, so they have to be set before the answer is asked for.
                self.assertLess(body.index("self.pending_family"),
                                body.index("self._refresh_cascade()"),
                                "the cascade is asked for before the family "
                                "and type it is meant to restore are recorded")
                return
        self.fail("_on_rule_selected is not in script.py")

    def test_a_pending_family_is_dropped_when_nothing_can_consume_it(self):
        """With no categories picked no cascade is asked for and no answer
        arrives. A pending left set is applied to whatever rule is being
        edited when the NEXT one lands -- one rule's family appearing on
        another, with nothing on screen to explain it."""
        for node in ast.walk(ast.parse(_read(_SCRIPT))):
            if isinstance(node, ast.FunctionDef) and node.name == "_refresh_cascade":
                body = ast.get_source_segment(_read(_SCRIPT), node) or ""
                head = body[:body.index("self._fill_combo")]
                self.assertIn("self.pending_family = None", head)
                self.assertIn("self.pending_type = None", head)
                return
        self.fail("_refresh_cascade is not in script.py")

    def test_both_pendings_are_consumed_where_the_answer_lands(self):
        """They are cleared as they are applied, or the next cascade re-applies
        them to a rule that never had them."""
        source = _read(_SCRIPT)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_receive":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("self.pending_family = None", body)
                self.assertIn("self.pending_type = None", body)
                return
        self.fail("_receive is not in script.py")


class RuleSelectionTests(unittest.TestCase):
    """Ctrl+click, Shift+click and the tick that reports them."""

    def _rule_list(self):
        for element in _tree().iter():
            if element.get(_X + "Name") == "RuleList":
                return element
        self.fail("RuleList is not in the XAML")

    def test_the_saved_rules_list_takes_a_multiple_selection(self):
        """``Extended`` is the whole of Ctrl+click and Shift+click -- WPF does
        both natively -- and is the mode cad2bim's layer mapping already uses,
        so the two tools behave the same way under the same gesture."""
        self.assertEqual(self._rule_list().get("SelectionMode"), "Extended")

    def test_the_rows_stretch_so_the_tick_column_lines_up(self):
        """Left-aligned rows make a ragged column of checkboxes, and the ones
        beside a short rule name sit nowhere near the ones beside a long."""
        self.assertEqual(self._rule_list().get("HorizontalContentAlignment"),
                         "Stretch")

    def test_the_tick_reports_the_selection_rather_than_being_a_second_one(self):
        """§12.7.Q. A Python bool does not coerce for ``IsChecked``, so the
        binding goes to the native container's own ``IsSelected``; and it is
        one-way and not hit-testable, so clicking the box selects the row
        exactly as clicking the name does. Two independent notions of
        "chosen" in one list is the bug this avoids.
        """
        for element in _tree().iter():
            if _tag(element) != "CheckBox":
                continue
            checked = element.get("IsChecked") or ""
            if "IsSelected" not in checked:
                continue
            self.assertIn("RelativeSource", checked)
            self.assertIn("Mode=OneWay", checked)
            self.assertEqual(element.get("IsHitTestVisible"), "False")
            return
        self.fail("no checkbox is bound to its row's IsSelected")

    def test_the_list_offers_all_four_places_to_move_a_rule(self):
        """One place at a time is fine for two rules and useless for thirty."""
        names = set(window_names())
        for name in ("MoveUpBtn", "MoveDownBtn", "MoveTopBtn", "MoveBottomBtn"):
            self.assertIn(name, names)

    def test_the_editor_does_not_load_a_rule_when_several_are_selected(self):
        """There is one editor and it cannot show two rules. Loading the last
        one clicked would silently discard whatever was being edited."""
        self.assertIn("SelectedItems.Count != 1", _read(_SCRIPT))

    def test_moving_keeps_the_block_selected(self):
        """A move rewrites the list, which drops the selection. Without the
        memo the block you just moved is deselected and the second press does
        nothing -- which reads as the button being broken."""
        source = _read(_SCRIPT)
        self.assertIn("_keep_selected", source)
        # Scoped to _rebuild_rules: the category list re-ticks itself the same
        # way, so an unscoped search is green whatever this function does.
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_rebuild_rules":
                body = ast.get_source_segment(source, node) or ""
                self.assertIn("_keep_selected", body)
                self.assertIn("SelectedItems.Add(row)", body)
                return
        self.fail("_rebuild_rules is not in script.py")

    def test_the_bulk_actions_go_through_the_tested_block_move(self):
        """``move`` one at a time reverses a selection going up and collapses
        it going down. The block move is in ``RuleSet.reorder``, where it can
        be tested without a window."""
        tree = ast.parse(_read(_SCRIPT))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_move":
                body = ast.get_source_segment(_read(_SCRIPT), node) or ""
                self.assertIn("rule_set.reorder(", body)
                return
        self.fail("_move is not in script.py")

    def test_delete_removes_the_whole_selection_in_one_go(self):
        self.assertIn("remove_many(", _read(_SCRIPT))


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
        # ``serve`` and anything it delegates to. A branch lifted into a
        # ``_serve_*`` helper is still on Revit's thread and still answers
        # across the boundary, so the same rule applies to it -- and a gate
        # that only looked at ``serve`` would be satisfied by moving the
        # offending return one method away.
        answering = [n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef)
                     and (n.name == "serve" or n.name.startswith("_serve_"))]
        self.assertTrue(any(n.name == "serve" for n in answering),
                        "serve() not found")
        for node in answering:
            # The function's OWN returns. A nested helper defined inside serve
            # -- a find_ids closure handed to revit_apply -- returns element
            # ids, and that is not serve answering across the boundary.
            returned = _own_returns(node)
            self.assertTrue(returned, node.name)
            for one in returned:
                if isinstance(one.value, ast.Dict):
                    continue
                delegated = (isinstance(one.value, ast.Call)
                             and isinstance(one.value.func, ast.Attribute)
                             and one.value.func.attr.startswith("_serve_"))
                self.assertTrue(
                    delegated,
                    "{0}() must return a plain dict or delegate to another "
                    "_serve_ helper, not a Revit object".format(node.name))

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
