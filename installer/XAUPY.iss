[Setup]
AppId={{07BF11D7-1E2A-478F-A51F-428439D1CF3A}
AppName=XAUPY Control Center
AppVersion=0.17.0
VersionInfoVersion=0.17.0.1
AppVerName=XAUPY Control Center 0.17.0 DEMO1
DefaultDirName={localappdata}\Programs\XAUPY
DefaultGroupName=XAUPY
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=XAUPY-0.17.0-demo1-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\XAUPY.Desktop.exe
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
SetupLogging=yes

[Files]
Source: "..\dist\XAUPY-win-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Icons]
Name: "{group}\XAUPY Control Center"; Filename: "{app}\XAUPY.Desktop.exe"
Name: "{autodesktop}\XAUPY Control Center"; Filename: "{app}\XAUPY.Desktop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\XAUPY.Desktop.exe"; Description: "Open XAUPY Control Center"; Flags: nowait postinstall skipifsilent unchecked

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  StartupCommand: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Preserve a startup entry belonging to another portable or newer installation. }
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'XAUPY', StartupCommand) then
      if CompareText(StartupCommand, '"' + ExpandConstant('{app}\XAUPY.Desktop.exe') + '"') = 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'XAUPY');
  end;
end;
