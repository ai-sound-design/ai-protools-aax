; Inno Setup Script for AI Sound Design AAX plugin (Windows)
; Download Inno Setup from: https://jrsoftware.org/isdl.php
; Compile with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer_windows.iss

[Setup]
; Basic application info
AppName=AI Sound Design
AppVersion=0.1.0
AppPublisher=anonymous
AppPublisherURL=https://github.com/ai-sound-design/protools-aax
AppSupportURL=https://github.com/ai-sound-design/protools-aax/issues
AppUpdatesURL=https://github.com/ai-sound-design/protools-aax/releases
DefaultDirName={commoncf}\Avid\Audio\Plug-Ins
DefaultGroupName=AI Sound Design

; Disable directory selection page (fixed install location for Pro Tools)
DisableDirPage=yes
DirExistsWarning=no

; Output configuration
OutputDir=installer_output
OutputBaseFilename=AI-Sound-Design-Windows-Setup-v0.1.0
SetupIconFile=Resources\icon.ico
Compression=lzma2
SolidCompression=yes

; Windows version requirements
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64

; Admin rights required for system-wide AAX plugin installation
PrivilegesRequired=admin

; License and info files (optional - add if you have them)
; LicenseFile=LICENSE.txt
; InfoBeforeFile=README.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
; Copy the entire signed AAX plugin folder from staging directory
; Installs system-wide to Pro Tools common plugin directory
Source: "installer_staging\AI Sound Design.aaxplugin\*"; \
  DestDir: "{commoncf}\Avid\Audio\Plug-Ins\AI Sound Design.aaxplugin"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Ensure plugin directory exists with proper permissions
Name: "{commoncf}\Avid\Audio\Plug-Ins\AI Sound Design.aaxplugin"; Permissions: everyone-readexec

[Icons]
; No Start Menu shortcuts needed (plugin only)

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  
  // Check if Pro Tools is running - warn user to close it
  if CheckForMutexes('ProTools') then
  begin
    if MsgBox('Pro Tools appears to be running. Please close Pro Tools before installing the plugin.' + #13#10 + #13#10 + 'Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

[Run]
; Optional: Launch Pro Tools after installation (commented out by default)
; Filename: "{pf}\Avid\Pro Tools\ProTools.exe"; Description: "Launch Pro Tools"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up config files on uninstall
Type: filesandordirs; Name: "{userappdata}\AI Sound Design"

[Messages]
; Custom messages
WelcomeLabel1=Welcome to AI Sound Design Setup
WelcomeLabel2=This will install the AI Sound Design AAX plugin for Pro Tools.%n%nThe plugin uses AI to generate audio from video content and provides sound effect search capabilities.%n%nClick Next to continue.
FinishedHeadingLabel=Installation Complete
FinishedLabelNoIcons=AI Sound Design has been successfully installed.%n%nThe plugin is now available in Pro Tools under Plug-Ins > Utility > AI Sound Design.
