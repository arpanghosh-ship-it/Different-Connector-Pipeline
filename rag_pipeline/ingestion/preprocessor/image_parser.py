"""
image_parser.py — Extract text from images using GPT-4o vision.
"""

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_image(raw_path: Path, openai_client) -> list[dict]:
    """
    Extract text from an image file (jpg or png) using GPT-4o vision.

    Returns a list of one dict representing a prose block, compatible
    with `text_chunker`.

    Returns
    -------
    list[dict]
        A list of one dict with keys: "text", "page_or_sheet"
    """
    logger.info(f"[extract_image] Starting extraction for {raw_path}")

    try:
        ext = raw_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            media_type = "image/jpeg"
        elif ext == ".png":
            media_type = "image/png"
        else:
            media_type = "image/jpeg" # Default fallback
            
        with open(raw_path, "rb") as f:
            img_bytes = f.read()
            
        base64_img = base64.b64encode(img_bytes).decode("utf-8")

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
                                "url": f"data:{media_type};base64,{base64_img}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        
        ocr_text = response.choices[0].message.content or ""
        logger.info(f"[extract_image] Extracted {len(ocr_text)} characters via GPT-4o vision")

        return [{
            "text": ocr_text,
            "page_or_sheet": "image"
        }]

    except Exception as e:
        logger.error(f"[extract_image] Failed to process {raw_path}: {e}")
        raise
