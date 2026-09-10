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

Current build: **0.0.4** (extension 2.0.0). The rule engine is whole — the
tested half and the Revit half — and the button is a probe that runs it against
a real model. 155 tests. **Nothing has been confirmed in Revit yet**, and by
this file's own rule that means none of it is verified.

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

### CRIT-3 — the dockable panel still needs a startup component · `testing`

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

**Built in 0.2.0.** `startup.py` calls `anongee_filterpane.register()`, wrapped
so it can never take pyRevit's load down, and the outcome goes to its own record
because when registration is what failed there is no pane to look at and no
route to ask. Pressing **Panel** in the window reads that record back.

**What is still unknown, and only Revit can say:** whether pyRevit hands a
startup script a `UIControlledApplication` at all, and whether Revit accepts the
registration in this version. Three causes look identical from a ribbon with no
panel on it, and the record is what tells them apart.

**If it failed, nothing else is affected.** The window does not depend on the
panel, and Panel reports rather than breaks.

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
| FEAT-1 | Category → Family → Type cascade picker, correct for both system and loadable families (METHODOLOGY §13.3) | `testing` — built, with a searchable category list whose ticks survive a search |
| FEAT-2 | Parameter conditions on a rule — operator set, value parsing without `re`, units recorded with the number (§13.4) | `testing` — built; conditions are added one at a time and listed, not edited in a grid |
| FEAT-3 | Apply a rule to the active view — `IsolateElementsTemporary`, active view only (CRIT-1) | `testing` — the Apply button |
| FEAT-4 | Name and save a rule; rules survive the Revit session **and** open in another project — strings only, never `ElementId`s (§13.5) | `testing` — Save rule writes the machine store |
| FEAT-5 | The saved rules as pressable buttons in a modeless window | `testing` — the list on the left; select one and press Apply |
| FEAT-6 | Clear / restore the view to what it was before a rule was pressed | `testing` — the Clear button |
| FEAT-7 | Edit, rename, duplicate, delete and reorder saved rules | `testing` — all five, and Delete asks first |
| FEAT-8 | Live match count before applying, debounced (`ui/dialogs.DebounceTimer`) | `building` — the Count button gives the number on demand. It is not yet live-as-you-type, which is what the debounce is for |
| FEAT-9 | Select the matched elements in Revit (`revit/selection.set_selection`) | `testing` — the Select button |
| FEAT-10 | The dockable panel — hidden until the pushbutton shows it, docked under the ribbon by default, re-dockable left/right like Properties | `testing` — built in 0.2.0. Whether Revit accepts the registration is what the startup record answers |
| FEAT-11 | Apply a rule across several views at once, skipping views that cannot take filters (§13.7) | `pending` |
| FEAT-12 | Import / export a rule set, so an office shares one | `pending` |
| FEAT-13 | Convert a saved rule into a real `ParameterFilterElement` in the project — only possible for rules whose every parameter passed the CRIT-2 flag. Not wanted today; recorded because CRIT-2's answer paid for it | `pending` |
| FEAT-14 | Per-project rule store — **decided and read-side built**: `<model folder>/AnonGee/filter_view_rules.json`, one per folder, no precedence (both shown, each badged). Not Extensible Storage, because writing that modifies the model and PRD S6.1 forbids it. The window has no UI for it yet | `building` |

---

## 4. Working now

**Only what a test can prove.** Nothing here has run inside Revit, and by this
file's own rule that means none of it is verified — it is built, and green.

**The whole rule engine**, `AnonGee.extension/lib/anongee_filterrules`, and
**the window**. 183 tests:

- `values` — `parse_number` (no `re`), the unit table (mm/cm/m/ft/in and their
  squares and cubes, degrees), 13 operators, a float tolerance so
  "equals 100 m2" matches something.
- `names` — Revit's case- and whitespace-insensitive name matching.
- `rules` — `Condition`, `Rule`, `RuleSet`; JSON round trip; `problems()`;
  add / find / remove / duplicate / move.
- `store` — the machine store, the project store, atomic writes, `last_error()`,
  schema tolerance, and `load_all()` badging each rule with where it came from.

**The dual-engine gate.** `SharedCoreTests` refuses Python-3-only syntax, a
missing `from __future__ import division`, a non-ASCII literal, `re`, `csv`,
`anongee_toolkit` and Revit. Proved to bite by reintroducing each fault.

**One fault it already caught.** `Condition` silently folded an unrecognised
operator to `equals`, so a typo in a hand-edited rules file would have become a
rule quietly meaning something else. The operator is now kept and named in
`problems()`.

---

## 5. Pending scope

**Done:** the PRD, the architecture, the folder structure and the pure core.

**Next, in this order:**

1. **`revit_query.py`** — categories in the model; families and types under a
   category, correct for system *and* loadable families (FEAT-1, METHODOLOGY
   §13.3); parameters on a type with the CRIT-2 filterable flag; the four-stage
   narrowing of `ARCHITECTURE.md` §4. Thin on purpose — everything decidable is
   already above it.
2. **`revit_apply.py`** — `IsolateElementsTemporary`, `DisableTemporaryViewMode`,
   and the can-this-view-be-isolated check. Needs the two Revit behaviours
   `ARCHITECTURE.md` §6 flags as unverified: a view under a view template, and a
   view already manually isolated.
3. **`compat.py`** — the `ElementId` Int32→Int64 shim.
4. **The window** — `ui.xaml` and `script.py`, modeless per §12.8, plus
   `tests/test_filterview_ui.py` modelled on `test_autolevel_ui.py`.
5. **Ship 0.1.0** — README rewritten off "scaffold", `extension.json` to 2.1.0,
   a root changelog entry, `done-list.md` opened.

**Then:** prove CRIT-3 with a throwaway pane registered from `startup.py`, and
if it holds, the panel as 0.2.0.

**Later:** promotion off Dev.panel to Advance.panel beside
`FilterParameter.splitbutton`, once the project owner has confirmed it working
in Revit. A MAJOR extension change under the repo's own table.

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
