# -*- coding: utf-8 -*-
"""What shape the pane is in, and what follows from it. No Revit, no WPF.

Every decision the dockable panel makes about its own layout lives here, and
none of the plumbing that carries it out. The split is not tidiness: it is the
only way any of this gets tested. ``provider.py`` imports ``clr`` at module
scope and cannot be imported on a machine without Revit, which is every machine
that runs the suite -- so a rule that lives in ``provider.py`` can only ever be
checked by reading its source text, and a rule that lives here can be **run**.

``tests/test_filterrules.py`` holds the line with a ceiling: no Revit-coupled
module may carry more logic than the largest tested one. This module exists
because ``provider.py`` crossed it, and the honest answer to crossing it is to
move the thinking out, not to raise the bar.

Same five rules as the rest of ``lib/`` (see ``anongee_filterrules``): 2.7 and
3.12 alike, ``from __future__ import division``, pure ASCII, no ``re``, no
``anongee_toolkit``.
"""

from __future__ import division

#: Below this width the pane is treated as a side dock and lays out as a
#: column. It is a hair wider than the 240-360 a side-docked pane is allowed to
#: be (brand guidelines S12.4) so that dragging one to the edge switches layout
#: BEFORE the buttons start clipping rather than after.
NARROW_WIDTH = 420.0

#: How wide a rule chip may get in the across-the-top layout. A rule may be
#: named anything; without this one long name pushes every other button off the
#: strip. Down the side there is no cap -- the chip fills the column and the
#: label ellipsizes inside it.
CHIP_MAX_WIDTH = 220.0

#: How far one wheel notch scrolls the across-the-top strip. Roughly three
#: chips, which is close to what a notch does to a vertical list.
WHEEL_STEP = 120.0

#: Status tone to the brush that carries it. Checked against pane.xaml by
#: ``tests/test_filterpane_ui.py``, so a renamed brush is a failed test rather
#: than a silently uncoloured status line. The error tone is the LIFTED red:
#: ``BrushErrorRed`` is 2.43:1 on Revit grey (brand guidelines S3.8.6).
TONE_BRUSH = {
    "info": "BrushDarkTextMuted",
    "ok": "BrushSuccessGreenOnDark",
    "error": "BrushErrorRedOnDark",
}

#: The resource key for a saved-rule button. Named here rather than inline in
#: ``provider.py`` so the "every key the code asks for exists in the XAML" gate
#: has one place to read it from.
CHIP_STYLE = "ButtonRuleOnDark"


def wants_vertical(width, height):
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


def wheel_step(delta, offset):
    """Where a wheel notch should leave the horizontal scroll offset.

    WPF's wheel only ever drives the vertical axis. Across the top there is no
    vertical axis, so the wheel did nothing at all and the rules past the fold
    were reachable only by dragging the scrollbar.

    A negative *delta* is a pull toward the user, which everywhere else means
    "further down the list"; here that is further to the right. Clamped at zero
    because a negative offset is not a scroll position.
    """
    moved = offset + (WHEEL_STEP if delta < 0 else -WHEEL_STEP)
    return moved if moved > 0 else 0.0


def tone_brush(tone):
    """The brush key for a status tone, falling back to the quiet one."""
    return TONE_BRUSH.get(tone, TONE_BRUSH["info"])
