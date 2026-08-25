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
    six storeys from a foundation at -1.5 to a terrace at +16.5.

**Nothing here is built yet except levels and grids.** The other four commands
are declared in the registry and not written, so their buttons answer *declared
but not built yet* -- which is a clear failure rather than an obscure one, and is
why they are declared first.

Six conventions worth knowing before reading a sheet. Each was a question the
project owner asked, and the answer is in the sheet rather than in a note
somebody has to find.

*One unit for the whole workbook, named in every header.* ``INFO`` carries it
and ``m`` is the default, because a level at 3.3 reads and a level at 3300 is
counted. Every length column says which unit it is in -- ``Elevation PBP (m)``
-- so the unit is visible where the number is, the macro can find exactly the
columns it must rescale, and Revit is told what the number meant. Revit itself
is always in internal feet, whatever a project's display units say.

*Two elevations on a level, one authority.* Project Base Point and Survey Point
are both written; ``ElevationBase`` says which one drives. A survey elevation
that disagrees with the model's survey offset is reported, never resolved
quietly.

*Grid reference first, coordinates as the fallback.* Every placement sheet names
a grid intersection and leaves the offsets empty. ``OffsetX``/``OffsetY`` are
measured **from that intersection**, so a column shifted 150 off the grid says
so in one cell. Absolute position is what you fall back to when no grid is
named, which is the only way to describe something in a model with no grids in
it yet.

*A column mark follows the stack, not the storey.* A column at A1 marked ``C1``
is ``C1`` all the way up, even where its size changes. Two columns share a mark
on one floor only if their **size and rebar schedule are both** the same. So the
mark is a schedule label, not a key -- the key is grid position plus storey --
and ``TypeMark`` carries the size, which is free to change per lift.

*Beam continuity is the layout.* A simply supported beam is one row. A
continuous beam is a group of rows, one per span, sharing a mark, and **a blank
row separates groups**. The sheet then reads the way a beam schedule reads and
nobody has to keep a Continuity column true.

*A slab is a panel, not a floor.* One slab per bay, bounded by the four grids
around it, and its edge is the **inner face of the beams** -- so the slab stops
where the beam starts and the concrete is not counted twice. ``EdgeRule`` says
which convention a row uses, so a slab that runs over its beams can still be
described.
"""

import os
import sys

__version__ = "0.2.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TARGET = os.path.join(HERE, "AnonGee_Sample_Project.xlsx")

# ---------------------------------------------------------------------------
# The building. Everything below is generated from these.
# ---------------------------------------------------------------------------
PROJECT = "Sample Tower - Foundation + G + 4"

#: The unit every length in the workbook is written in. ``m`` or ``mm``.
#: Metres by default: a levels sheet in metres reads, and one in millimetres is
#: counted. The constants below stay in millimetres because that is how a
#: drawing dimensions them; :func:`length` converts on the way out.
UNITS = "m"

#: What one millimetre is, in each unit.
UNIT_FACTOR = {"mm": 1.0, "m": 0.001}

#: A cover and a bar diameter stay in millimetres whatever the workbook is in.
#:
#: Metres were chosen because a level at 3.3 reads better than one at 3300. By
#: the same argument a cover of 0.05 and a bar of 0.012 read worse than 50 and
#: 12 — so consistency here would cost the thing it was bought for. A column
#: whose name starts with one of these keeps ``(mm)`` and the converter leaves
#: it alone.
PINNED_TO_MM = ("cover", "dia", "diameter", "bardia")

#: How a length is shown. Millimetres are whole numbers because half a
#: millimetre is not a thing anybody schedules; metres carry two decimals
#: because three of them is where a level lives.
NUMBER_FORMAT = {"mm": "#,##0", "m": "0.00"}

#: The font, in order of preference. Excel stores one name per cell, so the
#: build writes the first; ``AnonGeeBridge_ApplyFormat`` swaps in the best one
#: actually installed on the machine opening it.
FONT_STACK = ("Inter", "Segoe UI", "Cambria", "Calibri")

#: Three sizes, one step apart each. A title should be findable, not loud.
SIZE_TITLE = 14
SIZE_HEADER = 11
SIZE_BODY = 10

#: Every row, on every sheet. One height, so a sheet scrolls evenly.
ROW_HEIGHT = 20

#: Column widths are computed from what is in them, between these. The floor
#: keeps a one-letter grid column clickable; the ceiling stops one long comment
#: from pushing everything else off the screen.
WIDTH_MIN = 8
WIDTH_MAX = 46
WIDTH_PADDING = 3

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

#: What the Survey Point reads where the Project Base Point reads zero. The
#: site datum, in other words: ground floor is RL 100.000 on the survey, which
#: is the convention most site drawings arrive in.
SURVEY_OFFSET_MM = 100000

#: Which point an elevation is measured from. The first is the default.
ELEVATION_BASES = ("Project Base Point", "Survey Point")

#: A storey is the space between two levels, and a column belongs to one.
#: ``(code, base level, top level)``.
STOREYS = [("S{0}".format(index + 1), LEVELS[index][0], LEVELS[index + 1][0])
           for index in range(len(LEVELS) - 1)]

#: Columns reduce going up. The mark does not: see :func:`column_marks`.
COLUMN_TYPE_BY_STOREY = {"S1": "C-300x600", "S2": "C-300x600",
                         "S3": "C-300x600", "S4": "C-300x450",
                         "S5": "C-300x450", "S6": "C-300x450"}

#: The rebar schedule a column carries, by where it stands and how high it is.
#: Two columns of the same size with different cages are different marks, which
#: is the whole reason this is separate from the type.
COLUMN_REBAR = {
    ("lower", "corner"): "CS-1", ("lower", "edge"): "CS-2",
    ("lower", "internal"): "CS-3",
    ("upper", "corner"): "CS-4", ("upper", "edge"): "CS-5",
    ("upper", "internal"): "CS-6",
}

#: Which band a storey is in, for the rebar schedule above.
STOREY_BAND = {"S1": "lower", "S2": "lower", "S3": "lower",
               "S4": "upper", "S5": "upper", "S6": "upper"}

#: Every floor that carries framing. The foundation carries none; the ground
#: floor carries plinth beams, which are simply supported between pedestals.
FRAMED_LEVELS = [name for name, _elevation, _story in LEVELS[1:]]

#: Suspended slabs sit on every framed level above the ground. The ground floor
#: slab is on grade and is not a panel between beams, so it is not here.
SLAB_LEVELS = FRAMED_LEVELS[1:]

#: How a slab panel meets its beams. The first is the default.
EDGE_RULES = ("Inner face of beam", "Grid line", "Outer face of beam")

CONCRETE = "C32/40"


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def length(mm):
    """A millimetre constant, in the workbook's unit.

    Rounded, because ``6000 * 0.001`` is not 6 in binary floating point and a
    grid at 5.999999999999999 metres is the kind of thing somebody spends an
    afternoon on.
    """
    if mm is None:
        return None
    return round(float(mm) * UNIT_FACTOR[UNITS], 6)


def is_pinned(name):
    """True for a column that stays in millimetres whatever the workbook is in."""
    folded = "".join(c for c in str(name or "").lower() if c.isalnum())
    return any(folded.startswith(prefix) for prefix in PINNED_TO_MM)


def unit_of(name):
    """Which unit this column is written in — the workbook's, or pinned mm."""
    return "mm" if is_pinned(name) else UNITS


def unit(name):
    """A length header, carrying its unit: ``Elevation PBP (m)``.

    The unit is written into the header rather than kept in a list somewhere,
    so it is visible in the sheet, the macro can find every length column
    without being told, and a column somebody adds is converted the moment they
    label it.

    A pinned column says ``(mm)`` and means it — see :data:`PINNED_TO_MM`.
    """
    return "{0} ({1})".format(name, unit_of(name))


def measure(mm, header):
    """A millimetre constant, in whatever unit its own column is written in."""
    if mm is None:
        return None
    if is_pinned(header):
        return float(mm)
    return length(mm)


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------

def grid_x(name):
    return dict(GRIDS_VERTICAL)[name]


def grid_y(name):
    return dict(GRIDS_HORIZONTAL)[name]


def intersections():
    """Every grid crossing, in reading order: A1, B1, C1, ... A2, B2, ..."""
    for number, _y in GRIDS_HORIZONTAL:
        for letter, _x in GRIDS_VERTICAL:
            yield letter, number


def position(letter, number):
    """Corner, edge or internal — which decides the footing and the cage."""
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

#: ``(key, value, what it is)``. A key that names a unit means the number
#: beside it is in that unit — which is how the converter finds it on a sheet
#: that has no column headers. BUG-17.
INFO_ROWS = [
    ("PROJECT", PROJECT, "Written onto what the bridge creates."),
    ("UNITS", UNITS,
     "Every length column, and every header that names a unit. Change it "
     "here, then press ApplyUnits. Cover and diameter stay in mm."),
    ("SURVEY_OFFSET", SURVEY_OFFSET_MM,
     "What the Survey Point reads where the Project Base Point reads zero."),
    ("STANDARD", "BS 8666:2020", "The reinforcement standard, for later."),
    ("REVIT_TEMPLATE", "", "Path to the .rvt this job is built from."),
    ("BRIDGE_URL", "http://localhost:48884/anongee",
     "Where Revit is listening. Change it only if the port moved."),
    ("GRID_SPACING", "6 x 6", "Four bays by two, 24 m x 12 m."),
    ("STOREY_HEIGHT", 3300,
     "S1 to S6 are the lifts between levels; every COLUMN_PLACEMENT row names "
     "its own base and top level, so the code is never looked up."),
]

#: Which INFO keys carry a length, and therefore a unit.
INFO_LENGTH_KEYS = ("SURVEY_OFFSET", "STOREY_HEIGHT")

INFO_HEADERS = ("Key", "Value", "What it is")


def info_rows():
    """INFO, with the length keys carrying their unit and their value in it."""
    rows = []
    for key, value, what in INFO_ROWS:
        if key in INFO_LENGTH_KEYS:
            rows.append(("{0} ({1})".format(key, UNITS), length(value), what))
        else:
            rows.append((key, value, what))
    return rows


#: The lines above the table on CONTROL. One each, because every row on that
#: sheet is 20 units high and a paragraph in a cell that tall is a paragraph
#: with its bottom half cut off.
CONTROL_NOTES = (
    "Save the workbook, then press a button. Revit runs the job and writes "
    "back here.",
    "Write? = No is a dry run: it reports and touches nothing. Yes builds.",
    "Built? = not yet means declared and not written; pressing it says so.",
    "Nothing happens unless Bridge Listener is on - AnonGee tab, Dev panel.",
    "No buttons? Alt+F8 - AnonGeeBridge_AddButtons - Run.",
)

#: Which row the table's header sits on, below the notes.
CONTROL_HEADER_ROW = 2 + len(CONTROL_NOTES)

#: ``(button, command, sheet, what it does, built yet)``. The names have to
#: match ``anongee_toolkit/bridge/registry.py``; a test holds them together.
COMMANDS = [
    ("Check the bridge", "bridge.echo", "",
     "Reads nothing, writes nothing. Run this first.", "yes"),
    ("Create / update levels", "levels.sync", "LEVELS",
     "Match by name, then create or move. Never deletes or renames.", "yes"),
    ("Create / update grids", "grids.sync", "GRIDS",
     "Angle 0 along +X, 90 along +Y. Position synced, extent not.", "yes"),
    ("Create footings", "footings.sync", "FOOTING_PLACEMENT",
     "Pads as structural floors, one under each intersection.", "yes"),
    ("Create columns", "columns.sync", "COLUMN_PLACEMENT",
     "One column per storey, between the levels the row names.", "yes"),
    ("Create beams", "beams.sync", "BEAM_PLACEMENT",
     "Framing between the intersections each row names.", "not yet"),
    ("Create slabs", "slabs.sync", "SLAB_PLACEMENT",
     "One slab per panel, to the inner face of its beams.", "not yet"),
]

CONTROL_HEADERS = ("Run", "Command", "Sheet", "What it does", "Built?",
                   "Write?", "Last status", "When", "Note")

LEVEL_HEADERS = ("Name", unit("Elevation PBP"), unit("Elevation Survey"),
                 "ElevationBase", "LevelType", "Story", "Comments")
GRID_HEADERS = ("Name", unit("X1"), unit("Y1"), unit("X2"), unit("Y2"),
                "Angle", unit("Length"), "BubbleStart", "BubbleEnd",
                "Comments")

FOOTING_TYPE_HEADERS = ("TypeMark", unit("Length"), unit("Width"),
                        unit("Thickness"), unit("CoverTop"),
                        unit("CoverBottom"), unit("CoverSide"), "Concrete",
                        "Comments")
FOOTING_TYPES = [
    ("F1", 2400, 2400, 600, 50, 75, 50, CONCRETE, "Internal - four bays meet"),
    ("F2", 1800, 1800, 500, 50, 75, 50, CONCRETE, "Edge"),
    ("F3", 1500, 1500, 450, 50, 75, 50, CONCRETE, "Corner"),
]
#: Which columns of a TYPES row are lengths, so :func:`typed_rows` can convert
#: them without guessing from the value.
FOOTING_TYPE_LENGTHS = (1, 2, 3, 4, 5, 6)
FOOTING_BY_POSITION = {"internal": "F1", "edge": "F2", "corner": "F3"}
FOOTING_PLACEMENT_HEADERS = ("Mark", "TypeMark", "GridX", "GridY",
                             unit("OffsetX"), unit("OffsetY"), "Level",
                             unit("TopOffset"), "Rotation", "Outline",
                             "Comments")

COLUMN_TYPE_HEADERS = ("TypeMark", unit("Width"), unit("Depth"), unit("Cover"),
                       "Concrete", "Comments")
COLUMN_TYPES = [
    ("C-300x600", 300, 600, 40, CONCRETE, "Foundation to second floor"),
    ("C-300x450", 300, 450, 40, CONCRETE, "Second floor up - reduced"),
]
COLUMN_TYPE_LENGTHS = (1, 2, 3)
COLUMN_PLACEMENT_HEADERS = ("Mark", "GridX", "GridY", unit("OffsetX"),
                            unit("OffsetY"), "Storey", "BaseLevel",
                            "TopLevel", unit("BaseOffset"), unit("TopOffset"),
                            "TypeMark", "RebarSchedule", "Rotation",
                            "Comments")

BEAM_TYPE_HEADERS = ("TypeMark", unit("Width"), unit("Depth"), unit("Cover"),
                     "Concrete", "Comments")
BEAM_TYPES = [
    ("B-300x600", 300, 600, 40, CONCRETE, "Floor beams, every framed level"),
    ("PB-230x450", 230, 450, 40, CONCRETE, "Plinth beams at ground"),
]
BEAM_TYPE_LENGTHS = (1, 2, 3)
BEAM_PLACEMENT_HEADERS = ("Mark", "TypeMark", "Span", "FromGridX", "FromGridY",
                          "ToGridX", "ToGridY", "Level", unit("Offset"),
                          "Comments")

SLAB_TYPE_HEADERS = ("TypeMark", unit("Thickness"), unit("Cover"), "Concrete",
                     "Comments")
SLAB_TYPES = [("SL-150", 150, 25, CONCRETE, "Typical floor slab")]
SLAB_TYPE_LENGTHS = (1, 2)
SLAB_PLACEMENT_HEADERS = ("Mark", "TypeMark", "Level", "FromGridX", "ToGridX",
                          "FromGridY", "ToGridY", "EdgeRule", unit("Offset"),
                          "Comments")

LOG_HEADERS = ("When", "Job", "Command", "Status", "Counts", "Note")


def typed_rows(rows, length_columns, headers):
    """A TYPES table with each length column converted to *its own* unit.

    Its own, not the workbook's: a cover column stays in millimetres, so the
    conversion has to be asked per column rather than applied to the row.
    """
    converted = []
    for row in rows:
        values = list(row)
        for index in length_columns:
            values[index] = measure(values[index], headers[index])
        converted.append(tuple(values))
    return converted


# ---------------------------------------------------------------------------
# Generating the rows
# ---------------------------------------------------------------------------

def level_rows():
    """Both elevations, and which one is authoritative.

    The survey elevation is written out rather than left to be worked out,
    because the number on a site drawing is the survey one and somebody will
    check this sheet against it.
    """
    rows = []
    for name, elevation, story in LEVELS:
        rows.append((name, length(elevation),
                     length(elevation + SURVEY_OFFSET_MM),
                     ELEVATION_BASES[0], "", story, ""))
    return rows


def grid_rows():
    """Vertical grids run at 90 degrees, horizontal ones at 0."""
    rows = []
    low_y = GRIDS_HORIZONTAL[0][1] - GRID_OVERHANG
    high_y = GRIDS_HORIZONTAL[-1][1] + GRID_OVERHANG
    low_x = GRIDS_VERTICAL[0][1] - GRID_OVERHANG
    high_x = GRIDS_VERTICAL[-1][1] + GRID_OVERHANG

    for name, x in GRIDS_VERTICAL:
        rows.append((name, length(x), length(low_y), length(x),
                     length(high_y), 90, None, "Yes", "Yes", "Vertical"))
    for name, y in GRIDS_HORIZONTAL:
        rows.append((name, length(low_x), length(y), length(high_x),
                     length(y), 0, None, "Yes", "Yes", "Horizontal"))
    return rows


def footing_rows():
    """One pad under every intersection.

    ``OffsetX``/``OffsetY`` are blank: the footing is centred on the grid
    crossing. They are an offset **from** that crossing, so 150 there means
    150 off the grid, not 150 from the origin — which is the only reading that
    survives somebody moving a grid.

    ``Outline`` is blank too, and stays blank for anything rectangular. It is
    where a pad the type cannot describe is written out: combined, stepped, or
    cut round a pit.
    """
    rows = []
    for letter, number in intersections():
        where = position(letter, number)
        rows.append(("F-{0}{1}".format(letter, number),
                     FOOTING_BY_POSITION[where], letter, number, None, None,
                     LEVELS[0][0], 0, 0, "", where.capitalize()))
    return rows


def column_type(code):
    return COLUMN_TYPE_BY_STOREY[code]


def column_rebar(code, letter, number):
    return COLUMN_REBAR[(STOREY_BAND[code], position(letter, number))]


def column_marks():
    """``{(letter, number): mark}`` — the owner's rule, as code.

    Marks are decided **once, at the bottom storey**, by grouping columns on
    what a schedule would group them on: size and rebar together. Two columns
    with the same size and a different cage are two marks. Then the mark is
    carried up the stack unchanged, because a column at A1 called ``C1`` is
    ``C1`` on every floor even where it reduces.

    Which means the mark is not a key. Two positions can share ``C1`` on the
    same floor, and the same ``C1`` at A1 is a different size at the top than
    at the bottom. The key is grid position plus storey, and it always was.
    """
    base = STOREYS[0][0]
    marks = {}
    by_group = {}
    for letter, number in intersections():
        group = (column_type(base), column_rebar(base, letter, number))
        if group not in by_group:
            by_group[group] = "C{0}".format(len(by_group) + 1)
        marks[(letter, number)] = by_group[group]
    return marks


def column_rows():
    """One row per column per storey. Six pours, six rows."""
    marks = column_marks()
    rows = []
    for letter, number in intersections():
        for code, base, top in STOREYS:
            rows.append((marks[(letter, number)], letter, number, None, None,
                         code, base, top, 0, 0, column_type(code),
                         column_rebar(code, letter, number), 0,
                         position(letter, number).capitalize()))
    return rows


def beam_groups():
    """``[[row, ...], ...]`` — one list per beam, one row per span.

    A group of one is a simply supported beam. A group of several is one
    continuous beam over that many spans, and they share a mark because they
    are one beam.
    """
    letters = [name for name, _x in GRIDS_VERTICAL]
    numbers = [name for name, _y in GRIDS_HORIZONTAL]
    groups = []

    for level in FRAMED_LEVELS:
        code = level.split()[0]
        plinth = level == FRAMED_LEVELS[0]
        beam_type = BEAM_TYPES[1][0] if plinth else BEAM_TYPES[0][0]
        note = "Plinth - simply supported" if plinth else "Continuous"

        # Along X: each horizontal grid carries one beam over four bays.
        for number in numbers:
            spans = list(zip(letters, letters[1:]))
            mark = "B{0}-{1}".format(code, number)
            groups.extend(_spans(mark, beam_type, level, note, plinth, [
                (first, number, second, number) for first, second in spans]))

        # Along Y: each vertical grid carries one beam over two bays.
        for letter in letters:
            spans = list(zip(numbers, numbers[1:]))
            mark = "B{0}-{1}".format(code, letter)
            groups.extend(_spans(mark, beam_type, level, note, plinth, [
                (letter, first, letter, second) for first, second in spans]))
    return groups


def _spans(mark, beam_type, level, note, simply_supported, spans):
    """One group per beam — or one group per span, when simply supported.

    A plinth beam between two pedestals is its own beam and carries its own
    mark. A floor beam running the length of a grid line is one beam over
    several spans, and the spans stay together.
    """
    if simply_supported:
        return [[(("{0}-{1}".format(mark, index + 1)), beam_type, 1,
                  from_x, from_y, to_x, to_y, level, 0, note)]
                for index, (from_x, from_y, to_x, to_y) in enumerate(spans)]
    return [[(mark, beam_type, index + 1, from_x, from_y, to_x, to_y, level,
              0, note)
             for index, (from_x, from_y, to_x, to_y) in enumerate(spans)]]


def beam_rows():
    """Every group, with a blank row between them.

    The blank row is not decoration. It is what says where one beam ends and
    the next begins, so continuity is read from the shape of the sheet instead
    of from a column somebody has to remember to keep true.
    """
    blank = ("",) * len(BEAM_PLACEMENT_HEADERS)
    rows = []
    for index, group in enumerate(beam_groups()):
        if index:
            rows.append(blank)
        rows.extend(group)
    return rows


def slab_panels():
    """``[(level, from_letter, to_letter, from_number, to_number)]``.

    One per bay: the four grids around a panel. Not one per floor — a floor is
    poured as panels between its beams, and a single slab over the whole
    footprint would swallow every beam under it in the quantities.
    """
    letters = [name for name, _x in GRIDS_VERTICAL]
    numbers = [name for name, _y in GRIDS_HORIZONTAL]
    panels = []
    for level in SLAB_LEVELS:
        for first_y, second_y in zip(numbers, numbers[1:]):
            for first_x, second_x in zip(letters, letters[1:]):
                panels.append((level, first_x, second_x, first_y, second_y))
    return panels


def slab_rows():
    """One slab per panel, stopping at the inner face of its beams."""
    rows = []
    for level, first_x, second_x, first_y, second_y in slab_panels():
        code = level.split()[0]
        rows.append(("SL{0}-{1}{2}{3}{4}".format(code, first_x, second_x,
                                                 first_y, second_y),
                     SLAB_TYPES[0][0], level, first_x, second_x, first_y,
                     second_y, EDGE_RULES[0], 0, ""))
    return rows


# ---------------------------------------------------------------------------
# Writing it
# ---------------------------------------------------------------------------

def build(target=DEFAULT_TARGET):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    keep_vba = target.lower().endswith(".xlsm")
    history = []
    if os.path.exists(target):
        # Read the old LOG before anything is thrown away, whatever the
        # extension. Only an .xlsm can carry the macros forward, but the record
        # of what was run belongs to the workbook rather than to its format.
        existing = load_workbook(target, keep_vba=keep_vba)
        history = _existing_log(existing)
        if keep_vba:
            book = existing
            for name in list(book.sheetnames):
                del book[name]
            book.create_sheet("CONTROL")
        else:
            book = Workbook()
            book.active.title = "CONTROL"
    else:
        book = Workbook()
        book.active.title = "CONTROL"

    face = FONT_STACK[0]
    head = Font(name=face, size=SIZE_HEADER, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F3864")
    label = Font(name=face, size=SIZE_BODY, bold=True)
    body = Font(name=face, size=SIZE_BODY)
    title = Font(name=face, size=SIZE_TITLE, bold=True)
    note = Font(name=face, size=SIZE_BODY, italic=True)

    def header(sheet, names, row=1):
        for column, name in enumerate(names, start=1):
            cell = sheet.cell(row=row, column=column, value=name)
            cell.font = head
            cell.fill = head_fill
        sheet.freeze_panes = sheet.cell(row=row + 1, column=1)

    def fit(sheet, headers, rows, first=1, header_row=1):
        """Set every column as wide as the widest thing in it.

        Excel's own AutoFit needs Excel; this is the same idea done from the
        numbers, so a workbook is correctly sized the moment it is written
        rather than after somebody double-clicks seven column borders.
        """
        for offset, head in enumerate(headers):
            widest = len(str(head))
            for values in rows:
                if offset >= len(values):
                    continue
                value = values[offset]
                if value is None:
                    continue
                if isinstance(value, float):
                    shown = "{0:,.2f}".format(value)
                else:
                    shown = str(value)
                widest = max(widest, len(shown))
            letter = get_column_letter(first + offset)
            sheet.column_dimensions[letter].width = min(
                WIDTH_MAX, max(WIDTH_MIN, widest + WIDTH_PADDING))
        del header_row

    def shape(sheet, headers, rows, header_row=1):
        """Fonts, row heights and number formats, applied the same way twice."""
        for offset, head in enumerate(headers):
            found = "mm" if "(mm)" in str(head) else (
                "m" if "(m)" in str(head) else None)
            if found is None:
                continue
            for index in range(len(rows)):
                cell = sheet.cell(row=header_row + 1 + index, column=1 + offset)
                cell.number_format = NUMBER_FORMAT[found]
        for index in range(len(rows) + 1):
            sheet.row_dimensions[header_row + index].height = ROW_HEIGHT
        for row in sheet.iter_rows(min_row=header_row,
                                   max_row=header_row + len(rows)):
            for cell in row:
                if cell.font is None or not cell.font.b:
                    cell.font = body

    def table(name, headers, rows):
        sheet = book.create_sheet(name)
        header(sheet, headers)
        for index, values in enumerate(rows):
            for column, value in enumerate(values, start=1):
                sheet.cell(row=2 + index, column=column, value=value)
        fit(sheet, headers, rows)
        shape(sheet, headers, rows)
        return sheet

    def choices(sheet, options, cells):
        rule = DataValidation(type="list",
                              formula1='"{0}"'.format(",".join(options)),
                              allow_blank=True)
        sheet.add_data_validation(rule)
        rule.add(cells)

    # -- CONTROL ------------------------------------------------------------
    control = book["CONTROL"]
    control["A1"] = "AnonGee Bridge - {0}".format(PROJECT)
    control["A1"].font = title
    for index, line in enumerate(CONTROL_NOTES):
        control.cell(row=2 + index, column=1, value=line).font = note

    header(control, CONTROL_HEADERS, row=CONTROL_HEADER_ROW)
    written = []
    for index, (button, command, sheet_name, what, built) in enumerate(COMMANDS):
        row = CONTROL_HEADER_ROW + 1 + index
        control.cell(row=row, column=1, value=button).font = label
        control.cell(row=row, column=2, value=command)
        control.cell(row=row, column=3, value=sheet_name)
        control.cell(row=row, column=4, value=what)
        control.cell(row=row, column=5, value=built)
        control.cell(row=row, column=6, value="No")
        written.append((button, command, sheet_name, what, built, "No"))

    choices(control, ("No", "Yes"), "F{0}:F{1}".format(
        CONTROL_HEADER_ROW + 1, CONTROL_HEADER_ROW + len(COMMANDS)))
    fit(control, CONTROL_HEADERS, written)
    shape(control, CONTROL_HEADERS, written, header_row=CONTROL_HEADER_ROW)
    for index in range(CONTROL_HEADER_ROW):
        control.row_dimensions[1 + index].height = ROW_HEIGHT

    # -- INFO ---------------------------------------------------------------
    #
    # Key, value, description in rows -- not a column table, which is why the
    # unit converter walked straight past it. The key carries the unit now, in
    # the same brackets, in the cell beside the number. BUG-17.
    info = book.create_sheet("INFO")
    rows = info_rows()
    header(info, INFO_HEADERS)
    for index, (key, value, what) in enumerate(rows):
        info.cell(row=2 + index, column=1, value=key).font = label
        cell = info.cell(row=2 + index, column=2, value=value)
        found = "mm" if "(mm)" in key else ("m" if "(m)" in key else None)
        if found:
            cell.number_format = NUMBER_FORMAT[found]
        info.cell(row=2 + index, column=3, value=what)
    units_row = 2 + [key for key, _v, _w in rows].index("UNITS")
    choices(info, ("m", "mm"), "B{0}".format(units_row))
    fit(info, INFO_HEADERS, rows)
    shape(info, INFO_HEADERS, rows)

    # -- the datum ----------------------------------------------------------
    levels = table("LEVELS", LEVEL_HEADERS, level_rows())
    choices(levels, ELEVATION_BASES, "D2:D{0}".format(1 + len(LEVELS)))

    table("GRIDS", GRID_HEADERS, grid_rows())

    # -- the structure ------------------------------------------------------
    table("FOOTING_TYPES", FOOTING_TYPE_HEADERS,
          typed_rows(FOOTING_TYPES, FOOTING_TYPE_LENGTHS,
                     FOOTING_TYPE_HEADERS))
    table("FOOTING_PLACEMENT", FOOTING_PLACEMENT_HEADERS, footing_rows())

    table("COLUMN_TYPES", COLUMN_TYPE_HEADERS,
          typed_rows(COLUMN_TYPES, COLUMN_TYPE_LENGTHS, COLUMN_TYPE_HEADERS))
    table("COLUMN_PLACEMENT", COLUMN_PLACEMENT_HEADERS, column_rows())

    table("BEAM_TYPES", BEAM_TYPE_HEADERS,
          typed_rows(BEAM_TYPES, BEAM_TYPE_LENGTHS, BEAM_TYPE_HEADERS))
    table("BEAM_PLACEMENT", BEAM_PLACEMENT_HEADERS, beam_rows())

    table("SLAB_TYPES", SLAB_TYPE_HEADERS,
          typed_rows(SLAB_TYPES, SLAB_TYPE_LENGTHS, SLAB_TYPE_HEADERS))
    slabs = table("SLAB_PLACEMENT", SLAB_PLACEMENT_HEADERS, slab_rows())
    choices(slabs, EDGE_RULES, "H2:H{0}".format(1 + len(slab_panels())))

    log = table("LOG", LOG_HEADERS, history)
    del log

    book.save(target)
    return target


def _existing_log(book):
    """The LOG rows already in a workbook being rebuilt.

    A rebuild replaces every sheet, and the LOG is the one sheet that is not
    generated — it is what happened. Losing it would mean losing the record of
    what was run and what came back, which is the only evidence a test round
    leaves behind.
    """
    if "LOG" not in book.sheetnames:
        return []
    kept = []
    for row in book["LOG"].iter_rows(min_row=2, values_only=True):
        if any(value not in (None, "") for value in row):
            kept.append(row)
    return kept


def counts():
    return {
        "levels": len(LEVELS),
        "grids": len(GRIDS_VERTICAL) + len(GRIDS_HORIZONTAL),
        "footings": len(footing_rows()),
        "columns": len(column_rows()),
        "beams": sum(len(group) for group in beam_groups()),
        "beam groups": len(beam_groups()),
        "slabs": len(slab_rows()),
    }


def main(argv):
    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    written = build(target)
    print("wrote {0}".format(written))
    print("  units      {0}".format(UNITS))
    for name, count in sorted(counts().items()):
        print("  {0:<11}{1}".format(name, count))
    marks = column_marks()
    print("  column marks: {0}".format(
        ", ".join(sorted(set(marks.values())))))
    if not written.lower().endswith(".xlsm"):
        print("\nSave As .xlsm in Excel, then Alt+F11 -> File -> Import File "
              "-> modAnonGeeBridge.bas. After that, re-run this against the "
              ".xlsm and the macros survive.")
    print("\nIn the workbook, once: Alt+F8 -> AnonGeeBridge_AddButtons.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
