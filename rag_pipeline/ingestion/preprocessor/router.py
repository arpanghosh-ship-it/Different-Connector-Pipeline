"""
router.py — Route a file to the correct parser based on file_type.
"""

import logging
from pathlib import Path

from ingestion.preprocessor.pdf_parser import extract_pdf
from ingestion.preprocessor.xlsx_parser import extract_xlsx
from ingestion.preprocessor.csv_parser import extract_csv
from ingestion.preprocessor.txt_parser import extract_txt
from ingestion.preprocessor.image_parser import extract_image

logger = logging.getLogger(__name__)


def extract_file(file_type: str, raw_path: Path, openai_client) -> list[dict]:
    """
    Route a file to the correct parser based on file_type.

    Supported types: pdf, xlsx, csv, txt, png, jpg

    Each returned dict will have EITHER:
        {"text": str, "page_or_sheet": str, "is_tabular": bool (optional)}
        — for prose/PDF pages
    OR:
        {"headers": list, "rows": list[list], "page_or_sheet": str}
        — for tabular data

    Parameters
    ----------
    file_type : str
        The lowercase extension without dot (e.g. "pdf").
    raw_path : Path
        The resolved Path to the raw file.
    openai_client : openai.OpenAI
        The initialized OpenAI client for vision OCR.

    Returns
    -------
    list[dict]
        Extracted content blocks.

    Raises
    ------
    ValueError
        If the file_type is not supported.
    """
    try:
        if file_type == "pdf":
            return extract_pdf(raw_path, openai_client)
        elif file_type == "xlsx":
            return extract_xlsx(raw_path)
        elif file_type == "csv":
            return extract_csv(raw_path)
        elif file_type == "txt":
            return extract_txt(raw_path)
        elif file_type in ("png", "jpg", "jpeg"):
            return extract_image(raw_path, openai_client)
        else:
            logger.warning(f"[extract_file] Unsupported file type: {file_type} for {raw_path}")
            raise ValueError(f"Unsupported file type: {file_type}")
            
    except Exception as e:
        # Avoid double-logging if the underlying parser already logged the error,
        # but re-raise with full context in case it wasn't caught.
        logger.error(f"[extract_file] Routing failed for {file_type} file {raw_path}: {e}")
        raise
