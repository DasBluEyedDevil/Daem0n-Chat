# Phase 9: Distribution & Packaging - Research

**Researched:** 2026-02-08
**Domain:** Windows installer packaging, MCP server auto-configuration, Python application distribution, model download orchestration
**Confidence:** MEDIUM (novel domain with multiple viable approaches; MCPB format is emerging but experimental for Python)

## Summary

Distributing a Python MCP server with heavy ML dependencies (PyTorch ~200MB+, sentence-transformers, Qdrant, leidenalg) to non-technical Windows users is the hardest problem in this phase. The project has three viable distribution strategies, each with significant tradeoffs:

1. **MCPB Desktop Extension (uv type)** -- Anthropic's official one-click install format. Experimental for Python; Claude Desktop auto-manages Python/dependencies via `uv`. Simplest user experience but the `uv` server type is still in development and may not be production-ready. Large ML dependencies (PyTorch ~200MB+, model downloads ~400MB) create a potentially very long first-run experience.

2. **Inno Setup + Embedded Python** -- Traditional Windows installer using Python embeddable distribution or python-build-standalone. Most control over first-run experience (progress bars, model pre-download). Requires significant custom work for JSON config manipulation and dependency bundling. Best antivirus compatibility since no PyInstaller bootloader is involved.

3. **Hybrid: MCPB + Inno Setup fallback** -- Ship MCPB for Claude Desktop users, Inno Setup installer for users who need more control or encounter MCPB issues.

A critical co-existence requirement exists: Daem0n-Chat must run alongside the original Daem0n-MCP (coding memory) without conflicts. Analysis shows tool names are already fully namespaced (`daem0n_*` vs `commune/consult/inscribe/etc.`), but the MCP server name "Daem0nMCP" and storage paths need differentiation.

**Primary recommendation:** Target MCPB Desktop Extension as the primary distribution format (it is Anthropic's blessed path), but implement a two-track approach: (1) MCPB bundle with `uv` type for one-click install when supported, (2) Inno Setup installer as the reliable fallback that handles everything the MCPB cannot (model pre-download, progress indication, custom first-run wizard). Both tracks share a common setup/configuration Python module.

## Standard Stack

### Core Distribution Tools
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| MCPB CLI | latest | Build .mcpb Desktop Extension bundles | Anthropic's official MCP packaging format |
| Inno Setup | 6.x | Windows installer builder | Free, scriptable, excellent Windows support, no AV issues |
| python-build-standalone | latest | Portable Python runtime for bundling | Astral-maintained, same builds `uv` uses, fully self-contained |
| claude-desktop-config | 0.2.1 | Programmatic claude_desktop_config.json management | Purpose-built library, handles platform paths, atomic writes |

### Python Dependencies (Distribution-Critical)
| Library | Version | Purpose | Distribution Impact |
|---------|---------|---------|---------------------|
| sentence-transformers | >=3.2.0 | Embedding generation | REQUIRES PyTorch (~200MB CPU wheel). Cannot avoid this dependency. |
| torch (CPU-only) | >=2.x | ML runtime for embeddings | ~200MB Windows wheel. Use `--index-url https://download.pytorch.org/whl/cpu` to avoid CUDA bloat. |
| qdrant-client | >=1.7.0 | Vector storage (local mode) | Pure Python + SQLite local backend. No external server needed. Clean for packaging. |
| leidenalg | 0.11.0 | Community detection | Has Windows binary wheels (cp38-abi3-win_amd64, 2MB). No compilation needed. |
| python-igraph | >=0.11.0 | Graph operations | Has Windows binary wheels. Clean dependency. |
| fastmcp | >=3.0.0b1 | MCP server framework | Pure Python. Clean for packaging. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sentence-transformers + PyTorch | fastembed (Qdrant's ONNX-only lib) | Eliminates PyTorch (~200MB savings), but `nomic-ai/modernbert-embed-base` is NOT in fastembed's supported model list. Would require model change or custom ONNX integration. Significant code change. |
| PyInstaller | Embedded Python + Inno Setup | PyInstaller has chronic antivirus false positive issues. Embedded Python + Inno Setup avoids this entirely. |
| Inno Setup | MCPB only | MCPB is the future but `uv` Python type is experimental and may not handle first-run model downloads gracefully. |
| PyInstaller --onefile | PyInstaller --onedir | --onedir avoids UPX-related AV flags and has faster startup, but still has bootloader AV issues |

### Installation (for build environment)
```bash
# Build tools
npm install -g @anthropic-ai/mcpb
pip install claude-desktop-config

# CPU-only PyTorch for distribution
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers[onnx]
```

## Architecture Patterns

### Recommended Project Structure (Distribution Additions)
```
Daem0n-Chat/
├── daem0nmcp/                    # Existing server code
├── installer/
│   ├── manifest.json             # MCPB manifest for Desktop Extension
│   ├── icon.png                  # Extension icon (512x512)
│   ├── setup_wizard.py           # Shared first-run setup logic
│   ├── config_manager.py         # Claude Desktop config manipulation
│   ├── model_downloader.py       # Embedding model pre-download with progress
│   ├── health_check.py           # Post-install verification
│   ├── inno/
│   │   ├── daem0n_chat.iss       # Inno Setup script
│   │   ├── post_install.py       # Post-install hook for Inno
│   │   └── assets/               # Installer graphics, license
│   └── build/
│       ├── build_mcpb.py         # MCPB bundle build script
│       └── build_inno.py         # Inno Setup build script
├── pyproject.toml                # Updated with distribution extras
└── scripts/
    └── build_installer.py        # Orchestrates full build
```

### Pattern 1: Two-Track Distribution
**What:** Ship both MCPB and Inno Setup installers from the same codebase
**When to use:** When targeting both technical and non-technical users, and when MCPB uv type maturity is uncertain
**Architecture:**
```
User downloads:
  Option A: daem0n-chat.mcpb  --> Claude Desktop auto-installs via Extensions UI
  Option B: DaemonChat-Setup.exe --> Traditional wizard installer

Both use same:
  - config_manager.py (reads/writes claude_desktop_config.json)
  - model_downloader.py (handles embedding model first-run download)
  - health_check.py (verifies everything works)
```

### Pattern 2: Server Name Namespacing for Co-existence
**What:** DaemonChat registers as a separate MCP server from DaemonMCP
**When to use:** Always -- users must be able to run both simultaneously

```json
// claude_desktop_config.json with BOTH servers co-existing
{
  "mcpServers": {
    "daem0nmcp": {
      "command": "python",
      "args": ["-m", "daem0nmcp.server"],
      "env": { "DAEM0NMCP_USER_ID": "." }
    },
    "daem0nchat": {
      "command": "python",
      "args": ["-m", "daem0nchat.server"],
      "env": {
        "DAEM0NCHAT_STORAGE_PATH": "%APPDATA%/DaemonChat/storage",
        "DAEM0NCHAT_QDRANT_PATH": "%APPDATA%/DaemonChat/qdrant"
      }
    }
  }
}
```

**Critical co-existence requirements:**
1. **Server key:** Use `"daem0nchat"` (not `"daem0nmcp"`) in config
2. **Tool names:** Already namespaced -- DaemonChat uses `daem0n_*` tools, DaemonMCP uses `commune/consult/inscribe/etc.` -- ZERO conflicts
3. **Storage paths:** DaemonChat must use `%APPDATA%/DaemonChat/` (isolated from DaemonMCP's `.daem0nmcp/storage/` in project dirs)
4. **Qdrant collections:** Both use local Qdrant but at different paths -- no conflicts
5. **FastMCP server name:** Change from `FastMCP("Daem0nMCP")` to `FastMCP("DaemonChat")` in mcp_instance.py
6. **Package name:** Consider renaming package from `daem0nmcp` to `daem0nchat` or keeping it but with distinct server registration

### Pattern 3: First-Run Model Download with Progress
**What:** Gracefully handle the ~400MB+ first-time download of embedding model + PyTorch
**When to use:** Always on first run

```python
# model_downloader.py pattern
import os
from pathlib import Path
from huggingface_hub import snapshot_download

MODELS_DIR = Path(os.environ.get(
    "DAEM0NCHAT_MODELS_PATH",
    Path.home() / "AppData" / "Local" / "DaemonChat" / "models"
))

def download_model(model_name: str, callback=None):
    """Download model with progress reporting."""
    cache_dir = MODELS_DIR / model_name.replace("/", "--")
    if cache_dir.exists():
        return cache_dir

    snapshot_download(
        model_name,
        cache_dir=str(MODELS_DIR),
        # HuggingFace Hub shows tqdm progress automatically
    )
    return cache_dir
```

### Anti-Patterns to Avoid
- **PyInstaller --onefile:** Chronic antivirus false positives on Windows. Never use for end-user distribution.
- **Requiring terminal/pip:** Non-technical users cannot use terminal. Every step must be GUI or automated.
- **Hardcoded paths:** Windows usernames with spaces (e.g., `C:\Users\John Smith\`) will break naive path handling. Always use `Path` objects and proper quoting.
- **Modifying system Python:** Never install into system Python. Always use isolated environment.
- **Assuming internet on every start:** Model download should be a one-time first-run operation. Cache aggressively.
- **Overwriting existing claude_desktop_config.json:** Must READ-MERGE-WRITE, never overwrite. User may have other MCP servers configured.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Claude Desktop config management | Custom JSON parser | claude-desktop-config library (v0.2.1) | Handles platform paths, atomic writes, idempotent operations |
| Windows installer | Batch scripts or NSIS | Inno Setup 6.x | Free, mature, excellent Windows support, Pascal scripting |
| Python runtime bundling | Compile Python from source | python-build-standalone or Python embeddable package | Pre-built, tested, Astral-maintained builds |
| MCPB packaging | Manual ZIP creation | `mcpb pack` CLI tool | Validates manifest, handles format correctly |
| Model download progress | Custom HTTP download | huggingface_hub.snapshot_download() | Handles caching, checksums, resume, progress |
| JSON merging in Inno Setup | Pascal JSON parser | Run Python post-install script from [Run] section | Inno Setup's Pascal scripting is weak for JSON; delegate to Python |

**Key insight:** The claude-desktop-config Python library is the single most important "don't hand-roll" item. It abstracts platform differences, handles atomic writes, and provides idempotent operations for adding/removing MCP servers.

## Common Pitfalls

### Pitfall 1: Antivirus False Positives
**What goes wrong:** Windows Defender and other AV software flag PyInstaller-generated executables as malware
**Why it happens:** PyInstaller's bootloader is used by actual malware, so heuristic scanners flag it
**How to avoid:** Do NOT use PyInstaller. Use embedded Python distribution + Inno Setup instead. Inno Setup-generated installers are well-known to AV vendors and rarely flagged.
**Warning signs:** VirusTotal shows >3 engines flagging your installer

### Pitfall 2: Windows Path Spaces
**What goes wrong:** Paths like `C:\Users\John Smith\AppData\...` break when passed unquoted in JSON or shell commands
**Why it happens:** Windows allows spaces in usernames; many developers test only with simple usernames
**How to avoid:** Always use `Path` objects in Python; always double-quote paths in JSON args; test with a username containing spaces
**Warning signs:** Works on dev machine, fails on "clean Windows machine" test

### Pitfall 3: First-Run Download Timeout/Failure
**What goes wrong:** sentence-transformers model (~400MB with dependencies) fails to download on slow connections, or user has no internet
**Why it happens:** Model is downloaded from HuggingFace on first use; no timeout handling or retry logic
**How to avoid:** Implement explicit download step with progress bar, retry logic, and clear error messages. Consider bundling the ONNX-quantized model (~50MB) in the installer to avoid runtime download.
**Warning signs:** Server starts but hangs for minutes with no feedback; then crashes

### Pitfall 4: claude_desktop_config.json Overwrite
**What goes wrong:** Installer overwrites existing config, destroying user's other MCP server configurations
**Why it happens:** Naive write instead of read-merge-write
**How to avoid:** Use claude-desktop-config library which handles this correctly. Always read existing config, add/update only the DaemonChat entry, write back.
**Warning signs:** User reports "my other MCP servers disappeared after installing DaemonChat"

### Pitfall 5: MCP Server Name Collision
**What goes wrong:** Both DaemonMCP (coding) and DaemonChat try to register as "daem0nmcp" in claude_desktop_config.json
**Why it happens:** Same package name heritage
**How to avoid:** Register DaemonChat as `"daem0nchat"` in config. Change FastMCP server name to `"DaemonChat"`.
**Warning signs:** Installing DaemonChat overwrites DaemonMCP's config entry

### Pitfall 6: PyTorch GPU Wheels Downloaded Instead of CPU
**What goes wrong:** Installer downloads ~2GB CUDA-enabled PyTorch instead of ~200MB CPU-only version
**Why it happens:** Default pip install gets CUDA wheels on systems with NVIDIA GPUs
**How to avoid:** Always specify `--index-url https://download.pytorch.org/whl/cpu` for distribution builds. Embedding models don't need GPU.
**Warning signs:** Install takes 2GB+ disk space; installer is enormous

### Pitfall 7: Storage Path Conflicts Between DaemonMCP and DaemonChat
**What goes wrong:** Both systems write to `.daem0nmcp/storage/` causing database corruption or data mixing
**Why it happens:** DaemonChat inherits DaemonMCP's storage path logic
**How to avoid:** DaemonChat must use a completely separate storage path: `%APPDATA%/DaemonChat/storage/` for SQLite, `%APPDATA%/DaemonChat/qdrant/` for vectors. Set via environment variables in the config.
**Warning signs:** Memories from coding sessions appear in chat context or vice versa

## Code Examples

### Example 1: claude-desktop-config Library Usage
```python
# Source: https://pypi.org/project/claude-desktop-config/
from claude_desktop_config import ClaudeDesktopConfig, enable_mcp_server, disable_mcp_server

def configure_daemon_chat(python_path: str, install_dir: str):
    """Add DaemonChat to Claude Desktop config without affecting other servers."""
    cdc = ClaudeDesktopConfig()
    config = cdc.read()

    changed = enable_mcp_server(config, "daem0nchat", {
        "command": python_path,
        "args": ["-m", "daem0nchat.server"],
        "env": {
            "DAEM0NCHAT_STORAGE_PATH": str(Path.home() / "AppData" / "Local" / "DaemonChat" / "storage"),
            "DAEM0NCHAT_QDRANT_PATH": str(Path.home() / "AppData" / "Local" / "DaemonChat" / "qdrant"),
        }
    })

    if changed:
        cdc.write(config)
        return True
    return False
```

### Example 2: MCPB Manifest for DaemonChat
```json
{
    "manifest_version": "0.3",
    "name": "daem0n-chat",
    "display_name": "DaemonChat - Conversational Memory",
    "version": "1.0.0",
    "description": "Claude remembers you. Persistent conversational memory that builds across sessions.",
    "author": {
        "name": "DasBluEyedDevil",
        "url": "https://github.com/DasBluEyedDevil/Daem0n-Chat"
    },
    "server": {
        "type": "uv",
        "entry_point": "server.py"
    },
    "tools": [
        {"name": "daem0n_briefing", "description": "Start session with personalized briefing"},
        {"name": "daem0n_remember", "description": "Store a memory about the user"},
        {"name": "daem0n_recall", "description": "Retrieve relevant memories"},
        {"name": "daem0n_forget", "description": "Remove specific memories"},
        {"name": "daem0n_profile", "description": "Manage user profile and preferences"},
        {"name": "daem0n_status", "description": "Check system health and statistics"},
        {"name": "daem0n_relate", "description": "Query relationship graph"},
        {"name": "daem0n_reflect", "description": "Analyze patterns and connections"}
    ],
    "tools_generated": false,
    "compatibility": {
        "platforms": ["win32"],
        "runtimes": {
            "python": ">=3.10,<3.14"
        }
    },
    "license": "MIT",
    "keywords": ["memory", "conversation", "personal", "companion"]
}
```

### Example 3: Inno Setup Script Core Structure
```pascal
; Source: https://jrsoftware.org/isinfo.php
[Setup]
AppName=DaemonChat
AppVersion=1.0.0
DefaultDirName={autopf}\DaemonChat
DefaultGroupName=DaemonChat
OutputBaseFilename=DaemonChat-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
; Non-admin install to avoid UAC for non-technical users

[Files]
; Embedded Python runtime
Source: "python\*"; DestDir: "{app}\python"; Flags: recursesubdirs
; Application code
Source: "daem0nmcp\*"; DestDir: "{app}\daem0nmcp"; Flags: recursesubdirs
; Pre-installed pip packages
Source: "site-packages\*"; DestDir: "{app}\site-packages"; Flags: recursesubdirs
; Pre-downloaded embedding model
Source: "models\*"; DestDir: "{app}\models"; Flags: recursesubdirs

[Run]
; Post-install: configure Claude Desktop
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" --install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  StatusMsg: "Configuring Claude Desktop..."

[UninstallRun]
; Remove from Claude Desktop config on uninstall
Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\installer\post_install.py"" --uninstall"; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated
```

### Example 4: Post-Install Script (used by Inno Setup)
```python
# installer/post_install.py
import sys
import json
from pathlib import Path

def get_claude_config_path():
    """Get Claude Desktop config path on Windows."""
    appdata = Path.home() / "AppData" / "Roaming" / "Claude"
    return appdata / "claude_desktop_config.json"

def install(install_dir: Path):
    """Add DaemonChat to Claude Desktop configuration."""
    config_path = get_claude_config_path()

    # Read existing config or create new
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {}

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    python_exe = str(install_dir / "python" / "python.exe")
    storage_dir = str(Path.home() / "AppData" / "Local" / "DaemonChat")

    config["mcpServers"]["daem0nchat"] = {
        "command": python_exe,
        "args": ["-m", "daem0nmcp.server"],
        "env": {
            "PYTHONPATH": str(install_dir / "site-packages"),
            "DAEM0NMCP_STORAGE_PATH": str(Path(storage_dir) / "storage"),
            "DAEM0NMCP_QDRANT_PATH": str(Path(storage_dir) / "qdrant"),
            "SENTENCE_TRANSFORMERS_HOME": str(install_dir / "models"),
            "PYTHONUNBUFFERED": "1"
        }
    }

    config_path.write_text(json.dumps(config, indent=2))

def uninstall():
    """Remove DaemonChat from Claude Desktop configuration."""
    config_path = get_claude_config_path()
    if not config_path.exists():
        return

    config = json.loads(config_path.read_text())
    if "mcpServers" in config and "daem0nchat" in config["mcpServers"]:
        del config["mcpServers"]["daem0nchat"]
        config_path.write_text(json.dumps(config, indent=2))

if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    else:
        install_dir = Path(sys.argv[sys.argv.index("--install-dir") + 1])
        install(install_dir)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual claude_desktop_config.json editing | MCPB Desktop Extensions (.mcpb) | Mid-2025 | One-click install for end users |
| PyInstaller --onefile | Embedded Python + Inno Setup | Ongoing (2024-2026) | Avoids AV false positives entirely |
| Custom JSON config scripts | claude-desktop-config Python library | 2025 | Safe, atomic config management |
| Bundling all deps in ZIP | MCPB `uv` server type | Late 2025 (experimental) | Auto-manages Python + deps via uv |
| Manual Python install required | python-build-standalone / uv auto-install | 2024-2025 | Users never need to install Python |

**Deprecated/outdated:**
- **PyInstaller for end-user distribution**: Chronic AV issues make it unsuitable for non-technical users
- **Manual config editing**: MCPB format replaces this for Claude Desktop
- **.dxt extension**: Renamed to .mcpb (Desktop Extensions to MCP Bundles)

## Co-existence Analysis: DaemonMCP + DaemonChat

### Tool Name Comparison (ZERO CONFLICTS)
| DaemonMCP (Coding) | DaemonChat (Companion) |
|---------------------|------------------------|
| commune | daem0n_briefing |
| consult | daem0n_recall |
| inscribe | daem0n_remember |
| reflect | daem0n_reflect |
| understand | daem0n_status |
| govern | daem0n_forget |
| explore | daem0n_relate |
| maintain | daem0n_profile |
| simulate_decision | (none) |
| evolve_rule | (none) |
| debate_internal | (none) |

**Verdict:** Tool names are FULLY distinct. No conflicts.

### Storage Isolation Requirements
| Resource | DaemonMCP | DaemonChat (Proposed) |
|----------|-----------|----------------------|
| SQLite DB | `<project>/.daem0nmcp/storage/daem0nmcp.db` | `%LOCALAPPDATA%/DaemonChat/storage/daem0nmcp.db` |
| Qdrant vectors | `<project>/.daem0nmcp/storage/qdrant/` | `%LOCALAPPDATA%/DaemonChat/qdrant/` |
| Config env prefix | `DAEM0NMCP_` | `DAEM0NMCP_` (override via env vars in claude_desktop_config.json) |
| MCP server key | `"daem0nmcp"` | `"daem0nchat"` |
| FastMCP name | `FastMCP("Daem0nMCP")` | `FastMCP("DaemonChat")` (MUST CHANGE) |

### Required Changes for Co-existence
1. Change `FastMCP("Daem0nMCP")` to `FastMCP("DaemonChat")` in `mcp_instance.py`
2. Set `DAEM0NMCP_STORAGE_PATH` and `DAEM0NMCP_QDRANT_PATH` env vars in config to isolate storage
3. Register as `"daem0nchat"` server key (not `"daem0nmcp"`)
4. Use `%LOCALAPPDATA%/DaemonChat/` as the base storage directory

## Dependency Size Estimate

| Component | Approximate Size | Notes |
|-----------|-----------------|-------|
| Python embeddable (3.12) | ~15 MB | Minimal Python runtime |
| PyTorch CPU-only wheel | ~200 MB | Required by sentence-transformers |
| sentence-transformers + deps | ~50 MB | transformers, huggingface_hub, etc. |
| nomic-ai/modernbert-embed-base ONNX quantized | ~50 MB | Embedding model (first download) |
| qdrant-client | ~5 MB | Local SQLite mode |
| All other deps (networkx, igraph, leidenalg, etc.) | ~30 MB | Binary wheels available for Windows |
| **Total installer size** | **~350 MB** | Without model; ~400MB with bundled model |
| **Total first-run download** | **~50 MB** | If model not bundled (HuggingFace download) |

### Size Optimization Options
| Strategy | Savings | Tradeoff |
|----------|---------|----------|
| CPU-only PyTorch | ~1.5 GB saved vs CUDA | No GPU acceleration (not needed for embeddings) |
| ONNX backend for sentence-transformers | No savings (still needs PyTorch) | Faster inference, but same install size |
| Switch to fastembed (eliminate PyTorch) | ~200 MB saved | Requires changing embedding model (modernbert-embed-base not supported). Significant code change. |
| Bundle ONNX model in installer | +50 MB installer, saves download time | Larger installer but no first-run download wait |

## Open Questions

1. **MCPB uv type readiness**
   - What we know: The `server.type = "uv"` is documented as experimental (v0.4+). There's an open GitHub issue (#96) where it doesn't work correctly yet.
   - What's unclear: Whether it's production-ready in current Claude Desktop builds (as of Feb 2026). Whether it handles the ~10 minute first-run dependency install gracefully.
   - Recommendation: Build MCPB manifest but validate against current Claude Desktop. Have Inno Setup as fallback.

2. **Embedding model strategy**
   - What we know: Current model (nomic-ai/modernbert-embed-base) requires PyTorch. FastEmbed would eliminate PyTorch but doesn't support this model.
   - What's unclear: Whether switching to a fastembed-supported model (e.g., nomic-embed-text-v1.5) would degrade recall quality. Whether bundling the ONNX model in the installer is practical.
   - Recommendation: Keep current model for Phase 9. Evaluate fastembed migration as a future optimization. Bundle the ONNX-quantized model file in the installer to avoid first-run download.

3. **Code signing**
   - What we know: Azure Trusted Signing costs $9.99/month, available to US/Canada individuals. Traditional OV certs cost $200-300/year. SmartScreen no longer gives instant reputation from EV certs (changed March 2024).
   - What's unclear: Whether unsigned Inno Setup installers will be blocked by SmartScreen for most users.
   - Recommendation: Start without code signing. If SmartScreen becomes a blocker, Azure Trusted Signing is the cheapest path at $9.99/month.

4. **Package renaming**
   - What we know: The package is currently named `daem0nmcp` (inherited from coding version). For co-existence, the MCP server key and FastMCP name must differ.
   - What's unclear: Whether the Python package should be renamed from `daem0nmcp` to `daem0nchat` (breaking change) or if env var isolation is sufficient.
   - Recommendation: Minimize changes -- keep package name `daem0nmcp` internally, but change FastMCP server name and use `"daem0nchat"` as the config key. Full package rename is a larger refactor that can be deferred.

5. **Env prefix collision**
   - What we know: Both DaemonMCP and DaemonChat use `DAEM0NMCP_` env prefix for settings.
   - What's unclear: Whether this causes issues when both are running (they run as separate processes with separate env).
   - Recommendation: Since each MCP server process gets its own `env` block in claude_desktop_config.json, env vars are isolated per process. No conflict. But document this clearly.

## Sources

### Primary (HIGH confidence)
- claude-desktop-config PyPI page (v0.2.1) - API, installation, usage
- Inno Setup official docs (jrsoftware.org) - [Run] section, Pascal scripting, FileExists
- MCPB GitHub repository (github.com/anthropics/dxt) - manifest spec, examples, uv type
- sentence-transformers installation docs (sbert.net) - PyTorch requirement confirmed
- FastEmbed supported models list (qdrant.github.io/fastembed) - modernbert-embed-base NOT supported
- leidenalg PyPI (v0.11.0) - Windows binary wheels confirmed available
- Python embeddable distribution docs (docs.python.org) - structure, limitations
- Daem0n-MCP GitHub (DasBluEyedDevil/Daem0n-MCP) - original tool names confirmed

### Secondary (MEDIUM confidence)
- PyTorch CPU-only wheel sizes (~200MB) - confirmed via GitHub issues and PyPI
- MCPB uv type experimental status - documented in manifest spec as v0.4+
- python-build-standalone (Astral) - maintained, used by uv
- Azure Trusted Signing pricing ($9.99/month) - Microsoft official pricing page
- Anthropic engineering blog on Desktop Extensions - format description

### Tertiary (LOW confidence)
- MCPB uv type production readiness - GitHub issue #96 shows it may not work yet (Jan 2026)
- Exact PyTorch CPU wheel size for Python 3.12 on Windows - varied between 200-590MB in recent builds
- SmartScreen behavior for unsigned Inno Setup installers - no definitive answer found

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - MCPB format is correct but uv type maturity is uncertain
- Architecture (two-track approach): HIGH - both Inno Setup and MCPB are well-documented
- Co-existence analysis: HIGH - tool names verified directly in both codebases
- Dependency sizing: MEDIUM - PyTorch wheel sizes fluctuate between builds
- Pitfalls: HIGH - well-documented in community (AV issues, path spaces, config overwrite)

**Research date:** 2026-02-08
**Valid until:** 2026-03-08 (30 days; MCPB format is evolving, check for uv type updates)
