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

**The spike, and only the spike** — `CRIT-1` in the repository's
[`todo-list.md`](../todo-list.md). It proves the wire exists. It does not post a
job, it does not read a sheet, and it changes nothing in any model.

Every estimate in the PRD is conditional on this working, which is why it is
built before anything that would sit on top of it.

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

### 3. Then from Excel

1. Open any workbook (a blank one is fine).
2. `Alt+F11` → **File → Import File…** → `bridge/excel/modAnonGeeBridge.bas`
3. `Alt+F8` → **AnonGeeBridge_Ping** → Run.
4. `Alt+F8` → **AnonGeeBridge_Status** → Run.

Each writes a row to a `BRIDGE_SPIKE` sheet and shows the raw response.

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

## What this is not

Not the product. The real bridge **posts a job and polls for a result**:

```
POST /anongee/jobs   {command, workbook, sheet, options}  → 202 {jobId}
GET  /anongee/jobs/<jobId>                                → status, summary, findings
```

Because Revit cannot be driven while it is busy, an Excel button **queues a job**
— it does not remote-control the application. A synchronous call that waits for a
5,000-element run will time out and leave Excel hung while the job is still
going.

Two other rules from the architecture, worth knowing before reading the VBA and
wondering why it is so short:

- **The envelope carries which sheet, not the data.** Revit opens the workbook
  itself, with the reader that already handles six formats. A JSON payload would
  be a second reader that eventually disagrees with the first.
- **Revit never writes into the open `.xlsm`.** Excel has it locked. Revit writes
  a JSON result file; the macro reads it and writes the sheet.

Which is why the macro must stay small. Anything it knows has to be kept in step
with Python by hand.

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
