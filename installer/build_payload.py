# -*- coding: utf-8 -*-
"""
AnonGee Toolkit release payload builder.

Build Pipeline Version: 0.2.0

Builds installer/payload/AnonGee.extension from the currently checked-out,
locally tested AnonGee.extension. It does not download from GitHub and does
not rebuild Python dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Sequence, Tuple


PIPELINE_VERSION = "0.2.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"

EXPECTED_PYTHON_ABI = "cp312"
EXPECTED_PLATFORM_TAG = "win_amd64"
EXPECTED_NUMPY_NATIVE = "_multiarray_umath.cp312-win_amd64.pyd"

EXTENSION_NAME = "AnonGee.extension"

# Confirmed development/debug data that must not ship.
EXCLUDED_RELATIVE_DIRS = {
    Path("lib/py3/anongee_toolkit/cad2bim/tests/fixtures/cad"),
}

# Generated/cache artifacts that should never be released.
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}


class BuildError(RuntimeError):
    """Raised when the release payload cannot be built safely."""


@dataclass(frozen=True)
class GitState:
    branch: str
    commit: str
    dirty: bool
    changed_entries: Tuple[str, ...]


@dataclass(frozen=True)
class TreeStats:
    file_count: int
    total_bytes: int
    pyd_count: int
    dll_count: int
    tree_sha256: str


def normalise_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_text_compat(path: Path) -> str:
    """Read UTF-8/UTF-8-BOM or UTF-16 text files deterministically."""
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
            return "{} {}".format(int(size), unit) if unit == "B" else "{:.2f} {}".format(size, unit)
        size /= 1024.0
    return "{} B".format(value)


def find_repo_root(script_path: Path) -> Path:
    candidate = script_path.resolve().parent.parent
    if (candidate / EXTENSION_NAME).is_dir() and (candidate / "installer").is_dir():
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
        raise BuildError(
            "Could not determine repository root. Place build_payload.py under "
            "<repo>/installer/ or run it inside a Git worktree."
        ) from exc

    root = Path(result.stdout.strip()).resolve()
    if not (root / EXTENSION_NAME).is_dir():
        raise BuildError("Repository root does not contain {}: {}".format(EXTENSION_NAME, root))
    return root


def ensure_windows_x64() -> None:
    if platform.system().lower() != "windows":
        raise BuildError("Build Pipeline {} supports Windows x64 only.".format(PIPELINE_VERSION))

    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise BuildError(
            "Unsupported build host architecture '{}'. Expected Windows x64/AMD64.".format(
                platform.machine()
            )
        )


def is_revit_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Revit.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError(
            "Could not determine whether Revit.exe is running. Close Revit and retry."
        ) from exc

    return "revit.exe" in result.stdout.lower()


def get_git_state(repo_root: Path) -> GitState:
    def run_git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BuildError("Git command failed: git {}".format(" ".join(args))) from exc
        return result.stdout.strip()

    branch = run_git("branch", "--show-current") or "<detached>"
    commit = run_git("rev-parse", "HEAD")
    porcelain = run_git("status", "--porcelain=v1", "--untracked-files=all")
    entries = tuple(line for line in porcelain.splitlines() if line.strip())
    return GitState(branch, commit, bool(entries), entries)


def parse_product_version(iss_path: Path) -> str:
    if not iss_path.is_file():
        raise BuildError("Inno Setup source not found: {}".format(iss_path))

    text = read_text_compat(iss_path)
    match = re.search(
        r'^\s*#define\s+MyAppVersion\s+"([^"]+)"\s*$',
        text,
        flags=re.MULTILINE,
    )
    if not match:
        raise BuildError('Could not find #define MyAppVersion "x.y.z" in {}'.format(iss_path))

    version = match.group(1).strip()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise BuildError(
            "MyAppVersion must use Semantic Versioning MAJOR.MINOR.PATCH; found '{}'.".format(version)
        )
    return version


def parse_pinned_requirements(requirements_path: Path) -> Dict[str, str]:
    if not requirements_path.is_file():
        raise BuildError("Requirements file not found: {}".format(requirements_path))

    pinned: Dict[str, str] = {}
    lines = read_text_compat(requirements_path).splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise BuildError(
                "requirements.txt must contain exact pins only. Line {} is not PACKAGE==VERSION: {!r}".format(
                    line_number, raw_line
                )
            )

        name, version = line.split("==", 1)
        name = name.strip()
        version = version.strip()
        if not name or not version:
            raise BuildError("Invalid requirements entry on line {}: {!r}".format(line_number, raw_line))

        key = normalise_package_name(name)
        if key in pinned:
            raise BuildError("Duplicate requirement for '{}'.".format(name))
        pinned[key] = version

    if not pinned:
        raise BuildError("requirements.txt contains no pinned packages.")
    return pinned


def installed_distributions(runtime_dir: Path) -> Dict[str, str]:
    installed: Dict[str, str] = {}
    for distribution in importlib.metadata.distributions(path=[str(runtime_dir)]):
        name = distribution.metadata.get("Name")
        if name:
            installed[normalise_package_name(name)] = distribution.version
    return installed


def verify_requirements(runtime_dir: Path, requirements_path: Path) -> Mapping[str, str]:
    expected = parse_pinned_requirements(requirements_path)
    installed = installed_distributions(runtime_dir)

    missing = sorted(set(expected) - set(installed))
    unexpected = sorted(set(installed) - set(expected))
    wrong_versions = sorted(
        name for name in set(expected) & set(installed) if expected[name] != installed[name]
    )

    messages = []
    if missing:
        messages.append("Missing distributions: {}".format(", ".join(missing)))
    if unexpected:
        messages.append("Unexpected distributions: {}".format(", ".join(unexpected)))
    if wrong_versions:
        messages.append(
            "Version mismatches: {}".format(
                ", ".join(
                    "{} expected {} found {}".format(name, expected[name], installed[name])
                    for name in wrong_versions
                )
            )
        )

    if messages:
        raise BuildError("Runtime metadata does not exactly match requirements.txt:\n- " + "\n- ".join(messages))
    return expected


def verify_required_structure(extension_dir: Path) -> None:
    required_paths = [
        extension_dir / "AnonGee.tab",
        extension_dir / "lib",
        extension_dir / "lib" / "py3",
        extension_dir / "lib" / "py3" / "anongee_toolkit",
        extension_dir / "lib" / "py3" / "anongee_clr.py",
        extension_dir / "lib" / "py3" / "numpy",
        extension_dir / "lib" / "py3" / "numpy.libs",
        extension_dir / "lib" / "py3" / "shapely",
        extension_dir / "lib" / "py3" / "shapely.libs",
        extension_dir / "lib" / "py3" / "ezdxf",
        extension_dir / "lib" / "py3" / "pythonnet",
    ]
    missing = [path for path in required_paths if not path.exists()]
    if missing:
        raise BuildError("Required extension/runtime paths are missing:\n- " + "\n- ".join(str(p) for p in missing))


def verify_native_runtime(extension_dir: Path) -> Tuple[int, int]:
    runtime = extension_dir / "lib" / "py3"
    pyd_files = sorted(runtime.rglob("*.pyd"))
    dll_files = sorted(runtime.rglob("*.dll"))

    if not pyd_files:
        raise BuildError(
            "No .pyd files were found under lib/py3. This is the exact failure mode "
            "that previously broke NumPy on another PC."
        )

    numpy_native = runtime / "numpy" / "_core" / EXPECTED_NUMPY_NATIVE
    if not numpy_native.is_file():
        raise BuildError("Required NumPy native module is missing: {}".format(numpy_native))

    if not list((runtime / "numpy.libs").glob("*.dll")):
        raise BuildError("numpy.libs contains no DLLs.")
    if not list((runtime / "shapely").rglob("*.pyd")):
        raise BuildError("Shapely contains no native .pyd modules.")
    if not list((runtime / "shapely.libs").glob("*.dll")):
        raise BuildError("shapely.libs contains no DLLs.")

    return len(pyd_files), len(dll_files)


def should_exclude(relative_path: Path, *, is_dir: bool) -> bool:
    if relative_path in EXCLUDED_RELATIVE_DIRS:
        return True
    if is_dir and relative_path.name in EXCLUDED_DIR_NAMES:
        return True
    if not is_dir:
        if relative_path.name in EXCLUDED_FILE_NAMES:
            return True
        if relative_path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
            return True
    return False


def collect_excluded_stats(source_extension: Path) -> Tuple[int, int]:
    count = 0
    total_bytes = 0
    for root, dirs, files in os.walk(source_extension):
        root_path = Path(root)
        rel_root = root_path.relative_to(source_extension)

        kept_dirs = []
        for directory in dirs:
            rel = rel_root / directory
            if should_exclude(rel, is_dir=True):
                excluded_root = root_path / directory
                for excluded_file in excluded_root.rglob("*"):
                    if excluded_file.is_file():
                        count += 1
                        total_bytes += excluded_file.stat().st_size
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs

        for filename in files:
            rel = rel_root / filename
            if should_exclude(rel, is_dir=False):
                file_path = root_path / filename
                count += 1
                total_bytes += file_path.stat().st_size
    return count, total_bytes


def copy_release_tree(source_extension: Path, payload_extension: Path) -> None:
    def ignore(directory: str, names: Sequence[str]) -> set[str]:
        directory_path = Path(directory)
        rel_root = directory_path.relative_to(source_extension)
        ignored: set[str] = set()
        for name in names:
            child = directory_path / name
            rel = rel_root / name
            if should_exclude(rel, is_dir=child.is_dir()):
                ignored.add(name)
        return ignored

    shutil.copytree(
        source_extension,
        payload_extension,
        copy_function=shutil.copy2,
        ignore=ignore,
    )


def build_file_map(root: Path, *, apply_source_exclusions: bool) -> Dict[str, Tuple[int, str]]:
    result: Dict[str, Tuple[int, str]] = {}
    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        rel_root = current_path.relative_to(root)

        if apply_source_exclusions:
            dirs[:] = [
                directory
                for directory in dirs
                if not should_exclude(rel_root / directory, is_dir=True)
            ]

        for filename in files:
            rel = rel_root / filename
            if apply_source_exclusions and should_exclude(rel, is_dir=False):
                continue
            path = current_path / filename
            result[rel.as_posix()] = (path.stat().st_size, sha256_file(path))
    return result


def verify_payload_integrity(source_extension: Path, payload_extension: Path) -> TreeStats:
    print("[VERIFY] Hashing release source tree...")
    source_map = build_file_map(source_extension, apply_source_exclusions=True)
    print("[VERIFY] Hashing payload tree...")
    payload_map = build_file_map(payload_extension, apply_source_exclusions=False)

    source_keys = set(source_map)
    payload_keys = set(payload_map)
    missing = sorted(source_keys - payload_keys)
    extras = sorted(payload_keys - source_keys)
    changed = sorted(key for key in source_keys & payload_keys if source_map[key] != payload_map[key])

    if missing or extras or changed:
        parts = []
        if missing:
            parts.append("Missing payload files (first 20): {}".format(", ".join(missing[:20])))
        if extras:
            parts.append("Unexpected payload files (first 20): {}".format(", ".join(extras[:20])))
        if changed:
            parts.append("Changed payload files (first 20): {}".format(", ".join(changed[:20])))
        raise BuildError("Payload integrity verification failed:\n- " + "\n- ".join(parts))

    total_bytes = sum(size for size, _ in payload_map.values())
    pyd_count = sum(1 for path in payload_map if path.lower().endswith(".pyd"))
    dll_count = sum(1 for path in payload_map if path.lower().endswith(".dll"))

    tree_digest = hashlib.sha256()
    for rel_path in sorted(payload_map):
        size, digest = payload_map[rel_path]
        tree_digest.update(rel_path.encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(str(size).encode("ascii"))
        tree_digest.update(b"\0")
        tree_digest.update(digest.encode("ascii"))
        tree_digest.update(b"\n")

    return TreeStats(
        file_count=len(payload_map),
        total_bytes=total_bytes,
        pyd_count=pyd_count,
        dll_count=dll_count,
        tree_sha256=tree_digest.hexdigest(),
    )


def write_manifest(
    manifest_path: Path,
    *,
    product_version: str,
    git_state: GitState,
    requirements_path: Path,
    requirements: Mapping[str, str],
    payload_stats: TreeStats,
    excluded_count: int,
    excluded_bytes: int,
) -> None:
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "product_version": product_version,
        "built_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "git_branch": git_state.branch,
            "git_commit": git_state.commit,
            "git_dirty": git_state.dirty,
            "git_changed_entry_count": len(git_state.changed_entries),
        },
        "runtime": {
            "python_abi": EXPECTED_PYTHON_ABI,
            "platform": EXPECTED_PLATFORM_TAG,
            "pyd_count": payload_stats.pyd_count,
            "dll_count": payload_stats.dll_count,
        },
        "requirements": {
            "path": "tools/requirements.txt",
            "sha256": sha256_file(requirements_path),
            "package_count": len(requirements),
        },
        "release_exclusions": {
            "exact_directories": sorted(path.as_posix() for path in EXCLUDED_RELATIVE_DIRS),
            "generated_directory_names": sorted(EXCLUDED_DIR_NAMES),
            "generated_file_suffixes": sorted(EXCLUDED_FILE_SUFFIXES),
            "excluded_file_count": excluded_count,
            "excluded_bytes": excluded_bytes,
        },
        "payload": {
            "extension": EXTENSION_NAME,
            "file_count": payload_stats.file_count,
            "total_bytes": payload_stats.total_bytes,
            "tree_sha256": payload_stats.tree_sha256,
        },
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and verify installer/payload/AnonGee.extension from the "
            "currently checked-out local tested repository."
        )
    )
    parser.add_argument(
        "--strict-git",
        action="store_true",
        help="Fail when the Git worktree has uncommitted or untracked changes.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="AnonGee build_payload.py {}".format(PIPELINE_VERSION),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    script_path = Path(__file__).resolve()

    try:
        repo_root = find_repo_root(script_path)
        installer_dir = repo_root / "installer"
        source_extension = repo_root / EXTENSION_NAME
        payload_root = installer_dir / "payload"
        payload_extension = payload_root / EXTENSION_NAME
        manifest_path = payload_root / "build-manifest.json"
        requirements_path = repo_root / "tools" / "requirements.txt"
        iss_path = installer_dir / "AnonGee.iss"

        print("=" * 68)
        print(" ANONGEE RELEASE PAYLOAD BUILDER")
        print(" Pipeline version : {}".format(PIPELINE_VERSION))
        print("=" * 68)

        ensure_windows_x64()
        if is_revit_running():
            raise BuildError("Revit.exe is running. Close every Revit session before building a release payload.")

        verify_required_structure(source_extension)
        product_version = parse_product_version(iss_path)
        git_state = get_git_state(repo_root)

        print(" Product version  : {}".format(product_version))
        print(" Git branch       : {}".format(git_state.branch))
        print(" Git commit       : {}".format(git_state.commit))
        print(" Git dirty        : {}".format("YES" if git_state.dirty else "no"))

        if git_state.dirty:
            print()
            print("[WARNING] Git worktree contains uncommitted/untracked changes.")
            for entry in git_state.changed_entries[:20]:
                print("          {}".format(entry))
            if len(git_state.changed_entries) > 20:
                print("          ... and {} more".format(len(git_state.changed_entries) - 20))
            if args.strict_git:
                raise BuildError("--strict-git was requested and the worktree is dirty.")

        runtime_dir = source_extension / "lib" / "py3"

        print()
        print("[VERIFY] Checking pinned dependency metadata...")
        requirements = verify_requirements(runtime_dir, requirements_path)
        print("[ OK ] {} pinned packages match requirements.txt".format(len(requirements)))

        print("[VERIFY] Checking native CPython runtime...")
        source_pyd_count, source_dll_count = verify_native_runtime(source_extension)
        print("[ OK ] .pyd files: {}".format(source_pyd_count))
        print("[ OK ] .dll files: {}".format(source_dll_count))
        print("[ OK ] NumPy native core: {}".format(EXPECTED_NUMPY_NATIVE))

        excluded_count, excluded_bytes = collect_excluded_stats(source_extension)
        print()
        print("[CLEAN] Release exclusions:")
        for path in sorted(EXCLUDED_RELATIVE_DIRS, key=lambda p: p.as_posix()):
            print("        {}".format(path.as_posix()))
        print("        excluded {} files / {}".format(excluded_count, format_bytes(excluded_bytes)))

        if payload_root.exists():
            print()
            print("[CLEAN] Removing previous payload: {}".format(payload_root))
            shutil.rmtree(payload_root)

        payload_root.mkdir(parents=True, exist_ok=True)

        print()
        print("[COPY]  {} -> {}".format(source_extension, payload_extension))
        copy_release_tree(source_extension, payload_extension)

        print()
        print("[VERIFY] Checking payload structure/native runtime...")
        verify_required_structure(payload_extension)
        payload_pyd_count, payload_dll_count = verify_native_runtime(payload_extension)

        if payload_pyd_count != source_pyd_count:
            raise BuildError(
                "Native .pyd count changed during payload copy: source={} payload={}".format(
                    source_pyd_count, payload_pyd_count
                )
            )
        if payload_dll_count != source_dll_count:
            raise BuildError(
                "DLL count changed during payload copy: source={} payload={}".format(
                    source_dll_count, payload_dll_count
                )
            )

        payload_requirements = verify_requirements(payload_extension / "lib" / "py3", requirements_path)
        if dict(payload_requirements) != dict(requirements):
            raise BuildError("Payload dependency metadata differs from source metadata.")

        payload_stats = verify_payload_integrity(source_extension, payload_extension)

        write_manifest(
            manifest_path,
            product_version=product_version,
            git_state=git_state,
            requirements_path=requirements_path,
            requirements=requirements,
            payload_stats=payload_stats,
            excluded_count=excluded_count,
            excluded_bytes=excluded_bytes,
        )

        print()
        print("=" * 68)
        print(" PAYLOAD READY FOR INNO SETUP")
        print("=" * 68)
        print(" Product version  : {}".format(product_version))
        print(" Source branch    : {}".format(git_state.branch))
        print(" Source commit    : {}".format(git_state.commit))
        print(" Git dirty        : {}".format("YES" if git_state.dirty else "no"))
        print(" Files            : {}".format(payload_stats.file_count))
        print(" Size             : {}".format(format_bytes(payload_stats.total_bytes)))
        print(" .pyd files       : {}".format(payload_stats.pyd_count))
        print(" .dll files       : {}".format(payload_stats.dll_count))
        print(" Tree SHA-256     : {}".format(payload_stats.tree_sha256))
        print(" Payload          : {}".format(payload_extension))
        print(" Build manifest   : {}".format(manifest_path))

        if git_state.dirty:
            print()
            print(
                "[WARNING] This payload was built from a DIRTY worktree. "
                "Suitable for development testing, not a formal tagged release."
            )

        print()
        print("Next: open installer/AnonGee.iss and compile the installer.")
        return 0

    except BuildError as exc:
        print()
        print("=" * 68)
        print(" BUILD FAILED")
        print("=" * 68)
        print(str(exc))
        return 1
    except Exception as exc:
        print()
        print("=" * 68)
        print(" UNEXPECTED BUILD ERROR")
        print("=" * 68)
        print("{}: {}".format(type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
