# Filter View Manager — how this repository works, and what this tool must obey

**Status:** research only. No tool code has been written.
**Read at:** `main` @ `860e0e5`, 2026-09-09.
**Scope:** everything below was read out of this repository, not recalled. Where
a claim rests on a Revit API behaviour rather than a file here, it says so and
is marked **unverified in this repo** — those are the ones to prove before they
are designed around.

This file exists because the next three documents (PRD, architecture, folder
structure) are only worth writing once the house rules are written down. A tool
that invents its own patterns here costs more than it delivers: the design
system, the engine, the test suite and the installer all already have opinions,
and every one of them is enforced somewhere.

---

## 1. The shape of the thing

Four layers, and a tool touches all four:

| Layer | Where | What it is |
| --- | --- | --- |
| **Ribbon** | `AnonGee.extension/AnonGee.tab/<Panel>.panel/…` | Folder-as-UI. A folder ending `.pushbutton` *is* a button. |
| **Shared library** | `AnonGee.extension/lib/py3/anongee_toolkit/` | `anongee_toolkit` — the Revit API abstraction every tool imports. Documented in its own `API.md` (1244 lines). |
| **Design system** | `AnonGee.extension/Resources/*.xaml` | Colours, typography, controls, panels, icons. Governed by `AnonGee_BIM_Tools_Brand_Guidelines.md` (v3.0). |
| **Runtime** | `AnonGee.extension/lib/py3/` | A pinned, bundled CPython 3.12 with numpy, openpyxl, ezdxf, pywin32. End users install no Python. |

Around them: `tests/` (Revit-free), `tools/` (dependency provisioning),
`installer/` (payload builder + Inno Setup), `bridge/` (the Excel↔Revit
transport).

**The rule that matters most:** nothing in `lib/py3` may be assumed to be a
stock Python. It is a *stripped* stdlib, deliberately, and §3 below is about
what that costs.

---

## 2. Where a tool lives — the bundle

pyRevit builds the ribbon by walking folders. A tool is:

```text
FilterViewManager.pushbutton/
├── bundle.yaml      # title, author, tooltip — the ribbon label and hover text
├── icon.png         # 32×32 (§7.4). icon.dark.png if the dark ribbon needs one
├── script.py        # #! python3 on line 1, or it runs on the wrong engine
├── ui.xaml          # the window, when there is one (§12.2 — never inline markup)
└── <package>/       # the tool's own logic, when it has enough to test
```

`.stack` folders group two or three buttons into a ribbon column. `.pulldown`
and `.splitbutton` nest buttons under one slot. A `.panel` holds them all, and
must be declared in `extension.json`.

**A stack takes exactly two or three buttons — never one.** Revit's
`RibbonPanel.AddStackedItems()` has overloads for two items and for three, and
none for one, so pyRevit cannot build a one-item stack: it skips it, and the
button never reaches the ribbon. There is no error anywhere; the tool is simply
not there.

This was learned the expensive way. `Dev.panel` already had three full stacks
(`Testing`, `col1`, `col2`), so 0.1.0 put this tool in a `col3.stack` of its
own — and it was **invisible in Revit** for exactly that reason. A button with
no stack-mate goes **directly on the panel**, which is what `AutoLevel` does on
Essential and `cad2bim` does on Core.

`tests/test_repo_docs.py` now refuses any `.stack` that does not hold two or
three child bundles.

Titles split over two ribbon lines with a real newline:
`title: "Filter\nView Manager"` — **double-quoted**, because unquoted YAML
leaves `\n` as two characters and the label renders with a visible backslash.
`ConvertFloor.pushbutton` is the reference.

Tooltips are two to four factual lines in the §8 voice — what it does, what it
needs selected. Some mature tools (RC Automation, cad2bim) carry a full manual
in the tooltip instead. Both are accepted; the long form is for tools whose
behaviour cannot be guessed.

---

## 3. Which engine runs it, and the traps that come with it

New scripts target **CPython 3** and say so on line 1:

```python
#! python3
```

Without that line pyRevit runs the script on **IronPython 2.7**, where
`lib/py3` is not on `sys.path` and `anongee_toolkit` does not exist. This is
not theoretical — root `todo-list.md` **BUG-9** records both bridge tools
shipping without it. One failed loudly; the other *worked*, because the
`bridge` package happened to be 2.7-compatible, and would have died on the
first job that needed openpyxl. `tests/test_scripts.py` now enforces the
shebang statically, and its docstring calls that "a working tool with a fuse in
it."

Four constraints follow from the engine, and all four are cheap to obey and
expensive to discover:

### 3.1 `re` is not available

§12.9.3: the engine ships a **partial stdlib**. Confirmed missing: **`re`** and
**`csv`**. Present: `os`, `json`, `traceback`, `tempfile`, `zipfile`, plus
numpy and openpyxl.

Every tool here that parses text hand-rolls it. `OneFilterParameter` has
`_bracket_int()` with the comment *"Replaces re.match — the `re` module is
unavailable in this CPython3 engine"*. `anongee_autolevel/textparse.py` parses
`FFL +3.500` and `TERRACE +14'-6"` without a regex, on purpose.
`tests/test_autolevel_ui.py`, `test_rc_automation_ui.py` and
`test_rc_automation_structural.py` each assert `re` is not imported.

**Direct consequence for this tool.** A rule like *Area above 100 m²* is a
parsed value. Parsing `"100"`, `"100 m²"`, `"100.5"`, `"1,00,000"` has to be
written by hand and unit-tested. Budget for it; do not discover it.

### 3.2 The engine is persistent, and it re-runs the script

pyRevit keeps one CPython interpreter alive for the whole Revit session and
re-executes `script.py` on **every** button press. `sys.modules`, the CLR
AppDomain and any emitted CLR types outlive the press. Three rules
(§12.8.7.1), all enforced by `tests/test_scripts.py`:

| # | Rule | What happens without it |
| --- | --- | --- |
| 1 | `__namespace__ = "AnonGee"` on any class subclassing a Revit/.NET interface | `TypeError: interface takes exactly one argument` |
| 2 | **No `__init__`** on that class — reset state after construction instead | the same `TypeError`, even with rule 1 |
| 3 | Define the class **once per session**, cached in a `sys.modules` module | `Duplicate type name within an assembly` — on the **second** press |

The session-state module is also where the live window reference goes, so
re-pressing the button activates the open window instead of stacking a second
one. `Dev.panel/Testing.stack/Modeless.pushbutton/script.py` is the trimmed
reference implementation; `OneFilterParameter` is the full one.

### 3.3 Revit objects cannot cross threads

A modeless window runs WPF on its own thread. `Element`, `Document`,
`Parameter` — none of them may be touched from it. Everything crossing the
boundary is plain data: `OneFilterParameter`'s note records that its
`PreviewItem` had to store an **int** id rather than an `ElementId` for exactly
this reason. Work goes onto Revit's thread through an `IExternalEventHandler`,
and results come back through the window's `Dispatcher`.

### 3.4 Marshalling and transactions

§12.9.4, all confirmed-good and all learned the hard way:

- Marshal Python lists to `List[T]` before handing them to the Revit API. A raw
  `[]` is a **fatal** marshalling fault, not an exception.
- `try/finally` around every `Transaction`, gated on
  `if t.HasStarted() and not t.HasEnded(): t.RollBack()`.
- All logic inside `run()`/`main()` — module-scope work runs at load and leaks
  into the persistent engine.
- A module-level guard at the entry point, so a logic error reports instead of
  leaving the engine half-initialised.
- Never import `pyrevit.*` from CPython 3 (§12.8.4). `Autodesk.*` and
  `System.*` only.

---

## 4. The shared library — reuse before writing

`anongee_toolkit` exists so that no tool re-solves document access,
transactions, parameter I/O or XAML loading. `API.md` is the reference. What
matters to this tool:

| Module | What it gives | Use it for |
| --- | --- | --- |
| `revit/application` | `get_app()`, `get_current_uidoc()`, `get_current_doc()` | never touch `pyrevit.revit` — it crashes CPython 3 in event callbacks |
| `revit/transactions` | `RevitTransaction`, `RevitTransactionGroup`, `SuppressWarningsPreprocessor` | commit on clean exit, roll back on exception, one undo step |
| `revit/parameters` | `get_parameter`, `get_parameter_value`, `set_parameter_value` | handles all four `StorageType` variants |
| `revit/filtering` | `get_elements_by_categories(category_names, view_id, doc)` | **the seed of this tool's collector** — currently the only function in the module |
| `revit/elements` | `get_family_name`, `get_type_name` | **the seed of the Family and Type levels of the cascade** |
| `revit/views` | `get_eligible_views()`, `get_view_label()`, `ALLOWED_VIEW_TYPES` | which views a filter may be applied to at all |
| `revit/units` | `FT_TO_MM`, `SF_TO_M2`, `CF_TO_M3`, `m_to_mm()`, `mm_to_ft()`, `strip_unit()` | Revit stores feet; a rule is written in millimetres and m² |
| `revit/compatibility` | `create_element_id()`, `get_element_id_value()` | Revit 2024 moved `ElementId` from Int32 to Int64 |
| `revit/selection` | `get_selected_elements()`, `set_selection()` | "Select in Revit" from a rule's matches |
| `ui/xaml` | `load_xaml()`, `fill_combo()`, `select_combo_containing()` | replaces the hand-rolled `FileStream`/`XamlReader` block |
| `ui/dialogs` | `WpfDialogBase`, `DebounceTimer` | debounce is what keeps a live preview from re-collecting on every keystroke |
| `ui/forms` | `alert()`, `error()`, `info()`, `confirm()` | native .NET dialogs — `pyrevit.forms` crashes CPython 3 |

**And one that is nearly this tool already:**
`anongee_toolkit/cad2bim/builders/view_filters.py` creates
`ParameterFilterElement`s, finds an existing one by Revit's own
case-insensitive name rule, builds `OverrideGraphicSettings`, and applies them
across open views — skipping and counting views that cannot take filters rather
than failing the run. It is 190 lines and it is the closest working precedent
in the repository. Read it before designing anything.

**Import style**, all three supported:

```python
from anongee_toolkit import get_current_doc, RevitTransaction      # flat
from anongee_toolkit.revit import get_current_doc                   # subpackage
from anongee_toolkit.revit.application import get_current_doc       # deep
```

Library code prefers the subpackage form; scripts use the flat one.

---

## 5. The design system

Six dictionaries under `AnonGee.extension/Resources/`: `Colors.xaml`,
`Typography.xaml`, `Controls.xaml`, `Panels.xaml`, `Icons.xaml`, merged by
`AnonGeeTheme.xaml`.

- **Reference tokens by key**, never a hex literal outside `Colors.xaml`:
  `{DynamicResource BrushVividRed}`. The palette is Vivid Red `#E02020`,
  Charcoal Black `#141414`, Pure White, Off White `#F4F4F6`, Mid Grey `#6B7280`.
- **Merge the theme by absolute path** at load time (strategy 1, §12.3). Some
  older tools paste the dictionaries inline because `pack://application` URIs
  do not resolve inside Revit's sandbox; where that is forced, the inline block
  must be a **verbatim** copy. Any divergence is a defect.
- **Templates exist — use them.** `AnonGeeWindowTemplate` (standard tool
  window), `AnonGeeDialogTemplate` (fixed-width modal), `DockablePanelTemplate`
  (`IDockablePaneProvider`, single column, `MinWidth=240 / MaxWidth=360`).
- The **header** carries the tool title only. The live count and status badges
  go in the **footer** status row (`x:Name="LiveCount"`). Not the header.

### 5.1 The XAML rules that are actually load-blockers

§12.7, distilled from `OneFilterParameter` v3.0 and enforced statically by
`tests/test_autolevel_ui.py` — which is the template for any new UI test here:

- **Never `{StaticResource}` on a root `Window` attribute.** `XamlReader`
  resolves `Window` attributes *before* `Window.Resources` is parsed.
- **A literal starting with `{` must be escaped `{}`**, or it is read as a
  markup extension and `XamlReader.Load` throws — the window simply never opens.
- Every `{StaticResource}` names a key that exists; no `x:Key` twice; every
  `Style`'s `TargetType` matches the element; every trigger `TargetName` exists
  in its own template.
- Every `{Binding}` path has a matching `__slots__` entry on the row class.
  Editable columns bind `TwoWay`, display-only columns `OneWay`.
- A `DataGrid` checkbox binds the row's own flag — a Python `bool` does not
  drive the tick reliably (§12.7.Q).
- A `ScrollBar` style must cover **both** orientations (§12.7.P).
- Every interactive control carries a tooltip.
- Every `FindName` in Python resolves, and every `x:Name` in XAML is used.

That last pair is worth stating plainly: the test suite refuses both a lookup
with no control and a control with no lookup. Dead names are treated as defects.

---

## 6. Modal, modeless, dockable — the three window modes

**Modal** (`ShowDialog()`) blocks Revit. Fine for a pick-and-go tool.

**Modeless** (`Show()`) leaves Revit interactive, and is what this tool needs —
a rule button is pressed *while* working in a view. The pattern is validated
(§12.8.6, July 2026) and ships in two reference implementations. It is not a
`ShowDialog()`→`Show()` swap: the §3.2 and §3.3 rules above are its price, and
a naive swap crashes.

**Dockable** (`IDockablePaneProvider`) is the "Properties / Project Browser"
placement the idea asks for — and it is a different kind of problem:

- `tests/test_scripts.py` already lists `IDockablePaneProvider` among the
  interfaces the three Python.NET rules apply to, so the repo anticipates it.
- `Resources/Panels.xaml` already ships `DockablePanelTemplate`.
- **But nothing in this repository registers one.** Grepping the whole tree
  finds the template, the guideline sentence and the test constant — no
  provider, no registration.

**The constraint that decides the architecture** (Revit API behaviour,
**unverified in this repo**): a dockable pane must be registered through
`IExternalApplication.OnStartup` — before any document is open. A pushbutton
runs far too late. The only startup hook this extension has is
`AnonGee.extension/startup.py`, and its own docstring records that pyRevit runs
startup scripts on the **core engine, which is IronPython**, and therefore
cannot import the CPython 3 toolkit in `lib/py3`. That file calls the same
question "a fork in the architecture worth knowing about before stage 1 rather
than during it."

So: **the dockable panel is a startup-time, IronPython-adjacent problem, not a
pushbutton problem.** It is separable from the rule engine and should be
scheduled separately. The pushbutton can ship, and be useful, first.

---

## 7. Remembering things between sessions

The idea's requirement — rules that "carry over Revit session and projects" —
already has a house pattern, in two halves:

**`cad2bim/prefs.py`** — settings that outlive the session, one flat JSON file:

```text
%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/cad2bim.json   (Windows/Revit)
~/.anongee/cad2bim.json                               (tests/fallback)
```

Overridable by `ANONGEE_PREFS_DIR`, which is what makes it testable. It
migrates a legacy path once, best-effort. Its stated rule: *"Nothing here can
fail a run — an unreadable or half-written file reads as 'no preferences', and
a save that cannot write says so through `last_error()` instead of raising into
the middle of a build."*

**`cad2bim/settings.py`** — a whole dialog snapshotted as a dict, with a
`SCHEMA` integer and two rules that are exactly this tool's problem:

> a combo is stored by its **LABEL, never by ElementId** — ids do not survive a
> session, let alone another project, and a label that no longer exists simply
> leaves that combo alone.

> anything the dialog computes for itself is never captured, so a reload cannot
> overwrite what the current drawing says.

**This is the single most important precedent for Filter View Manager.** A
saved rule must name `"Basic Wall"` and `"100mm Gypsum Wall"` as **strings**,
never as `ElementId`s, or it is worthless the moment it is opened in another
project — which is the whole point of the feature. The schema integer is how
old files keep loading: every reader takes what it recognises and ignores the
rest.

---

## 8. Versioning

Two levels, on purpose, both semantic (`MAJOR.MINOR.PATCH`).

**The extension** carries one version in `extension.json`, recorded in the root
`CHANGELOG.md`. Currently `2.0.0`. Adding a tool is a **MINOR** extension
change; reorganising the tab is **MAJOR** (which is what took it from `1.26.1`
to `2.0.0`).

**A tool** carries its own version and its own `CHANGELOG.md` beside its
`bundle.yaml` when "which build am I running" becomes a real question. Read
from the user's side:

| Part | For a tool |
| --- | --- |
| MAJOR | It behaves differently on purpose — a workflow moved, or what it writes to the model changed shape. |
| MINOR | A new capability. Everything you already did still works. |
| PATCH | A fix. Nothing new to learn. |

**One place holds the number.** `anongee_autolevel/__init__.py` declares
`VERSION`, and `tests/test_autolevel_ui.py` asserts it agrees with
`bundle.yaml`'s `Version:` line, the newest `CHANGELOG.md` heading, and the
badge in the window header. They cannot drift because a test says so.

This tool starts at **0.0.1** — the bundle exists, nothing runs. **0.1.0** will
be the first build that applies a rule to a view.

---

## 9. The documentation contract, and what enforces it

Documentation here is not optional prose; parts of it are tested.

`tests/test_repo_docs.py` holds the README to the ribbon:

- **every `.pushbutton` on disk must be named in `README.md`** — the test exists
  because nine tools once shipped undocumented, and nothing connected the
  folder to the prose;
- every `.panel` on disk must appear in the README **and** be declared in
  `extension.json`;
- the root `CHANGELOG.md` must lead with the version `extension.json` states,
  and its version headings must be newest-first.

That is why creating this bundle required one row in the README's Dev Panel
table. It is the contract, not doc sprawl — and it is the only root file this
scaffold touches.

`tests/test_scripts.py` holds every script to two things without running any of
them: the `#! python3` shebang, and no name that is read and never bound (the
bug that caught Bridge Check was `os` used in two functions and never imported).

Beside the tool, the house pattern is four files — RC Automation is the fullest
worked example:

| File | What belongs in it |
| --- | --- |
| `CHANGELOG.md` | what each version changed, newest first, in the §8 voice |
| `todo-list.md` | **the queue** — every item with an ID (`CRIT-1`, `BUG-3`, `FEAT-7`) and a phase (`pending` / `building` / `testing` / `superseded` / `done`) |
| `done-list.md` | what reached `done`, what confirmed it, and **what it cost including the wrong turns** |
| `METHODOLOGY.md` | this file — not a house convention, added because this tool starts from a blank folder |

Two standing rules read out of RC Automation's own `todo-list.md`:

> **Anything new is recorded here first.** A requirement, a bug, an idea — it
> gets an ID in this file before it is built, argued about, or written into any
> other document.

> **Verified means one thing here:** the project owner ran it in Revit and the
> report or the screenshot says so. A green test suite is not verification —
> every bug that reached a model passed the suite on the way there.

**Nothing is deleted to make a list look shorter.** A superseded item stays,
marked, with what replaced it.

---

## 10. Testing

The split is the point: **the thinking parts run without Revit.**

`anongee_autolevel` states it outright — only `compat` and `revit_ops` import
Autodesk namespaces; `textparse`, `naming`, `planner`, `stackview`, `settings`
are plain Python and are covered by `tests/test_autolevel.py`. The same shape
appears in `cad2bim` (`settings.py`, `prefs.py`, `type_names.py`, all the
`geom/` and `classify/` modules) and in `rc_automation`.

Two tiers:

- **Unit** — `tests/test_*.py`, run per file
  (`python3 tests/test_repo_docs.py`). Both `test_repo_docs.py` and
  `test_scripts.py` are green at the base commit of this branch.
- **Regression** — `cad2bim/tests/run_regressions.py`, a golden-baseline corpus
  (~3 min). Baselines are re-blessed **on purpose, in the commit that moves
  them**, never silently.

Note: `python3 -m unittest discover -s tests` fails — `tests/` has no
`__init__.py`. Run the files directly.

**What this means for Filter View Manager:** the rule model, the rule→match
evaluation, the JSON persistence and the value parsing must all be plain Python
in a package beside `script.py`, importing nothing from `Autodesk.*`. Only the
collector and the view application touch Revit. That is not a preference — it
is the only way any of it gets tested before it reaches a model.

---

## 11. Voice

§8, and it is consistent across every document here:

- Plain, factual, lower-case-honest. No marketing.
- Say what happened and what it means. An error message names the cause and
  what to do about it.
- Documents record **what it cost**, including the wrong turns — that is
  treated as the valuable part.
- Never claim more than was measured. "Verified" means someone ran it in Revit.

Match it. A document here that reads like release copy is out of place.

---

## 12. Where this tool lands, and why

**Ribbon slot:** `Dev.panel/FilterViewManager.pushbutton`.

- **Dev.panel**, because Dev is where "generators, the design system, and the
  reference patterns new tools are built from" live, and because a tool with no
  in-Revit confirmation does not belong on Essential or Advance yet. RC
  Automation is on Dev for the same reason. Promotion to **Advance.panel** —
  next to `FilterParameter.splitbutton`, which is its nearest relative — is the
  natural move once it is confirmed working, and that is a MAJOR extension
  change under the repo's own table.
- **Directly on the panel, not in a stack.** `Testing`, `col1` and `col2` each
  already hold three, and a stack of one cannot be built at all (§2) — it was
  in a `col3.stack` for one build and did not appear in Revit.

**What was deliberately not done in this scaffold:**

- `extension.json` version untouched. The tool ships nothing; bumping the
  extension to `2.1.0` would claim a capability that does not exist. The bump
  belongs in the commit that ships `0.1.0`.
- No root `CHANGELOG.md` entry yet, for the same reason.
- No `ui.xaml`. There is nothing to draw until the PRD settles what a rule is.

---

## 13. What this tool will run into

Open questions and hard constraints, found while reading. These are the input
to the PRD, not conclusions.

### 13.1 "Show only that filter element on view" is two different features

Revit offers two mechanisms and they behave differently in every way that
matters (**unverified in this repo** — Revit API behaviour):

| | Temporary isolation | View filter |
| --- | --- | --- |
| API | `View.IsolateElementsTemporary(ids)` | `ParameterFilterElement` + `View.AddFilter` / `SetFilterVisibility` |
| Survives save/close | no | yes |
| Prints | no — isolation is a view-session state | yes |
| Reversed by | Revit's own *Reset Temporary Hide/Isolate* | removing the filter |
| Leaves behind | nothing | a named filter in the project's Filters list |
| Works on any parameter | yes — it is just a set of ids | **no** — see 13.2 |

The idea says the *rules* should carry across sessions and projects. It does
**not** say the *applied state* should. Those are separable and the PRD must
separate them, because a tool that quietly writes permanent filters into a
client's project is a different product from one that isolates while you work.

### 13.2 Not every parameter can drive a native view filter

Revit exposes `ParameterFilterUtilities.GetFilterableParametersInCommon(doc,
categoryIds)` — the set of parameters a `ParameterFilterElement` may rule on
for a given category set, and it is smaller than "every parameter on the
element" (**unverified in this repo**).

If the rule engine allows any parameter, the native-view-filter route is
sometimes impossible and the tool must fall back to isolate-by-id. If it allows
only filterable ones, the picker is honest but narrower than the idea implies.
**This is the single biggest fork in the design** and it should be settled
before the UI is drawn, not after.

### 13.3 Family and Type mean two different things

The cascade *Walls → Basic Wall → 100mm Gypsum Wall* mixes two API shapes:

- **System families** (walls, floors, roofs, pipes): "Basic Wall" is a system
  family name reached from the *type*, not a `Family` element. There is no
  `Family` to collect.
- **Loadable families** (doors, windows, structural framing, most annotation):
  there is a real `Family`, and `FamilySymbol` is the type.

`revit/elements.py` already has `get_family_name()` and `get_type_name()` — read
what they actually do for each shape before the cascade is specified, because a
picker that assumes one shape will show an empty level for the other.

### 13.4 Units

Revit stores internally in feet. A rule written as *Area above 100 m²* is
`1076.39 ft²` internally, and Revit 2021+ routes unit identity through
`ForgeTypeId`. `revit/units.py` has `SF_TO_M2`, `FT_TO_MM`, `mm_to_ft()` and
`strip_unit()`. A rule saved as a number with no unit recorded is a bug waiting
for the first imperial project.

### 13.5 Saved rules must not carry ElementIds

Already argued in §7, repeated here because it is the requirement that makes
the feature worth building: rules travel between projects, so every reference
in a saved rule is a **string**, matched by Revit's own case- and
whitespace-insensitive name rule. `cad2bim/type_names.py` already implements
that matching (`key()`, `find()`, `resolve_type()`), and root `task_plan.md`
Phase 0.5 records what it cost to learn — an `==` comparison on a type name
produced *"The name is already in use for this element type"* in a live model.

### 13.6 Scale

A rule that matches on a parameter value cannot be answered by a
`FilteredElementCollector` alone — it needs a parameter read per element. On a
large model that is the performance risk, and `ui/dialogs.DebounceTimer` exists
because live previews here have hit it before. Measure before optimising, but
design so the collector narrows by category and type **first**.

### 13.7 A view that cannot take a filter

Schedules, sheets, and template-controlled views reject filters.
`view_filters.py` already handles this: `_can_take_filters(view)` skips and
counts rather than failing the run. Reuse the behaviour and the reporting.

---

## 14. Drift noticed in passing

Not this tool's to fix, recorded so it is not lost:

1. **Root `CHANGELOG.md` links RC Automation to a path that does not exist** —
   `AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md`. The tool
   moved into `col2.stack` during the 2.0.0 ribbon reorganisation and the link
   did not follow. `test_repo_docs.py` checks that the README links the root
   changelog, but nothing checks that per-tool changelog links resolve.
2. **`Dev.panel/bundle.yaml`'s `layout:` is stale** — it lists `CPython3
   engine`, `Modeless` and `Brand Guidelines`, which are all inside
   `Testing.stack`. Since the reorganisation the panel's direct children are
   the three stacks, so the layout directive names nothing at panel level.
3. **`tests/` cannot be discovered** — `python3 -m unittest discover -s tests`
   fails on a missing `__init__.py`. Every test file runs directly, so this has
   never bitten, but there is no single command that runs the whole suite.

---

## 15. The short version

1. `#! python3` on line 1. Always.
2. No `re`. No `csv`. No `pyrevit.*`.
3. Interface subclasses: `__namespace__`, no `__init__`, defined once per
   session in a `sys.modules` cache.
4. Plain data across the thread boundary — ints, not `ElementId`s.
5. Reuse `anongee_toolkit`. Read `view_filters.py` first; it is half this tool.
6. Tokens by key, templates by name, and the §12.7 XAML rules are load-blockers.
7. Saved state is strings and a schema integer, in `%APPDATA%`, and can never
   fail a run.
8. One place holds the version, and a test says so.
9. Logic that can run without Revit, does — that is the only part that gets
   tested before a model sees it.
10. Record it in `todo-list.md` before building it. "Verified" means the owner
    ran it in Revit.
