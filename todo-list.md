# AnonGee Bridge — todo list

The programme queue: one `.xlsm` driving a whole RCC job in Revit. See
[`docs/specs/2026-08-22-excel-revit-platform-prd.md`](docs/specs/2026-08-22-excel-revit-platform-prd.md)
for what is being built and how much of it is realistic, and
[`…-architecture.md`](docs/specs/2026-08-22-excel-revit-platform-architecture.md) for how a button in
Excel becomes a transaction in Revit.

## How this file works

| § | Section | What belongs in it |
| --- | --- | --- |
| 1 | **Critical** | Blocks the other implementation. Nothing ships until every one is closed or deliberately deferred. |
| 2 | **Errors and bugs** | Something is wrong now. Each carries how it was found and whether it is reproduced. |
| 3 | **Features** | New capability. Each is separable and can be scheduled on its own. |
| 4 | **Working now** | What is built and verified, so nobody rebuilds it and nobody claims more than was measured. |
| 5 | **Pending scope** | Agreed direction, not yet started. |
| 6 | **Owner's list** | Reserved for what the project owner sends next, and everything after. |

**Every entry has an ID** (`CRIT-1`, `BUG-3`, `FEAT-7`) so it can be referred to in one word.

**Every entry carries a phase**, so the state of the queue is readable without asking:

| Phase | Meaning |
| --- | --- |
| `pending` | Not started. |
| `building` | Being written now. |
| `testing` | Built and in a build the project owner can test; waiting for in Revit result. |
| `superseded` | It worked, and something else replaced it. Recorded rather than deleted — what it cost to build is part of the record. |
| `failed` | Tested in Revit and wrong. It stays here, carrying what was seen, and does not reach `done-list.md`. |
| `redo` | Failed, and being rebuilt. Deliberately not the same as `building` — something was built once and did not survive contact with a model, and that is worth being able to count. |
| `done` | Confirmed on the in Revit, and copied into `done-list.md` with what was done. |

An item leaves this file only by reaching `done`, and it is described in `done-list.md` when it
does. Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this file
before it is built, argued about, or written into any other document. Standing instruction from the
project owner, and it is what keeps this list the queue rather than a summary of one.

### The build record

Standing instruction from the project owner: **keep a record of what is built, tested, done, failed
and redone.** One row per thing that ends up in a model, so the question *where are we* is answered
by reading rather than by asking.

It is a view of the entries below, not a second queue — every row names the ID that owns it, and the
ID is where the detail lives. Four words, meaning exactly four things:

| Word | What has to have happened |
| --- | --- |
| **Built** | The code is in the repository and the suite is green. Worth nothing on its own. |
| **Tested** | The project owner ran it in Revit, against a model, and sent back what happened. |
| **Done** | The owner said it was right. Only this reaches `done-list.md`. |
| **Failed / redo** | It was tested and it was wrong, and how many times. Counted, because a thing that took four rounds is telling us something about the next thing like it. |

| Thing | Command | Built | Tested in Revit | Done | Failed → redone | ID |
| --- | --- | --- | --- | --- | --- | --- |
| The wire — Excel posts, Revit runs, Excel reads the answer | — | 1.10.0 | yes, five jobs round-tripped | **yes** | 0 — but 4 rounds lost to bugs *in the diagnostic*, not the bridge | DONE-1..4 |
| Sample project workbook — Foundation + G + 4 | — | 1.14.0 | **not yet — the format is the thing being reviewed** | no | 0 | FEAT-22 |
| Levels | `levels.sync` | yes | dry run only: `created=2 matched=1 modified=1 written=0` | no — the write path has never run | 0 | FEAT-5 |
| Grids | `grids.sync` | yes | **never run** | no | 0 | FEAT-6 |
| Footings | `footings.sync` | declared, not written | — | no | 0 | FEAT-23 |
| Columns | `columns.sync` | declared, not written | — | no | 0 | FEAT-10 |
| Beams | `beams.sync` | declared, not written | — | no | 0 | FEAT-11 |
| Slabs | `slabs.sync` | declared, not written | — | no | 0 | FEAT-13 |

**Declared, not written** is a deliberate third state and not a synonym for missing. The name and
the sheet are in `registry.py`, so the workbook can carry the button and the button answers *declared
but not built yet*. A test holds the registry, the `Built?` column on `CONTROL` and the macros
together, which means that column cannot quietly start claiming more than has been built.

The order is the owner's: **level, grid, column, footing, beam, slab**, one at a time, each confirmed
in a model before the next is started.

### Two queues, and which is which

| File | Scope |
| --- | --- |
| **this file** | The programme — the bridge, the templates, and every command from `levels.sync` to shop drawings. |
| `AnonGee.extension/AnonGee.tab/Dev.panel/RC Automation.pushbutton/todo-list.md` | RC Automation only. It becomes a module of this programme; its queue stays where the tool is. |

**An ID is unique within its file.** A reference across files is written in full —
*RC Automation · BUG-4*. Same rules, same phases, both files.

**Verified means one thing in both:** the project owner ran it in Revit and said so. A green test
suite is not verification — every bug this repository has shipped passed the suite on the way to a
model.

---

## 1. Critical

### CRIT-2 — neither template exists, and neither can be generated from here · `pending`

**`template.rvt`.** No library outside Revit writes a `.rvt`. The deliverable is a written
specification of what it must contain — families, view templates, title blocks, the shared parameter
file bound to the right categories, object styles, filters — plus a pyRevit tool, **Build Template**,
that runs *inside* Revit against an out-of-the-box template and produces the rest. The owner runs it
once and does a Save As.

**`template.xlsm`.** `openpyxl` preserves an existing `vbaProject.bin` with `keep_vba=True` and
cannot create one. So the VBA lives in the repository as `.bas` source, reviewable in a diff; the
owner imports it into a blank `.xlsm` **once**; from then on a build script regenerates every sheet
into it and the macros survive.

Both are one manual step each, once. Neither is a limitation that can be coded around, and pretending
otherwise wastes a session.

### CRIT-3 — one envelope, one registry · `testing`

**Built** (extension 1.10.0). `anongee_toolkit/bridge/` holds `envelope`, `jobs` and `registry`;
`anongee_toolkit/commands/` holds what runs. `filedrop.py` was never written and is not needed —
`CRIT-4` collapsed the two transports into one, so the outbox *is* the transport and `jobs.py` owns
it.

**A command is declared once, in `registry.py`.** The `CONTROL` sheet, the macro and the registry
are held to the same three names by a test, because that is exactly the contract that rots.

**To close it:** run `bridge.echo` from the workbook and see a `LOG` row.

---

## 2. Errors and bugs

### BUG-1 — Bridge Check could not reach the wire at all · `testing`

**Found by the `CRIT-1` run.** The pushbutton that exists to diagnose the bridge could not call it:

> `no answer — Cannot import name WebClient / No module named request`

Two separate mistakes, both mine, and both worth keeping:

- `from System.Net import WebClient` works on .NET Framework and **not on .NET 8**, which Revit 2025
  runs on — the class lives in its own assembly and has to be asked for with `clr.AddReference`.
- `urllib.request` is simply absent. The CPython 3 engine ships a partial standard library; `re` and
  `csv` were the two known missing, and this is a third.

**Reproduced:** yes, on the first run.

**Fixed in Bridge Check 0.2.0, unconfirmed.** Four ways are now tried in order — `WebClient`,
`HttpClient`, `urllib`, and a hand-written GET over a raw socket — every failure is kept rather than
only the last, and **the answer says which one worked**. That last part is not tidiness: what the
CPython engine can reach the network with is a thing every later part of the bridge needs to know.

### BUG-3 — a bad route pattern could take the diagnostic routes with it · `done`

**Confirmed 2026-08-24.** `/ping` answered from Excel reporting `bridge 0.3.0`,
so the rebuilt registration loaded and every route took. Moved to `done-list.md`
as part of `DONE-3`.

<details><summary>the original entry</summary>

**Found by a run**: both `/ping` and `/status` reported *no answer* from a session
where they had worked the day before, and the Bridge Listener was fine.

`/jobs/<string:job_id>` used a pattern pyRevit does not have — it supports
`<int:…>` and `<uuid:…>`, and a job id like `20260822-140311-0007` is neither.
Whether that actually killed the earlier routes or whether the Routes server was
simply switched off **could not be told apart**, which is the real fault: five
routes were decorated in a row with nothing between them.

**Reproduced:** the pattern is wrong either way — confirmed against pyRevit's
own documentation and a forum thread titled *"Route pattern is invalid"*.

**Fixed.** The route is gone; `GET /jobs` returns the list and a caller finds
its own id in it, which is what the macro did anyway. Each route is registered
on its own now, so one refusal cannot reach the others.

</details>

### BUG-4 — the macro raised instead of returning · `testing`

**Found by a run**: `Run-time error -2146697211 (800c0005): The system cannot
locate the resource specified`, with a Debug button, out of a function whose
entire job was to return failures rather than raise them.

**Cause, and it is a classic:** `On Error GoTo UseMsxml`, then
`On Error GoTo Failed` *inside* that handler. **VBA does not leave an error
handler until `Resume`, `Exit` or `On Error GoTo -1`**, so the second was ignored
and MSXML2's failure escaped unhandled.

**Reproduced:** yes, once, and it is deterministic — it happens on the first
failure of the first transport, every time.

**Fixed, unconfirmed.** One handler per procedure, no nesting, and a test that
reads the `.bas` and fails on any handler armed inside another. The trap cannot
recur because there is nothing left to nest.

### BUG-5 — nothing could say why nothing was listening · `testing`

**Found by the same run.** Three causes look identical from Excel and from
Revit: the Routes server switched off, the startup script failing to register,
or the extension never reloading. They need three different fixes and a dead
port distinguishes none of them.

Worse, Bridge Check reported *"no answer"* with the cause folded away behind
*See details*, which nobody expands — **the tool built to explain a failure
explained nothing, for the second release running.**

**Fixed, unconfirmed.** `startup.py` writes a record to disk on every load —
engine, routes registered, any refusal — precisely because when *it* is the
guilty one there is no route left to ask. Bridge Check reads it, names which of
the three it is, and puts the reason in the headline.

### BUG-6 — `python3` is not a command on Windows · `testing`

**Found by the owner running the documented command**: plain `python` hits the
Microsoft Store alias — *"Python was not found; run without arguments to install
from the Microsoft Store"* — and `python3` does not exist. They worked around it
with VS Code and a full interpreter path.

**Fixed in the documentation, unconfirmed.** `bridge/README.md` now says `py` for
Windows, which is the launcher the python.org installer provides, and names the
Store-alias error so it is recognisable.

### BUG-7 — the macro would not compile · `testing`

**Found by the owner importing it**: *"Compile error: Only comments may appear
after End Sub, End Function, or End Property."*

Two `Public Const` lines were written next to the code that used them, further
down the module. **VBA requires every module-level declaration to come before
the first procedure.** The error names the line after the previous procedure
rather than the misplaced declaration, so it points at innocent code — and it
appears at import time in Excel, long after everything here has passed.

**Reproduced:** yes, deterministically. Both declarations found by scanning the
file; only the first was in the error.

**Fixed, unconfirmed.** Every declaration is above the first procedure, under a
banner saying it has to stay there, and a test reads the `.bas` and fails on any
that is not.

**The `.xlsm` in the repository still carries the old module.** Re-import
`modAnonGeeBridge.bas` — this fix and `BUG-4` are both in it.

### BUG-8 — Bridge Check took minutes and showed nothing · `testing`

**Found by the owner**: *"bridgeCheck took so long to execute and nothing output
it in console empty."*

Two faults, and the second is worse than the first.

**Slow:** four ways to the wire, tried twice, with nothing listening. And
`WebClient.DownloadString` carries a **hundred-second default timeout** that was
never set — it cannot be set without subclassing `WebClient` — and it was tried
first.

**Silent:** the console was empty because nothing was ever printed, and the
dialog is the only output. **A diagnostic that can produce no output is broken
by definition**, and this one could.

**Reproduced:** by reading it. The timeout is documented .NET behaviour and the
absence of any `print` is plain in the source.

**Fixed, unconfirmed.** The TCP port is probed first — a refused connection
answers in microseconds, so when nothing is listening no HTTP is attempted at
all. `WebClient` is tried last, `/ping` gets five seconds and `/status` twenty,
the whole run is wrapped so its own failure becomes the report, and **the report
prints to the pyRevit console** as well as the dialog. Console output can be
pasted; a dialog has to be retyped, which is how the last three rounds of
findings arrived — one of them as a screenshot of a collapsed panel that said
nothing.

### BUG-9 — both bridge tools ran on the wrong Python · `testing`

**Found by the owner running Bridge Check**: *"global name 'os' is not
defined"* — and the wording is the finding. *"global name"* is Python 2, so the
tool was on IronPython 2.7, not the CPython 3 engine everything else here uses.

pyRevit selects the engine from a `#! python3` shebang on the first line.
**Neither bridge tool had one.** Every other CPython tool in this repository
does; these two were written without it and nothing said so.

**Bridge Check failed outright** — it uses `os` in two functions and never
imported it, which on the right engine would still have been a bug and on the
wrong one was the only symptom visible.

**Bridge Listener did not fail, and that is worse.** It imports the toolkit from
`lib/py3`, which is not on IronPython's path — but the `bridge` package happens
to be Python 2.7-compatible, so it started, reported its commands, and would
have died on the first job that needed openpyxl. **A working tool with a fuse in
it** is the worst thing a missing line can produce.

**Reproduced:** yes, and then confirmed statically across the whole repository —
one script imported the toolkit without the shebang, and it was the listener.

**Fixed, unconfirmed.** Both carry `#! python3`; Bridge Check imports `os` and
now reports which engine it is on, first line of its report.

**Guarded properly**, because neither fault was catchable by anything that
existed: `tests/test_scripts.py` fails if a script imports the toolkit without
selecting the engine, and fails if any script or toolkit module reads a name it
never binds. 107 of 108 scripts resolve completely; the one that does not uses a
star import and is exempted by name so the exemption cannot quietly widen.

### BUG-10 — the listener could not create its event handler · `testing`

**Found by the owner's run**, once `BUG-9` put it on the right engine:
`TypeError: interface takes exactly one argument`, at
`_state.handler = BridgeJobHandler()`.

Python.NET routes the constructor of a .NET interface subclass to the
interface's one-argument cast unless `__namespace__` is declared **on the
class**. I put it at module scope, where it does nothing at all.

**This repository's own brand guidelines state the rule and quote this exact
error.** §12.8.7.1, rule 1 of three.

**Reproduced:** yes, and then found statically — an audit of every
Revit-interface subclass in the repository turned up two more.

**It ran for a release anyway**, because it was on IronPython, where none of
these rules apply. `BUG-9` and this one were hiding each other: fixing the
engine is what made this visible, and until then the tool looked correct.

**Fixed, unconfirmed.** `__namespace__` on the class, and `claimed` as a class
attribute since rule 2 forbids the `__init__` that would otherwise set it.

**Guarded repo-wide**, since one instance of a documented rule being missed
means the rule needs a test rather than a paragraph: `tests/test_scripts.py`
checks all three rules across every interface subclass, scoped to the files
where Python.NET applies — IronPython needs none of them, and one script here
relies on that.

### BUG-11 — `SuppressWarningsPreprocessor` is missing the same line · `testing`

**Found by the audit for `BUG-10`**, not by a failure.
`anongee_toolkit/revit/transactions.py` declares no `__namespace__`, and
`RevitTransaction` instantiates it whenever `suppress_warnings` is set — which
on CPython should raise the same `TypeError`.

**Not reproduced.** It may be that nothing has taken that path on CPython yet.
Recorded honestly rather than claimed: the line is added because it is the rule,
not because a failure was seen.

### BUG-12 — Bridge Check deadlocked itself and blamed the bridge · `testing`

**Found in the owner's pasted console output**, which is the first round of
findings that arrived as text rather than a screenshot — and it is why this was
diagnosable at all.

`/status` declares `uiapp`, so pyRevit runs it as an External Event, which fires
only when Revit is **idle**. Revit was not idle: it was running Bridge Check,
which was blocking on the response. The two waited for each other until every
timeout expired — HttpClient, raw socket, urllib, then WebClient's unbounded
hundred seconds.

**Then it reported the wrong conclusion**: *"Ping answered and status did not.
The server is up and the External Event marshalling is not"*. **That is false.**
The marshalling was proved from Excel in `DONE-1` and has never stopped working.
The diagnostic invented a fault in the thing it was diagnosing.

**Reproduced:** yes, and it is structural — a tool inside Revit can *never*
call that route successfully.

**Fixed, unconfirmed.** `/status` is not called from inside Revit at all. The
document is read directly from `__revit__`, which is what that route would have
said and is instant. The report explains the absence and points at Excel.

### BUG-13 — the macro could not open the result it was told to wait for · `testing`

**Found by reading the path, not by running it** — while the first `Run_Echo`
was in flight, on the reasoning that four rounds of round trips is expensive and
this one was worth spending on the page instead.

The post's answer carries `resultTsv`, and **JSON doubles every backslash in a
Windows path**. `JsonValue` returned it verbatim: `C:\\Users\\praka\\…`.
Windows may or may not collapse doubled separators, and "may or may not" is not
a design.

**What it would have looked like:** the job runs, the result is written, and the
macro sits for five minutes and reports *"no result — is Bridge Listener
switched on?"* — pointing at the one thing that was working.

**Reproduced:** by porting the two VBA functions line for line and running them
against what the route actually sends. That port is now a test.

**Fixed, unconfirmed.** `JsonUnescape`, and a closing-quote scan that skips
escaped quotes so a value ending in a backslash cannot end the string early.

### BUG-14 — the result file's encoding was whatever the machine felt like · `testing`

**Found in the same read.** `open(path, "w")` with no encoding uses the locale's
— cp1252 on Windows — so the same file is written differently on two machines
and read wrongly on a third.

The TSV is read by VBA's `Input$`, which reads bytes as the ANSI code page and
knows nothing about UTF-8. A finding containing an em dash — and `bridge.echo`'s
own note contained one — would either fail to write or arrive in the spreadsheet
as mojibake.

**Fixed, unconfirmed.** The TSV is ASCII with anything else replaced; the JSON
keeps the full text and names UTF-8. That split is the one real cost of writing
the answer twice, and it is still cheaper than a JSON parser in VBA.

### BUG-15 — the macro's dialogs showed mojibake · `testing`

**Found in the owner's screenshots of the first successful job**: every dialog
ended `0 finding(s) a-hat-euro see the FINDINGS sheet.`

Two em dashes in message strings. **Excel imports a `.bas` as the machine's ANSI
code page**, not UTF-8, and there is nowhere in that format to declare
otherwise — so a file crossing into VBA must not need an encoding at all.

The same lesson as the result TSV two rounds earlier, one layer further out, and
I did not carry it across at the time.

**Reproduced:** by reading the bytes — six above 127, on two lines.

**Fixed, unconfirmed.** The module is pure ASCII and a test fails on any byte
above 127 in it.

### BUG-2 — the Routes server listens on every interface · `pending`

**Found while reading the settings panel**, which reports `listening on http://0.0.0.0:48884`;
pyRevit's own example URL is a LAN address rather than a loopback one.

**The bridge is reachable from any machine on the network, and its commands write to a live model.**
On one workstation that is harmless. Before this leaves one desk it is not.

**Not reproduced** — it does not need to be; `0.0.0.0` is the server telling us. Recorded as a bug
rather than a note because the default is open and nobody chose it. Three possible answers, and one
has to be picked rather than discovered: bind to loopback if pyRevit allows it, firewall the port,
or require a shared token in the envelope.

Nine open bugs live in *RC Automation · §2*, and two of them (`CRIT-1`, `CRIT-2` there — constraints
never confirmed applied, varying sets not varying) are the deepest technical risk in the whole
programme, because stage 5 is built on them.

---

## 3. Features

Each carries the verdict from the PRD, so the queue and the estimate cannot drift apart.

### The workbook and the bridge

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-1 | `CONTROL` sheet — a button per operation, with mode, dry-run, last-run status and findings count | **Built, `testing`.** `Write?` is `No` on every row, so a first press reports and touches nothing | `testing` |
| FEAT-2 | VBA: post a job, wait for the result, write the `LOG` row | **Built, `testing`.** No JSON parser was needed after all — Revit writes the result twice, `.json` for machines and `.tsv` for Excel, and the macro reads lines. Colouring the source rows is still to do | `testing` |
| FEAT-3 | **Build Template** pyRevit tool, and the written `.rvt` specification | Medium. The specification is the harder half | `pending` |
| FEAT-22 | **Sample project workbook** — a whole Foundation + G + 4 frame, generated from constants by `bridge/excel/build_sample_project.py` | **Built, `testing`.** 24 m x 12 m, grids A–E and 1–3 at 6 m, seven levels, six storeys: 7 levels, 8 grids, 15 footings, 90 columns, 132 beams, 6 slabs. Its point is the **format** — every placement sheet names a grid intersection and leaves the coordinates as the fallback, and a column that rises six storeys is six rows. Waiting on the owner's keep / add / remove | `testing` |
| FEAT-4 | `template.xlsm` build script — sheets, validation, `keep_vba=True` | **Built, `testing`.** `bridge/excel/build_workbook.py` writes `CONTROL`, `INFO`, `LEVELS`, `GRIDS`, `LOG`. One manual step remains and always will: `openpyxl` preserves a VBA project and cannot create one | `testing` |

### Datum and setup

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-5 | `levels.sync` | **Built, `testing`.** Rules in `rc_automation/datum.py`, tested off Revit: never delete, never rename, never fill an occupied elevation, match by name only. Idempotence is the acceptance test and there is one for it | `testing` |
| FEAT-6 | `grids.sync` | **Built, `testing`.** Angle column (0 along +X, 90 along +Y), both-ends or start-and-angle, position synced but extent not, a turned grid reported rather than redrawn. **The fiddly tail is still ahead**: bubble ends and 3D extents are per-view and belong with `FEAT-8` | `testing` |
| FEAT-7 | `types.sync` — duplicate, parameterise, load from a library | **Partly possible, and the boundary matters.** Duplicating and loading covers most of a real job. **Authoring a family from a spreadsheet is not on the table** — the template carries the families | `pending` |
| FEAT-8 | `views.sync` — plans, sections, 3D, templates, scope boxes, crops, filters | **Yes, medium.** The workbook supplies the judgement so the code does not guess | `pending` |
| FEAT-9 | `sheets.sync` — sheets, viewports, title block parameters | **Yes, medium.** Placing a viewport is arithmetic, not research | `pending` |

### Structure

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-23 | `footings.sync` — the bridge route to the footing placement RC Automation already does | Straightforward, and mostly already written. The pad-as-structural-floor path ships and is confirmed in a model; what is new is reading `FOOTING_PLACEMENT` and resolving a grid intersection to a point | `pending` |
| FEAT-10 | `columns.sync` — `NewFamilyInstance` between two levels | Straightforward. Closes *RC Automation · CRIT-3*, where every run claims to place columns and places none | `pending` |
| FEAT-11 | `beams.sync` | Medium. Creation is easy; joins and cutbacks are fiddly | `pending` |
| FEAT-12 | `walls.sync` | Medium | `pending` |
| FEAT-13 | `slabs.sync` — the footing path generalised | Straightforward. `Floor.Create` from an outline already ships | `pending` |

### Numbers

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-14 | `schedules.sync` — build Revit schedules with fields, filters, sorting, formatting | **The easiest win on the list.** No geometry, no judgement. Worth doing early for the feedback loop it gives everything else | `pending` |
| FEAT-15 | QTO write-back — Revit writes `qto.json`, the macro loads it into the `QTO` sheet | Straightforward. **Revit must never write into the open `.xlsm`** | `pending` |
| FEAT-16 | Costing — rates and totals in Excel, quantities from Revit | **Yes, by not doing it in Revit.** Calculated-value expressions are weak and a rate library belongs where a QS can see it | `pending` |

### Reinforcement, drawings, and after

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-17 | Rebar beyond footings — beams, columns, walls | **Yes, and the slowest item in the programme.** Footings alone have taken seven versions and their constraints are still unconfirmed. Each element type needs its own layout engine. Quarters, not weeks | `pending` |
| FEAT-18 | `tags.sync` | **Partly, and the gap matters.** Tagging everything is a morning. Tagging so nothing overlaps and the drawing is issuable is where every auto-tagging tool underdelivers. Expect placed-then-adjusted, improving per release | `pending` |
| FEAT-19 | Shop drawing assembly | **The hardest thing on the list, by a distance.** `Dimension.Create` needs stable geometric `Reference`s, and getting them for rebar and element faces is fragile and moves between Revit versions. Realistic first target: sheets, views, crops, schedules and most tags automatic; dimensions by hand | `pending` |
| FEAT-21 | **Bridge Listener as a modeless window** | **Built, `testing`.** Shows watching/stopped, the folder, which commands are ready, and jobs as they arrive with their counts — refreshed once a second, touching no Revit API. Closing it stops the watching. The dialog survives as a fallback | `testing` |
| FEAT-20 | MCP layer over the same `/anongee/jobs` endpoints | Straightforward **because it is deliberately last.** A solved shape — `revit-mcp-python` is a FastMCP server forwarding to pyRevit Routes. Costs nothing today beyond keeping the command surface small and named | `pending` |

---

## 4. Working now

What the programme inherits, already confirmed in Revit. Described in *RC Automation · done-list.md*.

| ID | What | Why it matters here | Phase |
| --- | --- | --- | --- |
| WORK-1 | The pure / Revit split — `rc_automation/` has no Revit in it and carries 575 tests; `structural/` touches Revit and is checked statically | **The reason this programme is affordable.** Every new command follows the same seam: parse and plan in the pure half, write in the Revit half | `done` |
| WORK-2 | External-event marshalling with a FIFO queue, proven in a modeless window | The bridge reuses it rather than inventing a second one. It is the answer to the constraint everything else is built around | `done` |
| WORK-3 | A workbook reader across six formats | The envelope carries *which sheet*, not the data, because this exists | `done` |
| WORK-4 | Validation that names the cell it came from | The finding shape the result envelope uses unchanged | `done` |
| WORK-5 | One undo step per run — chunked, assimilated | Extends to every command with no change | `done` |
| WORK-6 | Identity fields on everything built, plus never deleting what the tool did not create | Extends to every element type with no change | `done` |
| WORK-7 | A text report as the tool's only witness | Two of the last three bugs were found by reading one against a model | `done` |

---

## 5. Pending scope

### SCOPE-1 — the staging, in order · `pending`

Each stage ends with something the owner can use. Nothing starts until the stage before it is
confirmed in a model.

| Stage | Ships | Items |
| --- | --- | --- |
| 0 · Bridge spike | ~~the wire~~ **done** · ~~the doorbell and the listener~~ **built, unrun** | ~~CRIT-1~~ → DONE-1 · ~~CRIT-4~~ · CRIT-3 `testing` |
| 1 · Datum | Both templates; levels; grids | CRIT-2, FEAT-1..6 |
| 2 · Setup | Types, views, sheets | FEAT-7, 8, 9 |
| 3 · Structure | Columns, beams, walls, slabs | FEAT-10..13 |
| 4 · Numbers | Schedules, QTO, costing | FEAT-14, 15, 16 |
| 5 · Reinforcement | RC Automation grows up | FEAT-17, and RC Automation's own queue |
| 6 · Drawings | Tags, shop drawings, MCP | FEAT-18, 19, 20 |

### SCOPE-2 — C#, and the two conditions that would change the answer · `pending`

**Recommendation: no, and not now.** The toolkit is Python and works; the pythonnet traps are found,
written down and covered by tests; and **pyRevit already provides the one thing a C# add-in was
going to be needed for** — a server inside Revit that receives commands from outside. That was the
strongest argument for C#, and CRIT-1 answers it.

Two conditions would change this, and both should be **checked rather than assumed**:

1. The tool has to run somewhere pyRevit cannot be installed — which matters if this is ever sold.
2. A stage-3 or stage-5 run on a real project model is measurably too slow, *after profiling*.

If either lands, the move is a **small** C# add-in hosting the listener and the hot loops — not a
second implementation of the toolkit in a second repository.

### SCOPE-3 — round-trip conflict rules beyond the workbook · `pending`

Stage 4 sends numbers back from the model. The reconcile rule (workbook wins by default, the user
can say otherwise) covers a disagreement about an input. It does not yet say what happens when the
model has elements the workbook has never heard of, which is the normal state of a live project.

### SCOPE-4 — multi-user and worksharing · `pending`

Two people with the same workbook open, or one central model. `WorksharingUtils.GetCheckoutStatus`
is already queued as *RC Automation · FEAT-7*; the workbook-level version of the question — who owns
the sheet — has not been asked.

---

## 6. Owner's list

Reserved for what the project owner sends next, and everything after. Nothing is written here by
anybody else.

> **Settled.** Check `CRIT-1` first, then build the `.xlsm` control sheet and the templates.
> Both templates minimal and datum-only. The owner has an existing project `.rvt` and will describe
> it, with what needs adding — so `CRIT-2`'s template specification waits for that rather than being
> guessed at, and `FEAT-3` starts from a real template instead of an out-of-the-box one.
>
> **`CRIT-1` is confirmed** — both routes answered, the marshalling is real, and the engine question
> is settled. It moved to `done-list.md` as `DONE-1` and left `CRIT-4`, `BUG-1` and `BUG-2` behind it.
>
> **The first job went end to end on 2026-08-24** — recorded as `DONE-1` through
> `DONE-4`. `CRIT-3`, `FEAT-1`, `FEAT-2`, `FEAT-4`, `FEAT-21` and `BUG-3`
> through `BUG-14` are all closed by that one screenshot.
>
> **Next run to do**, in this order:
>
> 1. **pyRevit tab → Reload** (or restart Revit) so the new `startup.py` loads.
> 2. **Bridge Check.** It now says which of three things is wrong and what to do.
>    Send that dialog whatever it says — it is the whole diagnosis now.
> 3. Switch **Bridge Listener** on.
> 4. ~~`Run_Levels` with Write? = No~~ **done 2026-08-24**: `created=2
>    matched=1 modified=1 written=0`, four sheet rows and two model levels all
>    accounted for.
> 5. **`Run_Levels` with Write? = Yes, then run it again.** The second run must
>    report `matched=4` and nothing else. That is the acceptance test, not the
>    first one: anything can create.
> 6. Then `Run_Grids` the same way — dry run, write, write again.
>
> The workbook was rebuilt, so its GRIDS sheet now carries `Angle` and `Length`
> and one worked example of a skewed grid given as a start and an angle. The
> `.bas` did not change this time.
>
> A `LOG` row closes `CRIT-3`, `FEAT-1`, `FEAT-2` and `FEAT-4` in one go — they
> all describe the same journey — and `BUG-3` through `BUG-8` with it.
>
> **Bridge Check now prints to the pyRevit console.** Paste that rather than
> screenshotting the dialog; it carries the detail the dialog truncates.
>
> **Waiting on:** the RC Automation 0.7.0 bugs the owner found but has not sent, and the existing
> project `.rvt` that `CRIT-2` and `FEAT-3` start from.

> **Settled 2026-08-24 — the sample project, and the order.** No in Revit testing on this build; the
> speed is deliberate. A sample project is built first as a workbook — foundation + G + 4, three
> horizontal grids and five vertical, ordinary footings, columns, beams and slabs — and the owner
> reviews the **format**, saying what to keep, add and remove, before anything else is written.
> Then one element at a time: **level, grid, column, footing, beam, slab, and so on.**
>
> And: keep a record of what is built, tested, done, failed and redone. It is [the build
> record](#the-build-record), at the top of this file, and it is a view of these entries rather than
> a second list to keep in step by hand.
