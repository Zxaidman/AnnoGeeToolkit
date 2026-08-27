# Four questions, answered before anything is built

The project owner held a discussion round on 2026-08-27 rather than asking for a
build. This answers the four points in order. **Nothing here has been written
into code** — the IDs exist in `todo-list.md`, which is where they go first.

Recorded as `BUG-31`, `BUG-32`, `BUG-33`, `BUG-34` and `FEAT-41` … `FEAT-45`.

---

## 1 — The beams: why 110 of them vanished

**Not a guess.** The workbook that was pushed carries the evidence, and it is
enough to name the failure by elimination. It is also enough to show that two
*other* defects are the reason this looked like a success.

### What the log says

| Time | Job | Counts | What it means |
| --- | --- | --- | --- |
| 11:11:06 | `0006` | `created=132 written=132` | The last good run, on `B-300x600` |
| 11:38:36 | `0008` | `matched=22 modified=110 written=0` | After the edit. 110 planned, **none written** |
| 11:42:01 | `0013` | `created=132 written=22` | After deleting every beam. **22 built, 110 not** |

The 110 are exactly the `B-230x600` rows; the 22 are exactly the `PB-230x450`
rows. Counted from the sheet, not inferred.

### Why it is the type and not the level

The two are perfectly confounded in the sheet — every `B-230x600` is on levels
02–06 and every `PB-230x450` is on 01 — so the counts alone cannot separate
them. **The 11:38 run separates them.** That run took the `MODIFY` branch, which
never looks up a level and never calls `framing.create`. It still wrote nothing.
So the failure is in the type, and the levels are innocent — which the 11:11 run
already showed, having written all 132 against the same seven levels.

### Which line

`framing.ensure_symbol` has two ways to return `None`:

1. **No Width and Depth on `BEAM_TYPES`.** Ruled out — running the owner's own
   sheet through `placement.parse_types` here gives
   `{'width_mm': 230.0, 'depth_mm': 600.0}`.
2. **`base.Duplicate(name)` threw.** By elimination, this one.

And it must have thrown at 11:38 as well: had it succeeded there, the type would
exist, and the 11:42 run would have matched it on Type Mark and built all 132.

### The uncomfortable part

**The beam type-creation path has never once succeeded in a real model.** Every
green beam run, on 08-25 and 08-27, *found* its types — they were already there.
`FEAT-34` ("a missing type is created, not refused") was confirmed for columns
and for footings, and quietly assumed for beams. The first time a beam type
actually had to be made, it failed.

That is worth saying plainly because it is a pattern, not an accident: a shared
helper was proven on two callers and credited on three.

### What I cannot tell you yet, and why

**The exception text.** `slabs.sync` ran seventy-one seconds later and
`FINDINGS` now holds two rows, both its own. The 110 explanations the run
produced are gone — that is `BUG-32`, and it is the sibling of `BUG-20`. `BUG-20`
stopped an *empty* result wiping the sheet; **any** result still wipes it. So the
findings for a failure survive exactly until somebody tries the next thing, which
is precisely what a person does after a failure.

So the fix is in two halves, and the second half comes first:

- **`BUG-32`** — findings append under a per-job header, newest block on top.
- **`BUG-31`** — `ensure_symbol` reports the exception rather than folding it
  into `None`, and says which of the four passes it tried and what it duplicated
  from. Then one run names the cause instead of another round of elimination.

### The two counts that hid it — `BUG-33`

Both in `commands/_placement.py`, and both read as success:

1. `written=22` out of `created=132` is reported as *"22 beam(s) written, as one
   undo step"*. The number is correct and the sentence is reassuring, which is
   the worst combination available. **The note will lead with the shortfall.**
2. Job `0001` at 11:09:33: `invalid=132`, note *"every beam the sheet describes
   is already there"*. When every row is invalid there is nothing to do, and the
   nothing-to-do branch says everything already agrees — exactly backwards.

### And the slab question

The owner's reason for the whole exercise was to see whether a slab steps around
columns, and the slabs were built without floor beams under them. **That test has
not happened yet** — it needs `BUG-31` fixed first. It is not evidence about
slabs, and it should not be read as any.

---

## 2 — `NAMING`: keeping the sheet honest — `FEAT-41`

The new patterns are the house convention and they are what the sheet should
have shipped with:

| Element | Pattern |
| --- | --- |
| `column`, `beam` | `CH-{b} X {h}` |
| `footing` | `CH-{l} X {w} X {t}` |
| `slab` | `CH-{t} THK.` |
| `column_mark`, `footing_mark`, `beam_mark` | `C{n}`, `F{n}`, `B{n}` |

**`Example` and `Fields it may use` are now stale**, which is the report.

### It cannot be an Excel formula

`Example` is not a string substitution — it is `naming_sheet.render()` run
against a sample, including the rule that `600.0` prints as `600`. `Fields it may
use` comes from `PATTERNS`. A formula would be a second implementation of both,
and it would drift from the first one the day somebody adds a field.

**So: a button.** `Refresh naming`, drawn by `AnonGeeBridge_AddButtons` beside
the others, calling the same `render()` the placement commands call. The example
is then produced by the code that will produce the name — which is the only
version of this worth having, and the reason the example was generated rather
than typed in the first place.

### A defect the edit exposed — `BUG-34`

Running the edited sheet here returns a warning nobody has seen:

> `beam_mark: 'n' — this one takes {level}, {grid}. Using 'B{level}-{grid}' instead`

`B{n}` was **rejected** and the default silently used. `column_mark` and
`footing_mark` declare `{n}`; `beam_mark` declares `{level}` and `{grid}` and
nothing else. Meanwhile the sheet's own `Fields it may use` column — edited by
the owner — advertises `{n}` for all three. **The workbook offers a field the
code refuses.**

It degraded exactly as designed: a naming preference must never stop a run. So
132 beams were placed with marks the owner did not ask for and the run said
`done`. The one warning that would have said so went to `FINDINGS`, and `BUG-32`
wiped it. Three defects compounding is what made this invisible.

---

## 3 — Schedules

The five stand. Three changes, taken in the owner's order.

### a. Staircases — `FEAT-42`

New scope, and worth a warning about *how* rather than whether.

A real Revit **Stair** element is a poor fit for a sheet-driven tool: its runs
and landings are sketch-based, its type carries tread and riser rules that fight
an explicit dimension, and reading a waist volume back out of one is awkward.

**The alternative is what an RCC detailer draws anyway** — a waist slab, a
landing slab, and steps. Modelled as structural floors and framing, from a
`STAIR_TYPES` / `STAIR_PLACEMENT` sheet pair, it uses everything already built:
it places, it matches, it is idempotent, its volume is a volume, and the rebar
work later has a host it understands.

It looks less impressive in the Revit browser and it is right in the quantities.
**Recommend the second**, and say so now rather than after it is built.

### b. Volume *and* formwork, and a `SUMMARY` sheet — `FEAT-43`

Replaces the combined-concrete-volume schedule from the previous document. Each
schedule carries its own volume and its own shuttering area; `SUMMARY` adds them.

**Formwork is not a parameter — it is a decision.** Revit will not tell you the
contact area because which faces count is a judgement:

| Element | Faces that count | Deducted |
| --- | --- | --- |
| Footing | The four sides | Bottom sits on blinding; top is open |
| Column | Perimeter × storey height | Where beams and slabs frame in |
| Beam | Two sides + soffit | Slab thickness off each side; the column at each end |
| Slab | Soffit + edges | Where beams support it |

So it is computed and written into a parameter, not read out of one. **The
deductions are where this earns or loses trust** — a formwork figure that ignores
them is high by roughly the amount an estimator would notice.

Worth agreeing the deduction rules on the sample before the first number goes to
a client. That is a conversation, not a build step.

### c. A generator that is not Revit's — `FEAT-44`

The observation is correct: a native Revit schedule cannot show every parameter
an element has. It will not cross categories in one table, it hides some built-in
read-only values, and it cannot compute across elements.

**So there are two outputs, and they are for different readers:**

| Output | For | Built with |
| --- | --- | --- |
| Native Revit schedules | Placing on sheets and shop drawings | `schedules.sync` — `FEAT-39` |
| A generated table into the workbook | QTO, costing, anything crossing categories | `FEAT-44` |

The second reads `Element.Parameters` directly — every parameter, whatever its
scope — and writes a sheet. That is where the costing already lives, so it is not
a detour. **`FEAT-39` is still first**: the native ones are what a drawing needs,
and they are a morning's work against `FEAT-44`'s several days.

---

## 4 — Rebar: the sheet gets three more columns — `FEAT-45`

Bottom mats first is settled. The three additions are all right, and one of them
fixes something I had designed badly.

### Bar dimensions `A`–`E`

What a bar bending schedule actually prints — the shape code's own legs. The
proposed sheet had a shape code and no dimensions, which is a schedule you cannot
order steel from.

**Computed, with an override column.** For a bottom mat, `A` is
`L − 2 × cover` and typing it fifteen times is fifteen chances to be wrong; but
the moment a bar is non-standard the engineer must be able to say so. So: derive
from shape code + host size + cover, show the result, and let a typed value win.

### The layout rule

Revit's own, and the owner's four are exactly its four that matter: **Single**,
**Fixed Number**, **Number with Spacing**, **Maximum Spacing**.

This one **fixes a flaw in the previous document.** That sheet had `Spacing` and
`Count` with the rule *"one or the other, and saying both is an error"* — which
made the reader carry a constraint the sheet never stated. A `Layout` column says
which is meant, and the other greys out. Better than the version I proposed.

It also decides behaviour, not just a number: *Maximum Spacing* re-counts bars
when the pad grows, *Fixed Number* re-spaces them. That is a real engineering
choice and it belongs in the schedule.

### Phase / Procurement

**On both the concrete and the rebar parameters**, so a stage can be priced whole.

One caution: Revit already has a `Phase`, and it means *Created / Demolished* in
a construction sequence. Overloading it would make an element vanish from a view
because somebody set a pay stage. **So a separate shared parameter** — say
`S_Procurement` — bound to the structural categories and to rebar, carried by
every placement sheet, and totalled in `SUMMARY`.

If the model should genuinely phase as well, that is a second, easy thing, and it
should be asked for separately rather than inferred from this.

---

## What I would do, in order

| # | | Depends on | Size |
| --- | --- | --- | --- |
| 1 | **`BUG-32`** — findings stop being destroyed | — | An hour |
| 2 | **`BUG-31`, `BUG-33`, `BUG-34`** — the beam type, the two counts, the mark pattern | 1, to read the result | Half a day |
| 3 | **`FEAT-41`** — `Refresh naming` | — | An hour |
| 4 | **`FEAT-39`** — `schedules.sync` | — | A day |
| 5 | **`FEAT-43`** — volume + formwork, `SUMMARY` | 4; and agreement on deductions | Two days |
| 6 | **`FEAT-42`** — staircases | Agreement on waist-slab modelling | Two days |
| 7 | **`FEAT-44`** — the generator | 4 | Several days |
| 8 | **Confirm `rebar_constraints`** against the 15 footings | 2 | Half a day |
| 9 | **`FEAT-40` + `FEAT-45`** — bottom mats, with the new columns | 8 | **Weeks** |

**Why `BUG-32` is first.** It costs an hour and it is the reason this round took
elimination instead of reading a sentence. Every later item is easier to debug
once a failure explains itself and the explanation survives the next click.

**Why the beam fix comes before schedules.** A schedule of a model with 110
missing beams is a confident wrong number, and the slab-stepping question the
owner actually wanted answered is still waiting behind it.
