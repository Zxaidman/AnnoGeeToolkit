# AnonGee Installer Lifecycle

Installer milestone: **0.8.0**  
Release pipeline: **0.8.0**  
Lifecycle contract: **Implemented; 2.0.0 signed candidate proven; final upgrade/reinstall QA pending**  
Public Authenticode trust: **Deferred**

Milestone 0.8.0 makes install, same-version reinstall, upgrade, downgrade protection, uninstall, and release identity explicit contracts instead of relying on Inno Setup defaults or operator memory.

## Version semantics

AnonGee keeps these version streams separate:

| Contract | Current value | Meaning |
| --- | --- | --- |
| Product version | `2.0.0` | Next toolkit release candidate shown to users |
| Last published product version | `1.26.1` | Historical production floor; a formal new build must advance beyond it |
| Installer milestone | `0.8.0` | Installer behavior/QA contract |
| Base release pipeline | `0.8.0` | Unsigned build/verification orchestration |
| Signed release pipeline | `0.8.0` | Current integration of the proven 0.7 Authenticode capability |
| Base manifest schema | `1.2.0` | Unsigned release evidence format |
| Signed manifest schema | `1.4.0` | Authenticode release evidence format |

Product `2.0.0` is a MAJOR increment under this repository's existing SemVer policy because the Dev ribbon was reorganized and installation behavior changed. The root changelog explicitly classifies either a tab/ribbon reorganization or an installation-step change as a MAJOR extension change.

`extension.json`, the newest root `CHANGELOG.md` release heading, and `AnonGee.iss` `MyAppVersion` must always identify the same product version.

The release pipeline refuses to certify a production-named artifact whose product version is less than or equal to the last published product version. Self-signed test mode remains non-production even when it exercises a current candidate: its EXE is renamed with `-SELF-SIGNED-TEST` and its manifest is permanently `release_ready: false`.

## Stable install identity

The Inno Setup application identity remains:

```text
AppId=Zxaidman.AnonGee.Toolkit
DefaultDirName={localappdata}\Zxaidman\AnonGee\BIM-Toolkit
UsePreviousAppDir=no
DisableDirPage=yes
```

`AppId` must remain stable across upgrades. Inno derives the uninstall registration from this identity, so changing it would make a later installer a different application rather than the next AnonGee version.

The application directory is fixed and per-user. Setup does not inherit an arbitrary previous directory and does not ask the user to choose a different one.

## Explicit lifecycle mode detection

Release pipeline 0.8.0 compiles `installer/lifecycle-version.iss` into both unsigned and signed Setup builds. It reads the existing AnonGee Windows uninstall registration and compares its `DisplayVersion` with the candidate product version.

The modes are:

| Existing state | Candidate relationship | Setup behavior |
| --- | --- | --- |
| No AnonGee registration | — | `fresh-install`; caption says **Install** |
| Same product version installed | equal | `same-version-reinstall`; caption/dialog explicitly says **Reinstall** |
| Older AnonGee installed | candidate newer | `upgrade`; dialog names old and new versions |
| Newer AnonGee installed | candidate older | `blocked`; downgrade is refused before installation |
| Registration exists but version cannot be read/parsed | unknown | `blocked`; fail safe rather than guess |

Each path writes a `[LIFECYCLE] mode=...` entry to the Inno log.

### Legacy installer limitation

The archived official `1.26.1` Setup predates the 0.8 downgrade guard. It is immutable historical evidence and cannot be retroactively taught the new rule.

Therefore:

- use archived `1.26.1` only as the **starting point** for forward-upgrade QA;
- do not run archived `1.26.1` over an installed `2.0.0` except as an intentional legacy-risk experiment;
- downgrade blocking is guaranteed only by installers built with the 0.8 lifecycle overlay or later.

This is not a reason to modify or replace the historical `1.26.1` binary.

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

A signed build is different. The base verification stage remains:

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

The 0.8 workstation self-signed run confirmed the misleading intermediate `Release ready: YES` from the earlier 0.7 implementation is gone.

## Workstation QA status

The owner has exercised the current 0.8 / product 2.0.0 self-signed candidate end to end on Windows.

| Scenario | Status | Evidence / note |
| --- | --- | --- |
| 0.8 / 2.0.0 self-signed build + timestamp + `/pa` verification | **PASS** | final `release_ready: false` confirmed |
| Clean install | **PASS** | installer and toolkit loaded normally |
| Same-build reinstall, functional replacement | **PASS** | reinstall completed over existing copy |
| Same-version **explicit Reinstall UX** | **PENDING RETEST** | old candidate behaved like normal install; 0.8 lifecycle overlay now adds explicit mode |
| Uninstall | **PASS** | normal uninstall worked |
| Bridge state preservation | **PASS** | survived tested lifecycle operations |
| pyRevit independence | **PASS** | remained installed/unchanged |
| Revit loads AnonGee after install/reinstall | **PASS** | confirmed by owner |
| Archived `1.26.1` → `2.0.0` upgrade | **PENDING** | this is now the remaining real forward-upgrade proof |
| `2.0.0` downgrade guard | **STATIC CONTRACT PROVEN; destructive workstation proof deferred** | archived 1.26.1 cannot prove a guard it predates |

Observed successful current 2.0.0 self-signed candidate:

```text
AnonGee-Setup-2.0.0-SELF-SIGNED-TEST.exe
Size:    110.75 MiB
SHA-256: 1e6278cec11142fc4275eba90d063dfb1dd506f27191238c5d628c3c1266df1e
Release ready: NO — self-signed local test only
SignTool /pa verification: PASS
```

This hash is test evidence only. The self-signed candidate is not a public release.

Earlier integrated 0.8 proof before the 2.0.0 candidate bump:

```text
AnonGee-Setup-1.26.1-SELF-SIGNED-TEST.exe
SHA-256: 5f94ec9c9e4bdfcc7162500737fa33fd2c1691c60eebf987ca384bd246972315
Release ready: NO — self-signed local test only
```

That earlier hash is also test evidence only, not the historical production `1.26.1` artifact.

## Final upgrade QA: archived 1.26.1 → 2.0.0

Use the archived official `1.26.1` installer as the baseline and the new self-signed `2.0.0` candidate as the upgrade.

Expected when launching `2.0.0` over `1.26.1`:

```text
AnonGee Toolkit upgrade detected.
Installed: 1.26.1
Upgrade to: 2.0.0
```

Then verify:

- Windows treats it as the same AnonGee application because `AppId` is unchanged;
- new extension payload replaces the old tree completely;
- removed/renamed pushbuttons from the old version do not remain;
- bridge state survives;
- pyRevit remains installed and unchanged;
- Revit loads the upgraded toolkit;
- Windows Installed Apps reports `2.0.0`.

Run the `2.0.0` candidate a second time. Expected mode is explicit same-version reinstall rather than a generic install.

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
- product candidate is newer than historical `1.26.1`;
- Setup explicitly classifies fresh install, same-version reinstall, upgrade, and blocked downgrade;
- formal release identity cannot reuse published product version `1.26.1`;
- self-signed test mode remains available without claiming a public release;
- signed builds cannot claim release readiness before signature verification;
- extension replacement/uninstall and bridge preservation are pinned as contracts.

Workstation side already proven:

- clean install;
- functional same-build reinstall;
- uninstall;
- bridge preservation;
- pyRevit preservation;
- Revit loading after install/reinstall;
- 0.8 integrated self-signed signing path;
- current `2.0.0` self-signed candidate build, timestamp, and Authenticode verification.

Remaining workstation gates:

- prove archived official `1.26.1` → `2.0.0` is reported and performed as an upgrade;
- run `2.0.0` again and prove explicit same-version reinstall UX;
- confirm Windows Installed Apps reports `2.0.0` and Revit loads the upgraded toolkit.

Do not mark milestone 0.8.0 fully workstation-complete until those final gates pass.
