# cad2bim — todo list

The queue. Everything not yet confirmed in Revit lives here, and nothing leaves except by
reaching `done` — at which point it is written into `done-list.md` with what was actually done.
Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this
file before it is built, argued about, or written into any other document. Standing instruction
from the project owner, and it is what keeps this list the queue rather than a summary of one.

Current build: **v0.76.0** (`85205db`, branch `claude/cad2bim`). 714 unit tests, 3 regression
legs green. Longer records: `../../../../../task_plan.md`, `findings.md`, `progress.md` at the
repository root.

## Sections

| § | Section | What belongs in it |
| --- | --- | --- |
| 1 | **Critical** | Blocks the other implementation. Nothing ships until every one is closed or deliberately deferred. |
| 2 | **Errors and bugs** | Something is wrong now. Each carries how it was found and whether it is reproduced. |
| 3 | **Features** | New capability. Each is separable and can be scheduled on its own. |
| 4 | **Working now** | What is built and verified, so nobody rebuilds it and nobody claims more than was measured. |
| 5 | **Pending scope** | Agreed direction, not yet started. |
| 6 | **Owner's list** | Reserved for what the project owner sends next, and everything after. |

**Every entry has an ID** (`CRIT-1`, `BUG-3`, `FEAT-7`) so it can be referred to in one word.

## Phases

| Phase | Meaning |
| --- | --- |
| `pending` | Not started. |
| `building` | Being written now. |
| `testing` | Built and in a build the project owner can test; waiting for the in-Revit result. |
| `superseded` | It worked, and something else replaced it. Recorded rather than deleted — what it cost to build is part of the record. |
| `done` | Confirmed in Revit, and copied into `done-list.md` with what was done. |

---

## 1. Critical

### CRIT-4 — Beams are lost in the whole drawing that pair perfectly on their own · `pending`

**How found:** the owner's v0.84.0 run, images 3 and 4 — "two vertical beam is not drawn, one mid
vertical beam is correct, two horizontals beams are not align properly with layer outline".
**Reproduced, and isolated to a contradiction:**

The pair at `(204847..207398, 19519)` and `(204847..207398, 19869)` — both plain `line` records on
layer `BEAM`, 2551 mm long, fully overlapping, **350 mm apart**, a width inside the 80–700 pairing
band and one the drawing uses 21 times. Handed to `build_beam_segments` **alone it makes one
350-wide beam**; in the full drawing it makes **none**. So the pairing rule is right and something
else consumes or discards the pair.

Scale: the run reports **111 bare lines without a parallel partner**, and 114 beam edges have no
placed beam over their midpoint (300–2551 mm, median 1572).

**Why this is critical rather than cosmetic:** slabs on this drawing come from `placed_members`, so a
missing beam leaves its bay open. That one fault explains three more of the owner's symptoms — "beam
did not close column to column which leaks slab into for sunk slab" (images 1, 2), the large cutout
areas still cast as floor (no closed bay for the X to cross), and the sunk slabs missing entirely in
that zone (no bay to sink). Everything downstream of it should be judged only after it is fixed.

### CRIT-1 — One wall is drawn on two conventions, and both now build · `pending`

**Found:** measured in the P3a corpus survey, findings #12. **Reproduced:** offline, in the
planner. test8's 250 mm `S-RCC-WALL` quad carries a 150 mm arch `wall` trace 50 mm off its
centreline (250/2 − 150/2 = 50) — the two drawings share one face and disagree about the other.
The two kinds are planned by separate passes that cannot see each other, so since v0.76.0 both
plan **and both place**: two overlapping walls at that spot in Revit.

**Blocks:** P4 openings (a door needs one host, not two), and any wall count the owner reports
from test8.

**Needs from the owner:** which convention wins when both name the same wall — and whether the
loser is dropped in the planner (never planned) or the builder (planned, reported, not placed).
The only same-kind coincidences in the corpus are three drawn nibs (100–151 wide, 250–410 long
closed rings sitting on longer runs); those are drawn geometry and stay.

### CRIT-2 — Lift/stair core walls still place as thin COLUMNS · `pending`

**Found:** carried deliberately from P3b. `report.py` → `shapes.recover_core_walls` pairs the
opposing faces of a fragmented core and emits `recovered_core_wall` rectangles, which
`builders/columns.py` places as long thin columns — the stand-in P3 exists to replace. P3b did
not move it: **column counts have not moved and must not until this is decided**, because moving
them changes column and wall counts together.

**Blocks:** P4 (an opening in a core wall has no wall to host it), and the element counts of every
drawing whose core is fragmented (test18-era drawings, Project1).

**Needs from the owner:** the verdict on P3b's walls in Revit first. If the placed walls are right,
the core recovery feeds `wall_plan` instead of the column pass and both baselines move in one
commit, attributed.

### CRIT-3 — A saved settings file silently outvotes the conventions · `pending`

**Found:** the owner's Revit run left F6 flat against a drawing that labels it. **Reproduced and
root-caused** (findings #7): the dialog restores layer combos by name **after** the convention
proposes, so a mapping saved before a category existed (`S-FND: unmapped`, `S-FND-IDEN: ignore`)
wins; no notes are routed, `plan_foundations` has nothing to vouch for the layer, and the whole
foundation pass falls back to column-derived pads. Since v0.73.0 the same restore also outvotes a
**legend** proposal — the row's `*` marker and tooltip survive, the selection does not
(findings #6).

**Blocks:** trusting any bug report from a machine carrying an old settings file. The symptom is a
silently wrong model with no error printed — the failure mode this project treats as worse than a
crash.

**Needs:** FEAT-1 (the warning). Until then: when a foundation or legend result looks wrong, check
the settings file before the code. The owner's own copy was re-saved and is fixed; the trap is open
for every other pre-P1 file.

---

## 2. Errors and bugs

### BUG-4 — An L-shaped column is placed as a big tilted rectangle · `testing`

**Fixed in v0.77.0, awaiting the owner's Revit run.** `parse_column_polyline` now closes the
drafting noise before it believes a ring is angled: coordinates within `_AXIS_SNAP_MM = 1.0`
collapse onto one value, the ring is simplified again, and only a ring still not rectilinear gets
the oriented box. The tolerance sits inside a measured empty band — corpus-wide, 620 column rings
drift under 1 mm, **nothing at all lies between 1 and 2 mm**, and genuinely angled columns start at
2 mm and run to metres. Measured after the fix: test14's `oriented_rect` **51 → 0** (21 become
composite L/T shapes, 30 plain rectangles), test12 recovers **565** columns the same way, and
Project1 (89) and test10 (165) are **untouched** — every angled column keeps its oriented box. The
run reports how many rings it straightened (`axis_snapped`) rather than doing it silently.

**How found:** the owner's v0.76.0 Revit run on test14, with the drawing beside it — the placed
column is a rotated block where the drawing shows an L; six such cases on every level, and it
repeats on all three levels.

**Reproduced offline, and the mechanism is exact.** `shapes.parse_column_polyline` tests
`is_rectilinear` at `_TOL = 1e-4 ft` (~0.03 mm). test14's column rings miss that by drafting noise
— **51 rings fail the test and every one of them drifts by less than 1 mm** (9 under 0.1 mm, 42
between 0.1 and 1 mm, worst 0.7 mm; e.g. an edge wandering 0.39 mm sideways over 1747 mm, 0.013°).
Failing the test sends the ring down the non-rectilinear branch, which fits a **minimum-area**
enclosing box — and for an L or T ring that box is both TILTED and vastly bigger than the column:
`1166 x 3905` and `1084 x 3879` mm of solid concrete in the export, six per storey, exactly the
count the owner reports.

The four-corner rings (30 of the 51) come out nearly right, because a rectangle's min-area box is
the rectangle; it is the 21 multi-corner rings (18 with ten corners, 3 with six) that are visibly
wrong. **No genuinely rotated column exists in test14** — every failure is noise.

**Fix direction:** snap coordinates onto shared axes before the rectilinear test, in the millimetre
band the measurement leaves empty, then decompose as a composite. `_snapped` in `fold_plan` is the
donor. Tolerance to be set from the corpus-wide drift measurement, not chosen.

### BUG-17 — A slab schedule with a THK column is not read at all (test16) · `testing`

**Fixed in v0.89.0, awaiting the owner's Revit run.** `thk` / `thick` / `thickness` is now a header
word, `_is_header_row` accepts a Mark + one thickness column, and `parse_thickness_schedule` reads
such a table into `{mark: thickness_mm}` — kept apart from `parse_schedule`'s `(w, h)` sections,
because a mapping holding both would hand a thickness to a caller expecting a section and the error
would be a wrong beam rather than a missing slab. A bare `T` is deliberately NOT a header word:
measured, `THK` appears in test16 alone (twice, and those two cells ARE its headers) while `T`
appears in test4, test5 and test9 meaning something else.

**Measured:** test16 now reads S1 125, S2 150, S3 175, S4 200, S5 225, S6 250 plus the foundation
block beside it (F1 500, F2 550, F3 600, RF1/RF2 1200), and its 220 beam sections still parse
untouched. The sweep gained `slab_schedule_rows` and test16's **`slab_loops_sized` went 0 → 201** —
every labelled bay sized from the schedule, where none had been. The F/RF rows are read and
available; only the S-marks are routed to slabs today, so wiring them to the foundation pass is a
separate, easy step whenever it is wanted.

**The owner:** "slab schedule reading for type is not working while layout mark label is used for
parameter but type creation and using proper type as per schedule is not working for slab." Their
screenshot shows a floor carrying `S-ScheduleMark S3` correctly, and its type still `.Default Floor`.

**Reproduced, and the cause is two lines in `classify/marks.py`:**

test16 draws a real `SLAB SCHEDULE` on `G-ANNO-SCHD`, a clean two-column table —

```
Mark | Thk        Mark | Thk
S1   | 125        F1   | ...
S2   | 150        F2   | ...
S3   | 175        F3   | ...
S4   | 200        RF1  | ...
S5   | 225        RF2  | ...
S6   | 250
```

— and 201 slab labels on `A-FLOR-IDEN` using those marks (S1 ×34, S2 ×90, S3 ×46, S4 ×26, S5 ×3,
S6 ×2). `parse_schedule` returns **220 rows, every one a BEAM mark** (B1, B10 …). The slab table is
invisible to it because:

1. **`thk` is not a header word.** `_header_role` knows `w/b/width/breadth`, `l/d/depth/length`,
   `h/ht/height/lvl/level`, `size/section/dim…` — nothing for thickness.
2. **`_is_header_row` demands two dimension columns or a Size column.** A `Mark | Thk` table has
   exactly one, so even a recognised `thk` would still fail the gate.

So `run_builders`'s `slab_schedule` filter (marks beginning `S` + digit) finds nothing, every bay
falls back to the blanket note or the base type, and the type is never created from the schedule —
exactly what the owner sees.

**Shape note for whoever builds it:** a thickness table's value is a SCALAR, not the `(w, l)` pair
`parse_schedule` returns, so the two must not be crammed into one mapping. The same table shape
serves the F1/F2/F3/RF1/RF2 block beside it, which is the foundation/roof schedule — worth reading
in the same pass and filtering by mark at the consumer, as slabs already are.

### BUG-15 — A sunk beam must move by z Offset Value, and a bay's beams must sink too · `testing`

**The owner, twice over:** "beams are not getting sunk which has hatch pattern and its sunk value
should use Z Offset Value only for sunk or rise not the Start/End Level Offset."

**Both halves fixed, awaiting the owner's Revit run.**

- **The parameter.** `builders/beams._sink` sets `BuiltInParameter.Z_OFFSET_VALUE` to
  `-mm_to_internal(drop_mm)` and the driving curve is laid ON the level, so Start and End Level
  Offset stay at 0.000. **The sign:** z Offset Value counts along the model's +Z from whatever datum
  `z Justification` names — the justification chooses WHICH face sits on the location line, not
  which way the offset counts — so down is negative whatever it reads. With the owner's `Top`, −150
  puts the top face and the whole unchanged section 150 below the level, top and soffit together. A
  legend row pricing a RISE arrives as a negative depth and comes out positive, up. A family whose
  parameter refuses the number is REPORTED, not swallowed.
- **The coverage.** `fold_plan.beam_drops` now takes the sunk BAY hatches beside the strips and asks
  them the BEAM's share only (`_BEAM_CLAIM_SHARE`, 0.3 — the bay-side desert measured 0.2012 ..
  0.6251 over all 385 overlapping pairs, 0.4239 wide against a next-widest gap of 0.1824, so the
  strip-side constant is reused rather than a second one invented). **test14 goes from 12 of 660
  beams dropped to 261**: 90 at 75 mm and 171 at 150 mm, the biggest group being **105 of the
  200X600 beams at 150 mm** — image2's own size. Not one of the 12 bay hatches that sinks no bay
  claims a beam either, so every dropped beam is under a hatch that also stepped a floor. Nothing
  moves on any other fixture.

The two original faults, as found:
- **The parameter.** The drop is applied by lowering the curve, which Revit records as Start/End
  Level Offset. The owner wants `Z Offset Value` — the parameter meaning "this member sits below its
  level", which leaves the analytical line where the drawing puts it.
- **The coverage.** Only beams under a sunk STRIP drop today (20 of 227 on test14). A beam under a
  sunk BAY does not — and the bay's hatch overhangs onto exactly those beams by the beam
  half-widths, which is the drawing SAYING they sink with it ("SLAB/BEAM SUNK BY 150MM"). Since
  BUG-14 made the bay's own ring the geometry, that overhang now informs nothing; it should inform
  this.

### BUG-16 — A text naming a cutout does not mark one · `testing`

**The owner:** "Few large place still are still taking the Cutout Cross even when now that i have
put the `Cutout, Lift Shaft, Duct etc.` text there also."

**Fixed, awaiting the owner's Revit run, and now measured on the real drawing** — the owner has
pushed it (`89ba208`), and test14 carries `CUTOUT` ×15 and `LIFT SHAFT` ×15 on layer `CUTOUT`.
`slab_stops.cutout_bays` asks the WORD beside the X: a bay carrying either is withdrawn, a bay
carrying both is withdrawn once, and `by_cross` / `by_text` keep the two readings apart in the
console and the sweep.

**The rule is a WHOLE-STRING match, never a substring, and the corpus is why.** test15 keeps four
sheet titles on a layer called `A-CUTOUT` — `GROUND FLOOR PLAN`, `LIFT MACHINE ROOM FLOOR PLAN` —
and test9 two legend rows, `CUTOUT IN SLAB & NON STR. WALL` and `HATCH INDICATE CUTOUT FOR DOOR
ABOVE…`. Every one holds a word from the list and not one marks a void; read whole, all six are
refused. The layer is not asked either, for the same reason. `B111`, `S1`, `MB`, `200X400`,
`135 THK.`, `ST-1` are not names on the list and cannot become them.

**What it catches, corpus-wide — 80 texts of 13,415, on five drawings**, pinned as `cutout_texts` in
the sweep so a future false positive shows up as a number that moved: test14 `CUTOUT` ×15 +
`LIFT SHAFT` ×15, test16 `CUTOUT` ×12 + `SHAFT` ×6, test10 `SHAFT` ×20, test1/2/3 `SHAFT` ×4 each.

**What it withdraws:** test14 **+3 bays, 87.3 m²** — one per plan, 29.13 m² each, the largest of the
four the word names and **the only one no X crosses**, which is the owner's "large place" exactly.
test16 **+8 bays, 71.0 m²**. Every `SHAFT`-only drawing withdraws NOTHING: those 32 texts sit in no
closed bay at all (no bay closes round a lift well), and each is now named on a note rather than
being silently ignored. test12's 21 and test13's 11 crossed bays do not move.

### BUG-13 — A whole bay crossed by an X still gets a floor · `testing`

**Re-measured after v0.86.0 and the owner's re-pushed drawing (image3 — "still not fixed little
improvement").** The improvement was real and the leftover has a different cause. The beam-pairing
fix closes bays that never closed, so the X reading now finds **12 crossed bays on test14, not 6
(105.6 m², was 63.5)** and **11 on test13, not 4 (256.1 m², was 0.1)**; test12 is unmoved at 21.
What it still did not find was the largest cut-out of the four on each plan — 29.13 m², carrying a
`CUTOUT` text and **no diagonals at all**, so no reading of the geometry could ever have withdrawn
it. That one is BUG-16's, and BUG-16 takes it.

`slab_stops.cutout_bays` asks the existing
`slab_graph.crossed` of the BAY, and a crossed bay is withdrawn exactly as a staircase bay is —
counted and named on its own console line, area included. Corpus-wide it withdraws **test14 6 bays
/ 63.5 m², test12 21 / 121.3, test13 4 / 0.1**, and **no bay is both crossed and a staircase**
anywhere in the corpus (the pass is handed the stair set anyway, so one that is would be withdrawn
once and counted once, and the overlap named). test10's foundation numbers do not move —
`foundation_planned` 9, `steps_planned` 7, `step_supports` 2, `foundation_profiles` 9,
`foundation_cutouts` 2, all unchanged.

**One thing the measurement forced, and it is the only new judgement here.** `cross_strokes` casts
a deliberately wide net — any two-point record, whatever layer — because a COVER ring 0.03..0.23 m²
across is not a shape two members happen to span. A BAY is exactly that shape: **test11 draws four
2000x2500 bays with a pair of 3200 mm diagonals across each, on `ING-BEAM`** — diagonal BEAMS,
which the run places as beams, and reading them as an X would delete **20.0 m² of real floor**.
So the BAY reading, and only the bay reading, drops strokes drawn on a beam or column layer.
Measured: that takes test11's four out and moves nothing else — test12 still 21, test13 4,
test14 6, identical either way. The COVER-ring reading is untouched.

**How found:** the owner's v0.83.0 run — "cutout are still not working in large portion while, smaller
is working now". **Reproduced and measured, and the small/large split is exactly right:**

- the crossed `COVER` rings, which v0.83.0 does cut, are **all tiny** — 90 of them, 0.031 to
  0.227 m², and **not one contains or spans a bay**. Those are the small cutouts that now work.
- the large ones are not `COVER` rings at all. **6 slab BAYS are crossed corner-to-corner by an X,
  1.36 to 19.81 m², 63.5 m² in all**, and 48 of the cutout layer's strokes are longer than 3000 mm —
  the big crosses. Nothing looks for an X over a bay, so all 63.5 m² is cast as floor.

**The rule already exists** and is the foundation one, written for test10: *an X across a part means
no concrete there*. It is applied to `COVER` rings only. A bay carrying the X is the same statement
about a bigger piece, and should be withdrawn exactly as a staircase bay is.

### BUG-14 — A hatch is shaping the slab, when it should only inform it · `testing`

**Re-measured after v0.86.0 and the owner's re-pushed drawing (image2 — "did not see any
improvement").** The sunk SLAB half is working and the symptom the owner still sees is the BEAM.
Measured on the current test14: **132 of its 336 bays sink, 458.3 m² of dropped floor**, 60 at 75 mm
and 72 at 150 mm, from 117 of the 129 bay hatches; the 12 that sink nothing are all pattern `HONEY`
and are named. So the bay of 200X600 beams under a sunk hatch DOES produce a sunk slab. What did not
move was the beam under it — 12 of 660 — and that is BUG-15, which takes it: **105 of the 200X600
beams now drop at 150 mm.** One residual worth its own entry if the owner still sees it: the whole
`HONEY` / **50 mm** legend row builds nothing at all on test14 — its 12 bay hatches cover no bay by
70% and its 6 strips lie on no beam. Every one of those is reported by name.

**Fixed by DELETING the pass that shaped it, awaiting the owner's Revit run.** The sunk slab pass
no longer produces any geometry of its own: `fold_plan.sunk_bay_steps` asks which BAY each hatch
covers and at what depth — `beam_drops`' twin, and deliberately the same shape of question — and
the **bay's own ring**, already bounded by its beams, is the dropped slab. What came out with it:
`_trimmed_drop` (the beam-bodies-as-holes trim), `_report_trims`, `plan_steps`' `beams` parameter
and its `bodies` plumbing, and the `drops`/`trimmed` keys every step used to carry. `plan_steps` is
now purely the FOUNDATION reading, where the drawing does draw its steps to size. The support
arithmetic (`d > T_parent`, `offset = -T_parent`, `depth = d + T_dropped - T_parent`) is untouched
and reached through the same `_parts`.

**The threshold, set from the measured desert.** Asked as a share of the BAY, never of the hatch —
the hatch's own area says nothing, since it overhangs by the beam half-widths. Measured exactly
over every overlapping (sunk hatch, bay) pair in the corpus, 174 of them, all on test14:

| cover of the bay | pairs | what it is |
|---|---|---|
| 0.0000 .. 0.0088 | 33 | the overhang grazing the bay next door |
| 0.0809 .. 0.0894 | 3 | a corner of one |
| 0.2179 | 6 | the 2.56 m² hatch in the 8.66 m² bay |
| 0.4999 .. 0.5564 | 18 | a hatch over HALF a bay |
| **nothing at all, 0.3377 wide** | | twice the next widest gap (0.2820) |
| 0.8941 .. 1.0000 | 114 | the bay, as the drawing means it |

`_BAY_SINK_COVER = 0.7` — the geometric mean of the desert's rims (0.7053), rounded the way
`_SUNK_BAY_MIN_SIDE_MM` and `_BEAM_CLAIM_SHARE` were. **A hatch below the line sinks nothing and is
reported by pattern**: 30 of test14's 129, in three grouped lines.

**The two cases the owner asked about.** A hatch across SEVERAL bays sinks each of them — 15 of
test14's do, drawn straight over the beam between two bays, and the beam itself drops on its own
strip through `beam_drops`. Two hatches of DIFFERENT depths over one bay is refused loudly and
never averaged or maxed: the drawing is saying two things about one floor, so the bay is left flat
and named. (A beam covered twice still takes the deeper — one member must sit somewhere; a bay does
not have to.) The corpus has no conflict.

**What moved on test14, and why.** 108 steps → 114 (the multi-bay hatches now claim both sides);
84 supports → **0**, because what lies beyond a bay's edge is a BEAM, not another floor — the old
84 came from probing outside the overhanging HATCH and finding the bay on the far side, so they
were collars cast through the beams; `sunk_slab_defs` 498 → 321, one floor per bay exactly; dropped
area 400.8 m². Where two bays genuinely abut, the support arithmetic still fires, and there is a
test for it.

**How found:** the owner, stating the principle — "slab boundary still go with hatch pattern and
overlaps with beam, hatch pattern does should not change the slab geometry it should only carries
info and details."

**Measured, and the drawing agrees with them:** across test14's 108 sunk hatches that sit in a bay,
the hatch is **larger than the bay it marks** — ratio of areas 0.30 to 1.30, **median 1.14**, and
only **9 of 108** within 5% of their bay. The overhang is the beam half-widths: the hatch is drawn
across the bay AND the members around it. Using that outline as the dropped slab's geometry is
precisely why the slab overlaps the beam, and the v0.83.0 trim (beam bodies as holes of the hatch
ring) treats the symptom rather than the cause.

**The fix is a simplification, not more machinery:** the hatch says WHICH bay is sunk and BY HOW
MUCH; the bay's own ring — already bounded by its beams — is the geometry. The trim then has nothing
left to do.

**Open, and to be decided from the distribution rather than guessed:** a hatch covering only part of
its bay (the measured minimum is 0.30 — 2.56 m² of hatch in an 8.66 m² bay). Sinking a whole bay on
a third of a hatch would be as wrong as the present overhang, so the threshold wants the same
empty-band treatment every other constant here got.

### BUG-11 — `COVER` and `CUT` are unmapped, so the slab never learns where it stops · `pending`

**How found:** the owner's v0.81.0 Revit run of test14, with four images. **Reproduced and measured**
— and it explains four of the five symptoms at once. test14 carries two layers the convention does
not know:

| Layer | Records | Geometry, measured | What it is |
|-------|---------|--------------------|------------|
| `CUT` | 480 | **480 lines, every one diagonal, 0 axial** | the X-crosses: 240 crosses |
| `COVER` | 456 | 351 polylines + 105 lines, **288 closed rings, every segment axial** | the slab edge |

They are drawn as a pair. A `COVER` ring at (83810..84560, 37959..38549) has two `CUT` diagonals
across exactly that box — the same convention test10 uses for its foundations, with the ring and the
X on separate layers. **Run through the EXISTING X reader unchanged: 90 COVER rings are crossed and
243 are not.**

The owner's reading of the three cases, which the geometry matches:
- a crossed ring → the slab **stops**: a cutout, a hole in the slab;
- an uncrossed ring → still a slab edge, and where it carries the "SLAB AT BEAM BOTTOM" hatch
  (`GOST_GLASS`, 75 regions, currently report-only) it is a **chajja** — a cantilever slab at beam
  bottom;
- the open `COVER` lines mark where a slab edge runs without closing a ring.

This is also why the console says `source: placed_members`: with no slab-edge layer recognised the
outlines are inferred from beam faces, which is what puts slab where the drawing shows none.

### BUG-12 — Cutout and staircase areas are still slabbed · `pending`
**How found:** the owner's images 4 and 5 — an X-crossed area carries a slab anyway, and the
staircase area is slabbed too. Same root as BUG-11 for the crossed areas (the X is never read for
slabs; it is read only for foundations today). The staircase case is its own: a bay a stair occupies
should not also be a flat floor. Both need the slab pass to subtract what the drawing marks absent.

### BUG-10 — A sunk beam gets slab laid over it · `pending`
**How found:** the owner's image 1. A sunk hatch crossing a beam means **the beam is sunk too** —
which v0.81.0 now does — but it does **not** mean the slab spans over that beam: the slab must stop
at the beam's edge. Today the sunk bay is laid across it.

### BUG-9 — `Floor.Create` refuses one slab profile · `pending`
**How found:** the owner's console, one error against 151 created. **Not reproduced offline:** every
one of the 474 slab profiles the DXF produces passes a full check — corner count, closure, repeated
corners, self-intersection, hole-crosses-outer, hole-outside-outer, shared edges, hole-crosses-hole.
The Revit run builds from the LINK's records, which explode closed polylines into separate lines, so
its loops are not the DXF's. Until it can be reproduced the honest fix is for the builder to apply
those same checks before calling `Floor.Create` and report the profile it declines, with
coordinates, instead of letting Revit throw a stack into the console.

### BUG-8 — An error printed its markup instead of turning red · `testing`
**How found:** the owner's console showed `<span style="color:#c00000...">` as text. **Reproduced by
reading:** a Revit exception arrives as a paragraph, and one span wrapped around the whole of it
opens on the first line and closes on the last; the output view renders each line separately, so the
span styles nothing and the tag is what you read. **Fixed:** every line is wrapped on its own, and
the message is HTML-escaped first, being Revit data rather than markup.

### BUG-6 — A hatch's meaning is per PATTERN, but the mapping is per LAYER · `testing`

**Decided by the owner and shipped in v0.80.0:** the hatch table gains a row per (layer, pattern)
wherever the drawing's own legend gives a layer's patterns more than one meaning; a layer whose
patterns agree keeps its single row. Measured, not assumed — over the corpus the rule moves only the
two drawings that carry a legend, 36 → 42 rows, where splitting every layer would have gone to 61
and inflated three drawings that gain nothing. test14 8 → 11, test9 5 → 8 (all four still column),
**test10 3 → 3**, so the Revit-validated foundation path cannot be disturbed. Keys are
`<layer_key>|<PATTERN>`, composed and never parsed; lookup falls back to the plain layer key, so old
mappings and the offline harnesses still route. It also closes half of CRIT-3 for split rows: a
stale `HAT → sunk` can no longer put "sunk" back onto GOST_GLASS.

### BUG-7 — The legend's sunk depths reach neither slab nor beam · `testing`

**How found:** the owner's Revit run — "see the legend with sunk mention not apply to the hatch
region in revit to neither slab or beam". Root cause was BUG-5 (the legend was never read at all);
once it could be read, nothing consumed the depths.

**Fixed in v0.81.0, awaiting the owner's Revit run.** A sunk hatch is split by the narrow side of
its box at 600 mm — a threshold in a measured desert: test14's 273 plan hatches run 99.9–350.0, then
**nothing until 1007.4**, then on to 1665, so 144 strips and 129 bays separate cleanly. A strip
claims a beam when it covers half the strip's own area, with a second leg (30% of the beam) for a
member the segmentation cut at its columns; both thresholds sit in measured deserts, and on test14
the second leg claims no pair the first did not.

**Built on test14:** 108 bays step (12 × 50 mm, 36 × 75 mm, 60 × 150 mm) and **93 beams drop**
(12 × 75, 81 × 150), whole body down at unchanged depth, which is the owner's own decision. The void
rule holds exactly as they stated it for folds: only the 150 mm bays clear the 125 mm slab, so they
carry all **72 supports**, each 150 mm thick at −125 (`d + T_dropped - T_parent` at `-T_parent`),
while every 75 and 50 mm bay drops with no support at all. 72 GOST_GLASS regions are refused by
name in one line, 21 bays that sit in no slab loop are reported, and a loop wholly covered by its
own bay is not placed flat — named in a note, because a floor that quietly stops being placed is the
hardest kind to find.

**How found:** reading test14's legend (BUG-5). **Reproduced, and measured:** layer `HAT` carries
four patterns and three different meanings — `ANGLE` 198 regions (sunk 150), `ANSI37` 63 (sunk 75),
`HONEY` 21 (sunk 50) and `GOST_GLASS` 75 (**SLAB AT BEAM BOTTOM**, which is not a step at all). The
hatch table maps a LAYER to one meaning, so the honest proposal `HAT → sunk` sweeps all 357 regions
into one bucket: it cannot keep the three depths apart, and it mislabels the 75 that mean something
else entirely.

The depths themselves are safe — `legend_steps()` is keyed by pattern and returns exactly
`{ANSI37: -75, ANGLE: -150, HONEY: -50}` — so a stepping pass that routes by PATTERN is correct
today. It is the layer-keyed table and its override row that are too coarse, and the legend reader
names the coarseness in `notes` rather than hiding it.

**Decision needed:** whether the hatch table gains (layer, pattern) rows wherever a legend
distinguishes them — which is the honest model but a visible dialog change — or whether pattern
routing stays internal to the legend path with the table left per-layer. Recorded rather than
guessed.

### BUG-5 — The legend reader is blind to test14's whole legend · `testing`

**Fixed, awaiting the owner's Revit run.** The row rule is now the verb alone (`INDICATES?`) and the
SWATCH decides what a legend row is, which is what the convention always was. Measured: real rows
pair mutually at 657–947 mm (test9) and 751 mm (test14); test9's camber sentence has no swatch of
its own (nearest is 1697 mm away, and that swatch's own row sits 782 mm from it), so mutual-nearest
refuses it — and the reach was tightened 2500 → 1250 mm as a second, independent refusal. A step
depth is read only off the word SUNK with MM attached, never a bare number, or
`INDICATES 150MM THK. RC PARDI` would route 132 parapet hatches as a 150 mm step.

**Verified independently:** test9 unchanged at 14 entries and one proposal; test14 now reads 24
entries, proposes `HAT → sunk`, carries 5 report-only meanings (the RC PARDI thicknesses, slab at
beam bottom, floating column — real meanings with no pass behind them yet) and yields the three step
depths. The three-plan repetition reads as agreement, not ambiguity.

**How found:** measuring the owner's report that the legend's SUNK rows do not reach Revit.
**Reproduced:** `legend.read()` returns **0 entries** on test14. `_LEGEND_TEXT` requires the words
`HATCH INDICATE`; test14's rows read `INDICATES SLAB/BEAM SUNK BY 75MM.` — no HATCH, and the verb
carries an S. Nothing is read, so nothing can be proposed, so no hatch region is ever routed.

Everything else about that legend is machine-readable, measured: eight rows, every text exactly
**751 mm** from its swatch, every swatch **1050 x 500**, and each meaning carried by a distinct
pattern — SUNK 75 → `ANSI37` (63 plan hatches), SUNK 150 → `ANGLE` (198), SUNK 50 → `HONEY` (21),
SLAB AT BEAM BOTTOM → `GOST_GLASS` (75), 150 RC PARDI → `AR-HBONE` (135), 100 RC PARDI → `EARTH`
(51), 200 RC PARDI → `TRIANG` (12), floating column → `FC/SOLID` (27).

**Care needed:** the prefix rule exists to reject test9's `*A- INDICATE 20mm CAMBER TO BE PROVIDED
IN BEAM`, which is not a legend row. Loosening it must keep that rejection — the swatch pairing is
the stronger test and should carry the weight.

### BUG-1 — Placed footings' Width/Length: fixed, unconfirmed · `testing`

**How found:** the owner compared a placed footing against a hand-sketched twin — the placed one
showed blank read-only Width/Length, the sketched one reported both, and BOQ schedules read those
fields. **Reproduced:** yes, in Revit by the owner. Root cause: `Floor.Create` places a
NON-structural floor; the foundation dimensions belong to the structural element.

**Fix shipped v0.69.6** — every placed footing sets `FLOOR_PARAM_IS_STRUCTURAL` and hands Revit its
sketch the way the rectangle tool draws one (counter-clockwise from the lowest-left corner).
**Waiting on:** the owner's next Revit run. If the fields stay blank, the fallback is schedulable
parameters of our own, written from the rings this tool already measures exactly.

### BUG-2 — The bundled `lib/py3` ezdxf will not import on Linux · `pending`

**How found:** running the regression gate outside Windows. **Reproduced:** every run. The bundled
`numpy` is a Windows wheel whose import calls `os.add_dll_directory`, which does not exist on Linux,
so the bundled `ezdxf` cannot load. The DXF leg **skips with that message** rather than failing, and
`pip install ezdxf` restores it. Windows/pyRevit — the actual target — is unaffected, which is why
this is recorded rather than fixed (findings #11).

### BUG-3 — `graphify-out/` is 18 versions stale · `pending`

**How found:** the v0.76.0 documentation sweep. **Reproduced:** yes — it was generated at
`56c2d6a` (v0.50.0) and contains none of the twenty modules the v0.68.0 refactor created, nor any
of the P1–P3 modules. Documentation only; no build reads it, so it is not a gate.

---

## 3. Features

### FEAT-1 — Warn when a restored mapping downgrades what the convention recognises · `pending`
Closes CRIT-3's silent path. The dialog knows both the proposal and the restored value at the moment
it overwrites one with the other; today it says nothing. A marked row and a console line would make
a stale settings file visible instead of mysterious. Covers the legend case too (a proposal that is
seeded and then overwritten keeps its `*` and loses its selection).

### FEAT-2 — Folds and sunk on SLABS, not only foundations · `pending`
`fold_plan.plan_steps` runs for foundations only. A fold or sunk hatch drawn over a slab is read,
classified and counted, and then nothing steps it. The machinery is shared and Revit-free, so this
is wiring plus a regression pass rather than new geometry.

### FEAT-3 — Consume `legend.legend_steps()` · `pending`
2.4 delivers the per-pattern step DEPTH behind the same 3000 mm threshold `plan_steps` applies
(test9's `+6250` is refused and named wherever depths flow), and **no pass reads it yet**. Depends
on FEAT-2: stepping a slab from a legend depth is P2-on-slabs territory.

### FEAT-4 — Read the legend per tower, after the multi-storey split · `pending`
test9's sheet is three tower plans, each with its own legend block, and each block is internally
coherent. The whole-sheet read rightly refuses the patterns that mean different things per tower
(ZIGZAG, STARS, SOLID) — a per-tower read would resolve them honestly. It needs the split to hand
regions per plan to the mapping stage; today the mapping runs before the split.

### FEAT-5 — Naming templates for the step support and the dropped slab · `pending`
Both take their host's name today. Footings and rafts got their own templates in v0.71.0 on exactly
this argument — a name that encodes a size must be able to differ when the size does.

### FEAT-6 — Per-storey level mapping (name-match auto-assign, base below top) · `superseded`
Built v0.70.4, corrected v0.71.1 to the owner's convention (structure is drawn BELOW the slab it
supports, so a plan named "Ground Floor" TOPS OUT there and the base sits below). **Removed at
v0.72.1 on the owner's order** — "our level mapping in storey is destroying the model" — because
name-match auto-assign re-anchored the stack onto ladder-created levels and re-runs compounded the
damage. What replaced it is the plain positional ladder it had displaced, verified byte-identical
to its pre-feature form. Recorded, not deleted: the convention it encoded is still right, and
FEAT-7 is the way back.

### FEAT-7 — Re-run-safe redesign of the storey level mapping · `pending`
The requirement stands (the owner stated the convention twice); only the implementation was wrong.
A redesign has to be idempotent: running the tool twice on the same model must produce the same
levels, not a second ladder anchored to the first.

### FEAT-8 — Architecture beyond walls · `pending`
The Architecture sub-tab carries arch walls and a roofs note. Roofs, and whatever else the owner
wants under it, are unbuilt.

### FEAT-9 — The module constants the Advanced door still cannot reach · `pending`
`advanced.py` registers the 19 constants whose consumers read them LIVE, which is what makes an
override provable. findings #10 names three that failed that test and were excluded on purpose:
`slab_graph._COLUMN_RECT_PAD_MM` (imported by name, so the consumer holds a frozen copy),
`slab_labels._ORPHAN_MIN_AREA_M2` (frozen at function definition; a live dialog knob already
exists), and every `builders/*` constant (that package imports Revit at module level, so no
Revit-free registry can rebind it and no offline test could prove the wiring). Each needs its own
change with its own regression risk.

### FEAT-10 — The eight-tab dialog · `superseded`
Shipped v0.70.0 after the dialog audit, replaced within the day by the owner's own layout: a Build
tab with element sub-tabs (v0.70.1), fixed at exactly five — General / Structure / Architecture /
Foundation / Staircase, grids inside General (v0.70.4). Six top-level tabs today. The audit work it
carried (roughly forty settings that existed in code and nowhere in the dialog) survived into the
current layout and into FEAT-9.

---

## 4. Working now

What is built and verified. Nothing here claims more than was measured.

| ID | Capability | Phase | What was actually verified |
| --- | --- | --- | --- |
| WORK-1 | Columns — rect, round, rotated, blade, fused, clipped, schedule- and label-sized | `done` | The owner's Revit rounds v0.14–v0.24; every recovery answers a named case in a real drawing |
| WORK-2 | Beams — sized from labels, curved, sloped, split at columns, perimeter recovery | `done` | The owner's Revit rounds v0.25–v0.34 |
| WORK-3 | Slabs — drawn edges, placed-member faces, note recovery, openings, arcs | `done` | The owner's Revit rounds v0.35–v0.45; the 14.4 mm misalignment closed at v0.45.0 |
| WORK-4 | Staircases — dog-leg, L, circular, winders, drawn linework or text, waist, landings | `done` | The owner's Revit rounds v0.46–v0.62 |
| WORK-5 | Grids, levels, naming templates, standard sizes | `done` | v0.61–v0.62; naming re-checked at v0.67.1 |
| WORK-6 | Materials, grades, view filters, progress bars, JSON export | `done` | v0.63–v0.67 |
| WORK-7 | Multi-storey from one DXF, storey stack, per-storey build | `done` | v0.51, v0.66.1; the roof leg pinned by label at v0.69.2 |
| WORK-8 | Type names matched the way Revit matches them | `done` | The owner confirmed the duplication error gone (v0.68.1); two AST checks keep the shape from returning |
| WORK-9 | Regression gate — 3 legs, 714 unit tests | `done` | 29 archived exports, 17 fixture DXFs, 4 storey stacks; proved to bite (a perturbed baseline produced three named failures) |
| WORK-10 | Foundations from the drawing — outlines, notes, rafts, pads, nested blocks | `done` | The owner in Revit: "good we made proper raft on test10". Measured: 9 outlines + 2 cutouts, the raft one piece with 7 holes, 18 foundation-level elements |
| WORK-11 | X-cross cutouts — an X across a nested face means no concrete there | `done` | The owner's Revit run drove it; the corridor now voids where it is crossed out |
| WORK-12 | Folds and sunk — parent cut, dropped slab, pooled support collars | `testing` | Arithmetic given by the owner and twice corrected against their Revit runs (void rule `d > T_parent`; one support per fold GROUP — test10 measures exactly 2). The collar/L representation and the redrawn corridor have not been re-checked in Revit since the rework |
| WORK-13 | Legend reading — swatch pattern → legend text → meaning, proposed never silent | `testing` | Measured offline on test9: 14 rows across three tower legends, exactly ONE proposal survives the ambiguity and one-layer rules (ASPHALT → cutout on `PI_SHEAR WALL CUTOUT`) |
| WORK-14 | Hatch mapping on its own table, apart from geometry and text | `testing` | 495 regions across the owner's test9 + test10 exports, 0 degenerate rings; gate moved nothing (fold, sunk and column routing identical under both conventions) |
| WORK-15 | Walls — planner and builder | `testing` | Planned offline: Project1 17 segments / 11 skips, test8 178 / 110, test9 19 / 39; the other 14 fixtures pin zeros. Placed as `DB.Wall` since v0.76.0, **not yet seen in Revit** |
| WORK-16 | The dialog — six tabs, five Build sub-tabs, AnonGee brand, gated Advanced, saved settings | `done` | The owner in Revit: "tested all good, apply the AnonGee Brand Guidelines design to all cad2bim dialog now", then applied and re-confirmed |
| WORK-17 | Errors print red on the console; skips are named, never silent | `done` | The owner's instruction, shipped v0.69.3 and extended to all six creators |

---

## 5. Pending scope

Agreed direction, not yet started. Detail lives in
`docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`.

| ID | Scope | Phase | Depends on |
| --- | --- | --- | --- |
| SCOPE-1 | **P4 Openings** — doors, windows, shafts | `pending` | The hatch reader (done, P1.1) and P3's hosts — CRIT-1 and CRIT-2 first |
| SCOPE-2 | **P5 Round-trip QA** — the built model against the source DXF, delta reported | `pending` | Enough of the model to be worth diffing |
| SCOPE-3 | **P6 Annotation** — dimensions, tags, views, sheets | `pending` | P5 |
| SCOPE-4 | **P7 Rebar** — feeding `Dev.panel/BBS Generator.pushbutton` | `pending` | P4 |
| SCOPE-5 | **The step SIGN question** | `pending` | A drawing. Every step value on test9 is `+` (`+50`, `+400`, `+950`, `+6250`, `+6450`, all `T.O.S.`), and a plan cannot say what the parent slab's own level is — so `+` cannot be proven to mean raised rather than dropped. Step proposals go to fold whatever the sign, and the question stays recorded instead of guessed. A drawing that pairs a legend step with a section, or uses both signs, closes it |

---

## 6. Owner's list

Reserved for what the project owner sends next, and everything after. Each item gets its own ID
here as it arrives, then moves into §1, §2 or §3 once it is understood well enough to be worked.

| ID | Item | Phase |
| --- | --- | --- |
| OWN-1 | The owner's report on the v0.76.0 build — "this test still have few bugs and errors", not yet sent in detail. Nothing is guessed at in advance; each reported symptom is filed here first, with how it was found, then triaged | `pending` |
