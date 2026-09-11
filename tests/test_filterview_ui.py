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


class LiveCountTests(unittest.TestCase):
    """FEAT-8 -- the number follows the rule instead of waiting to be asked."""

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

    def test_a_stale_number_is_withdrawn_before_the_new_one_arrives(self):
        """A number left sitting there while a new one is computed is worse
        than no number: it looks settled."""
        body = self._body("_bump_count")
        self.assertIn('self.LiveCount.Text = "counting..."', body)
        self.assertIn("self.count_timer.reset()", body)

    def test_an_invalid_rule_shows_no_count_at_all(self):
        body = self._body("_bump_count")
        self.assertIn("if problems:", body)
        self.assertIn("self.count_timer.stop()", body)

    def test_the_debounce_restarts_rather_than_merely_starts(self):
        """A DispatcherTimer already running does not restart its interval on
        Start, so without the Stop a user typing steadily never reaches a
        quiet period and the count never arrives."""
        body = self._body("reset")
        self.assertLess(body.index("Stop()"), body.index("Start()"))

    def test_counts_cannot_stack_on_a_slow_model(self):
        self.assertIn("if self.counting:", self._body("_count_now"))

    def test_a_failed_count_releases_the_latch(self):
        """Unlatched in the branch that runs for every answer, not only the
        successful one -- otherwise one bad count stops the live count for the
        rest of the session."""
        body = self._body("_receive")
        self.assertLess(body.index("self.counting = False"),
                        body.index('problem = answer.get("error")'))

    def test_the_live_count_does_not_talk_over_the_status_bar(self):
        """It writes the same label as the Count button and says nothing else,
        or it would overwrite whatever the user was being told, once per
        keystroke."""
        self.assertIn('if answer.get("tag") != "FEAT-8":', self._body("_receive"))

    def test_the_timer_is_stopped_when_the_window_closes(self):
        """A DispatcherTimer left running holds a reference to a dead window
        and keeps firing into it."""
        self.assertIn("self.count_timer.stop()", self._body("_on_closed"))


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
            returned = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
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
