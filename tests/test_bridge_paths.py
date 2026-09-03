# -*- coding: utf-8 -*-
"""Filesystem contract for the Excel/Revit bridge.

Kept separate from test_bridge.py because this is an installer/path migration
contract, not a transport/API behaviour test. The bridge module is loaded under
a private module name in a temporary environment so its deliberate process-level
ANONGEE_BRIDGE_HOME activation cannot leak into the rest of the suite.
"""

import importlib.util
import os
import shutil
import tempfile
import unittest
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
            "USERPROFILE": self.root,
        }
        values.update(extra)
        return mock.patch.dict(os.environ, values, clear=True)

    def test_localappdata_is_the_installed_default(self):
        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_local_default")
            expected = os.path.join(
                self.local, "Zxaidman", "AnonGee", "bridge"
            )
            self.assertEqual(jobs.home(), expected)
            self.assertEqual(os.environ[jobs.ENV_HOME], expected)
            self.assertEqual(
                jobs.LOCALAPPDATA_PARTS,
                ("Zxaidman", "AnonGee", "bridge"),
            )

    def test_explicit_bridge_home_always_wins(self):
        custom = os.path.join(self.root, "managed", "bridge")
        with self.environment(ANONGEE_BRIDGE_HOME=custom):
            jobs = _load_jobs("_anongee_bridge_jobs_explicit_override")
            self.assertEqual(jobs.home(), custom)
            self.assertFalse(jobs._AUTO_CANONICAL_HOME)

    def test_legacy_roaming_tree_moves_to_the_canonical_home(self):
        legacy = os.path.join(self.roaming, "AnonGee", "bridge")
        old_outbox = os.path.join(legacy, "outbox")
        old_inbox = os.path.join(legacy, "inbox")
        os.makedirs(old_outbox)
        os.makedirs(old_inbox)
        with open(os.path.join(old_outbox, "old.job.json"), "w") as handle:
            handle.write("old")
        with open(os.path.join(old_inbox, "old.result.json"), "w") as handle:
            handle.write("old-result")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_legacy_move")
            canonical = jobs.ensure()
            self.assertEqual(
                canonical,
                os.path.join(self.local, "Zxaidman", "AnonGee", "bridge"),
            )
            self.assertTrue(
                os.path.isfile(os.path.join(canonical, "outbox", "old.job.json"))
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(canonical, "inbox", "old.result.json")
                )
            )
            self.assertFalse(os.path.exists(legacy))

    def test_migration_never_overwrites_newer_canonical_state(self):
        legacy = os.path.join(self.roaming, "AnonGee", "bridge")
        canonical = os.path.join(
            self.local, "Zxaidman", "AnonGee", "bridge"
        )
        old_outbox = os.path.join(legacy, "outbox")
        new_outbox = os.path.join(canonical, "outbox")
        os.makedirs(old_outbox)
        os.makedirs(new_outbox)

        name = "same.job.json"
        with open(os.path.join(old_outbox, name), "w") as handle:
            handle.write("legacy")
        with open(os.path.join(new_outbox, name), "w") as handle:
            handle.write("canonical")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_no_overwrite")
            jobs.ensure()
            with open(os.path.join(new_outbox, name), "r") as handle:
                self.assertEqual(handle.read(), "canonical")
            # The conflicting legacy file is retained rather than destroyed.
            self.assertTrue(os.path.isfile(os.path.join(old_outbox, name)))


if __name__ == "__main__":
    unittest.main()
