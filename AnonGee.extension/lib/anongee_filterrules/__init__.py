# -*- coding: utf-8 -*-
"""Filter View Manager -- the rule engine, shared by both Python engines.

A saved rule is Category > Family > Type > Parameter conditions. Pressing it
temporarily isolates its matches in the active view. This package is everything
about a rule that can be decided without a model open:

    ``values``  what the user typed, what unit it is in, and the operators
    ``names``   Revit's idea of "the same name" -- case and whitespace
    ``rules``   Condition, Rule, RuleSet, and their JSON shape
    ``store``   where rules live on disk, and the reading of them

Later, and NOT in this package until they exist:

    ``revit_query``  collecting and narrowing against a model
    ``revit_apply``  IsolateElementsTemporary and its undo

WHY THIS IS NOT BESIDE THE SCRIPT
---------------------------------
Every other tool here keeps its package inside its ``.pushbutton`` folder.
This one cannot. The modeless window runs on CPython 3.12; the dockable panel
is registered from ``startup.py``, which pyRevit loads on its core engine,
**IronPython 2.7** -- measured, not assumed: ``/anongee/ping`` reported
``"toolkit": {"importable": false}`` from inside it, and it is recorded in
``docs/specs/2026-08-22-excel-revit-platform-architecture.md`` S2a.

pyRevit puts ``<extension>/lib`` on ``sys.path`` for both engines and nothing
below it, so ``lib/`` is the only place a module both halves can import may
live. ``lib/py3`` is CPython-only, which is why ``anongee_toolkit`` is off
limits here.

THE FIVE RULES OF THIS PACKAGE
------------------------------
1. **Runs on Python 2.7 and 3.12 alike.** No f-strings, no annotations, no
   ``yield from``, no keyword-only arguments.
2. **``from __future__ import division`` in every module with arithmetic.**
   ``1/2`` is ``0`` on IronPython. Unit conversion is nothing but division.
3. **Pure ASCII.** A non-ASCII literal is bytes on one engine and text on the
   other. Escapes (``u"\\u00b2"``) instead. Not ``unicode_literals`` -- that
   would change what the .NET interop on the other side receives.
4. **No ``re``, no ``csv``.** Absent from the CPython 3 engine's stripped
   stdlib (brand guidelines S12.9.3).
5. **No ``anongee_toolkit``.** It is CPython-only. Where a helper here proves
   generally useful it is *mirrored* there with a contract test, the way
   ``bridge/jobs.py`` mirrors ``startup.py`` -- never imported across the
   boundary, because it cannot be.

``tests/test_filterrules.py`` enforces all five statically. There is no
IronPython on the machine that runs the suite, so those checks are the only
thing between a 3-only construct here and a panel that fails to load at Revit
start.
"""

#: The one place this tool's version is written. ``script.py``'s ``VERSION``,
#: ``bundle.yaml``'s ``Version:`` line and the newest ``CHANGELOG.md`` heading
#: are all held to it by ``tests/test_filterrules.py``, so the number the
#: window shows is the build actually running.
#:
#: MAJOR  the tool behaves differently on purpose.
#: MINOR  a new capability; everything already saved still works.
#: PATCH  a fix.
#:
#: 0.1.x is the window. 0.2.0 adds the dockable panel -- a NEW CAPABILITY,
#: so MINOR, and everything already saved still works. 0.3.0 gives that
#: panel the design system's new dark surface and a layout for each of the
#: two shapes Revit can dock it in: also MINOR, because the panel does
#: something it could not do before and every saved rule is untouched.
VERSION = "0.3.0"

#: The pure half is imported freely. ``compat``, ``revit_query`` and
#: ``revit_apply`` are NOT listed: they import ``Autodesk.Revit.DB`` at
#: module level, so importing the package must not drag them in on a
#: machine with no Revit -- which is every machine the tests run on.
__all__ = ["values", "names", "rules", "store"]
