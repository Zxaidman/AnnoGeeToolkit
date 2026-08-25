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
| RC Automation | 0.7.0 | [`RC Automation.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md) |

Both levels use [semantic versioning](https://semver.org), read from the point
of view of someone using the thing rather than someone reading the diff:

| Part      | For the extension                                                                                 | For a tool                                                                       |
| --------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **MAJOR** | A tool was removed or renamed, the tab was reorganised, or an installation step changed.          | The tool behaves differently on purpose — a workflow moved, or what it writes to the model changed shape. |
| **MINOR** | A tool was added, or an existing one gained a capability.                                          | A new capability. Everything you already did still works.                        |
| **PATCH** | Fixes only.                                                                                        | A fix. Nothing new to learn.                                                     |

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
  [`RC Automation.pushbutton/CHANGELOG.md`](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md).

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
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md).

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
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md).

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
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md).
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
  [changelog](AnonGee.extension/AnonGee.tab/Dev.panel/RC%20Automation.pushbutton/CHANGELOG.md).
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

**Changed**

- The README now lists every button actually on the ribbon. It had drifted:
  nine tools were shipping and undocumented.

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
