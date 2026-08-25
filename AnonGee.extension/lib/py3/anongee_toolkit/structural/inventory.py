# -*- coding: utf-8 -*-
"""What a model contains, as text somebody can read.

A ``.rvt`` is a compound binary that only Revit opens. There is no library that
reads one, and there will not be — which means a template cannot be reviewed,
diffed, or discussed anywhere except inside Revit, by one person at a time.

So the model describes itself. This walks it once and returns plain data;
:mod:`report` turns that into Markdown. Everything here is **read-only** — no
transaction is opened and nothing is written — because a tool that inspects a
template must be safe to point at the real one.

**Every parameter carries where it came from.** That is the part that matters
for the workbook: a shared parameter can be scheduled and tagged and survives a
family reload; a family parameter cannot leave its family; a project parameter
exists only in this file. A workbook that writes to the wrong kind produces a
value that vanishes on the next reload, and nothing says why.
"""

__version__ = "0.1.0"

#: Parameter scopes, in the order a reader wants them.
SHARED = "shared"
PROJECT = "project"
GLOBAL = "global"
FAMILY = "family"
BUILT_IN = "built-in"

#: How many instances of a category to count before giving up on precision.
#: A model with a hundred thousand elements should not take a minute to
#: describe itself.
COUNT_LIMIT = 200000


def gather(doc):
    """Everything, as nested plain data. ``{}`` of lists and dicts.

    One pass per section rather than one pass per element: a model is walked
    for its categories, then its families, then its parameters. Slower to read,
    faster to run, and each section fails on its own — a model whose global
    parameters raise still produces a family tree.
    """
    return {
        "model": _model(doc),
        "categories": _safe(_categories, doc, []),
        "families": _safe(_families, doc, []),
        "parameters": _safe(_parameters, doc, {}),
        "datum": _safe(_datum, doc, {}),
        "views": _safe(_views, doc, {}),
    }


def _safe(function, doc, fallback):
    try:
        return function(doc)
    except Exception as error:
        if isinstance(fallback, dict):
            return {"error": str(error)}
        return [{"error": str(error)}]


def _model(doc):
    from anongee_toolkit.structural import coordinates
    offset, note = coordinates.survey_offset_mm(doc)
    return {
        "title": _title(doc),
        "path": _path(doc),
        "survey_offset_mm": offset,
        "survey_note": note,
    }


def _categories(doc):
    """``[{name, kind, count}]`` — what the model uses, and how much of it.

    Only categories with something in them. A template's empty categories are
    noise; what is being asked is *what is this model made of*.
    """
    from Autodesk.Revit.DB import FilteredElementCollector

    counts = {}
    for element in (FilteredElementCollector(doc)
                    .WhereElementIsNotElementType()
                    .ToElements()):
        try:
            category = element.Category
            if category is None:
                continue
            name = category.Name
        except Exception:
            continue
        counts[name] = counts.get(name, 0) + 1
        if len(counts) > COUNT_LIMIT:
            break

    types = {}
    for element in (FilteredElementCollector(doc)
                    .WhereElementIsElementType()
                    .ToElements()):
        try:
            category = element.Category
            if category is None:
                continue
            name = category.Name
        except Exception:
            continue
        types[name] = types.get(name, 0) + 1

    rows = []
    for name in sorted(set(list(counts) + list(types))):
        rows.append({"name": name,
                     "instances": counts.get(name, 0),
                     "types": types.get(name, 0)})
    return rows


def _families(doc):
    """``[{category, family, types: [{name, mark, parameters}]}]``.

    Loadable families and system families both, because a template's floor
    types matter as much as its column families and a reader should not have to
    know which is which to find one.
    """
    from Autodesk.Revit.DB import (ElementType, FamilySymbol,
                                   FilteredElementCollector)

    grouped = {}
    for element_type in (FilteredElementCollector(doc)
                         .OfClass(ElementType)
                         .ToElements()):
        try:
            category = element_type.Category
            category_name = category.Name if category is not None else "(none)"
            name = _name(element_type)
            if not name:
                continue
            family = _family_name(element_type)
            loadable = isinstance(element_type, FamilySymbol)
        except Exception:
            continue

        key = (category_name, family, loadable)
        grouped.setdefault(key, []).append({
            "name": name,
            "mark": _type_mark(element_type),
            "parameters": _type_parameters(element_type),
        })

    rows = []
    for (category_name, family, loadable), types in sorted(grouped.items()):
        rows.append({"category": category_name, "family": family,
                     "loadable": loadable,
                     "types": sorted(types, key=lambda item: item["name"])})
    return rows


def _parameters(doc):
    """``{scope: [{name, category/binding, kind, type_or_instance}]}``.

    The section the workbook actually needs. A value written to the wrong scope
    is a value that disappears on the next family reload, and the run that
    wrote it says it succeeded.
    """
    found = {SHARED: [], PROJECT: [], GLOBAL: [], FAMILY: []}

    found[GLOBAL] = _global_parameters(doc)
    bound = _bindings(doc)
    for row in bound:
        found[SHARED if row["shared"] else PROJECT].append(row)
    found[FAMILY] = _family_parameters(doc)
    return found


def _bindings(doc):
    """Project and shared parameters bound in this file."""
    from Autodesk.Revit.DB import InstanceBinding

    rows = []
    try:
        iterator = doc.ParameterBindings.ForwardIterator()
    except Exception:
        return rows

    iterator.Reset()
    while iterator.MoveNext():
        try:
            definition = iterator.Key
            binding = iterator.Current
        except Exception:
            continue
        categories = []
        try:
            for category in binding.Categories:
                categories.append(category.Name)
        except Exception:
            pass
        rows.append({
            "name": _definition_name(definition),
            "kind": _definition_kind(definition),
            "group": _definition_group(definition),
            "categories": sorted(categories),
            "instance": isinstance(binding, InstanceBinding),
            "shared": _is_shared(definition),
            "guid": _guid(definition),
        })
    return sorted(rows, key=lambda row: row["name"].lower())


def _global_parameters(doc):
    """Global parameters — one value for the whole project."""
    from Autodesk.Revit.DB import GlobalParametersManager

    rows = []
    try:
        ids = GlobalParametersManager.GetAllGlobalParameters(doc)
    except Exception:
        return rows
    for element_id in ids:
        try:
            parameter = doc.GetElement(element_id)
            rows.append({"name": parameter.Name,
                         "kind": _value_kind(parameter),
                         "categories": [], "instance": False,
                         "shared": False, "guid": ""})
        except Exception:
            continue
    return sorted(rows, key=lambda row: row["name"].lower())


def _family_parameters(doc):
    """Parameters that belong to a loaded family, per family.

    Read from one type of each family rather than by opening the family
    document: opening every family to inspect it would take minutes and a
    great deal of memory, and the parameter list is visible from a type.
    """
    from Autodesk.Revit.DB import FamilySymbol, FilteredElementCollector

    seen = {}
    for symbol in (FilteredElementCollector(doc)
                   .OfClass(FamilySymbol)
                   .ToElements()):
        try:
            family = _family_name(symbol)
            if family in seen:
                continue
            names = []
            for parameter in symbol.Parameters:
                definition = parameter.Definition
                names.append({
                    "name": _definition_name(definition),
                    "kind": _definition_kind(definition),
                    "shared": _is_shared(definition),
                    "read_only": bool(parameter.IsReadOnly),
                })
            seen[family] = sorted(names, key=lambda row: row["name"].lower())
        except Exception:
            continue
    return [{"family": family, "parameters": names}
            for family, names in sorted(seen.items())]


def _datum(doc):
    """Levels and grids, with the numbers the workbook would have to match."""
    from anongee_toolkit.structural import grids as grid_module
    from anongee_toolkit.structural import levels as level_module

    rows = {"levels": [], "grids": []}
    try:
        for name, _element_id, elevation_mm in level_module.levels(doc):
            rows["levels"].append({"name": name, "elevation_mm": elevation_mm})
    except Exception:
        pass
    try:
        for name, grid in sorted(grid_module.grids(doc).items()):
            segment = grid_module.segment_mm(grid)
            rows["grids"].append({"name": name, "segment_mm": segment})
    except Exception:
        pass
    return rows


def _views(doc):
    """View templates, sheets and title blocks — the drawing half."""
    from Autodesk.Revit.DB import (BuiltInCategory, FamilyInstance,
                                   FilteredElementCollector, View,
                                   ViewSheet)

    rows = {"templates": [], "sheets": [], "title_blocks": []}
    for view in FilteredElementCollector(doc).OfClass(View).ToElements():
        try:
            if view.IsTemplate:
                rows["templates"].append({"name": _name(view),
                                          "kind": str(view.ViewType)})
        except Exception:
            continue
    for sheet in FilteredElementCollector(doc).OfClass(ViewSheet).ToElements():
        try:
            rows["sheets"].append({"number": sheet.SheetNumber,
                                   "name": _name(sheet)})
        except Exception:
            continue
    seen = set()
    for block in (FilteredElementCollector(doc)
                  .OfCategory(BuiltInCategory.OST_TitleBlocks)
                  .OfClass(FamilyInstance)
                  .ToElements()):
        try:
            label = "{0} : {1}".format(_family_name(block),
                                       _name(doc.GetElement(block.GetTypeId())))
        except Exception:
            continue
        if label not in seen:
            seen.add(label)
            rows["title_blocks"].append({"name": label})
    rows["templates"].sort(key=lambda row: row["name"])
    rows["sheets"].sort(key=lambda row: row["number"])
    rows["title_blocks"].sort(key=lambda row: row["name"])
    return rows


# ---------------------------------------------------------------------------
# The small Revit awkwardnesses, in one place
# ---------------------------------------------------------------------------

def _type_parameters(element_type):
    """The dimensions a type carries, as ``{name: shown value}``.

    Only what has a value and is not a formula's output. A type's full
    parameter list belongs under its family; what a reader wants beside a type
    name is how big it is.
    """
    found = {}
    try:
        for parameter in element_type.Parameters:
            if not parameter.HasValue:
                continue
            name = _definition_name(parameter.Definition)
            shown = _shown(parameter)
            if shown:
                found[name] = shown
    except Exception:
        pass
    return found


def _shown(parameter):
    from Autodesk.Revit.DB import StorageType
    try:
        if parameter.StorageType == StorageType.String:
            return parameter.AsString() or ""
        if parameter.StorageType == StorageType.Double:
            return parameter.AsValueString() or ""
        if parameter.StorageType == StorageType.Integer:
            return parameter.AsValueString() or str(parameter.AsInteger())
    except Exception:
        pass
    return ""


def _value_kind(parameter):
    try:
        return str(parameter.GetDefinition().GetDataType())
    except Exception:
        return ""


def _definition_name(definition):
    try:
        return definition.Name
    except Exception:
        return "(unnamed)"


def _definition_kind(definition):
    for attempt in ("GetDataType", "ParameterType", "UnitType"):
        try:
            value = getattr(definition, attempt)
            return str(value() if callable(value) else value)
        except Exception:
            continue
    return ""


def _definition_group(definition):
    for attempt in ("GetGroupTypeId", "ParameterGroup"):
        try:
            value = getattr(definition, attempt)
            return str(value() if callable(value) else value)
        except Exception:
            continue
    return ""


def _is_shared(definition):
    try:
        from Autodesk.Revit.DB import ExternalDefinition
        return isinstance(definition, ExternalDefinition)
    except Exception:
        pass
    try:
        return bool(definition.GUID)
    except Exception:
        return False


def _guid(definition):
    try:
        return str(definition.GUID)
    except Exception:
        return ""


def _family_name(element):
    try:
        family = element.Family
        if family is not None:
            return family.Name
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        parameter = element.get_Parameter(
            BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        if parameter is not None:
            return parameter.AsString() or "(system)"
    except Exception:
        pass
    return "(system)"


def _type_mark(element_type):
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        parameter = element_type.get_Parameter(
            BuiltInParameter.ALL_MODEL_TYPE_MARK)
        return (parameter.AsString() or "") if parameter is not None else ""
    except Exception:
        return ""


def _name(element):
    try:
        return element.Name
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)
    except Exception:
        return ""


def _title(doc):
    try:
        return doc.Title
    except Exception:
        return "(untitled)"


def _path(doc):
    try:
        return doc.PathName or ""
    except Exception:
        return ""
