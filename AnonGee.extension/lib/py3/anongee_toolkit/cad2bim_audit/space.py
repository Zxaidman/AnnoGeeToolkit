# -*- coding: utf-8 -*-
"""One coordinate space for four sources, so their numbers can be compared.

The four stages arrive in three different spaces and two different units: the
DXF in drawing units, the Revit link and the model in internal feet. Comparing
them at all means picking a common space, and the report carries BOTH -- a
position in DXF-space millimetres is what you type into AutoCAD's coordinate
readout to land on the entity, and a position in Revit-space millimetres is
where the element sits in the model. Neither alone lets you go and look at the
thing that went wrong.

So every item stores both, and records which one was MEASURED and which was
derived (`native_space`), because a derived coordinate is only ever as good as
the transform -- and the transform is one of the things the audit is checking.

The affine is the link's own `GetTotalTransform()`, taken from cad2bim's
`geom.transform.from_link`. Inverting it here (rather than fitting a second,
independent transform) is deliberate: a bug in the forward map then shows up as
both coordinate columns being consistently wrong together, which is visible,
instead of two independent fits disagreeing in a way nobody can attribute.

Revit-free and plain floats, so it is tested outside Revit.
"""

from . import config

#: One DXF drawing unit, in millimetres, for the units the Link CAD dialog offers.
#: Keyed by the labels `cad2bim.readers.dxf_linker.UNIT_CHOICES` uses, so the
#: dialog's own choice can be handed straight over.
UNIT_MM = {
    "Millimeter": 1.0,
    "Centimeter": 10.0,
    "Decimeter": 100.0,
    "Meter": 1000.0,
    "Foot": config.MM_PER_FT,
    "Inch": config.MM_PER_FT / 12.0,
}

_SINGULAR_EPS = 1e-12


def invert_rows(rows):
    """Invert a 3x4 affine given as [[a,b,c,tx],[d,e,f,ty],[g,h,i,tz]].

    Returns the inverse in the same shape, or None when the matrix is singular
    -- which a real link transform never is, but a hand-built or corrupted one
    can be, and a report must degrade to blank cells rather than raise.
    """
    a, b, c = rows[0][0], rows[0][1], rows[0][2]
    d, e, f = rows[1][0], rows[1][1], rows[1][2]
    g, h, i = rows[2][0], rows[2][1], rows[2][2]

    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < _SINGULAR_EPS:
        return None

    # Adjugate transposed / det -- the standard closed-form 3x3 inverse.
    inv = [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]
    tx, ty, tz = rows[0][3], rows[1][3], rows[2][3]
    # The inverse translation is -M^-1 * t.
    return [
        inv[0] + [-(inv[0][0] * tx + inv[0][1] * ty + inv[0][2] * tz)],
        inv[1] + [-(inv[1][0] * tx + inv[1][1] * ty + inv[1][2] * tz)],
        inv[2] + [-(inv[2][0] * tx + inv[2][1] * ty + inv[2][2] * tz)],
    ]


def apply_rows(rows, point):
    """p' = M * p + t for a 3x4 affine."""
    x, y, z = point[0], point[1], point[2]
    return (rows[0][0] * x + rows[0][1] * y + rows[0][2] * z + rows[0][3],
            rows[1][0] * x + rows[1][1] * y + rows[1][2] * z + rows[1][3],
            rows[2][0] * x + rows[2][1] * y + rows[2][2] * z + rows[2][3])


class Space(object):
    """Maps a point from whichever space it was read in into both report spaces.

    `dxf_unit_mm` converts DXF drawing units to millimetres. `forward_rows` is
    the DXF-units -> Revit-internal-feet affine from the link; pass None when no
    link was read, and the Revit-space columns simply stay empty (the audit is
    still perfectly useful on the DXF alone).
    """

    def __init__(self, dxf_unit_mm=1.0, forward_rows=None, method="none"):
        self.dxf_unit_mm = float(dxf_unit_mm)
        self.forward_rows = forward_rows
        self.inverse_rows = invert_rows(forward_rows) if forward_rows else None
        # How the forward map was obtained, for the Transform & settings sheet:
        # "link_transform", "empirical_bbox", or "none".
        self.method = method
        # Set when a forward map exists but could not be inverted, so the report
        # can say why the DXF-space columns are blank for Revit-read items.
        self.inverse_error = ("transform is singular; Revit-read items have no "
                              "DXF-space coordinates"
                              if forward_rows and self.inverse_rows is None
                              else None)

    @property
    def has_link(self):
        return self.forward_rows is not None

    # -- from the DXF ------------------------------------------------------
    def from_dxf(self, points):
        """DXF drawing units -> (dxf_space_mm, revit_space_mm).

        The second is None when no link transform is available.
        """
        if not points:
            return [], None
        dxf_mm = [(p[0] * self.dxf_unit_mm,
                   p[1] * self.dxf_unit_mm,
                   p[2] * self.dxf_unit_mm) for p in points]
        if self.forward_rows is None:
            return dxf_mm, None
        revit_mm = [_ft_point_to_mm(apply_rows(self.forward_rows, p)) for p in points]
        return dxf_mm, revit_mm

    # -- from Revit --------------------------------------------------------
    def from_revit(self, points_ft):
        """Revit internal feet -> (dxf_space_mm, revit_space_mm).

        The first is None when there is no invertible link transform.
        """
        if not points_ft:
            return None, []
        revit_mm = [_ft_point_to_mm(p) for p in points_ft]
        if self.inverse_rows is None:
            return None, revit_mm
        dxf_mm = []
        for point in points_ft:
            units = apply_rows(self.inverse_rows, point)
            dxf_mm.append((units[0] * self.dxf_unit_mm,
                           units[1] * self.dxf_unit_mm,
                           units[2] * self.dxf_unit_mm))
        return dxf_mm, revit_mm

    def describe(self):
        """Rows for the Transform & settings sheet: (label, value) pairs."""
        rows = [
            ("Transform source", self.method),
            ("DXF unit in mm", self.dxf_unit_mm),
            ("Link transform available", "yes" if self.has_link else "no"),
        ]
        if self.forward_rows:
            for index, row in enumerate(self.forward_rows):
                rows.append(("Forward row {0} (DXF units -> ft)".format(index),
                             ", ".join("{0:.9g}".format(v) for v in row)))
        if self.inverse_error:
            rows.append(("Inverse", self.inverse_error))
        return rows


def _ft_point_to_mm(point):
    return (point[0] * config.MM_PER_FT,
            point[1] * config.MM_PER_FT,
            point[2] * config.MM_PER_FT)


def from_link_instance(import_instance, unit_label="Millimeter"):
    """Build a Space from a live Revit ImportInstance. Revit-only caller.

    Kept here (rather than in a reader) so every construction of a Space is in
    one file; the Revit types are touched only inside this function, which the
    tests never call.
    """
    transform = import_instance.GetTotalTransform()
    bx, by, bz, origin = (transform.BasisX, transform.BasisY, transform.BasisZ,
                          transform.Origin)
    rows = [
        [bx.X, by.X, bz.X, origin.X],
        [bx.Y, by.Y, bz.Y, origin.Y],
        [bx.Z, by.Z, bz.Z, origin.Z],
    ]
    return Space(UNIT_MM.get(unit_label, 1.0), rows, method="link_transform")
