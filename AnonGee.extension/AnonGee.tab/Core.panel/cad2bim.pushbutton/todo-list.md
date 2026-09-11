# cad2bim — todo list

The queue. Everything not yet confirmed in Revit lives here, and nothing leaves except by
reaching `done` — at which point it is written into `done-list.md` with what was actually done.
Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this
file before it is built, argued about, or written into any other document. Standing instruction
from the project owner, and it is what keeps this list the queue rather than a summary of one.

Current build: **v0.98.0** (branch `claude/cad2bim`, restarted from `main` after PR #10 merged).
1373 unit tests, 3 regression legs over 31 archived exports, 23 fixture drawings and 13 storey
stacks, all three baselines re-recorded because the owner redrew both test17 fixtures. This round
wired FEAT-16 into the build — a column is now placed ONCE over the whole run it
is drawn for, which takes test17 from 2525 placed rectangles to 524 — and fixed the two faults the
wiring exposed: an L whose legs disagreed about which storey they belonged to (57 outlines), and a
storey with nothing left of its own being rebuilt whole (the terrace, 58 members). FEAT-13's spread
was fixed with it: under pythonnet a .NET object reaches a callback as a fresh wrapper, so matching
the combo by identity never matched and the selection never followed. BUG-34 closed to `testing` with
it: a column the drawing closed as one ring now keeps the size it was drawn at, which stops about 42
members a storey being inflated past their outline by a label. Then BUG-35, which FEAT-16 had
introduced and the owner caught on his own run: a grid point can carry TWO members, one stopping
there and one carrying on above, and identifying a column by position alone made them one. A column
is identified by its place AND its section now, and all 43 of test17's concentric pairs come apart.
Then FEAT-17, the one he asked for next and answered four questions about: each element family drawn
in its own boundary ZONE, folded back onto one plan by its own origin marker before anything reads
it, so no two families' outlines overlap in the link and nothing is eaten. His example file folds
from 4070 records to 2038 and says what the combined copy says. Then, at the owner's request before he tests any of it, the two halves of the
dialog he asked for: FEAT-17's ZONE TABLE (one row per zone, saying what that zone holds, pre-filled
from its own layer name) and FEAT-18, the six sections moved from a strip across the top to a
collapsible RAIL down the left. The pages themselves never moved, which is what kept it to one pass:
every TabItem still carries the header it had, so every pin still reads the same file the same way.
Then his three notes on that build, all in v1.0.0: the zone table turned round to ask per ELEMENT
rather than per zone and fill itself in from the drawing rather than the layer names, the rail's
collapse animated instead of snapping, and `floor boundary`/`floor origin` taken off the Layers tab
(FEAT-19) so the Multi-storey tab is the only place they are named. The branch also carries the
rc-automation merge and the 1.26.1 extension identity. Longer records: `../../../../../task_plan.md`, `findings.md`, `progress.md` at the
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

### BUG-44 — "Grids created: 0" does not say WHY, so a correct answer reads as a failure · `testing`

**The owner:** "grids are not being made, maybe because cad has small line only? in next test i would
try to extend and check again".

**Nothing is wrong with the reading, and his export already said so** — it just never reached the
console:

    "grids": {"created": 0, "skipped": 37, "errors": 0,
              "skip_details": [{"reason": "grid already in the model", "count": 37}]}

**His model already has those 37 grids**, and the run declined to draw them a second time. That is the
behaviour anybody would want; it is only the console that made it look like a fault, because
`_create_grids` printed the COUNTS and then only the errors:

    Grids -- created: 0, skipped: 37, errors: 0

A count with no reason beside it reads as a failure whatever it actually was. The skip reasons were
being grouped for the export already, so v1.0.4 prints the same grouping:

    Grids -- created: 0, skipped: 37, errors: 0
      grid: 37 -- grid already in the model

**So the short lines are a red herring** and he does not need to redraw anything. (For the record they
ARE short — the drawing's 229 grid-category records run to a 1827 mm maximum and a 896 mm median, so
they are bubble leaders — but that is not what stopped them: a short grid would have been created.
What stopped them is that they lie on grids the model already has, which is the right call either
way.)

### BUG-43 — Only 107 beams of the drawing's 810 · `pending`

**The owner:** "now we have to fix the beam almost very few beam are drawn even on them there are some
which is not correct." Two different causes, and the big one is not in the beam code:

| | count |
| --- | --- |
| `S-BEAM` curves in the DXF | 1755 |
| beam segments the reader derives OFFLINE | **810** |
| curves the **Revit link** delivered | **213** |
| beams his run built | **107** |

**The 810 → 213 is BUG-36** — the link eating overlapping outlines, the same fault that takes the
whole drawing from 1855 curves to 1614. Nothing in the beam code can recover a curve that never
arrived. **The 810 → 130 is this item**: offline, only **130 of the 810 segments get a depth** and
**none get a mark**, which is BUG-42 — their labels carry a name and no size, and the size is in the
schedule table.

So the order is: BUG-42 first (the labels), then measure again, then BUG-36 for what is still missing.

### BUG-42 — A beam mark is only read off a label that also carries a size · `testing`

**Measured on the drawing he ran.** Its `S-BEAM-IDEN` layer holds **870 texts, 822 of which parse as a
mark** (`B12`, `B20`) — and **not one of them carries a size**. The sizes live in the schedule table on
`G-ANNO-SCHD`, keyed by the mark, which is exactly how he described it.

But `_apply_beam_marks` is driven by `sized_labels` — labels carrying a BxH — and takes
`segment["mark"] = text.mark` as a by-product. A label with a name and no size is never in that list,
so it names nothing. Offline: **810 segments, 0 marked**. In Revit: 107 built, **3 marked**.

**But the chain was already there, and the routing is right.** `_sized_beam_labels` sizes a mark-only
label from `schedule[mark]`, and the DEFAULT text mapping already sends his layers to the right
places: `S-BEAM-IDEN` → beam text (870), `S-COL-IDEN` → column text (680), `G-ANNO-SCHD` → schedule
(19). Reading his beam schedule offline gives 6 rows — `B1 200x650`, `B3 300x650`, `B4 200x300`,
`B5 400x650`, `B6 200x325`, `B7 200x375` — and **626 of the 822 beam marks are in it**.

Fed that schedule, the reader sizes **618 of 836 segments** and names **5**.

**So the size was arriving and the NAME was being stripped**, by `_dedupe_marks`. It exists for a real
case — one label drawn between two parallel members, both taking it, only the nearer keeping the name
— but it grouped the segments by their mark TEXT and measured them all against the FIRST label
carrying that text. That assumes a drawing names every beam differently: B1, B2, B3.

**His names beams by TYPE.** 822 labels, **8 distinct marks** between them, every 200x650 member
reading "B1". Against the one B1 label the sweep happened to keep, the other 89 B1 beams are all
"further away", so every one of them was stripped.

**FIXED in v1.0.4.** The sweep works per LABEL, not per mark string: a label is one piece of text at
one place and names the member it sits on. Two segments contending for ONE label is the case it exists
for and is untouched; two segments that took two different labels keep both names, and that the two
labels say the same word is the drawing's business. Duplicate marks are not Revit's problem here
either — `set_element_mark` writes the user's configured parameter first (his is `S-ScheduleMark`),
and the duplicate-mark warning belongs to the built-in `Mark` alone.

| his drawing, 836 beam segments | before | after |
| --- | --- | --- |
| carrying a size | 618 | 618 |
| **carrying a mark** | **5** | **548** |

### BUG-41 — The column label is TWO texts and neither half is read · `testing`

**Measured on `S-COL-IDEN`: 680 texts, an exact 340 / 340 split.**

| what the text is | parses as | count |
| --- | --- | --- |
| `250x2750` | a SIZE, no mark | **340** |
| `T1SW1`, `T1SW33b`, `T1SW125a` | **neither** | **340** |

Two faults on top of each other:

**1. `T1SW1` does not parse as a mark at all.** `_MARK_RE` is
`\b([A-Za-z]{1,3}\d+[A-Za-z]?)(?![A-Za-z0-9])` — one to three letters, digits, at most one trailing
letter. `T1SW41a` is letters-digits-letters-digits-letter and matches nothing. Beam marks (`B20`) fit
the pattern, which is why 822 of those do parse.

**2. Even parsed, nothing joins the two halves.** The name is a separate DXF entity sitting directly
ABOVE its size — measured over all 340 pairs, the nearest name text is **223 mm** away at the closest,
**336 mm** at the median, **539 mm** at the furthest, and `dy` is positive every single time.

    'T1SW126b'  above  '200x1800'    dy=+223  dx=  +3
    'T1SW33b'   above  '250x2150'    dy=+245  dx= +28
    'T1SW23'    above  '250x1300'    dy=+380  dx=+382

**FIXED in v1.0.4, both halves, each read off a measurement.**

**The pattern**, widened to letters-then-digits REPEATED with an optional trailing letter. Widening it
is the risky half — it runs over EVERY text in every drawing — so it was measured over **all 36119
texts in the corpus** first:

| | |
| --- | --- |
| answers that CHANGE | **0** |
| texts that newly match | **415** |
| …their shapes | `T#SW#`, `T#W#`, `T#CW#`, `T#PW#`, `T#Y#` — every one a member mark |

One false positive showed up in that measurement and is guarded: without `(?![xX]\d)`, **`B200x2380`**
— a beam labelled by its section — reads as one long mark `B200X2380`, because `x2380` is a perfectly
good letters-then-digits group. The size separator never continues a mark. With the guard, **0** of the
415 contain one.

**The join.** A size-only text takes the mark of the nearest name-only text ON ITS OWN LAYER within
600 mm. Measured across every fixture drawing, over the 367 size-only texts that have a name-only text
on their layer:

    nearest name      min 223   10th  270   median  340   90th  411
    SECOND nearest    min 836   10th 1086   median 2276   90th 3422

**The band from 411 to 836 mm is empty** — no label's own name sits beyond 411 and no other label's
name comes nearer than 836. 600 is the middle of the gap. Same layer because that is what the drawing
groups by, and it stops a beam's name crossing to a column's size where the two are drawn close. The
name text is deliberately left naming nothing: what it names is the member the SIZE text sits on, and
giving it a size of its own would invent a second member at the name's position.

| his drawing | before | after |
| --- | --- | --- |
| sized texts carrying a mark | 0 of 346 | **340** of 346 |
| **column rectangles carrying a mark** | **0** of 342 | **257** of 342 |
| beam segments carrying a mark | 0 of 810 | 98 of 810 |

The join runs inside `parse_texts`, so there is one call site and no pipeline can be wired up and
quietly miss it.

### BUG-40 — A member built as a WALL gets neither its mark nor its grade · `testing`

**The owner:** "for some reason mark and grade is not being assign correctly for both column and
beam", with a screenshot of a wall whose `S-ConcreteGrade` and `S-ScheduleMark` are both **empty**
while its geometry is right (250 x 2750, the label beside it reading `T1SW1 250X2750`).

**His settings are correct** — `cb_grade_param: S-ConcreteGrade`, `cb_name_param: S-ScheduleMark`,
`tb_grade_column: M40`, `tb_grade_beam: M30`. Nothing is misconfigured.

**His run built 171 vertical members and every one of them is a WALL**: `{"rect": 0, "circular": 0,
"walls": 171}`. And `place_vertical_members` says what happens to those, in its own words:

> `"wall_ids"` the walls this pass created. **Kept OUT of "created" on purpose**: the caller files
> "created" as the columns for the material pass, and a wall type keeps no structural material
> parameter to write

So `_apply_materials` reads `outcomes["columns"][_element_ids]`, finds the 171 walls are not in it,
and stamps nothing. `builders/columns.py` calls `_set_mark` on the rectangular and circular paths;
`builders/walls.py` never does.

**The reasoning holds for MATERIAL and not for the other two.** A wall type genuinely has no
structural-material parameter to set. But the grade is a text parameter the user NAMES
(`S-ConcreteGrade`), and the mark is another (`S-ScheduleMark`) — his screenshot shows the wall
carrying both, empty. A wall can hold them perfectly well; it was never asked to.

**FIXED in v1.0.4**, one end each:

* `place_walls` stamps `segment["mark"]`, exactly as the column builder stamps its rectangles'.
  `wall_plan` has put the drawing's mark on every segment since it was written
  (`segment["mark"] = rect.get("mark")`) and this was the one end that never read it.
* the created wall ids ride in `_WALL_IDS`, beside `_IDS` rather than inside it, and `_apply_materials`
  stamps the GRADE on both lists and the MATERIAL on `_IDS` alone. The two passes want different
  answers about a wall, so they read different lists; the original reason for leaving walls out stands
  for the one that still excludes them.
* `_strip_ids` drops the new key too — an ElementId is no more serialisable than it was.

**On his drawing this is worth nothing without BUG-41**, and that is the order they were done in: the
mark it stamps is the one the rectangle carries, and before BUG-41 no rectangle carried one at all.
Together they take his 171 members from 0 named to 257 of 342 rectangles named, and the grade from
stamped-on-nothing to stamped on all 171.

### BUG-39 — The size label grows a closed outline's leg past the outline · `testing`

**This is what the owner's eight screenshots actually show**, and BUG-37 is not it. His export says so:
the run he photographed is `1.0.1_column_test17_with_textmode.json`, whose `source` is
**`StructuralPlan-Test17-separate-boundary-zones`** — the ONE-STOREY zoned fixture, not the 13-storey
stack. On a single plan `column_extent` never runs, so BUG-37's fix cannot touch that run at all.
BUG-37 is real and measured, but it is a fix for stacks; this is the one in the pictures.

**Read straight off the screenshots.** Red is the outline the drawing closed, grey is what was placed:

| shot | labels | what is wrong |
| --- | --- | --- |
| T1SW41a/b | 250x1525, 250x2150 | the grey arm of the L runs ~250 mm **past the red** to the right |
| T1SW33a/b | 250x2850, 250x2150 | two grey bars across a wall with **no red outline under them** |
| T1SW39a/b | 250x2850, 250x2150 | the same, on another grid |
| T1SW46b/c | 200x2300, 200x1800 | this one is right — the grey fills the red L |

**Measured on the drawing he ran.** Building its column sections twice, once with the size labels and
once without:

| `StructuralPlan-Test17-separate-boundary-zones.dxf` | without labels | with labels |
| --- | --- | --- |
| rectangles built | 342 | 342 |
| **reaching outside every drawn outline** | **0** | **76** |
| how much of each lies outside | — | median **12%**, worst **56%** |

**0 → 76.** Of the 76, **64 were wholly inside their outline before the label pass and outside it
after**. His own export agrees from the other side: `text_corrected: 83` of 169 placed.

**It is the shared corner, counted twice.** `decompose_to_rectangles` splits a closed L into a
vertical leg and a horizontal one, and the horizontal leg deliberately STOPS at the vertical leg's
face — the corner belongs to one of them, not both. The label measures the arm to the outer face. So
resizing the leg up to the label adds the corner back:

    drawn leg 1300 -> label 1500   (+200)   the other leg is 200 thick
    drawn leg 1325 -> label 1525   (+200)   the other leg is 200 thick
    drawn leg 1950 -> label 2150   (+200)   the other leg is 200 thick

**11 of the 13** legs resized on his drawing grow by exactly another leg's thickness, and **59 of 86**
on test17-clean. It is not a clip being corrected. It is the corner.

**Which branch does it, counted on his drawing** (1251 labels, 342 rectangles, 304 whole rings):

| what the label did | times |
| --- | --- |
| whole ring: kept as drawn (BUG-34 working) | 171 |
| mark only: kept | 68 |
| already the right size: kept | 15 |
| **one leg of a closed composite: RESIZED to the label** | **13** |
| **two whole rings: MERGED into one at the label size** | **7** |
| two composites: merged | 2 |

**So BUG-34's principle was right and was not carried far enough.** `_whole_rings` protects only
entries whose status is `rectangle` — one closed ring, one rectangle. But a `composite` is just as
CLOSED: the drawing stated that member's size by drawing it, and its legs are a decomposition, not
damage. The case the pass genuinely exists for is a column a beam SLICED — an open path, recovered as
a fragment — and that is a different status entirely.

**And BUG-34's fix never ran.** Looking for where the growth happens, it is not
`correct_columns_with_text` at all — that is the pass BUG-34 taught, and its `text_corrected` is 83 in
his export. The growth is in **`_apply_column_marks`**, which runs INSIDE `build_column_sections`,
resizes every rectangle to the nearest mark within 1300 mm with no protection whatever, and had
already done so by the time the later pass looked. His export says `text_sized` — no, it says
`text_corrected: 83`; the sizing pass reported **257** refinements on that drawing offline. So BUG-34
stated the right rule in the wrong place and the owner never saw any of it.

**FIXED in v1.0.3**, by putting the rule where the sizing happens:

* `_CLOSED_RINGS` is `("rectangle", "composite")` — a ring the drawing closed, however many
  rectangles it decomposes to. `oriented_rect` is deliberately NOT one: it is the tightest box round
  a ring that would not lie on the axes and its entry says `approx=True`, so a label does know
  better.
* `_apply_column_marks` **names** such a rectangle from its label and leaves its size alone. A
  recovered fragment or a line spine is still refined, which is the case the pass exists for.
* `_whole_rings` widens to the same set, so the later pass agrees with the earlier one.
* Two CLOSED rings are never a split pair. Fusing them spans the gap BETWEEN them and builds a member
  where the drawing has nothing — the bars with no outline under them in shots 2 and 4. Seven labels
  did this on the drawing he ran.

| rectangles reaching outside every drawn outline | v1.0.2 | v1.0.3 |
| --- | --- | --- |
| `…-separate-boundary-zones.dxf` — **the drawing he ran** | **76** of 342 | **0** |
| …how much of each lay outside | median 12%, worst 56% | — |
| `StructuralPlan-Test17-clean.dxf`, 13 storeys | **597** of 2531 | **6** |
| …how much of each lay outside | median 13%, worst 85% | — |
| rectangles resized by a label (`text_sized`) | 257 / 1855 | 0 / 6 |

**The 6 that remain on test17-clean are all `line_spine`** — members derived from bare lines, which
have no closed outline to be inside. That is the pass doing its job, not a residue.

With the labels switched off, both drawings put **0** rectangles outside their outlines, before and
after. The labels now agree with that instead of overruling it.

**The DXF sweep moved, and every line of it is the column footprint being the DRAWN size now.** The
fingerprint and storey legs did not move at all. Measured directly, the only input that changed:

| drawing | column rectangles | footprint area | resized by a label |
| --- | --- | --- | --- |
| `StructuralPlan-Test8.dxf` | 79 → 79 | 47.15 → 47.77 m² | 75 → 11 |
| `LayoutPlan-Project1.dxf` | 310 → **308** | 187.22 → 190.52 m² | 270 → 66 |
| `StructuralPlan-Test14.dxf` | 408 → 408 | 184.46 → **237.52 m²** | 165 → **0** |

**In these drawings the labels were SHRINKING the outlines**, so the footprints grow. Everything else
the sweep reports is downstream of that: `split_beams_at_columns` trims beams where a column stands,
so a bigger footprint trims more (Test8's beams 217 → 195, Project1's 563 → 516), and the slab loops
the beam graph closes follow the beams (Test8's 13 → 17).

**Two things the owner may want to look at.** Test14's column footprint grows 29% — every one of its
408 rectangles is a closed ring and all 165 label resizes are gone, so if its linework is drawn
thicker than its columns really are, that drawing will now build thicker. And Project1 loses 2
rectangles: at their drawn size they fall outside the column size limits (`out_of_range` 33 → 35),
where the label had been shrinking them inside. The limits are on the Advanced tab if 1500 mm is too
tight for that drawing.

### WORK-13 — The gate never feeds a beam SCHEDULE, so BUG-42's path is uncovered · `pending`

**Noticed while fixing BUG-42.** The DXF sweep calls `build_beam_segments(..., schedule=None)` and
hands it every text in the drawing rather than the routed ones, so the whole mark → schedule → size
chain is outside the gate. On the owner's drawing that chain is everything the beams have: with it,
618 of 836 segments are sized and 548 named; without it, 130 and 0. The sweep sees the second number
and calls it normal.

That is how BUG-42 survived — a pass with no coverage, whose output looked plausible.

**What it needs**: the sweep parsing each drawing's own schedule-routed texts and passing the result,
the way the run does. Held rather than done in the same breath, because it also means routing the beam
texts as the run routes them, and that moves `beams`, `sized_beams` and `marked_beams` on several
drawings at once — a baseline move wanted on its own, attributed on its own, not folded into a fix.

### WORK-12 — The gate files an export by its FILENAME, so test17 now measures another drawing · `pending`

**Noticed when the owner's 1.0.1 exports landed** and all three legs moved. The corpus takes the
newest export per drawing, and the drawing is read off the FILE NAME:
`1.0.1_column_test17_with_textmode.json` → `test17`. But that run's own `source` field says
**`StructuralPlan-Test17-separate-boundary-zones`** — he ran the zoned fixture and the file is named
test17. So both new exports came from the zoned drawing, and both the `test17` and the
`test17-separate-boundary-zones` fingerprints now measure it:

    test17.storey:      %%U(TOWER 1)- GROUND FLOOR ROOF SLAB  ->  single
    test17.records:     941 -> 991          test17.column_rectangles: 291 -> 169
    storey replay:      test17: in the baseline but not measured

**The 13-storey test17 export is no longer measured by either leg** — not because it was deleted, but
because a single-storey file sorted ahead of it under the same name. The stack coverage that survives
is the DXF side BUG-37 added, which reads `StructuralPlan-Test17.dxf` and its 13 storeys directly.

**Two ways out, and the owner should pick.** Key the corpus off the export's own `source` field
rather than the filename, which is what the run actually read — or keep the filename rule and name
the files after the drawing. The first is the more faithful and needs no discipline from anybody;
the second leaves his older exports keyed as they are. Not changed unilaterally: it re-keys the whole
baseline either way.

### BUG-38 — Two column LAYERS drawing the same member build it twice · `pending`

**Found by the column-extent baseline BUG-37 added**, which records per storey how many built
rectangles stand more than a third inside each other. Across the 11 fixture stacks the answer is now
zero everywhere except two drawings, and neither of them is BUG-37's fault — neither carries a
`_STOP` outline in the clash at all:

| drawing | storey | pairs | the two layers |
| --- | --- | --- | --- |
| `StructuralPlan-Test9.dxf` | 2 | **13** | `COL` + `PI_COLUMN & SHEAR WALL` |
| `StructuralPlan-Test12.dxf` | 0 | **2** | `COL` + `COL` |

    COL                     3795 x 400  @(11520,29917)
    PI_COLUMN & SHEAR WALL  3795 x 300  @(11520,29967)     the same member, twice

**Test9 is two layers over one member.** Both map to the column category and both draw the same
shear-wall columns, 50 mm apart in depth. Whether that is a duplicate or a deliberate second element
is not something the geometry can settle — `PI_COLUMN & SHEAR WALL` may well be meant to build
something the plain `COL` outline does not. **It needs the owner's word before anything is changed**,
which is why this is recorded rather than fixed.

**Test12 is one layer drawing it twice**, 650x240 and 650x300 at the same grid point 30 mm apart. That
looks like the drawing's own duplicate, but 2 pairs in 204 is not enough to read a rule off.

**Held, not ignored.** The gate now pins both counts, so neither can grow without the run saying so,
and the drawing the owner is actually testing (test17) is at zero.

### BUG-37 — A column and the column it stands on are both built on the same floor · `testing`

**The owner, on the v1.0.1 column-only run of test17:** "only column test show this many problem
still check the zip archive i have given you with 7 to 8 image" — eight screenshots, and the fault in
almost all of them is one thing seen from different angles: **two members standing in the same place,
the smaller inside the larger**, plus the legs and phantom bars that are what that looks like where
the members are L- or C-shaped.

**Measured on `StructuralPlan-Test17-clean.dxf`, all 13 storeys, v1.0.1.** Of the 338 rectangles the
ground plan builds, **167 pairs stand more than a third inside each other** — and every single pair is
a `_STOP` outline against an ordinary one:

| the two layers in the clashing pair | pairs |
| --- | --- |
| `S-COLUM_STOP` + `S-COLUMN` | **161** |
| `S-COLUM_STOP` + `S-COLUMN_START` | **6** |
| two ordinary columns | **0** |

    S-COLUM_STOP  250 x 2150  @grid       <->  S-COLUMN  200 x 2150  @the same grid
    S-COLUM_STOP 1500 x  250  @grid       <->  S-COLUMN   850 x  200  x2, inside it

**So the drawing is right and the reading was wrong.** A structural plan is a section just above the
floor, so where a column CHANGES at that level the plan shows **both** of them: the one coming up from
below, drawn on `_STOP` because that is where it ends, and the one carrying on upward, drawn
ordinarily. The owner said exactly this — "stop means that layer column is stop on that particular
floor means it can go above (if is shows on ground level, then it can make above ground level to 1st
level)". Built as drawn, the second one starts on the floor the first one is still occupying, and the
250 x 2150 has a 200 x 2150 running up the middle of it. That is the photograph.

**FIXED in v1.0.2. An ordinary outline sharing a place with a stopping one belongs to the storey
ABOVE** — it stands on the one that stops, so its base is that one's top.

* `starts_above_the_stop(rows)` names those rows on one plan, by the share of the SMALLER of the two
  outlines the two have in common — a share, not a distance, because these members share a face line
  and not a centre.
* `plan` lifts them one storey before it works the runs out, so the spans come out
  `250 span 0-0` and `200 span 1-…` instead of both starting on the ground.
* `plan_storey` asks the same question of the RECTANGLES, which it can now do because it is given the
  layer each was drawn on. It has to be asked twice: `plan` reads the drawing's outlines, the builder
  places the rectangles those outlines decompose into, and **a leg of an L is smaller than the flat
  outline stopping beside it** — so `assign`, which can only measure boxes, gives the leg to the
  column that stops however carefully it looks. The layer does not lie. This is the last 19.
* Never on the top plan, which has nowhere above to put it: what is drawn is always built. Given the
  rectangles but not the stack's height, `plan_storey` does nothing at all rather than guess there is
  a floor above — of the two ways to be wrong, leaving a clash is the one the owner can SEE.
* **The run says it out loud**, because the rule moves members between storeys and a silent move is
  noticed a release later:

      columns: 187 of those outlines are drawn over a _STOP outline -- they are the column
      carrying on above it, and are built on the next floor up, not on the floor they are drawn on

**The threshold is read off an empty band, not chosen.** Across the first three plans, of the 198
pairs where a `_STOP` outline meets an ordinary one the overlap is **1.000 at the median and 0.567 at
the tenth percentile**, and the same **181** pairs are caught at >20%, at >30% and at >50% — *nothing
at all lies between 0.20 and 0.50*. `_SAME_PLACE_SHARE` is 1/3, the middle of the gap.

| `StructuralPlan-Test17-clean.dxf`, 2344 outlines → 345 columns | v1.0.1 | v1.0.2 |
| --- | --- | --- |
| ground plan builds | 338 | **171** |
| …of which stand inside another | **167 pairs** | **0** |
| first floor builds | 15 | **167** |
| the whole stack builds | 475 | **460** |
| …of which stand inside another | **167 pairs** | **0** |

**and nothing is lost.** All **345** columns still have something built in their place. Every one of
the 187 rows the lift moves (179 off the ground plan, 8 off the eleventh) **is drawn on the storey
above**, 187 of 187 — the lift never sends a column somewhere the drawing does not draw it. The 19
rectangles the layer rule drops from the ground plan are **19 of 19 built on the first floor**. The
first floor going 15 → 167 is the same reading from the other side: the members that carry on past the
ground-floor stop are now built where they stand, on top of it, instead of being crammed onto the
ground with it.

**The gate could not see ANY of this, and now can.** All three legs passed this change unchanged,
which is not reassurance — it is the finding. The fingerprint and sweep legs replay ONE plan each, and
the storey replay reads archived exports, which record a placed column's x, y, b and h and **never the
layer it was drawn on** — so the `_START`/`_STOP` reading is unreplayable from an export. The most
delicate part of the column path had no coverage at all. The storey leg now reads the **11 fixture
DXFs that split into a stack** as a second corpus and records, per storey, the columns, the runs, what
builds, and **how many built rectangles stand inside each other**. It runs 40s → 70s. The fault itself
is in the baseline, so it cannot come back quietly:

    StructuralPlan-Test17-clean.dxf   builds  [171, 167, 11, 11, 11, 11, 11, 11, 10, 9, 11, 18, 8]
                                      clashes [  0,   0,  0,  0,  0,  0,  0,  0,  0, 0,  0,  0, 0]

Two other stacks still record clashes, from a different cause and on layers with no `_STOP` among
them — **BUG-38**.

### BUG-36 — The link imports 213 of 877 beam curves, and no `DROP SLAB` at all · `pending`

**The owner, on the zoned fixture:** "currently it does not working as i am expecting".

**His v0.99.0 export says where it goes, and it is not the fold.** Read against the drawing he ran:

| layer | the DXF holds (folded) | Revit's link delivered | |
| --- | --- | --- | --- |
| `S-BEAM` | 877 | **213** | 664 gone |
| `DROP SLAB` | 99 | **0** | all gone |
| `SLAB FOLD` | 41 | **0** | all gone |
| `S-CUTOUT` | 181 | 181 | whole |
| `S-COL_STOP` | 161 | 161 | whole |
| `S-NON STR RCC WALL` | 253 | 253 | whole |
| `S-STAIR` | 44 | 40 | 4 gone |

His run's own comparison block agrees: **1611 curves from the link against the DXF's 1862, 737
dxf-only, 86 clipped** — and 529 of what did arrive was `unmapped`.

**So the zones work.** Columns, walls, cutouts and stairs come through to the record, the fold halves
the sheet exactly (his 171 vertical members are the same 171 the reader derives offline), grids build
37, slabs 55, stairs 2. What is still being eaten is beams and slabs, and only them.

**What it is NOT.** Not overlap inside the shared Beam-Slab zone: of 882 slab and fold segments in
that box, **11** are drawn exactly on a beam line, and only 2 beam segments are drawn twice over. Not
a frozen or switched-off layer either: every layer in the file is on, thawed and unlocked.

**What would say.** The run had both halves of the drawing all along -- what the link produced and
what the DXF holds -- and reported only totals. v1.0.1 adds the two lines that name names:

    link: 'S-BEAM' -- Revit imported 213 of the drawing's 877 curve(s)
    unmapped: 'DIM' -- 300 curve(s) no category claimed

The first says which layers the import ate; the second turns "unmapped 529" into a mapping he can
fix in the table he already has open. **Both are wanted on the next run of this fixture**, because
between them they say whether the 664 beams are missing or merely arriving under a name nothing
claims -- and those want opposite fixes.

### BUG-35 — Two columns on one grid point are read as one · `testing`

**The owner, on the v0.97.1 run:** "results are worse now for column only fewer columns than before.
single standing columns are drawn accurately but it fails if both Column and column-stop outline are
on top on each other."

**His export says FEAT-16 did what it was built to do** — 2182 vertical members down to 438, storey 0
placing 291 of them and each floor above 10 to 24. The count is not the bug. What he is looking at is
the case he names, and the drawing says exactly what it is.

**Measured in `StructuralPlan-Test17-separate-boundary-zones.dxf`, Grid-Column zone** (one storey,
each column drawn once): 186 `S-COLUMN` outlines, 148 `S-COLUM_STOP`, 6 `S-COLUMN_START`. For each
stop outline, the nearest column outline:

| gap between their centres | count |
| --- | --- |
| **0.00 mm — exactly concentric** | **48** |
| …of those, a DIFFERENT size | **43** |
| …of those, the same size | 5 |
| within 100 mm | 77 |
| further off | 23 |

    stop outline        column outline
    250 x 1200    <->   200 x 1200      same centre, x43

**So a grid point can hold TWO members, not one.** The column that stops there is 250x1200; the one
that carries on above is 200x1200; they share a centre because they share a face line. The drawing is
not marking one column twice — it is drawing two.

**`column_extent` cannot see that**, because it identifies a column by POSITION alone: both outlines
cluster to one id, and `extents` then gets two rows on the same storey — one `None` at 200, one
`stop` at 250 — whose order decides everything. The size cut opens a second run on the same floor,
`run_at` hands the first run to both rectangles, and the member that should have carried on up is
built as the one that stops.

**FIXED in v0.97.2. A column's identity is its PLACE AND ITS SECTION**, which is what the drawing
says and what lets the two tell themselves apart without any ordering luck. `assign` matches a built
rectangle to the identity whose section is its own, falling back to the smallest box containing it —
which is what keeps a leg of an L with the L it came from (BUG-34's measurement). The section cut
inside `extents` is unreachable now and is gone: a run is cut by `_START`/`_STOP` alone, exactly as
the owner described them.

**Verified on `StructuralPlan-Test17-clean.dxf`, all 13 storeys.** Its 2344 outlines are 345 columns
in 386 runs, every one of the 2525 built rectangles finds its column, and of the 43 concentric
stop/column pairs:

| | before | after |
| --- | --- | --- |
| read as ONE column, the wrong one built | **43** | **0** |
| told apart, each with its own run | 0 | **43** |

    storey 0 | the one that STOPS   | the one that CARRIES ON
             | 250 x 2150  span 0-0 | 200 x 2150  span 0-10
             | 250 x 1200  span 0-0 | 200 x 1200  span 0-10

which is the drawing read correctly: the 250 is built ground to first and stops, the 200 is built
once from the ground to the eleventh floor.

### BUG-34 — A size label overrules an outline the drawing closed · `testing`

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

---

**MEASURED AGAIN on the redrawn `StructuralPlan-Test17-clean.dxf` (0.97.0), and the direction is the
opposite of what the first reading suggested.** Over its first three storeys, running the correction
exactly as the build does — `mark_radius_mm` 1300, no schedule, and the texts routed the way the
build routes them (`COL. NO.` and `COL. SIZE` only; a first pass that fed it every sized text,
beam labels included, is not what the run does and its numbers are not in this table):

| entry the member came from | left as drawn | **grown to a label** | shrunk to a label |
| --- | --- | --- | --- |
| `rectangle` — ONE closed ring | 496 | **127** | 14 |
| `composite` — a leg of an L or a C | 58 | 31 | 3 |

It is not mainly overruling with a *smaller* size. It is **inflating about 42 whole columns per
storey**, and a column inflated past its outline sits outside the linked CAD exactly as far as a
shrunken one sits inside it. The commonest changes:

    250 x 1200  ->  250 x 1300   |   200 x 1500  ->  250 x 1500
    250 x 1200  ->  250 x 1500   |   200 x 1150  ->  250 x 1150
    200 x 1200  ->  200 x 1500   |   200 x 2100  ->  200 x 2300

**The 31 composite legs are the case DONE-22 built this for and they are fine**: a leg really is
smaller than the column it belongs to, and its label really does state the whole. **The 127 whole
rings are the bug.** Two things say so:

  * they came from `parse_column_polyline` as `status: "rectangle"` — ONE closed ring, nothing
    clipped, nothing split. The drawing stated that column's size by drawing it;
  * **152 of the 158 grown members had a drawn size that is a round 25 mm on BOTH sides** — 200x1500,
    200x1150, 250x1900. A junction clip leaves an arbitrary sliver (187, 213); a round number is a
    section somebody drew on purpose.

The labels themselves are mostly the members' OWN: a `250x1150` label 408 mm from a member drawn
200x1150 matches it on the long side exactly and differs only in thickness. So this is not primarily
the radius dragging in a neighbour's label — **it is the drawing and the label disagreeing, and the
tool believing the label.** The reach still deserves its own look (median label distance 847 mm, up
to 1306 mm), but it is the second problem, not the first.

**FIXED in v0.97.1, and it is a three-line rule.** `correct_columns_with_text` flattened the entries
into a bare rectangle list in its first line, so the `status` that tells a whole ring from a leg was
gone before any decision was taken. It is carried through now, and a SINGLE rectangle is resized only
when it is a PIECE — a leg of a composite, a recovered fragment, a box round a shape that would not
close. A ring the drawing closed keeps the size it was drawn at, in both directions.

Measured again on the same three storeys, before and after:

| | before | after |
| --- | --- | --- |
| whole rings left at the size they were drawn | 496 | **603** |
| whole rings resized by a label | 141 | **35** |
| legs of an L or a C resized by a label | 34 | 34 |

The 35 that remain are the two-piece MERGE branch — two fragments of one column with one label
between them — which is untouched and should be. The mark is still stamped on every member either
way: keeping the size must not cost the naming, which the schedule, the naming template and the
abutment recovery all key off.

Nine tests hold it (`test_label_over_outline.py`), two of which fail if the rule is removed; the
1342-test suite and DONE-22's own recovery tests pass unchanged. FEAT-16 makes it cheaper still: a
member is built once per run now, so a wrong resize no longer repeats up the tower.

**Still open, and second:** the reach itself. The label that resizes a member is a median 847 mm away
and up to 1306 mm, on a plan whose columns sit ~1.5 m apart. That wants the band measured between
"this member's label" and "the next member's label" before `mark_radius_mm` is moved off 1300.

**And one for the owner, because the tool cannot settle it:** on this drawing the labels and the
outlines genuinely disagree — a member drawn 200x1150 with a `250x1150` label 408 mm away, matching
on the long side and differing only in thickness. The tool now believes the outline. If the LABELS
are the authority in his office, that is a one-line change in the other direction, and it is his call
rather than a measurement's.


### FEAT-19 — The boundary and origin layers belong to the Multi-storey tab alone · `testing`

**The owner, on v0.99.0:** "we don't require `floor boundary` and `floor origin` on layer mapping so
i want all the origin and boundary thing to be on multi storey tab only then."

He is right, and it is the same setting asked twice. The Layers tab's Category dropdown offers
`floor boundary` and `floor origin` on every row, while the Multi-storey tab has two pickers that name
those layers directly — and the pickers already WIN, because the run stamps their categories after
the layer table ("an explicit pick always wins over the naming convention"). So the two entries on the
Layers tab can only do one of two things: agree with the pickers, or be quietly overruled by them.

**The change:** the geometry table's dropdown stops offering them. The categories themselves stay —
they are what `split_floors`, `zone_plan` and auto-detection read — and they are still stamped, from
the Multi-storey tab's pickers, which is now the only place they are chosen.

### FEAT-17 — Boundary ZONES: one element family per zone, so the link stops eating outlines · `testing`

**The owner, and this is the one he wants next:**

> "cad2bim - separating column, beam & slab, wall outline to each boundary zone with proper origin
> point to eliminate Revit eating Linked Outline merge. like for example one big `boundary` layer
> which will hold 4 specific `combine-boundary`, `grid-column-boundary`, `beam-slab-boundary`,
> `wall-boundary` inside it. each with same origin point on each boundary. […] reason why we need
> this currently revit link cad eat overlapping outline which causes our tool to be unreliable with
> new cad file which is not good for sellable product."

**Why it is the right shape of fix.** Every recovery pass in this tool exists because the Revit link
delivered less than the DXF holds: `recover_rectilinear_columns`, `recover_oriented_columns`,
`recover_outline_columns`, `recover_face_columns`, the fragment reassembly, `_is_clipped`. All of
them are guesswork about geometry that was destroyed at import, and the destruction happens where a
column outline, a beam outline and a wall outline lie on top of one another. Draw each family in its
own zone and nothing overlaps, so nothing is eaten, so nothing has to be guessed back.

**Measured in `StructuralPlan-Test17-separate-boundary-zones.dxf` (one storey, 4070 records).** The
convention is already exact — this is not a sketch:

| zone layer | box (mm) | records | what is in it |
| --- | --- | --- | --- |
| `Boundary` | 242867 x 133659 | 1 | holds the four zones |
| `Combine-boundary` | 101387 x 39923 | 2024 | a full copy of everything |
| `Grid-Column-boundary` | same | 457 | `S-COLUMN` 188, `S-COLUM_STOP` 148, `S-COLUMN_START` 6, grid 114 |
| `Beam-Slab-boundary` | same | 1313 | `S-BEAM` 879, `DROP SLAB` 249, slab projection 65, stair 44, fold 41, cutout 31 |
| `Wall-boundary` | same | 254 | `S-NON STR RCC WALL` 221, `NON STR. RCC WALL` 30 |

  * **the four zone boxes are the same size to the millimetre**, laid out 2x2 inside `Boundary`;
  * **each carries one `Origin` point at the SAME offset inside its own box — 78949.90, 12805.57 mm
    from its corner, all four identical.** Shifting each zone by its own origin therefore lands every
    zone exactly on top of the others. This is the same mechanism `floor_plans.split_floors` already
    uses to stack storeys, one level down;
  * **the texts travel with their zone**: 170 `COL. NO.` + 170 `COL. SIZE` in Grid-Column, 435
    `S-BEAM-IDEN` + 12 `SLAB THK.` in Beam-Slab, none in Wall. The Combine copy carries all of them;
  * **the hatches travel too**: Grid-Column 340, Wall 302, Beam-Slab 137, Combine 779 (= the sum).

**What the tool would do:** read the zones inside a storey's boundary, shift each by its own origin
marker, and CONCATENATE the records into one plan before any pass runs. Every pass downstream then
sees exactly what it sees today — one plan in one frame — so beam-to-column trimming, slab loops from
beams and edges, the legend and the schedule all keep working unchanged. The merge moves out of Revit
and into the reader, which is the whole point.

**ANSWERED, and built to the answers, in v0.98.0** (`zone_plan.py`, Revit-free, 25 tests):

| question | the owner's answer | what was built |
| --- | --- | --- |
| what is `Combine-boundary` for | "Fallback only" | with specific zones present the combined copy is CONSUMED, not built; alone, it builds as an ordinary drawing |
| fixed zone names or a mapping | "Mapping table" | any layer ending `-boundary` is a zone; `merge_zones(mapping=...)` takes the dialog's table, and the convention in the name fills it in |
| how zones nest with storeys | "i like both option 1 and 2 … when there is 20 different storey cad the option 2 shines but if there is only few storey … option 1 is easily manageable" | BOTH. Which one a drawing uses is read off containment, never a setting |

**How it reads both nestings with one mechanism.** In both, the piece that gets shifted is the
INNERMOST box and its origin marker sits inside it. Zones inside a storey: a group is the zones in
one storey box. Storeys inside a zone: a group is the storey boxes at the SAME PLACE inside their own
zones — position within the zone pairs them, because every zone is a copy of the same sheet, so the
ground floor sits at the same offset in the column copy as in the beam copy. Pairing by ORDER would
put a zone that is missing a floor out of step with the rest, silently.

**Measured on his own file.** 4070 records fold to 2038 — one copy of the plan, one origin marker,
one storey box — with 879 beams, 343 columns, 314 slab edges, 251 walls, 114 grids, 44 stairs, 41
folds and 47 cutouts, and every text and hatch carried in with its own zone. Against the combined
copy the three specific zones hold **361 column rectangles to its 358, the same 44 sections, 3
columns it does not have and none of its own missing** — so the zones say what the combined copy
says, and a little more (he drew the `_START` outlines only in the column zone).

**The box that holds the zones is never one of them** (v0.98.1). The storey boundary's own layer ends
`-boundary` too -- `Boundary` in his file -- and the Multi-storey tab's picker may be left empty, in
which case nothing by NAME tells the outer box from the four inside it. It is told apart by SHAPE
instead: a zone box that holds another zone box is the storey boundary. Without that, an empty picker
folded the whole sheet onto one of its own quarters and built everything twice -- the exact failure
the feature exists to end.

Two things it says out loud rather than doing quietly:

  * **the wall zone's 2 column records** are turned away — "not what this zone is for". Built, they
    would be columns a bay from the real ones;
  * **17 records sit inside no zone at all** (16 `A-CUTOUT-THIN`, one `S-COLUM_STOP`) and are KEPT
    where they are drawn, with a line naming them. Those sixteen are the beam schedule table's
    rules, which classify as `cutout` and would punch sixteen holes in a slab; the owner has already
    moved them to `G-ANNO-SCHD` in his newer file, which is the right fix — and the console line is
    how the next one gets noticed.

**Not built yet, and named so it is not mistaken for done:**

  * ~~the dialog's zone table~~ — **built in v0.99.0 and TURNED ROUND in v1.0.0.** The first cut had
    one row per zone with a dropdown naming a family ("beams + slabs + stairs"). The owner: "make left
    side independent of each element. like don't do beam+slab+stairs there. only do the beam, slab and
    stair separately and auto map the beam-slab-boundary to all, because sometimes user can also
    separate those in each boundaries or grid+column etc also."

    So the table is inverted: **one row per ELEMENT — beam, slab, stair, column, grid, wall,
    foundation — and the dropdown names the ZONE it is read from.** A drawing that splits beams and
    slabs into two zones says so on two rows; one that keeps them together points both rows at the
    same zone. Bundles are gone, because they were a guess about how somebody draws.

    **The auto-fill reads the drawing, not the layer names.** Each element category goes to the zone
    whose box actually holds the most records of it (the combined copy excluded, since it holds a copy
    of everything). On the owner's file that answers beam, slab edge, stair, fold, cutout →
    `Beam-Slab-boundary`, column + grid → `Grid-Column-boundary`, wall → `Wall-boundary`, with no
    clicks — and it would answer a `Stair-boundary` correctly too, which no naming convention of mine
    was going to;
  * **the storey preview for the storeys-inside-a-zone layout.** The Multi-storey tab counts storey
    boxes BEFORE the fold, so four copies of a 13-storey sheet would offer 52 rows instead of 13.
    The BUILD is right either way — the fold runs before the split — but the preview is not, and a
    20-storey sheet is exactly where he said that layout shines.

### FEAT-18 — The dialog as a sidebar, not a tab strip · `testing`

**The owner, with a before-and-after mock-up:** "i want our main dialog to change from image1 to
image2 example. see if thats possible."

**It is possible, and it is XAML only.** The window is built by `XamlReader.Load` from `ui.xaml` and
wired by name in `ui_window.py`, so the six tabs (`Layers`, `Build`, `Multi-storey`, `Tolerances`,
`Output & Graphics`, `Naming`) can become a left rail without a single builder or reader changing —
the panels keep their names, only their container changes. What the mock-up asks for beyond a
re-skin: a collapsible rail (icons only when collapsed), section titles with a one-line description
at the top of each page, the source file on a `Browse...` row, and the version moved to the rail's
foot. The Run/Cancel/Save/Load bar stays where it is.

**BUILT in v0.99.0, and the pages never moved.** The owner asked for it alongside the zone table, so
both landed together — one pass over `ui.xaml` instead of two.

The six `TabItem`s are still there, still with the headers they had; what changed is that the strip
is gone (a keyed `HeadlessTabControl` template draws the selected page and nothing else) and a
`nav_list` on the left drives `SelectedIndex` through one binding. So every check about which control
lives on which section reads the same file the same way, and every `find("...")` in `ui_window`
resolves exactly as before. That is the whole reason this was a day and not a week.

What the mock-up asked for, and what it got:

  * **the rail**: charcoal, full height, the brand at its head, the version at its foot, one item per
    section with a 16 px line icon drawn as a `Path` and a red bar down the selected one;
  * **collapse to icons**: `btn_rail` is a ToggleButton; every label's `Visibility` binds to it
    through a `BooleanToVisibilityConverter`, so the column shrinks to the icons on its own and the
    chevron flips « / ». No code — one binding per label;
  * **a title and a line of what it is for** at the top of each page, in the dialog's own `HelpText`
    style (the readable floor the owner set when the guide notes were FontSize 10);
  * **remembered**: the rail's state is a ToggleButton with a name, so `_control_value` reads it like
    any other control and the dialog reopens the way it was left. `ToggleButton` had to become a kind
    the settings capture understands — it is the base of `CheckBox` and `RadioButton`, so the three
    now share one line.

Three of the dialog's own rules caught mistakes on the way in, which is what they are for: the
rail's hover and selection tints had to become theme tokens rather than hex, the page descriptions
had to use `HelpText` rather than a caption style of their own, and a named control the settings
capture could not read had to be either taught or unnamed.

**The collapse ANIMATES (v1.0.0).** The owner, on the first cut: "sidebar is good but can you add
smooth transition to the collapse and reopening action?" The rail was a column that sized itself to
its labels, so hiding them snapped it from wide to narrow in one frame. It now has a width of its own
and a storyboard either side of the toggle: 176 px to 52 and back, 180 ms, quadratic ease-out, with
the labels clipped by the edge as it passes them rather than blinking out. Two DataTriggers on the
rail itself, no code.

**Not verified in Revit**: no test here can say whether the rail LOOKS right — only that every
control still exists, is still bound, and still lives on the section it did. Six new pins hold the
structure.

### FEAT-16 — `_START` and `_STOP` column layers say where a column begins and ends · `testing`

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

`column_extent.py`, Revit-free and 57 tests:

  * `mark_of(layer)` reads the SUFFIX, so an office's own prefix is nobody's business, and test17's
    own spelling `S-COLUM_STOP` (one M) is covered along with `-STOP` and ` STOP`;
  * `key_for(points)` says which footprints across plans are the same column. **Clustered, not
    binned** — rounding into a cell puts two footprints a millimetre apart either side of an edge
    and calls them two columns, which is the one job it has. Free to do because `floor_plans` hands
    each storey's records ALREADY SHIFTED so that plan's origin sits at (0, 0);
  * `extents(storeys)` gives `{(column, run): (first storey, last storey)}` under rule A;
  * `plan_storey(keys, spans, storey, rows, storeys)` says, for one plan, what it builds and what was
    already built below it. `rows` and `storeys` arrived with BUG-37: the layer each rectangle was
    drawn on, and how tall the stack is.

**Wired into the build in v0.97.0**, and the wiring found three things the planner alone could not.

**1 — a column is not one column.** `extents` first gave one span per column. Measured on test17:
**126 of its 219 columns change section over their height** — 200x2150 becoming 250x2150 part way up
— and the drawing marks almost none of those changes. One column over the whole height would have
carried the bottom storey's section through more than half of them, which is worse than the stack it
replaces. A run is now cut where the section changes, at a `_START`, and after a `_STOP`, and the
span is the run's own lowest and highest storey. **2344 drawn outlines over 13 floors are 386
columns, 196 of them running through more than one storey**, the longest all 13.

The section is read to the WHOLE MILLIMETRE, off a measured band: within one column two footprints of
the same section differ by at most **0.195 mm** (99th percentile 0.066), and the smallest real change
anywhere in the drawing is **50 mm**. The run counts are identical at 1, 5 and 10 mm — the band is
that empty.

**2 — an L is not its middle.** A rectangle found its column by nearest centre, and a composite
outline is decomposed into legs whose centres are nowhere near the outline's. Measured: **57 of
test17's outlines came back with their legs disagreeing** — one leg carried up a storey while the
rest were rebuilt on it, which puts one column straight through another. `assign` now takes the
column whose drawn BOX holds the rectangle, smallest box first so a neighbour inside a long L's box
still takes its own. **All 2525 built rectangles now find a column (was 2209), and no outline is
left half-carried: 0 of the 66 whose legs take different columns take a different span.**

**3 — a storey can have nothing of its own.** test17's terrace is 58 members and every one is built
lower down and carried up to it. `_create_columns` fell back to rebuilding the whole storey when no
group came back, which would have put a second column inside each of them. Nothing to place is now
nothing placed.

Across the stack: **2525 rectangles placed, down to 524.** The console says so before the first
storey is built, and each storey says how many were carried up.

`_column_groups` groups the storey's rectangles by the level they reach — `place_vertical_members`
takes ONE top level per call — and keeps the ENTRIES they came from, so the drawing's own layer and
the approximated flag survive the grouping. A storey with no plan (single-storey run, or a drawing
with neither layer) returns its own one group untouched, so those runs are unchanged.

**IT CHANGES EVERY MULTI-STOREY DRAWING, not only the one with the layers**, and that is worth
seeing before the next run rather than after it. A column drawn on three plans at one section is one
column whether or not anything marks it, so:

| drawing | storeys | outlines drawn | columns built | of them multi-storey | marks |
| --- | --- | --- | --- | --- | --- |
| `StructuralPlan-Test17-clean.dxf` | 13 | 2344 | **386** | 196 | 24 start / 337 stop |
| `StructuralPlan-Test17.dxf` | 13 | 2166 | **196** | 192 | none |
| `StructuralPlan-Test12.dxf` | 5 | 887 | **511** | 142 | none |
| `LayoutPlan-Project1.dxf` | 5 | 311 | **169** | 68 | none |
| `StructuralPlan-Test16.dxf` | 5 | 308 | **83** | 73 | none |
| `StructuralPlan-Test14.dxf` | 3 | 195 | **65** | 65 | none |
| `StructuralPlan-Test10.dxf` | 7 | 166 | **149** | 12 | none |
| `StructuralPlan-Test11.dxf` | 4 | 124 | **31** | 31 | none |
| `StructuralPlan-Test9.dxf` | 3 | 97 | **57** | 21 | none |
| `StructuralPlan-Test15.dxf` | 4 | 20 | **8** | 8 | none |

**test14 is the one to watch**, because BUG-27 is being chased on it: its 195 outlines become 65
columns, every one of them three storeys tall, so the junction gaps under investigation there will
look different from the last run for a reason that is not BUG-27.

Merging by position rests on the same premise the multi-storey build already rests on — that the
plans on a sheet are storeys of ONE building, stacked on level pairs in the order they are found.
Where that premise held, nothing changed but the count; where it did not, the old behaviour was
already building one storey's columns on another's levels. **If the owner would rather have it under
a tick** (Structure tab: "build a column once over the storeys it runs through"), that is a small
change and this record is the argument for making it.

**Not verified in Revit.** Both ends import Revit, so the wiring is held by ten static pins in
`test_dialog_wiring.py` and the numbers above come from the DXF, not from a model. It wants the
owner's next test17 run.


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

**v0.96.8 SELECTED CORRECTLY AND SPREAD NOTHING.** The owner, on that build: "now layer, text, hatch
mapping selection working as expected but selected value is not change for all the all selected item
only item changes for which ever dropdown is change from."

The spread found the row that raised the event by matching the control — `combo is sender` — and
**under pythonnet that can never match**: a .NET object arrives at a callback as a FRESH managed
wrapper, so Python identity against the stored reference is False every time. `spread` was handed no
owner, returned nothing, and did it silently. The row is named by INDEX now, bound when the row is
built, and an index cannot be wrapped twice. Fixed in v0.97.0, with the failure written into
`selection.py`'s docstring so the next person does not reach for identity again.

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
