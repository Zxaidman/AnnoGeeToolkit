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

Current build: **0.0.1** (extension 2.0.0). Scaffold only — no tool code, no
tests, nothing has run in Revit.

---

## 1. Critical

### CRIT-1 — what pressing a rule actually does is not decided · `pending`

Revit offers two mechanisms and they are different products:

- **`View.IsolateElementsTemporary(ids)`** — session-only, does not print, does
  not survive save, cleared by Revit's own *Reset Temporary Hide/Isolate*,
  works on **any** parameter because it is just a set of ids.
- **`ParameterFilterElement` + `View.AddFilter` / `SetFilterVisibility`** —
  permanent, prints, survives save, leaves a named filter in the project's
  Filters list, and only accepts parameters Revit considers filterable
  (**CRIT-2**).

The idea says the *rules* carry across sessions and projects. It does not say
the *applied state* does. Until this is settled the UI cannot be drawn, because
the two need different controls, different warnings and different undo stories.

**Blocks:** FEAT-1, FEAT-3, FEAT-5.
**Needs:** the project owner's answer. See METHODOLOGY §13.1.

### CRIT-2 — not every parameter can drive a native view filter · `pending`

`ParameterFilterUtilities.GetFilterableParametersInCommon(doc, categoryIds)`
returns a set smaller than "every parameter on the element"
(**unverified — Revit API behaviour, must be proved in Revit**).

Two possible answers, and they give different tools:

- **Filterable only** — the picker is honest, every rule can become a real view
  filter, and the parameter list is narrower than the idea implies.
- **Any parameter** — the picker matches the idea, and any rule using a
  non-filterable parameter can only ever isolate, never write a view filter.

**Blocks:** CRIT-1, FEAT-2.
**Proof needed:** run `GetFilterableParametersInCommon` against Walls in a real
model and compare the result with the full parameter list. Screenshot or report.

### CRIT-3 — the dockable panel is a startup problem, not a pushbutton one · `pending`

A dockable pane must be registered through `IExternalApplication.OnStartup`,
before any document opens (**unverified in this repo — no provider exists
anywhere in the tree**). A pushbutton runs far too late.

The only startup hook this extension has is `AnonGee.extension/startup.py`, and
its own docstring records that pyRevit runs startup scripts on the **core
engine, which is IronPython**, so it cannot import the CPython 3 toolkit in
`lib/py3`.

`Resources/Panels.xaml` already ships `DockablePanelTemplate` and
`tests/test_scripts.py` already lists `IDockablePaneProvider` among the
interfaces the Python.NET rules apply to — so the repository anticipated this
and nothing has used it yet.

**Recommendation:** schedule separately from the rule engine. The pushbutton can
ship and be useful without it. See METHODOLOGY §6.

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
| FEAT-3 | Apply a rule to the active view | `pending` |
| FEAT-4 | Name and save a rule; rules survive the Revit session **and** open in another project — strings only, never `ElementId`s (§13.5) | `pending` |
| FEAT-5 | The saved rules as pressable buttons in a modeless window | `pending` |
| FEAT-6 | Clear / restore the view to what it was before a rule was pressed | `pending` |
| FEAT-7 | Edit, rename, duplicate, delete and reorder saved rules | `pending` |
| FEAT-8 | Live match count before applying, debounced (`ui/dialogs.DebounceTimer`) | `pending` |
| FEAT-9 | Select the matched elements in Revit (`revit/selection.set_selection`) | `pending` |
| FEAT-10 | The dockable panel — blocked on CRIT-3 | `pending` |
| FEAT-11 | Apply a rule across several views at once, skipping views that cannot take filters (§13.7) | `pending` |
| FEAT-12 | Import / export a rule set, so an office shares one | `pending` |

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

Reserved for what the project owner sends next.

**Open question 1.** CRIT-1 — isolate, or write a real view filter?

**Open question 2.** Should a rule be able to write into the *project's* Filters
list (visible to everyone who opens the model), or must it stay a personal
overlay?

**Open question 3.** Is the dockable panel wanted in the first build (CRIT-3
says it costs a startup-time component and an engine question), or is a modeless
window enough to start?

**Open question 4.** Rules stored per machine (`%APPDATA%`, like
`cad2bim/prefs.py`), per project (inside the `.rvt`), or both with the machine
set as the default and a per-project override?
