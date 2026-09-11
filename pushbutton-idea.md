# Pushbutton Ideas

Running log of pushbutton concepts for the AnonGee toolkit, one entry per idea, newest on top.

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
