#!/usr/bin/env python3
"""Build script for DaemonChat MCPB Desktop Extension bundle.

This script prepares the project for MCPB packaging by:
1. Creating a clean build directory with only necessary source files
2. Creating a server.py wrapper at the root (MCPB entry point requirement)
3. Running the mcpb pack CLI command to generate the .mcpb bundle

NOTE: Requires the @anthropic-ai/mcpb CLI to be installed:
      npm install -g @anthropic-ai/mcpb
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def prepare_build_dir(build_dir: Path) -> None:
    """Prepare build directory with project source files.

    Args:
        build_dir: Temporary directory for build staging
    """
    project_root = Path(__file__).parent.parent

    print("Preparing build directory...")

    # Copy the daem0nmcp package
    src_pkg = project_root / "daem0nmcp"
    dst_pkg = build_dir / "daem0nmcp"

    def ignore_patterns(directory, files):
        """Ignore __pycache__ and .pyc files."""
        return [f for f in files if f == "__pycache__" or f.endswith(".pyc")]

    shutil.copytree(src_pkg, dst_pkg, ignore=ignore_patterns)
    print(f"  Copied daem0nmcp/ -> {dst_pkg.relative_to(build_dir)}")

    # Copy pyproject.toml
    shutil.copy(project_root / "pyproject.toml", build_dir / "pyproject.toml")
    print("  Copied pyproject.toml")

    # Copy manifest.json to build root
    shutil.copy(
        project_root / "installer" / "manifest.json",
        build_dir / "manifest.json"
    )
    print("  Copied manifest.json")

    # Create minimal server.py wrapper at build root (MCPB entry point)
    server_wrapper = build_dir / "server.py"
    server_wrapper.write_text(
        "#!/usr/bin/env python3\n"
        '"""MCPB entry point for DaemonChat server."""\n'
        "from daem0nmcp.server import main\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
    print("  Created server.py wrapper")


def build_mcpb(output_dir: Path = None) -> None:
    """Build the .mcpb bundle.

    Args:
        output_dir: Directory for output .mcpb file (default: project_root/dist/)
    """
    project_root = Path(__file__).parent.parent

    if output_dir is None:
        output_dir = project_root / "dist"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create temporary build directory
    build_dir = Path(tempfile.mkdtemp(prefix="daem0n_mcpb_"))

    try:
        # Prepare build directory
        prepare_build_dir(build_dir)

        # Run mcpb pack
        print("\nRunning mcpb pack...")
        try:
            result = subprocess.run(
                ["mcpb", "pack", str(build_dir)],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)

            # Find the generated .mcpb file
            mcpb_files = list(build_dir.glob("*.mcpb"))
            if not mcpb_files:
                print("ERROR: No .mcpb file was generated", file=sys.stderr)
                sys.exit(1)

            # Move to output directory
            mcpb_file = mcpb_files[0]
            output_path = output_dir / mcpb_file.name
            shutil.move(str(mcpb_file), str(output_path))

            print(f"\nBuilt: {output_path}")

        except FileNotFoundError:
            print(
                "\nERROR: mcpb CLI not found.",
                file=sys.stderr
            )
            print(
                "Install MCPB CLI: npm install -g @anthropic-ai/mcpb",
                file=sys.stderr
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"\nERROR: mcpb pack failed:", file=sys.stderr)
            print(e.stderr, file=sys.stderr)
            sys.exit(1)

    finally:
        # Clean up build directory
        shutil.rmtree(build_dir, ignore_errors=True)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build DaemonChat MCPB Desktop Extension bundle"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for .mcpb file (default: dist/)"
    )

    args = parser.parse_args()
    build_mcpb(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
