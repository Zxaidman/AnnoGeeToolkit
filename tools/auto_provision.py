import os
import shutil
import subprocess
import sys

# 1. DEFINE YOUR MANUALLY CONTROLLED DEPENDENCIES HERE
# Simply list package names as space-separated strings.
# You can also add specific versions if needed (e.g., "openpyxl==3.1.5")
# ezdxf pulls pyparsing / numpy / fontTools / typing_extensions automatically and
# powers the CAD to BIM button's DXF parsing (run this with a CPython matching the
# pyRevit CPython3 engine, so the numpy/ezdxf binaries match). The target CPython
# version is controlled by TARGET_PY_VERSION below - edit that one value to retarget.
PY3_DEPENDENCIES = "numpy pandas openpyxl pythonnet ezdxf shapely xlwings requests"
PY2_DEPENDENCIES = ""

# 2. Setup folder pathways relative to this script
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.normpath(os.path.join(TOOLS_DIR, "..", "AnonGee.extension", "lib"))

# 3. The ONLY Python version that produces pip binaries compatible with
#    pyRevit's embedded CPython3 engine (e.g. CPY3123). Change THIS ONE
#    variable to retarget the whole tool (e.g. "3.12" -> "3.14"); every
#    derived value below (probe, launcher arg, install-dir name) follows.
TARGET_PY_VERSION = "3.12"
TARGET_PY = tuple(int(part) for part in TARGET_PY_VERSION.split("."))  # (3, 12)
TARGET_PY_TAG = TARGET_PY_VERSION.replace(".", "")                     # "312"
_RELAUNCH_MARKER = "__PYZAID_{}_RELAUNCHED".format(TARGET_PY_TAG)


def _probe_python(interpreter):
    """Return True only if `interpreter` is an actual CPython %d.%d."""
    if not interpreter:
        return False
    probe = (
        "import sys; "
        "sys.exit(0 if sys.version_info[:2] == (%d, %d) else 1)" % TARGET_PY
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


def _candidate_python_312():
    """Candidate interpreters that MIGHT be Python {0}, best first.

    `_probe_python` verifies each by actually launching it, so a guessed path
    that turns out to be a different version is simply skipped.
    """.format(TARGET_PY_VERSION)
    candidates = []

    # (a) We are already running under exactly 3.12 -> stay in-process.
    if sys.version_info[:2] == TARGET_PY:
        candidates.append([sys.executable])

    # (b) The `py` launcher (installed alongside python.org / py-installer)
    #     can pin a specific install by version shortcut, e.g. py -3.12.
    py_launcher = shutil.which("py") or shutil.which("py.exe")
    if py_launcher:
        launcher_arg = "-" + TARGET_PY_VERSION      # "-3.12"
        candidates.append([py_launcher, launcher_arg])
        candidates.append([py_launcher, launcher_arg.replace(".", "-")])  # "-3-12"

    # (c) Standalone installs in the well-known python.org / pip-manager dirs.
    root_dirs = [
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("USERPROFILE", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("PROGRAMFILES", ""),
        "C:\\",
    ]
    seen = set()
    for root in root_dirs:
        if not root:
            continue
        for candidate_dir in ("Programs", "Python", "Python" + TARGET_PY_TAG):
            base = os.path.join(root, candidate_dir)
            if not os.path.isdir(base):
                continue
            try:
                entries = os.listdir(base)
            except OSError:
                continue
            for entry in entries:
                if ("python" + TARGET_PY_TAG) not in entry.lower():
                    continue
                exe = os.path.join(base, entry, "python.exe")
                key = exe.lower()
                if key in seen:
                    continue
                seen.add(key)
                if os.path.isfile(exe):
                    candidates.append([exe])

    # (d) Last resort: whatever is on PATH under python / python3. The probe
    #     below decides whether it is actually 3.12.
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found and [found] not in candidates:
            candidates.append([found])

    return candidates


def ensure_python_312():
    """Ensure the current process is a genuine CPython {0}.

    Returns True when we are already running under Python {0}. Otherwise it
    finds any real {0} on the machine and relaunches THIS script under it (the
    child then performs the real work and mirrors its exit code back).

    When the child has already been relaunched once (marker env var) but still
    reports a different version, we abort instead of looping forever.
    """.format(TARGET_PY_VERSION)
    if sys.version_info[:2] == TARGET_PY:
        return True

    for interpreter in _candidate_python_312():
        if not _probe_python(interpreter):
            continue

        if os.environ.get(_RELAUNCH_MARKER):
            print(
                ("[ERROR] Relaunched under what should be Python {0}, but the "
                 "process still reports %d.%d. Aborting to avoid an infinite "
                 "loop.").format(TARGET_PY_VERSION) % sys.version_info[:2]
            )
            return False

        script = os.path.abspath(__file__)
        cmd = list(interpreter) + [script]
        print(("[INFO] Current interpreter is Python %d.%d, not Python {0}.")
              .format(TARGET_PY_VERSION) % sys.version_info[:2])
        print(("       Relaunching under discovered Python {0}: %s\n")
              .format(TARGET_PY_VERSION) % " ".join(cmd))

        env = dict(os.environ)
        env[_RELAUNCH_MARKER] = "1"
        try:
            rc = subprocess.call(cmd, env=env)
        except OSError as exc:
            print("[ERROR] Could not launch %s: %s" % (" ".join(interpreter), exc))
            continue
        sys.exit(rc)

    return False

def deploy_libraries(dependencies_string, subfolder):
    # Split the string into a clean Python list of packages
    packages = [pkg.strip() for pkg in dependencies_string.split() if pkg.strip()]
    
    if not packages:
        print(f"[INFO] No packages specified for lib/{subfolder}. Skipping.")
        return

    target_path = os.path.join(LIB_DIR, subfolder)
    os.makedirs(target_path, exist_ok=True)
    
    print(f"\n[PROCESS] Deploying to lib/{subfolder}...")
    print(f"          Packages: {packages}")
    
    # Run the standard pip installation using your current Python environment
    cmd = [
        sys.executable, "-m", "pip", 
        "install", 
        "--target", target_path, 
        "--upgrade"
    ] + packages
    
    subprocess.check_call(cmd)

def clean_metadata_clutter():
    print("\n[PROCESS] Sweeping away redundant .dist-info tracking metadata folders...")
    for sub in ['py2', 'py3']:
        sub_path = os.path.join(LIB_DIR, sub)
        if os.path.exists(sub_path):
            for item in os.listdir(sub_path):
                item_path = os.path.join(sub_path, item)
                # Remove messy metadata folders that pip generates
                if os.path.isdir(item_path) and (item.endswith('.dist-info') or item.endswith('.egg-info')):
                    print(f"          Removing: lib/{sub}/{item}")
                    subprocess.call(f'rmdir /s /q "{item_path}"', shell=True)

def _abort_python_not_found():
    print("\n====================================================")
    print(" PYTHON {0} NOT FOUND - PROVISIONING ABORTED        ".format(TARGET_PY_VERSION))
    print("====================================================")
    print()
    print(" This tool must run under CPython {0} so the compiled".format(TARGET_PY_VERSION))
    print(" numpy / ezdxf / shapely binaries match pyRevit's own")
    print(" embedded CPython{0} engine (CPY{0}).".format(TARGET_PY_TAG))
    print()
    print(" We looked in every normal Windows install location:")
    print("   - the `py` launcher        (py -{0})".format(TARGET_PY_VERSION))
    print("   - python.org install       (%LOCALAPPDATA%\\Programs\\Python\\Python{0})".format(TARGET_PY_TAG))
    print("   - install-manager/standalone  (Program Files, or the C: drive root, etc.)")
    print()
    print(" Install Python {0} from https://www.python.org/downloads/".format(TARGET_PY_VERSION))
    print(" (tick 'Add Python to PATH' and keep the bundled `py` launcher),")
    print(" then run this script again.")
    print()
    print(" No packages were installed. Nothing was modified.\n")


if __name__ == "__main__":
    print("====================================================")
    print(" MANUALLY CONTROLLED PYZAID DEPENDENCY PROVISIONER  ")
    print("====================================================")

    # 0. (Always) Verify we are running a REAL target CPython first.
    #    If not, this relaunches under a discovered install or hard-stops.
    if not ensure_python_312():
        _abort_python_not_found()
        sys.exit(1)

    try:
        # Deploy CPython 3 libraries
        deploy_libraries(PY3_DEPENDENCIES, "py3")

        # Deploy IronPython 2 libraries
        deploy_libraries(PY2_DEPENDENCIES, "py2")

        # Keep things clean
        # clean_metadata_clutter()

        print("\n====================================================")
        print(" SUCCESS: All requested libraries deployed cleanly! ")
        print("====================================================\n")

    except Exception as e:
        print(f"\n[CRITICAL ERROR]: {str(e)}")
        sys.exit(1)
