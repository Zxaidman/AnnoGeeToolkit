# -*- coding: utf-8 -*-
"""Run the checks over one drawing, or a folder of them.

A FAILED READ IS A FINDING, NOT A CRASH. Forty drawings arrive a month and they
are swept in a batch; one corrupt file must not take the other thirty-nine with
it. So everything that can go wrong with a file -- missing, not a DXF, damaged
past even ezdxf's recover pass -- comes back as a report carrying one Error,
with the same shape as any other report. The batch keeps going, the JSON still
parses, and the problem is visible in the same place as every other problem.

The one exception is a broken ENVIRONMENT (no ezdxf at all). That is not a fact
about the drawing and reporting it per-drawing would say it forty times, so it
raises and the CLI says it once.
"""

import os

from .checks import FAMILY_CHECKS
from .context import DrawingContext
from .deps import dxf_reader, ezdxf_available
from .findings import Finding, Report, SEVERITY_ERROR

__version__ = "1.0.0"

#: What this tool will read. DWG is deliberately absent: nothing in this
#: project writes back to CAD, so a DWG is converted to DXF once on the way in
#: (ODA File Converter) and every tool downstream reads one format. One reader
#: is what keeps the whole pipeline runnable off Windows and inside CI.
SUPPORTED_SUFFIXES = (".dxf",)


class EnvironmentError_(RuntimeError):
    """The machine cannot read DXF at all. Not a fact about any drawing."""


def require_environment():
    """Raise unless a DXF can actually be read here."""
    if not ezdxf_available():
        raise EnvironmentError_(
            "ezdxf is not importable, so no DXF can be read. Inside Revit the "
            "bundled copy in lib/py3 is used; off Revit, install it with "
            "'pip install ezdxf'.")


def run_file(path, unit_mm=1.0, tolerances=None, layer_overrides=None):
    """Check one drawing. Always returns a :class:`Report`.

    Raises only :class:`EnvironmentError_`, and only when nothing could ever be
    read on this machine.
    """
    require_environment()
    name = os.path.basename(path)

    unsupported = _unsupported_reason(path)
    if unsupported:
        return _failed_report(name, unsupported)

    try:
        result = dxf_reader.read_dxf(path)
    except Exception as error:                      # noqa: BLE001 - see docstring
        return _failed_report(
            name, "the file could not be read: {0}".format(error))

    context = DrawingContext(result, unit_mm=unit_mm, tolerances=tolerances,
                             layer_overrides=layer_overrides)
    return run_context(context)


def run_context(context):
    """Check an already-read drawing. The seam the tests and Revit both use."""
    report = Report(context.source, stats=context.stats())
    for _family, check in FAMILY_CHECKS:
        report.extend(check(context))
    return report


def run_folder(folder, unit_mm=1.0, tolerances=None, recursive=False):
    """Check every supported drawing in `folder`. Returns [Report, ...].

    Sorted by file name so a sweep of the same folder produces the same order
    twice -- a batch whose report order depends on the filesystem cannot be
    diffed between intakes.
    """
    require_environment()
    reports = []
    for path in drawings_in(folder, recursive=recursive):
        reports.append(run_file(path, unit_mm=unit_mm, tolerances=tolerances))
    return reports


def drawings_in(folder, recursive=False):
    """Every supported drawing under `folder`, sorted by path."""
    found = []
    if recursive:
        for root, _folders, files in os.walk(folder):
            for name in files:
                if _is_supported(name):
                    found.append(os.path.join(root, name))
    else:
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and _is_supported(name):
                found.append(path)
    return sorted(found)


def summarise(reports):
    """Roll-up counts across a batch, for the index a sweep prints."""
    totals = {"drawings": len(reports), "Error": 0, "Warning": 0, "Info": 0}
    for report in reports:
        for severity, count in report.counts().items():
            totals[severity] = totals.get(severity, 0) + count
    totals["clean"] = sum(1 for r in reports if not r.findings)
    totals["with_errors"] = sum(1 for r in reports if r.errors)
    return totals


# -- helpers ----------------------------------------------------------------

def _is_supported(name):
    return name.lower().endswith(SUPPORTED_SUFFIXES)


def _unsupported_reason(path):
    """Why this path cannot be checked, or None when it can."""
    if not os.path.exists(path):
        return "no such file"
    if not os.path.isfile(path):
        return "not a file"
    if path.lower().endswith(".dwg"):
        return ("DWG is not read directly. Convert it to DXF first (ODA File "
                "Converter, or SAVEAS in AutoCAD) and check the DXF.")
    if not _is_supported(path):
        return "not a DXF (this tool reads {0})".format(
            ", ".join(SUPPORTED_SUFFIXES))
    if os.path.getsize(path) == 0:
        return "the file is empty"
    return None


def _failed_report(name, reason):
    """A report that carries one Error and no stats. Same shape as any other."""
    report = Report(name, stats={"records": 0, "texts": 0, "regions": 0,
                                 "layers": 0})
    # The reason alone, not the rule title in front of it: "Drawing carries
    # no usable geometry: no such file" says two things and one of them is
    # wrong. G001 is the right id (nothing could be read) and the reason is the
    # whole message.
    report.add(Finding("G001", SEVERITY_ERROR, reason, count=0))
    return report
