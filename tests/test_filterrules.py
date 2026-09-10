# -*- coding: utf-8 -*-
"""The Filter View Manager rule core, exercised without Revit.

Four modules under ``AnonGee.extension/lib/anongee_filterrules`` — ``values``,
``names``, ``rules`` and ``store`` — contain everything about a rule that can be
decided without a model open: what the user typed, what it means, whether two
Revit names are the same name, and what a saved rule looks like on disk.

They are also the modules that must run on **two engines**. The window is
CPython 3.12; the dockable panel is registered from ``startup.py``, which pyRevit
loads on IronPython 2.7. So ``SharedCoreTests`` at the bottom is not a style
check — an f-string in one of these files is invisible on every machine that
runs this suite and shows up in Revit as a panel that fails to load at startup.

``AnonGee.extension/lib`` goes on ``sys.path`` here, which is what pyRevit does
for both engines. Note this is ``lib``, not ``lib/py3``: the vendored Windows
wheels ``tests/_rc_loader.py`` warns about are one level further down and stay
off the path.
"""

import ast
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "AnonGee.extension", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from anongee_filterrules import names, rules, store, values   # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# values — what the user typed, and what it means
# ═══════════════════════════════════════════════════════════════════════════

class ParseNumberTests(unittest.TestCase):
    """``parse_number`` is hand-written because this engine has no ``re``."""

    def test_a_plain_integer(self):
        self.assertEqual(values.parse_number("100"), (100.0, ""))

    def test_a_decimal(self):
        self.assertEqual(values.parse_number("100.5"), (100.5, ""))

    def test_a_negative(self):
        self.assertEqual(values.parse_number("-3.5"), (-3.5, ""))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(values.parse_number("  100  "), (100.0, ""))

    def test_a_unit_after_a_space(self):
        self.assertEqual(values.parse_number("100 m2"), (100.0, "m2"))

    def test_a_unit_with_no_space(self):
        self.assertEqual(values.parse_number("3000mm"), (3000.0, "mm"))

    def test_a_superscript_two_is_the_same_as_a_two(self):
        self.assertEqual(values.parse_number(u"100 m²"), (100.0, "m2"))

    def test_sq_m_spellings_all_arrive_at_m2(self):
        for text in ("100 sqm", "100 sq m", "100 sq.m", "100 SQ M"):
            self.assertEqual(values.parse_number(text), (100.0, "m2"), text)

    def test_the_unit_is_case_folded(self):
        self.assertEqual(values.parse_number("3000 MM"), (3000.0, "mm"))

    def test_nothing_at_all(self):
        for text in ("", "   ", None):
            self.assertIsNone(values.parse_number(text), repr(text))

    def test_text_that_is_not_a_number(self):
        self.assertIsNone(values.parse_number("wall"))

    def test_a_unit_with_no_number(self):
        self.assertIsNone(values.parse_number("mm"))

    def test_a_comma_is_refused_rather_than_guessed(self):
        """1,5 is one-and-a-half in Europe and fifteen everywhere else.

        Silently picking one is how a rule ends up meaning something the user
        never typed, so both are refused and the window says why.
        """
        for text in ("1,000", "1,5"):
            self.assertIsNone(values.parse_number(text), text)

    def test_an_unknown_unit_is_kept_so_the_caller_can_complain(self):
        parsed = values.parse_number("100 furlongs")
        self.assertEqual(parsed, (100.0, "furlongs"))
        self.assertFalse(values.is_known_unit("furlongs"))


class UnitTests(unittest.TestCase):
    """Revit stores feet, square feet, cubic feet and radians."""

    def test_no_unit_passes_through_untouched(self):
        self.assertEqual(values.to_internal(100.0, ""), 100.0)

    def test_metres_to_feet(self):
        self.assertAlmostEqual(values.to_internal(1.0, "m"), 3.280839895, 6)

    def test_millimetres_to_feet(self):
        self.assertAlmostEqual(values.to_internal(3000.0, "mm"), 9.842519685, 6)

    def test_square_metres_to_square_feet(self):
        self.assertAlmostEqual(values.to_internal(100.0, "m2"), 1076.391041671, 6)

    def test_cubic_metres_to_cubic_feet(self):
        self.assertAlmostEqual(values.to_internal(1.0, "m3"), 35.314666721, 6)

    def test_degrees_to_radians(self):
        self.assertAlmostEqual(values.to_internal(180.0, "deg"), 3.14159265, 6)

    def test_feet_are_already_internal(self):
        self.assertEqual(values.to_internal(10.0, "ft"), 10.0)

    def test_an_unknown_unit_raises_rather_than_guessing(self):
        self.assertRaises(ValueError, values.to_internal, 1.0, "furlongs")

    def test_every_known_unit_converts(self):
        for unit in values.known_units():
            self.assertIsInstance(values.to_internal(1.0, unit), float, unit)


class OperatorTests(unittest.TestCase):

    def test_every_operator_is_described(self):
        """The window shows these; an operator with no label is a blank row."""
        for key in values.OPERATORS:
            self.assertTrue(values.operator_label(key), key)

    def test_equals_on_text_ignores_case(self):
        self.assertTrue(values.compare("Basic Wall", "equals", "basic wall"))

    def test_equals_on_numbers_allows_for_float_drift(self):
        self.assertTrue(values.compare(100.0000000001, "equals", 100.0))

    def test_not_equals(self):
        self.assertTrue(values.compare("Basic Wall", "not_equals", "Curtain"))
        self.assertFalse(values.compare("Basic Wall", "not_equals", "BASIC WALL"))

    def test_contains_and_not_contains(self):
        self.assertTrue(values.compare("100mm Gypsum Wall", "contains", "gypsum"))
        self.assertTrue(values.compare("100mm Gypsum Wall", "not_contains", "brick"))

    def test_begins_and_ends_with(self):
        self.assertTrue(values.compare("C1 400x400", "begins_with", "c1"))
        self.assertTrue(values.compare("C1 400x400", "ends_with", "400"))

    def test_the_numeric_comparisons(self):
        self.assertTrue(values.compare(150.0, "greater", 100.0))
        self.assertFalse(values.compare(100.0, "greater", 100.0))
        self.assertTrue(values.compare(100.0, "greater_equal", 100.0))
        self.assertTrue(values.compare(50.0, "less", 100.0))
        self.assertTrue(values.compare(100.0, "less_equal", 100.0))

    def test_between_is_inclusive_at_both_ends(self):
        self.assertTrue(values.compare(100.0, "between", (100.0, 200.0)))
        self.assertTrue(values.compare(200.0, "between", (100.0, 200.0)))
        self.assertFalse(values.compare(99.0, "between", (100.0, 200.0)))

    def test_between_does_not_care_which_way_round_the_pair_is(self):
        self.assertTrue(values.compare(150.0, "between", (200.0, 100.0)))

    def test_is_empty_covers_none_and_blank(self):
        for actual in (None, "", "   "):
            self.assertTrue(values.compare(actual, "is_empty", None), repr(actual))
        self.assertFalse(values.compare("x", "is_empty", None))

    def test_is_not_empty(self):
        self.assertTrue(values.compare("x", "is_not_empty", None))
        self.assertFalse(values.compare(None, "is_not_empty", None))

    def test_a_missing_value_never_matches_a_real_comparison(self):
        """A wall with no Comments is not 'Comments = X'. It is also not
        'Comments != X' — it has no Comments to disagree with."""
        for operator in ("equals", "not_equals", "contains", "greater", "less"):
            self.assertFalse(values.compare(None, operator, "x"), operator)

    def test_a_numeric_operator_against_text_does_not_crash(self):
        """The parameter turned out to be a string. Say no, do not raise."""
        self.assertFalse(values.compare("not a number", "greater", 100.0))

    def test_a_number_and_a_numeric_string_still_compare(self):
        """Revit hands back strings for some parameters even when they read
        as numbers; a rule the user wrote as a number must still work."""
        self.assertTrue(values.compare("150", "greater", 100.0))

    def test_an_unknown_operator_raises(self):
        self.assertRaises(ValueError, values.compare, 1, "sideways", 1)

    def test_numeric_operators_are_named_so_the_ui_can_ask_for_a_number(self):
        self.assertIn("greater", values.NUMERIC_OPERATORS)
        self.assertIn("between", values.NUMERIC_OPERATORS)
        self.assertNotIn("contains", values.NUMERIC_OPERATORS)

    def test_operators_taking_no_value_are_named(self):
        self.assertEqual(set(values.VALUELESS_OPERATORS),
                         set(("is_empty", "is_not_empty")))


# ═══════════════════════════════════════════════════════════════════════════
# names — Revit's idea of "the same name"
# ═══════════════════════════════════════════════════════════════════════════

class NameMatchingTests(unittest.TestCase):
    """Revit matches type names case- and whitespace-insensitively.

    ``task_plan.md`` Phase 0.5 records what using ``==`` cost: a duplicate-type
    check that was stricter than Revit's own rule, and *"The name is already in
    use for this element type"* in a live model.
    """

    def test_case_is_ignored(self):
        self.assertTrue(names.same("Basic Wall", "BASIC WALL"))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertTrue(names.same("  Basic Wall ", "Basic Wall"))

    def test_repeated_inner_whitespace_collapses(self):
        self.assertTrue(names.same("Basic  Wall", "Basic Wall"))

    def test_a_tab_is_whitespace_too(self):
        self.assertTrue(names.same("Basic\tWall", "Basic Wall"))

    def test_different_names_stay_different(self):
        self.assertFalse(names.same("Basic Wall", "Curtain Wall"))

    def test_none_matches_nothing_including_none(self):
        self.assertFalse(names.same(None, "Basic Wall"))
        self.assertFalse(names.same(None, None))

    def test_find_returns_the_payload_of_the_matching_row(self):
        rows = [("Basic Wall", 1), ("Curtain Wall", 2)]
        self.assertEqual(names.find(rows, "  basic   wall "), 1)

    def test_find_returns_none_when_nothing_matches(self):
        self.assertIsNone(names.find([("Basic Wall", 1)], "Stacked Wall"))

    def test_key_is_stable_and_usable_as_a_dict_key(self):
        self.assertEqual(names.key("Basic  WALL "), names.key("basic wall"))


class DedupeTests(unittest.TestCase):
    """``dedupe`` is the one loop that ``families``, ``types`` and
    ``parameters`` all used to write out by hand.

    It exists as a tested function because ``parameters`` now reads from three
    sources at once, and merging them was where the bug lived: a model with
    types loaded and nothing placed offered no parameters at all.
    """

    def test_it_keeps_order_of_first_appearance_after_sorting(self):
        self.assertEqual(
            names.dedupe([("Zeta", 1), ("Alpha", 2)]),
            [("Alpha", 2), ("Zeta", 1)])

    def test_a_repeat_is_dropped_and_the_first_payload_wins(self):
        """First source wins, which is what makes source order meaningful."""
        self.assertEqual(
            names.dedupe([("Comments", True), ("comments", False)]),
            [("Comments", True)])

    def test_revits_name_rule_decides_what_is_a_repeat(self):
        self.assertEqual(
            len(names.dedupe([("Base  Level", 1), ("BASE LEVEL", 2)])), 1)

    def test_a_blank_name_is_dropped(self):
        self.assertEqual(names.dedupe([("", 1), ("   ", 2), (None, 3)]), [])

    def test_it_takes_plain_names_as_well_as_pairs(self):
        """``families`` and ``types`` have no payload to carry."""
        self.assertEqual(names.dedupe(["Zeta", "Alpha", "alpha"]),
                         ["Alpha", "Zeta"])

    def test_an_empty_source_is_an_empty_result(self):
        self.assertEqual(names.dedupe([]), [])

    def test_the_three_sources_a_parameter_list_is_built_from(self):
        """Filterable first, then instances, then types -- so the flag from
        the filterable set is the one that survives a name collision."""
        merged = names.dedupe([("Area", True)] + [("Area", False), ("Mark", False)]
                              + [("Type Mark", False)])
        self.assertEqual(merged, [("Area", True), ("Mark", False),
                                  ("Type Mark", False)])


# ═══════════════════════════════════════════════════════════════════════════
# rules — the model
# ═══════════════════════════════════════════════════════════════════════════

def a_condition(**kw):
    fields = {"parameter": "Area", "operator": "greater",
              "value": 100.0, "unit": "m2"}
    fields.update(kw)
    return rules.Condition(**fields)


def a_rule(**kw):
    fields = {"name": "Gypsum walls over 100 m2",
              "categories": ["Walls"],
              "family": "Basic Wall",
              "type_name": "100mm Gypsum Wall",
              "conditions": [a_condition()]}
    fields.update(kw)
    return rules.Rule(**fields)


class ConditionTests(unittest.TestCase):

    def test_it_round_trips_through_a_dict(self):
        original = a_condition()
        self.assertEqual(rules.Condition.from_dict(original.to_dict()).to_dict(),
                         original.to_dict())

    def test_an_unknown_key_in_the_file_is_ignored(self):
        data = a_condition().to_dict()
        data["invented_by_a_later_build"] = 42
        self.assertEqual(rules.Condition.from_dict(data).parameter, "Area")

    def test_a_missing_key_falls_back_rather_than_raising(self):
        self.assertEqual(rules.Condition.from_dict({}).operator, "equals")

    def test_the_filterable_flag_survives_the_round_trip(self):
        condition = a_condition(filterable=False)
        self.assertFalse(rules.Condition.from_dict(condition.to_dict()).filterable)

    def test_it_matches_a_value_in_the_units_it_was_written_in(self):
        """100 m2 is 1076.39 sq ft internally. 1200 sq ft is over it."""
        self.assertTrue(a_condition().matches(1200.0))
        self.assertFalse(a_condition().matches(900.0))

    def test_a_text_condition_needs_no_unit(self):
        condition = a_condition(parameter="Comments", operator="contains",
                                value="hold", unit="")
        self.assertTrue(condition.matches("On hold"))

    def test_a_valueless_operator_ignores_the_value(self):
        condition = a_condition(operator="is_empty", value=None, unit="")
        self.assertTrue(condition.matches(None))

    def test_an_unknown_unit_makes_the_condition_never_match_instead_of_raising(self):
        """A rules file edited by hand should not take the window down."""
        condition = a_condition(unit="furlongs")
        self.assertFalse(condition.matches(1200.0))
        self.assertTrue(condition.problems())


class RuleTests(unittest.TestCase):

    def test_it_round_trips_through_a_dict(self):
        original = a_rule()
        self.assertEqual(rules.Rule.from_dict(original.to_dict()).to_dict(),
                         original.to_dict())

    def test_family_and_type_are_optional(self):
        rule = a_rule(family=None, type_name=None)
        self.assertIsNone(rules.Rule.from_dict(rule.to_dict()).family)

    def test_conditions_are_optional(self):
        rule = a_rule(conditions=[])
        self.assertEqual(rules.Rule.from_dict(rule.to_dict()).conditions, [])

    def test_a_rule_gets_an_id_if_it_is_not_given_one(self):
        self.assertTrue(a_rule().id)

    def test_two_rules_made_in_a_row_get_different_ids(self):
        made = set(a_rule().id for _ in range(50))
        self.assertEqual(len(made), 50)

    def test_the_id_survives_a_rename(self):
        rule = a_rule()
        before = rule.id
        rule.name = "Something else"
        self.assertEqual(rule.id, before)

    def test_match_defaults_to_all(self):
        self.assertEqual(a_rule().match, "all")

    def test_an_unrecognised_match_falls_back_to_all(self):
        self.assertEqual(rules.Rule.from_dict({"match": "sideways"}).match, "all")

    def test_all_means_every_condition(self):
        rule = a_rule(match="all", conditions=[
            a_condition(operator="greater", value=100.0),
            a_condition(operator="less", value=200.0)])
        self.assertTrue(rule.matches_values({"Area": 1500.0}))    # 100-200 m2
        self.assertFalse(rule.matches_values({"Area": 3000.0}))   # over 200 m2

    def test_any_means_at_least_one(self):
        rule = a_rule(match="any", conditions=[
            a_condition(operator="greater", value=1000.0),
            a_condition(operator="less", value=200.0)])
        self.assertTrue(rule.matches_values({"Area": 1500.0}))

    def test_a_rule_with_no_conditions_matches_everything(self):
        """'All the structural columns' is a legitimate rule."""
        self.assertTrue(a_rule(conditions=[]).matches_values({}))

    def test_a_parameter_the_element_does_not_have_is_simply_not_a_match(self):
        self.assertFalse(a_rule().matches_values({}))

    def test_source_is_not_written_to_the_file(self):
        """Where a rule came from is the store's business, not the rule's."""
        rule = a_rule()
        rule.source = "project"
        self.assertNotIn("source", rule.to_dict())


class RuleCascadeTests(unittest.TestCase):
    """``matches_element`` -- the whole cascade below the category.

    The category is settled by the collector, so it is not re-checked here.
    Everything else is name-matched Revit's way and is therefore decidable
    without a model, which is what makes the Revit half thin.
    """

    def test_the_owners_example_end_to_end(self):
        rule = a_rule()          # Walls > Basic Wall > 100mm Gypsum Wall > Area > 100 m2
        self.assertTrue(rule.matches_element(
            "Basic Wall", "100mm Gypsum Wall", {"Area": 1500.0}))

    def test_the_family_must_agree(self):
        self.assertFalse(a_rule().matches_element(
            "Curtain Wall", "100mm Gypsum Wall", {"Area": 1500.0}))

    def test_the_type_must_agree(self):
        self.assertFalse(a_rule().matches_element(
            "Basic Wall", "200mm Blockwork", {"Area": 1500.0}))

    def test_the_conditions_must_agree(self):
        self.assertFalse(a_rule().matches_element(
            "Basic Wall", "100mm Gypsum Wall", {"Area": 500.0}))

    def test_family_and_type_are_matched_revits_way(self):
        self.assertTrue(a_rule().matches_element(
            "BASIC  WALL", "  100mm gypsum wall ", {"Area": 1500.0}))

    def test_no_family_on_the_rule_means_any_family(self):
        rule = a_rule(family=None, type_name=None)
        self.assertTrue(rule.matches_element("Curtain Wall", "Anything",
                                             {"Area": 1500.0}))

    def test_a_rule_naming_a_family_does_not_match_an_element_without_one(self):
        self.assertFalse(a_rule().matches_element(None, None, {"Area": 1500.0}))

    def test_all_the_walls_is_a_rule(self):
        """No family, no type, no conditions -- and that is legitimate."""
        rule = a_rule(family=None, type_name=None, conditions=[])
        self.assertTrue(rule.matches_element("Basic Wall", "Anything", {}))


class ConditionParameterTests(unittest.TestCase):
    """Only the parameters a rule names are ever read off an element."""

    def test_it_lists_what_the_conditions_name(self):
        rule = a_rule(conditions=[a_condition(parameter="Area"),
                                  a_condition(parameter="Comments",
                                              operator="contains",
                                              value="x", unit="")])
        self.assertEqual(rule.condition_parameters(), ["Area", "Comments"])

    def test_a_repeated_parameter_is_listed_once(self):
        rule = a_rule(conditions=[a_condition(operator="greater", value=100.0),
                                  a_condition(operator="less", value=200.0)])
        self.assertEqual(rule.condition_parameters(), ["Area"])

    def test_order_is_kept_so_the_read_is_predictable(self):
        rule = a_rule(conditions=[a_condition(parameter="Z"),
                                  a_condition(parameter="A")])
        self.assertEqual(rule.condition_parameters(), ["Z", "A"])

    def test_a_rule_with_no_conditions_needs_no_parameters_read(self):
        self.assertEqual(a_rule(conditions=[]).condition_parameters(), [])


class SelectTests(unittest.TestCase):
    """``select`` is the pure half of the collector, and where the four-stage
    narrowing of ``ARCHITECTURE.md`` §4 actually gets proved."""

    def rows(self):
        return [
            rules.ElementRow(101, "Basic Wall", "100mm Gypsum Wall", {"Area": 1500.0}),
            rules.ElementRow(102, "Basic Wall", "100mm Gypsum Wall", {"Area": 500.0}),
            rules.ElementRow(103, "Basic Wall", "200mm Blockwork", {"Area": 1500.0}),
            rules.ElementRow(104, "Curtain Wall", "Storefront", {"Area": 1500.0}),
            rules.ElementRow(105, "Basic Wall", "100mm Gypsum Wall", {}),
        ]

    def test_only_the_matching_ids_come_back(self):
        self.assertEqual(rules.select(self.rows(), a_rule()), [101])

    def test_the_order_given_is_the_order_returned(self):
        rule = a_rule(family=None, type_name=None, conditions=[])
        self.assertEqual(rules.select(self.rows(), rule),
                         [101, 102, 103, 104, 105])

    def test_an_element_missing_the_parameter_is_left_out_not_crashed_on(self):
        self.assertNotIn(105, rules.select(self.rows(), a_rule()))

    def test_nothing_matching_is_an_empty_list_not_an_error(self):
        rule = a_rule(type_name="A type this model has never heard of")
        self.assertEqual(rules.select(self.rows(), rule), [])

    def test_a_row_carries_an_int_id_because_a_revit_object_cannot(self):
        """S12.8.7.2 -- Revit objects do not cross to the WPF thread."""
        for row in self.rows():
            self.assertIsInstance(row.id, int)


class RuleValidationTests(unittest.TestCase):
    """``problems()`` returns sentences for a human, and [] means valid."""

    def test_a_good_rule_has_no_problems(self):
        self.assertEqual(a_rule().problems(), [])

    def test_a_rule_needs_a_name(self):
        self.assertTrue(a_rule(name="   ").problems())

    def test_a_rule_needs_at_least_one_category(self):
        self.assertTrue(a_rule(categories=[]).problems())

    def test_a_condition_needs_a_parameter(self):
        self.assertTrue(a_rule(conditions=[a_condition(parameter="")]).problems())

    def test_an_unknown_operator_is_a_problem(self):
        self.assertTrue(a_rule(conditions=[a_condition(operator="sideways")]).problems())

    def test_between_needs_two_numbers(self):
        self.assertTrue(a_rule(conditions=[
            a_condition(operator="between", value=100.0)]).problems())
        self.assertEqual(a_rule(conditions=[
            a_condition(operator="between", value=(100.0, 200.0))]).problems(), [])

    def test_a_numeric_operator_needs_a_number(self):
        self.assertTrue(a_rule(conditions=[
            a_condition(operator="greater", value="wall", unit="")]).problems())

    def test_every_problem_names_the_rule_so_a_list_of_them_reads(self):
        for problem in a_rule(name="  ", categories=[]).problems():
            self.assertTrue(problem.strip())


class RuleSetTests(unittest.TestCase):

    def setUp(self):
        self.set = rules.RuleSet()
        self.first = self.set.add(a_rule(name="First"))
        self.second = self.set.add(a_rule(name="Second"))

    def test_add_appends_and_numbers_the_order(self):
        self.assertEqual([r.name for r in self.set], ["First", "Second"])
        self.assertEqual([r.order for r in self.set], [0, 1])

    def test_find_by_id(self):
        self.assertIs(self.set.find(self.second.id), self.second)

    def test_find_by_an_id_that_is_not_there(self):
        self.assertIsNone(self.set.find("nope"))

    def test_remove(self):
        self.assertTrue(self.set.remove(self.first.id))
        self.assertEqual([r.name for r in self.set], ["Second"])
        self.assertEqual([r.order for r in self.set], [0])

    def test_removing_something_that_is_not_there_says_so(self):
        self.assertFalse(self.set.remove("nope"))

    def test_duplicate_makes_a_new_id_and_a_distinguishable_name(self):
        copy = self.set.duplicate(self.first.id)
        self.assertNotEqual(copy.id, self.first.id)
        self.assertNotEqual(copy.name, self.first.name)
        self.assertEqual(len(self.set), 3)

    def test_duplicating_twice_does_not_collide(self):
        one = self.set.duplicate(self.first.id)
        two = self.set.duplicate(self.first.id)
        self.assertNotEqual(one.name, two.name)

    def test_move_reorders_and_renumbers(self):
        self.set.move(self.second.id, 0)
        self.assertEqual([r.name for r in self.set], ["Second", "First"])
        self.assertEqual([r.order for r in self.set], [0, 1])

    def test_move_clamps_rather_than_raising(self):
        self.set.move(self.first.id, 99)
        self.assertEqual([r.name for r in self.set], ["Second", "First"])

    def test_a_name_may_repeat_because_two_stores_may_both_hold_one(self):
        """Uniqueness is not enforced. The id is what identifies a rule, and a
        machine rule and a project rule of the same name are two rules."""
        self.set.add(a_rule(name="First"))
        self.assertEqual(len(self.set), 3)

    def test_it_round_trips_through_a_list_of_dicts(self):
        restored = rules.RuleSet.from_list(self.set.to_list())
        self.assertEqual([r.name for r in restored], ["First", "Second"])
        self.assertEqual([r.id for r in restored], [self.first.id, self.second.id])

    def test_a_rule_the_file_cannot_describe_is_skipped_not_fatal(self):
        restored = rules.RuleSet.from_list([{"name": "ok", "categories": ["Walls"]},
                                            "this is not a rule", None])
        self.assertEqual(len(restored), 1)

    def test_loading_restores_the_saved_order_not_the_list_order(self):
        data = self.set.to_list()
        data[0]["order"], data[1]["order"] = 1, 0
        self.assertEqual([r.name for r in rules.RuleSet.from_list(data)],
                         ["Second", "First"])


# ═══════════════════════════════════════════════════════════════════════════
# store — the file
# ═══════════════════════════════════════════════════════════════════════════

class StorePathTests(unittest.TestCase):

    def setUp(self):
        self.saved = os.environ.get(store.ENV_OVERRIDE)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop(store.ENV_OVERRIDE, None)
        else:
            os.environ[store.ENV_OVERRIDE] = self.saved

    def test_the_override_wins_which_is_what_makes_this_testable(self):
        os.environ[store.ENV_OVERRIDE] = os.path.join("some", "where")
        self.assertEqual(store.machine_path(),
                         os.path.join("some", "where", store.FILE_NAME))

    def test_the_machine_path_sits_under_the_house_folder(self):
        os.environ.pop(store.ENV_OVERRIDE, None)
        path = store.machine_path()
        self.assertTrue(path.endswith(store.FILE_NAME), path)
        self.assertIn("anongee", path.lower())   # ~/.anongee off Windows

    def test_the_project_store_sits_beside_the_model(self):
        path = store.project_path(os.path.join("P", "Job", "Tower-STR.rvt"))
        self.assertEqual(path, os.path.join("P", "Job", store.PROJECT_DIR_NAME,
                                            store.FILE_NAME))

    def test_every_model_in_one_folder_shares_one_project_store(self):
        """A job is a folder with ARC, STR and MEP in it, and a rule about
        columns is about the job, not about one of the three files."""
        first = store.project_path(os.path.join("P", "Job", "Tower-STR.rvt"))
        second = store.project_path(os.path.join("P", "Job", "Tower-ARC.rvt"))
        self.assertEqual(first, second)

    def test_a_real_windows_path_works_on_this_machine_too(self):
        """``os.path.dirname`` only knows the local separator, so a Windows
        path on POSIX would otherwise read as "never saved" -- a bug that
        could only ever fire in this suite, on the function whose whole point
        is being testable off Windows."""
        path = store.project_path("P:\\2026\\Tower\\Tower-STR.rvt")
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith(os.path.join(store.PROJECT_DIR_NAME,
                                                   store.FILE_NAME)), path)
        self.assertIn("Tower", path)

    def test_a_forward_slash_path_works_as_well(self):
        self.assertEqual(store.project_path("P:/2026/Tower/Tower-STR.rvt"),
                         os.path.join("P:/2026/Tower", store.PROJECT_DIR_NAME,
                                      store.FILE_NAME))

    def test_a_bare_file_name_with_no_folder_has_no_project_store(self):
        self.assertIsNone(store.project_path("Tower-STR.rvt"))

    def test_a_model_that_has_never_been_saved_has_no_project_store(self):
        for model_path in ("", None, "   "):
            self.assertIsNone(store.project_path(model_path), repr(model_path))


class StoreRoundTripTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="anongee-filterrules-")
        self.path = os.path.join(self.folder, store.FILE_NAME)
        self.set = rules.RuleSet()
        self.set.add(a_rule(name="Gypsum walls"))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_save_then_load(self):
        self.assertTrue(store.save(self.set, self.path))
        loaded = store.load(self.path)
        self.assertEqual([r.name for r in loaded], ["Gypsum walls"])

    def test_save_creates_the_folder_it_needs(self):
        nested = os.path.join(self.folder, "AnonGee", store.FILE_NAME)
        self.assertTrue(store.save(self.set, nested))
        self.assertTrue(os.path.isfile(nested))

    def test_the_file_is_readable_json_a_person_can_edit(self):
        store.save(self.set, self.path)
        with io.open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["schema"], store.SCHEMA)
        self.assertEqual(len(data["rules"]), 1)

    def test_the_writing_build_is_recorded_for_support(self):
        store.save(self.set, self.path)
        with io.open(self.path, encoding="utf-8") as handle:
            self.assertTrue(json.load(handle)["version"])

    def test_no_temporary_file_is_left_behind(self):
        store.save(self.set, self.path)
        self.assertEqual(sorted(os.listdir(self.folder)), [store.FILE_NAME])

    def test_a_rule_survives_with_its_id_so_the_panel_keeps_its_button(self):
        original = list(self.set)[0]
        store.save(self.set, self.path)
        self.assertEqual(list(store.load(self.path))[0].id, original.id)

    def test_loading_stamps_where_each_rule_came_from(self):
        store.save(self.set, self.path)
        loaded = store.load(self.path, source="project")
        self.assertEqual(list(loaded)[0].source, "project")


class StoreToleranceTests(unittest.TestCase):
    """Nothing here may fail a run. ``cad2bim/prefs.py``'s rule, unchanged."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="anongee-filterrules-")
        self.path = os.path.join(self.folder, store.FILE_NAME)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def write(self, text):
        with io.open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_a_file_that_is_not_there_reads_as_no_rules(self):
        self.assertEqual(len(store.load(self.path)), 0)

    def test_a_file_of_nonsense_reads_as_no_rules(self):
        self.write(u"{not json at all")
        self.assertEqual(len(store.load(self.path)), 0)

    def test_a_half_written_file_reads_as_no_rules(self):
        self.write(u'{"schema": 1, "rules": [{"name": "half')
        self.assertEqual(len(store.load(self.path)), 0)

    def test_an_empty_file_reads_as_no_rules(self):
        self.write(u"")
        self.assertEqual(len(store.load(self.path)), 0)

    def test_json_of_the_wrong_shape_reads_as_no_rules(self):
        self.write(u'["a", "list", "not", "an", "object"]')
        self.assertEqual(len(store.load(self.path)), 0)

    def test_a_newer_schema_still_gives_up_the_rules_it_understands(self):
        """Schema is a statement of what a file may carry, not a gate."""
        self.write(u'{"schema": 99, "rules": [{"name": "Later",'
                   u' "categories": ["Walls"], "invented": true}]}')
        loaded = store.load(self.path)
        self.assertEqual([r.name for r in loaded], ["Later"])

    def test_a_folder_where_the_file_should_be_reads_as_no_rules(self):
        os.mkdir(self.path)
        self.assertEqual(len(store.load(self.path)), 0)

    def test_a_save_that_cannot_write_reports_instead_of_raising(self):
        target = os.path.join(self.path, store.FILE_NAME)   # self.path is a file
        self.write(u"{}")
        self.assertFalse(store.save(rules.RuleSet(), target))
        self.assertTrue(store.last_error())

    def test_a_successful_save_clears_the_last_error(self):
        blocker = os.path.join(self.folder, "blocker")
        with io.open(blocker, "w", encoding="utf-8") as handle:
            handle.write(u"not a folder")
        self.assertFalse(store.save(rules.RuleSet(),
                                    os.path.join(blocker, "x", store.FILE_NAME)))
        self.assertTrue(store.last_error())
        self.assertTrue(store.save(rules.RuleSet(), self.path))
        self.assertIsNone(store.last_error())

    def test_a_failed_save_leaves_the_previous_file_alone(self):
        good = rules.RuleSet()
        good.add(a_rule(name="Keep me"))
        store.save(good, self.path)
        blocker = os.path.join(self.folder, "blocker")
        with io.open(blocker, "w", encoding="utf-8") as handle:
            handle.write(u"not a folder")
        self.assertFalse(store.save(good, os.path.join(blocker, "x", "y")))
        self.assertEqual([r.name for r in store.load(self.path)], ["Keep me"])


class StoreMergeTests(unittest.TestCase):
    """Machine rules and project rules are both shown, each marked.

    Precedence that picks a winner loses somebody's rule silently, which for a
    tool whose whole point is remembering things is the worst failure it has.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="anongee-filterrules-")
        self.machine = os.path.join(self.folder, "machine.json")
        self.project = os.path.join(self.folder, "project.json")
        mine = rules.RuleSet()
        mine.add(a_rule(name="Mine"))
        theirs = rules.RuleSet()
        theirs.add(a_rule(name="Theirs"))
        store.save(mine, self.machine)
        store.save(theirs, self.project)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_both_stores_appear(self):
        merged = store.load_all(self.machine, self.project)
        self.assertEqual(sorted(r.name for r in merged), ["Mine", "Theirs"])

    def test_each_rule_knows_which_store_it_came_from(self):
        merged = store.load_all(self.machine, self.project)
        self.assertEqual(dict((r.name, r.source) for r in merged),
                         {"Mine": store.MACHINE, "Theirs": store.PROJECT})

    def test_the_same_name_in_both_stores_gives_two_rules_not_one(self):
        clash = rules.RuleSet()
        clash.add(a_rule(name="Mine"))
        store.save(clash, self.project)
        merged = store.load_all(self.machine, self.project)
        self.assertEqual(len(merged), 2)
        self.assertEqual(sorted(r.source for r in merged),
                         [store.MACHINE, store.PROJECT])

    def test_no_project_store_is_the_ordinary_case_not_an_error(self):
        merged = store.load_all(self.machine, None)
        self.assertEqual([r.name for r in merged], ["Mine"])

    def test_machine_rules_come_first(self):
        merged = store.load_all(self.machine, self.project)
        self.assertEqual([r.source for r in merged], [store.MACHINE, store.PROJECT])


# ═══════════════════════════════════════════════════════════════════════════
# The core has to run on IronPython 2.7 as well, and nothing else can say so
# ═══════════════════════════════════════════════════════════════════════════

#: Nodes the CPython 3 parser accepts and IronPython 2.7 does not.
_PY3_ONLY = {
    "JoinedStr": "an f-string",
    "FormattedValue": "an f-string",
    "AnnAssign": "a variable annotation",
    "AsyncFunctionDef": "async def",
    "Await": "await",
    "AsyncFor": "async for",
    "AsyncWith": "async with",
    "NamedExpr": "the walrus operator",
    "Nonlocal": "nonlocal",
    "YieldFrom": "yield from",
    "Match": "a match statement",
    "MatMult": "the @ operator",
}


#: The modules that decide things. No Revit in any of them, which is why every
#: test above this line exists at all.
PURE = ("__init__.py", "values.py", "names.py", "rules.py", "store.py")

#: The modules that fetch and write. They import ``Autodesk.Revit.DB``, so they
#: cannot be imported on this machine and only the static checks reach them --
#: which is the reason they are kept as thin as they are.
REVIT = ("compat.py", "revit_query.py", "revit_apply.py")


def _core_folder():
    return os.path.join(_LIB, "anongee_filterrules")


def core_modules():
    """Every module in the package, Revit-touching ones included."""
    folder = _core_folder()
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)
                  if name.endswith(".py"))


def pure_modules():
    return [os.path.join(_core_folder(), name) for name in PURE]


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _statements(path):
    """Executable statements in a module — docstrings and comments are free."""
    return sum(1 for node in ast.walk(ast.parse(_read(path)))
               if isinstance(node, ast.stmt))


class SharedCoreTests(unittest.TestCase):
    """The dual-engine contract, checked statically.

    There is no IronPython on the machine running this suite, so these are the
    only thing standing between a Python-3-only construct in the core and a
    dockable panel that fails to load when Revit starts — a failure that
    reproduces on nobody's development machine.

    ``ARCHITECTURE.md`` §2.1 is why the core is dual-engine at all: the window
    is CPython, the panel is registered from ``startup.py`` on IronPython 2.7,
    and one rule engine is worth more than two that drift.
    """

    def test_there_are_modules_to_check(self):
        self.assertGreaterEqual(len(core_modules()), 4)

    def test_no_module_uses_python_3_only_syntax(self):
        problems = []
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                found = _PY3_ONLY.get(type(node).__name__)
                if found:
                    problems.append("{0}:{1}: {2}".format(
                        os.path.basename(path), getattr(node, "lineno", "?"),
                        found))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_no_starred_assignment_target(self):
        """``a, *rest = x`` is 3-only. ``f(*args)`` is not, and is everywhere."""
        problems = []
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if not isinstance(node, (ast.Assign, ast.For)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for inner in ast.walk(target):
                        if isinstance(inner, ast.Starred):
                            problems.append("{0}:{1}".format(
                                os.path.basename(path), node.lineno))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_no_function_carries_an_annotation(self):
        problems = []
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if not isinstance(node, ast.FunctionDef):
                    continue
                annotated = [a for a in node.args.args if a.annotation]
                if annotated or node.returns:
                    problems.append("{0}: {1}()".format(
                        os.path.basename(path), node.name))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_no_signature_uses_keyword_only_arguments(self):
        problems = []
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if isinstance(node, ast.FunctionDef) and node.args.kwonlyargs:
                    problems.append("{0}: {1}()".format(
                        os.path.basename(path), node.name))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_every_module_imports_true_division(self):
        """``1/2`` is 0 on IronPython 2.7 and 0.5 here. Unit conversion is
        nothing but division, so this is the difference between a rule that
        matches and one that silently never does."""
        for path in core_modules():
            source = _read(path)
            if source.strip().endswith('"""') and "def " not in source:
                continue                       # a docstring-only __init__
            self.assertIn("from __future__ import division", source,
                          os.path.basename(path))

    def test_no_module_imports_unicode_literals(self):
        """It would make every bare literal unicode, which changes what the
        .NET interop on the other engine receives. Escapes are used instead.

        Checked through the AST, not the source text -- a docstring that
        explains the rule is not a breach of it.
        """
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    self.assertNotIn("unicode_literals",
                                     [a.name for a in node.names],
                                     os.path.basename(path))

    def test_every_module_is_pure_ascii(self):
        """A non-ASCII literal is bytes on one engine and text on the other.

        The rest of this repository writes unicode freely; the core cannot, so
        it uses escapes (``u"\\u00b2"``) and plain ASCII prose. One rule, and it
        removes the whole class of bug.
        """
        for path in core_modules():
            source = _read(path)
            for number, line in enumerate(source.splitlines(), 1):
                try:
                    line.encode("ascii")
                except UnicodeEncodeError:
                    self.fail("{0}:{1} is not ASCII: {2!r}".format(
                        os.path.basename(path), number, line))

    def test_the_core_imports_nothing_the_engine_does_not_have(self):
        """``re`` and ``csv`` are absent from the CPython 3 engine (S12.9.3)."""
        banned = ("re", "csv")
        problems = []
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if isinstance(node, ast.Import):
                    found = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    found = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in found:
                    if name in banned:
                        problems.append("{0} imports {1}".format(
                            os.path.basename(path), name))
        self.assertEqual(problems, [], "; ".join(problems))

    def test_the_core_never_imports_the_cpython_toolkit(self):
        """``anongee_toolkit`` lives in lib/py3 and IronPython cannot see it.

        The window uses it freely; the core may not. ``ARCHITECTURE.md`` S2.1.
        """
        for path in core_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if isinstance(node, ast.Import):
                    found = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    found = [node.module or ""]
                else:
                    continue
                for name in found:
                    self.assertFalse(name.startswith("anongee_toolkit"),
                                     "{0} imports {1}".format(
                                         os.path.basename(path), name))

    def test_every_module_is_accounted_for(self):
        """A new module is pure or it is not, and somebody has to say which."""
        self.assertEqual(sorted(os.path.basename(p) for p in core_modules()),
                         sorted(PURE + REVIT))

    def test_the_pure_core_never_imports_revit(self):
        """These five are what makes this suite possible at all.

        Through the AST, not the source text: a docstring that explains why
        the rule exists is not a breach of it.
        """
        for path in pure_modules():
            for node in ast.walk(ast.parse(_read(path))):
                if isinstance(node, ast.Import):
                    found = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    found = [node.module or ""]
                else:
                    continue
                for name in found:
                    self.assertFalse(
                        name == "clr" or name.startswith("Autodesk")
                        or name.startswith("System") or name.startswith("pyrevit"),
                        "{0} imports {1}".format(os.path.basename(path), name))

    def test_the_revit_half_imports_revit_and_not_pyrevit(self):
        """``pyrevit.*`` crashes CPython 3 in event callbacks (S12.8.4), and
        does not exist on the engine the panel runs on either."""
        for name in REVIT:
            source = _read(os.path.join(_core_folder(), name))
            self.assertNotIn("from pyrevit", source, name)
            self.assertNotIn("import pyrevit", source, name)

    def test_the_revit_half_does_no_comparing(self):
        """``values`` is the comparison engine, and it belongs above this line.

        The Revit modules fetch facts and write to a view. The moment one of
        them imports ``values``, a decision has moved into the half no test on
        this machine can reach — which is the exact drift the split exists to
        prevent.
        """
        for name in REVIT:
            for node in ast.walk(ast.parse(_read(os.path.join(_core_folder(),
                                                              name)))):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("values", [a.name for a in node.names],
                                     "{0} imports values".format(name))

    def test_no_revit_module_carries_more_logic_than_the_biggest_tested_one(self):
        """A ceiling with a reason behind it, counted in statements rather than
        lines so that documentation is free and code is not."""
        biggest = max(_statements(path) for path in pure_modules())
        for name in REVIT:
            found = _statements(os.path.join(_core_folder(), name))
            self.assertLess(found, biggest,
                            "{0} has {1} statements; the largest tested module "
                            "has {2}".format(name, found, biggest))

    def test_the_version_is_semantic(self):
        import anongee_filterrules
        parts = anongee_filterrules.VERSION.split(".")
        self.assertEqual(len(parts), 3, anongee_filterrules.VERSION)
        for part in parts:
            self.assertTrue(part.isdigit(), anongee_filterrules.VERSION)

    def test_the_version_agrees_with_the_bundle_and_the_changelog(self):
        """Four copies of one number, held together so they cannot drift.

        The same check ``tests/test_autolevel_ui.py`` runs for Auto Level
        Manager, and the reason the tool's window can be trusted to say which
        build is actually running.
        """
        import anongee_filterrules
        version = anongee_filterrules.VERSION
        button = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab",
                              "Dev.panel",
                              "FilterViewManager.pushbutton")

        # The script does not RE-DECLARE the number -- it imports it, which is
        # the stronger property: three copies to keep in step instead of four,
        # and the window header cannot drift from the package at all.
        script = _read(os.path.join(button, "script.py"))
        self.assertIn("from anongee_filterrules import VERSION", script)
        self.assertNotIn('VERSION = "', script)

        bundle = _read(os.path.join(button, "bundle.yaml"))
        self.assertIn("Version: {0}".format(version), bundle)

        changelog = _read(os.path.join(button, "CHANGELOG.md"))
        headings = [line[3:].strip() for line in changelog.splitlines()
                    if line.startswith("## ")]
        self.assertTrue(headings, "no version headings in CHANGELOG.md")
        self.assertTrue(headings[0].startswith(version),
                        "CHANGELOG leads with {0!r}, core says {1}".format(
                            headings[0], version))


if __name__ == "__main__":                                    # pragma: no cover
    unittest.main(verbosity=2)
