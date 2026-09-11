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

from Autodesk.Revit.UI import DockablePaneId                   # noqa: E402
from Autodesk.Revit.UI import ExternalEvent                    # noqa: E402
from Autodesk.Revit.UI import IExternalEventHandler            # noqa: E402
from Autodesk.Revit.UI import TaskDialog                       # noqa: E402
from Autodesk.Revit.UI import TaskDialogCommonButtons          # noqa: E402
from Autodesk.Revit.UI import TaskDialogResult                 # noqa: E402

from System import Action, Guid                                # noqa: E402
from System.Collections import ArrayList                       # noqa: E402
from System.IO import FileAccess, FileMode, FileStream         # noqa: E402
from System import TimeSpan                                    # noqa: E402
from System.Windows.Interop import WindowInteropHelper         # noqa: E402
from System.Windows.Threading import DispatcherTimer           # noqa: E402
from System.Windows.Markup import XamlReader                   # noqa: E402

__title__ = "Filter\nView Manager"
__author__ = "AnonGee"

# The version is declared once, in anongee_filterrules/__init__.py, and shown in
# the window header. bundle.yaml and CHANGELOG.md are held to it by
# tests/test_filterview_ui.py, so the badge cannot lie about which build is
# running -- quote it when reporting anything.

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
from anongee_filterrules import diagnostics, filters           # noqa: E402
from anongee_filterrules import names, rules, store, values    # noqa: E402

# Safe to import from CPython 3: this module holds the pane's identity and its
# startup record, and nothing Revit-shaped. ``anongee_filterpane.provider`` is
# the half that imports Autodesk, and it is only ever loaded by startup.py on
# IronPython. The two halves are split precisely so this line can exist.
import anongee_filterpane                                      # noqa: E402

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


class Debounce(object):
    """Fire *callback* once, after *delay_ms* of silence.

    A ``DispatcherTimer`` restarted on every change, which is the WPF way and
    the one the reference implementation in ``OneFilterParameter`` uses.
    Inlined rather than imported from ``anongee_toolkit.ui.dialogs``, which has
    the same class: that package is CPython-only and reachable from here, but
    a failed import takes the whole window with it, and the precedent for this
    exact control is to carry its own.

    ``reset`` is deliberately Stop-then-Start rather than Start alone -- a
    ``DispatcherTimer`` already running does not restart its interval when
    Start is called again, so without the Stop a user typing steadily would
    never reach a quiet period and the count would never arrive.
    """

    __slots__ = ("_timer", "_callback")

    def __init__(self, callback, delay_ms=350):
        self._callback = callback
        self._timer = DispatcherTimer()
        self._timer.Interval = TimeSpan.FromMilliseconds(delay_ms)
        self._timer.Tick += self._on_tick

    def _on_tick(self, sender, args):
        self._timer.Stop()
        try:
            self._callback()
        except Exception as error:                          # noqa: BLE001
            import traceback
            diagnostics.failure("FEAT-8", "the live count", error,
                                traceback.format_exc())

    def reset(self):
        self._timer.Stop()
        self._timer.Start()

    def stop(self):
        self._timer.Stop()


class ViewRow(object):
    """A view in the picker. S12.7.G: plain slots, no INotifyPropertyChanged."""

    __slots__ = ("Name", "Note", "ViewId", "Usable")

    def __init__(self, view_id, name, usable, why):
        self.Name = name
        self.Note = "" if usable else "cannot be isolated -- {0}".format(why)
        self.ViewId = view_id
        self.Usable = usable


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
                    # Revit's thread. Nothing above this catches, so an
                    # escape here is a Revit crash dialog with no stack --
                    # or silence. The tag travels with the request so the
                    # window can say WHICH feature asked for this.
                    import traceback
                    answer = {
                        "kind": request.get("kind"),
                        "error": diagnostics.failure(
                            request.get("tag", "UI"),
                            request.get("what", request.get("kind", "a request")),
                            error, traceback.format_exc())}
                app.post(answer)

        def GetName(self):
            return "AnonGee_FilterViewManager"

    _state.handler_cls = FilterViewHandler
else:
    FilterViewHandler = _state.handler_cls


# ═══════════════════════════════════════════════════════════════════════════
# The window
# ═══════════════════════════════════════════════════════════════════════════

class ViewPicker(object):
    """FEAT-11 -- the modal that answers "which views?".

    Modal on purpose. The main window stays modeless so the model stays
    interactive; this is one question, asked and answered. It touches **no**
    Revit API at all: it is handed plain rows and hands back plain ids, so it
    can be opened from the WPF thread without an external event (S12.8.7.2).

    Views that cannot be isolated are **listed with the reason** rather than
    hidden. A modeller hunting a missing schedule with nothing to say it was
    excluded on purpose is the failure; a greyed row that says why is not.
    """

    NAMES = ("ViewList", "ViewSearch", "ViewApplyBtn", "ViewCancelBtn",
             "ViewAllBtn", "ViewNoneBtn", "ViewStatus", "ViewCount",
             "ViewsHint")

    def __init__(self, owner, listed, heading):
        self.listed = list(listed or [])
        self.chosen = []
        self.rebuilding = False
        self._handlers = []
        path = os.path.join(HERE, "views.xaml")
        stream = FileStream(path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()
        for name in self.NAMES:
            setattr(self, name, self.window.FindName(name))
        try:
            self.window.Owner = owner
        except Exception:
            # A picker that will not parent is still a usable picker.
            pass
        self.ViewsHint.Text = "{0}. {1}".format(
            heading, self.ViewsHint.Text)
        self._wire()
        self._rebuild()

    def _wire(self):
        self.ViewSearch.TextChanged += self._guard(self._on_search)
        self.ViewApplyBtn.Click += self._guard(self._on_apply)
        self.ViewCancelBtn.Click += self._guard(self._on_cancel)
        self.ViewAllBtn.Click += self._guard(self._on_all)
        self.ViewNoneBtn.Click += self._guard(self._on_none)
        self.ViewList.SelectionChanged += self._guard(self._on_changed)

    def _guard(self, handler):
        """Guarded, and kept alive. Same reasoning as the window's guard."""
        def wrapped(sender, args):
            try:
                handler(sender, args)
            except Exception as error:                      # noqa: BLE001
                import traceback
                self.ViewStatus.Text = diagnostics.failure(
                    "FEAT-11", "the view picker", error, traceback.format_exc())
        self._handlers.append(wrapped)
        return wrapped

    # -- the list ---------------------------------------------------------

    def _rebuild(self):
        """Redraw for the current search, keeping what is ticked.

        ``self.chosen`` is the source of truth, not the ListBox -- rebuilding
        ItemsSource drops the selection, and a search must not silently untick
        the views it filters out. The same rule as the category list, and for
        the same reason.
        """
        needle = names.key(self.ViewSearch.Text)
        rows = ArrayList()
        for view_id, name, usable, why in self.listed:
            if needle and needle not in names.key(name):
                continue
            rows.Add(ViewRow(view_id, name, usable, why))
        self.rebuilding = True
        try:
            self.ViewList.ItemsSource = rows
            for row in self.ViewList.Items:
                if row.ViewId in self.chosen:
                    self.ViewList.SelectedItems.Add(row)
        finally:
            self.rebuilding = False
        self._say()

    def _say(self):
        usable = sum(1 for _i, _n, ok, _w in self.listed if ok)
        self.ViewCount.Text = "{0} ticked of {1} view(s), {2} usable".format(
            len(self.chosen), len(self.listed), usable)

    def _on_search(self, sender, args):
        self._rebuild()

    def _on_changed(self, sender, args):
        if self.rebuilding:
            return
        shown = set(row.ViewId for row in self.ViewList.Items)
        ticked = set(row.ViewId for row in self.ViewList.SelectedItems)
        self.chosen = list((set(self.chosen) - shown) | ticked)
        self._say()

    def _on_all(self, sender, args):
        """Every view in the list that can actually be isolated.

        The ones that cannot are left alone rather than ticked and skipped
        later -- ticking something that will be refused is a promise the
        picker cannot keep.
        """
        shown = set(row.ViewId for row in self.ViewList.Items if row.Usable)
        self.chosen = list(set(self.chosen) | shown)
        self._rebuild()

    def _on_none(self, sender, args):
        shown = set(row.ViewId for row in self.ViewList.Items)
        self.chosen = list(set(self.chosen) - shown)
        self._rebuild()

    # -- the answer -------------------------------------------------------

    def _on_apply(self, sender, args):
        usable = set(view_id for view_id, _n, ok, _w in self.listed if ok)
        refused = [view_id for view_id in self.chosen if view_id not in usable]
        keep = [view_id for view_id in self.chosen if view_id in usable]
        if not keep:
            self.ViewStatus.Text = diagnostics.headline(
                "FEAT-11", "Tick at least one view that can be isolated.")
            return
        if refused:
            # Reported rather than silently dropped: the count on the next
            # screen would otherwise be lower than the tick count with nothing
            # to explain the difference.
            diagnostics.record("FEAT-11", "{0} ticked view(s) cannot be "
                               "isolated and were dropped".format(len(refused)))
        self.chosen = keep
        self.window.DialogResult = True
        self.window.Close()

    def _on_cancel(self, sender, args):
        self.chosen = []
        self.window.DialogResult = False
        self.window.Close()

    def ask(self):
        """Show it. Returns the ticked view ids, or ``[]`` for a cancel."""
        try:
            self.window.ShowDialog()
        except Exception as error:                          # noqa: BLE001
            import traceback
            diagnostics.failure("FEAT-11", "opening the view picker", error,
                                traceback.format_exc())
            return []
        return list(self.chosen)


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

        #: Rule ids to re-tick after the next rebuild. A move rewrites the
        #: list, which drops the selection; without this the block you just
        #: moved is deselected and the next press does nothing.
        self._keep_selected = []

        #: FEAT-8. Restarted by every change to the rule, so a count is asked
        #: for once the user stops rather than once per keystroke.
        self.count_timer = Debounce(self._count_now, 350)
        #: Set while a count is in flight, so a slow model cannot stack them.
        self.counting = False
        #: FEAT-11. The rule the view picker is being opened for, held between
        #: asking Revit for the views and the picker coming back.
        self.pending_views_rule = None
        #: FEAT-19. The office's rules file, if this workstation has been
        #: pointed at one. Read once at startup; changed by the Choose button.
        self.shared_path = store.shared_path()

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
                "MoveTopBtn", "MoveBottomBtn",
                "StoreMachineRadio", "StoreProjectRadio", "StoreHint",
                "DiagnosticsBtn", "ImportBtn", "ExportBtn", "ViewsBtn",
                "StoreSharedRadio", "SharedPickBtn", "FilterBtn",
                "MoveUpBtn", "MoveDownBtn", "DeleteRuleBtn",
                "RefreshBtn", "PanelBtn", "RuleNameBox", "CategoryPickedText",
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

    #: Which feature owns a control's failures, and what a person would call
    #: the thing they just pressed. One table rather than a tag repeated down
    #: thirty subscription lines, so a new control cannot be wired without
    #: someone deciding who owns it -- a test fails on a control that is
    #: subscribed and not listed here.
    OWNERS = {
        "CloseBtn": ("UI", "Close"),
        "RefreshBtn": ("UI", "Re-read model"),
        "PanelBtn": ("PANEL", "Show the panel"),
        "DiagnosticsBtn": ("UI", "Diagnostics"),
        "NewRuleBtn": ("UI", "New rule"),
        "DuplicateRuleBtn": ("UI", "Duplicate"),
        "DeleteRuleBtn": ("UI", "Delete rule"),
        "MoveUpBtn": ("UI", "Move up"),
        "MoveDownBtn": ("UI", "Move down"),
        "MoveTopBtn": ("UI", "Move to top"),
        "MoveBottomBtn": ("UI", "Move to bottom"),
        "SaveRuleBtn": ("STORE", "Save rule"),
        "ImportBtn": ("FEAT-12", "Import rules"),
        "ExportBtn": ("FEAT-12", "Export rules"),
        "AddConditionBtn": ("UI", "Add condition"),
        "RemoveConditionBtn": ("UI", "Remove condition"),
        "ConditionList": ("UI", "Remove condition"),
        "CountBtn": ("UI", "Count"),
        "ApplyBtn": ("UI", "Apply"),
        "ViewsBtn": ("FEAT-11", "Apply to views"),
        "FilterBtn": ("FEAT-13", "Make a view filter"),
        "ClearBtn": ("UI", "Clear"),
        "SelectBtn": ("UI", "Select"),
        "RuleList": ("UI", "Loading a rule"),
        "CategoryList": ("UI", "Picking a category"),
        "CategorySearch": ("UI", "Category search"),
        "FamilyCombo": ("UI", "Choosing a family"),
        "MatchAllRadio": ("UI", "Match mode"),
        "MatchAnyRadio": ("UI", "Match mode"),
        "StoreMachineRadio": ("FEAT-14", "Store choice"),
        "StoreProjectRadio": ("FEAT-14", "Store choice"),
        "StoreSharedRadio": ("FEAT-19", "Store choice"),
        "SharedPickBtn": ("FEAT-19", "Choosing the shared file"),
    }

    def _wire(self):
        """Subscribe every handler THROUGH a guard, so nothing fails quietly.

        A Python exception raised inside a WPF event handler comes back to no
        caller -- it goes to the dispatcher's unhandled path, which is at best
        a Revit crash dialog with no stack and at worst nothing at all. Every
        bug found in this tool so far was found by pressing a button and
        seeing the WRONG THING rather than an error.

        The subscriptions are written out rather than looped over a table.
        A .NET event needs ``target.Event += handler`` -- through ``getattr``
        the ``+=`` rebinds a local and subscribes nothing, silently, which is
        precisely the failure this method exists to prevent.
        """
        self._handlers = []
        self.CloseBtn.Click += self._guard("CloseBtn", self._on_close)
        self.RefreshBtn.Click += self._guard("RefreshBtn", self._on_refresh)
        self.PanelBtn.Click += self._guard("PanelBtn", self._on_panel)
        self.DiagnosticsBtn.Click += self._guard("DiagnosticsBtn", self._on_diagnostics)
        self.NewRuleBtn.Click += self._guard("NewRuleBtn", self._on_new)
        self.DuplicateRuleBtn.Click += self._guard("DuplicateRuleBtn", self._on_duplicate)
        self.DeleteRuleBtn.Click += self._guard("DeleteRuleBtn", self._on_delete)
        self.MoveUpBtn.Click += self._guard("MoveUpBtn", self._on_move_up)
        self.MoveDownBtn.Click += self._guard("MoveDownBtn", self._on_move_down)
        self.MoveTopBtn.Click += self._guard("MoveTopBtn", self._on_move_top)
        self.MoveBottomBtn.Click += self._guard("MoveBottomBtn", self._on_move_bottom)
        self.SaveRuleBtn.Click += self._guard("SaveRuleBtn", self._on_save)
        self.ImportBtn.Click += self._guard("ImportBtn", self._on_import)
        self.ExportBtn.Click += self._guard("ExportBtn", self._on_export)
        self.AddConditionBtn.Click += self._guard("AddConditionBtn", self._on_add_condition)
        self.RemoveConditionBtn.Click += self._guard("RemoveConditionBtn", self._on_remove_condition)
        self.ConditionList.MouseDoubleClick += self._guard("ConditionList", self._on_remove_condition)
        self.CountBtn.Click += self._guard("CountBtn", self._on_count)
        self.ApplyBtn.Click += self._guard("ApplyBtn", self._on_apply)
        self.ViewsBtn.Click += self._guard("ViewsBtn", self._on_views)
        self.FilterBtn.Click += self._guard("FilterBtn", self._on_make_filter)
        self.ClearBtn.Click += self._guard("ClearBtn", self._on_clear)
        self.SelectBtn.Click += self._guard("SelectBtn", self._on_select)
        self.RuleList.SelectionChanged += self._guard("RuleList", self._on_rule_selected)
        self.CategoryList.SelectionChanged += self._guard("CategoryList", self._on_category_selected)
        self.CategorySearch.TextChanged += self._guard("CategorySearch", self._on_category_search)
        # S12.7.P: dependent fields load on DropDownClosed, never on
        # SelectionChanged -- which fires for every item arrowed past.
        self.FamilyCombo.DropDownClosed += self._guard("FamilyCombo", self._on_family_chosen)
        self.MatchAllRadio.Checked += self._guard("MatchAllRadio", self._on_match_changed)
        self.MatchAnyRadio.Checked += self._guard("MatchAnyRadio", self._on_match_changed)
        self.StoreMachineRadio.Checked += self._guard("StoreMachineRadio", self._on_store_changed)
        self.StoreProjectRadio.Checked += self._guard("StoreProjectRadio", self._on_store_changed)
        self.StoreSharedRadio.Checked += self._guard("StoreSharedRadio", self._on_store_changed)
        self.SharedPickBtn.Click += self._guard("SharedPickBtn", self._on_pick_shared)

    def _guard(self, control, handler):
        """*handler*, wrapped so a failure is loud, tagged and written down."""
        tag, what = self.OWNERS.get(control, ("UI", control))

        def wrapped(sender, args):
            try:
                handler(sender, args)
            except Exception as error:                  # noqa: BLE001
                import traceback
                self._blame(tag, what, error, traceback.format_exc())

        # Held for the life of the window. A Python closure handed to a .NET
        # event is not necessarily kept alive by the subscription, and a
        # collected handler is a button that silently stops working.
        self._handlers.append(wrapped)
        return wrapped

    def _blame(self, tag, what, error, detail=""):
        """Say which feature failed, why, and where the rest of it is."""
        try:
            self._status(diagnostics.failure(tag, what, error, detail), "error")
        except Exception:
            pass

    # -- the thread bridge -------------------------------------------------

    def ask(self, tag="UI", what="", **request):
        """Queue a request for Revit's thread and raise the event.

        *tag* and *what* travel WITH the request so that a failure on Revit's
        thread can name the feature that asked for it. Without them every
        error from over there reads "something went wrong in serve", which is
        the report that costs a round trip to act on.
        """
        request["tag"] = tag
        request["what"] = what or request.get("kind", "a request")
        self.handler.queue.append(request)
        diagnostics.record(tag, "asked Revit for {0}".format(request["what"]))
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

        if kind == "panel":
            pane = uiapp.GetDockablePane(
                DockablePaneId(Guid(anongee_filterpane.PANE_GUID)))
            pane.Show()
            return {"kind": kind, "ok": True, "message": ""}

        if kind == "views":
            return self._serve_views(doc, view, kind)

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

        if kind == "make_filter":
            from anongee_filterrules import revit_filter
            made, why = revit_filter.create(doc, rule)
            return {"kind": kind, "made": made, "why": why,
                    "name": filters.filter_name(rule)}

        if kind == "apply_many":
            # FEAT-11. What matches is worked out PER VIEW: a rule narrowed by
            # a category can match different elements in a plan and a section,
            # and reusing the active view's answer everywhere would isolate
            # the wrong set in all but one of them.
            from anongee_filterrules import compat
            pairs = []
            for view_id in request.get("views") or []:
                target = doc.GetElement(compat.element_id(view_id))
                if target is None:
                    continue
                pairs.append((target,
                              revit_query.matching_ids(doc, target, rule)))
            done, reports = revit_apply.isolate_many(doc, pairs)
            return {"kind": kind, "done": done, "reports": reports,
                    "asked": len(request.get("views") or [])}

        return {"kind": kind, "error": "unknown request"}

    def _report_many(self, answer):
        """Say what happened in EVERY view, not only the ones that worked.

        A multi-view apply that reports "done" while quietly doing nothing in
        four of eleven views is the failure this is written against. Each view
        gets a line in the log; the screen gets the count and a pointer,
        because there is room for a sentence and not for eleven.
        """
        reports = answer.get("reports") or []
        done = answer.get("done", 0)
        skipped = [(name, why) for name, count, why in reports if why]
        for name, count, why in reports:
            diagnostics.record("FEAT-11", "{0}: {1}".format(
                name, why or "isolated {0} element(s)".format(count)))
        if not done:
            self._status(diagnostics.headline("FEAT-11", (
                "Nothing was isolated. {0}".format(
                    skipped[0][1] if len(skipped) == 1 else
                    "None of the {0} view(s) could take it -- press "
                    "Diagnostics for the reason on each.".format(len(reports))
                ))), "error")
            return
        total = sum(count for _n, count, why in reports if not why)
        message = "Isolated in {0} view(s), {1} element(s) in all".format(
            done, total)
        if skipped:
            message = ("{0}. {1} view(s) skipped -- press Diagnostics for "
                       "which and why".format(message, len(skipped)))
        self._status(diagnostics.headline("FEAT-11", message),
                     "info" if skipped else "ok")

    def _serve_views(self, doc, view, kind):
        """Every view a rule could go to. Rule-free, so it is answered early."""
        from anongee_filterrules import compat
        active = None
        try:
            active = compat.id_value(view.Id) if view is not None else None
        except Exception:
            active = None
        return {"kind": kind, "views": revit_query.views(doc, active)}

    def _receive(self, answer):
        """Runs on the WPF thread. The only place controls are written."""
        self.busy = False
        kind = answer.get("kind")
        if kind == "count":
            # Released here rather than in the branch below, so a FAILED count
            # unlatches too -- otherwise one bad count stops the live one for
            # the rest of the session.
            self.counting = False
        problem = answer.get("error")
        if problem:
            # Already tagged and already logged if it came from serve's guard;
            # recorded here too when it is one of serve's own plain refusals
            # ("no project is open"), which never reach that guard.
            if not problem.startswith("["):
                problem = diagnostics.headline(
                    answer.get("tag", "UI"), problem)
                diagnostics.record(answer.get("tag", "UI"), problem)
            self._status(problem, "error")
            return

        if kind == "model":
            self.categories = answer["categories"]
            self.machine_path = answer["machine"]
            self.project_path = answer["project"]
            self._rebuild_categories()
            self._load_saved_rules()
            # project_path only exists once the model has answered, so this is
            # the first moment the store choice can say anything true.
            self._show_store_hint()
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
            # The rule changed shape, so what is wrong with it changed too.
            # Until 2026-09-10 nothing re-validated after the cascade returned
            # and the hint sat on "Pick a category to begin" with a category
            # already picked.
            self._validate()
            if not self.parameters:
                # An empty combo that says nothing is the failure BUG-5 is
                # about: three causes look identical from the window.
                self._status(
                    "No parameters found for {0}. Nothing of that category is "
                    "placed, none of its types answered, and Revit offered no "
                    "filterable parameters for it either. A rule on the "
                    "cascade alone still works.".format(
                        " + ".join(sorted(self.picked))), "error")
            else:
                self._status(
                    "{0} famil(ies), {1} type(s), {2} parameter(s) "
                    "({3} usable in a Revit view filter)".format(
                        len(answer["families"]), len(answer["types"]),
                        len(self.parameters),
                        sum(1 for _, ok in self.parameters if ok)), "info")
        elif kind == "types":
            self._fill_combo(self.TypeCombo, ANY_TYPE, answer["types"])
            if self.pending_type:
                self._select_text(self.TypeCombo, self.pending_type)
                self.pending_type = None
            self._status("{0} type(s)".format(len(answer["types"])), "info")
        elif kind == "count":
            self.LiveCount.Text = "{0} matched".format(answer["count"])
            if answer.get("tag") != "FEAT-8":
                # The Count button was pressed. The live count writes the same
                # label and says nothing else, or it would overwrite whatever
                # the status bar was telling the user, once per keystroke.
                self._status("Counted in the active view. Nothing changed.",
                             "info")
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
        elif kind == "make_filter":
            if not answer.get("made"):
                diagnostics.record("FEAT-13", "not created: {0}".format(
                    answer.get("why")))
                self._status(diagnostics.headline(
                    "FEAT-13", answer.get("why") or "Nothing was created."),
                    "error")
            else:
                diagnostics.record("FEAT-13", "created {0} (id {1})".format(
                    answer.get("name"), answer.get("made")))
                self._status(diagnostics.headline("FEAT-13", (
                    "Created {0!r} in Manage > Filters. It is not on any view "
                    "yet -- add it in Visibility/Graphics. Undo removes it."
                    .format(answer.get("name")))), "ok")
        elif kind == "views":
            self._open_view_picker(answer["views"])
        elif kind == "apply_many":
            self._report_many(answer)
        elif kind == "panel":
            self._status("The panel is docked under the ribbon. Drag it to "
                         "either edge if you would rather have it there.", "ok")
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
        """Re-read families, types and parameters for whatever is picked now.

        **Every path that changes ``self.picked`` ends here**, and that is the
        invariant, not a convention -- ``tests/test_filterview_ui.py`` fails a
        method that moves ``picked`` without it. BUG-13 was exactly that gap:
        loading a saved rule set ``picked`` and rebuilt the category list, but
        ``_rebuild_categories`` raises the ``rebuilding`` flag around its own
        selection loop (rightly -- a search must not re-ask Revit for every
        keystroke), so ``_on_category_selected`` never ran and nothing ever
        asked for the cascade.
        """
        if not self.picked:
            # Nothing will come back, so nothing will consume these. Left set,
            # they are applied to whatever rule is being edited when the NEXT
            # cascade lands -- one rule's family quietly appearing on another.
            self.pending_family = None
            self.pending_type = None
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
            conditions=list(self.conditions),
            source=self._chosen_store())

    # -- which store a rule lives in --------------------------------------

    def _chosen_store(self):
        """The store the editor is pointing at, as the engine spells it.

        Asked through ``store.destination`` rather than read straight off the
        radios, so a rule can never be marked for a file that does not exist
        -- an unsaved model has no folder, and a workstation nobody has
        pointed at a shared file has no shared file.
        """
        if self.StoreProjectRadio.IsChecked:
            wanted = store.PROJECT
        elif self.StoreSharedRadio.IsChecked:
            wanted = store.SHARED
        else:
            wanted = store.MACHINE
        return store.destination(wanted, bool(self.project_path),
                                 bool(self.shared_path))

    def _show_store(self, source):
        """Point the radios at *source* and say what it means."""
        self.rebuilding = True
        try:
            landing = store.destination(source, bool(self.project_path),
                                        bool(self.shared_path))
            self.StoreProjectRadio.IsChecked = landing == store.PROJECT
            self.StoreSharedRadio.IsChecked = landing == store.SHARED
            self.StoreMachineRadio.IsChecked = landing == store.MACHINE
        finally:
            self.rebuilding = False
        self._show_store_hint()

    def _show_store_hint(self):
        """Say where a Save will land, and why it cannot land elsewhere.

        A disabled control that does not say why is the failure S8.2 is about:
        "This project" is greyed for a model that has never been saved, and
        without a sentence that looks like the tool is broken rather than like
        the model needs saving first.
        """
        self.StoreProjectRadio.IsEnabled = bool(self.project_path)
        self.StoreSharedRadio.IsEnabled = bool(self.shared_path)
        if self.StoreProjectRadio.IsChecked and self.project_path:
            self.StoreHint.Text = (
                "Travels with the model: {0}".format(self.project_path))
        elif self.StoreSharedRadio.IsChecked and self.shared_path:
            self.StoreHint.Text = (
                "Everyone pointed at this file shares it: {0}".format(
                    self.shared_path))
        elif not self.project_path and not self.shared_path:
            self.StoreHint.Text = (
                "Saved on this workstation. \"This project\" needs the model "
                "saved first -- it has no folder yet. \"Shared\" needs a file "
                "chosen; press Choose.")
        elif not self.project_path:
            self.StoreHint.Text = (
                "Saved on this workstation. \"This project\" needs the model "
                "saved first: it has never been saved, so there is no folder "
                "to put a rules file in.")
        elif not self.shared_path:
            self.StoreHint.Text = (
                "Saved on this workstation. \"Shared\" needs a file chosen "
                "first -- press Choose and pick the one your office uses.")
        else:
            self.StoreHint.Text = ("Follows you into the next project: "
                                   "{0}".format(self.machine_path))

    def _on_pick_shared(self, sender, args):
        """Point this workstation at the office's rules file.

        A FILE rather than a folder, on purpose. WPF has no folder picker
        without dragging in WinForms, and pointing at the file is the better
        question anyway: several people picking the same file is exactly what
        sharing one set means, and "which folder" leaves the filename to be
        agreed separately.
        """
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Title = "Choose the shared rules file"
        dialog.Filter = "Filter View rules (*.json)|*.json|All files (*.*)|*.*"
        # False on purpose: pointing at a file nobody has created yet is how
        # the FIRST person in an office sets one up. It is written on save.
        dialog.CheckFileExists = False
        dialog.FileName = self.shared_path or store.FILE_NAME
        if not dialog.ShowDialog():
            return
        if not store.set_shared_path(dialog.FileName):
            self._status(diagnostics.headline("FEAT-19", (
                "Could not remember that choice: {0}".format(
                    store.last_error()))), "error")
            return
        self.shared_path = store.shared_path()
        diagnostics.record("FEAT-19", "shared store set to {0}".format(
            self.shared_path))
        self._load_saved_rules()
        self._show_store_hint()
        self._status(diagnostics.headline("FEAT-19", (
            "Shared rules: {0}".format(self.shared_path))), "ok")

    def _on_store_changed(self, sender, args):
        if self.rebuilding:
            return
        self._show_store_hint()
        self._validate()

    def _validate(self):
        """Show the first problem, or the rule read back as a sentence.

        Also the **single hook** for the live count (FEAT-8). Every change to
        the rule's shape already ends here -- a category ticked, a family
        chosen, a condition added, the match mode flipped, a rule loaded -- so
        hanging the count off this one call is the only version that cannot be
        forgotten when a new control is added. A test holds it here.
        """
        rule = self.current_rule()
        problems = rule.problems()
        self.ProblemText.Text = problems[0] if problems else rule.summary()
        self._bump_count(problems)
        return problems

    # -- FEAT-8: the live count -------------------------------------------

    def _bump_count(self, problems):
        """The rule changed, so the number on screen is now a lie.

        Said immediately and counted later. A stale number left sitting there
        while a new one is computed is worse than no number: it looks settled.
        """
        if self.rebuilding:
            return
        if problems:
            self.count_timer.stop()
            self.LiveCount.Text = ""
            return
        self.LiveCount.Text = "counting..."
        self.count_timer.reset()

    def _count_now(self):
        """The quiet period expired. Ask Revit, once."""
        if self.counting:
            # A slow model must not stack requests; the timer comes round
            # again when this one lands.
            self.count_timer.reset()
            return
        rule = self.current_rule()
        if rule.problems():
            self.LiveCount.Text = ""
            return
        self.counting = True
        self.ask(kind="count", tag="FEAT-8", what="the live count",
                 rule=rule.to_dict())

    # -- saved rules -------------------------------------------------------

    def _load_saved_rules(self):
        self.rule_set = store.load_all(self.machine_path, self.project_path,
                                       self.shared_path)
        self._rebuild_rules()

    def _rebuild_rules(self):
        rows = ArrayList()
        for rule in self.rule_set:
            rows.Add(RuleRow(rule))
        self.rebuilding = True
        try:
            self.RuleList.ItemsSource = rows
            # Rebuilding drops the selection, and a move rebuilds. Without
            # this, moving a block up one place deselects it and the second
            # press moves nothing -- which reads as the button being broken.
            keep = set(self._keep_selected)
            self._keep_selected = []
            if keep:
                self.RuleList.SelectedItems.Clear()
                for row in rows:
                    if row.RuleId in keep:
                        self.RuleList.SelectedItems.Add(row)
        finally:
            self.rebuilding = False
        self.RuleCountText.Text = "{0}".format(len(self.rule_set))

    def _selected_rule(self):
        row = self.RuleList.SelectedItem
        return self.rule_set.find(row.RuleId) if row is not None else None

    def _selected_rules(self):
        """Every ticked rule, in the order the list shows them.

        ``SelectedItems`` comes back in the order the user clicked, which is
        not the order they are looking at. Reading the set instead keeps a
        multi-rule move predictable: "these three, as they are" rather than
        "these three, shuffled into the order you happened to pick them".
        """
        wanted = set()
        for row in self.RuleList.SelectedItems:
            wanted.add(row.RuleId)
        return [rule for rule in self.rule_set if rule.id in wanted]

    def _on_rule_selected(self, sender, args):
        if self.rebuilding:
            return
        if self.RuleList.SelectedItems.Count != 1:
            # A multiple selection is for moving, copying and deleting. There
            # is one editor and it cannot show two rules, so loading the last
            # one clicked would silently discard whatever was being edited.
            chosen = self.RuleList.SelectedItems.Count
            if chosen:
                self._status("{0} rules selected. Duplicate, Delete and the "
                             "Move buttons act on all of them.".format(chosen),
                             "info")
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
        self._show_store(rule.source)
        # Set BEFORE the cascade is asked for, because _receive consumes them
        # the moment the answer lands. The cascade is fetched on Revit's
        # thread, so the family and type cannot be selected until it comes
        # back; _receive is the only place that knows they have arrived.
        self.pending_family = rule.family
        self.pending_type = rule.type_name
        self._rebuild_categories()
        self._rebuild_conditions()
        # BUG-13. Without this the editor showed the rule's NAME, categories
        # and conditions and nothing else: the Family and Type combos were
        # never filled, so the rule's own family and type could not be shown
        # and the two pendings above sat unconsumed forever. Worse than a
        # display fault -- current_rule() reads family and type off those
        # combos, so Apply, Count and Select built a rule with NO family and
        # NO type and quietly isolated a broader set than the rule names.
        self._refresh_cascade()
        self._validate()
        self._status("Loaded {0!r}. Press Apply to isolate what it "
                     "matches.".format(rule.name), "info")

    def _on_new(self, sender, args):
        self.editing_id = None
        self.RuleNameBox.Text = ""
        self.picked = set()
        self.conditions = []
        self.MatchAllRadio.IsChecked = True
        self._show_store(store.MACHINE)
        self.RuleList.SelectedIndex = -1
        self._rebuild_categories()
        self._rebuild_conditions()
        # Clears the combos and the parameter list too. Without it a new rule
        # started from a loaded one kept the old rule's families and types in
        # its dropdowns, offering a choice that no longer had anything behind
        # it -- and kept its pendings, which the next cascade would apply.
        self._refresh_cascade()
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
        """Write every rule to the store it belongs to.

        **Both files, every time.** A rule can move between stores, and a move
        is a write to both: added to one, gone from the other. Until 0.5.0 only
        the machine store was written, so editing a project rule wrote a copy
        to AppData and left the original beside the model -- and the next load
        showed the rule twice, with no way to tell which one Apply had used.
        """
        ok, problems = store.save_all(self.rule_set, self.machine_path,
                                      self.project_path, self.shared_path)
        self._rebuild_rules()
        if not ok:
            self._status("; ".join(problems), "error")
            return
        counts = store.partition(self.rule_set, bool(self.project_path),
                                 bool(self.shared_path))
        project = len(counts[store.PROJECT])
        shared = len(counts[store.SHARED])
        self._status(
            "Saved. {0} on this workstation{1}{2}.".format(
                len(counts[store.MACHINE]),
                ", {0} with the model".format(project) if project else "",
                ", {0} shared".format(shared) if shared else ""),
            "ok")

    def _on_duplicate(self, sender, args):
        chosen = self._selected_rules()
        if not chosen:
            self._status("Select a rule to duplicate.", "error")
            return
        for rule in chosen:
            copy = self.rule_set.duplicate(rule.id)
            # A copy of a project rule belongs beside the model too. Downgraded
            # when there is no project folder, which is what destination is for.
            copy.source = store.destination(rule.source,
                                            bool(self.project_path),
                                            bool(self.shared_path))
        self._write()

    def _on_delete(self, sender, args):
        chosen = self._selected_rules()
        if not chosen:
            self._status("Select a rule to delete.", "error")
            return
        dialog = TaskDialog("Filter View Manager")
        if len(chosen) == 1:
            dialog.MainInstruction = "Delete {0!r}?".format(chosen[0].name)
        else:
            dialog.MainInstruction = "Delete {0} rules?".format(len(chosen))
        # Named rather than counted up to a point: past a handful the list is
        # longer than the dialog and a count is the more honest summary.
        dialog.MainContent = (
            "{0}\n\nNothing in the model changes.".format(
                ", ".join(rule.name for rule in chosen[:6])
                + (", and {0} more".format(len(chosen) - 6)
                   if len(chosen) > 6 else "")))
        dialog.CommonButtons = (TaskDialogCommonButtons.Yes |
                                TaskDialogCommonButtons.No)
        if dialog.Show() != TaskDialogResult.Yes:
            return
        gone = [rule.id for rule in chosen]
        self.rule_set.remove_many(gone)
        if self.editing_id in gone:
            self.editing_id = None
        self._write()

    # -- FEAT-12: import and export ---------------------------------------

    def _on_export(self, sender, args):
        """Write rules to a file to send on.

        The selection if there is one, everything otherwise. With thirty rules
        saved, "export all" is rarely what somebody means when they have just
        ticked four.
        """
        chosen = self._selected_rules()
        going = rules.RuleSet(chosen) if chosen else self.rule_set
        if not len(going):
            self._status(diagnostics.headline(
                "FEAT-12", "There are no rules to export."), "error")
            return
        from Microsoft.Win32 import SaveFileDialog
        dialog = SaveFileDialog()
        dialog.Title = "Export filter view rules"
        dialog.Filter = "Filter View rules (*.json)|*.json|All files (*.*)|*.*"
        dialog.FileName = store.FILE_NAME
        if not dialog.ShowDialog():
            return
        if not store.export_set(going, dialog.FileName):
            self._status(diagnostics.headline(
                "FEAT-12", "Could not write {0}: {1}".format(
                    dialog.FileName, store.last_error())), "error")
            return
        diagnostics.record("FEAT-12", "exported {0} rule(s) to {1}".format(
            len(going), dialog.FileName))
        self._status(diagnostics.headline("FEAT-12", (
            "Exported {0} {1} to {2}".format(
                len(going), "selected rule(s)" if chosen else "rule(s)",
                dialog.FileName))), "ok")

    def _on_import(self, sender, args):
        """Add somebody else's rules. Never replace one of yours.

        An incoming rule is a gift, not an instruction: it cannot silently
        redefine a rule already in use, because nobody would notice. So every
        one arrives with a new id and, if its name is taken, a numbered name
        -- and the window says how many were renamed rather than leaving two
        identical-looking buttons to be discovered later.
        """
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Title = "Import filter view rules"
        dialog.Filter = "Filter View rules (*.json)|*.json|All files (*.*)|*.*"
        dialog.CheckFileExists = True
        if not dialog.ShowDialog():
            return
        coming, problem = store.import_set(dialog.FileName)
        if coming is None:
            diagnostics.record("FEAT-12", "import refused: {0}".format(problem))
            self._status(diagnostics.headline("FEAT-12", problem), "error")
            return
        added, renamed = self.rule_set.merge(coming, self._chosen_store())
        diagnostics.record("FEAT-12", "imported {0} rule(s) from {1}, {2} "
                           "renamed".format(added, dialog.FileName, renamed))
        self._write()
        self._status(diagnostics.headline("FEAT-12", (
            "Imported {0} rule(s){1}. They were saved to {2}.".format(
                added,
                ", {0} renamed because the name was taken".format(renamed)
                if renamed else "",
                "this project" if self._chosen_store() == store.PROJECT
                else "this workstation"))), "ok")

    def _on_move_up(self, sender, args):
        self._move(rules.UP)

    def _on_move_down(self, sender, args):
        self._move(rules.DOWN)

    def _on_move_top(self, sender, args):
        self._move(rules.TOP)

    def _on_move_bottom(self, sender, args):
        self._move(rules.BOTTOM)

    def _move(self, where):
        """Move the whole selection, keeping its own relative order.

        One rule at a time would reverse a multiple selection going up and
        collapse it going down, so the block move lives in ``RuleSet.reorder``
        where it can be tested without a window.
        """
        chosen = self._selected_rules()
        if not chosen:
            self._status("Select a rule to move.", "error")
            return
        if not self.rule_set.reorder([rule.id for rule in chosen], where):
            self._status("Already there.", "info")
            return
        self._keep_selected = [rule.id for rule in chosen]
        self._write()

    # -- the four actions --------------------------------------------------

    def _guard_payload(self):
        """Kept as the name the four action buttons already call."""
        return self._guard_rule()

    def _on_count(self, sender, args):
        payload = self._guard_payload()
        if payload:
            self._status("Counting...", "info")
            self.ask(kind="count", rule=payload)

    def _on_apply(self, sender, args):
        payload = self._guard_payload()
        if payload:
            self._status("Isolating...", "info")
            self.ask(kind="apply", rule=payload)

    def _on_select(self, sender, args):
        payload = self._guard_payload()
        if payload:
            self.ask(kind="select", rule=payload)

    def _on_clear(self, sender, args):
        self.ask(kind="clear", what="clearing the view")

    # -- FEAT-13: a real Revit view filter --------------------------------

    def _on_make_filter(self, sender, args):
        """Create a ParameterFilterElement. The one action here that WRITES.

        Everything else this tool does is temporary and leaves no trace. This
        creates an element that appears in Manage > Filters, survives a save,
        prints, and is visible to everyone who opens the model -- so it asks
        first, and it shows exactly what it is about to make rather than
        summarising it.

        The refusals are worked out here, on the window's side, from the
        parameter list already on screen. Revit checks again on its own thread
        (it is the only one that can be sure), but a rule that obviously
        cannot convert should say so without a round trip.
        """
        payload = self._guard_rule()
        if payload is None:
            return
        rule = self.current_rule()
        allowed, reasons = filters.convertible(
            rule, [name for name, ok in self.parameters if ok])
        if not allowed:
            diagnostics.record("FEAT-13", "refused: {0}".format("; ".join(reasons)))
            dialog = TaskDialog("Filter View Manager")
            dialog.MainInstruction = "This rule cannot become a Revit view filter"
            dialog.MainContent = (
                "It still works here -- pressing it isolates, which does not "
                "need a filter. Revit's own filters are narrower:\n\n- {0}"
                .format("\n- ".join(reasons)))
            dialog.Show()
            self._status(diagnostics.headline(
                "FEAT-13", reasons[0]), "error")
            return

        dialog = TaskDialog("Filter View Manager")
        dialog.MainInstruction = "Create a view filter in this project?"
        dialog.MainContent = (
            "This WRITES to the model. The filter appears in Manage > "
            "Filters, survives a save, prints, and everyone who opens the "
            "model will see it.\n\n{0}".format("\n".join(filters.plan(rule))))
        dialog.ExpandedContent = (
            "It is not added to any view. Add it where you want it in "
            "Visibility/Graphics, exactly as you would a filter you made by "
            "hand. Undo removes it.")
        dialog.CommonButtons = (TaskDialogCommonButtons.Yes |
                                TaskDialogCommonButtons.No)
        if dialog.Show() != TaskDialogResult.Yes:
            diagnostics.record("FEAT-13", "cancelled at the confirmation")
            self._status(diagnostics.headline(
                "FEAT-13", "Nothing was created."), "info")
            return

        self._status(diagnostics.headline(
            "FEAT-13", "Creating {0}...".format(filters.filter_name(rule))),
            "info")
        self.ask(kind="make_filter", tag="FEAT-13",
                 what="creating a view filter", rule=payload)

    # -- FEAT-11: apply to several views ----------------------------------

    def _on_views(self, sender, args):
        """Ask Revit what views there are; the picker opens when they land."""
        payload = self._guard_rule()
        if payload is None:
            return
        self.pending_views_rule = payload
        self._status(diagnostics.headline("FEAT-11", "Reading the views..."),
                     "info")
        self.ask(kind="views", tag="FEAT-11", what="reading the views")

    def _open_view_picker(self, listed):
        """The modal. Returns nothing; it asks for the isolate itself.

        Built and shown here rather than in ``_receive`` so the answer handler
        stays a dispatcher. A modal inside a dispatcher is how a window ends up
        unable to process the next answer.
        """
        picker = ViewPicker(self.window, listed, self._view_label_for_rule())
        chosen = picker.ask()
        if not chosen:
            self._status(diagnostics.headline(
                "FEAT-11", "No views ticked, so nothing was changed."), "info")
            return
        self._status(diagnostics.headline(
            "FEAT-11", "Isolating in {0} view(s)...".format(len(chosen))),
            "info")
        self.ask(kind="apply_many", tag="FEAT-11",
                 what="isolating in {0} view(s)".format(len(chosen)),
                 rule=self.pending_views_rule, views=list(chosen))

    def _view_label_for_rule(self):
        name = self.RuleNameBox.Text or "this rule"
        return "Isolating {0!r}".format(name)

    def _guard_rule(self):
        """The rule as data, or None with the reason already on screen."""
        problems = self._validate()
        if problems:
            self._status(problems[0], "error")
            return None
        return self.current_rule().to_dict()

    def _on_panel(self, sender, args):
        """Show the dockable pane, or say why there is not one.

        Registration happened at Revit start, on the other engine, and if it
        failed there is no pane to ask and no route to call -- so the record
        it left behind is the only thing that can answer. That is why it is
        written at all (BUG-5: three causes look identical from a ribbon with
        no panel on it).
        """
        record = anongee_filterpane.read_record()
        if not record:
            self._status(
                "The panel was never registered. startup.py left no record at "
                "all, which usually means the extension has not been reloaded "
                "since the panel was added -- reload pyRevit and try again.",
                "error")
            return
        if not record.get("registered"):
            self._status("The panel could not be registered at Revit start: "
                         "{0}".format(record.get("note") or "no reason given"),
                         "error")
            return
        self.ask(kind="panel")

    def _on_refresh(self, sender, args):
        self._status("Re-reading the model...", "info")
        self.ask(kind="model", what="reading the model")

    def _on_diagnostics(self, sender, args):
        """Show what happened, and put the log where it can be picked up.

        Not a MessageBox of a traceback: a traceback nobody can copy out of is
        the same as no traceback. The last few entries go in the window, and
        the folder is opened so the file itself can be attached to a message.
        """
        lines = diagnostics.recent(12)
        path = diagnostics.log_path()
        dialog = TaskDialog("Filter View Manager")
        dialog.MainInstruction = "Diagnostics"
        dialog.MainContent = (
            "Every action this tool takes is logged with the feature that owns "
            "it, so a failure can be reported in one line.\n\n{0}".format(path))
        dialog.ExpandedContent = ("\n".join(lines) if lines else
                                  "Nothing logged yet this session.")
        dialog.CommonButtons = (TaskDialogCommonButtons.Ok |
                                TaskDialogCommonButtons.Cancel)
        if dialog.Show() != TaskDialogResult.Ok:
            return
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            self._status("Nothing has been logged yet, so there is no folder "
                         "to open.", "info")
            return
        try:
            # .NET rather than subprocess: this engine ships a STRIPPED stdlib
            # (S12.9.3 -- no re, no csv), and finding out which way subprocess
            # went is not worth it when Process.Start is always there.
            from System.Diagnostics import Process
            Process.Start(folder)
            self._status("Diagnostics: opened {0}".format(folder), "info")
        except Exception as error:                          # noqa: BLE001
            # Never worth failing over: the path is on screen either way.
            self._status("The log is at {0} ({1})".format(
                path, diagnostics.describe(error)), "info")

    # -- lifecycle ---------------------------------------------------------

    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        # A DispatcherTimer left running holds a reference to a dead window and
        # keeps firing into it.
        try:
            self.count_timer.stop()
        except Exception:
            pass
        diagnostics.record("UI", "window closed")
        _state.window_ref = None

    def show(self, host):
        helper = WindowInteropHelper(self.window)
        helper.Owner = host
        self.window.Show()
        diagnostics.banner(VERSION)
        self._status("Reading the model...", "info")
        self.ask(kind="model", what="reading the model")


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
