# -*- coding: utf-8 -*-
"""AnonGee Toolkit one-command Windows release builder.

Release Pipeline Version: 0.5.0

This script orchestrates the already-proven release flow:

    locally tested AnonGee.extension
        -> installer/build_payload.py
        -> Inno Setup 7 command-line compiler (ISCC.exe)
        -> installer/output/AnonGee-Setup-<version>.exe
        -> installer/output/release-manifest.json

It deliberately does not rebuild Python dependencies and does not download
third-party prerequisites. Release inputs must already exist locally and match
pinned hashes before compilation starts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


PIPELINE_VERSION = "0.5.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"
EXPECTED_INNO_MAJOR = 7
EXPECTED_PYREVIT_FILE = "pyReVit_6.5.5.26237_signed.exe"
# Official pyRevit v6.5.5.26237 signed per-user release asset.
EXPECTED_PYREVIT_SHA256 = (
    "1e68bf525fce2e94d70f8e4f9d8a1d2489c86b1f7c79e75bbd65932d91d4a8d6"
)


class ReleaseBuildError(RuntimeError):
    """Raised when a release cannot be built or verified safely."""


def read_text_compat(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.2f} {}".format(size, unit)
        size /= 1024.0
    return "{} B".format(value)


def find_repo_root(script_path: Path) -> Path:
    candidate = script_path.resolve().parent.parent
    if (candidate / "AnonGee.extension").is_dir() and (candidate / "installer").is_dir():
        return candidate

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=script_path.resolve().parent,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseBuildError("Could not determine repository root.") from exc

    root = Path(result.stdout.strip()).resolve()
    if not (root / "AnonGee.extension").is_dir():
        raise ReleaseBuildError("Repository root does not contain AnonGee.extension: {}".format(root))
    return root


def ensure_windows_x64() -> None:
    if platform.system().lower() != "windows":
        raise ReleaseBuildError("Release Pipeline {} supports Windows x64 only.".format(PIPELINE_VERSION))

    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise ReleaseBuildError(
            "Unsupported build host architecture '{}'; expected Windows x64/AMD64.".format(
                platform.machine()
            )
        )


def run_git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseBuildError("Git command failed: git {}".format(" ".join(args))) from exc
    return result.stdout.strip()


def git_state(repo_root: Path) -> Tuple[str, str, Tuple[str, ...]]:
    branch = run_git(repo_root, "branch", "--show-current") or "<detached>"
    commit = run_git(repo_root, "rev-parse", "HEAD")
    porcelain = run_git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    entries = tuple(line for line in porcelain.splitlines() if line.strip())
    return branch, commit, entries


def parse_define(text: str, name: str) -> str:
    match = re.search(
        r'^\s*#define\s+' + re.escape(name) + r'\s+"([^"]+)"\s*$',
        text,
        flags=re.MULTILINE,
    )
    if not match:
        raise ReleaseBuildError('Could not find #define {} "...".'.format(name))
    return match.group(1).strip()


def parse_iss_contract(iss_path: Path) -> Dict[str, str]:
    if not iss_path.is_file():
        raise ReleaseBuildError("Inno Setup source not found: {}".format(iss_path))

    text = read_text_compat(iss_path)
    version = parse_define(text, "MyAppVersion")
    milestone = parse_define(text, "InstallerMilestone")
    pyrevit_file = parse_define(text, "PyRevitPrereqFile")

    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ReleaseBuildError("MyAppVersion is not semantic MAJOR.MINOR.PATCH: {}".format(version))
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", milestone):
        raise ReleaseBuildError("InstallerMilestone is not semantic MAJOR.MINOR.PATCH: {}".format(milestone))
    if pyrevit_file.lower() != EXPECTED_PYREVIT_FILE.lower():
        raise ReleaseBuildError(
            "AnonGee.iss prerequisite filename does not match the release pipeline pin: {} != {}".format(
                pyrevit_file, EXPECTED_PYREVIT_FILE
            )
        )

    expected_output_directive = "OutputBaseFilename=AnonGee-Setup-{#MyAppVersion}"
    if expected_output_directive not in text:
        raise ReleaseBuildError(
            "AnonGee.iss OutputBaseFilename contract changed; expected {!r}.".format(
                expected_output_directive
            )
        )

    return {
        "product_version": version,
        "installer_milestone": milestone,
        "pyrevit_file": pyrevit_file,
    }


def verify_pyrevit_prerequisite(installer_dir: Path, filename: str) -> Dict[str, Any]:
    path = installer_dir / "prerequisites" / "pyrevit" / filename
    if not path.is_file():
        raise ReleaseBuildError(
            "Pinned pyRevit prerequisite is missing:\n{}\n\n"
            "Place the official signed per-user installer there before building.".format(path)
        )

    digest = sha256_file(path)
    if digest.lower() != EXPECTED_PYREVIT_SHA256.lower():
        raise ReleaseBuildError(
            "Pinned pyRevit prerequisite SHA-256 mismatch.\n"
            "Expected: {}\n"
            "Actual:   {}\n"
            "File:     {}\n\n"
            "Do not build this release until the prerequisite is replaced with the exact official asset."
            .format(EXPECTED_PYREVIT_SHA256, digest, path)
        )

    return {
        "path": path,
        "size": path.stat().st_size,
        "sha256": digest,
    }


def candidate_iscc_paths(explicit: Optional[Path]) -> Sequence[Path]:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)

    env_path = os.environ.get("ISCC_PATH")
    if env_path:
        candidates.append(Path(env_path))

    which = shutil.which("ISCC.exe") or shutil.which("iscc")
    if which:
        candidates.append(Path(which))

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if not root:
            continue
        base = Path(root)
        candidates.append(base / "Inno Setup 7" / "ISCC.exe")
        if env_name == "LOCALAPPDATA":
            candidates.append(base / "Programs" / "Inno Setup 7" / "ISCC.exe")

    # Preserve order while removing duplicates case-insensitively.
    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def detect_iscc(explicit: Optional[Path]) -> Tuple[Path, str]:
    found = None
    for candidate in candidate_iscc_paths(explicit):
        if candidate.is_file():
            found = candidate.resolve()
            break

    if found is None:
        raise ReleaseBuildError(
            "Inno Setup 7 command-line compiler (ISCC.exe) was not found.\n"
            "Install Inno Setup 7, add ISCC.exe to PATH, set ISCC_PATH, or pass --iscc PATH."
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
        raise ReleaseBuildError("Could not execute Inno Setup compiler: {}".format(found)) from exc

    banner = (probe.stdout or "") + "\n" + (probe.stderr or "")
    match = re.search(r"Inno Setup\s+(\d+)(?:\.(\d+))?", banner, flags=re.IGNORECASE)
    if not match:
        raise ReleaseBuildError(
            "Could not verify the Inno Setup compiler version from {}.".format(found)
        )

    major = int(match.group(1))
    if major != EXPECTED_INNO_MAJOR:
        raise ReleaseBuildError(
            "AnonGee requires Inno Setup {} for this installer; detected major version {} at {}."
            .format(EXPECTED_INNO_MAJOR, major, found)
        )

    version_text = match.group(0).strip()
    return found, version_text


def run_payload_builder(repo_root: Path, strict_git: bool) -> None:
    script = repo_root / "installer" / "build_payload.py"
    if not script.is_file():
        raise ReleaseBuildError("Payload builder is missing: {}".format(script))

    command = [sys.executable, str(script)]
    if strict_git:
        command.append("--strict-git")

    print("\n=== 1/3 BUILD VERIFIED PAYLOAD ===")
    print("Command: {}".format(subprocess.list2cmdline(command)))
    result = subprocess.run(command, cwd=repo_root, check=False)
    if result.returncode != 0:
        raise ReleaseBuildError(
            "build_payload.py failed with exit code {}.".format(result.returncode)
        )


def compile_inno(iscc: Path, iss_path: Path, repo_root: Path) -> None:
    print("\n=== 2/3 COMPILE INNO SETUP ===")
    command = [str(iscc), str(iss_path)]
    print("Command: {}".format(subprocess.list2cmdline(command)))
    result = subprocess.run(command, cwd=repo_root, check=False)
    if result.returncode != 0:
        raise ReleaseBuildError(
            "Inno Setup compilation failed with exit code {}.".format(result.returncode)
        )


def load_payload_manifest(installer_dir: Path) -> Optional[Dict[str, Any]]:
    candidates = [
        installer_dir / "payload" / "build-manifest.json",
        installer_dir / "payload" / "AnonGee.extension" / "build-manifest.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                return json.loads(read_text_compat(path))
            except (OSError, ValueError) as exc:
                raise ReleaseBuildError("Could not read payload manifest: {}".format(path)) from exc
    return None


def verify_output(
    repo_root: Path,
    contract: Dict[str, str],
    prereq: Dict[str, Any],
    iscc: Path,
    iscc_version: str,
    strict_git: bool,
) -> Path:
    print("\n=== 3/3 VERIFY RELEASE ARTIFACT ===")
    installer_dir = repo_root / "installer"
    output_dir = installer_dir / "output"
    output_path = output_dir / "AnonGee-Setup-{}.exe".format(contract["product_version"])

    if not output_path.is_file():
        raise ReleaseBuildError(
            "Expected installer output was not produced: {}".format(output_path)
        )

    size = output_path.stat().st_size
    if size <= 0:
        raise ReleaseBuildError("Installer output is empty: {}".format(output_path))
    digest = sha256_file(output_path)

    branch, commit, changed_entries = git_state(repo_root)
    if strict_git and changed_entries:
        raise ReleaseBuildError(
            "Worktree became dirty during strict release build:\n- " + "\n- ".join(changed_entries)
        )

    payload_manifest = load_payload_manifest(installer_dir)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "release_pipeline_version": PIPELINE_VERSION,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "product": {
            "name": "AnonGee Toolkit",
            "version": contract["product_version"],
            "installer_milestone": contract["installer_milestone"],
        },
        "source": {
            "git_branch": branch,
            "git_commit": commit,
            "git_dirty": bool(changed_entries),
            "strict_git": strict_git,
            "changed_entries": list(changed_entries),
        },
        "compiler": {
            "path": str(iscc),
            "version": iscc_version,
        },
        "prerequisites": {
            "pyrevit": {
                "filename": contract["pyrevit_file"],
                "size_bytes": prereq["size"],
                "sha256": prereq["sha256"],
            }
        },
        "payload_manifest": payload_manifest,
        "artifact": {
            "filename": output_path.name,
            "size_bytes": size,
            "sha256": digest,
        },
    }

    manifest_path = output_dir / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("[PASS] Installer: {}".format(output_path))
    print("[PASS] Size:      {}".format(format_bytes(size)))
    print("[PASS] SHA-256:   {}".format(digest))
    print("[PASS] Manifest:  {}".format(manifest_path))
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and verify the complete AnonGee Windows Setup artifact."
    )
    parser.add_argument(
        "--strict-git",
        action="store_true",
        help="Fail unless the release source worktree remains clean.",
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
        ensure_windows_x64()
        repo_root = find_repo_root(Path(__file__))
        installer_dir = repo_root / "installer"
        iss_path = installer_dir / "AnonGee.iss"

        print("AnonGee Release Pipeline {}".format(PIPELINE_VERSION))
        print("Repository: {}".format(repo_root))

        contract = parse_iss_contract(iss_path)
        print("Product version:      {}".format(contract["product_version"]))
        print("Installer milestone:  {}".format(contract["installer_milestone"]))

        prereq = verify_pyrevit_prerequisite(installer_dir, contract["pyrevit_file"])
        print("[PASS] pyRevit prerequisite hash verified")
        print("       {}".format(prereq["sha256"]))

        iscc, iscc_version = detect_iscc(args.iscc)
        print("[PASS] Compiler: {} ({})".format(iscc, iscc_version))

        output_dir = installer_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_output = output_dir / "AnonGee-Setup-{}.exe".format(contract["product_version"])
        manifest_path = output_dir / "release-manifest.json"
        # Never allow a stale previous artifact to masquerade as this build.
        for generated in (expected_output, manifest_path):
            if generated.exists():
                generated.unlink()

        run_payload_builder(repo_root, args.strict_git)
        compile_inno(iscc, iss_path, repo_root)
        verify_output(
            repo_root,
            contract,
            prereq,
            iscc,
            iscc_version,
            args.strict_git,
        )

        print("\n=== RELEASE BUILD PASSED ===")
        return 0

    except ReleaseBuildError as exc:
        print("\n[FAIL] {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[FAIL] Build cancelled by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
