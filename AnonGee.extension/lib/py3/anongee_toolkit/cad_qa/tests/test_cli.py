# -*- coding: utf-8 -*-
"""The command line: what it writes, and what it exits with.

ADVISORY IS THE DEFAULT and that is the behaviour most worth pinning. A change
that made a finding exit non-zero would quietly turn this tool into a gate, and
whatever it was wired into would start failing on drawings it used to pass.
"""

import io as _io
import os
import shutil
import sys
import tempfile
import unittest

import _support
from cad_qa import cli


class _Capture(object):
    """Swap stdout/stderr for buffers around a main() call."""

    def __enter__(self):
        self._out, self._err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _io.StringIO(), _io.StringIO()
        return self

    def __exit__(self, *_exc):
        self.out = sys.stdout.getvalue()
        self.err = sys.stderr.getvalue()
        sys.stdout, sys.stderr = self._out, self._err
        return False


def _run(argv):
    with _Capture() as capture:
        code = cli.main(argv)
    return code, capture.out, capture.err


class InvocationTests(unittest.TestCase):

    def test_version_prints_and_exits_clean(self):
        code, out, _err = _run(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(cli.__version__, out)

    def test_rules_prints_the_whole_catalogue(self):
        from cad_qa import rules
        code, out, _err = _run(["--rules"])
        self.assertEqual(code, 0)
        for rule_id in rules.RULES:
            self.assertIn(rule_id, out)

    def test_no_path_is_a_usage_error(self):
        code, _out, _err = _run([])
        self.assertEqual(code, 2)

    def test_a_missing_folder_is_reported_on_stderr(self):
        code, _out, err = _run(["/definitely/not/here"])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)


class OutputTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_cli_")
        self.drawing = os.path.join(self.folder, "broken.dxf")
        with open(self.drawing, "wb") as handle:
            handle.write(b"not a dxf\n" * 20)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_single_drawing_prints_a_report(self):
        code, out, _err = _run([self.drawing])
        self.assertEqual(code, 0)
        self.assertIn("broken.dxf", out)

    def test_quiet_prints_nothing(self):
        _code, out, _err = _run([self.drawing, "--quiet"])
        self.assertEqual(out, "")

    def test_json_is_written_where_asked(self):
        target = os.path.join(self.folder, "out", "r.json")
        _code, _out, _err = _run([self.drawing, "--json", target, "--quiet"])
        self.assertTrue(os.path.isfile(target))

    def test_out_writes_one_file_per_drawing(self):
        target = os.path.join(self.folder, "reports")
        _code, _out, _err = _run([self.folder, "--out", target, "--quiet"])
        self.assertEqual(os.listdir(target), ["broken.qa.json"])

    def test_an_empty_folder_is_an_error_not_an_empty_report(self):
        empty = tempfile.mkdtemp(prefix="cad_qa_empty_")
        try:
            code, _out, err = _run([empty])
            self.assertEqual(code, 2)
            self.assertIn("no .dxf", err)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class ExitCodeTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cad_qa_exit_")
        self.drawing = os.path.join(self.folder, "broken.dxf")
        with open(self.drawing, "wb") as handle:
            handle.write(b"not a dxf\n" * 20)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_findings_alone_do_not_fail_the_run(self):
        """The tool is advisory. This is the line that says so."""
        code, _out, _err = _run([self.drawing, "--quiet"])
        self.assertEqual(code, 0)

    def test_fail_on_error_opts_into_a_non_zero_exit(self):
        code, _out, _err = _run([self.drawing, "--quiet", "--fail-on", "error"])
        self.assertEqual(code, 1)

    def test_fail_on_warning_also_catches_errors(self):
        code, _out, _err = _run([self.drawing, "--quiet",
                                 "--fail-on", "warning"])
        self.assertEqual(code, 1)

    def test_a_clean_drawing_exits_zero_even_under_fail_on(self):
        from cad_qa import runner
        report = runner.run_context(_support.plan())
        self.assertEqual(cli._exit_code("error", [report]), 0)


if __name__ == "__main__":
    unittest.main()
