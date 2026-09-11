# -*- coding: utf-8 -*-
"""The command line. One drawing or a folder of them, no Revit required.

    python -m cad_qa DRAWING.dxf
    python -m cad_qa /intake/2026-09 --xlsx qa.xlsx --out reports/

ADVISORY BY DEFAULT, which is a decision and not an oversight: the tool exits 0
even when it finds Errors, because its job is to tell somebody something, not
to stop a pipeline. ``--fail-on`` opts into a non-zero exit for the day this is
wired into a gate, and until somebody asks for that day it never blocks
anything.

Exit codes::

    0   ran (findings or not)
    1   --fail-on was given and the threshold was met
    2   the environment cannot read DXF at all, or the path is unusable
"""

import argparse
import os
import sys

from . import rules
from .findings import SEVERITY_ERROR, SEVERITY_WARNING
from . import report_console, report_json, report_excel, runner

__version__ = "1.0.0"

FAIL_CHOICES = ("none", "error", "warning")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cad_qa",
        description="Check a structural DXF before converting it with cad2bim.")
    parser.add_argument("path", nargs="?",
                        help="a .dxf file, or a folder of them")
    parser.add_argument("--recursive", action="store_true",
                        help="with a folder, descend into subfolders")
    parser.add_argument("--unit-mm", type=float, default=1.0, metavar="MM",
                        help="millimetres per drawing unit (default 1: the "
                             "drawing is in mm; use 1000 for metres)")
    parser.add_argument("--json", metavar="PATH",
                        help="write the findings as JSON to PATH")
    parser.add_argument("--xlsx", metavar="PATH",
                        help="write the findings as an .xlsx workbook")
    parser.add_argument("--out", metavar="DIR",
                        help="with a folder, also write one JSON per drawing "
                             "into DIR")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the console report (exit code and "
                             "written files only)")
    parser.add_argument("--no-guidance", action="store_true",
                        help="omit the what-to-do paragraph under each finding")
    parser.add_argument("--fail-on", choices=FAIL_CHOICES, default="none",
                        help="exit 1 when a finding of this severity or worse "
                             "is present (default: none -- advisory)")
    parser.add_argument("--rules", action="store_true",
                        help="print the rule catalogue and exit")
    parser.add_argument("--version", action="store_true",
                        help="print the version and exit")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    out = sys.stdout

    if args.version:
        out.write("cad_qa {0}\n".format(__version__))
        return 0
    if args.rules:
        for line in format_rules():
            out.write(line + "\n")
        return 0
    if not args.path:
        parser.print_usage(out)
        out.write("cad_qa: a path is required (or --rules / --version)\n")
        return 2

    try:
        runner.require_environment()
    except runner.EnvironmentError_ as error:
        sys.stderr.write("{0}\n".format(error))
        return 2

    if os.path.isdir(args.path):
        reports = runner.run_folder(args.path, unit_mm=args.unit_mm,
                                    recursive=args.recursive)
        if not reports:
            sys.stderr.write("no .dxf files found in {0}\n".format(args.path))
            return 2
        _emit_batch(args, reports, out)
    elif os.path.exists(args.path) or args.path.lower().endswith(".dxf"):
        reports = [runner.run_file(args.path, unit_mm=args.unit_mm)]
        _emit_single(args, reports[0], out)
    else:
        sys.stderr.write("no such file or folder: {0}\n".format(args.path))
        return 2

    _write_files(args, reports, out)
    return _exit_code(args.fail_on, reports)


def format_rules():
    """The catalogue as plain lines -- what ``--rules`` prints."""
    lines = ["cad_qa {0} -- {1} rules".format(__version__, len(rules.RULES)),
             ""]
    for family, family_rules in rules.by_family().items():
        if not family_rules:
            continue
        lines.append(rules.FAMILY_TITLES.get(family, family))
        lines.append("-" * len(rules.FAMILY_TITLES.get(family, family)))
        for rule in family_rules:
            lines.append("  {0}  {1:<8} {2}".format(
                rule.rule_id, rule.severity, rule.title))
        lines.append("")
    return lines


def _emit_single(args, report, out):
    if args.quiet:
        return
    for line in report_console.format_report(
            report, guidance=not args.no_guidance):
        out.write(line + "\n")


def _emit_batch(args, reports, out):
    if args.quiet:
        return
    for line in report_console.format_batch(reports):
        out.write(line + "\n")
    out.write("\n")
    totals = runner.summarise(reports)
    out.write("{drawings} drawings · {clean} clean · {with_errors} with "
              "errors · {Error} Error, {Warning} Warning, {Info} Info\n"
              .format(**totals))


def _write_files(args, reports, out):
    """Write whichever outputs were asked for, reporting each one."""
    if args.json:
        if len(reports) == 1:
            report_json.write_report(args.json, reports[0])
        else:
            report_json.write_batch(args.json, reports,
                                    summary=runner.summarise(reports))
        _say(args, out, "JSON  {0}".format(args.json))

    if args.out:
        written = 0
        for report in reports:
            stem = os.path.splitext(report.source)[0] or "report"
            report_json.write_report(
                os.path.join(args.out, stem + ".qa.json"), report)
            written += 1
        _say(args, out, "JSON  {0} files in {1}".format(written, args.out))

    if args.xlsx:
        try:
            report_excel.write_workbook(args.xlsx, reports)
        except report_excel.ExcelUnavailable as error:
            # Deliberately not fatal: the formats that did work are already
            # written, and losing them because the third one is unavailable
            # would be the wrong trade.
            sys.stderr.write("{0}\n".format(error))
        else:
            _say(args, out, "XLSX  {0}".format(args.xlsx))


def _say(args, out, message):
    if not args.quiet:
        out.write(message + "\n")


def _exit_code(fail_on, reports):
    if fail_on == "none":
        return 0
    wanted = ((SEVERITY_ERROR,) if fail_on == "error"
              else (SEVERITY_ERROR, SEVERITY_WARNING))
    for report in reports:
        if any(f.severity in wanted for f in report.findings):
            return 1
    return 0
