#ifndef Payload
  #error Payload is required
#endif
#ifndef Output
  #error Output is required
#endif
[Setup]
AppId={{6F0A05D0-EA2A-4CCA-9019-47D6F49D0437}
AppName=数伴
AppVersion=0.3.5
AppPublisher=数伴项目组
DefaultDirName={localappdata}\Programs\Shuban
DefaultGroupName=数伴
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Output}
OutputBaseFilename=Shuban-Setup-0.3.5-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName=数伴桌面版
CloseApplications=yes
RestartApplications=no
InfoAfterFile={#Payload}\使用说明.txt

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Icons]
Name: "{autodesktop}\数伴"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\数伴"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"""; WorkingDir: "{app}"
Name: "{group}\模型配置"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"" --configure"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载数伴"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B ""{app}\desktop.py"""; Description: "启动数伴"; Flags: nowait postinstall skipifsilent

; Data is outside {app}. No UninstallDelete entries: retain data and local config.
