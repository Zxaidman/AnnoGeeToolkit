# AnonGee Installer Prerequisites

This directory contains **local build inputs** for the AnonGee Toolkit Setup.
Third-party executable installers are deliberately excluded from Git by
`.gitignore`; they must be obtained from their official publisher and staged
locally before compiling a release.

## pyRevit prerequisite

Required local file:

```text
installer/prerequisites/pyrevit/pyRevit_6.5.5.26237_signed.exe
```

Pinned contract:

- Publisher: pyRevitLabs
- Product: pyRevit
- Pinned prerequisite version: 6.5.5.26237
- Installer type: official signed **per-user** installer
- AnonGee compatibility version used after install: 6.5.5
- AnonGee minimum compatibility metadata: 6.1.0
- SHA-256: `1e68bf525fce2e94d70f8e4f9d8a1d2489c86b1f7c79e75bbd65932d91d4a8d6`
- Standalone Python: not required
- License: pyRevit remains a separate GPLv3-licensed third-party project

Do not rename a different pyRevit release to this filename. Release pipeline
0.6.0 verifies the SHA-256 before payload generation or Inno Setup compilation,
so a wrong or replaced prerequisite is rejected before it can be embedded.

When the pinned prerequisite changes, update the installer compatibility policy,
`installer/build_release.py`, this document, and
`installer/legal/THIRD_PARTY_NOTICES.txt` together.

## Build preparation

From the repository root, the expected local layout is:

```text
installer/
└── prerequisites/
    └── pyrevit/
        └── pyRevit_6.5.5.26237_signed.exe
```

The executable is a build input only. It is embedded inside the generated
AnonGee Setup executable and is not committed to this repository.

You can independently verify the staged file with PowerShell:

```powershell
Get-FileHash ".\installer\prerequisites\pyrevit\pyRevit_6.5.5.26237_signed.exe" -Algorithm SHA256
```

Expected digest:

```text
1E68BF525FCE2E94D70F8E4F9D8A1D2489C86B1F7C79E75BBD65932D91D4A8D6
```

## Installer prerequisite behavior

AnonGee Setup:

1. Leaves an existing compatible pyRevit installation unchanged.
2. Leaves a newer unvalidated 6.x installation unchanged and uses the existing
   warning/opt-in policy.
3. Installs pyRevit 6.5.5 when pyRevit is missing.
4. Detects stale/incompatible **per-user** pyRevit registrations even when a
   compatible version is also present.
5. Requests explicit user consent before repairing an incompatible per-user
   installation.
6. On approval, runs each incompatible installation's Windows-registered
   uninstaller, verifies those registrations are gone, then installs/repairs
   pyRevit 6.5.5.
7. Refuses to modify an incompatible **all-users** pyRevit installation and
   directs the user to their BIM/IT administrator.
8. Never installs standalone Python as an AnonGee prerequisite.

The prerequisite must complete successfully and be re-detected as a clean
compatible pyRevit 6.5.5 environment before AnonGee's extension payload is
installed.

## Release pipeline 0.6.0

`installer/build_release.py` is the release-candidate orchestrator. It:

1. Requires Windows x64.
2. Requires a clean Git worktree by default.
3. Cross-checks the product version in `extension.json`, the newest root
   `CHANGELOG.md` heading, and `AnonGee.iss` `MyAppVersion`.
4. Checks that `extension.json` declares the validated pyRevit minimum of
   `6.1.0`; the special `6.4.x` exclusion remains enforced by Setup.
5. Requires installer milestone `0.6.0` and the pinned pyRevit compatibility
   contract.
6. Verifies the staged pyRevit filename and pinned SHA-256.
7. Locates and validates Inno Setup **7** `ISCC.exe`.
8. Runs the existing `installer/build_payload.py` verifier/builder with strict
   Git validation for release builds.
9. Compiles `installer/AnonGee.iss` through ISCC.
10. Refuses to accept a stale previous Setup EXE as a successful build.
11. Refuses to certify an artifact if the Git commit/worktree changes during
    the build.
12. Computes the final Setup EXE SHA-256 and size.
13. Writes `installer/output/release-manifest.json`, including a
    `release_ready` flag and the complete source/compiler/prerequisite/payload
    provenance.

Release-candidate build (clean source required):

```powershell
py -3.12 .\installer\build_release.py
```

Intentional development build from a dirty worktree:

```powershell
py -3.12 .\installer\build_release.py --allow-dirty
```

A dirty development artifact is explicitly marked `release_ready: false` and
must not be distributed as a release candidate.

If Inno Setup 7 is installed somewhere non-standard:

```powershell
py -3.12 .\installer\build_release.py --iscc "C:\Path\To\ISCC.exe"
```
