#define MyAppName "AnonGee-Toolkit"
#define MyAppVersion "0.1.0"
#define MyPublisher "Zxaidman"

[Setup]
; IMPORTANT:
; Never change this AppId between AnonGee versions.
AppId=Zxaidman.AnonGee.Toolkit

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}

; Keep Inno's uninstall files OUTSIDE the pyRevit extension.
DefaultDirName={localappdata}\Programs\Zxaidman\AnonGee Toolkit

DisableDirPage=yes
DisableProgramGroupPage=yes

; Per-user installation. No elevation required.
PrivilegesRequired=lowest

; Current AnonGee runtime is cp312-win_amd64.
; ARM64 is not supported/tested in v0.1.0.
SetupArchitecture=x64
ArchitecturesAllowed=x64os

WizardStyle=modern

Compression=lzma2
SolidCompression=yes

OutputDir=output
OutputBaseFilename=AnonGee-Setup-{#MyAppVersion}

UninstallDisplayName={#MyAppName}

VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyPublisher}
VersionInfoDescription={#MyAppName} Installer


[InstallDelete]
; AnonGee is an immutable application payload.
; Remove the previous version completely so stale Python
; packages, .pyd modules and removed pushbuttons cannot remain.
Type: filesandordirs; \
    Name: "{userappdata}\pyRevit\Extensions\AnonGee.extension"


[Files]
Source: "payload\AnonGee.extension\*"; \
    DestDir: "{userappdata}\pyRevit\Extensions\AnonGee.extension"; \
    Flags: ignoreversion recursesubdirs createallsubdirs


[UninstallDelete]
; Remove the installed extension when AnonGee is uninstalled.
Type: filesandordirs; \
    Name: "{userappdata}\pyRevit\Extensions\AnonGee.extension"