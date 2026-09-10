# -*- coding: utf-8 -*-
"""The pane itself: an ``IDockablePaneProvider`` and the buttons it draws.

Everything Revit-shaped about the panel lives here, and it is kept apart from
``__init__`` for one reason: ``__init__`` must be importable on a machine with
no Revit, so the record can be read and the paths tested. This module imports
``Autodesk.Revit.UI`` at module scope and cannot be.

WHAT PRESSING A BUTTON DOES
---------------------------
The same as pressing Apply in the window: ``IsolateElementsTemporary`` on the
active view, nothing written to the project. It goes through an
``ExternalEvent`` rather than running inline, and that is not ceremony --
``ExternalEvent.Execute`` is handed the ``UIApplication``, which is the only
way a dockable pane can reach the active document at all. A pane is not a
command; nothing hands it an ``ExternalCommandData``.

IRONPYTHON, NOT CPYTHON
-----------------------
pyRevit loads ``startup.py`` on its core engine. That makes this file simpler
than its CPython counterpart, not harder: the three Python.NET interface rules
(``__namespace__``, no ``__init__``, define-once) are Python.NET's, and none of
them apply on IronPython. If this ever moves to CPython all three come back.

It still obeys the dual-engine rules -- 2.7 syntax, pure ASCII, no ``re``, no
``anongee_toolkit`` -- because ``tests/test_filterrules.py`` checks this
package the same way it checks the rule engine, and because being loadable on
either engine is the property that makes the whole design work.
"""

from __future__ import division

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

import os                                                          # noqa: E402
import System                                                      # noqa: E402

from Autodesk.Revit.UI import (DockablePaneId, DockablePaneProviderData,  # noqa: E402
                               DockPosition, ExternalEvent,
                               IDockablePaneProvider, IExternalEventHandler)
from System.IO import FileAccess, FileMode, FileStream              # noqa: E402
from System.Windows.Markup import XamlReader                        # noqa: E402

from . import PANE_GUID, PANE_TITLE

HERE = os.path.dirname(os.path.abspath(__file__))

#: Held for the life of the Revit session. Revit keeps its own reference to the
#: provider, but the ExternalEvent and the handler would otherwise be collected
#: the moment registration returned, and the buttons would stop working with no
#: error to show for it.
_live = {}


def pane_id():
    return DockablePaneId(System.Guid(PANE_GUID))


class IsolateHandler(IExternalEventHandler):
    """Runs the isolate on Revit's thread, which is the only place it may run.

    A dockable pane is not a command: nothing gives it an
    ``ExternalCommandData``, so it has no document, no view and no API context
    of its own. ``Execute`` is handed a ``UIApplication``, and that is how the
    pane reaches the model at all.
    """

    def __init__(self):
        # IronPython, so an __init__ on an interface subclass is fine -- that
        # trap is Python.NET's. See this module's docstring.
        self.rule = None
        self.action = "apply"
        self.report = None

    def Execute(self, uiapp):
        try:
            self._run(uiapp)
        except Exception as error:                     # never let it out
            self._say("could not be done: {0}".format(error))

    def _run(self, uiapp):
        from anongee_filterrules import revit_apply, revit_query

        uidoc = uiapp.ActiveUIDocument
        if uidoc is None or uidoc.Document is None:
            self._say("open a project first")
            return
        doc = uidoc.Document
        view = doc.ActiveView

        if self.action == "clear":
            ok, message = revit_apply.clear(doc, view)
            self._say(message or ("the view is back to normal" if ok
                                  else "the view could not be cleared"))
            return

        if self.rule is None:
            return
        missing = revit_query.resolve(doc, self.rule)
        if missing:
            self._say("; ".join(missing))
            return
        matched = revit_query.matching_ids(doc, view, self.rule)
        count, message = revit_apply.isolate(doc, view, matched)
        self._say(message or "{0}: {1} element(s) isolated".format(
            self.rule.name, count))

    def _say(self, message):
        if self.report is not None:
            try:
                self.report(message)
            except Exception:
                pass

    def GetName(self):
        return "AnonGee_FilterViewPane"


class FilterViewPane(IDockablePaneProvider):
    """The pane Revit docks. Single control, rebuilt from the rules file."""

    def __init__(self):
        self.control = None
        self.status = None
        self.buttons = None
        self.handler = IsolateHandler()
        self.handler.report = self._show
        self.event = ExternalEvent.Create(self.handler)
        self._build()

    # -- IDockablePaneProvider --------------------------------------------

    def SetupDockablePane(self, data):
        """Revit calls this to learn what to dock and where.

        ``DockPosition.Top`` puts it as a horizontal strip across the top of
        the drawing area -- under the ribbon, which is what was asked for. The
        user can drag it to either edge afterwards and Revit remembers; the
        layout is a ``WrapPanel`` so it reflows into a column without being
        told.
        """
        data.FrameworkElement = self.control
        data.InitialState = _initial_state()

    # -- the control -------------------------------------------------------

    def _build(self):
        path = os.path.join(HERE, "pane.xaml")
        stream = FileStream(path, FileMode.Open, FileAccess.Read)
        try:
            self.control = XamlReader.Load(stream)
        finally:
            stream.Close()
        self.status = self.control.FindName("PaneStatus")
        self.buttons = self.control.FindName("PaneButtons")
        refresh = self.control.FindName("PaneRefresh")
        if refresh is not None:
            refresh.Click += self._on_refresh
        clear = self.control.FindName("PaneClear")
        if clear is not None:
            clear.Click += self._on_clear
        self.reload()

    def reload(self):
        """Redraw the buttons from the rules file. Never raises.

        The window writes that file and this reads it -- the two run on
        different engines and share a folder, not a module. It is re-read on
        every refresh rather than cached, so a rule saved in the window is one
        press away from appearing here.
        """
        from System.Windows import Thickness
        from System.Windows.Controls import Button

        try:
            from anongee_filterrules import store
            rules = list(store.load_all(store.machine_path(), None))
        except Exception as error:
            self._show("the rules could not be read: {0}".format(error))
            return

        try:
            self.buttons.Children.Clear()
            for rule in rules:
                button = Button()
                button.Content = rule.name or "(unnamed)"
                button.Margin = Thickness(0, 0, 6, 0)
                button.Padding = Thickness(10, 3, 10, 3)
                button.ToolTip = rule.summary()
                button.Tag = rule
                button.Click += self._on_rule
                self.buttons.Children.Add(button)
        except Exception as error:
            self._show("the buttons could not be drawn: {0}".format(error))
            return

        self._show("{0} rule(s). Press one to isolate it in the active "
                   "view.".format(len(rules)) if rules else
                   "No saved rules yet. Build one in Filter View Manager.")

    # -- events ------------------------------------------------------------

    def _on_rule(self, sender, args):
        self.handler.rule = sender.Tag
        self.handler.action = "apply"
        self._show("isolating {0}...".format(sender.Content))
        self.event.Raise()

    def _on_clear(self, sender, args):
        self.handler.action = "clear"
        self.event.Raise()

    def _on_refresh(self, sender, args):
        self.reload()

    def _show(self, message):
        if self.status is not None:
            try:
                self.status.Text = message
            except Exception:
                pass


def _initial_state():
    """Docked under the ribbon, across the drawing area.

    Built defensively because ``DockablePaneState`` moved namespace between
    Revit releases: a pane that will not register because of an import is a
    pane nobody can see, and Revit's own default is a perfectly good fallback.
    """
    try:
        from Autodesk.Revit.UI import DockablePaneState
    except ImportError:
        return None
    state = DockablePaneState()
    state.DockPosition = DockPosition.Top
    return state


def register(controlled_application):
    """Register the pane. Returns a dict describing what happened.

    Registering **twice** is the failure worth guarding: pyRevit reloads
    extensions without restarting Revit, so this can be reached a second time
    in one session, and Revit raises on a GUID it already knows. That is not a
    failure to report -- the pane from the first load is still there and still
    works -- so it is recorded as registered, with a note.
    """
    if _live.get("provider") is not None:
        return {"registered": True,
                "note": "already registered earlier in this Revit session"}

    provider = FilterViewPane()
    controlled_application.RegisterDockablePane(pane_id(), PANE_TITLE, provider)
    _live["provider"] = provider
    return {"registered": True,
            "note": "registered; hidden until the ribbon button shows it"}
