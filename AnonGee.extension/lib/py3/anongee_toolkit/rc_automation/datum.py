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
RENAME = "Rename"
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

#: A level has two elevations and one authority. The Project Base Point is what
#: Revit calls a level's elevation; the Survey Point is what the site drawing
#: says, and the two differ by wherever the survey point was put. Both are
#: written, ``ElevationBase`` says which one drives, and a disagreement between
#: them is reported rather than resolved — because resolving it means deciding
#: whose drawing is wrong.
_ELEVATION_SURVEY = ("elevationsurvey", "surveyelevation", "survey")
_ELEVATION_BASE = ("elevationbase", "basepoint", "datum")

#: What ``ElevationBase`` may say. The first is the default and the one Revit
#: writes when nothing says otherwise.
BASE_PROJECT = "Project Base Point"
BASE_SURVEY = "Survey Point"

#: The level this row replaces. A template ships with ``Level 0`` at 0.000 and
#: a real sheet asks for ``01 GROUND LVL.`` at 0.000 — which the *never create a
#: second level at an occupied elevation* rule refuses, correctly, and then
#: every column naming the level that was never created fails too.
#:
#: Naming the level to be renamed is how a row asks for that, explicitly. The
#: rule is not weakened for anything that does not ask, and renaming stays
#: something somebody wrote down — which is what the refusal was protecting.
_RENAME_FROM = ("renamefrom", "replaces", "wasnamed", "oldname")

_TYPE = ("leveltype", "type")
_STORY = ("story", "storey", "buildingstory", "isstory")
_COMMENTS = ("comment", "note")


class LevelRow(object):
    """One row of the LEVELS sheet, coerced and remembering where it came from."""

    __slots__ = ("name", "elevation_mm", "level_type", "story", "comments",
                 "row", "elevation_survey_mm", "elevation_base",
                 "rename_from")

    def __init__(self, name, elevation_mm=None, level_type="", story=None,
                 comments="", row=None, elevation_survey_mm=None,
                 elevation_base="", rename_from=""):
        self.name = name
        #: The Project Base Point elevation, in millimetres. This is what gets
        #: written, whichever column the sheet said was authoritative — see
        #: :func:`resolve_elevations`, which is what makes that true.
        self.elevation_mm = elevation_mm
        #: What the survey drawing reads at this level, if the sheet said.
        self.elevation_survey_mm = elevation_survey_mm
        #: Which of the two the sheet means. Blank is the project base point.
        self.elevation_base = elevation_base
        #: The existing level this row renames rather than being blocked by.
        self.rename_from = rename_from
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
        return self.action in (CREATE, MODIFY, RENAME)

    def __repr__(self):
        return "<LevelPlan {0} {1!r}>".format(self.action, self.row.name)


# ---------------------------------------------------------------------------
# Reading the sheet
# ---------------------------------------------------------------------------

def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())


#: Every length this reads is millimetres inside. The workbook says what its
#: numbers are, and they are converted once, on the way in.
#:
#: This is not a nicety. A LEVELS sheet in metres read as millimetres puts the
#: terrace at 16.5 mm, and every level in the building lands inside the slab
#: thickness of the one below. It would build, and it would look like nothing
#: happened.
UNITS_MM = "mm"
UNITS_M = "m"
UNIT_SCALE_TO_MM = {UNITS_MM: 1.0, UNITS_M: 1000.0}


def normalise_unit(text, fallback=UNITS_MM):
    """``"mm"`` or ``"m"`` from whatever was written, or the fallback.

    The fallback is millimetres because every workbook before the unit existed
    was in millimetres, and a default that silently rescales one of those by a
    thousand is not a default.
    """
    folded = _fold(text)
    if not folded:
        return fallback
    if folded.startswith("mm") or folded.startswith("millim"):
        return UNITS_MM
    if folded.startswith("m"):
        return UNITS_M
    return fallback


def unit_in_header(text):
    """The unit a header declares in brackets — ``Elevation PBP (m)`` — or None.

    A column that names its own unit is a column that cannot be misread after
    somebody rescales half a sheet by hand, so the header wins over whatever
    the job says the workbook is in.
    """
    folded = _fold(text)
    for suffix, value in (("mm", UNITS_MM), ("m", UNITS_M)):
        if folded.endswith(suffix) and _bracketed(text, suffix):
            return value
    return None


def _bracketed(text, suffix):
    """True when ``text`` ends with ``(<suffix>)``, spacing and case aside."""
    stripped = str(text or "").strip().lower().rstrip()
    return stripped.endswith("({0})".format(suffix))


def to_mm(value, units=UNITS_MM):
    """A number in ``units``, in millimetres."""
    if value is None:
        return None
    return float(value) * UNIT_SCALE_TO_MM.get(units, 1.0)


def _header_map(header):
    """``{index: field}`` for the columns this understands."""
    found = {}
    for index, cell in enumerate(header):
        folded = _fold(cell)
        if not folded:
            continue
        # Order matters, and it is not alphabetical. "Elevation Survey" and
        # "ElevationBase" both start with the word Elevation, so the specific
        # ones are asked first — otherwise the survey column would be taken
        # for the elevation and the level would be built 100 m in the air.
        for field, names in (("level_type", _TYPE),
                             ("rename_from", _RENAME_FROM),
                             ("elevation_base", _ELEVATION_BASE),
                             ("elevation_survey_mm", _ELEVATION_SURVEY),
                             ("name", _NAME),
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


def _header_units(header, columns):
    """``{index: unit}`` for the columns whose header names one."""
    units = {}
    for index in columns:
        if index < len(header):
            found = unit_in_header(header[index])
            if found:
                units[index] = found
    return units


def parse_levels(grid, sheet=SHEET_LEVELS, units=UNITS_MM):
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

    # A column that names its own unit wins over the job's. The header is
    # beside the number; the job's option is somewhere else entirely.
    column_units = _header_units(rows[header_at], columns)
    by_field = {}
    for index, field in columns.items():
        by_field[field] = column_units.get(index, units)

    found = []
    for offset, raw in enumerate(rows[header_at + 1:]):
        values = {}
        for index, field in columns.items():
            values[field] = raw[index] if index < len(raw) else None
        name = str(values.get("name") or "").strip()
        if not name:
            continue                              # a blank row is not an error

        number = to_mm(_number(values.get("elevation_mm")),
                       by_field.get("elevation_mm", units))
        survey = to_mm(_number(values.get("elevation_survey_mm")),
                       by_field.get("elevation_survey_mm", units))
        level_row = LevelRow(
            name, number, str(values.get("level_type") or "").strip(),
            _yes_no(values.get("story")),
            str(values.get("comments") or "").strip(),
            header_at + offset + 2,
            elevation_survey_mm=survey,
            elevation_base=str(values.get("elevation_base") or "").strip(),
            rename_from=str(values.get("rename_from") or "").strip())
        if number is None and survey is None:
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

def resolve_elevations(rows, survey_offset_mm=None, sheet=SHEET_LEVELS):
    """Settle which of a row's two elevations is the one to build. ``[Issue]``.

    ``survey_offset_mm`` is what the Survey Point reads where the Project Base
    Point reads zero — the model's own number, read from the model, never
    assumed. Three things happen here and each is a refusal to guess:

    A row measured from the **survey point** is converted to a project-base
    elevation, because that is the only thing Revit can be told. Without the
    model's offset it cannot be converted, so it is left unbuildable and says
    why rather than being placed a hundred metres out.

    A row that gives **both** and disagrees with the offset is reported and
    **not corrected**. One of the two numbers is wrong, this cannot know which,
    and quietly picking one is how a level ends up somewhere nobody chose.

    A row that gives only the project base elevation is left exactly alone,
    which is the common case and stays cheap.
    """
    issues = []
    for row in rows:
        base = _fold(row.elevation_base)
        wants_survey = base.startswith(_fold(BASE_SURVEY))

        if wants_survey:
            if row.elevation_survey_mm is None:
                issues.append(models.Issue(
                    models.SEVERITY_ERROR,
                    "{0!r} is measured from the survey point and has no "
                    "survey elevation.".format(row.name),
                    sheet=sheet, row=row.row, column="Elevation Survey"))
                row.elevation_mm = None
            elif survey_offset_mm is None:
                issues.append(models.Issue(
                    models.SEVERITY_ERROR,
                    "{0!r} is measured from the survey point, and this model "
                    "would not say where its survey point is.".format(row.name),
                    sheet=sheet, row=row.row, column="ElevationBase"))
                row.elevation_mm = None
            else:
                row.elevation_mm = row.elevation_survey_mm - survey_offset_mm
            continue

        if (row.elevation_survey_mm is not None
                and row.elevation_mm is not None
                and survey_offset_mm is not None):
            expected = row.elevation_mm + survey_offset_mm
            if abs(expected - row.elevation_survey_mm) > ELEVATION_TOLERANCE_MM:
                issues.append(models.Issue(
                    models.SEVERITY_WARNING,
                    "{0!r}: the survey elevation says {1:g} and the project "
                    "elevation says {2:g}, which with this model's survey "
                    "offset of {3:g} should be {4:g}. Building the project "
                    "elevation; one of the two is wrong.".format(
                        row.name, row.elevation_survey_mm, row.elevation_mm,
                        survey_offset_mm, expected),
                    sheet=sheet, row=row.row, column="Elevation Survey"))
    return issues


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
            if row.rename_from and _fold(row.rename_from) == _fold(occupant):
                key = _key_of(existing, occupant)
                claimed.add(key)
                plans.append(LevelPlan(
                    row, RENAME,
                    "renaming {0!r}, which the sheet asked for by "
                    "name".format(occupant), key, row.elevation_mm))
                issues.append(models.Issue(
                    models.SEVERITY_INFO,
                    "{0!r} is being renamed to {1!r}. The sheet named it in "
                    "RenameFrom, which is the only way this happens — a level "
                    "is never renamed on a guess, because a rename changes "
                    "what every view and sheet refers to.".format(
                        occupant, row.name),
                    sheet=sheet, row=row.row, column="RenameFrom"))
                continue
            plans.append(LevelPlan(
                row, BLOCKED,
                "{0!r} is already at {1:g} mm".format(occupant,
                                                      row.elevation_mm)))
            issues.append(models.Issue(
                models.SEVERITY_ERROR,
                "A level called {0!r} already sits at {1:g} mm. Creating a "
                "second one there would give every plan view two candidates. "
                "**Put {0!r} in this row's RenameFrom column** and it will be "
                "renamed to {2!r} instead — or change the elevation.".format(
                    occupant, row.elevation_mm, row.name),
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


def _key_of(existing, name):
    """The caller's key for the level it calls *name*."""
    for found, key, _elevation in existing or ():
        if _fold(found) == _fold(name):
            return key
    return None


def _at_elevation(existing, elevation_mm, tolerance_mm, claimed):
    """The name of a level already at this height, or ``None``."""
    for name, key, found in existing or ():
        if key in claimed:
            continue
        if abs(found - elevation_mm) <= tolerance_mm:
            return name
    return None


def summarise(plans):
    """``{created, modified, renamed, matched, blocked, invalid}``."""
    counts = {"created": 0, "modified": 0, "renamed": 0, "matched": 0,
              "blocked": 0, "invalid": 0}
    for action, key in ((CREATE, "created"), (MODIFY, "modified"),
                        (RENAME, "renamed"),
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


def parse_grids(grid, sheet=SHEET_GRIDS, units=UNITS_MM):
    """``([GridRow], [Issue])``. Same header rules as the levels sheet.

    Same unit rules too: a column that names its unit is believed over the
    job's, and everything is millimetres by the time it leaves here.
    """
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

    column_units = _header_units(rows[header_at], columns)
    by_field = {}
    for index, field in columns.items():
        by_field[field] = column_units.get(index, units)

    def measure(values, field):
        # Angle is not a length and is never scaled. Turning 90 degrees into
        # 90000 would be a very quiet way to ruin a grid.
        return to_mm(_number(values.get(field)), by_field.get(field, units))

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
            measure(values, "x1"), measure(values, "y1"),
            measure(values, "x2"), measure(values, "y2"),
            _number(values.get("angle_deg")), measure(values, "length_mm"),
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
