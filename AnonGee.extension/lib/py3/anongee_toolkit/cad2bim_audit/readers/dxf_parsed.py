# -*- coding: utf-8 -*-
"""Stage A, as cad2bim sees it: the same DXF through cad2bim's own reader.

The point of this pass is that it is NOT independent. It calls
`cad2bim.readers.dxf_reader.read_dxf` verbatim and converts the records it
returns into audit items, so the numbers in this column are exactly the numbers
the real pipeline works from. Set beside the raw census, the difference is a
measurement of the reader rather than of the drawing.

Nothing in cad2bim is modified or monkey-patched to get this. If the reader is
changed tomorrow, this column follows it automatically, which is the property
that keeps the audit honest.

Revit-free: `dxf_reader` imports only ezdxf and `cad2bim.model`.
"""

from .. import config
from ..model import AuditItem, Capture


def read(dxf_path, space, settings=None, classifier=None, reader=None):
    """Read `dxf_path` through cad2bim's reader into a Capture.

    `classifier` is an optional callable taking a layer name and returning a
    cad2bim category; when given, every item is classified exactly as a real run
    would classify it, so a category mismatch downstream is attributable.

    `reader` overrides which module is called. It exists for the tests, which
    load `dxf_reader` from its file to avoid importing the cad2bim package (whose
    __init__ pulls in Revit assemblies). In Revit it is always None and the real
    module is imported -- the audit must never read through a stand-in.
    """
    config.settings(settings)   # validate overrides even though none are used yet
    capture = Capture(config.STAGE_DXF_PARSED, _basename(dxf_path))

    dxf_reader = reader
    if dxf_reader is None:
        try:
            from anongee_toolkit.cad2bim.readers import dxf_reader
        except ImportError as error:
            capture.fail("import",
                         "cad2bim.readers.dxf_reader unavailable: {0}".format(error))
            return capture

    try:
        result = dxf_reader.read_dxf(dxf_path)
    except Exception as error:
        capture.fail("read_dxf", error)
        return capture

    capture.source_name = result.source_name
    for record in result.records:
        capture.add(_curve_item(record, space, classifier))
    for text in result.texts:
        capture.add(_text_item(text, space, classifier))
    for region in result.regions:
        capture.add(_region_item(region, space, classifier))

    capture.meta["curves"] = len(result.records)
    capture.meta["texts"] = len(result.texts)
    capture.meta["regions"] = len(result.regions)
    return capture


def _curve_item(record, space, classifier):
    points_dxf, points_revit = space.from_dxf(record.points)
    item = AuditItem(
        config.STAGE_DXF_PARSED, "curve", source_type=record.kind,
        layer=record.layer, points_dxf=points_dxf, points_revit=points_revit,
        native_space="dxf", category=_classify(record, classifier),
    )
    # cad2bim's own length, kept verbatim rather than recomputed: if the two
    # disagree, that disagreement is itself worth seeing.
    if record.length_ft is not None:
        item.extra["length_mm"] = record.length_ft * config.MM_PER_FT
    item.extra["vertex_count"] = len(record.points)
    return item


def _text_item(record, space, classifier):
    points_dxf, points_revit = space.from_dxf([record.point] if record.point else [])
    item = AuditItem(
        config.STAGE_DXF_PARSED, "text", source_type="text", layer=record.layer,
        points_dxf=points_dxf, points_revit=points_revit, native_space="dxf",
        text=record.text, mark=record.mark, category=_classify(record, classifier),
    )
    item.extra["rotation_deg"] = record.rotation_deg
    # b_mm/h_mm are filled by marks.parse_mark during a real run; carrying them
    # lets the report say a label was READ but its size never reached the model.
    item.extra["b_mm"] = record.b_mm
    item.extra["h_mm"] = record.h_mm
    return item


def _region_item(record, space, classifier):
    points_dxf, points_revit = space.from_dxf(record.points)
    item = AuditItem(
        config.STAGE_DXF_PARSED, "hatch", source_type="region", layer=record.layer,
        points_dxf=points_dxf, points_revit=points_revit, native_space="dxf",
        type_name=record.pattern, category=_classify(record, classifier),
    )
    item.extra["pattern"] = record.pattern
    item.extra["solid_fill"] = record.solid
    return item


def _classify(record, classifier):
    """The record's own category if a run already set one, else the classifier's."""
    if getattr(record, "category", None):
        return record.category
    if classifier is None:
        return None
    try:
        return classifier(record.layer)
    except Exception:
        return None


def _basename(path):
    import os
    return os.path.basename(path or "")
