# -*- coding: utf-8 -*-
"""Type names as patterns, written in the workbook rather than in code.

The project owner asked for this the way ``cad2bim`` already does it: a
``NAMING`` sheet with one row per element and a pattern like ``{b} X {h}``, so
the house convention lives where a person can change it without touching Python.

Pure — patterns in, names out, no Revit anywhere.

**A bad pattern never stops a run.** It is reported and the default is used.
A naming sheet is a preference; a run that refuses to place ninety columns
because somebody typed ``{width}`` instead of ``{b}`` has confused the two.

The fields are the drawing's words, not Revit's: ``b`` and ``h`` for a section,
``l``/``w``/``t`` for a pad, because that is what an engineer writes on a
sketch and this sheet is for them.
"""

__version__ = "0.1.0"

SHEET = "NAMING"

#: The fields **every** mark pattern may use. One list rather than three,
#: because three lists is how ``beam_mark`` came to refuse ``{n}`` while the
#: sheet's own *Fields it may use* column offered it — the workbook advertising
#: a field the code rejects, and the rejection degrading silently. BUG-34.
MARK_FIELDS = ("prefix", "n", "level", "grid")

#: ``key -> (fields it may use, the default pattern, what it names)``.
#:
#: The defaults are the template's own convention — ``300 X 600``, capital X,
#: spaces — because a workbook that ships agreeing with the model it will meet
#: creates nothing on the first run.
PATTERNS = {
    "column": (("b", "h"), "{b} X {h}", "a rectangular column type"),
    "beam": (("b", "h"), "{b} X {h}", "a rectangular beam type"),
    "footing": (("l", "w", "t"), "{l} x {w} x {t}mm", "a pad footing type"),
    "slab": (("t",), "{t}mm thk", "a floor or foundation slab type"),
    "stair": (("w", "t"), "{w} X {t}", "a stair waist and its landing"),
    "column_mark": (MARK_FIELDS, "{prefix}{n}", "a column's schedule mark"),
    "footing_mark": (MARK_FIELDS, "{prefix}{n}", "a footing's schedule mark"),
    "beam_mark": (MARK_FIELDS, "{prefix}{n}", "a beam's schedule mark"),
}

#: Which keys are read by a command. All of them, now.
#:
#: The three ``*_mark`` keys were read by nothing for two releases — a
#: placement sheet carried its own ``Mark`` column and that was what went into
#: ``S_ScheduleMark``. The project owner asked for the schedule mark to be
#: generated instead, so that a plinth beam schedules as ``PB1`` and a floor
#: beam as ``B1`` whatever the placement sheet's per-row marks say.
#:
#: ``{prefix}`` is what makes that work without three separate patterns: it is
#: the letters the workbook's own ``TypeMark`` starts with — ``PB`` out of
#: ``PB-230x450``, ``B`` out of ``B-230x600``, ``F`` out of ``F1`` — so the
#: distinction the engineer already made in the TypeMark column carries into
#: the schedule mark rather than being typed a second time.
WIRED = ("column", "beam", "footing", "slab", "stair",
         "column_mark", "beam_mark", "footing_mark")

#: Which keys are text rather than a size, so a check feeds them something
#: readable instead of 100.
_TEXT_FIELDS = ("level", "grid", "name", "label", "prefix")

#: What each field is worth in an example. Per field, not per position: a
#: positional sample gave ``C300`` for a column mark, which is not a mark and
#: not a number anybody would recognise.
_SAMPLE = {"b": 300, "h": 600, "l": 2400, "w": 2400, "t": 150, "n": 1,
           "level": "01", "grid": "1", "prefix": "B"}

#: Where one field means two different sizes. ``w`` is a pad's 2400 and a
#: stair's 1200, and an example showing a 2400-wide flight teaches the wrong
#: thing about a sheet whose entire job is to be read.
_SAMPLE_BY_KEY = {"stair": {"w": 1200, "t": 150},
                  "column_mark": {"prefix": "C"},
                  "footing_mark": {"prefix": "F"},
                  "beam_mark": {"prefix": "PB"}}


def defaults():
    """``{key: pattern}`` — the convention with nothing overridden."""
    return dict((key, pattern) for key, (_fields, pattern, _what)
                in PATTERNS.items())


def parse(grid, sheet=SHEET):
    """``({key: pattern}, [Issue])`` from a NAMING sheet.

    A sheet that is absent, empty, or unreadable gives the defaults and says
    nothing — it is optional, and a workbook without one is not wrong.
    """
    from anongee_toolkit.rc_automation import models

    found = defaults()
    issues = []
    rows = list(grid or [])
    if not rows:
        return found, issues

    header_at = None
    key_at = pattern_at = None
    for index, row in enumerate(rows):
        folded = [_fold(cell) for cell in row]
        for column, cell in enumerate(folded):
            if cell in ("element", "key", "what"):
                key_at = column
            elif cell in ("pattern", "template", "format", "name"):
                pattern_at = column
        if key_at is not None and pattern_at is not None:
            header_at = index
            break

    if header_at is None:
        return found, issues

    # Folded on both sides. ``_fold`` drops underscores, so comparing a folded
    # cell against the raw keys rejected `beam_mark`, `column_mark` and
    # `footing_mark` — three of the seven, in the sheet this repository writes
    # itself. Fold the keys too, and the comparison means what it looks like.
    by_folded = dict((_fold(name), name) for name in PATTERNS)

    for offset, raw in enumerate(rows[header_at + 1:]):
        cell = _fold(raw[key_at] if key_at < len(raw) else "")
        pattern = str(raw[pattern_at] if pattern_at < len(raw) else "").strip()
        if not cell or not pattern:
            continue
        key = by_folded.get(cell)
        if key is None:
            issues.append(models.Issue(
                models.SEVERITY_WARNING,
                "{0!r} is not a name this understands. It knows: {1}.".format(
                    raw[key_at], ", ".join(sorted(PATTERNS))),
                sheet=sheet, row=header_at + offset + 2, column="Element"))
            continue

        problem = check(key, pattern)
        if problem:
            issues.append(models.Issue(
                models.SEVERITY_WARNING,
                "{0}: {1}. Using {2!r} instead — a naming preference should "
                "not stop a run.".format(key, problem, PATTERNS[key][1]),
                sheet=sheet, row=header_at + offset + 2, column="Pattern"))
            continue
        found[key] = pattern
        if key not in WIRED and pattern != PATTERNS[key][1]:
            issues.append(models.Issue(
                models.SEVERITY_INFO,
                "{0} is recorded but nothing reads it yet — a placement sheet "
                "carries its own Mark column and that is what is written. The "
                "pattern is kept and will apply when marks are generated "
                "rather than typed.".format(key),
                sheet=sheet, row=header_at + offset + 2, column="Pattern"))
    return found, issues


def check(key, pattern):
    """``None`` when *pattern* is usable for *key*, else why it is not."""
    if key not in PATTERNS:
        return "not a name this understands"
    fields = PATTERNS[key][0]
    sample = dict((field, field if field in _TEXT_FIELDS else 100)
                  for field in fields)
    try:
        text = pattern.format(**sample)
    except (KeyError, IndexError, ValueError) as error:
        return "{0} — this one takes {1}".format(
            error, ", ".join("{" + field + "}" for field in fields))
    if not text.strip():
        return "gives an empty name"
    return None


def render(patterns, key, **values):
    """The name *key* gives for these values, falling back to the default.

    Falls back rather than raising, for the same reason ``parse`` does: the
    caller is halfway through placing ninety columns and a naming preference is
    not a reason to stop.
    """
    pattern = (patterns or {}).get(key) or PATTERNS[key][1]
    shown = dict((name, _number(value)) for name, value in values.items())
    for candidate in (pattern, PATTERNS[key][1]):
        try:
            text = candidate.format(**shown).strip()
        except (KeyError, IndexError, ValueError):
            continue
        if text:
            return text
    return ""


def example(patterns, key):
    """What this pattern produces for a sample, so a sheet can show it.

    The example is *generated* rather than typed beside the pattern, so it
    cannot drift from it — which is the whole reason it is worth having.
    """
    special = _SAMPLE_BY_KEY.get(key) or {}
    sample = dict((field, special.get(field, _SAMPLE.get(field, 100)))
                  for field in PATTERNS[key][0])
    return render(patterns, key, **sample)


def _number(value):
    """``600.0`` reads as ``600`` in a type name, and ``0.45`` as ``0.45``."""
    if isinstance(value, float) and abs(value - round(value)) < 1e-6:
        return int(round(value))
    return value


def _fold(text):
    return "".join(character for character in str(text or "").lower()
                   if character.isalnum())
