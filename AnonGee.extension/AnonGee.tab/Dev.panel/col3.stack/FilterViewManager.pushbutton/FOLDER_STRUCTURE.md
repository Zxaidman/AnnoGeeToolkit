# Filter View Manager — folder structure

**Status:** 2026-09-09. The bundle and the **pure half of the rule core** exist
and are tested; everything marked *(planned)* does not.
**Follows from:** `ARCHITECTURE.md` §2 — the rule core is dual-engine, so where
a file sits decides which engine can read it. That is the whole reason this
document exists separately.

---

## 1. The three places code goes

```text
AnonGee.extension/
│
├── lib/                                    ← BOTH engines can import from here
│   ├── path_resolver.py                        (existing — proves the point)
│   └── anongee_filterrules/                THE RULE CORE
│       ├── __init__.py                     ✅  VERSION lives here
│       ├── values.py                       ✅  parsing, operators, units — no Revit
│       ├── names.py                        ✅  Revit's "same name" — no Revit
│       ├── rules.py                        ✅  Condition, Rule, RuleSet — no Revit
│       ├── store.py                        ✅  the two JSON files — no Revit
│       ├── revit_query.py                  (planned)  collection + name resolution
│       ├── revit_apply.py                  (planned)  isolate / clear
│       └── compat.py                       (planned)  the ElementId width shim
│
├── lib/py3/anongee_toolkit/                ← CPython 3 ONLY (the shared toolkit)
│       …unchanged. Used by the window, never by the core.
│
├── startup.py                              ← IronPython 2.7, runs at pyRevit load
│       + register the dockable pane (planned, 0.2.0)
│
├── lib/anongee_filterpane/                 (planned, 0.2.0)  THE PANEL
│       ├── __init__.py
│       ├── provider.py                         IDockablePaneProvider
│       └── pane.xaml                           the button strip
│
└── AnonGee.tab/Dev.panel/col3.stack/
    └── FilterViewManager.pushbutton/       ← CPython 3, the window
        ├── bundle.yaml                         ✅ exists
        ├── icon.png                            ✅ exists
        ├── script.py                           ✅ exists (scaffold)
        ├── METHODOLOGY.md                      ✅ exists
        ├── PRD.md                              ✅ exists
        ├── ARCHITECTURE.md                     ✅ exists
        ├── FOLDER_STRUCTURE.md                 ✅ this file
        ├── CHANGELOG.md                        ✅ exists
        ├── todo-list.md                        ✅ exists
        ├── done-list.md                        (planned — on the first `done`)
        └── ui.xaml                             (planned, 0.1.0)
```

### Why the core is not inside the pushbutton folder

Every other tool here keeps its package beside its script — `anongee_autolevel/`
sits inside `AutoLevel.pushbutton/`, and that is the house pattern.

**This tool cannot.** *"pyRevit puts `<extension>/lib` on sys.path but nothing
below it"* (`ConvertFloor.pushbutton/script.py`), and a `.pushbutton` folder is
not on any engine's path at all — a script reaches its own package because
pyRevit runs the script *from* that folder. `startup.py` never runs from there,
so it could not import a package living inside a pushbutton bundle.

Since the panel and the window must share one rule engine
(`ARCHITECTURE.md` §2.1), the engine has to live somewhere both can reach, and
`lib/` is the only such place. **The deviation from the house pattern is forced
by the dual-engine requirement, and it is the only deviation.**

### Why the panel is not in the pushbutton folder either

Same reason, from the other side: `startup.py` imports it, and `startup.py` runs
on IronPython from the extension root.

---

## 2. The core, module by module

Everything in `lib/anongee_filterrules/` obeys three rules: **plain Python 2.7
*and* 3.12**, **no `re` / no `csv`**, **no `anongee_toolkit` import**.

| Module | Revit? | What it holds |
| --- | --- | --- |
| `__init__.py` | no | `VERSION`. The one place the number is written. |
| `values.py` | **no** ✅ | Hand-written parsing (`"100 m²"` → `100.0, "m2"`), 13 operators, the unit table, and the float tolerance. The most testable file in the tool. |
| `names.py` | **no** ✅ | `key()`, `same()`, `find()`, `index()` — Revit's case- and whitespace-insensitive name matching. Turned out entirely pure, so it lives here rather than in `compat.py` as first sketched. |
| `rules.py` | **no** ✅ | `Condition`, `Rule`, `RuleSet` — plain objects with `to_dict()` / `from_dict()`. Ordering, renaming, duplication, id generation, `problems()`. |
| `store.py` | **no** ✅ | Both stores, the `ANONGEE_PREFS_DIR` override, atomic write, `last_error()`, schema tolerance, and `load_all()` merging machine and project with each rule badged. Modelled on `cad2bim/prefs.py`. |
| `revit_query.py` | **yes** | Categories in the model; families and types under a category; parameters on a type; the four-stage narrowing of `ARCHITECTURE.md` §4; the CRIT-2 filterable flag. |
| `revit_apply.py` | **yes** | `IsolateElementsTemporary`, `DisableTemporaryViewMode`, and the "can this view be isolated at all" check. |
| `compat.py` | **yes** | `ElementId` Int32→Int64 (Revit 2024). The name matching that was going to live here turned out to need no Revit at all and became `names.py`. |

**The Revit/no-Revit line is the test boundary.** `values`, `names`, `rules` and
`store` are four-fifths of the thinking and run on any machine — which is the whole
point of `METHODOLOGY.md` §10, and the reason `anongee_autolevel` states outright
that *"only `compat` and `revit_ops` import Autodesk namespaces."*

---

## 3. Tests

```text
tests/
├── test_filterrules.py       ✅  131 tests — values, names, rules, store, and the
│                                 dual-engine contract. No Revit, no WPF.
└── test_filterview_ui.py     (planned)  ui.xaml + script.py, statically
```

`test_filterrules.py` covers the pure core: round-tripping a rule through JSON,
every operator, `"100 m²"` and its awkward siblings, unit conversion, an
unreadable file reading as no rules, a newer `schema` still loading, and an
atomic save that survives being interrupted.

`test_filterview_ui.py` is `tests/test_autolevel_ui.py` applied to this tool —
that file is the template and it is worth copying rather than re-deriving. It
holds: every `FindName` resolves and every `x:Name` is used, no literal mistaken
for a markup extension, no `{StaticResource}` on the root `Window`, every
resource key exists, every interactive control has a tooltip, no `re`, no
pyRevit import, and **the version agrees across `__init__.py`, `bundle.yaml`,
`CHANGELOG.md` and the window header**.

One test this tool needs that no existing one has, and it is built:
**`SharedCoreTests`**, the dual-engine contract checked statically. No
Python-3-only syntax, no annotations, no keyword-only arguments, no starred
assignment targets, `from __future__ import division` everywhere, no
`unicode_literals`, pure ASCII, no `re`, no `csv`, no `anongee_toolkit`, no
Revit — plus the four-copies-of-one-version check.

There is no IronPython on the machine that runs the suite, so these are the only
thing standing between a 3-only construct and a dockable panel that fails to
load at Revit start. Proved to bite by reintroducing each fault: an f-string, a
non-ASCII literal, a toolkit import and a dropped `division` each fail it by
name.

---

## 4. What comes from `anongee_toolkit`

The window is a normal CPython tool and uses the toolkit fully. The core does
not use it at all (`ARCHITECTURE.md` §2.1).

| Used by the window | For |
| --- | --- |
| `ui/xaml.load_xaml` | loading `ui.xaml` — replaces the hand-rolled `FileStream`/`XamlReader` block |
| `ui/xaml.fill_combo`, `select_combo_containing` | the cascade combos |
| `ui/dialogs.WpfDialogBase`, `DebounceTimer` | the window base, and the debounce the live count needs |
| `ui/forms.alert`, `error`, `confirm` | native dialogs — `pyrevit.forms` crashes CPython 3 |
| `revit/application.get_current_doc`, `get_current_uidoc` | document access without `pyrevit.revit` |
| `revit/transactions.RevitTransaction` | the isolate transaction, rollback on exception |
| `revit/selection.set_selection` | FEAT-9, "Select in Revit" |
| `revit/views.get_eligible_views`, `get_view_label` | FEAT-11, applying across several views |
| `revit/compatibility` | `ElementId` width, in the window's own code |

| Deliberately **not** used by the core | Why | Instead |
| --- | --- | --- |
| `revit/filtering.get_elements_by_categories` | CPython-only path | `revit_query.py`'s own collector — it needs view-scoped collection and four-stage narrowing anyway |
| `revit/elements.get_family_name`, `get_type_name` | CPython-only path | `revit_query.py`, handling system and loadable families explicitly (§4.1) |
| `revit/units` constants | CPython-only path | `values.py` carries its own, with a contract test |
| `cad2bim/type_names.key/find` | CPython-only path | `compat.py`, same algorithm |

### 4.1 The mirrored-helper rule

Where the core grows a helper that is generally useful, it is **mirrored** into
`anongee_toolkit` and a contract test holds the two together. It is never
imported across the engine boundary, because it cannot be.

This is not a new idea here. `bridge/jobs.py` duplicates `startup.py`'s path
rules for exactly this reason, says so in a comment — *"Duplication is
deliberate: startup.py must remain IronPython 2.7 compatible and cannot import
the CPython toolkit"* — and `tests/test_bridge.py` holds the two contracts
together. The same comment and the same kind of test belong on any helper
mirrored here.

**What should NOT move into `anongee_toolkit`:** the rule model, the store, the
operators. They are this tool's domain, used by one tool, and a shared library
that accumulates one tool's vocabulary stops being a library.

**What might, later:** the view-isolation helpers in `revit_apply.py`, and
"can this view take a filter" — `cad2bim/builders/view_filters.py` already has
its own `_can_take_filters()`, so that one is *already* duplicated once and is
the strongest candidate for promotion.

---

## 5. Files outside the tool that will need touching

Named now so they are not a surprise, and so a reviewer can see the blast radius:

| File | When | Why |
| --- | --- | --- |
| `README.md` | already done | `tests/test_repo_docs.py` requires every `.pushbutton` to be documented. The row currently says *scaffold*; it must be rewritten when 0.1.0 ships. |
| `extension.json` | 0.1.0 | Adding a working tool is a **MINOR** extension change: `2.0.0` → `2.1.0`. Deliberately not touched yet — the scaffold ships no capability. |
| `CHANGELOG.md` (root) | 0.1.0 | Must lead with `extension.json`'s version, and gains a row in the per-tool version table. *(Note: that table's RC Automation link is already stale — `METHODOLOGY.md` §14.1.)* |
| `startup.py` | 0.2.0 | Pane registration. **It must never raise** — a throwing startup script takes pyRevit's whole load with it. |
| `AnonGee_BIM_Tools_Brand_Guidelines.md` | 0.2.0 | §12.4 and `DockablePanelTemplate` only describe a tall left/right pane; a top-docked strip is a new shape (`ARCHITECTURE.md` §7.3). Belongs in §15.4's reconciliation table. |
| `installer/build_payload.py` | 0.2.0 | Check whether a new top-level `lib/` package needs declaring in the payload rules. Read it before assuming it does not. |

---

## 6. Build order

Mirrors `ARCHITECTURE.md` §10, as a file checklist:

| # | Build | Files | Provable without Revit? |
| --- | --- | --- | --- |
| 1 | ✅ The pure core | `values.py`, `names.py`, `rules.py`, `store.py`, `tests/test_filterrules.py` | **done** — 131 tests, written first |
| 2 | ✅ The 2.7 syntax gate | `SharedCoreTests` | **done** — and proved to bite |
| 3 | The Revit half of the core | `revit_query.py`, `revit_apply.py`, `compat.py` | no — thin on purpose |
| 4 | The window | `ui.xaml`, `script.py`, `tests/test_filterview_ui.py` | statically, yes |
| 5 | **Ship 0.1.0** | `README.md`, `extension.json`, root `CHANGELOG.md`, `done-list.md` | — |
| 6 | Prove CRIT-3 | a throwaway pane registered from `startup.py` | no — one afternoon in Revit, and it decides whether 0.2.0 exists |
| 7 | The panel | `anongee_filterpane/`, `startup.py` | no |
| 8 | **Ship 0.2.0** | brand guidelines §15.4, payload rules | — |

Steps 1 and 2 are the ones worth insisting on. Everything after them is
ordinary; those two are what make the rest testable at all.
