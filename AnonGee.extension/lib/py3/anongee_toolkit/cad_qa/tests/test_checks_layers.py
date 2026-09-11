# -*- coding: utf-8 -*-
"""Layer coverage, L001-L009.

Each test starts from ``_support.plan()`` -- a drawing that trips nothing in
this family -- and breaks exactly one thing. When a test fails it therefore
names the rule that broke, not "something in the output changed".
"""

import unittest

import _support
from _support import context, curve, rect, text, rule_ids
from cad_qa.checks import layers


class BaselineTests(unittest.TestCase):

    def test_a_sound_plan_trips_no_layer_rule(self):
        self.assertEqual(rule_ids(layers.check(_support.plan())), [])


class UnmappedTests(unittest.TestCase):

    def test_an_unrecognised_layer_is_reported(self):
        found = layers.check(_support.plan(
            [curve("SOMETHING-ELSE", [(0, 0), (100, 100)], kind="line")]))
        self.assertIn("L001", rule_ids(found))

    def test_the_finding_names_the_layer_and_counts_it(self):
        found = [f for f in layers.check(_support.plan(
            [curve("ZZZ", [(0, 0), (1, 1)], kind="line"),
             curve("ZZZ", [(2, 2), (3, 3)], kind="line")]))
            if f.rule == "L001"]
        self.assertEqual(found[0].subject, "ZZZ")
        self.assertEqual(found[0].count, 2)

    def test_an_annotation_layer_is_not_called_unrecognised(self):
        """L006 says it better, and saying both is the noise this avoids."""
        found = layers.check(_support.plan(
            [curve("S-BEAM-HDLN", [(0, 0), (100, 0)], kind="line")]))
        self.assertNotIn("L001", rule_ids(found))
        self.assertIn("L006", rule_ids(found))

    def test_a_pure_annotation_layer_is_reported_by_neither(self):
        """A-ANNO-DIMS is correctly ignored and is nobody's finding."""
        found = layers.check(_support.plan(
            [curve("A-ANNO-DIMS", [(0, 0), (100, 0)], kind="line")]))
        self.assertEqual([f for f in found if f.rule in ("L001", "L006")], [])

    def test_there_is_no_share_based_escalation(self):
        """A-DETL-THIN holds 64% of test6 and is meant to be ignored."""
        bulk = [curve("A-DETL-THIN", [(i, 0), (i, 10)], kind="line")
                for i in range(500)]
        found = [f for f in layers.check(_support.plan(bulk))
                 if f.rule == "L001"]
        self.assertTrue(found)
        self.assertEqual([f.severity for f in found], ["Warning"])


class MissingCategoryTests(unittest.TestCase):

    def test_no_grid_is_reported_as_a_warning_not_an_error(self):
        found = [f for f in layers.check(context([
            rect("S-COLS", 0, 0, 400, 400)])) if f.rule == "L002"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "Warning")

    def test_no_columns_is_an_error(self):
        found = [f for f in layers.check(context([
            curve("S-GRID", [(0, 0), (9000, 0)], kind="line")]))
            if f.rule == "L003"]
        self.assertEqual(found[0].severity, "Error")

    def test_no_beams_is_reported(self):
        self.assertIn("L004", rule_ids(layers.check(context([
            rect("S-COLS", 0, 0, 400, 400)]))))

    def test_no_floor_layer_is_only_information(self):
        found = [f for f in layers.check(context([
            rect("S-COLS", 0, 0, 400, 400)])) if f.rule == "L005"]
        self.assertEqual(found[0].severity, "Info")


class LabelLayerTests(unittest.TestCase):

    def test_labels_on_no_recognised_layer_are_reported(self):
        found = layers.check(context(
            [rect("S-COLS", 0, 0, 400, 400)],
            [text("RANDOM-LAYER", "C1 400x400", (100, 100))]))
        self.assertIn("L007", rule_ids(found))

    def test_a_drawing_with_no_text_is_not_told_about_label_layers(self):
        """M002 and G001 already cover it; a third voice is noise."""
        found = layers.check(context([rect("S-COLS", 0, 0, 400, 400)]))
        self.assertNotIn("L007", rule_ids(found))


class SingleLayerTests(unittest.TestCase):

    def test_a_drawing_drafted_onto_one_layer_is_an_error(self):
        records = [curve("0", [(i, 0), (i, 100)], kind="line")
                   for i in range(40)]
        found = [f for f in layers.check(context(records)) if f.rule == "L009"]
        self.assertEqual(found[0].severity, "Error")

    def test_a_tiny_fragment_is_not_accused_of_being_unlayered(self):
        found = layers.check(context([curve("0", [(0, 0), (1, 1)], kind="line")]))
        self.assertNotIn("L009", rule_ids(found))


class HatchTests(unittest.TestCase):

    def test_a_hatch_layer_with_no_meaning_is_information(self):
        found = [f for f in layers.check(context(
            [rect("S-COLS", 0, 0, 400, 400)],
            regions=[_support.region("DECOR", [(0, 0), (1, 0), (1, 1)])]))
            if f.rule == "L008"]
        self.assertEqual(found[0].severity, "Info")


if __name__ == "__main__":
    unittest.main()
