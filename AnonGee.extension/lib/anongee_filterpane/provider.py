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
from System.Windows.Input import Keyboard, ModifierKeys             # noqa: E402
from System.Windows.Controls import (Button, Dock, DockPanel,       # noqa: E402
                                     Orientation, ScrollBarVisibility)
from System.Windows.Markup import XamlReader                        # noqa: E402

from . import PANE_GUID, PANE_TITLE
from .layout import (CHIP_MAX_WIDTH, CHIP_STYLE, tone_brush,
                     wants_vertical, wheel_step)

HERE = os.path.dirname(os.path.abspath(__file__))

#: Held for the life of the Revit session. Revit keeps its own reference to the
#: provider, but the ExternalEvent and the handler would otherwise be collected
#: the moment registration returned, and the buttons would stop working with no
#: error to show for it.
_live = {}

#: ``ModifierKeys.None`` cannot be written down -- ``None`` is a Python
#: keyword, so the attribute access is a SyntaxError on both engines and
#: getattr is the only way to name the .NET member.
NO_MODIFIER = getattr(ModifierKeys, "None")


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
        #: Called with the model's project-store path on every run. The pane
        #: has no document of its own, so this is the only moment it can learn
        #: where the model keeps its rules -- see FilterViewPane.on_paths.
        self.on_paths = None

    def Execute(self, uiapp):
        try:
            self._run(uiapp)
        except Exception as error:                     # never let it out
            import traceback
            from anongee_filterrules import diagnostics
            self._say(diagnostics.failure("PANEL", self.action or "a press",
                                          error, traceback.format_exc()),
                      "error")

    def _run(self, uiapp):
        from anongee_filterrules import revit_apply, revit_query

        uidoc = uiapp.ActiveUIDocument
        if uidoc is None or uidoc.Document is None:
            self._say("open a project first", "error")
            return
        doc = uidoc.Document
        view = doc.ActiveView
        self._tell_paths(doc)

        if self.action == "refresh":
            # Nothing to do in the model: the point of the trip was the path.
            return

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
        # Pressing a SECOND rule has to put the view back first. Two reasons,
        # and the second is the one that bites: isolating again can only
        # narrow, and the collector cannot see past the isolate rule 1 left
        # behind -- so the search for rule 2 runs against rule 1's survivors
        # and usually finds nothing at all.
        rule = self.rule

        def find_ids():
            return revit_query.matching_ids(doc, view, rule)

        count, message, was_reset = revit_apply.isolate_fresh(doc, view,
                                                              find_ids)
        if message:
            self._say("{0}: {1}".format(rule.name, message), "error")
            return
        self._say("{0}: {1} element(s) isolated{2}".format(
            rule.name, count,
            ", replacing what was shown" if was_reset else ""), "ok")

    def _tell_paths(self, doc):
        """Hand the pane the model's project-store path.

        A dockable pane is not a command and never sees a document, so it
        cannot work out where THIS model keeps its rules. Every trip through
        the external event has one, so every trip carries the answer back.
        """
        if self.on_paths is None:
            return
        try:
            from anongee_filterrules import store
            self.on_paths(store.project_path(doc.PathName))
        except Exception:
            pass

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
        self.search = None
        #: Every rule read from disk, unfiltered. The search narrows what is
        #: DRAWN; it never narrows what is held, or clearing the box would
        #: have nothing to bring back.
        self.rules = []
        self.chips = []
        #: Guard closures, held for the life of the pane. A Python closure
        #: handed to a .NET event is not necessarily kept alive by the
        #: subscription, and a collected handler is a button that silently
        #: stops working.
        self.guards = []
        #: None until the first measured size arrives, so the first real
        #: SizeChanged always applies a layout rather than matching a guess.
        self.vertical = None
        #: Where this model keeps its rules, once a trip through the external
        #: event has told us. None until then, and for a model never saved.
        self.project_path = None
        self.handler = IsolateHandler()
        self.handler.report = self._show
        self.handler.on_paths = self.on_paths
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
        self.control = _load()
        self._adopt(self.control)
        self.control.SizeChanged += self._on_size
        self._draw()

    def _adopt(self, tree):
        """Take the named controls out of *tree* and wire them up.

        Used for the first build and for every re-skin, so the two cannot
        drift -- a control wired only in one of them is a button that stops
        working the first time somebody presses Refresh.
        """
        self.status = tree.FindName("PaneStatus")
        self.buttons = tree.FindName("PaneButtons")
        self.actions = tree.FindName("PaneActions")
        self.scroll = tree.FindName("PaneScroll")
        self.search = tree.FindName("PaneSearch")
        if self.search is not None:
            self.search.TextChanged += self._guard("Search", self._on_search)
        refresh = tree.FindName("PaneRefresh")
        if refresh is not None:
            refresh.Click += self._guard("Refresh", self._on_refresh)
        clear = tree.FindName("PaneClear")
        if clear is not None:
            clear.Click += self._guard("Clear", self._on_clear)
        if self.scroll is not None:
            # The wheel scrolls whichever axis is live. WPF only ever scrolls
            # the vertical one, so across the top -- where there IS no vertical
            # axis -- the wheel did nothing at all.
            self.scroll.PreviewMouseWheel += self._on_wheel
        return self.status is not None and self.buttons is not None

    def _reskin(self):
        """Re-read pane.xaml into the live control. ``True`` if it took.

        Revit is handed the ``FrameworkElement`` once, at registration, and
        will not take another -- so a pyRevit reload leaves the OLD control on
        screen and an appearance change needs a full Revit restart. That is a
        poor trade for a panel being iterated on, and it is avoidable: Revit
        holds the UserControl, not its contents, so the contents can be
        replaced underneath it.

        The order matters. Names are resolved from the fresh tree BEFORE its
        content is detached, because re-parenting the content does not carry
        its name scope with it and ``FindName`` on the live control would
        return None afterwards. The element references stay valid; only the
        lookup would not.

        Any failure leaves the tree that is already on screen alone. A pane
        showing the previous theme is a blemish; a pane showing nothing is a
        lost tool.
        """
        try:
            fresh = _load()
            old = (self.status, self.buttons, self.actions, self.scroll)
            if not self._adopt(fresh):
                self.status, self.buttons, self.actions, self.scroll = old
                return False
            content = fresh.Content
            fresh.Content = None          # an element may have one parent
            self.control.Resources = fresh.Resources
            self.control.Content = content
            self.vertical = None          # whatever it was, re-decide it
            return True
        except Exception:
            return False

    def reload(self):
        """Everything Refresh does: re-read the pane's own XAML, then the rules.

        Two separate re-reads, and they are separate on purpose -- the first
        build has just parsed the XAML and has no reason to parse it twice.
        """
        self._reskin()
        self._draw()

    def _draw(self):
        """Redraw the buttons from the rules file. Never raises.

        The window writes those files and this reads them -- the two run on
        different engines and share a folder, not a module. They are re-read on
        every refresh rather than cached, so a rule saved in the window is one
        press away from appearing here.

        Both stores, once a trip through the external event has said where the
        project one is. Until then it is the machine store alone, which is the
        honest answer rather than a guess at the model's folder.
        """
        try:
            from anongee_filterrules import store
            self.rules = list(store.load_all(store.machine_path(),
                                             self.project_path,
                                             store.shared_path()))
        except Exception as error:
            self._show("the rules could not be read: {0}".format(error), "error")
            return
        self._paint()

    def _paint(self):
        """Draw the chips for whatever the search box currently allows."""
        from anongee_filterrules import names

        needle = ""
        if self.search is not None:
            needle = names.key(self.search.Text)
        rules = [rule for rule in self.rules
                 if not needle or needle in names.key(rule.name)]

        try:
            chip_style = self.control.TryFindResource(CHIP_STYLE)
            self.buttons.Children.Clear()
            self.chips = []
            for rule in rules:
                button = Button()
                button.Content = rule.name or "(unnamed)"
                if chip_style is not None:
                    button.Style = chip_style
                button.ToolTip = rule.summary()
                button.Tag = rule
                button.Click += self._guard("pressing {0}".format(rule.name),
                                            self._on_rule)
                self.buttons.Children.Add(button)
                self.chips.append(button)
            self._dress_chips()
        except Exception as error:
            self._show("the buttons could not be drawn: {0}".format(error), "error")
            return

        self._on_size(None, None)     # a content swap raises no SizeChanged
        if rules:
            self._show("{0}{1}. Press one to isolate it in the active "
                       "view.".format(
                           "{0} rule(s)".format(len(rules)),
                           " of {0}".format(len(self.rules))
                           if len(rules) != len(self.rules) else ""))
        elif self.rules:
            self._show("No rule matches that search. {0} saved in "
                       "all.".format(len(self.rules)))
        else:
            self._show("No saved rules yet. Build one in Filter View Manager.")

    # -- layout ------------------------------------------------------------

    def _on_size(self, sender, args):
        """Re-lay out when, and only when, the pane changes shape.

        ``SizeChanged`` fires on every drag pixel, so the work is gated on the
        orientation actually flipping. Without that gate a drag rebuilds the
        margins of every chip several hundred times.
        """
        try:
            self._layout(wants_vertical(self.control.ActualWidth,
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

    def _guard(self, what, handler):
        """*handler*, wrapped so a failure on this pane is loud and written.

        The same reasoning as the window's guard: a Python exception inside a
        WPF handler reaches no caller. Here it is worse -- a press that does
        nothing looks exactly like a rule that matched nothing.
        """
        def wrapped(sender, args):
            try:
                handler(sender, args)
            except Exception as error:                 # noqa: BLE001
                import traceback
                from anongee_filterrules import diagnostics
                self._show(diagnostics.failure("PANEL", what, error,
                                               traceback.format_exc()),
                           "error")
        self.guards.append(wrapped)
        return wrapped

    def _on_rule(self, sender, args):
        self.handler.rule = sender.Tag
        self.handler.action = "apply"
        self._show("isolating {0}...".format(sender.Content))
        self.event.Raise()

    def _on_clear(self, sender, args):
        self.handler.action = "clear"
        self.event.Raise()

    def on_paths(self, project_path):
        """Revit's thread, with a document in hand. Redraw if it moved.

        Runs on Revit's main thread, which is also the thread this pane's WPF
        content lives on -- the same reason the status line can be written
        from the handler. A different model, or the first press in a session,
        brings rules that were not on screen a moment ago.
        """
        if project_path == self.project_path:
            return
        self.project_path = project_path
        try:
            self._draw()
        except Exception:
            pass

    def _on_search(self, sender, args):
        """Redraw from what is already held -- no disk, no Revit.

        Narrowing what is DRAWN rather than what is held is the whole point:
        clearing the box brings every rule straight back, and typing never
        costs a file read.
        """
        self._paint()

    def _on_refresh(self, sender, args):
        self.reload()
        # The rules beside the MODEL cannot be read without a document, and a
        # pane has none. This trip is only for the path; on_paths redraws if
        # it turns out to be a different one.
        self.handler.action = "refresh"
        self.event.Raise()

    def _on_wheel(self, sender, args):
        """Send the wheel to the axis that is actually scrolling.

        Down the side the default is already right, so this stands aside and
        lets WPF handle it. Across the top there is no vertical axis at all,
        and WPF's default is to scroll one -- so the wheel did nothing and the
        rules past the fold were reachable only by dragging the scrollbar.

        Shift+wheel is left alone in both orientations: that is the platform's
        own "scroll sideways" and overriding it would be rude.
        """
        if self.vertical or self.scroll is None:
            return
        try:
            if Keyboard.Modifiers != NO_MODIFIER:
                return        # Shift-wheel is the platform's own sideways
            self.scroll.ScrollToHorizontalOffset(
                wheel_step(args.Delta, self.scroll.HorizontalOffset))
            args.Handled = True
        except Exception:
            pass

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
            brush = self.control.TryFindResource(tone_brush(tone))
            if brush is not None:
                self.status.Foreground = brush
        except Exception:
            pass


def _load():
    """Parse pane.xaml into a fresh UserControl."""
    path = os.path.join(HERE, "pane.xaml")
    stream = FileStream(path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(stream)
    finally:
        stream.Close()


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
