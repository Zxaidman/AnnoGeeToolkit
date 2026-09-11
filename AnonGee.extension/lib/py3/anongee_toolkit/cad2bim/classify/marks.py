# -*- coding: utf-8 -*-
"""Parse structural marks from DXF text and match them to members.

A label like "C1 400x400" or "B1 230x500" carries the one thing geometry alone
cannot give: the member's intended size (and, for a beam, its DEPTH). This module
turns those strings into (name, b_mm, h_mm) and finds the nearest sized label to a
member's centroid so column/beam sizing can be refined from the drawing's own text.

The sheet's own BLANKET NOTE ("ALL BEAMS ARE 750MM IN DEPTH U.N.O.") is read here
too, by `parse_blanket_note` / `sheet_defaults`. It is the other half of the same
question: a label sizes the member it stands beside, the blanket note sizes every
member no label reached. It is a DEFAULT and never an override -- "unless noted
otherwise" says so in the drawing's own words.

Revit-free and 2D (internal feet), so it is unit-testable outside Revit.
"""

import re

# size token: 400x400, 230 x 500, 400X600, 400*600 (b first, h second -- order kept)
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×X*]\s*(\d+(?:\.\d+)?)")
# mark token: letters then digits, REPEATED, with an optional trailing letter --
# "C1", "RB12", "C1A", and "T1SW41a", "T2CW3B", which alternate twice.
# The token may butt directly against a size with an underscore ("C16_300 X 600"): an
# underscore is a regex word char, so a trailing \b would NOT fire there and the mark was
# lost. A negative lookahead instead just forbids the token running on into another
# letter/digit, so "_", a space, or end-of-string all close it.
#
# The repeat arrived with BUG-41 -- the owner's shear walls are "T1SW41a" and one
# letters-then-digits group could not reach them. MEASURED over all 36119 texts in
# the corpus before widening it: the answer CHANGES on none of them, and 415 texts
# newly match, every one of the shape T#SW#, T#W#, T#CW#, T#PW# or T#Y#.
#
# `(?![xX]\d)` is what keeps it a mark and not a size: without it "B200x2380" --
# a beam labelled by its section -- reads as one long mark "B200X2380", because
# "x2380" is a perfectly good letters-then-digits group. The size separator never
# continues a mark.
_MARK_RE = re.compile(r"\b([A-Za-z]{1,3}\d+(?:(?![xX]\d)[A-Za-z]{1,3}\d+)*"
                      r"[A-Za-z]?)(?![A-Za-z0-9])")

# How near a NAME-only text has to be to a SIZE-only text before the two are read
# as the two halves of one label. MEASURED across every fixture drawing, over the
# 367 size-only texts that have a name-only text on their own layer:
#
#     nearest name        min 223   10th  270   median  340   90th  411
#     SECOND nearest      min 836   10th 1086   median 2276   90th 3422
#
# The band from 411 to 836 mm is EMPTY -- no label's own name sits beyond 411 and
# no other label's name comes nearer than 836. 600 is the middle of the gap.
_LABEL_HALVES_MM = 600.0
# "B20(c)" -- the mark carries a parenthesised SCHEDULE KEY instead of a size;
# the size lives in a MARK/SIZE table whose mark column reads "(a)", "(b)"...
_SIZE_KEY_RE = re.compile(r"\(\s*([A-Za-z0-9]{1,3})\s*\)")


def size_key(text):
    """The parenthesised SCHEDULE KEY in a label, normalised, or None.

    Some drawings write the size as a key into a beam-size table instead of
    spelling it out: "B20(c)" means beam B20 of size (c), and a MARK/SIZE
    schedule elsewhere on the sheet says (c) = 400x600. The key is returned in
    the same "(C)" form the schedule reader stores, so one lookup serves both.
    """
    if not text:
        return None
    flat = text.replace("\n", " ")
    found = _SIZE_KEY_RE.search(flat)
    if not found:
        return None
    key = found.group(1).strip().upper()
    # a bare number in brackets is a quantity/callout, not a size key
    if key.isdigit():
        return None
    return "({0})".format(key)


def parse_mark(text):
    """Parse one text string into (name, b_mm, h_mm); any field may be None.

    `name` is the first mark-like token (e.g. "C1"); `b_mm`/`h_mm` come from the
    first BxH token, order preserved (b = first number, h = second). Tolerant of
    surrounding junk and multi-line text.
    """
    if not text:
        return (None, None, None)
    flat = text.replace("\n", " ").strip()

    b_mm = h_mm = None
    size = _SIZE_RE.search(flat)
    if size:
        try:
            b_mm = float(size.group(1))
            h_mm = float(size.group(2))
        except (ValueError, TypeError):
            b_mm = h_mm = None

    name = None
    mark = _MARK_RE.search(flat)
    if mark:
        name = mark.group(1).upper()

    return (name, b_mm, h_mm)


def parse_texts(texts):
    """Stamp .mark/.b_mm/.h_mm/.size_key on every TextRecord; return the list."""
    for record in texts:
        name, b_mm, h_mm = parse_mark(record.text)
        record.mark = name
        record.b_mm = b_mm
        record.h_mm = h_mm
        record.size_key = size_key(record.text)
    join_split_labels(texts)
    return texts


def join_split_labels(texts, radius_mm=None):
    """Give a size-only text the name written just beside it (BUG-41).

    A drawing does not have to put a member's name and its section in one piece
    of text. The owner's writes them as two, the name directly above the size:

        T1SW1            <- one DXF text, a name and no size
        250X2750         <- another, a size and no name

    Read one at a time, neither half is a label: the size text names nothing, so
    every member it sizes is built unnamed, and the name text sizes nothing, so
    it is never looked at. His drawing is an exact 340 / 340 split of the two,
    and all 171 members came out with the schedule mark blank.

    So a size-only text takes the mark of the nearest name-only text ON ITS OWN
    LAYER within `radius_mm` (`_LABEL_HALVES_MM`, read off an empty band -- see
    the constant). Same layer because that is what the drawing itself groups by,
    and it stops a beam's name crossing to a column's size where the two happen
    to be drawn close.

    In place, and idempotent: a text that already carries both is never touched,
    and neither is a name-only text -- it keeps naming nothing, because what it
    names is the member the size text sits on.

    Returns the number of size texts that gained a name.
    """
    reach = (_LABEL_HALVES_MM if radius_mm is None else float(radius_mm)) / 304.8
    sizes, names = {}, {}
    for record in texts or ():
        point = getattr(record, "point_internal", None)
        if not point:
            continue
        sized = (getattr(record, "b_mm", None) is not None
                 and getattr(record, "h_mm", None) is not None)
        named = bool(getattr(record, "mark", None))
        if sized and not named:
            sizes.setdefault(getattr(record, "layer", ""), []).append(record)
        elif named and not sized:
            names.setdefault(getattr(record, "layer", ""), []).append(record)
    joined = 0
    for layer, wanting in sizes.items():
        offering = names.get(layer)
        if not offering:
            continue
        for record in wanting:
            x, y = record.point_internal[0], record.point_internal[1]
            best, best_d2 = None, reach * reach
            for other in offering:
                d2 = ((other.point_internal[0] - x) ** 2
                      + (other.point_internal[1] - y) ** 2)
                if d2 <= best_d2:
                    best, best_d2 = other, d2
            if best is not None:
                record.mark = best.mark
                joined += 1
    return joined


def sized_texts(texts):
    """The subset of texts that carry a usable BxH size and an internal point."""
    return [t for t in texts
            if t.b_mm is not None and t.h_mm is not None and t.point_internal]


# ------------------------------------------------------- the sheet's blanket note
# "NOTE - 1) ALL BEAMS ARE 750MM IN DEPTH U.N.O." is not a label: it names no
# member and sits nowhere near one. It is the sheet speaking about EVERY member
# the plan did not size individually -- the DEFAULT, never an override. Four
# drawings in the corpus carry one, and no two write it the same way:
#
#   test14  NOTE - 1) ALL BEAMS ARE 750MM IN DEPTH U.N.O.
#           2) ALL SALB ARE 125MM  U.N.O.
#   test12  NOTE:-1) ALL BEAMS 650 DEEP U.N.O.
#   test9   * ALL BEAM SIZE SHALL BE 240x600 (U.N.O.)
#           * ALL SLAB THICKNESS SHALL BE 150MM THK. (U.N.O.)
#           *ALL SLAB SHALL BE 175MM THICK (UNLESS MENTIONED)
#
# So each CLAUSE is read on its own, one text record at a time. test14 writes
# its two clauses as two separate records -- the second ("2) ALL SALB...") does
# not repeat the word NOTE -- and nothing here needs them joined: the clause
# carries its own subject and its own number. The word NOTE is never required.
#
# Two gates decide whether a string is a blanket note at all, and each was
# written for a drawing that would otherwise be read wrong:
#
#   * the subject must be UNQUALIFIED -- "ALL" immediately followed by the
#     element word. test12's "2) ALL INVETED BEAM FOR ELEVATION JALI ARE 800
#     DEEP." names a SUBSET of the beams, so it sets no sheet default; test9's
#     "ALL BKT SIZE ..." is brackets, not beams. Both fail this gate.
#   * the clause must carry an UNLESS marker (U.N.O. / UNO / "unless ..."),
#     which is what makes it a default rather than a statement of fact. The
#     inverted-beam clause carries none, and so fails this one too.
#
# "SALB" is the drawing's own misspelling of SLAB and is accepted as written:
# the parser reads the sheet as drawn, not as it should have been drawn.
_BLANKET_SUBJECT_RE = re.compile(r"\bALL\s+(BEAM|SLAB|SALB)S?\b", re.IGNORECASE)
# "U.N.O." / "U.N.O" / "UNO" / "(U.N.O.)" / "UNLESS NOTED OTHERWISE" /
# "(UNLESS MENTIONED)". The trailing \b keeps "UNOCCUPIED" out.
_BLANKET_UNO_RE = re.compile(r"\bU\.?N\.?O\.?\b|\bUNLESS\b", re.IGNORECASE)
# the figure, read from what follows the subject -- which is what keeps the
# CLAUSE NUMBER out of it ("1)" and "2)" always sit BEFORE the word ALL)
_BLANKET_NUM_RE = re.compile(r"(\d{2,4})")

# A blanket figure below this is not a structural member (the thinnest slab in
# the corpus is 125), and one above it is a storey, not a member -- the same
# line max_step_mm draws between a step and a level. A number outside the band
# is something else the clause happened to mention, so the clause sets nothing.
_BLANKET_MIN_MM = 50.0
_BLANKET_MAX_MM = 3000.0

BLANKET_KEYS = ("beam_depth_mm", "slab_thickness_mm")


def parse_blanket_note(text):
    """{"beam_depth_mm": 750.0} / {"slab_thickness_mm": 125.0} / {} for ONE clause.

    A beam clause yields its DEPTH only. Where the sheet writes a whole section
    ("ALL BEAM SIZE SHALL BE 240x600") the width is dropped on purpose: a plan
    MEASURES a beam's width from the pair of drawn edges, so the drawing already
    knows it, and a blanket width would overwrite a measurement with an
    assumption. Depth is the one dimension a 2D plan cannot give, which is the
    whole reason the sheet writes the note.
    """
    flat = _blanket_text(text)
    if not flat or not _BLANKET_UNO_RE.search(flat):
        return {}
    subject = _BLANKET_SUBJECT_RE.search(flat)
    if not subject:
        return {}
    beams = subject.group(1).upper() == "BEAM"
    rest = flat[subject.end():]
    value = None
    if beams:
        size = _SIZE_RE.search(rest)
        if size:
            try:
                # "240x600" -- depth is the LARGER, exactly as a beam label is
                # read (_apply_beam_marks: width = smaller, depth = larger)
                value = max(float(size.group(1)), float(size.group(2)))
            except (ValueError, TypeError):
                value = None
    if value is None:
        number = _BLANKET_NUM_RE.search(rest)
        if not number:
            return {}
        value = float(number.group(1))
    if not (_BLANKET_MIN_MM <= value <= _BLANKET_MAX_MM):
        return {}
    return {"beam_depth_mm" if beams else "slab_thickness_mm": value}


def sheet_defaults(texts):
    """What the sheet's blanket notes say, as {beam_depth_mm, slab_thickness_mm,
    conflicts}. Either figure is None when the sheet did not settle it.

    CONFLICTS ARE REFUSED, NOT RESOLVED. A sheet holding several plans can carry
    several notes, and they need not agree: test12 says 650 DEEP on twelve of
    its fifteen note blocks and 600 DEEP on the other three, and test9's three
    towers say 150 THK and 175 THICK. There is no way to tell from the text
    which beam belongs to which note, and a majority vote on a structural depth
    is exactly the kind of silent guess that puts a wrong member in the model --
    so a kind whose notes disagree yields None and the disagreement is listed in
    `conflicts` for the caller to say out loud. The user can still settle it by
    typing a figure into the dialog.

    `conflicts` is [(key, [values...]), ...], sorted, so the message can name
    every figure the sheet offered.
    """
    seen = dict((key, set()) for key in BLANKET_KEYS)
    for record in (texts or []):
        for key, value in parse_blanket_note(record).items():
            seen[key].add(value)
    found = {"conflicts": []}
    for key in BLANKET_KEYS:
        values = sorted(seen[key])
        found[key] = values[0] if len(values) == 1 else None
        if len(values) > 1:
            found["conflicts"].append((key, values))
    return found


def _blanket_text(record):
    """The string of a note, whether it arrives as a TextRecord or as plain text.

    The pushbutton and the harnesses hand over TextRecords; the unit tests pin
    the drawings' own strings, and reading those directly keeps the pin honest.
    """
    if isinstance(record, str):
        return record.replace("\n", " ")
    return (getattr(record, "text", "") or "").replace("\n", " ")


def parse_schedule(texts, allow_split=True):
    """Build a {mark: (b_mm, h_mm)} lookup from a column-schedule's text cells.

    A column schedule is a table; in DXF its cells are individual TEXT entities.
    This reconstructs the mark->size mapping so a plan label that carries ONLY a
    mark ("C9") can still be sized from its schedule row.

    Three cell layouts are handled, most specific first:
      * tabular -- a real table with a header row (e.g. "Mark W L H", repeated for
        several side-by-side blocks). The header fixes each column's x and role;
        every data row is read column by column. Plan size is W x L; a height
        column (H) is ignored. This is the common CAD column schedule.
      * inline -- one cell carries both mark and size ("C1  400x600").
      * split -- a mark cell and a single size cell ("400x600") share a row.
    On a conflict the tabular reading wins, then inline, then the first split.
    Returns {} for no input. Sizes keep (b, h) order as written.

    `allow_split` gates the split layout. It must be OFF when parsing PLAN labels
    (not a table): there, a markless size label and an unrelated mark merely sharing
    a Y are different columns metres apart, and pairing them mis-sizes a column from
    a neighbour's label (e.g. C5 inheriting a 350x750 label a whole bay away).
    """
    schedule = {}
    if not texts:
        return schedule

    placed = [(record.text, _schedule_xy(record)) for record in texts]
    cells = [(xy[0], xy[1], text) for text, xy in placed if xy]

    # 1. Tabular: header-driven, the usual CAD column schedule.
    for mark, size in _parse_schedule_table(_cluster_rows(cells)).items():
        schedule.setdefault(mark, size)

    parsed = [(parse_mark(text) + (xy,)) for text, xy in placed]

    # 2. Inline cells: a single cell carrying both a mark and a size.
    for mark, b_mm, h_mm, _xy in parsed:
        if mark and b_mm is not None and h_mm is not None:
            schedule.setdefault(mark, (b_mm, h_mm))

    # 3. Split cells: pair each size-only cell with its row's mark-only cell.
    if not allow_split:
        return schedule
    mark_cells = [(mark, xy) for mark, b_mm, h_mm, xy in parsed
                  if mark and b_mm is None and xy is not None]
    size_cells = [(b_mm, h_mm, xy) for mark, b_mm, h_mm, xy in parsed
                  if b_mm is not None and h_mm is not None and mark is None
                  and xy is not None]
    for b_mm, h_mm, (sx, sy) in size_cells:
        best_mark = None
        best_d2 = None
        for mark, (mx, my) in mark_cells:
            dx, dy = mx - sx, my - sy
            if abs(dy) >= abs(dx):
                continue   # the mark is in another row (above/below), not this one
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best_d2, best_mark = d2, mark
        if best_mark and best_mark not in schedule:
            schedule[best_mark] = (b_mm, h_mm)

    return schedule


# Schedule header keywords -> column role. Plan size is W x L; H is the column's
# vertical height (ignored for the footprint). Single letters cover terse CAD
# headers ("W L H"); full words cover verbose ones.
# "comments": a schedule exported FROM Revit keeps the element name in the
# Comments column (StaircasePlan-Test2), so that column heads the table there
_HDR_MARK = ("mark", "ref", "col", "column", "type", "no", "id",
             "comments", "comment", "name")
_HDR_W = ("w", "b", "width", "breadth")
_HDR_L = ("l", "d", "depth", "length")
_HDR_H = ("h", "ht", "height", "lvl", "level")
# A SLAB (or raft) schedule is a two-column Mark|Thk table -- one dimension, not
# two -- so it needs its own role and its own reader; the value is a scalar, not
# a (w, l) pair, and cramming it into the same mapping would hand a slab's
# thickness to something expecting a section. Measured across the corpus before
# choosing the words: "THK" appears in test16 alone, twice, and those two cells
# ARE its slab schedule's headers. A bare "T" is deliberately NOT here -- it
# appears in test4, test5 and test9 meaning something else entirely.
_HDR_T = ("thk", "thick", "thickness")
_HDR_SIZE = ("size", "section", "dim", "dimensions", "bxd", "wxl", "wxd")


def _header_role(text):
    """Role of a header cell ('mark'/'w'/'l'/'h'/'size'), or None if not a header."""
    t = (text or "").strip().lower().rstrip(".")
    if t in _HDR_MARK:
        return "mark"
    if t in _HDR_W:
        return "w"
    if t in _HDR_L:
        return "l"
    if t in _HDR_T:
        return "t"
    if t in _HDR_H:
        return "h"
    if t in _HDR_SIZE:
        return "size"
    return None


def _cluster_rows(cells):
    """Group (x, y, text) cells into table rows by y (single-linkage).

    The row pitch is learned from the data (median y-gap), so this works in mm or
    metres without a hard-coded tolerance. Returns [(row_y, [(x, text), ...]), ...]
    ordered top-to-bottom.
    """
    if not cells:
        return []
    ys = sorted(set(c[1] for c in cells))
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 1e-9]
    pitch = _median(gaps) if gaps else 1.0
    tol = pitch * 0.45
    rows = []   # each: [anchor_y, [(x, text), ...], last_y]
    for x, y, text in sorted(cells, key=lambda c: -c[1]):
        if rows and (rows[-1][2] - y) <= tol:
            rows[-1][1].append((x, text))
            rows[-1][2] = y
        else:
            rows.append([y, [(x, text)], y])
    return [(r[0], r[1]) for r in rows]


def _is_header_row(cells):
    """Header roles [(x, role), ...] sorted by x if `cells` is a schedule header,
    else None. A header needs a Mark column and either two dimension columns
    (W and L) or a single combined Size column."""
    roles = [(x, _header_role(t)) for x, t in cells]
    roles = [(x, r) for x, r in roles if r]
    n_mark = sum(1 for _, r in roles if r == "mark")
    n_dim = sum(1 for _, r in roles if r in ("w", "l"))
    n_size = sum(1 for _, r in roles if r == "size")
    n_thk = sum(1 for _, r in roles if r == "t")
    if n_mark >= 1 and (n_dim >= 2 or n_size >= 1 or n_thk >= 1):
        return sorted(roles)
    return None


def parse_thickness_schedule(texts):
    """{mark: thickness_mm} from a Mark|Thk table -- the SLAB (or raft) schedule.

    Kept apart from `parse_schedule` on purpose. That one answers with a SECTION,
    a (w, h) pair, and a slab schedule answers with one number; a single mapping
    holding both would hand a thickness to a caller expecting a section, and the
    error would be a wrong beam rather than a missing slab.

    test16 is the case the owner reported: it draws

        Mark | Thk        Mark | Thk
        S1   | 125        F1   | ...
        ...                RF2 | ...
        S6   | 250

    on G-ANNO-SCHD, with 201 slab labels using those marks, and until `thk` was
    a header word at all the table was invisible -- so every bay fell back to
    the blanket note and no type was ever created from the schedule. The second
    block beside it is the foundation/roof schedule, read by the same pass; the
    caller filters by mark, exactly as the slab pass already filters `S`-marks
    out of the beam schedule.
    """
    out = {}
    if not texts:
        return out
    placed = [(record.text, _schedule_xy(record)) for record in texts]
    cells = [(xy[0], xy[1], text) for text, xy in placed if xy]
    header, data_rows = None, None
    for _y, row in _cluster_rows(cells):
        roles = _is_header_row(row)
        if roles is not None:
            if header is not None:
                _read_thickness_table(header, data_rows, out)
            header, data_rows = roles, []
        elif header is not None:
            data_rows.append(row)
    if header is not None:
        _read_thickness_table(header, data_rows, out)
    return out


def _read_thickness_table(header, data_rows, out):
    """Read one Mark|Thk table's rows into `out`, block by block.

    A header with no thickness column contributes nothing -- a column or beam
    schedule passes through here untouched, which is what keeps the two readings
    independent.
    """
    blocks, current = [], None
    for x, role in header:
        if role == "mark":
            current = {"mark": x}
            blocks.append(current)
        elif current is not None and role == "t":
            current.setdefault("t", x)
    blocks = [b for b in blocks if "t" in b]
    if not blocks:
        return

    xs = sorted(x for x, _ in header)
    pitch = min((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    tol = pitch * 0.5 if pitch > 0 else None

    for cells in data_rows:
        for block in blocks:
            name, _b, _h = parse_mark(_cell_at(cells, block["mark"], tol) or "")
            if not name:
                continue
            value = _first_number(_cell_at(cells, block["t"], tol) or "")
            if value is None:
                continue
            out.setdefault(name, value)


def _first_number(text):
    """The first plain number in a cell, or None. "175" / "175 THK." / "175mm"."""
    match = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_schedule_table(rows):
    """Header-driven {mark: (w, l)} from row-clustered cells -- ONE table per header.

    Several schedules (column / beam / slab) often share a layer and stack
    vertically. Each header row starts an INDEPENDENT table that owns the data rows
    beneath it (until the next header), and every table is read with its OWN block
    x-positions. That keeps a beam table's 'D' column from being read as a column
    table's length, and a column's 'H' from being read as its length, when the
    tables sit on one layer. The common single-header case (including side-by-side
    blocks) is unchanged.
    """
    out = {}
    header = None
    data_rows = None
    for _y, cells in rows:
        roles = _is_header_row(cells)
        if roles is not None:
            if header is not None:
                _read_table(header, data_rows, out)
            header, data_rows = roles, []
        elif header is not None:
            data_rows.append(cells)
    if header is not None:
        _read_table(header, data_rows, out)
    return out


def _read_table(header, data_rows, out):
    """Read one table's data rows into `out` using only that header's block x's.

    Splits the header into side-by-side Mark|W|L|H (or Mark|Size) blocks and reads each
    data row column by column. The section is W x (its second dimension): for a COLUMN
    that is W x L (footprint), the H column is the storey height and is ignored; for a
    BEAM (a "B"-mark) the section is W x H (depth) and the L column is the SPAN, ignored.
    A column schedule with the columns ordered "W H L" would otherwise read a beam's span
    as its depth.
    """
    blocks = []   # each: {"mark": x, "w": x, "l": x, "h": x} or {"mark": x, "size": x}
    current = None
    for x, role in header:
        if role == "mark":
            current = {"mark": x}
            blocks.append(current)
        elif current is not None and role in ("w", "l", "h", "size"):
            current.setdefault(role, x)
    blocks = [b for b in blocks
              if ("w" in b and ("l" in b or "h" in b)) or "size" in b
              or ("h" in b and "w" not in b and "l" not in b)]
    if not blocks:
        return

    xs = sorted(x for x, _ in header)
    pitch = min((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    tol = pitch * 0.5 if pitch > 0 else None

    for cells in data_rows:
        for block in blocks:
            mark_cell = _cell_at(cells, block["mark"], tol) or ""
            name, _b, _h = parse_mark(mark_cell)
            if not name:
                # a KEYED table ("SCHEDULE OF BEAM SIZE": MARK (a) | SIZE
                # 200x600). The key is the mark here, and plan labels reach it
                # through the "(a)" written after their own mark: "B20(c)".
                name = size_key(mark_cell)
            if not name:
                continue
            if "size" in block:
                wh = _two_numbers(_cell_at(cells, block["size"], tol))
            elif "w" not in block and "l" not in block:
                # thickness-only table (slab schedule: Mark | H | Volume). Only an
                # S-mark may read it -- a column table reduced to Mark | H would be
                # the storey height, never a section size.
                h = _number(_cell_at(cells, block["h"], tol))
                wh = (h, h) if (_is_slab_mark(name) and h is not None) else None
            else:
                w = _number(_cell_at(cells, block["w"], tol))
                l = _number(_cell_at(cells, block["l"], tol)) if "l" in block else None
                h = _number(_cell_at(cells, block["h"], tol)) if "h" in block else None
                if _is_beam_mark(name) and h is not None:
                    second = h          # beam: depth is H; L is the span (ignore)
                else:
                    second = l if l is not None else h   # column: footprint W x L
                wh = (w, second) if (w is not None and second is not None) else None
            if wh:
                out.setdefault(name, wh)


def _is_beam_mark(name):
    """True for a beam mark like 'B1'/'B23' (a 'B' followed by a digit)."""
    return bool(name) and name[:1].upper() == "B" and name[1:2].isdigit()


def _is_slab_mark(name):
    """True for a slab mark like 'S1'/'S12' (an 'S' followed by a digit)."""
    return bool(name) and name[:1].upper() == "S" and name[1:2].isdigit()


def _cell_at(cells, target_x, tol):
    """Text of the cell whose x is nearest target_x (within tol, if given)."""
    best, best_d = None, None
    for x, text in cells:
        d = abs(x - target_x)
        if (tol is None or d <= tol) and (best_d is None or d < best_d):
            best, best_d = text, d
    return best


def _number(text):
    """A plain numeric cell as float, or None."""
    if not text:
        return None
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _two_numbers(text):
    """(a, b) from a 'AxB' size cell, or None."""
    if not text:
        return None
    match = _SIZE_RE.search(text)
    if not match:
        return None
    try:
        return (float(match.group(1)), float(match.group(2)))
    except (ValueError, TypeError):
        return None


def _median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _schedule_xy(record):
    """Planar (x, y) for a schedule cell: internal feet if mapped, else DXF coords.

    Only the cells' positions RELATIVE to each other matter for row pairing, and
    both spaces share one scale within a file, so either works."""
    point = record.point_internal or record.point
    if not point:
        return None
    return (point[0], point[1])


def nearest_sized_text(cx, cy, candidates, radius_ft):
    """Return the nearest sized TextRecord within radius_ft of (cx, cy), or None.

    `candidates` should already be filtered to sized_texts (each has b_mm/h_mm and
    point_internal). Distance is planar (x, y) in feet.
    """
    best = None
    best_d2 = radius_ft * radius_ft
    for text in candidates:
        px, py = text.point_internal[0], text.point_internal[1]
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 <= best_d2:
            best = text
            best_d2 = d2
    return best


# ------------------------------------------- is this member a column or a wall?
# Every vertical member the run recovers has been placed as a Structural Column
# since day one. The user asked for the other two readings as well -- all of them
# as walls, and a SMART one that decides member by member -- and gave the rule
# the smart one follows, in two parts.
#
# THE RATIO. "The aspect ratio of the cross-section -- specifically the
# length-to-thickness ratio (L/B) -- decides whether a vertical member is
# classified as a column or a shear wall":
#
#   * COLUMN (or wall pier): L/B < 4 -- length less than 4 times its thickness;
#     designed primarily for axial compression and localised bending.
#   * SHEAR WALL: L/B >= 4 -- length 4 or more times its thickness; designed to
#     resist major lateral forces through in-plane bending and shear.
#
# IS 456, IS 13920 and ACI 318 all draw the line in the same place, which is why
# the 4 is a named constant carrying its codes rather than a bare number in a
# branch: an office that works to a different code edits one line.
WALL_ASPECT_RATIO = 4.0

KIND_COLUMN = "column"
KIND_WALL = "wall"

# THE MARK, which is asked FIRST. A drawing that has named a member has already
# said what it is, and a ratio must not argue with the engineer: test7 marks a
# 300 x 5300 member C10 -- L/B 17.7, a shear wall by the ratio and a column by
# the drawing -- and the drawing wins.
#
# What a mark's letters mean was MEASURED over the twenty fixture drawings, not
# assumed. Every alphabetic prefix in the corpus, and what its layer says it is:
#
#   C     554 texts   columns (test7's C1..C18 sit on the column outlines)
#   AC     48         "COLUMN NO._ASC" -- Project1/test8 column numbers
#   BC     54         the same layer, the other grid direction
#   ALC    10   BLC 8 the same layer again
#   SW     18         S-COLS-IDEN / S-WALL-IDEN -- StaircasePlan-Test1's six
#                     300 x 3300 and 6300 x 300 shear walls, test15/16's SW9..11
#   B    1088         beams. 289 of them land on a COLUMN rectangle in test5.
#   S 29, F 7, RF 2, P 2, T 1, BKT 1     slabs, footings, rafts, and one bracket
#
# So the noun is the LAST letter of the prefix: C says column (C, AC, BC, ALC,
# BLC all being column numbers in this corpus), W says wall (SW, and the user's
# own W1 and CW1 by the same reading). Anything else ABSTAINS and the ratio
# decides -- which is the whole reason the table is a table and not "starts with
# C". Read "starts with B" as a vote and test5's 289 bled beam labels would each
# re-classify the column they happened to land on.
#
# The user's warning that "a mark starting with W might be something else
# entirely" is worth recording: the corpus carries NO bare W mark at all, so
# nothing here validates or contradicts it. What contains the risk is the
# routing rather than this table -- a mark only reaches a member from the text
# layer the Layers tab routed to "column mark", so a window tag W1 on an
# architectural layer is never offered in the first place.
_MARK_NOUN = {"C": KIND_COLUMN, "W": KIND_WALL}


def mark_kind(mark):
    """KIND_COLUMN / KIND_WALL for a mark that says which, else None.

    None means the mark abstains -- it is a beam's, a slab's, or a letter this
    convention has no reading for -- and the caller falls through to the ratio.
    Separators are forgiven ("C-1" reads as C1, the way a drafter writes it),
    because `parse_mark` only ever yields the tight C1/SW1 form and a mark
    arriving from a schedule cell or a settings file need not be that tidy.
    """
    letters = _mark_prefix(mark)
    if not letters:
        return None
    return _MARK_NOUN.get(letters[-1])


def _mark_prefix(mark):
    """The letters before a mark's LAST run of digits, uppercased.

        C1        -> "C"
        SW1       -> "SW"
        T1SW95    -> "SW"          Tower 1, Shear Wall, number 95
        T1SW109A  -> "SW"
        WALL      -> ""            no digits: not a mark in this convention

    The NOUN sits next to the number, not at the front. The owner spelled his
    convention out: "T1 refer mean Tower-1 and SW as Shearwall and 95 is number
    so all this big `T1SW95` is mark for vertical member". Reading the letters
    before the FIRST digit saw only the "T" of the tower and abstained, so every
    one of his shear walls was routed on its L/B ratio instead of on its name.

    MEASURED over the 1573 distinct marks in the corpus before changing it:
    **no answer changes**, and 410 marks that abstained are now decided -- every
    one of them an SW or CW wall. On his own drawing the ratio had been agreeing
    with the name on all 257, so this changes nothing he can see today; what it
    changes is a squat shear wall, which the ratio would call a column and the
    drawing calls a wall.
    """
    text = "".join(ch for ch in (mark or "") if ch.isalnum()).upper()
    letters, before_digits = "", ""
    for char in text:
        if char.isdigit():
            if letters:
                before_digits = letters
            letters = ""
        else:
            letters += char
    return before_digits


def aspect_ratio(width_mm, height_mm):
    """L/B of a rectangular section -- long side over short side, always >= 1.

    None for a section with no thickness to divide by (a zero or negative side
    is not a member), so the caller can say "unmeasurable" instead of dividing.
    """
    try:
        sides = (float(width_mm), float(height_mm))
    except (TypeError, ValueError):
        return None
    short, long_side = min(sides), max(sides)
    if short <= 0.0:
        return None
    return long_side / short


def vertical_kind(mark, width_mm, height_mm):
    """(kind, why) for ONE rectangular vertical member: the smart reading.

    `why` is "mark" when the drawing's own label settled it and "ratio" when the
    L/B rule did, so the console can group the two and the user can see which
    rule moved which member. A section too degenerate to measure falls back to
    the column, the reading this project has always used.

    A ROUND column never reaches here: a circle has no L/B and no long axis to
    lay a wall centreline along, so it can only ever be a column (see
    `wall_plan.split_vertical_members`).
    """
    kind = mark_kind(mark)
    if kind is not None:
        return kind, "mark"
    ratio = aspect_ratio(width_mm, height_mm)
    if ratio is None:
        return KIND_COLUMN, "ratio"
    return (KIND_WALL if ratio >= WALL_ASPECT_RATIO else KIND_COLUMN), "ratio"
