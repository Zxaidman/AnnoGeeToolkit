# Bridge Listener — changelog

## 0.4.0 — 2026-08-24

A modeless window, because a dialog is the wrong shape for a thing that watches.

- **The button opens a small window instead of a dialog.** A `TaskDialog`
  reports what was true at the instant it opened; a job arriving thirty seconds
  later was invisible. Five rounds of diagnosis went by with no way to see
  whether a job had even landed. Requested by the project owner, and it was the
  right call.
- **It shows jobs as they arrive** — id, command, status, and the counts the
  command reported — refreshed once a second from the folder. The refresh runs
  on the WPF thread and **touches no Revit API at all**, so it cannot interfere
  with a job; a test enforces that.
- **Idling is subscribed once per session and never removed.** The button flips
  a flag instead. That costs one attribute read per tick and removes the whole
  question of adding and removing a Revit event from the WPF thread.
- **Closing the window stops the watching**, deliberately: a listener running
  behind a closed window is a thing that writes to a model with nothing on
  screen saying so.
- **The dialog is still there as a fallback.** The window is the interface, not
  the mechanism, and if it will not build the listener still has to be usable.
- §12.9.4 throughout: `__slots__` rows in an `ArrayList` reassigned to
  `ItemsSource` rather than mutated, no `StaticResource` on the root `Window`,
  `Show()` then `WindowInteropHelper.Owner`.

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
