# AnonGee BIM Tools — pyRevit Extension for Autodesk Revit

A professional suite of structural and architectural BIM automation tools for **Autodesk Revit**, currently delivered through the **pyRevit** framework. The current packaged installer target is **Autodesk Revit 2025 on native Windows x64**. End users do not need a standalone Python installation because the tested CPython dependencies are bundled inside the extension.

> **Source status:** This repository is private and proprietary. Repository access does not grant redistribution, resale, sublicensing, or source-publication rights. See [LICENSE](LICENSE), [RELICENSING_NOTICE.md](RELICENSING_NOTICE.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

![Revit](https://img.shields.io/badge/Autodesk%20Revit-2025-blue)
![pyRevit](https://img.shields.io/badge/pyRevit-6.1.x--6.3.x%20%7C%206.5.x-brightgreen)
![Python](https://img.shields.io/badge/Python-CPython%203.12-yellow)
![License](https://img.shields.io/badge/License-Proprietary-red)

---

## ✨ Tools Overview

The extension adds an **AnonGee** tab to the Revit ribbon with four panels and 29 tools.

### 🟢 Essential Panel

Everyday modelling and clean-up work.

**Auto Level Manager** *(v2.0.0 · [changelog](AnonGee.extension/AnonGee.tab/Essential.panel/AutoLevel.pushbutton/CHANGELOG.md))*

| Tool | Description |
| --- | --- |
| **Auto Level Manager** | Every level in the model from one **modeless** window — Revit stays interactive while it is open. Reads level marks out of drawing text ("FFL +3.500", "TOS -1.200", "TERRACE +14'-6\"") from the active view, the Revit selection, a DXF, or a paste box; infers the drawing's unit from the storey heights and cross-checks each text against where it sits on the sheet. Adds, renames, re-spaces and deletes levels. The stack is drawn to scale and editable in place — click to select, drag to move, double-click to rename, wheel to zoom. Undo/redo over staged changes; nothing reaches the model until Apply, which lands as one undo step. |

**StrucBIM** — structural slabs and setting-out

| Tool | Description |
| --- | --- |
| **Round Element Dist** | Check element distances against one correct datum element or point and round them to a design value. Reports every deviation first; you approve each fix before anything moves. Skips pinned, grouped and linked elements. |
| **Draw Floor** | Click inside a closed region formed by structural framing and columns in a plan view; a structural floor or foundation slab is created with its boundary on the **inner faces** of those elements. Pick a type, click regions, repeat. |
| **Convert Slab** | Convert Structural Floor ⇄ Structural Foundation (slab). Works on a pre-selection or lets you pick in plan, 3D, section or elevation, and shows a pre-flight list of every element with its resolved target type before committing. |

**Bulk Tool** — model-wide clean-up

| Tool | Description |
| --- | --- |
| **Bulk Delete** | Bulk-delete **Fill Patterns**, **Line Patterns** or **Line Styles**. Search and tick what to remove, with All / None helpers. |
| **Bulk Rename** | Bulk find-and-replace across all **Fill Pattern**, **Line Pattern** or **Line Style** names. |
| **Obscured Rebar** | Set rebars as Unobscured and Solid across selected views. Uses the pre-selection if there is one, otherwise every rebar in the document. |
| **Copy Rebar Visibility** | Copy rebar visibility from one view to many: hidden/unhidden state, the Unobscured flag, and the Solid flag for 3D → 3D pairs. |

**Action** — annotation and placement

| Tool | Description |
| --- | --- |
| **AutoDIM** | *Self Dimension.* Dimension a selected element's own extents, measured along the element's **own** orientation, on whichever axes lie in the active view's plane. Placement is tuned per category so dimensions stay clear of the geometry. |
| **Export Schedule** | Export Revit schedules to a single Excel workbook (`.xlsx`) with borders, fonts and header styling. Lists every project schedule with checkboxes. |
| **Rotate Column** | Rotate selected columns sequentially by a dynamically calculated step angle. Pure Revit API through Python.NET. |

**Modify** — joins and link visibility

| Tool | Description |
| --- | --- |
| **Join Priority** | Enforce a category-based join order on selected elements, so higher-priority categories cut lower-priority ones. |
| **Unjoin by Category** | Unjoin the selected elements from everything they are joined to in the categories you choose. |
| **Toggle Linked** | Toggle the visibility of linked Revit categories in the current view. |

### 🔵 Advance Panel

Parameter work across many elements, always with a preview before anything is written.

| Tool | Description |
| --- | --- |
| **One Filter Parameter** | Filter elements by a single parameter condition, preview the matches in a table, then batch-change a parameter on everything that passes (Set / Prefix / Suffix / Replace / Delete). |
| **Multi Filter Parameter** | Filter by multiple parameter conditions (All / Any logic), then batch-edit a parameter on everything that matches. |
| **Parameter Combination** | Write a value into a target parameter across model elements, built from one of four operations, with a live per-element preview before you apply. |

### 🔴 Core Panel

Build a model from an external source.

| Tool | Description |
| --- | --- |
| **BIM Generation** | Build a structural Revit model from a PLANWIN / FRAMEWIN **INP** file. Creates levels, structural columns, beams and floors with auto-sized type duplicates. |
| **FramewinToBIM** | Generate a structural RC frame (columns / beams / slabs) from FRAMEWIN data. |
| **cad2bim** | Pick a **DXF**, link it with unit and positioning settings, then build Revit grids, columns, beams, slabs and stairs from it. Hybrid extraction — the Revit link's geometry plus ezdxf for geometry and text — with layer classification and size refinement from text marks ("C1 400x400"). |
| **CAD QA** *(v1.0.0)* | Check a structural **DXF before** converting it. Reads the drawing the way cad2bim reads it — same reader, same layer classifier, same mark grammar — and reports every place that reading will produce a wrong or incomplete model: layers it cannot classify, size labels it cannot parse, outlines that do not close, storeys that will land on top of each other. 28 rules in four families, graded Error / Warning / Info. Advisory: no model is opened, nothing is written, no undo step is left. Writes a JSON report (the format the later cross-checkers read) and an `.xlsx` workbook beside the drawing. Also runs with no Revit at all: `python -m cad_qa plan.dxf`. |

### 🟠 Dev Panel

Generators, the design system, and the reference patterns new tools are built from.

| Tool | Description |
| --- | --- |
| **BBS Generator** | **Bar Bending Schedule** generator. Reads native `DB.Rebar` elements and exports formatted Excel workbooks (BBS, Calculation, Summary sheets). Supports **IS 2502:2019**, **BS 8666:2020** and **ACI 318-19 / CRSI**, with revision tracking. |
| **Brand Guidelines** | Living component gallery for the design system — brand colours, typography, buttons, inputs, selection controls, lists and status badges, exactly as they render inside Revit. |
| **Bridge Check** | Asks the AnonGee Bridge whether it is running, from inside Revit, and reports what answered. |
| **Bridge Listener** | The half of the bridge that does the work: a small modeless window that watches for bridge jobs and runs them on Revit's own thread, showing what it is doing. |
| **CPython3 engine** | Engine health check. Reports whether the CPython 3 engine is a fresh load or a reused instance (and how many runs this session), which third-party libraries resolve, and whether the Revit API bridge responds. |
| **Create Button** | Scaffold a new pyRevit pushbutton: collects the tab / panel / group / metadata in a brand-themed dialog, writes the folder, script, icon and `bundle.yaml`, then asks pyRevit to reload. |
| **Extract Template** | Writes everything the open model contains to a Markdown file, so a `.rvt` can be read, diffed and discussed by anyone who does not have Revit open. |
| **Modeless Window** | Reference implementation of the modeless (non-blocking) window pattern — `window.Show()`, an `IExternalEventHandler` bridge marshalling every Revit call onto Revit's primary thread, and the session-state rules that go with it. |
| **RC Automation** | Reads an Excel reinforcement schedule, checks it, works out what every existing footing would become, and reconciles the workbook against the model before a transaction is opened. Held to the same **BS 8666:2020** module the BBS Generator ships. |

---

## 🏷️ Versioning

The extension carries one version in `extension.json`, recorded in the [root changelog](CHANGELOG.md).

A tool that changes often enough for "which build am I running" to be a real question carries **its own version and its own changelog**, beside its `bundle.yaml`. Those move independently — `AnonGee BIM Tools 1.26.1` can ship `Auto Level Manager 2.0.0`, and neither number is wrong. The version shown in a tool's own window is the build actually running; quote it when reporting anything.

The installer/build pipeline also uses milestone versions independently from the user-facing AnonGee product version while the deployment system is being developed.

## 🎨 Design System

All tools use a **custom WPF design system** with:

- Brand color palette & theming (`Colors.xaml`, `AnonGeeTheme.xaml`)
- Reusable WPF controls (`Controls.xaml`)
- SVG/vector icons (`Icons.xaml`)
- Consistent typography (`Typography.xaml`)
- Panel layout templates (`Panels.xaml`)

Preview the full system in Revit via **AnonGee > Dev > Brand Guidelines**.

---

## 📦 Installation (End User)

AnonGee source code is not distributed through a public clone/download workflow.

### Current packaged prerequisites

- **Windows 10/11 native x64**
- **Autodesk Revit 2025**
- **pyRevit 6.1.x–6.3.x or 6.5.x**
- **pyRevit 6.4.x is not supported** because of reproduced CPython initialization failures
- **Standalone Python is not required** for end users

The current installer detects the supported environment before modifying the AnonGee installation. End users receive the packaged installer when they are entitled to use the Software under the applicable EULA.

### Licensing model

- **Personal non-commercial use:** may be used without charge under the packaged EULA.
- **Company, employer, client, professional, governmental, or organizational use:** requires an appropriate commercial license or written authorization.
- **Redistribution, resale, OEM distribution, sublicensing, and source access:** require a separate written agreement.

The exact rights for a particular packaged release are defined by the EULA supplied with that release.

> ✅ **No standalone Python installation or end-user pip setup is required.** The tested CPython runtime dependencies are bundled with the extension.

---

## 🛠️ Development (Approved Collaborators)

Development access is limited to approved collaborators. Access to this private repository does not by itself grant rights to publish, redistribute, sublicense, resell, or commercially exploit AnonGee source code.

Before making substantial human-authored contributions, review [CONTRIBUTING.md](CONTRIBUTING.md). Contributor/IP terms may be required before a contribution is accepted.

If you're modifying or extending the tools, use the controlled dependency workflow:

```bash
# From the repository root
cd tools
py -3.12 -m pip install -r requirements.txt
py -3.12 auto_provision.py
```

This builds the pinned CPython 3.12 runtime used by the extension. Release payloads are subsequently verified by `installer/build_payload.py` before installer compilation.

### Tests

Some tools keep their Revit-free logic in plain Python modules so it can be exercised without opening Revit. Run the applicable unit suite from the repository root using the project-standard Python environment.

`tests/test_repo_docs.py` holds this README and the [root changelog](CHANGELOG.md) to what is actually on the ribbon — every `.pushbutton` on disk has to be documented, every panel has to be declared in `extension.json`, and the changelog has to lead with the version `extension.json` states. `tests/test_autolevel.py` covers the Auto Level Manager's text detection, naming, plan model and stack-drawing camera. `tests/test_autolevel_ui.py` checks its XAML and Python wiring statically, against the delivery rules in §12.7–§12.9 of the brand guidelines and against the failures that are expensive to find inside Revit:

- every `FindName` lookup resolves and every named control is used;
- every `{Binding}` path has a matching `__slots__` entry;
- no `re`, no pyRevit imports, no `StaticResource` on the root `Window`;
- **no attribute value is mistaken for a markup extension** — a literal starting with `{` must be escaped `{}`, or `XamlReader.Load` throws and the window never opens;
- every `{StaticResource}` names a key that exists, no `x:Key` is defined twice, every `Style` matches the element it is applied to, and every trigger `TargetName` exists in its own template;
- every interactive control carries a tooltip;
- the tool's version agrees across `__init__.py`, `bundle.yaml`, `CHANGELOG.md` and the window header.

CAD2BIM additionally maintains a large regression corpus. Heavy CAD fixtures used only for development are excluded from packaged release payloads by `installer/build_payload.py`.

### Project Structure

```text
pyRevit-addons/
├── LICENSE                         # proprietary source license
├── RELICENSING_NOTICE.md           # historical GPL → proprietary transition
├── CONTRIBUTING.md                 # approved collaborator/IP policy
├── CHANGELOG.md                    # extension version history
├── README.md
├── extension.json                  # extension name, version, panel order
├── tests/                          # Revit-free tests
├── tools/                          # dependency provisioning
├── installer/                      # payload builder + Inno Setup sources
├── AnonGee_BIM_Tools_Brand_Guidelines.md
└── AnonGee.extension/
    ├── AnonGee.tab/                # Revit ribbon tab definition
    │   ├── Essential.panel/
    │   ├── Advance.panel/
    │   ├── Core.panel/
    │   └── Dev.panel/
    ├── lib/
    │   └── py3/                    # CPython 3.12 runtime + anongee_toolkit
    ├── Resources/                  # WPF design system
    │   ├── AnonGeeTheme.xaml
    │   ├── Colors.xaml
    │   ├── Controls.xaml
    │   ├── Icons.xaml
    │   ├── Panels.xaml
    │   └── Typography.xaml
    └── path_resolver.py
```

A tool bundle is a folder ending in `.pushbutton`, holding `bundle.yaml` (title, author, tooltip), `icon.png`, `script.py`, and — for anything with a window — a sibling `ui.xaml`. A tool with its own version adds a `CHANGELOG.md` and keeps its logic in a package beside the script, so the parts that do not touch Revit can be tested:

```text
AutoLevel.pushbutton/
├── bundle.yaml
├── CHANGELOG.md
├── icon.png
├── script.py
├── ui.xaml
└── anongee_autolevel/
```

---

## 📦 Installer / Release Pipeline

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

Generated payloads, installer outputs, and prerequisite executables are intentionally excluded from normal Git history.

---

## 🤝 Contributing

AnonGee Toolkit does **not** use an unrestricted public/open-source contribution model.

Only approved collaborators may contribute source code, and substantial human-authored contributions may require a contributor/IP agreement before acceptance. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 🧾 Third-Party Software

AnonGee Toolkit uses third-party software and libraries. Those components remain governed by their own licenses and do not become proprietary AnonGee code merely because they are bundled with or used by AnonGee.

The current dependency inventory is maintained in [`installer/legal/THIRD_PARTY_NOTICES.txt`](installer/legal/THIRD_PARTY_NOTICES.txt). Upstream LICENSE/COPYING/NOTICE files supplied with Python wheels and native libraries should be retained in release payloads where applicable.

pyRevit and Autodesk Revit are separate third-party products and are not owned by Zxaidman.

---

## 🪪 License

AnonGee Toolkit source code and original project materials are proprietary and are governed by [LICENSE](LICENSE).

Historical revisions that were available while GPLv3 licensing was present are addressed in [RELICENSING_NOTICE.md](RELICENSING_NOTICE.md). Rights validly granted for historical copies are not revoked by the later licensing change.

Packaged end-user releases are governed by the EULA supplied with the installer. Personal non-commercial use and commercial/organizational use are licensed differently.

Third-party components retain their respective licenses.

---

Copyright © 2026 Zxaidman. All rights reserved.
