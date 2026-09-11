# Pushbutton Ideas

Running log of pushbutton concepts for the AnonGee toolkit, one entry per idea, newest on top.

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
