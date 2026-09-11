# -*- coding: utf-8 -*-
"""The catalogue holds together, and the checks only raise rules it declares.

The second of those is the one that matters. A check raising an undeclared id
would produce a finding with no severity, no guidance and no row in the RULES
sheet -- and it would do it silently, on whichever drawing happened to trip it.
This walks the source instead of waiting for that drawing.
"""

import ast
import os
import re
import unittest

import _support                                            # noqa: F401
from cad_qa import rules
from cad_qa.findings import SEVERITIES

_CHECKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "checks")


#: A rule id as it is written in the source: family letter, three digits.
_RULE_ID = re.compile(r"^[LMGS]\d{3}$")


def _raised_rule_ids():
    """Every rule id that appears as a string constant anywhere in checks/.

    NOT just the first argument of a rules.finding(...) call, which is what
    this looked for first and why it missed L002-L005: those are raised from a
    lookup table of (rule_id, category) pairs, so the literal never appears in
    call position. Any constant shaped like a rule id counts -- a check module
    has no other reason to contain one, and a guard that only sees one calling
    style silently stops guarding the moment somebody writes a loop.
    """
    found = set()
    for name in sorted(os.listdir(_CHECKS_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(_CHECKS_DIR, name), "rb") as handle:
            tree = ast.parse(handle.read().decode("utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and _RULE_ID.match(node.value)):
                found.add(node.value)
    return found


class CatalogueTests(unittest.TestCase):

    def test_there_are_rules(self):
        self.assertGreater(len(rules.RULES), 20)

    def test_every_rule_id_matches_its_family(self):
        prefixes = {rules.FAMILY_LAYERS: "L", rules.FAMILY_MARKS: "M",
                    rules.FAMILY_GEOMETRY: "G", rules.FAMILY_STRUCTURE: "S"}
        for rule in rules.catalogue():
            self.assertTrue(rule.rule_id.startswith(prefixes[rule.family]),
                            "{0} is in family {1}".format(rule.rule_id,
                                                          rule.family))

    def test_every_rule_has_a_known_severity(self):
        for rule in rules.catalogue():
            self.assertIn(rule.severity, SEVERITIES, rule.rule_id)

    def test_every_rule_says_what_to_do_about_it(self):
        """A finding that names a problem without a fix starts a conversation."""
        for rule in rules.catalogue():
            self.assertGreater(len(rule.guidance or ""), 40, rule.rule_id)

    def test_declaring_the_same_id_twice_is_refused(self):
        with self.assertRaises(ValueError):
            rules.declare("L001", rules.FAMILY_LAYERS, "dup",
                          rules.SEVERITY_INFO, "x" * 50)

    def test_every_family_has_rules(self):
        for family, family_rules in rules.by_family().items():
            self.assertTrue(family_rules, family)

    def test_a_finding_inherits_the_declared_severity(self):
        self.assertEqual(rules.finding("L003").severity,
                         rules.get("L003").severity)

    def test_a_finding_can_override_the_severity_deliberately(self):
        finding = rules.finding("L001", severity=rules.SEVERITY_ERROR)
        self.assertEqual(finding.severity, rules.SEVERITY_ERROR)

    def test_an_undeclared_id_raises_rather_than_inventing_a_rule(self):
        with self.assertRaises(KeyError):
            rules.finding("Z999")


class ChecksMatchTheCatalogueTests(unittest.TestCase):

    def test_every_rule_the_checks_raise_is_declared(self):
        undeclared = sorted(_raised_rule_ids() - set(rules.RULES))
        self.assertEqual(undeclared, [])

    def test_the_scan_actually_found_rules(self):
        """Guard against the check above passing because it parsed nothing."""
        self.assertGreater(len(_raised_rule_ids()), 15)

    def test_every_declared_rule_is_reachable_from_some_check(self):
        """A rule nothing can raise is documentation pretending to be code.

        G001 is raised by the runner rather than a check module, so it is the
        one expected absence and is named here rather than waved through.
        """
        raised = _raised_rule_ids() | {"G001"}
        unreachable = sorted(set(rules.RULES) - raised)
        self.assertEqual(unreachable, [])


if __name__ == "__main__":
    unittest.main()
