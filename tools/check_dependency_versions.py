import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)
PY3_DIR = os.path.join(
    REPO_DIR,
    "AnonGee.extension",
    "lib",
    "py3"
)

sys.path.insert(0, PY3_DIR)

packages = [
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("pythonnet", "pythonnet"),
    ("ezdxf", "ezdxf"),
    ("shapely", "shapely"),
    ("xlwings", "xlwings"),
    ("requests", "requests"),
]

print("Python:", sys.version)
print("Runtime:", PY3_DIR)
print()

for distribution, module_name in packages:
    try:
        module = __import__(module_name)

        version = getattr(module, "__version__", None)

        print("{}:".format(distribution))
        print("  Version:", version or "<no __version__>")
        print("  Loaded:", getattr(module, "__file__", "<unknown>"))
        print()

    except Exception as exc:
        print("{}: ERROR: {}".format(distribution, exc))
        print()
