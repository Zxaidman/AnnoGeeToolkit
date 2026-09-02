#define MyAppName "AnonGee Toolkit"
#define MyAppVersion "0.1.0"
#define MyPublisher "Zxaidman"
#define InstallerMilestone "0.3.0"

[Setup]
AppId=Zxaidman.AnonGee.Toolkit
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={localappdata}\Zxaidman\AnonGee\BIM-Toolkit
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64os
MinVersion=10.0
WizardStyle=modern dynamic
DisableWelcomePage=no
SetupIconFile=assets\anongee-setup.ico
WizardImageFile=assets\wizard\welcome-light.png
WizardImageFileDynamicDark=assets\wizard\welcome-dark.png
WizardSmallImageFile=assets\wizard\small-light.png
WizardSmallImageFileDynamicDark=assets\wizard\small-dark.png
LicenseFile=legal\EULA.txt
InfoBeforeFile=legal\INSTALL_NOTES.txt
Compression=lzma2
SolidCompression=yes
OutputDir=output
OutputBaseFilename=AnonGee-Setup-{#MyAppVersion}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\assets\anongee-setup.ico
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyPublisher}
VersionInfoDescription={#MyAppName} Installer - prerequisite milestone {#InstallerMilestone}
CloseApplications=no
RestartApplications=no

[InstallDelete]
; AnonGee is an immutable application payload. Replace it completely
; so stale packages, .pyd files, DLLs, or removed pushbuttons cannot remain.
Type: filesandordirs; Name: "{userappdata}\pyRevit\Extensions\AnonGee.extension"

[Files]
Source: "payload\AnonGee.extension\*"; DestDir: "{userappdata}\pyRevit\Extensions\AnonGee.extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\anongee-setup.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "legal\EULA.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\INSTALL_NOTES.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}\legal"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\AnonGee Toolkit"; Filename: "{code:GetRevitExePath}"; WorkingDir: "{code:GetRevitInstallPath}"; IconFilename: "{app}\assets\anongee-setup.ico"; Comment: "Launch Autodesk Revit 2025 with AnonGee Toolkit installed"; AppUserModelID: "Zxaidman.AnonGee.Toolkit"; Flags: createonlyiffileexists

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\pyRevit\Extensions\AnonGee.extension"

[Code]

const
  CRLF = #13#10;

  Revit2025UninstallKey =
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' +
    '{7346B4A0-2500-0510-0000-705C0D862004}';

  Revit2025ProductKey =
    'SOFTWARE\Autodesk\Revit\Autodesk Revit 2025';

  WindowsUninstallKey =
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall';

var
  DetectedRevitPath: String;

  UserPyRevitFound: Boolean;
  UserPyRevitName: String;
  UserPyRevitVersionRaw: String;
  UserPyRevitInstallLocation: String;
  UserPyRevitMajor: Integer;
  UserPyRevitMinor: Integer;
  UserPyRevitPatch: Integer;

  MachinePyRevitFound: Boolean;
  MachinePyRevitName: String;
  MachinePyRevitVersionRaw: String;
  MachinePyRevitInstallLocation: String;
  MachinePyRevitMajor: Integer;
  MachinePyRevitMinor: Integer;
  MachinePyRevitPatch: Integer;

  DetectedPyRevitName: String;
  DetectedPyRevitVersionRaw: String;
  DetectedPyRevitInstallLocation: String;
  DetectedPyRevitScope: String;
  DetectedPyRevitMajor: Integer;
  DetectedPyRevitMinor: Integer;
  DetectedPyRevitPatch: Integer;

function IsDigitChar(const C: Char): Boolean;
begin
  Result := (C >= '0') and (C <= '9');
end;

function TryParseSemVer3(
  const VersionText: String;
  var Major, Minor, Patch: Integer
): Boolean;
var
  I: Integer;
  PartIndex: Integer;
  Token: String;
  Value: Integer;
begin
  Result := False;
  Major := 0;
  Minor := 0;
  Patch := 0;
  I := 1;
  PartIndex := 0;

  while (I <= Length(VersionText)) and (PartIndex < 3) do
  begin
    while (I <= Length(VersionText)) and
          (not IsDigitChar(VersionText[I])) do
      I := I + 1;

    if I > Length(VersionText) then
      Exit;

    Token := '';
    while (I <= Length(VersionText)) and IsDigitChar(VersionText[I]) do
    begin
      Token := Token + VersionText[I];
      I := I + 1;
    end;

    Value := StrToIntDef(Token, -1);
    if Value < 0 then
      Exit;

    if PartIndex = 0 then
      Major := Value
    else if PartIndex = 1 then
      Minor := Value
    else
      Patch := Value;

    PartIndex := PartIndex + 1;
  end;

  Result := PartIndex = 3;
end;

function CompareSemVer3(
  MajorA, MinorA, PatchA,
  MajorB, MinorB, PatchB: Integer
): Integer;
begin
  if MajorA < MajorB then
    Result := -1
  else if MajorA > MajorB then
    Result := 1
  else if MinorA < MinorB then
    Result := -1
  else if MinorA > MinorB then
    Result := 1
  else if PatchA < PatchB then
    Result := -1
  else if PatchA > PatchB then
    Result := 1
  else
    Result := 0;
end;

function SemVer3ToString(Major, Minor, Patch: Integer): String;
begin
  Result := IntToStr(Major) + '.' + IntToStr(Minor) + '.' + IntToStr(Patch);
end;

function IsPyRevitProductName(const DisplayName: String): Boolean;
var
  N: String;
begin
  N := LowerCase(Trim(DisplayName));

  // pyRevit CLI is a separate product and is not sufficient for AnonGee.
  Result := (Pos('pyrevit', N) = 1) and (Pos('cli', N) = 0);
end;

procedure ConsiderPyRevitCandidate(
  const ScopeName: String;
  const DisplayName: String;
  const VersionRaw: String;
  const InstallLocation: String;
  const RegistryPath: String
);
var
  Major: Integer;
  Minor: Integer;
  Patch: Integer;
  IsUserScope: Boolean;
  ShouldReplace: Boolean;
begin
  if not TryParseSemVer3(VersionRaw, Major, Minor, Patch) then
  begin
    Log(
      'Ignoring pyRevit-like registry entry with unreadable version: ' +
      DisplayName + ' | ' + VersionRaw + ' | ' + RegistryPath
    );
    Exit;
  end;

  IsUserScope := ScopeName = 'Per-user';
  ShouldReplace := False;

  Log(
    'Found pyRevit candidate: ' + DisplayName +
    ' | version=' + VersionRaw +
    ' | scope=' + ScopeName +
    ' | registry=' + RegistryPath
  );

  if IsUserScope then
  begin
    if not UserPyRevitFound then
      ShouldReplace := True
    else if CompareSemVer3(
      Major, Minor, Patch,
      UserPyRevitMajor, UserPyRevitMinor, UserPyRevitPatch
    ) > 0 then
      ShouldReplace := True;

    if ShouldReplace then
    begin
      UserPyRevitFound := True;
      UserPyRevitName := DisplayName;
      UserPyRevitVersionRaw := VersionRaw;
      UserPyRevitInstallLocation := InstallLocation;
      UserPyRevitMajor := Major;
      UserPyRevitMinor := Minor;
      UserPyRevitPatch := Patch;
    end;
  end
  else
  begin
    if not MachinePyRevitFound then
      ShouldReplace := True
    else if CompareSemVer3(
      Major, Minor, Patch,
      MachinePyRevitMajor, MachinePyRevitMinor, MachinePyRevitPatch
    ) > 0 then
      ShouldReplace := True;

    if ShouldReplace then
    begin
      MachinePyRevitFound := True;
      MachinePyRevitName := DisplayName;
      MachinePyRevitVersionRaw := VersionRaw;
      MachinePyRevitInstallLocation := InstallLocation;
      MachinePyRevitMajor := Major;
      MachinePyRevitMinor := Minor;
      MachinePyRevitPatch := Patch;
    end;
  end;
end;

procedure ScanPyRevitUninstallRoot(
  RootKey: HKEY;
  const ScopeName: String;
  const RegistryViewName: String
);
var
  SubKeys: TArrayOfString;
  I: Integer;
  KeyPath: String;
  DisplayName: String;
  DisplayVersion: String;
  InstallLocation: String;
begin
  if not RegGetSubkeyNames(RootKey, WindowsUninstallKey, SubKeys) then
  begin
    Log(
      'Could not enumerate uninstall registry: ' +
      ScopeName + ' / ' + RegistryViewName
    );
    Exit;
  end;

  for I := 0 to GetArrayLength(SubKeys) - 1 do
  begin
    KeyPath := WindowsUninstallKey + '\' + SubKeys[I];
    DisplayName := '';

    if RegQueryStringValue(RootKey, KeyPath, 'DisplayName', DisplayName) then
    begin
      if IsPyRevitProductName(DisplayName) then
      begin
        DisplayVersion := '';
        InstallLocation := '';

        if RegQueryStringValue(
          RootKey,
          KeyPath,
          'DisplayVersion',
          DisplayVersion
        ) then
        begin
          RegQueryStringValue(
            RootKey,
            KeyPath,
            'InstallLocation',
            InstallLocation
          );

          ConsiderPyRevitCandidate(
            ScopeName,
            DisplayName,
            DisplayVersion,
            InstallLocation,
            RegistryViewName + '\' + KeyPath
          );
        end
        else
        begin
          Log(
            'Ignoring pyRevit-like registry entry without DisplayVersion: ' +
            DisplayName + ' | ' + RegistryViewName + '\' + KeyPath
          );
        end;
      end;
    end;
  end;
end;

function DetectPyRevit: Boolean;
begin
  UserPyRevitFound := False;
  MachinePyRevitFound := False;

  // Search both registry views because pyRevit can be registered by
  // different installer technologies/builds.
  ScanPyRevitUninstallRoot(HKCU64, 'Per-user', 'HKCU64');
  ScanPyRevitUninstallRoot(HKCU32, 'Per-user', 'HKCU32');
  ScanPyRevitUninstallRoot(HKLM64, 'All-users', 'HKLM64');
  ScanPyRevitUninstallRoot(HKLM32, 'All-users', 'HKLM32');

  // Prefer current-user scope if both installations exist.
  if UserPyRevitFound then
  begin
    DetectedPyRevitName := UserPyRevitName;
    DetectedPyRevitVersionRaw := UserPyRevitVersionRaw;
    DetectedPyRevitInstallLocation := UserPyRevitInstallLocation;
    DetectedPyRevitScope := 'Per-user';
    DetectedPyRevitMajor := UserPyRevitMajor;
    DetectedPyRevitMinor := UserPyRevitMinor;
    DetectedPyRevitPatch := UserPyRevitPatch;

    if MachinePyRevitFound then
      Log(
        'Both per-user and all-users pyRevit installations were detected. ' +
        'Per-user is used for compatibility checks.'
      );

    Result := True;
    Exit;
  end;

  if MachinePyRevitFound then
  begin
    DetectedPyRevitName := MachinePyRevitName;
    DetectedPyRevitVersionRaw := MachinePyRevitVersionRaw;
    DetectedPyRevitInstallLocation := MachinePyRevitInstallLocation;
    DetectedPyRevitScope := 'All-users';
    DetectedPyRevitMajor := MachinePyRevitMajor;
    DetectedPyRevitMinor := MachinePyRevitMinor;
    DetectedPyRevitPatch := MachinePyRevitPatch;

    Log(
      'All-users pyRevit detected. Detection is supported; this scope ' +
      'remains an AnonGee QA item before 1.0.0.'
    );

    Result := True;
    Exit;
  end;

  Result := False;
end;

function DetectRevit2025(var RevitPath: String): Boolean;
var
  InstallLocation: String;
  CandidateExe: String;
begin
  Result := False;
  RevitPath := '';
  InstallLocation := '';

  // Primary: Autodesk Revit 2025 uninstall product registration.
  if RegKeyExists(HKLM64, Revit2025UninstallKey) then
  begin
    if not RegQueryStringValue(
      HKLM64,
      Revit2025UninstallKey,
      'InstallLocation',
      InstallLocation
    ) then
    begin
      RegQueryStringValue(
        HKLM64,
        Revit2025UninstallKey,
        'InstallationLocation',
        InstallLocation
      );
    end;

    if InstallLocation <> '' then
    begin
      CandidateExe := AddBackslash(InstallLocation) + 'Revit.exe';
      if FileExists(CandidateExe) then
      begin
        RevitPath := RemoveBackslashUnlessRoot(InstallLocation);
        Result := True;
        Exit;
      end;
    end;
  end;

  // Secondary: Autodesk product registry key plus executable validation.
  if RegKeyExists(HKLM64, Revit2025ProductKey) then
  begin
    CandidateExe :=
      ExpandConstant('{autopf64}\Autodesk\Revit 2025\Revit.exe');

    if FileExists(CandidateExe) then
    begin
      RevitPath := ExpandConstant('{autopf64}\Autodesk\Revit 2025');
      Result := True;
      Exit;
    end;
  end;

  // Final normal-install fallback.
  CandidateExe :=
    ExpandConstant('{autopf64}\Autodesk\Revit 2025\Revit.exe');

  if FileExists(CandidateExe) then
  begin
    RevitPath := ExpandConstant('{autopf64}\Autodesk\Revit 2025');
    Result := True;
  end;
end;

function GetRevitInstallPath(Param: String): String;
begin
  if DetectedRevitPath = '' then
    DetectRevit2025(DetectedRevitPath);

  Result := DetectedRevitPath;
end;

function GetRevitExePath(Param: String): String;
var
  RevitPath: String;
begin
  RevitPath := GetRevitInstallPath('');

  if RevitPath <> '' then
    Result := AddBackslash(RevitPath) + 'Revit.exe'
  else
    Result := '';
end;

function IsRevitRunning(var CheckSucceeded: Boolean): Boolean;
var
  ResultCode: Integer;
  Output: TExecOutput;
  I: Integer;
  Line: String;
begin
  Result := False;
  CheckSucceeded := False;

  try
    if ExecAndCaptureOutputWithNativeSysDir(
      'tasklist.exe',
      '/FI "IMAGENAME eq Revit.exe" /FO CSV /NH',
      '',
      SW_SHOWNORMAL,
      ewWaitUntilTerminated,
      ResultCode,
      Output
    ) then
    begin
      if (ResultCode = 0) and (not Output.Error) then
      begin
        CheckSucceeded := True;

        for I := 0 to GetArrayLength(Output.StdOut) - 1 do
        begin
          Line := LowerCase(Output.StdOut[I]);
          if Pos('revit.exe', Line) > 0 then
          begin
            Result := True;
            Exit;
          end;
        end;
      end
      else
      begin
        Log(
          'tasklist process check failed. Exit code=' +
          IntToStr(ResultCode)
        );
      end;
    end
    else
      Log('Could not execute tasklist.exe for Revit process detection.');
  except
    Log(
      'Exception while checking for Revit.exe: ' +
      GetExceptionMessage
    );
  end;
end;

function ConfirmUnvalidatedPyRevitVersion: Boolean;
var
  MessageText: String;
begin
  MessageText :=
    'AnonGee Toolkit detected pyRevit ' +
    SemVer3ToString(
      DetectedPyRevitMajor,
      DetectedPyRevitMinor,
      DetectedPyRevitPatch
    ) + '.' + CRLF + CRLF +
    'AnonGee has currently been validated through pyRevit 6.5.5. ' +
    'This newer 6.x version has not yet been validated.' + CRLF + CRLF +
    'You may continue, but if AnonGee or CPython behaves incorrectly, ' +
    'install a validated pyRevit version before reporting an AnonGee bug.' +
    CRLF + CRLF + 'Continue installation anyway?';

  if WizardSilent then
  begin
    Log(
      'Blocking silent installation: ' +
      'unvalidated newer pyRevit 6.x version.'
    );
    Result := False;
    Exit;
  end;

  Result :=
    MsgBox(
      MessageText,
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2
    ) = IDYES;
end;

function ValidatePyRevitCompatibility: Boolean;
var
  VersionCore: String;
begin
  Result := False;

  VersionCore :=
    SemVer3ToString(
      DetectedPyRevitMajor,
      DetectedPyRevitMinor,
      DetectedPyRevitPatch
    );

  if DetectedPyRevitMajor < 6 then
  begin
    MsgBox(
      'AnonGee Toolkit requires pyRevit 6.1.0 or newer within the ' +
      'supported 6.x compatibility policy.' + CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'Install a supported pyRevit version and run Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  if DetectedPyRevitMajor >= 7 then
  begin
    MsgBox(
      'AnonGee Toolkit has not been validated with pyRevit ' +
      IntToStr(DetectedPyRevitMajor) + '.x.' + CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'Installation has been blocked to protect the Revit environment.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  if CompareSemVer3(
    DetectedPyRevitMajor,
    DetectedPyRevitMinor,
    DetectedPyRevitPatch,
    6, 1, 0
  ) < 0 then
  begin
    MsgBox(
      'AnonGee Toolkit requires pyRevit 6.1.0 or newer.' +
      CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'Install a supported pyRevit version and run Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  // Known-bad family for AnonGee's CPython workload.
  if (DetectedPyRevitMajor = 6) and
     (DetectedPyRevitMinor = 4) then
  begin
    MsgBox(
      'pyRevit 6.4.x is not supported by AnonGee Toolkit.' +
      CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'The pyRevit 6.4.x line has known CPython initialization problems. ' +
      'Use pyRevit 6.1.x-6.3.x or 6.5.x instead, then run Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  // Validated compatibility contract:
  // 6.1.x-6.3.x -> allow
  // 6.4.x       -> block
  // 6.5.0-6.5.5 -> allow
  // >6.5.5 <7   -> warn + allow interactively
  if (DetectedPyRevitMajor = 6) and
     (DetectedPyRevitMinor <= 3) then
  begin
    Result := True;
    Exit;
  end;

  if (DetectedPyRevitMajor = 6) and
     (DetectedPyRevitMinor = 5) and
     (DetectedPyRevitPatch <= 5) then
  begin
    Result := True;
    Exit;
  end;

  if DetectedPyRevitMajor = 6 then
  begin
    Result := ConfirmUnvalidatedPyRevitVersion;
    Exit;
  end;
end;

function InitializeSetup: Boolean;
var
  ProcessCheckSucceeded: Boolean;
begin
  Result := False;

  Log('============================================================');
  Log('AnonGee Toolkit prerequisite preflight');
  Log('Installer milestone: {#InstallerMilestone}');
  Log('Product version: {#MyAppVersion}');
  Log('============================================================');

  // 1. Native x64 Windows.
  if not IsX64OS then
  begin
    MsgBox(
      'AnonGee Toolkit currently requires native x64 Windows.' +
      CRLF + CRLF +
      'Windows on ARM64 is not yet supported.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;
  Log('[PASS] Native x64 Windows detected.');

  // 2. Revit must not be running.
  if IsRevitRunning(ProcessCheckSucceeded) then
  begin
    MsgBox(
      'Autodesk Revit is currently running.' + CRLF + CRLF +
      'Save your work and close every Revit window before installing or ' +
      'upgrading AnonGee Toolkit.' + CRLF + CRLF +
      'Setup will exit without changing your AnonGee installation.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  if not ProcessCheckSucceeded then
  begin
    MsgBox(
      'AnonGee Setup could not safely verify whether Revit.exe is running.' +
      CRLF + CRLF +
      'No files have been changed. Close Revit and run Setup again.' +
      CRLF + CRLF +
      'If this continues, review the Setup log or contact your BIM/IT administrator.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;
  Log('[PASS] Revit.exe is not running.');

  // 3. Revit 2025 must exist and Revit.exe must be present.
  if not DetectRevit2025(DetectedRevitPath) then
  begin
    MsgBox(
      'Autodesk Revit 2025 was not detected.' + CRLF + CRLF +
      'AnonGee Toolkit milestone 0.3.0 supports Revit 2025 only.' +
      CRLF + CRLF +
      'Install or repair Autodesk Revit 2025, then run Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;
  Log('[PASS] Autodesk Revit 2025 detected at: ' + DetectedRevitPath);

  // 4-6. Detect pyRevit, scope, and version.
  if not DetectPyRevit then
  begin
    MsgBox(
      'pyRevit was not detected.' + CRLF + CRLF +
      'AnonGee Toolkit requires a compatible pyRevit installation.' + CRLF +
      'Standalone Python is NOT required.' + CRLF + CRLF +
      'Install pyRevit first, then run AnonGee Setup again.' +
      CRLF + CRLF +
      'Automatic pyRevit installation is intentionally deferred to a later milestone.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  Log(
    '[PASS] pyRevit detected: ' + DetectedPyRevitName +
    ' | version=' + DetectedPyRevitVersionRaw +
    ' | normalized=' +
    SemVer3ToString(
      DetectedPyRevitMajor,
      DetectedPyRevitMinor,
      DetectedPyRevitPatch
    ) +
    ' | scope=' + DetectedPyRevitScope
  );

  if DetectedPyRevitInstallLocation <> '' then
    Log(
      '       pyRevit install location: ' +
      DetectedPyRevitInstallLocation
    );

  // 7. Explicit compatibility policy.
  if not ValidatePyRevitCompatibility then
    Exit;
  Log('[PASS] pyRevit compatibility policy accepted.');

  // 8. Payload integrity stays a build-time responsibility of
  // build_payload.py 0.2.0. [Files] also fails compilation if absent.

  Log('============================================================');
  Log('AnonGee prerequisite preflight PASSED.');
  Log('Revit 2025 path: ' + DetectedRevitPath);
  Log(
    'pyRevit: ' +
    SemVer3ToString(
      DetectedPyRevitMajor,
      DetectedPyRevitMinor,
      DetectedPyRevitPatch
    ) +
    ' (' + DetectedPyRevitScope + ')'
  );
  Log('Standalone Python prerequisite: NOT REQUIRED');
  Log('============================================================');

  Result := True;
end;

function InitializeUninstall: Boolean;
var
  ProcessCheckSucceeded: Boolean;
begin
  Result := False;

  if IsRevitRunning(ProcessCheckSucceeded) then
  begin
    MsgBox(
      'Autodesk Revit is currently running.' + CRLF + CRLF +
      'Close every Revit window before uninstalling AnonGee Toolkit.' +
      CRLF + CRLF +
      'Uninstall has been cancelled and no AnonGee files were removed.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  if not ProcessCheckSucceeded then
  begin
    MsgBox(
      'AnonGee Uninstall could not safely verify whether Revit.exe is running.' +
      CRLF + CRLF +
      'No files have been removed. Close Revit and run Uninstall again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  Result := True;
end;
