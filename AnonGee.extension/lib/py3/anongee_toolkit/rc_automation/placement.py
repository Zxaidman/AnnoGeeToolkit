# -*- coding: utf-8 -*-
"""Where a column or a footing goes, decided before any of it touches Revit.

Pure: rows in, plans out, no Revit anywhere. Same seam as ``datum`` — the
command that writes does nothing this file has not already decided, so the rules
below can be argued with, and tested, without opening a model.

**The key is the position, not the mark.** This is the rule the whole file turns
on, and it is the project owner's:

    A column at A1 marked ``C1`` is ``C1`` all the way up, even where its size
    changes. Two columns share a mark on one floor only if their size *and*
    rebar schedule are both the same.

So a mark is a schedule label, repeated on purpose, and it cannot be what a
second run matches on. What identifies a column is **where it stands and which
storey it is in**; what identifies a footing is **where it stands**. That is what
gets matched, and it is why running twice is safe.

**Nothing is deleted, ever.** An element in the model the sheet does not mention
is left alone and reported. A sheet is one person's view of a building and a
model is everybody's.

**Nothing is moved by default.** A column found within tolerance of where the
sheet wants one *is* that column. A column found nowhere near is not the same
column, so a new one is planned and the odd one is reported — moving it would
mean deciding that somebody's deliberate offset was a mistake.
"""

from anongee_toolkit.rc_automation import datum
from anongee_toolkit.rc_automation import models

__version__ = "0.1.0"

SHEET_COLUMNS = "COLUMN_PLACEMENT"
SHEET_FOOTINGS = "FOOTING_PLACEMENT"

#: Two positions within this are the same position. Generous on purpose: it is
#: the round trip through Revit's feet plus whatever a person typed, not a
#: statement about how accurately anything is built.
POSITION_TOLERANCE_MM = 5.0

CREATE = datum.CREATE
MODIFY = datum.MODIFY
MATCH = datum.MATCH
BLOCKED = datum.BLOCKED
INVALID = datum.INVALID

_MARK = ("mark", "id", "ref")
_TYPE_MARK = ("typemark", "type", "section", "size")
_GRID_X = ("gridx", "gridalongx", "gridletter", "grid1")
_GRID_Y = ("gridy", "gridalongy", "gridnumber", "grid2")
_OFFSET_X = ("offsetx", "dx", "ex")
_OFFSET_Y = ("offsety", "dy", "ey")
_STOREY = ("storey", "story", "lift", "stage")
_BASE_LEVEL = ("baselevel", "frombase", "bottomlevel")
_TOP_LEVEL = ("toplevel", "totop", "uptolevel")
_BASE_OFFSET = ("baseoffset", "bottomoffset")
_TOP_OFFSET = ("topoffset", "toffset")
_LEVEL = ("level", "onlevel", "atlevel")
_ROTATION = ("rotation", "angle", "turn")
_REBAR = ("rebarschedule", "rebar", "cage", "schedule")
_OUTLINE = ("outline", "polygon", "shape")
_COMMENTS = ("comment", "note")

#: Order matters for the same reason it does in ``datum``: several of these
#: start with the same word. ``BaseOffset`` must be asked before ``BaseLevel``
#: would swallow it, and ``TopLevel`` before ``TopOffset`` — every pair that
#: shares a prefix is ordered longest-first.
_COLUMN_FIELDS = (
    ("type_mark", _TYPE_MARK), ("rebar", _REBAR),
    ("base_offset_mm", _BASE_OFFSET), ("top_offset_mm", _TOP_OFFSET),
    ("base_level", _BASE_LEVEL), ("top_level", _TOP_LEVEL),
    ("offset_x_mm", _OFFSET_X), ("offset_y_mm", _OFFSET_Y),
    ("grid_x", _GRID_X), ("grid_y", _GRID_Y),
    ("storey", _STOREY), ("rotation_deg", _ROTATION),
    ("mark", _MARK), ("comments", _COMMENTS),
)

_FOOTING_FIELDS = (
    ("type_mark", _TYPE_MARK),
    ("top_offset_mm", _TOP_OFFSET),
    ("offset_x_mm", _OFFSET_X), ("offset_y_mm", _OFFSET_Y),
    ("grid_x", _GRID_X), ("grid_y", _GRID_Y),
    ("level", _LEVEL), ("rotation_deg", _ROTATION),
    ("outline", _OUTLINE), ("mark", _MARK), ("comments", _COMMENTS),
)


class PlacementRow(object):
    """One row of a placement sheet, coerced and remembering where it came from.

    One class for both, because a column and a footing differ in what they span
    rather than in how they are found. Fields the sheet did not carry are
    ``None``, and ``None`` means *the sheet did not say* — never zero.
    """

    __slots__ = ("mark", "type_mark", "grid_x", "grid_y", "offset_x_mm",
                 "offset_y_mm", "storey", "base_level", "top_level",
                 "base_offset_mm", "top_offset_mm", "level", "rotation_deg",
                 "rebar", "outline", "comments", "row", "point_mm")

    def __init__(self, row=None, **fields):
        for name in self.__slots__:
            setattr(self, name, fields.get(name))
        self.row = row
        #: Filled in by :func:`locate`, once the grids are known.
        self.point_mm = None

    @property
    def key(self):
        """What a second run matches on.

        Position and storey — not the mark, which repeats by design. A row with
        no storey (a footing) keys on position alone, which is right: there is
        one footing under an intersection.
        """
        return (self.grid_x, self.grid_y, self.storey or "",
                round(self.offset_x_mm or 0.0, 1),
                round(self.offset_y_mm or 0.0, 1))

    def __repr__(self):
        return "<PlacementRow {0!r} at {1}{2}>".format(
            self.mark, self.grid_x, self.grid_y)


class PlacementPlan(object):
    """What one row means for the model."""

    __slots__ = ("row", "action", "reason", "existing")

    def __init__(self, row, action=CREATE, reason="", existing=None):
        self.row = row
        self.action = action
        self.reason = reason
        #: Whatever the caller uses to name an element it already found.
        self.existing = existing

    @property
    def will_write(self):
        return self.action in (CREATE, MODIFY)

    def __repr__(self):
        return "<PlacementPlan {0} {1!r}>".format(self.action, self.row.mark)


# ---------------------------------------------------------------------------
# Reading a sheet
# ---------------------------------------------------------------------------

def _header_map(header, fields):
    found = {}
    for index, cell in enumerate(header):
        folded = datum._fold(cell)
        if not folded:
            continue
        for field, names in fields:
            if field in found.values():
                continue
            if any(folded.startswith(candidate) for candidate in names):
                found[index] = field
                break
    return found


def _text(value):
    return str(value if value is not None else "").strip()


def parse(grid, fields, required, sheet, units=datum.UNITS_MM):
    """``([PlacementRow], [Issue])`` from a sheet's rows.

    *required* is the folded field every table must have for the header to be
    the header — the same trick ``datum`` uses, and for the same reason: a real
    workbook grows a title above its table sooner or later.

    **A blank row is skipped, not failed.** On the beam sheet a blank row means
    something; here it means somebody pressed Enter.
    """
    issues = []
    rows = list(grid or [])

    header_at = None
    columns = {}
    for index, row in enumerate(rows):
        found = _header_map(row, fields)
        if all(name in found.values() for name in required):
            header_at, columns = index, found
            break

    if header_at is None:
        issues.append(models.Issue(
            models.SEVERITY_ERROR,
            "No header row with {0}.".format(" and a ".join(required)),
            sheet=sheet))
        return [], issues

    column_units = {}
    for index, field in columns.items():
        found = None
        if index < len(rows[header_at]):
            found = datum.unit_in_header(rows[header_at][index])
        column_units[field] = found or units

    found_rows = []
    for offset, raw in enumerate(rows[header_at + 1:]):
        values = {}
        for index, field in columns.items():
            values[field] = raw[index] if index < len(raw) else None
        if not any(_text(value) for value in values.values()):
            continue

        fields_out = {}
        for field in [name for name, _names in fields]:
            value = values.get(field)
            if field.endswith("_mm"):
                fields_out[field] = datum.to_mm(datum._number(value),
                                                column_units.get(field, units))
            elif field.endswith("_deg"):
                fields_out[field] = datum._number(value)
            else:
                fields_out[field] = _text(value)

        found_rows.append(PlacementRow(row=header_at + offset + 2,
                                       **fields_out))

    if not found_rows:
        issues.append(models.Issue(
            models.SEVERITY_WARNING, "The sheet places nothing.", sheet=sheet))
    return found_rows, issues


def parse_columns(grid, sheet=SHEET_COLUMNS, units=datum.UNITS_MM):
    """``([PlacementRow], [Issue])`` from COLUMN_PLACEMENT."""
    return parse(grid, _COLUMN_FIELDS, ("mark", "grid_x"), sheet, units)


def parse_footings(grid, sheet=SHEET_FOOTINGS, units=datum.UNITS_MM):
    """``([PlacementRow], [Issue])`` from FOOTING_PLACEMENT."""
    return parse(grid, _FOOTING_FIELDS, ("mark", "grid_x"), sheet, units)


_LENGTH = ("length", "l")
_WIDTH = ("width", "w", "breadth", "b")
_THICKNESS = ("thickness", "depth", "d", "t")

_TYPE_FIELDS = (("type_mark", _TYPE_MARK), ("thickness_mm", _THICKNESS),
                ("length_mm", _LENGTH), ("width_mm", _WIDTH))


def parse_types(grid, sheet="", units=datum.UNITS_MM):
    """``({type mark: {field: mm}}, [Issue])`` from a TYPES sheet.

    A placement row names a type and a type sheet says how big it is. Keeping
    those apart is what lets fifteen footings share three sizes, and it is why
    a placement row can leave ``Outline`` blank — the rectangle is the type's,
    not the row's.
    """
    issues = []
    rows = list(grid or [])

    header_at = None
    columns = {}
    for index, row in enumerate(rows):
        found = _header_map(row, _TYPE_FIELDS)
        if "type_mark" in found.values():
            header_at, columns = index, found
            break

    if header_at is None:
        issues.append(models.Issue(
            models.SEVERITY_WARNING,
            "No header row with a TypeMark column.", sheet=sheet))
        return {}, issues

    column_units = {}
    for index, field in columns.items():
        found = None
        if index < len(rows[header_at]):
            found = datum.unit_in_header(rows[header_at][index])
        column_units[field] = found or units

    types = {}
    for raw in rows[header_at + 1:]:
        values = {}
        for index, field in columns.items():
            values[field] = raw[index] if index < len(raw) else None
        mark = _text(values.get("type_mark"))
        if not mark:
            continue
        sizes = {}
        for field in ("length_mm", "width_mm", "thickness_mm"):
            sizes[field] = datum.to_mm(datum._number(values.get(field)),
                                       column_units.get(field, units))
        types[datum._fold(mark)] = sizes
    return types, issues


# ---------------------------------------------------------------------------
# Working out where that is
# ---------------------------------------------------------------------------

def locate(rows, intersection, sheet=SHEET_COLUMNS):
    """Fill in ``point_mm`` on every row. ``[Issue]``.

    *intersection* is ``(name_x, name_y) -> ((x, y), note)`` — whatever the
    caller uses to cross two grids. Opaque here, so this function never learns
    what Revit is.

    **The grid is asked first and the offset is added to it.** A row that names
    no grid falls back to its offsets read as absolute coordinates, which is the
    only way to describe a position in a model that has no grids in it yet. A
    row that names a grid the model does not have is reported and left without
    a point, which makes it unbuildable rather than built in the wrong place.
    """
    issues = []
    for row in rows:
        if row.grid_x and row.grid_y:
            point, note = intersection(row.grid_x, row.grid_y)
            if point is None:
                issues.append(models.Issue(
                    models.SEVERITY_ERROR,
                    "{0!r}: {1}".format(row.mark or "this row", note),
                    sheet=sheet, row=row.row, column="GridX"))
                continue
            row.point_mm = (point[0] + (row.offset_x_mm or 0.0),
                            point[1] + (row.offset_y_mm or 0.0))
            continue

        if row.offset_x_mm is None or row.offset_y_mm is None:
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r} names no grid and gives no coordinates, so there is "
                "nowhere to put it.".format(row.mark or "this row"),
                sheet=sheet, row=row.row, column="GridX"))
            continue

        # No grid named: the offsets are the position, measured from the
        # project origin. Reported, because it is unusual enough to be worth
        # seeing in a run that otherwise reads as ordinary.
        row.point_mm = (row.offset_x_mm, row.offset_y_mm)
        issues.append(models.Issue(
            models.SEVERITY_INFO,
            "{0!r} names no grid, so its offsets are being read as absolute "
            "coordinates.".format(row.mark or "this row"),
            sheet=sheet, row=row.row, column="OffsetX"))
    return issues


def near(first, second, tolerance_mm=POSITION_TOLERANCE_MM):
    """True when two millimetre points are the same point."""
    if first is None or second is None:
        return False
    return (abs(first[0] - second[0]) <= tolerance_mm
            and abs(first[1] - second[1]) <= tolerance_mm)


# ---------------------------------------------------------------------------
# Deciding what to do about it
# ---------------------------------------------------------------------------

def plan(rows, existing, sheet=SHEET_COLUMNS,
         tolerance_mm=POSITION_TOLERANCE_MM, span=True):
    """``([PlacementPlan], [Issue])``.

    *existing* is ``[(key, point_mm, level_name, type_name)]`` — whatever the
    caller uses to identify an element it already has. Opaque on purpose.

    *span* says whether an element belongs to a storey (a column) or sits on one
    level (a footing), which is the only place the two differ.
    """
    issues = []
    plans = []
    seen = {}
    claimed = set()

    for row in rows:
        if not row.mark:
            plans.append(PlacementPlan(row, INVALID, "no mark"))
            continue

        if row.point_mm is None:
            plans.append(PlacementPlan(row, INVALID, "nowhere to put it"))
            continue

        if not row.type_mark:
            plans.append(PlacementPlan(row, INVALID, "no type"))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r} names no type, so there is nothing to place.".format(
                    row.mark),
                sheet=sheet, row=row.row, column="TypeMark"))
            continue

        wanted_level = row.base_level if span else row.level
        if not wanted_level:
            plans.append(PlacementPlan(row, INVALID, "no level"))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r} names no level.".format(row.mark),
                sheet=sheet, row=row.row,
                column="BaseLevel" if span else "Level"))
            continue

        if row.key in seen:
            plans.append(PlacementPlan(
                row, INVALID,
                "row {0} already puts something here".format(seen[row.key])))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "Two rows place an element at the same spot: {0!r} and the "
                "one on row {1}. One of them is a typo.".format(
                    row.mark, seen[row.key]),
                sheet=sheet, row=row.row, column="GridX"))
            continue
        seen[row.key] = row.row

        match = _find(existing, row, wanted_level, tolerance_mm, claimed)
        if match is None:
            plans.append(PlacementPlan(row, CREATE))
            continue

        key, _point, _level, type_name = match
        claimed.add(key)
        if type_name and row.type_mark and not _same_type(type_name,
                                                          row.type_mark):
            plans.append(PlacementPlan(
                row, MODIFY,
                "is {0} in the model, {1} in the sheet".format(
                    type_name, row.type_mark), key))
        else:
            plans.append(PlacementPlan(row, MATCH, "", key))

    for key, point, level, _type_name in existing or ():
        if key not in claimed:
            issues.append(models.Issue(
                models.SEVERITY_INFO,
                "the model has something at {0} on {1} that the sheet does "
                "not mention. Nothing is ever deleted, so it has been left "
                "alone.".format(_where(point), level),
                sheet=sheet))
    return plans, issues


def _find(existing, row, wanted_level, tolerance_mm, claimed):
    """The element already standing where this row wants one, or ``None``."""
    for entry in existing or ():
        key, point, level, _type_name = entry
        if key in claimed:
            continue
        if not near(point, row.point_mm, tolerance_mm):
            continue
        if wanted_level and level and datum._fold(level) != datum._fold(
                wanted_level):
            continue
        return entry
    return None


def _same_type(model_name, sheet_name):
    """Whether a type name in the model is the one the sheet asked for.

    Folded and *contained*, not equal: a sheet says ``C-300x600`` and Revit
    holds ``AnonGee Rect Column : C-300x600``. Demanding equality would report
    every single element as needing a change, on every run, for ever.
    """
    model, wanted = datum._fold(model_name), datum._fold(sheet_name)
    return wanted in model or model in wanted


def _where(point):
    if not point:
        return "an unknown position"
    return "{0:.0f}, {1:.0f}".format(point[0], point[1])


def summarise(plans):
    """``{created, modified, matched, blocked, invalid}`` for a run's report."""
    counts = {"created": 0, "modified": 0, "matched": 0, "blocked": 0,
              "invalid": 0}
    for item in plans:
        counts[{CREATE: "created", MODIFY: "modified", MATCH: "matched",
                BLOCKED: "blocked", INVALID: "invalid"}[item.action]] += 1
    return counts
