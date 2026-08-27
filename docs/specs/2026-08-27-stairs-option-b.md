# Stairs, option B — built so it can be argued with

**This is for a decision, not for approval.** The project owner leans towards a
real Revit `Stair` element and asked to see the alternative working first. So
this says what was built, what it gets right, and — at more length — what it
costs, because that is the half that decides it.

---

## What option B is

An RCC stair is a **waist slab with triangular steps on it**. Both are shapes
this repository can already place, size, match and schedule, so:

| Part | Modelled as | Why |
| --- | --- | --- |
| **Waist** | A slanted structural framing member, section = stair width × waist thickness | A beam's section is swept **perpendicular to its curve**, which is exactly how a waist slab's thickness is measured. The volume is right, not nearly right |
| **Steps** | One `DirectShape` per flight holding a triangular prism per tread | A step is a triangle. Modelled as a box it is **twice** the concrete, on every step in the building |
| **Landing** | *Not built yet* | See below. This is the honest gap |

Five flights are in the sample workbook, one per storey, all in the same bay —
which is what a stair core is, and which makes the second run's `matched` the
test that matters.

---

## What it gets right

**The arithmetic, which is the part you cannot check by looking.** A staircase
one riser out arrives at the floor looking almost right.

- **A flight lands exactly on the floor.** The `Riser` on the types sheet is a
  *nominal*. The riser built is the rise divided by a whole number of steps, so
  3300 at a nominal 165 gives 20 × 165 exactly — and 3320 gives 20 × 166, not
  20 × 165 and a 20 mm step at the top. The change is reported every time.
- **`n` risers have `n − 1` treads.** The last riser lands on the slab and has
  no tread, so the waist stops one riser below the floor. Getting this wrong
  makes every flight one tread too long, and it still fits in the bay, so
  nothing complains.
- **The waist is measured along the slope**, not the run. Using the run
  understates a 30° flight by about 14%.

For the sample: **20 risers of 165, 19 treads of 280, 5320 mm run, 30.5° pitch,
1.638 m³ — 1.111 waist + 0.527 steps.** Every flight reports that line into
FINDINGS, so it can be checked without a schedule that does not exist yet.

**And everything the other commands already have**: driven from a sheet, matched
rather than duplicated on a second run, types found before they are created, and
a dog-leg describable as two rows sharing a mark — the same idiom that makes a
continuous beam a group.

---

## What it costs

### 1. The waist pollutes the beam schedule

It is a structural framing instance, so it appears in Structural Framing
schedules and quantities beside the beams. It carries `STAIR WAIST` in its
comments, so excluding it is one filter condition — **but somebody has to
remember to add that condition to every beam schedule, for ever.** A schedule
that forgets it counts staircases as beams.

**This is the strongest argument for a real `Stair`,** and it does not go away.

### 2. No mid-landing

A dog-leg comes out as two flights with a gap where the landing should be. The
two flights are placed correctly; the landing between them is not placed at all.
Straight flights — which is what the sample has — are complete.

### 3. It is not a Stair to Revit

No automatic railings, no stair path annotation, no run/landing behaviour in
section, and it will not appear in a Stairs schedule as a stair. It is concrete
in the right shape with the right volume.

---

## What a real Revit `Stair` costs instead

Stated so the comparison is fair, rather than only listing option B's problems:

- Runs and landings are **sketch-based**, and driving a sketch from a
  spreadsheet is a different order of work from placing a line.
- The type carries tread and riser **rules** that fight an explicit dimension —
  you ask for 165 and get what the type's rules allow.
- Reading a **waist volume** back out is awkward, and the waist volume is what a
  QTO wants.
- **Rebar hosting** into a monolithic stair is harder than into a framing member.

Neither option is clean. That is why this is a decision rather than a
recommendation.

---

## How to judge it

Run `stairs.sync` on the sample and look at:

1. **Does it look like a staircase** in 3D and in section?
2. **Is the schedule pollution tolerable** — open a Structural Framing schedule
   and see the five waists sitting in it.
3. **Is the volume usable** — the numbers are in FINDINGS, one line per flight.
4. **Is the missing landing a blocker** or a fortnight's work you would rather
   spend elsewhere?

If the answer to 2 is no, that alone settles it and nothing else matters.

---

## If option A is chosen instead

Nothing here is wasted, and that is worth saying plainly:

| Kept | Why |
| --- | --- |
| `rc_automation/flight.py` | The arithmetic is the same whatever places the geometry. A Revit `Stair` still needs the riser count, and it still has to land on the floor |
| `STAIR_TYPES` / `STAIR_PLACEMENT` | The sheets describe a stair, not an implementation |
| `commands/stairs.py`'s reading half | Parsing, locating, planning and idempotence are unchanged |

What would be replaced is `structural/stairs.py` — roughly a day's work — and
what would be gained back is the schedule pollution and the landing.

**So the honest recommendation is: look at point 2 first.** It is the one that
cannot be fixed by spending more time on option B.
