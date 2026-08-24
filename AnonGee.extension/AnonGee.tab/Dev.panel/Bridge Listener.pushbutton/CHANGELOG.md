# Bridge Listener — changelog

## 0.3.0 — 2026-08-24

- **`__namespace__` moved onto the class, where Python.NET looks for it.** It
  was at module scope, which does nothing. Without it pythonnet routes
  `BridgeJobHandler()` to the interface's one-argument cast instead of building
  a real derived CLR type, and the failure is
  `TypeError: interface takes exactly one argument`.

  It ran anyway for one release **because it was on IronPython**, where none of
  these rules apply. Selecting the right engine in 0.2.0 is what exposed it —
  two faults, one hiding the other.
- `claimed` is a class attribute now, so an instance always has it. Rule 2
  forbids the `__init__` that would otherwise set it.

## 0.2.0 — 2026-08-24

- **`#! python3` on the first line**, and this tool cannot work without it. It
  imports `anongee_toolkit` from `lib/py3`; on IronPython that path is never
  added and openpyxl will not load at all.

  **It ran anyway for a release**, because the `bridge` package happens to be
  Python 2.7-compatible — so it looked entirely correct, reported its commands,
  and would have failed on the first job that needed to read a workbook. That is
  the worst kind of missing line: one whose absence produces a working tool with
  a fuse in it.

## 0.1.0 — 2026-08-22

The half of the bridge that does the work.

- **Idling to notice, an external event to act.** A pyRevit script runs once and
  ends; a subscription outlives it. `UIApplication.Idling` fires when Revit has
  nothing else to do, which is also the only moment the API may be used — but
  work must not happen there, because Idling holds the UI while it runs. The
  callback does a timestamp check and one directory listing, then hands off.
- **Claiming a job is an atomic rename.** Two Revit sessions watching one folder
  produce one winner per job rather than two runs against two models.
- **A failed job becomes a result, not a dead listener.** One bad job must not
  take the next five with it, and a listener that dies silently is found out
  five jobs later.
- **§12.9 in full**: no `__init__` on the external event handler, `__namespace__`
  set, the CLR type defined once per session, and the Idling delegate held in
  session state — .NET keeps the subscription and Python keeps the callable, so
  letting the second go leaves the first pointing at nothing and failing
  silently.
- Ships `bridge.echo`, which reads no workbook and writes nothing. Every command
  after it has two things that can be wrong — the wire and the work; this one
  has only the wire.
