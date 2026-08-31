# 1. DEFINE YOUR MANUALLY CONTROLLED DEPENDENCIES HERE
# Simply list package names as space-separated strings.
# You can also add specific versions if needed (e.g., "openpyxl==3.1.5")
# ezdxf pulls pyparsing / numpy / fontTools / typing_extensions automatically and
# powers the CAD to BIM button's DXF parsing (run this with a CPython matching the
# pyRevit CPython3 engine, so the numpy/ezdxf binaries match). The target CPython
# version is controlled by TARGET_PY_VERSION below - edit that one value to retarget.
# PY3_DEPENDENCIES = "numpy pandas openpyxl pythonnet ezdxf shapely xlwings requests"
# PY2_DEPENDENCIES = ""
# -*- coding: utf-8 -*-

import importlib.metadata
import os
import re
import shutil
import struct
import subprocess
import sys
import datetime

# ============================================================
# ANONGEE / PYZAID DEPENDENCY PROVISIONER
# ============================================================
#
# Purpose:
#   Install the exact tested CPython dependencies required by
#   the AnonGee pyRevit extension into:
#
#       AnonGee.extension/lib/py3
#
# Important:
#   - Uses pinned versions from requirements.txt
#   - Requires CPython 3.12 x64
#   - Does NOT delete .dist-info metadata
#   - Does NOT change the existing lib/py3 structure
#   - Verifies installed versions after provisioning
#
# Expected layout:
#
#   repo/
#   ├── AnonGee.extension/
#   │   └── lib/
#   │       └── py3/
#   │
#   └── tools/
#       ├── auto_provision.py
#       ├── install_dependencies.bat
#       └── requirements.txt
#
# ============================================================


# ------------------------------------------------------------
# 1. PATH CONFIGURATION
# ------------------------------------------------------------

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

LIB_DIR = os.path.normpath(
    os.path.join(
        TOOLS_DIR,
        "..",
        "AnonGee.extension",
        "lib"
    )
)

PY3_TARGET_DIR = os.path.join(
    LIB_DIR,
    "py3"
)

REQUIREMENTS_FILE = os.path.join(
    TOOLS_DIR,
    "requirements.txt"
)

# ------------------------------------------------------------
# CLEAN REBUILD / BACKUP SETTINGS
# ------------------------------------------------------------

# True:
#   Creates a complete lib/py3 backup before rebuilding.
#   If installation or validation fails, automatically restores it.
#
# False:
#   Performs the clean rebuild without keeping a backup.
ENABLE_BACKUP = False

BACKUP_ROOT = os.path.join(
    TOOLS_DIR,
    "_runtime_backups"
)

# ------------------------------------------------------------
# 2. REQUIRED PYTHON RUNTIME
# ------------------------------------------------------------

# pyRevit CPython engine target.
#
# Example:
#   CPY3123 -> Python 3.12
#
# Change this one value only if the pyRevit runtime is
# deliberately migrated in the future.

TARGET_PY_VERSION = "3.12"

TARGET_PY = tuple(
    int(part)
    for part in TARGET_PY_VERSION.split(".")
)

TARGET_PY_TAG = TARGET_PY_VERSION.replace(".", "")

TARGET_ARCH_BITS = 64

_RELAUNCH_MARKER = "__PYZAID_{}_RELAUNCHED".format(
    TARGET_PY_TAG
)


# ------------------------------------------------------------
# 3. RUNTIME VALIDATION
# ------------------------------------------------------------

def _current_runtime_is_valid():
    """
    Return True only when this process is running under:

        CPython
        Python 3.12
        64-bit

    This is important because native packages such as NumPy,
    Shapely and Python.NET must match pyRevit's CPython runtime.
    """

    implementation_ok = (
        getattr(sys.implementation, "name", "").lower()
        == "cpython"
    )

    version_ok = (
        sys.version_info[:2] == TARGET_PY
    )

    architecture_ok = (
        struct.calcsize("P") * 8 == TARGET_ARCH_BITS
    )

    return (
        implementation_ok
        and version_ok
        and architecture_ok
    )


def _probe_python(interpreter):
    """
    Launch a candidate interpreter and verify that it is:

        CPython
        target Python version
        64-bit

    Example candidate:

        ["C:\\Python312\\python.exe"]

    or:

        ["py.exe", "-3.12"]
    """

    if not interpreter:
        return False

    probe = (
        "import sys, struct; "
        "ok = ("
        "sys.implementation.name.lower() == 'cpython' "
        "and sys.version_info[:2] == ({major}, {minor}) "
        "and struct.calcsize('P') * 8 == {bits}"
        "); "
        "sys.exit(0 if ok else 1)"
    ).format(
        major=TARGET_PY[0],
        minor=TARGET_PY[1],
        bits=TARGET_ARCH_BITS
    )

    try:
        subprocess.check_output(
            list(interpreter) + ["-c", probe],
            stderr=subprocess.STDOUT,
            timeout=30,
            universal_newlines=True
        )

        return True

    except (
        subprocess.CalledProcessError,
        OSError,
        subprocess.TimeoutExpired
    ):
        return False


# ------------------------------------------------------------
# 4. PYTHON DISCOVERY
# ------------------------------------------------------------

def _candidate_target_pythons():
    """
    Return possible target Python interpreters.

    Every candidate is verified later by _probe_python(), so
    simply finding python.exe is not enough for it to be used.
    """

    candidates = []
    seen = set()

    def add_candidate(command):
        if not command:
            return

        key = tuple(
            str(part).lower()
            for part in command
        )

        if key in seen:
            return

        seen.add(key)
        candidates.append(command)

    # --------------------------------------------------------
    # A. Current interpreter
    # --------------------------------------------------------

    if _current_runtime_is_valid():
        add_candidate([sys.executable])


    # --------------------------------------------------------
    # B. Windows Python Launcher
    #
    # Preferred normal installation route:
    #
    #     py -3.12
    # --------------------------------------------------------

    py_launcher = (
        shutil.which("py")
        or shutil.which("py.exe")
    )

    if py_launcher:

        add_candidate([
            py_launcher,
            "-" + TARGET_PY_VERSION
        ])


    # --------------------------------------------------------
    # C. Known Python installation paths
    # --------------------------------------------------------

    local_app_data = os.environ.get(
        "LOCALAPPDATA",
        ""
    )

    program_files = os.environ.get(
        "ProgramFiles",
        ""
    )

    user_profile = os.environ.get(
        "USERPROFILE",
        ""
    )

    known_paths = []


    # Standard python.org user installation:
    #
    # %LOCALAPPDATA%\Programs\Python\Python312\python.exe

    if local_app_data:
        known_paths.append(
            os.path.join(
                local_app_data,
                "Programs",
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe"
            )
        )


    # Newer Python install-manager layout:
    #
    # %LOCALAPPDATA%\Python\pythoncore-3.12-64\python.exe

    if local_app_data:
        known_paths.append(
            os.path.join(
                local_app_data,
                "Python",
                "pythoncore-{}-64".format(
                    TARGET_PY_VERSION
                ),
                "python.exe"
            )
        )


    # Machine-wide installation:
    #
    # C:\Program Files\Python312\python.exe

    if program_files:
        known_paths.append(
            os.path.join(
                program_files,
                "Python{}".format(TARGET_PY_TAG),
                "python.exe"
            )
        )


    # Alternative machine-wide layout:
    #
    # C:\Program Files\Python\Python312\python.exe

    if program_files:
        known_paths.append(
            os.path.join(
                program_files,
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe"
            )
        )


    # Explicit user-profile fallback.

    if user_profile:
        known_paths.append(
            os.path.join(
                user_profile,
                "AppData",
                "Local",
                "Programs",
                "Python",
                "Python{}".format(TARGET_PY_TAG),
                "python.exe"
            )
        )


    # Traditional standalone location:
    #
    # C:\Python312\python.exe

    known_paths.append(
        os.path.join(
            "C:\\",
            "Python{}".format(TARGET_PY_TAG),
            "python.exe"
        )
    )


    for exe in known_paths:

        if os.path.isfile(exe):
            add_candidate([exe])


    # --------------------------------------------------------
    # D. PATH fallback
    # --------------------------------------------------------

    for name in (
        "python",
        "python3"
    ):

        found = shutil.which(name)

        if found:
            add_candidate([found])


    return candidates


# ------------------------------------------------------------
# 5. ENSURE CORRECT PYTHON
# ------------------------------------------------------------

def ensure_target_python():
    """
    Ensure this script runs under the exact supported runtime.

    If launched using another Python version, try to discover
    CPython 3.12 x64 and restart this script under it.
    """

    if _current_runtime_is_valid():
        return True


    # Prevent accidental relaunch loops.

    if os.environ.get(_RELAUNCH_MARKER):

        print()
        print("[ERROR] Python relaunch validation failed.")
        print(
            "        Expected CPython {} x64.".format(
                TARGET_PY_VERSION
            )
        )

        return False


    for interpreter in _candidate_target_pythons():

        if not _probe_python(interpreter):
            continue


        script = os.path.abspath(__file__)

        cmd = (
            list(interpreter)
            + [script]
        )


        print()
        print(
            "[INFO] Current interpreter is not "
            "CPython {} x64.".format(
                TARGET_PY_VERSION
            )
        )

        print(
            "[INFO] Relaunching with:"
        )

        print(
            "       {}".format(
                " ".join(
                    '"{}"'.format(part)
                    if " " in str(part)
                    else str(part)
                    for part in cmd
                )
            )
        )

        print()


        env = dict(os.environ)

        env[_RELAUNCH_MARKER] = "1"


        try:

            rc = subprocess.call(
                cmd,
                env=env
            )

        except OSError as exc:

            print(
                "[ERROR] Could not launch {}: {}".format(
                    " ".join(interpreter),
                    exc
                )
            )

            continue


        # Mirror child exit code.

        sys.exit(rc)


    return False


# ------------------------------------------------------------
# 6. REQUIREMENTS VALIDATION
# ------------------------------------------------------------

def validate_requirements_file():
    """
    Verify that requirements.txt exists before making any
    changes to lib/py3.
    """

    if not os.path.isfile(REQUIREMENTS_FILE):

        raise RuntimeError(
            "Requirements file not found:\n{}".format(
                REQUIREMENTS_FILE
            )
        )


# ------------------------------------------------------------
# 7. DEPLOY PINNED DEPENDENCIES
# ------------------------------------------------------------

def deploy_py3_requirements():
    """
    Install the exact dependency versions specified in
    requirements.txt directly into the extension's existing
    lib/py3 directory.
    """

    validate_requirements_file()

    os.makedirs(
        PY3_TARGET_DIR,
        exist_ok=True
    )


    print()
    print("====================================================")
    print(" DEPLOYING PINNED CPYTHON DEPENDENCIES")
    print("====================================================")

    print(
        " Python      : {}.{}.{}".format(
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro
        )
    )

    print(
        " Architecture: {}-bit".format(
            struct.calcsize("P") * 8
        )
    )

    print(
        " Interpreter : {}".format(
            sys.executable
        )
    )

    print(
        " Requirements: {}".format(
            REQUIREMENTS_FILE
        )
    )

    print(
        " Target      : {}".format(
            PY3_TARGET_DIR
        )
    )

    print()


    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",

        "--requirement",
        REQUIREMENTS_FILE,

        "--target",
        PY3_TARGET_DIR,

        "--upgrade",

        "--disable-pip-version-check"
    ]


    subprocess.check_call(cmd)


# ------------------------------------------------------------
# 8. REQUIREMENTS PARSING
# ------------------------------------------------------------

def _normalise_package_name(name):
    """
    Apply Python package-name normalisation so names such as:

        typing_extensions
        typing-extensions

    compare correctly.
    """

    return re.sub(
        r"[-_.]+",
        "-",
        name
    ).lower()


def _read_pinned_requirements():
    """
    Read exact package==version entries from requirements.txt.

    Returns:

        {
            "numpy": "2.5.2",
            "shapely": "2.1.2",
            ...
        }
    """

    pinned = {}


    # utf-8-sig also safely handles a UTF-8 BOM if present.

    with open(
        REQUIREMENTS_FILE,
        "r",
        encoding="utf-8-sig"
    ) as requirements_file:

        for raw_line in requirements_file:

            line = raw_line.strip()


            if not line:
                continue

            if line.startswith("#"):
                continue


            # Current lock file intentionally uses exact pins.
            #
            # Example:
            #
            #     numpy==2.5.2

            if "==" not in line:
                continue


            package_name, version = line.split(
                "==",
                1
            )


            package_name = (
                package_name.strip()
            )

            version = (
                version.strip()
            )


            if not package_name:
                continue

            if not version:
                continue


            pinned[
                _normalise_package_name(
                    package_name
                )
            ] = version


    return pinned


# ------------------------------------------------------------
# 9. VERIFY INSTALLED VERSIONS
# ------------------------------------------------------------

def verify_installed_requirements():
    """
    Verify that every pinned dependency exists inside lib/py3
    with the exact expected version.

    This uses .dist-info metadata, which is intentionally kept.
    """

    print()
    print("====================================================")
    print(" VERIFYING INSTALLED DEPENDENCIES")
    print("====================================================")
    print()


    expected = _read_pinned_requirements()


    if not expected:

        raise RuntimeError(
            "No exact package pins were found in requirements.txt."
        )


    installed = {}


    for distribution in importlib.metadata.distributions(
        path=[PY3_TARGET_DIR]
    ):

        package_name = distribution.metadata.get(
            "Name"
        )

        if not package_name:
            continue


        normalised_name = _normalise_package_name(
            package_name
        )


        installed[normalised_name] = (
            distribution.version
        )


    errors = []


    for package_name in sorted(expected):

        expected_version = expected[
            package_name
        ]

        actual_version = installed.get(
            package_name
        )


        if actual_version is None:

            errors.append(
                "{}: NOT FOUND "
                "(expected {})".format(
                    package_name,
                    expected_version
                )
            )

            print(
                "[FAIL] {:25} missing".format(
                    package_name
                )
            )

            continue


        if actual_version != expected_version:

            errors.append(
                "{}: expected {}, found {}".format(
                    package_name,
                    expected_version,
                    actual_version
                )
            )

            print(
                "[FAIL] {:25} expected {} / found {}".format(
                    package_name,
                    expected_version,
                    actual_version
                )
            )

            continue


        print(
            "[ OK ] {:25} {}".format(
                package_name,
                actual_version
            )
        )


    print()


    if errors:

        raise RuntimeError(
            "Dependency verification failed:\n\n{}".format(
                "\n".join(errors)
            )
        )


    print(
        "[SUCCESS] All {} pinned packages match "
        "requirements.txt.".format(
            len(expected)
        )
    )


# ------------------------------------------------------------
# 10. ERROR MESSAGE WHEN PYTHON IS MISSING
# ------------------------------------------------------------

def _abort_python_not_found():

    print()
    print("====================================================")
    print(" PYTHON {} x64 NOT FOUND".format(
        TARGET_PY_VERSION
    ))
    print(" PROVISIONING ABORTED")
    print("====================================================")
    print()

    print(
        "This toolkit requires:"
    )

    print()
    print(
        "    CPython {} x64".format(
            TARGET_PY_VERSION
        )
    )

    print()

    print(
        "This matches the pyRevit CPython engine used by "
        "the toolkit."
    )

    print()

    print(
        "No dependencies were installed."
    )

    print()

    print(
        "Install Python {} x64 and run the installer again."
        .format(
            TARGET_PY_VERSION
        )
    )

    print()


# ------------------------------------------------------------
# 11. MAIN
# ------------------------------------------------------------

def main():

    print()
    print("====================================================")
    print(" PYZAID / ANONGEE DEPENDENCY PROVISIONER")
    print("====================================================")
    print()


    # --------------------------------------------------------
    # Step 1:
    # Make absolutely sure pip runs under CPython 3.12 x64.
    # --------------------------------------------------------

    if not ensure_target_python():

        _abort_python_not_found()

        return 1


    try:

        # ----------------------------------------------------
        # Step 2:
        # Install exact locked versions from requirements.txt.
        # ----------------------------------------------------

        deploy_py3_requirements()


        # ----------------------------------------------------
        # Step 3:
        # Verify every pinned package using retained
        # .dist-info metadata.
        # ----------------------------------------------------

        verify_installed_requirements()


        print()
        print("====================================================")
        print(" SUCCESS")
        print("====================================================")
        print()

        print(
            "All pinned dependencies were deployed to:"
        )

        print(
            "    {}".format(
                PY3_TARGET_DIR
            )
        )

        print()

        print(
            "Dependency metadata (.dist-info) was retained."
        )

        print()

        return 0


    except subprocess.CalledProcessError as exc:

        print()
        print("====================================================")
        print(" PIP INSTALLATION FAILED")
        print("====================================================")
        print()

        print(
            "pip exited with code: {}".format(
                exc.returncode
            )
        )

        print()

        return 1


    except Exception as exc:

        print()
        print("====================================================")
        print(" CRITICAL ERROR")
        print("====================================================")
        print()

        print(
            str(exc)
        )

        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())