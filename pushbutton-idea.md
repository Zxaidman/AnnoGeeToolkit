# Pushbutton Ideas

Running log of pushbutton concepts for the AnonGee toolkit, one entry per idea, newest on top.

---

## 2026-09-12 15:39 UTC

**Idea name:** Parameter Migrator — batch, many-to-many parameter value moves driven by a reusable, save/load mapping table

**Potential:**
Every firm-wide shared parameter file revision, every consultant handover with its own parameter naming, and every BIM standard change mid-project (a client's COBie/data-drop spec landing after modelling has already started, or the model simply outgrowing a legacy text parameter that should have been a real shared one) produces the same job: values sitting in parameter A need to end up in parameter B, across hundreds of elements, and then A needs clearing so nobody edits a now-dead field by mistake. Today that's either a manual per-element Type Properties edit, or — the best this toolkit currently offers — `Parameter Combine.pushbutton`, whose `TargetParamCombo` (`Parameter Combine.pushbutton/script.py:197`) is a single `ComboBox` with one `SelectedIndex`: it writes into exactly **one** target parameter per run (confirmed at `script.py:623-625`, which errors "Please select a target parameter" if none is chosen), so migrating 20 parameters after a shared-parameter-file change means reconfiguring scope, categories and formula 20 separate times. The gap shows up again one layer over: `ConvertFloor.pushbutton`'s own README documents that parameters are carried over "matched by BuiltInParameter → shared GUID → name; anything without a counterpart in the target category is listed by name in the report" — i.e. every conversion already produces a list of elements now missing a value because the old and new parameter names don't line up, and nothing in the repo closes that list back up in bulk; the same gap is inherited by the proposed `Convert Column-Wall.pushbutton` idea above, which documents the identical "unmatched ones listed by name" behaviour. On the market, this is sold as one feature of paid whole-project data-management add-ins (Ideate BIMLink's parameter-copy dialogs, BIM One/Naviate's parameter tools) that charge per seat for exactly this one operation; nothing free does a template-driven, many-pairs-at-once move with a reusable mapping profile.

**Description:**
`Parameter Migrator.pushbutton` (new tool in `Advance.panel`, sibling to `Parameter Combine.pushbutton`) runs in one window:

1. **Build the mapping** — add rows of `Source Parameter → Target Parameter`, each row scoped to its own category set (reusing the same Categories tab pattern `MultiFilterParameter.pushbutton` already ships: scope = whole model / active view / selection, tick categories, live element count) and an explicit **Instance** or **Type** parameter mode, a **Copy** or **Move** direction (Move clears the source after a successful write), and an on-conflict rule (**Skip if target already has a value** / **Overwrite**). Rows can be typed by hand, or the whole table can be imported from a two-column-plus-flags Excel workbook — the fast path for a client-supplied rename schedule or a firm's shared-parameter-file diff that already exists as a spreadsheet.
2. **Preview grid** — one row per (element, mapping): current source value, current target value, and the resolved action — **will write**, **skipped (target occupied)**, **skipped (source blank)**, or **blocked (unit/type mismatch)** — tick to confirm, blocked rows pre-unticked and un-tickable, same posture `ConvertFloor.pushbutton`'s checklist already uses.
3. **Execute** — one `RevitTransaction` per mapping row (`anongee_toolkit.revit.transactions.RevitTransaction`, the same wrapper already proven as the engine behind `operations/bulk_rename.py` and `operations/bulk_delete.py`, i.e. `Bulk Rename.pulldown` / `Bulk Delete.pulldown`), each element inside the row read/written through `anongee_toolkit.revit.parameters.get_parameter_value` / `set_parameter_value` — so a bad mapping definition rolls back only its own row, not rows already applied successfully.
4. **Save the profile** — the exact mapping table (source/target pairs, scope, mode, direction, conflict rule) saves as a small JSON "migration profile," reusable next project without re-building the table — the shared-parameter-file scenario is firm-wide, not project-specific, so the same profile runs again the next time the standard changes.
5. **Report** — a result table (migrated / skipped-occupied / skipped-blank / blocked, per mapping row and per element) exportable to Excel via the same `openpyxl` path `Export Schedule.pushbutton` and `BBS Generator.pushbutton` already use (confirmed present in both scripts), giving a handover-ready audit trail of exactly what moved where.

**Implementation:**
- Core read/write goes through `anongee_toolkit.revit.parameters.get_parameter_value(..., as_string=False)` / `set_parameter_value` directly — that module already handles all four `StorageType`s and the instance-then-type fallback, but today it's only reached internally via `anongee_toolkit/utils/helpers.py`; no pushbutton script currently imports it (checked: no `AnonGee.tab/**/script.py` references `revit.parameters`), so this would be the first tool to put it to direct, user-facing bulk use.
- Numeric/unit handling reuses `anongee_toolkit.revit.units` (`strip_unit`, `mm_to_ft`, `ft_to_mm`) — already the engine behind every `structural/*` module RC Automation depends on — so a legacy text parameter storing `"230 mm"` can migrate cleanly into a real Length parameter, and a mismatch between an unparseable text value and a numeric target is what trips the "blocked (unit/type mismatch)" preview row rather than a silent bad write.
- Category/scope picking reuses `anongee_toolkit.revit.filtering.get_elements_by_categories`, the same helper already behind the Categories tab in `MultiFilterParameter.pushbutton`.
- Transaction wrapper is `anongee_toolkit.revit.transactions.RevitTransactionGroup` + one `RevitTransaction` per mapping row — not a new pattern, but the first time it is reused by name outside `operations/bulk_rename.py` / `operations/bulk_delete.py`.
- Mapping-table Excel import/export and the migration-profile JSON both sit alongside `script.py`, mirroring `slab_convert_config.json`'s "override by config, not code" shape.
- Same modeless window shell (`anongee_toolkit.ui.hostwnd` / `progressbar` / `checklist` / `theme`) every other multi-step tool in the repo already runs on, so the UI behaves consistently with `ConvertFloor.pushbutton` and `MultiFilterParameter.pushbutton`.
- `bundle.yaml` / `README.md` / `CHANGELOG.md` layout following the root README's documented convention for versioned tools, since — like `AutoLevel.pushbutton` — its mapping vocabulary (conflict rules, unit handling) is expected to keep growing.

**Future update:**
- Feed the "unmatched, listed by name" report `ConvertFloor.pushbutton` (and the proposed `Convert Column-Wall.pushbutton`) already produces straight into this tool as a pre-filled mapping table, so a conversion's parameter gaps close in the very next click instead of a separately remembered chore.
- Many-to-one migration (several legacy parameters folding into one canonical target, last-non-blank-wins or first-non-blank-wins) for the case where a firm's standard consolidates duplicate fields, complementing rather than duplicating `Parameter Combine.pushbutton`'s formula-based combination.
- A "diff mode" that re-runs a saved profile against a model months later and reports only what's changed since — useful when a migration profile is applied repeatedly across a rolling multi-phase project rather than once.
- Cross-project batch mode: point the tool at a folder of project files (or a list open in one Revit session) and apply one saved profile to all of them in sequence, for firm-wide parameter standard rollouts.

---

## 2026-09-12 10:39 UTC

**Idea name:** Warning Auditor — categorize, explain and batch-resolve Revit's own warning log, with a jump-to-element action for everything it can't safely fix

**Potential:**
Every model that survives more than a few weeks of team modelling accumulates a warning list that nobody reads until handover forces someone to: "Room is not in a properly enclosed region," "Elements are joined but do not intersect," "Highly used" duplicate-Mark warnings on rebar and framing, identical instances stacked at the same point after a copy/paste-align mistake. Revit's own **Manage → Review Warnings** dialog dumps every one of these into one flat, unsearchable, ungrouped list with no batch action at all — you click each row, "Show," look at it, close, next — so most teams either ignore the list until a coordination review flags it or burn an afternoon at handover clicking through 200+ rows by hand. This repo already fought exactly one instance of the pain this causes blind: `todo-list.md`'s own `BUG-22`/`BUG-23` record chasing a "duplicate-Mark" warning down manually in `RC Automation.pushbutton`'s column sync, the same failure mode this tool would have caught in seconds as a named, countable category instead of a build-log entry. Every tool in this repo that touches Revit's failure-suppression API (`ConvertFloor.pushbutton`, `AutoLevel.pushbutton`, `RC Automation.pushbutton`, `FramewinToBIM.pushbutton`) uses `IFailuresPreprocessor` only to *swallow* warnings during its own transaction — none of them ever calls `Document.GetWarnings()` to look at the model's standing list, and no such module exists anywhere under `anongee_toolkit`. On the market, this exact capability — read the warning log, group it, explain it, fix what's safe to fix automatically — exists only bundled as one feature among dozens inside paid whole-model BIM-QA suites (the kind of thing sold alongside clash detection and model-health dashboards); nothing free does this one job on its own for a modeler who just wants their warning count down before a Friday upload.

**Description:**
`Warning Auditor.pushbutton` (new tool in `Essential.panel/Bulk Tool.stack`, alongside `Bulk Delete.pulldown` — this is a cleanup tool in the same family) runs in one window:

1. **Scan** — calls `doc.GetWarnings()` once, groups every `FailureMessage` by its `FailureDefinitionId` GUID, and resolves each GUID to a human category via a lookup table shipped with the tool (Revit doesn't expose a readable name for most of its own warning types through the API — only the pre-formatted description string, which the table is keyed against as a fallback for anything not in the GUID map). Results show as one row per category: warning text, instance count, and a severity tag (**auto-fixable** vs **report-only**).
2. **Preview checklist** (`anongee_toolkit.ui.hostwnd` + `progressbar` + `checklist`, the same shell `ConvertFloor.pushbutton` and `AutoLevel.pushbutton` already run on) — auto-fixable categories are ticked by default per `warnings_config.json`, report-only categories are shown unticked and un-tickable, each with a **Locate** action per row that isolates the failing elements in the active view (`Selection.SetElementIds` + `ShowElements`) so a modeler jumps straight to the problem instead of hunting through Revit's own dialog one click at a time.
3. **Fix** — for v1's three auto-fixable categories: (a) **exact-duplicate instances at the same location** (same category + type + placement point) are collapsed to one, keeping the lower ElementId unless the config says otherwise; (b) **duplicate `Mark` values within a category** are resolved by appending a configurable numeric suffix to every collision but the first — the identical failure `RC Automation · BUG-22/23` hit and fixed by hand; (c) **"joined but do not intersect"** pairs are unjoined and rejoined, reusing the exact refresh routine `JoinPriority.pushbutton` already implements for its own "refresh edge-to-edge joins" option. One `TransactionGroup`, one `Transaction` per category, so a bad fix in one category rolls back without touching the others.
4. **Report** — a result table (per category: found / fixed / skipped / still-flagged) exportable via the same `openpyxl` path `Export Schedule.pushbutton` and `BBS Generator.pushbutton` already use, giving a QA sign-off artifact that says the warning count *and* what specifically changed to get there — the same audit trail `ConvertFloor.pushbutton`'s geometry-delta report gives for conversions.

**Implementation:**
- New `anongee_toolkit.revit.warnings` module: `doc.GetWarnings()` → group-by-GUID, a GUID→category lookup table (with a text-match fallback for unmapped GUIDs across Revit versions), and one fix function per auto-fixable category — kept separate from any one button's `script.py`, the same separation `anongee_toolkit.revit.geometry`/`transactions` already give `ConvertFloor.pushbutton`.
- Duplicate-instance and duplicate-Mark detection use `FilteredElementCollector` + a dict keyed on (category, type, location) or (category, Mark) respectively — no geometry-intersection code needed, unlike the Sleeve Coordinator idea above.
- Join refresh calls into `JoinPriority.pushbutton`'s existing unjoin/rejoin helper rather than reimplementing it, so the two tools can't drift on what "refresh a join" means.
- `warnings_config.json` alongside `script.py`, mirroring `slab_convert_config.json`'s shape: which categories default-ticked for auto-fix, the Mark-suffix format, and which ElementId is kept on a duplicate-instance collapse — safe defaults ship with everything but duplicate-Mark and exact-duplicate-instance off, since join-refresh has a wider blast radius on a real model.
- Report export reuses the `openpyxl` write path already proven in `Export Schedule.pushbutton`/`BBS Generator.pushbutton` — no new dependency.
- Sits in `Essential.panel/Bulk Tool.stack/` next to `Bulk Delete.pulldown`, following the same `bundle.yaml`/`README.md`/`CHANGELOG.md` layout the root README documents for versioned tools, since — like `AutoLevel.pushbutton` — its category coverage is expected to keep growing.

**Future update:**
- Fold in the "type bloat" health-check the Type Matrix Generator idea above proposes as a future update, so one "Model Health" report covers duplicate types and standing warnings together.
- Trend tracking: append each scan's category counts (timestamp + username) to a small CSV/Excel log, so a team lead can see whether a modeler's warning count is trending down over the week rather than only ever seeing a single snapshot.
- Firm-specific fix rules loaded from `warnings_config.json` without touching code — e.g. a different Mark-collision naming convention per discipline — the same override-by-config posture `slab_convert_config.json` and the proposed `sleeve_config.json` already use.
- Extend the auto-fixable set once these three are proven in production: snapping near-miss room-separation boundaries closed, and collapsing coincident line-based elements (detail lines, grid extents) reported as overlapping.

---

## 2026-09-12 05:39 UTC

**Idea name:** Sleeve & Opening Coordinator — MEP-clash-driven structural opening placement, sizing rules and blocked-zone reporting

**Potential:**
Every RCC project with MEP in the model or linked in hits the same weekly grind: a clash report (Navisworks export, or the linked MEP model itself) names 40–300 pipe/duct/conduit crossings through beams, walls, slabs and footings, and a modeler works through them one by one — measure the pipe/duct diameter and angle, check it against the beam's depth and the code's max-opening-to-depth ratio, check it isn't inside a column strip or too close to a support, place a generic opening or sleeve family at the right host/location/rotation, and tag it back to the clash ID for the MEP team to trace. Fifteen to forty crossings an hour by hand is optimistic once beam-depth and edge-distance checks are done properly instead of eyeballed, and a missed edge-distance check is exactly the kind of thing that surfaces as a site RFI months later. Every existing tool in the repo that touches structural elements (`ConvertFloor.pushbutton`, `RC Automation.pushbutton`, `RoundElementDist.pushbutton`) works host-by-host on elements already selected or already scoped by category — none of them read a second, MEP-side model and turn its crossings into structural openings; that geometry-intersection step doesn't exist anywhere in `anongee_toolkit` yet (`revit/geometry.py` has none, and there's no `sleeve`/`opening` module under `structural/`). On the market, this exact workflow is sold as a paid module inside larger BIM-coordination suites (Naviate/Symetri's openings tool, BIMOne's sleeve manager) — nothing free does clash-in, sized-and-code-checked-opening-out for Revit natively.

**Description:**
`Sleeve Coordinator.pushbutton` (new tool in `Essential.panel/StrucBIM.stack`, sibling to `Convert Slab.pushbutton` and `RoundElementDist.pushbutton`) runs in one window:

1. **Load crossings** — either import a Navisworks clash report (CSV/XML export, matched by element GUID/UniqueId back to the host Revit model) or scan directly: pick a linked MEP model (or a category set in the same model), pick the structural host categories (Structural Framing, Walls, Floors, Foundations), and the tool geometrically intersects MEP curve-based elements (pipes, ducts, conduits, cable trays) against host solids to build the same crossing list itself, one row per penetration.
2. **Resolve & size** — per crossing, works out opening shape (circular for pipe/conduit/round duct, rectangular for rectangular duct/tray) and size from the MEP element's diameter/width-height plus a configurable clearance allowance; checks it against per-category rules (max opening size as a fraction of beam depth/width, minimum edge distance from any column/support face or from another opening, no penetration inside a defined column-strip/shear-wall-boundary zone) — same shape as `ConvertFloor.pushbutton`'s pre-flight plan: every row resolves to **place** / **blocked** with the specific rule it failed.
3. Preview checklist (`anongee_toolkit.ui.hostwnd` + `progressbar`, same shell `AutoLevel.pushbutton` and `Convert Slab.pushbutton` already use): tick rows to place, blocked rows pre-unticked with the reason shown, each row tagged with the source clash ID for traceability.
4. **Place** — creates (or updates, if a sleeve at that clash ID already exists) a host-based opening/sleeve family instance per confirmed row, sets its size/rotation/host parameters and a "Clash Ref" instance parameter back to the originating clash ID; one `TransactionGroup`, one `Transaction` per element, same rollback-per-element posture as `Convert Slab.pushbutton`.
5. **Report** — result table (placed / blocked / updated / removed-because-crossing-no-longer-exists-on-rerun) exportable to Excel via the same `openpyxl` path `Export Schedule.pushbutton` and `BBS Generator.pushbutton` already use, so the MEP team gets back exactly the list they need to close their clash report against.

**Implementation:**
- New `anongee_toolkit.structural.openings` module: crossing detection (`Solid`/`Curve` intersection via `Autodesk.Revit.DB.BooleanOperationsUtils` or bounding-box-then-exact-solid test against each MEP curve swept as a thin solid), sizing/rule evaluation, and opening-family placement, following the same host-parameter-matching convention (`BuiltInParameter` → shared GUID → name) `ConvertFloor.pushbutton` uses for its own parameter carry-over.
- Reuses `anongee_toolkit.revit.geometry` for the low-level intersection/bounding-box helpers rather than duplicating them inline, and `anongee_toolkit.revit.transactions` for the per-element rollback pattern already proven there.
- Clash-report import: a thin CSV/XML reader matching Navisworks' export columns (test-name, item1/item2 GUIDs, clash point) to Revit elements via `UniqueId`; falls back to the direct-scan mode when no report is supplied, so the tool works even for teams that don't run Navisworks.
- Sizing/edge-distance rule set lives in a `sleeve_config.json` alongside `script.py`, mirroring `slab_convert_config.json`'s shape — per-category max-opening-ratio, min-edge-distance, clearance allowance, all overridable per project/firm standard.
- Opening family itself: ships one parametric round + one rectangular generic-model-based-opening family (or a face-based void-cutting family, matching whatever the firm's existing opening family already is, if one exists in the extension's family library) with type parameters for diameter/width/height and an instance "Clash Ref" text parameter for traceability.
- Excel report reuses the `openpyxl` write path already proven in `Export Schedule.pushbutton` / `BBS Generator.pushbutton` — no new dependency.
- `bundle.yaml` / `README.md` / `CHANGELOG.md` layout following the root README's documented convention for versioned StrucBIM tools.

**Future update:**
- Re-run mode that diffs against the last placed set: crossings that moved get the sleeve relocated, crossings that vanished (pipe re-routed) get the orphaned sleeve flagged for removal instead of silently left behind.
- Feed blocked rows (opening too big for the beam, or inside a shear-wall boundary) straight into a structural-engineer review queue, cross-referenced by the same "Clash Ref" id, so a redesign request is one export away instead of a re-explained email.
- Extend past MEP crossings to structural-vs-structural coordination: a duct penetrating both a beam and the slab it frames into, reconciling the two openings into one that satisfies both hosts' rules.
- Multi-linked-model support (structural host model with two or more linked MEP disciplines — plumbing, HVAC, electrical — scanned in one pass), each discipline's crossings tagged separately in the report.

---

## 2026-09-12 00:38 UTC

**Idea name:** Type Matrix Generator — Excel-driven bulk type creation, parameter sync and duplicate-type detection, across system families and loadable families

**Potential:**
Every structural revision that adds a new column/beam/wall size, or a schedule handed over by the engineer as "here are the 18 column sizes for this project," turns into the single most repetitive click-chain a BIM modeler does: open Type Properties, Duplicate, rename by hand, retype 3–6 dimension parameters, close, repeat — 2–4 minutes per type, 18 types is an hour of pure clicking, and a mistyped dimension on type 14 of 18 is invisible until a clash or a quantity take-off surfaces it. The toolkit already has a `type_name_mode` "convention" matcher baked into `ConvertFloor.pushbutton` and an Excel round-trip (`openpyxl`) proven in `Export Schedule.pushbutton` / `BBS Generator.pushbutton`, but nothing turns those two proven pieces into a general type factory — the closest thing, `BIMGeneration.pushbutton`'s "auto-sized type duplicates," is a hidden internal step of one INP-import workflow, not a tool a modeler can point at an arbitrary family and a spreadsheet. Revit's own answer, type catalogs, only works for loadable families that ship a `.txt` catalog and cannot touch system families (Structural Column, Structural Framing, Wall, Floor, Duct, Pipe) at all — which is exactly where a structural team's type churn actually happens. Paid market tools (e.g. Case/Ideate-style "batch type creator" add-ins) do the create-from-spreadsheet half for a fee; none of them add the other half this idea includes for free: scanning the project for types that are already duplicates of each other in every parameter but name, which is the silent bloat that makes a family's type list unusable a year into a project.

**Description:**
`Type Matrix Generator.pushbutton` (new `TypeTools.stack` in `Advance.panel`, alongside `Parameter Combine.pushbutton`) runs in three modes from one window:

1. **Generate from matrix** — pick a category + family (any loaded family, system or component), pick a base type to duplicate from, then load a CSV/XLSX where each row is a new type: a name column (or name-template tokens: `{b}x{d}`, `{Prefix}-{Index:03}`) plus one column per parameter to set (dimensions, material, structural usage, cost code, comments — anything writable on that family). Live preview grid resolves every row to "will create" / "already exists, will update" / "blocked" (missing required parameter, invalid value, name collision) before anything runs.
2. **Harvest to matrix** — the reverse: pick a category/family, tick which parameters matter, and export every existing type as a spreadsheet row — the fast way to hand an engineer "here is every column type in the model today" or to seed the input for mode 1 when duplicating a size series.
3. **Duplicate-type finder** — scan a category (or the whole model) for types whose full parameter set matches another type in the same family bar name, surface them as merge candidates with a usage count (how many instances use each), and — on confirm — repoint every instance of the duplicate to the kept type via `ChangeTypeId` before deleting the redundant type, same "what's lost, confirm per row" gate the conversion tools already use.

**Implementation:**
- Excel read/write via the `openpyxl` path already vendored for `Export Schedule.pushbutton` / `BBS Generator.pushbutton` — no new dependency.
- Row → type resolution: `Element.Duplicate` (or `ElementType.Duplicate`) for the create path, then set each mapped parameter by `BuiltInParameter` → shared GUID → name, exactly the matching order `ConvertFloor.pushbutton` already uses for its own parameter carry-over, so a name typo in the sheet falls back the same predictable way instead of silently no-op'ing.
- Name-template tokens reuse the same small `re`-based token formatter proposed for the Universal Renamer idea below (`{b}`, `{d}`, `{Index:03}`, a regex capture from an existing name) — if that tool lands first, this one imports its formatter instead of re-implementing it.
- Duplicate-type finder: compare each type's full writable-parameter dict (value + unit) pairwise within a family; `Element.GetDependentElements` / `FilteredElementCollector` filtered by `ElementId` gives the instance count and the instance list to repoint with `doc.Regenerate()` + `ChangeTypeId` inside the same per-element transaction-rollback pattern `ConvertFloor.pushbutton` uses.
- One preview grid + Generate/Report-only toggle shared across all three modes, same modeless-window shell (`anongee_toolkit.ui.hostwnd` / `progressbar` / `theme`) `AutoLevel.pushbutton` already runs on, so the window behaves consistently with the rest of the toolkit.
- Sits in a new `TypeTools.stack` in `Advance.panel` next to `Parameter Combine.pushbutton` (its natural sibling — one sets instance parameter values, this sets type parameter values and creates the types themselves); own `bundle.yaml` tooltip and `CHANGELOG.md` since, like `AutoLevel`, it is a tool that will keep growing new source categories.

**Future update:**
- Two-way live sync mode: re-import the same sheet after an engineer edits it and diff against current model types, so a revised design table updates existing types in place instead of only creating new ones.
- Cross-project type library: save a matrix + base-family pairing as a firm-standard "type set" (e.g. "IS 456 column sizes 230–900mm"), reusable project to project without re-authoring the sheet.
- Extend the duplicate-type finder into a background/report-only health-check mode runnable on a schedule, surfaced next to the model's other cleanup tools (`Bulk Delete.pulldown`) as a periodic "type bloat" report.
- Feed the harvested matrix straight into `BBS Generator.pushbutton`'s member/diameter filters, so a rebar schedule and a type-dimension schedule stay traceable to the same source spreadsheet.

---

## 2026-09-11 15:39 UTC

**Idea name:** Convert Column ⇄ Wall — cross-category recreate for structural columns and shear/RC walls

**Potential:**
Mid-project structural revisions routinely flip vertical elements between the two systems a BIM modeler has zero built-in tooling to bridge: a lift core or stair shaft redesigned from a column grid into shear walls, a party/boundary wall that a revised scheme turns into a column line, or an architect's RFI that swaps a stub wall for a column so a door can open past it. Today that's manual: note the location, height, offsets, phase, structural flag and hosted rebar of every element, delete it, hand-place the replacement, retype every parameter, and re-tag rebar and joins — 15–30 minutes per element, with hosted reinforcement and join order silently lost if the modeler forgets to redo them. `Convert Slab` already proved the team will invest in solving exactly this class of problem for Floor ⇄ Foundation; this is the same problem one category pair over, on elements that carry far more downstream dependents (rebar cages, joins to beams/slabs, tags) per element than a slab does. It is squarely in the productivity bracket the team already funds, it is a direct sibling of a tool already shipped, and there is no free (or, as far as public listings show, even paid) Revit add-in that does a *bidirectional*, dependent-preserving Column ⇄ Wall recreate — the paid category-swap tools on the market handle system-family-to-system-family swaps (wall type to wall type) or rely on Revit's own Type Selector, which cannot cross `OST_StructuralColumns` ⇄ `OST_Walls` at all.

**Description:**
`Convert Column-Wall.pushbutton` (sibling to `Convert Slab.pushbutton` in `StrucBIM.stack`) converts selected Structural Columns to Structural (or Basic) Walls, and selected Walls back to Structural Columns, on a pre-selection or an interactive pick, in plan, 3D, section or elevation:

1. Reads the pre-selection, or prompts a pick filtered to the relevant category (columns when going →Wall, structural/basic walls when going →Column).
2. Builds a plan per element:
   - **Column → Wall:** the column's plan footprint (rectangular or the sketch of a non-rectangular profile) resolves to a wall location **line** (the long axis, or a user-chosen axis for a square column) and a **thickness** (the other side); base level + base/top offsets carry across as the wall's own; a column whose footprint isn't reducible to one straight line + thickness (an L/T-shaped or round column with no dominant axis) is flagged and blocked, same as `Convert Slab` blocks a non-horizontal sketch.
   - **Wall → Column:** a straight wall's length and thickness resolve to a rectangular column footprint at each end (or split into repeated column instances at a spacing the user sets, for a long wall being replaced by a column line) — curved or multi-segment walls are blocked with the reason named, same posture as isolated footings being out of scope for `Convert Slab`.
3. Shows the same pre-flight checklist UX as `Convert Slab`: resolved target type per element, what survives, what's lost, blocked rows pre-unticked, Convert vs. Report-only.
4. One `TransactionGroup`, one `Transaction` per element — a single failure rolls back only that element.
5. Result table with a geometry delta (footprint area / volume / centroid) per element, flagged the same way `Convert Slab` flags a delta over tolerance.

What survives: level + base/top offset, structural flag, phase, workset, pin state, all writable instance + shared parameters matched by BuiltInParameter → shared GUID → name (unmatched ones listed by name), joins and join order (recorded, re-applied via `SwitchJoinOrder`), and — the hard part that makes this worth building rather than hand-converting — **hosted rebar re-pointed to the new host** via `Rebar.SetHostId` before the original is deleted, exactly like `Convert Slab` already does for slab-hosted rebar. What's lost, reported per element for confirmation: tags, dimensions, face-hosted family instances (door/window openings on a converted wall have nowhere to go on a column and vice versa), parts, the ElementId itself.

**Implementation:**
- Fork `ConvertFloor.pushbutton/script.py` structurally rather than the code: same recreate → replay → delete → rejoin → rehost-rebar → verify pipeline, same `type_name_mode` (`"same"` 1:1 by name, `"convention"` prefix/suffix + dimension-tolerance matching), same model-group ungroup/convert/regroup handling for single-instance groups, same blocked-by-default posture for multi-instance groups and elements in assemblies/inactive design options.
- New geometry step neither existing tool needs: footprint → line+thickness resolution for Column→Wall (via the column's `BoundingBoxXYZ` / cross-section sketch, falling back to the family's cross-section parameters when available) and line+thickness → footprint for Wall→Column — this is the one genuinely new piece of logic; everything else (parameter carry-over, join preservation, group handling, checklist UX, transaction-per-element rollback) is lifted from `ConvertFloor.pushbutton` and `anongee_toolkit.ui`.
- Rebar rehost reuses the exact `Rebar.SetHostId` call already proven in `ConvertFloor.pushbutton`; the "what's lost" report reuses its `forms.confirm` gate naming every element whose dependents will be destroyed.
- New `column_wall_convert_config.json` alongside `script.py`, mirroring `slab_convert_config.json`'s shape (`type_name_mode`, `thickness_tolerance_mm`, `groups.multi_instance`, plus a new `wall_axis_mode: "long_side" | "prompt"` and `column_spacing_mm` for the wall→column split case).
- Sits in `Essential.panel/StrucBIM.stack/`, next to `Convert Slab.pushbutton`, using the same `bundle.yaml` / `README.md` / `CHANGELOG.md` layout the root README documents for versioned tools.

**Future update:**
- Extend the footprint resolver to L/T-shaped and round columns by decomposing into multiple straight wall segments instead of blocking outright.
- Wall→Column mode learns a "replace every column-spaced stretch of this wall" batch mode, for converting an entire shear-wall run back into a column-and-infill scheme in one pick.
- Curved wall support via a chord-segmented column line, once the straight case has proven the rebar-rehost and join-preservation path in production.
- Shared `anongee_toolkit.convert` package factoring the recreate/replay/delete/rejoin/rehost pipeline out of both `Convert Slab` and this tool, so a third cross-category converter (e.g. Beam ⇄ Wall) starts from a real base instead of a second fork.

---

## 2026-09-11 14:30 UTC

**Idea name:** Universal Renamer — token templates + Excel mapping, across every renameable category

**Potential:**
Renaming to match a client's naming standard is one of the most repeated, most tedious tasks on a BIM team, and today it's done by hand, category by category, inside dialog boxes that only support simple find/replace. A model handover or a mid-project standard change (new discipline codes, new level naming, a merged project) can mean renaming 100+ sheets, views, levels, grids and schedules by hand — normally a half-day to a full day of pure clicking, with the real risk of dropped titleblock/view sync errors along the way. A token-driven, previewed, one-batch rename collapses that to minutes and removes the manual-error risk entirely. This is squarely in the productivity bracket the team already values enough to have built **Bulk Rename** for — it just stops short of the categories modelers actually rename most.

**Description:**
`Universal Rename.pushbutton` (or a new `Universal Rename.pulldown` sibling to the existing `Bulk Rename.pulldown`) extends renaming beyond Fill Patterns / Line Patterns / Line Styles to the categories a BIM modeler renames every week:

- Views (all types) and Sheets
- Levels and Grids
- Schedules and View Filters
- Family Types (within a family, e.g. duplicating a type-catalog row)

Two rename modes, selectable per run:
1. **Token template** — build a pattern from live tokens (`{Discipline}`, `{Level}`, `{ViewType}`, `{SheetNumber}`, `{OldName}`, `{Index:03}`, a regex capture group from the current name) and apply it across every selected/filtered element in one pass, e.g. turn `S-101 - Foundation Plan` into `STR-L00-FOUNDATION-PLAN`.
2. **Excel mapping** — drop in a two-column workbook (`Old Name → New Name`), matched by exact name or regex; this is the fast path for a client-supplied rename schedule that already exists as a spreadsheet, and it's fully auditable (the workbook itself is the change record).

Both modes share one pipeline: filter (by category, by naming pattern, by pre-selection) → live preview table showing old name / new name / collision flags → user unticks anything wrong → single `Transaction`, one undo step → result report (renamed / skipped / collided), exportable back to Excel for a handover record.

**Implementation:**
- Reuse the existing `Bulk Rename.pulldown` engine (`AnonGee.extension/AnonGee.tab/Essential.panel/Bulk Tool.stack/Bulk Rename.pulldown/`) as the base: it already has the search/tick/apply/report loop for style-type elements — generalize its element-fetch + rename-call layer behind a small per-category adapter (`views.py`, `sheets.py`, `levels.py`, `grids.py`, `schedules.py`, `filters.py`, `family_types.py`), each just implementing "list renameable items" + "apply new name" + "collision check", same shape `ConvertFloor.pushbutton` uses for its own per-category resolution.
- Token engine: small formatter over Revit's built-in parameters + regex capture groups pulled from the current name (`re.match` against a user-supplied pattern) — no new dependency, CPython3 stdlib `re` is enough.
- Excel mapping: reuse the `openpyxl` path already proven in `Export Schedule.pushbutton` / `BBS Generator.pushbutton` for read + the write-back report.
- Collision detection before the transaction opens (duplicate target names within the batch, or a target name already used elsewhere in the model) — block those rows, same "blocked rows pre-unticked" UX `Convert Slab` uses.
- Sits as a new pulldown/stack entry in `Essential.panel/Bulk Tool.stack/`, next to `Bulk Rename.pulldown`, following the same `bundle.yaml` / `ui.xaml` / `script.py` bundle layout documented in the root README.
- Ships with its own `CHANGELOG.md` since it's a tool likely to grow new categories over time (same pattern as `AutoLevel.pushbutton`).

**Future update:**
- Saved rename profiles (per-client naming standard), reusable across projects — analogous to Filter View Manager's project/workstation rule store.
- Extend token source to shared parameters, not just built-ins, so a firm-specific "Discipline Code" parameter can drive the template directly.
- Batch rename across a set of linked/worksharing-central models in one run (multi-document mode), for firms that split a project into linked structural/architectural/MEP files with a shared naming standard.
- Dry-run diff export (old vs. new) as a standalone Excel report without touching the model, for client sign-off before the actual rename.
