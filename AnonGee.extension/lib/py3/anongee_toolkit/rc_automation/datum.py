# -*- coding: utf-8 -*-
"""Levels and grids, as a sheet describes them and as a model would have to change.

Pure: rows in, plans out, no Revit anywhere. The command that writes to a model
does nothing this file has not already decided, which is what makes the rules
below arguable without opening Revit.

**Four rules, and every one of them is a refusal to be clever.**

*Never delete.* A level in the model that the sheet does not mention is left
alone and reported. Deleting a level takes every view, every sheet reference and
every element hosted on it, and no spreadsheet is worth that.

*Match by name, and only by name.* ``rc_automation.naming`` can match ``Level 1``
to ``01 1st Floor Lvl.`` by storey number, and that is exactly right when a
schedule *refers* to a level somebody else named. Here the sheet **is** the
naming authority, so a fuzzy match would mean silently deciding two differently
named things are the same one. Exact, then case- and space-insensitive, then
nothing.

*Never create a second level at an occupied elevation.* Revit will let you, and
then every plan view in the project has two candidates. If a level already sits
there under another name, that is reported with the name — the fix is a rename
somebody makes on purpose.

*Never rename.* Renaming a level renames what every view and sheet refers to. A
name that does not match is a level that does not exist yet, or a collision
under rule three.
"""

from anongee_toolkit.rc_automation import models

__version__ = "0.1.0"

#: Two elevations within this are the same elevation. Revit stores feet, so a
#: millimetre round trip never lands exactly; anything tighter reports a
#: modification that would change nothing.
ELEVATION_TOLERANCE_MM = 0.5

SHEET_LEVELS = "LEVELS"

#: What the plan decided for one row.
CREATE = "Create"
MODIFY = "Modify"
MATCH = "Matches"
BLOCKED = "Blocked"
INVALID = "Invalid"

#: Column headings this reads, folded, and matched as a **prefix** — because a
#: real sheet writes ``RL (mm)`` and ``Elevation (mm)``, and a reader that
#: demanded the bare word would reject the workbook somebody actually keeps.
#:
#: ``level`` is a name candidate and deliberately not an elevation one. A column
#: headed *Level* is what the level is called; taking it for a height would put
#: the wrong thing in the wrong column silently, and that is the failure mode
#: worth spending a comment on.
_NAME = ("name", "levelname", "level")
_ELEVATION = ("elevation", "height", "rl", "value")
_TYPE = ("leveltype", "type")
_STORY = ("story", "storey", "buildingstory", "isstory")
_COMMENTS = ("comment", "note")


class LevelRow(object):
    """One row of the LEVELS sheet, coerced and remembering where it came from."""

    __slots__ = ("name", "elevation_mm", "level_type", "story", "comments",
                 "row")

    def __init__(self, name, elevation_mm=None, level_type="", story=None,
                 comments="", row=None):
        self.name = name
        self.elevation_mm = elevation_mm
        self.level_type = level_type
        #: ``True``/``False``/``None``. ``None`` means the sheet did not say,
        #: and a thing the sheet did not say is a thing this does not change.
        self.story = story
        self.comments = comments
        #: The spreadsheet row number, so a finding can be typed into the Name
        #: Box.
        self.row = row

    def __repr__(self):
        return "<LevelRow {0!r} at {1}>".format(self.name, self.elevation_mm)


class LevelPlan(object):
    """What one row means for the model."""

    __slots__ = ("row", "action", "reason", "key", "current_mm")

    def __init__(self, row, action=CREATE, reason="", key=None,
                 current_mm=None):
        self.row = row
        self.action = action
        self.reason = reason
        #: Whatever the caller uses to name an existing level — an ``ElementId``
        #: in Revit, a string in a test. Opaque here on purpose.
        self.key = key
        self.current_mm = current_mm

    @property
    def will_write(self):
        return self.action in (CREATE, MODIFY)

    def __repr__(self):
        return "<LevelPlan {0} {1!r}>".format(self.action, self.row.name)


# ---------------------------------------------------------------------------
# Reading the sheet
# ---------------------------------------------------------------------------

def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())


def _header_map(header):
    """``{index: field}`` for the columns this understands."""
    found = {}
    for index, cell in enumerate(header):
        folded = _fold(cell)
        if not folded:
            continue
        for field, names in (("level_type", _TYPE), ("name", _NAME),
                             ("elevation_mm", _ELEVATION), ("story", _STORY),
                             ("comments", _COMMENTS)):
            if field in found.values():
                continue
            if any(folded.startswith(candidate) for candidate in names):
                found[index] = field
                break
    return found


def _number(value):
    """A millimetre value, or ``None``. Tolerates ``"3300 mm"`` and commas."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    kept = []
    for character in text:
        if character.isdigit() or character in "+-.":
            kept.append(character)
        elif kept:
            break
    try:
        return float("".join(kept))
    except ValueError:
        return None


def _yes_no(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return value
    return _fold(value) in ("yes", "y", "true", "1")


def parse_levels(grid, sheet=SHEET_LEVELS):
    """``([LevelRow], [Issue])`` from a sheet's rows.

    The header is found rather than assumed: a real workbook grows a title block
    above the table sooner or later, and a reader that demands row one is a
    reader somebody works around by deleting their own notes.
    """
    issues = []
    rows = list(grid or [])

    header_at = None
    columns = {}
    for index, row in enumerate(rows):
        found = _header_map(row)
        if "name" in found.values() and "elevation_mm" in found.values():
            header_at, columns = index, found
            break

    if header_at is None:
        issues.append(models.Issue(
            models.SEVERITY_ERROR,
            "No header row with a Name and an Elevation column.", sheet=sheet))
        return [], issues

    found = []
    for offset, raw in enumerate(rows[header_at + 1:]):
        values = {}
        for index, field in columns.items():
            values[field] = raw[index] if index < len(raw) else None
        name = str(values.get("name") or "").strip()
        if not name:
            continue                              # a blank row is not an error

        number = _number(values.get("elevation_mm"))
        level_row = LevelRow(
            name, number, str(values.get("level_type") or "").strip(),
            _yes_no(values.get("story")),
            str(values.get("comments") or "").strip(),
            header_at + offset + 2)
        if number is None:
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r} has no elevation this can read.".format(name),
                sheet=sheet, row=level_row.row, column="Elevation"))
        found.append(level_row)

    if not found:
        issues.append(models.Issue(
            models.SEVERITY_WARNING, "The sheet names no levels.", sheet=sheet))
    return found, issues


# ---------------------------------------------------------------------------
# Planning against a model
# ---------------------------------------------------------------------------

def plan_levels(rows, existing, tolerance_mm=ELEVATION_TOLERANCE_MM,
                sheet=SHEET_LEVELS):
    """``([LevelPlan], [Issue])``.

    *existing* is ``[(name, key, elevation_mm)]`` — whatever the caller uses to
    identify a level. Opaque, so this function never learns what Revit is.
    """
    issues = []
    by_name = {}
    by_folded = {}
    for name, key, elevation in existing or ():
        by_name[name] = (key, elevation)
        by_folded.setdefault(_fold(name), (name, key, elevation))

    plans = []
    seen_names = {}
    claimed = set()

    for row in rows:
        folded = _fold(row.name)

        if folded in seen_names:
            plans.append(LevelPlan(row, INVALID, "the sheet already has a "
                                   "level called {0!r} on row {1}".format(
                                       row.name, seen_names[folded])))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r} appears twice.".format(row.name),
                sheet=sheet, row=row.row, column="Name"))
            continue
        seen_names[folded] = row.row

        if row.elevation_mm is None:
            plans.append(LevelPlan(row, INVALID, "no elevation"))
            continue

        match = None
        if row.name in by_name:
            key, elevation = by_name[row.name]
            match = (row.name, key, elevation)
        elif folded in by_folded:
            match = by_folded[folded]

        if match is not None:
            found_name, key, elevation = match
            claimed.add(key)
            if abs(elevation - row.elevation_mm) <= tolerance_mm:
                plans.append(LevelPlan(row, MATCH, "", key, elevation))
            else:
                plans.append(LevelPlan(
                    row, MODIFY,
                    "{0:g} mm in the model, {1:g} mm in the sheet".format(
                        elevation, row.elevation_mm), key, elevation))
            if found_name != row.name:
                issues.append(models.Issue(
                    models.SEVERITY_INFO,
                    "matched {0!r} to the model's {1!r}; levels are never "
                    "renamed, because a rename changes what every view and "
                    "sheet refers to".format(row.name, found_name),
                    sheet=sheet, row=row.row, column="Name"))
            continue

        occupant = _at_elevation(existing, row.elevation_mm, tolerance_mm,
                                 claimed)
        if occupant is not None:
            plans.append(LevelPlan(
                row, BLOCKED,
                "{0!r} is already at {1:g} mm".format(occupant,
                                                      row.elevation_mm)))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "A level called {0!r} already sits at {1:g} mm. Creating a "
                "second one there would give every plan view two candidates — "
                "rename one of them, or change the elevation.".format(
                    occupant, row.elevation_mm),
                sheet=sheet, row=row.row, column="Elevation"))
            continue

        plans.append(LevelPlan(row, CREATE))

    for name, key, elevation in existing or ():
        if key not in claimed:
            issues.append(models.Issue(
                models.SEVERITY_INFO,
                "the model has {0!r} at {1:g} mm and the sheet does not "
                "mention it — left alone".format(name, elevation),
                sheet=sheet))
    return plans, issues


def _at_elevation(existing, elevation_mm, tolerance_mm, claimed):
    """The name of a level already at this height, or ``None``."""
    for name, key, found in existing or ():
        if key in claimed:
            continue
        if abs(found - elevation_mm) <= tolerance_mm:
            return name
    return None


def summarise(plans):
    """``{created: n, modified: n, matched: n, blocked: n, invalid: n}``."""
    counts = {"created": 0, "modified": 0, "matched": 0, "blocked": 0,
              "invalid": 0}
    for action, key in ((CREATE, "created"), (MODIFY, "modified"),
                        (MATCH, "matched"), (BLOCKED, "blocked"),
                        (INVALID, "invalid")):
        counts[key] = len([plan for plan in plans if plan.action == action])
    return counts


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------
# A grid is a line rather than a number, so it needs two things levels do not:
# a way to say where it runs, and a rule for what counts as "already there".
#
# **Angle is 0 along +X and 90 along +Y** — a horizontal grid is 0, a vertical
# one is 90, and a skewed one is whatever it is. Requested by the project owner
# after adding the column to a real sheet, and the convention is theirs.
#
# **A grid's position is synced; its extent is not.** Grid extents are adjusted
# by hand in nearly every view of a real project, so comparing endpoints would
# report every one of them as needing a change and then undo somebody's work.
# Two grids on the same infinite line are the same grid, whatever their lengths.

SHEET_GRIDS = "GRIDS"

#: Two points within this are the same point, and two directions within this
#: many degrees are the same direction.
POSITION_TOLERANCE_MM = 1.0
ANGLE_TOLERANCE_DEG = 0.05

#: When a row gives an angle but no second point and no length. Real sheets do
#: this — "grid A runs north" — and something has to decide how far. The extent
#: of every explicitly drawn grid in the same sheet is the honest answer;
#: this is the fallback when there are none.
DEFAULT_GRID_LENGTH_MM = 20000.0

_GRID_NAME = ("name", "grid", "gridname")
_X1 = ("x1", "startx", "xstart", "x")
_Y1 = ("y1", "starty", "ystart", "y")
_X2 = ("x2", "endx", "xend")
_Y2 = ("y2", "endy", "yend")
_ANGLE = ("angle", "bearing", "rotation")
_LENGTH = ("length", "extent", "run")
_BUBBLE_START = ("bubblestart", "startbubble", "bubble1")
_BUBBLE_END = ("bubbleend", "endbubble", "bubble2")

_GRID_FIELDS = (("bubble_start", _BUBBLE_START), ("bubble_end", _BUBBLE_END),
                ("x1", _X1), ("y1", _Y1), ("x2", _X2), ("y2", _Y2),
                ("angle_deg", _ANGLE), ("length_mm", _LENGTH),
                ("name", _GRID_NAME), ("comments", _COMMENTS))


class GridRow(object):
    """One row of the GRIDS sheet."""

    __slots__ = ("name", "x1", "y1", "x2", "y2", "angle_deg", "length_mm",
                 "bubble_start", "bubble_end", "comments", "row")

    def __init__(self, name, x1=None, y1=None, x2=None, y2=None,
                 angle_deg=None, length_mm=None, bubble_start=None,
                 bubble_end=None, comments="", row=None):
        self.name = name
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        #: 0 along +X, 90 along +Y. ``None`` means the row did not say.
        self.angle_deg = angle_deg
        self.length_mm = length_mm
        self.bubble_start = bubble_start
        self.bubble_end = bubble_end
        self.comments = comments
        self.row = row

    def __repr__(self):
        return "<GridRow {0!r}>".format(self.name)


class GridPlan(object):
    """What one grid row means for the model."""

    __slots__ = ("row", "action", "reason", "key", "line", "current_line")

    def __init__(self, row, action=CREATE, reason="", key=None, line=None,
                 current_line=None):
        self.row = row
        self.action = action
        self.reason = reason
        self.key = key
        #: ``((x1, y1), (x2, y2))`` in millimetres, resolved from whichever of
        #: the columns the row actually filled in.
        self.line = line
        self.current_line = current_line

    @property
    def will_write(self):
        return self.action in (CREATE, MODIFY)

    def __repr__(self):
        return "<GridPlan {0} {1!r}>".format(self.action, self.row.name)


def parse_grids(grid, sheet=SHEET_GRIDS):
    """``([GridRow], [Issue])``. Same header rules as the levels sheet."""
    issues = []
    rows = list(grid or [])

    header_at = None
    columns = {}
    for index, row in enumerate(rows):
        found = _grid_header(row)
        if "name" in found.values() and "x1" in found.values():
            header_at, columns = index, found
            break

    if header_at is None:
        issues.append(models.Issue(
            models.SEVERITY_ERROR,
            "No header row with a Name and an X1 column.", sheet=sheet))
        return [], issues

    found = []
    for offset, raw in enumerate(rows[header_at + 1:]):
        values = {}
        for index, field in columns.items():
            values[field] = raw[index] if index < len(raw) else None
        name = str(values.get("name") or "").strip()
        if not name:
            continue
        found.append(GridRow(
            name,
            _number(values.get("x1")), _number(values.get("y1")),
            _number(values.get("x2")), _number(values.get("y2")),
            _number(values.get("angle_deg")), _number(values.get("length_mm")),
            _yes_no(values.get("bubble_start")),
            _yes_no(values.get("bubble_end")),
            str(values.get("comments") or "").strip(),
            header_at + offset + 2))

    if not found:
        issues.append(models.Issue(
            models.SEVERITY_WARNING, "The sheet names no grids.", sheet=sheet))
    return found, issues


def _grid_header(header):
    """``{index: field}``. Longest names first, so ``X1`` cannot eat ``X2``."""
    found = {}
    for index, cell in enumerate(header):
        folded = _fold(cell)
        if not folded:
            continue
        for field, names in _GRID_FIELDS:
            if field in found.values():
                continue
            if any(folded.startswith(candidate) for candidate in names):
                found[index] = field
                break
    return found


def _direction(angle_deg):
    """A unit vector for an angle in degrees. 0 is +X, 90 is +Y."""
    import math
    radians = math.radians(angle_deg)
    return math.cos(radians), math.sin(radians)


def _angle_of(line):
    """The angle of a line in degrees, folded into 0 <= angle < 180.

    A grid drawn left-to-right and the same grid drawn right-to-left are one
    grid, so direction is taken modulo half a turn throughout.
    """
    import math
    (x1, y1), (x2, y2) = line
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
    return angle


def default_length(rows, fallback=DEFAULT_GRID_LENGTH_MM):
    """How long to draw a grid that gave an angle and no extent.

    Measured across every grid in the sheet that *did* say — which is what makes
    a mixed sheet come out looking deliberate rather than ragged.
    """
    points = []
    for row in rows:
        for x, y in ((row.x1, row.y1), (row.x2, row.y2)):
            if x is not None and y is not None:
                points.append((x, y))
    if len(points) < 2:
        return fallback
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return span if span > 0 else fallback


def grid_line(row, length_mm=None):
    """``(line, note)`` — where this row's grid runs, or ``(None, why not)``.

    Three ways a row can say it, in order of how definite they are:

    1. **Both ends given.** That is the line. An angle in the same row is then
       a claim about it, and a claim that disagrees is worth a word — but the
       points win, because they are the more specific statement.
    2. **A start and an angle.** The length is the row's own, or the sheet's
       overall extent.
    3. **Anything else** is not a grid yet.
    """
    if row.x1 is None or row.y1 is None:
        return None, "no start point"

    if row.x2 is not None and row.y2 is not None:
        line = ((row.x1, row.y1), (row.x2, row.y2))
        if abs(row.x2 - row.x1) < 1e-9 and abs(row.y2 - row.y1) < 1e-9:
            return None, "both ends are the same point"
        if row.angle_deg is not None:
            drawn = _angle_of(line)
            wanted = row.angle_deg % 180.0
            if _angle_gap(drawn, wanted) > ANGLE_TOLERANCE_DEG:
                return line, ("the points run at {0:g}\u00b0 and the Angle "
                              "column says {1:g}\u00b0 - the points win, "
                              "because they say more".format(drawn,
                                                             row.angle_deg))
        return line, ""

    if row.angle_deg is None:
        return None, "no end point and no angle"

    run = row.length_mm or length_mm or DEFAULT_GRID_LENGTH_MM
    across, up = _direction(row.angle_deg)
    return ((row.x1, row.y1),
            (row.x1 + across * run, row.y1 + up * run)), ""


def _angle_gap(first, second):
    """How far apart two directions are, modulo half a turn."""
    gap = abs((first % 180.0) - (second % 180.0)) % 180.0
    return min(gap, 180.0 - gap)


def same_line(first, second, position_tolerance_mm=POSITION_TOLERANCE_MM,
              angle_tolerance_deg=ANGLE_TOLERANCE_DEG):
    """Are these the same infinite line?

    **Not the same segment.** Grid extents are adjusted by hand in nearly every
    view of a real project; comparing endpoints would report all of them as
    needing a change and then undo the work. Same direction, and one line's
    start sitting on the other, is the same grid.
    """
    if first is None or second is None:
        return False
    if _angle_gap(_angle_of(first), _angle_of(second)) > angle_tolerance_deg:
        return False
    return _distance_to_line(first[0], second) <= position_tolerance_mm


def _distance_to_line(point, line):
    """Perpendicular distance from a point to an infinite line."""
    (x1, y1), (x2, y2) = line
    px, py = point
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    return abs(dy * (px - x1) - dx * (py - y1)) / length


def plan_grids(rows, existing, sheet=SHEET_GRIDS):
    """``([GridPlan], [Issue])``.

    *existing* is ``[(name, key, line)]`` with *line* as ``((x1, y1), (x2, y2))``
    in millimetres. The same four refusals as levels, plus one that is specific
    to a thing with a direction: **a grid whose line runs a different way is not
    moved.** Changing a grid's direction means recreating it, which loses
    anything dimensioned or constrained to it — so that is reported and left.
    """
    issues = []
    by_name = {}
    by_folded = {}
    for name, key, line in existing or ():
        by_name[name] = (key, line)
        by_folded.setdefault(_fold(name), (name, key, line))

    length = default_length(rows)
    plans = []
    seen = {}
    claimed = set()

    for row in rows:
        folded = _fold(row.name)
        if folded in seen:
            plans.append(GridPlan(row, INVALID,
                                  "the sheet already has a grid called "
                                  "{0!r} on row {1}".format(row.name,
                                                            seen[folded])))
            issues.append(models.Issue(
                models.SEVERITY_ERROR, "{0!r} appears twice.".format(row.name),
                sheet=sheet, row=row.row, column="Name"))
            continue
        seen[folded] = row.row

        line, note = grid_line(row, length)
        if line is None:
            plans.append(GridPlan(row, INVALID, note))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "{0!r}: {1}.".format(row.name, note),
                sheet=sheet, row=row.row, column="X1"))
            continue
        if note:
            issues.append(models.Issue(
                models.SEVERITY_WARNING, "{0!r}: {1}".format(row.name, note),
                sheet=sheet, row=row.row, column="Angle"))

        match = None
        if row.name in by_name:
            key, found_line = by_name[row.name]
            match = (row.name, key, found_line)
        elif folded in by_folded:
            match = by_folded[folded]

        if match is not None:
            found_name, key, found_line = match
            claimed.add(key)
            if same_line(line, found_line):
                plans.append(GridPlan(row, MATCH, "", key, line, found_line))
            elif _angle_gap(_angle_of(line),
                            _angle_of(found_line)) > ANGLE_TOLERANCE_DEG:
                plans.append(GridPlan(
                    row, BLOCKED,
                    "runs at {0:g}\u00b0 in the model and {1:g}\u00b0 in the "
                    "sheet".format(_angle_of(found_line), _angle_of(line)),
                    key, line, found_line))
                issues.append(models.Issue(
                    models.SEVERITY_ERROR,
                    "{0!r} runs at a different angle in the model. Changing a "
                    "grid's direction means recreating it, which loses "
                    "anything dimensioned or constrained to it - so this one "
                    "is left alone.".format(row.name),
                    sheet=sheet, row=row.row, column="Angle"))
            else:
                plans.append(GridPlan(row, MODIFY, "moved to the sheet's "
                                      "position", key, line, found_line))
            if found_name != row.name:
                issues.append(models.Issue(
                    models.SEVERITY_INFO,
                    "matched {0!r} to the model's {1!r}; grids are never "
                    "renamed".format(row.name, found_name),
                    sheet=sheet, row=row.row, column="Name"))
            continue

        occupant = _on_line(existing, line, claimed)
        if occupant is not None:
            plans.append(GridPlan(row, BLOCKED,
                                  "{0!r} is already on that line".format(
                                      occupant), None, line))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "A grid called {0!r} already runs along that line. Creating a "
                "second one there would put two labels on one line - rename "
                "one of them, or move it.".format(occupant),
                sheet=sheet, row=row.row, column="Name"))
            continue

        plans.append(GridPlan(row, CREATE, "", None, line))

    for name, key, line in existing or ():
        if key not in claimed:
            issues.append(models.Issue(
                models.SEVERITY_INFO,
                "the model has a grid called {0!r} that the sheet does not "
                "mention - left alone".format(name), sheet=sheet))
    return plans, issues


def _on_line(existing, line, claimed):
    for name, key, found in existing or ():
        if key in claimed:
            continue
        if same_line(line, found):
            return name
    return None


def summarise_grids(plans):
    return summarise(plans)
