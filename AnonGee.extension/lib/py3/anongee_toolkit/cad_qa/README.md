# cad_qa — check a structural DXF before converting it

Utility 1 of the BIM automation suite. Version 1.0.0.

It reads a drawing **the way cad2bim reads it** — cad2bim's own reader, its
layer classifier, its mark grammar — and reports every place that reading is
going to produce a wrong or incomplete model.

It writes nothing, changes nothing and blocks nothing. The point is that a
bad drawing is cheapest to find out about before an hour has been spent
converting it.

**What it is not.** It is not a drafting-standards checker and says nothing
about whether a drawing is well drafted — only whether cad2bim will misread
it. Those are different claims, and a tool that mixes them is one nobody
trusts.

## Running it

```
python -m cad_qa plan.dxf                      # one drawing
python -m cad_qa /intake/2026-09               # a folder
python -m cad_qa /intake --out reports/        # one JSON per drawing
python -m cad_qa plan.dxf --xlsx qa.xlsx       # a workbook
python -m cad_qa --rules                       # the catalogue below
```

No Revit. Needs `ezdxf`, which is bundled in `lib/py3` for Windows and is
`pip install ezdxf` anywhere else. From inside Revit it is the **CAD QA**
button on the Core panel; from Python it is `cad_qa.run_file(path)`.

Drawings are assumed to be in **millimetres**. `--unit-mm 1000` for a drawing
in metres; rule G007 catches the case where that assumption was wrong.

DXF only. Nothing in this project writes back to CAD, so a DWG is converted
once on the way in (ODA File Converter) and every tool downstream reads one
format — which is what keeps the whole pipeline runnable off Windows and in
CI.

## Severity, in an advisory tool

| | |
| --- | --- |
| **Error** | cad2bim will build the **wrong** model, or leave most of it out. Not "it will crash" — a run that builds forty columns where the drawing has four hundred reports success and is an Error. |
| **Warning** | It will build, and part of it needs fixing by hand. |
| **Info** | Worth knowing before the run. Not wrong. |

Errors are meant to be rare. They were calibrated against the 23-drawing
corpus, all of which cad2bim converts: an earlier build flagged 14 of 23, the
shipped one flags 2 — both verified as drawings carrying no sizes and no
schedule. `regression_corpus` pins that share so the calibration cannot drift
back.

## The rulebook

Rule ids are **permanent**. A rule is retired rather than renumbered, so a
report filed against last month's drawing still means what it said. Severity
lives in `rules.py` and nowhere else.

### Layers and classification

| Rule | Severity | What it means |
| --- | --- | --- |
| `L001` | Warning | Layer carries geometry but classifies as unmapped |
| `L002` | Warning | No geometry classified as grid |
| `L003` | Error | No geometry classified as column |
| `L004` | Warning | No geometry classified as beam |
| `L005` | Info | No slab edge or floor layer |
| `L006` | Warning | Structural-looking layer suppressed by an annotation exclusion |
| `L007` | Warning | No text layer routed to column or beam labels |
| `L008` | Info | Hatch layer not routed to a meaning |
| `L009` | Error | Almost all geometry sits on one layer |

### Marks, labels and sizes

| Rule | Severity | What it means |
| --- | --- | --- |
| `M001` | Warning | Text looks like a mark or size label but will not parse |
| `M002` | Error | No usable size label anywhere in the drawing |
| `M003` | Warning | Labelled size is outside plausible bounds |
| `M004` | Error | One mark carries conflicting sizes |
| `M005` | Warning | Size label sits far from any member |
| `M006` | Info | Mark named with no size given anywhere |

### Geometry integrity

| Rule | Severity | What it means |
| --- | --- | --- |
| `G001` | Error | Drawing carries no usable geometry |
| `G002` | Info | Zero-length or degenerate geometry |
| `G003` | Warning | Duplicate geometry stacked on itself |
| `G004` | Warning | Structural linework carries a non-zero Z |
| `G005` | Warning | Outline does not close |
| `G006` | Warning | Geometry sits far outside the drawing's main extent |
| `G007` | Error | Drawing extent is implausible for a building plan |

### Grid and storey structure

| Rule | Severity | What it means |
| --- | --- | --- |
| `S001` | Warning | No grid labels found |
| `S002` | Warning | Grid lines run in only one direction |
| `S003` | Error | Floor boundaries and origin markers do not pair up |
| `S004` | Error | Floor boundaries present with no origin markers |
| `S005` | Warning | Origin markers present with no floor boundaries |
| `S006` | Info | Drawing carries a single plan |

Each rule also carries a **guidance** line saying what to do about it. That
is what the console prints under a finding, what the `.xlsx` RULES sheet
holds, and what `--rules` lists — a finding that names a problem without
naming the fix starts a conversation instead of ending one.

## Output

| Format | For | Notes |
| --- | --- | --- |
| Console | a person | Plain text, no markup — renders the same in a terminal, pyRevit's output window and a pasted email. |
| JSON | **a machine** | The published contract the accuracy checker and the cross-checker read. Fields are added, never renamed. No timestamp by default, so two runs of one drawing are identical byte for byte and an archive can be diffed between revisions. |
| `.xlsx` | the job folder | SUMMARY / FINDINGS / RULES. The catalogue travels inside the file, so "what does L006 mean" is answered without an email. |

## Layout

```
findings.py      Finding / Report — the severity model
rules.py         THE RULEBOOK: every rule, its severity and its fix
context.py       one drawing, read and classified once
spatial.py       a uniform grid index, so "nearest member" is not quadratic
checks/          the four families, each a pure function of a context
runner.py        one file or a folder -> Report(s)
report_*.py      console, JSON and .xlsx
cli.py           the command line
deps.py          the one place that knows cad2bim has two import names
```

`deps.py` is worth reading before anything else. Inside Revit the toolkit is
`anongee_toolkit.cad2bim.*`, and importing it that way loads Revit
assemblies; off Revit it is a top-level `cad2bim`. Both routes load the same
files, so there is no stub and no second implementation to drift.

## Tests

```
cd cad_qa/tests
python3 -m unittest discover -p "test_*.py"        # ~0.4s, no DXF, no Revit
python3 -m unittest regression_corpus              # ~20s, all 23 drawings
CAD2BIM_BLESS=1 python3 -m unittest regression_corpus   # re-record
```

Two tiers, kept apart for the reason `cad2bim/tests/README.md` gives: the
everyday suite stays under a second, because a gate that slows the inner loop
stops being run. The corpus leg borrows `cad2bim/tests/_golden.py` rather
than growing a second baseline mechanism beside it.
