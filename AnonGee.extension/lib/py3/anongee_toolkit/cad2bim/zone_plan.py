# -*- coding: utf-8 -*-
"""One element family per boundary ZONE, folded back into one plan (FEAT-17).

The owner:

    "cad2bim - separating column, beam & slab, wall outline to each boundary
    zone with proper origin point to eliminate Revit eating Linked Outline
    merge. like for example one big `boundary` layer which will hold 4 specific
    `combine-boundary`, `grid-column-boundary`, `beam-slab-boundary`,
    `wall-boundary` inside it. each with same origin point on each boundary.
    [...] reason why we need this currently revit link cad eat overlapping
    outline which causes our tool to be unreliable with new cad file which is
    not good for sellable product."

WHY IT IS THE RIGHT SHAPE OF FIX. Half this package exists because the Revit
link delivers less than the DXF holds -- `recover_rectilinear_columns`,
`recover_oriented_columns`, `recover_outline_columns`, `recover_face_columns`,
the fragment reassembly, `_is_clipped`. Every one of them is guesswork about
geometry destroyed at import, and the destruction happens where a column
outline, a beam outline and a wall outline lie on top of one another. Draw each
family in its own zone and nothing overlaps, so nothing is eaten, so nothing has
to be guessed back. THE MERGE MOVES OUT OF REVIT AND INTO THE READER, which is
the whole point: this module does it, before any pass runs.

Measured in `StructuralPlan-Test17-separate-boundary-zones.dxf`, the owner's
example (one storey, 4070 records): four zone boxes the same size to the
millimetre inside one `Boundary`, each carrying ONE origin marker at the same
offset inside its own box -- 78949.90, 12805.57 mm from its corner, all four
identical. Shifting each zone by its own origin therefore lands every zone
exactly on top of the others. Its texts travel with it (170 `COL. NO.` + 170
`COL. SIZE` in Grid-Column, 435 `S-BEAM-IDEN` in Beam-Slab) and so do its
hatches (Grid-Column 340, Wall 302, Beam-Slab 137).

BOTH NESTINGS ARE REAL, and the owner asked for both: "i like both option 1 and
2, maybe when there is 20 different storey cad the option 2 shines but if there
is only few storey are there then option 1 is easily manageable".

  * ZONES INSIDE A STOREY -- each storey's boundary holds its own set of zones.
    Easy to draft while the storeys are few; it is what the example does;
  * STOREYS INSIDE A ZONE -- each zone holds the whole sheet of storeys. Four
    copies of the sheet, one per family, which is the one that scales to twenty
    floors.

Both are read the same way, because in both the piece that gets shifted is the
INNERMOST box and the origin marker sits inside it. Which nesting a drawing uses
is decided by containment, not by a setting.

Revit-free: this is arithmetic over records, and it runs before anything is
built.
"""

from .classify.layers import (CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN,
                              CATEGORY_GRID, CATEGORY_COLUMN, CATEGORY_BEAM,
                              CATEGORY_SLAB_EDGE, CATEGORY_STAIR,
                              CATEGORY_STRUCT_WALL, CATEGORY_ARCH_WALL,
                              CATEGORY_FOUNDATION, CATEGORY_FOLD,
                              CATEGORY_SUNK, CATEGORY_CUTOUT,
                              CATEGORY_SLAB_STOP)
from .floor_plans import (_record_bounds, _record_point, _shift_record,
                          _shift_text, origin_points)


# What makes a layer a zone box rather than a drawn thing. The owner's names all
# end this way (`Grid-Column-boundary`), and so does the storey boundary itself
# -- which is why the storey layer is always excluded by name before this is
# applied.
ZONE_SUFFIX = "-boundary"

# The zone that holds a full copy of everything. The owner, asked what it is
# for: it is the FALLBACK -- when the specific zones are there the tool builds
# from them and ignores this one; when they are not, this is an ordinary
# drawing and builds as it always has.
COMBINE_TOKEN = "combine"

# Which categories a zone's NAME claims, ONE ELEMENT AT A TIME. The owner, on a
# first cut that bundled them: "make left side independent of each element. like
# don't do beam+slab+stairs there. only do the beam, slab and stair separately
# [...] because sometimes user can also separate those in each boundaries or
# grid+column etc also." A bundle is a guess about how somebody draws; a token
# per element is the drawing's own word for it, and a name carrying two of them
# (`Beam-Slab-boundary`) claims both.
#
# Only ever a FALLBACK now: `suggest_element_zones` reads the drawing instead,
# which answers a `Stair-boundary` correctly and no naming convention would.
_CONVENTION = (
    ("grid", (CATEGORY_GRID,)),
    ("col", (CATEGORY_COLUMN,)),
    ("beam", (CATEGORY_BEAM,)),
    # a slab's own features travel with it: a fold, a sunk step, a cutout and a
    # slab stop are all edges OF a slab, drawn beside it and never on their own
    ("slab", (CATEGORY_SLAB_EDGE, CATEGORY_FOLD, CATEGORY_SUNK,
              CATEGORY_CUTOUT, CATEGORY_SLAB_STOP)),
    ("stair", (CATEGORY_STAIR,)),
    ("wall", (CATEGORY_STRUCT_WALL, CATEGORY_ARCH_WALL)),
    ("found", (CATEGORY_FOUNDATION,)),
    ("footing", (CATEGORY_FOUNDATION,)),
)

# The rows the dialog's table shows, top to bottom: one per element the user
# might give a zone of its own. `_CONVENTION` says what a NAME means; this says
# what the table asks about.
ZONED_CATEGORIES = (
    CATEGORY_GRID, CATEGORY_COLUMN, CATEGORY_BEAM, CATEGORY_SLAB_EDGE,
    CATEGORY_STAIR, CATEGORY_STRUCT_WALL, CATEGORY_ARCH_WALL,
    CATEGORY_FOUNDATION, CATEGORY_FOLD, CATEGORY_SUNK, CATEGORY_CUTOUT,
    CATEGORY_SLAB_STOP,
)

# What a row says when no zone owns that element: it is read wherever it is
# drawn, which is what every drawing without zones has always done.
ANY_ZONE = "(wherever it is drawn)"

# Two boxes are the same size when they differ by less than this, in feet. The
# zone boxes in the example are identical to well under a millimetre; this only
# has to absorb the drafting noise of a copied rectangle.
_SAME_BOX_FT = 10.0 / 304.8


def is_zone_layer(layer, storey_layer=None):
    """Whether a layer names a ZONE box rather than the storey boundary.

    The storey layer is excluded by name because it ends the same way: the
    owner's sheet has `Boundary` holding `Grid-Column-boundary` and the rest.
    """
    name = str(layer or "").strip()
    if not name:
        return False
    if storey_layer and name.lower() == str(storey_layer).strip().lower():
        return False
    return name.lower().endswith(ZONE_SUFFIX)


def is_combine(layer):
    """Whether this zone is the full copy that only stands in when alone."""
    return COMBINE_TOKEN in str(layer or "").lower()


def default_categories(layer):
    """The categories a zone claims, read off its name; None when it claims all.

    None is the combine zone's answer, and any zone whose name says nothing we
    recognise: taking everything is the safe reading, because a zone that
    claimed nothing would silently drop the drawing it holds.
    """
    name = str(layer or "").lower()
    claimed = []
    for token, categories in _CONVENTION:
        if token in name:
            for category in categories:
                if category not in claimed:
                    claimed.append(category)
    return tuple(claimed) or None


def suggest_element_zones(records, zone_list=None, storey_layer=None,
                          origin_layer=None):
    """{category: zone layer} read off THE DRAWING, for the table's first draft.

    Each element goes to the zone whose box actually holds the most records of
    it. That is better than reading the zone names, and not by a little: it
    answers a `Stair-boundary` or a `Zone-3` correctly, it survives an office
    that names its boxes in another language, and it cannot disagree with what
    is drawn -- which a convention can, quietly.

    The COMBINED copy is left out of the count. It holds a copy of everything,
    so it would win every row and the table would say the drawing has no zones
    at all.

    An element no zone holds comes back as `ANY_ZONE`: read wherever it is
    drawn, which is what a drawing without zones has always done.
    """
    zone_list = (zone_list if zone_list is not None
                 else zones(records, storey_layer, origin_layer))
    specific = [zone for zone in zone_list if not is_combine(zone.layer)]
    counts = {}
    for record in records or ():
        category = getattr(record, "category", None)
        if category not in ZONED_CATEGORIES:
            continue
        points = getattr(record, "points", None) or []
        if not points:
            continue
        x, y = _record_point(record)
        for zone in specific:
            if zone.contains(x, y):
                seen = counts.setdefault(category, {})
                seen[zone.layer] = seen.get(zone.layer, 0) + 1
                break
    out = {}
    for category in ZONED_CATEGORIES:
        seen = counts.get(category) or {}
        if not seen:
            out[category] = ANY_ZONE
            continue
        # the zone holding the most of them; the name breaks a tie, so the
        # answer does not depend on the order the records were read in
        out[category] = max(sorted(seen), key=lambda layer: seen[layer])
    return out


def zone_choices(zone_list):
    """What the table's dropdown offers: every zone, and "wherever it is drawn".

    The combined copy is not offered. It is the fallback for a drawing that has
    no specific zones, and pointing an element at it while specific zones exist
    would ask for the copy that is deliberately not built.
    """
    names = [zone.layer for zone in (zone_list or ())
             if not is_combine(zone.layer)]
    seen, ordered = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered + [ANY_ZONE]


def claims_from_elements(element_zones):
    """{zone layer: (categories)} -- the table's answer, turned back round.

    The table asks per ELEMENT ("where do beams come from?"); the fold works per
    ZONE ("what does this box hold?"). This is the one place the two meet.
    """
    claims = {}
    for category, layer in (element_zones or {}).items():
        if not layer or str(layer) == ANY_ZONE:
            continue
        claims.setdefault(layer, [])
        if category not in claims[layer]:
            claims[layer].append(category)
    return dict((layer, tuple(categories))
                for layer, categories in claims.items())


class Zone(object):
    """One zone box: its layer, its bounds, its origin marker."""

    def __init__(self, layer, bounds, origin=None):
        self.layer = layer
        self.bounds = bounds          # (x0, y0, x1, y1) in internal feet
        self.origin = origin          # (x, y) in feet, or None

    def contains(self, x, y):
        x0, y0, x1, y1 = self.bounds
        return x0 <= x <= x1 and y0 <= y <= y1

    def inside(self, other):
        """Whether this box sits within `other`."""
        return (self.bounds[0] >= other.bounds[0] - _SAME_BOX_FT
                and self.bounds[1] >= other.bounds[1] - _SAME_BOX_FT
                and self.bounds[2] <= other.bounds[2] + _SAME_BOX_FT
                and self.bounds[3] <= other.bounds[3] + _SAME_BOX_FT)

    @property
    def corner(self):
        return (self.bounds[0], self.bounds[1])

    def __repr__(self):
        return "<Zone {0} {1:.0f}x{2:.0f}ft>".format(
            self.layer, self.bounds[2] - self.bounds[0],
            self.bounds[3] - self.bounds[1])


def zones(records, storey_layer=None, origin_layer=None):
    """[Zone] -- every zone box in the drawing, with its own origin marker.

    A zone box is a closed rectangle on a layer ending `-boundary` that is not
    the storey layer. Its origin is the marker inside it; a zone without one
    cannot be folded onto the others and is reported rather than guessed at.

    `origin_layer` names the marker layer when the caller knows it, so this can
    run before any layer mapping exists -- the same route every marker reader
    in `floor_plans` takes.
    """
    found = []
    for record in records or ():
        layer = getattr(record, "layer", None)
        if not is_zone_layer(layer, storey_layer):
            continue
        points = getattr(record, "points", None) or []
        if len(points) < 3:
            continue
        found.append(Zone(layer, _record_bounds(record)))
    if not found:
        return []
    # A box that HOLDS other zone boxes is the storey boundary, whatever it is
    # called: the owner's sheet has `Boundary` holding four zones and every one
    # of those names ends the same way. Told apart by shape rather than by the
    # layer the dialog happened to pick, so leaving that picker empty cannot
    # fold the whole sheet onto one of its own quarters.
    found = [zone for zone in found
             if not any(other is not zone and other.inside(zone)
                        for other in found)]
    if not found:
        return []
    markers = origin_points(records, origin_layer)
    for zone in found:
        inside = [p for p in markers if zone.contains(p[0], p[1])]
        zone.origin = inside[0] if inside else None
    return found


def storey_boxes(records, storey_layer=None):
    """[Zone] -- the storey boundary boxes, as zones of their own.

    They are read here rather than borrowed from `floor_plans.boundary_regions`
    because that one dissolves nested boxes: inside a zone, the storey boxes
    ARE nested (in the sheets-inside-a-zone layout) and dissolving them would
    leave one box per zone instead of one per floor.
    """
    name = str(storey_layer or "").strip().lower()
    found = []
    for record in records or ():
        layer = str(getattr(record, "layer", "") or "").strip()
        category = getattr(record, "category", None)
        if name:
            if layer.lower() != name:
                continue
        elif category != CATEGORY_FLOOR_BOUNDARY or is_zone_layer(layer):
            continue
        points = getattr(record, "points", None) or []
        if len(points) < 3:
            continue
        found.append(Zone(layer, _record_bounds(record)))
    return found


def _cells(zone_list, storeys, markers=()):
    """[[Zone]] -- the cells to fold together, one group per storey.

    A CELL is the innermost box of one zone on one storey, and it is the piece
    that gets shifted: its origin marker sits inside it in both layouts. Which
    layout the drawing uses is read off containment, never off a setting:

      * zones inside a storey -- each storey box holds one box per zone, and a
        group is the zones inside that storey;
      * storeys inside a zone -- each zone box holds one box per storey, and a
        group is the boxes at the SAME PLACE inside their own zones. Position
        within the zone is what pairs them, because every zone is a copy of the
        same sheet: the ground floor sits at the same offset in the column copy
        as it does in the beam copy. Pairing by order would put a zone that is
        missing a floor out of step with the rest, silently.
    """
    if not zone_list:
        return []
    if not storeys:
        return [list(zone_list)]
    nested = [s for s in storeys
              if any(s.inside(z) for z in zone_list)]
    if nested:
        groups = {}
        for storey in nested:
            home = next((z for z in zone_list if storey.inside(z)), None)
            if home is None or home.origin is None:
                continue
            # where this storey sits inside its own zone, to the millimetre
            place = (round((storey.bounds[0] - home.origin[0]) * 304.8),
                     round((storey.bounds[1] - home.origin[1]) * 304.8))
            cell = Zone(home.layer, storey.bounds)
            inside = [p for p in markers if cell.contains(p[0], p[1])]
            cell.origin = inside[0] if inside else None
            groups.setdefault(place, []).append(cell)
        return [groups[place] for place in sorted(groups)]
    # zones inside a storey: group each zone by the storey box holding it
    groups = {}
    for zone in zone_list:
        home = next((s for s in storeys if zone.inside(s)), None)
        key = home.corner if home is not None else None
        groups.setdefault(key, []).append(zone)
    return [groups[key] for key in sorted(groups, key=lambda k: k or (0.0, 0.0))]


def merge_zones(records, texts=None, hatches=None, storey_layer=None,
                mapping=None, marker_records=None, origin_layer=None,
                element_zones=None):
    """(records, texts, hatches, notes) with every zone folded onto one plan.

    This runs BEFORE `split_floors` and hands it a drawing shaped exactly like
    the ones it has always read: one copy of the plan, in one frame. Everything
    downstream -- beams trimmed at columns, slab loops closed from beams and
    edges, the legend, the schedule -- therefore keeps working unchanged, which
    is the point of folding here rather than teaching every pass about zones.

    A drawing with NO zone layer comes back untouched, so every existing sheet
    reads exactly as it did.

    `mapping` is {zone layer: [categories it claims]}, from the dialog; a zone
    the mapping does not name falls back to the convention in its own name. A
    record whose category the zone does not claim is dropped and counted -- the
    2 stray column records in the example's Wall zone are how a copy-paste slip
    shows up, and they should not become columns a metre from the real ones.

    `marker_records` supplies the zone boxes and origin markers when they are
    not in `records`, exactly as `split_floors` takes them: a plan's origin is a
    bare POINT and the Revit link does not always import one, so the boxes are
    read from the DXF and the RECORDS folded by them are the Revit ones the
    build uses.
    """
    markers_from = marker_records if marker_records is not None else records
    zone_list = zones(markers_from, storey_layer, origin_layer)
    if element_zones:
        # the dialog answers per element; the fold asks per zone
        mapping = claims_from_elements(element_zones)
    if not zone_list:
        return list(records or ()), list(texts or ()), list(hatches or ()), []

    notes = []
    markers = origin_points(markers_from, origin_layer)
    groups = _cells(zone_list, storey_boxes(markers_from, storey_layer),
                    markers)

    kept_records, kept_texts, kept_hatches = [], [], []
    claimed_records, claimed_texts, claimed_hatches = set(), set(), set()
    unclaimed = {}
    folded = 0
    for group in groups:
        # A zone the table was told to SKIP is used up unbuilt, like the
        # combined copy: "nothing" is an answer, and a zone that claims no
        # category must not have its contents fall through as strays.
        skipped_zones = [cell for cell in group
                         if not is_combine(cell.layer)
                         and _claimed_by(cell.layer, mapping) == ()]
        for cell in skipped_zones:
            notes.append("zone '{0}' is set to build nothing, so its contents "
                         "were left out".format(cell.layer))
        group = [cell for cell in group if cell not in skipped_zones]
        group, spare = _without_combine(group, notes)
        spare = list(spare) + skipped_zones
        # the combined copy is USED UP, not merely skipped. Leaving its records
        # unclaimed would drop them straight back into the plan as strays and
        # build the whole drawing twice -- which is what the owner's 0.97.1 run
        # did with this very file: 346 columns, 178 of them the combine copy's.
        for cell in spare:
            _consume(cell, records, texts, hatches,
                     claimed_records, claimed_texts, claimed_hatches,
                     storey_layer)
        usable = [cell for cell in group if cell.origin is not None]
        for cell in group:
            if cell.origin is None:
                notes.append("zone '{0}' has no origin marker inside it -- it "
                             "cannot be folded onto the others and was left "
                             "where it is drawn".format(cell.layer))
        if not usable:
            continue
        anchor = min(usable, key=lambda cell: str(cell.layer).lower())
        folded += len(usable)
        # what the OTHER zones in this group claim: a record is only turned away
        # for being in the wrong zone when another zone is the right one. A
        # category nobody claims stays where it is drawn rather than vanishing.
        spoken_for = set()
        for cell in usable:
            for category in _claimed_by(cell.layer, mapping) or ():
                spoken_for.add(category)
        for cell in usable:
            dx = anchor.origin[0] - cell.origin[0]
            dy = anchor.origin[1] - cell.origin[1]
            takes = _claimed_by(cell.layer, mapping)
            for record in records or ():
                if id(record) in claimed_records:
                    continue
                layer = getattr(record, "layer", None)
                if is_zone_layer(layer, storey_layer):
                    claimed_records.add(id(record))     # the box itself is used up
                    continue
                x, y = _record_point(record)
                if not cell.contains(x, y):
                    continue
                claimed_records.add(id(record))
                category = getattr(record, "category", None)
                if category in (CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN):
                    # one storey box and one origin survive a fold, the
                    # anchor's; the others would land on top of it and be read
                    # as a second storey drawn in the same place
                    if cell is anchor:
                        kept_records.append(_shift_record(record, dx, dy))
                    continue
                if (takes is not None and category not in takes
                        and category in spoken_for):
                    unclaimed.setdefault(cell.layer, {})
                    unclaimed[cell.layer][category] = (
                        unclaimed[cell.layer].get(category, 0) + 1)
                    continue
                kept_records.append(_shift_record(record, dx, dy))
            for text in texts or ():
                point = getattr(text, "point_internal", None)
                if point is None or id(text) in claimed_texts:
                    continue
                if not cell.contains(point[0], point[1]):
                    continue
                claimed_texts.add(id(text))
                kept_texts.append(_shift_text(text, dx, dy))
            for hatch in hatches or ():
                if id(hatch) in claimed_hatches:
                    continue
                x, y = _record_point(hatch)
                if not cell.contains(x, y):
                    continue
                claimed_hatches.add(id(hatch))
                kept_hatches.append(_shift_record(hatch, dx, dy))

    # everything the zones did not take keeps its place: a schedule table beside
    # the plan, a note in the title block. Said out loud rather than dropped,
    # because a member that missed its zone box looks exactly like this.
    strays = [r for r in (records or ()) if id(r) not in claimed_records]
    outside = {}
    for record in strays:
        category = getattr(record, "category", None)
        outside[category] = outside.get(category, 0) + 1
    kept_records.extend(strays)
    kept_texts.extend(t for t in (texts or ()) if id(t) not in claimed_texts)
    kept_hatches.extend(h for h in (hatches or ())
                        if id(h) not in claimed_hatches)

    notes.insert(0, "boundary zones: {0} folded onto one plan by their origin "
                    "markers".format(folded))
    for layer, dropped in sorted(unclaimed.items()):
        notes.append("zone '{0}' held {1} -- not what this zone is for, so it "
                     "was left out".format(
                         layer, ", ".join("{0} {1}".format(count, name)
                                          for name, count in sorted(
                                              dropped.items(),
                                              key=lambda item: str(item[0])))))
    named = [(name, count) for name, count in outside.items()
             if name not in (CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN,
                             None, "unmapped")]
    if named:
        notes.append("{0} record(s) sit inside no zone at all and were kept "
                     "where they are drawn: {1}".format(
                         sum(count for _n, count in named),
                         ", ".join("{0} {1}".format(count, name)
                                   for name, count in sorted(
                                       named, key=lambda item: str(item[0])))))
    return kept_records, kept_texts, kept_hatches, notes


def _consume(cell, records, texts, hatches, seen_records, seen_texts,
             seen_hatches, storey_layer=None):
    """Mark everything inside `cell` as dealt with, keeping none of it."""
    for record in records or ():
        if id(record) in seen_records:
            continue
        x, y = _record_point(record)
        if cell.contains(x, y):
            seen_records.add(id(record))
    for text in texts or ():
        point = getattr(text, "point_internal", None)
        if point is None or id(text) in seen_texts:
            continue
        if cell.contains(point[0], point[1]):
            seen_texts.add(id(text))
    for hatch in hatches or ():
        if id(hatch) in seen_hatches:
            continue
        x, y = _record_point(hatch)
        if cell.contains(x, y):
            seen_hatches.add(id(hatch))


def _without_combine(group, notes):
    """(the cells to fold, the cells to consume unbuilt).

    The owner's answer, on what the combine zone is for: it is the fallback. Its
    copy of the drawing is what a reader looks at, and what builds when no
    specific zone exists -- but with the specific zones there it would build
    every element a second time, which is exactly what his 0.97.1 run did: 346
    columns, 178 of them from the combine copy and 168 from the column zone.
    """
    specific = [cell for cell in group if not is_combine(cell.layer)]
    if not specific:
        return list(group), []
    combined = [cell for cell in group if is_combine(cell.layer)]
    for cell in combined:
        notes.append("zone '{0}' is the combined copy and the drawing has "
                     "{1} specific zone(s), so it was not built twice".format(
                         cell.layer, len(specific)))
    return specific, combined


def _claimed_by(layer, mapping):
    """The categories this zone takes: the dialog's answer, else the name's.

    `mapping` is {zone layer: categories}, which is what the dialog's per-element
    table comes to through `claims_from_elements`. An empty tuple is a real
    answer -- this zone holds nothing the build wants -- and is kept apart from
    None, which means everything in it.
    """
    if mapping:
        for key, answer in mapping.items():
            if str(key).strip().lower() != str(layer).strip().lower():
                continue
            return None if answer is None else tuple(answer)
        # A zone the table names NOTHING for holds nothing the build wants: the
        # user pointed every element somewhere else. Its contents are turned
        # away by the same rule a stray column in the wall zone is.
        return ()
    return default_categories(layer)
