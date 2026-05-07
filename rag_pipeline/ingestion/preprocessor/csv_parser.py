"""
csv_parser.py — Extract tabular data from CSV files using pandas.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


def extract_csv(raw_path: Path) -> list[dict]:
    """
    Extract a CSV file as tabular data.

    Returns a list containing one dict representing a tabular page,
    compatible with `table_chunker`.

    Returns
    -------
    list[dict]
        A list of one dict with keys: "headers", "rows", "page_or_sheet"
    """
    logger.info(f"[extract_csv] Starting extraction for {raw_path}")

    try:
        # Try UTF-8 first, fallback to latin-1
        try:
            df = pd.read_csv(raw_path, encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(f"[extract_csv] UTF-8 decoding failed for {raw_path.name}, falling back to latin-1")
            df = pd.read_csv(raw_path, encoding="latin-1")

        # Drop completely empty rows
        df = df.dropna(how="all")
        
        # Extract headers and cast to string
        headers = [str(col) for col in df.columns]
        
        # Extract rows and cast all values to string
        df_clean = df.fillna("")
        rows = df_clean.values.tolist()
        str_rows = [[str(val) for val in row] for row in rows]
        
        logger.info(f"[extract_csv] Extracted {len(str_rows)} rows from {raw_path.name}")
        
        return [{
            "headers": headers,
            "rows": str_rows,
            "page_or_sheet": "csv"
        }]

    except Exception as e:
        logger.error(f"[extract_csv] Failed to process {raw_path}: {e}")
        raise
