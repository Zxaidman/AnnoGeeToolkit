# -*- coding: utf-8 -*-
"""Static release-signing contract for AnonGee pipeline milestone 0.7.0."""

import ast
import io
import os
import unittest
import warnings


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIGNED = os.path.join(_ROOT, "installer", "build_signed_release.py")
_TEST_CERT = os.path.join(_ROOT, "installer", "create_test_signing_certificate.ps1")
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
        cls.test_cert = _read(_TEST_CERT)
        cls.overlay = _read(_OVERLAY)
        cls.gitignore = _read(_GITIGNORE)
        cls.docs = _read(_SIGNING_DOC)

    def test_signing_builder_compiles_without_escape_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(self.signed, _SIGNED, "exec")

    def test_pipeline_and_manifest_schema_are_separately_versioned(self):
        self.assertEqual(_constant(self.signed, "PIPELINE_VERSION"), "0.7.0")
        self.assertEqual(_constant(self.signed, "MANIFEST_SCHEMA_VERSION"), "1.3.0")

    def test_signing_uses_sha256_and_rfc3161_timestamping(self):
        body = _function(self.signed, "make_sign_command")
        for token in ("sign /fd SHA256", "/tr {timestamp}", "/td SHA256"):
            self.assertIn(token, body)
        self.assertNotIn(" sign /t ", body)

    def test_final_setup_is_verified_with_windows_authenticode_policy(self):
        body = _function(self.signed, "verify_authenticode")
        for token in ('"verify"', '"/pa"', '"/all"', '"/v"'):
            self.assertIn(token, body)

    def test_inno_signs_the_uninstaller_and_retries_transient_signing(self):
        self.assertIn("SignTool=AnonGeeAuthenticode", self.overlay)
        self.assertIn("SignedUninstaller=yes", self.overlay)
        self.assertIn("SignToolRetryCount=3", self.overlay)
        self.assertIn("SignToolRetryDelay=1000", self.overlay)

    def test_manifest_changes_only_after_signature_verification(self):
        main = _function(self.signed, "main")
        verify_at = main.index("verify_authenticode(signtool, artifact)")
        upgrade_at = main.index("upgrade_manifest(")
        self.assertLess(verify_at, upgrade_at)

        upgrade = _function(self.signed, "upgrade_manifest")
        self.assertIn('data["release_ready"] = not test_mode', upgrade)
        self.assertIn('"signing_profile": "self-signed-test" if test_mode else "formal"',
                      upgrade)

    def test_self_signed_identity_requires_explicit_test_mode(self):
        main = _function(self.signed, "main")
        self.assertIn('certificate.get("self_signed") and not test_mode', main)
        self.assertIn("--allow-self-signed-test", self.signed)
        self.assertIn("SELF-SIGNED-TEST", self.signed)
        self.assertIn("test-signing-manifest.json", self.signed)
        self.assertIn("Release ready: NO", main)

    def test_builder_parses_raw_eku_extension_when_host_property_is_empty(self):
        body = _function(self.signed, "verify_certificate")
        self.assertIn("Oid.Value -eq '2.5.29.37'", body)
        self.assertIn("X509EnhancedKeyUsageExtension", body)
        self.assertIn("EnhancedKeyUsages", body)
        self.assertIn("certificate is not valid for Code Signing; EKUs=", body)

    def test_test_certificate_helper_uses_explicit_code_signing_shape(self):
        for token in (
            "New-SelfSignedCertificate",
            "-Type Custom",
            "-KeyUsage DigitalSignature",
            "2.5.29.37={text}1.3.6.1.5.5.7.3.3",
            'CodeSigningEku = "1.3.6.1.5.5.7.3.3"',
            "Cert:\\CurrentUser\\My",
            "KeyExportPolicy NonExportable",
            "HashAlgorithm SHA256",
        ):
            self.assertIn(token, self.test_cert)
        self.assertNotIn("Export-PfxCertificate", self.test_cert)

    def test_test_certificate_helper_parses_raw_eku_extension(self):
        self.assertIn('Oid.Value -eq "2.5.29.37"', self.test_cert)
        self.assertIn("X509EnhancedKeyUsageExtension", self.test_cert)
        self.assertIn("RawExtensions=", self.test_cert)

    def test_test_certificate_helper_uses_windows_powershell_pki_under_core(self):
        self.assertIn('$PSVersionTable.PSEdition -ne "Desktop"', self.test_cert)
        self.assertIn("System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                      self.test_cert)
        self.assertIn("ANONGEE_CERT_THUMBPRINT=", self.test_cert)
        self.assertIn("-EmitThumbprintMarker", self.test_cert)

    def test_test_certificate_helper_reloads_and_cleans_only_new_invalid_cert(self):
        self.assertIn("Get-Item -LiteralPath", self.test_cert)
        self.assertIn("$CreatedNew = $true", self.test_cert)
        self.assertIn("if ($CreatedNew -and $Certificate -and $Certificate.Thumbprint)",
                      self.test_cert)
        self.assertIn("Remove-Item -LiteralPath", self.test_cert)
        self.assertIn("Existing certificates are never deleted automatically", self.test_cert)

    def test_local_trust_is_explicit_and_current_user_only(self):
        self.assertIn("[switch]$TrustForLocalVerification", self.test_cert)
        self.assertIn("Cert:\\CurrentUser\\Root", self.test_cert)
        self.assertIn("Import-Certificate", self.test_cert)
        self.assertNotIn("Cert:\\LocalMachine\\Root", self.test_cert)

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

    def test_docs_keep_public_trust_deferred(self):
        lowered = self.docs.lower()
        self.assertIn("public-trust adoption: **deferred**", lowered)
        self.assertIn("self-signed", lowered)
        self.assertIn("release_ready: false", lowered)
        self.assertIn("does not create or distribute a **publicly trusted", lowered)
        self.assertIn("installer\\build_release.py", lowered)

    def test_docs_explain_key_storage_and_future_public_signing(self):
        lowered = self.docs.lower()
        plain = lowered.replace("*", "").replace("`", "")
        self.assertIn("where the self-signed key lives", plain)
        self.assertIn("private signing key", plain)
        self.assertIn("not saved in this git repository", plain)
        self.assertIn("hardware crypto module", plain)
        self.assertIn("managed signing service", plain)
        self.assertIn("do not reuse the self-signed development key", plain)


if __name__ == "__main__":
    unittest.main()
