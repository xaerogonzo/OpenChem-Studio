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
#else
  #define AppIdGuid "{{C33CE7E7-F8EE-4EEA-82B6-142ECE2F7F4F}"
  #define OutputName "OpenChemStudio-v" + AppVersion + "-windows-x64-setup"
#endif

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
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#SourceDir}\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
WizardStyle=modern
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

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; The whole previous runtime goes first (see the header). Not `plugins\`.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\OpenChem Studio"; Filename: "{app}\OpenChemStudio.exe"
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
