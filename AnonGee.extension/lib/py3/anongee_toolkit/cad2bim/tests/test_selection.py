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


class _Combo(object):
    """Stands in for a row's category combo. Identity is what matters."""

    def __init__(self, value=None):
        self.value = value


class WhenASelectedRowChanges(unittest.TestCase):

    def setUp(self):
        self.combos = [_Combo(), _Combo(), _Combo(), _Combo()]

    def rows(self, *selected):
        chosen = set(selected)
        return [(index in chosen, combo)
                for index, combo in enumerate(self.combos)]

    def test_every_other_selected_row_follows(self):
        rows = self.rows(0, 2, 3)
        self.assertEqual(selection.spread(rows, self.combos[0]), [2, 3])

    def test_the_sender_is_never_told_to_change_itself(self):
        rows = self.rows(0, 1)
        self.assertNotIn(0, selection.spread(rows, self.combos[0]))

    def test_unselected_rows_are_left_alone(self):
        rows = self.rows(1, 2)
        self.assertEqual(selection.spread(rows, self.combos[1]), [2])

    def test_a_change_on_an_unselected_row_spreads_to_nothing(self):
        # Editing one row on its own must keep working exactly as it did.
        rows = self.rows(1, 2)
        self.assertEqual(selection.spread(rows, self.combos[0]), [])

    def test_the_only_selected_row_changes_nothing_else(self):
        rows = self.rows(2)
        self.assertEqual(selection.spread(rows, self.combos[2]), [])

    def test_they_come_back_in_table_order(self):
        rows = self.rows(0, 1, 2, 3)
        self.assertEqual(selection.spread(rows, self.combos[2]), [0, 1, 3])

    def test_a_combo_from_another_table_spreads_to_nothing(self):
        rows = self.rows(0, 1)
        self.assertEqual(selection.spread(rows, _Combo()), [])

    def test_rows_that_hold_equal_values_are_still_told_apart(self):
        # Identity, not equality: two layers can share a category and mean
        # different rows.
        same = [_Combo("BEAM"), _Combo("BEAM"), _Combo("BEAM")]
        rows = [(True, same[0]), (True, same[1]), (False, same[2])]
        self.assertEqual(selection.spread(rows, same[1]), [0])

    def test_nothing_at_all_is_not_a_crash(self):
        self.assertEqual(selection.spread([], _Combo()), [])
        self.assertEqual(selection.spread(None, _Combo()), [])


if __name__ == "__main__":
    unittest.main()
