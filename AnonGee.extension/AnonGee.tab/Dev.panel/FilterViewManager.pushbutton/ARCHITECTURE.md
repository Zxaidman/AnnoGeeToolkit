# Filter View Manager — architecture

**Status:** agreed 2026-09-09. The pure half of the rule core is **built and
tested** as of 0.0.3; the Revit half and the two surfaces are not.
**Requires:** `PRD.md` (what it must do), `METHODOLOGY.md` (the repository's
rules). `FOLDER_STRUCTURE.md` turns this into a file tree.

---

## 1. The constraint everything is built around

**Two Python engines, and they cannot see each other's code.**

The modeless window runs on **CPython 3.12** and can import `anongee_toolkit`.
The dockable panel must be registered from `startup.py`, which pyRevit loads on
its **core engine, IronPython 2.7**, where `lib/py3` is not on the path at all.

This is measured, not assumed.
`docs/specs/2026-08-22-excel-revit-platform-architecture.md` §2a records
`/anongee/ping` reporting from inside `startup.py`:

```json
"engine":  {"implementation": "IronPython", "version": "2.7.12 … on .NET 8.0.30 (64-bit)"}
"toolkit": {"importable": false, "path_entries": [], "error": "No module named anongee_toolkit"}
```

The bridge hit exactly this and settled it with one sentence, which this tool
adopts unchanged:

> **The route is a doorbell. The worker is CPython. They share a folder, not a
> module.**

For this tool the same shape reads:

> **The rules file is the contract. The window writes it, the panel reads it,
> and the engine that runs each never has to be the same one.**

---

## 2. The three pieces, and which engine each runs on

| Piece | Engine | Job | Lives at |
| --- | --- | --- | --- |
| **Rule core** | *both* — plain 2.7 **and** 3.12 | The rule model, JSON load/save, value parsing, operators, matching, and the Revit collection/isolation calls | `AnonGee.extension/lib/anongee_filterrules/` — **the pure half is built as of 0.0.3** |
| **Window** | CPython 3 | Build, preview, name and save rules. WPF, `anongee_toolkit`, `IExternalEventHandler` | `…/FilterViewManager.pushbutton/` |
| **Panel** | IronPython 2.7 | Register the pane at load, show it on request, draw the rule buttons, press one | `AnonGee.extension/startup.py` + a small module beside it |

**The rule core is the whole design decision.** Everything else follows from it.

### 2.1 Why the core is dual-engine, and what that costs

The alternative was a CPython-only core with the panel asking it to do the work
through a job file — the Bridge Listener's `UIApplication.Idling` pattern. It
was rejected: a rule button must isolate *now*, and routing a click through a
file drop and an idle tick to do something Revit can do synchronously is
latency bought for nothing.

So the core is written to run on both. The price is real and worth stating:

- **No f-strings, no `pathlib`, no type hints, no dataclasses, no `enum`** —
  nothing newer than Python 2.7. `startup.py` is already written to exactly this
  rule and says so in its own docstring.
- **No `re`, no `csv`** — the CPython engine does not ship them (§12.9.3), so
  neither half may rely on them regardless.
- **The core may not import `anongee_toolkit`.** It calls the raw Revit API
  directly.

That last one is the trade the reader will object to, so here is the arithmetic.
What `anongee_toolkit` would give this tool is
`revit/filtering.get_elements_by_categories` (the module's only function),
`revit/elements.get_family_name` and `get_type_name` (its only two), and the
`revit/units` constants. That is a handful of small functions. Paying for them
with **two implementations of the whole evaluator, on two engines, drifting
apart** is the wrong trade, and this repository has already made the same call
once — `bridge/jobs.py` duplicates `startup.py`'s path rules on purpose, and
`tests/test_bridge.py` holds the two contracts together.

**The rule adopted here:** the core owns its Revit calls. Where a helper it
grows turns out to be generally useful, it is *mirrored* into
`anongee_toolkit`, and a contract test holds the two together. It is never
imported across the engine boundary, because it cannot be.

`anongee_toolkit` is still used, heavily — by the window, for everything that is
not the rule engine: `ui/xaml`, `ui/dialogs`, `ui/forms`, `revit/transactions`,
`revit/selection`, `revit/views`, `revit/compatibility`. See
`FOLDER_STRUCTURE.md` §4.

### 2.2 Where the core lives, and why there

`AnonGee.extension/lib/anongee_filterrules/`.

A comment in `ConvertFloor.pushbutton/script.py` states the mechanism:
**"pyRevit puts `<extension>/lib` on sys.path but nothing below it."** So `lib/`
itself is reachable from *both* engines — which is exactly why
`lib/path_resolver.py` sits there and works for both — while `lib/py3/` is
CPython-only.

That makes `lib/` the only correct home for dual-engine code, and it is already
being used that way.

---

## 3. The rules file is the contract

One JSON file, machine level, the `cad2bim/prefs.py` location and rules:

```text
%APPDATA%/Zxaidman/AnonGee/BIM-Toolkit/filter_view_rules.json   (Windows/Revit)
~/.anongee/filter_view_rules.json                               (fallback/tests)
$ANONGEE_PREFS_DIR/filter_view_rules.json                       (override — this is what makes it testable)
```

And the **project store**, settled 2026-09-09 and built in 0.0.3:

```text
<the folder holding the .rvt>/AnonGee/filter_view_rules.json
```

Chosen over Revit's Extensible Storage on a point of principle rather than
convenience: **writing Extensible Storage modifies the model** and needs a
transaction, and PRD §6.1 says this tool writes nothing to the project. A file
beside the model also stays visible, editable, diffable and shareable — a
project folder is already how an office shares anything — and needs no schema
GUID that can never be changed afterwards.

One file per **folder**, not per model: a job is a folder with ARC, STR and MEP
in it, and a rule about structural columns is about the job. A model that has
never been saved has no project store, and that is the ordinary case for a new
project rather than an error.

*Workshared models:* `Document.PathName` on a local file points at the user's
own copy, not the shared central, so the caller passes the **central** path when
there is one. `project_path()` is pure and neither knows nor cares which it was
handed — which is what keeps it testable.

**There is no precedence.** Both stores are shown, each rule marked with where
it came from, and the same name in both gives two rules. Picking a winner loses
somebody's rule silently, and for a tool whose whole job is remembering things
that is the worst failure available.

```jsonc
{
  "schema": 1,
  "version": "0.1.0",              // the build that last wrote it, for support
  "rules": [
    {
      "id": "r-20260909-0001",     // stable across renames; the panel's button key
      "name": "Gypsum walls over 100 m²",
      "order": 0,
      "categories": ["Walls"],     // Revit category NAMES, not BuiltInCategory ints
      "family": "Basic Wall",      // optional; omitted means "any"
      "type": "100mm Gypsum Wall", // optional
      "match": "all",              // "all" | "any"
      "conditions": [
        {"parameter": "Area",
         "operator": "greater",
         "value": 100.0,
         "unit": "m2",             // ALWAYS recorded — see §5
         "filterable": true}       // the CRIT-2 flag, informational
      ]
    }
  ]
}
```

Five rules govern this file, and each has a scar behind it:

1. **Strings, never `ElementId`s.** `cad2bim/settings.py`'s rule: ids do not
   survive a session, let alone another project.
2. **Category names, not `BuiltInCategory` integers.** The enum's numeric values
   are not a public contract across Revit versions, and a name reads in a diff.
3. **`schema` is a statement of what a file may carry, not a gate.** Every
   reader takes what it recognises and ignores the rest, so a file written by a
   newer build still loads what an older one understands. `cad2bim/settings.py`
   §SCHEMA, verbatim.
4. **Nothing here can fail a run.** Unreadable, half-written, or newer: it reads
   as `{"rules": []}`. A failed save reports through `last_error()`.
5. **Written atomically** — temp file in the same directory, then `os.rename`.
   Revit and the panel may both be reading it; a half-written file that reads as
   "no rules" is safe but still loses the user's work for that session.

**Concurrency.** Both surfaces write the same file. The window is the only
*editor*; the panel writes at most a reorder. The panel reloads on show and when
the file's mtime changes, so a rule saved in the window appears without a
restart. Two Revit instances editing rules simultaneously is a known,
unhandled, last-writer-wins case — recorded rather than solved, because solving
it costs a lock file and nobody has asked.

---

## 4. Matching a rule

Four stages, narrowing at each, and the order is a performance decision:

```text
1. Category   FilteredElementCollector(doc, view.Id)
                .WherePasses(ElementMulticategoryFilter([...]))
                .WhereElementIsNotElementType()
2. Family     filter the collected elements by family NAME
3. Type       filter by type NAME
4. Parameters read the parameter per surviving element and compare
```

**Stages 1–3 are cheap and stage 4 is not.** Stage 4 costs a parameter read per
element, so it must run on the smallest set possible — which is why the cascade
narrows before it, and why a rule of *Walls > Area > 100 m²* with no family or
type is the expensive shape to write. Measure before optimising, but do not
design the expensive order in.

**Collect from the active view, not the document.** `FilteredElementCollector(doc,
view.Id)` returns what the view can show, which is what an isolate operates on
anyway, and on a large model it is the difference that matters.

### 4.1 Family and Type mean two different things

The cascade mixes two API shapes and a picker that assumes one shows an empty
level for the other:

- **System families** (Walls, Floors, Roofs): *"Basic Wall"* is a system family
  name reached from the **type**. There is no `Family` element to collect.
- **Loadable families** (Doors, Windows, most framing): there is a real
  `Family`, and `FamilySymbol` is the type.

The core exposes one function per level that answers correctly for both, and the
picker never has to know which it is looking at. `revit/elements.py`'s
`get_family_name()`/`get_type_name()` are the reference for what each shape
needs — read them before writing the equivalent.

### 4.2 Name matching is Revit's rule, not Python's

`"basic wall"`, `"Basic Wall"` and `"Basic  Wall"` are the same name to Revit.
`cad2bim/type_names.py` already implements this (`key()`, `find()`) and root
`task_plan.md` Phase 0.5 records the cost of getting it wrong — an `==`
comparison produced *"The name is already in use for this element type"* in a
live model. The core reuses the algorithm; being unable to *import* it across the
engine boundary is exactly the mirrored-helper case from §2.1.

Built as **`names.py`** — `key()`, `same()`, `find()`, `index()`. It turned out
to be entirely pure, so it lives in the tested half rather than in `compat.py`
as first sketched; `compat.py` is left holding only the `ElementId` width shim,
which genuinely does need Revit.

### 4.3 A rule that matches nothing

Two different outcomes, and conflating them is a bug:

- **Matched nothing** — the type exists, no element passed. Zero is a valid
  answer; say so and isolate nothing.
- **Could not resolve** — this project has no *"100mm Gypsum Wall"*. The rule is
  shown greyed, naming what it could not find. **It is never deleted or
  rewritten.** Losing a user's rule because they opened a different model is the
  worst thing this tool could do.

---

## 5. Units are stored with the number

Revit stores internally in **feet**. A rule written as *Area > 100 m²* is
`1076.39 ft²` internally, and Revit 2021+ routes unit identity through
`ForgeTypeId`.

**A rule stores the number the user typed *and* the unit they typed it in.**
Conversion happens at compare time, against the parameter's own storage. A rule
saved as a bare number is a bug waiting for the first imperial project, and it
cannot be fixed later because the intent is gone.

`revit/units.py` (`SF_TO_M2`, `FT_TO_MM`, `mm_to_ft()`, `strip_unit()`) is the
reference for the constants; the core carries its own copy for §2.1's reason.

**Parsing is hand-written** — `re` is not available. `"100"`, `"100 m2"`,
`"100 m²"`, `"100.5"`, `" 100 "` and `""` are all inputs, and this is a pure
function with no Revit in it, so it is the most testable code in the tool and
should be written test-first.

---

## 6. Applying to a view

```python
with RevitTransaction("AnonGee · Filter View Manager"):
    view.IsolateElementsTemporary(List[ElementId](ids))
```

Four things, each of which has bitten something in this repository already:

1. **A transaction is required.** Temporary isolation is a view state change.
   `try/finally` gated on `HasStarted()/HasEnded()` (§12.9.4).
2. **`List[ElementId]`, not a Python list.** A raw `[]` across the pythonnet
   bridge is a **fatal** marshalling fault, not an exception (§12.9.4).
3. **`ElementId` is Int64 on Revit 2024+.** `revit/compatibility.py` exists for
   this; the core carries the same two-line shim.
4. **Clear is `DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)`**,
   not a re-isolate of everything.

**Verify in Revit before building on it:** that `IsolateElementsTemporary`
behaves as expected in a view already under a view template, and in a view with
an existing manual isolation. Both are ordinary states in a real project and
neither is documented here from measurement.

---

## 7. The dockable panel

### 7.1 Registration and visibility are different things

The project owner's requirement — *"does not need to start with Revit, only when
user click the pushbutton"* — is satisfiable exactly as stated, but not the way
it sounds:

| | When | Where from | Cost |
| --- | --- | --- | --- |
| **Register** | Revit start, before any document | `IExternalApplication.OnStartup` — for us, `startup.py` | A GUID and a WPF control. No window, no document, no toolkit. |
| **Show** | When the pushbutton is pressed | anywhere | `DockablePane(guid).Show()` |

A pushbutton **cannot** register a pane — it runs long after `OnStartup` and
Revit refuses. So the panel costs a startup component whether or not it is
visible. That component is cheap, and it must never raise: `startup.py`'s own
docstring is blunt about why — *"a startup script that throws takes pyRevit's
load with it, and a broken bridge must never cost the user their other tools."*

**This is CRIT-3 and it is unproven.** No `IDockablePaneProvider` exists
anywhere in this repository — `Resources/Panels.xaml` ships the template and
`tests/test_scripts.py` lists the interface, and nothing has ever used either.
**Prove registration works from a pyRevit `startup.py` in the target Revit +
pyRevit version before 0.2.0 is scheduled.** If it does not, the fallback is the
modeless window pinned — which is 0.1.0, already shipped, so the floor is not
far down.

### 7.2 The three interface rules apply here too

`IDockablePaneProvider` is on `tests/test_scripts.py`'s list of Revit interfaces
— but that list exists for **Python.NET**, and on IronPython none of the three
rules apply. The provider class living in `startup.py` is therefore *simpler*
than the CPython equivalent would be. If it ever moves to CPython, all three
come back: `__namespace__`, no `__init__`, defined once per session.

### 7.3 Two shapes, one layout

Registered with `DockPosition.Top`, the pane opens as a **horizontal strip**
across the drawing area. The user can then drag it to the left or right edge,
where it becomes a **tall narrow column** like Properties. Revit gives both for
free; the layout has to survive both.

`Resources/Panels.xaml`'s `DockablePanelTemplate` and §12.4 only describe the
tall one (`MinWidth=240 / MaxWidth=360`, single column). **A design-system
reconciliation item**, and it belongs in the brand guidelines' §15.4 table, not
in this tool: either the template grows a horizontal variant, or §12.4 says
top-docked panes are exempt. Raise it when 0.2.0 is scheduled.

The content itself is a `WrapPanel` of buttons — which reflows into a row when
wide and a column when narrow without being told which it is. That is one
control doing both shapes, rather than two layouts kept in step.

---

## 8. The window

Modeless, per §12.8, and the two reference implementations
(`Dev.panel/Testing.stack/Modeless.pushbutton` and `OneFilterParameter`) are the
pattern — not a starting point to improve on.

- `Show()`, not `ShowDialog()`.
- All Revit work inside an `IExternalEventHandler.Execute()`, queued with
  `ExternalEvent.Raise()`, with a **serialized request queue** so rapid typing
  cannot swallow a button press (`OneFilterParameter`'s note).
- Handler class **defined once per session**, cached in a `sys.modules` state
  module, together with the live window reference so re-pressing the button
  activates the open window instead of stacking a second one.
- `WindowInteropHelper.Owner` anchored to Revit's main handle.
- **Plain data across the thread boundary** — an `int` id, never an `ElementId`.
- The live count is **debounced** (`ui/dialogs.DebounceTimer`), because it
  re-collects on every keystroke otherwise.

---

## 9. Failure model

| Failure | What happens |
| --- | --- |
| Rules file unreadable / half-written / newer schema | Reads as no rules. The window says so; it never raises. |
| Rules file cannot be written | The save reports through `last_error()`, in the footer status row. The rule stays in the window so it is not lost. |
| A rule's type does not exist in this project | Rule shown greyed with what it could not find. Never deleted, never rewritten. |
| A rule matches zero elements | A valid answer. Say "0 matched", isolate nothing. |
| Active view cannot be isolated (schedule, sheet) | Refused before the transaction opens, naming the view type. `view_filters._can_take_filters` is the precedent: skip and count, never fail the run. |
| Parameter missing on some matched elements | Those elements do not match. Not an error — a wall without a `Comments` value is simply not "Comments = X". |
| Pane registration fails at startup | Swallowed and **recorded to disk**, never raised — a throwing `startup.py` takes pyRevit's whole load down. The pushbutton then reports why, the way Bridge Check reads `startup.py`'s record (root `todo-list.md` BUG-5). |

---

## 10. What gets built first

1. **`rules.py` + `values.py` + `store.py`** — the pure core. No Revit, no WPF.
   Test-first; this is the part that can be *proved* before Revit sees it.
2. **`revit_query.py`** — collection, name resolution, parameter reads. Needs
   Revit, so it is thin on purpose and everything decidable lives above it.
3. **The window** — cascade, conditions, count, Apply/Clear, save. 0.1.0.
4. **Prove CRIT-3** — a dockable pane registered from `startup.py`, showing an
   empty control. One afternoon, and it decides whether 0.2.0 exists.
5. **The panel.** 0.2.0.

Step 4 comes *after* the window ships on purpose. If it fails, 0.1.0 is still a
working tool; if it were first, a failure would leave nothing.
