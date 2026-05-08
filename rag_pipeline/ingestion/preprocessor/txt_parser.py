"""
txt_parser.py — Read plain text files.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_txt(raw_path: Path) -> list[dict]:
    """
    Read a plain text file as a single text block.

    Returns a list of one dict representing a prose block, compatible
    with `text_chunker`.

    Returns
    -------
    list[dict]
        A list of one dict with keys: "text", "page_or_sheet"
    """
    logger.info(f"[extract_txt] Starting extraction for {raw_path}")

    try:
        # Try UTF-8 first, fallback to latin-1
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            logger.warning(f"[extract_txt] UTF-8 decoding failed for {raw_path.name}, falling back to latin-1")
            with open(raw_path, "r", encoding="latin-1") as f:
                text = f.read()

        logger.info(f"[extract_txt] Read {len(text)} characters from {raw_path.name}")
        
        return [{
            "text": text,
            "page_or_sheet": "null"
        }]

    except Exception as e:
        logger.error(f"[extract_txt] Failed to process {raw_path}: {e}")
        raise
