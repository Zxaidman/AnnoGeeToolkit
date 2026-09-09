# -*- coding: utf-8 -*-
"""Give every item the category cad2bim would give it.

Categories are what the matcher buckets on, so if the audit classified layers
its own way it would be reconciling against a pipeline that does not exist. It
therefore calls `cad2bim.classify.layers` directly -- the same three routers a
real run uses, each for the kind of thing it routes:

    geometry  classify_layer         linework -> column / beam / slab_edge / ...
    text      classify_text_layer    labels   -> column text / grid text / ignore
    hatch     hatch_category         regions  -> column fill / fold / sunk / cutout

They are genuinely different mappings in cad2bim (a hatch layer and a linework
layer of the same name can mean different things), and collapsing them into one
would put a hatch and the lines drawn over it into the same bucket.

`overrides` accepts the mappings a real run used -- the layer table the user
edited in cad2bim's dialog -- so the audit can be run against the same routing
the build actually had, rather than against the defaults.

Stages C and D already carry a category from their own source and are left
alone: a placed structural column IS a column, and re-deriving that from a layer
name would only introduce a way to get it wrong.

Revit-free.
"""

from . import config


def apply(captures, overrides=None, layers=None, marks=None):
    """Classify every item, and parse every label, in place. Returns diagnostics.

    `layers` and `marks` override which modules do the work; they exist for the
    tests, which load cad2bim's modules from their files. In Revit both are None
    and the real modules are imported.
    """
    overrides = overrides or {}
    module = layers
    if module is None:
        try:
            from anongee_toolkit.cad2bim.classify import layers as module
        except ImportError as error:
            return {"error": "cad2bim.classify.layers unavailable: {0}".format(error)}

    geometry_map = overrides.get("geometry") or {}
    text_map = overrides.get("text") or {}
    hatch_map = overrides.get("hatch") or {}

    counts = {}
    unmapped_layers = set()
    for stage, capture in captures.items():
        if capture is None or stage in (config.STAGE_MODEL, config.STAGE_INTENT):
            continue
        for item in capture.items:
            if item.category:
                continue
            category = _category_for(module, item, geometry_map, text_map, hatch_map)
            if category and category != _unmapped(module):
                item.category = category
                counts[category] = counts.get(category, 0) + 1
            elif item.layer:
                unmapped_layers.add(item.layer)

    parsed = _parse_marks(captures, marks)
    return {"assigned": counts,
            "unmapped_layers": sorted(unmapped_layers),
            "marks_parsed": parsed,
            "overrides_used": sorted(k for k, v in overrides.items() if v)}


def _parse_marks(captures, marks=None):
    """Fill mark / b_mm / h_mm on every text item, using cad2bim's own parser.

    Without this the label checks can only ever fire on stage D. `read_dxf`
    returns TextRecords with those fields empty -- a real cad2bim run fills them
    later, in `marks.parse_texts`, which the reader never reaches on its own. So
    an audit of a DXF would carry every label and know the size in none of them,
    and "the label says 400x400 and the model says 300x300" -- the most direct
    statement the report can make -- would be unreachable on the one input the
    tool is most often pointed at.

    cad2bim's parser is used rather than a regex of our own for the usual
    reason: a label the build cannot read is not one the audit should claim to.
    """
    module = marks
    if module is None:
        try:
            from anongee_toolkit.cad2bim.classify import marks as module
        except ImportError:
            return 0
    parse = getattr(module, "parse_mark", None)
    if parse is None:
        return 0

    count = 0
    for stage, capture in captures.items():
        if capture is None or stage == config.STAGE_INTENT:
            continue                     # stage D arrives already parsed
        for item in capture.items:
            if item.kind != "text" or not item.text:
                continue
            if item.mark and item.extra.get("b_mm"):
                continue
            try:
                name, b_mm, h_mm = parse(item.text)
            except Exception:
                continue
            if name and not item.mark:
                item.mark = name
            if b_mm and item.extra.get("b_mm") is None:
                item.extra["b_mm"] = b_mm
                item.extra["h_mm"] = h_mm
            if name or b_mm:
                count += 1
    return count


def _category_for(module, item, geometry_map, text_map, hatch_map):
    layer = item.layer
    if item.kind == "text":
        category = _call(module, "classify_text_layer", text_map.get(layer), layer)
        # A text layer routed to "ignore" is a deliberate decision, not a gap;
        # carrying it through means the report can distinguish annotation the
        # user chose to drop from geometry nothing knew what to do with.
        return category
    if item.kind == "hatch":
        pattern = item.extra.get("pattern") or item.type_name
        if hatch_map:
            try:
                return module.hatch_category(hatch_map, item.layer_key, pattern)
            except Exception:
                pass
        return _safe(lambda: module.classify_hatch_layer(layer))
    return _call(module, "classify_layer", geometry_map.get(layer), layer)


def _call(module, function_name, override, layer):
    if override:
        return override
    function = getattr(module, function_name, None)
    if function is None:
        return None
    return _safe(lambda: function(layer))


def _unmapped(module):
    return getattr(module, "CATEGORY_UNMAPPED", "unmapped")


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None
