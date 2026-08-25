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
| `testing` | Being written now. |
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
| The `Write?` switch | — | 1.15.0 | **fixed and confirmed**: levels and grids were written the run after | **yes** | **1** — read from the wrong column, so no run could ever write | BUG-16 |
| **Levels** | `levels.sync` | yes | **built in Revit 2026-08-25** | **yes** | 0 | FEAT-5 |
| **Grids** | `grids.sync` | yes | **built in Revit 2026-08-25** | **yes** | 0 | FEAT-6 |
| Sample project workbook — Foundation + G + 4 | — | 1.16.0, third format | reviewed twice; ten changes asked for and made | no | 0 | FEAT-22, 24–33 |
| **Footings** | `footings.sync` | 1.22.0 | **built in Revit**: 15 written, then 15 matched | **yes** | **1** | FEAT-23, 27, 34 |
| **Columns** | `columns.sync` | 1.22.0 | **built in Revit 2026-08-25**: all 90, no duplicate-Mark warning | **yes** | **2** | FEAT-10, 28, 34, BUG-22, 23 |
| **Levels** | `levels.sync` | 1.22.0 | **built in Revit**: `Level 0` renamed to `01 GROUND LVL.`, then *every level already agrees with the sheet* | **yes** | **1** | FEAT-5, BUG-23 |
| **Grids** | `grids.sync` | 1.22.0 | **built in Revit** | **yes** | 0 | FEAT-6 |
| **Slabs** | `slabs.sync` | 1.22.0 | **built in Revit 2026-08-25** | **yes** | 0 | FEAT-13, 30 |
| Beams | `beams.sync` | 1.23.0, `redo` | **built, and wrong twice**: a −1500 z offset nobody set, and running centre to centre with joins on | no | **2** | FEAT-11, 29, BUG-29, 30 |
| **Extract Template** | — | 1.20.0 | **ran twice, and the second report is right**: `ID` shared, six project, real data types | **yes** | **2** | FEAT-35, BUG-18, 21 |
| Buttons | — | 1.19.0 | **style, position and scaling all confirmed** | **yes** | **1** | FEAT-32, BUG-19 |

**The first two things this ever built** were levels and grids, on 2026-08-25, the run after BUG-16
was fixed. Both had been reported as *created* twice before that while writing nothing — which is
worth keeping in the record, because both reports were true and the tool was right about itself the
whole way through.

**Idempotent in a test is not idempotent in a model.** Columns and footings are proved to plan
correctly against the sample — created once, matched twice after — and that is worth exactly as much
as a green suite always is. Neither has met a family symbol, a real grid or a transaction.

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

### BUG-29 — every beam arrived with a z offset of −1500 · `testing`

**How it was found.** The project owner's properties panel: a beam on `06 TERRACE LVL.` with
`Start Level Offset` 0, `End Level Offset` 0, and **`z Offset Value` −1500.000**.

**Cause.** Nothing set it. `NewFamilyInstance` gives a beam whatever the family and the last
placement left behind, and −1500 is the foundation level — a value from somewhere else in the model
that the API happily carried into ninety beams.

**Fix, and the general form of it.** Justification and offset are **stated, not inherited**: `yz`
uniform, `y` origin at zero, `z` top at zero, and the sheet's `Offset` written to the start and end
level offsets where it belongs. Anything a run does not set is a value somebody else chose, and on a
family instance that is most of them.

### BUG-30 — beams ran column centre to column centre, and joined · `testing`

**How it was found.** The project owner: *"it is right as per Excel but not as BIM model — beam is
not disallowed join from both ends and it should stop at column face, not on centre."*

**Both halves are right and they are one job.** A grid intersection is a column's *centre*; a beam
drawn between two of them runs through both columns. Revit's automatic join then extends it further,
so the concrete is counted twice at every junction and the shop drawing shows a beam that does not
exist.

**Fix.** `DisallowJoinAtEnd` on both ends, and each end **cut back to the column face** — by half the
column's dimension *along the beam's own direction*, which is its Width for a beam running along X
and its Depth for one running along Y. The column is looked up in `COLUMN_PLACEMENT` by the same
intersection the beam names, and its size in `COLUMN_TYPES`; rotation is read, because a turned
column presents its other face.

An end with no column under it is not cut back, and that is said once. `EndPrep` on the sheet says
which convention a row uses, so a beam that really does run to the grid can still say so.

### BUG-28 — footings never wrote the schedule mark · `testing`

**How it was found.** The project owner, after `S_ScheduleMark` started working for columns: *"footing
mark is not using `S_ScheduleMark`, only using `Mark`."*

**Cause.** The schedule-mark chain was written into `commands/columns.py` and nowhere else. Footings
were placed through `structural.footings.set_mark`, which writes Revit's own `Mark` and stops.

**And a second thing underneath it.** The two sheets do not mean the same thing by `Mark`. A column
row says `C1` — a **repeating schedule label**. A footing row says `F-A1` — a **unique key**. So even
with the chain shared, the two would write different kinds of value into the same parameter and a
schedule reading it would be incoherent.

**Fix.** `Mark` on every placement sheet is the repeating schedule label: footings become `F1`, `F2`,
`F3`, matching their types. Revit's `Mark` gets the key — `F1-A1` — as it already does for columns,
and `S_ScheduleMark` gets the label. One rule, four sheets.

### BUG-27 — `BRIDGE_URL` on `INFO` was decoration · `testing`

**How it was found.** pyRevit moved from port 48884 to **48885**. The project owner changed
`BRIDGE_URL` on `INFO` to match, pressed the button, and the error still named **48884**.

**Cause.** `BridgeUrl` built the address from the module constants and never read the sheet. The row
had been there since the first workbook, describing something nothing consulted.

**Why the port moves at all**, which is the part worth knowing: pyRevit takes 48884 when it can and
**the next free one when it cannot**. A second Revit session, or one that did not shut down cleanly,
is enough. So the port is not a constant and never was.

**Fix, and the better half of it.** `BridgeUrl` reads `INFO` and falls back to the constants. And
when a call fails, the macro **looks** — pinging 48884 to 48892 with a one-second timeout each — and
says *"something IS answering on 48885, put this in INFO"*. That turns a dead end into an
instruction.

One second, not the usual fifteen: nine ports at fifteen seconds is over two minutes of Excel not
responding, which is exactly the shape of `BUG-8`. A diagnostic slower than the user's patience is
worse than none, because they stop it and learn nothing.

### BUG-24 — every rebuild leaked thirteen VBA sheet modules · `testing`

**How it was found.** The project owner's screenshot of the VBA editor: **forty**
`Sheet` objects listed for a workbook with fourteen sheets, and *"with each pull the count
increases"*. Nothing visible from Excel.

**Cause.** A rebuild deleted every worksheet and made new ones with the same names. That is not the
same operation to a workbook carrying VBA: a macro-enabled file holds a **code module per sheet**,
and `openpyxl` rewrites the worksheets without touching the VBA project. So thirteen modules were
orphaned and thirteen more added, every time, for ever.

**Fix.** Clear the sheets in place instead. Sheets the build no longer writes are still removed —
only those, and they are the ones whose modules should go too.

### BUG-25 — the same survey disagreement was reported seven times · `testing`

**How it was found.** Reading the `FINDINGS` sheet from a real run: seven warnings, one per level,
all saying the survey elevation disagreed. The model puts its survey point at the origin; the
workbook says 100 m. **One wrong cell, reported seven times.**

**Fix.** When every row is out by the same amount it is one fact, and it is said once, naming the
number to change and where. Rows out by *different* amounts are still reported one each — then they
really are separate mistakes and collapsing them would hide six of the seven.

### BUG-26 — a test hard-coded a ribbon path and the panel moved · `testing`

**How it was found.** The project owner reorganised `Dev.panel` into stacks. One test failed —
`BBS Generator.pushbutton` had moved into `col1.stack/`.

**Fix.** The test searches for the file. A ribbon gets reorganised; a failure that says nothing about
the code costs somebody the time it takes to work out that it says nothing.

### BUG-20 — the FINDINGS sheet was wiped by the next job · `testing`

**How it was found.** Reading the pushed workbook: `columns.sync` reported `written=75` of `created=90`,
and `FINDINGS` was **empty**. Fifteen columns failed for a reason the run knew exactly, and the sheet
that was supposed to say it had nothing in it.

**Cause.** `ShowFindings` clears the sheet on every result, including one with nothing to say. The
owner pressed *Create beams* and *Create slabs* after the columns run; both were rejected as unbuilt,
both cleared the sheet, and the fifteen explanations went with them.

**Fix.** The sheet carries a header saying which job and command its findings belong to, and how many
there were. A run with none says *no findings* under that header rather than leaving a blank sheet —
which is the same picture as a run that failed to report and cannot be told apart from one.

### BUG-21 — the extraction called every parameter a project parameter · `testing`

**How it was found.** Reading the report the owner sent. It has a **Project** section, a **Family**
section, and **no Shared section at all** — for a template that has been through a real job. And every
parameter's type reads `Autodesk.Revit.DB.ForgeTypeId`, which is the name of a class rather than the
name of anything.

**Two causes, both in `inventory`.** `_is_shared` tests `isinstance(definition, ExternalDefinition)`,
and `doc.ParameterBindings` hands out `InternalDefinition` — for shared and project parameters alike.
So the test is **always false** and everything lands under *project*. And `_definition_kind` calls
`GetDataType()`, which returns a `ForgeTypeId` object; printing it prints the class.

**Why this one is the worst of the four.** The report exists to answer *where may the workbook safely
write*, and the difference between shared and project is the whole answer. A wrong answer here is
acted on — parameters bound in the wrong scope, values that vanish on the next family reload — and it
is expensive to unpick.

### BUG-22 — `Mark` was given a value that repeats, and Revit warned · `testing`

**How it was found.** The project owner's screenshot: *Elements have duplicate "Mark" values*, three
warnings.

**Cause, and it is a design mistake rather than a slip.** The owner's marking rule is that `C1` repeats
— up a stack and across a floor — and `Mark` is the one Revit parameter that is expected to be unique
per instance. Writing a deliberately repeating label into it was always going to warn.

**Fix.** `Mark` gets the **key**, which is unique by construction: `C1-A1-S1`. The schedule label goes
to a parameter the workbook names, and if no parameter is named it is not written and one finding says
which one to bind. That is the template/workbook boundary doing its job rather than being worked
around.

### BUG-23 — one blocked level cost fifteen columns and left a storey-high gap · `testing`

**How it was found.** Two symptoms, one cause. The project owner's section shows the lowest columns
stopping at `Level 0` with a storey-high gap above them, and `columns.sync` wrote 75 of 90.

**Cause.** `levels.sync` reported `blocked=1`. The template carries `Level 0` at 0.000, and the sheet
asks for `01 GROUND LVL.` at 0.000 — so the rule *never create a second level at an occupied
elevation* refused it, correctly. Then every column naming `01 GROUND LVL.` as its **base** failed
(fifteen of them, exactly the S2 lift) and every column naming it as its **top** was placed without one.

Both were reported. **The reports were wiped by BUG-20**, which is why this arrived as a picture rather
than a message.

**Fix.** A `RenameFrom` column on `LEVELS`. A row that names the level it is replacing renames it
instead of being blocked — explicit, auditable, and it does not weaken the rule for anything that does
not ask. Renaming stays a thing somebody writes down, which is what the original refusal was
protecting.

### BUG-18 — Extract Template could not import the toolkit, and blamed the wrong thing · `testing`

**How it was found.** First press: *No module named 'anongee_toolkit'*, followed by my own error message
telling the project owner to check the `#! python3` line — **which was there, on line one, and was not
the problem.**

**Cause.** pyRevit puts `<extension>/lib` on `sys.path` and **nothing below it**. The toolkit lives in
`lib/py3`, so every tool that uses it calls `path_resolver.update_paths()` first. This one did not.

The two failures are indistinguishable from inside Revit — the same `ImportError`, the same wording —
which is exactly why a confident wrong message is worse than none. It would have sent the owner to
look at a line that was already correct.

**Fix, and a repo-wide test.** Any script that imports the toolkit must **run** something that puts
`lib` on the path — and *run* is the word: the first version of the test looked for a `sys.path`
insert anywhere in the file, so a script keeping the bootstrap in a function it never called still
passed. A mutation proved it: the call was deleted and nothing went red. It now walks module-level
code only, and a helper counts only when something at module level calls it.

The same test caught its own false positive on the way: it first flagged a tool whose only mention of
the toolkit is inside a comment. **Fourth time a test in this repository has matched prose rather than
code**; it reads the AST now, and there is a test holding it to that.

### BUG-19 — the buttons did not move or size with their cells · `testing`

**How it was found.** The project owner ran `AddButtons`, confirmed the style matched theirs exactly,
and reported that resizing a row or column left the buttons where they were.

**Not diagnosed — instrumented.** `Placement` was being set inside a blanket `On Error Resume Next`
and never checked, so there were three indistinguishable possibilities: the line did not run, it ran
and failed, or it ran and Excel overwrote it. The workbook's own XML says `twoCellAnchor` with no
`editAs`, which *is* move-and-size — so the file contradicts the symptom, and another round of
guessing would have been the fourth.

So the macro now **sets it, reads it back, and reports the count**: *"7 button(s) drawn, 7 of them set
to move and size with their cells."* Two attempts, because they fail differently — the `Shape`
property and the `ShapeRange` form go through different code paths. And
`AnonGeeBridge_AnchorButtons` runs the anchoring alone, so if a button still will not follow its cell
after that says it did, the cause is Excel and not the macro. **One press turns this from a guess into
a fact.**

### BUG-17 — `ApplyUnits` skipped the `INFO` sheet · `testing`

**How it was found.** The project owner switched the workbook to metres, ran the converter, and
found `INFO` still carrying metres values while the rest of the workbook had moved. **Reproduced by
reading the pushed workbook**: `INFO!B4` is `100` under a key cell reading `SURVEY_OFFSET`.

**Cause.** The converter finds length columns by their header — `Elevation PBP (m)` — and scales the
column under it. `INFO` is not a column table. It is key, value, description in rows, so there is no
header above the number and nothing for the converter to find.

**Fix.** The key carries the unit instead: `SURVEY_OFFSET (m)`, in the same brackets, in the cell
beside the value. One extra shape of table for the converter to know about, and the rule stays
"a cell that names a unit says what the number next to it is".

### BUG-16 — `Write? = Yes` did nothing, and the switch overwrote itself · `testing`

**How it was found.** The project owner ran `levels.sync` and `grids.sync` against a model with
`Write?` set, and reported *created=6* and *created=8* with nothing in Revit. **Reproduced from the
workbook they pushed**, without needing Revit: the `LOG` sheet says `written=0` and the note says
*"dry run"*, and the `CONTROL` row shows the outcome written one column to the left of where it
belongs.

**Cause, and it is one number.** The sample workbook added a `Built?` column at position 5, so
`Write?` moved to 6 and `Last status` to 7. The macro has those positions hard-coded from the datum
workbook's layout:

```vba
ReadDryRun = (UCase$(Trim$(CStr(sheet.Cells(row, 5).Value))) <> "NO")   ' reads Built?
sheet.Cells(row, 6).Value = status                                      ' writes over Write?
```

So the switch was read from `Built?`, which says `yes` or `not yet` and never says `No` — and
`ReadDryRun` defaults to a dry run for anything that is not `No`. **`Write? = Yes` could not work,
whatever the owner typed.** Then the status was written into the `Write?` cell, so after the first
run the switch said `done`, and the workbook could never be made to write again.

The tool was right about itself the whole time — the note said *dry run*, and `written=0` was true.
Which is worth noting: the report was the thing that made this findable from a workbook alone.

**The fix is not a corrected number.** Any column added to `CONTROL` breaks a hard-coded index
again, silently, and the failure looks like Revit not working. The macro finds its columns **by
header name**, once per run, and says so if a header is missing. A test fails on any `Cells(row, n)`
against `CONTROL` in the `.bas`.

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
| FEAT-24 | **Buttons on `CONTROL`** — real Form Control buttons, one per command | `openpyxl` cannot draw a form control, so the workbook cannot ship with them. A macro can: `AnonGeeBridge_AddButtons` draws one per row and assigns its macro, and re-running it replaces rather than stacks them. One `Alt+F8`, like the `.bas` import, and never again | `testing` |
| FEAT-25 | **A unit for the whole workbook** — `mm` or `m`, chosen on `INFO`, **`m` by default** | Every length header carries its unit — `Elevation (m)` — so the unit is visible in the sheet rather than remembered, and a converter can find exactly the columns it must scale. The job carries the unit to Revit, which is always internal feet whatever the project units say | `testing` |
| FEAT-26 | **Two elevations on `LEVELS`** — Project Base Point and Survey Point | Both columns, one authority. `ElevationBase` says which one drives, PBP by default; the other is checked against the model's survey offset and a disagreement is reported rather than resolved | `testing` |
| FEAT-34 | **A missing type is created, not refused** | The first real run placed nothing: fifteen footings and ninety columns each reported *no type called `F1`* and stopped, which was correct and useless. A named type is now duplicated from a standard family and sized from the TYPES sheet. **Creating a type is not authoring a family** — the family has to be loaded; what is generated is a sized, named type of it | `testing` |
| FEAT-35 | **Extract Template** — a pyRevit button that writes the model's contents to Markdown | A `.rvt` cannot be read outside Revit: it is a compound binary only Revit opens. So the model describes itself instead — every category, family, type, and every parameter with its scope (shared, project, global, family, instance, type) — as a tree in one `.md`, which is reviewable in a diff and readable by anybody | `testing` |
| FEAT-36 | **The template and the workbook, coordinated** | **Proposal written**, `docs/specs/2026-08-25-template-and-workbook.md`: each fact has one owner, the template says what is possible and the workbook says what is wanted. It is a starting position to argue with, not a description of anything — The question is which of the two is the authority for each thing — a family is the template's, a size is the workbook's, and the list of which is which is the deliverable | `pending` |
| FEAT-37 | **The survey point, set from the workbook** | The owner fixed a survey mismatch by hand with *Specify Coordinates at Point* and asked whether it could be automated. It can: `levels.sync` already reads the model's offset to check the sheet against it, so making it *set* the offset is the same knowledge pointed the other way. **Off by default** — moving a survey point re-coordinates a whole project, and that is a decision, not a convenience | `testing` |
| FEAT-39 | **`schedules.sync`** — Revit schedules from a sheet | **Proposed, `pending`**: `docs/specs/2026-08-26-schedules-and-footing-rebar.md`. The easiest thing left — no geometry, no judgement — and the first time `S_ScheduleMark` earns its keep. Until something reads that parameter, filling it in is an act of faith | `pending` |
| FEAT-40 | **`REBAR_FOOTING` sheet** — footing rebar from the workbook | **Proposed, `pending`**, same document, and the estimate is the point of it: **weeks, not days**. RC Automation has spent seven versions on footing rebar and its constraints are still `testing`. Every other command places one thing per row; this one places a hundred bars from a row and each can be wrong on its own | `pending` |
| FEAT-38 | **A `NAMING` sheet** — type names as patterns, `{b} X {h}` | The project owner asked for this in the workbook rather than in code, the way `cad2bim` already does it. One row per element, a pattern, and a worked example beside it so the syntax is visible rather than documented. A pattern that will not render is reported and the default used — a naming sheet that stops a run is worse than one with a typo in it | `testing` |
| FEAT-31 | **The workbook's formatting**, as a build output rather than something re-applied by hand | Fonts `Inter, Segoe UI, Cambria, Calibri`; three sizes a step apart, not a jump; every row 20 units; every column width computed from what is in it; `mm` shown as a whole number and `m` to two decimals. All of it generated, because a rebuild throws away anything done by hand | `testing` |
| FEAT-32 | **Shape buttons, from the owner's own template** | The owner replaced the Form Controls with rounded rectangles — and `openpyxl` deletes every drawing on a rebuild, so the buttons have to be redrawable rather than drawn. `AnonGeeBridge_AddButtons` now duplicates a template shape when the sheet has one and builds one to match when it does not, on `CONTROL` and on `INFO` for `ApplyUnits` | `testing` |
| FEAT-33 | **Cover and diameter stay in millimetres** | A cover of `0.05` and a bar of `0.012` is the workbook being consistent at the cost of being readable, which was the reason for metres in the first place. Those columns are pinned: their header says `(mm)`, and the converter is told to leave a pinned column alone | `testing` |
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
| FEAT-27 | **`FOOTING_PLACEMENT` — say what `X`/`Y` and `Outline` are** | `X`/`Y` become `OffsetX`/`OffsetY`: an offset from the named intersection, blank meaning dead on it, and the absolute position only when no grid is named. `Outline` is for a pad the type cannot describe — combined, stepped, cut round a pit — and is blank for every rectangular footing | `testing` |
| FEAT-28 | **Column marks follow the stack, not the storey** | The owner's rule: a column at A1 marked `C1` is `C1` all the way up, even where its size changes. Two columns share a mark on one floor **only if size and rebar schedule are both the same**. So `Mark` is a stack label and not a key — the key is grid position plus storey — and `TypeMark` carries the size, which is free to change per lift | `testing` |
| FEAT-29 | **`BEAM_PLACEMENT` — continuity is the layout** | A simply supported beam is one row. A continuous beam is a group of rows, one per span, sharing a mark, and **a blank row separates groups**. The sheet then reads the way a beam schedule reads, and the parser gets continuity for free instead of from a column somebody has to keep true | `testing` |
| FEAT-30 | **`SLAB_PLACEMENT` — one slab per panel, to the inner face of the beams** | Not one slab per floor. A panel is bounded by the four grids around it and its edge is the beam's inner face, so the slab stops where the beam starts and the concrete is not counted twice. `EdgeRule` names the convention per row so a cantilever or a slab running over a beam can still be said | `testing` |
| FEAT-23 | `footings.sync` — the bridge route to the footing placement RC Automation already does | **Built, `testing`.** Straightforward, and mostly already written. The pad-as-structural-floor path ships and is confirmed in a model; what is new is reading `FOOTING_PLACEMENT` and resolving a grid intersection to a point | `testing` |
| FEAT-10 | `columns.sync` — `NewFamilyInstance` between two levels | **Built, `testing`.** Matched on position and storey, never on the mark. Idempotent at the planning layer: 90 created, then 90 matched, then 90 matched again. Closes *RC Automation · CRIT-3*, where every run claims to place columns and places none | `pending` |
| FEAT-11 | `beams.sync` | **Built, `testing`.** One instance per span; a group of rows sharing a mark is one continuous beam, which is how Revit models it anyway. Joins and cutbacks are still ahead | `testing` |
| FEAT-12 | `walls.sync` | Medium | `pending` |
| FEAT-13 | `slabs.sync` — the footing path generalised | **Built, `testing`.** One slab per panel, inset from the four grids by half the width of the beam actually on each edge — read from `BEAM_PLACEMENT`, not assumed | `testing` |

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

### OWN-1 — the shape of every handover from here · `done`

Standing instruction, given 2026-08-25 and in force from the workbook review onwards. **Every
delivery says the same five things, in this order**, so a build can be read without reconstructing
what changed from the diff:

| # | Section | What goes in it, and what does not |
| --- | --- | --- |
| 1 | **New — built** | What did not exist before this build. Named, with where it lives. |
| 2 | **Changed** | What existed and now behaves differently. Says the old behaviour as well as the new one, because that is the half that is hard to recover later. |
| 3 | **Untouched** | What was deliberately left alone. The point of this section is that *silence is not evidence* — a thing not mentioned might be finished, or forgotten, and this is where the difference gets stated. |
| 4 | **Test procedure** | Numbered steps, in the order they are done, each one saying what to expect. Not "test it in Revit" — the actual clicks, and the number that says it passed. Idempotence is a step, never an assumption. |
| 5 | **Next phase** | A roadmap table: what comes next, what it depends on, and what state it is in. |

Sections 1–3 are a partition — everything in the build lands in exactly one of them, and *untouched*
is the one that must not be skipped when it is empty. Say "nothing" and mean it.

This is a reporting rule, not a queue rule. The [build record](#the-build-record) stays the record of
state; this governs how each delivery is written.

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
