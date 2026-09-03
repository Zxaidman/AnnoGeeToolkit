# AnonGee Filesystem Path Contract

Status: **Canonical**  
Applies from: installer/path migration after milestone 0.3.0

This document defines where AnonGee-owned files belong on Windows. New tools and branches should follow this layout unless a documented compatibility requirement says otherwise.

## Canonical paths

### Installer-owned application/support files

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit
```

Use for files owned by the AnonGee installer itself, including the Inno uninstaller, installed legal notices, installer icon assets, and similar machine-local support files.

This directory is **not** the pyRevit extension directory and is **not** intended for roaming user preferences.

### Roaming AnonGee BIM Toolkit user data

```text
%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit
```

Use for small user-specific settings that should follow the user profile where Windows roaming profiles are enabled.

Current known files include:

```text
%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit\cad2bim.json
%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit\autolevel_settings.json
```

Where a tool previously stored settings elsewhere, migration must be backward-compatible: prefer copying the legacy file to the canonical location when the canonical file does not yet exist, and leave the legacy copy untouched during the migration period.

### Local AnonGee machine/cache root

```text
%LOCALAPPDATA%\Zxaidman\AnonGee
```

Reserve this root for machine-specific or non-roaming AnonGee data such as caches, IPC/bridge state, generated temporary working data that must persist beyond one process, diagnostic state, or similar data.

Sub-tools should normally use their own child directory rather than writing directly into the root.

### pyRevit extension payload

```text
%APPDATA%\pyRevit\Extensions\AnonGee.extension
```

This location is controlled by pyRevit's extension-discovery contract. Do not move it into the AnonGee vendor folders while AnonGee is distributed as a pyRevit extension.

The bundled CPython runtime remains relative to the extension at:

```text
AnonGee.extension\lib\py3
```

That path is an existing compatibility boundary and must not be casually restructured.

## Legacy locations

Historical builds may have created:

```text
%APPDATA%\AnonGee\cad2bim.json
%APPDATA%\AnonGee\autolevel_settings.json
```

CAD2BIM and AutoLevel now perform best-effort first-use migration from those files into the canonical roaming directory. Legacy files are intentionally left intact for rollback during the migration period.

The following path is **not owned by the CAD2BIM branch migration**:

```text
%APPDATA%\AnonGee\bridge
```

That folder belongs to work originating from the separate `pushbutton/rc-automation` branch. Its owner must be inspected on that branch before any relocation. If it is confirmed to contain local IPC/cache/runtime state, the expected future destination is under:

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\...
```

but this document does not authorize moving it yet.

## Paths that should not be rewritten merely for consistency

A tool may inspect `%APPDATA%`, `%LOCALAPPDATA%`, `%PATH%`, `PYTHONPATH`, pyRevit engine directories, or Python installation directories in order to discover external dependencies. Those are **lookup paths**, not AnonGee-owned storage.

Do not redirect such discovery logic into the AnonGee folders unless the tool is explicitly being redesigned. For example, the current BBS Generator searches pyReVit/Python installation locations for `openpyxl`; this path contract does not change that behavior.

Third-party libraries may also use the operating system temporary directory internally. Do not patch vendored libraries simply to force their temporary files under the AnonGee local-data root.

## Design rules for new tools

1. User preferences and small user configuration → `%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit`.
2. Machine-specific cache, IPC, logs, or persistent temporary state → a suitable child of `%LOCALAPPDATA%\Zxaidman\AnonGee`.
3. Installer/uninstaller support files → `%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit` while the current installer architecture remains in use.
4. pyRevit extension code/runtime → `%APPDATA%\pyRevit\Extensions\AnonGee.extension`.
5. Never hard-code a developer machine path.
6. Existing working paths must be migrated defensively rather than abruptly replaced.
7. Do not delete legacy user data automatically unless a later release defines and validates a specific cleanup policy.

## Future standalone Revit add-in

If AnonGee later stops using pyRevit and becomes a native C#/Python Revit add-in, the pyRevit-specific extension path can be retired without changing the vendor/user-data hierarchy defined above. A future installer milestone should define the native add-in installation location separately while preserving roaming and local AnonGee data where practical.
