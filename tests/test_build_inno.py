"""
Tests for Inno Setup build orchestrator.
"""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from installer.build_inno import (
    copy_application,
    generate_requirements,
    prepare_staging,
    CPU_TORCH_INDEX,
)


def test_generate_requirements_includes_cpu_torch(tmp_path):
    """Verify requirements file includes CPU-only PyTorch index."""
    # Create a minimal pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
dependencies = [
    "fastmcp>=3.0.0",
    "torch>=2.0.0",
]
""")

    output_file = tmp_path / "requirements-dist.txt"

    # Patch Path("pyproject.toml") to return our test file
    with patch("installer.build_inno.Path") as mock_path_class:
        mock_path_class.return_value = pyproject
        generate_requirements(output_file)

    content = output_file.read_text()

    # Verify CPU torch index is present
    assert f"--index-url {CPU_TORCH_INDEX}" in content
    assert "--extra-index-url https://pypi.org/simple/" in content


def test_generate_requirements_includes_all_deps(tmp_path):
    """Verify requirements file includes all project dependencies."""
    # Create a pyproject.toml with key dependencies
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
dependencies = [
    "fastmcp>=3.0.0",
    "sqlalchemy>=2.0.0",
    "sentence-transformers>=3.0.0",
    "qdrant-client>=1.7.0",
]
""")

    output_file = tmp_path / "requirements-dist.txt"

    with patch("installer.build_inno.Path") as mock_path_class:
        mock_path_class.return_value = pyproject
        generate_requirements(output_file)

    content = output_file.read_text()

    # Verify all key dependencies are present
    assert "fastmcp>=3.0.0" in content
    assert "sqlalchemy>=2.0.0" in content
    assert "sentence-transformers>=3.0.0" in content
    assert "qdrant-client>=1.7.0" in content


def test_copy_application_excludes_pycache(tmp_path):
    """Verify __pycache__ directories are excluded from copied application."""
    # Create mock source structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    daem0nmcp_dir = src_dir / "daem0nmcp"
    daem0nmcp_dir.mkdir()

    # Create some Python files
    (daem0nmcp_dir / "server.py").write_text("# server code")
    (daem0nmcp_dir / "models.py").write_text("# models code")

    # Create __pycache__ directory
    pycache_dir = daem0nmcp_dir / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "server.cpython-312.pyc").write_text("bytecode")

    # Create installer directory
    installer_dir = src_dir / "installer"
    installer_dir.mkdir()
    (installer_dir / "post_install.py").write_text("# installer")

    # Create staging directory
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    # Patch Path to use our test directories
    with patch("installer.build_inno.Path") as mock_path:
        def path_side_effect(arg):
            if arg == "daem0nmcp":
                return daem0nmcp_dir
            elif arg == "installer":
                return installer_dir
            else:
                return Path(arg)

        mock_path.side_effect = path_side_effect

        copy_application(staging_dir)

    # Verify daem0nmcp was copied
    dst_daem0nmcp = staging_dir / "app" / "daem0nmcp"
    assert dst_daem0nmcp.exists()
    assert (dst_daem0nmcp / "server.py").exists()
    assert (dst_daem0nmcp / "models.py").exists()

    # Verify __pycache__ was excluded
    assert not (dst_daem0nmcp / "__pycache__").exists()


def test_copy_application_excludes_test_files(tmp_path):
    """Verify test files are excluded from copied application."""
    # Create mock source structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    daem0nmcp_dir = src_dir / "daem0nmcp"
    daem0nmcp_dir.mkdir()

    # Create regular files
    (daem0nmcp_dir / "server.py").write_text("# server code")

    # Create test files/directories
    (daem0nmcp_dir / "test_server.py").write_text("# test code")
    tests_dir = daem0nmcp_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_models.py").write_text("# test code")

    # Create installer directory
    installer_dir = src_dir / "installer"
    installer_dir.mkdir()
    (installer_dir / "post_install.py").write_text("# installer")

    # Create staging directory
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    # Patch Path to use our test directories
    with patch("installer.build_inno.Path") as mock_path:
        def path_side_effect(arg):
            if arg == "daem0nmcp":
                return daem0nmcp_dir
            elif arg == "installer":
                return installer_dir
            else:
                return Path(arg)

        mock_path.side_effect = path_side_effect

        copy_application(staging_dir)

    # Verify regular files were copied
    dst_daem0nmcp = staging_dir / "app" / "daem0nmcp"
    assert (dst_daem0nmcp / "server.py").exists()

    # Verify test files/directories were excluded
    assert not (dst_daem0nmcp / "test_server.py").exists()
    assert not (dst_daem0nmcp / "tests").exists()


def test_staging_dir_structure(tmp_path, monkeypatch):
    """Verify prepare_staging creates expected directory structure."""
    # Change to tmp_path as working directory
    monkeypatch.chdir(tmp_path)

    # Create minimal pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
dependencies = ["fastmcp>=3.0.0"]
""")

    # Create minimal source structure
    daem0nmcp_dir = tmp_path / "daem0nmcp"
    daem0nmcp_dir.mkdir()
    (daem0nmcp_dir / "server.py").write_text("# server")

    installer_dir = tmp_path / "installer"
    installer_dir.mkdir()
    (installer_dir / "post_install.py").write_text("# installer")

    # Mock the download and install functions to avoid network calls
    with patch("installer.build_inno.download_python_standalone") as mock_download:
        with patch("installer.build_inno.install_dependencies") as mock_install:
            with patch("installer.build_inno.download_embedding_model") as mock_model:
                # Mock returns
                mock_python_exe = tmp_path / "installer" / "inno" / "staging" / "python" / "python.exe"
                mock_python_exe.parent.mkdir(parents=True, exist_ok=True)
                mock_python_exe.touch()
                mock_download.return_value = mock_python_exe

                # Mock install_dependencies to create site-packages directory
                def mock_install_side_effect(python_exe, site_packages):
                    site_packages.mkdir(parents=True, exist_ok=True)

                mock_install.side_effect = mock_install_side_effect

                # Run prepare_staging with skip_model to avoid model download
                staging_dir = prepare_staging(skip_model=True)

                # Verify directory structure
                assert staging_dir.exists()
                assert (staging_dir / "python").exists()
                assert (staging_dir / "python" / "python.exe").exists()
                assert (staging_dir / "app").exists()
                assert (staging_dir / "app" / "daem0nmcp").exists()
                assert (staging_dir / "installer").exists()
                assert (staging_dir / "site-packages").exists()
                assert (staging_dir / "requirements-dist.txt").exists()

                # Verify model download was skipped
                mock_model.assert_not_called()


def test_staging_dir_with_model_download(tmp_path, monkeypatch):
    """Verify prepare_staging calls model download when not skipped."""
    monkeypatch.chdir(tmp_path)

    # Create minimal pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
dependencies = ["fastmcp>=3.0.0"]
""")

    # Create minimal source structure
    daem0nmcp_dir = tmp_path / "daem0nmcp"
    daem0nmcp_dir.mkdir()
    (daem0nmcp_dir / "server.py").write_text("# server")

    installer_dir = tmp_path / "installer"
    installer_dir.mkdir()
    (installer_dir / "post_install.py").write_text("# installer")

    # Mock all external operations
    with patch("installer.build_inno.download_python_standalone") as mock_download:
        with patch("installer.build_inno.install_dependencies") as mock_install:
            with patch("installer.build_inno.download_embedding_model") as mock_model:
                # Mock returns
                mock_python_exe = tmp_path / "installer" / "inno" / "staging" / "python" / "python.exe"
                mock_python_exe.parent.mkdir(parents=True, exist_ok=True)
                mock_python_exe.touch()
                mock_download.return_value = mock_python_exe

                # Run prepare_staging WITHOUT skip_model
                staging_dir = prepare_staging(skip_model=False)

                # Verify model download was called
                mock_model.assert_called_once()
