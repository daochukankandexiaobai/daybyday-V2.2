; Compile this file after scripts\build_win7_dist.ps1 creates dist\day by day.
; The packaged executable is x64 because the bundled Win7 Python runtime is x64.

#define MyAppName "day by day"
#define MyAppVersion "2.2.3"
#define MyAppExeName "day by day.exe"

[Setup]
AppId={{2B633C6D-1A9C-493E-8B82-D9D33199D94B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName=day by day V2.2.3
DefaultDirName={localappdata}\day by day
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=day by day
SetupIconFile=..\assets\yinshui.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=classic

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\day by day\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
