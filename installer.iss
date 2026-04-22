; Inno Setup Script — IPTV Stream Checker v2.0.0
; Builds a proper Windows installer with version upgrade + uninstall support

#define MyAppName      "IPTV Stream Checker"
#define MyAppVersion   "2.1.1"
#define MyAppPublisher "IPTV Tools"
#define MyAppExeName   "IPTVChecker.exe"
#define MyAppID        "{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}"
#define SourceDir      "dist\IPTVChecker"

[Setup]
AppId={{#MyAppID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Automatically uninstall previous version before installing new one
OutputDir=dist
OutputBaseFilename=Setup_IPTVChecker_v{#MyAppVersion}
SetupIconFile=iptv_checker.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; Version info for Windows
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} Setup
; Require admin for install to Program Files
PrivilegesRequired=admin
UsedUserAreasWarning=no
; Show changelog page
; Allow users to upgrade by running setup again
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon";   Description: "Start automatically with Windows";              GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Copy all built files from the PyInstaller dist folder
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";         Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Startup registry entry (only if task selected)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[UninstallRun]
; Kill the process before uninstall if running
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName} 2>nul"; RunOnceId: "KillApp"; Flags: runhidden

[UninstallDelete]
; Clean up user data files created by the app
Type: files; Name: "{localappdata}\{#MyAppName}\reddit_cache.json"
Type: dirifempty; Name: "{localappdata}\{#MyAppName}"

[Code]
// Auto-remove any previous version before installing
function InitializeSetup(): Boolean;
var
  UninstallString: String;
  ResultCode: Integer;
begin
  Result := True;
  // Check if old version is installed via registry
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppID}_is1',
                         'UninstallString', UninstallString) then
  begin
    if MsgBox('A previous version of {#MyAppName} is installed.'#13#10 +
              'It will be uninstalled before continuing.'#13#10#13#10 +
              'Continue?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      // Run the old uninstaller silently
      Exec(RemoveQuotes(UninstallString), '/SILENT /NORESTART', '', SW_HIDE,
           ewWaitUntilTerminated, ResultCode);
    end else
      Result := False;
  end;
end;
