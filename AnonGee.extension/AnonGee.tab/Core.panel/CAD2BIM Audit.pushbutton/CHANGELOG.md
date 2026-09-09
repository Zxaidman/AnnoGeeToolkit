# CAD2BIM Audit — changelog

Semantic versioning, read from the point of view of somebody using the tool:
**MAJOR** the tool behaves differently on purpose, **MINOR** a new capability,
**PATCH** a fix.

---

## 0.2.0

The report filled out: a sheet per category in that category's own units, and
eleven checks that ask what no verdict can.

**Added**

- **Per-category sheets carry that category's own measurements.** They were the
  Reconciliation sheet filtered, which is the intersection of what seven
  categories have in common -- and almost nothing means the same thing for a
  column and a slab. Columns now report b x h and rotation; beams report width,
  depth and RUN, because a beam's bounding box *is* its length and a "size"
  column for one is a length column under the wrong heading; slabs report area,
  thickness and hatch islands, having no cross-section at all; grids report
  direction and orientation. Identity and position stay in the same leading and
  trailing columns on every sheet, so a reader is never re-learning the frame.
- **Eleven checks**, in three families. *Drawing hygiene*: geometry drawn twice,
  outlines left open at a junction cut, entities occupying no space, stray Z in
  a plan. *Labelling*: a size label with no member to size, a label the model
  disagrees with, one mark used for two different sizes. *Model hygiene*:
  elements placed twice, elements built on the wrong storey, linear members
  whose run was clipped, a member built as the wrong category, and a type name
  that disagrees with its own dimensions.
- **Labels are parsed with cad2bim's own `parse_mark`.** `read_dxf` returns text
  with mark and size empty -- a real run fills them later, in a pass the reader
  never reaches -- so before this the audit carried every label and knew the
  size in none of them, and the most direct statement the report can make ("the
  label says 400x400 and the model says 300x300") was unreachable on a DXF.

**Changed**

- **Linear members are matched as runs, not points.** Clipping moves a centroid:
  a 1 m clip on a 6 m beam shifts it 500 mm, five times the match radius, so
  centroid matching reported one clipped beam as two members -- one missing, one
  orphan. Beams, grids and walls now match on distance to the member's span, and
  a group may hold several segments per stage, because cad2bim splits a beam at
  every column it crosses and a one-per-stage cap reported the rest as orphans.
  Collinearity (`collinear_tol_deg`, 15 deg) is what keeps that safe: without it
  the span test would pair a beam with the beam it meets at a corner. Beam
  lengths are summed over segments, and `built_segments` shows the split.
  Point-like members keep the strict one-item-per-stage rule that stops two
  distinct columns 60 mm apart from collapsing into one.
- **Centroids of closed rings are area centroids.** The vertex mean depends on
  how a shape was written down rather than where it is: a ring whose closing
  vertex repeats the first anchored 300 mm from the same ring without it, and
  the two passes over one hatch reconciled as two separate members -- two false
  findings from one correct hatch.
- Findings that would flood are aggregated. Orphan labels fired 2,351 times on a
  real 13-storey export; they are now one row per distinct mark, with the count
  and the positions in `detail`.
- A size claim is made only when exactly one sized member is within the mark
  radius. With several in range "the nearest one" is a guess, and a guess
  dressed as a size error sends somebody to check a member that was built
  correctly. Ambiguous labels are counted and reported once.
- The spatial grid all of this rests on moved to `spatial.py`, shared by the
  matcher and the checks instead of written twice.

**Fixed**

- A nested block chain read as a pile of identical entities drawn on top of each
  other -- one INSERT per nesting level sits at the very same point. Block depth
  is part of what makes two entities "the same thing".

---

## 0.1.0

First release. The walking skeleton: the whole path runs end to end, from the
button to a workbook on disk.

**Added**

- **Four independent captures.** Stage A reads the DXF with ezdxf, stage B the
  same DXF linked into Revit, stage C the placed elements in the document, and
  stage D — optional — a cad2bim run's JSON export.
- **Two passes over each drawing source.** A full-fidelity walker in this
  package, and cad2bim's own reader called verbatim. The difference between the
  two columns measures the reader instead of the drawing, which is what lets the
  report say *what is missing* rather than only *what is present*.
- **Reader gaps, named and quantified.** Entity types cad2bim's DXF reader does
  not handle; geometry nested past its depth limit of 3; hatch islands it
  discards; hatch edge paths whose arc CENTRE it reads as a boundary vertex;
  bulged polylines it flattens to straight chords, reported as a measured shape
  delta because nothing went missing and so no count can show it; and the
  solids, meshes and points `geometry_reader` ignores by design — which is why
  an imported hatch reaches no builder.
- **Read failures recorded.** cad2bim's reader swallows a malformed entity in a
  bare `except: continue`. Here each one is a row.
- **Reconciliation across stages,** matched by category, then centroid, then
  size, with a verdict that names the transition that lost the member:
  `missing_in_link`, `not_intended`, `missing_in_model`, `orphan`, plus
  `size_mismatch`, `position_mismatch` and `rotation_mismatch` for members that
  were built wrong rather than not at all.
- **`link_gap_recovered`,** an info verdict for geometry Revit's import lost and
  the build recovered from the DXF. cad2bim builds from ezdxf geometry by
  design, so this is a healthy outcome and reporting it as an error would bury
  the real findings.
- **`expected_absent`** for text, stated explicitly: the Revit API cannot read
  text inside a linked CAD file, so its absence on the Revit side is never a
  defect.
- **Both coordinate spaces on every row** — DXF-space millimetres to find the
  entity in AutoCAD, Revit-space millimetres to find the element in the model.
- **An .xlsx report** via the vendored openpyxl, needing no Excel install:
  Summary, Findings, Reconciliation, Layer census, a sheet per structural
  category, and the raw per-stage tables; plus a complete JSON sidecar for
  diffing runs between cad2bim versions.

**Notes**

- The tool is separate from cad2bim and read-only against it. It imports that
  package's readers and modifies nothing in it.
- The only write to a model is linking the DXF, in its own transaction, and only
  when a fresh link is requested. An existing link makes the run read-only.
- Stage C is a whole-document sweep, which is correct for the fresh-model
  workflow it is built for. In a populated model, pre-existing content is listed
  and reported as `orphan`.
