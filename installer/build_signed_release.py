# -*- coding: utf-8 -*-
"""AnonGee Toolkit Authenticode release builder.

Release Pipeline Version: 0.7.0

This is a thin signed-release layer over the proven 0.6.0 build_release.py
pipeline. It intentionally reuses the existing identity, source-cleanliness,
payload, prerequisite, compiler and manifest checks instead of duplicating
those rules.

The difference is the Inno compile step:

    clean source
        -> build_payload.py
        -> Inno Setup 7 + signing-authenticode.iss
        -> SignTool signs Setup AND Inno's embedded uninstaller
        -> RFC 3161 SHA-256 timestamp
        -> SignTool /pa verification of the resulting Setup EXE
        -> release-manifest.json upgraded with Authenticode evidence

Private signing keys are never read from the repository. The default contract
selects a code-signing certificate from the Windows CurrentUser\My certificate
store by SHA-1 thumbprint. Hardware-backed/non-exportable keys work with that
model and no PFX password appears in process arguments.
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


PIPELINE_VERSION = "0.7.0"
MANIFEST_SCHEMA_VERSION = "1.2.0"
SIGN_TOOL_NAME = "AnonGeeAuthenticode"
SIGNING_INCLUDE = "signing-authenticode.iss"
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"
CODE_SIGNING_EKU = "1.3.6.1.5.5.7.3.3"


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
    parts = []
    for token in path.parent.name.split("."):
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

    # Windows SDK: prefer the newest x64 SignTool available.
    sdk_candidates = []
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(env_name)
        if not root:
            continue
        bin_root = Path(root) / "Windows Kits" / "10" / "bin"
        if not bin_root.is_dir():
            continue
        sdk_candidates.extend(bin_root.glob("*\\x64\\signtool.exe"))
        # Older SDK layouts can expose x64 directly under bin.
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

    # SignTool commonly returns 0 or 1 for its help invocation depending on SDK
    # build; proving it launched and printed its own name is the useful check.
    banner = (probe.stdout or "") + "\n" + (probe.stderr or "")
    if "signtool" not in banner.lower() and "sign tool" not in banner.lower():
        raise SigningError("Could not verify SignTool executable: {}".format(found))
    return found


def verify_certificate(thumbprint: str, machine_store: bool) -> Dict[str, str]:
    """Verify certificate existence, private key, and Code Signing EKU."""
    location = "LocalMachine" if machine_store else "CurrentUser"
    cert_path = "Cert:\\{}\\My\\{}".format(location, thumbprint)

    script = (
        "$ErrorActionPreference='Stop';"
        "$c=Get-Item -LiteralPath '{path}';"
        "if(-not $c.HasPrivateKey){{throw 'certificate has no private key'}};"
        "$ekus=@($c.EnhancedKeyUsageList | ForEach-Object {{$_.ObjectId.Value}});"
        "if($ekus -notcontains '{eku}'){{throw 'certificate is not valid for Code Signing'}};"
        "Write-Output $c.Subject;"
        "Write-Output $c.NotAfter.ToUniversalTime().ToString('o')"
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
        "not_after_utc": lines[1] if len(lines) > 1 else "",
    }


def make_sign_command(
    signtool: Path,
    thumbprint: str,
    timestamp_url: str,
    machine_store: bool,
) -> str:
    """Command Inno invokes for every file it signs; $f is Inno's filename."""
    store_switch = "/sm " if machine_store else ""
    # $q is Inno's quote placeholder. It avoids fragile nested Windows quoting
    # when this command itself is passed as one ISCC command-line argument.
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
    signing_include: Path,
    sign_command: str,
    repo_root: Path,
) -> None:
    print("\n=== 2/4 COMPILE + AUTHENTICODE SIGN INNO SETUP ===")
    command = [
        str(iscc),
        "--include={}".format(signing_include),
        "--signtool={}={}".format(SIGN_TOOL_NAME, sign_command),
        str(iss_path),
    ]
    # Never print the complete command if future signing backends add secrets.
    print("Compiler: {}".format(iscc))
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


def upgrade_manifest(
    manifest_path: Path,
    certificate: Dict[str, str],
    signtool: Path,
    timestamp_url: str,
) -> None:
    data = json.loads(base.read_text_compat(manifest_path))
    data["schema_version"] = MANIFEST_SCHEMA_VERSION
    data["release_pipeline_version"] = PIPELINE_VERSION
    data["release_ready"] = True
    data["authenticode"] = {
        "signed": True,
        "setup_signature_verified": True,
        "signed_uninstaller_requested_by_inno": True,
        "file_digest": "SHA256",
        "timestamp_digest": "SHA256",
        "timestamp_url": timestamp_url,
        "signtool_path": str(signtool),
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

    try:
        base.ensure_windows_x64()
        repo_root = base.find_repo_root(Path(__file__))
        installer_dir = repo_root / "installer"
        iss_path = installer_dir / "AnonGee.iss"
        signing_include = installer_dir / SIGNING_INCLUDE

        print("AnonGee Signed Release Pipeline {}".format(PIPELINE_VERSION))
        print("Repository: {}".format(repo_root))

        if not signing_include.is_file():
            raise SigningError("Signing overlay is missing: {}".format(signing_include))

        source_state = base.verify_source_state(repo_root, allow_dirty=False)
        branch, commit, _changed = source_state
        print("Source branch:        {}".format(branch))
        print("Source commit:        {}".format(commit))
        print("Source state:         CLEAN")

        extension = base.load_extension_contract(repo_root)
        installer = base.parse_iss_contract(iss_path)
        base.verify_release_identity(extension, installer)
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

        timestamp_url = (args.timestamp_url or "").strip()
        if not timestamp_url.lower().startswith(("http://", "https://")):
            raise SigningError("Timestamp URL must start with http:// or https://")

        output_dir = installer_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "AnonGee-Setup-{}.exe".format(
            installer["product_version"]
        )
        manifest_path = output_dir / "release-manifest.json"
        for generated in (output_path, manifest_path):
            if generated.exists():
                generated.unlink()

        # Reuse the proven payload builder in formal clean mode.
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
            signing_include,
            sign_command,
            repo_root,
        )

        print("\n=== 3/4 VERIFY RELEASE ARTIFACT ===")
        artifact = base.verify_output(
            repo_root,
            extension,
            installer,
            prereq,
            iscc,
            iscc_version,
            source_state,
            allow_dirty=False,
        )

        verify_authenticode(signtool, artifact)
        upgrade_manifest(manifest_path, certificate, signtool, timestamp_url)

        print("[PASS] Signed manifest: {}".format(manifest_path))
        print("[PASS] Release ready: YES — Authenticode verified")
        print("\n=== SIGNED RELEASE BUILD PASSED ===")
        return 0

    except base.ReleaseBuildError as exc:
        print("\n[FAIL] {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[FAIL] Build cancelled by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
