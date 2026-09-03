#define MyAppName "AnonGee Toolkit"
#define MyAppVersion "1.1.0"
#define MyPublisher "Zxaidman"
#define InstallerMilestone "0.6.0"
#define PyRevitPrereqVersion "6.5.5.26237"
#define PyRevitPrereqCompatibilityVersion "6.5.5"
#define PyRevitPrereqFile "pyRevit_6.5.5.26237_signed.exe"

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
; Build-time prerequisite. The EXE is intentionally ignored by Git and must
; exist locally at compile time. dontcopy keeps it out of the installed app;
; it is extracted to {tmp} only when Setup actually needs pyRevit.
Source: "prerequisites\pyrevit\{#PyRevitPrereqFile}"; Flags: dontcopy noencryption

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

  PyRevitInstallRequired: Boolean;
  PyRevitCleanupRequired: Boolean;
  PyRevitInstallReason: String;
  IncompatibleUserPyRevitCount: Integer;
  IncompatibleUserPyRevitSummary: String;

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

function IsRepairIncompatiblePyRevitVersion(
  Major, Minor, Patch: Integer
): Boolean;
begin
  Result :=
    (Major < 6) or
    (CompareSemVer3(Major, Minor, Patch, 6, 1, 0) < 0) or
    ((Major = 6) and (Minor = 4));
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

  if IsUserScope and
     IsRepairIncompatiblePyRevitVersion(Major, Minor, Patch) then
  begin
    IncompatibleUserPyRevitCount := IncompatibleUserPyRevitCount + 1;
    if IncompatibleUserPyRevitSummary <> '' then
      IncompatibleUserPyRevitSummary := IncompatibleUserPyRevitSummary + ', ';
    IncompatibleUserPyRevitSummary :=
      IncompatibleUserPyRevitSummary + SemVer3ToString(Major, Minor, Patch);
  end;

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
  IncompatibleUserPyRevitCount := 0;
  IncompatibleUserPyRevitSummary := '';

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
      'remains an AnonGee QA item for broader production rollout.'
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

function SplitRegisteredCommand(
  const CommandLine: String;
  var FileName: String;
  var Params: String
): Boolean;
var
  S: String;
  EndQuote: Integer;
  FirstSpace: Integer;
begin
  Result := False;
  FileName := '';
  Params := '';
  S := Trim(CommandLine);

  if S = '' then
    Exit;

  if S[1] = '"' then
  begin
    Delete(S, 1, 1);
    EndQuote := Pos('"', S);
    if EndQuote = 0 then
      Exit;

    FileName := Copy(S, 1, EndQuote - 1);
    Params := Trim(Copy(S, EndQuote + 1, Length(S)));
  end
  else
  begin
    FirstSpace := Pos(' ', S);
    if FirstSpace = 0 then
      FileName := S
    else
    begin
      FileName := Copy(S, 1, FirstSpace - 1);
      Params := Trim(Copy(S, FirstSpace + 1, Length(S)));
    end;
  end;

  Result := FileName <> '';
end;

function RemoveIncompatiblePyRevitFromRoot(
  RootKey: HKEY;
  const RegistryViewName: String;
  var RemovedCount: Integer;
  var ErrorText: String
): Boolean;
var
  SubKeys: TArrayOfString;
  I: Integer;
  KeyPath: String;
  DisplayName: String;
  DisplayVersion: String;
  UninstallCommand: String;
  UninstallerExe: String;
  UninstallerParams: String;
  Major: Integer;
  Minor: Integer;
  Patch: Integer;
  ResultCode: Integer;
begin
  Result := False;

  if not RegKeyExists(RootKey, WindowsUninstallKey) then
  begin
    Result := True;
    Exit;
  end;

  if not RegGetSubkeyNames(RootKey, WindowsUninstallKey, SubKeys) then
  begin
    ErrorText :=
      'Could not enumerate the current-user uninstall registry (' +
      RegistryViewName + ').';
    Exit;
  end;

  for I := 0 to GetArrayLength(SubKeys) - 1 do
  begin
    KeyPath := WindowsUninstallKey + '\' + SubKeys[I];
    DisplayName := '';
    DisplayVersion := '';

    if RegQueryStringValue(RootKey, KeyPath, 'DisplayName', DisplayName) and
       IsPyRevitProductName(DisplayName) and
       RegQueryStringValue(RootKey, KeyPath, 'DisplayVersion', DisplayVersion) and
       TryParseSemVer3(DisplayVersion, Major, Minor, Patch) and
       IsRepairIncompatiblePyRevitVersion(Major, Minor, Patch) then
    begin
      UninstallCommand := '';
      if not RegQueryStringValue(
        RootKey,
        KeyPath,
        'UninstallString',
        UninstallCommand
      ) then
      begin
        ErrorText :=
          'AnonGee Setup found incompatible pyRevit ' +
          SemVer3ToString(Major, Minor, Patch) +
          ' but Windows did not provide its uninstall command.';
        Exit;
      end;

      if not SplitRegisteredCommand(
        UninstallCommand,
        UninstallerExe,
        UninstallerParams
      ) then
      begin
        ErrorText :=
          'AnonGee Setup could not read the registered uninstall command for ' +
          'pyRevit ' + SemVer3ToString(Major, Minor, Patch) + '.';
        Exit;
      end;

      if not FileExists(UninstallerExe) then
      begin
        ErrorText :=
          'The registered uninstaller for pyRevit ' +
          SemVer3ToString(Major, Minor, Patch) + ' is missing:' +
          CRLF + UninstallerExe;
        Exit;
      end;

      // All pyRevit desktop installers covered by this repair policy are
      // Inno Setup installers. Keep their uninstall progress visible while
      // suppressing confirmation/message boxes because the user already
      // approved the repair in the AnonGee wizard.
      if UninstallerParams <> '' then
        UninstallerParams := UninstallerParams + ' ';
      UninstallerParams :=
        UninstallerParams + '/SILENT /SUPPRESSMSGBOXES /NORESTART';

      Log(
        '[ACTION] Removing incompatible per-user pyRevit ' +
        SemVer3ToString(Major, Minor, Patch) +
        ' using registered uninstaller: ' + UninstallerExe
      );

      if not Exec(
        UninstallerExe,
        UninstallerParams,
        '',
        SW_SHOWNORMAL,
        ewWaitUntilTerminated,
        ResultCode
      ) then
      begin
        ErrorText :=
          'AnonGee Setup could not start the registered uninstaller for ' +
          'pyRevit ' + SemVer3ToString(Major, Minor, Patch) + '.';
        Exit;
      end;

      if ResultCode <> 0 then
      begin
        ErrorText :=
          'The pyRevit ' + SemVer3ToString(Major, Minor, Patch) +
          ' uninstaller returned exit code ' + IntToStr(ResultCode) + '.';
        Exit;
      end;

      if RegKeyExists(RootKey, KeyPath) then
      begin
        ErrorText :=
          'pyRevit ' + SemVer3ToString(Major, Minor, Patch) +
          ' still appears in Windows after its uninstaller completed.';
        Exit;
      end;

      RemovedCount := RemovedCount + 1;
      Log(
        '[PASS] Removed incompatible per-user pyRevit ' +
        SemVer3ToString(Major, Minor, Patch)
      );
    end;
  end;

  Result := True;
end;

function RemoveIncompatiblePerUserPyRevit(
  var RemovedCount: Integer;
  var ErrorText: String
): Boolean;
begin
  Result := False;
  RemovedCount := 0;
  ErrorText := '';

  if not RemoveIncompatiblePyRevitFromRoot(
    HKCU64,
    'HKCU64',
    RemovedCount,
    ErrorText
  ) then
    Exit;

  if not RemoveIncompatiblePyRevitFromRoot(
    HKCU32,
    'HKCU32',
    RemovedCount,
    ErrorText
  ) then
    Exit;

  // Re-scan after uninstall. This also refreshes the selected candidate in
  // case a compatible pyRevit registration was already present beside the old
  // one. We still reinstall 6.5.5 afterward because the old and new pyRevit
  // products can share %APPDATA%\pyRevit-Master and the old uninstaller may
  // legitimately remove files currently used by the newer registration.
  DetectPyRevit;

  if IncompatibleUserPyRevitCount > 0 then
  begin
    ErrorText :=
      'One or more incompatible per-user pyRevit installations are still ' +
      'registered after cleanup: ' + IncompatibleUserPyRevitSummary + '.';
    Exit;
  end;

  Result := True;
end;

procedure MarkPyRevitForInstall(const Reason: String);
begin
  PyRevitInstallRequired := True;
  PyRevitInstallReason := Reason;
  Log('[ACTION] Bundled pyRevit {#PyRevitPrereqCompatibilityVersion} prerequisite required: ' + Reason);
end;

function ConfirmPerUserPyRevitRepair(const VersionSummary: String): Boolean;
var
  MessageText: String;
begin
  Result := False;

  if WizardSilent then
  begin
    Log(
      'Blocking silent installation: incompatible existing per-user pyRevit ' +
      VersionSummary + ' requires explicit repair consent.'
    );
    Exit;
  end;

  MessageText :=
    'AnonGee Toolkit detected incompatible per-user pyRevit installation(s).' +
    CRLF + CRLF +
    'Detected incompatible version(s): ' + VersionSummary + CRLF +
    'Required repair version: pyRevit {#PyRevitPrereqCompatibilityVersion}' +
    CRLF + CRLF +
    'To avoid multiple pyRevit versions conflicting inside Revit, Setup will ' +
    'first uninstall the incompatible per-user pyRevit installation(s), then ' +
    'install/repair pyRevit {#PyRevitPrereqCompatibilityVersion} using the ' +
    'bundled official signed installer.' + CRLF + CRLF +
    'Your AnonGee extension and roaming AnonGee settings are stored outside ' +
    'the pyRevit-Master application folder.' + CRLF + CRLF +
    'Yes: remove incompatible pyRevit, install 6.5.5, and continue.' + CRLF +
    'No: close AnonGee Setup without changing pyRevit or installing AnonGee.' +
    CRLF + CRLF +
    'Do you want Setup to repair pyRevit now?';

  if MsgBox(
    MessageText,
    mbConfirmation,
    MB_YESNO or MB_DEFBUTTON2
  ) = IDYES then
  begin
    PyRevitCleanupRequired := True;
    MarkPyRevitForInstall(
      'user approved cleanup/repair of incompatible per-user pyRevit ' +
      VersionSummary
    );
    Result := True;
  end
  else
    Log(
      '[CANCEL] User declined cleanup/repair of incompatible per-user pyRevit ' +
      VersionSummary + '. AnonGee Setup will close.'
    );
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
    'Setup will leave this newer pyRevit installation unchanged.' + CRLF + CRLF +
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

  // Never automatically downgrade a future major pyRevit release.
  if DetectedPyRevitMajor >= 7 then
  begin
    MsgBox(
      'AnonGee Toolkit has not been validated with pyRevit ' +
      IntToStr(DetectedPyRevitMajor) + '.x.' + CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'Setup will not downgrade this installation automatically.' +
      CRLF + CRLF +
      'Installation has been blocked to protect the Revit environment.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  if IsRepairIncompatiblePyRevitVersion(
    DetectedPyRevitMajor,
    DetectedPyRevitMinor,
    DetectedPyRevitPatch
  ) then
  begin
    if DetectedPyRevitScope = 'Per-user' then
    begin
      // The consent prompt is performed once in InitializeSetup after the
      // complete per-user scan, so it also catches stale side-by-side versions.
      Result := PyRevitCleanupRequired and PyRevitInstallRequired;
      Exit;
    end;

    MsgBox(
      'AnonGee Toolkit detected an incompatible all-users pyRevit installation.' +
      CRLF + CRLF +
      'Detected: pyRevit ' + VersionCore +
      ' (' + DetectedPyRevitScope + ')' + CRLF + CRLF +
      'AnonGee Setup is a per-user installer and will not modify an ' +
      'all-users pyRevit installation that may be managed by your company.' +
      CRLF + CRLF +
      'Ask your BIM/IT administrator to install a supported pyRevit version, ' +
      'then run AnonGee Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;

  // Compatibility contract:
  // 6.1.x-6.3.x -> allow unchanged
  // 6.4.x       -> per-user ask to purge+repair / all-users block
  // 6.5.0-6.5.5 -> allow unchanged
  // >6.5.5 <7   -> warn + allow unchanged interactively
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

function VerifyBundledPyRevitInstalled: Boolean;
begin
  Result := False;

  if not DetectPyRevit then
  begin
    Log('[FAIL] pyRevit was still not detectable after prerequisite Setup completed.');
    Exit;
  end;

  if IncompatibleUserPyRevitCount > 0 then
  begin
    Log(
      '[FAIL] Incompatible per-user pyRevit remains after repair: ' +
      IncompatibleUserPyRevitSummary
    );
    Exit;
  end;

  if (DetectedPyRevitMajor = 6) and
     (DetectedPyRevitMinor = 5) and
     (DetectedPyRevitPatch = 5) then
  begin
    Log(
      '[PASS] Bundled pyRevit prerequisite verified: ' +
      DetectedPyRevitVersionRaw + ' | scope=' + DetectedPyRevitScope
    );
    Result := True;
    Exit;
  end;

  Log(
    '[FAIL] Unexpected pyRevit after prerequisite Setup: ' +
    SemVer3ToString(
      DetectedPyRevitMajor,
      DetectedPyRevitMinor,
      DetectedPyRevitPatch
    ) + ' | raw=' + DetectedPyRevitVersionRaw +
    ' | scope=' + DetectedPyRevitScope
  );
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PrereqPath: String;
  Params: String;
  ResultCode: Integer;
  RemovedCount: Integer;
  CleanupError: String;
begin
  Result := '';
  NeedsRestart := False;

  if PyRevitCleanupRequired then
  begin
    Log('============================================================');
    Log('Removing incompatible per-user pyRevit before repair');
    Log('Detected version(s): ' + IncompatibleUserPyRevitSummary);
    Log('============================================================');

    if not RemoveIncompatiblePerUserPyRevit(RemovedCount, CleanupError) then
    begin
      Result :=
        'AnonGee Setup could not safely remove the incompatible per-user ' +
        'pyRevit installation.' + CRLF + CRLF + CleanupError + CRLF + CRLF +
        'AnonGee installation has been stopped. Resolve the pyRevit entry ' +
        'manually in Windows Installed Apps, then run AnonGee Setup again.';
      Log('[FAIL] pyRevit cleanup failed: ' + CleanupError);
      Exit;
    end;

    Log(
      '[PASS] Incompatible per-user pyRevit cleanup completed. Removed=' +
      IntToStr(RemovedCount)
    );
  end;

  if not PyRevitInstallRequired then
  begin
    Log('pyRevit prerequisite action: existing installation accepted; nothing to install.');
    Exit;
  end;

  Log('============================================================');
  Log('Installing bundled pyRevit prerequisite');
  Log('Version: {#PyRevitPrereqVersion}');
  Log('Reason: ' + PyRevitInstallReason);
  Log('============================================================');

  try
    ExtractTemporaryFile('{#PyRevitPrereqFile}');
  except
    Result :=
      'AnonGee Setup could not extract the bundled pyRevit prerequisite.' +
      CRLF + CRLF +
      'No AnonGee files have been installed. Rebuild or obtain a complete ' +
      'AnonGee Setup package and try again.';
    Log('[FAIL] ExtractTemporaryFile failed: ' + GetExceptionMessage);
    Exit;
  end;

  PrereqPath := ExpandConstant('{tmp}\{#PyRevitPrereqFile}');
  if not FileExists(PrereqPath) then
  begin
    Result :=
      'The bundled pyRevit prerequisite could not be found after extraction.' +
      CRLF + CRLF + 'AnonGee installation has been stopped.';
    Log('[FAIL] Extracted pyRevit prerequisite is missing: ' + PrereqPath);
    Exit;
  end;

  // pyRevit's official per-user installer is itself Inno Setup. /SILENT skips
  // its wizard but intentionally keeps its progress window visible so AnonGee
  // Setup never appears frozen while the prerequisite is being installed.
  // Install only the fixed Core component; AnonGee does not require pyRevit's
  // optional extended, developer, or tutorial extensions.
  Params :=
    '/SILENT /SUPPRESSMSGBOXES /NORESTART /SP- ' +
    '/COMPONENTS="core"';

  if not Exec(
    PrereqPath,
    Params,
    '',
    SW_SHOWNORMAL,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Result :=
      'AnonGee Setup could not start the bundled pyRevit installer.' +
      CRLF + CRLF +
      'No AnonGee files have been installed. Try again, or install ' +
      'pyRevit 6.5.5 manually before running AnonGee Setup.';
    Log('[FAIL] Could not execute pyRevit prerequisite.');
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    Result :=
      'pyRevit Setup did not complete successfully.' + CRLF + CRLF +
      'Exit code: ' + IntToStr(ResultCode) + CRLF + CRLF +
      'AnonGee installation has been stopped. Install pyRevit 6.5.5 ' +
      'manually or review the Setup logs before trying again.';
    Log('[FAIL] pyRevit prerequisite exited with code ' + IntToStr(ResultCode));
    Exit;
  end;

  if not VerifyBundledPyRevitInstalled then
  begin
    Result :=
      'pyRevit Setup completed, but AnonGee could not verify a clean compatible ' +
      'pyRevit 6.5.5 installation afterward.' + CRLF + CRLF +
      'AnonGee files have not been installed. Check Windows Installed Apps for ' +
      'stale pyRevit versions, then run AnonGee Setup again.';
    Exit;
  end;

  PyRevitCleanupRequired := False;
  PyRevitInstallRequired := False;
  Log('[PASS] pyRevit prerequisite installation completed and verified.');
end;

function InitializeSetup: Boolean;
var
  ProcessCheckSucceeded: Boolean;
begin
  Result := False;
  PyRevitInstallRequired := False;
  PyRevitCleanupRequired := False;
  PyRevitInstallReason := '';
  IncompatibleUserPyRevitCount := 0;
  IncompatibleUserPyRevitSummary := '';

  Log('============================================================');
  Log('AnonGee Toolkit prerequisite preflight');
  Log('Installer milestone: {#InstallerMilestone}');
  Log('Product version: {#MyAppVersion}');
  Log('Bundled pyRevit prerequisite: {#PyRevitPrereqVersion}');
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
      'AnonGee Toolkit installer milestone {#InstallerMilestone} supports Revit 2025 only.' +
      CRLF + CRLF +
      'Install or repair Autodesk Revit 2025, then run Setup again.',
      mbCriticalError,
      MB_OK
    );
    Exit;
  end;
  Log('[PASS] Autodesk Revit 2025 detected at: ' + DetectedRevitPath);

  // 4-6. Detect every registered pyRevit candidate. Missing pyRevit is
  // provisioned later by PrepareToInstall. Any incompatible per-user entries
  // require explicit consent and are purged before the bundled repair runs.
  if not DetectPyRevit then
  begin
    MarkPyRevitForInstall('pyRevit is not installed');
    Log('[INFO] Setup will install bundled pyRevit {#PyRevitPrereqCompatibilityVersion}.');
  end
  else
  begin
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

    if IncompatibleUserPyRevitCount > 0 then
    begin
      Log(
        '[WARN] Incompatible per-user pyRevit registration(s) detected: ' +
        IncompatibleUserPyRevitSummary
      );

      if not ConfirmPerUserPyRevitRepair(
        IncompatibleUserPyRevitSummary
      ) then
        Exit;
    end;

    // 7. Explicit compatibility/repair policy for the selected candidate.
    if not ValidatePyRevitCompatibility then
      Exit;

    if PyRevitCleanupRequired then
      Log('[PASS] User approved purge + bundled per-user pyRevit repair.')
    else
      Log('[PASS] pyRevit compatibility policy accepted.');
  end;

  // 8. Payload integrity stays a build-time responsibility of
  // build_payload.py 0.2.0. [Files] also fails compilation if absent.
  // The bundled pyRevit EXE is likewise a required [Files] compile input.

  Log('============================================================');
  Log('AnonGee prerequisite preflight PASSED.');
  Log('Revit 2025 path: ' + DetectedRevitPath);
  if PyRevitCleanupRequired then
    Log(
      'pyRevit action: purge incompatible per-user version(s), then install/repair ' +
      '{#PyRevitPrereqVersion}'
    )
  else if PyRevitInstallRequired then
    Log('pyRevit action: install bundled {#PyRevitPrereqVersion}')
  else
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

  // pyRevit is an independent prerequisite and may be used by other tools.
  // Removing AnonGee must never uninstall or modify pyRevit.
  Result := True;
end;
