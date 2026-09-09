#! python3
# -*- coding: utf-8 -*-
"""AnonGee · Filter View Manager — build a rule, save it, press it.

A rule is Category > Family > Type > Parameter conditions. Pressing one
**temporarily isolates** what it matches in the **active view**. Nothing is
written to the project: no ParameterFilterElement, nothing in the Filters list,
no trace for a colleague opening the model.

Saved rules live in %APPDATA%, so they follow you into the next project, and
beside the model, so a job can carry its own. Every reference in a saved rule is
a NAME, never an ElementId — ids do not survive a session, let alone another
project, and that portability is the whole feature.

MODELESS (§12.8), and it is not a ShowDialog->Show swap. The three rules that
make it work, all of which fail at instantiation or on the *second* press:

  * ``FilterViewHandler`` carries ``__namespace__`` and has **no __init__**;
  * it is defined **exactly once per Revit session**, cached in a module kept
    in ``sys.modules``, because the persistent CPython engine re-executes this
    script on every press and pythonnet would re-emit the same CLR type;
  * the same module holds the live window, so pressing the button again
    activates the open window instead of stacking a second one.

Every request crosses to Revit's thread as **plain data** — a rule travels as
the dict it saves as, and comes back as ints and strings. A Revit object cannot
cross to the WPF thread (§12.8.7.2).

The thinking is not in here. It is in ``anongee_filterrules``, which runs
without Revit and has 155 tests on it; this file is the window and the wiring.

No pyRevit modules — Autodesk.* and System.* only (§12.8.4).
"""

import os
import sys
import types

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System")
clr.AddReference("System.Xaml")

from Autodesk.Revit.UI import ExternalEvent                    # noqa: E402
from Autodesk.Revit.UI import IExternalEventHandler            # noqa: E402
from Autodesk.Revit.UI import TaskDialog                       # noqa: E402
from Autodesk.Revit.UI import TaskDialogCommonButtons          # noqa: E402
from Autodesk.Revit.UI import TaskDialogResult                 # noqa: E402

from System import Action                                      # noqa: E402
from System.Collections import ArrayList                       # noqa: E402
from System.IO import FileAccess, FileMode, FileStream         # noqa: E402
from System.Windows.Interop import WindowInteropHelper         # noqa: E402
from System.Windows.Markup import XamlReader                   # noqa: E402

__title__ = "Filter\nView Manager"
__author__ = "AnonGee"

#: The version is declared once, in ``anongee_filterrules/__init__.py``, and
#: shown in the window header. ``bundle.yaml`` and ``CHANGELOG.md`` are held to
#: it by ``tests/test_filterview_ui.py``, so the badge cannot lie about which
#: build is running -- quote it when reporting anything.

HERE = os.path.dirname(os.path.abspath(__file__))


def _lib_on_path():
    """Make ``anongee_filterrules`` importable whatever pyRevit did.

    pyRevit puts ``<extension>/lib`` on ``sys.path`` — that is how
    ``path_resolver`` is imported everywhere else here — so this is normally a
    no-op. Spelled out anyway, because a window that cannot say *why* it failed
    to import is a window that just does not open.
    """
    lib = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "lib"))
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    return lib


_LIB = _lib_on_path()

from anongee_filterrules import VERSION                        # noqa: E402
from anongee_filterrules import names, rules, store, values    # noqa: E402

#: What the combos show for "I do not care about this level".
ANY_FAMILY = "(any family)"
ANY_TYPE = "(any type)"
NO_UNIT = "(no unit)"

#: Marks a parameter Revit would refuse in a native view filter. It still makes
#: a perfectly good rule here, because pressing a rule isolates (CRIT-2).
NOT_FILTERABLE = "   (no view filter)"


# ═══════════════════════════════════════════════════════════════════════════
# Rows — §12.7.G: plain ``__slots__``, no INotifyPropertyChanged
# ═══════════════════════════════════════════════════════════════════════════
# DataTemplate bindings to Python properties on an INPC class fail silently in
# this engine — blank cells, no error. Every slot named below appears verbatim
# in a binding path in ui.xaml, and nothing else is bound.

class RuleRow(object):
    __slots__ = ("Name", "Badge", "Summary", "RuleId")

    def __init__(self, rule):
        self.Name = rule.name or "(unnamed)"
        self.Badge = (rule.source or "machine").upper()
        self.Summary = rule.summary()
        self.RuleId = rule.id


class CategoryRow(object):
    __slots__ = ("Name",)

    def __init__(self, name):
        self.Name = name


class ConditionRow(object):
    __slots__ = ("Text",)

    def __init__(self, text):
        self.Text = text


# ═══════════════════════════════════════════════════════════════════════════
# Session state — §12.8.7.3
# ═══════════════════════════════════════════════════════════════════════════
# The persistent engine re-runs this module on every press, but sys.modules and
# the CLR AppDomain outlive it. The handler class must be emitted once, and the
# live window must survive run() returning.

_STATE_MODULE = "AnonGee_FilterViewManagerState"
_state = sys.modules.get(_STATE_MODULE)
if _state is None:
    _state = types.ModuleType(_STATE_MODULE)
    _state.handler_cls = None
    _state.window_ref = None
    sys.modules[_STATE_MODULE] = _state


if _state.handler_cls is None:
    # Defined ONLY on the first execution per Revit session. Re-running the
    # class statement would raise "Duplicate type name within an assembly" on
    # the second press.
    class FilterViewHandler(IExternalEventHandler):
        """Everything that touches Revit, on Revit's own thread.

        The WPF thread appends a request and raises the event; ``Execute``
        drains the queue in order, so rapid typing cannot swallow a button
        press. Results go back through the window's Dispatcher.
        """

        # REQUIRED by pythonnet to emit a real derived CLR type (§12.8.7.1).
        __namespace__ = "AnonGee"

        # NO __init__ — defining one trips pythonnet's interface __new__ and
        # raises "interface takes exactly one argument". State is rebound in
        # run() straight after construction.
        app = None
        queue = None

        def Execute(self, uiapp):
            app = self.app
            if app is None:
                return
            while self.queue:
                request = self.queue.pop(0)
                try:
                    answer = app.serve(uiapp, request)
                except Exception as error:                    # noqa: BLE001
                    answer = {"kind": request.get("kind"),
                              "error": "{0}".format(error)}
                app.post(answer)

        def GetName(self):
            return "AnonGee_FilterViewManager"

    _state.handler_cls = FilterViewHandler
else:
    FilterViewHandler = _state.handler_cls


# ═══════════════════════════════════════════════════════════════════════════
# The window
# ═══════════════════════════════════════════════════════════════════════════

class FilterViewApp(object):
    """The WPF half. Knows nothing about Revit beyond the request names."""

    def __init__(self):
        self.window = self._load_xaml()
        self._bind_controls()

        self.handler = FilterViewHandler()
        self.handler.app = self
        self.handler.queue = []
        self.event = ExternalEvent.Create(self.handler)

        # Everything the model told us, as plain data.
        self.categories = []            # [name]
        self.parameters = []            # [(name, filterable)]
        self.picked = set()             # category names, the source of truth
        self.conditions = []            # [Condition]
        self.rule_set = rules.RuleSet()
        self.editing_id = None          # the saved rule being edited, if any
        self.machine_path = None
        self.project_path = None
        self.busy = False
        self.pending_family = None      # restored once the cascade comes back
        self.pending_type = None

        # Set while a list is being rebuilt. A SelectionChanged handler is NOT
        # detached with ``-=`` to do this: ``self._on_x`` builds a new bound
        # method on every attribute access, so pythonnet can wrap a different
        # delegate and remove nothing at all. A flag cannot be got wrong.
        self.rebuilding = False

        self._fill_static_combos()
        self._wire()
        self.window.Closed += self._on_closed

    # -- construction ------------------------------------------------------

    def _load_xaml(self):
        path = os.path.join(HERE, "ui.xaml")
        stream = FileStream(path, FileMode.Open, FileAccess.Read)
        try:
            return XamlReader.Load(stream)
        finally:
            stream.Close()

    def _bind_controls(self):
        """Every name in ui.xaml, looked up once.

        ``tests/test_filterview_ui.py`` holds this tuple to the XAML both ways:
        a lookup with no control and a control with no lookup are both defects.
        """
        find = self.window.FindName
        for name in (
                "VersionText", "HintText",
                "RuleList", "RuleCountText", "NewRuleBtn", "DuplicateRuleBtn",
                "MoveUpBtn", "MoveDownBtn", "DeleteRuleBtn",
                "RefreshBtn", "RuleNameBox", "CategoryPickedText",
                "CategorySearch", "CategoryList", "FamilyCombo", "TypeCombo",
                "MatchAllRadio", "MatchAnyRadio",
                "ParameterCombo", "OperatorCombo", "ValueBox", "UnitCombo",
                "AddConditionBtn", "ConditionList", "RemoveConditionBtn",
                "ProblemText", "SaveRuleBtn",
                "StatusBadge", "StatusBadgeText", "StatusBar", "LiveCount",
                "CountBtn", "SelectBtn", "ClearBtn", "ApplyBtn", "CloseBtn"):
            setattr(self, name, find(name))

    def _fill_static_combos(self):
        self.VersionText.Text = VERSION
        for key in values.OPERATORS:
            self.OperatorCombo.Items.Add(values.operator_label(key))
        self.OperatorCombo.SelectedIndex = 0
        self.UnitCombo.Items.Add(NO_UNIT)
        for unit in values.known_units():
            self.UnitCombo.Items.Add(unit)
        self.UnitCombo.SelectedIndex = 0

    def _wire(self):
        self.CloseBtn.Click += self._on_close
        self.RefreshBtn.Click += self._on_refresh
        self.NewRuleBtn.Click += self._on_new
        self.DuplicateRuleBtn.Click += self._on_duplicate
        self.DeleteRuleBtn.Click += self._on_delete
        self.MoveUpBtn.Click += self._on_move_up
        self.MoveDownBtn.Click += self._on_move_down
        self.SaveRuleBtn.Click += self._on_save
        self.AddConditionBtn.Click += self._on_add_condition
        self.RemoveConditionBtn.Click += self._on_remove_condition
        self.CountBtn.Click += self._on_count
        self.ApplyBtn.Click += self._on_apply
        self.ClearBtn.Click += self._on_clear
        self.SelectBtn.Click += self._on_select
        self.RuleList.SelectionChanged += self._on_rule_selected
        self.CategoryList.SelectionChanged += self._on_category_selected
        self.CategorySearch.TextChanged += self._on_category_search
        # §12.7.P: dependent fields load on DropDownClosed, never on
        # SelectionChanged -- which fires for every item arrowed past.
        self.FamilyCombo.DropDownClosed += self._on_family_chosen
        self.MatchAllRadio.Checked += self._on_match_changed
        self.MatchAnyRadio.Checked += self._on_match_changed

    # -- the thread bridge -------------------------------------------------

    def ask(self, **request):
        """Queue a request for Revit's thread and raise the event."""
        self.handler.queue.append(request)
        self.event.Raise()

    def post(self, answer):
        """Called on REVIT's thread; hop back to WPF before touching a control."""
        self.window.Dispatcher.Invoke(Action(lambda: self._receive(answer)))

    def serve(self, uiapp, request):
        """Runs on Revit's thread. Returns plain data, never a Revit object."""
        from anongee_filterrules import revit_apply, revit_query

        uidoc = uiapp.ActiveUIDocument
        if uidoc is None or uidoc.Document is None:
            return {"kind": request.get("kind"),
                    "error": "no project is open"}
        doc = uidoc.Document
        view = doc.ActiveView
        kind = request.get("kind")

        if kind == "model":
            allowed, why = revit_apply.can_isolate(view)
            project = store.project_path(doc.PathName)
            return {"kind": kind,
                    "categories": [name for name, _ in revit_query.categories(doc)],
                    "view": revit_apply.view_label(view),
                    "can_isolate": allowed,
                    "why": why,
                    "machine": store.machine_path(),
                    "project": project}

        if kind == "cascade":
            picked = request["categories"]
            return {"kind": kind,
                    "families": revit_query.families(doc, picked),
                    "types": revit_query.types(doc, picked, request.get("family")),
                    "parameters": revit_query.parameters(doc, picked)}

        if kind == "types":
            return {"kind": kind,
                    "types": revit_query.types(doc, request["categories"],
                                               request.get("family"))}

        if kind == "clear":
            ok, message = revit_apply.clear(doc, view)
            return {"kind": kind, "ok": ok, "message": message}

        rule = rules.Rule.from_dict(request["rule"])
        missing = revit_query.resolve(doc, rule)
        if missing:
            return {"kind": kind, "error": "; ".join(missing)}

        if kind == "count":
            return {"kind": kind, "count": revit_query.count(doc, view, rule)}

        if kind == "apply":
            matched = revit_query.matching_ids(doc, view, rule)
            count, message = revit_apply.isolate(doc, view, matched)
            return {"kind": kind, "count": count, "message": message}

        if kind == "select":
            matched = revit_query.matching_ids(doc, view, rule)
            from anongee_filterrules import compat
            uidoc.Selection.SetElementIds(compat.id_list(matched))
            return {"kind": kind, "count": len(matched)}

        return {"kind": kind, "error": "unknown request"}

    def _receive(self, answer):
        """Runs on the WPF thread. The only place controls are written."""
        self.busy = False
        kind = answer.get("kind")
        problem = answer.get("error")
        if problem:
            self._status(problem, "error")
            return

        if kind == "model":
            self.categories = answer["categories"]
            self.machine_path = answer["machine"]
            self.project_path = answer["project"]
            self._rebuild_categories()
            self._load_saved_rules()
            note = answer["view"]
            if not answer["can_isolate"]:
                note = "{0} — {1}".format(note, answer["why"])
            self._status("{0} categories. Active view: {1}".format(
                len(self.categories), note),
                "info" if answer["can_isolate"] else "error")
        elif kind == "cascade":
            self._fill_combo(self.FamilyCombo, ANY_FAMILY, answer["families"])
            self._fill_combo(self.TypeCombo, ANY_TYPE, answer["types"])
            self.parameters = answer["parameters"]
            self._fill_parameters()
            if self.pending_family:
                self._select_text(self.FamilyCombo, self.pending_family)
                self.pending_family = None
                self.ask(kind="types", categories=sorted(self.picked),
                         family=self._combo_value(self.FamilyCombo, ANY_FAMILY))
            elif self.pending_type:
                self._select_text(self.TypeCombo, self.pending_type)
                self.pending_type = None
            self._status("{0} famil(ies), {1} type(s), {2} parameter(s)".format(
                len(answer["families"]), len(answer["types"]),
                len(answer["parameters"])), "info")
        elif kind == "types":
            self._fill_combo(self.TypeCombo, ANY_TYPE, answer["types"])
            if self.pending_type:
                self._select_text(self.TypeCombo, self.pending_type)
                self.pending_type = None
            self._status("{0} type(s)".format(len(answer["types"])), "info")
        elif kind == "count":
            self.LiveCount.Text = "{0} matched".format(answer["count"])
            self._status("Counted in the active view. Nothing changed.", "info")
        elif kind == "apply":
            if answer["message"]:
                self._status(answer["message"], "error")
            else:
                self.LiveCount.Text = "{0} isolated".format(answer["count"])
                self._status("Isolated in the active view. Nothing was written "
                             "to the project.", "ok")
        elif kind == "select":
            self.LiveCount.Text = "{0} selected".format(answer["count"])
            self._status("Pushed to Revit's selection.", "ok")
        elif kind == "clear":
            self.LiveCount.Text = ""
            self._status(answer["message"] or "The view is back to normal.",
                         "ok" if answer["ok"] else "error")

    # -- small helpers -----------------------------------------------------

    def _status(self, message, tone="info"):
        keys = {"info": ("BrushInfoBadgeBackground", "BrushInfoBadgeText", "READY"),
                "ok": ("BrushSuccessBadgeBackground", "BrushSuccessBadgeText", "DONE"),
                "error": ("BrushErrorBadgeBackground", "BrushErrorBadgeText", "PROBLEM")}
        background, foreground, label = keys.get(tone, keys["info"])
        self.StatusBadge.Background = self.window.FindResource(background)
        self.StatusBadgeText.Foreground = self.window.FindResource(foreground)
        self.StatusBadgeText.Text = label
        self.StatusBar.Text = message

    def _fill_combo(self, combo, blank, items):
        combo.Items.Clear()
        combo.Items.Add(blank)
        for item in items:
            combo.Items.Add(item)
        combo.SelectedIndex = 0

    def _fill_parameters(self):
        self.ParameterCombo.Items.Clear()
        for name, filterable in self.parameters:
            self.ParameterCombo.Items.Add(
                name if filterable else name + NOT_FILTERABLE)
        if self.ParameterCombo.Items.Count:
            self.ParameterCombo.SelectedIndex = 0

    def _select_text(self, combo, wanted):
        """Select the item Revit calls *wanted*, matched Revit's way.

        A saved rule names a type as text; this project may spell it with a
        different case or a doubled space, and Revit calls those the same name.
        Nothing is selected when the project does not have it -- the rule is
        greyed rather than quietly rewritten to something else.
        """
        for index in range(combo.Items.Count):
            if names.same("{0}".format(combo.Items[index]), wanted):
                combo.SelectedIndex = index
                return True
        return False

    def _combo_value(self, combo, blank):
        chosen = combo.SelectedItem
        if chosen is None:
            return None
        text = "{0}".format(chosen)
        return None if text == blank else text

    def _parameter_name(self):
        chosen = self.ParameterCombo.SelectedItem
        if chosen is None:
            return ""
        return "{0}".format(chosen).replace(NOT_FILTERABLE, "").strip()

    def _operator_key(self):
        label = "{0}".format(self.OperatorCombo.SelectedItem or "")
        for key in values.OPERATORS:
            if values.operator_label(key) == label:
                return key
        return "equals"

    # -- categories --------------------------------------------------------

    def _rebuild_categories(self):
        """Redraw the list for the current search, keeping what was ticked.

        ``self.picked`` is the source of truth, not the ListBox: rebuilding
        ItemsSource clears the selection, and the ticks must survive a search.
        """
        needle = names.key(self.CategorySearch.Text)
        rows = ArrayList()
        for name in self.categories:
            if not needle or needle in names.key(name):
                rows.Add(CategoryRow(name))
        self.rebuilding = True
        try:
            self.CategoryList.ItemsSource = rows
            for row in self.CategoryList.Items:
                if row.Name in self.picked:
                    self.CategoryList.SelectedItems.Add(row)
        finally:
            self.rebuilding = False
        self._show_picked()

    def _show_picked(self):
        count = len(self.picked)
        self.CategoryPickedText.Text = (
            "none picked" if not count else
            "{0} picked: {1}".format(count, ", ".join(sorted(self.picked)[:3]) +
                                     ("..." if count > 3 else "")))

    def _on_category_search(self, sender, args):
        self._rebuild_categories()

    def _on_category_selected(self, sender, args):
        """Mirror the ListBox's own selection into Python (§12.7.Q).

        The tick is drawn from the native ``ListBoxItem.IsSelected``; a Python
        bool does not coerce in this engine. Only the rows currently shown can
        change, so a search does not silently unpick what is filtered out.
        """
        if self.rebuilding:
            return
        shown = set(row.Name for row in self.CategoryList.Items)
        chosen = set(row.Name for row in self.CategoryList.SelectedItems)
        self.picked = (self.picked - shown) | chosen
        self._show_picked()
        self._refresh_cascade()

    def _refresh_cascade(self):
        if not self.picked:
            self._fill_combo(self.FamilyCombo, ANY_FAMILY, [])
            self._fill_combo(self.TypeCombo, ANY_TYPE, [])
            self.parameters = []
            self._fill_parameters()
            self._validate()
            return
        self._status("Reading families, types and parameters...", "info")
        self.ask(kind="cascade", categories=sorted(self.picked), family=None)

    def _on_family_chosen(self, sender, args):
        if not self.picked:
            return
        self.ask(kind="types", categories=sorted(self.picked),
                 family=self._combo_value(self.FamilyCombo, ANY_FAMILY))

    def _on_match_changed(self, sender, args):
        self._validate()

    # -- conditions --------------------------------------------------------

    def _on_add_condition(self, sender, args):
        unit = self._combo_value(self.UnitCombo, NO_UNIT) or ""
        condition = rules.Condition(
            parameter=self._parameter_name(),
            operator=self._operator_key(),
            value=self.ValueBox.Text,
            unit=unit,
            filterable=self._is_filterable(self._parameter_name()))
        problems = condition.problems()
        if problems:
            self._status(problems[0], "error")
            return
        self.conditions.append(condition)
        self.ValueBox.Text = ""
        self._rebuild_conditions()
        self._validate()

    def _is_filterable(self, parameter_name):
        for name, filterable in self.parameters:
            if names.same(name, parameter_name):
                return filterable
        return True

    def _on_remove_condition(self, sender, args):
        index = self.ConditionList.SelectedIndex
        if index < 0:
            self._status("Select a condition to remove.", "error")
            return
        del self.conditions[index]
        self._rebuild_conditions()
        self._validate()

    def _rebuild_conditions(self):
        rows = ArrayList()
        for condition in self.conditions:
            rows.Add(ConditionRow("{0} {1} {2}{3}".format(
                condition.parameter,
                values.operator_label(condition.operator),
                "" if condition.operator in values.VALUELESS_OPERATORS
                else condition.value,
                (" " + condition.unit) if condition.unit else "").strip()))
        self.ConditionList.ItemsSource = rows

    # -- the rule being built ---------------------------------------------

    def current_rule(self):
        return rules.Rule(
            id=self.editing_id,
            name=self.RuleNameBox.Text,
            categories=sorted(self.picked),
            family=self._combo_value(self.FamilyCombo, ANY_FAMILY),
            type_name=self._combo_value(self.TypeCombo, ANY_TYPE),
            match=rules.MATCH_ALL if self.MatchAllRadio.IsChecked
            else rules.MATCH_ANY,
            conditions=list(self.conditions))

    def _validate(self):
        """Show the first problem, or the rule read back as a sentence."""
        rule = self.current_rule()
        problems = rule.problems()
        self.ProblemText.Text = problems[0] if problems else rule.summary()
        return problems

    # -- saved rules -------------------------------------------------------

    def _load_saved_rules(self):
        self.rule_set = store.load_all(self.machine_path, self.project_path)
        self._rebuild_rules()

    def _rebuild_rules(self):
        rows = ArrayList()
        for rule in self.rule_set:
            rows.Add(RuleRow(rule))
        self.rebuilding = True
        try:
            self.RuleList.ItemsSource = rows
        finally:
            self.rebuilding = False
        self.RuleCountText.Text = "{0}".format(len(self.rule_set))

    def _selected_rule(self):
        row = self.RuleList.SelectedItem
        return self.rule_set.find(row.RuleId) if row is not None else None

    def _on_rule_selected(self, sender, args):
        if self.rebuilding:
            return
        rule = self._selected_rule()
        if rule is None:
            return
        self.editing_id = rule.id
        self.RuleNameBox.Text = rule.name
        self.picked = set(rule.categories)
        self.conditions = list(rule.conditions)
        self.MatchAllRadio.IsChecked = rule.match == rules.MATCH_ALL
        self.MatchAnyRadio.IsChecked = rule.match == rules.MATCH_ANY
        self._rebuild_categories()
        self._rebuild_conditions()
        # The cascade is fetched on Revit's thread, so the family and type
        # cannot be selected until it comes back. Held here and applied in
        # _receive, which is the only place that knows they have arrived.
        self.pending_family = rule.family
        self.pending_type = rule.type_name
        self._validate()
        self._status("Loaded {0!r}. Press Apply to isolate what it "
                     "matches.".format(rule.name), "info")

    def _on_new(self, sender, args):
        self.editing_id = None
        self.RuleNameBox.Text = ""
        self.picked = set()
        self.conditions = []
        self.MatchAllRadio.IsChecked = True
        self.RuleList.SelectedIndex = -1
        self._rebuild_categories()
        self._rebuild_conditions()
        self._validate()
        self._status("New rule. Tick the categories it should look in.", "info")

    def _on_save(self, sender, args):
        problems = self._validate()
        if problems:
            self._status(problems[0], "error")
            return
        rule = self.current_rule()
        existing = self.rule_set.find(rule.id) if rule.id else None
        if existing is None:
            self.rule_set.add(rule)
        else:
            self.rule_set.remove(existing.id)
            self.rule_set.add(rule)
            self.rule_set.move(rule.id, existing.order)
        self.editing_id = rule.id
        self._write()

    def _write(self):
        """Machine rules only. A project rule is read but not yet written.

        Writing the project store is FEAT-14 and needs its own decision about
        what happens when the same name is in both; until then a rule saved
        here goes where it will follow the user, which is the promise the tool
        actually made.
        """
        keep = rules.RuleSet([r for r in self.rule_set
                              if r.source != store.PROJECT])
        if store.save(keep, self.machine_path):
            self._rebuild_rules()
            self._status("Saved. It will be here next time, and in your next "
                         "project.", "ok")
        else:
            self._status("Could not save: {0}".format(store.last_error()),
                         "error")

    def _on_duplicate(self, sender, args):
        rule = self._selected_rule()
        if rule is None:
            self._status("Select a rule to duplicate.", "error")
            return
        copy = self.rule_set.duplicate(rule.id)
        copy.source = store.MACHINE
        self._write()

    def _on_delete(self, sender, args):
        rule = self._selected_rule()
        if rule is None:
            self._status("Select a rule to delete.", "error")
            return
        dialog = TaskDialog("Filter View Manager")
        dialog.MainInstruction = "Delete {0!r}?".format(rule.name)
        dialog.MainContent = ("Only this rule is removed. Nothing in the model "
                             "changes.")
        dialog.CommonButtons = (TaskDialogCommonButtons.Yes |
                                TaskDialogCommonButtons.No)
        if dialog.Show() != TaskDialogResult.Yes:
            return
        self.rule_set.remove(rule.id)
        if self.editing_id == rule.id:
            self.editing_id = None
        self._write()

    def _on_move_up(self, sender, args):
        self._move(-1)

    def _on_move_down(self, sender, args):
        self._move(1)

    def _move(self, step):
        rule = self._selected_rule()
        if rule is None:
            self._status("Select a rule to move.", "error")
            return
        self.rule_set.move(rule.id, rule.order + step)
        self._write()

    # -- the four actions --------------------------------------------------

    def _guard(self):
        problems = self._validate()
        if problems:
            self._status(problems[0], "error")
            return None
        return self.current_rule().to_dict()

    def _on_count(self, sender, args):
        payload = self._guard()
        if payload:
            self._status("Counting...", "info")
            self.ask(kind="count", rule=payload)

    def _on_apply(self, sender, args):
        payload = self._guard()
        if payload:
            self._status("Isolating...", "info")
            self.ask(kind="apply", rule=payload)

    def _on_select(self, sender, args):
        payload = self._guard()
        if payload:
            self.ask(kind="select", rule=payload)

    def _on_clear(self, sender, args):
        self.ask(kind="clear")

    def _on_refresh(self, sender, args):
        self._status("Re-reading the model...", "info")
        self.ask(kind="model")

    # -- lifecycle ---------------------------------------------------------

    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        _state.window_ref = None

    def show(self, host):
        helper = WindowInteropHelper(self.window)
        helper.Owner = host
        self.window.Show()
        self._status("Reading the model...", "info")
        self.ask(kind="model")


def run():
    living = _state.window_ref
    if living is not None:
        try:
            living.window.Activate()
            return
        except Exception:                       # the window is gone; start again
            _state.window_ref = None

    uiapp = __revit__                            # noqa: F821 — pyRevit injects it
    if uiapp.ActiveUIDocument is None:
        TaskDialog.Show("Filter View Manager",
                        "Open a project first — a rule is built from what the "
                        "model has in it.")
        return
    app = FilterViewApp()
    _state.window_ref = app
    app.show(uiapp.MainWindowHandle)


# Module-level guard (§12.9.4): a logic error reports cleanly instead of
# leaving the persistent engine in a half-state.
try:
    run()
except Exception as error:                      # noqa: BLE001 — report, never raise
    import traceback
    detail = traceback.format_exc()
    print(detail)
    dialog = TaskDialog("Filter View Manager")
    dialog.MainInstruction = "The window did not open"
    dialog.MainContent = "{0}".format(error)
    dialog.ExpandedContent = detail
    dialog.Show()
