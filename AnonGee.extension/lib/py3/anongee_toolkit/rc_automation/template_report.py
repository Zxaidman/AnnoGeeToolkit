# -*- coding: utf-8 -*-
"""Turn what a model contains into Markdown somebody can read and diff.

Pure: data in, text out, no Revit anywhere — which is what makes the shape of
the report arguable without opening a model, and testable against fixtures.

**Written for two readers at once.** A person opening it wants to find their
column family in ten seconds; a diff wants stable ordering so that
re-extracting an unchanged model produces an identical file. Both are served by
the same rule: everything is sorted, nothing carries a timestamp, and no line
depends on how many elements happened to come back.
"""

__version__ = "0.1.0"

#: Sections, in the order they are written.
SECTIONS = ("model", "datum", "categories", "families", "parameters", "views")


def render(data):
    """The whole report. ``str``."""
    lines = []
    _model(lines, (data or {}).get("model") or {})
    _datum(lines, (data or {}).get("datum") or {})
    _categories(lines, (data or {}).get("categories") or [])
    _families(lines, (data or {}).get("families") or [])
    _parameters(lines, (data or {}).get("parameters") or {})
    _views(lines, (data or {}).get("views") or {})
    _footer(lines)
    return "\n".join(lines).rstrip() + "\n"


def _model(lines, model):
    lines.append("# {0}".format(model.get("title") or "This model"))
    lines.append("")
    lines.append("What this model contains, written out so it can be read, "
                 "diffed and argued with outside Revit.")
    lines.append("")
    lines.append("A `.rvt` is a compound binary that only Revit opens, so a "
                 "template cannot be reviewed anywhere else. This is the model "
                 "describing itself instead.")
    lines.append("")
    if model.get("path"):
        lines.append("- **File** — `{0}`".format(model["path"]))
    offset = model.get("survey_offset_mm")
    if offset is not None:
        lines.append("- **Survey offset** — {0:g} mm. What the Survey Point "
                     "reads where the Project Base Point reads zero.".format(
                         offset))
    elif model.get("survey_note"):
        lines.append("- **Survey offset** — not readable: {0}".format(
            model["survey_note"]))
    lines.append("")


def _datum(lines, datum):
    levels = datum.get("levels") or []
    grids = datum.get("grids") or []
    if not levels and not grids:
        return

    lines.append("## Datum")
    lines.append("")
    lines.append("What `levels.sync` and `grids.sync` match against. A name "
                 "here is what the workbook has to write to reach this level "
                 "— they are matched exactly, never fuzzily.")
    lines.append("")

    if levels:
        lines.append("### Levels")
        lines.append("")
        lines.append("| Name | Elevation (mm) |")
        lines.append("| --- | ---: |")
        for level in sorted(levels, key=lambda row: row.get("elevation_mm")
                            if row.get("elevation_mm") is not None else 0):
            lines.append("| `{0}` | {1} |".format(
                level.get("name", ""), _number(level.get("elevation_mm"))))
        lines.append("")

    if grids:
        lines.append("### Grids")
        lines.append("")
        lines.append("| Name | From | To |")
        lines.append("| --- | --- | --- |")
        for grid in grids:
            segment = grid.get("segment_mm")
            if segment:
                start = "{0}, {1}".format(_number(segment[0][0]),
                                          _number(segment[0][1]))
                end = "{0}, {1}".format(_number(segment[1][0]),
                                        _number(segment[1][1]))
            else:
                start = end = "not a straight line"
            lines.append("| `{0}` | {1} | {2} |".format(
                grid.get("name", ""), start, end))
        lines.append("")


def _categories(lines, categories):
    if not categories:
        return
    lines.append("## Categories")
    lines.append("")
    lines.append("What the model is made of. **Types** is what a template "
                 "carries; **instances** is what a project has built with them "
                 "— a template with types and no instances is doing its job.")
    lines.append("")
    lines.append("| Category | Types | Instances |")
    lines.append("| --- | ---: | ---: |")
    for row in categories:
        if "error" in row:
            lines.append("| _could not be read: {0}_ | | |".format(
                row["error"]))
            continue
        lines.append("| {0} | {1} | {2} |".format(
            row.get("name", ""), row.get("types", 0), row.get("instances", 0)))
    lines.append("")


def _families(lines, families):
    if not families:
        return
    lines.append("## Families and types")
    lines.append("")
    lines.append("Every family in the model and every type inside it. A **type "
                 "mark** in bold is what a workbook's `TypeMark` column has to "
                 "say to reach that type.")
    lines.append("")

    by_category = {}
    for row in families:
        if "error" in row:
            lines.append("_Families could not be read: {0}_".format(
                row["error"]))
            lines.append("")
            continue
        by_category.setdefault(row.get("category", "(none)"), []).append(row)

    for category in sorted(by_category):
        lines.append("### {0}".format(category))
        lines.append("")
        for family in sorted(by_category[category],
                             key=lambda row: row.get("family", "")):
            kind = "loadable" if family.get("loadable") else "system"
            lines.append("- **{0}** _({1})_".format(
                family.get("family", "(unnamed)"), kind))
            for element_type in family.get("types", []):
                mark = element_type.get("mark") or ""
                sizes = _sizes(element_type.get("parameters") or {})
                lines.append("  - `{0}`{1}{2}".format(
                    element_type.get("name", ""),
                    " — **{0}**".format(mark) if mark else "",
                    " — {0}".format(sizes) if sizes else ""))
        lines.append("")


def _sizes(parameters):
    """The two or three numbers a reader wants beside a type name."""
    wanted = ("b", "h", "Width", "Depth", "Thickness", "Length", "Diameter",
              "Default Thickness")
    found = []
    for name in wanted:
        if name in parameters and parameters[name]:
            found.append("{0} {1}".format(name, parameters[name]))
    return ", ".join(found[:4])


def _parameters(lines, parameters):
    if not parameters:
        return
    lines.append("## Parameters")
    lines.append("")
    lines.append("**The section the workbook needs most.** Where a parameter "
                 "comes from decides whether a value written into it survives: "
                 "a shared parameter can be scheduled and tagged and lives "
                 "through a family reload; a family parameter cannot leave its "
                 "family; a project parameter exists only in this file. A "
                 "workbook that writes to the wrong kind produces a value that "
                 "quietly disappears.")
    lines.append("")

    for scope, title, note in (
            ("shared", "Shared", "Scheduleable, taggable, and survives a "
             "family reload. **This is what a workbook should write to.**"),
            ("project", "Project", "Bound in this file only. A value written "
             "here does not travel to another model."),
            ("global", "Global", "One value for the whole project, not per "
             "element."),
            ("family", "Family", "Belongs to the family and cannot be reached "
             "from outside it.")):
        rows = parameters.get(scope)
        if not rows:
            continue
        lines.append("### {0}".format(title))
        lines.append("")
        lines.append(note)
        lines.append("")
        if scope == "family":
            _family_parameters(lines, rows)
        else:
            _bound_parameters(lines, rows)


def _bound_parameters(lines, rows):
    lines.append("| Name | Type | Per | Categories |")
    lines.append("| --- | --- | --- | --- |")
    for row in rows:
        lines.append("| `{0}` | {1} | {2} | {3} |".format(
            row.get("name", ""), _short(row.get("kind", "")),
            "instance" if row.get("instance") else "type",
            ", ".join(row.get("categories") or []) or "—"))
    lines.append("")


def _family_parameters(lines, rows):
    for family in rows:
        names = family.get("parameters") or []
        writable = [row for row in names if not row.get("read_only")]
        lines.append("<details><summary><strong>{0}</strong> — {1} "
                     "parameters, {2} writable</summary>".format(
                         family.get("family", ""), len(names), len(writable)))
        lines.append("")
        lines.append("| Name | Type | Shared | Writable |")
        lines.append("| --- | --- | --- | --- |")
        for row in names:
            lines.append("| `{0}` | {1} | {2} | {3} |".format(
                row.get("name", ""), _short(row.get("kind", "")),
                "yes" if row.get("shared") else "no",
                "no" if row.get("read_only") else "yes"))
        lines.append("")
        lines.append("</details>")
        lines.append("")


def _views(lines, views):
    templates = views.get("templates") or []
    sheets = views.get("sheets") or []
    blocks = views.get("title_blocks") or []
    if not (templates or sheets or blocks):
        return

    lines.append("## Views, sheets and title blocks")
    lines.append("")
    lines.append("What `views.sync` and `sheets.sync` will have to work with.")
    lines.append("")
    if templates:
        lines.append("**View templates** — {0}".format(", ".join(
            "`{0}`".format(row.get("name", "")) for row in templates)))
        lines.append("")
    if blocks:
        lines.append("**Title blocks** — {0}".format(", ".join(
            "`{0}`".format(row.get("name", "")) for row in blocks)))
        lines.append("")
    if sheets:
        lines.append("**Sheets** — {0}".format(len(sheets)))
        lines.append("")
        lines.append("| Number | Name |")
        lines.append("| --- | --- |")
        for sheet in sheets:
            lines.append("| {0} | {1} |".format(sheet.get("number", ""),
                                                sheet.get("name", "")))
        lines.append("")


def _footer(lines):
    lines.append("---")
    lines.append("")
    lines.append("_Written by AnonGee **Extract Template**. Read-only — "
                 "nothing in the model was changed. Re-running it on an "
                 "unchanged model produces an identical file, so this is worth "
                 "committing and diffing._")


def _short(kind):
    """``autodesk.spec.aec:length-2.0.0`` is not a thing anybody wants to read."""
    text = str(kind or "")
    if ":" in text:
        text = text.split(":")[-1]
    if "-" in text:
        text = text.split("-")[0]
    return text or "—"


def _number(value):
    if value is None:
        return "—"
    return "{0:g}".format(value)
