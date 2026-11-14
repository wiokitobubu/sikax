; Installateur Windows de Sikax (Inno Setup 6).
;
;   iscc /DVersion=2.0.0 packaging\sikax.iss
;
; À lancer après PyInstaller : l'installateur emballe le dossier dist\Sikax,
; crée les raccourcis et associe les fichiers .sikax à l'application.

#ifndef Version
  #define Version "2.0.0"
#endif

[Setup]
AppId={{6F1D2C0E-7A54-4B6F-9E0B-51CA5A1F2D10}
AppName=Sikax
AppVersion={#Version}
AppPublisher=Sikax
DefaultDirName={autopf}\Sikax
DefaultGroupName=Sikax
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Sikax-{#Version}-setup
SetupIconFile=..\resources\icons\sikax.ico
UninstallDisplayIcon={app}\Sikax.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Sikax\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sikax"; Filename: "{app}\Sikax.exe"
Name: "{autodesktop}\Sikax"; Filename: "{app}\Sikax.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.sikax"; ValueType: string; ValueData: "Sikax.Projet"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Sikax.Projet"; ValueType: string; ValueData: "Projet Sikax"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Sikax.Projet\DefaultIcon"; ValueType: string; ValueData: "{app}\Sikax.exe,0"
Root: HKA; Subkey: "Software\Classes\Sikax.Projet\shell\open\command"; ValueType: string; ValueData: """{app}\Sikax.exe"" ""%1"""

[Run]
Filename: "{app}\Sikax.exe"; Description: "{cm:LaunchProgram,Sikax}"; Flags: nowait postinstall skipifsilent
