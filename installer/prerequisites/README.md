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
- SHA-256: `1e68bf525fce2e94d70f8e4f9d8a1d2489c86b1f7c79e75bbd65932d91d4a8d6`
- Standalone Python: not required
- License: pyRevit remains a separate GPLv3-licensed third-party project

Do not rename a different pyRevit release to this filename. Release pipeline
0.5.0 verifies the SHA-256 before payload generation or Inno Setup compilation,
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

## Installer 0.4.0 behavior

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

## Release pipeline 0.5.0

`installer/build_release.py` is the release orchestrator. It:

1. Verifies Windows x64.
2. Reads the product/prerequisite contract from `AnonGee.iss`.
3. Verifies the staged pyRevit filename and pinned SHA-256.
4. Locates and validates Inno Setup **7** `ISCC.exe`.
5. Runs the existing `installer/build_payload.py` verifier/builder.
6. Compiles `installer/AnonGee.iss` through ISCC.
7. Refuses to accept a stale previous Setup EXE as a successful build.
8. Computes the final Setup EXE SHA-256 and size.
9. Writes `installer/output/release-manifest.json` containing source, compiler,
   prerequisite, payload-manifest, and final-artifact information.

Normal development build:

```powershell
py -3.12 .\installer\build_release.py
```

Formal clean-worktree release build:

```powershell
py -3.12 .\installer\build_release.py --strict-git
```

If Inno Setup 7 is installed somewhere non-standard:

```powershell
py -3.12 .\installer\build_release.py --iscc "C:\Path\To\ISCC.exe"
```
