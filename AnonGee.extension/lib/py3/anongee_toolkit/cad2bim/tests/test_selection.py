# -*- coding: utf-8 -*-
"""Which mapping rows follow when a selected row's category is changed (FEAT-13).

The owner, after the first attempt: "it should use any selected item dropdown if
one change all the select should also change" — and, on that attempt's selection
handling, "without Ctrl hold i can select multiple which is not good ... i could
not unselect it with ctrl + click".

So the clicking is WPF's now (`SelectionMode="Extended"` over real
ListBoxItems, the way `OneFilterParameter.pushbutton` and this dialog's own
storey table do it) and is not tested here — there is nothing of ours to test in
it. What IS ours is the fan-out, which is the difference between editing one
layer and editing forty.

Standalone (no Revit, no WPF).
"""

import unittest

import _loader


selection = _loader.load("selection")


class WhenASelectedRowChanges(unittest.TestCase):
    """`rows` is [is_selected]; the changed row is named by INDEX.

    Matching the control that raised the event is what the first version did --
    `combo is sender` -- and under pythonnet it never matched: a .NET object
    reaches a callback as a fresh managed wrapper, so identity against the
    stored reference is False every time. The spread found no owner and quietly
    did nothing, which is exactly what the owner reported: "selected value is
    not change for all the all selected item only item changes for which ever
    dropdown is change from".
    """

    def test_every_other_selected_row_follows(self):
        self.assertEqual(selection.spread([True, False, True, True], 0), [2, 3])

    def test_the_owner_is_never_told_to_change_itself(self):
        self.assertNotIn(0, selection.spread([True, True], 0))

    def test_unselected_rows_are_left_alone(self):
        self.assertEqual(selection.spread([False, True, True, False], 1), [2])

    def test_a_change_on_an_unselected_row_spreads_to_nothing(self):
        # Editing one row on its own must keep working exactly as it did.
        self.assertEqual(selection.spread([False, True, True], 0), [])

    def test_the_only_selected_row_changes_nothing_else(self):
        self.assertEqual(selection.spread([False, False, True], 2), [])

    def test_they_come_back_in_table_order(self):
        self.assertEqual(selection.spread([True, True, True, True], 2),
                         [0, 1, 3])

    def test_an_index_that_is_not_a_row_spreads_to_nothing(self):
        self.assertEqual(selection.spread([True, True], 9), [])
        self.assertEqual(selection.spread([True, True], -1), [])
        self.assertEqual(selection.spread([True, True], None), [])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(selection.spread([], 0), [])
        self.assertEqual(selection.spread(None, 0), [])

    def test_every_row_selected_takes_every_other_one(self):
        self.assertEqual(selection.spread([True] * 5, 0), [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
