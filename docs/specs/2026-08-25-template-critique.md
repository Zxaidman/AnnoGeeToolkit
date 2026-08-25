# R25_REBAR_AUTOMATION — what the extraction says, and what to change

Read from the report the project owner ran on 2026-08-25: 4,746 lines describing
the real template. Everything below is a fact from that file or a proposal built
on one. The owner's words were *"half baked, nothing is set in stone"* — so this
is written as a set of changes to argue with, not a verdict.

**One correction first, because it changes how to read the report.** The
parameter section of that extraction is **wrong**. It lists everything under
*Project* and shows no *Shared* section at all — not because the template has no
shared parameters, but because the code asked the wrong question (`BUG-21`). It
also printed `Autodesk.Revit.DB.ForgeTypeId` in every Type column, which is the
name of a class rather than the name of anything. Both are fixed; **re-run the
extraction before trusting that section.** The rest of the report is sound.

---

## 1. The column family is a project's leftovers, not a template's kit

`COLUMN` carries **about ninety types**, and the list reads like the residue of a
finished job:

```
200 X 2000    230 X 2875    300 X 1660    300 X 2515    450 X 2885
200 X 2400    230 X 5950    300 X 1675    300 X 2520    500 X 1160
230 X 2280    300 X 1200    300 X 1820    300 X 2525    600 X 1740
...
300 X 300     300 X 450     300 X 600     300 x 2940    450 x 2940
```

Three things are wrong with it, in increasing order of cost:

**The case is inconsistent.** `300 X 2940` and `300 x 2940` — capital and small
`x` in the same family. Harmless until something matches on names, at which
point it is a bug that only appears for two types out of ninety.

**Most of these are not columns.** `230 X 5950`, `300 X 4475`, `600 X 2095` — a
5,950 mm "column" is a wall, or a lift shaft, converted from CAD and left
behind. They will appear in every column schedule and every type selector on
every future job started from this template.

**A template should carry a kit, not a history.** Six or eight sections that the
practice actually standardises on, and nothing else. Everything on a live job
gets created as it is needed — which the bridge now does by itself, duplicating
and sizing from the workbook.

**Proposal:** keep `300 X 300`, `300 X 450`, `300 X 600`, `450 X 750`,
`450 X 900`, `600 X 600` (or whatever the practice's real standard set is);
delete the rest from the template. They are not lost — they are in the projects
that used them.

## 2. The type name is the size, and that is right

`300 X 600` names a section, not a schedule position. That is the correct
convention, and it is what the marking rule needs: a column marked `C1` is
`300 X 600` low down and `300 X 450` higher up, so **`C1` can never be a type
name**. The template has this right and the workbook has been built to match.

What follows from it is where the schedule mark goes, which is §5.

## 3. Foundations are named three different ways

```
Footing-Rectangular (loadable)   1800 x 1200 x 450mm, 2400 x 1800 x 450mm
Foundation Slab (system)         RCC FOOTING 750mm thk, 900mm thk, 1000mm thk
Wall Foundation (system)         Bearing Footing - 900 x 300
```

Three families, three naming styles, and a decision that has not been made:
**is a pad footing a loadable family or a foundation slab?** The bridge places
pads as **foundation slabs**, because that is what lets an arbitrary outline be
drawn — combined, stepped, cut round a pit — and a rectangular loadable family
cannot do that.

**Proposal:** foundation slabs for pads, and retire `Footing-Rectangular` unless
something specific needs it. Then one naming rule covers all of them.

## 4. A naming convention, since you raised ISO 19650

ISO 19650 is really about **information containers** — the file name — rather
than family and type names. Worth separating the two, because only one of them
is actually standardised:

**Containers (the standard's own subject):**

```
AG-XX-XX-M3-S-0001        Project-Originator-Volume-Level-Type-Role-Number
```

**Families and types (a house convention, not the standard's):** the useful
property is that a type name can be *derived from the thing itself*, so the
workbook can generate it and the template can hold it and they agree without
anybody maintaining a mapping.

| Element | Family | Type |
| --- | --- | --- |
| Column | `S_Col_Rect` | `S_Col_300x600` |
| Beam | `S_Bm_Rect` | `S_Bm_300x600` |
| Pad footing | `S_Fnd_Pad` | `S_Fnd_2400x2400x600` |
| Slab | `S_Slb_RC` | `S_Slb_150` |

`S` for structural, a three-letter element, then the size. Sorts sensibly,
reads in a schedule, and is generated rather than typed.

**This is a proposal and it costs almost nothing to reject** — it is one
constant in the workbook builder. What matters more than the exact letters is
that the workbook's `TypeMark` and the template's type name are **the same
string**, because then nothing has to guess.

**And they no longer have to be.** As of this build the matcher compares the
*dimensions* when the names differ, so a workbook asking for `S_Col_300x600`
finds the template's existing `300 X 600` rather than duplicating it — and says
so in the findings when it does. That takes the urgency out of this decision:
either convention works now, and matching names is a tidiness argument rather
than a correctness one.

## 5. The schedule mark has nowhere to live, and this is the real gap

The marking rule — `C1` repeats up a stack and across a floor — means the label
cannot go in Revit's `Mark`, which Revit expects to be unique and warns about.
That warning appeared on the first real run. `Mark` now carries the key
(`C1-A1-S1`), which is unique by construction.

**So `C1` itself needs a parameter, and the template does not have one.** It
must be:

- **shared**, so it can be scheduled and tagged and survives a family reload;
- **instance**, because it changes per column, not per type;
- **text**, because `C1` is not a number;
- bound to **Structural Columns, Structural Framing, Structural Foundations**.

Proposed name: `S_ScheduleMark`. Once it exists, put its name in the workbook's
`INFO` sheet under `SCHEDULE_MARK_PARAM` and every run fills it. Until then the
bridge writes the key, says once per run that the label had nowhere to go, and
carries on.

**This is the one item on this list that blocks something.** Schedules, tags and
the whole of stage 4 need it.

## 6. Seven project parameters bound to almost everything

`CHECK`, `ID`, `ID_LIC`, `ID_V`, `ITEM`, `LEVEL_V`, `WING` — each bound to
between eighty and two hundred categories, including `Analytical Pipe
Connections` and `Food Service Equipment` in a structural template.

`ID_LIC` in particular looks like a third-party add-in's licence marker rather
than anything the practice chose. **Worth checking what put them there before
deleting any of them** — an add-in that expects its parameter and does not find
it usually fails in an interesting way.

If they are the practice's own QA scheme, they should be **shared** rather than
project, or they will not survive being copied into another model.

## 7. The drawing half is empty

One sheet, `A101`, named *Unnamed*. View templates are Autodesk's defaults plus
four structural ones. No title block appears in the report at all.

Not a criticism — it is honestly what a half-baked template looks like, and it
is the half `FEAT-8` and `FEAT-9` will need. It is worth knowing that stage 6
starts from nothing rather than from something.

---

## What to change, in order

| # | Change | Cost | Blocks |
| --- | --- | --- | --- |
| 1 | **Re-run Extract Template** — the parameter section was wrong | one press | reading everything below |
| 2 | Bind `S_ScheduleMark` — shared, instance, text, three categories | ten minutes | schedules, tags, stage 4 |
| 3 | Delete the ~80 leftover column types; keep the standard set | an hour, careful | nothing, but it compounds |
| 4 | Decide pad footings are foundation slabs; retire `Footing-Rectangular` | a decision | `footings.sync` staying simple |
| 5 | Agree a type-naming convention — §4, or your own | a decision | nothing now that dimensions match |
| 6 | Work out what `ID_LIC` and friends belong to | an afternoon | deleting them safely |
| 7 | A real title block and a sheet naming scheme | a day | stage 6 |

**Only items 1 and 2 are urgent.** Everything else is tidiness that gets more
expensive the longer the template is used, which is an argument for doing it
now rather than an argument for doing it today.
