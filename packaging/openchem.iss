; Inno Setup script for OpenChem Studio. Compiled by tools/make_installer.py, which
; passes AppVersion and SourceDir (the built dist\OpenChemStudio) on the command line.
;
; WHAT IT DOES
;   * Install: per-user OR all-users, chosen by the person at the start (the dialog
;     Inno shows when PrivilegesRequiredOverridesAllowed=dialog). Per-user needs no
;     administrator and is the default.
;   * Upgrade: the same AppId replaces the old version in place. The previous
;     `_internal` folder is DELETED first, so a file the new version no longer ships
;     cannot linger and mix two versions' DLLs (the reason a zip is unpacked into a
;     versioned folder). `plugins\` is NOT cleared: people add their own there.
;   * Uninstall: removes what the installer put down. A small form then asks whether
;     to ALSO remove the settings (registry) and the data folder (caches, downloaded
;     tools, recovery copies). Both are unchecked: the default is to keep everything.
;     Saved project files live wherever the person saved them and are never touched.
;
; Silent use (what the tests drive): /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /DIR=...
;   Silent uninstall keeps everything unless /REMOVESETTINGS=1 and/or /REMOVEDATA=1 is given.
;
; NOT SIGNED. Windows SmartScreen will say "unknown publisher" until it is.

#ifndef AppVersion
  #error AppVersion must be passed: ISCC /DAppVersion=0.10.0 ...
#endif
#ifndef SourceDir
  #error SourceDir must be passed: ISCC /DSourceDir=dist\OpenChemStudio ...
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

; A test build uses its own AppId (so it can never be mistaken for, or clobber, a real
; installation), a sandbox data folder and registry key (so removal can be tested without
; touching the person's real data), and cheaper compression. The shipped script is this
; same file with none of these defined.
#ifdef TestBuild
  #define AppIdGuid "{{C33CE7E7-F8EE-4EEA-82B6-142ECE2F7F40}"
  #define OutputName "OpenChemStudio-TEST-setup"
  ; Its own Start menu folder, so installing and uninstalling the test build can never touch the
  ; shortcuts of a real installation.
  #define GroupName "OpenChem Studio (TEST)"
#else
  #define GroupName "OpenChem Studio"
  #define AppIdGuid "{{C33CE7E7-F8EE-4EEA-82B6-142ECE2F7F4F}"
  #define OutputName "OpenChemStudio-v" + AppVersion + "-windows-x64-setup"
#endif
; The same GUID with a single brace, as the registry key under Uninstall spells it (the doubled
; brace above is how [Setup] escapes it). [Code] uses this to find an existing installation.
#define AppIdKey Copy(AppIdGuid, 2)

[Setup]
AppId={#AppIdGuid}
AppName=OpenChem Studio
AppVersion={#AppVersion}
AppVerName=OpenChem Studio {#AppVersion}
AppPublisher=OpenChem Studio
AppPublisherURL=https://github.com/xaerogonzo/OpenChem-Studio
AppSupportURL=https://github.com/xaerogonzo/OpenChem-Studio/issues
AppUpdatesURL=https://github.com/xaerogonzo/OpenChem-Studio/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName=OpenChem Studio
VersionInfoCompany=OpenChem Studio
VersionInfoDescription=OpenChem Studio Setup
VersionInfoCopyright=Copyright (C) OpenChem Studio contributors. GPL-3.0-or-later.
DefaultDirName={autopf}\OpenChem Studio
; One Start menu folder, not chosen by the person: the program, its uninstaller and a link to
; the documentation. The uninstaller is also copied into the install folder (unins000.exe) and
; listed in Windows Settings > Apps, but nobody looks there, hence the shortcut.
DefaultGroupName={#GroupName}
DisableProgramGroupPage=yes
ChangesAssociations=yes
; Always ask where to install. Inno's default ("auto") skips the page when a copy is already
; installed, which hid the choice from anyone re-running Setup. The previous folder is still
; the suggestion (UsePreviousAppDir).
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#SourceDir}\LICENSE
; Shown during installation, after the licence: what the program contacts, and that nothing is
; sent unless a feature that needs a service is used. Code signing terms require this page for
; software that can send user data. Kept in step with docs/CODE_SIGNING_POLICY.md by a test.
InfoBeforeFile={#SourcePath}installer_privacy.txt
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
WizardStyle=modern
; Artwork drawn by tools/make_brand_art.py. Each image is given at two sizes so it stays sharp
; at higher display scaling. The same pictures frame Setup and the uninstaller.
SetupIconFile={#SourcePath}icon.ico
WizardImageFile={#SourcePath}installer\wizard_large.bmp,{#SourcePath}installer\wizard_large_2x.bmp
WizardSmallImageFile={#SourcePath}installer\wizard_small.bmp,{#SourcePath}installer\wizard_small_2x.bmp
UninstallDisplayName=OpenChem Studio
UninstallDisplayIcon={app}\OpenChemStudio.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
#ifdef TestBuild
Compression=lzma2/fast
SolidCompression=no
#else
Compression=lzma2/normal
SolidCompression=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

#ifndef TestBuild
; Not in the test installer: it would take over a developer's real association while testing.
Name: "associate"; Description: "Open OpenChem Studio project files (.ocsproj) with &OpenChem Studio"; GroupDescription: "File types:"
#endif

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

#ifndef TestBuild
[Registry]
; Per-user installs write under HKCU\Software\Classes, all-users installs under HKLM (HKA picks).
; The program takes the project path as its first argument (main.project_argument).
Root: HKA; Subkey: "Software\Classes\.ocsproj"; ValueType: string; ValueName: ""; ValueData: "OpenChemStudio.Project"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.ocsproj\OpenWithProgids"; ValueType: string; ValueName: "OpenChemStudio.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\OpenChemStudio.Project"; ValueType: string; ValueName: ""; ValueData: "OpenChem Studio project"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\OpenChemStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\OpenChemStudio.exe,0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\OpenChemStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OpenChemStudio.exe"" ""%1"""; Tasks: associate
#endif

[InstallDelete]
; The whole previous runtime goes first (see the header). Not `plugins\`.
Type: filesandordirs; Name: "{app}\_internal"
; What an earlier build (0.11.0 drafts) put beside the exe and this one does not: the README's
; screenshots and the maintainer files. `docs\` is cleared so a document dropped from the list
; does not linger; the current set is installed again below. `plugins\` stays.
Type: filesandordirs; Name: "{app}\docs"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\CONTRIBUTING.md"
Type: files; Name: "{app}\CODE_OF_CONDUCT.md"
#ifndef TestBuild
; The single shortcut an earlier build made directly in the Start menu; it is now in a folder.
Type: files; Name: "{autoprograms}\OpenChem Studio.lnk"
#endif

[Icons]
Name: "{group}\OpenChem Studio"; Filename: "{app}\OpenChemStudio.exe"
Name: "{group}\Uninstall OpenChem Studio"; Filename: "{uninstallexe}"
Name: "{group}\Documentation"; Filename: "{app}\docs"
Name: "{group}\What's new (changelog)"; Filename: "{app}\CHANGELOG.md"
Name: "{group}\OpenChem Studio documentation (online)"; Filename: "https://github.com/xaerogonzo/OpenChem-Studio"
Name: "{autodesktop}\OpenChem Studio"; Filename: "{app}\OpenChemStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OpenChemStudio.exe"; Description: "Launch OpenChem Studio"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The runtime is ours entirely. `plugins\` is not removed wholesale: a person's own plugins
; live there, and Inno leaves a folder that still holds files it did not install.
Type: filesandordirs; Name: "{app}\_internal"

[Code]
var
  RemoveSettings: Boolean;
  RemoveData: Boolean;

{ The uninstaller of an existing installation of THIS product ('' when there is none), found
  through the same registry key Windows' Apps list reads: per-user installs register under
  HKCU, all-users installs under HKLM. }
function InstalledUninstaller(): String;
var
  Key, Command: String;
begin
  Result := '';
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppIdKey}_is1';
  if RegQueryStringValue(HKCU, Key, 'UninstallString', Command) or
     RegQueryStringValue(HKLM, Key, 'UninstallString', Command) then
    Result := RemoveQuotes(Command);
end;

{ Running Setup again over an installation used to just upgrade it, with no way to say "I
  wanted to remove it". Ask first, as most programs do: repair (a reinstall of this version,
  which replaces every shipped file), uninstall, or leave. A silent run (what the tests and an
  administrator's script use) skips the question and installs, exactly as before. }
function InitializeSetup(): Boolean;
var
  Uninstaller: String;
  Answer, ResultCode: Integer;
  Labels: TArrayOfString;
begin
  Result := True;
  if WizardSilent then
    Exit;
  SetArrayLength(Labels, 3);
  Labels[0] := 'Repair or update the existing installation';
  Labels[1] := 'Uninstall OpenChem Studio';
  Labels[2] := 'Cancel';
  Uninstaller := InstalledUninstaller();
  if (Uninstaller = '') or not FileExists(Uninstaller) then
    Exit;
  Answer := TaskDialogMsgBox(
    'OpenChem Studio is already installed',
    'Repair reinstalls this version over the existing one and keeps your settings, data and ' +
    'plugins. Uninstall removes the program and asks what else to remove.',
    mbInformation, MB_YESNOCANCEL, Labels, IDYES);
  if Answer = IDNO then
  begin
    ShellExec('', Uninstaller, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
    Result := False;
  end
  else if Answer <> IDYES then
    Result := False;
end;

{ Setup's own Browse button opens a folder picker with no "Make New Folder" button, so choosing
  a folder that does not exist yet meant typing its path. The same picker is available to the
  script with that button switched on; use it. The chosen folder is taken exactly as picked (no
  "OpenChem Studio" is appended), so a person who makes a new folder here gets that folder. }
procedure BrowseForInstallFolder(Sender: TObject);
var
  Dir: String;
begin
  Dir := WizardForm.DirEdit.Text;
  if BrowseForFolder('Select the folder to install OpenChem Studio into, then click OK.', Dir, True) then
    WizardForm.DirEdit.Text := Dir;
end;

procedure InitializeWizard();
begin
  WizardForm.DirBrowseButton.OnClick := @BrowseForInstallFolder;
end;

{ Where the application keeps its caches, downloaded tools and recovery copies by default.
  src/openchem/paths.py: platformdirs user_data_dir("OpenChemStudio") on Windows. }
function DataFolder(): String;
begin
#ifdef TestBuild
  Result := ExpandConstant('{param:TESTDATADIR|{localappdata}\OpenChemStudio-TEST}');
#else
  Result := ExpandConstant('{localappdata}\OpenChemStudio');
#endif
end;

{ The Qt settings (window layout, preferences) are written to this registry key
  (QSettings("OpenChemStudio", "OpenChemStudio")). }
function SettingsKey(): String;
begin
#ifdef TestBuild
  Result := 'Software\OpenChemStudio-TEST';
#else
  Result := 'Software\OpenChemStudio';
#endif
end;

{ If the person moved their data folder (Settings > Storage), the real location is named in
  data_root.txt inside the default folder. We never delete a folder somebody chose elsewhere;
  we only tell them where it is. Empty when the data is in the default place. }
function MovedDataFolder(): String;
var
  Recorded: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(DataFolder() + '\data_root.txt', Recorded) then
  begin
    Recorded := Trim(Recorded);
    if (Recorded <> '') and (CompareText(RemoveBackslash(String(Recorded)), RemoveBackslash(DataFolder())) <> 0) then
      Result := String(Recorded);
  end;
end;

function ParamIsOne(Name: String): Boolean;
begin
  Result := ExpandConstant('{param:' + Name + '|0}') = '1';
end;

function AskWhatToRemove(): Boolean;
var
  Form: TSetupForm;
  Heading, Note, Moved: TNewStaticText;
  SettingsBox, DataBox: TNewCheckBox;
  OkButton, CancelButton: TNewButton;
  MovedPath: String;
begin
  Result := True;
  Form := CreateCustomForm(ScaleX(460), ScaleY(330), True, False);
  try
    Form.Caption := 'Uninstall OpenChem Studio';

    Heading := TNewStaticText.Create(Form);
    Heading.Parent := Form;
    Heading.Left := ScaleX(16);
    Heading.Top := ScaleY(14);
    Heading.Width := Form.ClientWidth - ScaleX(32);
    Heading.AutoSize := False;
    Heading.WordWrap := True;
    Heading.Height := ScaleY(48);
    Heading.Caption := 'The program will be removed. Your saved project files are never deleted. ' +
      'Tick below only if you also want to remove what the program stored for you:';

    SettingsBox := TNewCheckBox.Create(Form);
    SettingsBox.Parent := Form;
    SettingsBox.Left := ScaleX(16);
    SettingsBox.Top := Heading.Top + Heading.Height + ScaleY(6);
    SettingsBox.Width := Form.ClientWidth - ScaleX(32);
    SettingsBox.Caption := 'Remove my settings and window layout';

    DataBox := TNewCheckBox.Create(Form);
    DataBox.Parent := Form;
    DataBox.Left := ScaleX(16);
    DataBox.Top := SettingsBox.Top + SettingsBox.Height + ScaleY(8);
    DataBox.Width := Form.ClientWidth - ScaleX(32);
    DataBox.Caption := 'Remove caches, downloaded tools and recovery copies';

    Note := TNewStaticText.Create(Form);
    Note.Parent := Form;
    Note.Left := ScaleX(36);
    Note.Top := DataBox.Top + DataBox.Height + ScaleY(2);
    Note.Width := Form.ClientWidth - ScaleX(52);
    Note.AutoSize := False;
    Note.WordWrap := True;
    Note.Height := ScaleY(64);
    Note.Caption := DataFolder() + #13#10 + 'This can be several gigabytes if you downloaded ORCA, pKa or ADMET tools.';

    MovedPath := MovedDataFolder();
    Moved := TNewStaticText.Create(Form);
    Moved.Parent := Form;
    Moved.Left := ScaleX(16);
    Moved.Top := Note.Top + Note.Height + ScaleY(6);
    Moved.Width := Form.ClientWidth - ScaleX(32);
    Moved.AutoSize := False;
    Moved.WordWrap := True;
    Moved.Height := ScaleY(64);
    if MovedPath <> '' then
      Moved.Caption := 'Your data folder was moved to ' + MovedPath + '. That folder is never removed here; delete it yourself if you no longer need it.'
    else
      Moved.Caption := '';

    OkButton := TNewButton.Create(Form);
    OkButton.Parent := Form;
    OkButton.Caption := 'Uninstall';
    OkButton.ModalResult := mrOk;
    OkButton.Default := True;
    OkButton.Width := ScaleX(90);
    OkButton.Height := ScaleY(26);
    OkButton.Left := Form.ClientWidth - ScaleX(16) - ScaleX(90) - ScaleX(8) - ScaleX(90);
    OkButton.Top := Form.ClientHeight - ScaleY(26) - ScaleY(14);

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Cancel';
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    CancelButton.Width := ScaleX(90);
    CancelButton.Height := ScaleY(26);
    CancelButton.Left := Form.ClientWidth - ScaleX(16) - ScaleX(90);
    CancelButton.Top := OkButton.Top;

    if Form.ShowModal() = mrOk then
    begin
      RemoveSettings := SettingsBox.Checked;
      RemoveData := DataBox.Checked;
    end
    else
      Result := False;
  finally
    Form.Free();
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  RemoveSettings := ParamIsOne('REMOVESETTINGS');
  RemoveData := ParamIsOne('REMOVEDATA');
  { Silent: only what the command line asked for. Interactive: ask, defaulting to keep. }
  if not UninstallSilent() then
    Result := AskWhatToRemove();
  Log(Format('Uninstall choices: remove settings=%d, remove data=%d', [Ord(RemoveSettings), Ord(RemoveData)]));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Folder: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  if RemoveSettings then
    Log(Format('Removing settings key %s: %d', [SettingsKey(), Ord(RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, SettingsKey()))]));
  if RemoveData then
  begin
    Folder := RemoveBackslash(DataFolder());
    { Only ever the application's own folder, never a drive root or a parent of it. }
    if (Pos('OpenChemStudio', ExtractFileName(Folder)) = 1) and DirExists(Folder) then
      DelTree(Folder, True, True, True);
  end;
end;
