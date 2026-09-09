# -*- coding: utf-8 -*-
"""Write the sheet model to .xlsx with openpyxl. Formatting only, no decisions.

openpyxl is vendored in lib/py3, so no Excel installation is needed -- which
matters because the audit has to run on whatever machine Revit is on, and the
COM writer in `anongee_toolkit.io.excel` requires Excel itself.

Everything about WHAT the report says lives in `sheets.py`. This module only
turns tables into a formatted workbook: header styling, frozen panes, autofilter,
column widths, and a colour per severity so the eye finds the errors first.
"""

from . import config

_MAX_SHEET_NAME = 31        # Excel's hard limit
_MAX_WIDTH = 70             # columns wider than this become unreadable
_MIN_WIDTH = 9
_SAMPLE_ROWS = 200          # rows sampled for width; a full scan is needless work

#: Fills per severity. Muted deliberately: a sheet where every row shouts is a
#: sheet nobody reads, so `ok` and `info` stay unfilled and only the two that
#: need action carry colour.
_SEVERITY_FILL = {
    config.SEVERITY_ERROR: "FFF4CCCC",
    config.SEVERITY_WARNING: "FFFCE5CD",
}
_HEADER_FILL = "FF333333"
_NOTE_FILL = "FFF3F3F3"


def write(path, sheets):
    """Write `sheets` to `path` as .xlsx. Returns the path.

    Raises if openpyxl is unavailable -- a caller that wants to degrade to CSV
    should catch that rather than have this module silently write a lesser file
    under an .xlsx name.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)

    header_font = Font(bold=True, color="FFFFFFFF")
    header_fill = PatternFill("solid", fgColor=_HEADER_FILL)
    note_font = Font(italic=True, size=9)
    note_fill = PatternFill("solid", fgColor=_NOTE_FILL)
    wrap = Alignment(vertical="top", wrap_text=False)

    used_names = set()
    for sheet in sheets:
        worksheet = workbook.create_sheet(_unique_name(sheet.name, used_names))
        row_index = 1

        for note in sheet.notes:
            cell = worksheet.cell(row=row_index, column=1, value=note)
            cell.font = note_font
            cell.fill = note_fill
            row_index += 1
        if sheet.notes:
            row_index += 1
        header_row = row_index

        for column_index, name in enumerate(sheet.columns, start=1):
            cell = worksheet.cell(row=header_row, column=column_index, value=name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        row_index += 1

        severity_column = _severity_column(sheet)
        for row in sheet.rows:
            fill = None
            if severity_column is not None:
                colour = _SEVERITY_FILL.get(row[severity_column])
                fill = PatternFill("solid", fgColor=colour) if colour else None
            for column_index, value in enumerate(row, start=1):
                cell = worksheet.cell(row=row_index, column=column_index,
                                      value=_cell_value(value))
                cell.alignment = wrap
                if fill is not None:
                    cell.fill = fill
            row_index += 1

        _finish(worksheet, sheet, header_row, row_index - 1, get_column_letter)

    workbook.save(path)
    return path


def _finish(worksheet, sheet, header_row, last_row, get_column_letter):
    """Freeze panes, add the autofilter, and size the columns."""
    if sheet.freeze:
        worksheet.freeze_panes = worksheet.cell(row=header_row + 1, column=1)
    if sheet.columns and last_row > header_row:
        worksheet.auto_filter.ref = "A{0}:{1}{2}".format(
            header_row, get_column_letter(len(sheet.columns)), last_row)
    for index, name in enumerate(sheet.columns):
        width = len(str(name)) + 3
        for row in sheet.rows[:_SAMPLE_ROWS]:
            if index < len(row) and row[index] is not None:
                width = max(width, len(str(row[index])) + 2)
        worksheet.column_dimensions[get_column_letter(index + 1)].width = \
            max(_MIN_WIDTH, min(_MAX_WIDTH, width))


def _severity_column(sheet):
    """Index of a `severity` column, so rows can be tinted. None when absent."""
    for index, name in enumerate(sheet.columns):
        if name.lower() == "severity":
            return index
    return None


def _cell_value(value):
    """Coerce to something openpyxl accepts, without losing numbers to strings."""
    if value is None or isinstance(value, (int, float, bool, str)):
        # Excel refuses a leading "=" as anything but a formula, and a layer
        # genuinely can be named that. A leading apostrophe would show, so the
        # value is spaced instead -- visible, and never evaluated.
        if isinstance(value, str) and value.startswith("="):
            return " " + value
        return value
    return str(value)


def _unique_name(name, used):
    """A legal, unique sheet name. Excel forbids []:*?/\\ and caps at 31 chars."""
    cleaned = "".join("-" if character in "[]:*?/\\" else character
                      for character in name)[:_MAX_SHEET_NAME]
    candidate = cleaned or "Sheet"
    suffix = 2
    while candidate.lower() in used:
        tail = " ({0})".format(suffix)
        candidate = cleaned[:_MAX_SHEET_NAME - len(tail)] + tail
        suffix += 1
    used.add(candidate.lower())
    return candidate


def write_csv(folder, sheets):
    """Fallback: one .csv per sheet. Returns the paths written.

    Kept because a run that cannot write .xlsx (a locked file, an openpyxl that
    did not provision) should still hand back its data rather than nothing.
    """
    import csv
    import os

    if not os.path.isdir(folder):
        os.makedirs(folder)
    written = []
    used = set()
    for sheet in sheets:
        name = _unique_name(sheet.name, used)
        path = os.path.join(folder, "{0}.csv".format(name.replace(" ", "_")))
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            for note in sheet.notes:
                writer.writerow(["# " + note])
            writer.writerow(sheet.columns)
            for row in sheet.rows:
                writer.writerow(["" if value is None else value for value in row])
        written.append(path)
    return written
