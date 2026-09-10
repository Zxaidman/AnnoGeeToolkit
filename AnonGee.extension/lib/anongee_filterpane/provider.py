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

TWO ORIENTATIONS, ONE TREE
--------------------------
Revit lets the user drag this pane to the top, the bottom, or either side, and
the two shapes want opposite layouts: a wide short strip reads across, a narrow
tall column reads down. The first version used a ``WrapPanel`` on the theory
that it would reflow on its own. It did not -- docked to the right it centred a
single button in a column of dead space and clipped the second one off the
edge behind a horizontal scrollbar.

So the orientation is decided here, in ``_layout``, from the control's own
measured size, and applied to four things at once: which edge the actions dock
to, which way the two stacks run, which scrollbar is live, and how
each rule button is aligned and margined. There is still one element tree; only
its properties move.

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

from Autodesk.Revit.UI import (DockablePaneId, DockPosition,       # noqa: E402
                               ExternalEvent, IDockablePaneProvider,
                               IExternalEventHandler)
from System.IO import FileAccess, FileMode, FileStream              # noqa: E402
from System.Windows import (HorizontalAlignment, TextWrapping,      # noqa: E402
                            Thickness)
from System.Windows.Controls import (Button, Dock, DockPanel,       # noqa: E402
                                     Orientation, ScrollBarVisibility)
from System.Windows.Markup import XamlReader                        # noqa: E402

from . import PANE_GUID, PANE_TITLE

HERE = os.path.dirname(os.path.abspath(__file__))

#: Below this width the pane is treated as a side dock and lays out as a
#: column. It is a hair wider than the 240-360 a side-docked pane is allowed
#: to be (brand guidelines S12.4) so that dragging one to the edge switches
#: layout before the buttons start clipping, rather than after.
NARROW_WIDTH = 420.0

#: How wide a rule chip may get in the across-the-top layout. A rule may be
#: named anything; without this one long name pushes every other button off
#: the strip. Down the side there is no cap -- the chip fills the column and
#: the label ellipsizes inside it.
CHIP_MAX_WIDTH = 220.0

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
            self._say("could not be done: {0}".format(error), "error")

    def _run(self, uiapp):
        from anongee_filterrules import revit_apply, revit_query

        uidoc = uiapp.ActiveUIDocument
        if uidoc is None or uidoc.Document is None:
            self._say("open a project first", "error")
            return
        doc = uidoc.Document
        view = doc.ActiveView

        if self.action == "clear":
            ok, message = revit_apply.clear(doc, view)
            self._say(message or ("the view is back to normal" if ok
                                  else "the view could not be cleared"),
                      "ok" if ok else "error")
            return

        if self.rule is None:
            return
        missing = revit_query.resolve(doc, self.rule)
        if missing:
            self._say("; ".join(missing), "error")
            return
        matched = revit_query.matching_ids(doc, view, self.rule)
        count, message = revit_apply.isolate(doc, view, matched)
        self._say(message or "{0}: {1} element(s) isolated".format(
            self.rule.name, count), "ok" if count else "error")

    def _say(self, message, tone="info"):
        if self.report is not None:
            try:
                self.report(message, tone)
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
        self.actions = None
        self.scroll = None
        self.chips = []
        #: None until the first measured size arrives, so the first real
        #: SizeChanged always applies a layout rather than matching a guess.
        self.vertical = None
        self.handler = IsolateHandler()
        self.handler.report = self._show
        self.event = ExternalEvent.Create(self.handler)
        self._build()

    # -- IDockablePaneProvider --------------------------------------------

    def SetupDockablePane(self, data):
        """Revit calls this to learn what to dock, where, and whether to show it.

        ``VisibleByDefault = False`` is the whole of BUG-7. Registering a pane
        and showing it are separate things in the API but not in its defaults:
        the property starts **True**, so the first Revit start after install
        put the panel on screen with nobody having pressed anything. The
        project owner asked for the opposite in the first conversation about
        this tool -- *"does not need to start with revit, only when user click
        the pushbutton"* -- and this is the one line that delivers it. Revit
        remembers the user's own show/hide from then on.

        ``DockPosition.Top`` is only the *first* position: a horizontal strip
        under the ribbon. Drag it to either edge and Revit remembers that
        instead; ``_layout`` notices the new shape and lays out down the
        column.
        """
        data.FrameworkElement = self.control
        data.InitialState = _initial_state()
        try:
            data.VisibleByDefault = False
        except Exception:
            # Not worth failing registration over: a pane that shows itself
            # once is a nuisance, a pane that never registers is a missing
            # feature.
            pass

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
        self.actions = self.control.FindName("PaneActions")
        self.scroll = self.control.FindName("PaneScroll")
        refresh = self.control.FindName("PaneRefresh")
        if refresh is not None:
            refresh.Click += self._on_refresh
        clear = self.control.FindName("PaneClear")
        if clear is not None:
            clear.Click += self._on_clear
        self.control.SizeChanged += self._on_size
        self.reload()

    def reload(self):
        """Redraw the buttons from the rules file. Never raises.

        The window writes that file and this reads it -- the two run on
        different engines and share a folder, not a module. It is re-read on
        every refresh rather than cached, so a rule saved in the window is one
        press away from appearing here.
        """
        try:
            from anongee_filterrules import store
            rules = list(store.load_all(store.machine_path(), None))
        except Exception as error:
            self._show("the rules could not be read: {0}".format(error), "error")
            return

        try:
            chip_style = self.control.TryFindResource("ButtonRuleOnDark")
            self.buttons.Children.Clear()
            self.chips = []
            for rule in rules:
                button = Button()
                button.Content = rule.name or "(unnamed)"
                if chip_style is not None:
                    button.Style = chip_style
                button.ToolTip = rule.summary()
                button.Tag = rule
                button.Click += self._on_rule
                self.buttons.Children.Add(button)
                self.chips.append(button)
            self._dress_chips()
        except Exception as error:
            self._show("the buttons could not be drawn: {0}".format(error), "error")
            return

        self._show("{0} rule(s). Press one to isolate it in the active "
                   "view.".format(len(rules)) if rules else
                   "No saved rules yet. Build one in Filter View Manager.")

    # -- layout ------------------------------------------------------------

    def _on_size(self, sender, args):
        """Re-lay out when, and only when, the pane changes shape.

        ``SizeChanged`` fires on every drag pixel, so the work is gated on the
        orientation actually flipping. Without that gate a drag rebuilds the
        margins of every chip several hundred times.
        """
        try:
            self._layout(_wants_vertical(self.control.ActualWidth,
                                         self.control.ActualHeight))
        except Exception:
            pass

    def _layout(self, vertical):
        """Point the whole pane down the column, or across the strip."""
        if vertical == self.vertical:
            return
        self.vertical = vertical

        if self.buttons is not None:
            self.buttons.Orientation = (Orientation.Vertical if vertical
                                        else Orientation.Horizontal)
            # Without this the chips cannot fill the column however they are
            # aligned: a StackPanel left-aligned in its parent sizes to its
            # widest child, so Stretch on a chip stretches it to nothing.
            self.buttons.HorizontalAlignment = (HorizontalAlignment.Stretch
                                                if vertical
                                                else HorizontalAlignment.Left)
        if self.actions is not None:
            # Down the side there is no room beside the list, so the actions
            # take the top row; across the top there is nothing but room, so
            # they sit at the right where they do not push the rules along.
            DockPanel.SetDock(self.actions, Dock.Top if vertical else Dock.Right)
            self.actions.Orientation = Orientation.Horizontal
            self.actions.Margin = (Thickness(0, 0, 0, 6) if vertical
                                   else Thickness(6, 0, 0, 0))
            self.actions.HorizontalAlignment = (HorizontalAlignment.Stretch
                                                if vertical
                                                else HorizontalAlignment.Right)
        if self.scroll is not None:
            # Exactly one axis scrolls. Leaving the other on Auto is what put
            # a horizontal scrollbar under a side-docked column.
            self.scroll.VerticalScrollBarVisibility = (
                ScrollBarVisibility.Auto if vertical else ScrollBarVisibility.Disabled)
            self.scroll.HorizontalScrollBarVisibility = (
                ScrollBarVisibility.Disabled if vertical else ScrollBarVisibility.Auto)
        if self.status is not None:
            self.status.TextWrapping = _wrapping(vertical)
        self._dress_chips()

    def _dress_chips(self):
        """Align and space the rule buttons for the orientation in force."""
        vertical = bool(self.vertical)
        for button in self.chips:
            try:
                if vertical:
                    button.Margin = Thickness(0, 0, 0, 4)
                    button.HorizontalAlignment = HorizontalAlignment.Stretch
                    button.HorizontalContentAlignment = HorizontalAlignment.Left
                    button.MaxWidth = System.Double.PositiveInfinity
                else:
                    button.Margin = Thickness(0, 0, 6, 0)
                    button.HorizontalAlignment = HorizontalAlignment.Left
                    button.HorizontalContentAlignment = HorizontalAlignment.Center
                    button.MaxWidth = CHIP_MAX_WIDTH
            except Exception:
                pass

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

    def _show(self, message, tone="info"):
        """Say what happened, in a colour that agrees with the words.

        Colour is never the only signal (brand guidelines S10.4) -- the
        sentence says it too. The tint is there so a failure is noticed in a
        strip of text the user is not reading.
        """
        if self.status is None:
            return
        try:
            self.status.Text = message
            brush = self.control.TryFindResource(_TONE_BRUSH.get(
                tone, "BrushDarkTextMuted"))
            if brush is not None:
                self.status.Foreground = brush
        except Exception:
            pass


#: Status tone to the brush that carries it. Keys are checked against
#: pane.xaml by tests/test_filterview_ui.py, so a renamed brush is a failed
#: test rather than a silently uncoloured status line.
_TONE_BRUSH = {
    "info": "BrushDarkTextMuted",
    "ok": "BrushSuccessGreenOnDark",
    "error": "BrushErrorRedOnDark",
}


def _wants_vertical(width, height):
    """Is this pane shaped like a side dock?

    Two questions, because neither answers it alone. A side dock is narrow --
    that is the ordinary case and ``NARROW_WIDTH`` catches it. But a floating
    pane can be narrow-ish and very tall, or wide and short, and there the
    shape is the better guide than the width.

    Before the first layout pass both are zero, and a zero-sized control gets
    the horizontal layout the XAML already declares -- no flicker on load.
    """
    if width <= 0 or height <= 0:
        return False
    return width <= NARROW_WIDTH or height > width


def _wrapping(vertical):
    """Wrap the status down the side, ellipsize it across the top.

    A column has the height to spare and a truncated status is useless; a
    28px-tall strip does not, and a wrapping line there would push the buttons
    out of the pane.
    """
    return TextWrapping.Wrap if vertical else TextWrapping.NoWrap


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
