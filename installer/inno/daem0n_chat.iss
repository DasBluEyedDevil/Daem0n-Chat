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
Source: "staging\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion
Source: "staging\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion
Source: "staging\site-packages\*"; DestDir: "{app}\site-packages"; Flags: recursesubdirs ignoreversion
Source: "staging\installer\*"; DestDir: "{app}\installer"; Flags: recursesubdirs ignoreversion

[Run]
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" install --python-path ""{app}\python\python.exe"" --install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Configuring Claude Desktop..."

[UninstallRun]
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" uninstall"; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated

[Code]
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
