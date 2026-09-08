# -*- coding: utf-8 -*-
"""Static installer lifecycle contract for AnonGee milestone 0.8.0."""

import ast
import io
import json
import os
import re
import unittest
import warnings


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASE = os.path.join(_ROOT, "installer", "build_release.py")
_SIGNED = os.path.join(_ROOT, "installer", "build_signed_release.py")
_ISS = os.path.join(_ROOT, "installer", "AnonGee.iss")
_VERSION_OVERLAY = os.path.join(_ROOT, "installer", "lifecycle-version.iss")
_LIFECYCLE = os.path.join(_ROOT, "installer", "LIFECYCLE.md")
_EXTENSION = os.path.join(_ROOT, "extension.json")
_CHANGELOG = os.path.join(_ROOT, "CHANGELOG.md")


def _read(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _constant(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name
               for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("missing top-level constant {}".format(name))


def _function(source, name):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            lines = source.splitlines(True)
            end = getattr(node, "end_lineno", None)
            if end is None:
                raise AssertionError("Python runtime must expose AST end_lineno")
            return "".join(lines[node.lineno - 1:end])
    raise AssertionError("missing function {}".format(name))


def _define(source, name):
    match = re.search(
        r'^\s*#define\s+' + re.escape(name) + r'\s+"([^"]+)"\s*$',
        source,
        flags=re.MULTILINE,
    )
    if not match:
        raise AssertionError("missing Inno define {}".format(name))
    return match.group(1)


def _section(source, name):
    marker = "[{}]".format(name)
    start = source.index(marker)
    next_section = source.find("\n[", start + len(marker))
    return source[start:] if next_section < 0 else source[start:next_section]


def _function_like_inno(source, name):
    marker = "function {}".format(name)
    if marker not in source:
        marker = "procedure {}".format(name)
    start = source.index(marker)
    next_function = source.find("\nfunction ", start + len(marker))
    next_procedure = source.find("\nprocedure ", start + len(marker))
    candidates = [value for value in (next_function, next_procedure) if value >= 0]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


class InstallerLifecycleContractTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base = _read(_BASE)
        cls.signed = _read(_SIGNED)
        cls.iss = _read(_ISS)
        cls.overlay = _read(_VERSION_OVERLAY)
        cls.docs = _read(_LIFECYCLE)
        cls.extension = json.loads(_read(_EXTENSION))
        cls.changelog = _read(_CHANGELOG)

    def test_release_builders_compile_without_escape_warnings(self):
        for source, path in ((self.base, _BASE), (self.signed, _SIGNED)):
            with warnings.catch_warnings():
                warnings.simplefilter("error", SyntaxWarning)
                compile(source, path, "exec")

    def test_080_version_contract_is_aligned(self):
        self.assertEqual(_constant(self.base, "PIPELINE_VERSION"), "0.8.0")
        self.assertEqual(_constant(self.base, "MANIFEST_SCHEMA_VERSION"), "1.2.0")
        self.assertEqual(_constant(self.base, "EXPECTED_INSTALLER_MILESTONE"), "0.8.0")
        self.assertEqual(_constant(self.signed, "PIPELINE_VERSION"), "0.8.0")
        self.assertEqual(_constant(self.signed, "MANIFEST_SCHEMA_VERSION"), "1.4.0")
        self.assertEqual(_define(self.iss, "InstallerMilestone"), "0.8.0")

    def test_200_product_identity_is_aligned(self):
        self.assertEqual(self.extension["version"], "2.0.0")
        self.assertEqual(_define(self.iss, "MyAppVersion"), "2.0.0")
        headings = re.findall(
            r"^##\s+(\d+\.\d+\.\d+)\s*$",
            self.changelog,
            flags=re.MULTILINE,
        )
        self.assertTrue(headings)
        self.assertEqual(headings[0], "2.0.0")

    def test_stable_app_identity_and_fixed_per_user_directory(self):
        setup = _section(self.iss, "Setup")
        self.assertIn("AppId=Zxaidman.AnonGee.Toolkit", setup)
        self.assertIn(
            "DefaultDirName={localappdata}\\Zxaidman\\AnonGee\\BIM-Toolkit",
            setup,
        )
        self.assertIn("UsePreviousAppDir=no", setup)
        self.assertIn("DisableDirPage=yes", setup)
        self.assertIn("PrivilegesRequired=lowest", setup)

    def test_extension_payload_is_replace_all_on_install(self):
        install_delete = _section(self.iss, "InstallDelete")
        files = _section(self.iss, "Files")
        extension = "{userappdata}\\pyRevit\\Extensions\\AnonGee.extension"
        self.assertIn('Type: filesandordirs; Name: "{}"'.format(extension),
                      install_delete)
        self.assertIn('DestDir: "{}"'.format(extension), files)
        self.assertIn("recursesubdirs", files)
        self.assertIn("createallsubdirs", files)

    def test_uninstall_removes_extension_but_not_bridge_runtime(self):
        uninstall_delete = _section(self.iss, "UninstallDelete")
        extension = "{userappdata}\\pyRevit\\Extensions\\AnonGee.extension"
        self.assertIn('Type: filesandordirs; Name: "{}"'.format(extension),
                      uninstall_delete)
        bridge = "{localappdata}\\Zxaidman\\AnonGee\\bridge"
        self.assertNotIn(bridge.lower(), uninstall_delete.lower())
        self.assertNotIn(bridge.lower(), _section(self.iss, "InstallDelete").lower())

    def test_uninstall_keeps_pyrevit_independent(self):
        body = _function_like_inno(self.iss, "InitializeUninstall")
        self.assertIn("pyRevit is an independent prerequisite", body)
        self.assertIn("must never uninstall or modify pyRevit", body)

    def test_formal_release_cannot_reuse_last_published_product_version(self):
        self.assertEqual(
            _constant(self.base, "LAST_PUBLISHED_PRODUCT_VERSION"),
            "1.26.1",
        )
        body = _function(self.base, "verify_release_identity")
        self.assertIn("allow_published_version", body)
        self.assertIn("LAST_PUBLISHED_PRODUCT_VERSION", body)
        self.assertIn("<= semver_tuple", body)
        self.assertIn("Bump extension.json, CHANGELOG.md and", body)

    def test_normal_release_does_not_opt_out_of_published_version_guard(self):
        main = _function(self.base, "main")
        self.assertIn("verify_release_identity(extension, installer)", main)
        self.assertNotIn("allow_published_version=True", main)

    def test_self_signed_test_is_the_only_published_version_exception(self):
        main = _function(self.signed, "main")
        self.assertIn("allow_published_version=test_mode", main)
        self.assertIn("TEST_ARTIFACT_SUFFIX", self.signed)
        self.assertIn("release_ready_override=False", main)

    def test_base_manifest_records_release_readiness_reason(self):
        body = _function(self.base, "verify_output")
        self.assertIn("release_ready_override", body)
        self.assertIn("release_ready_reason", body)
        self.assertIn('"release_readiness_reason": release_ready_reason', body)
        self.assertIn("release readiness explicitly held by caller", body)

    def test_lifecycle_overlay_reads_stable_uninstall_registration(self):
        self.assertIn("Zxaidman.AnonGee.Toolkit_is1", self.overlay)
        self.assertIn("DisplayVersion", self.overlay)
        self.assertIn("HKCU64", self.overlay)
        self.assertIn("HKCU32", self.overlay)
        self.assertIn("AnonGeeProductVersion", self.overlay)

    def test_lifecycle_overlay_names_install_reinstall_upgrade_and_blocked_modes(self):
        for token in (
            "fresh-install",
            "same-version-reinstall",
            "upgrade",
            "blocked",
            "Reinstall AnonGee Toolkit",
            "AnonGee Toolkit upgrade detected",
            "Downgrades are blocked by installer milestone 0.8.0",
            "Abort;",
        ):
            self.assertIn(token, self.overlay)

    def test_base_and_signed_builds_compile_lifecycle_overlay(self):
        base_compile = _function(self.base, "compile_inno")
        signed_compile = _function(self.signed, "compile_signed_inno")
        for body in (base_compile, signed_compile):
            self.assertIn("--define=AnonGeeProductVersion={}", body)
            self.assertIn("--include={}", body)
            self.assertIn("lifecycle_include", body)
        self.assertIn("signing_include", signed_compile)
        self.assertIn("--signtool={}=", signed_compile)

    def test_lifecycle_document_covers_all_required_scenarios(self):
        plain = self.docs.lower().replace("*", "").replace("`", "")
        for phrase in (
            "clean install",
            "same-version reinstall",
            "upgrade from the archived 1.26.1 installer",
            "uninstall",
            "bridge runtime state",
            "intentionally preserved",
            "release_ready = false",
            "2.0.0",
        ):
            self.assertIn(phrase, plain)


if __name__ == "__main__":
    unittest.main()
