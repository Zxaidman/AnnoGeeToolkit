; AnonGee installer lifecycle mode overlay.
;
; Included by the 0.8 release builders through ISCC --include. The builders
; provide AnonGeeProductVersion as a command-line ISPP define so this file can
; compare the candidate against the existing Windows uninstall registration.
;
; This stays outside AnonGee.iss deliberately: the mature Revit/pyRevit
; prerequisite code does not need to be refactored just to add lifecycle UX.

#ifndef AnonGeeProductVersion
  #error AnonGeeProductVersion must be supplied by the AnonGee release builder.
#endif

[Code]

const
  AGLifecycleUninstallKey =
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' +
    'Zxaidman.AnonGee.Toolkit_is1';
  AGLifecycleTargetVersion = '{#AnonGeeProductVersion}';

var
  AGLifecycleMode: String;
  AGLifecyclePreviousVersion: String;

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
begin
  Result := False;
  VersionText := '';
  RegistrationFound :=
    RegKeyExists(HKCU64, AGLifecycleUninstallKey) or
    RegKeyExists(HKCU32, AGLifecycleUninstallKey);

  if RegQueryStringValue(
    HKCU64,
    AGLifecycleUninstallKey,
    'DisplayVersion',
    VersionText
  ) then
  begin
    Result := True;
    Exit;
  end;

  if RegQueryStringValue(
    HKCU32,
    AGLifecycleUninstallKey,
    'DisplayVersion',
    VersionText
  ) then
    Result := True;
end;

procedure AGLifecycleStop(const Reason: String);
begin
  AGLifecycleMode := 'blocked';
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
  AGLifecycleMode := 'fresh-install';
  AGLifecyclePreviousVersion := '';

  if not AGLifecycleReadInstalledVersion(
    AGLifecyclePreviousVersion,
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
      'Install AnonGee Toolkit ' + AGLifecycleTargetVersion;
    Log(
      '[LIFECYCLE] mode=fresh-install | target=' +
      AGLifecycleTargetVersion
    );
    Exit;
  end;

  if not AGLifecycleTryParseSemVer3(
    AGLifecyclePreviousVersion,
    InstalledMajor,
    InstalledMinor,
    InstalledPatch
  ) then
    AGLifecycleStop(
      'AnonGee Toolkit ' + AGLifecyclePreviousVersion +
      ' is already registered, but that installed version is not valid ' +
      'MAJOR.MINOR.PATCH metadata.'
    );

  if not AGLifecycleTryParseSemVer3(
    AGLifecycleTargetVersion,
    TargetMajor,
    TargetMinor,
    TargetPatch
  ) then
    AGLifecycleStop(
      'This AnonGee Setup carries invalid product version metadata: ' +
      AGLifecycleTargetVersion
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
      'Installed: ' + AGLifecyclePreviousVersion + #13#10 +
      'This Setup: ' + AGLifecycleTargetVersion + #13#10 + #13#10 +
      'Downgrades are blocked by installer milestone 0.8.0.'
    );

  if Comparison = 0 then
  begin
    AGLifecycleMode := 'same-version-reinstall';
    WizardForm.Caption :=
      'Reinstall AnonGee Toolkit ' + AGLifecycleTargetVersion;
    MessageText :=
      'AnonGee Toolkit ' + AGLifecycleTargetVersion +
      ' is already installed.' + #13#10 + #13#10 +
      'Setup will reinstall/repair this same version by replacing the ' +
      'AnonGee extension payload. Bridge runtime state and pyRevit are ' +
      'preserved.';
  end
  else
  begin
    AGLifecycleMode := 'upgrade';
    WizardForm.Caption :=
      'Upgrade AnonGee Toolkit ' + AGLifecyclePreviousVersion +
      ' to ' + AGLifecycleTargetVersion;
    MessageText :=
      'AnonGee Toolkit upgrade detected.' + #13#10 + #13#10 +
      'Installed: ' + AGLifecyclePreviousVersion + #13#10 +
      'Upgrade to: ' + AGLifecycleTargetVersion + #13#10 + #13#10 +
      'Setup will replace the AnonGee extension payload while preserving ' +
      'bridge runtime state and the independent pyRevit installation.';
  end;

  Log(
    '[LIFECYCLE] mode=' + AGLifecycleMode +
    ' | installed=' + AGLifecyclePreviousVersion +
    ' | target=' + AGLifecycleTargetVersion
  );

  if not WizardSilent then
    MsgBox(MessageText, mbInformation, MB_OK);
end;
