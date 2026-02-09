"""
CLI entry point for DaemonChat installation and uninstallation.

This module provides a command-line interface for configuring Claude Desktop
with DaemonChat and verifying the installation.
"""

import sys
import argparse
from pathlib import Path

# Add parent directory, site-packages, and app to path so we can import
# installer modules, pip dependencies (claude_desktop_config), and daem0nmcp
_script_dir = Path(__file__).parent
_install_dir = _script_dir.parent
if str(_install_dir) not in sys.path:
    sys.path.insert(0, str(_install_dir))
_site_packages = _install_dir / "site-packages"
if _site_packages.exists() and str(_site_packages) not in sys.path:
    sys.path.insert(0, str(_site_packages))
_app_dir = _install_dir / "app"
if _app_dir.exists() and str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from installer.config_manager import add_daemon_chat, remove_daemon_chat
from installer.health_check import run_health_check


def install_command(args):
    """Handle install subcommand."""
    python_path = args.python_path or sys.executable
    install_dir = args.install_dir

    print(f"Installing DaemonChat...")
    print(f"  Python: {python_path}")
    if install_dir:
        print(f"  Install dir: {install_dir}")

    changed = add_daemon_chat(python_path, install_dir)

    if changed:
        print("\nDaemonChat has been configured for Claude Desktop!")
        print("Restart Claude Desktop to activate the server.")
    else:
        print("\nDaemonChat is already configured in Claude Desktop.")

    # Run health check unless skipped
    if not args.skip_health_check:
        print("\nRunning health checks...")
        results = run_health_check()

        print(f"  Python importable: {'PASS' if results['python_importable'][0] else 'FAIL'}")
        if not results['python_importable'][0]:
            print(f"    {results['python_importable'][1]}")

        print(f"  Storage writable: {'PASS' if results['storage_writable'][0] else 'FAIL'}")
        if not results['storage_writable'][0]:
            print(f"    {results['storage_writable'][1]}")

        print(f"  Config entry: {'PASS' if results['config_entry'][0] else 'FAIL'}")
        if not results['config_entry'][0]:
            print(f"    {results['config_entry'][1]}")

        if results['all_passed']:
            print("\nAll checks passed!")
            return 0
        else:
            print("\nSome checks failed. Installation may be incomplete.")
            return 1
    else:
        return 0


def uninstall_command(args):
    """Handle uninstall subcommand."""
    print("Uninstalling DaemonChat...")

    changed = remove_daemon_chat()

    if changed:
        print("DaemonChat has been removed from Claude Desktop configuration.")
        print("Restart Claude Desktop to complete the removal.")
    else:
        print("DaemonChat was not found in Claude Desktop configuration.")

    return 0


def check_command(args):
    """Handle check subcommand."""
    print("Running health checks...")
    results = run_health_check()

    print(f"\nPython importable: {'PASS' if results['python_importable'][0] else 'FAIL'}")
    if not results['python_importable'][0]:
        print(f"  {results['python_importable'][1]}")

    print(f"Storage writable: {'PASS' if results['storage_writable'][0] else 'FAIL'}")
    if not results['storage_writable'][0]:
        print(f"  {results['storage_writable'][1]}")

    print(f"Config entry: {'PASS' if results['config_entry'][0] else 'FAIL'}")
    if not results['config_entry'][0]:
        print(f"  {results['config_entry'][1]}")

    if results['all_passed']:
        print("\nAll checks passed!")
        return 0
    else:
        print("\nSome checks failed.")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="DaemonChat Installer",
        epilog="Use 'post_install.py <command> --help' for command-specific options."
    )

    # Support legacy-style args for Inno Setup compatibility
    parser.add_argument("--install-dir", dest="install_dir_legacy", metavar="DIR",
                       help="Installation directory (legacy mode)")
    parser.add_argument("--uninstall", dest="uninstall_legacy", action="store_true",
                       help="Uninstall mode (legacy)")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Install subcommand
    install_parser = subparsers.add_parser("install", help="Install DaemonChat")
    install_parser.add_argument("--python-path", help="Path to Python executable (default: current Python)")
    install_parser.add_argument("--install-dir", help="Installation directory for PYTHONPATH and models")
    install_parser.add_argument("--skip-health-check", action="store_true",
                               help="Skip post-install health checks")

    # Uninstall subcommand
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall DaemonChat")

    # Check subcommand
    check_parser = subparsers.add_parser("check", help="Run health checks")

    args = parser.parse_args()

    # Handle legacy mode
    if args.uninstall_legacy:
        args.command = "uninstall"
    elif args.install_dir_legacy and not args.command:
        args.command = "install"
        args.install_dir = args.install_dir_legacy
        args.python_path = None
        args.skip_health_check = False

    # Execute command
    if args.command == "install":
        return install_command(args)
    elif args.command == "uninstall":
        return uninstall_command(args)
    elif args.command == "check":
        return check_command(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
