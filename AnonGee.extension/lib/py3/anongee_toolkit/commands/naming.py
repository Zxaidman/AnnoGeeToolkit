# -*- coding: utf-8 -*-
"""``naming.refresh`` — make the NAMING sheet agree with itself again.

The sheet has four columns and only one of them is written by a person. The
project owner rewrote every ``Pattern`` to the house convention and the
``Example`` and ``Fields it may use`` beside them still described the old ones —
so a sheet whose entire job is to be read was, in writing, wrong. FEAT-41.

**Why this is not an Excel formula.** ``Example`` is not a string substitution;
it is :func:`naming_sheet.render` run against a sample, including the rule that
``600.0`` prints as ``600`` and the per-key samples that stop a stair being
1200 wide in one column and 2400 in another. ``Fields it may use`` comes out of
``PATTERNS``. A formula would be a second implementation of both and would drift
from the first one the day somebody adds a field — which is the same failure the
generated example existed to prevent.

So the example is produced **by the code that will produce the name**. That is
the only version of this worth having.

**Writes nothing to Revit.** It is the first command that answers into a sheet
rather than a model, so it needs no document, no transaction, and ignores
``Write?`` entirely — there is nothing to be careful about.
"""

__version__ = "0.1.0"

#: The three columns this maintains, and what goes in each. ``Pattern`` is
#: deliberately absent: it is the one column a person owns, and a refresh that
#: rewrote it would be a refresh nobody would press twice.
COLUMNS = ("Example", "Fields it may use", "What it names")


def run(uiapp, envelope):
    """``(summary, findings, note, cells)``. Never raises."""
    from anongee_toolkit.bridge import envelope as envelope_module
    from anongee_toolkit.commands import _sheets
    from anongee_toolkit.rc_automation import excel_engine
    from anongee_toolkit.rc_automation import naming_sheet

    findings = []

    def finding(severity, row, message, column=""):
        return {"severity": severity, "sheet": naming_sheet.SHEET,
                "row": row, "column": column, "message": message}

    workbook = (envelope or {}).get("workbook") or ""
    if not workbook:
        return ({"read": 0, "refreshed": 0},
                [finding("Error", "", "the job names no workbook")], "", [])

    sheets, read_issues = excel_engine.read_grid(workbook)
    findings.extend(envelope_module.findings_from_issues(read_issues))

    grid = _sheets.sheet({"sheets": sheets}, naming_sheet.SHEET)
    if grid is None:
        findings.append(finding(
            "Error", "", "this workbook has no {0} sheet, so there is nothing "
            "to refresh".format(naming_sheet.SHEET)))
        return {"read": 0, "refreshed": 0}, findings, "", []

    patterns, issues = naming_sheet.parse(grid)
    findings.extend(envelope_module.findings_from_issues(issues))

    header_at, columns = _header(grid)
    if header_at is None:
        findings.append(finding(
            "Error", "", "the {0} sheet has no Element and Pattern columns, so "
            "its rows cannot be found".format(naming_sheet.SHEET)))
        return {"read": 0, "refreshed": 0}, findings, "", []

    missing = [name for name in COLUMNS if _fold(name) not in columns]
    for name in missing:
        findings.append(finding(
            "Info", header_at + 1,
            "there is no {0!r} column on this sheet, so that part was left "
            "alone. Add the column and run this again.".format(name),
            column=name))

    cells, read, refreshed = _cells(grid, header_at, columns, patterns)

    note = "{0} row(s) read; {1} cell(s) refreshed".format(read, refreshed)
    if not refreshed and read:
        note = "{0} row(s) read and every one already agreed".format(read)
    return ({"read": read, "refreshed": refreshed}, findings, note, cells)


def _cells(grid, header_at, columns, patterns):
    """``(cells, rows read, cells changed)``.

    Only cells whose value actually differs are returned. A refresh that
    rewrote all sixty would put an unsaved-changes dot on a workbook that had
    not changed, and would say ``refreshed=21`` every time — which stops
    meaning anything the second time it is read.
    """
    from anongee_toolkit.rc_automation import naming_sheet

    by_folded = dict((_fold(name), name) for name in naming_sheet.PATTERNS)
    key_at = columns.get("element")
    cells = []
    read = 0

    for offset, raw in enumerate(grid[header_at + 1:]):
        row_number = header_at + offset + 2
        cell = _fold(_at(raw, key_at))
        key = by_folded.get(cell)
        if key is None:
            continue
        read += 1

        for name, value in (("Example", naming_sheet.example(patterns, key)),
                            ("Fields it may use", _fields(key)),
                            ("What it names", naming_sheet.PATTERNS[key][2])):
            column_at = columns.get(_fold(name))
            if column_at is None:
                continue
            if _text(_at(raw, column_at)) == _text(value):
                continue
            cells.append({"sheet": naming_sheet.SHEET, "row": row_number,
                          "column": column_at + 1, "value": value})
    return cells, read, len(cells)


def _fields(key):
    """``{b}, {h}`` — what the sheet's own column should say this key takes."""
    from anongee_toolkit.rc_automation import naming_sheet
    return ", ".join("{" + field + "}"
                     for field in naming_sheet.PATTERNS[key][0])


def _header(grid):
    """``(row index, {folded name: column index})`` for the header row.

    The same two-column test :func:`naming_sheet.parse` uses, so a sheet this
    can refresh and a sheet that can be read are the same sheet.
    """
    for index, row in enumerate(grid or ()):
        columns = {}
        for column, raw in enumerate(row):
            folded = _fold(raw)
            if folded:
                columns[folded] = column
        if "element" in columns and "pattern" in columns:
            return index, columns
    return None, {}


def _at(row, index):
    if index is None or index >= len(row):
        return ""
    return row[index]


def _text(value):
    return "" if value is None else "{0}".format(value).strip()


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
