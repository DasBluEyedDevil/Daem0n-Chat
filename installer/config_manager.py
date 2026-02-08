"""
Claude Desktop configuration management using claude-desktop-config library.

This module provides functions to add/remove the DaemonChat MCP server entry
in claude_desktop_config.json without destroying other MCP server entries.
"""

import sys
from pathlib import Path

from claude_desktop_config.api import ClaudeDesktopConfig, enable_mcp_server, disable_mcp_server


def get_claude_config_path() -> Path:
    """
    Get the path to claude_desktop_config.json.

    Delegates platform detection to claude-desktop-config library:
    - Windows: %APPDATA%/Claude/claude_desktop_config.json
    - macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
    - Linux: ~/.config/Claude/claude_desktop_config.json

    Returns:
        Path to the Claude Desktop config file.
    """
    cdc = ClaudeDesktopConfig()
    return Path(cdc.path)


def add_daemon_chat(python_path: str, install_dir: str | None = None) -> bool:
    """
    Add DaemonChat server entry to Claude Desktop config.

    Args:
        python_path: Path to Python executable (usually sys.executable)
        install_dir: Optional installation directory for PYTHONPATH and model cache

    Returns:
        True if config was modified, False if entry already existed with same values.
    """
    try:
        cdc = ClaudeDesktopConfig()
        config = cdc.read()
    except FileNotFoundError:
        # No config exists yet, create new
        cdc = ClaudeDesktopConfig()
        config = {"mcpServers": {}}
    except Exception as e:
        # Handle JSON decode errors by backing up and creating new
        import shutil
        from datetime import datetime
        backup_path = get_claude_config_path().with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            shutil.copy(get_claude_config_path(), backup_path)
        except Exception:
            pass
        cdc = ClaudeDesktopConfig()
        config = {"mcpServers": {}}

    # Determine platform-specific storage path
    if sys.platform == "win32":
        storage_base = Path.home() / "AppData" / "Local" / "DaemonChat"
    elif sys.platform == "darwin":
        storage_base = Path.home() / "Library" / "Application Support" / "DaemonChat"
    else:  # Linux and others
        storage_base = Path.home() / ".local" / "share" / "DaemonChat"

    env = {
        "DAEM0NMCP_STORAGE_PATH": str(storage_base / "storage"),
        "DAEM0NMCP_QDRANT_PATH": str(storage_base / "qdrant"),
        "PYTHONUNBUFFERED": "1",
    }

    if install_dir:
        env["PYTHONPATH"] = str(Path(install_dir) / "site-packages")
        env["SENTENCE_TRANSFORMERS_HOME"] = str(Path(install_dir) / "models")

    changed = enable_mcp_server(config, "daem0nchat", {
        "command": python_path,
        "args": ["-m", "daem0nmcp.server"],
        "env": env,
    })

    if changed:
        cdc.write(config)

    return changed


def remove_daemon_chat() -> bool:
    """
    Remove DaemonChat server entry from Claude Desktop config.

    Returns:
        True if config was modified, False if entry didn't exist.
    """
    try:
        cdc = ClaudeDesktopConfig()
        config = cdc.read()
    except FileNotFoundError:
        # No config file, nothing to remove
        return False
    except Exception:
        # Can't read config, can't remove
        return False

    changed = disable_mcp_server(config, "daem0nchat")

    if changed:
        cdc.write(config)

    return changed
