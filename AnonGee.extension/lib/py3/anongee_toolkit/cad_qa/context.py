# -*- coding: utf-8 -*-
"""One drawing, read and classified once, ready for every check to interrogate.

Reading a 33 MB DXF takes seconds and classifying it takes milliseconds; doing
either four times because four check families each wanted it would be the
tool's whole runtime. So the read and the classification happen HERE, exactly
once, and the checks are pure functions of the result.

UNITS. cad2bim asks the user for the drawing unit in its link dialog, because a
DXF does not reliably say. This tool has no user to ask, so it assumes
MILLIMETRES -- which is what every drawing in the corpus is, and what the
regression harness assumes when it scales by 1/304.8. ``unit_mm`` overrides it
(``unit_mm=1000`` for a drawing in metres), and rule G007 is the check that
catches an assumption that was wrong: a plan that comes out 40 mm across was
drawn in metres and read as millimetres.

Everything this class exposes is in DRAWING UNITS except the ``_mm`` helpers,
which apply ``unit_mm``. Mixing the two silently is how a check ends up
comparing a tolerance in millimetres against a coordinate in feet, so the
suffix is on every name that carries a converted value.
"""

from .deps import dxf_reader, layers, marks, config

__version__ = "1.0.0"

#: A ring is treated as closed when its ends are within this fraction of its
#: own size. Relative, not absolute: a 300 mm column outline and a 40 m raft
#: outline do not deserve the same gap allowance, and an absolute tolerance
#: generous enough for the raft closes the column by accident.
CLOSE_RATIO = 0.01

#: Below this a ring is too small to be any member -- a leftover vertex pair,
#: not a column. In drawing units squared at unit_mm=1 (i.e. mm^2).
MIN_RING_AREA_MM2 = 100.0 * 100.0


class DrawingContext(object):
    """The read drawing plus the classification every check shares."""

    def __init__(self, result, unit_mm=1.0, tolerances=None,
                 layer_overrides=None):
        self.result = result
        self.unit_mm = float(unit_mm or 1.0)
        self.tolerances = dict(config.DEFAULTS)
        if tolerances:
            self.tolerances.update(tolerances)

        self.records = list(getattr(result, "records", []) or [])
        self.texts = list(getattr(result, "texts", []) or [])
        self.regions = list(getattr(result, "regions", []) or [])

        # --- classification, once ------------------------------------------
        geometry_layers = sorted(set(r.layer_key for r in self.records))
        self.mapping = layers.build_default_mapping(geometry_layers)
        if layer_overrides:
            self.mapping.update(layer_overrides)
        layers.apply_mapping(self.records, self.mapping)

        text_layers = sorted(set(t.layer_key for t in self.texts))
        self.text_mapping = layers.build_default_text_mapping(text_layers)

        hatch_layers = sorted(set(r.layer_key for r in self.regions))
        self.hatch_mapping = layers.build_default_hatch_mapping(hatch_layers)
        layers.apply_hatch_mapping(self.regions, self.hatch_mapping)

        # --- marks parsed onto the texts, once -----------------------------
        marks.parse_texts(self.texts)
        self._schedule = None

    # -- convenience accessors ---------------------------------------------

    @property
    def schedule(self):
        """The drawing's mark/size table, parsed once, or {}.

        Lazy because parsing it walks every text on the sheet and only one
        check asks. Cached because that check must not pay for it twice, and
        because the answer cannot change -- the texts are already read.
        """
        if self._schedule is None:
            try:
                self._schedule = marks.parse_schedule(self.texts) or {}
            except Exception:
                # A schedule that will not parse is a fact about the drawing,
                # not a reason to lose the other twenty-seven checks.
                self._schedule = {}
        return self._schedule

    @property
    def source(self):
        return getattr(self.result, "source_name", "") or ""

    def to_mm(self, value):
        return float(value) * self.unit_mm

    def point_mm(self, point):
        """(x, y) of a drawing point in millimetres, for a finding's location."""
        if not point:
            return None
        return (self.to_mm(point[0]), self.to_mm(point[1]))

    def records_by_layer(self):
        out = {}
        for record in self.records:
            out.setdefault(record.layer_key, []).append(record)
        return out

    def records_by_category(self):
        out = {}
        for record in self.records:
            out.setdefault(record.category, []).append(record)
        return out

    def texts_by_layer(self):
        out = {}
        for text in self.texts:
            out.setdefault(text.layer_key, []).append(text)
        return out

    def regions_by_layer(self):
        out = {}
        for region in self.regions:
            out.setdefault(region.layer_key, []).append(region)
        return out

    def count_in(self, category):
        return sum(1 for r in self.records if r.category == category)

    def extent(self):
        """(min_x, min_y, max_x, max_y) over every record point, drawing units.

        None for a drawing with no geometry -- the caller checks, because an
        extent of (0, 0, 0, 0) is a real answer for a degenerate drawing and
        must not be confused with "nothing to measure".
        """
        xs = []
        ys = []
        for record in self.records:
            for point in record.points:
                xs.append(point[0])
                ys.append(point[1])
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def extent_mm(self):
        box = self.extent()
        if box is None:
            return None
        return tuple(self.to_mm(v) for v in box)

    def stats(self):
        """What the run measured. The denominator a reader judges findings by."""
        counts = {}
        for record in self.records:
            counts[record.category] = counts.get(record.category, 0) + 1
        box = self.extent_mm()
        out = {
            "records": len(self.records),
            "texts": len(self.texts),
            "regions": len(self.regions),
            "layers": len(set(r.layer_key for r in self.records)),
            "by_category": counts,
            "unit_mm": self.unit_mm,
        }
        if box:
            out["extent_mm"] = {
                "width": int(round(box[2] - box[0])),
                "height": int(round(box[3] - box[1])),
            }
        return out


def read(path, unit_mm=1.0, tolerances=None, layer_overrides=None):
    """Read one DXF and return its :class:`DrawingContext`.

    Raises whatever the reader raises. The CLI turns that into a finding; a
    library caller usually wants the exception.
    """
    result = dxf_reader.read_dxf(path)
    return DrawingContext(result, unit_mm=unit_mm, tolerances=tolerances,
                          layer_overrides=layer_overrides)


# -- shared geometry helpers, used by more than one check family ------------

def ring_points(record):
    """The record's points as a list, or [] when it carries none."""
    return list(getattr(record, "points", None) or [])


def is_closed(points, ratio=CLOSE_RATIO):
    """Whether a point run closes, judged against its OWN size.

    Two points can never enclose anything, so they are never closed. The
    tolerance is a fraction of the ring's bounding box rather than a fixed
    distance -- see CLOSE_RATIO.
    """
    if len(points) < 3:
        return False
    first, last = points[0], points[-1]
    gap = _distance(first, last)
    if gap == 0.0:
        return True
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    size = max(max(xs) - min(xs), max(ys) - min(ys))
    if size <= 0.0:
        return gap == 0.0
    return gap <= size * ratio


def bbox_area(points):
    """Bounding-box area of a point run. Cheap stand-in for the real area.

    A QA check asks "is this big enough to be a member", and for that question
    the bounding box is the right tool: it never under-reports, so a ring is
    never dismissed as too small when it is not.
    """
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
