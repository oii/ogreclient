; vi: set ff=dos :
[Setup]
#define AppName "OGRE"
#define AppVersion "0.0.2"

AppId={{9BAD40C1-B4D6-4D17-A1B7-820383559FF5}
AppName={#AppName}
AppVerName={#AppName} {#AppVersion}
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Oii, Inc.
AppPublisherURL=https://ogre.oii.yt/
AppSupportURL=https://ogre.oii.yt/
AppUpdatesURL=https://ogre.oii.yt/
DefaultDirName={pf}\OGRE
DisableDirPage=yes
DefaultGroupName=OGRE
Compression=lzma
SolidCompression=yes
OutputBaseFilename=ogresetup
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\OgreClientTray\bin\Release\OgreClientTray.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\OgreClientService\bin\Release\OgreClientService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\OgreClientTray\route.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ogreclient-{#AppVersion}.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "WinPython-64bit-2.7.12.3Zero\*"; DestDir: "{app}\WinPython-64bit-2.7.12.3Zero"; Flags: ignoreversion recursesubdirs
Source: "Calibre Portable\*"; DestDir: "{app}\CalibrePortable"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\OGRE"; Filename: "{app}\OgreClientTray.exe"
Name: "{group}\{cm:UninstallProgram,OGRE}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\WinPython-64bit-2.7.12.3Zero\scripts\install_ogre.bat"
Filename: "{app}\OgreClientService.exe"; Parameters: "--install"
Filename: "net.exe"; Parameters: "start ogre"
Filename: "{app}\OgreClientTray.exe"; Description: "{cm:LaunchProgram,OGRE}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "net.exe"; Parameters: "stop ogre"
Filename: "{app}\OgreClientService.exe"; Parameters: "--uninstall"
Filename: "{cmd}"; Parameters: "/C ""taskkill /im OgreClientTray.exe /f /t"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
/////////////////////////////////////////////////////////////////////
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

/////////////////////////////////////////////////////////////////////
function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

/////////////////////////////////////////////////////////////////////
function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
// Return Values:
// 1 - uninstall string is empty
// 2 - error executing the UnInstallString
// 3 - successfully executed the UnInstallString

  // default return value
  Result := 0;

  // get the uninstall string of the old app
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES','', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3
    else
      Result := 2;
  end else
    Result := 1;
end;

/////////////////////////////////////////////////////////////////////
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep=ssInstall) then
  begin
    if (IsUpgrade()) then
    begin
      UnInstallOldVersion();
    end;
  end;
end;
