# -*- coding: utf-8 -*-
"""The Revit half of a run: get the link, read all four stages, hand back data.

Everything Revit-specific that the audit does is here, so the pushbutton is a
dialog and `run.py` is plain Python. The output is a dict of Captures plus a
Space, which is exactly what `run.build_report` consumes -- and which a test can
build by hand.

The ONE write
-------------
Linking the DXF is the only thing this package ever writes to a model, it runs
in its own transaction (Revit refuses `Document.Link` outside one), and it
happens only when the user explicitly chooses "link a fresh copy". Choosing an
existing link makes the whole audit read-only. `link_created` in the returned
diagnostics says which happened, so the report can state it.

Revit-only.
"""

from . import classify, config, space as space_module
from .readers import cad2bim_json, dxf_parsed, dxf_raw, revit_elements, revit_geometry

#: How the link for stage B is obtained.
LINK_NEW = "new"            # link a fresh copy of the chosen DXF (one write)
LINK_EXISTING = "existing"  # use a link already in the model (read-only)
LINK_NONE = "none"          # skip stage B entirely


def capture(doc, options, settings=None, log=None):
    """Read every requested stage. Returns (captures, space, diagnostics).

    `options` keys: dxf_path, link_mode, link_instance, unit, placement,
    this_view_only, want_dxf, want_link, want_model, json_path, overrides.
    Every stage is independently optional; a stage that is not requested is
    absent from `captures` rather than empty, because "not read" and "read and
    found nothing" must never look the same to the findings.
    """
    values = config.settings(settings)
    say = log or (lambda message: None)
    diagnostics = {"link_created": False, "link_mode": options.get("link_mode")}
    captures = {}

    instance, diagnostics = _resolve_link(doc, options, diagnostics, say)
    unit_label = options.get("unit") or "Millimeter"
    if instance is not None:
        space = space_module.from_link_instance(instance, unit_label)
    else:
        # No link: the DXF still audits perfectly well on its own, in DXF space.
        space = space_module.Space(space_module.UNIT_MM.get(unit_label, 1.0))
        diagnostics["transform"] = "none (no Revit link read)"
    diagnostics["transform"] = diagnostics.get("transform", space.method)

    dxf_path = options.get("dxf_path")
    if options.get("want_dxf") and dxf_path:
        say("reading the DXF (raw census)")
        captures[config.STAGE_DXF_RAW] = dxf_raw.read(dxf_path, space, values)
        say("reading the DXF through cad2bim's reader")
        captures[config.STAGE_DXF_PARSED] = dxf_parsed.read(dxf_path, space, values)

    if options.get("want_link") and instance is not None:
        say("reading the Revit link (all geometry)")
        captures[config.STAGE_LINK_RAW] = revit_geometry.read_raw(
            doc, instance, space, values)
        say("reading the Revit link through cad2bim's reader")
        captures[config.STAGE_LINK_PARSED] = revit_geometry.read_parsed(
            doc, instance, space, values)

    if options.get("want_model"):
        say("sweeping the model for placed elements")
        captures[config.STAGE_MODEL] = revit_elements.read(doc, space, values)

    json_path = options.get("json_path")
    if json_path:
        say("reading the cad2bim run's JSON")
        captures[config.STAGE_INTENT] = cad2bim_json.read(json_path, space, values)

    diagnostics["classification"] = classify.apply(captures, options.get("overrides"))
    return captures, space, diagnostics


def _resolve_link(doc, options, diagnostics, say):
    """Return (ImportInstance or None, diagnostics), linking only if asked to."""
    mode = options.get("link_mode", LINK_NONE)

    if mode == LINK_EXISTING:
        instance = options.get("link_instance")
        if instance is None:
            diagnostics["link_error"] = "no existing CAD link was chosen"
        return instance, diagnostics

    if mode == LINK_NEW:
        path = options.get("dxf_path")
        if not path:
            diagnostics["link_error"] = "no DXF chosen to link"
            return None, diagnostics
        try:
            from anongee_toolkit.cad2bim.readers import dxf_linker
            say("linking the DXF")
            instance = dxf_linker.link_dxf(
                doc, path, options.get("unit") or "Millimeter",
                options.get("placement") or "Auto - Center to Center",
                this_view_only=bool(options.get("this_view_only")))
            diagnostics["link_created"] = True
            return instance, diagnostics
        except Exception as error:
            # A failed link must not lose the DXF audit: stage A is still worth
            # having, and the reason the link failed is itself a finding.
            diagnostics["link_error"] = str(error)
            return None, diagnostics

    return None, diagnostics


def existing_links(doc):
    """[(label, ImportInstance)] for every linked CAD in the model."""
    try:
        from anongee_toolkit.cad2bim.readers.cad_links import (find_cad_links,
                                                               describe_link)
    except ImportError:
        return []
    out = []
    for instance in find_cad_links(doc):
        try:
            out.append((describe_link(doc, instance), instance))
        except Exception:
            continue
    return out
