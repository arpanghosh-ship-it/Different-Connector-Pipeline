"""
file_io.py — Read-only access to the connector's storage folder.

Reads `normalized.json` and locates the raw file for a given folder number.
Uses pathlib exclusively to resolve paths. Read-only by design.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_storage_folder(folder_number: int) -> tuple[dict, Path]:
    """
    Load normalized.json and locate the raw file for a given folder number.

    Reads STORAGE_BASE_PATH from the environment. Since the environment
    variable is an absolute path, it works reliably from anywhere.

    Parameters
    ----------
    folder_number : int
        The integer folder ID in the connector's storage directory (e.g. 24).

    Returns
    -------
    tuple[dict, Path]
        A tuple containing:
        - normalized_dict: The parsed JSON contents of normalized.json.
        - raw_file_path: A resolved pathlib.Path to the raw file (e.g. raw.pdf).

    Raises
    ------
    FileNotFoundError
        If the folder, normalized.json, or the raw file does not exist.
    ValueError
        If normalized.json cannot be parsed, or if STORAGE_BASE_PATH is not set.
    """
    try:
        base_path_str = os.getenv("STORAGE_BASE_PATH")
        if not base_path_str:
            raise ValueError("STORAGE_BASE_PATH environment variable is not set")

        base_path = Path(base_path_str).resolve()
        folder_path = base_path / str(folder_number)

        if not folder_path.exists() or not folder_path.is_dir():
            raise FileNotFoundError(f"Storage folder not found: {folder_path}")

        # 1. Load normalized.json
        json_path = folder_path / "normalized.json"
        if not json_path.exists():
            raise FileNotFoundError(f"normalized.json not found in {folder_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            try:
                normalized = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse normalized.json in {folder_path}: {e}")

        # 2. Locate raw file
        # The spec states the raw file is named 'raw.{ext}' where {ext} is the extension.
        # It's safest to glob for 'raw.*' and take the first match.
        raw_files = list(folder_path.glob("raw.*"))
        if not raw_files:
            raise FileNotFoundError(f"No raw file (raw.*) found in {folder_path}")

        raw_path = raw_files[0]

        # 3. Log essential metadata
        file_name = normalized.get("file_name", "unknown")
        file_type = normalized.get("file_type", "unknown")
        status = normalized.get("content_status", "unknown")
        
        logger.info(
            f"[load_storage_folder] Folder {folder_number} loaded — "
            f"file: {file_name!r}, type: {file_type}, status: {status}"
        )

        return normalized, raw_path

    except Exception as e:
        logger.error(f"[load_storage_folder] Failed to load folder {folder_number}: {e}")
        raise
