// AnonGee installer lifecycle mode fragment.
//
// Included by the 0.8 release builders through ISCC --include. ISCC processes
// that include before the root script, so the final #insert 0 below defers this
// fragment until after AnonGee.iss. At that point the root script is already in
// its [Code] section, therefore this file must contain Pascal Script only: no
// [Code] header and no semicolon-style ISS comments.
//
// The builders provide AnonGeeProductVersion as a command-line ISPP define so
// this fragment can compare the candidate against the existing Windows uninstall
// registration without changing the mature prerequisite implementation.

#ifndef AnonGeeProductVersion
  #error AnonGeeProductVersion must be supplied by the AnonGee release builder.
#endif

function AGLifecycleUninstallKey: String;
begin
  Result :=
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' +
    'Zxaidman.AnonGee.Toolkit_is1';
end;

function AGLifecycleTargetVersion: String;
begin
  Result := '{#AnonGeeProductVersion}';
end;

function AGLifecycleIsDigit(const C: Char): Boolean;
begin
  Result := (C >= '0') and (C <= '9');
end;

function AGLifecycleTryParseSemVer3(
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
          (not AGLifecycleIsDigit(VersionText[I])) do
      I := I + 1;

    if I > Length(VersionText) then
      Exit;

    Token := '';
    while (I <= Length(VersionText)) and
          AGLifecycleIsDigit(VersionText[I]) do
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

function AGLifecycleCompareSemVer3(
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

function AGLifecycleReadInstalledVersion(
  var VersionText: String;
  var RegistrationFound: Boolean
): Boolean;
var
  UninstallKey: String;
begin
  Result := False;
  VersionText := '';
  UninstallKey := AGLifecycleUninstallKey;
  RegistrationFound :=
    RegKeyExists(HKCU64, UninstallKey) or
    RegKeyExists(HKCU32, UninstallKey);

  if RegQueryStringValue(
    HKCU64,
    UninstallKey,
    'DisplayVersion',
    VersionText
  ) then
  begin
    Result := True;
    Exit;
  end;

  if RegQueryStringValue(
    HKCU32,
    UninstallKey,
    'DisplayVersion',
    VersionText
  ) then
    Result := True;
end;

procedure AGLifecycleStop(const Reason: String);
begin
  Log('[LIFECYCLE] mode=blocked | ' + Reason);

  if not WizardSilent then
    MsgBox(
      Reason + #13#10 + #13#10 +
      'Setup has not changed the installed AnonGee Toolkit.',
      mbCriticalError,
      MB_OK
    );

  Abort;
end;

procedure InitializeWizard;
var
  LifecycleMode: String;
  PreviousVersion: String;
  TargetVersion: String;
  RegistrationFound: Boolean;
  InstalledMajor: Integer;
  InstalledMinor: Integer;
  InstalledPatch: Integer;
  TargetMajor: Integer;
  TargetMinor: Integer;
  TargetPatch: Integer;
  Comparison: Integer;
  MessageText: String;
begin
  LifecycleMode := 'fresh-install';
  PreviousVersion := '';
  TargetVersion := AGLifecycleTargetVersion;

  if not AGLifecycleReadInstalledVersion(
    PreviousVersion,
    RegistrationFound
  ) then
  begin
    if RegistrationFound then
      AGLifecycleStop(
        'AnonGee Toolkit is already registered in Windows, but its installed ' +
        'product version cannot be read safely. Repair or uninstall that entry ' +
        'before continuing.'
      );

    WizardForm.Caption :=
      'Install AnonGee Toolkit ' + TargetVersion;
    Log(
      '[LIFECYCLE] mode=fresh-install | target=' +
      TargetVersion
    );
    Exit;
  end;

  if not AGLifecycleTryParseSemVer3(
    PreviousVersion,
    InstalledMajor,
    InstalledMinor,
    InstalledPatch
  ) then
    AGLifecycleStop(
      'AnonGee Toolkit ' + PreviousVersion +
      ' is already registered, but that installed version is not valid ' +
      'MAJOR.MINOR.PATCH metadata.'
    );

  if not AGLifecycleTryParseSemVer3(
    TargetVersion,
    TargetMajor,
    TargetMinor,
    TargetPatch
  ) then
    AGLifecycleStop(
      'This AnonGee Setup carries invalid product version metadata: ' +
      TargetVersion
    );

  Comparison := AGLifecycleCompareSemVer3(
    TargetMajor,
    TargetMinor,
    TargetPatch,
    InstalledMajor,
    InstalledMinor,
    InstalledPatch
  );

  if Comparison < 0 then
    AGLifecycleStop(
      'A newer AnonGee Toolkit is already installed.' + #13#10 +
      'Installed: ' + PreviousVersion + #13#10 +
      'This Setup: ' + TargetVersion + #13#10 + #13#10 +
      'Downgrades are blocked by installer milestone 0.8.0.'
    );

  if Comparison = 0 then
  begin
    LifecycleMode := 'same-version-reinstall';
    WizardForm.Caption :=
      'Reinstall AnonGee Toolkit ' + TargetVersion;
    MessageText :=
      'AnonGee Toolkit ' + TargetVersion +
      ' is already installed.' + #13#10 + #13#10 +
      'Setup will reinstall/repair this same version by replacing the ' +
      'AnonGee extension payload. Bridge runtime state and pyRevit are ' +
      'preserved.';
  end
  else
  begin
    LifecycleMode := 'upgrade';
    WizardForm.Caption :=
      'Upgrade AnonGee Toolkit ' + PreviousVersion +
      ' to ' + TargetVersion;
    MessageText :=
      'AnonGee Toolkit upgrade detected.' + #13#10 + #13#10 +
      'Installed: ' + PreviousVersion + #13#10 +
      'Upgrade to: ' + TargetVersion + #13#10 + #13#10 +
      'Setup will replace the AnonGee extension payload while preserving ' +
      'bridge runtime state and the independent pyRevit installation.';
  end;

  Log(
    '[LIFECYCLE] mode=' + LifecycleMode +
    ' | installed=' + PreviousVersion +
    ' | target=' + TargetVersion
  );

  if not WizardSilent then
    MsgBox(MessageText, mbInformation, MB_OK);
end;

// ISCC --include is processed before the root script. Keep this directive as
// the final non-empty line so the subsequently processed signing overlay (when
// present) and AnonGee.iss are inserted before this Pascal code fragment.
#insert 0
