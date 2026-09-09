# -*- coding: utf-8 -*-
"""Assemble captures into a finished report. Revit-free, so the whole of the
report's behaviour is testable outside Revit.

The Revit work -- linking, walking geometry, sweeping the document -- happens in
`revit_capture`, which hands this module a plain dict of Captures. Everything
from that point on (matching, judging, laying out sheets, writing files) is
ordinary Python operating on ordinary data. That boundary is deliberate: it is
the difference between a report whose logic is covered by tests and one that can
only be checked by clicking a button in Revit and reading a spreadsheet.
"""

import os
import re
import time

from . import config, findings as findings_module, matching, sheets as sheets_module
from . import __version__


class AuditReport(object):
    """Everything one audit run produced."""

    __slots__ = ("captures", "space", "groups", "verdicts", "findings",
                 "diagnostics", "version", "generated", "dxf_name", "link_name",
                 "model_name", "cad2bim_version", "settings")

    def __init__(self, captures, space, settings=None):
        self.captures = captures
        self.space = space
        self.settings = config.settings(settings)
        self.version = __version__
        self.generated = time.strftime("%Y-%m-%d %H:%M:%S")
        self.groups = []
        self.verdicts = []
        self.findings = []
        self.diagnostics = {}
        self.dxf_name = _source_of(captures, config.STAGE_DXF_RAW,
                                   config.STAGE_DXF_PARSED)
        self.link_name = _source_of(captures, config.STAGE_LINK_RAW,
                                    config.STAGE_LINK_PARSED)
        self.model_name = _source_of(captures, config.STAGE_MODEL)
        intent = captures.get(config.STAGE_INTENT)
        self.cad2bim_version = intent.meta.get("cad2bim_version") if intent else None

    # -- convenience for the console summary --------------------------------
    def counts(self):
        return {stage: len(capture.items)
                for stage, capture in self.captures.items() if capture is not None}

    def severity_counts(self):
        counts = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def verdict_counts(self):
        counts = {}
        for verdict in self.verdicts:
            counts[verdict] = counts.get(verdict, 0) + 1
        return counts

    def to_dict(self, max_points=None):
        """The JSON sidecar's payload: the full data, not the capped sheets."""
        limit = (max_points if max_points is not None
                 else self.settings["max_points_per_item"])
        return {
            "audit_version": self.version,
            "cad2bim_version": self.cad2bim_version,
            "generated": self.generated,
            "sources": {"dxf": self.dxf_name, "link": self.link_name,
                        "model": self.model_name},
            "settings": self.settings,
            "space": dict(self.space.describe()),
            "diagnostics": self.diagnostics,
            "verdict_counts": self.verdict_counts(),
            "severity_counts": self.severity_counts(),
            "findings": [finding.to_dict() for finding in self.findings],
            "reconciliation": self._reconciliation_dicts(),
            "captures": {stage: capture.to_dict(limit)
                         for stage, capture in self.captures.items()
                         if capture is not None},
        }

    def _reconciliation_dicts(self):
        out = []
        for group, verdict in zip(self.groups, self.verdicts):
            out.append({
                "verdict": verdict,
                "category": group.category,
                "level": group.level,
                "anchor_mm": [round(group.anchor[0], 1), round(group.anchor[1], 1)],
                "stages": {stage: group.count(stage) for stage in group.stages()},
                "sizes_mm": {stage: _round_pair(group.size_mm(stage))
                             for stage in group.stages()},
            })
        return out


def build_report(captures, space, settings=None):
    """Match, judge, and return a finished AuditReport."""
    clean = {stage: capture for stage, capture in captures.items()
             if capture is not None}
    report = AuditReport(clean, space, settings)
    groups, diagnostics = matching.build_groups(clean, report.settings)
    verdicts, found = findings_module.evaluate(
        groups, clean, report.settings, space_key=diagnostics["space"])
    report.groups = groups
    report.verdicts = verdicts
    report.findings = found
    report.diagnostics = diagnostics
    return report


def build_sheets(report):
    """The workbook's tables, in tab order."""
    return sheets_module.build(report, report.settings)


def console_lines(report):
    """A short plain-text summary for the pyRevit output window."""
    lines = ["cad2bim audit {0}".format(report.version)]
    for stage in config.STAGES:
        capture = report.captures.get(stage)
        if capture is None:
            continue
        note = "" if not capture.errors else "  ({0} read failures)".format(
            len(capture.errors))
        lines.append("  {0:<28} {1} item(s){2}".format(
            config.STAGE_LABELS[stage], len(capture.items), note))
    lines.append("  matched into {0} candidate member(s) in {1} space".format(
        len(report.groups), report.diagnostics.get("space", "?")))

    severities = report.severity_counts()
    lines.append("  findings: {0} error, {1} warning, {2} info".format(
        severities.get(config.SEVERITY_ERROR, 0),
        severities.get(config.SEVERITY_WARNING, 0),
        severities.get(config.SEVERITY_INFO, 0)))
    for verdict, count in sorted(report.verdict_counts().items()):
        if verdict != config.VERDICT_OK:
            lines.append("    {0:<20} {1}".format(verdict, count))
    return lines


def export_name(dxf_path, captures, extension="xlsx"):
    """Default file name, following cad2bim's own convention.

    cad2bim writes `[version]_[element]_[testN]_[textmode].json`. The audit has
    no single element and no text mode, so the two variable slots carry what
    does vary here: the plan, and which stages were captured. A name like
    `0.1.0_audit_test17_ABD.xlsx` says at a glance that no model was swept.
    """
    stem = os.path.splitext(os.path.basename(dxf_path or ""))[0]
    match = re.search(r"(test|project)\s*-?_?(\d+)", stem, re.IGNORECASE)
    plan = ("{0}{1}".format(match.group(1).lower(), match.group(2)) if match
            else (_slug(stem) or "plan"))
    letters = ""
    for letter, stages in (("A", (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED)),
                           ("B", (config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED)),
                           ("C", (config.STAGE_MODEL,)),
                           ("D", (config.STAGE_INTENT,))):
        if any(captures.get(stage) is not None for stage in stages):
            letters += letter
    return "{0}_audit_{1}_{2}.{3}".format(__version__, plan, letters or "none",
                                          extension)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())[:16]


def _source_of(captures, *stages):
    for stage in stages:
        capture = captures.get(stage)
        if capture is not None and capture.source_name:
            return capture.source_name
    return None


def _round_pair(pair, places=1):
    return None if not pair else [round(float(pair[0]), places),
                                  round(float(pair[1]), places)]
