# AnonGee Installer Lifecycle

Installer milestone: **0.8.0**  
Release pipeline: **0.8.0**  
Lifecycle contract: **Implemented; workstation lifecycle QA pending**  
Public Authenticode trust: **Deferred**

Milestone 0.8.0 makes install, reinstall, upgrade, uninstall, and release identity explicit contracts instead of relying on Inno Setup defaults or operator memory.

## Version semantics

AnonGee keeps these version streams separate:

| Contract | Current value | Meaning |
| --- | --- | --- |
| Product version | `1.26.1` in source today | Toolkit release identity shown to users |
| Last published product version | `1.26.1` | A formal new build must advance beyond this value |
| Installer milestone | `0.8.0` | Installer behavior/QA contract |
| Base release pipeline | `0.8.0` | Unsiged build/verification orchestration |
| Signed release pipeline | `0.8.0` | Current integration of the proven 0.7 Authenticode capability |
| Base manifest schema | `1.2.0` | Unsiged release evidence format |
| Signed manifest schema | `1.4.0` | Authenticode release evidence format |

The repository intentionally does **not** bump the product version merely because installer engineering advanced. Before the next formal release, `extension.json`, the newest `CHANGELOG.md` release heading, and `AnonGee.iss` `MyAppVersion` must be bumped together to a version newer than `1.26.1`.

The release pipeline now refuses to certify a production-named artifact whose product version is less than or equal to the last published product version. Self-signed test mode is the only exception because its EXE is renamed with `-SELF-SIGNED-TEST` and its manifest is permanently `release_ready: false`.

## Stable install identity

The Inno Setup application identity remains:

```text
AppId=Zxaidman.AnonGee.Toolkit
DefaultDirName={localappdata}\Zxaidman\AnonGee\BIM-Toolkit
UsePreviousAppDir=no
DisableDirPage=yes
```

`AppId` must remain stable across upgrades. Changing it would make Windows/Inno treat a later installer as a different application instead of the same AnonGee installation.

The application directory is fixed and per-user. Setup does not inherit an arbitrary previous directory and does not ask the user to choose a different one.

## Managed paths and lifecycle policy

### Installed application support files

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit
```

This directory is owned by the installer. Inno Setup may replace/remove files it installed there during upgrade or uninstall.

### pyRevit extension payload

```text
%APPDATA%\pyRevit\Extensions\AnonGee.extension
```

This is an **immutable application payload**. Every install/reinstall/upgrade removes the previous complete extension tree before copying the new payload. This prevents stale pushbuttons, `.pyd` files, DLLs, packages, or renamed files from surviving an upgrade.

Uninstall removes the complete AnonGee extension tree.

### Bridge runtime state

```text
%LOCALAPPDATA%\Zxaidman\AnonGee\bridge
```

The bridge directory is intentionally **preserved** across install, reinstall, upgrade, and normal uninstall.

Reason: it is runtime IPC state and may contain queued, running, or result files owned by an Excel/Revit bridge session. Installer/uninstaller code must not delete that state blindly.

This is different from the immutable extension payload. Bridge cleanup is an explicit maintenance action only after Revit, Excel, and bridge listeners are fully closed.

Manual cleanup, when intentionally required:

```powershell
Remove-Item "$env:LOCALAPPDATA\Zxaidman\AnonGee\bridge" `
    -Recurse -Force
```

Do not run that command while a bridge client/listener is active.

### Revit and pyRevit

Revit and pyRevit are prerequisites, not AnonGee-owned application data.

Normal AnonGee uninstall must **not** uninstall or modify pyRevit. The installer may only perform the already-defined prerequisite repair flow during installation when the user explicitly approves repair of an incompatible per-user pyRevit installation.

## Release-readiness states

A base unsigned clean release may become `release_ready: true` only after its normal release verification succeeds.

A signed build is different. The base verification stage must remain:

```text
release_ready = false
```

while Authenticode is still pending.

For formal trusted signing, only successful final Authenticode verification may promote the manifest to:

```text
release_ready = true
release_readiness_reason = Authenticode signature and release verification passed
```

For self-signed local testing, final state remains:

```text
release_ready = false
release_readiness_reason = self-signed local test only
```

This removes the misleading intermediate `Release ready: YES` message previously seen during the 0.7 workstation self-signed test.

## Lifecycle QA matrix

The static repository contract is automated. The following workstation scenarios still require an intentional manual QA pass before 0.8.0 is considered fully workstation-proven.

### A. Clean install

Precondition:

- Revit 2025 installed and closed.
- Supported pyRevit installed, or allow Setup to provision the pinned prerequisite.
- No installed AnonGee extension/application files.

Expected:

- Setup completes without requiring elevation for normal per-user installation.
- `%APPDATA%\pyRevit\Extensions\AnonGee.extension` exists and matches the new payload.
- `%LOCALAPPDATA%\Zxaidman\AnonGee\BIM-Toolkit` exists.
- Start Menu launcher resolves to the detected Revit 2025 executable.
- Revit loads AnonGee successfully.

### B. Same-candidate reinstall

Expected:

- Existing `AnonGee.extension` is removed before the new extension payload is copied.
- A deliberately inserted stale file inside `AnonGee.extension` does not survive reinstall.
- Bridge runtime state/sentinel survives.
- pyRevit is left unchanged when already compatible.

### C. Upgrade from the archived 1.26.1 installer

Use the archived official `1.26.1` installer as the old installation and a future product version greater than `1.26.1` as the 0.8 candidate.

Expected:

- Windows treats the candidate as the same AnonGee application because `AppId` is unchanged.
- New extension payload replaces the old tree completely.
- Removed/renamed pushbuttons from the old version do not remain.
- Bridge state survives the upgrade.
- Revit loads the upgraded toolkit.
- Product version shown by Windows/Setup matches the new candidate version.

### D. Uninstall

Expected:

- Revit must be closed before uninstall continues.
- `AnonGee.extension` is removed.
- Installer-owned application support files are removed by Inno Setup.
- AnonGee Start Menu shortcut is removed.
- pyRevit remains installed and unchanged.
- `%LOCALAPPDATA%\Zxaidman\AnonGee\bridge` remains intact by policy.

## Bridge preservation sentinel for QA

Before reinstall/upgrade/uninstall QA, with Revit and Excel closed:

```powershell
$bridge = "$env:LOCALAPPDATA\Zxaidman\AnonGee\bridge"
New-Item -ItemType Directory -Force $bridge | Out-Null
$sentinel = Join-Path $bridge "lifecycle-0.8-preserve.test"
Set-Content -LiteralPath $sentinel -Value "preserve"
```

After the lifecycle operation:

```powershell
Test-Path $sentinel
```

Expected result:

```text
True
```

Remove the QA sentinel after testing:

```powershell
Remove-Item $sentinel -ErrorAction SilentlyContinue
```

## Definition of done for milestone 0.8.0

Repository side:

- installer milestone and release pipelines identify `0.8.0`;
- static lifecycle tests pass;
- formal release identity cannot reuse published product version `1.26.1`;
- self-signed test mode remains available without claiming a public release;
- signed builds cannot claim release readiness before signature verification;
- extension replacement/uninstall and bridge preservation are pinned as contracts.

Workstation side:

- clean install passes;
- same-candidate reinstall passes;
- upgrade from archived `1.26.1` to the next product version passes;
- uninstall passes;
- bridge preservation sentinel survives reinstall, upgrade, and uninstall;
- Revit loads the upgraded toolkit after install/upgrade.

Do not mark workstation lifecycle QA complete until those scenarios are actually executed on Windows.
