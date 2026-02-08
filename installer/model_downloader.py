"""
Embedding model pre-download with progress reporting.

This module provides functions to pre-download the sentence-transformers
embedding model used by DaemonChat. Primarily for Inno Setup distribution;
MCPB path relies on auto-download on first use.
"""

import sys
from pathlib import Path

# Determine platform-specific default models directory
if sys.platform == "win32":
    DEFAULT_MODELS_DIR = Path.home() / "AppData" / "Local" / "DaemonChat" / "models"
elif sys.platform == "darwin":
    DEFAULT_MODELS_DIR = Path.home() / "Library" / "Application Support" / "DaemonChat" / "models"
else:  # Linux and others
    DEFAULT_MODELS_DIR = Path.home() / ".local" / "share" / "DaemonChat" / "models"

DEFAULT_MODEL = "nomic-ai/modernbert-embed-base"


def is_model_cached(model_name: str = DEFAULT_MODEL, models_dir: Path = None) -> bool:
    """
    Check if the model is already cached.

    Args:
        model_name: Model identifier (default: nomic-ai/modernbert-embed-base)
        models_dir: Directory for model cache (default: platform-specific)

    Returns:
        True if model is cached, False otherwise.
    """
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR

    # Sentence-transformers cache structure: models--{org}--{model}/snapshots/
    cache_name = f"models--{model_name.replace('/', '--')}"
    model_dir = models_dir / cache_name / "snapshots"

    return model_dir.exists() and any(model_dir.iterdir())


def download_model(model_name: str = DEFAULT_MODEL, models_dir: Path = None, callback: callable = None) -> Path | None:
    """
    Download the embedding model using huggingface_hub.

    Args:
        model_name: Model identifier (default: nomic-ai/modernbert-embed-base)
        models_dir: Directory for model cache (default: platform-specific)
        callback: Optional callback function(message: str) for progress updates

    Returns:
        Path to downloaded model directory, or None on failure.
    """
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR

    try:
        from huggingface_hub import snapshot_download

        if callback:
            callback(f"Downloading model '{model_name}'...")

        # Create cache directory
        models_dir.mkdir(parents=True, exist_ok=True)

        # Download model
        model_path = snapshot_download(
            repo_id=model_name,
            cache_dir=str(models_dir),
            resume_download=True,
        )

        if callback:
            callback("Download complete.")

        return Path(model_path)

    except ImportError:
        if callback:
            callback("Download failed: huggingface_hub not installed")
        return None
    except Exception as e:
        if callback:
            callback(f"Download failed: {e}")
        return None


def download_with_console_progress(model_name: str = DEFAULT_MODEL, models_dir: Path = None):
    """
    Download model with console progress output.

    Convenience wrapper that prints progress to stdout.
    Suitable for use from post_install.py or Inno Setup hooks.

    Args:
        model_name: Model identifier (default: nomic-ai/modernbert-embed-base)
        models_dir: Directory for model cache (default: platform-specific)
    """
    if is_model_cached(model_name, models_dir):
        print(f"Model '{model_name}' is already cached.")
        return

    def progress_callback(message):
        print(f"  {message}")

    result = download_model(model_name, models_dir, progress_callback)

    if result:
        print(f"Model downloaded to: {result}")
    else:
        print("Model download failed.")


if __name__ == "__main__":
    download_with_console_progress()
