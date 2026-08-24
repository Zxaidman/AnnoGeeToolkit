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
