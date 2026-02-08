"""
Build orchestrator for DaemonChat Inno Setup installer.

This module prepares a staging directory containing:
- Embedded Python runtime (from python-build-standalone)
- Application code (daem0nmcp/ and installer/ directories)
- Dependencies installed to site-packages/
- Pre-downloaded embedding model

The staging directory is then compiled by Inno Setup (ISCC.exe) into a
Windows installer that bundles everything for offline installation.
"""

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# Constants
PYTHON_STANDALONE_VERSION = "3.12"
# NOTE: python-build-standalone URLs follow this pattern:
# https://github.com/astral-sh/python-build-standalone/releases/download/YYYYMMDD/
# cpython-3.12.X+YYYYMMDD-x86_64-pc-windows-msvc-shared-install_only.tar.gz
#
# You will need to update this URL to match the latest release at build time.
# Visit: https://github.com/astral-sh/python-build-standalone/releases
#
# Example for reference (update YYYYMMDD and patch version):
PYTHON_STANDALONE_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/20241002/cpython-3.12.7%2B20241002-x86_64-pc-windows-msvc-shared-install_only.tar.gz"

STAGING_DIR = Path("installer/inno/staging")
CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"


def download_python_standalone(staging_dir: Path) -> Optional[Path]:
    """
    Download python-build-standalone for Windows x86_64.

    This function downloads the Python runtime from Astral's python-build-standalone
    releases and extracts it to staging_dir/python/.

    NOTE: The PYTHON_STANDALONE_URL constant above may need updating at build time
    to match the latest release. Visit the GitHub releases page and update the URL.

    Args:
        staging_dir: Root staging directory

    Returns:
        Path to python.exe, or None if download/extraction fails
    """
    python_dir = staging_dir / "python"

    # Skip if already downloaded
    python_exe = python_dir / "python.exe"
    if python_exe.exists():
        print(f"Python runtime already exists at {python_exe}")
        return python_exe

    print("Downloading python-build-standalone...")
    print(f"  URL: {PYTHON_STANDALONE_URL}")

    try:
        # Download to temp file
        download_path = staging_dir / "python-standalone.tar.gz"
        urllib.request.urlretrieve(PYTHON_STANDALONE_URL, download_path)
        print(f"  Downloaded to {download_path}")

        # Extract using tar (requires tar.exe on Windows 10+)
        print(f"  Extracting to {python_dir}...")
        python_dir.mkdir(parents=True, exist_ok=True)

        # Use tarfile module for cross-platform extraction
        import tarfile
        with tarfile.open(download_path, "r:gz") as tar:
            # Extract all to a temp dir first
            temp_extract = staging_dir / "python_temp"
            tar.extractall(temp_extract)

            # Find the python directory (usually named "python")
            extracted_python = temp_extract / "python"
            if extracted_python.exists():
                # Move contents to python_dir
                for item in extracted_python.iterdir():
                    shutil.move(str(item), str(python_dir / item.name))
                shutil.rmtree(temp_extract)
            else:
                # If no "python" subdirectory, move everything directly
                for item in temp_extract.iterdir():
                    shutil.move(str(item), str(python_dir / item.name))
                shutil.rmtree(temp_extract)

        # Clean up download
        download_path.unlink()

        if python_exe.exists():
            print(f"  Python runtime ready at {python_exe}")
            return python_exe
        else:
            print("  ERROR: python.exe not found after extraction")
            return None

    except Exception as e:
        print(f"  ERROR downloading Python: {e}")
        return None


def generate_requirements(output_path: Path):
    """
    Generate requirements-dist.txt from pyproject.toml dependencies.

    This file includes the CPU-only PyTorch index URL to avoid downloading
    the massive CUDA wheel (~2GB vs ~200MB).

    Args:
        output_path: Path where requirements-dist.txt will be written
    """
    print("Generating requirements-dist.txt...")

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    dependencies = pyproject.get("project", {}).get("dependencies", [])

    # Write requirements with CPU-only torch index
    with open(output_path, "w") as f:
        f.write(f"--index-url {CPU_TORCH_INDEX}\n")
        f.write("--extra-index-url https://pypi.org/simple/\n")
        f.write("\n")
        for dep in dependencies:
            f.write(f"{dep}\n")

    print(f"  Generated {output_path} with {len(dependencies)} dependencies")


def install_dependencies(python_exe: Path, site_packages: Path):
    """
    Install dependencies into site-packages using embedded Python's pip.

    Uses CPU-only PyTorch index to avoid downloading CUDA wheels.

    Args:
        python_exe: Path to embedded python.exe
        site_packages: Target directory for installed packages
    """
    print("Installing dependencies...")

    requirements_file = STAGING_DIR / "requirements-dist.txt"

    if not requirements_file.exists():
        print("  ERROR: requirements-dist.txt not found")
        return

    site_packages.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_exe),
        "-m",
        "pip",
        "install",
        "--target",
        str(site_packages),
        "-r",
        str(requirements_file),
    ]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("  Dependencies installed successfully")
    else:
        print(f"  ERROR: pip install failed with code {result.returncode}")


def copy_application(staging_dir: Path):
    """
    Copy application code to staging directory.

    Copies:
    - daem0nmcp/ -> staging/app/daem0nmcp/
    - installer/ -> staging/installer/

    Excludes __pycache__, .pyc files, and test directories.

    Args:
        staging_dir: Root staging directory
    """
    print("Copying application code...")

    app_dir = staging_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    # Copy daem0nmcp package
    src_daem0nmcp = Path("daem0nmcp")
    dst_daem0nmcp = app_dir / "daem0nmcp"

    if dst_daem0nmcp.exists():
        shutil.rmtree(dst_daem0nmcp)

    shutil.copytree(
        src_daem0nmcp,
        dst_daem0nmcp,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test_*")
    )
    print(f"  Copied daem0nmcp/ to {dst_daem0nmcp}")

    # Copy installer package
    src_installer = Path("installer")
    dst_installer = staging_dir / "installer"

    if dst_installer.exists():
        shutil.rmtree(dst_installer)

    shutil.copytree(
        src_installer,
        dst_installer,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "build_mcpb.py",
            "build_inno.py",
            "inno",
            "mcpb"
        )
    )
    print(f"  Copied installer/ to {dst_installer}")


def download_embedding_model(staging_dir: Path):
    """
    Pre-download the embedding model for offline installation.

    This downloads the sentence-transformers model (~400MB) so users don't
    have to wait for first-run download.

    Args:
        staging_dir: Root staging directory
    """
    print("Downloading embedding model...")

    models_dir = staging_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    try:
        from installer.model_downloader import download_model, is_model_cached, DEFAULT_MODEL

        if is_model_cached(DEFAULT_MODEL, models_dir):
            print(f"  Model '{DEFAULT_MODEL}' already cached")
            return

        def progress_callback(message):
            print(f"  {message}")

        result = download_model(DEFAULT_MODEL, models_dir, progress_callback)

        if result:
            print(f"  Model downloaded to {result}")
        else:
            print("  WARNING: Model download failed (will download on first run)")

    except ImportError as e:
        print(f"  WARNING: Could not import model_downloader: {e}")
        print("  Model will be downloaded on first run")
    except Exception as e:
        print(f"  WARNING: Model download failed: {e}")
        print("  Model will be downloaded on first run")


def prepare_staging(skip_model: bool = False) -> Path:
    """
    Orchestrate staging directory preparation.

    Creates staging directory structure and populates with:
    - Python runtime
    - Requirements file
    - Installed dependencies
    - Application code
    - Pre-downloaded embedding model (unless skip_model=True)

    Args:
        skip_model: Skip model download for faster iteration

    Returns:
        Path to staging directory
    """
    print(f"Preparing staging directory: {STAGING_DIR}")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download Python runtime
    python_exe = download_python_standalone(STAGING_DIR)
    if not python_exe:
        print("ERROR: Failed to download Python runtime")
        sys.exit(1)

    # Step 2: Generate requirements file
    requirements_file = STAGING_DIR / "requirements-dist.txt"
    generate_requirements(requirements_file)

    # Step 3: Install dependencies
    site_packages = STAGING_DIR / "site-packages"
    install_dependencies(python_exe, site_packages)

    # Step 4: Copy application code
    copy_application(STAGING_DIR)

    # Step 5: Download embedding model
    if not skip_model:
        download_embedding_model(STAGING_DIR)
    else:
        print("Skipping model download (--skip-model)")

    print(f"\nStaging directory ready at {STAGING_DIR.absolute()}")
    return STAGING_DIR


def build(iscc_path: Optional[str] = None):
    """
    Build the Inno Setup installer.

    Prepares staging directory, then compiles the .iss script using ISCC.exe.

    Args:
        iscc_path: Path to ISCC.exe (optional, will auto-detect if not provided)
    """
    # Prepare staging
    staging_dir = prepare_staging()

    # Find ISCC.exe
    if not iscc_path:
        # Try standard locations
        possible_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]

        for path in possible_paths:
            if Path(path).exists():
                iscc_path = path
                break

    if not iscc_path or not Path(iscc_path).exists():
        print("\nStaging directory prepared successfully!")
        print("However, ISCC.exe was not found.")
        print("\nTo compile the installer:")
        print("  1. Install Inno Setup 6 from https://jrsoftware.org/isdl.php")
        print(f"  2. Run: ISCC.exe installer\\inno\\daem0n_chat.iss")
        print(f"\nOr run: python installer/build_inno.py --iscc-path <path-to-ISCC.exe>")
        return

    # Compile with ISCC
    print(f"\nCompiling installer with ISCC.exe...")
    iss_script = Path("installer/inno/daem0n_chat.iss")

    cmd = [iscc_path, str(iss_script.absolute())]
    print(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("\nInstaller built successfully!")
        print(f"  Output: installer\\inno\\Output\\DaemonChat-1.0.0-Setup.exe")
    else:
        print(f"\nERROR: ISCC failed with code {result.returncode}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build DaemonChat Inno Setup installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python installer/build_inno.py --stage-only
  python installer/build_inno.py --iscc-path "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
  python installer/build_inno.py --clean --skip-model
        """
    )

    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Prepare staging directory without compiling installer"
    )

    parser.add_argument(
        "--iscc-path",
        help="Path to ISCC.exe (Inno Setup compiler)"
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing staging directory before building"
    )

    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip embedding model download (faster iteration)"
    )

    args = parser.parse_args()

    # Clean if requested
    if args.clean and STAGING_DIR.exists():
        print(f"Removing existing staging directory: {STAGING_DIR}")
        shutil.rmtree(STAGING_DIR)

    # Stage-only mode
    if args.stage_only:
        prepare_staging(skip_model=args.skip_model)
        return

    # Full build
    build(iscc_path=args.iscc_path)


if __name__ == "__main__":
    main()
