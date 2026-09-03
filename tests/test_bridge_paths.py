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

    def legacy_home(self):
        return os.path.join(self.roaming, "AnonGee", "bridge")

    def canonical_home(self):
        return os.path.join(self.local, "Zxaidman", "AnonGee", "bridge")

    def test_localappdata_is_the_installed_default(self):
        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_local_default")
            expected = self.canonical_home()
            self.assertEqual(jobs.home(), expected)
            self.assertEqual(os.environ[jobs.ENV_HOME], expected)
            self.assertEqual(
                jobs.LOCALAPPDATA_PARTS,
                ("Zxaidman", "AnonGee", "bridge"),
            )

    def test_explicit_bridge_home_always_wins_and_does_not_migrate(self):
        custom = os.path.join(self.root, "managed", "bridge")
        legacy = self.legacy_home()
        os.makedirs(os.path.join(legacy, "outbox"))
        legacy_job = os.path.join(legacy, "outbox", "old.job.json")
        with open(legacy_job, "w") as handle:
            handle.write("old")

        with self.environment(ANONGEE_BRIDGE_HOME=custom):
            jobs = _load_jobs("_anongee_bridge_jobs_explicit_override")
            self.assertEqual(jobs.home(), custom)
            self.assertFalse(jobs._AUTO_CANONICAL_HOME)
            jobs.ensure()
            self.assertTrue(os.path.isfile(legacy_job))

    def test_appdata_remains_the_fallback_when_localappdata_is_missing(self):
        with mock.patch.dict(
            os.environ,
            {"APPDATA": self.roaming, "USERPROFILE": self.root},
            clear=True,
        ):
            jobs = _load_jobs("_anongee_bridge_jobs_roaming_fallback")
            self.assertEqual(jobs.home(), self.legacy_home())
            self.assertFalse(jobs._AUTO_CANONICAL_HOME)

    def test_legacy_roaming_tree_moves_to_the_canonical_home(self):
        legacy = self.legacy_home()
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
            self.assertEqual(canonical, self.canonical_home())
            self.assertTrue(
                os.path.isfile(os.path.join(canonical, "outbox", "old.job.json"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(canonical, "inbox", "old.result.json"))
            )
            self.assertFalse(os.path.exists(legacy))

    def test_cross_volume_queue_is_never_copied_and_is_claimed_in_place(self):
        legacy = self.legacy_home()
        old_outbox = os.path.join(legacy, "outbox")
        os.makedirs(old_outbox)
        legacy_job = os.path.join(old_outbox, "old.job.json")
        with open(legacy_job, "w") as handle:
            handle.write("old")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_cross_volume")
            real_rename = os.rename
            canonical_job = os.path.join(
                self.canonical_home(), "outbox", "old.job.json"
            )

            def rename(source, target):
                if source == legacy_job and target == canonical_job:
                    raise OSError("simulated cross-device rename")
                return real_rename(source, target)

            with mock.patch.object(jobs.os, "rename", side_effect=rename), \
                    mock.patch.object(
                        jobs.shutil,
                        "copy2",
                        wraps=jobs.shutil.copy2,
                    ) as copy2:
                jobs.ensure()
                self.assertTrue(os.path.isfile(legacy_job))
                self.assertFalse(os.path.exists(canonical_job))
                self.assertFalse(
                    any(call.args and call.args[0] == legacy_job
                        for call in copy2.call_args_list),
                    "a runnable queued job must never be copied",
                )
                pending = jobs.pending()

            self.assertEqual(pending, [("old", legacy_job)])
            claimed = jobs.claim(legacy_job)
            self.assertEqual(
                claimed,
                os.path.join(old_outbox, "old.running.json"),
            )
            self.assertTrue(os.path.isfile(claimed))
            self.assertFalse(os.path.exists(legacy_job))

    def test_running_job_is_left_in_legacy_tree(self):
        legacy = self.legacy_home()
        old_outbox = os.path.join(legacy, "outbox")
        os.makedirs(old_outbox)
        running = os.path.join(old_outbox, "busy.running.json")
        with open(running, "w") as handle:
            handle.write("busy")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_running_state")
            jobs.ensure()
            self.assertTrue(os.path.isfile(running))
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        self.canonical_home(), "outbox", "busy.running.json"
                    )
                )
            )

    def test_conflicting_legacy_queue_is_quarantined_not_executed(self):
        legacy = self.legacy_home()
        old_outbox = os.path.join(legacy, "outbox")
        canonical_inbox = os.path.join(self.canonical_home(), "inbox")
        os.makedirs(old_outbox)
        os.makedirs(canonical_inbox)
        legacy_job = os.path.join(old_outbox, "same.job.json")
        with open(legacy_job, "w") as handle:
            handle.write("legacy")
        with open(os.path.join(canonical_inbox, "same.result.json"), "w") as handle:
            handle.write("canonical-result")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_conflict")
            jobs.ensure()
            quarantined = legacy_job + jobs.MIGRATION_CONFLICT_SUFFIX
            self.assertFalse(os.path.exists(legacy_job))
            self.assertTrue(os.path.isfile(quarantined))
            self.assertEqual(jobs.pending(), [])

    def test_migration_never_overwrites_newer_canonical_state(self):
        legacy = self.legacy_home()
        canonical = self.canonical_home()
        old_outbox = os.path.join(legacy, "outbox")
        new_outbox = os.path.join(canonical, "outbox")
        os.makedirs(old_outbox)
        os.makedirs(new_outbox)

        name = "same.job.json"
        legacy_job = os.path.join(old_outbox, name)
        with open(legacy_job, "w") as handle:
            handle.write("legacy")
        with open(os.path.join(new_outbox, name), "w") as handle:
            handle.write("canonical")

        with self.environment():
            jobs = _load_jobs("_anongee_bridge_jobs_no_overwrite")
            jobs.ensure()
            with open(os.path.join(new_outbox, name), "r") as handle:
                self.assertEqual(handle.read(), "canonical")
            self.assertFalse(os.path.exists(legacy_job))
            self.assertTrue(
                os.path.isfile(legacy_job + jobs.MIGRATION_CONFLICT_SUFFIX)
            )


if __name__ == "__main__":
    unittest.main()
