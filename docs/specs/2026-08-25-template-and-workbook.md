# The template and the workbook, and which one is in charge

**Status:** proposal. Written before the first extraction, so it is a starting
position to argue with rather than a description of anything.

Two files now describe the same building. `template.rvt` holds families, types,
view templates, title blocks and shared parameters; `AnonGee_Sample_Project.xlsm`
holds levels, grids, sizes and placement. They overlap, and **every place they
overlap is a place they can disagree.** This says which one wins where, and why.

---

## Why a `.rvt` cannot simply be read

A Revit file is a compound binary that only Revit opens. No library reads one —
not openpyxl's equivalent, not anything, and this will not change. Which has one
consequence worth stating plainly: **a template cannot be reviewed, diffed or
discussed anywhere except inside Revit, by one person at a time.**

So the model describes itself instead. **Extract Template** (AnonGee tab → Dev)
walks the open model and writes one Markdown file beside the `.rvt`: every
category with what is in it, every family and every type inside it, every
parameter with its scope, the levels and grids, the view templates and sheets.
It is read-only, opens no transaction, and is safe to point at the real
template.

The file is sorted, carries no timestamp, and contains nothing that changes
between two runs over an unchanged model. That is deliberate: it makes the
report **committable**, so *what changed in the template* becomes a question
with an answer instead of an argument.

**This is how you hand me the template.** Run it, and send the `.md`.

---

## The rule: each fact has exactly one owner

The failure this avoids is not a crash. It is a value that gets written, looks
right, and disappears at the next family reload — with the run reporting
success.

| The template owns | The workbook owns |
| --- | --- |
| **Families.** What a column *is* — its geometry, its materials, its subcategories, how it behaves when it is cut | **Sizes.** What this job's columns are: 300 × 600 down to the second floor, 300 × 450 above |
| **Shared parameter definitions** — name, type, GUID, and which categories they bind to | **Values** in those parameters, per element |
| **View templates, title blocks, object styles, line patterns** | **Which views and sheets this job needs**, and what goes on each |
| **Naming conventions** — how a type is named once it exists | **Which types this job uses**, by mark |
| **Units, the survey point, project base point** | **Numbers**, in whichever unit `INFO` says |

Read the table as one sentence: **the template says what is possible, the
workbook says what is wanted.**

### The three cases where that has to be enforced

**A type the workbook names and the template does not have.** This is the
common one, and it is what stopped the first real run: fifteen footings and
ninety columns each reported *no type called `F1`* and placed nothing. Correct,
and useless.

The rule now is *duplicate and size*: the command finds a loaded family, copies
one of its types, names it after the mark, and sets its dimensions from the
TYPES sheet. **Creating a type is not authoring a family**, and the distinction
is what makes this safe — the new type inherits the template's materials,
subcategories and behaviour, because it is a copy of something the template set
up. A model with no family to copy is reported, not guessed at.

**A parameter the workbook writes to that the template has not bound.** Three
scopes behave differently and only one of them is safe:

| Scope | What happens to a value written into it |
| --- | --- |
| **Shared** | Survives a family reload, can be scheduled and tagged. **This is what a workbook should write to.** |
| **Project** | Lives in this file only. Does not travel to another model, and is not in the schedule of a model that opens the same family |
| **Family** | Cannot be reached from outside the family at all |

The extraction lists all three, which is the point of that section. Where the
workbook needs a parameter the template has not bound, the answer is to bind it
**in the template**, once, rather than have every command create parameters on
the fly in whatever model it is pointed at.

**A level or grid that exists in both.** Already settled and already built:
matched by name, never renamed, never deleted, never given a second one at an
occupied elevation. The workbook is the authority for the *number*; the model is
the authority for the *name*, because a rename changes what every view and sheet
refers to.

---

## What the extraction is for, concretely

Three things, in this order:

1. **Naming.** The first run failed because the workbook said `C-300x600` and
   the model had something else. The extraction lists every type mark actually
   present, so the workbook's TYPES sheets can be written against real names
   instead of guessed ones — or the template renamed, whichever is less work.

2. **The parameter list the workbook can rely on.** `FEAT-17` (rebar), `FEAT-14`
   (schedules) and `FEAT-18` (tagging) all need shared parameters that exist and
   are bound to the right categories. That list has to come from the template,
   and it does not exist yet.

3. **`CRIT-2`, which has been waiting on exactly this.** The written
   specification of what `template.rvt` must contain has been `pending` since the
   programme started, because writing it from imagination would have been
   fiction. With an extraction of the real template it becomes an edit: here is
   what you have, here is what the programme needs, here is the difference.

---

## The order this should go in

| # | Step | Who |
| --- | --- | --- |
| 1 | Run **Extract Template** on the real template and send the `.md` | project owner |
| 2 | Compare its type marks against the workbook's TYPES sheets; fix whichever is wrong | both |
| 3 | Write `CRIT-2` — the template specification — as a diff against what is actually there | me |
| 4 | Bind whatever shared parameters the specification calls for, in the template, once | project owner |
| 5 | Re-run the extraction; it should be a small diff | project owner |
| 6 | Only then, `types.sync` (`FEAT-7`) — because it needs to know what it is duplicating from | me |

Step 5 is the one worth insisting on. A template that can be extracted, changed
and re-extracted into a **readable diff** is a template that can be maintained
by more than one person, which is the thing this whole programme is for.
