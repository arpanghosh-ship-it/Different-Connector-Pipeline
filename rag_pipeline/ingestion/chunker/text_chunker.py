"""
text_chunker.py — Chunk prose text using LangChain.

This is the ONLY file in the entire project that imports or uses LangChain.
It provides `RecursiveCharacterTextSplitter` to safely split text into
overlapping chunks without breaking words or sentences where possible.
"""

import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


def chunk_text(text: str) -> list[str]:
    """
    Split prose text into overlapping chunks.

    Uses LangChain's RecursiveCharacterTextSplitter with:
      - chunk_size: 600 characters
      - chunk_overlap: 80 characters
      - separators: ["\\n\\n", "\\n", ". ", " ", ""]

    Parameters
    ----------
    text : str
        The raw text string to split (from PDF, TXT, OCR, etc.).

    Returns
    -------
    list[str]
        A list of string chunks. Each chunk is stripped of leading/trailing
        whitespace. Any chunk shorter than 20 characters is discarded.
    """
    try:
        if not text or not text.strip():
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=80,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        raw_chunks = splitter.split_text(text)
        
        cleaned_chunks = []
        for c in raw_chunks:
            stripped = c.strip()
            if len(stripped) >= 20:
                cleaned_chunks.append(stripped)

        return cleaned_chunks

    except Exception as e:
        logger.error(f"[chunk_text] Failed to chunk text: {e}")
        raise
