# -*- coding: utf-8 -*-
"""Resolve AnonGee's bundled Python runtime for pyRevit scripts.

`lib/py3` is a deployment compatibility boundary.  Runtime dependencies must
come from the extension payload rather than an unrelated standalone Python or
another pyRevit installation on the workstation.
"""

import os
import sys


def update_paths():
    """Promote the engine-appropriate bundled package directory on ``sys.path``.

    Returns the absolute runtime directory when it exists, otherwise ``None``.
    Existing callers may ignore the return value; promoting an already-present
    path to index 0 prevents later search locations from taking precedence.
    """
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    subdir = "py3" if sys.version_info.major == 3 else "py2"
    target_package_dir = os.path.abspath(os.path.join(lib_dir, subdir))

    if not os.path.isdir(target_package_dir):
        return None

    # Remove duplicate/equivalent entries before inserting at highest priority.
    target_key = os.path.normcase(target_package_dir)
    retained = []
    for entry in sys.path:
        try:
            entry_key = os.path.normcase(os.path.abspath(entry))
        except (TypeError, ValueError, OSError):
            entry_key = None
        if entry_key != target_key:
            retained.append(entry)

    sys.path[:] = [target_package_dir] + retained
    return target_package_dir
