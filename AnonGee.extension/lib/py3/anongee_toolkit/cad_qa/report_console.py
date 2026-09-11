# -*- coding: utf-8 -*-
"""The report a person reads: plain lines, no markup.

Plain text rather than anything richer because this has to render identically
in a terminal, in pyRevit's output window and in a pasted email, and the moment
it carries escape codes one of those three shows them as gibberish. The style
follows ``cad2bim/export.py``'s console summary for the same reason -- one
office, one voice.

ORDER IS DELIBERATE: the measurements first, then the findings worst-first.
A reader needs the denominator before the numerator; "12 unmapped layers" means
nothing until you know whether the drawing has 14 layers or 400.
"""

from . import rules
from .findings import SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO

__version__ = "1.0.0"

_MARKER = {SEVERITY_ERROR: "!!", SEVERITY_WARNING: " !", SEVERITY_INFO: "  "}


def format_report(report, guidance=True, width=78):
    """The full report for one drawing as a list of lines."""
    lines = []
    lines.append(report.source)
    lines.append("=" * min(len(report.source), width))
    lines.extend(_stats_lines(report))
    lines.append("")

    if not report.findings:
        lines.append("No findings. Nothing here will stop cad2bim reading "
                     "this drawing.")
        return lines

    counts = report.counts()
    lines.append("{0} Error, {1} Warning, {2} Info".format(
        counts[SEVERITY_ERROR], counts[SEVERITY_WARNING],
        counts[SEVERITY_INFO]))
    lines.append("")

    for finding in report.sorted_findings():
        lines.extend(_finding_lines(finding, guidance=guidance, width=width))
    return lines


def format_batch(reports, width=78):
    """The index for a folder sweep: one line per drawing, worst first."""
    lines = ["{0} drawings checked".format(len(reports)), ""]
    ordered = sorted(reports, key=_batch_key)
    name_width = max([len(r.source) for r in ordered] or [10])
    name_width = min(name_width, 44)
    for report in ordered:
        counts = report.counts()
        lines.append("{0}  {1}  E{2:<3} W{3:<3} I{4:<3}".format(
            _MARKER.get(report.worst, "  "),
            report.source[:name_width].ljust(name_width),
            counts[SEVERITY_ERROR], counts[SEVERITY_WARNING],
            counts[SEVERITY_INFO]))
    return lines


def _batch_key(report):
    """Worst drawings first, then by name. Severity ranks, name breaks ties."""
    order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
    return (order.get(report.worst, 3), report.source)


def _stats_lines(report):
    stats = report.stats
    lines = []
    if not stats.get("records"):
        return ["Nothing was read from this file."]
    lines.append("{0} records on {1} layers · {2} texts · {3} regions".format(
        stats.get("records", 0), stats.get("layers", 0),
        stats.get("texts", 0), stats.get("regions", 0)))
    extent = stats.get("extent_mm")
    if extent:
        lines.append("Extent {0} x {1} mm at {2:g} mm per drawing unit".format(
            extent.get("width"), extent.get("height"), stats.get("unit_mm", 1)))
    by_category = stats.get("by_category") or {}
    if by_category:
        shown = ", ".join("{0} {1}".format(count, name)
                          for name, count in sorted(by_category.items()))
        lines.append("Classified: " + shown)
    return lines


def _finding_lines(finding, guidance=True, width=78):
    marker = _MARKER.get(finding.severity, "  ")
    head = "{0} {1}  {2}".format(marker, finding.rule, finding.message)
    lines = [head]
    if finding.subject:
        lines.append("      layer/subject: {0}".format(finding.subject))
    if finding.examples:
        lines.append("      e.g. {0}".format(", ".join(
            str(example) for example in finding.examples)))
    if finding.where:
        lines.append("      at x={0:.0f} y={1:.0f} mm".format(*finding.where))
    if guidance:
        rule = rules.RULES.get(finding.rule)
        if rule:
            for line in _wrap(rule.guidance, width - 6):
                lines.append("      {0}".format(line))
    lines.append("")
    return lines


def _wrap(text, width):
    """Greedy word wrap. `textwrap` would do, but this keeps the module free of
    surprises about how it treats the long hyphenated tokens in guidance."""
    words = (text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
