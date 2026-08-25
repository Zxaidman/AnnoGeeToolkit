# Schedules, and footing rebar from the workbook

**For review before anything is built.** Two things are proposed here and they
are very different sizes: one is a morning, the other is where the programme
slows down. Worth saying which is which before either starts.

---

## Part 1 — `schedules.sync`

**The easiest thing left, and worth doing next for what it proves.** No
geometry, no judgement, no round-trip: a schedule is a view with a list of
fields, a filter and a sort. If it comes out wrong it is obvious in a second,
and nothing in the model is at risk.

It is also the first time `S_ScheduleMark` earns its keep. Until something
reads that parameter, filling it in is an act of faith.

### The sheet

One row per schedule, and the fields as a comma-separated list because a
schedule with fourteen fields should not be fourteen columns:

| Column | Example | What it does |
| --- | --- | --- |
| `Name` | `S-COLUMN SCHEDULE` | The view's name. Matched on this; never renamed |
| `Category` | `Structural Columns` | What it counts |
| `Fields` | `S_ScheduleMark, Type, Base Level, Top Level, Volume` | In order, left to right |
| `SortBy` | `S_ScheduleMark, Base Level` | In order |
| `GroupBy` | `S_ScheduleMark` | Blank for none |
| `Totals` | `Volume, Count` | Which columns get a total |
| `Filter` | `Base Level = 01 GROUND LVL.` | Blank for none. One condition to start |
| `Itemise` | `No` | `No` collapses identical rows — which is what makes it a schedule rather than a list |

Five rows would cover the sample: columns, footings, beams, slabs, and a
combined concrete-volume schedule.

### The rules it would follow

Same as every other command, and for the same reasons:

- **Matched by name, never renamed.** A schedule's name is what a sheet
  references.
- **Never deleted.** A schedule in the model the sheet does not mention is
  reported and left.
- **A field the model does not have is reported by name**, with the parameter
  to bind — the same shape as *no column type called `C-300x600`*.
- **Idempotent**: run twice, the second says `matched`.

### What it will not do in the first version

Calculated values, conditional formatting, multi-condition filters, key
schedules, and embedded schedules. Each is real work and none blocks a
quantity coming out. **Worth saying now** so the first result is not read as a
disappointment.

### Cost

Small. A day, perhaps, most of it in mapping field names to Revit's parameter
ids, which is fiddly rather than hard.

---

## Part 2 — footing rebar

**This is the slow one, and the estimate is the important part of this
document.**

RC Automation already places footing rebar and has done for seven versions. But
its constraints — the thing that makes a bar follow a sloped or stepped pad —
are still `testing` after four rounds, and that is with one engineer looking at
one model. The bars themselves are the easy half.

### What already exists and can be reused

| | |
| --- | --- |
| Bar placement from a schedule | `rebar_run`, `rebar_factory`, `rebar_spec` — confirmed in a model |
| Bend geometry, cover-aware | `rebar_spec.bar_points`, and the cover-versus-centreline rule that took three rounds to get right |
| Cover types, matched or created | `rebar_types.match_cover_type` |
| Constraints to a host's faces | `rebar_constraints` — **`testing`, and the least certain thing in the repository** |
| Shape codes, three standards | BS 8666, IS 2502, ACI 315 |

So the modelling is not being started from nothing. What is new is the
**workbook front** — reading a rebar sheet instead of RC Automation's own
schedule format — and that part is genuinely small.

### The sheet

One row per bar set, which is how a bar bending schedule already reads:

| Column | Example | What it does |
| --- | --- | --- |
| `Mark` | `F1` | Which footing type this belongs to — matches `FOOTING_TYPES` |
| `BarMark` | `01` | The bar's own mark within that footing |
| `Layer` | `Bottom X` | `Bottom X`, `Bottom Y`, `Top X`, `Top Y`, `Side` |
| `Dia (mm)` | `16` | |
| `Spacing (mm)` | `150` | Or `Count` instead — one or the other, and saying both is an error |
| `ShapeCode` | `21` | To the standard named on `INFO` |
| `Cover` | `Bottom` | Which cover face governs |
| `Comments` | | |

Five or six rows per footing type; fifteen or twenty rows for the sample.

### The three things that will take the time

**1. A pad's rebar is not one layer.** Bottom X, bottom Y, top X, top Y, and
sometimes side bars — five sets that have to interleave without clashing, each
sitting inside the cover of the one below it. The arithmetic is not hard; the
number of ways to be one bar diameter out is.

**2. Constraints, which are still unconfirmed.** Whether a bar follows a
sloped top face is `rebar_constraints`, which has been through four rounds and
is `testing`. Building on top of it means either confirming it first or
inheriting its uncertainty.

**3. Hooks and laps.** A bar with a hook is a different length from the same
bar without one, and the schedule is what the steel is ordered against. BS 8666
gives the rules; applying them per shape code per standard is where the
detail lives.

### Cost, honestly

**Weeks, not days**, and the first version will be bottom mats only. Compare:
levels took an afternoon, columns took a day, footings took a day. Rebar is a
different kind of problem — every other command places *one thing per row*, and
this one places a hundred bars from a row and every one of them can be wrong on
its own.

The seven versions RC Automation has already spent on footing rebar are the
evidence, not a pessimistic guess.

---

## What I would do, in order

| # | | Why |
| --- | --- | --- |
| 1 | **`schedules.sync`** | A morning. Proves `S_ScheduleMark`, and gives quantities out of everything already built |
| 2 | **Confirm `rebar_constraints`** in the model that now has 15 footings in it | It is `testing` and everything in part 2 sits on it. Cheaper to settle now than to inherit |
| 3 | **`REBAR_FOOTING` sheet, bottom mats only** | The workbook front, against the placement that already works |
| 4 | Top mats, then side bars | Each is the same shape of work again |
| 5 | Hooks, laps, and the BBS out | Where the standards live |

**The reason for that order:** step 1 makes step 3 checkable. A rebar run
without a schedule to read is a run judged by looking at the model, which is
how the first four constraint rounds went.

---

## Two questions before building

1. **Schedules — are five the right five?** Columns, footings, beams, slabs,
   and combined concrete volume. Or does the practice have a standard set worth
   matching instead?

2. **Rebar — bottom mats first, or a whole footing at once?** Bottom mats first
   gives something checkable in days rather than weeks; a whole footing means
   the first thing seen is complete. Both are defensible and the answer changes
   the order of everything in part 2.
