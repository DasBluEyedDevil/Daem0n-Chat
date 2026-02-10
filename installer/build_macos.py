"""
Build orchestrator for DaemonChat macOS .pkg installer.

This module prepares a staging directory containing:
- Embedded Python runtime (from python-build-standalone, macOS build)
- Application code (daem0nmcp/ and installer/ directories)
- Dependencies installed to site-packages/

The staging directory is then packaged by pkgbuild + productbuild into a
macOS .pkg installer that bundles everything for offline installation.
"""

import argparse
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# Ensure project root is on path for imports (needed when running as script)
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Constants
PYTHON_STANDALONE_VERSION = "3.12"
# python-build-standalone URLs for macOS builds.
# Update the date/patch version to match the latest release at build time.
# Visit: https://github.com/astral-sh/python-build-standalone/releases
PYTHON_STANDALONE_URLS = {
    "arm64": "https://github.com/astral-sh/python-build-standalone/releases/download/20241002/cpython-3.12.7%2B20241002-aarch64-apple-darwin-install_only.tar.gz",
    "x86_64": "https://github.com/astral-sh/python-build-standalone/releases/download/20241002/cpython-3.12.7%2B20241002-x86_64-apple-darwin-install_only.tar.gz",
}

STAGING_DIR = Path("installer/macos/staging")
CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"

# pkg metadata
PKG_IDENTIFIER = "chat.daemon.DaemonChat"
PKG_VERSION = "1.0.0"
# Install to user's Application Support (no admin required)
PKG_INSTALL_LOCATION = "/Library/Application Support/DaemonChat"


def download_python_standalone(staging_dir: Path, arch: str) -> Path | None:
    """
    Download python-build-standalone for macOS.

    Args:
        staging_dir: Root staging directory
        arch: Target architecture ('arm64' or 'x86_64')

    Returns:
        Path to python3 binary, or None if download/extraction fails
    """
    python_dir = staging_dir / "python"
    python_bin = python_dir / "bin" / "python3"

    if python_bin.exists():
        print(f"Python runtime already exists at {python_bin}")
        return python_bin

    url = PYTHON_STANDALONE_URLS.get(arch)
    if not url:
        print(f"ERROR: Unknown architecture '{arch}'. Expected 'arm64' or 'x86_64'.")
        return None

    print(f"Downloading python-build-standalone for macOS {arch}...")
    print(f"  URL: {url}")

    try:
        download_path = staging_dir / "python-standalone.tar.gz"
        urllib.request.urlretrieve(url, download_path)
        print(f"  Downloaded to {download_path}")

        print(f"  Extracting to {python_dir}...")
        python_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(download_path, "r:gz") as tar:
            temp_extract = staging_dir / "python_temp"
            tar.extractall(temp_extract)

            # python-build-standalone extracts to a "python" subdirectory
            extracted_python = temp_extract / "python"
            if extracted_python.exists():
                for item in extracted_python.iterdir():
                    shutil.move(str(item), str(python_dir / item.name))
                shutil.rmtree(temp_extract)
            else:
                for item in temp_extract.iterdir():
                    shutil.move(str(item), str(python_dir / item.name))
                shutil.rmtree(temp_extract)

        download_path.unlink()

        if python_bin.exists():
            print(f"  Python runtime ready at {python_bin}")
            return python_bin
        else:
            print("  ERROR: python3 not found after extraction")
            return None

    except Exception as e:
        print(f"  ERROR downloading Python: {e}")
        return None


def generate_requirements(output_path: Path):
    """
    Generate requirements-dist.txt from pyproject.toml dependencies.

    Includes CPU-only PyTorch index to avoid massive CUDA wheels.

    Args:
        output_path: Path where requirements-dist.txt will be written
    """
    print("Generating requirements-dist.txt...")

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    dependencies = pyproject.get("project", {}).get("dependencies", [])

    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    installer_deps = optional_deps.get("installer", [])

    with open(output_path, "w") as f:
        f.write(f"--index-url {CPU_TORCH_INDEX}\n")
        f.write("--extra-index-url https://pypi.org/simple/\n")
        f.write("\n")
        for dep in dependencies:
            f.write(f"{dep}\n")

        if installer_deps:
            f.write("\n# Installer dependencies\n")
            for dep in installer_deps:
                f.write(f"{dep}\n")

    total_deps = len(dependencies) + len(installer_deps)
    print(f"  Generated {output_path} with {total_deps} dependencies")


def install_dependencies(python_exe: Path, site_packages: Path, requirements_file: Path):
    """
    Install dependencies into site-packages using embedded Python's pip.

    Args:
        python_exe: Path to embedded python3
        site_packages: Target directory for installed packages
        requirements_file: Path to requirements-dist.txt
    """
    print("Installing dependencies...")

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
        "--no-compile",
        "-r",
        str(requirements_file),
    ]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("  Dependencies installed successfully")
    else:
        print(f"  ERROR: pip install failed with code {result.returncode}")


def strip_unnecessary_files(site_packages: Path):
    """
    Remove test files, __pycache__, and other unnecessary files to reduce size.

    Args:
        site_packages: Path to site-packages directory
    """
    print("Stripping unnecessary files from site-packages...")

    removed_count = 0
    removed_size = 0

    patterns_to_remove = [
        "**/__pycache__",
        "**/tests",
        "**/test",
        "**/*.pyc",
        "**/*.pyo",
    ]

    for pattern in patterns_to_remove:
        for path in site_packages.glob(pattern):
            try:
                if path.is_dir():
                    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                    shutil.rmtree(path)
                else:
                    size = path.stat().st_size
                    path.unlink()
                removed_count += 1
                removed_size += size
            except Exception as e:
                print(f"  Warning: Could not remove {path}: {e}")

    removed_mb = removed_size / (1024 * 1024)
    print(f"  Removed {removed_count} items ({removed_mb:.1f} MB)")


def copy_application(staging_dir: Path):
    """
    Copy application code to staging directory.

    Copies:
    - daem0nmcp/ -> staging/app/daem0nmcp/
    - installer/ -> staging/installer/ (excluding build scripts and platform dirs)

    Args:
        staging_dir: Root staging directory
    """
    print("Copying application code...")

    app_dir = staging_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    # Copy daem0nmcp package
    src_daem0nmcp = PROJECT_ROOT / "daem0nmcp"
    dst_daem0nmcp = app_dir / "daem0nmcp"

    if dst_daem0nmcp.exists():
        shutil.rmtree(dst_daem0nmcp)

    shutil.copytree(
        src_daem0nmcp,
        dst_daem0nmcp,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test_*")
    )
    print(f"  Copied daem0nmcp/ to {dst_daem0nmcp}")

    # Copy installer package (excluding build scripts and platform-specific dirs)
    src_installer = PROJECT_ROOT / "installer"
    dst_installer = staging_dir / "installer"

    if dst_installer.exists():
        shutil.rmtree(dst_installer)

    shutil.copytree(
        src_installer,
        dst_installer,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "build_inno.py",
            "build_macos.py",
            "inno",
            "macos",
            "mcpb"
        )
    )
    print(f"  Copied installer/ to {dst_installer}")


def prepare_staging(arch: str) -> Path:
    """
    Orchestrate staging directory preparation for macOS.

    Args:
        arch: Target architecture ('arm64' or 'x86_64')

    Returns:
        Path to staging directory
    """
    print(f"Preparing macOS staging directory: {STAGING_DIR} (arch: {arch})")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download Python runtime
    python_exe = download_python_standalone(STAGING_DIR, arch)
    if not python_exe:
        print("ERROR: Failed to download Python runtime")
        sys.exit(1)

    # Step 2: Generate requirements file
    requirements_file = STAGING_DIR / "requirements-dist.txt"
    generate_requirements(requirements_file)

    # Step 3: Install dependencies
    site_packages = STAGING_DIR / "site-packages"
    install_dependencies(python_exe, site_packages, requirements_file)

    # Step 4: Strip unnecessary files
    strip_unnecessary_files(site_packages)

    # Step 5: Copy application code
    copy_application(STAGING_DIR)

    # Note: Model is downloaded during installation by postinstall script
    print("Skipping model bundling (downloaded during install by postinstall script)")

    print(f"\nStaging directory ready at {STAGING_DIR.absolute()}")
    return STAGING_DIR


def build_pkg(arch: str, signing_identity: str | None = None):
    """
    Build the macOS .pkg installer.

    Prepares staging, then uses pkgbuild + productbuild to create the package.

    Args:
        arch: Target architecture ('arm64' or 'x86_64')
        signing_identity: Optional Developer ID Installer identity for signing
    """
    staging_dir = prepare_staging(arch)

    output_dir = Path("installer/macos/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    scripts_dir = Path("installer/macos/scripts")
    distribution_xml = Path("installer/macos/distribution.xml")

    # Step 1: Build component package with pkgbuild
    component_pkg = output_dir / "DaemonChat-component.pkg"
    print(f"\nBuilding component package...")

    pkgbuild_cmd = [
        "pkgbuild",
        "--root", str(staging_dir),
        "--identifier", PKG_IDENTIFIER,
        "--version", PKG_VERSION,
        "--install-location", PKG_INSTALL_LOCATION,
        "--scripts", str(scripts_dir),
        str(component_pkg),
    ]

    print(f"  Running: {' '.join(pkgbuild_cmd)}")
    result = subprocess.run(pkgbuild_cmd, capture_output=False)

    if result.returncode != 0:
        print(f"  ERROR: pkgbuild failed with code {result.returncode}")
        sys.exit(1)

    # Step 2: Build product archive with productbuild
    arch_suffix = "arm64" if arch == "arm64" else "x86_64"
    unsigned_pkg = output_dir / f"DaemonChat-{PKG_VERSION}-{arch_suffix}-unsigned.pkg"
    final_pkg = output_dir / f"DaemonChat-{PKG_VERSION}-{arch_suffix}.pkg"

    print(f"Building product archive...")

    productbuild_cmd = [
        "productbuild",
        "--distribution", str(distribution_xml),
        "--package-path", str(output_dir),
        str(unsigned_pkg),
    ]

    print(f"  Running: {' '.join(productbuild_cmd)}")
    result = subprocess.run(productbuild_cmd, capture_output=False)

    if result.returncode != 0:
        print(f"  ERROR: productbuild failed with code {result.returncode}")
        sys.exit(1)

    # Step 3: Sign if identity provided
    if signing_identity:
        print(f"Signing package with identity: {signing_identity}")

        productsign_cmd = [
            "productsign",
            "--sign", signing_identity,
            str(unsigned_pkg),
            str(final_pkg),
        ]

        print(f"  Running: {' '.join(productsign_cmd)}")
        result = subprocess.run(productsign_cmd, capture_output=False)

        if result.returncode != 0:
            print(f"  ERROR: productsign failed with code {result.returncode}")
            sys.exit(1)

        # Remove unsigned package
        unsigned_pkg.unlink()
        print(f"\nSigned installer built: {final_pkg}")
    else:
        # Rename unsigned to final
        unsigned_pkg.rename(final_pkg)
        print(f"\nUnsigned installer built: {final_pkg}")
        print("  Note: Users will see a Gatekeeper warning without code signing.")

    # Clean up component package
    component_pkg.unlink(missing_ok=True)

    print(f"  Output: {final_pkg}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build DaemonChat macOS .pkg installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python installer/build_macos.py --arch arm64 --stage-only
  python installer/build_macos.py --arch x86_64
  python installer/build_macos.py --arch arm64 --sign "Developer ID Installer: Your Name (TEAMID)"
  python installer/build_macos.py --clean --arch arm64
        """
    )

    parser.add_argument(
        "--arch",
        required=True,
        choices=["arm64", "x86_64"],
        help="Target architecture"
    )

    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Prepare staging directory without building .pkg"
    )

    parser.add_argument(
        "--sign",
        metavar="IDENTITY",
        help="Developer ID Installer identity for signing (e.g. 'Developer ID Installer: Name (TEAMID)')"
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing staging directory before building"
    )

    args = parser.parse_args()

    if args.clean and STAGING_DIR.exists():
        print(f"Removing existing staging directory: {STAGING_DIR}")
        shutil.rmtree(STAGING_DIR)

    if args.stage_only:
        prepare_staging(args.arch)
        return

    build_pkg(arch=args.arch, signing_identity=args.sign)


if __name__ == "__main__":
    main()
