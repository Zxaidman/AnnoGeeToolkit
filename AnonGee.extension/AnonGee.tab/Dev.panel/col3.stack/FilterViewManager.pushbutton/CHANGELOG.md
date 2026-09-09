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

## 0.1.0 - 2026-09-09

The window. The first build a person would call the tool: build a rule, name
it, save it, press it, and only what it matches is left in the view.

**Pressing a rule temporarily isolates its matches in the active view, and
writes nothing to the project.** No `ParameterFilterElement`, nothing in
Manage > Filters, no trace for a colleague opening the model. It lasts the
session, does not print, and Clear puts the view back -- the same thing Revit's
own Reset Temporary Hide/Isolate does.

### The window

- **Saved rules on the left**, with New, Duplicate, Delete, Move up and Move
  down. Selecting one loads it into the editor. Delete asks first, and only
  that rule goes.
- **The cascade on the right.** Categories are a searchable ticked list -- the
  ticks survive a search, because the search filters what is *shown*, not what
  is *chosen*. Family and Type are optional; leaving them on "any" is how "all
  the walls" is said.
- **Conditions are added one at a time** and listed, rather than edited inside
  a grid. That is a deliberate scope choice: in-grid combo columns are where
  §12.7's worst traps live (checkbox coercion, edit-commit cancellation,
  per-row ItemsSource), and none of them can happen to a list.
- **The footer carries all the transient state** -- the badge, the status line
  and the live count -- because §12.6 says the header holds the title only.
- **Count, Select, Apply, Clear.** Count changes nothing; Select pushes the
  matches into Revit's selection; Apply isolates; Clear restores.
- **Every control has a tooltip**, and a test refuses one that does not.

### Modeless, done the way this repository already proved

- The handler carries `__namespace__`, has **no `__init__`**, and is defined
  **once per Revit session** behind a `sys.modules` cache. All three fail at
  instantiation or on the *second* press, and a test checks each.
- The same module holds the live window, so pressing the ribbon button again
  **activates the open window** instead of stacking a second one.
- Requests cross to Revit's thread as plain data -- a rule travels as the dict
  it saves as, and comes back as ints and strings. A Revit object cannot cross
  to the WPF thread, and a test refuses a `serve()` that returns anything but a
  dict.
- Results come back through the window's `Dispatcher`, which is the only place
  a control is written.

### Two traps avoided on purpose

- **The category tick is the native `ListBoxItem.IsSelected`, never a Python
  bool.** §12.7.Q: a Python bool does not coerce in this engine -- the tick
  looks permanently disabled and TwoWay write-back is unreliable. Python
  mirrors `SelectedItems`, not the other way round.
- **Lists are rebuilt behind a flag, not by detaching the handler.**
  `event -= self._handler` may remove nothing at all: `self._handler` builds a
  new bound method on every attribute access, so pythonnet can wrap a different
  delegate. A flag cannot be got wrong, and a test refuses `SelectionChanged -=`.

### The theme is the sanctioned copy, spliced rather than written

`ui.xaml` carries the inline theme **verbatim** from
`Dev.panel/Testing.stack/Modeless.pushbutton/ui.xaml` (§12.3 strategy 2), copied
by script so it cannot drift. **This tool adds no styles of its own** -- the
implicit `ListBoxItem` and `ScrollBar` styles already theme the three lists, and
everything else is a key that block defines. A test refuses any resource key
that is not in the sanctioned theme.

### Tests

`tests/test_filterview_ui.py`, 28 static checks, modelled on
`test_autolevel_ui.py`. Every `{StaticResource}` resolves, no `x:Key` twice, no
`{StaticResource}` on the root `Window`, no literal mistaken for markup, every
`Style` matches its element, every trigger targets its own template, every
binding path has a `__slots__` entry, **every `FindName` resolves and every
`x:Name` is looked up** (36 and 36, exactly), every control has a tooltip, no
`re`, no pyRevit, and the version agrees across four files.

Proved to bite by reintroducing five faults: a resource key that is not there,
a removed tooltip, a binding with no slot, a lookup with no control, and an
`__init__` on the handler.

### Four faults found while reviewing this build

- **`event -= self._handler` was used to suppress selection callbacks** during
  a rebuild. See above -- it may remove nothing.
- **The family and type of a loaded rule were stored and never restored.** The
  cascade is fetched on Revit's thread, so they cannot be selected until it
  comes back; they are now held and applied when it does, matched Revit's way.
- **`clear` was parsed as though it carried a rule**, which it does not.
- **A guard was inserted above a docstring**, which demotes the docstring to a
  dead expression.

### Not in this version

The dockable panel. It needs a startup-time component and is its own milestone,
blocked on proving `CRIT-3` in Revit. Writing the **project** rule store is
FEAT-14 -- project rules are read and badged, and Save writes the machine store.

## 0.0.4 - 2026-09-09

The Revit half of the rule engine, and a probe button that runs it against a
real model. 155 tests. The tool itself -- the modeless window -- is still 0.1.0.

- **`revit_query`** -- what a rule can be built from and what it matches.
  Categories, families, types, parameters, and the four-stage narrowing:
  category through a view-scoped `FilteredElementCollector`, then family, then
  type, then **only the parameters the rule's conditions name**. Reading every
  parameter of every element is the difference between a live count and a
  frozen window on a real model.
- **Both family shapes answer through one accessor.** A system family (Basic
  Wall, Floor) has no `Family` element at all and its name comes from the
  type's `FamilyName`; a loadable family has a real `Family` and the same
  property returns it. The picker never has to know which it is looking at, and
  never shows an empty level for one of them.
- **`revit_apply`** -- `IsolateElementsTemporary` on the active view, and
  `DisableTemporaryViewMode` to put it back. The only module in the package
  that opens a transaction, gated `try/finally` per S12.9.4. A view that cannot
  be isolated is refused **before** the transaction opens, naming the view
  type. Isolating nothing is refused too: Revit would leave the view showing
  an empty sheet, which looks exactly like a broken tool.
- **`compat`** -- the `ElementId` Int32/Int64 change, `Element.Name`, and
  `List[ElementId]`, which is not optional: a raw Python list across the
  pythonnet bridge is a **fatal** marshalling fault, not an exception.
- **The split is now enforced, not just described.** The Revit half may not
  import `values` -- the comparison engine -- so no decision can drift into the
  half no test on this machine can reach. And no Revit module may carry more
  *statements* than the largest tested module, counted through the AST so
  documentation is free and code is not.
- **`ElementRow` and `select`** are the pure half of the collector, so "what
  does this rule actually match" is proved before a model ever sees it. A row
  is an int id and two names, because a Revit object cannot cross to the WPF
  thread (S12.8.7.2) and an int can.

### The button is a probe now, not a placeholder

It reads the model, builds a rule from what it finds, and will isolate it. It
writes nothing to the project. It exists because four things cannot be answered
anywhere but in Revit, and every one of them is load-bearing:

- whether `GetFilterableParametersInCommon` returns what CRIT-2 assumes;
- whether the cascade is right for a system family as well as a loadable one;
- whether `IsolateElementsTemporary` behaves in a view under a view template,
  and in one already isolated by hand;
- whether rules saved here survive a restart and open in another project.

The report is written to a file **and** printed to the pyRevit console. Root
`todo-list.md` BUG-5 is why: a dialog has to be retyped, a file can be pasted,
and three rounds of findings arrived as screenshots of a panel that said
nothing.

### Three things found while reviewing this build

- `families()` built a collector it never used -- dead work on every call.
- `revit_apply` imported `ViewType` and then kept a fake reference alive to
  stop it looking unused. The import is gone; view types are compared as text,
  which also means a name missing from an older or newer Revit never matches
  rather than raising at import.
- `categories()` also required `AllowsBoundParameters`, which was a guess
  dressed as a rule: it would have hidden any model category that holds
  elements but takes no bound parameters, and a rule isolates those fine.

### Not in this version

The window. **0.1.0** is the cascade picker, the live count, Apply/Clear and
save -- the first build a person would call the tool.

## 0.0.3 - 2026-09-09

The rule engine, built test-first. 131 tests, none of which need Revit. There is
still no window, so nothing is on the ribbon but the scaffold.

- **`lib/anongee_filterrules`** -- the four modules that decide everything about
  a rule that can be decided without a model open: `values` (parsing, units,
  operators), `names` (Revit's idea of the same name), `rules` (`Condition`,
  `Rule`, `RuleSet`), `store` (the JSON files).
- **It is in `lib/`, not beside the script**, which is the one deliberate
  deviation from the house pattern and is forced rather than chosen: the panel
  is registered from `startup.py` on IronPython 2.7, and *pyRevit puts
  `<extension>/lib` on sys.path but nothing below it*, so `lib/` is the only
  folder both engines can import from.
- **The dual-engine contract is enforced statically**, because there is no
  IronPython on the machine that runs the suite: no Python-3-only syntax, no
  annotations, no keyword-only arguments, no starred assignment targets,
  `from __future__ import division` in every module, no `unicode_literals`,
  pure ASCII throughout, no `re`, no `csv`, no `anongee_toolkit`, no Revit.
  An f-string here would otherwise be invisible everywhere except Revit's
  startup, where it would show up as a panel that fails to load.
- **The project store is decided: a JSON file in the model's own folder**,
  `<folder>/AnonGee/filter_view_rules.json`, one per folder rather than per
  model -- a job is a folder with ARC, STR and MEP in it, and a rule about
  columns is about the job. Revit's Extensible Storage was rejected on a point
  of principle rather than convenience: writing it **modifies the model** and
  needs a transaction, and PRD S6.1 says this tool writes nothing to the
  project. A file also stays visible, editable, diffable and shareable, and
  needs no schema GUID that can never be changed afterwards.
  *Workshared models:* `Document.PathName` points at the user's local copy, so
  the caller passes the central path when there is one. `project_path` is pure
  and neither knows nor cares which it was handed.
- **There is no precedence between the two stores.** Both are shown, each rule
  marked with where it came from, and the same name in both gives two rules.
  Picking a winner loses somebody's rule silently, which for a tool whose whole
  job is remembering things is the worst failure available.
- **A value is stored in the unit it was typed in**, and converted at compare
  time. Storing the converted number would lose which unit the rule was written
  in, and that cannot be recovered afterwards.
- **A comma in a value box is refused rather than guessed at.** `1,5` is
  one-and-a-half in half of Europe and fifteen everywhere else.
- **A missing parameter never matches a real comparison.** A wall with no
  Comments is not `Comments = X`, and it is not `Comments != X` either -- it has
  no Comments to disagree with. Only `is empty` says yes.
- **Writing is atomic** -- temp file in the same directory, then rename -- so a
  save that fails costs the new rule rather than every old one, and a reader
  never sees a half-written file.

### One fault the tests found

`Condition` silently folded an unrecognised operator to `equals`. A typo in a
hand-edited rules file would have become a rule that quietly meant something
else, and `problems()` would have had nothing to report. The operator is now
kept as given and named in `problems()`; `matches()` already answered `False`
for anything it could not evaluate, so keeping it costs nothing. The `match`
mode still folds to `all`, and the code says why the two differ.

### Not in this version

The Revit half -- `revit_query`, `revit_apply` -- and the window. **0.1.0** is
the first build that applies a rule to a view.

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
