# -*- coding: utf-8 -*-
"""cad_qa -- check a structural DXF BEFORE converting it with cad2bim.

Utility 1 of the BIM automation suite. It reads a drawing the same way cad2bim
reads it, using cad2bim's own reader and classifier, and reports every place
that reading is going to produce a wrong or incomplete model. It writes
nothing, changes nothing, and blocks nothing: the point is that a bad drawing
is cheapest to find out about before an hour has been spent converting it.

    from anongee_toolkit import cad_qa
    report = cad_qa.run_file("plan.dxf")
    print(report.worst, report.counts())

or from a terminal, with no Revit anywhere::

    python -m cad_qa plan.dxf
    python -m cad_qa /intake/2026-09 --xlsx qa.xlsx

WHAT IT IS NOT. It is not a drafting-standards checker and says nothing about
whether a drawing is well drafted -- only whether cad2bim will misread it.
Those are different claims, and a tool that mixes them is one nobody trusts.

Layout::

    findings.py      Finding / Report -- the severity model
    rules.py         THE RULEBOOK: every rule, its severity and its fix
    context.py       one drawing, read and classified once
    checks/          the four families, each a pure function of a context
    runner.py        one file or a folder -> Report(s)
    report_*.py      console, JSON (the contract) and .xlsx
    cli.py           the command line
    deps.py          the one place that knows cad2bim has two import names
"""

__version__ = "1.0.0"
__author__ = "AnonGee"

from .findings import (Finding, Report, SEVERITY_ERROR, SEVERITY_WARNING,
                       SEVERITY_INFO)
from .runner import run_file, run_folder, run_context, summarise, drawings_in

__all__ = [
    "Finding", "Report",
    "SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_INFO",
    "run_file", "run_folder", "run_context", "summarise", "drawings_in",
    "__version__",
]
