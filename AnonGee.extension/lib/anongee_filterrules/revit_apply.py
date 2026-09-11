# -*- coding: utf-8 -*-
"""Showing only what a rule matched, and putting the view back.

``View.IsolateElementsTemporary`` -- the active view, and nothing else.

That choice is CRIT-1's answer and it decides what this tool *is*. Temporary
isolation lives for the Revit session, does not print, does not survive a save,
and is cleared by Revit's own *Reset Temporary Hide/Isolate*. Above all it
leaves **nothing behind**: no ``ParameterFilterElement``, nothing in the
project's Filters list, no trace for a colleague opening the model. A tool that
quietly wrote named filters into a client's project would be a different and
riskier product, and nobody asked for that one.

It also works on **any** parameter, because it is a set of ids rather than a
filter Revit has to understand -- which is why CRIT-2's flag is informational
here rather than a restriction.

This is the only module in the package that opens a transaction.
"""

from __future__ import division

import clr

clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import TemporaryViewMode, Transaction   # noqa: E402

from . import compat

#: The transaction name, and therefore what the undo stack says. Named for the
#: tool so a user scrolling their undo history knows what put it there.
TRANSACTION_NAME = "AnonGee - Filter View Manager"

#: View types that hold no graphics to isolate. Everything else is allowed --
#: Revit isolates in any graphical view, and enumerating the *permitted* ones
#: would quietly refuse a view type added by a later release.
#:
#: Compared as text rather than against ``ViewType`` members, so that a name
#: missing from an older or newer Revit is simply a name that never matches
#: instead of an AttributeError at import time.
_NOT_GRAPHICAL = ("Schedule", "ColumnSchedule", "PanelSchedule", "DrawingSheet",
                  "Legend", "Report", "CostReport", "LoadsReport",
                  "PresureLossReport", "ProjectBrowser", "SystemBrowser",
                  "Internal", "Undefined")


def can_isolate(view):
    """``(True, "")`` if *view* can be isolated, else ``(False, why)``.

    Checked **before** a transaction is opened, so a refusal costs nothing and
    the reason names the view type rather than surfacing a Revit exception.
    ``cad2bim/builders/view_filters.py`` sets the precedent: a view that cannot
    take what a tool is doing is skipped and counted, never a failed run.
    """
    if view is None:
        return (False, "there is no active view")
    try:
        if view.IsTemplate:
            return (False, "{0!r} is a view template".format(view.Name))
    except Exception:
        pass
    try:
        kind = str(view.ViewType)
        if kind in _NOT_GRAPHICAL:
            return (False, "a {0} has no graphics to isolate".format(kind))
    except Exception:
        pass
    return (True, "")


def is_isolated(view):
    """Whether *view* is currently under a temporary hide/isolate."""
    try:
        return bool(view.IsInTemporaryViewMode(
            TemporaryViewMode.TemporaryHideIsolate))
    except Exception:
        return False


def isolate(doc, view, element_ids):
    """Show only *element_ids* in *view*. Returns ``(count, message)``.

    ``count`` is how many elements were isolated; a ``message`` is present only
    when nothing happened, and says why in the words the footer will show.

    **Isolating nothing is refused.** Revit would happily leave the view
    showing an empty sheet of paper, which looks exactly like a broken tool --
    so a rule that matched nothing says so and leaves the view alone
    (``PRD.md`` S6.7).
    """
    allowed, why = can_isolate(view)
    if not allowed:
        return (0, why)

    wanted = list(element_ids or [])
    if not wanted:
        return (0, "nothing matched, so the view is unchanged")

    transaction = Transaction(doc, TRANSACTION_NAME)
    try:
        transaction.Start()
        view.IsolateElementsTemporary(compat.id_list(wanted))
        transaction.Commit()
    except Exception as error:
        # S12.9.4: gated rollback, never an orphaned transaction.
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass
        return (0, "Revit refused the isolate: {0}".format(error))
    return (len(wanted), "")


def isolate_many(doc, pairs):
    """Isolate in several views at once. ``(done, reports)``.

    *pairs* is ``[(view, element_ids)]`` -- the caller works out what matches
    in each view, because that needs ``revit_query`` and this module
    deliberately does not import it.

    *reports* is ``[(view label, count, why-not)]`` for **every** view asked
    about, including the ones that were skipped. A multi-view apply that says
    "done" while quietly doing nothing in four of the eleven views is the
    failure worth designing against: the caller gets a row per view and can
    show it.

    **One transaction for all of them.** Not because it is faster -- because a
    single Ctrl+Z puts every view back. Eleven transactions would need eleven
    undos, and a modeller who applied to a sheet set by mistake would have to
    find that out one press at a time.
    """
    reports = []
    doable = []
    for view, element_ids in pairs or []:
        name = view_label(view)
        allowed, why = can_isolate(view)
        if not allowed:
            reports.append((name, 0, why))
            continue
        wanted = list(element_ids or [])
        if not wanted:
            # Same rule as the single-view isolate: Revit would happily leave
            # a blank sheet of paper, which looks like a broken tool.
            reports.append((name, 0, "nothing matched, so it is unchanged"))
            continue
        doable.append((view, wanted, name))

    if not doable:
        return (0, reports)

    transaction = Transaction(doc, TRANSACTION_NAME)
    try:
        transaction.Start()
        for view, wanted, _name in doable:
            view.IsolateElementsTemporary(compat.id_list(wanted))
        transaction.Commit()
    except Exception as error:
        # S12.9.4: gated rollback, never an orphaned transaction.
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass
        refused = "Revit refused the isolate: {0}".format(error)
        # Every view is reported as untouched, because the rollback means
        # every view IS untouched -- reporting the ones that had already been
        # written inside the transaction would be a lie.
        return (0, reports + [(name, 0, refused) for _v, _w, name in doable])

    for _view, wanted, name in doable:
        reports.append((name, len(wanted), ""))
    return (len(doable), reports)


def clear(doc, view):
    """Put *view* back. Returns ``(True, "")`` or ``(False, why)``.

    ``DisableTemporaryViewMode`` and not a re-isolate of everything: the two
    look alike for one press and diverge on the second, and this is the one
    Revit's own *Reset Temporary Hide/Isolate* does.

    A view that is not isolated is already clear, and saying so is not an
    error -- it is the answer to pressing Clear twice.
    """
    allowed, why = can_isolate(view)
    if not allowed:
        return (False, why)
    if not is_isolated(view):
        return (True, "")

    transaction = Transaction(doc, TRANSACTION_NAME + " (clear)")
    try:
        transaction.Start()
        view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)
        transaction.Commit()
    except Exception as error:
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass
        return (False, "Revit refused to clear the view: {0}".format(error))
    return (True, "")


def view_label(view):
    """``"Level 1 [FloorPlan]"`` -- what the window's status row calls a view."""
    if view is None:
        return "no view"
    try:
        return "{0} [{1}]".format(view.Name, view.ViewType)
    except Exception:
        return "the active view"
