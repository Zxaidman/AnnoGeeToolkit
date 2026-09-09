# -*- coding: utf-8 -*-
"""The report as plain tables. No openpyxl, no Revit -- so all of it is tested.

Splitting the sheet MODEL from the sheet WRITER is what makes the report
testable at all: the vendored openpyxl is a Windows wheel that cannot even be
imported outside Revit, so anything expressed in openpyxl calls could only ever
be checked by running Revit. Everything that decides what a report SAYS lives
here, and `workbook.py` is left with nothing but formatting.

A `Sheet` is a name, a column list and a list of rows. Cells are plain
str/int/float/None. Row order is decided here, not by the writer, because the
order is part of the meaning: worst finding first, and every table sorted so two
runs of the same drawing produce diffable files.
"""

from . import config, matching

#: Column headers whose values are numeric, so the writer can right-align and
#: number-format them without guessing from the data (a column of Nones would
#: otherwise be formatted as text and then jump to numeric on the next run).
NUMERIC_SUFFIXES = ("_mm", "_mm2", "_mm3", "_deg", "count", "_ft", "delta")


class Sheet(object):
    """One tab: a name, headers, rows, and any notes that belong above them."""

    __slots__ = ("name", "columns", "rows", "notes", "freeze", "omitted")

    def __init__(self, name, columns, rows=None, notes=None, freeze=True):
        self.name = name
        self.columns = list(columns)
        self.rows = list(rows or [])
        self.notes = list(notes or [])
        self.freeze = freeze
        self.omitted = 0

    def cap(self, limit):
        """Trim to `limit` rows, recording how many were dropped. Returns self.

        A workbook Excel refuses to open reports nothing, so the cap is real --
        but a silent cap is worse than no cap, so the count goes in the notes
        where the reader cannot miss it.
        """
        if limit and len(self.rows) > limit:
            self.omitted = len(self.rows) - limit
            self.rows = self.rows[:limit]
            self.notes.append(
                "{0} further row(s) omitted: this sheet is capped at {1}. The "
                "complete data is in the JSON sidecar.".format(self.omitted, limit))
        return self

    def is_numeric(self, index):
        header = self.columns[index].lower()
        return any(header.endswith(suffix) or suffix in header
                   for suffix in NUMERIC_SUFFIXES)

    def __repr__(self):
        return "<Sheet {0!r} cols={1} rows={2}>".format(
            self.name, len(self.columns), len(self.rows))


def build(report, settings=None):
    """Every sheet for one audit run, in tab order. `report` is a run.AuditReport."""
    values = config.settings(settings)
    limit = values["max_rows_per_sheet"]

    sheets = [
        _summary(report, values),
        _findings(report).cap(limit),
        _reconciliation(report).cap(limit),
        _layer_census(report).cap(limit),
    ]
    sheets.extend(sheet.cap(limit) for sheet in _category_sheets(report))
    sheets.extend([
        _dxf_entities(report).cap(limit),
        _dxf_text(report).cap(limit),
        _dxf_hatches(report).cap(limit),
        _link_geometry(report).cap(limit),
        _model_elements(report).cap(limit),
        _transform(report, values),
    ])
    return sheets


# --- summary ----------------------------------------------------------------

def _summary(report, values):
    """Counts per stage, verdict tallies, and per-level breakdown, in one place."""
    columns = ["Section", "Item", "Value"]
    rows = []

    rows.append(["Run", "Audit version", report.version])
    rows.append(["Run", "cad2bim version", report.cad2bim_version or "-"])
    rows.append(["Run", "Generated", report.generated])
    rows.append(["Run", "DXF", report.dxf_name or "-"])
    rows.append(["Run", "Revit link", report.link_name or "-"])
    rows.append(["Run", "Model", report.model_name or "-"])
    rows.append(["Run", "Matching space", report.diagnostics.get("space", "-")])

    for stage in config.STAGES:
        capture = report.captures.get(stage)
        label = config.STAGE_LABELS[stage]
        if capture is None:
            rows.append(["Stages", label, "not captured"])
            continue
        rows.append(["Stages", label, len(capture.items)])
        if capture.errors:
            rows.append(["Stages", label + " - read failures", len(capture.errors)])

    for stage in config.STAGES:
        capture = report.captures.get(stage)
        if capture is None:
            continue
        for kind, count in sorted(capture.by_kind().items()):
            rows.append([config.STAGE_LABELS[stage], kind, count])

    tally = {}
    for verdict in report.verdicts:
        tally[verdict] = tally.get(verdict, 0) + 1
    for verdict, count in sorted(tally.items(),
                                 key=lambda row: (_severity_rank(row[0]), row[0])):
        rows.append(["Verdicts", verdict, count])

    severities = {}
    for finding in report.findings:
        severities[finding.severity] = severities.get(finding.severity, 0) + 1
    for severity in (config.SEVERITY_ERROR, config.SEVERITY_WARNING,
                     config.SEVERITY_INFO):
        rows.append(["Findings", severity, severities.get(severity, 0)])

    for level, counts in sorted(_per_level(report).items()):
        for verdict, count in sorted(counts.items()):
            rows.append(["By level: {0}".format(level), verdict, count])

    for key in ("size_tol_mm", "position_tol_mm", "rotation_tol_deg",
                "match_radius_mm", "max_rows_per_sheet"):
        rows.append(["Thresholds", key, values[key]])

    return Sheet("Summary", columns, rows)


def _per_level(report):
    levels = {}
    for group, verdict in zip(report.groups, report.verdicts):
        key = group.level or "(no level)"
        levels.setdefault(key, {})
        levels[key][verdict] = levels[key].get(verdict, 0) + 1
    return levels


# --- findings ---------------------------------------------------------------

def _findings(report):
    columns = ["severity", "code", "message", "category", "layer", "level",
               "mark", "x_dxf_mm", "y_dxf_mm", "x_revit_mm", "y_revit_mm",
               "stages", "detail"]
    rows = []
    for finding in report.findings:
        rows.append([
            finding.severity, finding.code, finding.message,
            finding.category, finding.layer, finding.level, finding.mark,
            _coord(finding.point_dxf, 0), _coord(finding.point_dxf, 1),
            _coord(finding.point_revit, 0), _coord(finding.point_revit, 1),
            ", ".join(finding.stages), _brief(finding.detail),
        ])
    return Sheet("Findings", columns, rows)


# --- reconciliation ---------------------------------------------------------

_RECON_COLUMNS = [
    "verdict", "severity", "category", "level", "layer", "mark",
    "A_dxf_raw", "A_dxf_parsed", "B_link_raw", "B_link_parsed",
    "D_intent", "C_model",
    "drawing_short_mm", "drawing_long_mm", "built_short_mm", "built_long_mm",
    "size_delta_mm", "offset_mm", "rotation_drawing_deg", "rotation_built_deg",
    "x_dxf_mm", "y_dxf_mm", "x_revit_mm", "y_revit_mm",
    "built_type", "notes",
]


def _reconciliation(report, only=None):
    """One row per candidate member: what each stage saw, and the verdict."""
    rows = []
    for group, verdict in zip(report.groups, report.verdicts):
        if only is not None and group.category not in only:
            continue
        rows.append(_recon_row(group, verdict, report))
    rows.sort(key=_recon_sort)
    return Sheet("Reconciliation", _RECON_COLUMNS, rows)


def _recon_row(group, verdict, report):
    source = _first_present(group, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                                    config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED))
    target = _first_present(group, (config.STAGE_MODEL, config.STAGE_INTENT))
    drawing_size = group.size_mm(source) if source else None
    built_size = group.size_mm(target) if target else None
    source_item = group.first(source) if source else None
    target_item = group.first(target) if target else None

    dxf_xy = _centroid_of(group, "dxf")
    revit_xy = _centroid_of(group, "revit")
    offset = _offset(source_item, target_item, report.diagnostics.get("space", "revit"))

    return [
        verdict, config.VERDICT_SEVERITY.get(verdict, config.SEVERITY_INFO),
        group.category, group.level, _layer(group), _mark(group),
        group.count(config.STAGE_DXF_RAW), group.count(config.STAGE_DXF_PARSED),
        group.count(config.STAGE_LINK_RAW), group.count(config.STAGE_LINK_PARSED),
        group.count(config.STAGE_INTENT), group.count(config.STAGE_MODEL),
        _at(drawing_size, 0), _at(drawing_size, 1),
        _at(built_size, 0), _at(built_size, 1),
        _size_delta(drawing_size, built_size), _round(offset),
        _round(getattr(source_item, "rotation_deg", None)),
        _round(getattr(target_item, "rotation_deg", None)),
        _coord(dxf_xy, 0), _coord(dxf_xy, 1),
        _coord(revit_xy, 0), _coord(revit_xy, 1),
        getattr(target_item, "type_name", None),
        _notes(group),
    ]


#: Column indices the sort reads, resolved from the header list so that
#: reordering a column can never silently sort by the wrong one.
_X_REVIT = _RECON_COLUMNS.index("x_revit_mm")
_Y_REVIT = _RECON_COLUMNS.index("y_revit_mm")
_X_DXF = _RECON_COLUMNS.index("x_dxf_mm")
_Y_DXF = _RECON_COLUMNS.index("y_dxf_mm")


def _recon_sort(row):
    """Worst first, then by category and position, so two runs diff cleanly.

    Position falls back to DXF space: a run with no Revit link has no Revit
    coordinates at all, and sorting every row on a column of blanks would leave
    the sheet in read order -- which differs between runs and defeats diffing.
    """
    x = row[_X_REVIT] if row[_X_REVIT] is not None else row[_X_DXF]
    y = row[_Y_REVIT] if row[_Y_REVIT] is not None else row[_Y_DXF]
    return (config.SEVERITY_ORDER.get(row[1], 9), str(row[0]), str(row[2] or ""),
            _sortable(x), _sortable(y))


def _category_sheets(report):
    """One sheet per structural category, with the same columns as Reconciliation.

    Same columns on purpose: a reader who has learned the Reconciliation sheet
    has learned all seven of these, and a formula written against one works
    against any of them.
    """
    sheets = []
    for name, keys in config.CATEGORY_SHEETS:
        sheet = _reconciliation(report, only=set(keys))
        sheet.name = name
        if not sheet.rows:
            sheet.notes.append("No {0} were matched in this run.".format(name.lower()))
        sheets.append(sheet)
    return sheets


# --- census sheets ----------------------------------------------------------

def _layer_census(report):
    """Per layer, how many items each stage produced -- where losses show up."""
    stages = [stage for stage in config.STAGES if report.captures.get(stage)]
    columns = ["layer", "category"] + [config.STAGE_LABELS[s] for s in stages] + [
        "dxf_raw_to_parsed_lost", "link_raw_to_parsed_lost"]
    tables = {stage: report.captures[stage].by_layer() for stage in stages}
    categories = _layer_categories(report)

    layers = set()
    for table in tables.values():
        layers.update(table)

    rows = []
    for layer in sorted(layers):
        counts = [tables[stage].get(layer, 0) for stage in stages]
        rows.append([layer, categories.get(layer)] + counts + [
            _lost(tables, config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED, layer),
            _lost(tables, config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED, layer),
        ])
    return Sheet("Layer census", columns, rows)


def _layer_categories(report):
    mapping = {}
    for capture in report.captures.values():
        if capture is None:
            continue
        for item in capture.items:
            if item.category and item.layer_key not in mapping:
                mapping[item.layer_key] = item.category
    return mapping


def _lost(tables, raw_stage, parsed_stage, layer):
    if raw_stage not in tables or parsed_stage not in tables:
        return None
    delta = tables[raw_stage].get(layer, 0) - tables[parsed_stage].get(layer, 0)
    return delta if delta > 0 else 0


_ITEM_COLUMNS = ["stage", "kind", "source_type", "layer", "category", "handle",
                 "level", "type_name", "text", "mark",
                 "x_dxf_mm", "y_dxf_mm", "x_revit_mm", "y_revit_mm",
                 "short_mm", "long_mm", "length_mm", "area_mm2", "rotation_deg",
                 "vertices", "read_by_cad2bim", "notes"]


def _item_rows(items):
    rows = []
    for item in items:
        dxf = item.centroid_dxf
        revit = item.centroid_revit
        size = item.plan_size_mm
        reads = item.extra.get("cad2bim_reads")
        rows.append([
            item.stage, item.kind, item.source_type, item.layer_key, item.category,
            item.handle, item.level, item.type_name, item.text, item.mark,
            _coord(dxf, 0), _coord(dxf, 1), _coord(revit, 0), _coord(revit, 1),
            _at(size, 0), _at(size, 1), _round(item.length_mm),
            _round(item.area_mm2), _round(item.rotation_deg),
            len(item.points),
            "-" if reads is None else ("yes" if reads else "NO"),
            "; ".join(item.notes),
        ])
    return rows


def _dxf_entities(report):
    items = _items(report, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED),
                   exclude_kinds=("text", "hatch"))
    sheet = Sheet("DXF entities", _ITEM_COLUMNS, _item_rows(items))
    sheet.notes.append(
        "Every non-text, non-hatch entity from both DXF passes. A row whose "
        "read_by_cad2bim is NO is present in the drawing and invisible to "
        "cad2bim; its reason is in the notes column.")
    return sheet


def _dxf_text(report):
    items = _items(report, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                            config.STAGE_INTENT), kinds=("text",))
    sheet = Sheet("DXF text", _ITEM_COLUMNS, _item_rows(items))
    sheet.notes.append(
        "Text exists only on the DXF side. The Revit API cannot read text "
        "inside a linked CAD file, so the absence of a Revit column here is "
        "expected and is not a defect.")
    return sheet


def _dxf_hatches(report):
    items = _items(report, (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED),
                   kinds=("hatch",))
    columns = _ITEM_COLUMNS + ["pattern", "solid_fill", "paths", "islands",
                               "textbox_paths", "edge_paths"]
    rows = []
    for item, row in zip(items, _item_rows(items)):
        rows.append(row + [item.extra.get("pattern"),
                           item.extra.get("solid_fill"),
                           item.extra.get("path_count"),
                           item.extra.get("island_count"),
                           item.extra.get("textbox_paths"),
                           item.extra.get("edge_paths")])
    sheet = Sheet("DXF hatches", columns, rows)
    sheet.notes.append(
        "cad2bim keeps one outer ring per hatch and discards islands. An "
        "islands count above zero means the built shape is solid where the "
        "drawing shows a hole.")
    return sheet


def _link_geometry(report):
    items = _items(report, (config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED))
    sheet = Sheet("Revit link geometry", _ITEM_COLUMNS, _item_rows(items))
    sheet.notes.append(
        "Everything the Revit link exposes. Solids, meshes and points are "
        "read here and ignored by cad2bim's geometry_reader, which is why an "
        "imported hatch never reaches a builder.")
    return sheet


def _model_elements(report):
    items = _items(report, (config.STAGE_MODEL, config.STAGE_INTENT))
    columns = _ITEM_COLUMNS + ["family", "type_b_mm", "type_h_mm", "role"]
    rows = []
    for item, row in zip(items, _item_rows(items)):
        rows.append(row + [item.extra.get("family"),
                           _round(item.extra.get("type_b_mm")
                                  or item.extra.get("b_mm")),
                           _round(item.extra.get("type_h_mm")
                                  or item.extra.get("h_mm")),
                           item.extra.get("role")])
    sheet = Sheet("Model elements", columns, rows)
    sheet.notes.append(
        "Stage C is a whole-document sweep, so a model with pre-existing "
        "content lists it here and reports it as orphan.")
    return sheet


def _transform(report, values):
    columns = ["Section", "Item", "Value"]
    rows = [["Coordinates", label, value] for label, value in report.space.describe()]
    for key in sorted(values):
        rows.append(["Settings", key, values[key]])
    for stage in config.STAGES:
        capture = report.captures.get(stage)
        if capture is None:
            continue
        for key, value in sorted(capture.meta.items()):
            rows.append([config.STAGE_LABELS[stage], key, _brief(value)])
        for name, count in sorted(capture.skipped.items()):
            rows.append([config.STAGE_LABELS[stage], "skipped: " + name, count])
        for error in capture.errors[:50]:
            rows.append([config.STAGE_LABELS[stage],
                         "error: " + str(error.get("where")), error.get("detail")])
    return Sheet("Transform & settings", columns, rows)


# --- helpers ----------------------------------------------------------------

def _items(report, stages, kinds=None, exclude_kinds=()):
    out = []
    for stage in stages:
        capture = report.captures.get(stage)
        if capture is None:
            continue
        for item in capture.items:
            if kinds is not None and item.kind not in kinds:
                continue
            if item.kind in exclude_kinds:
                continue
            out.append(item)
    return out


def _first_present(group, stages):
    for stage in stages:
        if group.has(stage):
            return stage
    return None


def _centroid_of(group, space):
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is None:
            continue
        point = item.centroid_revit if space == "revit" else item.centroid_dxf
        if point is not None:
            return point
    return None


def _offset(source_item, target_item, space_key):
    from . import geometry
    if source_item is None or target_item is None:
        return None
    a = matching.match_point(source_item, space_key)
    b = matching.match_point(target_item, space_key)
    if a is None or b is None:
        return None
    return geometry.plan_distance((a[0], a[1], 0.0), (b[0], b[1], 0.0))


def _size_delta(drawing, built):
    if not drawing or not built:
        return None
    return round(max(abs(drawing[0] - built[0]), abs(drawing[1] - built[1])), 1)


def _layer(group):
    item = group.any_item()
    return item.layer_key if item is not None else None


def _mark(group):
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is not None and item.mark:
            return item.mark
    return None


def _notes(group):
    notes = []
    for stage in matching.FOLD_ORDER:
        for item in group.by_stage.get(stage, ()):
            notes.extend(item.notes)
    # Deduplicated: the same note repeated by four stages says nothing extra.
    seen = []
    for note in notes:
        if note not in seen:
            seen.append(note)
    return "; ".join(seen)


def _severity_rank(verdict):
    return config.SEVERITY_ORDER.get(
        config.VERDICT_SEVERITY.get(verdict, config.SEVERITY_INFO), 9)


def _at(pair, index):
    return None if not pair else round(float(pair[index]), 1)


def _coord(point, index):
    return None if point is None else round(float(point[index]), 1)


def _round(value, places=1):
    return None if value is None else round(float(value), places)


def _sortable(value):
    return value if isinstance(value, (int, float)) else 0.0


def _brief(value, limit=300):
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        text = str(value)
    else:
        import json
        try:
            text = json.dumps(value, default=str, sort_keys=True)
        except Exception:
            text = str(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."
