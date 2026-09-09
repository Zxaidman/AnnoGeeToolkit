# Filter View Manager — changelog

Semantic versioning, read from the point of view of someone using the tool:

| Part | Meaning |
| --- | --- |
| **MAJOR** | The tool behaves differently on purpose — a workflow moved, or what pressing a rule does to the model changed shape. |
| **MINOR** | A new capability. Everything already saved still works. |
| **PATCH** | A fix. Nothing new to learn. |

The version is declared once, in `script.py`'s `VERSION`. `bundle.yaml`'s
`Version:` line and the newest heading here are held to it — once the tool has
a window with a header to check, by a test, the way `tests/test_autolevel_ui.py`
holds Auto Level Manager's four copies together.

---

## 0.0.1 — 2026-09-09

The bundle exists. Nothing runs.

- **The ribbon slot is real from the first commit**, so the tool is covered by
  the repository's own checks straight away rather than at the end:
  `tests/test_scripts.py` holds the `#! python3` shebang and every name the
  script reads, and `tests/test_repo_docs.py` holds the README to the folder.
- **Pressing it says so.** A placeholder that opened an empty window would look
  like a broken tool; this one names its version, says what the tool will do,
  and points at the three documents beside it. The first thing anybody presses a
  new button for is to find out what it is.
- **`METHODOLOGY.md`** — how this repository works and what this tool has to
  obey: the engine and its stripped stdlib, the persistent-engine interface
  rules, what `anongee_toolkit` already provides, the design-system rules that
  are load-blockers, the three window modes, how settings survive a session, the
  two-level versioning, and the documentation contract the tests enforce. Plus
  the constraints this tool specifically will run into — §13.
- **`todo-list.md`** — the queue, seeded. Three `CRIT` items, twelve `FEAT`
  items, and four open questions for the project owner. Nothing is specified
  yet; specification is the PRD's job.
- **Placed on `Dev.panel/col3.stack`.** Dev is where tools with no in-Revit
  confirmation live — RC Automation is there for the same reason. A new stack,
  because `Testing`, `col1` and `col2` each already hold pyRevit's maximum of
  three buttons. Promotion to Advance.panel, beside the FilterParameter tools it
  is related to, belongs to the build that is confirmed working.
- **The extension version was deliberately left at 2.0.0.** Adding a tool is a
  MINOR extension change, but this one ships no capability; bumping now would
  claim one. The bump belongs in the commit that ships 0.1.0.

### Not in this version

Everything. There is no rule model, no picker, no persistence, no window, and
no dockable panel. **0.1.0** will be the first build that applies a rule to a
view, and it is blocked on `CRIT-1` and `CRIT-2` in `todo-list.md`.
