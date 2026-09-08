# AnonGee Installer Milestone 0.8.0 — Completion Record

Status: **Workstation-complete**  
Validated on: **2026-09-08**  
Product candidate: **2.0.0**  
Installer milestone: **0.8.0**  
Signed release pipeline: **0.8.0**

## Workstation evidence

The following milestone gates were exercised successfully on the Windows development workstation:

- static installer/signing/bridge contract suite: **48 tests passed**;
- self-signed `2.0.0` release candidate build: **PASS**;
- Inno Setup 7 compile: **PASS**;
- embedded uninstaller Authenticode signing: **PASS**;
- final Setup Authenticode signing: **PASS**;
- RFC 3161 timestamping: **PASS**;
- `signtool verify /pa /all /v`: **PASS**;
- final self-signed manifest remained `release_ready = false`;
- clean install: **PASS**;
- archived `1.26.1` → `2.0.0` upgrade classification: **PASS**;
- `2.0.0` → `2.0.0` same-version reinstall/repair classification: **PASS**;
- pyRevit remained installed and intact: **PASS**;
- bridge runtime state survived install/upgrade/reinstall: **PASS**;
- AnonGee loaded correctly in Revit after lifecycle operations: **PASS**;
- normal uninstall removes the AnonGee extension tree: **PASS**.

The upgrade dialog explicitly reported:

```text
AnonGee Toolkit upgrade detected.
Installed: 1.26.1
Upgrade to: 2.0.0
```

The same-version dialog explicitly reported that `AnonGee Toolkit 2.0.0` was already installed and that Setup would reinstall/repair the same version while preserving bridge runtime state and pyRevit.

## Proven self-signed candidate

```text
AnonGee-Setup-2.0.0-SELF-SIGNED-TEST.exe
Size:    110.75 MiB
SHA-256: 1e6278cec11142fc4275eba90d063dfb1dd506f27191238c5d628c3c1266df1e
release_ready = false
```

This is test evidence only. It is not a publicly trusted production release.

## QA note: stale extension files

A deliberately planted stale file was **not separately observed** during upgrade or same-version reinstall.

This is not recorded as a failed milestone gate because:

1. the installer contract statically pins complete removal of `%APPDATA%\pyRevit\Extensions\AnonGee.extension` in `[InstallDelete]` before payload copy;
2. the static lifecycle tests verify that replace-all contract; and
3. the workstation uninstall test physically confirmed that the managed extension tree is removable as intended.

If stronger destructive QA is desired later, place a temporary sentinel file inside the installed `AnonGee.extension` tree, rerun the current installer, and verify that the sentinel disappears. That is an optional additional proof, not required to reopen milestone 0.8.0.

## Deferred items

The following are intentionally outside milestone 0.8.0 completion:

- public-trust code signing;
- Microsoft SmartScreen reputation;
- a publicly trusted CA or managed signing-service identity;
- destructive proof using a legacy `1.26.1` installer as a downgrade attempt;
- broader production rollout validation beyond the current workstation.

## Conclusion

Installer milestone **0.8.0 is workstation-complete**. The release pipeline now has explicit install, upgrade, same-version reinstall, downgrade-blocking contract, bridge preservation, pyRevit independence, release-version safety, and integrated Authenticode validation.
