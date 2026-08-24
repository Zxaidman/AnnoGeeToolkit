# Bridge Check — changelog

## 0.4.0 — 2026-08-24

It answers in a second, and it always answers.

- **The port is probed before any HTTP.** A refused TCP connection comes back in
  microseconds; when nothing is listening, four HTTP attempts against two routes
  are wasted minutes. A run of 0.3.0 took exactly that and showed nothing.
- **`WebClient` goes last, and every other way now takes a timeout.**
  `WebClient.DownloadString` carries a **hundred-second default** and cannot have
  one set without subclassing it, so it is the last thing tried rather than the
  first. `HttpClient` leads.
- **`/ping` gets five seconds, `/status` twenty.** `/ping` touches no Revit and
  should answer at once; `/status` runs as an External Event and legitimately
  waits for Revit to be idle. Giving them the same number made a working bridge
  look slow and a dead one look hung.
- **The report goes to the pyRevit console, not only a dialog** — and that is the
  important half. Console output can be selected and pasted; a dialog has to be
  retyped or screenshotted.
- **It cannot produce no output.** The previous version could, and did. A
  diagnostic that shows nothing is broken by definition, so the whole run is
  wrapped and its own failure becomes the report.

## 0.3.0 — 2026-08-22

The reason moves into the headline, and the tool can now answer when nothing
is listening at all.

- **"No answer" now says why, in the main panel.** A run reported it twice with
  the cause folded away behind *See details*, which nobody expands — so the tool
  built to explain a failure explained nothing, for the second release running.
- **It reads the startup record.** When nothing answers there are three causes
  and they look identical: the Routes server is off, the startup script failed
  to register, or the extension never reloaded. `startup.py` now writes a record
  on every load precisely because when *it* is the guilty one there is no route
  left to ask. The dialog says which of the three it is and what to do about it.

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
