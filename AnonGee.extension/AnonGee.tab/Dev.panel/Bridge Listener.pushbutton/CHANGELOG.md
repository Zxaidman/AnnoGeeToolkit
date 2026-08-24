# Bridge Listener — changelog

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
