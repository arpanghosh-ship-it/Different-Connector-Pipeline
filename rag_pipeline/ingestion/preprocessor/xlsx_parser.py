"""
xlsx_parser.py — Extract tabular data from Excel spreadsheets using pandas.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


def extract_xlsx(raw_path: Path) -> list[dict]:
    """
    Extract all sheets from an Excel file as tabular data.

    Returns a list of dicts representing tabular pages, compatible with `table_chunker`.

    Returns
    -------
    list[dict]
        A list of dicts with keys: "headers", "rows", "page_or_sheet"
    """
    logger.info(f"[extract_xlsx] Starting extraction for {raw_path}")
    results = []

    try:
        # sheet_name=None reads all sheets into a dict of DataFrames
        all_sheets = pd.read_excel(raw_path, sheet_name=None)
        
        for sheet_name, df in all_sheets.items():
            # Drop completely empty rows
            df = df.dropna(how="all")
            
            # Extract headers and cast to string
            headers = [str(col) for col in df.columns]
            
            # Extract rows and cast all values to string (handling NaNs as empty strings)
            # Fillna to prevent pandas from exporting 'nan' strings
            df_clean = df.fillna("")
            rows = df_clean.values.tolist()
            
            # Make sure we convert everything to strictly string so downstream logic is happy
            str_rows = [[str(val) for val in row] for row in rows]
            
            results.append({
                "headers": headers,
                "rows": str_rows,
                "page_or_sheet": str(sheet_name)
            })

        logger.info(f"[extract_xlsx] Extracted {len(all_sheets)} sheets from {raw_path.name}")
        return results

    except Exception as e:
        logger.error(f"[extract_xlsx] Failed to process {raw_path}: {e}")
        raise
