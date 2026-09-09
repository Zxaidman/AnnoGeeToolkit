# Filter View Manager — changelog

Semantic versioning, read from the point of view of someone using the tool:

| Part | Meaning |
| --- | --- |
| **MAJOR** | The tool behaves differently on purpose — a workflow moved, or what pressing a rule does to the model changed shape. |
| **MINOR** | A new capability. Everything already saved still works. |
| **PATCH** | A fix. Nothing new to learn. |

The version is declared once, in `script.py`'s `VERSION`. `bundle.yaml`'s
`Version:` line and the newest heading here are held to it — once the tool has
a window with a header to check, by a test, the way `tests/test_autolevel_ui.py`
holds Auto Level Manager's four copies together.

---

## 0.0.2 — 2026-09-09

Still nothing runs. What it will do is now decided and written down, and one of
the decisions came back corrected.

- **What pressing a rule does is settled: it temporarily isolates, in the active
  view only.** Saving a rule applies nothing — it adds a button to the list. So
  the tool never writes to the project: no `ParameterFilterElement`, nothing in
  the Filters list, no trace for a colleague opening the model. The alternative
  — writing real view filters — is recorded as FEAT-13 because the parameter
  flag below pays for it, not because it is wanted.
- **Any parameter may be used, with the non-filterable ones flagged.** Because a
  rule isolates rather than filtering, a parameter Revit refuses in a view filter
  still makes a perfectly good button. The flag is honest about the limit today
  and is exactly the check FEAT-13 would need later.
- **Rules live at machine level**, in
  `%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json` — the
  `cad2bim/prefs.py` pattern, so they follow the user into the next project. A
  per-project override is wanted; its location and its precedence are two open
  questions in `todo-list.md` §6, and guessing either can lose somebody's rules.
- **One answer needed correcting, and the correction is the finding.** The panel
  was asked for as *"does not need to start with Revit, only when the user
  clicks the pushbutton"*. That is right about **visibility** and wrong about
  **registration**: `RegisterDockablePane` must be called from
  `OnStartup`, before any document is open, and a pushbutton runs far too late.
  A registered pane is hidden until something calls `Show()` — so the
  requirement holds exactly as stated, and it still costs a startup component.
- **The startup component lands on IronPython, and that was already measured
  here.** pyRevit loads `startup.py` on its core engine, IronPython 2.7, where
  `lib/py3` is not on the path — `/anongee/ping` reported it from inside
  `startup.py` and it is recorded in the platform architecture spec. So the
  window and the panel cannot share a module, and the bridge's own answer
  applies unchanged: **share a folder, not a module.**
- **`PRD.md`** — what a rule is, what pressing one does, the two surfaces, where
  rules live, the seven non-negotiables, the six things it will explicitly not
  do, the staging, and what success looks like in Revit rather than in a test
  runner.
- **`ARCHITECTURE.md`** — the dual-engine constraint and what it costs, the rule
  core that both engines run, the JSON contract and its five rules, four-stage
  matching, why units are stored with the number, applying to a view, the
  dockable pane's registration-vs-visibility split, the failure model, and the
  build order.
- **`FOLDER_STRUCTURE.md`** — where each file goes and why. The rule core sits in
  `lib/`, not beside the script, because *pyRevit puts `<extension>/lib` on
  sys.path but nothing below it* and `startup.py` could never reach a package
  inside a pushbutton bundle. That is the one deviation from the house pattern
  and it is forced, not chosen. Also: what comes from `anongee_toolkit`, what
  deliberately does not, and the six files outside this tool that will need
  touching.
- **The highest-value test in the plan is named**: the core is compiled under
  Python 2.7 syntax rules. There is no IronPython on the CI machine, so an
  f-string in the core is invisible on every developer machine and shows up as a
  dockable panel that fails to load at Revit start.

### Not in this version

Everything, still. **0.1.0** is the modeless window — cascade, conditions, live
count, Apply/Clear, save — and nothing now blocks it.

---

## 0.0.1 — 2026-09-09

The bundle exists. Nothing runs.

- **The ribbon slot is real from the first commit**, so the tool is covered by
  the repository's own checks straight away rather than at the end:
  `tests/test_scripts.py` holds the `#! python3` shebang and every name the
  script reads, and `tests/test_repo_docs.py` holds the README to the folder.
- **Pressing it says so.** A placeholder that opened an empty window would look
  like a broken tool; this one names its version, says what the tool will do,
  and points at the three documents beside it. The first thing anybody presses a
  new button for is to find out what it is.
- **`METHODOLOGY.md`** — how this repository works and what this tool has to
  obey: the engine and its stripped stdlib, the persistent-engine interface
  rules, what `anongee_toolkit` already provides, the design-system rules that
  are load-blockers, the three window modes, how settings survive a session, the
  two-level versioning, and the documentation contract the tests enforce. Plus
  the constraints this tool specifically will run into — §13.
- **`todo-list.md`** — the queue, seeded. Three `CRIT` items, twelve `FEAT`
  items, and four open questions for the project owner. Nothing is specified
  yet; specification is the PRD's job.
- **Placed on `Dev.panel/col3.stack`.** Dev is where tools with no in-Revit
  confirmation live — RC Automation is there for the same reason. A new stack,
  because `Testing`, `col1` and `col2` each already hold pyRevit's maximum of
  three buttons. Promotion to Advance.panel, beside the FilterParameter tools it
  is related to, belongs to the build that is confirmed working.
- **The extension version was deliberately left at 2.0.0.** Adding a tool is a
  MINOR extension change, but this one ships no capability; bumping now would
  claim one. The bump belongs in the commit that ships 0.1.0.

### Not in this version

Everything. There is no rule model, no picker, no persistence, no window, and
no dockable panel. **0.1.0** will be the first build that applies a rule to a
view, and it is blocked on `CRIT-1` and `CRIT-2` in `todo-list.md`.
