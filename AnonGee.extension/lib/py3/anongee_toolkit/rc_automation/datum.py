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
