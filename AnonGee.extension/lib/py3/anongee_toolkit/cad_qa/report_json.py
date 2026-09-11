# -*- coding: utf-8 -*-
"""The report a machine reads.

THIS IS THE CONTRACT. Utilities 4 (CAD-vs-Revit accuracy) and 6 (the master
cross-checker) consume this file, so its shape is a published interface and not
a convenience: fields are added, never renamed or repurposed, and
``cad_qa_version`` says which release wrote it.

Deliberately mirrors ``cad2bim/export.py``: millimetres, compact keys, empty
keys omitted, sorted output. A file that reshuffles itself between runs cannot
be diffed between drawing revisions, and diffing revisions is most of what
anybody will eventually want from a QA archive.

NO TIMESTAMP BY DEFAULT. A clock in the payload makes every run differ from
every other, which defeats exactly that. The CLI passes one in when asked
(``--stamp``); the default is a file that is a pure function of the drawing.
"""

import json
import os

__version__ = "1.0.0"

#: Bumped when a consumer would have to change to keep reading these files.
SCHEMA_VERSION = "1.0"


def build_payload(report, stamp=None):
    """The dict written for one drawing."""
    payload = report.to_dict()
    payload["schema"] = SCHEMA_VERSION
    if stamp:
        payload["generated"] = stamp
    return payload


def write_report(path, report, stamp=None):
    """Write one drawing's findings. Returns the path."""
    _ensure_folder(path)
    with open(path, "w") as handle:
        json.dump(build_payload(report, stamp=stamp), handle, indent=1,
                  sort_keys=True)
    return path


def build_batch_payload(reports, summary=None, stamp=None):
    """The dict written for a folder sweep -- an index plus every report."""
    payload = {
        "schema": SCHEMA_VERSION,
        "drawings": [build_payload(report) for report in reports],
    }
    if summary:
        payload["summary"] = dict(summary)
    if stamp:
        payload["generated"] = stamp
    return payload


def write_batch(path, reports, summary=None, stamp=None):
    """Write a whole sweep into one file. Returns the path."""
    _ensure_folder(path)
    with open(path, "w") as handle:
        json.dump(build_batch_payload(reports, summary=summary, stamp=stamp),
                  handle, indent=1, sort_keys=True)
    return path


def _ensure_folder(path):
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
