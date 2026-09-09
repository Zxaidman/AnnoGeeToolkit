# -*- coding: utf-8 -*-
"""The JSON sidecar: the same run, complete and diffable.

The workbook is capped and rounded so a person can read it. This is not: it
carries every item, every finding and every setting, so two runs can be diffed
between cad2bim versions and so a capture can be replayed without Revit.

`_jsonable` is the last-resort encoder, for the same reason cad2bim's export has
one: a live Revit object that leaked into a capture would otherwise raise out of
`json.dump` AFTER the audit had finished, losing the report and reporting a
crash for a run that worked.
"""

import json


def write(path, report, max_points=None):
    """Write the sidecar. Returns the path."""
    payload = report.to_dict(max_points)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1, default=_jsonable, sort_keys=True)
    return path


def _jsonable(value):
    for attribute in ("Value", "IntegerValue"):
        try:
            return getattr(value, attribute)
        except Exception:
            continue
    return str(value)
