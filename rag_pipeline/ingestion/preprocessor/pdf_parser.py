"""
pdf_parser.py — Extract text from PDFs using PyMuPDF and GPT-4o vision fallback.

Handles prose extraction, tabular page detection, and falls back to vision OCR
for scanned pages (pages yielding <150 chars of text).
"""

import base64
import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _clean_fitz_text(text: str) -> str:
    """
    Clean raw text extracted by PyMuPDF.
    
    Fixes word-per-line fragments from multi-column PDF layouts.
    Strips excessive whitespace and normalizes newlines.
    """
    if not text:
        return ""
    # Very basic cleanup: remove excessive newlines and normalize spaces
    lines = [line.strip() for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned


def _is_tabular_page(text: str) -> bool:
    """
    Detect if a PDF page contains tabular data.
    
    Returns True if 3 or more lines in the text start with a digit.
    """
    if not text:
        return False
        
    lines = text.split("\n")
    digit_lines = sum(1 for line in lines if line.strip() and line.strip()[0].isdigit())
    return digit_lines >= 3


def _page_to_base64(page) -> str:
    """
    Render a PyMuPDF page object to a PNG image at 2x zoom.
    
    Returns base64-encoded PNG string for GPT-4o vision input.
    """
    try:
        # 2x zoom for better OCR resolution
        matrix = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img_bytes = pix.tobytes("png")
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"[_page_to_base64] Failed to render page to image: {e}")
        raise


def _ocr_page_with_vision(base64_img: str, openai_client) -> str:
    """
    Send a rendered PDF page to GPT-4o vision for OCR.
    
    Used when PyMuPDF extracts fewer than 150 characters.
    """
    try:
        prompt = (
            "Extract ALL text from this document page exactly as it appears. "
            "For tables, extract every row completely — do not skip any row or column. "
            "Output each row on a separate line."
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_img}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"[_ocr_page_with_vision] OCR failed: {e}")
        raise


def extract_pdf(raw_path: Path, openai_client) -> list[dict]:
    """
    Extract text from all pages of a PDF file.

    For each page:
        1. Extract text with fitz (PyMuPDF)
        2. If len(text.strip()) < 150: scanned page detected
           → render page to base64 PNG
           → call _ocr_page_with_vision()
           → log: "Page {n} scanned — using GPT-4o OCR"
        3. Else: apply _clean_fitz_text()
        4. Detect tabular: _is_tabular_page(cleaned_text)

    Returns
    -------
    list[dict]
        A list of dicts with keys: "text", "page_or_sheet", "is_tabular"
    """
    logger.info(f"[extract_pdf] Starting extraction for {raw_path}")
    results = []
    ocr_count = 0

    try:
        doc = fitz.open(str(raw_path))
        total_pages = len(doc)
        
        for i in range(total_pages):
            page = doc[i]
            page_label = f"page {i + 1}"
            
            raw_text = page.get_text("text")
            
            # Check for scanned page (< 150 chars of real text)
            if len(raw_text.strip()) < 150:
                logger.info(f"[extract_pdf] {page_label} scanned — using GPT-4o OCR")
                ocr_count += 1
                base64_img = _page_to_base64(page)
                text = _ocr_page_with_vision(base64_img, openai_client)
            else:
                text = _clean_fitz_text(raw_text)
                
            is_tabular = _is_tabular_page(text)
            
            results.append({
                "text": text,
                "page_or_sheet": page_label,
                "is_tabular": is_tabular
            })

        doc.close()
        logger.info(f"[extract_pdf] Extracted {total_pages} pages ({ocr_count} via OCR)")
        return results

    except Exception as e:
        logger.error(f"[extract_pdf] Failed to process {raw_path}: {e}")
        raise
