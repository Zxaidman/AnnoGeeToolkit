# -*- coding: utf-8 -*-
"""What a flight of stairs *is*, in numbers, before any of it reaches Revit.

Kept pure and kept separate because the arithmetic here is the part that is
easy to get subtly wrong and impossible to check by looking at a model. A
staircase that is one riser out arrives at the floor looking almost right.

**The rule that governs everything below.** A flight has to land exactly on the
floor above. So the ``Riser`` on the types sheet is a *nominal* — what the
engineer wants — and the riser actually built is the rise divided by a whole
number of steps. 3300 over a nominal 165 gives 20 risers of exactly 165; move
that level to 3320 and it gives 20 risers of 166, not 20 of 165 and a 20 mm
step at the top.

**And the one that decides the shape.** ``n`` risers have ``n - 1`` treads.
The last riser is the one that lands on the floor slab, so it has no tread of
its own — which is why the waist's top line stops one riser short of the floor
and a vertical face closes the gap.
"""

from anongee_toolkit.rc_automation import models

__version__ = "0.1.0"

#: A flight with fewer than this is a step, not a staircase, and almost
#: certainly two levels that are nearly the same height.
MINIMUM_RISERS = 2

#: Beyond this the sheet is describing something that is not one flight.
MAXIMUM_RISERS = 60


class Flight(object):
    """One flight, solved. Every number here is millimetres except ``risers``."""

    __slots__ = ("risers", "riser_mm", "tread_mm", "run_mm", "rise_mm",
                 "width_mm", "waist_mm", "nominal_riser_mm")

    def __init__(self, risers, riser_mm, tread_mm, run_mm, rise_mm,
                 width_mm, waist_mm, nominal_riser_mm):
        self.risers = risers
        self.riser_mm = riser_mm
        self.tread_mm = tread_mm
        self.run_mm = run_mm
        self.rise_mm = rise_mm
        self.width_mm = width_mm
        self.waist_mm = waist_mm
        self.nominal_riser_mm = nominal_riser_mm

    @property
    def treads(self):
        """``risers - 1``. The last riser lands on the floor and has no tread."""
        return self.risers - 1

    @property
    def waist_top_rise_mm(self):
        """How far the waist's top line climbs — one riser short of the floor."""
        return self.rise_mm - self.riser_mm

    @property
    def step_volume_m3(self):
        """The triangular bit above the waist, for all the steps.

        Half a tread by a riser by the width, per step. **Half**, because a step
        is a triangular prism and not a box — modelling it as a box doubles
        every step in the building's concrete take-off.
        """
        return (0.5 * self.tread_mm * self.riser_mm * self.width_mm
                * self.treads) / 1.0e9

    @property
    def waist_volume_m3(self):
        """Slope length by waist thickness by width. The thickness is measured
        **perpendicular to the slope**, which is what makes the slope length —
        not the run — the right multiplier."""
        return (self.slope_length_mm * self.waist_mm * self.width_mm) / 1.0e9

    @property
    def slope_length_mm(self):
        rise = self.waist_top_rise_mm
        return (self.run_mm ** 2 + rise ** 2) ** 0.5

    @property
    def volume_m3(self):
        return self.waist_volume_m3 + self.step_volume_m3

    @property
    def pitch_degrees(self):
        import math
        if self.run_mm <= 0:
            return 90.0
        return math.degrees(math.atan2(self.waist_top_rise_mm, self.run_mm))

    def corners_mm(self):
        """``[(along, up)]`` — the internal corners, where the waist line runs.

        ``along`` is measured from the bottom of the flight in plan, ``up`` from
        the floor it starts on. The first is the foot of the first riser and the
        last is one riser below the floor above.
        """
        return [(index * self.tread_mm, index * self.riser_mm)
                for index in range(self.risers)]

    def steps_mm(self):
        """``[(along0, up0, along1, up1)]`` — one per tread.

        Each is the right triangle sitting on the waist: the vertical riser
        face at ``along0``, the horizontal tread at ``up1``, and the waist line
        closing it.
        """
        found = []
        for index in range(self.treads):
            found.append((index * self.tread_mm, index * self.riser_mm,
                          (index + 1) * self.tread_mm,
                          (index + 1) * self.riser_mm))
        return found


def solve(rise_mm, sizes, sheet="", row=None, mark="", available_mm=None):
    """``(Flight, [Issue])`` — or ``(None, [Issue])`` when it cannot be one.

    *available_mm* is how far apart the two grid intersections are. It does not
    set the run — the tread does — but a flight that needs more room than the
    sheet's own geometry allows is reported, because that is a drawing error
    somebody has to see rather than a number to quietly honour.
    """
    issues = []

    def problem(message, column="", severity=models.SEVERITY_ERROR):
        issues.append(models.Issue(severity, message, sheet=sheet, row=row,
                                   column=column))

    width = _positive(sizes.get("width_mm"))
    waist = _positive(sizes.get("waist_mm"))
    tread = _positive(sizes.get("tread_mm"))
    nominal = _positive(sizes.get("riser_mm"))

    missing = [name for name, value in (("Width", width), ("Waist", waist),
                                        ("Tread", tread), ("Riser", nominal))
               if value is None]
    if missing:
        problem("{0} needs {1} on the types sheet, and it is blank.".format(
            mark or "this stair", " and ".join(missing)), column=missing[0])
        return None, issues

    if not rise_mm or rise_mm <= 0:
        problem("{0} rises {1:g} mm — its two levels are the same height, or "
                "the wrong way round.".format(mark or "this stair",
                                              rise_mm or 0.0), column="Level")
        return None, issues

    risers = int(round(rise_mm / nominal))
    if risers < MINIMUM_RISERS:
        problem("{0} works out at {1} riser(s) over {2:g} mm, which is a step "
                "rather than a flight.".format(mark or "this stair", risers,
                                               rise_mm), column="TopLevel")
        return None, issues
    if risers > MAXIMUM_RISERS:
        problem("{0} works out at {1} risers in one flight. Split it at a "
                "landing — two rows sharing a mark, with a blank row after "
                "them.".format(mark or "this stair", risers), column="TopLevel")
        return None, issues

    riser = rise_mm / float(risers)
    run = (risers - 1) * tread

    flight = Flight(risers, riser, tread, run, rise_mm, width, waist, nominal)

    # Half a millimetre, not one. A 20-riser flight at 166 instead of 165 is
    # 20 mm of stair nobody asked for, and `> 1.0` let exactly that case
    # through because the difference was exactly one.
    if abs(riser - nominal) > 0.5:
        problem("{0}: {1} risers of {2:.1f} mm, not the {3:g} mm asked for — a "
                "flight has to land exactly on the floor, so the rise is "
                "divided by a whole number of steps.".format(
                    mark or "this stair", risers, riser, nominal),
                column="Riser", severity=models.SEVERITY_INFO)

    if available_mm and run > available_mm + 1.0:
        problem("{0} needs {1:.0f} mm of run and its two grids are {2:.0f} mm "
                "apart, so it overshoots by {3:.0f} mm. It is built as the "
                "sheet describes — the grids, the tread or the landing is "
                "what needs changing.".format(
                    mark or "this stair", run, available_mm,
                    run - available_mm),
                column="ToGridX", severity=models.SEVERITY_WARNING)

    return flight, issues


def _positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
