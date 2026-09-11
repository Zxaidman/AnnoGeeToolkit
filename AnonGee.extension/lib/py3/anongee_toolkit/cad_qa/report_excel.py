# -*- coding: utf-8 -*-
"""The report that goes in a folder with the job.

openpyxl, NOT ``anongee_toolkit/io/excel.py``. That module drives Excel over
COM, which needs Excel installed and Windows under it; this tool has to run on
a build machine and in a batch sweep with no Excel anywhere. openpyxl is
already vendored in lib/py3 (3.1.5), is pure Python, and writes the same .xlsx
either way -- and ``bridge/excel/build_workbook.py`` already sets the
precedent for using it to build a workbook offline.

IMPORTED LAZILY. A missing openpyxl must not stop the JSON and the console
report being written: the Excel sheet is the nice-to-have of the three, and a
tool that refuses to run at all because its third output format is unavailable
has its priorities backwards.

Three sheets, because they answer three different questions:
    SUMMARY   one row per drawing -- "which of these forty needs attention"
    FINDINGS  one row per finding -- "what is wrong with this one"
    RULES     the catalogue -- "what does L006 even mean", answered in the file
              rather than in a document somebody has to be sent
"""

from . import rules
from .findings import SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO

__version__ = "1.0.0"

SUMMARY_HEADERS = ("Drawing", "Worst", "Errors", "Warnings", "Info",
                   "Records", "Layers", "Texts")
FINDING_HEADERS = ("Drawing", "Rule", "Severity", "Family", "Message",
                   "Subject", "Count", "Examples", "X (mm)", "Y (mm)",
                   "What to do")
RULE_HEADERS = ("Rule", "Family", "Title", "Default severity", "Guidance")

#: Solid fills, by severity. Muted on purpose -- a sheet where every other row
#: is a warning should still be readable, and saturated reds make it a sign
#: nobody looks at twice.
_FILLS = {
    SEVERITY_ERROR: "FFF0C4C4",
    SEVERITY_WARNING: "FFF6E2B8",
    SEVERITY_INFO: "FFE4E8EC",
}

_HEADER_FILL = "FF2F3A45"
_HEADER_FONT = "FFFFFFFF"


class ExcelUnavailable(RuntimeError):
    """openpyxl could not be imported. The other two formats still work."""


def _openpyxl():
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as error:
        raise ExcelUnavailable(
            "openpyxl is not importable, so no .xlsx can be written "
            "({0}). The JSON and console reports are unaffected.".format(
                error))
    return openpyxl, Alignment, Font, PatternFill


def write_workbook(path, reports):
    """Write SUMMARY / FINDINGS / RULES for `reports`. Returns the path."""
    openpyxl, Alignment, Font, PatternFill = _openpyxl()

    book = openpyxl.Workbook()
    summary = book.active
    summary.title = "SUMMARY"
    _write_summary(summary, reports, Alignment, Font, PatternFill)

    findings = book.create_sheet("FINDINGS")
    _write_findings(findings, reports, Alignment, Font, PatternFill)

    catalogue = book.create_sheet("RULES")
    _write_rules(catalogue, Alignment, Font, PatternFill)

    book.save(path)
    return path


def _write_summary(sheet, reports, Alignment, Font, PatternFill):
    _header(sheet, SUMMARY_HEADERS, Alignment, Font, PatternFill)
    for report in sorted(reports, key=lambda r: r.source):
        counts = report.counts()
        stats = report.stats
        row = (report.source, report.worst or "clean",
               counts[SEVERITY_ERROR], counts[SEVERITY_WARNING],
               counts[SEVERITY_INFO], stats.get("records", 0),
               stats.get("layers", 0), stats.get("texts", 0))
        sheet.append(row)
        if report.worst in _FILLS:
            _fill_row(sheet, sheet.max_row, len(SUMMARY_HEADERS),
                      _FILLS[report.worst], PatternFill)
    _widths(sheet, (38, 10, 9, 11, 7, 10, 8, 8))


def _write_findings(sheet, reports, Alignment, Font, PatternFill):
    _header(sheet, FINDING_HEADERS, Alignment, Font, PatternFill)
    for report in sorted(reports, key=lambda r: r.source):
        for finding in report.sorted_findings():
            rule = rules.RULES.get(finding.rule)
            sheet.append((
                report.source, finding.rule, finding.severity,
                rule.family if rule else "",
                finding.message, finding.subject or "",
                finding.count if finding.count is not None else "",
                "; ".join(str(e) for e in finding.examples),
                int(round(finding.where[0])) if finding.where else "",
                int(round(finding.where[1])) if finding.where else "",
                rule.guidance if rule else "",
            ))
            if finding.severity in _FILLS:
                _fill_row(sheet, sheet.max_row, 3,
                          _FILLS[finding.severity], PatternFill)
    _widths(sheet, (32, 7, 10, 12, 54, 22, 8, 40, 10, 10, 70))
    _wrap_column(sheet, 11, Alignment)
    _wrap_column(sheet, 5, Alignment)


def _write_rules(sheet, Alignment, Font, PatternFill):
    _header(sheet, RULE_HEADERS, Alignment, Font, PatternFill)
    for rule in rules.catalogue():
        sheet.append((rule.rule_id, rule.family, rule.title, rule.severity,
                      rule.guidance))
        if rule.severity in _FILLS:
            _fill_row(sheet, sheet.max_row, 4, _FILLS[rule.severity],
                      PatternFill)
    _widths(sheet, (7, 12, 52, 16, 80))
    _wrap_column(sheet, 5, Alignment)


# -- sheet plumbing ---------------------------------------------------------

def _header(sheet, headers, Alignment, Font, PatternFill):
    sheet.append(tuple(headers))
    fill = PatternFill("solid", fgColor=_HEADER_FILL)
    font = Font(bold=True, color=_HEADER_FONT)
    for column in range(1, len(headers) + 1):
        cell = sheet.cell(row=1, column=column)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"


def _fill_row(sheet, row, columns, colour, PatternFill):
    fill = PatternFill("solid", fgColor=colour)
    for column in range(1, columns + 1):
        sheet.cell(row=row, column=column).fill = fill


def _widths(sheet, widths):
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[_column_letter(index)].width = width


def _wrap_column(sheet, column, Alignment):
    letter = _column_letter(column)
    for row in range(2, sheet.max_row + 1):
        sheet["{0}{1}".format(letter, row)].alignment = Alignment(
            wrap_text=True, vertical="top")


def _column_letter(index):
    """1 -> A, 27 -> AA. openpyxl ships a helper; this avoids the import."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters
