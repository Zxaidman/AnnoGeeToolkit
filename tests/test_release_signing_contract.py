# -*- coding: utf-8 -*-
"""Static release-signing contract for AnonGee pipeline 0.7.0.

These tests deliberately avoid invoking SignTool or requiring a certificate.
They protect the repository-level security and sequencing contract. The signed
path is implemented but may remain dormant until a production signing identity
is provisioned.
"""

import ast
import io
import os
import re
import unittest


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIGNED = os.path.join(_ROOT, "installer", "build_signed_release.py")
_OVERLAY = os.path.join(_ROOT, "installer", "signing-authenticode.iss")
_GITIGNORE = os.path.join(_ROOT, ".gitignore")
_SIGNING_DOC = os.path.join(_ROOT, "installer", "SIGNING.md")


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


class SigningContractTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.signed = _read(_SIGNED)
        cls.overlay = _read(_OVERLAY)
        cls.gitignore = _read(_GITIGNORE)
        cls.docs = _read(_SIGNING_DOC)

    def test_pipeline_and_manifest_schema_are_separately_versioned(self):
        self.assertEqual(_constant(self.signed, "PIPELINE_VERSION"), "0.7.0")
        self.assertEqual(_constant(self.signed, "MANIFEST_SCHEMA_VERSION"), "1.2.0")

    def test_signing_uses_sha256_and_rfc3161_timestamping(self):
        body = _function(self.signed, "make_sign_command")
        for token in ('"/fd"', '"SHA256"', '"/tr"', '"/td"'):
            self.assertIn(token, body)
        self.assertNotIn('"/t"', body)

    def test_final_setup_is_verified_with_windows_authenticode_policy(self):
        body = _function(self.signed, "verify_authenticode")
        for token in ('"verify"', '"/pa"', '"/all"', '"/v"'):
            self.assertIn(token, body)

    def test_inno_signs_the_uninstaller_and_retries_transient_signing(self):
        self.assertRegex(self.overlay, r"(?m)^SignTool=AnonGeeAuthenticode\s*$")
        self.assertRegex(self.overlay, r"(?m)^SignedUninstaller=yes\s*$")
        self.assertRegex(self.overlay, r"(?m)^SignToolRetryCount=3\s*$")
        self.assertRegex(self.overlay, r"(?m)^SignToolRetryDelay=1000\s*$")

    def test_release_manifest_is_promoted_only_after_signature_verification(self):
        main = _function(self.signed, "main")
        verify_at = main.index("verify_authenticode(signtool, artifact)")
        upgrade_at = main.index("upgrade_manifest(")
        self.assertLess(verify_at, upgrade_at)

        upgrade = _function(self.signed, "upgrade_manifest")
        self.assertIn('data["release_ready"] = True', upgrade)
        before_upgrade = self.signed[:self.signed.index("def upgrade_manifest")]
        self.assertNotIn('release_ready"] = True', before_upgrade)

    def test_certificate_identity_is_by_thumbprint_not_committed_password(self):
        self.assertIn("ANONGEE_SIGN_CERT_SHA1", self.signed)
        self.assertIn("normalize_thumbprint", self.signed)
        lowered = self.signed.lower()
        for unsafe in ("--pfx", "pfx_password", "cert_password", "private_key_password"):
            self.assertNotIn(unsafe, lowered)

    def test_private_key_container_patterns_are_ignored(self):
        for pattern in ("*.pfx", "*.p12", "*.pvk", "*.key",
                        "installer/signing/private/"):
            self.assertIn(pattern, self.gitignore)

    def test_docs_do_not_claim_a_certificate_is_already_configured(self):
        self.assertIn("do not create or distribute a publicly trusted code-signing identity",
                      self.docs.lower())
        self.assertIn("obtain an appropriate Code Signing certificate".lower(),
                      self.docs.lower())

    def test_signing_adoption_is_deferred_without_blocking_unsigned_builds(self):
        lowered = self.docs.lower()
        self.assertIn("adoption status: **implemented / deferred**", lowered)
        self.assertIn("not a release blocker", lowered)
        self.assertIn("installer\\build_release.py", lowered)
        self.assertIn("having them installed does **not** by itself provide", lowered)


if __name__ == "__main__":
    unittest.main()
