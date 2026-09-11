# -*- coding: utf-8 -*-
"""The package README against the package.

The rulebook exists twice -- in ``rules.py`` where it runs, and in README.md
where it is read -- and the second copy is the one that silently goes stale.
This connects them, the same way ``tests/test_repo_docs.py`` connects the
ribbon to the root README.
"""

import io
import os
import unittest

import _support                                            # noqa: F401
from cad_qa import __version__, rules

_README = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "README.md")


def _read():
    with io.open(_README, encoding="utf-8") as handle:
        return handle.read()


class ReadmeTests(unittest.TestCase):

    def test_the_readme_exists(self):
        self.assertTrue(os.path.isfile(_README))

    def test_every_rule_is_documented(self):
        text = _read()
        missing = [rule.rule_id for rule in rules.catalogue()
                   if rule.rule_id not in text]
        self.assertEqual(missing, [])

    def test_every_rule_is_documented_at_its_real_severity(self):
        """A table that says Warning where the code says Error is worse than
        no table: it is read, believed, and wrong."""
        text = _read()
        wrong = []
        for rule in rules.catalogue():
            row = "| `{0}` | {1} |".format(rule.rule_id, rule.severity)
            if row not in text:
                wrong.append(rule.rule_id)
        self.assertEqual(wrong, [])

    def test_the_readme_states_the_current_version(self):
        self.assertIn(__version__, _read())

    def test_no_rule_id_is_documented_that_does_not_exist(self):
        """A retired rule left in the table sends somebody looking for it."""
        import re
        documented = set(re.findall(r"\| `([LMGS]\d{3})` \|", _read()))
        self.assertEqual(sorted(documented - set(rules.RULES)), [])

    def test_the_scan_found_the_table(self):
        """Guard against the two checks above passing on an empty match."""
        import re
        self.assertGreater(len(re.findall(r"\| `([LMGS]\d{3})` \|", _read())),
                           20)


if __name__ == "__main__":
    unittest.main()
