# -*- coding: utf-8 -*-
r"""AnonGee Toolkit Authenticode release builder.

Release Pipeline Version: 0.8.0

The Authenticode capability was introduced and workstation-proven in milestone
0.7.0. The current 0.8.0 wrapper integrates that signing path with the 0.8.0
lifecycle/release-identity contract from build_release.py.

It intentionally reuses the existing identity, source-cleanliness, payload,
prerequisite, compiler and manifest checks instead of duplicating those rules.

The signed path is:

    clean source
        -> build_payload.py
        -> Inno Setup 7 + lifecycle + signing overlays
        -> SignTool signs Setup AND Inno's embedded uninstaller
        -> RFC 3161 SHA-256 timestamp
        -> SignTool /pa verification of the resulting Setup EXE
        -> manifest upgraded with Authenticode evidence

Private signing keys are never read from the repository. The default contract
selects a code-signing certificate from the Windows CurrentUser\My certificate
store by SHA-1 thumbprint. Hardware-backed/non-exportable keys work with that
model and no PFX password appears in process arguments.

A self-signed certificate is supported only with --allow-self-signed-test.
That mode exercises the same signing, timestamping and verification plumbing,
but its artifact is renamed SELF-SIGNED-TEST and its manifest is never marked
release-ready. Public/company signing therefore remains a separate future gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import build_release as base


PIPELINE_VERSION = "0.8.0"
MANIFEST_SCHEMA_VERSION = "1.4.0"
SIGN_TOOL_NAME = "AnonGeeAuthenticode"
SIGNING_INCLUDE = "signing-authenticode.iss"
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"
CODE_SIGNING_EKU = "1.3.6.1.5.5.7.3.3"
TEST_ARTIFACT_SUFFIX = "-SELF-SIGNED-TEST"
TEST_MANIFEST_NAME = "test-signing-manifest.json"


class SigningError(base.ReleaseBuildError):
    """Raised when the signing identity/toolchain cannot be trusted."""


def normalize_thumbprint(value: str) -> str:
    thumbprint = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if len(thumbprint) != 40:
        raise SigningError(
            "Code-signing certificate thumbprint must be a 40-character SHA-1 "
            "certificate thumbprint. Found {!r}.".format(value)
        )
    return thumbprint


def _version_key(path: Path) -> Tuple[int, ...]:
    # Normal SDK layout: ...\Windows Kits\10\bin\10.0.x.y\x64\signtool.exe
    version_dir = path.parent.parent.name
    parts = []
    for token in version_dir.split("."):
        try:
            parts.append(int(token))
        except ValueError:
            return ()
    return tuple(parts)


def candidate_signtool_paths(explicit: Optional[Path]) -> Sequence[Path]:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)

    env_path = os.environ.get("SIGNTOOL_PATH")
    if env_path:
        candidates.append(Path(env_path))

    which = shutil.which("signtool.exe") or shutil.which("signtool")
    if which:
        candidates.append(Path(which))

    sdk_candidates = []
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(env_name)
        if not root:
            continue
        bin_root = Path(root) / "Windows Kits" / "10" / "bin"
        if not bin_root.is_dir():
            continue
        sdk_candidates.extend(bin_root.glob("*/x64/signtool.exe"))
        sdk_candidates.append(bin_root / "x64" / "signtool.exe")

    sdk_candidates = [path for path in sdk_candidates if path.is_file()]
    sdk_candidates.sort(key=_version_key, reverse=True)
    candidates.extend(sdk_candidates)

    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def detect_signtool(explicit: Optional[Path]) -> Path:
    found = None
    for candidate in candidate_signtool_paths(explicit):
        if candidate.is_file():
            found = candidate.resolve()
            break

    if found is None:
        raise SigningError(
            "Microsoft SignTool.exe was not found. Install a current Windows "
            "SDK, add SignTool to PATH, set SIGNTOOL_PATH, or pass "
            "--signtool PATH."
        )

    try:
        probe = subprocess.run(
            [str(found), "/?"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SigningError("Could not execute SignTool: {}".format(found)) from exc

    banner = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if "signtool" not in banner.lower() and "sign tool" not in banner.lower():
        raise SigningError("Could not verify SignTool executable: {}".format(found))
    return found


def verify_certificate(thumbprint: str, machine_store: bool) -> Dict[str, object]:
    """Verify certificate existence, private key, validity, and Code Signing EKU."""
    location = "LocalMachine" if machine_store else "CurrentUser"
    cert_path = "Cert:\\{}\\My\\{}".format(location, thumbprint)

    # EnhancedKeyUsageList is a convenience property and has proven host-sensitive
    # on a real workstation. If it is empty, validate the persisted X.509 EKU
    # extension (OID 2.5.29.37) directly before rejecting the certificate.
    script = (
        "$ErrorActionPreference='Stop';"
        "$c=Get-Item -LiteralPath '{path}';"
        "if(-not $c.HasPrivateKey){{throw 'certificate has no private key'}};"
        "if($c.NotAfter -le (Get-Date)){{throw 'certificate is expired'}};"
        "$ekus=@($c.EnhancedKeyUsageList | ForEach-Object {{$_.ObjectId.Value}});"
        "if($ekus -notcontains '{eku}'){{"
        "$raw=$c.Extensions | Where-Object {{$_.Oid.Value -eq '2.5.29.37'}} | Select-Object -First 1;"
        "if($raw){{"
        "$x=New-Object System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension;"
        "$x.CopyFrom($raw);"
        "$ekus=@($x.EnhancedKeyUsages | ForEach-Object {{$_.Value}})"
        "}}"
        "}};"
        "if($ekus -notcontains '{eku}'){{"
        "throw ('certificate is not valid for Code Signing; EKUs=' + (($ekus -join ',') -replace '^$','<none>'))"
        "}};"
        "Write-Output $c.Subject;"
        "Write-Output $c.Issuer;"
        "Write-Output $c.NotAfter.ToUniversalTime().ToString('o');"
        "Write-Output ([string]($c.Subject -eq $c.Issuer))"
    ).format(path=cert_path, eku=CODE_SIGNING_EKU)

    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SigningError(
            "Could not query the Windows certificate store with PowerShell."
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown certificate error").strip()
        raise SigningError(
            "Code-signing certificate could not be used from {}\\My.\n{}"
            .format(location, detail)
        )

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {
        "store_location": location,
        "store_name": "My",
        "thumbprint_sha1": thumbprint,
        "subject": lines[0] if lines else "",
        "issuer": lines[1] if len(lines) > 1 else "",
        "not_after_utc": lines[2] if len(lines) > 2 else "",
        "self_signed": (
            lines[3].lower() == "true"
            if len(lines) > 3
            else bool(lines and len(lines) > 1 and lines[0] == lines[1])
        ),
    }


def make_sign_command(
    signtool: Path,
    thumbprint: str,
    timestamp_url: str,
    machine_store: bool,
) -> str:
    """Command Inno invokes for every file it signs; $f is Inno's filename."""
    store_switch = "/sm " if machine_store else ""
    return (
        "$q{tool}$q sign /fd SHA256 {store}/s My /sha1 {thumb} "
        "/tr {timestamp} /td SHA256 /d $qAnonGee Toolkit$q $f"
    ).format(
        tool=str(signtool),
        store=store_switch,
        thumb=thumbprint,
        timestamp=timestamp_url,
    )


def compile_signed_inno(
    iscc: Path,
    iss_path: Path,
    lifecycle_include: Path,
    signing_include: Path,
    product_version: str,
    sign_command: str,
    repo_root: Path,
) -> None:
    print("\n=== 2/4 COMPILE + AUTHENTICODE SIGN INNO SETUP ===")
    command = [
        str(iscc),
        "--define=AnonGeeProductVersion={}".format(product_version),
        "--include={}".format(lifecycle_include),
        "--include={}".format(signing_include),
        "--signtool={}={}".format(SIGN_TOOL_NAME, sign_command),
        str(iss_path),
    ]
    print("Compiler: {}".format(iscc))
    print("Lifecycle overlay: {}".format(lifecycle_include))
    print("Signing overlay: {}".format(signing_include))
    result = subprocess.run(command, cwd=repo_root, check=False)
    if result.returncode != 0:
        raise SigningError(
            "Signed Inno Setup compilation failed with exit code {}."
            .format(result.returncode)
        )


def verify_authenticode(signtool: Path, artifact: Path) -> None:
    print("\n=== 4/4 VERIFY AUTHENTICODE SIGNATURE ===")
    command = [str(signtool), "verify", "/pa", "/all", "/v", str(artifact)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise SigningError(
            "SignTool could not verify the final Setup EXE.\n{}".format(detail)
        )
    print("[PASS] SignTool /pa verified the final Setup EXE.")


def test_artifact_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.stem + TEST_ARTIFACT_SUFFIX + artifact.suffix)


def upgrade_manifest(
    manifest_path: Path,
    artifact: Path,
    certificate: Dict[str, object],
    signtool: Path,
    timestamp_url: str,
    test_mode: bool,
) -> None:
    data = json.loads(base.read_text_compat(manifest_path))
    data["schema_version"] = MANIFEST_SCHEMA_VERSION
    data["release_pipeline_version"] = PIPELINE_VERSION
    data["release_ready"] = not test_mode
    data["release_readiness_reason"] = (
        "self-signed local test only"
        if test_mode
        else "Authenticode signature and release verification passed"
    )
    data["artifact"]["filename"] = artifact.name
    data["artifact"]["size_bytes"] = artifact.stat().st_size
    data["artifact"]["sha256"] = base.sha256_file(artifact)
    data["authenticode"] = {
        "signed": True,
        "setup_signature_verified": True,
        "signed_uninstaller_requested_by_inno": True,
        "file_digest": "SHA256",
        "timestamp_digest": "SHA256",
        "timestamp_url": timestamp_url,
        "signtool_path": str(signtool),
        "signing_profile": "self-signed-test" if test_mode else "formal",
        "local_windows_policy_verified": True,
        "public_trust_claimed": False if test_mode else None,
        "certificate": certificate,
    }
    manifest_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, Authenticode-sign, timestamp, and verify AnonGee Setup."
    )
    parser.add_argument(
        "--cert-sha1",
        default=os.environ.get("ANONGEE_SIGN_CERT_SHA1", ""),
        help=(
            "SHA-1 thumbprint of the Code Signing certificate in the Windows "
            "My store. Defaults to ANONGEE_SIGN_CERT_SHA1."
        ),
    )
    parser.add_argument(
        "--machine-store",
        action="store_true",
        default=os.environ.get("ANONGEE_SIGN_MACHINE_STORE", "").strip().lower()
        in {"1", "true", "yes", "on"},
        help="Use LocalMachine\\My instead of the default CurrentUser\\My store.",
    )
    parser.add_argument(
        "--allow-self-signed-test",
        action="store_true",
        help=(
            "Allow a self-signed certificate for local pipeline validation. "
            "The result is clearly renamed and release_ready stays false."
        ),
    )
    parser.add_argument(
        "--timestamp-url",
        default=os.environ.get("ANONGEE_TIMESTAMP_URL", DEFAULT_TIMESTAMP_URL),
        help="RFC 3161 timestamp server URL.",
    )
    parser.add_argument(
        "--signtool",
        type=Path,
        help="Explicit path to Microsoft SignTool.exe.",
    )
    parser.add_argument(
        "--iscc",
        type=Path,
        help="Explicit path to Inno Setup 7 ISCC.exe.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    test_mode = bool(args.allow_self_signed_test)
    manifest_path = None
    test_artifact = None

    try:
        base.ensure_windows_x64()
        repo_root = base.find_repo_root(Path(__file__))
        installer_dir = repo_root / "installer"
        iss_path = installer_dir / "AnonGee.iss"
        lifecycle_include = installer_dir / base.LIFECYCLE_INCLUDE
        signing_include = installer_dir / SIGNING_INCLUDE

        print("AnonGee Signed Release Pipeline {}".format(PIPELINE_VERSION))
        print("Repository: {}".format(repo_root))

        if not lifecycle_include.is_file():
            raise SigningError(
                "Installer lifecycle overlay is missing: {}".format(lifecycle_include)
            )
        if not signing_include.is_file():
            raise SigningError("Signing overlay is missing: {}".format(signing_include))

        source_state = base.verify_source_state(repo_root, allow_dirty=False)
        branch, commit, _changed = source_state
        print("Source branch:        {}".format(branch))
        print("Source commit:        {}".format(commit))
        print("Source state:         CLEAN")

        extension = base.load_extension_contract(repo_root)
        installer = base.parse_iss_contract(iss_path)
        base.verify_release_identity(
            extension,
            installer,
            allow_published_version=test_mode,
        )
        print("[PASS] Release identity: {} {}".format(
            extension["name"], extension["version"]
        ))

        prereq = base.verify_pyrevit_prerequisite(
            installer_dir, installer["pyrevit_file"]
        )
        print("[PASS] pyRevit prerequisite hash verified")

        iscc, iscc_version = base.detect_iscc(args.iscc)
        print("[PASS] Inno compiler: {} ({})".format(iscc, iscc_version))

        signtool = detect_signtool(args.signtool)
        print("[PASS] SignTool: {}".format(signtool))

        thumbprint = normalize_thumbprint(args.cert_sha1)
        certificate = verify_certificate(thumbprint, args.machine_store)
        print("[PASS] Code-signing certificate: {}".format(
            certificate.get("subject") or thumbprint
        ))

        if certificate.get("self_signed") and not test_mode:
            raise SigningError(
                "The selected certificate is self-signed. Formal signed releases "
                "reject self-signed identities. Re-run with --allow-self-signed-test "
                "only for local validation, or configure a trusted signing identity."
            )

        if test_mode:
            print("[TEST] Self-signed/local validation mode.")
            print("[TEST] This artifact will NOT be marked release-ready.")

        timestamp_url = (args.timestamp_url or "").strip()
        if not timestamp_url.lower().startswith(("http://", "https://")):
            raise SigningError("Timestamp URL must start with http:// or https://")

        output_dir = installer_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "AnonGee-Setup-{}.exe".format(
            installer["product_version"]
        )
        manifest_path = output_dir / "release-manifest.json"

        if test_mode:
            protected_existing = [
                path for path in (output_path, manifest_path) if path.exists()
            ]
            if protected_existing:
                raise SigningError(
                    "Self-signed test build refuses to overwrite existing "
                    "production-named release output. Move/archive these files "
                    "first:\n- {}"
                    .format("\n- ".join(str(path) for path in protected_existing))
                )

        for generated in (output_path, manifest_path):
            if generated.exists():
                generated.unlink()

        base.run_payload_builder(repo_root, True)

        sign_command = make_sign_command(
            signtool,
            thumbprint,
            timestamp_url,
            args.machine_store,
        )
        compile_signed_inno(
            iscc,
            iss_path,
            lifecycle_include,
            signing_include,
            installer["product_version"],
            sign_command,
            repo_root,
        )

        artifact = base.verify_output(
            repo_root,
            extension,
            installer,
            prereq,
            iscc,
            iscc_version,
            source_state,
            allow_dirty=False,
            release_ready_override=False,
            release_ready_reason=(
                "self-signed local test only"
                if test_mode
                else "awaiting Authenticode verification"
            ),
        )

        verify_authenticode(signtool, artifact)

        if test_mode:
            test_artifact = test_artifact_path(artifact)
            if test_artifact.exists():
                test_artifact.unlink()
            artifact.replace(test_artifact)
            artifact = test_artifact

        upgrade_manifest(
            manifest_path,
            artifact,
            certificate,
            signtool,
            timestamp_url,
            test_mode,
        )

        if test_mode:
            test_manifest = output_dir / TEST_MANIFEST_NAME
            if test_manifest.exists():
                test_manifest.unlink()
            manifest_path.replace(test_manifest)
            manifest_path = test_manifest

        print("[PASS] Signed manifest: {}".format(manifest_path))
        if test_mode:
            print("[PASS] Release ready: NO — self-signed local test only")
            print("[PASS] Test artifact: {}".format(artifact))
            print("\n=== SELF-SIGNED SIGNING VALIDATION PASSED ===")
        else:
            print("[PASS] Release ready: YES — Authenticode verified")
            print("\n=== SIGNED RELEASE BUILD PASSED ===")
        return 0

    except base.ReleaseBuildError as exc:
        if manifest_path is not None and manifest_path.exists():
            try:
                manifest_path.unlink()
            except OSError:
                pass
        if test_artifact is not None and test_artifact.exists():
            try:
                test_artifact.unlink()
            except OSError:
                pass
        print("\n[FAIL] {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if manifest_path is not None and manifest_path.exists():
            try:
                manifest_path.unlink()
            except OSError:
                pass
        if test_artifact is not None and test_artifact.exists():
            try:
                test_artifact.unlink()
            except OSError:
                pass
        print("\n[FAIL] Build cancelled by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
