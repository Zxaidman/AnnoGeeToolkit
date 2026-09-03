# AnonGee Bridge — done list

What the programme has built and confirmed working in Revit, and what it took.

**An entry arrives here only when the project owner has run it in Revit and said it works.** A green
test suite is not confirmation — every bug this repository has shipped passed the suite on the way
to a model. Where the evidence is weaker than that, the entry says so in its own words rather than
rounding up.

Nothing is deleted from here. An item later replaced stays, marked `superseded`, with what replaced
it — what a thing cost to build is part of the record even when it no longer runs.

| Column | Meaning |
| --- | --- |
| **Confirmed** | The report, screenshot or sentence from the owner that closed it. |
| **Shipped in** | The version it first worked in. |
| **Cost** | What it took, including the wrong turns — those are the expensive part and the part worth remembering. |

---

## DONE-1 — an Excel button reaches a live Revit model

**Shipped in** extension 1.9.0 · **Confirmed** 2026-08-22, Revit 2025 25.4.50.35, by the owner
running both routes from Excel and pasting the raw responses.

`/anongee/status` came back with the open document:

```json
{"document": {"title": "R25_REBAR_AUTOMATION",
              "path": "D:\\ZAID\\Advance AI\\rvt\\R25_REBAR_AUTOMATION.rvt",
              "workshared": false, "read_only": false},
 "user": "praka", "revit": "Autodesk Revit 2025 25.4.50.35", "revit_context": true}
```

**Four questions, four answers.**

1. **Does the Routes server start, and is the port reachable from Excel?** Yes. pyRevit Settings →
   Routes → *Routes Server (Beta)*, restart Revit; it reports `listening on http://0.0.0.0:48884`.
   Both routes answered from a plain workbook with `WinHttp`.
2. **Is the External Event marshalling real?** Yes. `/status` declares `uiapp` and returned a live
   document, its path, and the Revit build — none of which can be read anywhere but Revit's own
   thread.
3. **Which engine runs a startup script, and can it see the toolkit?** IronPython 2.7.12 on .NET 8,
   and **no**: `path_entries` came back empty and `anongee_toolkit` does not import. This is the
   finding, and it is written up as `CRIT-4`.
4. **What happens with no document open?** Not exercised — the owner ran it with a model open. The
   code path exists (`no document is open` rather than an error) and is still untested.

**Cost.** Two things, and the second one is the one worth remembering.

*Both routes worked first time.* Two routes rather than one — `ping` declaring no Revit argument,
`status` declaring `uiapp` — cost about twenty extra lines and would have localised the failure to
one half instantly. They both answered, so it bought nothing this time. It was still the right
shape: the alternative was one route and a coin flip.

*The diagnostic tool was the thing that broke.* Bridge Check could not reach the wire at all —
`System.Net.WebClient` needs `clr.AddReference` on .NET 8, and `urllib.request` is not in this
engine's standard library. The tool built to explain a failure was the only part that failed, and
the spike survived it only because the same two URLs could be called from Excel. Recorded as
`BUG-1`; it now tries four ways and reports which one worked.

*What it changed.* The IronPython answer is not an obstacle — it forces **the route is a doorbell,
the worker is CPython, they share a folder rather than a module**, which collapses the two designed
transports into one. There is no second implementation to keep in step, because HTTP is now just a
faster way to write a file into the outbox.

---

## DONE-2 — the engine split, resolved into one transport

**Shipped in** extension 1.10.0 · **Confirmed** by `DONE-1`'s `/ping` response, which is what
settled it. The code that follows from it is built and unrun; this entry records the *decision*,
which is confirmed, not the run.

`CRIT-1` reported IronPython 2.7 with no toolkit on its path. The design that came out of it:

> **The route is a doorbell. The worker is CPython. They share a folder, not a module.**

**What that deleted.** The architecture had two transports — HTTP and a file drop — behind one
envelope, and warned that keeping two implementations in step was the thing most likely to rot.
There is now one. HTTP writes into the outbox; so does anything else. `filedrop.py` was on the
module map and never needed writing.

**What it cost.** The folder rules are written twice, in two languages —
`anongee_toolkit/bridge/jobs.py` in CPython 3 and `AnonGee.extension/startup.py` in IronPython 2.7
— because neither engine can import the other's code. That duplication is the price of the split
and it is held down two ways: a test compares the constants, and `/ping` reports the home the route
computed so a disagreement shows up as a sentence in a dialog rather than as a job nobody ever sees.

**A third copy was very nearly written.** The macro needed to know where the result file would be,
which would have put those same rules in VBA, untestable, and wrong the first time somebody set
`ANONGEE_BRIDGE_HOME`. Instead the post's answer carries `resultTsv` and the macro waits for a path
it was given.

---

## DONE-3 — an Excel button reaches the bridge, and both ends agree where jobs live

**Shipped in** extension 1.10.1 · **Confirmed** 2026-08-24, by `/ping` answering
from Excel:

```json
{"bridge": "0.3.0", "ok": true, "api": "anongee",
 "bridge_home": "C:\\Users\\praka\\AppData\\Roaming\\AnonGee\\bridge",
 "engine": {"implementation": "IronPython", "version": "2.7.12 … on .NET 8.0.30"},
 "toolkit": {"importable": false, "path_entries": []}}
```

Three things in that, and the second is the one worth having built for.

**The routes register and answer.** `bridge: "0.3.0"` is the rebuilt
registration — each route added on its own so a bad pattern cannot reach the
others. `/jobs/<string:job_id>` had used a placeholder pyRevit does not have;
whether it had actually killed the diagnostic routes was a question that could
not be answered, which was the real fault.

**`bridge_home` matches the listener's outbox exactly.**
`…\AppData\Roaming\AnonGee\bridge` from the route, `…\bridge\outbox` from
the listener. Those are two implementations of the same three rules, in two
languages, in two engines that cannot import each other — the price of the split
recorded in `DONE-2`. **They agree**, and now they are known to agree rather than
assumed to.

**The engine answer holds.** IronPython 2.7, no toolkit, exactly as `DONE-1`
found. The doorbell design is correct.

**Cost.** Four fixes to get here, and the pattern in them is the same one twice
over: *the tool that reports the failure failed at reporting it*. Bridge Check
could not reach the wire at all in one release, hid the reason behind a
collapsed panel in the next, and took minutes to show nothing in the one after —
each time because a detail was put somewhere tidy rather than somewhere read. It
prints to the console now.

The macro contributed two of its own: a handler armed inside another handler,
which VBA ignores, and two constants declared below the first procedure, which
Excel refuses to compile. Both are now held by tests that read the `.bas`.

---

## DONE-4 — a button in Excel changed a Revit model's report, end to end

**Shipped in** extension 1.11.0 · **Confirmed** 2026-08-24 by the owner, five
jobs in the listener window:

```
20260824-174025-0005  grids.sync   rejected
20260824-174002-0004  bridge.echo  done   grids=0 levels=2 option.dryRun=True
                                          title=R25_REBAR_AUTOMATION read=2 written=0
20260824-173933-0003  levels.sync  rejected
20260824-173919-0002  grids.sync   rejected
20260824-173909-0001  bridge.echo  done   option.dryRun=False …
```

**Everything in the chain is now proved by something that ran.** Excel posted;
the IronPython route stamped a job and wrote it; the CPython listener noticed it
on an Idling tick, claimed it with an atomic rename and raised its external
event; the command ran on Revit's own thread and read the real model — `levels=2`,
`grids=0`, `R25_REBAR_AUTOMATION`; the result was written twice; the macro read
the TSV and reported it.

Three details worth keeping:

**`dryRun` round-tripped.** Job 0001 carried `False` and job 0004 `True`, which
is the CONTROL sheet's *Write?* column arriving intact at the far end. The
option channel works, and that is what makes every later command safe to try.

**The unbuilt commands rejected themselves.** `levels.sync` and `grids.sync`
answered *"declared but not built yet"* rather than failing obscurely — the
reason for declaring commands before writing them.

**The window earned itself immediately.** Five jobs, their statuses and their
counts, visible at once. The `TaskDialog` it replaced could not have shown any
of it.

**Cost.** Fourteen bugs between the first spike and this screenshot, and the
shape of them is the lesson. Four were in the diagnostic rather than the thing
being diagnosed — it could not reach the wire, hid the reason behind a collapsed
panel, took minutes to show nothing, and finally invented a fault in the bridge
that did not exist. Two were engine mistakes hiding each other. Three were VBA
and encoding rules that have no runtime error until the moment a user sees them.

The round that broke the pattern was the first one whose findings arrived as
**pasted console text rather than a screenshot** — three separate bugs were
diagnosable from it at once. That is why the report prints to the console.

---

## What this programme inherits

Not entries — these were built and confirmed under **RC Automation**, and they are described in
`AnonGee.extension/AnonGee.tab/Dev.panel/RC Automation.pushbutton/done-list.md`. They are listed
here because the programme is built on them and nobody should rebuild them.

| Inherited | Recorded as | Why it matters to the bridge |
| --- | --- | --- |
| The pure / Revit split | *RC Automation · DONE-1, DONE-2* | 575 tests run on any machine. Every new command follows the same seam. |
| External-event marshalling, FIFO queue, modeless window | *RC Automation · DONE-11* | The answer to the one constraint the whole architecture is built around: the Revit API runs on Revit's thread, when Revit is idle. |
| A workbook reader across six formats | *RC Automation · DONE-1* | Why the command envelope carries *which sheet*, not the data. |
| Validation that names its cell | *RC Automation · DONE-2* | The finding shape the result envelope uses unchanged. |
| Level and grid name matching | *RC Automation · DONE-3, DONE-4* | `levels.sync` and `grids.sync` start from working code, not from nothing. |
| One undo step, chunked and assimilated | *RC Automation · DONE-10* | Extends to every command without change. |
| Identity fields, and never deleting what the tool did not create | RC Automation 0.7.0 | Extends to every element type without change. |
| A text report as the tool's only witness | *RC Automation · DONE-12* | Two of the last three bugs were found by reading one against a model rather than by anyone testing anything. |
