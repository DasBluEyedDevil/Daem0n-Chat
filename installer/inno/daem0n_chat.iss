; DaemonChat Inno Setup Installer Script
; Installs DaemonChat with embedded Python runtime to local AppData (no admin required)

[Setup]
AppName=DaemonChat
AppVersion=1.0.0
AppPublisher=DasBluEyedDevil
AppPublisherURL=https://github.com/DasBluEyedDevil/Daem0n-Chat
DefaultDirName={localappdata}\DaemonChat
DefaultGroupName=DaemonChat
OutputBaseFilename=DaemonChat-1.0.0-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayName=DaemonChat - Conversational Memory

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "staging\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; BeforeInstall: UpdateStatus('Installing Python runtime...')
Source: "staging\site-packages\*"; DestDir: "{app}\site-packages"; Flags: recursesubdirs ignoreversion; BeforeInstall: UpdateStatus('Installing dependencies...')
Source: "staging\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion; BeforeInstall: UpdateStatus('Installing DaemonChat...')
Source: "staging\installer\*"; DestDir: "{app}\installer"; Flags: recursesubdirs ignoreversion

[Run]
; Download embedding model with visible console progress
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\download_model_console.py"" --install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  Flags: waituntilterminated; \
  StatusMsg: "Downloading AI model..."

; Configure Claude Desktop
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" install --python-path ""{app}\python\python.exe"" --install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Configuring Claude Desktop..."

; Offer to open onboarding prompt if Claude needs help
Filename: "notepad.exe"; \
  Parameters: """{app}\installer\onboarding_prompt.txt"""; \
  Description: "View Getting Started guide (only needed if Claude doesn't greet you by name)"; \
  Flags: postinstall nowait skipifsilent shellexec unchecked

[UninstallRun]
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" uninstall"; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated

[Code]
procedure UpdateStatus(Status: String);
begin
  WizardForm.StatusLabel.Caption := Status;
end;

function InitializeSetup(): Boolean;
var
  ClaudeAppDataDir: String;
begin
  Result := True;

  // Check if Claude Desktop is installed by looking for its AppData directory
  ClaudeAppDataDir := ExpandConstant('{userappdata}\Claude');

  if not DirExists(ClaudeAppDataDir) then
  begin
    MsgBox('Claude Desktop does not appear to be installed.' + #13#10 + #13#10 +
           'DaemonChat requires Claude Desktop to function.' + #13#10 + #13#10 +
           'Install Claude Desktop first from https://claude.ai/download, then run this installer again.',
           mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox('DaemonChat has been installed and configured!' + #13#10 + #13#10 +
           'What happens now:' + #13#10 +
           '  - Restart Claude Desktop to activate DaemonChat' + #13#10 +
           '  - Claude should greet you and remember context automatically' + #13#10 +
           '  - All data stays private on your machine' + #13#10 + #13#10 +
           'If Claude doesn''t greet you by name after restarting, check the' + #13#10 +
           '"View Getting Started guide" box on the next page for a quick' + #13#10 +
           'one-time setup prompt you can paste into Claude.',
           mbInformation, MB_OK);
  end;
end;
