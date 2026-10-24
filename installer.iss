; ตัวติดตั้ง MySoundpad (Inno Setup 6) — สร้างด้วย build.bat
; ติดตั้งแบบรายผู้ใช้: ไม่ต้องใช้สิทธิ์แอดมิน, ข้อมูลผู้ใช้อยู่ที่ %APPDATA%\MySoundpad (ถอนโปรแกรมแล้วไม่หาย)

#define MyAppName "MySoundpad"
#define MyAppVersion "1.0.0"
#define MyAppExe "MySoundpad.exe"

[Setup]
AppId={{D73350B3-B8E2-4D1E-BAD2-69B1FF949EE5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=build\installer
OutputBaseFilename=MySoundpad-Setup-{#MyAppVersion}
SetupIconFile=build_assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; ถ้าโปรแกรมเปิดอยู่ ตัวติดตั้ง/ถอนการติดตั้งจะขอให้ปิดก่อน (ชื่อเดียวกับใน soundpad.py)
AppMutex=MySoundpad_SingleInstance
CloseApplications=yes

[Languages]
Name: "thai"; MessagesFile: "compiler:Languages\Thai.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
thai.NoCable=ยังไม่พบ VB-CABLE ในเครื่องนี้%n%nMySoundpad ต้องใช้ VB-CABLE (ฟรี) เพื่อส่งเสียงเข้าไมค์ใน Discord/เกม%nถ้าไม่มี จะเล่นเสียงออกลำโพงได้อย่างเดียว%n%nดาวน์โหลดได้ที่ https://vb-audio.com/Cable/%n(ติดตั้งแล้วรีสตาร์ทเครื่อง จากนั้นตั้งไมค์ใน Discord เป็น "CABLE Output")%n%nติดตั้ง MySoundpad ต่อเลยไหม?
english.NoCable=VB-CABLE was not found on this PC.%n%nMySoundpad needs VB-CABLE (free) to send sounds into your microphone in Discord/games.%nWithout it, sounds only play through your speakers.%n%nDownload: https://vb-audio.com/Cable/%n%nContinue installing MySoundpad?
thai.OpenCablePage=เปิดเว็บดาวน์โหลด VB-CABLE
english.OpenCablePage=Open the VB-CABLE download page

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "build\dist\MySoundpad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "{cm:OpenCablePage}"; Flags: shellexec postinstall skipifsilent unchecked; Check: not CableInstalled
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function CableInstalled: Boolean;
begin
  { ไดรเวอร์ VB-CABLE ลงทะเบียนเป็น service ชื่อ VBAudioVACMME }
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\VBAudioVACMME');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if (not CableInstalled) and (not WizardSilent) then
    Result := MsgBox(CustomMessage('NoCable'), mbConfirmation, MB_YESNO) = IDYES;
end;
