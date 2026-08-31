# -*- coding: utf-8 -*-
"""
AnonGee Toolkit - CPython dependency provisioner

Developer-only clean rebuild tool for:
    AnonGee.extension/lib/py3

Design goals:
- Require Windows x64 + CPython 3.12.
- Refuse to modify the runtime while Revit is running.
- Treat requirements.txt as the exact dependency lock.
- Build into a fresh staging directory first.
- Use binary wheels only; never compile packages from source.
- Verify exact installed distribution versions.
- Smoke-test important imports without falling back to global site-packages.
- Replace lib/py3 only after the staged runtime passes validation.
- Optionally keep timestamped permanent backups.
- Always keep a temporary swap copy long enough to rollback a failed replacement.
- Preserve .dist-info metadata.
"""

import codecs
import datetime
import importlib.metadata
import os
import re
import shutil
import struct
import subprocess
import sys


# ============================================================
# USER SETTINGS
# ============================================================

TARGET_PY_VERSION = "3.12"
TARGET_ARCH_BITS = 64

# Optional permanent backup:
# False = no permanent backup is retained after a successful rebuild.
# True  = copy the old lib/py3 to tools/_runtime_backups before replacement.
ENABLE_BACKUP = False

# Important imports to test from the staged private runtime.
# Add/remove names here when your direct dependencies change.
PRESERVE_RUNTIME_ITEMS = [
    "anongee_clr.py",
    "anongee_toolkit",
]

# Important imports to test from the staged private runtime.
SMOKE_TEST_IMPORTS = [
    "numpy",
    "pandas",
    "openpyxl",
    "pythonnet",
    "ezdxf",
    "shapely",
    "xlwings",
    "requests",
]


# ============================================================
# PATHS
# ============================================================

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.normpath(os.path.join(TOOLS_DIR, ".."))

LIB_DIR = os.path.join(REPO_DIR, "AnonGee.extension", "lib")
PY3_TARGET_DIR = os.path.join(LIB_DIR, "py3")

REQUIREMENTS_FILE = os.path.join(TOOLS_DIR, "requirements.txt")

WORK_ROOT = os.path.join(TOOLS_DIR, "_runtime_work")
STAGING_DIR = os.path.join(WORK_ROOT, "py3_staging")
NORMALIZED_REQUIREMENTS = os.path.join(WORK_ROOT, "requirements.normalized.txt")
OVERLAY_DIR = os.path.join(WORK_ROOT, "runtime_overlay")

BACKUP_ROOT = os.path.join(TOOLS_DIR, "_runtime_backups")

# Temporary same-volume runtime used only during replacement.
# This is removed after a successful swap.
SWAP_OLD_DIR = os.path.join(LIB_DIR, ".py3_previous_swap")


# ============================================================
# DERIVED RUNTIME VALUES
# ============================================================

TARGET_PY = tuple(int(part) for part in TARGET_PY_VERSION.split("."))
TARGET_PY_TAG = TARGET_PY_VERSION.replace(".", "")
_RELAUNCH_MARKER = "__ANONGEE_PY{}_RELAUNCHED".format(TARGET_PY_TAG)


# ============================================================
# SMALL HELPERS
# ============================================================

def _print_header(title):
    print()
    print("=" * 60)
    print(" {}".format(title))
    print("=" * 60)


def _remove_tree(path):
    if os.path.isdir(path):
        shutil.rmtree(path)


def _normalise_package_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


# ============================================================
# WINDOWS / REVIT SAFETY
# ============================================================

def ensure_windows_x64():
    if os.name != "nt":
        raise RuntimeError(
            "This provisioner is intended for 64-bit Windows only."
        )

    bits = struct.calcsize("P") * 8
    if bits != TARGET_ARCH_BITS:
        raise RuntimeError(
            "This provisioner requires a {}-bit Python process; found {}-bit."
            .format(TARGET_ARCH_BITS, bits)
        )


def is_revit_running():
    """Check whether Revit.exe is currently running without psutil."""
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Revit.exe", "/NH"],
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

    return "revit.exe" in output.lower()


def ensure_revit_closed():
    if is_revit_running():
        raise RuntimeError(
            "Revit.exe is currently running.\n\n"
            "Close every Revit session before rebuilding lib/py3. "
            "Native .pyd/.dll files can be locked while Revit is open."
        )


# ============================================================
# PYTHON 3.12 x64 DISCOVERY / RELAUNCH
# ============================================================

def _current_runtime_is_valid():
    implementation_ok = (
        getattr(sys.implementation, "name", "").lower() == "cpython"
    )
    version_ok = sys.version_info[:2] == TARGET_PY
    architecture_ok = struct.calcsize("P") * 8 == TARGET_ARCH_BITS

    return implementation_ok and version_ok and architecture_ok


def _probe_python(interpreter):
    """Return True only if the candidate is CPython TARGET_PY_VERSION x64."""
    if not interpreter:
        return False

    probe = (
        "import sys, struct; "
        "ok=("
        "sys.implementation.name.lower()=='cpython' and "
        "sys.version_info[:2]==({major},{minor}) and "
        "struct.calcsize('P')*8=={bits}"
        "); "
        "sys.exit(0 if ok else 1)"
    ).format(
        major=TARGET_PY[0],
        minor=TARGET_PY[1],
        bits=TARGET_ARCH_BITS,
    )

    try:
        subprocess.check_output(
            list(interpreter) + ["-c", probe],
            stderr=subprocess.STDOUT,
            timeout=30,
            universal_newlines=True,
        )
        return True
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False


def _candidate_target_pythons():
    candidates = []
    seen = set()

    def add_candidate(command):
        if not command:
            return
        key = tuple(str(part).lower() for part in command)
        if key in seen:
            return
        seen.add(key)
        candidates.append(command)

    if _current_runtime_is_valid():
        add_candidate([sys.executable])

    py_launcher = shutil.which("py") or shutil.which("py.exe")
    if py_launcher:
        add_candidate([py_launcher, "-" + TARGET_PY_VERSION])

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    user_profile = os.environ.get("USERPROFILE", "")

    known_paths = []

    if local_app_data:
        known_paths.append(
            os.path.join(
                local_app_data,
                "Programs",
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe",
            )
        )
        known_paths.append(
            os.path.join(
                local_app_data,
                "Python",
                "pythoncore-{}-64".format(TARGET_PY_VERSION),
                "python.exe",
            )
        )

    if program_files:
        known_paths.append(
            os.path.join(
                program_files,
                "Python{}".format(TARGET_PY_TAG),
                "python.exe",
            )
        )
        known_paths.append(
            os.path.join(
                program_files,
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe",
            )
        )

    if user_profile:
        known_paths.append(
            os.path.join(
                user_profile,
                "AppData",
                "Local",
                "Programs",
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe",
            )
        )

    known_paths.append(
        os.path.join(
            "C:\\",
            "Python{}".format(TARGET_PY_TAG),
            "python.exe",
        )
    )

    for exe in known_paths:
        if os.path.isfile(exe):
            add_candidate([exe])

    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            add_candidate([found])

    return candidates


def ensure_target_python():
    """Relaunch this script under CPython 3.12 x64 when necessary."""
    if _current_runtime_is_valid():
        return True

    if os.environ.get(_RELAUNCH_MARKER):
        return False

    for interpreter in _candidate_target_pythons():
        if not _probe_python(interpreter):
            continue

        script = os.path.abspath(__file__)
        cmd = list(interpreter) + [script]

        print(
            "[INFO] Relaunching under CPython {} x64: {}".format(
                TARGET_PY_VERSION,
                " ".join(
                    '"{}"'.format(x) if " " in str(x) else str(x)
                    for x in cmd
                ),
            )
        )

        env = dict(os.environ)
        env[_RELAUNCH_MARKER] = "1"

        try:
            rc = subprocess.call(cmd, env=env)
        except OSError:
            continue

        sys.exit(rc)

    return False


# ============================================================
# REQUIREMENTS LOCK HANDLING
# ============================================================

def _read_text_with_bom_support(path):
    """Read UTF-8/UTF-8-BOM/UTF-16 requirement files safely."""
    with open(path, "rb") as stream:
        data = stream.read()

    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")

    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16")

    return data.decode("utf-8")


def prepare_locked_requirements():
    """
    Validate requirements.txt as a strict exact lock and create a normalized
    UTF-8 copy for pip. Every active requirement must be package==version.
    """
    if not os.path.isfile(REQUIREMENTS_FILE):
        raise RuntimeError(
            "requirements.txt was not found:\n{}".format(REQUIREMENTS_FILE)
        )

    text = _read_text_with_bom_support(REQUIREMENTS_FILE)
    expected = {}
    normalized_lines = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            if line.startswith("#"):
                normalized_lines.append(raw_line.rstrip())
            continue

        if "==" not in line:
            raise RuntimeError(
                "requirements.txt line {} is not exactly pinned:\n{}\n\n"
                "Use package==version for every dependency."
                .format(line_number, raw_line)
            )

        package_name, version = line.split("==", 1)
        package_name = package_name.strip()
        version = version.strip()

        if not package_name or not version:
            raise RuntimeError(
                "Invalid requirement on line {}: {}".format(
                    line_number, raw_line
                )
            )

        normalized_name = _normalise_package_name(package_name)

        if normalized_name in expected:
            raise RuntimeError(
                "Duplicate package in requirements.txt: {}".format(package_name)
            )

        expected[normalized_name] = version
        normalized_lines.append("{}=={}".format(package_name, version))

    if not expected:
        raise RuntimeError("requirements.txt contains no pinned packages.")

    _remove_tree(WORK_ROOT)
    os.makedirs(WORK_ROOT, exist_ok=True)

    with open(
        NORMALIZED_REQUIREMENTS,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        stream.write("\n".join(normalized_lines))
        stream.write("\n")

    return expected


# ============================================================
# PRESERVE CUSTOM RUNTIME CODE
# ============================================================

def capture_runtime_overlay():
    """
    Copy AnonGee-owned files/directories that intentionally live inside
    lib/py3 but are not pip distributions. This prevents a clean dependency
    rebuild from deleting toolkit source such as anongee_toolkit.
    """
    _remove_tree(OVERLAY_DIR)
    os.makedirs(OVERLAY_DIR, exist_ok=True)

    captured = []

    for item_name in PRESERVE_RUNTIME_ITEMS:
        source = os.path.join(PY3_TARGET_DIR, item_name)
        destination = os.path.join(OVERLAY_DIR, item_name)

        if os.path.isdir(source):
            shutil.copytree(source, destination)
            captured.append(item_name)
        elif os.path.isfile(source):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
            captured.append(item_name)

    if captured:
        print("[INFO] Preserved custom runtime items: {}".format(
            ", ".join(captured)
        ))
    else:
        print("[INFO] No configured custom runtime overlay items were present.")


def apply_runtime_overlay():
    """Overlay preserved AnonGee-owned runtime code onto the staged pip tree."""
    if not os.path.isdir(OVERLAY_DIR):
        return

    for item_name in PRESERVE_RUNTIME_ITEMS:
        source = os.path.join(OVERLAY_DIR, item_name)
        destination = os.path.join(STAGING_DIR, item_name)

        if os.path.isdir(source):
            if os.path.exists(destination):
                _remove_tree(destination)
            shutil.copytree(source, destination)
        elif os.path.isfile(source):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)


# ============================================================
# FRESH STAGED BUILD
# ============================================================

def build_staged_runtime():
    """
    Build a completely fresh runtime using binary wheels only.
    No files are written to the live lib/py3 during this step.
    """
    _print_header("BUILDING FRESH STAGED RUNTIME")

    _remove_tree(STAGING_DIR)
    os.makedirs(STAGING_DIR, exist_ok=True)

    print("Python       : {}.{}.{}".format(
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    ))
    print("Interpreter  : {}".format(sys.executable))
    print("Architecture : {}-bit".format(struct.calcsize("P") * 8))
    print("Requirements : {}".format(REQUIREMENTS_FILE))
    print("Staging      : {}".format(STAGING_DIR))
    print()

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--requirement",
        NORMALIZED_REQUIREMENTS,
        "--target",
        STAGING_DIR,
        "--only-binary=:all:",
        "--disable-pip-version-check",
    ]

    subprocess.check_call(cmd)

    # Restore AnonGee-owned runtime code that is not managed by pip.
    apply_runtime_overlay()


# ============================================================
# DISTRIBUTION VERIFICATION
# ============================================================

def _installed_distributions(path):
    result = {}

    for distribution in importlib.metadata.distributions(path=[path]):
        name = distribution.metadata.get("Name")
        if not name:
            continue

        normalized_name = _normalise_package_name(name)

        if normalized_name in result:
            raise RuntimeError(
                "Duplicate installed distribution metadata found for: {}".format(name)
            )

        result[normalized_name] = distribution.version

    return result


def verify_distribution_lock(path, expected):
    """
    Require an exact set match:
    - every pinned package exists
    - exact version matches
    - no unexpected distribution is present
    """
    _print_header("VERIFYING LOCKED DISTRIBUTIONS")

    installed = _installed_distributions(path)
    errors = []

    for package_name in sorted(expected):
        wanted = expected[package_name]
        actual = installed.get(package_name)

        if actual is None:
            errors.append(
                "{} missing (expected {})".format(package_name, wanted)
            )
            print("[FAIL] {:28} missing".format(package_name))
        elif actual != wanted:
            errors.append(
                "{} expected {}, found {}".format(package_name, wanted, actual)
            )
            print(
                "[FAIL] {:28} expected {} / found {}".format(
                    package_name, wanted, actual
                )
            )
        else:
            print("[ OK ] {:28} {}".format(package_name, actual))

    unexpected = sorted(set(installed) - set(expected))

    for package_name in unexpected:
        errors.append(
            "{} installed but not present in requirements.txt ({})".format(
                package_name, installed[package_name]
            )
        )
        print(
            "[FAIL] {:28} unexpected ({})".format(
                package_name, installed[package_name]
            )
        )

    if errors:
        raise RuntimeError(
            "Dependency lock verification failed:\n\n{}".format(
                "\n".join(errors)
            )
        )

    print()
    print(
        "[SUCCESS] Exact lock verified: {} distributions.".format(
            len(expected)
        )
    )


# ============================================================
# IMPORT SMOKE TEST
# ============================================================

def smoke_test_runtime(path):
    """
    Launch Python with -S so global site-packages are unavailable.
    Insert only the private runtime, then import important packages.
    """
    _print_header("SMOKE-TESTING PRIVATE RUNTIME")

    imports_literal = repr(SMOKE_TEST_IMPORTS)
    target_literal = repr(os.path.abspath(path))

    smoke_code = (
        "import os, sys\n"
        "target = {target}\n"
        "sys.path.insert(0, target)\n"
        "mods = {mods}\n"
        "for name in mods:\n"
        "    mod = __import__(name)\n"
        "    location = getattr(mod, '__file__', '') or ''\n"
        "    print('[ OK ] {{:<20}} {{}}'.format(name, location))\n"
        "    if location and not os.path.normcase(os.path.abspath(location)).startswith("
        "os.path.normcase(os.path.abspath(target))):\n"
        "        raise RuntimeError('Module loaded outside private runtime: ' + name + ' -> ' + location)\n"
    ).format(
        target=target_literal,
        mods=imports_literal,
    )

    subprocess.check_call(
        [
            sys.executable,
            "-S",
            "-c",
            smoke_code,
        ]
    )

    print()
    print("[SUCCESS] Import smoke test passed.")


# ============================================================
# OPTIONAL PERMANENT BACKUP
# ============================================================

def backup_current_runtime():
    """Create a timestamped permanent backup only when ENABLE_BACKUP=True."""
    if not ENABLE_BACKUP:
        print("[INFO] Permanent runtime backup: disabled.")
        return None

    if not os.path.isdir(PY3_TARGET_DIR):
        print("[INFO] No existing lib/py3 runtime to back up.")
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_ROOT, exist_ok=True)

    backup_path = os.path.join(
        BACKUP_ROOT,
        "py3_{}".format(timestamp),
    )

    _print_header("CREATING PERMANENT BACKUP")
    print("Source : {}".format(PY3_TARGET_DIR))
    print("Backup : {}".format(backup_path))

    shutil.copytree(PY3_TARGET_DIR, backup_path)

    print("[SUCCESS] Permanent backup created.")
    return backup_path


# ============================================================
# TRANSACTIONAL LIVE RUNTIME REPLACEMENT
# ============================================================

def replace_live_runtime():
    """
    Replace lib/py3 with the validated staged runtime.

    Even when permanent backups are disabled, the old live runtime is
    temporarily renamed to .py3_previous_swap until the new runtime has
    been installed and verified. This gives an automatic rollback path.
    """
    _print_header("REPLACING LIVE lib/py3")

    _remove_tree(SWAP_OLD_DIR)

    old_runtime_existed = os.path.isdir(PY3_TARGET_DIR)

    if old_runtime_existed:
        print("Temporarily preserving current runtime:")
        print("  {} -> {}".format(PY3_TARGET_DIR, SWAP_OLD_DIR))
        os.replace(PY3_TARGET_DIR, SWAP_OLD_DIR)

    try:
        print("Installing validated staged runtime:")
        print("  {} -> {}".format(STAGING_DIR, PY3_TARGET_DIR))
        os.replace(STAGING_DIR, PY3_TARGET_DIR)

    except Exception:
        if os.path.isdir(PY3_TARGET_DIR):
            _remove_tree(PY3_TARGET_DIR)

        if old_runtime_existed and os.path.isdir(SWAP_OLD_DIR):
            os.replace(SWAP_OLD_DIR, PY3_TARGET_DIR)

        raise


def rollback_swap_runtime():
    """Restore .py3_previous_swap after a failed post-swap verification."""
    if not os.path.isdir(SWAP_OLD_DIR):
        return False

    print("[WARNING] Restoring previous known-good runtime...")

    if os.path.isdir(PY3_TARGET_DIR):
        _remove_tree(PY3_TARGET_DIR)

    os.replace(SWAP_OLD_DIR, PY3_TARGET_DIR)

    print("[SUCCESS] Previous runtime restored.")
    return True


def finalize_swap():
    """Delete the temporary swap copy after the new runtime passes final tests."""
    _remove_tree(SWAP_OLD_DIR)


# ============================================================
# CLEANUP
# ============================================================

def cleanup_work_area():
    _remove_tree(WORK_ROOT)


# ============================================================
# ERROR MESSAGE
# ============================================================

def print_python_not_found():
    _print_header("SUPPORTED PYTHON NOT FOUND")

    print(
        "AnonGee dependency provisioning requires CPython {} x64."
        .format(TARGET_PY_VERSION)
    )
    print()
    print(
        "Install Python {} x64 on the DEVELOPMENT PC and rerun."
        .format(TARGET_PY_VERSION)
    )
    print()
    print("No runtime files were modified.")


# ============================================================
# MAIN
# ============================================================

def main():
    _print_header("ANONGEE CLEAN-RUNTIME PROVISIONER")

    if not ensure_target_python():
        print_python_not_found()
        return 1

    try:
        ensure_windows_x64()
        ensure_revit_closed()

        expected = prepare_locked_requirements()

        # Preserve AnonGee-owned source that intentionally lives inside lib/py3.
        capture_runtime_overlay()

        # 1. Build completely outside the live runtime.
        build_staged_runtime()

        # 2. Validate staged package set and native imports.
        verify_distribution_lock(STAGING_DIR, expected)
        smoke_test_runtime(STAGING_DIR)

        # 3. Optional retained backup of the current working runtime.
        backup_current_runtime()

        # 4. Transactionally replace live lib/py3.
        replace_live_runtime()

        try:
            # 5. Verify again from the final location.
            verify_distribution_lock(PY3_TARGET_DIR, expected)
            smoke_test_runtime(PY3_TARGET_DIR)
        except Exception:
            rollback_swap_runtime()
            raise

        # 6. New runtime is known good. Remove temporary rollback copy.
        finalize_swap()
        cleanup_work_area()

        _print_header("CLEAN REBUILD SUCCESSFUL")
        print("Runtime:")
        print("  {}".format(PY3_TARGET_DIR))
        print()
        print("requirements.txt is now the exact source of truth.")
        print("Removed packages do not survive a rebuild.")
        print(".dist-info metadata is retained.")
        print("Only prebuilt binary wheels were accepted.")

        if ENABLE_BACKUP:
            print()
            print("Permanent backup mode was ENABLED.")
            print("Backup root:")
            print("  {}".format(BACKUP_ROOT))
        else:
            print()
            print("Permanent backup mode was disabled.")

        return 0

    except subprocess.CalledProcessError as exc:
        print()
        print(
            "[ERROR] A subprocess failed with exit code {}."
            .format(exc.returncode)
        )
        return 1

    except Exception as exc:
        print()
        print("[CRITICAL ERROR]")
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
