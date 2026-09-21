# -*- coding: utf-8 -*-
"""The session, rendered as one file somebody can attach to a message.

WHY THIS IS A SEPARATE MODULE
-----------------------------
``diagnostics`` records. This renders. Keeping them apart buys two things
worth more than the extra file:

* the renderer can be **tested without a session having happened**. Every
  function here takes plain data -- lists of dicts, lists of pairs -- so the
  awkward cases (no failures at all, a failure with no traceback, a timeline
  of two thousand rows) are ordinary test inputs rather than something that
  has to be provoked inside Revit;
* ``diagnostics`` is imported by every module in the tool, including the
  handlers that run when things are already going wrong. It should carry as
  little as possible, and a Markdown writer is not part of recording.

WHAT THE SHAPE OF THE FILE IS FOR
---------------------------------
The report exists because a bug report was costing a screenshot per bug. One
round of testing produced ten separate observations, two of which were
crashes, and each arrived as its own image with its own partial context.

So the file is ordered by **what the reader needs first**, not by what
happened first:

1. what went wrong, all of it, at the top;
2. the environment, because "which Revit, which model, which view" is the
   first question asked of any report;
3. where the session was actually spent, per feature;
4. only then the full timeline, which is the evidence rather than the answer.

Markdown, not plain text: the timeline is a table, and a table in ``.txt``
stops being readable the first time a family name runs long. It still reads
fine unrendered, which matters because it is going to be opened in Notepad at
least once.

Dual-engine and pure ASCII, like the rest of ``lib/``: 2.7 and 3.12, no
``re``, no f-strings.
"""

from __future__ import division

#: Timeline rows in the table. The rest are still counted and still in the
#: log; a report with four thousand rows in it does not get read.
MAX_ROWS = 400

#: Traceback lines kept per failure. Enough to reach the frame that matters
#: without the file becoming mostly stack.
MAX_TRACE_LINES = 40

TITLE = "Filter View Manager -- diagnostic report"


def render(version="", notes=(), actions=(), found=(), tallies=(),
           log_tail=(), stores=()):
    """The whole report as one string of Markdown. Never raises.

    Every argument is plain data and every one of them is optional, because a
    report asked for from a half-broken session is the one most worth having.
    A missing section says it is missing rather than disappearing.
    """
    try:
        blocks = [_header(version),
                  _first(actions, found),
                  _environment(notes),
                  _tallies(tallies),
                  _timeline(actions),
                  _failures(actions),
                  _stores(stores),
                  _log(log_tail),
                  _footer()]
        return "\n".join(block for block in blocks if block)
    except Exception as error:                              # noqa: BLE001
        return ("# {0}\n\nThe report could not be rendered: {1}: {2}\n".format(
            TITLE, type(error).__name__, error))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _header(version):
    import datetime
    out = ["# {0}".format(TITLE), ""]
    out.append("Written {0} from Filter View Manager {1}.".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        version or "an unknown version"))
    out.append("")
    out.append("This file is the whole session in one piece: every action "
               "the tool took, in order, with the feature that owns it and "
               "what came back. Attach it as it is -- it is written to be "
               "read without the screenshots.")
    out.append("")
    out.append("> It names things from the open model: category, family and "
               "type names, parameter names, view names and file paths. "
               "Nothing else about the project is in it, and no geometry -- "
               "but read section 2 before sending it outside the practice.")
    out.append("")
    return "\n".join(out)


def _first(actions, found):
    """Everything wrong, at the top, in the order it is worth looking at."""
    failures = [one for one in actions if one.get("outcome") == "failed"]
    silent = [one for one in actions if one.get("outcome") == "no answer"]
    refused = [one for one in actions if one.get("outcome") == "refused"]

    out = ["## 1. What to look at first", ""]
    if not (failures or silent or refused or found):
        out.append("Nothing in this session raised, went unanswered or was "
                   "refused. If the tool still did the wrong thing, the "
                   "timeline in section 4 is the record of what it did "
                   "instead -- find the action that should have changed "
                   "something and did not.")
        out.append("")
        return "\n".join(out)

    if failures:
        out.append("### {0} failure(s) -- something raised".format(
            len(failures)))
        out.append("")
        for one in failures:
            out.append("- **{0}** at {1}: {2}{3} (full traceback in section "
                       "5, entry #{4})".format(
                           one.get("tag", "?"), one.get("at", "?"),
                           one.get("action", "?"),
                           _cause(one), one.get("seq", "?")))
        out.append("")

    if silent:
        out.append("### {0} action(s) went out and never came back".format(
            len(silent)))
        out.append("")
        out.append("These are the expensive ones. Nothing raised, so nothing "
                   "was reported to the user -- the request was made and no "
                   "answer ever arrived. A control stuck on \"working...\", "
                   "a count that never lands and a button that does nothing "
                   "all look like this.")
        out.append("")
        for one in silent:
            out.append("- **{0}** at {1}: {2} (entry #{3})".format(
                one.get("tag", "?"), one.get("at", "?"),
                one.get("action", "?"), one.get("seq", "?")))
        out.append("")

    if found:
        out.append("### {0} finding(s) -- wrong, but nothing raised".format(
            len(found)))
        out.append("")
        for one in found:
            out.append("- **{0}**: {1}{2}".format(
                one.get("tag", "?"), one.get("message", ""), _seen(one)))
            detail = (one.get("detail") or "").strip()
            if detail:
                for line in detail.split("\n"):
                    if line.strip():
                        out.append("  - {0}".format(line.strip()))
        out.append("")

    if refused:
        out.append("### {0} action(s) refused".format(len(refused)))
        out.append("")
        out.append("The tool declined these on purpose. They are here because "
                   "a refusal the user did not expect is a bug in the "
                   "refusal, not in the user.")
        out.append("")
        for one in refused:
            out.append("- **{0}** at {1}: {2} -- {3}".format(
                one.get("tag", "?"), one.get("at", "?"),
                one.get("action", "?"),
                one.get("detail") or "no reason recorded"))
        out.append("")
    return "\n".join(out)


def _environment(notes):
    out = ["## 2. Session and environment", ""]
    if not notes:
        out.append("Nothing was recorded about the environment. That in "
                   "itself is worth reporting: the window records the Revit "
                   "version, the document and the active view as soon as the "
                   "model answers, so an empty section here means the model "
                   "never answered.")
        out.append("")
        return "\n".join(out)
    out.append("| what | value |")
    out.append("| --- | --- |")
    for key, value in notes:
        out.append("| {0} | {1} |".format(_cell(key), _cell(value)))
    out.append("")
    return "\n".join(out)


def _tallies(tallies):
    out = ["## 3. Where the session went", ""]
    if not tallies:
        out.append("No actions were recorded.")
        out.append("")
        return "\n".join(out)
    out.append("Sorted so the feature carrying the trouble is the first row.")
    out.append("")
    out.append("| feature | actions | did not finish |")
    out.append("| --- | ---: | ---: |")
    for tag, count, bad in tallies:
        out.append("| {0} | {1} | {2} |".format(_cell(tag), count, bad))
    out.append("")
    return "\n".join(out)


def _timeline(actions):
    out = ["## 4. Everything that happened", ""]
    if not actions:
        out.append("Nothing was recorded.")
        out.append("")
        return "\n".join(out)
    shown = list(actions)
    if len(shown) > MAX_ROWS:
        out.append("The last {0} of {1} actions. The rest are in the log "
                   "(section 7 has its tail).".format(MAX_ROWS, len(shown)))
        out.append("")
        shown = shown[-MAX_ROWS:]
    out.append("| # | time | feature | action | outcome | ms | facts |")
    out.append("| ---: | --- | --- | --- | --- | ---: | --- |")
    for one in shown:
        facts = ", ".join("{0}={1}".format(key, value)
                          for key, value in one.get("data") or [])
        out.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            one.get("seq", ""), _cell(one.get("at", "")),
            _cell(one.get("tag", "")), _action(one),
            _outcome(one), _cell(one.get("ms")) if one.get("ms") is not None
            else "", _cell(facts)))
    out.append("")
    return "\n".join(out)


def _failures(actions):
    failures = [one for one in actions if one.get("outcome") == "failed"]
    out = ["## 5. Failures in full", ""]
    if not failures:
        out.append("Nothing raised this session.")
        out.append("")
        return "\n".join(out)
    for one in failures:
        out.append("### #{0} {1} -- {2}".format(
            one.get("seq", "?"), one.get("tag", "?"), one.get("action", "?")))
        out.append("")
        out.append("At {0}.{1}".format(one.get("at", "?"), _cause(one)))
        out.append("")
        detail = (one.get("detail") or "").strip()
        if not detail:
            out.append("No traceback was captured for this one.")
            out.append("")
            continue
        lines = [line for line in detail.replace("\r\n", "\n").split("\n")
                 if line.strip()]
        clipped = len(lines) > MAX_TRACE_LINES
        if clipped:
            lines = lines[-MAX_TRACE_LINES:]
        out.append("```")
        out.extend(lines)
        out.append("```")
        if clipped:
            out.append("")
            out.append("(the last {0} lines; the whole traceback is in the "
                       "log)".format(MAX_TRACE_LINES))
        out.append("")
    return "\n".join(out)


def _stores(stores):
    out = ["## 6. What is on disk", ""]
    if not stores:
        out.append("The rule stores could not be read from here.")
        out.append("")
        return "\n".join(out)
    out.append("| store | path | rules |")
    out.append("| --- | --- | ---: |")
    for which, path, count in stores:
        out.append("| {0} | {1} | {2} |".format(
            _cell(which), _cell(path), _cell(count)))
    out.append("")
    return "\n".join(out)


def _log(log_tail):
    out = ["## 7. The log, including earlier sessions", ""]
    if not log_tail:
        out.append("The log could not be read.")
        out.append("")
        return "\n".join(out)
    out.append("The tail of the file this session appended to. Sessions "
               "before this one are above the `session start` line -- the "
               "previous run is usually what explains this one.")
    out.append("")
    out.append("```")
    out.extend(log_tail)
    out.append("```")
    out.append("")
    return "\n".join(out)


def _footer():
    return ("---\n\nGenerated by Filter View Manager's action tracker "
            "(FEAT-21).\n")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _cause(entry):
    cause = (entry.get("cause") or "").strip()
    return " {0}".format(cause) if cause else ""


def _seen(entry):
    """`` (seen 4 times)`` when a finding recurred, else ``""``."""
    try:
        seen = int(entry.get("seen") or 1)
    except Exception:
        seen = 1
    return " (seen {0} times)".format(seen) if seen > 1 else ""


def _action(entry):
    """The action, with ``x N`` when the row folded repeats of itself.

    The facts column carries the LAST of them, so "typed in the search box
    x17, text=struct" reads as the one thing the person did.
    """
    action = _cell(entry.get("action", ""))
    repeat = entry.get("repeat") or 1
    try:
        repeat = int(repeat)
    except Exception:
        repeat = 1
    return "{0} x{1}".format(action, repeat) if repeat > 1 else action


def _outcome(entry):
    """``failed`` and ``no answer`` in bold: they are what is being looked for."""
    outcome = entry.get("outcome") or ""
    if outcome in ("failed", "no answer"):
        return "**{0}**".format(outcome)
    return outcome


def _cell(value):
    """A table cell that cannot break the table.

    A pipe in a family name splits a Markdown row into the wrong number of
    columns and silently shifts every value after it one to the left, which
    is a corrupt report that still looks like a report.
    """
    try:
        text = "{0}".format("" if value is None else value)
        return text.replace("|", "/").replace("\r", " ").replace("\n", " ")
    except Exception:
        return "?"
