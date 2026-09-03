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

Where a tool previously stored settings elsewhere, migration must be backward-compatible: prefer copying the legacy file to the canonical location when the canonical file does not yet exist, and leave the legacy copy untouched during the migration period unless a tool-specific migration has a stronger validated contract.

### Local AnonGee machine/cache root

```text
%LOCALAPPDATA%\Zxaidman\AnonGee
```

Reserve this root for machine-specific or non-roaming AnonGee data such as caches, IPC/bridge state, generated temporary working data that must persist beyond one process, diagnostic state, or similar data.

Current known child directories include:

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\bridge
```

The RC Automation Excel/Revit bridge uses this directory for its `outbox`, `inbox`, startup diagnostics, and other local IPC state. `ANONGEE_BRIDGE_HOME` remains the highest-priority explicit override for development or managed deployments.

Bridge migration from the legacy `%APPDATA%\AnonGee\bridge` location is deliberately stricter than preference-file migration because the bridge contains executable IPC state:

- completed inbox/result files are passive records and can be moved best-effort; a cross-volume move may safely fall back to copy-then-remove;
- queued `*.job.json` files are **never copied**. They are moved only by an atomic rename. If roaming and local profiles are on different volumes and the rename cannot succeed, the queued file stays in the legacy outbox and the current listener claims it there in place;
- `*.running.json`, partial writes, and unknown files are never moved automatically because another Revit session may still own them;
- if canonical state already accounts for the same job id, the old queued file is made non-runnable and retained as migration-conflict evidence rather than being executed again;
- a migration failure must never stop the pyRevit extension from loading.

These rules are specifically intended to prevent an upgrade from creating two runnable copies of one Revit command.

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
%APPDATA%\AnonGee\bridge
```

CAD2BIM and AutoLevel perform best-effort first-use migration into the canonical roaming directory while retaining their legacy files during the migration period.

The RC Automation bridge is different: it contains live IPC/runtime state rather than roaming preferences. Its canonical destination is therefore:

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\bridge
```

The bridge activates this canonical location for the current Revit process when no explicit `ANONGEE_BRIDGE_HOME` is configured. Legacy state is then reconciled under the IPC safety rules above. `%APPDATA%\AnonGee\bridge` remains the fallback when `LOCALAPPDATA` is unavailable.

## Paths that should not be rewritten merely for consistency

A tool may inspect `%APPDATA%`, `%LOCALAPPDATA%`, `%PATH%`, `PYTHONPATH`, pyRevit engine directories, or Python installation directories for legitimate discovery purposes. Those are **lookup paths**, not automatically AnonGee-owned storage.

Do not redirect such discovery logic into the AnonGee folders unless the tool is explicitly being redesigned. The BBS Generator and Export Schedule are already configured to prefer AnonGee's bundled `AnonGee.extension\lib\py3` runtime for `openpyxl`; standalone Python is not a deployment prerequisite.

Third-party libraries may also use the operating system temporary directory internally. Do not patch vendored libraries simply to force their temporary files under the AnonGee local-data root.

## Design rules for new tools

1. User preferences and small user configuration → `%APPDATA%\Zxaidman\AnonGee\BIM-Toolkit`.
2. Machine-specific cache, IPC, logs, or persistent temporary state → a suitable child of `%LOCALAPPDATA%\Zxaidman\AnonGee`.
3. Installer/uninstaller support files → `%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit` while the current installer architecture remains in use.
4. pyRevit extension code/runtime → `%APPDATA%\pyRevit\Extensions\AnonGee.extension`.
5. Never hard-code a developer machine path.
6. Existing working paths must be migrated defensively rather than abruptly replaced.
7. Do not delete legacy user data automatically unless a later release defines and validates a specific cleanup policy.
8. Executable IPC state must never be copied during migration merely for convenience.

## Future standalone Revit add-in

If AnonGee later stops using pyRevit and becomes a native C#/Python Revit add-in, the pyRevit-specific extension path can be retired without changing the vendor/user-data hierarchy defined above. A future installer milestone should define the native add-in installation location separately while preserving roaming and local AnonGee data where practical.
