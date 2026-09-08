#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all three regression legs and say, in one line, whether anything moved.

    cd cad2bim/tests
    python3 run_regressions.py                 # check against the baselines
    python3 run_regressions.py --bless         # re-record them

This is the command to run before shipping a release. The unit suite
(`python3 -m unittest discover -s . -p "test_*.py"`) stays under a second and is
the inner loop; these three take about three minutes between them and are the
gate. Keeping them apart is deliberate -- a gate nobody runs because it makes
the inner loop slow is a gate that does not exist, which is how the last set
ended up in a scratchpad and got lost.

Exit code 0 when every leg matches its baseline, 1 when anything moved or a leg
could not run.
"""

import os
import sys
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Each leg is (name, module, what it counts). The COUNT IS MEASURED, not typed:
# these were once written into the label by hand and every one of them had gone
# stale -- the screen said 29 archived exports, 17 fixture drawings and 4 storey
# stacks while the legs were actually replaying 31, 22 and 7. A gate that
# misreports its own corpus size is a gate whose green line means less than it
# claims, so the size is now read off the corpus at print time and cannot drift
# again. `None` means the leg has nothing countable and prints no size.
LEGS = (
    ("slab fingerprints", "regression_slab_fingerprints",
     ("_corpus", "archived exports")),
    ("DXF sweep", "regression_dxf_sweep",
     ("_fixtures", "fixture drawings")),
    ("storey replay", "regression_storeys",
     ("_multi_storey_corpus", "storey stacks")),
)

_LABEL_WIDTH = 18


def _leg_title(name, module_name, counts):
    """"DXF sweep          (22 fixture drawings)" -- with the 22 counted now.

    Never raises. A label is a label: if the corpus cannot be counted (the
    archive is not on this machine, the helper was renamed) the leg still runs
    and still reports, it just reports without a size rather than dying before
    the measurement everybody actually came for.
    """
    padded = name.ljust(_LABEL_WIDTH)
    if not counts:
        return padded
    helper, noun = counts
    try:
        module = __import__(module_name)
        size = len(getattr(module, helper)())
    except Exception:
        return padded
    return "{0} ({1} {2})".format(padded, size, noun)


_CAP = 60


def _moved_lines(trace, cap=_CAP):
    """EVERY number a leg says moved, not just the last one.

    This printed `trace.splitlines()[-1]` and nothing else, which is one line of
    a message that carries one line PER MOVED NUMBER. A run that moved eight
    numbers showed the eighth; the seven above it were in the traceback and
    never reached the screen -- and the whole point of the gate is that a moved
    number is read and attributed before it is blessed. Caught when a sweep run
    reported `foundation_profiles: 0 -> 73` alone while the failure itself held
    `foundation_planned: 0 -> 73` above it.

    Each leg's message is "<what> moved:" and then the lines, so the marker is
    the same in all three. Anything else -- an error rather than a failure, a
    message this never anticipated -- still shows its last line, which is what
    it always did.
    """
    body = trace.strip()
    marker = " moved:\n"
    if marker not in body:
        last = body.splitlines()
        return [last[-1]] if last else []
    lines = [line.strip()
             for line in body.split(marker, 1)[1].splitlines()
             if line.strip()]
    if len(lines) > cap:
        hidden = len(lines) - cap
        lines = lines[:cap] + ["... and {0} more".format(hidden)]
    return lines


def main(argv):
    if "--bless" in argv:
        os.environ["CAD2BIM_BLESS"] = "1"
        print("RE-RECORDING baselines (CAD2BIM_BLESS=1)\n")

    loader = unittest.TestLoader()
    failed = []
    written = []
    for name, module, counts in LEGS:
        title = _leg_title(name, module, counts)
        started = time.time()
        suite = loader.loadTestsFromName(module)
        with open(os.devnull, "w") as quiet:
            result = unittest.TextTestRunner(verbosity=0, stream=quiet).run(suite)
        elapsed = time.time() - started
        if result.wasSuccessful() and not result.skipped:
            print("  ok       {0}   {1:.0f}s".format(title, elapsed))
        elif result.wasSuccessful():
            written.append(title)
            print("  written  {0}   {1:.0f}s".format(title, elapsed))
            for _test, reason in result.skipped:
                print("           {0}".format(reason))
        else:
            failed.append(title)
            print("  MOVED    {0}   {1:.0f}s".format(title, elapsed))
            for _test, trace in result.failures + result.errors:
                for line in _moved_lines(trace):
                    print("           " + line[:200])

    print()
    if failed:
        print("{0} of {1} legs moved. Read the diff above, decide whether the "
              "change was intended, then --bless if it was."
              .format(len(failed), len(LEGS)))
        return 1
    if written:
        # A leg that WROTE its baseline checked nothing. Saying "all legs match"
        # here would be the exact failure this harness exists to prevent: a
        # green line that means "not measured".
        print("{0} of {1} legs wrote a baseline and checked nothing. Run again "
              "with no flags to check against them."
              .format(len(written), len(LEGS)))
        return 0
    print("all {0} legs match their baselines.".format(len(LEGS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
