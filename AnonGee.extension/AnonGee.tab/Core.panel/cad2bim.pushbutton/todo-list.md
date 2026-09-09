# cad2bim — todo list

The queue. Everything not yet confirmed in Revit lives here, and nothing leaves except by
reaching `done` — at which point it is written into `done-list.md` with what was actually done.
Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this
file before it is built, argued about, or written into any other document. Standing instruction
from the project owner, and it is what keeps this list the queue rather than a summary of one.

Current build: **v0.96.9** (branch `claude/cad2bim`, restarted from `main` after PR #10 merged).
1292 unit tests, 3 regression legs over 31 archived exports, 23 fixture drawings and 13 storey
stacks. This round answered the owner's column question with a measurement — BUG-34, a size label
1.3 m away rebuilding a column the drawing had right — and built the `_START`/`_STOP` extent planner
(FEAT-16) as a tested, Revit-free module, wiring still to come. The branch also carries the rc-automation merge and the 1.26.1
extension identity. Longer records: `../../../../../task_plan.md`, `findings.md`, `progress.md` at the
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

### BUG-34 — A label 1.3 m away resizes a column that was drawn correctly · `pending`

**The owner:** "in some place column size and its outline is not matching with Linked cad. check if
this is dxf cad issue or coding issue."

**It is a CODING issue, and the numbers name it.** Measured off his 0.96.7 test17 export, first
storey: 290 columns placed against 327 outlines in the link's own geometry.

| | |
| --- | --- |
| placed size matches the link's outline | 171 |
| **differs from it** | **118** |
| …and of those 118, the placed size matches a nearby LABEL exactly | **91** |
| …matches neither outline nor label | 27 |

    placed      | outline drawn | label says  | label distance
    250x1500    | 200x1200      | 250x1500    |   506 mm
    250x1500    | 200x1200      | 250x1500    |  1335 mm
    250x1300    | 250x1200      | 250x1300    |   742 mm

`mark_radius_mm` is **1300 mm** by default — "a size label this close to a member sizes it (labels
sit offset from the column, ~1.1 m)". On test17's density that reach covers the NEXT column's label,
so a 200x1200 column is being rebuilt as its neighbour's 250x1500.

Not the standards snap: 250 and 200 are not in `standard_columns` at all. And not the drawing's
fault — the link's outlines are right; it is the reach that is wrong.

**Immediate workaround, no new build needed:** Tolerances tab → lower the size-label radius from
1300 mm until the columns stop changing. That is his own control and it costs one run.

**The fix worth making, and why it is not made yet.** Trusting a label over the outline is
deliberate — DONE-22 built it so a CLIPPED column could be snapped up to its authoritative label
size. The rule should be that a label only overrules an outline that is clipped or fragmented: a
complete closed ring already states its own size, and the drawing decides. `correct_columns_with_text`
flattens entries into a bare rectangle list before it chooses, so the clipped/whole distinction the
entry's `status` carries is thrown away before the decision is made — putting it back is the change,
and it touches the recovery DONE-22 depends on, so it wants its own round rather than a rushed one
the day before a client trip.


### FEAT-16 — `_START` and `_STOP` column layers say where a column begins and ends · `building`

**The owner:** "in column layers there two new Stop and Start layer which both should be treated
differently stop means that layer column is stop on that particular floor means it can go above *(if
is shows on ground level, then it can make above ground level to 1st level)*, similarly start means
this layer column is start from this level. *(similarly ground level, it would start from ground
level to 1st level not below it)*"

**Measured on `StructuralPlan-Test17-clean.dxf`** — 361 records, both classified as `column` today
and so treated identically, which is why they build wrong:

| plan | `S-COLUM_STOP` | `S-COLUMN_START` |
| --- | --- | --- |
| GROUND FLOOR ROOF SLAB | **148** | 6 |
| 1ST & 2ND FLOOR ROOF SLAB | 0 | 6 |
| 3RD FLOOR ROOF SLAB | 4 | 2 |
| 4TH … 10TH (one each) | 0 | 2 |
| TERRACE SLAB LVL. | **135** | 0 |
| OHWT BOTTOM / TOP SLAB | 24 / 26 | 0 |

The shape of it reads true: columns stop in bulk where the structure changes — at ground and at the
terrace — and start in twos and sixes where a new column is introduced part way up.

**One question before this is built, because it decides 361 columns in a model that ships this week
and getting it the wrong way round puts 148 of them on the wrong floor.** Both of the owner's
examples are the ground plan and both come out "ground to 1st", so they do not separate the two
rules. Which of these is meant:

  * **A** — the layer names the column's OWN EXTENT: a `_STOP` column drawn on a plan is the LAST
    storey it exists in, and a `_START` column is the FIRST. On the terrace plan, 135 `_STOP`
    columns would then be the tower columns ending there.
  * **B** — the layer names where the column is CUT from the default: `_STOP` ends a run that came
    up from below, `_START` begins one that carries on above.

**A** fits the counts as measured. It is not built on a guess.

---

**ANSWERED — "A is correct, build the start/stop column logic" — and the planner is built (v0.96.9).**

`column_extent.py`, Revit-free and 26 tests:

  * `mark_of(layer)` reads the SUFFIX, so an office's own prefix is nobody's business, and test17's
    own spelling `S-COLUM_STOP` (one M) is covered along with `-STOP` and ` STOP`;
  * `key_for(points)` says which footprints across plans are the same column. **Clustered, not
    binned** — rounding into a cell puts two footprints a millimetre apart either side of an edge
    and calls them two columns, which is the one job it has. Free to do because `floor_plans` hands
    each storey's records ALREADY SHIFTED so that plan's origin sits at (0, 0);
  * `extents(storeys)` gives `{column: (first storey, last storey)}` under rule A — the lowest
    `start` mark or the lowest storey it is drawn on, the highest `stop` mark or the highest it is
    drawn on. A drawing that stops a column before it starts still yields one column rather than
    none;
  * `build_here(extent, storey)` puts a spanning column in ONCE, at its first storey, instead of
    stacking one per floor.

**Not yet wired into the build, and that is the honest state.** `place_columns` takes ONE
`top_level_id` for every column in a call, so a stack where columns end at different levels needs
either grouping by top level or a change to the builder — and the multi-storey loop has to gather
every storey's footprints before the first one is built. That is a real change to how columns are
placed, it cannot be checked outside Revit, and the owner travels after Saturday. The planner ships
tested; the wiring is the next thing and wants his go-ahead on timing.


### BUG-33 — test17 builds no slab at all, and said nothing about it · `testing`

**The owner, with the Saturday deadline on it:** "test17 only columns are made and that still not
correct. some beams are drawn, no slab is drawn, some wall is drawn."

**Measured off his 0.96.4 export: every one of the sixteen storeys reports `created: 0, skipped: 0,
errors: 0` for slabs**, and the slab report carries none of its usual counters — so no slab loop was
ever formed, and the pass had nothing to try.

**The cause is a layer that never reaches the slab reader.** In the DXF, test17's slab edges come off
three layers — `DROP SLAB` (2549 records), `B-300xSLAB THK.` (460) and `SLAB THK.` (62), 3071
records between them, and the DXF sweep reads **1056 slab loops from edges**. In his Revit run the
link delivered **not one** slab-edge record: the export's geometry is `wall 258, beam 293, stair 40,
column 169` and nothing else, with `B-300xSLAB THK.` arriving as a BEAM. `slab_loops_from_edges`
therefore returns nothing, the chain falls back to `placed_members`, and that closes no face either.

**Two things follow, and both are done:**

  * **the run now says so.** `finish`'s docstring has always promised that "a category that produced
    nothing while it was asked for" counts as failure, and the code only ever checked errors and
    rollbacks — so sixteen storeys of no slabs ended in silence and he found it by looking at the
    model. An outcome exists only when the user ticked that category, so an outcome that created
    nothing IS one that was asked for and got nothing. The console opens and names the category;
  * **FEAT-13** makes the mapping fixable in one gesture rather than one layer at a time.

**Narrowed on his 0.96.6 run of the CLEAN drawing (`StructuralPlan-Test17-clean.dxf`).** He redrew it
with proper layer names and the slab layers are there: `DROP SLAB` (1004 records),
`S-SLAB-PROJECTION` (787) and `SLAB THK.` (62), **1853 records the default mapping routes to slab
edge on the DXF side**. The link still delivered none — its geometry is `S-BEAM 221, S-COLUMN 175,
S-CUTOUT 176, S-STAIR 40, NON STR. RCC WALL 34` and nothing else — and slabs came back
`created: 0` on 12 of 13 storeys again.

**It is not a saved setting.** `script.py` rebuilds `default_mapping` from the run's own layer names
every time, so nothing carries over from an earlier session; the dialog would show `DROP SLAB` as
slab edge unless it is not in the list at all. Which leaves the layers not reaching the LINK — the
run already has the line for that, `Layers present in the DXF but not in the Revit link (still
mappable)`, and it was written into the deferred console that a run with no errors never opened.

**LARGELY FIXED, and his v0.96.7 console says so.** The layers reach the link now:
`Layers present in the DXF but not in the Revit link (still mappable): B-200x400, Origin` — those
two only — and each storey reads `by category: ... slab_edge 158 ...`. Slabs build:

    Slabs -- source: slab_edges, loops: 153, thickness-noted: 153, created: 79, skipped: 0, errors: 6

and the same shape repeats down the stack (87 created on most storeys, 66 on one). Every loop is
accounted for: 79 built + 68 withdrawn as marked void + 6 refused = 153. The owner: "test17 now
there is some improvement in beam and slab but still far from actual number".

**What is left is two things, and they are separate:**

  * **6 refused profiles per storey on the first plan**, all the same shape — `845 x 496 mm, 8
    corner(s)`, "it comes back to a corner it has already been through". A repeating shape, not
    scattered noise, so it is one rule to find. Tracked here until it is;
  * **68 bays per storey withdrawn as marked void** on 10.1 m2. That is the drawing's crosses being
    read, and it may be right — worth his eye before anything is changed.

**And the columns are not a fault at all.** His console:
`column: vertical members -- Structural Wall for every vertical member: 290 placed as walls, 0 kept
as columns.` The Build tab's vertical-member toggle (WORK-18) is set to WALL for every one, so the
run is doing exactly what it was asked and no columns are created anywhere. That is why "columns are
still same". It is a setting, not code.

### FEAT-15 — A wall under a beam stops at the beam's soffit · `pending`

**The owner:** "if both beam and wall are on same place which is most of the cases, then wall height
top offset should be minus beam depth so it does not overlaps with beam."

Where a wall and a beam occupy the same line, the wall's top offset comes down by the beam's depth,
so the two do not model the same concrete twice. Wants the beam that actually sits over each wall,
which is the same "which member is above this one" question `_carrying_beam` answers for chajjas —
so the rule has a precedent to follow rather than being invented.

### FEAT-14 — Read a wall by its HATCH and a beam by its MARK when the outline is gone · `pending`

**The owner:** "in some case inside Revit linked cad wall outline might remove beam outline if both
are overlapping similar is true in vice-versa, in that case we will use wall hatch to identify if
wall exist there or not. and beam mark to identify if beam exist or not."

A second witness for each member, for where the link has eaten the first. This is the same shape as
the fix that closed BUG-24 — the drawing states a thing more than once, and the reader should not
depend on the one statement Revit happens to drop. Related evidence already in hand: test17's console
reports `8957 in DXF missing/merged in Revit, 3002 clipped`, so the loss is measured, not suspected.


### FEAT-13 — Map many layers at once, not one at a time · `testing`

**The owner:** "i want to add in layer, text and hatch mapping is that there should be option to
select multiple items just like windows explorer (using ctrl, shift click etc to select multi) and
assign multi select at one time instead of one at a time, because in test17 i have to manually assign
B-200x500 or etc one at a time which is inefficient though i can also change the layer names to one
singular beam layer but that will defeat our actual purpose."

His last clause is the requirement, not an aside: collapsing `B-200x500`, `B-200x650` and the rest
into one beam layer would lose the sizes the layer NAMES carry, which the beam reader uses. The
drawing's naming is data, so the dialog has to cope with many layers rather than the drawing being
flattened to suit the dialog. test17 is the case — its layer list is long enough that one-at-a-time
assignment is the slowest part of a run.

**Scope:** the three mapping tables (layer, text, hatch) get Windows-Explorer selection — ctrl-click
to add one, shift-click for a run, ctrl-A for all — and one assignment applied to every selected row
at once. WPF gives the selection for nothing (`SelectionMode="Extended"`); the work is the apply
step and making it clear how many rows a choice is about to change.

---

**v0.96.7 GOT IT WRONG and v0.96.8 rewrote it on the reference.** The first attempt hand-rolled
Explorer's click rules on mouse events, and every one of them misbehaved: "without Ctrl hold i can
select multiple which is not good. and i could not unselect it with ctrl + click ... it should
follow `OneFilterParameter.pushbutton` reference".

He was right to point at that button, and the pattern was already in this dialog: its **storey table
has used a real `ListBox` of `ListBoxItem`s since it was written**, with a comment saying exactly
why — "A hand-rolled click handler on the row could not work". I built a fourth thing next to it
instead of reading it.

So WPF owns the clicking now. Each mapping row is a `ListBoxItem` in a `SelectionMode="Extended"`
ListBox, which is what the reference's DataGrid does and what the storey table does, and Explorer's
rules come for nothing: a plain click takes ONE row, ctrl-click toggles ONE, shift-click takes the
run between. No preview handler, deliberately — the storey table forces selection on any click
because it is single-select, and forcing it here would override the modifiers and put the same bug
straight back.

**The Apply button and its separate dropdown are gone**, per "it should use any selected item
dropdown if one change all the select should also change": changing the category on a SELECTED row
now sets every selected row. Changing one on an UNSELECTED row spreads to nothing, which is what
keeps single-row editing working. `selection.py` shrank to that one rule — the only part still ours
— with 9 tests on it, and six AST pins hold the wiring, including that the hand-rolled machinery is
GONE rather than merely bypassed.

**Waiting on:** the owner's next run. test17's layer list is the drawing that needs it.

### BUG-29 — The zoom never framed the model once · `testing`

**Found in the owner's test17 console, which said it out loud:**
`view: could not measure the model to zoom to (cannot unpack non-iterable BoundingBoxXYZ object).`

`_union_box` unpacks a PAIR, and the fold seeded itself with the Revit box, so the **second** model
element raised — which is every real run. The scan caught it, set the box to None and fell back to
`ZoomToFit`: precisely the behaviour FEAT-11 exists to be rid of. It was reported as working because
what the owner saw was a zoom; it was the wrong zoom, the one that frames the linked CAD and the
grids along with the building.

**Why nothing caught it:** the fold sat in `run_builders`, which imports Revit at module level and so
cannot be imported by a test at all. Only its source could be pinned, and a pin reads names, not
behaviour. Fixed by moving the arithmetic to `views.model_box`, where nine tests now RUN it against a
fake box that is deliberately **not iterable**, so a tuple cannot pass what the real object fails.
**Waiting on:** the owner's next run — the building alone in frame, no link, no grids.

### BUG-28 — Two hundred identical lines bury the console · `testing`

**Seen in the owner's test17 paste**, where
`step: a fold region of 0.9 m2 sits inside no outline: nothing to step`
runs about two hundred times without a break, burying the dozen lines around it that each said
something different. The console is the only account of what a run did, and a page of one repeated
sentence is not an account.

Both skip-printing sites now go through `run_console._say_each`, which says each DISTINCT message once
with a `[xN]` count and keeps first-appearance order — the console is read top to bottom as the run's
story, so sorting by frequency would scramble it. Measured on the owner's own numbers: 224 lines
become 3.

### BUG-27 — An L column is inaccurate in places on test14 · `testing`

**The owner:** "plus one existing bug related to column it is not make accurate L column in some
place in test14." Distinct from BUG-4, which was an L coming back as a tilted block and which he has
confirmed fixed — this is an L that IS built as an L but with the wrong shape somewhere.

**What is measured so far:** test14 reads 195 column entries over 408 rectangles — 111 composite,
84 plain rectangles, 51 axis-snapped (BUG-4's fix), 0 oriented, 0 circular. Nothing in those counts
looks wrong on its own, and "in some place" is not enough to find which of the 111 composites he
means: they are grouped by mark, so a bad one cannot be picked out by shape statistics alone.

**Needed from the owner:** a screenshot of one wrong L with enough of the plan around it to locate
it, or its column mark. One example is enough — the twelve C-cutouts of BUG-24 were found from one
image the same way.

---

**LOCATED, v0.96.5, and it splits three ways exactly as he described it.** Clustering each mark's
rectangles by proximity first (one cluster = one physical column, because an entry is a MARK and a
mark names many columns) test14 builds **90 columns out of more than one piece**:

  * **69 meet cleanly** — "in some places it create perfectly column as per outline";
  * **9 leave a GAP** — "it leaves gap between junctions ... or disconnected";
  * **12 OVERLAP** — "or overlap does not follow outline properly".

Both faults are the same thing: **a stub is positioned on the drawn centreline instead of being taken
to the blade's face.** Measured, two cases:

    entry 16, GAP     blade x 30100..30401; the 200 x 600 stub ends at x 30076
                      -- 24 mm short of the blade, so nothing joins
    entry 11, OVERLAP blade x 51351..51601; one stub starts at 51500 and another
                      ends at 51476 -- both ~100-125 mm INSIDE the blade

They repeat per plan, which is what makes them findable: the 9 gaps are 3 a plan, all at y 39909
(x 29876 / 36700 / 40351 and the same three in the other two plans); the 12 overlaps are 4 a plan at
y 41759, 40209, 19329 and 40209.

**FIXED in v0.96.6, and it was not the decomposition.** `decompose_to_rectangles` is an exact cover
and all 111 of test14's composite rings tile PERFECTLY before anything touches them — measured. The
damage came after, from the two places that rewrite a rectangle's size and leave `center` alone:
`_apply_column_marks` (the label) and `_filter_column_entries` (the standards snap). Every piece
therefore grew or shrank about its own middle and BOTH its faces moved. For a column that is one
rectangle that is exactly right; for a column that is more than one it is wrong every time.

A resized piece now keeps the face it shares with its neighbours, read off the ORIGINAL tiling:
touching on one side it is anchored there and grows away from it; touching on neither it keeps its
centre, as before; touching on BOTH it keeps the drawn extent on that axis, because a label cannot
move a face another piece is drawn against — that last case is the 300 mm blade relabelled 350 with a
leg on each side, which spread 25 mm into both of them.

A second fault in the same two functions: `width_ft`/`height_ft` were never updated with the
millimetres, and `column_geom._bbox_half` reads the FEET — so every trim footprint was computed from
the DRAWN size while the column was placed at the LABELLED one.

Measured, composite columns whose pieces meet:

| | clean | gap | overlap |
| --- | --- | --- | --- |
| test14 before | 69 | 9 | 12 |
| test14 after | **90** | **0** | **0** |
| corpus before | 651 | 29 | 205 |
| corpus after | **923** | **5** | **3** |

**What it costs, stated rather than buried:** correct trim footprints cover more ground than stale
ones, so a small bay beside a widened column is absorbed — Test8 loses one def and 4.2 m² (43 →
42, 1002.3 → 998.1), Project1 one and 2.8 m² (153 → 152, 2877.1 → 2874.3). Project1 also sizes four
more beams (128 → 132). The direction is right: a slab should not be cast over the footprint the
column is actually placed at.

**Waiting on:** the owner's next Revit run on test14's 16 similar columns.

---

**v0.96.7 — HIS REPORT: "still shows test14 column still has gap while overlap is not there." The
overlaps are gone and the gaps are a DIFFERENT JOINT.** Measured: of the gaps left on test14, the
repeating one is **27 gaps of exactly 50 mm between a column piece and the BEAM beside it** — three
per plan at each of nine places — plus 9 of 100 mm. Between the pieces of a column there are none:
that count is still 0, which is what v0.96.6 fixed.

**And a correction to this entry's own measurements.** They were taken through
`build_column_sections(texts=all texts)`, which is what the sweep and my probes do — **the product
passes `texts=None`** and applies labels later through `correct_columns_with_text` on layer-ROUTED
column texts. So `_apply_column_marks` never runs in a real run, and half of what this entry
measured was a path the tool does not take. What DOES run in production is the standards snap in
`_filter_column_entries`, which v0.96.6 fixed, and `correct_columns_with_text`, which deliberately
leaves a cluster of three or more pieces alone (`len(near) > 2: continue`).

**A cascade was tried and thrown away.** Letting a boxed-in piece take its label and having its legs
follow to the new faces moved the 50 mm gaps from 27 to 18 but put 3 overlaps back — not clearly
better, and unproven against the production path. Reverted rather than shipped.

**ANSWERED, and it is neither of the two things this entry had been chasing.** The owner: "it beam
and column junctions with both being 350 thk width vertical, horizontal it is beam length and column
longer side gap is between junctions not because of width at all."

So the two members are the SAME 350 thickness and the gap is along the beam's LENGTH where it meets
the column — the beam stops short of the column face. Not a width disagreement, not a composite
piece drifting off its neighbour. Every measurement in this entry above was of the wrong joint,
which is why the numbers kept looking almost right.

**MEASURED, and it is LINK-side only, which is why nothing offline showed it.** Beam ends against
column faces on test14:

  * from the **DXF**, on the production path (`texts=None`): 30 ends off a face at all, the largest
    by **13 mm**. Nothing at 25 or 50;
  * from the **LINK**, replayed out of his 0.96.7 export: the same shape appears at **25 mm**, and
    the geometry is his sentence exactly —

        beam w=350 d=750  end (40300, 19444) | column piece 500 x 350 at (40326, 19269)  gap 25.9
        beam w=350 d=750  end (37801, 19444) | column piece 500 x 350 at (37276, 19269)  gap 24.8
        beam w=300 d=750  end (56751, 25069) | column piece 300 x 700 at (56601, 25094)  gap 25.1

Both members 350 thick, the gap along the beam's LENGTH at the junction, 25 mm — half of the 50 mm
by which a piece resized about its centre moves each face. So the beam was trimmed against one
version of the column's footprint and the column was placed at another.

**Where to look, named rather than guessed:** `column_trim_footprints` reads `_bbox_half`, which
reads `width_ft`/`height_ft` — the pair v0.96.6 started keeping in step with the millimetres. If the
trim is computed before the resize and the placement after it, every junction is out by half the
difference, which is what these numbers are. **Not changed this round**: it is a two-line change in a
place that decides every beam end in the model, and it wants its own gate run rather than being
squeezed in beside the dialog rewrite.

### BUG-26 — test17 refuses 78 slab profiles and takes eight minutes · `done`

**The owner:** "test17 json which took very long time image2 and it got stuck image1." The run
finished — 8 min 08 sec building, 11 min 09 sec from the click — and the progress bar he caught was
`create footings (8/10, 31s left)` with 1596 footings and 3530 walls still to place. So it was slow
rather than hung, and the "31s left" estimate was badly wrong, which is what made it look stuck.

**The refusals are the real fault.** `Slabs -- created: 173, skipped: 0, errors: 78`, every one a
profile Revit would not take: "it comes back to a corner it has already been through" (most) or "it
crosses or touches itself". The outlines repeat at a handful of sizes — 2400 x 2000 mm with 8 or 11
corners, 845 x 496 with 8, 125 x 1400 with 6 — which is a pattern, not scattered bad luck.

**BUG-24's merge does not touch these.** Measured: test17 merges 0 crosses, because none of its 145
free-standing marks hosts in a bay at all ("88 free-standing cut-out cross(es) sit inside no slab
bay"). So this is its own fault and gets its own entry rather than riding on that one.

**Not reproducible offline yet:** replaying test17's DXF through `apply_slab_stops` and then
`check_profile` declines nothing, because `split_profile` has already resolved the geometry by then.
The refusals happen on the LINK's records, and test17 is the drawing where link and DXF differ most
(`revit 18956 vs dxf 20972 curves; matched 12015`). Wants the same treatment BUG-24 got: numbers from
a failing run, then a rule measured against them.

---

**CLOSED BY THE DRAWING, v0.96.5. The owner: "there was no errors this time around, and it took 4 min
rather than 8 min."** He redrew test17 and pushed it: the DXF is replaced wholesale (1,012,916 lines
changed) and its export went from ONE storey to **sixteen**. The old run's own console said why it
was slow and why it refused so much — `Storeys: no layer boxes each floor plan -- building as one
storey` — so sixteen floor plans were being built into a single storey, every plan's linework
overlapping every other's. That is what produced 78 self-touching profiles and 3530 walls in one
pass. With the storey boxes drawn, each plan builds on its own and both faults go with it.

Nothing in the tool was changed for this, and the entry says so rather than claiming a fix. The
baselines moved accordingly and are attributed to the new fixture: the DXF sweep reads 20817 records
where it read 20972, the storey leg gains an eighth stack, and the fingerprint leg now measures
test17's richest storey (764 records) instead of the whole sheet (10148).

### BUG-25 — Run it from a schedule or a sheet and the link dies · `done`

**CONFIRMED by the owner in Revit, v0.96.2: "view switch working".**

**The owner, with the dialog:** "i am getting this error when i am usually running cad2bim link from
either schedule view or sheet view. not from 3D or Plan view."

```
Autodesk.Revit.Exceptions.ArgumentException: The view is not printable.
Parameter name: pDBView
  at Autodesk.Revit.DB.Document.Link(String file, DWGImportOptions options,
     View pDBView, ElementId& elementId)
  readers/dxf_linker.py, line 74, in link_dxf:  result = doc.Link(path, options, view)
```

**The mechanism is one line and it is not in doubt.** `link_dxf` takes `view = view or
doc.ActiveView`, and `Document.Link` will only take a view it can draw the import into. A schedule
has no drawing surface and a sheet is not a model view, so Revit refuses the argument before
anything is linked. The run then dies in the outermost `except` in `script.main` and the owner sees
a traceback where the tool should simply have got on with it.

**The owner's own fix, and it is the right one:** when the active view cannot host the link, DO NOT
show a dialog — put the user in a 3D view and carry on. A tool that knows exactly what is wrong and
what to do about it should not be asking.

**What "cannot host it" means, stated rather than guessed:** a link needs a graphical model view —
plan, ceiling, elevation, section, callout, 3D, or a drafting view — and no view template. A
schedule, a sheet, a legend, a browser or report view is out. The choice of substitute prefers the
3D view the owner asked for: the default `{3D}` first, then any other non-template `View3D`, then
whatever plan is open, and only if a model has literally no such view does it say so.

### BUG-24 — A double or triple cross reads as nothing, so its L or C is slabbed · `done`

**STILL FAILING in the owner's v0.95.x Revit run: "bug-24 still not working on test14."** BUG-11 is
the same fault seen from the other side -- "working on test14 expect on L or C cutout area is not
working currently both are linked bug".

**What was measured offline, and why it is not enough.** v0.94.0's rule reads test14's C-shapes
correctly *from the DXF*: 246 marks, the C at (26005..27633, 28268..29565) coming back as its three
real limbs, and of 246 voids none left with floor over more than half of it, where 36 had been. That
measurement stands and is reproducible. It is also, evidently, measuring something the Revit run
does not do.

**The gap is the SOURCE of the records, and it is the obvious suspect.** The build does not read the
DXF's records -- it reads the LINK's (`geometry_reader.read_link`), which is a different set: Revit
explodes closed polylines into separate lines, merges some, and drops others at junctions
(`comparison` reports `dxf_only` / `revit_only` on every run). Every offline measurement in this
entry was taken on the DXF side. A single cross survives that difference -- the owner confirms
BUG-18 works -- and a mitred limb may not, because its rule is the stricter of the two: both strokes
on a CUTOUT layer, properly crossing, and crossing within the middle 60% of each other.

**What is needed to fix it rather than guess at it:** a console report or JSON export from a failing
test14 run, so `cutout_cross_marks`, `free_cutouts_read` and `free_cutout_holes` can be read on the
LINK's records instead of the DXF's. If those numbers are lower in Revit than the 246 / 144 / 72
measured offline, the strokes are arriving differently and the rule has to be measured against what
Revit actually hands it. Nothing here should move until that is on the table.

---

**v0.96.4 — THE EXPORT ARRIVED AND IT WAS NOT THE SOURCE OF THE RECORDS.** The owner pushed
`0.96.2_footing_test14_with_textmode.json`, the link-side numbers this entry had been waiting for.
They are close to the DXF's, not far from them: per storey **62 cross marks, 28 free-standing, 9 cut
as holes**, against 246 / 144 / 72 read whole-file off the DXF. The strokes are arriving. The
diagnosis above was wrong, and the real fault was one step further on.

**What was actually wrong: an L is one void and it was cut as two.** Clustering test14's 246 marks by
which of them are drawn against each other says the shape of the problem exactly — 186 stand alone,
**12 pairs make an L and 12 triples make a C**. The C is a 225 mm left upright and a 250 mm right
upright, both 1297 mm tall, joined by a 1617 x 275 mm base; the drawing repeats it twelve times. And
every one of the 36 pieces of those twelve C's lands in the **same bay** as its siblings.

So each C was three abutting rectangles subtracted from one floor. That is not a C. Revit reads a
profile that comes back to a corner it has already been through and refuses the floor outright —
which is what the owner's test17 console prints 78 times — and where it does not refuse, the strip of
concrete between two limbs survives, which is his "it also create slab on cutout area".

**The fix:** voids already sharing a host bay are unioned before they are cut, through
`fold_plan.rect_union_outline` — the same coordinate-compressed grid walk the collar work uses, exact
for axis-aligned input. Measured: test14 **48 crosses become 18 voids**, test13 **70 become 26**, and
the C comes back as the eight-cornered ring it always was with its mouth still open (a point in the
gap between the uprights is tested as NOT void). test17 merges none — none of its 145 free marks
hosts in a bay at all — so its 78 refusals are a separate question, tracked at BUG-26.

Only voids in ONE bay are merged, so two crosses touching across a beam are never joined into a shape
spanning two floors.

---

**v0.96.5 — STILL FAILING, and the merge was never the missing piece: the MARKS were never formed.**
"1st of all L and C cutouts are still not working it is still there. C is being made with one whole
slab without respecting hatch." The v0.96.4 export finally makes the fault countable, per PLAN
(test14 draws three plans, which is why per-file numbers hid it):

| | DXF per plan | Revit link |
| --- | --- | --- |
| cross marks | 82 | **62** |
| free-standing | 48 | **28** |
| cut as holes | 27 | **9** |
| slab_cutouts | 30 | 30 |
| cutout bays by cross | 4 | 4 |

Twenty marks short — and the drawing carries exactly **62 standalone marks and 20 compound ones** per
plan. Revit forms every single standalone mark and **not one** belonging to an L or a C.

**The cause: `_cutout_strokes` kept only two-point records and dropped every polyline whole, in
silence.** A standalone X's diagonals cross in the MIDDLE of each other, so the link keeps them as two
lines; the limbs of an L or a C share an edge, their diagonals meet END TO END at the shared corners,
and connected linework comes back from `geometry_reader.read_link` as one polyline. Every segment of
a cutout polyline is cutout linework, so each is a stroke now.

**Proved offline, not merely argued:** test18's DXF carries exactly one three-point cutout record,
dropped whole until now, and it holds two real crosses — `cutout_cross_marks` 42 → 44. test14, test13
and test12 are all two-point records and do not move.

**And the offline pipeline was right the whole time**, which is why two rounds of measuring it found
nothing: replaying test14's C through `split_profile` returns exactly one piece, the 1141 x 1022 mm
island at (28059, 28544) — precisely the hatched area in his image 1. The fault was never in the
cutting; it was that Revit never had the marks to cut with.

**Two instruments added so this cannot hide a third time.** The export now carries CUTOUT linework
(it carried none, so link strokes could only be inferred by arithmetic), and the run prints
`stops: N cut-out cross(es) are drawn against each other, read as M L/C void(s)` — every other
counter is taken BEFORE the merge, so a run where no compound mark formed reported numbers identical
to one where they all did. test14 offline answers 48 into 18; 16 into 6 a plan.

**CONFIRMED FIXED, v0.96.6. The owner in Revit: "yes now cutout are being made on test14."** And the
numbers say it too, off his own 0.96.5 export — the console never opened to show him the new line,
because the console is DEFERRED and only flushes on failure, and his run had no failures. The export
carried the answer instead:

| per plan | v0.96.4 | v0.96.5 | the DXF |
| --- | --- | --- | --- |
| cross marks | 62 | **82** | 82 |
| free-standing | 28 | **48** | 48 |
| cut as holes | 9 | **25** | 27 |
| crosses merged into an L/C | — | **16** | 16 |
| voids they made | — | **6** | 6 |
| errors | — | **0** | |

Revit now forms every mark the drawing carries, and the 16-into-6 merge is exactly what the DXF
predicts per plan. Two of the 27 holes still do not land; that is a remainder, not the fault, and it
is small enough to wait for a drawing that shows it.


**The owner, testing v0.93.2 in Revit:** "almost all the single cross cutout line is working to
create actual cutout, but there is still issue persisting multiple cross cutout line ... double
cross cutout which makes L-shape and Triple cutout cross which makes C-Shape."

**Measured, and the cause is the shape the reading could return.** An L or a C is drawn as two or
three crosses, one over each limb — and a limb of a mitred C **is not a rectangle**. Its four stroke
ends form a trapezoid. `cross_marks` could only ever return an axis-aligned box (each end had to sit
within 50 mm of a bbox corner), so it refused them outright. test14's 504 cutout diagonals cluster
into **192 pairs (a plain cross), 12 clusters of four (an L) and 12 of six (a C)** — and of the
twelve C's, **not one stroke paired**: 72 read by nothing. test13 draws 30 more C's, 180 strokes.
The midpoint index compounded it: a mitred limb's diagonals do not bisect each other (test14's sit
138–225 mm apart), so the two halves of one limb never even met as candidates.

**Fixed in v0.94.0.** Two segments that properly cross ARE the diagonals of the quadrilateral their
four ends make, so the mark is that quad and no corner test is needed. What the corner test was
really doing — keeping neighbouring marks from pairing across their shared mitre — is now done by
two rules that are measured rather than incidental:

* **the drawing decides**: both strokes must be on a layer routed to `CUTOUT`. Crossing alone is
  catastrophic without it — MessyPlan-Test0 makes **188** crossing pairs from stair bands, grid
  lines and foundation linework, 24 inside a bay, **8,174 m² of floor** that would be deleted from a
  drawing that marks no cutout at all. Not one is on a cutout layer, while every one of test14's
  249, test13's 254, test12's 745 and test15's 5 is.
* **the crossing must be central**: `|t − 0.5| ≤ 0.30`. Over 1,248 cutout-layer crossings the
  measurement is a desert — 0.00 (1,081 pairs), 0.05 (28), 0.10 (98), 0.15 (10), **nothing at all
  until 0.50 (31)**, and 0.50 is an endpoint, which is two marks touching rather than one mark.

**Measured on test14: of its 246 voids, 36 had floor cast over more than half of themselves at
v0.93.2. Now none does.** The C at (26005–27633, 28268–29565) reads as its three real limbs —
225 × 1296, 225 × 1296 and 1627 × 275 — and `free_cutout_holes` doubles, 36 → 72.

### BUG-23 — On test17 the cutout reading is offered 7,120 beam strokes · `done` (v0.94.0)

Closed by BUG-24's layer rule, which is the fix this entry pointed at from the other side: a free X
is now read only off a cutout layer, so test17's 1,100 marks become **145**, and the 7,120 beam
strokes, 2,592 sanitary ones and 2,040 on layer `0` are refused before they can pair. Its
`free_cutout_holes` stays 0, so no floor moves on that drawing — the risk is what went away.

**The measurement that filed it**, taken as test17 entered the corpus and left here because it is
the evidence, not the story: found by re-taking the free-standing-X census after test17 entered the corpus — the comment in
`free_cutouts` claimed "every mark that survives the filter anywhere in the corpus is drawn on a
cutout or detail layer", which was true of the twenty drawings it was measured on and false the day
the twenty-first arrived. The comment is corrected in v0.93.2; this is the risk it leaves behind.

**Measured.** test17 pairs **1,100 X marks**, the most in the corpus, and the strokes they come from
sit on `B-200x650` (**7,120** of them), `A-_SANIFIX-_E-` (2,592), layer `0` (2,040), `DROP SLAB`
(1,546) and its other section-named beam layers. They measure 125 to 2,400 mm across, median 550 —
sanitary symbols and beam hatching, not voids.

**Nothing is cut for any of them: `free_cutout_holes` is 0 on test17.** Not one of the 1,100 lands
inside a slab bay. So no floor is wrong today — but the safety rests on the drawing's bays not
overlapping its plumbing, rather than on the member filter, which is the wrong thing to rest on.

`annotation_strokes` drops a stroke drawn on a BEAM or COLUMN layer, and it cannot drop these
because nothing classifies `B-200x650` as a beam layer yet. **BUG-22 is therefore the fix for most
of this**: the moment those layers classify, 7,120 strokes leave the pairing by the rule that is
already written. What remains after that — the sanitary and layer-`0` strokes — is the part worth
looking at on its own, and only with a drawing where it costs something.

### BUG-22 — test17 states each beam's SECTION in the layer name, and nothing reads it · `pending`

**Found** by measuring the owner's new `StructuralPlan-Test17.dxf` (pushed `6243f12`) as it entered
the corpus. Nothing is broken that used to work — the drawing is simply drawn on a convention
cad2bim has never met.

**Measured.** The drawing carries **9,515 records on nine layers named for the section they hold** —
`B-200x650` (7,165), `B-200x325` (981), `B-200x375` (480), `B-200x400` (430), `BK1-200x650` (264),
`B-200x300` (137), `B-200x450` (44), `B-300X650` (8), `B-400x650` (6), eight distinct sections in
all. `build_default_mapping` recognises none of them, so all 9,515 land in `unmapped` and the
drawing yields **151 beams** where it plainly draws thousands. Its other numbers are healthy — 48,441
records, 2,824 column entries, **7,336 wall segments** (the largest wall drawing in the corpus by
far, next is test8 at 178), 1,210 slab loops, 18,248 hatch regions — and it carries no foundation
layer, no legend and no schedule.

**Why it is worth its own entry rather than a mapping tweak:** the layer name is not just a
category here, it is the SIZE. A `B-200x650` record needs to reach the beam pass already sized
200 × 650, which is a source of section the pipeline has never had — today a beam is sized by a
text label or by a schedule row, and this drawing has neither for its beams. The routing and the
sizing are one question and should be answered together.

**Not started, and not to be started on a guess.** The owner has not reported anything about test17
yet; this is the measurement taken as the fixture arrived, filed so it is not re-derived later.

### BUG-20 — test16 builds NO footing from its 73 drawn outlines · `done`

**The owner, v0.91.0 round:** "our test16 schedule is not working still for slab and footing alike
and now it is even worse for footing is is not making it using footing outline at all in test16".
Their screenshot shows the F1/F2 marks written UNDER each footing outline, in magenta, clear of the
yellow ring.

**Measured, and the mechanism is one line.** test16 carries the convention in full — **73
foundation outlines** on `S-FND` and **73 marks** on `S-FND-IDEN` (F1 x30, F2 x26, F3 x15, RF1,
RF2) — and `plan_foundations` returns **nothing at all**. A note is assigned only to a ring that
CONTAINS it, and **not one of test16's 73 marks lies inside any ring**: 68 of them sit exactly
285 mm below the ring they name, the nearest-ring gaps running 87, 115 and 285 mm with nothing
between 115 and 285. No ring is labelled, so `if not labelled: return []` judges the drawing not to
carry the convention and the whole set is refused — which is why the footings vanished rather than
came out wrong. test10 writes all 17 of its notes INSIDE its rings, which is why it never showed.

**Two more things the same drawing proves.** `RF1`/`RF2` do not read as marks at all (`_MARK` is
`F\d+`), so its two rafts are nameless and the schedule rows that price them are unreachable; and
those two rings are L-shaped at 50.9 and 49.8 m², under the 60 m² line, so the area rule calls the
drawing's own rafts pads.

**Fixed in v0.92.0.** A note that lands inside no ring attaches to the nearest ring it is written
UNDER — its x inside the ring's x-span, the ring's foot above it — and failing that to the nearest
ring within `_LABEL_REACH_MM = 500`. "Under" comes first because it is what makes stacked footings
work: test16 draws its 1800 mm pads in pairs 400 mm apart, so the upper pad's mark sits 115 mm above
the LOWER pad's top edge and nearest-wins hands it to the wrong pad — measured, five pairs. The
reach is flat anywhere from 300 to 2000 mm (73 of 73 rings labelled, no ring twice, no ring with two
different marks), so the constant sits in the middle of a plateau. `RF\d+` is a mark, and an `RF`
mark makes a raft whatever the area. **Measured: test16 0 → 73 foundations planned**, each sized
from the schedule (F1 500 x30, F2 550 x26, F3 600 x15, RF1/RF2 1200); **test10 unchanged at 9** with
its marks, thicknesses and kinds identical, Test0 still plans nothing.

### BUG-21 — No storey can see the schedule, because the table is not on any storey · `done` (v0.93.0)

The other half of the owner's sentence — the slab schedule — and it is not the reader this time.

**Measured on test16:** the whole sheet reads 11 schedule rows (S1 125 … S6 250, F1 500, F2 550,
F3 600, RF1 1200, RF2 1200). Split into storeys the way a build does, **not one of the five storeys
reads a single row**: FOUNDATION LEVEL 0, GROUND FLOOR 0, 1ST FLOOR 0, TYPICAL 0, TERRACE 0 — while
those same storeys carry **62, 62, 62 and 15 S-marks on their plans**. The `SLAB SCHEDULE` block
sits outside every plan boundary, so the per-storey text list never holds it.

The slab pass parses the schedule from `sheet_texts`, which `_build_one_storey` sets to the STOREY's
texts, and the foundation pass parses it from its routed foundation notes, which are `S-FND-IDEN`
only and never `G-ANNO-SCHD`. Both therefore read `{}` on every storey of a multi-storey sheet,
every bay falls back to the blanket note or the base type, and no floor type is ever created from
the schedule — exactly what the owner sees.

**Fixed in v0.93.0.** `_build_one_storey` keeps one `file_texts = schedule_source or dxf_texts`
beside `dxf_texts`, and both passes take it as `schedule_texts` — the slab pass for its `S` rows and
the footing pass for its `F`/`RF` rows. `sheet_texts` is deliberately NOT widened: the blanket note
is read per plan at the owner's instruction ("150 is deliberate, read the note per plan"), and the
legend is drawn once per plan too, so both keep seeing their own storey. Measured: test16's
`foundation_planned_sized` **0 → 73** — every ring sized from the table (F1 500 ×30, F2 550 ×26,
F3 600 ×15, RF1/RF2 1200) — and `foundation_schedule_rows` reads 5 on test16 and 0 on the other
nineteen fixtures. Three AST pins hold the wiring, since every link in it fails silently.

### BUG-18 — A free-standing X marks nothing, so slab is cast over the opening · `testing`

**The owner, v0.95.x round:** "yes mostly working on test14 only place where slab are actually placed." So where a bay exists the cross now voids it. What is left is the 63 marks measured as sitting inside no bay at all -- nothing is cut there because the beam graph closed no floor over that ground, which is CRIT-4's territory, not this one's.


**Reported urgent** by the owner on the v0.91.0 Revit run: where the duplicate slab used to be two
pieces it is now three — one respects the outline and its holes, and **two are drawn inside a
cutout cross** (owner's images 2, 3 and 4).

**Measured on test14, and the mechanism is exact.** The `CUTOUT` layer carries **492 diagonal
strokes**, which group by shared bounding box into **130 X pairs**. Of those:

| what the X spans | count | read today |
|---|---|---|
| a `COVER` slab-stop ring | 52 | yes — becomes a hole |
| a whole slab bay | 6 | yes — the bay is withdrawn |
| **neither** | **72** | **no — nothing looks at it** |

Both readers we have (`chajja_cutouts` → holes, `cutout_bays` → withdrawal) need the X to sit on a
ring or a bay that already exists. **72 X pairs sit on open floor**, so they are read by nothing and
the bay is slabbed straight over them. They are not noise: nine of them are large and regular —
six of **2300 x 2925 mm** (x ≈ 25351, 27951, 98111, 100711, 178198, 180798, all at y 31766) and
three of **2300 x 2300 mm** (y 31294) — down to 2000 x 844 mm, and every one of the largest nine
reports "inside 0 bay(s)".

**Ruled out first:** `apply_slab_stops`' own report is healthy — `crossed 90, holes 66,
chajja_holes 18, divided 12, stair_bays 6, cutout_bays 15, chajjas 72` — and **no placed piece is
centred inside a crossed `COVER` ring**, so nothing is failing to subtract what it already sees.
The documented order (withdrawals before holes before division) is correct as written.

**Fix direction:** the rectangle an X spans is itself a cutout, whether or not a ring or a bay is
drawn there. Read the pair's own bounding rectangle as the opening and subtract it, so the 72
unread pairs stop being invisible. Sizes and positions above are the measurement to hold the fix
against; test10's foundation numbers (`foundation_planned` 9, `steps_planned` 7, `step_supports` 2,
`foundation_profiles` 9) must not move.

### BUG-19 — A chajja between two beams takes the deeper one · `done`

Reported by the owner on the same run (image 1): where a chajja's edge attaches to **two beams of
different depth**, it must hang off the **lesser** depth. In the owner's example it took the 600 mm
beam where the shallower one governs.

**Where it sits:** v0.91.0 taught the ledge to follow the beam it hangs off — the tie-break when
there are two was never stated, and the code takes the deeper. The reversal is local to the chajja
drop lookup; the count of chajjas built (72 on test14) must not move, only the depth each one takes.

### BUG-4 — An L-shaped column is placed as a big tilted rectangle · `done`

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

### BUG-17 — A slab schedule with a THK column is not read at all (test16) · `done` (v0.89.0, v0.93.0)

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

**The F/RF rows were wired in v0.89.1**, at the owner's word ("wire F/RF rows to foundation pass
too"): `plan_foundations` now takes the same `{mark: thickness_mm}` mapping and a ring that names a
mark but carries no thickness of its own takes the schedule's — the schedule speaks only where the
ring did not, so a drawing that dimensions its footings is untouched. test10's foundation numbers
(`foundation_planned` 9, `steps_planned` 7, `step_supports` 2, `foundation_profiles` 9) do not move.

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

### BUG-15 — A sunk beam must move by z Offset Value, and a bay's beams must sink too · `done`

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

**The owner:** "yes working on test14 mostly." Kept open on his "mostly" -- the word is doing work and the remainder has not been named yet.


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

### BUG-13 — A whole large bay crossed by an X still gets a floor · `done`

**The owner: "did not understand your wording, maybe you meant large area with X cutout line which
is now working on test14."** That is exactly it, and the title now says so. A small cutout is a
COVER ring with an X over it; this one was the LARGE areas -- whole slab bays, 1.36 to 19.81 m2, 63.5
m2 on test14 -- crossed corner to corner with nothing drawn around them, which no reading had ever
asked about. Confirmed working.


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

### BUG-14 — A hatch is shaping the slab, when it should only inform it · `done`

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

### BUG-11 — `COVER` and `CUT` are unmapped, so the slab never learns where it stops · `done`

**The owner:** "yes working on test14 expect on L or C cutout area is not working currently both are linked bug." Correct -- the remaining gap is BUG-24's, not this one's: the COVER rings are classified and read, and it is the mitred L/C marks that still fail to void. This entry closes when BUG-24 does.

**CLOSED with BUG-24 at v0.96.6**, on its own terms: the owner's "yes now cutout are being made on test14", and his export reading 82 of the drawing's 82 cross marks per plan where it read 62.


**Overtaken and closed in v0.83.0**, and the phase here was stale until this was re-checked: `COVER`
is `CATEGORY_SLAB_STOP` and the cutout token is classified, which is what the whole slab-stop pass
rests on. Left at `testing` rather than `done` because the owner has not called this one out as
fixed in its own words.


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

### BUG-12 — Cutout and staircase areas are still slabbed · `testing`

**The owner:** "yes mostly working on already tested fixtures need further testing." Held open for the same reason as BUG-6.


**Overtaken in v0.83.0 and after** — `apply_slab_stops` withdraws stair bays and cutout bays and cuts
crossed rings, free crosses and chajjas out of the bays that hold them. Phase corrected on re-check.

**How found:** the owner's images 4 and 5 — an X-crossed area carries a slab anyway, and the
staircase area is slabbed too. Same root as BUG-11 for the crossed areas (the X is never read for
slabs; it is read only for foundations today). The staircase case is its own: a bay a stair occupies
should not also be a flat floor. Both need the slab pass to subtract what the drawing marks absent.

### BUG-10 — A sunk beam gets slab laid over it · `pending`
**How found:** the owner's image 1. A sunk hatch crossing a beam means **the beam is sunk too** —
which v0.81.0 now does — but it does **not** mean the slab spans over that beam: the slab must stop
at the beam's edge. Today the sunk bay is laid across it.

### BUG-9 — `Floor.Create` refuses one slab profile · `testing` (not a console item)

**The owner asked what this one even is: "if it is related to console or bug-8 then it is not
working, or i am misunderstanding this point and unclear about it."** Fair -- the entry never said
plainly what would be seen.

It is NOT about colour. It is about one slab that Revit refused to create: a run reported one
`Floor.Create` error against 151 floors, with a stack and no geometry, so nothing said WHICH slab or
where. Since v0.82.0 every profile is checked before it is handed over, and a bad one is declined
here with its mark, its size and its position instead of throwing.

**What confirms it:** nothing visible, if no slab is bad -- which is the point. It shows only when a
drawing contains a profile Revit would refuse, and then the console names it rather than showing a
stack. It rides on BUG-8 only in that the naming line is printed through the same error channel,
so it cannot be judged until that channel is readable.


**Overtaken in v0.82.0**: `builders/slabs.check_profile` runs every profile through the same checks
before `Floor.Create` is called and declines a bad one by name, with its mark, size and position, on
the red channel. Phase corrected on re-check.

**How found:** the owner's console, one error against 151 created. **Not reproduced offline:** every
one of the 474 slab profiles the DXF produces passes a full check — corner count, closure, repeated
corners, self-intersection, hole-crosses-outer, hole-outside-outer, shared edges, hole-crosses-hole.
The Revit run builds from the LINK's records, which explode closed polylines into separate lines, so
its loops are not the DXF's. Until it can be reproduced the honest fix is for the builder to apply
those same checks before calling `Floor.Create` and report the profile it declines, with
coordinates, instead of letting Revit throw a stack into the console.

### BUG-8 — Console errors are still not red · `testing`

**STILL FAILING, second report: "still not marking errors in red on console."**

v0.81.1 wrapped each line separately on the theory that one `<span>` around a whole paragraph opened
on the first line and closed on the last, so the tag itself was what got read. That theory fitted
the first report -- the owner saw the markup -- and it has not fixed anything.

**The thing that was never established is whether pyRevit's CPython3 output window renders printed
HTML at all.** cad2bim is the only tool in this repository that tries: nothing else prints a `<span>`
or calls `print_html`, so there is no working precedent here to copy, and no way to settle it from
outside Revit. The two possibilities need opposite fixes:

  * the tags are RENDERED but the colour is overridden -- then the styling changes;
  * the tags are NOT rendered -- then every error line is currently showing its own markup as text,
    the markup has to go entirely, and errors are marked some other way (a plain `ERROR` marker,
    which reads correctly in any renderer).

**Needs one look from the owner:** does an error line in the console read
`<span style="color:#c00000;font-weight:bold">Slab creation failed.</span>`, or does it read
`Slab creation failed.` in ordinary black? That single answer picks the fix.

---

**ANSWERED, v0.96.3: "about yes bug-24 it shows `<span style ...`".** The second possibility, so the
markup goes entirely. His test17 console shows it eighty times over — the tag competing for attention
with the sentence it was supposed to emphasise, on the lines that matter most.

A second fault came with it. The message was HTML-ESCAPED before being wrapped, to protect markup
nothing ever interpreted, so an error quoting a Revit string containing `&`, `<` or `>` reached the
screen as `&amp;` and `&lt;` — corrupted text, on an error line, where the exact string is the whole
value of the report. Both are gone: an error is prefixed `!! ` now, which is text and needs nothing
to render it, and which a reader can search for.

**Red is not available and this entry should stop asking for it.** Colour would mean importing
pyRevit's output module, and those modules crash the CPython3 engine (Brand Guidelines 12.1). A mark
every console shows beats a colour this one does not. **Waiting on:** the owner confirming the tag is
gone and the `!!` lines read clearly.

**How found:** the owner's console showed `<span style="color:#c00000...">` as text. **Reproduced by
reading:** a Revit exception arrives as a paragraph, and one span wrapped around the whole of it
opens on the first line and closes on the last; the output view renders each line separately, so the
span styles nothing and the tag is what you read. **Fixed:** every line is wrapped on its own, and
the message is HTML-escaped first, being Revit data rather than markup.

### BUG-6 — A hatch's meaning is per PATTERN, but the mapping is per LAYER · `testing`

**The owner:** "yes working correctly on test14 but need further test fixtures for truly mark done." Held at `testing` at his request: one drawing proving it is not the same as the corpus proving it, and he is right to want a second.


**Decided by the owner and shipped in v0.80.0:** the hatch table gains a row per (layer, pattern)
wherever the drawing's own legend gives a layer's patterns more than one meaning; a layer whose
patterns agree keeps its single row. Measured, not assumed — over the corpus the rule moves only the
two drawings that carry a legend, 36 → 42 rows, where splitting every layer would have gone to 61
and inflated three drawings that gain nothing. test14 8 → 11, test9 5 → 8 (all four still column),
**test10 3 → 3**, so the Revit-validated foundation path cannot be disturbed. Keys are
`<layer_key>|<PATTERN>`, composed and never parsed; lookup falls back to the plain layer key, so old
mappings and the offline harnesses still route. It also closes half of CRIT-3 for split rows: a
stale `HAT → sunk` can no longer put "sunk" back onto GOST_GLASS.

### BUG-7 — The legend's sunk depths reach neither slab nor beam · `done`

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

### BUG-5 — The legend reader is blind to test14's whole legend · `done`

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

### BUG-1 — Placed footings' Width/Length: fixed, unconfirmed · `done`

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

### FEAT-11 — When the model is built, show it: 3D view, zoomed to fit · `testing`

**The owner:** "once model is ready, auto open the 3D view if not active by user and zoom to fit to
the model."

**Half confirmed, v0.96.3.** "zoom to building is also working" — but it was not: BUG-29 shows the
model box never folded, so what he saw was `ZoomToFit` framing the link and the grids too. The view
opening is done; the framing is fixed and unconfirmed. Stays `testing` until he sees the building
alone in frame.

The run ends today with the console and nothing else — whatever view the user started in is the view
they are left in, which after a build from a plan is a plan showing a fraction of what was made. So
at the end of a successful run: if the active view is not already a 3D view, open one, and zoom it
to fit either way, so the first thing the owner sees is the model that was just built.

The same view choice BUG-25 makes for the link, reused rather than written twice — the default
`{3D}` first, then any other non-template `View3D`. Zoom is `UIView.ZoomToFit()` on the open UI view
for that view; a model with no 3D view at all is a console line, never a dialog.

### FEAT-12 — Say how long it took, in a popup that gets out of the way · `done`

**The owner:** "one dialog popup which shows actually how much time it tooks in BOLD and BIGGER.
from when user click the run command. which should also close in 10s after showing and can also be
close manually or by pressing esc key."

A window at the end of the run carrying the elapsed time as its own headline — large and bold, the
one thing on it — that closes itself after **10 seconds**, and closes at once on **Esc** or on the
button.

**CONFIRMED by the owner in Revit, v0.96.2:** "elapsed to 30s is working / now dialog shows build
time headline and captions as dialog, input time". Two corrections of his are in it: the headline is
the BUILD alone, because the total counts the minutes spent reading the Link Options and settings
dialogs, and the wait is **30 seconds**, not 10, "because 10s go by very quickly". That figure is
written in exactly one place, `ui_dialogs.ELAPSED_AUTO_CLOSE_SECONDS`, and reaches `show_elapsed` as
a default argument so there is no second copy to miss.

**One thing to be plain about, because "from when the user clicks the run command" can mean two
things.** Timed from the ribbon click, the number includes however long the owner spent in the Link
Options dialog and the settings window — minutes of reading, not of work. Timed from Build, it is
what the tool actually took. The headline is the owner's literal ask, the ribbon click, and the
breakdown underneath says how much of it was the build, so neither number is lost and neither is
mistaken for the other.

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
| WORK-18 | Vertical members — a three-way choice: every one a COLUMN, every one a WALL, or COMBINE, where the mark decides (`C1` column, `SW1`/`W1` wall) and, where the mark is silent, L/B decides: under 4 a column, 4 and over a shear wall (IS 456, IS 13920, ACI 318) | `done` | Built v0.87.0 to the owner's spec. Their own 0.89.1 test16 export ran it: `columns.outcome` reports **71 walls, 0 rects** across the stack, so the toggle reaches the builder. **The owner in Revit: "work-18 is working"** |
| WORK-19 | Wall joins — both ends disallowed, and the corner they leave open filled: one wall runs through, the other stops on its face, so an L or a T keeps the drawn outline instead of pulling back to the centreline | `done` | The owner in Revit, v0.91.0 round: "test wall joins are working good for wall and column as expected" |
| WORK-20 | Chajjas — a beam-bottom ledge hangs at the soffit of the beam it is cast off, follows that beam down when a sunk hatch drops it, and the bay above it is no longer cast over the top of it | `testing` | The owner in Revit: "Chajja following its sunk beam is working good now". Two things remain open: which beam a ledge between two takes (BUG-19), and one bay near a ledge splitting into three (BUG-18) |

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
