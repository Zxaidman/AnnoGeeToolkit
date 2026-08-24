# Bridge Check — changelog

## 0.2.0 — 2026-08-22

Four ways to the wire, because the first two both failed on a real run.

The tool built to explain a bridge failure was the only part of the spike that
failed: `no answer — Cannot import name WebClient / No module named request`.

- **`System.Net.WebClient` needs its own assembly on .NET 8.** Importing it
  works on .NET Framework and not on the runtime Revit 2025 uses, where the
  class moved into `System.Net.WebClient.dll`. `clr.AddReference` first.
- **`urllib.request` is not in this engine's standard library.** `re` and `csv`
  were the two known absences; this is a third.
- **Four ways, tried in order** — `WebClient`, `HttpClient`, `urllib`, and a
  hand-written GET over a raw socket. `socket` is a built-in extension module
  rather than a pure Python one, so it survives a stdlib with pieces taken out.
- **Every failure is kept, not just the last**, and the answer says **which way
  worked**. That is not tidiness: what the CPython 3 engine can reach the
  network with is something every later part of the bridge needs to know.
- The expanded panel now names where the Routes toggle is and what it reports
  when it is on.

## 0.1.0 — 2026-08-22

The diagnostic half of the bridge spike (`CRIT-1`).

- Calls `/anongee/ping` and `/anongee/status` — the same URLs an Excel button
  calls — from inside the Revit session, and shows what came back.
- **Two routes, on purpose.** `ping` takes no Revit argument and answers even
  while Revit is busy; `status` declares `uiapp` and so runs as an External
  Event. If ping answers and status does not, the server is up and the
  marshalling is not, which is a finding rather than a failure.
- Reaches the wire through `System.Net.WebClient` before `urllib`. The CPython 3
  engine ships a partial standard library — `re` and `csv` are both missing — so
  the tool that has to work when nothing else does should not bet on it.
- Read-only. No transaction, nothing written, no undo step.
