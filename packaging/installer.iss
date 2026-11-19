; Inno Setup script: builds HyperGet-Setup.exe from the PyInstaller output in dist\HyperGet
#define AppName "HyperGet Downloader"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F2B8F3C-6C7E-4A57-9C1B-5E0D3B7A9A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=HyperGet
DefaultDirName={autopf}\HyperGet
DefaultGroupName=HyperGet
UninstallDisplayIcon={app}\HyperGet.exe
OutputDir=..\dist
OutputBaseFilename=HyperGet-Setup-{#AppVersion}
SetupIconFile=hypeget.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start HyperGet when I sign in (needed for the browser extension)"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\HyperGet\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\HyperGet Downloader"; Filename: "{app}\HyperGet.exe"
Name: "{group}\Browser extension folder"; Filename: "{app}\extension"
Name: "{group}\Uninstall HyperGet"; Filename: "{uninstallexe}"
Name: "{autodesktop}\HyperGet Downloader"; Filename: "{app}\HyperGet.exe"; Tasks: desktopicon
Name: "{userstartup}\HyperGet Downloader"; Filename: "{app}\HyperGet.exe"; Tasks: startup

[Run]
Filename: "{app}\HyperGet.exe"; Description: "Launch HyperGet now"; Flags: nowait postinstall skipifsilent
