# -*- coding: utf-8 -*-
"""Windows-Explorer selection semantics for the mapping tables (FEAT-13).

The owner: "there should be option to select multiple items just like windows
explorer (using ctrl, shift click etc to select multi) and assign multi select
at one time instead of one at a time, because in test17 i have to manually
assign B-200x500 or etc one at a time which is inefficient though i can also
change the layer names to one singular beam layer but that will defeat our
actual purpose."

His last clause is the requirement, not an aside. Collapsing `B-200x325`,
`B-200x650` and the rest into one beam layer would throw away the sizes the
layer NAMES carry, which `build_beam_segments` reads. The drawing's naming is
data, so the dialog has to cope with many layers rather than the drawing being
flattened to suit the dialog.

WHY THIS IS ITS OWN MODULE. `ui_window` imports `System.Windows` at module
level, so nothing in it can be imported by a test -- only its source can be
pinned, and a pin reads names, not behaviour. That is exactly how the zoom
shipped broken (BUG-29). The rules below are arithmetic on indices with no WPF
in them, so they are unit-tested for real and the window is left with the
wiring alone.

The rules are Explorer's, and they are stated here rather than discovered by a
user: a plain click selects one row and starts a range there; ctrl-click adds or
removes one row and moves the range start to it; shift-click selects everything
between the range start and the clicked row, replacing what was selected;
ctrl-shift-click adds that range to what is already selected.
"""


def click(selected, anchor, index, ctrl=False, shift=False, count=None):
    """(new selection, new anchor) after a click on row `index`.

    `selected` is any iterable of indices and comes back as a SET, so a caller
    may hold it however it likes. `anchor` is where a shift-range measures from
    -- Explorer keeps it at the last plainly-clicked row, not at the last row
    the selection touched, which is what makes a run of shift-clicks re-measure
    from one place instead of creeping.

    `count` is how many rows exist; when given, an index outside it is ignored
    rather than selecting a row that is not there.
    """
    chosen = set(selected or ())
    if index is None:
        return chosen, anchor
    if count is not None and not (0 <= index < count):
        return chosen, anchor

    if shift and anchor is not None:
        span = _span(anchor, index)
        if ctrl:
            return chosen | span, anchor      # add the range, keep the start
        return span, anchor                   # replace with the range
    if ctrl:
        # Toggle, and the range now measures from here: ctrl-clicking a row and
        # then shift-clicking another selects between the two, as it does in
        # Explorer.
        if index in chosen:
            chosen.discard(index)
        else:
            chosen.add(index)
        return chosen, index
    return set([index]), index


def _span(anchor, index):
    """Every index from `anchor` to `index`, either way round, both ends in."""
    low, high = (anchor, index) if anchor <= index else (index, anchor)
    return set(range(low, high + 1))


def select_all(count):
    """Every row, for ctrl-A and the Select-all button."""
    return set(range(max(0, int(count or 0))))


def describe(selected, count):
    """What the bulk bar says about the selection, for a person reading it.

    Names the number because the button acts on rows that may be scrolled out
    of sight: "apply to 14 selected" is a sentence somebody can check before
    pressing it, where a bare "Apply" is a leap.
    """
    chosen = len(set(selected or ()))
    if not chosen:
        return "no rows selected"
    if chosen == 1:
        return "1 row selected"
    if count and chosen >= count:
        return "all {0} rows selected".format(count)
    return "{0} rows selected".format(chosen)


def apply_to(rows, selected, value):
    """[(index, value)] for the rows a bulk assignment should change.

    Only the SELECTED rows, in row order so the caller writes them the way the
    table reads. A row that already holds the value is still listed: the caller
    setting it again costs nothing, and leaving it out would make the count in
    the message disagree with what was done.
    """
    chosen = set(selected or ())
    return [(index, value) for index in range(len(rows or ()))
            if index in chosen]
