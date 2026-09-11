# -*- coding: utf-8 -*-
"""What a QA run produces: one finding, and the report that holds them.

THE TOOL IS ADVISORY. Nothing here blocks anything, and the severity names are
borrowed from :mod:`anongee_toolkit.rc_automation.validation` so one office
reads one vocabulary -- but they mean something different in an advisory tool
and the difference is worth stating once:

``Error``
    cad2bim will build the WRONG model, or leave most of it out. Not "the run
    will crash" -- a run that produces forty columns where the drawing has four
    hundred reports success and is an Error.

``Warning``
    cad2bim will build something, and part of it will need fixing by hand.

``Info``
    Worth knowing before the run. Counts, and things that are unusual without
    being wrong.

AGGREGATED, NOT ENUMERATED. A real drawing carries 1158 records on one bad
layer, and a report with 1158 rows in it is a report nobody reads. A finding
therefore describes a SUBJECT (a layer, a mark, a category) and carries the
count plus a few examples. The examples are capped and ordered so two runs of
the same drawing produce the same file, byte for byte -- a QA report that
reshuffles itself cannot be diffed between drawing revisions, which is most of
what a QA report is for.

Pure Python: no ezdxf, no Revit, no openpyxl. Importable anywhere, including
IronPython 2.7, so nothing about where a report is *displayed* constrains where
it can be *built*.
"""

__version__ = "1.0.0"

#: cad2bim will build the wrong model, or leave most of it out.
SEVERITY_ERROR = "Error"
#: It will build, and part of it needs fixing by hand.
SEVERITY_WARNING = "Warning"
#: Worth knowing. Not wrong.
SEVERITY_INFO = "Info"

SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)

_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

#: How many examples a single finding carries. Enough to recognise the problem
#: in the drawing, few enough that a hundred findings stay readable.
MAX_EXAMPLES = 5


class Finding(object):
    """One thing worth saying about one drawing.

    ``rule``     the stable rule id ("L001"). Stable across releases: a rule is
                 retired rather than renumbered, so a finding in an old report
                 still means what it meant.
    ``subject``  what the finding is ABOUT -- a layer name, a mark, a category.
                 Two findings of the same rule on different subjects are two
                 findings; on the same subject they are one, aggregated.
    ``count``    how many things the subject covers (records, texts, members).
    ``examples`` up to MAX_EXAMPLES strings, already formatted, sorted.
    ``where``    (x_mm, y_mm) in drawing coordinates, or None. Present when the
                 finding has ONE location worth zooming to; absent when it is
                 about a whole layer.
    """

    __slots__ = ("rule", "severity", "message", "subject", "count",
                 "examples", "where")

    def __init__(self, rule, severity, message, subject=None, count=None,
                 examples=None, where=None):
        self.rule = rule
        self.severity = severity
        self.message = message
        self.subject = subject
        self.count = count
        self.examples = list(examples or [])[:MAX_EXAMPLES]
        self.where = tuple(where) if where else None

    @property
    def is_error(self):
        return self.severity == SEVERITY_ERROR

    def sort_key(self):
        """Severity first, then rule, then subject. Deterministic and readable.

        `subject` may be None, and None is not orderable against a string on
        Python 3 -- hence the empty-string fallback rather than the obvious
        tuple. A report that raises while sorting itself is a report lost at
        the last step.
        """
        return (_SEVERITY_ORDER.get(self.severity, 9), self.rule,
                self.subject or "")

    def to_dict(self):
        """The JSON shape. Keys are omitted when empty so the file stays small."""
        out = {"rule": self.rule, "severity": self.severity,
               "message": self.message}
        if self.subject is not None:
            out["subject"] = self.subject
        if self.count is not None:
            out["count"] = self.count
        if self.examples:
            out["examples"] = list(self.examples)
        if self.where:
            out["x"] = int(round(self.where[0]))
            out["y"] = int(round(self.where[1]))
        return out

    def __str__(self):
        head = "{0} {1}".format(self.rule, self.message)
        if self.subject:
            head = "{0} [{1}]".format(head, self.subject)
        if self.count is not None:
            head = "{0} (x{1})".format(head, self.count)
        return head

    def __repr__(self):
        return "<Finding {0} {1}: {2}>".format(self.rule, self.severity, self)


class Report(object):
    """Every finding for one drawing, plus the counts a summary needs.

    ``stats`` is what the run MEASURED (records read, layers seen, columns
    sectioned). It is not a finding and never carries a severity -- it is the
    denominator a reader needs to judge whether "12 unmapped layers" is most of
    the drawing or a rounding error.
    """

    def __init__(self, source, stats=None, findings=None, qa_version=None):
        self.source = source
        self.stats = dict(stats or {})
        self.findings = list(findings or [])
        self.qa_version = qa_version or __version__

    def add(self, finding):
        self.findings.append(finding)
        return finding

    def extend(self, findings):
        for finding in findings or []:
            self.add(finding)
        return self

    def sorted_findings(self):
        return sorted(self.findings, key=lambda f: f.sort_key())

    def counts(self):
        """{severity: n} with every severity present, so a zero is visible."""
        out = dict((name, 0) for name in SEVERITIES)
        for finding in self.findings:
            if finding.severity in out:
                out[finding.severity] += 1
        return out

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def worst(self):
        """The highest severity present, or None for a clean drawing."""
        for name in SEVERITIES:
            if any(f.severity == name for f in self.findings):
                return name
        return None

    def to_dict(self):
        return {
            "source": self.source,
            "cad_qa_version": self.qa_version,
            "units": "mm (positions and sizes)",
            "worst": self.worst,
            "counts": self.counts(),
            "stats": dict(self.stats),
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }

    def __repr__(self):
        counts = self.counts()
        return "<Report {0} E{1} W{2} I{3}>".format(
            self.source, counts[SEVERITY_ERROR], counts[SEVERITY_WARNING],
            counts[SEVERITY_INFO])
