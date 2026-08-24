# The bridge

An Excel button, a command, and a Revit model that changes because of it.

This folder holds the **Excel end**. The Revit end is
[`AnonGee.extension/startup.py`](../AnonGee.extension/startup.py) and the
[Bridge Check](../AnonGee.extension/AnonGee.tab/Dev.panel/Bridge%20Check.pushbutton)
pushbutton. The design is in
[`docs/specs/2026-08-22-excel-revit-platform-architecture.md`](../docs/specs/2026-08-22-excel-revit-platform-architecture.md).

```
bridge/
  excel/
    modAnonGeeBridge.bas    the VBA. Import it into a workbook once.
```

---

## What this is right now

**A job goes end to end.** Press a button in Excel, Revit runs it, the answer
comes back into the workbook. One command exists — `bridge.echo` — and it reads
no workbook and writes nothing, on purpose: every command after it has two
things that can be wrong, the wire and the work, and this one has only the wire.

`levels.sync` and `grids.sync` are **declared and not built**. Pressing them
answers *"declared but not built yet"*, which is a clear failure rather than a
silent one.

```
bridge/
  excel/
    modAnonGeeBridge.bas    the VBA. Import it into a workbook once.
    build_workbook.py       writes the workbook. Run it here.
    AnonGee_Bridge.xlsx     what it wrote — CONTROL, INFO, LEVELS, GRIDS, LOG
```

---

## The workbook

`build_workbook.py` writes every sheet, header and validation. **It cannot make
a working `.xlsm`, and that is a fact about the format**: `openpyxl` can
*preserve* a VBA project with `keep_vba=True` but cannot create one, because a
`vbaProject.bin` is an OLE compound document holding compressed VBA source.

So, once:

1. Run the builder:

   | | |
   | --- | --- |
   | **Windows** | `py bridge\excel\build_workbook.py` |
   | macOS / Linux | `python3 bridge/excel/build_workbook.py` |

   On Windows, `python3` is not a command and plain `python` usually hits the
   Microsoft Store alias rather than a real interpreter — *"Python was not
   found; run without arguments to install from the Microsoft Store"*. `py` is
   the launcher that ships with the python.org installer and finds the real one.
   Failing that, the full path to `python.exe`, or VS Code's **Run Python File**,
   both of which work.

   It needs `openpyxl`: `py -m pip install openpyxl`.

2. Open `AnonGee_Bridge.xlsx`, **Save As** `.xlsm`.
3. `Alt+F11` → File → Import File → `modAnonGeeBridge.bas`.
4. From then on run `build_workbook.py <path to the .xlsm>` and **the macros
   survive** — they are preserved, not recreated.

The VBA lives here as `.bas` source, which is why it is reviewable in a diff
like everything else.

| Sheet | |
| --- | --- |
| `CONTROL` | One row per command. `Write?` is `No` by default — a dry run reports what it would do and touches nothing. The outcome is written back beside the row that caused it. |
| `INFO` | Project, units, standard, template path, bridge URL. |
| `LEVELS` `GRIDS` | The datum. Sample rows included so the format is visible rather than described. |
| `LOG` | Every job: when, id, command, status, counts, note. Append-only. |

`FINDINGS` and `BRIDGE_SPIKE` are made by the macro when they are first needed.

---

## Running it

### 1. Turn the Routes server on

pyRevit ships an HTTP server that runs inside the Revit process. **It is off by
default.**

pyRevit tab → **Settings** → **Routes** → the **Routes Server (Beta)** toggle →
**restart Revit**.

It confirms itself in an orange bar:

> Routes server is listening on `http://0.0.0.0:48884`

**`0.0.0.0` means every interface, not just this machine.** On one workstation
that is harmless; before this leaves one desk it is not, and it is tracked as
`BUG-2` in [`todo-list.md`](../todo-list.md).

*Confirmed on Revit 2025 25.4.50.35, 2026-08-22.*

### 2. Check it from inside Revit first

AnonGee tab → Dev → **Bridge Check**.

This calls the same two URLs Excel will call, from the machine Revit is on. Doing
it here first takes the network out of the question — and when Excel later gets
no answer, this is how you tell "the bridge is down" from "Excel cannot reach
it".

### 3. Switch the listener on

AnonGee tab → Dev → **Bridge Listener**. It is a toggle; press it again to stop.

The route only ever *writes a job into a folder* — pyRevit serves it on
IronPython, where the CPython toolkit does not exist. This is the half that
notices and does the work. **Without it, jobs queue and nothing happens**, which
the macro says in as many words after five minutes.

### 4. Then from Excel

1. Open the `.xlsm` (see **The workbook** above).
2. `Alt+F8` → **AnonGeeBridge_Ping** → Run. Then **AnonGeeBridge_Status**.
   These write to a `BRIDGE_SPIKE` sheet and are the diagnostics.
3. `Alt+F8` → **Run_Echo**. This is the real thing: it posts a job, waits for
   the result file, and writes a `LOG` row.

Assign `Run_Echo`, `Run_Levels` and `Run_Grids` to buttons on `CONTROL` when you
want them clickable — right-click a shape → Assign Macro.

---

## What the two calls mean

| Route | Declares | Answers when | Proves |
| --- | --- | --- | --- |
| `/anongee/ping` | nothing | always, even mid-command | the server is up and the port is reachable |
| `/anongee/status` | `uiapp` | only once Revit is idle | pyRevit really did marshal the handler onto Revit's thread |

**Two routes rather than one, deliberately.** If ping answers and status hangs,
the server is fine and the marshalling is not. One route cannot tell you that,
and the difference is a day.

---

## What it answered

**Run 2026-08-22, Revit 2025 25.4.50.35.** Recorded in full as `DONE-1` in
[`done-list.md`](../done-list.md).

| | |
| --- | --- |
| Server up, port reachable from Excel | **yes** — both routes answered |
| External Event marshalling real | **yes** — `/status` returned the open document, its path and the Revit build |
| Engine running `startup.py` | **IronPython 2.7.12** on .NET 8 |
| Can that engine see the toolkit | **no** — `path_entries` empty, `No module named anongee_toolkit` |

The last two are the finding, and they set the design:

> **The route is a doorbell. The worker is CPython. They share a folder, not a
> module.**

The route validates, stamps a job id, writes the job file and returns. The
CPython worker does everything else with the toolkit unchanged. Which means the
two transports below are **the same transport** — HTTP is a faster way to write
into the outbox, not a second path with a second implementation.

Still untested: **no document open**, and **a modal dialog up**. Worth doing when
you next have the model closed — the second is the one a real user hits first.

---

## How a job actually travels

```
Excel                    Revit (IronPython)        Revit (CPython)
  │ save the workbook
  │ POST /anongee/jobs ──►  stamp a jobId
  │                         write outbox/<id>.job.json
  │ ◄── {jobId, resultTsv}  return, immediately
  │                                            Idling: anything waiting?
  │ wait for resultTsv                         claim it (atomic rename)
  │                                            ExternalEvent.Raise()
  │                                              └─ run it on Revit's thread
  │                                                 write inbox/<id>.result.json
  │                                                            + .result.tsv
  │ read the TSV, write LOG
```

Four decisions in that picture are worth knowing before reading the code and
wondering why it is shaped this way:

- **Posting answers instantly.** The route declares no Revit argument, so pyRevit
  does not run it as an External Event and it never waits for Revit to be idle.
  A synchronous call waiting on a 5,000-element run would time out and leave
  Excel hung while the job was still going.
- **The macro never works out where the bridge folder is.** The post's answer
  carries `resultTsv`. A third implementation of those rules, in VBA and
  untestable, would be wrong the first time somebody set
  `ANONGEE_BRIDGE_HOME`.
- **The result is written twice** — `.result.json` for machines, `.result.tsv`
  for Excel. VBA has no JSON parser and should not be given a hand-written one:
  a hundred and twenty lines that get escaping wrong the first time a sheet name
  contains a quote. Excel reads lines; give it lines.
- **The envelope carries which sheet, not the data.** Revit opens the workbook
  itself, with the reader that already handles six formats. A JSON payload would
  be a second reader that eventually disagrees with the first — and it is why the
  macro can stay this short.

---

## When nothing answers

Three causes, and **they look identical from Excel**:

| | What says so | What fixes it |
| --- | --- | --- |
| The Routes server is off | Bridge Check: *"the startup script ran … nothing is listening"* | pyRevit Settings → Routes → **Routes Server (Beta)**, restart Revit |
| The extension has not reloaded | Bridge Check: *"no startup record"* | pyRevit tab → **Reload**, or restart Revit |
| A route failed to register | Bridge Check: `routes NONE`, with the reason | read the note; it names the route and the error |

**Bridge Check tells them apart**, and it can do that even when nothing is
listening because `startup.py` writes a record to disk on every load — when the
startup script is the guilty one there is no route left to ask.

Two things worth knowing about that:

- The **Routes server toggle does not survive everything**. If it worked
  yesterday and not today, check it first.
- **Editing `startup.py` needs a pyRevit reload**, not just a new Revit session
  in some cases. The record's `loaded` timestamp says whether the version you
  are looking at is the version that ran.

---

## When the doorbell is not there

Not a second transport — **the same one, without the bell**. The route writes
into this folder and so does the macro when it cannot reach the route:

```
<workbook folder>/.anongee/
    outbox/  <jobId>.job.json     Excel writes, Revit reads
    inbox/   <jobId>.result.json  Revit writes, Excel reads
```

If Routes cannot be turned on — a locked-down machine, a blocked local port,
Revit not running when the button is pressed — the macro writes the job file and
the user presses the button in Revit instead. Same envelope, same handler, same
result. Slower at the edge, identical everywhere else.

That is not a fallback bolted on afterwards. It is the reason the transport is
kept at the edge and the command registry knows nothing about it — and after
`DONE-1` it is not even a fallback, it is the mechanism.
