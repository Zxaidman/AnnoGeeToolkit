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
| `done` | Confirmed on the in Revit, and copied into `done-list.md` with what was done. |

An item leaves this file only by reaching `done`, and it is described in `done-list.md` when it
does. Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this file
before it is built, argued about, or written into any other document. Standing instruction from the
project owner, and it is what keeps this list the queue rather than a summary of one.

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

### CRIT-5 — `levels.sync` and `grids.sync` are declared and not built · `pending`

The registry names them, the `CONTROL` sheet has a button for each, and pressing
either answers *"declared but not built yet"*. That is a deliberate state and not
a comfortable one: the workbook shows a capability the model does not have.

Declared first on purpose — the workbook could then be built and checked against
a registry that already knew what it would be asked for, and a test holds the
`CONTROL` sheet, the registry and the macro to the same three names.

**What each needs** is now only the handler: `anongee_toolkit/commands/levels.py`
and `grids.py`, each `run(uiapp, envelope)` returning `(summary, findings, note)`.
Everything under them exists — the transport, the listener, the workbook, the
name matching (`rc_automation/naming.py`, already proven on level names), and the
read-only level and grid adapters in `structural/`.

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
| FEAT-4 | `template.xlsm` build script — sheets, validation, `keep_vba=True` | **Built, `testing`.** `bridge/excel/build_workbook.py` writes `CONTROL`, `INFO`, `LEVELS`, `GRIDS`, `LOG`. One manual step remains and always will: `openpyxl` preserves a VBA project and cannot create one | `testing` |

### Datum and setup

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-5 | `levels.sync` | **Straightforward, and now only a handler** — see `CRIT-5`. Matching already built and proven. Sync-and-modify only: deleting a level deletes everything hosted on it | `pending` |
| FEAT-6 | `grids.sync` | **Straightforward, with a fiddly tail.** Creating them is an afternoon; per-view bubbles and 3D extents are where the time goes | `pending` |
| FEAT-7 | `types.sync` — duplicate, parameterise, load from a library | **Partly possible, and the boundary matters.** Duplicating and loading covers most of a real job. **Authoring a family from a spreadsheet is not on the table** — the template carries the families | `pending` |
| FEAT-8 | `views.sync` — plans, sections, 3D, templates, scope boxes, crops, filters | **Yes, medium.** The workbook supplies the judgement so the code does not guess | `pending` |
| FEAT-9 | `sheets.sync` — sheets, viewports, title block parameters | **Yes, medium.** Placing a viewport is arithmetic, not research | `pending` |

### Structure

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
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
| FEAT-21 | **Bridge Listener as a modeless window** — minimal, always-visible: watching or stopped, the folder it watches, jobs as they arrive and what each did | Straightforward, and the pattern is already proven twice in this repository. A TaskDialog says what was true at the moment it opened; a job that arrives thirty seconds later is invisible, which is the wrong shape for a thing whose whole job is to be watching. Owner's request | `pending` |
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
> **Next run to do**, in this order:
>
> 1. **pyRevit tab → Reload** (or restart Revit) so the new `startup.py` loads.
> 2. **Bridge Check.** It now says which of three things is wrong and what to do.
>    Send that dialog whatever it says — it is the whole diagnosis now.
> 3. Once it is up: switch **Bridge Listener** on and press **Run_Echo**. The
>    `.bas` is already re-imported and `/ping` answers from Excel.
>
> A `LOG` row closes `CRIT-3`, `FEAT-1`, `FEAT-2` and `FEAT-4` in one go — they
> all describe the same journey — and `BUG-3` through `BUG-8` with it.
>
> **Bridge Check now prints to the pyRevit console.** Paste that rather than
> screenshotting the dialog; it carries the detail the dialog truncates.
>
> **Waiting on:** the RC Automation 0.7.0 bugs the owner found but has not sent, and the existing
> project `.rvt` that `CRIT-2` and `FEAT-3` start from.
