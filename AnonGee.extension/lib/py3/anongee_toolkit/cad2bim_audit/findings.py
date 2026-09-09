# -*- coding: utf-8 -*-
"""Turn matched groups into verdicts, and verdicts into findings you can act on.

Two rules govern everything here.

**Only judge stages that were actually captured.** If the user audited a DXF
without building anything, every member is "missing from the model" and the
report is a wall of red that says nothing. A stage that was not read is not
evidence of absence, so `_captured` gates every rule that could fire on one.

**Say which stage lost it.** A verdict names the transition, not just the
outcome: `missing_in_link` and `missing_in_model` are both "the column isn't
there" and they have entirely different fixes. That is the whole reason the
audit reads four times instead of once.

Findings carry a position in both spaces wherever one exists, because a finding
you cannot go and look at is a statistic rather than a bug report.

Revit-free.
"""

from . import checks, config, geometry, matching


class Finding(object):
    """One thing worth a person's attention, with somewhere to go and look."""

    __slots__ = ("code", "severity", "message", "category", "layer", "level",
                 "mark", "point_dxf", "point_revit", "stages", "detail")

    def __init__(self, code, severity, message, category=None, layer=None,
                 level=None, mark=None, point_dxf=None, point_revit=None,
                 stages=None, detail=None):
        self.code = code
        self.severity = severity
        self.message = message
        self.category = category
        self.layer = layer
        self.level = level
        self.mark = mark
        self.point_dxf = point_dxf
        self.point_revit = point_revit
        self.stages = list(stages or [])
        self.detail = dict(detail or {})

    @property
    def sort_key(self):
        return (config.SEVERITY_ORDER.get(self.severity, 9), self.code,
                self.category or "", self.layer or "")

    def to_dict(self):
        return {
            "code": self.code, "severity": self.severity, "message": self.message,
            "category": self.category, "layer": self.layer, "level": self.level,
            "mark": self.mark, "stages": self.stages,
            "point_dxf_mm": _round_xy(self.point_dxf),
            "point_revit_mm": _round_xy(self.point_revit),
            "detail": self.detail,
        }

    def __repr__(self):
        return "<Finding {0} {1}>".format(self.severity, self.code)


#: Stages that describe the drawing, best first. The first one present in a
#: group is the group's "source" -- what the drawing said this member should be.
_SOURCE_STAGES = (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED,
                  config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED)

_DRAWING_STAGES = (config.STAGE_DXF_RAW, config.STAGE_DXF_PARSED)
_LINK_STAGES = (config.STAGE_LINK_RAW, config.STAGE_LINK_PARSED)


def evaluate(groups, captures, settings=None, space_key="revit"):
    """Assign a verdict to every group and collect findings. Returns (verdicts, findings).

    `verdicts` is a list parallel to `groups`, so the Reconciliation sheet can
    render a group and its verdict without a second lookup.
    """
    values = config.settings(settings)
    captured = set(stage for stage, capture in captures.items() if capture is not None)

    verdicts = []
    findings = []
    for group in groups:
        verdict, group_findings = _judge(group, captured, values, space_key)
        verdicts.append(verdict)
        findings.extend(group_findings)
        # Independent of the verdict: the same member, measured by a raw pass and
        # by cad2bim's reader, should be the same SHAPE. Where it is not, the
        # reader changed the geometry rather than dropping it -- a bulged
        # polyline read as straight chords is the standing example, and it is
        # invisible to every count-based check because nothing went missing.
        findings.extend(_shape_drift(group, values))

    findings.extend(checks.run_all(groups, captures, values, space_key))
    findings.extend(_reader_gap_findings(captures))
    findings.extend(_text_findings(captures, captured))
    findings.extend(_read_error_findings(captures))
    findings.extend(_layer_findings(captures, values))
    findings.sort(key=lambda finding: finding.sort_key)
    return verdicts, findings


# --- per-group judgement ----------------------------------------------------

def _judge(group, captured, values, space_key):
    """The verdict for one candidate member, plus any findings it raises."""
    in_drawing = any(group.has(stage) for stage in _DRAWING_STAGES)
    in_link = any(group.has(stage) for stage in _LINK_STAGES)
    in_intent = group.has(config.STAGE_INTENT)
    in_model = group.has(config.STAGE_MODEL)

    link_read = _captured(captured, _LINK_STAGES)
    intent_read = config.STAGE_INTENT in captured
    model_read = config.STAGE_MODEL in captured
    drawing_read = _captured(captured, _DRAWING_STAGES)

    source = _source_stage(group)
    anchor_dxf, anchor_revit = _anchor_points(group)
    context = {
        "category": group.category, "level": group.level,
        "layer": _layer_of(group), "mark": _mark_of(group),
        "point_dxf": anchor_dxf, "point_revit": anchor_revit,
        "stages": group.stages(),
    }

    # 1. Built with nothing behind it. Only meaningful if the drawing was read.
    if in_model and drawing_read and not in_drawing and not in_link:
        return config.VERDICT_ORPHAN, [_finding(
            config.VERDICT_ORPHAN,
            "A {0} exists in the model with no matching geometry in the drawing "
            "within {1:.0f} mm. Either it predates this run, or the match radius "
            "is too tight.".format(group.category, values["match_radius_mm"]),
            context)]

    # 2. Nothing maps this geometry to a category, so no builder will ever look
    #    at it. Checked before the stage-gap rules because an unmapped layer
    #    EXPLAINS every absence downstream -- reporting those absences first
    #    would send the reader hunting for a fault that is really one missing
    #    row in the layer mapping.
    if group.category == matching.UNCLASSIFIED:
        return config.VERDICT_UNCLASSIFIED, [_finding(
            config.VERDICT_UNCLASSIFIED,
            "No layer-to-category mapping applies, so this geometry reaches no "
            "builder. Map its layer, or confirm it is annotation.",
            context)]

    # 3. The drawing has it and Revit's import does not.
    #
    #    Whether that is a defect depends entirely on what happened NEXT, and
    #    getting this wrong would make the report useless: cad2bim deliberately
    #    builds from the ezdxf geometry rather than the link, so on a healthy run
    #    a great many members are absent from the link and built correctly
    #    anyway. Calling those errors would bury the real ones.
    if in_drawing and link_read and not in_link:
        if model_read and in_model:
            findings = [_finding(
                config.VERDICT_LINK_RECOVERED,
                "Revit's CAD import lost this, and the build recovered it from "
                "the DXF. Not a defect -- but this is geometry Revit's importer "
                "cannot be trusted with.", context)]
            verdict, more = _compare(group, source, values, space_key, context)
            if verdict == config.VERDICT_OK:
                verdict = config.VERDICT_LINK_RECOVERED
            return verdict, findings + more
        return config.VERDICT_MISSING_IN_LINK, [_finding(
            config.VERDICT_MISSING_IN_LINK,
            "Present in the DXF, absent from the Revit link, and absent from the "
            "model. Revit's CAD import dropped or merged it and nothing "
            "downstream recovered it.", context)]

    # 4. Seen, and cad2bim decided against it. The gate is classification or a
    #    builder limit, both of which are cad2bim's own settings to change.
    #    Terminal only when the model does not have it either; an element that
    #    exists without appearing in the run's own output is a reporting gap in
    #    cad2bim rather than a missing member, and is worth saying so.
    if (in_drawing or in_link) and intent_read and not in_intent:
        if model_read and in_model:
            return config.VERDICT_OK, [_finding(
                config.VERDICT_NOT_INTENDED,
                "Built, but absent from the cad2bim run's JSON. The element is "
                "in the model, so this is a gap in what the run reported rather "
                "than a missing member.", context)]
        return config.VERDICT_NOT_INTENDED, [_finding(
            config.VERDICT_NOT_INTENDED,
            "Read from the drawing but not present in the cad2bim run's output. "
            "It was classified out or refused by a builder limit rather than "
            "lost -- check the layer mapping and the size limits.",
            context)]

    # 5. cad2bim asked for it and the model does not have it: Revit refused the
    #    creation, or it was created and later removed.
    if in_intent and model_read and not in_model:
        return config.VERDICT_MISSING_IN_MODEL, [_finding(
            config.VERDICT_MISSING_IN_MODEL,
            "cad2bim reported placing this, but no element matches it in the "
            "model. The creation failed, or the element was deleted after.",
            context)]

    # 6. No intent file to consult: the drawing has it and the model does not.
    if (in_drawing or in_link) and model_read and not intent_read and not in_model:
        return config.VERDICT_MISSING_IN_MODEL, [_finding(
            config.VERDICT_MISSING_IN_MODEL,
            "Present in the drawing, absent from the model. Export a cad2bim "
            "JSON and re-run the audit to tell 'never built' from 'refused'.",
            context)]

    # 7. It is everywhere it should be -- so check that it is RIGHT.
    return _compare(group, source, values, space_key, context)


def _compare(group, source, values, space_key, context):
    """Geometry checks on a member present in both the drawing and the model."""
    target = (config.STAGE_MODEL if group.has(config.STAGE_MODEL)
              else config.STAGE_INTENT if group.has(config.STAGE_INTENT) else None)
    if source is None or target is None:
        return config.VERDICT_OK, []

    findings = []
    verdict = config.VERDICT_OK

    source_size = group.size_mm(source)
    target_size = group.size_mm(target)
    if source_size and target_size:
        short_delta = abs(source_size[0] - target_size[0])
        long_delta = abs(source_size[1] - target_size[1])
        worst = max(short_delta, long_delta)
        if worst > values["size_tol_mm"]:
            verdict = config.VERDICT_SIZE_MISMATCH
            findings.append(_finding(
                config.VERDICT_SIZE_MISMATCH,
                "Section differs by {0:.0f} mm: drawing {1:.0f}x{2:.0f}, built "
                "{3:.0f}x{4:.0f}.".format(worst, source_size[0], source_size[1],
                                          target_size[0], target_size[1]),
                context, detail={"drawing_mm": list(source_size),
                                 "built_mm": list(target_size),
                                 "delta_mm": round(worst, 1),
                                 "source_stage": source, "target_stage": target}))

    offset = _offset(group, source, target, space_key)
    if offset is not None and offset > values["position_tol_mm"]:
        verdict = config.VERDICT_POSITION_MISMATCH
        findings.append(_finding(
            config.VERDICT_POSITION_MISMATCH,
            "Built {0:.0f} mm from where the drawing puts it.".format(offset),
            context, detail={"offset_mm": round(offset, 1),
                             "source_stage": source, "target_stage": target}))

    source_item = group.first(source)
    target_item = group.first(target)
    if source_item is not None and target_item is not None:
        delta = geometry.angle_delta_deg(source_item.rotation_deg,
                                         target_item.rotation_deg)
        if delta is not None and delta > values["rotation_tol_deg"]:
            if verdict == config.VERDICT_OK:
                verdict = config.VERDICT_ROTATION_MISMATCH
            findings.append(_finding(
                config.VERDICT_ROTATION_MISMATCH,
                "Built {0:.1f} deg from the drawing's orientation.".format(delta),
                context, detail={"delta_deg": round(delta, 2),
                                 "source_stage": source, "target_stage": target}))

    return verdict, findings


def _offset(group, source, target, space_key):
    source_item = group.first(source)
    target_item = group.first(target)
    if source_item is None or target_item is None:
        return None
    a = matching.match_point(source_item, space_key)
    b = matching.match_point(target_item, space_key)
    if a is None or b is None:
        return None
    return geometry.plan_distance((a[0], a[1], 0.0), (b[0], b[1], 0.0))


def _shape_drift(group, values):
    """Size differences between a raw pass and its parsed twin, per stage pair."""
    out = []
    for raw_stage, parsed_stage in config.STAGE_PAIRS:
        raw_size = group.size_mm(raw_stage)
        parsed_size = group.size_mm(parsed_stage)
        if not raw_size or not parsed_size:
            continue
        delta = max(abs(raw_size[0] - parsed_size[0]),
                    abs(raw_size[1] - parsed_size[1]))
        if delta <= values["size_tol_mm"]:
            continue
        item = group.first(raw_stage)
        out.append(Finding(
            config.VERDICT_READER_GAP,
            config.VERDICT_SEVERITY[config.VERDICT_READER_GAP],
            "Shape changes by {0:.0f} mm between the raw read and cad2bim's "
            "reader: {1:.0f}x{2:.0f} becomes {3:.0f}x{4:.0f}. The geometry was "
            "not lost, it was altered -- so no count anywhere will show it."
            .format(delta, raw_size[0], raw_size[1],
                    parsed_size[0], parsed_size[1]),
            category=group.category, layer=_layer_of(group), level=group.level,
            mark=_mark_of(group), stages=[raw_stage, parsed_stage],
            point_dxf=_xy(item.centroid_dxf) if item else None,
            point_revit=_xy(item.centroid_revit) if item else None,
            detail={"raw_mm": list(raw_size), "parsed_mm": list(parsed_size),
                    "delta_mm": round(delta, 1)}))
    return out


# --- capture-level findings -------------------------------------------------

def _reader_gap_findings(captures):
    """One finding per distinct reason cad2bim's readers dropped something.

    Aggregated by reason rather than emitted per item: a drawing with 4,000
    DIMENSION entities has one problem, not four thousand, and a Findings sheet
    that says so four thousand times hides the other nine problems.
    """
    reasons = {}
    for stage in (config.STAGE_DXF_RAW, config.STAGE_LINK_RAW):
        capture = captures.get(stage)
        if capture is None:
            continue
        for item in capture.items:
            if item.extra.get("cad2bim_reads") is not False:
                continue
            for note in item.notes:
                key = (stage, note)
                bucket = reasons.setdefault(key, {"count": 0, "types": {},
                                                  "layers": {}, "item": item})
                bucket["count"] += 1
                _tally(bucket["types"], item.source_type)
                _tally(bucket["layers"], item.layer_key)

    findings = []
    for (stage, note), bucket in sorted(reasons.items(),
                                        key=lambda row: -row[1]["count"]):
        item = bucket["item"]
        findings.append(Finding(
            config.VERDICT_READER_GAP,
            config.VERDICT_SEVERITY[config.VERDICT_READER_GAP],
            "{0} item(s) in {1}: {2}".format(bucket["count"],
                                             config.STAGE_LABELS.get(stage, stage),
                                             note),
            category=item.category, layer=_top(bucket["layers"]),
            point_dxf=_xy(item.centroid_dxf), point_revit=_xy(item.centroid_revit),
            stages=[stage],
            detail={"count": bucket["count"], "types": bucket["types"],
                    "layers": bucket["layers"]}))
    return findings


def _text_findings(captures, captured):
    """State the one absence that is expected, so it is never read as a defect.

    The Revit API cannot expose text inside a CAD link. Every drawing therefore
    has text on the DXF side and none on the Revit side, and a report that let
    that pass silently would leave the reader to wonder every single time.
    """
    if not _captured(captured, _LINK_STAGES):
        return []
    texts = 0
    for stage in _DRAWING_STAGES:
        capture = captures.get(stage)
        if capture is not None:
            texts = max(texts, sum(1 for item in capture.items if item.kind == "text"))
    if not texts:
        return []
    return [Finding(
        config.VERDICT_EXPECTED_ABSENT,
        config.SEVERITY_INFO,
        "{0} text item(s) exist in the DXF and none in the Revit link. This is "
        "expected, not a defect: the Revit API cannot read text inside a linked "
        "CAD file, which is why cad2bim reads the DXF directly for its size "
        "marks.".format(texts),
        stages=[config.STAGE_DXF_RAW, config.STAGE_LINK_RAW],
        detail={"dxf_text_items": texts, "link_text_items": 0})]


def _read_error_findings(captures):
    """Every recorded read failure, which cad2bim's own readers discard silently."""
    findings = []
    for stage, capture in captures.items():
        if capture is None or not capture.errors:
            continue
        shown = capture.errors[:20]
        findings.append(Finding(
            "read_error", config.SEVERITY_ERROR,
            "{0} read failure(s) in {1}. cad2bim's reader swallows these in a "
            "bare except, so they are invisible during a normal run.".format(
                len(capture.errors), config.STAGE_LABELS.get(stage, stage)),
            stages=[stage],
            detail={"count": len(capture.errors), "first": shown}))
    return findings


def _layer_findings(captures, values):
    """Per-layer count differences between a raw pass and its parsed twin."""
    findings = []
    for raw_stage, parsed_stage in config.STAGE_PAIRS:
        raw = captures.get(raw_stage)
        parsed = captures.get(parsed_stage)
        if raw is None or parsed is None:
            continue
        raw_counts = raw.by_layer()
        parsed_counts = parsed.by_layer()
        for layer in sorted(set(raw_counts) | set(parsed_counts)):
            before = raw_counts.get(layer, 0)
            after = parsed_counts.get(layer, 0)
            if before <= after:
                continue
            findings.append(Finding(
                "layer_shrink", config.SEVERITY_WARNING,
                "Layer {0}: {1} item(s) read raw, {2} survived cad2bim's reader "
                "({3} lost).".format(layer, before, after, before - after),
                layer=layer, stages=[raw_stage, parsed_stage],
                detail={"raw": before, "parsed": after, "lost": before - after}))
    return findings


# --- helpers ----------------------------------------------------------------

def _finding(verdict, message, context, detail=None):
    return Finding(verdict, config.severity_of(verdict), message, category=context["category"], layer=context["layer"],
                   level=context["level"], mark=context["mark"],
                   point_dxf=context["point_dxf"], point_revit=context["point_revit"],
                   stages=context["stages"], detail=detail)


def _captured(captured, stages):
    return any(stage in captured for stage in stages)


def _source_stage(group):
    for stage in _SOURCE_STAGES:
        if group.has(stage):
            return stage
    return None


def _anchor_points(group):
    """The group's position in both spaces, from whichever item has each."""
    dxf = revit = None
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is None:
            continue
        if dxf is None:
            dxf = _xy(item.centroid_dxf)
        if revit is None:
            revit = _xy(item.centroid_revit)
        if dxf is not None and revit is not None:
            break
    return dxf, revit


def _layer_of(group):
    item = group.any_item()
    return item.layer_key if item is not None else None


def _mark_of(group):
    for stage in matching.FOLD_ORDER:
        item = group.first(stage)
        if item is not None and item.mark:
            return item.mark
    return None


def _tally(bucket, key):
    key = key or "?"
    bucket[key] = bucket.get(key, 0) + 1


def _top(bucket):
    return max(bucket.items(), key=lambda row: row[1])[0] if bucket else None


def _xy(point):
    return None if point is None else (point[0], point[1])


def _round_xy(point, places=1):
    return None if point is None else [round(float(v), places) for v in point[:2]]
