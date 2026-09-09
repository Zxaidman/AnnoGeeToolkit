# Filter View Manager — todo list

The queue. Everything that is wanted, wrong, or waiting, in one file, so the
state of the tool can be read without asking anybody.

## How this file works

Same rules as `RC Automation.pushbutton/todo-list.md`, because they are the
house rules and a second convention would help nobody.

| § | Section | What belongs in it |
| --- | --- | --- |
| 1 | **Critical** | Blocks the other implementation. Nothing ships until every one is closed or deliberately deferred. |
| 2 | **Errors and bugs** | Something is wrong now. Each carries how it was found and whether it is reproduced. |
| 3 | **Features** | New capability. Each is separable and can be scheduled on its own. |
| 4 | **Working now** | What is built and verified, so nobody rebuilds it and nobody claims more than was measured. |
| 5 | **Pending scope** | Agreed direction, not yet started. |
| 6 | **Owner's list** | Reserved for what the project owner sends next, and everything after. |

**Every entry has an ID** (`CRIT-1`, `BUG-3`, `FEAT-7`) so it can be referred to
in one word.

**Every entry carries a phase:**

| Phase | Meaning |
| --- | --- |
| `pending` | Not started. |
| `building` | Being written now. |
| `testing` | Built and in a build the project owner can test; waiting for an in-Revit result. |
| `superseded` | It worked, and something else replaced it. Recorded rather than deleted. |
| `done` | Confirmed in Revit, and copied into `done-list.md` with what was done. |

**Anything new is recorded here first** — a requirement, a bug, an idea — before
it is built, argued about, or written into any other document.

**Verified means one thing here:** the project owner ran it in Revit and the
report or the screenshot says so. A green test suite is not verification.

**An ID is unique within this file.** A reference across files is written in
full — *Bridge · FEAT-17*, *RC Automation · CRIT-1*.

Current build: **0.0.2** (extension 2.0.0). Documented, not built — PRD,
architecture and folder structure agreed; no tool code, no tests, nothing has
run in Revit.

---

## 1. Critical

### CRIT-1 — what pressing a rule does · `done — answered 2026-09-09`

**Answered by the project owner.** Saving a rule **applies nothing**; it adds an
item to the list the dockable panel shows. Pressing a rule **temporarily
isolates, in the active view only**.

So the mechanism is `View.IsolateElementsTemporary(ids)` — session-only, does
not print, does not survive save, cleared by Revit's own *Reset Temporary
Hide/Isolate*, and works on **any** parameter because it is just a set of ids.
Nothing is written into the project's Filters list, so the tool never changes
what a colleague sees when they open the model.

`ParameterFilterElement` is **out of scope**. It stays recorded as FEAT-13
because CRIT-2's answer keeps the door open for it, not because it is wanted.

**Unblocks:** FEAT-1, FEAT-3, FEAT-5.

### CRIT-2 — not every parameter can drive a native view filter · `done — answered 2026-09-09`

**Answered by the project owner.** Offer **any parameter on the element**, and
**flag** the ones Revit will not accept in a `ParameterFilterElement`. A flagged
parameter still makes a perfectly good rule button, because CRIT-1 settled that
a button isolates rather than writing a view filter.

The flag is therefore **informational today and load-bearing later** — it is
exactly the check FEAT-13 would need, so it is cheap to carry now and expensive
to retrofit.

**Still needs proving in Revit:** that
`ParameterFilterUtilities.GetFilterableParametersInCommon(doc, categoryIds)`
returns what is expected for a real category set, and how it behaves for a
multi-category rule. Until that runs in a model the flag is drawn from an API
contract, not from a measurement — so the first build shows it and says where it
came from rather than asserting it.

**Unblocks:** FEAT-2.

### CRIT-3 — the dockable panel still needs a startup component · `pending`

**Partly answered, and one part of the answer was wrong — the correction is the
finding.**

The project owner's answer was that the panel *"does not need to start with
Revit, only when user click the pushbutton"*. That is right about **visibility**
and wrong about **registration**, and Revit separates the two:

- **Registration** — `RegisterDockablePane` must be called from
  `IExternalApplication.OnStartup`, before any document is open. A pushbutton
  runs far too late; Revit refuses. (**Revit API contract — must be proved in
  this pyRevit version before 0.2.0 is scheduled.**)
- **Visibility** — a registered pane is *hidden* until something calls
  `DockablePane(guid).Show()`. That call is fine from a pushbutton.

So the owner's requirement is satisfiable exactly as stated: nothing appears
until the button is pressed. It still costs a startup-time component, and
registration is cheap — no UI, no document, no toolkit.

**The engine question is answered, and it was measured, not assumed.**
`docs/specs/2026-08-22-excel-revit-platform-architecture.md` §2a records
`/anongee/ping` reporting from inside `startup.py`:

```json
"engine":  {"implementation": "IronPython", "version": "2.7.12 … on .NET 8.0.30"}
"toolkit": {"importable": false, "error": "No module named anongee_toolkit"}
```

pyRevit loads `startup.py` on its **core engine, IronPython 2.7**, and `lib/py3`
is not on that engine's path. So the dock panel cannot import
`anongee_toolkit`, and the architecture's answer to the same problem applies
unchanged: **share a folder, not a module.** See `ARCHITECTURE.md` §3.

**Blocks:** FEAT-10 only. It does **not** block 0.1.0 — the modeless window
ships first (the owner's answer to question 3).

---

## 2. Errors and bugs

None. Nothing has run.

---

## 3. Features

Seeded from the project owner's idea, one ID each so they can be scheduled
independently. None is specified yet — specification is the PRD's job, and
nothing here is agreed until it says so.

| ID | Feature | Phase |
| --- | --- | --- |
| FEAT-1 | Category → Family → Type cascade picker, correct for both system and loadable families (METHODOLOGY §13.3) | `pending` |
| FEAT-2 | Parameter conditions on a rule — operator set, value parsing without `re`, units recorded with the number (§13.4) | `pending` |
| FEAT-3 | Apply a rule to the active view — `IsolateElementsTemporary`, active view only (CRIT-1) | `pending` |
| FEAT-4 | Name and save a rule; rules survive the Revit session **and** open in another project — strings only, never `ElementId`s (§13.5) | `pending` |
| FEAT-5 | The saved rules as pressable buttons in a modeless window | `pending` |
| FEAT-6 | Clear / restore the view to what it was before a rule was pressed | `pending` |
| FEAT-7 | Edit, rename, duplicate, delete and reorder saved rules | `pending` |
| FEAT-8 | Live match count before applying, debounced (`ui/dialogs.DebounceTimer`) | `pending` |
| FEAT-9 | Select the matched elements in Revit (`revit/selection.set_selection`) | `pending` |
| FEAT-10 | The dockable panel — hidden until the pushbutton shows it, docked under the ribbon by default, re-dockable left/right like Properties. Blocked on CRIT-3 | `pending` |
| FEAT-11 | Apply a rule across several views at once, skipping views that cannot take filters (§13.7) | `pending` |
| FEAT-12 | Import / export a rule set, so an office shares one | `pending` |
| FEAT-13 | Convert a saved rule into a real `ParameterFilterElement` in the project — only possible for rules whose every parameter passed the CRIT-2 flag. Not wanted today; recorded because CRIT-2's answer paid for it | `pending` |
| FEAT-14 | Per-project rule store overriding the machine one — location and precedence still to be discussed (owner's answer to question 4) | `pending` |

---

## 4. Working now

Nothing. The bundle exists; pressing it says so.

---

## 5. Pending scope

- **PRD** — what a rule is, what pressing one does, where rules live, what the
  window looks like. Blocked on CRIT-1 and CRIT-2.
- **Architecture** — which parts are plain Python (rule model, evaluation,
  persistence, parsing) and which touch Revit (collector, view application).
  The split decides what can be tested; see METHODOLOGY §10.
- **Folder structure** — the tool's own package beside `script.py`, following
  `anongee_autolevel`. Whether anything belongs in `anongee_toolkit` instead is
  an architecture decision: a rule model used by one tool does not, a view-filter
  helper that `cad2bim/builders/view_filters.py` could also use might.
- **Promotion off Dev.panel** to Advance.panel beside `FilterParameter.splitbutton`,
  once confirmed working. A MAJOR extension change under the repo's own table.

---

## 6. Owner's list

**Answered 2026-09-09.** Kept in full, because what was asked is part of the
record and one answer needed correcting.

| # | Question | Answer |
| --- | --- | --- |
| 1 | Isolate, or write a real view filter? | **Isolate**, active view only. Saving adds a button; pressing it isolates. CRIT-1. |
| 2 | May a rule write into the project's Filters list? | **No.** Nothing is written to the project. Recorded as FEAT-13 for later. |
| 3 | Dockable panel in the first build? | **No** — modeless window first, panel after. But it still needs a startup component; see the correction in CRIT-3. |
| 4 | Where do rules live? | **`%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/*.json`**, machine-level. A **per-project override** is wanted; its location and precedence are still to be discussed → FEAT-14. |

### Still open, and needed before FEAT-14 is built

1. **Where does a per-project rule store live?** Three candidates, and they
   behave differently: a JSON file beside the `.rvt` (visible, editable, easy to
   lose in a move), Extensible Storage inside the `.rvt` (travels with the
   model, invisible outside Revit, needs a schema GUID that can never change),
   or a path the user points at per project (a shared network folder — which is
   how an office actually shares one).
2. **Precedence when both stores hold a rule of the same name** — does the
   project win, does the machine win, or are both shown with their source
   marked? Both-shown is the only one that never silently loses a rule.

### Answered by reading, not by asking

**The dock panel's shape.** The owner asked for it *"below ribbon, narrow
height, length being viewport"* **and** *"just like property or project browser,
dock left or right"*. Revit gives both for free: register with
`DockPosition.Top` and it opens as a horizontal strip across the drawing area,
and the user can re-dock it left or right like any Revit pane. Nothing special
is needed — but the layout has to survive both shapes, and §12.4 of the brand
guidelines only covers the tall one (`MinWidth=240 / MaxWidth=360`). Recorded as
a design-system reconciliation item in `ARCHITECTURE.md` §7.
