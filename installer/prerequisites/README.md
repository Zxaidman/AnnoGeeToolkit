# AnonGee Installer Prerequisites

This directory contains **local build inputs** for the AnonGee Toolkit Setup.
Third-party executable installers are deliberately excluded from Git by
`.gitignore`; they must be obtained from their official publisher and staged
locally before compiling a release.

## pyRevit — milestone 0.4.0

Required local file:

```text
installer/prerequisites/pyrevit/pyRevit_6.5.5.26237_signed.exe
```

Contract:

- Publisher: pyRevitLabs
- Product: pyRevit
- Pinned prerequisite version: 6.5.5.26237
- Installer type: official signed **per-user** installer
- AnonGee compatibility version used after install: 6.5.5
- Standalone Python: not required
- License: pyRevit remains a separate GPLv3-licensed third-party project

Do not rename a different pyRevit release to this filename. When the pinned
prerequisite changes, update the Inno Setup constants, this document, the
compatibility policy, and `installer/legal/THIRD_PARTY_NOTICES.txt` together.

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

Before a production build, record the file's SHA-256 hash locally, for example:

```powershell
Get-FileHash ".\installer\prerequisites\pyrevit\pyRevit_6.5.5.26237_signed.exe" -Algorithm SHA256
```

A later hardening milestone should pin that SHA-256 in the build pipeline so a
wrong or replaced prerequisite cannot be embedded accidentally.

## 0.4.0 behavior

AnonGee Setup should:

1. Leave an existing compatible pyRevit installation unchanged.
2. Leave a newer unvalidated 6.x installation unchanged and use the existing
   warning/opt-in policy.
3. Automatically install pyRevit 6.5.5 when pyRevit is missing.
4. Automatically repair/upgrade an incompatible **per-user** pyRevit version
   when safe to do so.
5. Refuse to modify an incompatible **all-users** pyRevit installation and
   direct the user to their BIM/IT administrator.
6. Never install standalone Python as an AnonGee prerequisite.

The prerequisite must complete successfully and be re-detected as compatible
before AnonGee's extension payload is installed.
