# -*- coding: utf-8 -*-
"""The command envelope, and the result that comes back.

Two dictionaries and the rules for reading them. No Revit, no openpyxl, no
filesystem — so the format both ends of the bridge depend on can be argued with
on any machine, which is the whole reason it lives here rather than in the route
that receives it or the worker that runs it.

**Versioned from the first line**, because the workbook and the tool will be on
different versions in the field within a week of anybody else using this.

**The envelope carries which sheet and what to do — never the data.** Revit opens
the workbook itself, with the reader that already handles six formats. A payload
of rows would be a second reader that eventually disagrees with the first, and
whoever debugs *that* loses a day.

The result exists twice on disk and this module writes both:

``<jobId>.result.json``
    The canonical form. What another program reads, and what an MCP layer will
    serve later.
``<jobId>.result.tsv``
    The same thing flat, for Excel. **VBA has no JSON parser**, and a
    hand-written one in a macro module is a hundred and twenty lines that will
    be wrong about escaping the first time somebody puts a quote in a sheet
    name. Excel reads lines; give it lines.
"""

__version__ = "0.1.0"

#: Bumped when a reader has to change to keep working. Both ends check it.
ENVELOPE_VERSION = "1.0"

# --- what a job can be doing -----------------------------------------------
#: Written, not yet picked up.
STATUS_QUEUED = "queued"
#: The listener has claimed it. Revit may be part-way through.
STATUS_RUNNING = "running"
#: It finished. Findings may still say the model was not touched — a dry run
#: with errors is a *successful* job that wrote nothing.
STATUS_DONE = "done"
#: It started and could not finish.
STATUS_FAILED = "failed"
#: It never started: no document, an unsaved workbook, an unknown command.
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_QUEUED, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED,
            STATUS_REJECTED)

#: Which side wins where the workbook and the model disagree. The workbook, by
#: default, which is the rule already recorded for reconciliation.
CONFLICT_WORKBOOK = "workbook"
CONFLICT_MODEL = "model"

#: Nothing is written unless this is switched off. A command with no dry run is
#: a command nobody can try.
DEFAULT_OPTIONS = {
    "dryRun": True,
    "onConflict": CONFLICT_WORKBOOK,
    "keyParameter": "Mark",
}


def job_id(stamp, counter=0):
    """``("20260822-140311", 7)`` -> ``"20260822-140311-0007"``.

    The stamp is passed in rather than read from the clock, so a test can name
    a job and get the same name twice. The counter makes two jobs in the same
    second distinguishable, which two button presses will be.
    """
    return "{0}-{1:04d}".format(stamp, int(counter))


def new_job(command, workbook="", sheet="", options=None, identifier=""):
    """An envelope ready to be written. A plain dict, deliberately.

    Not a class: this crosses a process boundary as JSON and gets read by
    IronPython at one end, CPython at the other and VBA at a third. A dict is
    the only shape all three agree about.
    """
    settings = dict(DEFAULT_OPTIONS)
    settings.update(options or {})
    return {
        "envelope": ENVELOPE_VERSION,
        "jobId": identifier,
        "command": command,
        "workbook": workbook,
        "sheet": sheet,
        "options": settings,
    }


def problems(envelope):
    """What is wrong with this envelope, as sentences. Empty means usable.

    Deliberately not "is it valid" — a caller that has to reject something owes
    the user a reason, and a boolean cannot give one.
    """
    found = []
    if not isinstance(envelope, dict):
        return ["the job is not an object"]

    version = envelope.get("envelope")
    if not version:
        found.append("the job does not say which envelope version it is")
    elif _major(version) != _major(ENVELOPE_VERSION):
        found.append(
            "this job is envelope {0} and this build reads {1} — update the "
            "workbook or the extension so the two agree".format(
                version, ENVELOPE_VERSION))

    if not (envelope.get("command") or "").strip():
        found.append("the job names no command")
    if not (envelope.get("jobId") or "").strip():
        found.append("the job has no id")

    options = envelope.get("options")
    if options is not None and not isinstance(options, dict):
        found.append("options is not an object")
    return found


def _major(version):
    return str(version).split(".")[0]


def option(envelope, name, fallback=None):
    """One option, with the default behind it. Never raises."""
    if not isinstance(envelope, dict):
        return fallback
    options = envelope.get("options")
    if isinstance(options, dict) and name in options:
        return options[name]
    if name in DEFAULT_OPTIONS:
        return DEFAULT_OPTIONS[name]
    return fallback


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def new_result(envelope, status=STATUS_QUEUED, summary=None, findings=None,
               started="", finished="", note=""):
    """What went back. Carries the job it answers, so a file stands alone."""
    return {
        "envelope": ENVELOPE_VERSION,
        "jobId": (envelope or {}).get("jobId", ""),
        "command": (envelope or {}).get("command", ""),
        "status": status,
        "started": started,
        "finished": finished,
        "note": note,
        "summary": dict(summary or {}),
        "findings": [dict(finding) for finding in (findings or ())],
        "cells": [],
    }


def unpack(answer):
    """A handler's return value as ``(summary, findings, note, cells)``.

    Seven handlers return three things and one returns four. Rather than make
    six of them carry an empty list they have no use for, the fourth is
    optional and this is the one place that knows it — so the listener does not
    grow a branch, and the rule can be tested off Revit.
    """
    items = list(answer or ())
    while len(items) < 4:
        items.append(None)
    summary, findings, note, cells = items[0], items[1], items[2], items[3]
    return summary, findings, note or "", cells or []


def rejected(envelope, note):
    """A job that never started, and why. Its own function because the reason
    is the entire content of the answer."""
    return new_result(envelope, STATUS_REJECTED, note=note)


#: The finding columns, in the order the TSV prints them. Same five fields
#: ``rc_automation.models.Issue`` already carries, because a finding from a
#: workbook check and a finding from a run are the same thing to whoever has to
#: fix it.
FINDING_FIELDS = ("severity", "sheet", "row", "column", "message")

#: Marks the blocks in the TSV. A line starting with ``#`` is structure;
#: everything else is data. Excel reads this with ``Line Input`` and nothing
#: else, which is the point.
TSV_RESULT_MARKER = "#RESULT"
TSV_FINDINGS_MARKER = "#FINDINGS"

#: The third block: cells a command wants written back into the workbook.
#:
#: Every command so far has been one-way — the workbook says what it wants and
#: Revit reports what it did. ``naming.refresh`` is the first that has an answer
#: belonging *in a sheet* rather than in a log, and the parameter-driven
#: schedule generator will be the second. ``sheet, row, column, value``, one per
#: line, and the macro writes exactly those and nothing else.
TSV_CELLS_MARKER = "#CELLS"

#: The cell columns, in the order the TSV prints them.
CELL_FIELDS = ("sheet", "row", "column", "value")


def as_tsv(result):
    """The result as tab-separated lines, for a macro to read.

    Key/value first, then a table. Tabs rather than commas because a finding's
    message contains commas roughly always and tabs roughly never — and because
    the engine that writes this ships no ``csv`` module, so quoting would be
    hand-rolled and hand-rolled quoting is where this kind of file goes wrong.
    A tab inside a value is replaced by a space rather than escaped, for the
    same reason.
    """
    lines = [TSV_RESULT_MARKER]
    for key in ("jobId", "command", "status", "started", "finished", "note"):
        lines.append("{0}\t{1}".format(key, _flat(result.get(key, ""))))
    for key in sorted(result.get("summary") or {}):
        lines.append("{0}\t{1}".format(key, _flat(result["summary"][key])))

    lines.append(TSV_FINDINGS_MARKER)
    lines.append("\t".join(field.title() for field in FINDING_FIELDS))
    for finding in result.get("findings") or ():
        lines.append("\t".join(
            _flat(finding.get(field, "")) for field in FINDING_FIELDS))

    # Written unconditionally, header and all, even when there is nothing to
    # write. A block that appears only sometimes is a block a macro forgets to
    # handle, and the failure would be silent.
    lines.append(TSV_CELLS_MARKER)
    lines.append("\t".join(field.title() for field in CELL_FIELDS))
    for cell in result.get("cells") or ():
        lines.append("\t".join(
            _flat(cell.get(field, "")) for field in CELL_FIELDS))
    return "\n".join(lines) + "\n"


#: What a character outside ASCII becomes on the way to Excel.
#:
#: The result file is written as ``ascii``, because a file crossing into VBA
#: has no way to declare its encoding — the same lesson the ``.bas`` learned
#: the hard way. But ``errors="replace"`` turns every one of these into a
#: literal ``?``, so a run reported *"0 of 5 stair flight(s) written ? 5 did
#: NOT happen"* and a note written in English arrived looking like a bug.
#:
#: Transliterating here rather than policing every message means a future
#: sentence with a degree sign in it cannot reintroduce the fault.
TRANSLITERATE = {
    u"\u2014": "-", u"\u2013": "-", u"\u2212": "-",
    u"\u2018": "'", u"\u2019": "'", u"\u201c": '"', u"\u201d": '"',
    u"\u2026": "...", u"\u00b0": " deg", u"\u00b2": "2", u"\u00b3": "3",
    u"\u00d7": "x", u"\u00a0": " ", u"\u2192": "->", u"\u00b7": "-",
}


def _flat(value):
    """One cell's worth of text: no tabs, no newlines, and nothing Excel
    cannot be handed as plain ASCII."""
    if value is None:
        return ""
    text = u"{0}".format(value)
    for bad, good in (("\t", " "), ("\r", " "), ("\n", " ")):
        text = text.replace(bad, good)
    for bad, good in TRANSLITERATE.items():
        if bad in text:
            text = text.replace(bad, good)
    # Anything still outside ASCII is dropped rather than left to become a
    # question mark somebody has to interpret.
    return "".join(character if ord(character) < 128 else "?"
                   for character in text)


def findings_from_issues(issues):
    """``rc_automation.models.Issue`` objects into finding dicts.

    The one place the two vocabularies meet. Anything with these attributes
    works, so the workbook layer does not have to know the bridge exists.
    """
    found = []
    for issue in issues or ():
        found.append({
            "severity": getattr(issue, "severity", ""),
            "sheet": getattr(issue, "sheet", "") or "",
            # ``Issue.row`` is the spreadsheet row the user sees, 1-based and
            # counting the header, so it can be typed into Excel's Name Box.
            # The first version of this asked for ``row_number`` — a name from
            # a different DTO — and every finding would have crossed the bridge
            # without the one field that makes it actionable, silently.
            "row": _first(issue, ("row", "row_number")),
            "column": getattr(issue, "column", "") or "",
            "message": getattr(issue, "message", ""),
        })
    return found


def _first(owner, names):
    for name in names:
        value = getattr(owner, name, None)
        if value is not None:
            return value
    return ""
