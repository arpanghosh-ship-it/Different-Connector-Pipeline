"""
table_chunker.py — Chunk tabular data (XLSX, CSV, PDF tables) into rows.

Custom chunker. LangChain is NOT used here because it cannot preserve
row boundaries. Each chunk produced represents exactly one row.
"""

import logging

logger = logging.getLogger(__name__)


def chunk_table_rows(headers: list[str], rows: list[list]) -> list[str]:
    """
    Convert tabular data into one chunk string per row.

    Every chunk string follows this exact format:
        "Headers: col1 | col2 | col3\\nRow: val1 | val2 | val3"

    Rules:
    - Join header names with " | ".
    - Join row values (cast each to str) with " | ".
    - Skip rows where ALL values are empty, None, or NaN.
    - Never split a row across multiple chunks.

    Parameters
    ----------
    headers : list[str]
        The column names.
    rows : list[list]
        A list of rows, where each row is a list of values.

    Returns
    -------
    list[str]
        A list of formatted chunk strings (one per valid row).
    """
    try:
        if not headers or not rows:
            return []

        # Convert headers to string and join
        headers_str = " | ".join(str(h).strip() for h in headers)
        header_prefix = f"Headers: {headers_str}\nRow: "

        chunks = []
        for row in rows:
            # Check if row is completely empty
            is_empty = True
            row_str_values = []
            
            for val in row:
                if val is None:
                    str_val = ""
                else:
                    # Handle pandas NaN/NaT without importing pandas here
                    # by checking common string representations
                    str_val = str(val).strip()
                    if str_val in ("nan", "NaN", "NaT", "<NA>"):
                        str_val = ""
                        
                row_str_values.append(str_val)
                if str_val:
                    is_empty = False

            if is_empty:
                continue

            row_str = " | ".join(row_str_values)
            chunk_content = f"{header_prefix}{row_str}"
            chunks.append(chunk_content)

        return chunks

    except Exception as e:
        logger.error(f"[chunk_table_rows] Failed to chunk table rows: {e}")
        raise
