; 照片相册 —— Inno Setup 打包脚本
; 用 ISCC 编译：  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; 产物：dist\照片相册_安装包.exe（双击即装，带卸载项、桌面与开始菜单快捷方式）

#define AppName "照片相册"
#define AppVersion "1.1.1"
#define AppExeName "照片相册.exe"

[Setup]
; AppId 是应用的唯一身份，升级/卸载靠它认人；一经发布不要再改
AppId={{7B4C2E9A-5D31-4F86-9C0A-6E2B5D71A348}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; lowest：不弹 UAC，装到「用户目录」，头像不带盾牌，普通用户双击就能装
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename={#AppName}_安装包
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AllowNoIcons=yes

[Languages]
; 官方发行版没带中文，所以中文语言包随项目一起放到根目录（UTF-8 BOM）
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式（双击直接打开）"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只清应用自己产生的索引与缩略图缓存；你的原图在别的地方，不会被删
Type: filesandordirs; Name: "{app}\photoalbum_data"
