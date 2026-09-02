# AnonGee BIM Tools — Revit Automation Toolkit

AnonGee Toolkit is a proprietary suite of structural and architectural BIM automation tools for Autodesk Revit, currently delivered through the pyRevit framework. The current packaged installer target is **Autodesk Revit 2025 on native Windows x64**. End users do not need a standalone Python installation because the tested CPython dependencies are bundled with the extension.

> **Source status:** This repository is private and proprietary. Repository access does not grant redistribution, resale, sublicensing, or source-code publication rights. See [LICENSE](LICENSE), [RELICENSING_NOTICE.md](RELICENSING_NOTICE.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

![Revit](https://img.shields.io/badge/Autodesk%20Revit-2025-blue)
![pyRevit](https://img.shields.io/badge/pyRevit-6.1.x--6.3.x%20%7C%206.5.x-brightgreen)
![Python](https://img.shields.io/badge/Python-CPython%203.12-yellow)
![License](https://img.shields.io/badge/License-Proprietary-red)

---

## Tools Overview

The extension adds an **AnonGee** tab to the Revit ribbon with four panels and a growing collection of automation tools.

### Essential Panel

Everyday modelling and clean-up work.

**Auto Level Manager** — manage project levels from one modeless window. Reads level marks from drawing text, selections, DXF input, or pasted text; previews proposed changes; and applies approved modifications to the Revit model.

**StrucBIM** — structural slab and setting-out tools, including element-distance checks, floor creation from bounded regions, and slab/foundation conversion.

**Bulk Tool** — bulk clean-up and rename tools for patterns, line styles, rebar visibility, and related model-wide operations.

**Action** — annotation and placement tools including self-dimensioning, schedule export, and column rotation.

**Modify** — join-priority, category unjoin, and linked-model visibility tools.

### Advance Panel

Parameter workflows for filtering, previewing, and batch-editing Revit element parameters.

### Core Panel

Model-generation tools from external sources, including FRAMEWIN/PLANWIN workflows and **CAD2BIM**, which reads DXF geometry and annotations to generate Revit grids, columns, beams, slabs, stairs, walls, and related structural content.

### Dev Panel

Development and reference tooling including BBS generation, the AnonGee design system, CPython engine health checks, pushbutton scaffolding, and modeless-window implementation patterns.

---

## Versioning

The extension carries its own version in `extension.json`, recorded in the root [CHANGELOG.md](CHANGELOG.md).

Individual tools that evolve independently may carry their own semantic version and changelog beside their bundle. Tool versions and the toolkit version therefore do not need to move together.

The installer/build pipeline also uses milestone versions independently from the user-facing AnonGee product version while the deployment system is being developed.

---

## Design System

AnonGee tools use a custom WPF design system with shared colors, typography, controls, icons, and panel patterns under `AnonGee.extension/Resources/`.

Preview the component system in Revit through **AnonGee > Dev > Brand Guidelines**.

---

## Supported Packaged Environment

The current production-target compatibility contract is intentionally narrow while the installer is being validated:

- **Windows 10/11 native x64**
- **Autodesk Revit 2025**
- **pyRevit 6.1.x–6.3.x or 6.5.x**
- **pyRevit 6.4.x is blocked** because of reproduced CPython initialization failures
- pyRevit versions newer than the validated 6.5.x range may require explicit compatibility validation
- **Standalone Python is not required for end users**

Support for additional Revit, pyRevit, Windows, or architecture combinations must be explicitly tested before being added to the supported contract.

---

## Installation — End Users

AnonGee source code is not distributed through a public clone/download workflow.

End users receive a packaged AnonGee installer when they are entitled to use the Software under the applicable End User License Agreement.

The installer places the extension into the current user's pyRevit Extensions directory and performs compatibility checks before modifying the installation.

### Licensing model

- **Personal non-commercial use:** may be permitted without charge under the packaged EULA.
- **Company, employer, client, professional, governmental, or organizational use:** requires an appropriate commercial license or written authorization.
- **Redistribution, resale, OEM distribution, sublicensing, and source access:** require a separate written agreement.

The exact rights for a particular release are defined by the EULA supplied with that release.

---

## Development — Approved Collaborators

Development access is limited to approved collaborators. Access to this private repository does not by itself grant rights to publish, redistribute, sublicense, or commercially exploit AnonGee source code.

Before making substantial human-authored contributions, review [CONTRIBUTING.md](CONTRIBUTING.md). Contributor/IP terms may be required before a contribution is accepted.

### Dependency provisioning

The controlled CPython runtime is built from pinned requirements. From the repository root, approved developers can use the project provisioning/build tooling rather than installing ad-hoc packages into the release payload.

```bash
cd tools
py -3.12 -m pip install -r requirements.txt
py -3.12 auto_provision.py
```

Runtime dependencies are bundled under `AnonGee.extension/lib/py3/` and are validated by the release payload builder before installer compilation.

### Tests

Revit-independent logic is covered by Python tests where practical. Run the applicable suite from the repository root using the project-standard Python environment.

CAD2BIM additionally maintains a large regression corpus. Heavy CAD fixtures used only for development are excluded from packaged release payloads by `installer/build_payload.py`.

---

## Installer / Release Pipeline

The current release flow is:

```text
Locally tested AnonGee.extension
        ↓
installer/build_payload.py
        ↓
validated installer/payload/AnonGee.extension
        ↓
Inno Setup compiler
        ↓
AnonGee-Setup-<version>.exe
```

`build_payload.py` verifies pinned dependency metadata, native `.pyd`/DLL content, key NumPy runtime files, release exclusions, Git source information, and payload integrity before the installer is compiled.

Generated payloads, build outputs, and prerequisite executables are intentionally excluded from normal Git history.

---

## Project Structure

```text
pyRevit-addons/
├── LICENSE                         # proprietary source license
├── RELICENSING_NOTICE.md           # historical GPL → proprietary transition
├── CONTRIBUTING.md                 # approved collaborator/IP policy
├── CHANGELOG.md
├── README.md
├── extension.json
├── AnonGee_BIM_Tools_Brand_Guidelines.md
│
├── tools/
│   ├── requirements.txt
│   ├── auto_provision.py
│   └── install_dependencies.bat
│
├── installer/
│   ├── AnonGee.iss
│   ├── build_payload.py
│   ├── legal/
│   │   ├── EULA.txt
│   │   ├── LICENSE.txt
│   │   ├── INSTALL_NOTES.txt
│   │   └── THIRD_PARTY_NOTICES.txt
│   ├── assets/
│   ├── prerequisites/
│   ├── payload/                    # generated / gitignored
│   └── output/                     # generated / gitignored
│
└── AnonGee.extension/
    ├── AnonGee.tab/
    │   ├── Essential.panel/
    │   ├── Advance.panel/
    │   ├── Core.panel/
    │   └── Dev.panel/
    ├── lib/
    │   └── py3/
    ├── Resources/
    └── path_resolver.py
```

---

## Third-Party Software

AnonGee Toolkit uses third-party open-source and proprietary-platform components. These components remain governed by their own licenses and are not converted into proprietary AnonGee code merely because they are bundled with or used by AnonGee.

The current packaged dependency inventory is maintained in:

`installer/legal/THIRD_PARTY_NOTICES.txt`

Third-party license files distributed inside Python wheel/package metadata must be retained in release payloads where applicable.

pyRevit and Autodesk Revit are separate third-party products and are not owned by Zxaidman.

---

## Contributing

AnonGee Toolkit does **not** accept unrestricted public/open-source contributions.

Only approved collaborators may contribute source code, and substantial human-authored contributions may require a contributor/IP agreement before acceptance. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

AnonGee Toolkit source code and original project materials are proprietary and are governed by [LICENSE](LICENSE).

Historical revisions that were available while GPLv3 licensing was present are addressed in [RELICENSING_NOTICE.md](RELICENSING_NOTICE.md). Rights validly granted for historical copies are not revoked by the later licensing change.

Packaged end-user releases are governed by the EULA supplied with the installer. Personal non-commercial use and commercial/organizational use are licensed differently.

Third-party components retain their respective licenses.

---

Copyright © 2026 Zxaidman. All rights reserved.
