# -*- coding: utf-8 -*-
"""The whole DXF corpus through the whole QA pipeline, against a baseline.

The unit suite proves each rule fires on a drawing built to trip it. It cannot
prove that a change to one rule left the other twenty-seven alone on
twenty-three real drawings -- for that you need the numbers a real corpus
produces, recorded, and re-checked after every edit. This is that leg, and it
deliberately borrows ``cad2bim/tests/_golden.py`` rather than growing a second
baseline mechanism beside it.

WHAT IS FINGERPRINTED is the count per rule per drawing, plus the severity
totals. Not the messages: a reworded message is not a behaviour change and a
baseline that treats it as one gets re-blessed so often it stops being read.

SLOW -- about half a minute, most of it ezdxf parsing the two large drawings.
That is why this is ``regression_*`` and not ``test_*``: the unit suite stays
under a second, and a gate that slows the inner loop stops being run.

    cd cad_qa/tests
    python3 -m unittest regression_corpus
    CAD2BIM_BLESS=1 python3 -m unittest regression_corpus   # re-record

Re-blessing is deliberate and explicit, for the reason _golden.py gives: a
harness that silently updates its own baseline measures nothing at all.
"""

import os
import sys
import unittest

import _support
from cad_qa import runner
from cad_qa.deps import ezdxf_available

_CAD2BIM_TESTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cad2bim", "tests")
if _CAD2BIM_TESTS not in sys.path:
    sys.path.insert(0, _CAD2BIM_TESTS)

import _golden                                              # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_DIR = os.path.join(_HERE, "baselines")
_BASELINE = os.path.join(BASELINE_DIR, "corpus.json")


def _fixtures():
    """Every corpus DXF by file name, discovered rather than listed.

    Discovered for the same reason the cad2bim sweep discovers: a drawing added
    to the corpus should appear in the baseline diff as a new fixture, not be
    silently unmeasured because nobody remembered to add it to a list.
    """
    if not os.path.isdir(_support.FIXTURE_CAD):
        return []
    return sorted(name for name in os.listdir(_support.FIXTURE_CAD)
                  if name.lower().endswith(".dxf"))


def _fingerprint(report):
    """{metric: count} for one drawing -- per rule, plus severity totals."""
    numbers = dict(report.counts())
    for finding in report.findings:
        numbers[finding.rule] = numbers.get(finding.rule, 0) + 1
    numbers["records"] = report.stats.get("records", 0)
    numbers["layers"] = report.stats.get("layers", 0)
    return numbers


#: Measured once per process. Four tests ask for the corpus and reading it is
#: the whole cost of this leg -- doing it four times turned a 16-second gate
#: into a 63-second one, and a slow gate is a gate that stops being run.
_MEASURED = {}


def _measure():
    if not _MEASURED:
        for name in _fixtures():
            report = runner.run_file(os.path.join(_support.FIXTURE_CAD, name))
            _MEASURED[name] = _fingerprint(report)
    return _MEASURED


@unittest.skipUnless(ezdxf_available(),
                     "ezdxf is not importable; the corpus cannot be read")
class CorpusRegressionTests(unittest.TestCase):

    def test_the_corpus_is_there(self):
        """Guard against a green run that measured an empty folder."""
        self.assertGreater(len(_fixtures()), 15, _support.FIXTURE_CAD)

    def test_no_finding_count_moved(self):
        current = _measure()
        baseline = _golden.load(_BASELINE)

        if _golden.blessing() or baseline is None:
            _golden.save(_BASELINE, current)
            if baseline is None:
                self.skipTest("no baseline yet -- recorded {0} drawings"
                              .format(len(current)))
            return

        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "\n".join([""] + moved))

    def test_every_drawing_produced_a_report(self):
        """A drawing that fails to read still reports; none may vanish."""
        current = _measure()
        self.assertEqual(sorted(current), _fixtures())

    def test_errors_stay_rare_on_a_corpus_cad2bim_converts(self):
        """THE CRY-WOLF GUARD, and the reason it is a test.

        These are drawings cad2bim builds from. An Error that fires on many of
        them is not information, it is noise that teaches the reader to skip
        Errors -- which is how a QA tool stops working without anything
        failing. An earlier build flagged 14 of 23; the share is pinned here so
        that regression is caught by the suite rather than by somebody
        eventually ignoring the reports.
        """
        current = _measure()
        with_errors = sum(1 for numbers in current.values()
                          if numbers.get("Error", 0))
        self.assertLessEqual(
            with_errors, len(current) // 4,
            "{0} of {1} corpus drawings report an Error".format(
                with_errors, len(current)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
