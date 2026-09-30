; Inno Setup script for the AI Sound Design AAX plugin (Windows).
;
; Build it with build_installer_windows.ps1, which passes the signed bundle and the
; version, or by hand:
;   ISCC.exe /DBundleDir="C:\path\to\AI Sound Design.aaxplugin" /DAppVer=0.1.0 installer_windows.iss
; Inno Setup 6: https://jrsoftware.org/isdl.php (winget install JRSoftware.InnoSetup)
;
; The resulting setup .exe carries the whole bundle (the DLL and the embedded Python)
; and installs it, from wherever it is run and for any user with admin rights, into
; Pro Tools' plug-in folder. An older copy of the plugin is removed first, so the
; folder ends up exactly like the bundle (the same as robocopy /MIR).

#ifndef BundleDir
  #define BundleDir "..\..\build-aax-vs\pt_v2a_artefacts\Release\AAX\AI Sound Design.aaxplugin"
#endif
#ifndef AppVer
  #define AppVer "0.1.0"
#endif
#define PluginFolder "AI Sound Design.aaxplugin"

[Setup]
AppId={{7C1E2B54-6D3A-4F0E-9B7B-AAX0A15D0001}
AppName=AI Sound Design
AppVersion={#AppVer}
AppVerName=AI Sound Design {#AppVer}
AppPublisher=AI Sound Design
AppPublisherURL=https://github.com/ai-sound-design/ai-protools-aax
AppSupportURL=https://github.com/ai-sound-design/ai-protools-aax/issues
DefaultDirName={commoncf}\Avid\Audio\Plug-Ins\{#PluginFolder}
DefaultGroupName=AI Sound Design
DisableDirPage=yes
DirExistsWarning=no
DisableProgramGroupPage=yes
DisableReadyPage=no
UninstallDisplayName=AI Sound Design (AAX plugin for Pro Tools)
UninstallFilesDir={commonappdata}\AI Sound Design\uninstall
OutputDir=installer_output
OutputBaseFilename=AI-Sound-Design-Windows-Setup-v{#AppVer}
SetupIconFile=Resources\icon.ico
Compression=lzma2/max
SolidCompression=yes
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[InstallDelete]
; An earlier version of the plugin goes first, so nothing stale survives beside the new files
Type: filesandordirs; Name: "{app}"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}"; Permissions: everyone-readexec

[Messages]
WelcomeLabel1=Welcome to AI Sound Design Setup
WelcomeLabel2=This installs the AI Sound Design AAX plugin, version {#AppVer}, for Pro Tools.%n%nPlease close Pro Tools before you continue. The plugin itself needs no settings; the backends it talks to are configured in the plugin's Settings.
FinishedHeadingLabel=Installation complete
FinishedLabelNoIcons=AI Sound Design is installed. Start Pro Tools and insert the plugin on a track (Plug-Ins > Other > AI Sound Design).

[Code]
// Pro Tools holds the plugin DLL open, so it has to be closed before the files can be replaced.
function ProToolsRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{cmd}'), '/C tasklist /FI "IMAGENAME eq ProTools.exe" | find /I "ProTools.exe" > nul',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  while ProToolsRunning() do
  begin
    // Silent runs (/VERYSILENT) cannot ask, they just stop
    if WizardSilent() or (MsgBox('Pro Tools is running. Close it, then click Retry.', mbError, MB_RETRYCANCEL) = IDCANCEL) then
    begin
      Log('Pro Tools is running: giving up');
      Result := False;
      Exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  while ProToolsRunning() do
  begin
    // Silent runs (/VERYSILENT) cannot ask, they just stop
    if UninstallSilent() or (MsgBox('Pro Tools is running. Close it, then click Retry.', mbError, MB_RETRYCANCEL) = IDCANCEL) then
    begin
      Log('Pro Tools is running: giving up');
      Result := False;
      Exit;
    end;
  end;
end;
