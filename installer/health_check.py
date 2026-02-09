"""
Post-install verification for DaemonChat.

This module provides health checks to verify the installation was successful.
"""

import sys
from pathlib import Path

# Ensure site-packages and app dir are importable when run from installer context
_script_dir = Path(__file__).parent
_install_dir = _script_dir.parent
_site_packages = _install_dir / "site-packages"
if _site_packages.exists() and str(_site_packages) not in sys.path:
    sys.path.insert(0, str(_site_packages))
_app_dir = _install_dir / "app"
if _app_dir.exists() and str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))


def check_python_importable() -> tuple[bool, str]:
    """
    Verify daem0nmcp can be imported and server name is DaemonChat.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from daem0nmcp.mcp_instance import mcp
        if mcp.name == "DaemonChat":
            return (True, "OK")
        else:
            return (False, f"Server name is '{mcp.name}' (expected 'DaemonChat')")
    except ImportError as e:
        return (False, f"Import failed: {e}")
    except Exception as e:
        return (False, f"Unexpected error: {e}")


def check_storage_writable() -> tuple[bool, str]:
    """
    Verify the DaemonChat storage directory can be created and is writable.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Determine platform-specific storage path
        if sys.platform == "win32":
            storage_base = Path.home() / "AppData" / "Local" / "DaemonChat"
        elif sys.platform == "darwin":
            storage_base = Path.home() / "Library" / "Application Support" / "DaemonChat"
        else:  # Linux and others
            storage_base = Path.home() / ".local" / "share" / "DaemonChat"

        storage_dir = storage_base / "storage"

        # Create directory if it doesn't exist
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Try to create and delete a temp file
        test_file = storage_dir / ".health_check_test"
        test_file.write_text("test")
        test_file.unlink()

        return (True, "OK")
    except PermissionError:
        return (False, f"Permission denied: {storage_dir}")
    except Exception as e:
        return (False, f"Storage check failed: {e}")


def check_config_entry_exists() -> tuple[bool, str]:
    """
    Verify the daem0nchat entry exists in claude_desktop_config.json.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from installer.config_manager import get_claude_config_path
        from claude_desktop_config.api import ClaudeDesktopConfig

        config_path = get_claude_config_path()
        if not config_path.exists():
            return (False, f"Config file not found: {config_path}")

        cdc = ClaudeDesktopConfig()
        config = cdc.read()

        if "mcpServers" not in config:
            return (False, "No mcpServers section in config")

        if "daem0nchat" not in config["mcpServers"]:
            return (False, "daem0nchat entry not found in mcpServers")

        return (True, "OK")
    except ImportError as e:
        return (False, f"Import failed: {e}")
    except Exception as e:
        return (False, f"Config check failed: {e}")


def run_health_check() -> dict:
    """
    Run all health checks and return results.

    Returns:
        Dictionary with check results:
        {
            "python_importable": (bool, str),
            "storage_writable": (bool, str),
            "config_entry": (bool, str),
            "all_passed": bool
        }
    """
    results = {}

    try:
        results["python_importable"] = check_python_importable()
    except Exception as e:
        results["python_importable"] = (False, f"Check crashed: {e}")

    try:
        results["storage_writable"] = check_storage_writable()
    except Exception as e:
        results["storage_writable"] = (False, f"Check crashed: {e}")

    try:
        results["config_entry"] = check_config_entry_exists()
    except Exception as e:
        results["config_entry"] = (False, f"Check crashed: {e}")

    # All checks must pass
    results["all_passed"] = all(
        passed for passed, _ in [
            results["python_importable"],
            results["storage_writable"],
            results["config_entry"]
        ]
    )

    return results
