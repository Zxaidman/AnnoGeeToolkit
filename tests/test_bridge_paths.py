# -*- coding: utf-8 -*-
"""Filesystem contract for the Excel/Revit bridge."""

import importlib.util
import io
import os
import shutil
import tempfile
import unittest
import warnings
from unittest import mock


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JOBS = os.path.join(
    _ROOT,
    "AnonGee.extension",
    "lib",
    "py3",
    "anongee_toolkit",
    "bridge",
    "jobs.py",
)


def _load_jobs(name="_anongee_bridge_jobs_path_test"):
    spec = importlib.util.spec_from_file_location(name, _JOBS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source():
    with io.open(_JOBS, "r", encoding="utf-8") as handle:
        return handle.read()


class BridgePathContractTests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.local = os.path.join(self.root, "local")
        self.roaming = os.path.join(self.root, "roaming")
        os.makedirs(self.local)
        os.makedirs(self.roaming)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def environment(self, **extra):
        values = {
            "LOCALAPPDATA": self.local,
            "APPDATA": self.roaming,
            "HOME": self.root,
            "USERPROFILE": self.root,
        }
        values.update(extra)
        return mock.patch.dict(os.environ, values, clear=True)

    def fallback_appdata_home(self):
        return os.path.join(self.roaming, "AnonGee", "bridge")

    def canonical_home(self):
        return os.path.join(self.local, "Zxaidman", "AnonGee", "bridge")

    def test_jobs_source_compiles_without_escape_sequence_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            warnings.simplefilter("error", DeprecationWarning)
            compile(_source(), _JOBS, "exec")

    def test_localappdata_is_the_installed_default(self):
        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_local_default")
            self.assertEqual(jobs.home(), self.canonical_home())
            self.assertNotIn(jobs.ENV_HOME, os.environ)
            self.assertEqual(
                jobs.LOCALAPPDATA_PARTS,
                ("Zxaidman", "AnonGee", "bridge"),
            )

    def test_explicit_bridge_home_always_wins(self):
        custom = os.path.join(self.root, "managed", "bridge")
        with self.environment(ANONGEE_BRIDGE_HOME=custom):
            jobs = _load_jobs("_anongee_bridge_jobs_explicit_override")
            self.assertEqual(jobs.home(), custom)
            self.assertEqual(jobs.ensure(), custom)
            self.assertTrue(os.path.isdir(os.path.join(custom, "outbox")))
            self.assertTrue(os.path.isdir(os.path.join(custom, "inbox")))

    def test_appdata_remains_fallback_when_localappdata_is_missing(self):
        with mock.patch.dict(
            os.environ,
            {"APPDATA": self.roaming, "HOME": self.root,
             "USERPROFILE": self.root},
            clear=True,
        ):
            jobs = _load_jobs("_anongee_bridge_jobs_roaming_fallback")
            self.assertEqual(jobs.home(), self.fallback_appdata_home())

    def test_home_directory_is_final_fallback(self):
        with mock.patch.dict(
            os.environ,
            {"HOME": self.root, "USERPROFILE": self.root},
            clear=True,
        ):
            jobs = _load_jobs("_anongee_bridge_jobs_home_fallback")
            self.assertEqual(
                jobs.home(),
                os.path.join(self.root, ".anongee", "bridge"),
            )

    def test_completed_migration_is_not_replayed(self):
        old_home = self.fallback_appdata_home()
        old_outbox = os.path.join(old_home, "outbox")
        os.makedirs(old_outbox)
        old_job = os.path.join(old_outbox, "old.job.json")
        with open(old_job, "w") as handle:
            handle.write("old")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_no_legacy_scan")
            canonical = jobs.ensure()
            self.assertEqual(canonical, self.canonical_home())
            self.assertTrue(os.path.isfile(old_job))
            self.assertEqual(jobs.pending(), [])
            self.assertFalse(hasattr(jobs, "_migrate_legacy_if_needed"))

    def test_pending_reads_only_selected_bridge_home(self):
        canonical_outbox = os.path.join(self.canonical_home(), "outbox")
        os.makedirs(canonical_outbox)
        first = os.path.join(canonical_outbox, "001.job.json")
        second = os.path.join(canonical_outbox, "002.job.json")
        with open(second, "w") as handle:
            handle.write("two")
        with open(first, "w") as handle:
            handle.write("one")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_pending")
            self.assertEqual(
                jobs.pending(),
                [("001", first), ("002", second)],
            )

    def test_claim_is_an_in_place_atomic_rename(self):
        canonical_outbox = os.path.join(self.canonical_home(), "outbox")
        os.makedirs(canonical_outbox)
        queued = os.path.join(canonical_outbox, "one.job.json")
        with open(queued, "w") as handle:
            handle.write("one")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_claim")
            running = jobs.claim(queued)
            self.assertEqual(
                running,
                os.path.join(canonical_outbox, "one.running.json"),
            )
            self.assertFalse(os.path.exists(queued))
            self.assertTrue(os.path.isfile(running))


if __name__ == "__main__":
    unittest.main()
