# CAD2BIM Audit — changelog

Semantic versioning, read from the point of view of somebody using the tool:
**MAJOR** the tool behaves differently on purpose, **MINOR** a new capability,
**PATCH** a fix.

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
