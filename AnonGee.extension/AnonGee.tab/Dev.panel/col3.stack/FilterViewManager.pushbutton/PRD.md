# Filter View Manager — product requirements

**Status:** agreed 2026-09-09, from the project owner's answers to the four
questions in `todo-list.md` §6. Nothing here is built.
**Companion documents:** `METHODOLOGY.md` (the rules of this repository),
`ARCHITECTURE.md` (how it is put together), `FOLDER_STRUCTURE.md` (where the
code goes), `todo-list.md` (the queue).

---

## 1. What is being asked for

> *"Category→Family→Type→Parameters wise filter view manager — where I can create
> rule based views buttons on dialog box with name which carry over Revit session
> and projects; when click it, only show that filter element on view. So for
> example I have made one button rule for category family type parameters, only
> filter Wall > Basic Wall > 100mm Gypsum Wall > area above 100 sqm."*
>
> *"Dockpanel like Properties and Project Browser in Revit, for showing created
> rule buttons from Filter View Manager."*

Underneath the example there is one job: **a modeller keeps re-making the same
temporary isolation, by hand, several times a day, and loses it every time.**
Revit will isolate anything you can select, but selecting *"every 100mm gypsum
wall over 100 m²"* is the slow part, and nothing remembers you did it.

So the product is not a filter builder. It is **a remembered one** — the
building of a rule is a cost paid once, and the pressing of it is the feature.

---

## 2. What a rule is

Four levels, narrowing:

```text
Category      Walls
  Family      Basic Wall               (system family here; a real Family for loadables)
    Type      100mm Gypsum Wall
      Parameter conditions             Area > 100 m²
```

**Every level is optional except the first.** A rule of *Walls* alone is legal
and matches every wall. A rule of *Walls > Area > 100 m²* skips family and type.
Making the lower levels mandatory would make the common case — "all the
structural columns" — impossible to express.

**Parameter conditions** are a list, combined with **All** or **Any**, matching
`MultiFilterParameter`'s existing model so a user who knows one knows the other.

**Every reference is stored as a string, never an `ElementId`.** That is the
requirement that makes the rule portable, and it is not negotiable — see §5.

### 2.1 Which parameters are offered

**Any parameter on the element**, with the ones Revit will not accept in a
native view filter **flagged**.

The flag does not stop a rule being saved or pressed, because pressing isolates
rather than writing a view filter (§3). It is carried for two reasons: it is
honest about what Revit can and cannot do with the rule, and it is exactly the
check FEAT-13 would need if converting a rule into a real project filter is ever
wanted. Cheap now, expensive to retrofit.

**It is drawn from an API contract, not from a measurement.** Until
`ParameterFilterUtilities.GetFilterableParametersInCommon` has been run against
a real model, the flag says where it came from rather than asserting it is right.

---

## 3. What pressing a rule does

**Saving a rule applies nothing.** It adds the rule to the list.

**Pressing a rule temporarily isolates its matches, in the active view only.**

`View.IsolateElementsTemporary(ids)`. Which means, and each of these is a
product decision, not an implementation detail:

| | |
| --- | --- |
| Scope | The **active view**. Not "all open views", not the project. |
| Lifetime | The Revit session. Gone on close, not saved with the model. |
| Printing | It does **not** print. Temporary isolation is a view-session state. |
| Undoing it | Revit's own *Reset Temporary Hide/Isolate*, or the tool's own Clear. |
| Left behind | **Nothing.** No filter appears in the project's Filters list. |
| Parameter limits | **None.** It is a set of ids, so any parameter works. |

**The tool never writes to the project.** A colleague opening the model sees no
trace that it was used. That is the point of choosing isolation: a tool that
quietly added named filters to a client's project would be a different, riskier
product, and nobody asked for that one.

---

## 4. The two surfaces

### 4.1 The modeless window — the workshop *(0.1.0)*

Where a rule is **built, previewed, named and saved**. Modeless, because a rule
is built while looking at the view it is meant for; Revit must stay interactive
(§12.8, and it is the pattern `OneFilterParameter` already proves).

It carries:

- the Category → Family → Type cascade;
- the parameter condition rows, All/Any;
- a **live match count**, debounced, before anything is applied;
- **Apply** (isolate now, in the active view) and **Clear**;
- **Save as rule** — name it, and it joins the list;
- the saved rules, as a list you can press, rename, duplicate, reorder and
  delete;
- **Select in Revit**, because sometimes the matches are wanted in the selection
  rather than isolated.

### 4.2 The dockable panel — the everyday surface *(0.2.0)*

Where the saved rules live once they exist: **a row of named buttons, always to
hand, no dialog in the way.**

- **It does not appear when Revit starts.** It appears when the pushbutton is
  pressed. (Registration still happens at startup — that is invisible, costs no
  UI, and is a Revit requirement, not a choice. See `ARCHITECTURE.md` §7.)
- **Docked under the ribbon by default** — a horizontal strip the width of the
  drawing area, one narrow row of rule buttons.
- **Re-dockable left or right**, like Properties or the Project Browser, where
  it becomes a vertical list. Revit gives this for free once the pane is
  registered; the layout has to survive both shapes.
- Pressing a button isolates. Pressing it again, or pressing **Clear**, restores.
- It is a *launcher*, not an editor. Building and editing a rule is the window's
  job. The panel stays narrow enough to leave alone.

**The window ships first.** The panel is worth having, and it is the half that
carries a startup-time component and an engine question with it — so it is
scheduled after there is something worth docking.

---

## 5. Where rules live

**Machine level, one JSON file:**

```text
%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json   (Windows/Revit)
~/.anongee/filter_view_rules.json                               (tests/fallback)
```

Overridable by `ANONGEE_PREFS_DIR`, which is what makes it testable. Exactly the
`cad2bim/prefs.py` pattern, which is already proven here and already migrates a
legacy path.

**This is what "carries over sessions and projects" means:** the rules follow
*the person*, at their desk, into whatever model they open next.

**A per-project override is wanted, and is not specified yet** (FEAT-14). Two
things must be settled before it is built, and both can lose a user's work if
they are guessed:

1. **Where a project store lives** — a JSON beside the `.rvt` (visible and
   editable, easy to lose in a move), Extensible Storage inside the `.rvt`
   (travels with the model, invisible outside Revit, needs a schema GUID that
   can never change afterwards), or a path the user points at per project (which
   is how an office actually shares one).
2. **What happens when both stores hold a rule of the same name.** Showing both,
   with their source marked, is the only answer that never silently loses one.

### 5.1 Why strings, and why it matters

A saved rule names `"Basic Wall"` and `"100mm Gypsum Wall"`. It does **not**
store their `ElementId`s.

`cad2bim/settings.py` states the rule and the reason: *"ids do not survive a
session, let alone another project, and a label that no longer exists simply
leaves that combo alone."* A rule carrying ids would be worthless the moment it
was opened in another project — which is the entire feature.

Names are matched the way **Revit** matches them: case- and
whitespace-insensitively. `cad2bim/type_names.py` already implements this
(`key()`, `find()`, `resolve_type()`), and root `task_plan.md` Phase 0.5 records
what learning it cost — an `==` comparison on a type name produced *"The name is
already in use for this element type"* in a live model.

**A rule that matches nothing in this project is not an error.** It is shown,
greyed, with what it could not find. Deleting a user's rule because they opened
a different model would be the worst thing this tool could do.

---

## 6. Non-negotiables

1. **Nothing is written to the project.** No `ParameterFilterElement`, no view
   template change, no element modified. The only Revit state this tool touches
   is the active view's temporary isolation.
2. **A rule is portable or it is pointless.** Strings only. A rule that cannot
   open in another project has failed at its main job.
3. **Nothing can fail a run.** An unreadable, half-written or
   newer-schema rules file reads as *no rules*, and a save that cannot write
   says so through `last_error()` rather than raising into the middle of the
   session. `cad2bim/prefs.py`'s rule, unchanged.
4. **The value parsing is hand-written.** `re` is not in this engine's stdlib
   (§12.9.3). `"100"`, `"100 m²"`, `"100.5"` and an empty box are all inputs.
5. **The rule engine runs without Revit**, so it can be tested before a model
   sees it (`METHODOLOGY.md` §10).
6. **One place holds the version**, and a test says so.
7. **A match count is shown before anything is applied.** Isolating 12,000
   elements by accident is slow to do and slower to undo.

---

## 7. What it will NOT do

Stated so nobody has to ask, and so the scope cannot drift quietly:

- **Not write view filters into the project.** FEAT-13 if it is ever wanted.
- **Not apply to more than the active view** in 0.1.0. FEAT-11 covers several
  views, and has to handle views that refuse filters (§13.7).
- **Not modify any element.** It selects and isolates. Editing parameters is
  what `OneFilterParameter` and `MultiFilterParameter` are for, and duplicating
  them would be a second place for the same bug to live.
- **Not survive a save.** Temporary isolation is temporary; that was the choice.
- **Not share rules between users** in 0.1.0. FEAT-12 (import/export) and
  FEAT-14 (project store) are the two routes, and neither is specified.
- **Not replace Revit's own view filters.** Anything that must print belongs in
  a real view filter, made in Revit. The tool should say so rather than pretend.

---

## 8. Staging

| Version | What it is | Blocked on |
| --- | --- | --- |
| **0.0.1** | The bundle exists. Pressing it says so. | — *(shipped)* |
| **0.0.2** | Documented: PRD, architecture, folder structure, queue. | — *(this build)* |
| **0.1.0** | The modeless window. Cascade, conditions, live count, Apply/Clear, save/rename/delete, Select in Revit. Rules persist at machine level. | — |
| **0.2.0** | The dockable panel. Registration at startup, shown by the pushbutton, under the ribbon by default, re-dockable. | CRIT-3 proved in Revit |
| **0.3.0** | Per-project store and precedence (FEAT-14). | the two questions in §5 |
| **later** | FEAT-11 multi-view, FEAT-12 import/export, FEAT-13 convert to a real view filter. | — |

**Promotion off Dev.panel** to Advance.panel — beside `FilterParameter.splitbutton`,
its nearest relative — belongs to the build the project owner has confirmed
working in Revit. That is a MAJOR extension change under the repository's own
table.

---

## 9. What success looks like

Not "the tests pass". The tests passing is the floor, and every bug this
repository has shipped passed them on the way to a model.

**0.1.0 succeeds when**, in the project owner's own Revit:

1. A rule for *Walls > Basic Wall > 100mm Gypsum Wall > Area > 100 m²* is built,
   the count shown before Apply matches what Revit selects afterwards, and Apply
   isolates exactly those walls in the active view.
2. Clear puts the view back.
3. Revit is closed and reopened, and the rule is still in the list.
4. **A different project is opened, and the rule is still there** — matching if
   that model has those types, greyed with a reason if it does not.
5. Nothing appears in the project's Filters list, and the model is unmodified.

**0.2.0 adds:** the panel is not there until the button is pressed; it opens
under the ribbon; the rule buttons work from it; and it can be dragged to the
left or right edge and still be usable.
