; ตัวติดตั้ง MySoundpad (Inno Setup 6) — สร้างด้วย build.bat
; ติดตั้งแบบรายผู้ใช้: ไม่ต้องใช้สิทธิ์แอดมิน, ข้อมูลผู้ใช้อยู่ที่ %APPDATA%\MySoundpad (ถอนโปรแกรมแล้วไม่หาย)
; ถ้าเครื่องยังไม่มี VB-CABLE มีตัวเลือกดาวน์โหลดจากเว็บทางการ ตรวจลายเซ็น แล้วเปิดตัวติดตั้งของ VB-Audio ให้
;
; พารามิเตอร์สำหรับทดสอบ (ไม่ต้องใช้ตอนติดตั้งจริง):
;   /fakenocable=1  ทำเหมือนเครื่องยังไม่มี VB-CABLE (แสดงตัวเลือกได้แม้ติดตั้งแบบเงียบ)
;   /cabletest=1    ดาวน์โหลด + ตรวจลายเซ็น + แตกไฟล์ แต่ไม่เปิดตัวติดตั้ง VB-CABLE
;   /cableurl=URL   เปลี่ยนลิงก์ดาวน์โหลด (ใช้ทดสอบกรณีโหลดไม่ได้)

#define MyAppName "MySoundpad"
#define MyAppVersion "1.2.0"
#define MyAppExe "MySoundpad.exe"
#define CableUrl "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
#define CablePage "https://vb-audio.com/Cable/"

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
thai.OpenCablePage=เปิดเว็บดาวน์โหลด VB-CABLE
english.OpenCablePage=Open the VB-CABLE download page
thai.CableGroup=ไมค์เสมือน (จำเป็นสำหรับส่งเสียงเข้า Discord / เกม):
english.CableGroup=Virtual microphone (needed to send sounds into Discord / games):
thai.CableTask=ดาวน์โหลดและติดตั้ง VB-CABLE (ฟรี) ให้ด้วย — ต้องกดยอมรับสิทธิ์แอดมิน และรีสตาร์ทเครื่องหลังติดตั้ง
english.CableTask=Download and install VB-CABLE (free) — needs admin approval and a restart afterwards
thai.CableDownloading=กำลังดาวน์โหลด VB-CABLE... %1 KB
english.CableDownloading=Downloading VB-CABLE... %1 KB
thai.CableChecking=กำลังตรวจลายเซ็นดิจิทัลของ VB-CABLE...
english.CableChecking=Checking the VB-CABLE digital signature...
thai.CableAbout=ต่อไปหน้าต่างติดตั้ง VB-CABLE จะเปิดขึ้น%n%n1. กด Yes ที่หน้าต่างขอสิทธิ์ผู้ดูแลระบบ%n2. กดปุ่ม Install Driver แล้วรอจนขึ้นว่าติดตั้งเสร็จ%n3. ปิดหน้าต่างนั้น แล้วกลับมาที่ตัวติดตั้งนี้
english.CableAbout=The VB-CABLE installer will open next.%n%n1. Click Yes on the administrator prompt%n2. Click Install Driver and wait until it finishes%n3. Close that window and come back here
thai.CableFailed=ติดตั้ง VB-CABLE อัตโนมัติไม่สำเร็จ%n(%1)%n%nจะเปิดหน้าเว็บดาวน์โหลดให้ติดตั้งเองแทน
english.CableFailed=Could not install VB-CABLE automatically%n(%1)%n%nThe download page will open so you can install it yourself.
thai.CableNoDownload=ดาวน์โหลดไม่ได้
english.CableNoDownload=download failed
thai.CableNoUnzip=แตกไฟล์ไม่ได้
english.CableNoUnzip=could not extract the archive
thai.CableBadSig=ไฟล์ที่ดาวน์โหลดมาไม่มีลายเซ็นที่ถูกต้องของ VB-Audio จึงไม่เปิดใช้
english.CableBadSig=the downloaded file is not validly signed by VB-Audio, so it was not run
thai.CableNotInstalled=ยังไม่พบ VB-CABLE หลังปิดหน้าต่างติดตั้ง (อาจกดยกเลิก)
english.CableNotInstalled=VB-CABLE was still not found after its installer closed (it may have been cancelled)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installcable"; Description: "{cm:CableTask}"; GroupDescription: "{cm:CableGroup}"; Check: ShowCableTask

[Files]
Source: "build\dist\MySoundpad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{#CablePage}"; Description: "{cm:OpenCablePage}"; Flags: shellexec postinstall skipifsilent unchecked; Check: not CableInstalled
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CableRestart: Boolean;

function TestParam(const Name: String): Boolean;
begin
  Result := ExpandConstant('{param:' + Name + '|0}') = '1';
end;

function CableInstalled: Boolean;
begin
  { ไดรเวอร์ VB-CABLE ลงทะเบียนเป็น service ชื่อ VBAudioVACMME }
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\VBAudioVACMME') and not TestParam('fakenocable');
end;

function ShowCableTask: Boolean;
begin
  { ติดตั้งแบบเงียบ: ไม่เปิดหน้าต่างติดตั้ง VB-CABLE เอง (ต้องมีคนกดยืนยัน) ยกเว้นตอนทดสอบ }
  Result := not CableInstalled and (not WizardSilent or TestParam('fakenocable'));
end;

function NeedRestart: Boolean;
begin
  Result := CableRestart;
end;

function RunPowerShell(const Command: String): Integer;
var
  ResultCode: Integer;
begin
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' + Command + '"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    ResultCode := -1;
  Result := ResultCode;
end;

function OnCableProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  WizardForm.StatusLabel.Caption := FmtMessage(CustomMessage('CableDownloading'), [IntToStr(Progress div 1024)]);
  Result := True;
end;

procedure CableFail(const Reason: String);
var
  ErrorCode: Integer;
begin
  Log('VB-CABLE: FAILED - ' + Reason);
  if not WizardSilent then
  begin
    MsgBox(FmtMessage(CustomMessage('CableFailed'), [Reason]), mbError, MB_OK);
    ShellExec('open', '{#CablePage}', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  end;
end;

procedure InstallCable;
var
  Url, Zip, Dir, SetupExe: String;
  ResultCode: Integer;
begin
  Url := ExpandConstant('{param:cableurl|{#CableUrl}}');
  Dir := ExpandConstant('{tmp}\vbcable');
  Log('VB-CABLE: downloading ' + Url);
  try
    DownloadTemporaryFile(Url, 'vbcable.zip', '', @OnCableProgress);
  except
    CableFail(CustomMessage('CableNoDownload') + ': ' + GetExceptionMessage);
    Exit;
  end;
  Zip := ExpandConstant('{tmp}\vbcable.zip');

  WizardForm.StatusLabel.Caption := CustomMessage('CableChecking');
  if RunPowerShell('Expand-Archive -LiteralPath ''' + Zip + ''' -DestinationPath ''' + Dir + ''' -Force') <> 0 then
  begin
    CableFail(CustomMessage('CableNoUnzip'));
    Exit;
  end;
  SetupExe := Dir + '\VBCABLE_Setup_x64.exe';
  { ต้องมีลายเซ็นดิจิทัลที่ถูกต้องของผู้พัฒนา VB-Audio เท่านั้นถึงจะเปิดใช้ }
  if not FileExists(SetupExe) or
     (RunPowerShell('$s = Get-AuthenticodeSignature -LiteralPath ''' + SetupExe + '''; ' +
                    'if ($s.Status -eq ''Valid'' -and $s.SignerCertificate.Subject -like ''*BUREL VINCENT*'') ' +
                    '{ exit 0 } else { exit 1 }') <> 0) then
  begin
    CableFail(CustomMessage('CableBadSig'));
    Exit;
  end;
  Log('VB-CABLE: downloaded, extracted and signature verified: ' + SetupExe);
  if TestParam('cabletest') then
  begin
    Log('VB-CABLE: test mode - not launching the driver installer');
    Exit;
  end;

  if not WizardSilent then
    MsgBox(CustomMessage('CableAbout'), mbInformation, MB_OK);
  { runas = ขอสิทธิ์แอดมินเฉพาะตัวติดตั้งไดรเวอร์ของ VB-Audio }
  if not ShellExec('runas', SetupExe, '', Dir, SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then
  begin
    CableFail(SysErrorMessage(ResultCode));
    Exit;
  end;
  if RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\VBAudioVACMME') then
  begin
    Log('VB-CABLE: installed, restart needed');
    CableRestart := True;
  end
  else
    CableFail(CustomMessage('CableNotInstalled'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('installcable') then
    InstallCable;
end;
