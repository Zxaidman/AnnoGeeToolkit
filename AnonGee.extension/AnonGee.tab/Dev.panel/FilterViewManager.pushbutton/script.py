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
from System.Windows import GridLength, GridUnitType, Thickness # noqa: E402
from System.Windows.Controls import (Button, ColumnDefinition,  # noqa: E402
                                     ComboBox, Grid, ListBoxItem, TextBox)
from System.Windows.Input import Keyboard, ModifierKeys        # noqa: E402
from System.Windows.Media import VisualTreeHelper              # noqa: E402
from System.IO import FileAccess, FileMode, FileStream         # noqa: E402
from System.Windows import Visibility                          # noqa: E402
from System.Windows.Interop import WindowInteropHelper         # noqa: E402
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

#: ``ModifierKeys.None`` cannot be written down -- ``None`` is a Python
#: keyword, so the attribute access is a SyntaxError and getattr is the only
#: way to name the .NET member.
NO_MODIFIER = getattr(ModifierKeys, "None")

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
    """One row for one rule, however many stores it happens to live in.

    ``RuleIds`` is every copy. Pointing the shared store at an export of your
    own rules puts the same rule in two files -- ``load_all`` keeps both,
    because neither store may silently win -- and ten rows for five rules
    reads as a broken list. One row badged ``MACHINE + SHARED`` says the same
    thing and does not.
    """

    __slots__ = ("Name", "Badge", "Summary", "RuleId", "RuleIds")

    def __init__(self, rule, copies=None):
        copies = list(copies or [rule])
        self.Name = rule.name or "(unnamed)"
        self.Badge = " + ".join(
            sorted(set((one.source or "machine").upper() for one in copies)))
        self.Summary = rule.summary()
        #: The copy the editor loads. The first, which is the machine store
        #: when there is one, because that is the one a person can always save.
        self.RuleId = rule.id
        #: Every copy, so Delete and the Move buttons act on all of them --
        #: deleting a row that leaves an identical rule behind in another file
        #: is the row coming straight back on the next load.
        self.RuleIds = [one.id for one in copies]


class CategoryRow(object):
    __slots__ = ("Name",)

    def __init__(self, name):
        self.Name = name


class ViewRow(object):
    """A view in the picker. S12.7.G: plain slots, no INotifyPropertyChanged."""

    __slots__ = ("Name", "Note", "ViewId", "Usable")

    def __init__(self, view_id, name, usable, why):
        self.Name = name
        self.Note = "" if usable else "cannot be isolated -- {0}".format(why)
        self.ViewId = view_id
        self.Usable = usable


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
                # The tag goes out with the request and has to come back
                # with the answer: serve's own branches build their dicts by
                # hand and none of them carried it, so every answer looked
                # untagged and the live count talked over the status bar.
                if isinstance(answer, dict):
                    answer.setdefault("tag", request.get("tag", "UI"))
                    answer.setdefault("what", request.get("what", ""))
                app.post(answer)

        def GetName(self):
            return "AnonGee_FilterViewManager"

    _state.handler_cls = FilterViewHandler
else:
    FilterViewHandler = _state.handler_cls


# ═══════════════════════════════════════════════════════════════════════════
# The window
# ═══════════════════════════════════════════════════════════════════════════

class ConditionEditor(object):
    """One editable filter-rule row: parameter, compare, value, unit, remove.

    Revit's Filters dialog edits each rule in place, on its own row, and that
    is the shape this copies. Ours used to compose a condition in four
    controls at the top and push it into a read-only list, which meant
    changing one operator was remove-then-rebuild.

    **Built in Python, not from a DataTemplate.** A template would have to
    bind to a row object, and S12.7.G is explicit that DataTemplate bindings
    to a Python property fail *silently* in this engine -- blank cells, no
    error. Real controls, added and read back directly, cannot fail that way;
    it costs more lines here and none of them are mysterious.
    """

    def __init__(self, owner, condition=None):
        self.owner = owner
        self._handlers = []
        self.root = Grid()
        for width in (GridLength(1, GridUnitType.Star), GridLength(6),
                      GridLength(150), GridLength(6), GridLength(160),
                      GridLength(6), GridLength(100), GridLength(34)):
            column = ColumnDefinition()
            column.Width = width
            self.root.ColumnDefinitions.Add(column)
        self.root.Margin = Thickness(0, 0, 0, 6)

        self.parameter = self._combo(0, "InputComboBox")
        self.operator = self._combo(2, "InputComboBox")
        self.value = self._text(4)
        self.unit = self._combo(6, "InputComboBox")
        self.remove = self._remove_button(7)

        for key in values.OPERATORS:
            self.operator.Items.Add(values.operator_label(key))
        self.operator.SelectedIndex = 0
        self.unit.Items.Add(NO_UNIT)
        for one in values.known_units():
            self.unit.Items.Add(one)
        self.unit.SelectedIndex = 0

        self.pending_parameter = ""
        if condition is not None:
            self.pending_parameter = condition.parameter
            self._select(self.operator, values.operator_label(condition.operator))
            self.value.Text = "" if condition.operator in values.VALUELESS_OPERATORS \
                else "{0}".format(condition.value)
            self._select(self.unit, condition.unit or NO_UNIT)

    # -- building ----------------------------------------------------------

    def _place(self, control, column):
        Grid.SetColumn(control, column)
        self.root.Children.Add(control)
        return control

    def _combo(self, column, style):
        combo = ComboBox()
        found = self.owner.window.TryFindResource(style)
        if found is not None:
            combo.Style = found
        combo.DropDownClosed += self._guard(
            self._changed, "editing a filter rule")
        return self._place(combo, column)

    def _text(self, column):
        box = TextBox()
        found = self.owner.window.TryFindResource("InputTextBox")
        if found is not None:
            box.Style = found
        box.TextChanged += self._guard(
            self._changed, "typing a rule value")
        return self._place(box, column)

    def _remove_button(self, column):
        button = Button()
        button.Content = "X"
        found = self.owner.window.TryFindResource("ButtonGhost")
        if found is not None:
            button.Style = found
        button.ToolTip = "Remove this rule row."
        button.Margin = Thickness(6, 0, 0, 0)
        button.Click += self._guard(
            self._on_remove, "removing a filter rule")
        return self._place(button, column)

    def _guard(self, handler, what="a filter rule row"):
        """Held for the life of the row, and loud when it fails.

        FEAT-21: recorded as well as guarded. These rows are where a rule is
        actually built -- picking a parameter, changing an operator, typing a
        value -- and a timeline that skipped them would show a rule being
        applied with no record of it ever being written.
        """
        def wrapped(sender, args):
            import time
            began = time.time()
            try:
                handler(sender, args)
            except Exception as error:                     # noqa: BLE001
                import traceback
                self.owner._blame("UI", what, error, traceback.format_exc())
                return
            diagnostics.step("UI", what, ms=(time.time() - began) * 1000.0)
        self._handlers.append(wrapped)
        return wrapped

    def _changed(self, sender, args):
        if self.owner.rebuilding:
            return
        self.owner._validate()

    def _on_remove(self, sender, args):
        self.owner._remove_row(self)

    def _select(self, combo, wanted):
        for index in range(combo.Items.Count):
            if names.same("{0}".format(combo.Items[index]), wanted):
                combo.SelectedIndex = index
                return True
        return False

    # -- reading -----------------------------------------------------------

    def fill_parameters(self, parameters):
        """Refill the parameter list, keeping what this row already names."""
        wanted = self.pending_parameter or self.parameter_name()
        self.parameter.Items.Clear()
        for name, filterable in parameters:
            self.parameter.Items.Add(
                name if filterable else name + NOT_FILTERABLE)
        if wanted and self._select_parameter(wanted):
            self.pending_parameter = ""
        elif self.parameter.Items.Count and not wanted:
            self.parameter.SelectedIndex = 0

    def _select_parameter(self, wanted):
        for index in range(self.parameter.Items.Count):
            plain = "{0}".format(self.parameter.Items[index]).replace(
                NOT_FILTERABLE, "").strip()
            if names.same(plain, wanted):
                self.parameter.SelectedIndex = index
                return True
        return False

    def parameter_name(self):
        chosen = self.parameter.SelectedItem
        if chosen is None:
            return self.pending_parameter or ""
        return "{0}".format(chosen).replace(NOT_FILTERABLE, "").strip()

    def operator_key(self):
        label = "{0}".format(self.operator.SelectedItem or "")
        for key in values.OPERATORS:
            if values.operator_label(key) == label:
                return key
        return "equals"

    def read(self):
        """This row as a ``Condition``."""
        chosen_unit = self.unit.SelectedItem
        unit = "" if chosen_unit is None else "{0}".format(chosen_unit)
        return rules.Condition(
            parameter=self.parameter_name(),
            operator=self.operator_key(),
            value=self.value.Text,
            unit="" if unit == NO_UNIT else unit,
            filterable=self.owner._is_filterable(self.parameter_name()))


class Ask(object):
    """Every question this tool asks, in our own chrome.

    It replaces Revit's ``TaskDialog``, which worked and looked like Revit --
    the wrong half of the screen to borrow from when everything around it is
    ours.

    Three shapes, one window:

    ``Ask.tell``     something happened, or something was refused. One button.
    ``Ask.confirm``  yes or no, with the detail a person needs to answer.
    ``Ask.edit``     the same, plus one line they can change first.

    Four separate dialogs would drift -- the third one written would put the
    buttons in a different order and nobody would notice until somebody
    pressed the wrong one.

    It touches no Revit API, so it opens straight from the WPF thread.
    """

    NAMES = ("DialogTitle", "DialogMessage", "DialogDetail", "DialogDetailBox",
             "DialogInput", "DialogInputRow", "DialogInputLabel",
             "DialogYesBtn", "DialogNoBtn", "DialogAccent")

    def __init__(self, owner, title, message, detail="", yes="Yes", no="No",
                 field="", value=""):
        path = os.path.join(HERE, "dialog.xaml")
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
            pass                       # a dialog that will not parent is fine
        self.window.Title = title
        self.DialogTitle.Text = title
        self.DialogMessage.Text = message
        if detail:
            self.DialogDetail.Text = detail
            self.DialogDetailBox.Visibility = Visibility.Visible
        if field:
            self.DialogInputLabel.Text = field
            self.DialogInput.Text = value or ""
            self.DialogInputRow.Visibility = Visibility.Visible
        self.DialogYesBtn.Content = yes
        if no is None:
            # One button. A refusal has nothing to say no to, and offering a
            # choice where there is none is how a Cancel gets pressed by habit.
            self.DialogNoBtn.Visibility = Visibility.Collapsed
        else:
            self.DialogNoBtn.Content = no
        self._handlers = []
        self.DialogYesBtn.Click += self._guard(self._on_yes)
        self.DialogNoBtn.Click += self._guard(self._on_no)
        self.answer = False

    def _guard(self, handler):
        def wrapped(sender, args):
            try:
                handler(sender, args)
            except Exception:                              # noqa: BLE001
                try:
                    self.window.DialogResult = False
                    self.window.Close()
                except Exception:
                    pass
        self._handlers.append(wrapped)
        return wrapped

    def _on_yes(self, sender, args):
        self.answer = True
        self.window.DialogResult = True
        self.window.Close()

    def _on_no(self, sender, args):
        self.answer = False
        self.window.DialogResult = False
        self.window.Close()

    def show(self):
        try:
            self.window.ShowDialog()
        except Exception as error:                         # noqa: BLE001
            import traceback
            diagnostics.failure("UI", "opening a dialog", error,
                                traceback.format_exc())
            return False
        return bool(self.answer)

    # -- the three shapes --------------------------------------------------

    @staticmethod
    def tell(owner, title, message, detail=""):
        """Say something. One button, because there is nothing to refuse."""
        Ask(owner, title, message, detail, yes="Close", no=None).show()

    @staticmethod
    def confirm(owner, title, message, detail="", yes="Yes", no="No"):
        return Ask(owner, title, message, detail, yes=yes, no=no).show()

    @staticmethod
    def edit(owner, title, message, value, field="Name", detail="",
             yes="Create", no="Cancel"):
        """Ask, with one line they can change first. ``None`` for a cancel."""
        dialog = Ask(owner, title, message, detail, yes=yes, no=no,
                     field=field, value=value)
        if not dialog.show():
            return None
        return "{0}".format(dialog.DialogInput.Text).strip()


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

    def _guard(self, handler, what="the view picker"):
        """Guarded, recorded, and kept alive. As the window's guard."""
        def wrapped(sender, args):
            import time
            began = time.time()
            try:
                handler(sender, args)
            except Exception as error:                      # noqa: BLE001
                import traceback
                self.ViewStatus.Text = diagnostics.failure(
                    "FEAT-11", what, error, traceback.format_exc())
                return
            diagnostics.step("FEAT-11", what,
                             ms=(time.time() - began) * 1000.0)
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
        self.conditions = []            # [Condition], as loaded
        self.rows = []                  # [ConditionEditor], what is on screen
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

        #: FEAT-21. Tickets for round trips that Revit has not answered yet,
        #: oldest first. See ``_receive`` for why this is a queue and not a
        #: ticket carried in the answer.
        self.pending = []
        #: FEAT-8. ``count_wanted`` says the rule has changed since the last
        #: count; ``counting`` says one is in flight. Together they are a
        #: self-clocking coalescer -- see ``_pump_count``.
        self.count_wanted = False
        self.counting = False
        #: FEAT-11. The rule the view picker is being opened for, held between
        #: asking Revit for the views and the picker coming back.
        self.pending_views_rule = None
        #: FEAT-19. The office's rules file, if this workstation has been
        #: pointed at one. Read once at startup; changed by the Choose button.
        self.shared_path = store.shared_path()
        #: FEAT-13. What a created view filter is called before the rule's own
        #: name. Remembered from the last one created, because a team's naming
        #: convention is a convention.
        self.filter_prefix = store.filter_prefix()

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
                "RefreshBtn", "PanelBtn", "RuleNameBox",
                "CategorySearch", "CategoryList", "FamilyCombo", "TypeCombo",
                "HideUnpicked", "CheckAllBtn", "CheckNoneBtn",
                "MatchAllRadio", "MatchAnyRadio",
                "AddConditionBtn", "ConditionRows",
                "ProblemText", "SaveRuleBtn",
                "StatusBadge", "StatusBadgeText", "StatusBar", "LiveCount",
                "CountBtn", "SelectBtn", "ClearBtn", "ApplyBtn", "CloseBtn"):
            setattr(self, name, find(name))

    def _fill_static_combos(self):
        """Only the version now: the operator and unit lists belong to a row.

        Each ``ConditionEditor`` fills its own, because there is one of each
        per rule row rather than one shared pair at the top of the panel.
        """
        self.VersionText.Text = VERSION

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
        "AddConditionBtn": ("UI", "Add rule row"),
        "HideUnpicked": ("UI", "Hide un-ticked categories"),
        "CheckAllBtn": ("UI", "Check all"),
        "CheckNoneBtn": ("UI", "Check none"),
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
        self.CheckAllBtn.Click += self._guard("CheckAllBtn", self._on_check_all)
        self.CheckNoneBtn.Click += self._guard("CheckNoneBtn", self._on_check_none)
        self.HideUnpicked.Click += self._guard("HideUnpicked", self._on_category_search)
        # A plain left click TOGGLES, in both lists, so clicking a ticked row
        # unticks it. Extended's own behaviour is to replace the selection,
        # which makes the tick look like it is not a tick.
        self.RuleList.PreviewMouseLeftButtonDown += self._guard(
            "RuleList", self._toggle_click)
        self.CategoryList.PreviewMouseLeftButtonDown += self._guard(
            "CategoryList", self._toggle_click)
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
        self.TypeCombo.DropDownClosed += self._guard("FamilyCombo", self._on_match_changed)
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
            import time
            began = time.time()
            try:
                handler(sender, args)
            except Exception as error:                  # noqa: BLE001
                import traceback
                # failure() writes its own timeline entry, so this one does
                # not -- a press that raised must appear once, as a failure.
                self._blame(tag, what, error, traceback.format_exc())
                return
            # FEAT-21. Every press, not only the ones that broke. The two bugs
            # that shipped in 0.6.0 both raised nothing at all, and a record
            # that only holds exceptions cannot show an action that simply
            # never happened. diagnostics folds consecutive repeats, so
            # typing in the search box is one row and not twenty.
            diagnostics.step(tag, what,
                             ms=(time.time() - began) * 1000.0)

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
        # FEAT-21. OPEN until the answer lands. An entry still open at the end
        # of the session is a request that went out and never came back --
        # which is what the live count did for a whole release, silently,
        # because a ``DispatcherTimer`` that never ticks raises nothing. The
        # report gives those their own heading.
        self.pending.append(diagnostics.begin(
            tag, request["what"], kind=request.get("kind", "?")))
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
            # FEAT-21. "Which Revit, which model, which view" is the first
            # question asked of any report and the one a screenshot never
            # answers. Read here because this is the only thread that may.
            return {"kind": kind,
                    "categories": [name for name, _ in revit_query.categories(doc)],
                    "view": revit_apply.view_label(view),
                    "can_isolate": allowed,
                    "why": why,
                    "machine": store.machine_path(),
                    "project": project,
                    "revit": self._host(uiapp),
                    "document": doc.Title or doc.PathName or "unsaved",
                    "worksets": doc.IsWorkshared}

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
            # The live count, fired on every keystroke, stays VIEW-ONLY. The
            # model-wide pass reads a parameter per element and typing is not
            # the moment to spend that. Explicit presses ask for "deep".
            if not request.get("deep"):
                return {"kind": kind,
                        "count": revit_query.count(doc, view, rule)}
            in_view, in_model = revit_query.audit(doc, view, rule)
            return {"kind": kind, "count": in_view, "in_model": in_model}

        if kind == "apply":
            # Reset first, then search: see revit_apply.isolate_fresh. A second
            # Apply would otherwise search the view through the first one's
            # isolate and report "nothing matched" about a model full of them.
            def find_ids():
                return revit_query.matching_ids(doc, view, rule)

            count, message, was_reset = revit_apply.isolate_fresh(
                doc, view, find_ids)
            # AFTER the isolate, and deliberately: model_count does not scope
            # to the view, so the isolate standing does not change it -- and
            # asking first would have paid for it even when Revit went on to
            # refuse the isolate.
            return {"kind": kind, "count": count, "message": message,
                    "replaced": was_reset,
                    "in_model": revit_query.model_count(doc, view, rule)}

        if kind == "select":
            matched = revit_query.matching_ids(doc, view, rule)
            from anongee_filterrules import compat
            uidoc.Selection.SetElementIds(compat.id_list(matched))
            return {"kind": kind, "count": len(matched),
                    "in_model": revit_query.model_count(doc, view, rule)}

        if kind == "make_filter":
            from anongee_filterrules import revit_filter
            wanted = request.get("filter_name") or filters.filter_name(rule)
            made, why = revit_filter.create(doc, rule, name=wanted)
            return {"kind": kind, "made": made, "why": why, "name": wanted}

        if kind == "apply_many":
            # FEAT-11. What matches is worked out PER VIEW: a rule narrowed by
            # a category can match different elements in a plan and a section,
            # and reusing the active view's answer everywhere would isolate
            # the wrong set in all but one of them.
            from anongee_filterrules import compat

            def find_ids(target):
                return revit_query.matching_ids(doc, target, rule)

            pairs = []
            for view_id in request.get("views") or []:
                target = doc.GetElement(compat.element_id(view_id))
                if target is None:
                    continue
                pairs.append((target, find_ids))
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

    def _host(self, uiapp):
        """Revit's version, as one line. Never raises -- it is a note.

        Every attribute is fetched defensively: a report that fell over
        because one of them is missing on some release is a report nobody
        gets, and the version string is the least important thing in it.
        """
        parts = []
        try:
            app = uiapp.Application
        except Exception:
            return "unknown"
        for attribute in ("VersionName", "VersionNumber", "VersionBuild",
                          "SubVersionNumber"):
            try:
                value = getattr(app, attribute, None)
                if value:
                    parts.append("{0}".format(value))
            except Exception:
                continue
        return " / ".join(parts) if parts else "unknown"

    def _serve_views(self, doc, view, kind):
        """Every view a rule could go to. Rule-free, so it is answered early.

        ``revit_query`` is imported HERE and not taken from ``serve``. It is a
        local there, so this method could not see it and every press of Views
        raised ``NameError: name 'revit_query' is not defined`` -- which the
        0.6.0 diagnostics reported by name, tag and all, which is the whole
        reason that work went first.
        """
        from anongee_filterrules import compat, revit_query
        active = None
        try:
            active = compat.id_value(view.Id) if view is not None else None
        except Exception:
            active = None
        return {"kind": kind, "views": revit_query.views(doc, active)}

    def _receive(self, answer):
        """Runs on the WPF thread. The only place controls are written."""
        self.busy = False
        # FIFO, and it is exact rather than approximate: Execute drains the
        # queue in order and posts each answer as it finishes one, so the nth
        # answer belongs to the nth request. Closing by ticket carried in the
        # answer would have been equivalent but for one thing -- the handler
        # class is emitted ONCE per Revit session (S12.8.7.3), so a change to
        # Execute does not reach a Revit that is already running, and a
        # pairing that depends on it would quietly do nothing until restart.
        if self.pending:
            diagnostics.finish(
                self.pending.pop(0),
                diagnostics.FAILED if answer.get("error") else diagnostics.OK,
                detail=answer.get("error") or "")
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
            if kind == "count":
                self._pump_count()
            return

        if kind == "model":
            self.categories = answer["categories"]
            self.machine_path = answer["machine"]
            self.project_path = answer["project"]
            diagnostics.note("Revit", answer.get("revit", "unknown"))
            diagnostics.note("document", answer.get("document", "unknown"))
            diagnostics.note("workshared", answer.get("worksets"))
            diagnostics.note("active view", answer.get("view", "unknown"))
            diagnostics.note("can isolate", answer.get("can_isolate"))
            diagnostics.note("categories", len(self.categories))
            diagnostics.note("machine store", self.machine_path)
            diagnostics.note("project store", self.project_path or "none")
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
            hidden = self._hidden_note(answer)
            self.LiveCount.Text = self._count_label(answer, "matched")
            self._pump_count()      # the rule may have moved on since
            if answer.get("tag") != "FEAT-8":
                # The Count button was pressed. The live count writes the same
                # label and says nothing else, or it would overwrite whatever
                # the status bar was telling the user, once per keystroke.
                self._status(hidden or "Counted in the active view. Nothing "
                             "changed.", "error" if hidden else "info")
        elif kind == "apply":
            if answer["message"]:
                self._status(answer["message"], "error")
            else:
                hidden = self._hidden_note(answer)
                self.LiveCount.Text = self._count_label(answer, "isolated")
                self._status(hidden or (
                    "Isolated in the active view{0}. Nothing was written to "
                    "the project.".format(
                        ", replacing what was shown"
                        if answer.get("replaced") else "")),
                    "error" if hidden else "ok")
        elif kind == "select":
            hidden = self._hidden_note(answer)
            self.LiveCount.Text = self._count_label(answer, "selected")
            self._status(hidden or "Pushed to Revit's selection.",
                         "error" if hidden else "ok")
        elif kind == "make_filter":
            if not answer.get("made"):
                why = answer.get("why") or "Nothing was created."
                diagnostics.record("FEAT-13", "not created: {0}".format(why))
                # A refusal that only reaches the status bar is one somebody
                # presses through twice before reading it. This action writes
                # to the model when it succeeds, so it gets a dialog either way.
                Ask.tell(self.window, "No filter was created", why)
                self._status(diagnostics.headline("FEAT-13", why), "error")
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

    def _hidden_note(self, answer):
        """BUG-20. The sentence for "the view is hiding some of these", or "".

        Recorded as a FINDING and not as a failure, because nothing failed:
        ``FilteredElementCollector(doc, view.Id)`` answered the question it
        was asked. It is in the report all the same -- a tool that quietly
        isolates eighteen of twenty-four columns and says "18 matched" is
        telling the truth in a way that reads as a lie.
        """
        sentence = diagnostics.gap(answer.get("count"),
                                   answer.get("in_model"))
        if not sentence:
            return ""
        return diagnostics.headline(
            answer.get("tag", "UI"),
            diagnostics.finding(answer.get("tag", "UI"), sentence))

    def _count_label(self, answer, verb):
        """``"18 matched"``, or ``"18 matched, 24 in the model"``.

        The label carries the gap as well as the status bar, because the label
        is the thing being read a second later when the view looks wrong and
        the status bar has already been written over by something else.
        """
        shown = answer.get("count")
        total = answer.get("in_model")
        if not diagnostics.gap(shown, total):
            return "{0} {1}".format(shown, verb)
        return "{0} {1}, {2} in the model".format(shown, verb, total)

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
        """Refill every row's parameter list, keeping what each row names.

        A row keeps its parameter across a cascade: ticking another category
        must not silently re-point a rule row at whatever happens to be first
        in the new list.
        """
        self.rebuilding = True
        try:
            for row in self.rows:
                row.fill_parameters(self.parameters)
        finally:
            self.rebuilding = False

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

    # -- categories --------------------------------------------------------

    def _toggle_click(self, sender, args):
        """A plain left click ticks, or UNTICKS what is already ticked.

        ``SelectionMode="Extended"`` gives Ctrl+click and Shift+click for
        free, and its plain click REPLACES the selection -- so clicking a
        ticked row leaves it ticked and clears everything else, which makes
        the tick look like it is not really a tick.

        Ctrl and Shift are left entirely alone: those gestures mean what they
        mean everywhere in Windows, and re-implementing them here would only
        get them subtly wrong.
        """
        if Keyboard.Modifiers != NO_MODIFIER:
            return
        item = self._item_under(args.OriginalSource)
        if item is None:
            return
        item.IsSelected = not item.IsSelected
        # Handled, or WPF's own click runs afterwards and replaces what we
        # just toggled.
        args.Handled = True
        # Focus still has to move, or the keyboard is left behind the mouse.
        try:
            item.Focus()
        except Exception:
            pass

    def _item_under(self, source):
        """The ``ListBoxItem`` a click landed in, walking up from whatever
        part of the template actually got hit."""
        current = source
        for _step in range(24):          # templates are not that deep
            if current is None:
                return None
            if isinstance(current, ListBoxItem):
                return current
            try:
                current = VisualTreeHelper.GetParent(current)
            except Exception:
                return None
        return None

    def _on_check_all(self, sender, args):
        """Tick everything SHOWN -- with a search in the box that is the
        search results, not all 137 categories."""
        shown = set(row.Name for row in self.CategoryList.Items)
        self.picked = self.picked | shown
        self._rebuild_categories()
        self._refresh_cascade()

    def _on_check_none(self, sender, args):
        shown = set(row.Name for row in self.CategoryList.Items)
        self.picked = self.picked - shown
        self._rebuild_categories()
        self._refresh_cascade()

    def _rebuild_categories(self):
        """Redraw the list for the current search, keeping what was ticked.

        ``self.picked`` is the source of truth, not the ListBox: rebuilding
        ItemsSource clears the selection, and the ticks must survive a search.
        """
        needle = names.key(self.CategorySearch.Text)
        only_picked = bool(self.HideUnpicked.IsChecked)
        rows = ArrayList()
        for name in self.categories:
            if needle and needle not in names.key(name):
                continue
            if only_picked and name not in self.picked:
                continue
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
        """The count lives in the rule summary now, not in its own label."""
        return len(self.picked)

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
        """An empty row, edited in place -- Revit's shape.

        No validation here: an empty row IS the thing being added, and
        refusing to add one until it is already correct is the opposite of
        editing in place. ``_validate`` says what is still missing.
        """
        self._add_row(None)
        self._validate()

    def _add_row(self, condition):
        row = ConditionEditor(self, condition)
        row.fill_parameters(self.parameters)
        self.rows.append(row)
        self.ConditionRows.Children.Add(row.root)
        return row

    def _remove_row(self, row):
        try:
            self.ConditionRows.Children.Remove(row.root)
        except Exception:
            pass
        if row in self.rows:
            self.rows.remove(row)
        self._validate()

    def _is_filterable(self, parameter_name):
        for name, filterable in self.parameters:
            if names.same(name, parameter_name):
                return filterable
        return True

    def _rebuild_conditions(self):
        """Redraw every row from ``self.conditions``."""
        self.rebuilding = True
        try:
            self.ConditionRows.Children.Clear()
            self.rows = []
            for condition in self.conditions:
                self._add_row(condition)
        finally:
            self.rebuilding = False

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
            conditions=[row.read() for row in self.rows],
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

        Said immediately and counted next. A stale number left sitting there
        while a new one is computed is worse than no number: it looks settled.
        """
        if self.rebuilding:
            return
        if problems:
            self.count_wanted = False
            self.LiveCount.Text = ""
            return
        self.count_wanted = True
        self.LiveCount.Text = "counting..."
        self._pump_count()

    def _pump_count(self):
        """Ask for a count if one is wanted and none is already in flight.

        **No timer.** 0.6.0 debounced with a ``DispatcherTimer`` and the count
        never arrived -- it sat on "counting..." for the whole session. A
        timer that does not tick fails *silently* and there is nothing to
        catch: no exception, no answer, no way to tell it apart from a slow
        model.

        This clocks itself off the answers instead. A change while a count is
        in flight only sets the flag; the answer landing pumps again. So the
        rate is whatever Revit can actually manage, requests can never stack,
        and the two flags cannot wedge -- every answer clears ``counting`` and
        pumps, so the worst case is one extra count, never none.
        """
        if self.counting or not self.count_wanted:
            return
        rule = self.current_rule()
        if rule.problems():
            self.count_wanted = False
            self.LiveCount.Text = ""
            return
        self.count_wanted = False
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
        for rule, copies in self.rule_set.grouped():
            rows.Add(RuleRow(rule, copies))
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
                    if keep.intersection(row.RuleIds):
                        self.RuleList.SelectedItems.Add(row)
        finally:
            self.rebuilding = False
        # The row count, not the rule count: with a shared store pointed at a
        # copy of your own rules they differ, and the number beside "Saved
        # rules" has to mean the list under it.
        self.RuleCountText.Text = "{0}".format(rows.Count)

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
            wanted.update(row.RuleIds)
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
        # Named rather than counted up to a point: past a handful the list is
        # longer than the dialog and a count is the more honest summary.
        named = ", ".join(rule.name for rule in chosen[:6]) + (
            ", and {0} more".format(len(chosen) - 6) if len(chosen) > 6 else "")
        stores = sorted(set((rule.source or store.MACHINE) for rule in chosen))
        if not Ask.confirm(
                self.window, "Delete rules",
                "Delete {0}? Nothing in the model changes.".format(
                    "{0!r}".format(chosen[0].name) if len(chosen) == 1
                    else "{0} rules".format(len(chosen))),
                detail="{0}\n\nFrom: {1}".format(named, ", ".join(stores)),
                yes="Delete", no="Keep them"):
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
            # deep: also count the MODEL, so the view hiding some of them is
            # something the user is told rather than something they notice.
            # The live count never asks for this -- see serve's count branch.
            self.ask(kind="count", rule=payload, deep=True)

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
            Ask.tell(self.window, "Not a Revit view filter",
                     "This rule still works here -- pressing it isolates, "
                     "which does not need a filter. Revit's own filters are "
                     "narrower, in these ways:",
                     detail="- " + "\n- ".join(reasons))
            self._status(diagnostics.headline("FEAT-13", reasons[0]), "error")
            return

        # The name is EDITABLE, and the prefix is taken from what they type.
        # A filter lands in a list the whole team shares, so it wants a
        # prefix -- but which prefix is the team's business, not ours, and a
        # separate control for it is one nobody would find.
        chosen_name = Ask.edit(
            self.window, "Create a view filter",
            "This WRITES to the model. The filter appears in Manage > "
            "Filters, survives a save, prints, and everyone who opens the "
            "model will see it. It is not added to any view -- add it in "
            "Visibility/Graphics, as you would one made by hand. Undo removes "
            "it.",
            value=filters.filter_name(rule, self.filter_prefix),
            field="Filter name",
            detail="\n".join(filters.plan(rule, self.filter_prefix)),
            yes="Create", no="Cancel")
        if chosen_name is None:
            diagnostics.record("FEAT-13", "cancelled at the confirmation")
            self._status(diagnostics.headline(
                "FEAT-13", "Nothing was created."), "info")
            return
        if not chosen_name:
            self._status(diagnostics.headline(
                "FEAT-13", "A filter needs a name."), "error")
            return

        # Typing "STR - Columns" over "AnonGee - Columns" says the prefix is
        # now "STR - ". Remembered so the next one is offered it; NOT
        # remembered when they simply renamed this one filter, because
        # guessing a convention from that makes every later name wrong.
        implied = filters.prefix_of(chosen_name, rule)
        if implied is not None and implied != self.filter_prefix:
            self.filter_prefix = implied
            store.set_filter_prefix(implied)
            diagnostics.record("FEAT-13",
                               "filter prefix is now {0!r}".format(implied))

        self._status(diagnostics.headline(
            "FEAT-13", "Creating {0}...".format(chosen_name)), "info")
        self.ask(kind="make_filter", tag="FEAT-13",
                 what="creating a view filter", rule=payload,
                 filter_name=chosen_name)

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
        """FEAT-21. Write the session to one file and open the folder.

        The 0.7.0 version of this showed the last twelve log lines and opened
        a folder, which asked the user to find the right file and then to work
        out which twelve lines mattered. A round of testing produces ten
        observations, and they were arriving one screenshot at a time.

        So the button now WRITES: one Markdown file holding the whole session
        -- everything that happened, everything that failed, everything that
        went out and never came back, and what is on disk -- ordered so the
        problems are at the top. It is meant to be attached whole.
        """
        report = diagnostics.write_report()
        if not report:
            # Writing it is the point of the press, so a failure to write is
            # not something to swallow and carry on from.
            Ask.tell(self.window, "The report could not be written",
                     "Nothing could be written to {0}. The folder may be "
                     "read-only, or on a drive that is not connected. The "
                     "raw log is still being appended to at {1}.".format(
                         diagnostics.report_path(), diagnostics.log_path()))
            self._status(diagnostics.headline(
                "FEAT-21", "the report could not be written"), "error")
            return

        actions = diagnostics.timeline()
        broken = [one for one in actions
                  if one.get("outcome") in (diagnostics.FAILED,
                                            diagnostics.OPEN)]
        found = diagnostics.findings()
        summary = "{0} action(s) recorded, {1} that did not finish, {2} " \
                  "finding(s).".format(len(actions), len(broken), len(found))
        if not Ask.confirm(
                self.window, "Diagnostic report written",
                "{0}\n\nThe whole session is in one file. Attach it as it "
                "is -- it is written to be read without the "
                "screenshots.\n\n{1}".format(summary, report),
                detail="\n".join(diagnostics.recent(12))
                       or "Nothing logged yet this session.",
                yes="Open the folder", no="Close"):
            self._status(diagnostics.headline(
                "FEAT-21", "report written to {0}".format(report)), "ok")
            return
        folder = os.path.dirname(report)
        try:
            # .NET rather than subprocess: this engine ships a STRIPPED stdlib
            # (S12.9.3 -- no re, no csv), and finding out which way subprocess
            # went is not worth it when Process.Start is always there.
            from System.Diagnostics import Process
            Process.Start(folder)
            self._status("FEAT-21: opened {0}".format(folder), "ok")
        except Exception as error:                          # noqa: BLE001
            # Never worth failing over: the path is on screen either way.
            self._status("The report is at {0} ({1})".format(
                report, diagnostics.describe(error)), "info")

    # -- lifecycle ---------------------------------------------------------

    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        self.count_wanted = False
        diagnostics.step("UI", "window closed")
        # FEAT-21. Written without being asked for, so that a session where
        # something went wrong has a report in it whether or not the user
        # thought to press the button before closing. The press is for
        # getting at it mid-session; this is for the one they will be asked
        # for tomorrow. Never fails the close.
        try:
            diagnostics.write_report()
        except Exception:                                   # noqa: BLE001
            pass
        _state.window_ref = None

    def show(self, host):
        helper = WindowInteropHelper(self.window)
        helper.Owner = host
        self.window.Show()
        diagnostics.banner(VERSION)
        diagnostics.note("log", diagnostics.log_path())
        diagnostics.note("report", diagnostics.report_path())
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
        # Revit's own dialog, deliberately, and one of only two left. There
        # is no window yet to parent ours to, and if XAML loading is what
        # broke then reporting it through more XAML reports nothing.
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
    # The other one, for the same reason: this is the handler for the window
    # failing to open, so it cannot depend on the window's machinery.
    dialog = TaskDialog("Filter View Manager")
    dialog.MainInstruction = "The window did not open"
    dialog.MainContent = "{0}".format(error)
    dialog.ExpandedContent = detail
    dialog.Show()
