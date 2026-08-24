# -*- coding: utf-8 -*-
"""Build the sample project workbook: Foundation + G + 4, on a 5 x 3 grid.

Run it here, on any machine::

    py bridge\\excel\\build_sample_project.py            (Windows)
    python3 bridge/excel/build_sample_project.py         (elsewhere)

A whole small building, described the way a real schedule would describe it, so
the **format** can be argued with before any of it is built. Change the numbers
at the top and re-run; every sheet is generated from them, so the building stays
consistent with itself no matter what is moved.

    24 m x 12 m, five vertical grids A-E and three horizontal grids 1-3,
    six storeys from a foundation at -1500 to a terrace at +16500.

    7 levels - 8 grids - 15 footings - 90 columns - 132 beams - 6 slabs

**Nothing here is built yet except levels and grids.** The other four commands
are declared in the registry and not written, so their buttons answer *declared
but not built yet* — which is a clear failure rather than an obscure one, and is
why they are declared first.

Two conventions worth knowing before reading a sheet:

*Grid reference first, coordinates as the fallback.* Every placement sheet names
a grid intersection and leaves X and Y empty. Coordinates are there for the
things a grid cannot describe, and for a model that has no grids in it yet.

*One row per element that will exist.* A column that rises six storeys is six
rows, not one, because in a reinforced concrete frame those are six pours with a
joint between each — and because a column that changes size at the fourth floor
has to be able to say so. It is verbose and it is honest.
"""

import os
import sys

__version__ = "0.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TARGET = os.path.join(HERE, "AnonGee_Sample_Project.xlsx")

# ---------------------------------------------------------------------------
# The building. Everything below is generated from these.
# ---------------------------------------------------------------------------
PROJECT = "Sample Tower - Foundation + G + 4"

#: Five vertical grids, four bays of 6 m: a 24 m frontage.
GRIDS_VERTICAL = [("A", 0), ("B", 6000), ("C", 12000), ("D", 18000),
                  ("E", 24000)]
#: Three horizontal grids, two bays of 6 m: 12 m deep.
GRIDS_HORIZONTAL = [("1", 0), ("2", 6000), ("3", 12000)]

#: How far past the outermost grid a grid line is drawn.
GRID_OVERHANG = 2000

#: ``(name, elevation, is_building_story)``. The foundation is not a storey.
LEVELS = [
    ("00 FOUNDATION LVL.", -1500, "No"),
    ("01 GROUND LVL.", 0, "Yes"),
    ("02 FIRST FLOOR LVL.", 3300, "Yes"),
    ("03 SECOND FLOOR LVL.", 6600, "Yes"),
    ("04 THIRD FLOOR LVL.", 9900, "Yes"),
    ("05 FOURTH FLOOR LVL.", 13200, "Yes"),
    ("06 TERRACE LVL.", 16500, "Yes"),
]

#: A storey is the space between two levels, and a column belongs to one.
#: ``(code, base level, top level)``.
STOREYS = [("S{0}".format(index + 1), LEVELS[index][0], LEVELS[index + 1][0])
           for index in range(len(LEVELS) - 1)]

#: Columns reduce going up, which is what a second type is for.
COLUMN_TYPE_BY_STOREY = {"S1": "C1", "S2": "C1", "S3": "C1",
                         "S4": "C2", "S5": "C2", "S6": "C2"}

#: Every floor that carries beams and a slab. The foundation carries neither;
#: the ground floor carries plinth beams and a slab on grade.
FRAMED_LEVELS = [name for name, _elevation, _story in LEVELS[1:]]

CONCRETE = "C32/40"


def grid_x(name):
    return dict(GRIDS_VERTICAL)[name]


def grid_y(name):
    return dict(GRIDS_HORIZONTAL)[name]


def intersections():
    """Every grid crossing, in reading order: A1, A2, A3, B1, ..."""
    for letter, _x in GRIDS_VERTICAL:
        for number, _y in GRIDS_HORIZONTAL:
            yield letter, number


def position(letter, number):
    """Corner, edge or internal — which decides the footing type."""
    letters = [name for name, _x in GRIDS_VERTICAL]
    numbers = [name for name, _y in GRIDS_HORIZONTAL]
    on_x_edge = letter in (letters[0], letters[-1])
    on_y_edge = number in (numbers[0], numbers[-1])
    if on_x_edge and on_y_edge:
        return "corner"
    if on_x_edge or on_y_edge:
        return "edge"
    return "internal"


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

INFO_ROWS = [
    ("PROJECT", PROJECT, "Written onto what the bridge creates."),
    ("UNITS", "mm", "Every length in this workbook is millimetres."),
    ("STANDARD", "BS 8666:2020", "The reinforcement standard, for later."),
    ("REVIT_TEMPLATE", "", "Path to the .rvt this job is built from."),
    ("BRIDGE_URL", "http://localhost:48884/anongee",
     "Where Revit is listening. Change it only if the port moved."),
    ("GRID_SPACING", "6000 x 6000", "Four bays by two, 24 m x 12 m."),
    ("STOREY_HEIGHT", "3300", "Foundation at -1500, terrace at +16500."),
]

#: ``(button, command, sheet, what it does, built yet)``. The names have to
#: match ``anongee_toolkit/bridge/registry.py``; a test holds them together.
COMMANDS = [
    ("Check the bridge", "bridge.echo", "",
     "Reads nothing, writes nothing. Run this first.", "yes"),
    ("Create / update levels", "levels.sync", "LEVELS",
     "Match by name, then create or move each level. Never deletes one the "
     "sheet omits, never renames, never fills an occupied elevation.", "yes"),
    ("Create / update grids", "grids.sync", "GRIDS",
     "Angle is 0 along +X and 90 along +Y. Position is synced, extent is not. "
     "A grid running a different way is reported, never redrawn.", "yes"),
    ("Create footings", "footings.sync", "FOOTING_PLACEMENT",
     "Pad footings as structural floors, so an arbitrary outline can be "
     "drawn.", "not yet"),
    ("Create columns", "columns.sync", "COLUMN_PLACEMENT",
     "One column per storey, between the base and top levels named.",
     "not yet"),
    ("Create beams", "beams.sync", "BEAM_PLACEMENT",
     "Framing between the grid intersections each row names.", "not yet"),
    ("Create slabs", "slabs.sync", "SLAB_PLACEMENT",
     "Floor slabs from the outline each row carries.", "not yet"),
]

CONTROL_HEADERS = ("Run", "Command", "Sheet", "What it does", "Built?",
                   "Write?", "Last status", "When", "Note")

LEVEL_HEADERS = ("Name", "Elevation", "LevelType", "Story", "Comments")
GRID_HEADERS = ("Name", "X1", "Y1", "X2", "Y2", "Angle", "Length",
                "BubbleStart", "BubbleEnd", "Comments")

FOOTING_TYPE_HEADERS = ("TypeMark", "Length", "Width", "Thickness", "CoverTop",
                        "CoverBottom", "CoverSide", "Concrete", "Comments")
FOOTING_TYPES = [
    ("F1", 2400, 2400, 600, 50, 75, 50, CONCRETE, "Internal - four bays meet"),
    ("F2", 1800, 1800, 500, 50, 75, 50, CONCRETE, "Edge"),
    ("F3", 1500, 1500, 450, 50, 75, 50, CONCRETE, "Corner"),
]
FOOTING_BY_POSITION = {"internal": "F1", "edge": "F2", "corner": "F3"}
FOOTING_PLACEMENT_HEADERS = ("Mark", "TypeMark", "GridX", "GridY", "X", "Y",
                             "Level", "TopOffset", "Rotation", "Outline")

COLUMN_TYPE_HEADERS = ("TypeMark", "Width", "Depth", "Cover", "Concrete",
                       "Comments")
COLUMN_TYPES = [
    ("C1", 300, 600, 40, CONCRETE, "Foundation to second floor"),
    ("C2", 300, 450, 40, CONCRETE, "Second floor to terrace - reduced"),
]
COLUMN_PLACEMENT_HEADERS = ("Mark", "TypeMark", "GridX", "GridY", "X", "Y",
                            "BaseLevel", "BaseOffset", "TopLevel", "TopOffset",
                            "Rotation")

BEAM_TYPE_HEADERS = ("TypeMark", "Width", "Depth", "Cover", "Concrete",
                     "Comments")
BEAM_TYPES = [
    ("B1", 300, 600, 40, CONCRETE, "Floor beams, every framed level"),
    ("PB1", 230, 450, 40, CONCRETE, "Plinth beams at ground"),
]
BEAM_PLACEMENT_HEADERS = ("Mark", "TypeMark", "FromGridX", "FromGridY",
                          "ToGridX", "ToGridY", "X1", "Y1", "X2", "Y2",
                          "Level", "Offset", "Comments")

SLAB_TYPE_HEADERS = ("TypeMark", "Thickness", "Cover", "Concrete", "Comments")
SLAB_TYPES = [("S1", 150, 25, CONCRETE, "Typical floor slab")]
SLAB_PLACEMENT_HEADERS = ("Mark", "TypeMark", "Level", "Offset", "Outline",
                          "Comments")

LOG_HEADERS = ("When", "Job", "Command", "Status", "Counts", "Note")


# ---------------------------------------------------------------------------
# Generating the rows
# ---------------------------------------------------------------------------

def level_rows():
    return [(name, elevation, "", story, "")
            for name, elevation, story in LEVELS]


def grid_rows():
    """Vertical grids run at 90 degrees, horizontal ones at 0."""
    rows = []
    low_y = GRIDS_HORIZONTAL[0][1] - GRID_OVERHANG
    high_y = GRIDS_HORIZONTAL[-1][1] + GRID_OVERHANG
    low_x = GRIDS_VERTICAL[0][1] - GRID_OVERHANG
    high_x = GRIDS_VERTICAL[-1][1] + GRID_OVERHANG

    for name, x in GRIDS_VERTICAL:
        rows.append((name, x, low_y, x, high_y, 90, None, "Yes", "Yes",
                     "Vertical"))
    for name, y in GRIDS_HORIZONTAL:
        rows.append((name, low_x, y, high_x, y, 0, None, "Yes", "Yes",
                     "Horizontal"))
    return rows


def footing_rows():
    rows = []
    for letter, number in intersections():
        where = position(letter, number)
        rows.append(("F-{0}{1}".format(letter, number),
                     FOOTING_BY_POSITION[where], letter, number, None, None,
                     LEVELS[0][0], 0, 0, ""))
    return rows


def column_rows():
    """One row per column per storey. Six pours, six rows."""
    rows = []
    for letter, number in intersections():
        for code, base, top in STOREYS:
            rows.append(("C-{0}{1}-{2}".format(letter, number, code),
                         COLUMN_TYPE_BY_STOREY[code], letter, number,
                         None, None, base, 0, top, 0, 0))
    return rows


def beam_rows():
    """Every bay of every grid line, on every framed level."""
    letters = [name for name, _x in GRIDS_VERTICAL]
    numbers = [name for name, _y in GRIDS_HORIZONTAL]
    rows = []

    for level in FRAMED_LEVELS:
        code = level.split()[0]
        beam_type = "PB1" if level == FRAMED_LEVELS[0] else "B1"
        note = "Plinth" if beam_type == "PB1" else ""

        # Along X: one beam per bay of each horizontal grid.
        for number in numbers:
            for first, second in zip(letters, letters[1:]):
                rows.append((
                    "B-{0}-{1}-{2}{3}".format(code, number, first, second),
                    beam_type, first, number, second, number,
                    None, None, None, None, level, 0, note))

        # Along Y: one beam per bay of each vertical grid.
        for letter in letters:
            for first, second in zip(numbers, numbers[1:]):
                rows.append((
                    "B-{0}-{1}-{2}{3}".format(code, letter, first, second),
                    beam_type, letter, first, letter, second,
                    None, None, None, None, level, 0, note))
    return rows


def slab_rows():
    """One slab per framed level, over the whole footprint."""
    x1, y1 = GRIDS_VERTICAL[0][1], GRIDS_HORIZONTAL[0][1]
    x2, y2 = GRIDS_VERTICAL[-1][1], GRIDS_HORIZONTAL[-1][1]
    outline = "{0},{1}; {2},{1}; {2},{3}; {0},{3}".format(x1, y1, x2, y2)
    rows = []
    for level in FRAMED_LEVELS:
        code = level.split()[0]
        note = "On grade" if level == FRAMED_LEVELS[0] else ""
        rows.append(("SL-{0}".format(code), "S1", level, 0, outline, note))
    return rows


# ---------------------------------------------------------------------------
# Writing it
# ---------------------------------------------------------------------------

def build(target=DEFAULT_TARGET):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    keep_vba = target.lower().endswith(".xlsm")
    if keep_vba and os.path.exists(target):
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

    def table(name, headers, rows, widths=()):
        sheet = book.create_sheet(name)
        header(sheet, headers)
        for index, values in enumerate(rows):
            for column, value in enumerate(values, start=1):
                sheet.cell(row=2 + index, column=column, value=value)
        for column, width in widths:
            sheet.column_dimensions[column].width = width
        return sheet

    # -- CONTROL ------------------------------------------------------------
    control = book["CONTROL"]
    control["A1"] = "AnonGee Bridge - {0}".format(PROJECT)
    control["A1"].font = Font(bold=True, size=16)
    control["A2"] = ("Save the workbook, then press a button. Revit runs the "
                     "job and writes back here.")
    control["A3"] = ("Write? = No is a dry run: it reports what it would do "
                     "and touches nothing. Change it to Yes to build.")
    control["A4"] = ("Built? = not yet means the command is declared and not "
                     "written; pressing it says so rather than failing "
                     "obscurely.")
    control["A5"] = ("Nothing happens unless Bridge Listener is switched on in "
                     "Revit - AnonGee tab, Dev panel.")

    header(control, CONTROL_HEADERS, row=7)
    for index, (title, command, sheet_name, what, built) in enumerate(COMMANDS):
        row = 8 + index
        control.cell(row=row, column=1, value=title).font = label
        control.cell(row=row, column=2, value=command)
        control.cell(row=row, column=3, value=sheet_name)
        control.cell(row=row, column=4, value=what).alignment = wrap
        control.cell(row=row, column=5, value=built)
        control.cell(row=row, column=6, value="No")

    switch = DataValidation(type="list", formula1='"No,Yes"', allow_blank=False)
    control.add_data_validation(switch)
    switch.add("F8:F{0}".format(7 + len(COMMANDS)))

    for column, width in (("A", 24), ("B", 17), ("C", 20), ("D", 62),
                          ("E", 10), ("F", 9), ("G", 13), ("H", 20), ("I", 44)):
        control.column_dimensions[column].width = width
    for index in range(len(COMMANDS)):
        control.row_dimensions[8 + index].height = 42

    # -- INFO ---------------------------------------------------------------
    info = book.create_sheet("INFO")
    header(info, ("Key", "Value", "What it is"))
    for index, (key, value, what) in enumerate(INFO_ROWS):
        info.cell(row=2 + index, column=1, value=key).font = label
        info.cell(row=2 + index, column=2, value=value)
        info.cell(row=2 + index, column=3, value=what)
    for column, width in (("A", 20), ("B", 40), ("C", 56)):
        info.column_dimensions[column].width = width

    # -- the rest -----------------------------------------------------------
    table("LEVELS", LEVEL_HEADERS, level_rows(),
          (("A", 26), ("B", 12), ("C", 16), ("D", 8), ("E", 30)))
    table("GRIDS", GRID_HEADERS, grid_rows(),
          (("A", 8), ("B", 10), ("C", 10), ("D", 10), ("E", 10), ("F", 9),
           ("G", 10), ("H", 13), ("I", 13), ("J", 26)))

    table("FOOTING_TYPES", FOOTING_TYPE_HEADERS, FOOTING_TYPES,
          (("A", 10), ("I", 34)))
    table("FOOTING_PLACEMENT", FOOTING_PLACEMENT_HEADERS, footing_rows(),
          (("A", 12), ("B", 11), ("G", 26), ("J", 22)))

    table("COLUMN_TYPES", COLUMN_TYPE_HEADERS, COLUMN_TYPES,
          (("A", 10), ("F", 40)))
    table("COLUMN_PLACEMENT", COLUMN_PLACEMENT_HEADERS, column_rows(),
          (("A", 14), ("B", 11), ("G", 26), ("I", 26)))

    table("BEAM_TYPES", BEAM_TYPE_HEADERS, BEAM_TYPES,
          (("A", 10), ("F", 38)))
    table("BEAM_PLACEMENT", BEAM_PLACEMENT_HEADERS, beam_rows(),
          (("A", 18), ("B", 11), ("K", 26), ("M", 14)))

    table("SLAB_TYPES", SLAB_TYPE_HEADERS, SLAB_TYPES,
          (("A", 10), ("E", 30)))
    table("SLAB_PLACEMENT", SLAB_PLACEMENT_HEADERS, slab_rows(),
          (("A", 12), ("C", 26), ("E", 46), ("F", 16)))

    log = book.create_sheet("LOG")
    header(log, LOG_HEADERS)
    for column, width in (("A", 20), ("B", 22), ("C", 16), ("D", 12),
                          ("E", 34), ("F", 60)):
        log.column_dimensions[column].width = width

    book.save(target)
    return target


def counts():
    return {
        "levels": len(LEVELS),
        "grids": len(GRIDS_VERTICAL) + len(GRIDS_HORIZONTAL),
        "footings": len(footing_rows()),
        "columns": len(column_rows()),
        "beams": len(beam_rows()),
        "slabs": len(slab_rows()),
    }


def main(argv):
    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    written = build(target)
    print("wrote {0}".format(written))
    for name, count in sorted(counts().items()):
        print("  {0:<10} {1}".format(name, count))
    if not written.lower().endswith(".xlsm"):
        print("\nSave As .xlsm in Excel, then Alt+F11 -> File -> Import File "
              "-> modAnonGeeBridge.bas. After that, re-run this against the "
              ".xlsm and the macros survive.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
