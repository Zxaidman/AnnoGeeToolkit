# Pushbutton Ideas

Running log of pushbutton concepts for the AnonGee toolkit, one entry per idea, newest on top.

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
