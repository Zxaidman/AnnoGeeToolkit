# AnonGee BIM Tools — changelog

The version of the extension as a whole, as declared in `extension.json`.

## How this repository is versioned

There are two levels, on purpose.

**The extension** has one version covering the ribbon as a whole — which tools
exist, what the shared library and design system provide, how the thing is
installed. That is what this file records.

**A tool** may carry its own version and its own `CHANGELOG.md`, beside its
`bundle.yaml`, when it changes often enough that "which build am I running"
becomes a real question. A tool's version moves independently of the
extension's, and the version shown in a tool's own window is the build
actually running — quote it when reporting anything.

So `AnonGee BIM Tools 1.1.0` ships `Auto Level Manager 2.0.0`, and neither
number is wrong.

| Tool | Version | Changelog |
| ---- | ------- | --------- |
| Auto Level Manager | 2.0.0 | [`AutoLevel.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Essential.panel/AutoLevel.pushbutton/CHANGELOG.md) |
| Filter View Manager | 0.6.0 | [`FilterViewManager.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Dev.panel/FilterViewManager.pushbutton/CHANGELOG.md) |
| RC Automation | 0.7.0 | [`RC Automation.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md) |
| CAD2BIM Audit | 0.3.0 | [`CAD2BIM Audit.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Core.panel/CAD2BIM%20Audit.pushbutton/CHANGELOG.md) |

Both levels use [semantic versioning](https://semver.org), read from the point
of view of someone using the thing rather than someone reading the diff:

| Part      | For the extension                                                                                 | For a tool                                                                       |
| --------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **MAJOR** | A tool was removed or renamed, the tab was reorganised, or an installation step changed.          | The tool behaves differently on purpose — a workflow moved, or what it writes to the model changed shape. |
| **MINOR** | A tool was added, or an existing one gained a capability.                                          | A new capability. Everything you already did still works.                        |
| **PATCH** | Fixes only.                                                                                        | A fix. Nothing new to learn.                                                     |

---

## Unreleased — 2.1.0 candidate

> Not a release. Adding a tool is a **MINOR** extension change under the table
> above, so this is what `2.1.0` will say — but the product version is pinned to
> the installer's `MyAppVersion` and to the signed-build identity by
> `tests/test_installer_lifecycle_contract.py`, and `CONTRIBUTING.md` requires
> explicit review for anything touching installer or deployment. The bump, the
> `.iss` alignment and the contract update belong to a deliberate release step.
>
> The tool's own version moves independently and **is** released: Filter View
> Manager 0.1.0.

**Added**

- **Filter View Manager** *(Dev panel, tool version 0.1.0)* — saved,
  rule-based views. Build a rule down Category > Family > Type > Parameter,
  name it, and pressing it temporarily isolates what it matches in the active
  view. **It writes nothing to the project**: no view filter is created,
  nothing appears in Manage > Filters, and a colleague opening the model sees
  no trace. Rules live in `%APPDATA%` so they follow the user into the next
  project, and a rules file beside the model is read alongside them.
- **`AnonGee.extension/lib/anongee_filterrules`** — the tool's rule engine, and
  the first package to live in `lib/` rather than `lib/py3`. It is written to
  run on **both** engines, because the dockable panel that will hold the rule
  buttons must be registered from `startup.py`, which pyRevit loads on
  IronPython 2.7. `lib/` is the only folder both engines can import from. The
  dual-engine contract is enforced statically, since no machine that runs the
  test suite has IronPython on it.

**Fixed**

- **A stack holding one button is skipped by pyRevit entirely.**
  `RibbonPanel.AddStackedItems()` has overloads for two items and three, and
  none for one, so the stack and everything in it never reaches the ribbon —
  with no error anywhere. Filter View Manager shipped into a `col3.stack` of its
  own and was invisible in Revit because of it. It now sits directly on
  `Dev.panel`, and `tests/test_repo_docs.py` refuses any stack that does not
  hold two or three children.
- **The README's tool count is held to the number of rows it lists.** It read
  "30 tools" over 31 rows, because two branches each added a tool without
  touching the number.
- **Six dead links in this changelog.** The 2.0.0 ribbon reorganisation moved
  `RC Automation.pushbutton` into `col2.stack` and every link to its changelog
  kept pointing at the old path.
- **`Dev.panel/bundle.yaml`'s `layout:` named nothing.** It listed three
  *buttons* that live inside `Testing.stack`; pyRevit's layout names a panel's
  direct children, so it resolved to nothing and ribbon order fell back to
  discovery. It now names the four stacks, in the order discovery was already
  producing, so nothing visible moves.

**Testing**

- `tests/` is a package, so `python3 -m unittest discover -s tests -t .` runs
  the whole suite in one command. It previously failed outright, and sixteen
  files had to be run one at a time.
- Two new gates in `tests/test_repo_docs.py`: every markdown link into
  `AnonGee.extension/` has to resolve, and every panel layout entry has to name
  a direct child of its panel.
- `tests/test_filterrules.py` (155) and `tests/test_filterview_ui.py` (28).
  1260 tests in total.

---

## 2.0.0

**Changed**

- **The Dev ribbon was reorganised into stack columns.** Under this repository's
  existing SemVer contract a tab/ribbon reorganisation is a MAJOR extension
  change, so the product advances from the last published `1.26.1` to `2.0.0`.
- **Windows Setup now has an explicit lifecycle contract.** Installer/release
  milestone `0.8.0` distinguishes fresh install, same-version reinstall and
  forward upgrade, and blocks downgrades for installers built with the 0.8
  lifecycle overlay. The stable `AppId` remains the same so a newer version is
  the same Windows application rather than a side-by-side product.
- **The AnonGee extension remains replace-all on install/reinstall/upgrade.**
  Bridge runtime state under `%LOCALAPPDATA%\Zxaidman\AnonGee\bridge` is
  preserved, and pyRevit remains an independent prerequisite rather than
  something AnonGee uninstall owns.
- **Release pipeline `0.8.0` integrates the workstation-proven Authenticode path
  introduced in `0.7.0`.** Self-signed local builds remain permanently
  non-release-ready; publicly trusted signing remains deferred.
- **The bridge runtime default is the canonical local path**
  `%LOCALAPPDATA%\Zxaidman\AnonGee\bridge`, with `ANONGEE_BRIDGE_HOME` retained
  as the explicit override.

**Added**

- `installer/lifecycle-version.iss`, compiled into unsigned and signed Setup
  builds, reads the existing AnonGee uninstall registration and reports
  `fresh-install`, `same-version-reinstall`, `upgrade`, or `blocked` lifecycle
  mode before the normal prerequisite flow continues.
- Static installer lifecycle and signing contracts now pin product identity,
  immutable extension replacement, bridge preservation, version reuse guards,
  signing readiness, and the self-signed development certificate path.
- CAD2BIM continued to gain model/view helpers and more complete compound slab
  opening handling; detailed tool-level evolution remains in its own project
  history and tests.

**Fixed**

- Repeated CAD2BIM console messages are consolidated, and abutting compound
  slab void components such as L/C shapes are handled as one opening rather
  than competing rectangular cuts.
- Bridge Windows-path documentation no longer produces Python invalid-escape
  warnings during normal use or contract tests.

## 1.26.1

**Fixed**

- **Two definitions of one function, and Python took the stale one.**
  `structural/footings.py` carried two top-level `ensure_named_type`
  definitions — 1.26.0's edit spliced the new one in and left the old one
  below it — so every call reached the version that had never heard of the
  `name` argument, and fifteen footings died with
  `got an unexpected keyword argument 'name'`. `_set_thickness` was duplicated
  the same way by the same edit. Both are gone. (BUG-43)

**Added**

- **No module may define a top-level name twice**, or assign a module-level
  constant twice. Mutation-checked, and it found the second duplicate
  immediately.
- **A static call-signature check.** Every keyword one toolkit module passes to
  another must be one the callee accepts. These functions take a Revit
  `Document`, so no test can call them — a thousand tests could not have caught
  this. Re-removing the `name` parameter now names both call sites at the desk.

  Second time a repository-wide static check has been the right answer to a bug
  found in a live model. Where a function cannot be called by a test, its shape
  still can be.

## 1.26.0

**Fixed**

- **A reused type was resized, and the plinth beams went with it.**
  `ensure_symbol` sized whatever it was handed, created or found — so a run
  asking for 230 x 600 took the existing `PB-230x450`, set its depth to 600, and
  every plinth beam in the model became 600 deep. `written=110`, `status=done`.
  `duplicate` now returns whether it *made* the type, and only what was made is
  sized. (BUG-39)
- **Every category but columns ignored the naming convention.** Footings came
  out `F3`, beams `PB-230x450`, slabs `SL-150`, while the workbook said
  otherwise. The house name was only ever used to *name a type being created*;
  the search still adopted whatever the template already had. Now
  `typemaker.choose` makes **the house name the identity** — a beam is
  `CH-230 X 600`, not whatever the model calls a 230 x 600 section — with the
  old passes kept only as a reported fallback. Footings and slabs were never
  passed the patterns at all; they are now. (BUG-40)
- **`S_ScheduleMark` held the sheet's row label, not the convention.** The three
  `*_mark` patterns were read by nothing. They are wired, and `{prefix}` is new:
  the letters the workbook's own `TypeMark` starts with, so `PB-230x450` gives
  `PB1` and `B-230x600` gives `B1` from one pattern. `{n}` counts distinct
  TypeMarks within a prefix, in sheet order. A pattern that would give two
  sections the same label is reported every run, and the three legacy patterns
  are migrated once by the builder. (BUG-41)
- **The stair API was wrong in three places at once.** `StairsEditScope` is in
  `Autodesk.Revit.DB`, not `.Architecture`. The type members are CLR properties,
  not parameters — `LookupParameter("MaxRiserHeight")` returns `None`, which is
  why all four writes failed silently. And the waist is `StairsRunType`'s, not
  `StairsType`'s, and reads back as zero unless the run is monolithic first.
  `StairsConstructionMethod` is read at runtime rather than named, because its
  members could not be confirmed and guessing is what caused this. (BUG-42)

**Changed**

- **`REVIT_API_RESEARCH.md` is a general reference now**, not a rebar note. §0
  carries the five rules that have each cost a round in a live model —
  namespaces are not guessable, a property is not a parameter, a Python list is
  not a .NET list, `__namespace__` goes on the class, an edit scope will not
  start inside a transaction — and §1 is stairs, checked member by member
  against the published reference.

  It does **not** contain every Revit API, and says so: that document cannot be
  written or checked, and claiming otherwise would make it the file nobody
  verifies a claim against. What it has instead is coverage by contact — a
  member earns a place when this repository calls it — plus a stated method for
  settling the next one before the first line is written.

## 1.25.0

**Changed**

- **Stairs are real Revit stairs now.** The project owner ran option B — a
  waist slab with triangular steps, built out of framing and a `DirectShape` —
  and chose Revit's own `Stairs` instead: *"building stairs with beam and slab
  is management nightmare and scheduling for use Revit own stairs"*. That is
  what the review document pointed at: schedule pollution was the one cost
  option B could never fix.

  `structural/stairs.py` is rewritten against `StairsEditScope` and
  `StairsRun.CreateStraightRun`. `rc_automation/flight.py`, `STAIR_TYPES`,
  `STAIR_PLACEMENT` and the reading half of the command carried over unchanged,
  as the review said they would.

  **This is the one command that holds no transaction while it writes.**
  `StairsEditScope.Start` throws if a transaction is open and has to open one of
  its own, so `_placement.run` now takes a *write* override and stairs use
  `outside_a_transaction`: the transaction group stays, so the undo step is
  still one, but each flight commits its own scope. The cost is real and it is
  reported — a run that fails on the fourth of five leaves three built, where
  every other command rolls back whole.

  The sheet drives the type: waist to `StructuralDepth`, tread to
  `MinimumTreadDepth`, riser to `MaxRiserHeight`, with `MonolithicStairs` set
  first because a stair that is not monolithic has no structural depth to set.
  The riser **count** goes on the instance, so Revit divides the rise by the
  same whole number `flight.solve` does and the two agree by construction.

**Recorded, not fixed**

- **Option B's steps could never have been built.** `List[object]()` is not a
  marshallable .NET list — pythonnet answers `type(s) expected` — so every
  flight raised after its waist was placed and `written` stayed 0. The code is
  gone with option B. It is recorded because a test asserted `List[CurveLoop]()`
  was present and passed, while the actual failure was one line below it in a
  list the test never looked at. (BUG-38)

## 1.24.1

**Fixed**

- **BUG-31's actual cause, found in the model.** `ensure_symbol` takes a
  parameter called `name` — the type name the NAMING sheet asked for — and its
  four match passes were written `for _label, name, ... in loaded:`. Python's
  for-loop leaks its variable, so once all four ran without matching, which is
  precisely when a type has to be created, `name` held **the last loaded type's
  name** instead. `Duplicate(name or wanted)` therefore asked Revit for a name
  that already existed by construction, and could never succeed. `columns.py`
  escaped it only because its passes live in a separate `find_symbol` with no
  parameter to shadow — which is why columns created types happily and beams
  never once did. A repository-wide test now fails on any loop that rebinds one
  of its own function's parameters, mutation-checked against the original line.
- **A same-named type was reused without checking its size.** Introduced with
  1.24.0's hardening, and worse than the bug it was fixing: `beams.sync`
  reported `written=110`, `status=done`, and gave every 230 x 600 floor beam the
  230 x 450 plinth section. A name is not a size. `duplicate` now takes an
  `accept` callback and every caller compares the type's real width and depth
  before reusing it. (BUG-36)
- **Every message arrived with a question mark in the middle of it** — *"0 of 5
  stair flight(s) written ? 5 did NOT happen"*. The result file is written as
  ASCII on purpose, and `errors="replace"` turned the new em dashes and degree
  signs into literal `?`. Transliterated in one place rather than policed per
  message, with a test that reports any character transliteration does not know
  about. (BUG-37)

**Confirmed in Revit**

- Findings now survive the next command — eighteen jobs of history, newest
  first, in the workbook the owner pushed back. (BUG-32)
- The shortfall is reported first: *"0 of 5 stair flight(s) written"* rather
  than *"0 written"*, which is what made the stair failure visible. (BUG-33)
- `naming.refresh` runs and is idempotent. (FEAT-41)

## 1.24.0

**Fixed**

- **A beam type the model does not have could not be created, and a hundred
  and ten beams went with it.** Narrowed by elimination from the pushed
  workbook: the failing rows were exactly the ones naming a type no model had
  ever held, and the run that took the modify path — which never touches a
  level — still wrote nothing, so the levels were innocent. Running the owner's
  own `BEAM_TYPES` through `parse_types` ruled out the missing-size path, which
  leaves `Duplicate` throwing. **The beam type-creation path had never once
  succeeded in a real model**; every green beam run had *found* its types. It
  was proven for columns and footings and assumed for beams. Type creation now
  lives in one module, `structural/typemaker`, and reports the exception in
  Revit's own words along with the name that was refused and the family it was
  refused in — then tries the workbook's TypeMark and a numbered variant.
  (BUG-31)
- **The next command destroyed the last command's findings.** BUG-20 stopped an
  *empty* result wiping the sheet; any result still wiped it, so the reasons a
  run failed survived only until somebody tried the next thing. A hundred and
  ten explanations were overwritten seventy-one seconds after they were
  written. Each job's findings are now inserted above the last, and only
  `AnonGeeBridge_ClearFindings` empties the sheet. (BUG-32)
- **Two counts that read as success.** `written=22` out of `created=132` was
  reported as "22 beam(s) written" with no mention of the other hundred and
  ten; and a run where every row was invalid reported that every beam was
  already there. The note now leads with the shortfall, and *nothing matched*
  is told apart from *nothing was usable*. (BUG-33)
- **`beam_mark` refused the field its own sheet advertised.** `B{n}` was
  rejected because that key declared only `{level}` and `{grid}`, while the
  NAMING sheet's *Fields it may use* column offered `{n}`. It degraded silently
  by design, so beams were placed with marks nobody asked for. All three mark
  patterns now share one field list. The three are also **read by no command
  yet**, and a pattern typed against one now says so. (BUG-34)
- **A rebuild threw away hand-edited naming patterns.** Found by doing it: the
  rebuild that added the stair sheets reset every `Pattern` to the module's
  default. The workbook now ships the house convention and a hand-edited
  pattern wins over it, read before anything is cleared — as the LOG already
  was. (BUG-35)

**Added**

- **`naming.refresh`** — a button that rewrites the NAMING sheet's `Example`,
  `Fields it may use` and `What it names` from the patterns beside them, so the
  sheet cannot disagree with itself. Not an Excel formula, because `Example` is
  the renderer run against a sample and a formula would be a second copy of it.
  It touches no model and never writes the `Pattern` column. (FEAT-41)
- **A `#CELLS` block on the result**, so a command can answer into a sheet
  rather than into a log. Every command until now was one-way. (FEAT-41)
- **Stairs, option B, for review.** `stairs.sync`, `STAIR_TYPES` and
  `STAIR_PLACEMENT`: an RC stair as a waist slab with triangular steps on it —
  the waist a slanted structural framing member whose section is the stair's
  width by the waist thickness, the steps one `DirectShape` of triangular
  prisms. Exact quantities, sheet-driven, idempotent, and the waist is a real
  structural element rebar can host on later. **The cost:** the waist appears
  in Structural Framing schedules and has to be filtered out of them. No
  mid-landing yet, so a dog-leg comes out as two flights with a gap. Shipped to
  be judged against a real Revit `Stair`, not as a finished thing. (FEAT-42)

## 1.23.0

**Fixed**

- **Every beam arrived with a z offset of −1500.** Nothing set it.
  `NewFamilyInstance` gives a beam whatever the family and the **last
  placement** left behind, and −1500 is the foundation level — a number from
  somewhere else entirely in the model, carried into ninety beams because
  nothing said otherwise.

  Justification and offset are **stated now, not inherited**: `yz` uniform, `y`
  origin at zero, `z` top at zero, and the sheet's `Offset` written to the level
  offsets, where it belongs. Anything a run does not set is a value somebody
  else chose, and on a family instance that is most of them.

- **Beams ran column centre to column centre, and joined.** A grid intersection
  is where a **column** stands, not where a beam ends — so a beam drawn between
  two of them runs through both columns, the concrete is counted twice at every
  junction, and Revit's automatic join then extends it further.

  Each end is now **cut back to the column face**: half the column's dimension
  *along the beam's own direction*, which is its Width for a beam running along
  X and its Depth for one along Y, swapped when the column is turned. The column
  is looked up in `COLUMN_PLACEMENT` by the same intersection the beam names,
  keyed on the level its **top** reaches — because that is the level the beam
  sits on. Joins are disallowed at both ends. An end with no column under it is
  left on the grid and that is said once.

  `EndPrep` on the sheet says which convention a row uses, so a beam that really
  does run to the grid can still say so.

**Added**

- **A `NAMING` sheet** — type names as patterns, `{b} X {h}`, the way `cad2bim`
  already does it. The house convention lives where a person can change it, and
  the **example beside each pattern is generated from it** rather than typed, so
  it cannot drift.

  A pattern that will not render is reported and the default used. Ninety
  columns refused because somebody typed `{width}` for `{b}` would be the tool
  confusing a preference with a requirement.

  The workbook's `TypeMark` is still what a row *asks for* and is matched against
  the model first; the pattern decides what a type is *called* when one has to
  be made — so a model does not fill up with names in the workbook's dialect
  beside the template's own.

- **A proposal for schedules and footing rebar**,
  `docs/specs/2026-08-26-schedules-and-footing-rebar.md`, for review before
  either is built. The estimates are the point: schedules are a morning, footing
  rebar is **weeks, not days**, and the seven versions RC Automation has already
  spent on it are the evidence rather than a pessimistic guess.

**Changed**

- The test suite is 921 tests, from 899.

---

## 1.22.0

**Added**

- **`beams.sync` and `slabs.sync` — the last two structural commands.** All
  seven are bound now; nothing is left declared-but-unwritten.

  **Continuity is the layout, and the parser is the only thing that reads it.**
  A blank row says where one beam ends and the next begins, so `parse_beams`
  returns *groups* rather than rows — the one parser in the toolkit that must
  not skip a blank line, where every other one must. 62 beams over 132 spans in
  the sample; one Revit member per span, which is not a simplification but how
  Revit models a continuous beam. What the grouping buys is the schedule mark.

  **A slab's inset is read, not assumed.** `EdgeRule = Inner face of beam`
  means each edge comes in by half the width of the beam **actually on that
  edge** — looked up in `BEAM_PLACEMENT`, whose section is looked up in
  `BEAM_TYPES`. A panel with a 300 floor beam one side and a 230 plinth beam
  another is inset differently on those two sides, and averaging them would put
  the edge wrong on both. An edge with no beam is left on the grid line and
  that is said once, not forty times.

  Both idempotent off Revit: 132 beams and 40 slabs created, then matched.

- **The survey point can be set from the workbook** — `APPLY_SURVEY_OFFSET`,
  and it is **No** by default. The owner fixed a mismatch by hand with *Specify
  Coordinates at Point* and asked whether it could be automated; it can, because
  `levels.sync` already reads the model's offset to check the sheet against it.
  Making it *set* the offset is the same knowledge pointed the other way.

  Off by default because moving a survey point re-coordinates a whole project —
  every shared coordinate, every linked model's alignment. That is a decision,
  not a convenience. The point is unpinned, moved and pinned again exactly as it
  was found, because setting a pinned element's parameter fails silently.

**Fixed**

- **Footings never wrote the schedule mark.** The chain was in `columns.py` and
  nowhere else, so footings wrote Revit's `Mark` and stopped — and the owner
  found it in a model.

  Underneath it, a second thing: the two sheets did not mean the same by
  `Mark`. A column row said `C1`, a repeating label; a footing row said `F-A1`,
  a unique key. Even shared, the two would have written different kinds of value
  into one parameter. **`Mark` is the repeating schedule label on every
  placement sheet now** — footings are `F1`, `F2`, `F3` — and Revit's own `Mark`
  gets the key. One rule, one home, four sheets, and a test that fails if any of
  the four stops using it.

**Changed**

- A mark no longer repeats its level: `B01-1-1-A1B1`, not
  `B01-1-1-A1B1-01`. Unique either way; only one of them is readable. All 277
  marks across the four sheets are unique — checked together, because Revit's
  `Mark` is one namespace for the whole model.

- The test suite is 899 tests, from 882.

---

## 1.21.0

**Fixed**

- **`BRIDGE_URL` on `INFO` was decoration.** pyRevit moved from 48884 to
  **48885**, the owner changed the cell to match, and the error still named
  48884 — because `BridgeUrl` built the address from the module constants and
  never read the sheet.

  Worth knowing why the port moves at all: **pyRevit takes 48884 when it can and
  the next free one when it cannot.** A second Revit session, or one that did
  not shut down cleanly, is enough. So it was never a constant.

  The cell is read now, with the constants as a fallback. And when a call fails
  the macro **looks** — pinging 48884 to 48892 — and answers *"something IS
  answering on 48885, put this in INFO"*. A dead end becomes an instruction.

  The probe waits **one second** per port rather than the usual fifteen. Nine
  ports at fifteen is over two minutes of Excel not responding, which is the
  exact shape of `BUG-8`: a diagnostic slower than the user's patience is worse
  than none, because they stop it and learn nothing.

**Added**

- **The schedule mark falls back through a chain**, as the owner asked:
  `SCHEDULE_MARK_PARAM` now reads `S_ScheduleMark, ID, Comments` and the first
  one the model actually has wins. The order is the point — a shared parameter
  is the proper home, `ID` is an existing shared one that will at least
  schedule, and `Comments` is where things end up when nothing better exists.

  **A fallback that gets used is reported.** Falling back silently would leave a
  schedule reading `S_ScheduleMark` empty while the values sat in `Comments`,
  where nobody looked.

**Changed**

- The test suite is 882 tests, from 878.

---

## 1.20.0

**Fixed**

- **Every rebuild leaked thirteen VBA sheet modules.** The VBA editor listed
  **forty** `Sheet` objects for a workbook with fourteen sheets, growing with
  each rebuild, and none of it visible from Excel.

  A rebuild deleted every worksheet and made new ones with the same names — not
  the same operation to a workbook carrying VBA, which holds a **code module per
  sheet** that `openpyxl` rewrites worksheets without touching. Thirteen modules
  orphaned, thirteen more added, every time. The sheets are cleared in place
  now; only sheets the build no longer writes are deleted, and those are the
  ones whose modules should go too.

- **The same survey disagreement was reported seven times.** One warning per
  level, all saying the same thing: the model puts its survey point at the
  origin and the workbook says 100 m. One wrong cell, seven findings, and the
  one instruction that mattered buried among them.

  Reported once now, naming the number and where to change it. Rows out by
  *different* amounts are still reported one each — then they really are
  separate mistakes, and collapsing them would hide six of the seven.

- **A test hard-coded a ribbon path**, and the owner reorganising `Dev.panel`
  into stacks broke it. It searches for the file now: a ribbon gets
  reorganised, and a failure that says nothing about the code costs somebody the
  time it takes to work out that it says nothing.

**Changed**

- **The template critique is rewritten from the corrected extraction.** The
  re-run confirms the fix: `ID` is shared, six others are project, and the types
  read `spec.string` and `massPerUnitLength` rather than the name of a class.
  Which changes the recommendation — **the template already has a shared
  parameter file**, so adding `S_ScheduleMark` is one definition rather than a
  new piece of setup.

- The test suite is 878 tests, from 871.

---

## 1.19.0

**Fixed**

- **`Mark` was given a value that repeats, and Revit warned.** The owner's
  marking rule is that `C1` repeats — up a stack and across a floor — and `Mark`
  is the one Revit parameter expected to be unique per instance. Writing a
  deliberately repeating label into it was always going to warn.

  `Mark` now carries the **key**, unique by construction: `C1-A1-S1`. The
  schedule label goes to a parameter the workbook names on `INFO` under
  `SCHEDULE_MARK_PARAM`; with none named it is not written and **one** finding
  per run says which parameter to bind — not ninety identical ones.

- **One blocked level cost fifteen columns and left a storey-high gap.** The
  template carries `Level 0` at 0.000 and the sheet asks for `01 GROUND LVL.` at
  0.000, so *never create a second level at an occupied elevation* refused it —
  correctly. Then every column naming that level as its **base** failed (fifteen,
  exactly the S2 lift) and every column naming it as its **top** was placed
  without one.

  `LEVELS` gains a **`RenameFrom`** column. A row that names the level it
  replaces renames it instead of being blocked — explicit, auditable, and it
  does not weaken the rule for anything that does not ask. The refusal now also
  says what to type where.

- **The FINDINGS sheet was wiped by the next job.** It was cleared on every
  result including one with nothing to say, so pressing two unbuilt commands
  after the columns run erased fifteen explanations. It now carries a header
  saying which job and command its findings belong to, and a run with none says
  *no findings* — because a blank sheet and a run that failed to report look
  identical.

- **The extraction called every parameter a project parameter.**
  `doc.ParameterBindings` hands out an `InternalDefinition` for shared and
  project parameters alike, so the `isinstance(…, ExternalDefinition)` test was
  **always false** — a real template came back with no shared section at all.
  Shared parameters are now found through `SharedParameterElement`. And the Type
  column printed `Autodesk.Revit.DB.ForgeTypeId`, the name of a class: it is the
  `TypeId` string that was wanted.

  Worst of the four, because the report exists to answer *where may the workbook
  safely write* and that is the whole answer. **Re-run the extraction.**

**Added**

- **A type is matched by its dimensions when the names differ.** A template
  holding `300 X 600` and a workbook asking for `S_Col_300x600` mean the same
  section; duplicating it because the words differ fills a model with types that
  already existed. Reported every time it is used, and order is kept — 300 × 600
  is not 600 × 300, and treating them as the same would turn every column in a
  frame ninety degrees.

- **A critique of the real template**,
  `docs/specs/2026-08-25-template-critique.md`, read from the extraction: about
  ninety leftover column types where a template wants six, three naming styles
  across three foundation families, seven project parameters bound to two
  hundred categories including `Food Service Equipment`, and one sheet called
  *Unnamed*. With a naming proposal, and the two items that actually block
  something separated from the five that are tidiness.

**Changed**

- The test suite is 871 tests, from 853.

---

## 1.18.0

**Fixed**

- **Extract Template could not import the toolkit — and blamed the wrong
  thing.** First press: *No module named 'anongee_toolkit'*, followed by my own
  message telling the owner to check the `#! python3` line, which was there, on
  line one, and was not the problem.

  pyRevit puts `<extension>/lib` on `sys.path` and **nothing below it**. The
  toolkit lives in `lib/py3`, so every tool that uses it calls
  `path_resolver.update_paths()` first. This one did not. The two failures are
  indistinguishable from inside Revit — same `ImportError`, same wording — which
  is why a confident wrong message is worse than no message: it sends somebody
  to look at a line that is already correct.

  **A repo-wide test now holds it**, and the test had to be fixed twice before
  it was worth having. It first flagged a tool whose only mention of the toolkit
  is in a comment — the fourth time a test here has matched prose rather than
  code — so it reads the AST. Then a mutation showed it passed a script that
  *defined* a bootstrap and never called it, so it now walks module-level code
  only and requires the call.

- **The buttons did not move or size with their cells.** Not diagnosed —
  instrumented. `Placement` was set inside a blanket `On Error Resume Next` and
  never checked, leaving three indistinguishable possibilities: the line did not
  run, it ran and failed, or Excel overwrote it. The workbook's own XML says
  `twoCellAnchor` with no `editAs`, which *is* move-and-size, so the file
  contradicts the symptom and another round of guessing would have been the
  fourth.

  It now **sets it, reads it back and reports the count** — *"7 button(s) drawn,
  7 of them set to move and size with their cells"* — with two attempts, because
  the `Shape` property and the `ShapeRange` form fail differently.
  `AnonGeeBridge_AnchorButtons` runs the anchoring on its own, so if a button
  still will not follow its cell after that reports success, the cause is Excel
  and not the macro. One press turns it from a guess into a fact.

**Changed**

- The test suite is 849 tests, from 844.

---

## 1.17.0

**Fixed**

- **A missing type stopped the run instead of being made.** The first real
  attempt at columns and footings reported `created=90` and `created=15` with
  `written=0`: every row said *no type called `C-300x600`* and stopped. Both
  halves were right — the model genuinely did not have those types, and the run
  genuinely refused to guess — and the result was still nothing built.

  A type the model does not have is now **duplicated from a loaded family and
  sized from the TYPES sheet**. `C-300x600` becomes a copy of the rectangular
  concrete column family with `b` and `h` set to 300 and 600 and its Type Mark
  written; `F1` becomes a copy of the model's foundation type at 600 thick.

  **Creating a type is not authoring a family**, and that boundary is what makes
  it safe: the new type inherits the template's materials, subcategories and
  behaviour because it is a copy of something the template set up. A model with
  no family to copy is reported, by name, with the standard family to load. A
  family whose dimensions are not called anything recognisable gets a correctly
  named type at the wrong size — **and says so**, because a 300 × 600 column
  that is silently 400 × 400 is worse than none.

**Added**

- **Extract Template** — a pyRevit button that writes everything the model
  contains to one Markdown file. Every category with what is in it, every family
  and every type inside it, and **every parameter with its scope** — shared,
  project, global, family, instance, type — plus levels, grids, view templates
  and sheets.

  A `.rvt` is a compound binary that only Revit opens, so a template cannot be
  reviewed, diffed or discussed anywhere else, by anybody. This is the model
  describing itself instead. The report is sorted, carries no timestamp, and
  contains nothing that changes between two runs over an unchanged model — so it
  can be committed, and *what changed in the template* becomes a question with an
  answer. Read-only: no transaction, nothing written, safe to point at the real
  template.

  Parameter scope is the section that matters. A value written to a **shared**
  parameter survives a family reload and can be scheduled and tagged; a
  **project** one lives in this file only; a **family** one cannot be reached
  from outside its family. A workbook writing to the wrong kind produces a value
  that quietly disappears, and the run reports success.

- **The template and the workbook, coordinated** —
  `docs/specs/2026-08-25-template-and-workbook.md`. Each fact has exactly one
  owner: the template says what is *possible*, the workbook says what is
  *wanted*. Families, shared parameter definitions and view templates are the
  template's; sizes, values and which types this job uses are the workbook's.
  Written as a proposal to argue with rather than a description of anything,
  because the first extraction has not happened yet.

**Changed**

- **Cover and diameter stay in millimetres** — already true — and now the
  **buttons sit on the gridlines**: no inset, a one-unit border, and set to move
  and size with the cell under them, so widening a column or dragging a row
  taller takes the button with it.

- **`Segoe UI Semibold` leads the font stack**, ahead of Inter, for the whole
  workbook and for the buttons.

- The test suite is 844 tests, from 816.

---

## 1.16.0

**Added**

- **`columns.sync` and `footings.sync` — the first two commands that place
  something.** Both read a placement sheet, resolve a grid intersection to a
  point, and write in one undo step.

  **The match is on position, never on the mark.** The owner's marking rule
  repeats a mark up a stack and across a floor on purpose, so a mark cannot be
  what a second run recognises. What identifies a column is where it stands and
  which storey it is in; a footing keys on position alone. Proved against the
  sample: 90 columns created, then 90 matched, then 90 matched again — and 15
  footings the same.

  Everything either of them decides is decided in
  `rc_automation/placement.py`, which has no Revit in it and carries 34 tests.
  Four refusals, all of them a refusal to guess:

  | | |
  | --- | --- |
  | **A grid the model does not have** | the row is left unbuildable and reported. The alternative is a column at the project origin, which looks deliberate |
  | **Two rows in the same place** | one of them is a typo; neither is built |
  | **No type, or no level** | reported by name, with what the model does have |
  | **Something the sheet does not mention** | left alone and reported. Nothing is ever deleted |

  A pad is a floor, which is what lets an arbitrary outline be drawn. A blank
  `Outline` means the type's own Length and Width describe it, read from
  `FOOTING_TYPES` — so fifteen footings share three sizes and the placement row
  stays readable.

- **`AnonGeeBridge_ApplyFormat`** — picks the first font in
  `Inter, Segoe UI, Cambria, Calibri` that is actually installed and applies it,
  with 20-unit rows and fitted columns. Excel stores one font name per cell and
  has no fallback list, so the fallback has to happen once rather than at render
  time.

**Fixed**

- **`ApplyUnits` walked straight past `INFO`.** It finds lengths by their column
  header, and `INFO` is key-value-description in rows — no header above the
  number, nothing to find. The key carries the unit now, in the same brackets,
  in the cell beside the value: `SURVEY_OFFSET (m)`.

**Changed**

- **Cover and diameter stay in millimetres.** Metres were chosen so a level
  reads as 3.30 rather than 3300; by the same argument a cover of 0.05 and a bar
  of 0.012 read worse than 50 and 12, so consistency there would cost the thing
  it was bought for. Those columns are pinned by what they are — a header
  starting `Cover` or `Dia` — rather than by a list somebody keeps in step.

- **Buttons are shapes, from the owner's own template.** `AddButtons`
  duplicates a shape the sheet already has, so the rounded rectangles the owner
  drew become the house style without their fill colour being written down in
  code; a sheet with no template gets one built to match. It also draws
  `ApplyUnits` on `INFO`, beside the unit it applies. This is re-runnable
  because it has to be: `openpyxl` deletes every drawing in a workbook it
  rewrites, so a rebuild keeps the macros and loses the buttons.

- **The workbook's formatting is a build output.** Fonts, three sizes one step
  apart, every row 20 units, every column width computed from what is in it,
  `mm` shown whole and `m` to two decimals. Generated rather than applied by
  hand, because a rebuild throws away anything applied by hand.

- The test suite is 816 tests, from 781.

---

## 1.15.0

**Fixed**

- **`Write? = Yes` did nothing, and the switch overwrote itself.** The macro
  read the dry-run switch from CONTROL column 5 and wrote the outcome to column
  6. The sample workbook added a `Built?` column at 5, so `Write?` moved to 6 —
  and from then on the switch was read from a cell that says `yes` or `not yet`
  and never says `No`. **No run could be made to write, whatever was typed.**
  Then the status landed in the `Write?` cell, so the switch said `done` and
  stayed that way.

  Two dry runs were reported against a live model as *created=6* and *created=8*
  with nothing built. Both were true; the note said *dry run* and `written=0`
  both times. The tool was right about itself the whole way through, which is
  the only reason this was findable from a pushed workbook without opening
  Revit.

  **The fix is not a corrected number.** Every CONTROL column is now found by
  its header, once per run, and a sheet whose `Write?` column cannot be found
  stops the run and says so rather than falling back to a dry run — a silent dry
  run is indistinguishable from Revit ignoring you, and that is what cost the
  round. A test fails on any `Cells(row, <number>)` in the three procedures that
  touch CONTROL.

**Added**

- **One unit for the whole workbook, named in every header.** `INFO` carries it
  and **metres is the default**. Every length column says which unit it is in —
  `Elevation PBP (m)` — so the unit sits beside the number rather than in
  somebody's memory, `AnonGeeBridge_ApplyUnits` can find exactly the columns it
  must rescale, and a job tells Revit what the number meant. Revit is internal
  feet whatever a project's display units say.

  The header beats the job. A column headed `(m)` is metres even if the job says
  the workbook is millimetres, because the header is the thing sitting next to
  the number. Millimetres stays the fallback: every workbook written before this
  was in millimetres, and a default that rescales one of those by a thousand is
  not a default.

- **Two elevations on `LEVELS`** — Project Base Point and Survey Point, with
  `ElevationBase` saying which one drives. The survey offset is read from the
  model's own base points, never assumed. A row measured from the survey point
  in a model that will not say where its survey point is stays unbuilt and says
  why; a row giving both elevations that disagree is **reported and not
  corrected**, because one of the two numbers is wrong and picking one is not
  something a spreadsheet import should do.

- **Buttons, from a macro.** `AnonGeeBridge_AddButtons` draws a Form Control
  button on every CONTROL row and assigns its macro. `openpyxl` writes sheets,
  values and validation, and cannot write a form control — so this is one
  `Alt+F8`, like the `.bas` import, and re-running it replaces the buttons
  rather than stacking them.

**Changed**

- **The sample workbook's format, on six counts, all from the owner's review:**

  | | |
  | --- | --- |
  | `X`/`Y` say what they are | now `OffsetX`/`OffsetY`, measured **from** the named intersection. Blank means dead on the grid. `Outline` is for a pad the type cannot describe — combined, stepped, cut round a pit — and is blank for anything rectangular |
  | **A column mark follows the stack** | a column at A1 marked `C1` is `C1` all the way up, even where it reduces. Two columns share a mark on one floor only if size **and** rebar schedule agree. So the mark is a schedule label, not a key — the key is grid position plus storey — and the sample now shows three marks by cage where it used to show two by size |
  | `S1`–`S6` are storeys, and the sheet says so | every row names its own base and top level, so the code never has to be looked up |
  | **Beam continuity is the layout** | a simply supported beam is one row, a continuous beam is a group of rows sharing a mark, and a blank row separates groups. 62 beams over 132 spans, and the plinth beams are simply supported so the sample shows both |
  | **A slab is a panel, not a floor** | one slab per bay, bounded by its four grids, stopping at the **inner face of the beams** — so the beam is not counted twice. 40 panels, and `EdgeRule` names the convention per row so a slab that runs over its beams can still be said |
  | The `LOG` survives a rebuild | it is the only sheet that is not generated. It is what happened |

- The test suite is 781 tests, from 741.

---

## 1.14.0

**Added**

- **A sample project workbook — Foundation + G + 4, generated.**
  `bridge/excel/build_sample_project.py` writes a whole small building so the
  **format** of every sheet can be argued with before any of it is built:

      24 m x 12 m, five vertical grids A-E and three horizontal 1-3 at 6 m,
      seven levels from -1500 to +16500, six storeys.

      7 levels - 8 grids - 15 footings - 90 columns - 132 beams - 6 slabs

  Everything comes from the constants at the top of the file. Move a bay or add
  a storey, re-run, and the building stays consistent with itself — the beams
  follow the grids, the footings follow the intersections, the columns follow
  the storeys.

  Two conventions are what the review is actually about:

  | | |
  | --- | --- |
  | **Grid reference first, coordinates as the fallback** | every placement row names an intersection and leaves X and Y empty. Coordinates are there for what a grid cannot describe, and for a model with no grids in it yet |
  | **One row per element that will exist** | a column rising six storeys is six rows. In a reinforced concrete frame those are six pours with a joint between each — and a column that changes size at the fourth floor has to be able to say so. Verbose, and honest |

- **`footings.sync`, `columns.sync`, `beams.sync` and `slabs.sync` declared —
  and deliberately not written.** The name and the sheet are in `registry.py`,
  so the workbook can carry the button and pressing it answers *declared but not
  built yet*. That is a clear failure instead of an obscure one, and it is the
  same thing the datum commands did before they existed.

  A test holds the three files that could disagree — the registry, the `Built?`
  column on `CONTROL`, and the macros — so the sheet cannot quietly start
  claiming more than has been built.

- **The build record**, at the top of `todo-list.md`: one row per thing that
  ends up in a model, and four words that mean four different things — *built*
  is code with a green suite and is worth nothing on its own, *tested* is the
  owner running it in Revit, *done* is the owner saying it was right, and
  *failed / redo* counts the rounds that came back. `failed` and `redo` are now
  phases in their own right; a thing that took four rounds is telling us
  something about the next thing like it.

**Changed**

- The test suite is 741 tests, from 727.

---

## 1.13.0

**Added**

- **`grids.sync`, with an `Angle` column.** 0 runs along +X and 90 along +Y — a
  horizontal grid is 0, a vertical one is 90, a skewed one is whatever it is.
  The convention is the project owner's, added after meeting a real job with
  grids at 30 and 45 degrees.

  A row gives **both ends, or a start and an angle**. Giving both is allowed:
  the points win, because they say more, and the disagreement is reported
  rather than quietly resolved. A row with an angle and no length borrows the
  extent of the grids in the same sheet that did say — "grid A runs north" is a
  thing real sheets write, and something has to decide how far.

  Two rules are specific to a thing with a direction, and both are refusals:

  | | |
  | --- | --- |
  | **Position is synced; extent is not** | grid extents are adjusted by hand in nearly every view of a real project. Comparing endpoints would report all of them as needing a change and then undo the work — so two grids on the same *infinite line* are the same grid, whatever their lengths |
  | **A grid running a different way is never redrawn** | Revit cannot turn a grid; it would mean deleting and recreating, which loses anything dimensioned or constrained to it. Reported with both angles, and left |

  A grid that does move is **translated perpendicular to itself**, never
  redrawn — sliding along its own direction would move it without changing
  where it is, and drag its extents off the building for nothing.

  Existing grids are read through `structural.grids.segment_mm`, which already
  knows an arc grid has no straight line to compare.

---

## 1.12.0

**Added**

- **`levels.sync` — the first command that builds something.** Match the LEVELS
  sheet against the model, then create or move each level. Its rules live in
  `anongee_toolkit/rc_automation/datum.py`, which imports nothing from Revit and
  is tested off it, so all four refusals can be argued with before anybody
  presses a button:

  | | |
  | --- | --- |
  | **Never delete** | a level the sheet omits is left alone and reported — deleting one takes every view, every sheet reference and every element hosted on it |
  | **Match by name only** | `naming.py` can match `Level 1` to `01 1st Floor Lvl.` by storey number, and that is right when a schedule *refers* to a level somebody else named. Here the sheet **is** the naming authority, so a fuzzy match would silently decide two differently named things are the same one |
  | **Never fill an occupied elevation** | Revit allows two levels at one height, and then every plan view has two candidates. Reported with the occupant's name; the fix is a rename somebody makes on purpose |
  | **Never rename** | a rename changes what every view and sheet refers to |

  **Idempotence is the acceptance test, not creation.** Anything can create;
  only a tool that can be run twice is one anybody trusts with a live model, and
  a test runs the plan against the model its own first run would have built.

  Headings are matched as prefixes, because a real sheet writes `RL (mm)` rather
  than `Elevation` — and a column headed `Level` is deliberately a name and not
  a height.

**Fixed**

- **The macro's dialogs showed mojibake.** Two em dashes in message strings came
  back as `a-hat-euro`: Excel imports a `.bas` as the machine's ANSI code page,
  not UTF-8, and there is nowhere in that format to say otherwise. The module is
  pure ASCII now and a test fails on any byte above 127 in it — the same lesson
  as the result TSV, one layer further out.

---

## 1.11.0

**Added**

- **Bridge Listener 0.4.0 is a modeless window**, not a dialog. A `TaskDialog`
  reports what was true at the instant it opened, which is the wrong shape for
  a thing whose entire job is to be watching: a job arriving thirty seconds
  later was invisible, and five rounds of diagnosis went by with no way to see
  whether one had even landed. Requested by the project owner.

  It lists jobs as they arrive — id, command, status, counts — refreshed once a
  second from the folder. The refresh runs on the WPF thread and **touches no
  Revit API**, so it cannot interfere with a job.

**Changed**

- **Idling is subscribed once per session and never removed**; the button flips
  a flag. One attribute read per tick, and no question of adding or removing a
  Revit event from the WPF thread.
- **Closing the window stops the watching.** A listener running behind a closed
  window writes to a model with nothing on screen saying so.
- The dialog survives as a fallback — the window is the interface, not the
  mechanism.

---

## 1.10.5

**Fixed**

Both found by reading the `Run_Echo` path rather than by running it, while the
first real job was in flight.

- **The macro was handed a path it could not open.** The post's answer carries
  `resultTsv`, and JSON doubles every backslash in a Windows path.
  `JsonValue` returned that verbatim — `C:\\Users\\praka\\…` — which Windows
  may or may not collapse for you, and "may or may not" is not a design. The
  result file it pointed at would never be found and the macro would have
  reported a job that had in fact finished. It now undoes JSON string escapes,
  and finds the closing quote by skipping escaped ones so a value ending in a
  backslash cannot terminate the string early.
- **The result TSV is written as ASCII, and every write names its encoding.**
  `open(path, "w")` with no encoding uses the machine's locale — cp1252 on
  Windows — so the same file would be written differently on two machines and
  read wrongly on a third. The TSV is read by VBA's `Input$`, which reads bytes
  as the ANSI code page and knows nothing about UTF-8, so a message containing
  an em dash would either fail to write or arrive as mojibake. The JSON keeps
  the full text: that is the one real cost of writing the answer twice, and it
  beats hand-rolling a JSON parser in VBA.

---

## 1.10.4

**Fixed**

- **`Bridge Listener` could not create its event handler.**
  `TypeError: interface takes exactly one argument` — Python.NET routes the
  constructor of a .NET interface subclass to the interface's one-argument cast
  unless `__namespace__` is declared **on the class**. It was at module scope,
  which does nothing. It ran anyway for one release because it was on
  IronPython, where none of these rules apply; selecting the right engine is
  what exposed it. Two faults, one hiding the other.
- **The same line was missing from `SuppressWarningsPreprocessor`** in
  `anongee_toolkit/revit/transactions.py`, which `RevitTransaction` instantiates
  when `suppress_warnings` is set. Found by an audit rather than by a failure
  and **not reproduced** — it may be that nothing has taken that path on CPython
  yet. One line either way.
- **`Bridge Check` was deadlocking itself and blaming the bridge.** It called
  `/status`, which runs as an External Event and fires only when Revit is idle —
  and Revit was busy running Bridge Check, which was blocking on the response.
  After every timeout expired it reported *"the External Event marshalling is
  not [up]"*, **which was false**: that had already been proved from Excel. The
  route is no longer called from inside Revit, because it never can be. The tool
  reads the document directly instead, which is instant and cannot deadlock.

**Added**

- `tests/test_scripts.py` now enforces the three Python.NET interface rules
  across the repository — `__namespace__` on the class, no `__init__`, and the
  class emitted once per session — scoped to the files where they apply, since
  IronPython needs none of them. Eight interface subclasses are checked, and a
  further test fails if that count ever collapses to nothing.

---

## 1.10.3

**Fixed**

- **Both bridge tools were running on the wrong Python.** pyRevit selects the
  engine from a `#! python3` shebang on the first line, and neither had one.
  Every other CPython tool in the repository does.

  Bridge Check failed outright — *"global name 'os' is not defined"*, Python 2
  wording naming a missing import while saying nothing about the missing engine
  that made it Python 2. **Bridge Listener did not fail**, because the `bridge`
  package happens to be Python 2.7-compatible: it ran, reported its commands,
  and would have died on the first job that needed openpyxl. A working tool
  with a fuse in it.
- **Bridge Check imports `os`**, which two of its functions had always used.
- Bridge Check reports which engine it is running on, first line of the report.

**Added**

- `tests/test_scripts.py` — two repo-wide checks, both of which would have
  caught the above and neither of which anything else here could:
  **every script that imports the toolkit must select the CPython engine**, and
  **no script or toolkit module may read a name it never binds**. 107 of the
  108 scripts resolve completely; the one that does not uses
  `from Autodesk.Revit.DB import *` and is exempted explicitly, so the
  exemption stays visible rather than quietly widening.

---

## 1.10.2

**Fixed**

- **The macro would not compile.** Two `Public Const` lines were written next to
  the code that used them, further down the module. VBA requires every
  module-level declaration to come **before the first procedure**, and Excel
  refused the whole thing with *"Only comments may appear after End Sub, End
  Function, or End Property"* — an error that points at the line after the
  previous procedure rather than at the misplaced declaration, and that appears
  only at import time in Excel, long after every test here has passed. There is
  now a test that reads the `.bas` and fails on any declaration below the first
  procedure.
- **Bridge Check 0.4.0 took minutes and showed nothing.** It now probes the TCP
  port first — a refused connection answers in microseconds, and when nothing is
  listening four HTTP attempts against two routes are wasted time.
  `WebClient.DownloadString` carries a hundred-second default timeout that
  cannot be set without subclassing it, so it is tried last instead of first;
  `/ping` gets five seconds and `/status` twenty, because one touches Revit and
  the other does not.
- **Bridge Check could produce no output at all**, which it did. The run is
  wrapped so its own failure becomes the report, and **the report goes to the
  pyRevit console as well as the dialog** — console output can be pasted, a
  dialog has to be retyped.

---

## 1.10.1

**Fixed**

- **`/jobs/<string:job_id>` used a route pattern pyRevit does not have.** It
  supports `<int:…>` and `<uuid:…>`, and a job id — `20260822-140311-0007` — is
  neither. The route is gone: `GET /jobs` returns the recent list and a caller
  finds its own id in it, which is what the macro did anyway. **Each route is
  now registered on its own**, so one bad pattern can never again be in a
  position to take the diagnostic routes down with it.
- **The macro raised instead of returning.** `On Error GoTo UseMsxml` followed
  by `On Error GoTo Failed` *inside* that handler does not work — **VBA does not
  leave a handler until `Resume`, `Exit` or `On Error GoTo -1`**, so the second
  was ignored and MSXML2's failure escaped as *"800c0005, the system cannot
  locate the resource specified"* with a Debug button, from a function whose
  whole job was to return failures rather than raise them. One handler per
  procedure now, no nesting, and a test that reads the `.bas` and fails on any
  handler armed inside another.
- **Bridge Check hid the reason.** "No answer" is now followed by the reason in
  the main panel rather than behind *See details*.
- **Nothing could say why nothing was listening.** `startup.py` writes a record
  to disk on every load — engine, routes registered, and any refusal — so the
  three identical-looking causes (server off, registration failed, extension
  never reloaded) can be told apart. Bridge Check reads it and names the fix.
- The macro now names the switch to flick when a post finds nothing listening,
  rather than showing the raw error.
- **`python3` is not a command on Windows**, and plain `python` hits the
  Microsoft Store alias. `bridge/README.md` says `py` for Windows now, which is
  what the python.org launcher provides.

---

## 1.10.0

**Added**

- **The bridge carries a job end to end.** An Excel button writes one, Revit
  runs it, and the answer comes back into the workbook. Stage 0 of the
  programme, closing the design left open by `DONE-1`.
- `anongee_toolkit/bridge/` — `envelope` (the command and result shapes,
  versioned), `jobs` (where a job lives on disk, from written to answered) and
  `registry` (every command declared once). Pure Python: no Revit, no openpyxl,
  and none of it importable by the IronPython route, which is the point.
- `anongee_toolkit/commands/` — where a job meets a model. Ships `bridge.echo`,
  which reads no workbook and writes nothing: every command after it has two
  things that can be wrong, the wire and the work, and this one has only the
  wire.
- **Bridge Listener** pushbutton — `Idling` to notice a job, an **external
  event** to run it. Work never happens in the Idling callback, which holds the
  UI while it runs; the callback does a timestamp check and one directory
  listing, then hands off. Claiming is an atomic rename, so two Revit sessions
  watching one folder never run the same job twice.
- `POST /anongee/jobs`, `GET /anongee/jobs`, `GET /anongee/jobs/<id>` — the
  doorbell. **No Revit argument on any of them**, so posting answers instantly
  even mid-command; a route that waited for Revit to be idle is the exact hang
  the design exists to avoid.
- **The minimal workbook** — `CONTROL`, `INFO`, `LEVELS`, `GRIDS`, `LOG`, built
  by `bridge/excel/build_workbook.py`. "Write?" starts at No on every row.
- The macro submits a job and waits for a file rather than for a response.
  **The post's answer carries the path the result will be written to**, so the
  macro never works out where the bridge folder is — a third implementation of
  those rules, in VBA and untestable, would be wrong the first time somebody
  set `ANONGEE_BRIDGE_HOME`.

**Fixed**

- `findings_from_issues` read `row_number` off a workbook `Issue`, which
  carries `row`. Every finding would have crossed the bridge without the one
  field that makes it actionable — the spreadsheet row you type into Excel's
  Name Box — and nothing would have said so. Caught by a test written against
  the real DTO rather than against the name I remembered.

---

## 1.9.1

**Fixed**

- **Bridge Check 0.2.0 could not reach the bridge at all.** The tool built to
  explain a bridge failure was the only part of the spike that failed:
  `System.Net.WebClient` needs `clr.AddReference` on .NET 8, and
  `urllib.request` is not in the CPython 3 engine's partial standard library.
  It now tries four ways — `WebClient`, `HttpClient`, `urllib`, and a
  hand-written GET over a raw socket — keeps every failure rather than only the
  last, and says which one worked.

**Changed**

- **The bridge spike is confirmed**, and it settled the engine question: pyRevit
  loads `startup.py` on IronPython 2.7, which cannot see the CPython 3 toolkit.
  So **the route is a doorbell and the worker is CPython; they share a folder,
  not a module** — which collapses the two designed transports into one, because
  HTTP becomes a faster way to write into the outbox rather than a second path.
  Written up in the architecture document §2a, and as `DONE-1` in
  [`done-list.md`](done-list.md).

---

## 1.9.0

**Added**

- **The bridge — one `.xlsm` driving a whole RCC job.** The design is in
  [`docs/specs/2026-08-22-excel-revit-platform-prd.md`](docs/specs/2026-08-22-excel-revit-platform-prd.md)
  and [`…-architecture.md`](docs/specs/2026-08-22-excel-revit-platform-architecture.md);
  the queue is [`todo-list.md`](todo-list.md). What ships here is the **spike**
  and nothing above it, because every estimate in the PRD is conditional on it.
- `AnonGee.extension/startup.py` — two HTTP routes pyRevit serves from inside
  the Revit process. `/anongee/ping` takes no Revit argument and answers even
  while Revit is busy; `/anongee/status` declares `uiapp`, so pyRevit runs it as
  an External Event. **Two routes on purpose:** ping answering while status does
  not says the server is up and the marshalling is not, which one route cannot
  tell you. Nothing in the file may raise — a startup script that throws takes
  pyRevit's load with it.
- **Bridge Check** pushbutton — calls the same two URLs from inside Revit, so
  when Excel gets no answer the network is out of the question. Reaches the wire
  through `System.Net` before `urllib`, because the CPython 3 engine ships a
  partial standard library and the diagnostic tool should not bet on it.
- `bridge/excel/modAnonGeeBridge.bas` — the Excel end, and deliberately small.
  The command envelope carries *which sheet*, not the data, so the macro
  marshals nothing and cannot get the data model wrong.

---

## 1.8.0

**Changed**

- **RC Automation 0.7.0** — bends stay inside the rebar cover, a varying set is
  tied to the sloping face its bars actually end on, each footing face gets its
  own cover type instead of the top face's, and the project's own identity
  parameters (`ID`, `ID_LIC`, `ID_V`, `ITEM`, `LEVEL_V`, plus `Host Category`
  and `Host Mark` on bars) are filled in — with a Parameters box choosing
  whether missing ones are created as shared parameters or left alone. See
  [`RC Automation.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md).

**Added**

- `anongee_toolkit.rc_automation.identity` — what goes in the schedule's
  identity fields, derived from the workbook and testable without Revit.
- `anongee_toolkit.structural.element_params` — reading, creating and writing
  those fields against a document.

---

## 1.7.0

**Changed**

- **RC Automation 0.6.0** cuts a reinforcement layer at the outline's vertices
  and gives each stretch its own set, because a set cannot follow a change of
  slope; fixes the two reasons cover was created and never applied; and reads
  back what Revit actually did with a distribution instead of reporting what it
  asked for.

---

## 1.6.0

**Added**

- **`REVIT_API_RESEARCH.md`** at the repository root — what the Revit 2025/2026
  reinforcement API actually offers, written after a real run's error message
  showed the constraint code was aimed at free-form rebar while every bar this
  tool places is shape-driven. Covers the shape-driven constraint flow, varying
  sets, how the manual detailing workflow maps onto the API, and a dozen other
  calls worth having — including one that may overturn the phase 3 plan.

**Changed**

- **RC Automation 0.5.0** constrains bars through the shape-driven API, places a
  varied area as one varying set, names cover types for the element and creates
  them once, shows placed bars instead of hiding them, and puts the run's
  failures in the exported report as well as the window.

---

## 1.5.0

**Changed**

- **RC Automation 0.4.0** bends the bars, keeps them inside the concrete, writes
  the scheduled cover onto the footing, and constrains the reinforcement to it so
  editing a footing updates its steel. Full history in its own
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md).

---

## 1.4.0

**Changed**

- **RC Automation 0.3.0 creates footings.** "Create structure and reinforcement"
  builds the pads a schedule places and then reinforces them, both halves in one
  `TransactionGroup` so reversing the run does not leave bare footings behind.

  Pads are floors, so a non-rectangular `Outline` is sketched as drawn rather
  than approximated, and every one is flagged structural — without which Revit
  accepts no reinforcement and nothing looks wrong. Level names are matched
  rather than demanded: `Ground` finds `00 Ground Lvl.` and `Level 1` finds
  `01 1st Floor Lvl.` by storey number, with an optional `LEVELS` sheet for the
  ones matching cannot reach. Full history in its own
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md).

---

## 1.3.0

**Changed**

- **RC Automation 0.2.0 places reinforcement.** The first release read and
  reported only; this one writes, into footings that already exist. Creating the
  structure itself needs the placement sheets and is not in this build, so
  Create is reachable only in "Reinforce existing structure".

  A plan is worked out and shown in full before a transaction exists, so what is
  about to happen can be read and refused. The run is then one
  `TransactionGroup`, assimilated into a single undo step, chunked so a failure
  rolls back its chunk and the rest carries on. A footing that already carries
  reinforcement is left alone, and "Replace mine" rebuilds only the bars this
  tool stamped. Full history in its own
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md).
- **Delimited schedules in one file.** A `.csv` or `.txt` holding every sheet,
  separated by `#SHEET,<name>` rows, alongside the folder-of-sheets layout.

---

## 1.2.0

**Added**

- **RC Automation** (Dev panel) — reads an Excel reinforcement schedule, checks
  it, and reports what the open model would give it. Shipping at its own version
  0.1.0, and deliberately **read-only**: it opens no transaction and creates
  nothing.

  Everything hard about driving reinforcement from a schedule is downstream of
  questions nobody had answered inside Revit yet — whether the CPython 3 engine
  imports the toolkit, whether the bundled openpyxl loads, whether the modeless
  bridge holds, whether the levels and bar types a schedule names are present,
  and whether the elements it would host into can take reinforcement at all.
  Finding that out during a four-hundred element write is the expensive way
  round, so this build answers it first.

  Validates against BS 8666:2020 and reports every finding against the cell it
  came from. Works out what the schedule would build without building it,
  including whether a layer can ship as one Revit element or has to be
  individual bars. Full history in its own
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/col2.stack/RC%20Automation.pushbutton/CHANGELOG.md).
- **`anongee_toolkit.rc_automation`** — the schedule layer, with no Revit in it:
  workbook reading, validation, reconciliation against a model, and bar
  geometry. 343 tests now run without Revit.

---

## 1.1.0

**Added**

- **Auto Level Manager** (Essential panel) — a modeless window for level work,
  shipping at its own version 2.0.0. Reads level marks out of drawing text
  from the active view, the Revit selection, a DXF, or a paste box; infers the
  drawing's unit from the storey heights the numbers imply; cross-checks each
  text against where it sits on the sheet. Adds, renames, re-spaces and deletes
  levels, with the stack drawn to scale and editable in place. Nothing reaches
  the model until Apply, which lands as one undo step. Full history in its own
  [changelog](AnonGee.extension/AnonGee.tab/Essential.panel/AutoLevel.pushbutton/CHANGELOG.md).
- **A test suite that runs without Revit**, at `tests/`. Tools that keep their
  logic in plain Python modules can have that logic argued with on any machine:

      python -m unittest discover -s tests -v

  184 tests today, covering the Auto Level Manager's text detection, naming,
  plan model and drawing camera, plus static checks on its XAML that catch the
  class of fault that is well-formed XML and a dead window.
- **Per-tool changelogs**, as a convention: a tool with its own version keeps a
  `CHANGELOG.md` beside its `bundle.yaml`, and tests hold the version in the
  package, the bundle tooltip, the changelog heading and the window header to
  the same value so they cannot drift.
- **Packaged Windows Setup delivery** for Revit 2025 x64. The installer carries
  the tested CPython 3.12 runtime dependencies inside `AnonGee.extension`, so
  end users do not need standalone Python or pip. It can provision the pinned
  signed pyRevit 6.5.5 prerequisite when pyRevit is missing, and can repair an
  incompatible per-user pyRevit installation after explicit user approval.

**Changed**

- The README now lists every button actually on the ribbon. It had drifted:
  nine tools were shipping and undocumented.
- AnonGee Setup now uses the extension's **1.1.0** product version instead of
  the earlier installer-development `0.1.0` identity. Windows Installed Apps,
  the Setup EXE filename and generated release metadata therefore identify the
  same product version as `extension.json` and this changelog.
- The pyRevit compatibility metadata now declares a minimum of **6.1.0**. The
  installer keeps the more precise compatibility policy: 6.4.x is blocked,
  6.5.5 is the current confirmed working prerequisite, and newer unvalidated
  6.x versions use the installer warning policy.
- Installer support/user-data paths are separated from the pyRevit extension
  path: installer support files live under `%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit`,
  roaming settings under `%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit`, while the
  extension remains under `%APPDATA%\pyRevit\Extensions\AnonGee.extension`.
- The release pipeline now validates the pinned pyRevit installer hash,
  compiles Inno Setup from one command, records source/compiler/artifact
  provenance, and requires a clean Git source tree by default for a
  release-ready artifact.

## 1.0.0

The extension as it stood before this changelog began — the four panels, the
shared WPF design system in `Resources/`, the bundled `lib/py2` and `lib/py3`
libraries, and the `anongee_toolkit` package behind cad2bim and friends.

The tools at that point: **Essential** — bulk delete and bulk rename for fill
patterns, line patterns and line styles; obscured rebar and copy rebar
visibility; self dimension, export schedule and rotate column; unjoin by
category, toggle linked and join priority; round element distances, draw floor
and convert slab. **Advance** — one filter parameter, multi filter parameter
and parameter combination. **Core** — BIM generation from INP, FramewinToBIM,
and cad2bim. **Dev** — BBS generator, brand guidelines, the CPython 3 engine
health check, create button, and the modeless window reference.

Per-tool history from before this file is in the git log rather than
reconstructed here; `progress.md` carries the detailed record of the cad2bim
work up to v0.68.0.
