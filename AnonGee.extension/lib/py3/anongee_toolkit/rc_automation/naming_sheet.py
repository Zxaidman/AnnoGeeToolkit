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
    "column_mark": (("n",), "C{n}", "a column's schedule mark"),
    "footing_mark": (("n",), "F{n}", "a footing's schedule mark"),
    "beam_mark": (("level", "grid"), "B{level}-{grid}", "a beam's mark"),
}

#: Which keys are text rather than a size, so a check feeds them something
#: readable instead of 100.
_TEXT_FIELDS = ("level", "grid", "name", "label")

#: What each field is worth in an example. Per field, not per position: a
#: positional sample gave ``C300`` for a column mark, which is not a mark and
#: not a number anybody would recognise.
_SAMPLE = {"b": 300, "h": 600, "l": 2400, "w": 2400, "t": 150, "n": 1,
           "level": "01", "grid": "1"}


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
    try:
        text = pattern.format(**shown).strip()
    except (KeyError, IndexError, ValueError):
        text = ""
    if text:
        return text
    try:
        return PATTERNS[key][1].format(**shown).strip()
    except (KeyError, IndexError, ValueError):
        return ""


def example(patterns, key):
    """What this pattern produces for a sample, so a sheet can show it.

    The example is *generated* rather than typed beside the pattern, so it
    cannot drift from it — which is the whole reason it is worth having.
    """
    sample = dict((field, _SAMPLE.get(field, 100))
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
