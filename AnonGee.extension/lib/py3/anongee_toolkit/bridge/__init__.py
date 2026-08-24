# -*- coding: utf-8 -*-
"""The bridge: how a button in Excel becomes a job Revit runs.

Everything here is pure Python. No Revit, no openpyxl, no WPF — because the
format both ends of the bridge agree on has to be arguable on any machine, and
because one of those ends is IronPython and cannot import this package at all.

``envelope``   the command and result shapes, versioned
``jobs``       where a job lives on disk, from written to answered
``registry``   every command the bridge knows, declared once

The thing worth knowing before reading any of it: **pyRevit loads an extension's
``startup.py`` on IronPython 2.7, and this package is CPython 3.** The HTTP route
therefore cannot call this code. It writes the same files by the same rules, and
what the two ends share is a folder layout rather than a module. That sounds like
a compromise and is the opposite — it collapsed two designed transports into one,
because HTTP became a faster way to write into the outbox rather than a second
path with a second implementation to keep in step.
"""

from anongee_toolkit.bridge import envelope    # noqa: F401
from anongee_toolkit.bridge import jobs        # noqa: F401
from anongee_toolkit.bridge import registry    # noqa: F401

__all__ = ["envelope", "jobs", "registry"]
