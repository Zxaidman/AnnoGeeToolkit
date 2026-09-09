# -*- coding: utf-8 -*-
"""Explorer selection semantics for the mapping tables (FEAT-13).

The owner asked for the interaction he already knows -- "just like windows
explorer (using ctrl, shift click etc to select multi)" -- so these hold the
rules Explorer actually follows, not an approximation of them. The anchor is
the part worth testing hardest: a run of shift-clicks must re-measure from the
last PLAIN click, not creep along behind the last thing selected.

Standalone (no Revit, no WPF): `ui_window` cannot be imported by a test at all,
which is why the arithmetic lives in `selection` and only the wiring is pinned.
"""

import unittest

import _loader


selection = _loader.load("selection")


class APlainClick(unittest.TestCase):

    def test_selects_only_that_row(self):
        chosen, anchor = selection.click({0, 1, 2}, 0, 5)
        self.assertEqual(chosen, {5})
        self.assertEqual(anchor, 5)

    def test_on_an_already_selected_row_still_narrows_to_it(self):
        chosen, _anchor = selection.click({3, 4, 5}, 3, 4)
        self.assertEqual(chosen, {4})

    def test_starts_the_range_where_it_landed(self):
        _chosen, anchor = selection.click(set(), None, 7)
        self.assertEqual(anchor, 7)


class CtrlClick(unittest.TestCase):

    def test_adds_a_row_without_losing_the_others(self):
        chosen, _anchor = selection.click({1, 2}, 1, 6, ctrl=True)
        self.assertEqual(chosen, {1, 2, 6})

    def test_clicking_a_selected_row_takes_it_out(self):
        chosen, _anchor = selection.click({1, 2, 6}, 1, 2, ctrl=True)
        self.assertEqual(chosen, {1, 6})

    def test_moves_the_range_start_to_the_row_it_touched(self):
        # Explorer: ctrl-click a row, then shift-click another, and the range
        # runs between those two.
        chosen, anchor = selection.click({0}, 0, 4, ctrl=True)
        self.assertEqual(anchor, 4)
        chosen, _anchor = selection.click(chosen, anchor, 7, shift=True)
        self.assertEqual(chosen, {4, 5, 6, 7})


class ShiftClick(unittest.TestCase):

    def test_takes_everything_between_the_anchor_and_the_row(self):
        chosen, _anchor = selection.click({2}, 2, 5, shift=True)
        self.assertEqual(chosen, {2, 3, 4, 5})

    def test_works_upwards_as_well_as_downwards(self):
        chosen, _anchor = selection.click({5}, 5, 2, shift=True)
        self.assertEqual(chosen, {2, 3, 4, 5})

    def test_replaces_the_selection_rather_than_adding_to_it(self):
        chosen, _anchor = selection.click({9}, 2, 4, shift=True)
        self.assertEqual(chosen, {2, 3, 4})

    def test_a_second_shift_click_remeasures_from_the_same_anchor(self):
        # The creep this guards against: shift to 6, then shift to 4, must give
        # 2..4 and not 2..6 or 4..6.
        chosen, anchor = selection.click({2}, 2, 6, shift=True)
        self.assertEqual(chosen, {2, 3, 4, 5, 6})
        chosen, _anchor = selection.click(chosen, anchor, 4, shift=True)
        self.assertEqual(chosen, {2, 3, 4})

    def test_ctrl_shift_adds_the_range_to_what_was_there(self):
        chosen, _anchor = selection.click({9, 10}, 2, 4, ctrl=True, shift=True)
        self.assertEqual(chosen, {2, 3, 4, 9, 10})

    def test_with_no_anchor_it_behaves_like_a_plain_click(self):
        chosen, anchor = selection.click(set(), None, 3, shift=True)
        self.assertEqual(chosen, {3})
        self.assertEqual(anchor, 3)

    def test_shift_onto_the_anchor_itself_is_just_that_row(self):
        chosen, _anchor = selection.click({1, 2, 3}, 2, 2, shift=True)
        self.assertEqual(chosen, {2})


class RowsThatAreNotThere(unittest.TestCase):

    def test_an_index_past_the_end_changes_nothing(self):
        chosen, anchor = selection.click({1}, 1, 99, count=10)
        self.assertEqual((chosen, anchor), ({1}, 1))

    def test_a_negative_index_changes_nothing(self):
        chosen, anchor = selection.click({1}, 1, -1, count=10)
        self.assertEqual((chosen, anchor), ({1}, 1))

    def test_no_index_at_all_changes_nothing(self):
        chosen, anchor = selection.click({1}, 1, None)
        self.assertEqual((chosen, anchor), ({1}, 1))

    def test_the_selection_comes_back_as_a_set_whatever_went_in(self):
        chosen, _anchor = selection.click([1, 1, 2], 1, 3, ctrl=True)
        self.assertEqual(chosen, {1, 2, 3})


class SelectAll(unittest.TestCase):

    def test_takes_every_row(self):
        self.assertEqual(selection.select_all(4), {0, 1, 2, 3})

    def test_an_empty_table_selects_nothing(self):
        self.assertEqual(selection.select_all(0), set())
        self.assertEqual(selection.select_all(None), set())


class WhatTheBarSays(unittest.TestCase):
    """The button acts on rows that may be scrolled out of sight."""

    def test_nothing_selected_says_so(self):
        self.assertEqual(selection.describe(set(), 10), "no rows selected")

    def test_one_row_is_singular(self):
        self.assertEqual(selection.describe({3}, 10), "1 row selected")

    def test_several_rows_are_counted(self):
        self.assertEqual(selection.describe({1, 2, 3}, 10), "3 rows selected")

    def test_every_row_says_all_of_them(self):
        self.assertEqual(selection.describe({0, 1, 2}, 3), "all 3 rows selected")


class ApplyingOneChoiceToMany(unittest.TestCase):

    def test_only_the_selected_rows_change(self):
        rows = ["a", "b", "c", "d"]
        self.assertEqual(selection.apply_to(rows, {1, 3}, "BEAM"),
                         [(1, "BEAM"), (3, "BEAM")])

    def test_they_come_back_in_table_order(self):
        rows = ["a", "b", "c", "d", "e"]
        got = selection.apply_to(rows, {4, 0, 2}, "SLAB")
        self.assertEqual([index for index, _value in got], [0, 2, 4])

    def test_nothing_selected_changes_nothing(self):
        self.assertEqual(selection.apply_to(["a", "b"], set(), "BEAM"), [])

    def test_a_selection_past_the_end_is_ignored(self):
        self.assertEqual(selection.apply_to(["a"], {0, 9}, "BEAM"),
                         [(0, "BEAM")])


if __name__ == "__main__":
    unittest.main()
