# -*- coding: utf-8 -*-
"""Build the minimal bridge workbook: CONTROL, INFO, LEVELS, GRIDS, LOG.

Run it here, on any machine::

    python3 bridge/excel/build_workbook.py [target]

**It cannot produce a working ``.xlsm`` from nothing, and that is a fact about
the format rather than a shortcoming.** ``openpyxl`` can *preserve* a VBA project
with ``keep_vba=True``; it cannot create one, because a ``vbaProject.bin`` is an
OLE compound document holding compressed VBA source and generating a valid one
by hand is a project of its own.

So the one manual step, once:

1. Run this. It writes ``AnonGee_Bridge.xlsx`` with every sheet, table, header
   and validation in place.
2. Open it in Excel, **Save As** ``.xlsm``, then ``Alt+F11`` → File → Import
   File → ``modAnonGeeBridge.bas``.
3. Re-run this against the ``.xlsm`` from then on. It rewrites the sheets and
   **the macros survive**, because the VBA is preserved rather than recreated.

The VBA lives in the repository as ``.bas`` source, which means it is reviewable
in a diff like everything else — the reason for keeping it out of the binary in
the first place.

Datum only, on purpose. The first version of a format is the one everybody
copies, so it should be the smallest one that works rather than the one that
guesses at nine sheets nobody has used yet.
"""

import os
import sys

__version__ = "0.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TARGET = os.path.join(HERE, "AnonGee_Bridge.xlsx")

#: One row per command, in the order the CONTROL sheet lists them. The names
#: come from ``anongee_toolkit/bridge/registry.py`` and have to match it — a
#: button naming a command the registry does not have is a button that answers
#: "not a command this build knows", which is at least a clear failure.
COMMANDS = [
    ("Check the bridge", "bridge.echo", "",
     "Reads nothing, writes nothing. Answers with what the model is. Run this "
     "first — every command after it has two things that can be wrong, and "
     "this one has only the wire."),
    ("Create / update levels", "levels.sync", "LEVELS",
     "Match the LEVELS sheet against the model by name, then create or move "
     "each level. Never deletes one the sheet omits, never renames one, and "
     "never creates a second level where one already sits - each of those is "
     "reported instead. Run it twice and the second run changes nothing."),
    ("Create / update grids", "grids.sync", "GRIDS",
     "Match the GRIDS sheet against the model, then create, modify or leave "
     "each grid alone."),
]

CONTROL_HEADERS = ("Run", "Command", "Sheet", "What it does", "Write?",
                   "Last status", "When", "Note")

INFO_ROWS = [
    ("PROJECT", "", "The project name. Written onto what the bridge creates."),
    ("UNITS", "mm", "Millimetres. Every length in this workbook is one."),
    ("STANDARD", "BS 8666:2020", "The reinforcement standard, for later stages."),
    ("REVIT_TEMPLATE", "", "Path to the .rvt this job is built from."),
    ("BRIDGE_URL", "http://localhost:48884/anongee",
     "Where Revit is listening. Change it only if the port moved."),
]

LEVEL_HEADERS = ("Name", "Elevation", "LevelType", "Story", "Comments")
LEVEL_ROWS = [
    ("00 FOUNDATION LVL.", -1500, "", "No", "Underside of the pad"),
    ("01 GROUND LVL.", 0, "", "Yes", ""),
    ("02 1ST FLOOR LVL.", 3300, "", "Yes", ""),
    ("03 2ND FLOOR LVL.", 6600, "", "Yes", ""),
]

GRID_HEADERS = ("Name", "X1", "Y1", "X2", "Y2", "BubbleStart", "BubbleEnd",
                "Comments")
GRID_ROWS = [
    ("A", 0, -2000, 0, 14000, "Yes", "Yes", "Vertical, west"),
    ("B", 6000, -2000, 6000, 14000, "Yes", "Yes", ""),
    ("C", 12000, -2000, 12000, 14000, "Yes", "Yes", ""),
    ("1", -2000, 0, 14000, 0, "Yes", "Yes", "Horizontal, south"),
    ("2", -2000, 6000, 14000, 6000, "Yes", "Yes", ""),
    ("3", -2000, 12000, 14000, 12000, "Yes", "Yes", ""),
]

LOG_HEADERS = ("When", "Job", "Command", "Status", "Counts", "Note")


def build(target=DEFAULT_TARGET):
    """Write the workbook. Returns its path."""
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    keep_vba = target.lower().endswith(".xlsm")
    if keep_vba and os.path.exists(target):
        # The macros are in this file and nothing here can recreate them.
        book = load_workbook(target, keep_vba=True)
        for name in list(book.sheetnames):
            del book[name]
        book.create_sheet("CONTROL")
    else:
        book = Workbook()
        book.active.title = "CONTROL"

    head = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F3864")
    label = Font(bold=True)
    wrap = Alignment(vertical="top", wrap_text=True)

    def header(sheet, names, row=1):
        for column, name in enumerate(names, start=1):
            cell = sheet.cell(row=row, column=column, value=name)
            cell.font = head
            cell.fill = head_fill
        sheet.freeze_panes = sheet.cell(row=row + 1, column=1)

    # -- CONTROL ------------------------------------------------------------
    control = book["CONTROL"]
    control["A1"] = "AnonGee Bridge"
    control["A1"].font = Font(bold=True, size=16)
    control["A2"] = ("Save the workbook, then press a button. Revit runs the "
                     "job and writes back here.")
    control["A3"] = ("Write? = No means a dry run: it reports what it would do "
                     "and touches nothing. Change it to Yes to build.")
    control["A4"] = ("Nothing happens unless Bridge Listener is switched on in "
                     "Revit — AnonGee tab, Dev panel.")

    header(control, CONTROL_HEADERS, row=6)
    for index, (title, command, sheet_name, what) in enumerate(COMMANDS):
        row = 7 + index
        control.cell(row=row, column=1, value=title).font = label
        control.cell(row=row, column=2, value=command)
        control.cell(row=row, column=3, value=sheet_name)
        control.cell(row=row, column=4, value=what).alignment = wrap
        control.cell(row=row, column=5, value="No")

    switch = DataValidation(type="list", formula1='"No,Yes"', allow_blank=False)
    control.add_data_validation(switch)
    switch.add("E7:E{0}".format(6 + len(COMMANDS)))

    for column, width in (("A", 24), ("B", 16), ("C", 10), ("D", 62),
                          ("E", 9), ("F", 13), ("G", 20), ("H", 44)):
        control.column_dimensions[column].width = width
    for index in range(len(COMMANDS)):
        control.row_dimensions[7 + index].height = 46

    # -- INFO ---------------------------------------------------------------
    info = book.create_sheet("INFO")
    header(info, ("Key", "Value", "What it is"))
    for index, (key, value, what) in enumerate(INFO_ROWS):
        info.cell(row=2 + index, column=1, value=key).font = label
        info.cell(row=2 + index, column=2, value=value)
        info.cell(row=2 + index, column=3, value=what)
    for column, width in (("A", 20), ("B", 42), ("C", 62)):
        info.column_dimensions[column].width = width

    # -- LEVELS and GRIDS ---------------------------------------------------
    for name, headers, rows, widths in (
            ("LEVELS", LEVEL_HEADERS, LEVEL_ROWS,
             (("A", 26), ("B", 12), ("C", 18), ("D", 8), ("E", 40))),
            ("GRIDS", GRID_HEADERS, GRID_ROWS,
             (("A", 10), ("B", 10), ("C", 10), ("D", 10), ("E", 10),
              ("F", 13), ("G", 13), ("H", 32)))):
        sheet = book.create_sheet(name)
        header(sheet, headers)
        for index, values in enumerate(rows):
            for column, value in enumerate(values, start=1):
                sheet.cell(row=2 + index, column=column, value=value)
        for column, width in widths:
            sheet.column_dimensions[column].width = width

    yes_no = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    book["LEVELS"].add_data_validation(yes_no)
    yes_no.add("D2:D200")
    bubbles = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    book["GRIDS"].add_data_validation(bubbles)
    bubbles.add("F2:G200")

    # -- LOG ----------------------------------------------------------------
    log = book.create_sheet("LOG")
    header(log, LOG_HEADERS)
    for column, width in (("A", 20), ("B", 22), ("C", 16), ("D", 12),
                          ("E", 34), ("F", 60)):
        log.column_dimensions[column].width = width

    book.save(target)
    return target


def main(argv):
    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    written = build(target)
    print("wrote {0}".format(written))
    if not written.lower().endswith(".xlsm"):
        print("Save As .xlsm in Excel, then import modAnonGeeBridge.bas once. "
              "After that, re-run this against the .xlsm and the macros "
              "survive.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
