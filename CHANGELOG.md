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
