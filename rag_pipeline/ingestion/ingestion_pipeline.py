"""
ingestion_pipeline.py — Orchestrates the full synchronous ingestion flow.
"""

import logging

from utils.schema import ChunkPayload
from utils.ids import make_document_id, make_chunk_id
from utils.file_io import load_storage_folder
from ingestion.preprocessor.router import extract_file
from ingestion.chunker.text_chunker import chunk_text
from ingestion.chunker.table_chunker import chunk_table_rows
from store.qdrant_store import delete_by_source_id, embed_texts, upsert_chunks

logger = logging.getLogger(__name__)


def build_chunks(extracted: list[dict], normalized: dict, document_id: str) -> list[ChunkPayload]:
    """
    Convert extracted content blocks into fully populated ChunkPayload objects.

    Merges extracted text with normalized.json metadata.
    Handles prose routing vs tabular routing.
    """
    try:
        # Fields shared by all chunks from this file
        base_payload = {
            "document_id": document_id,
            "source_id": normalized["source_id"],
            "source_type": normalized["source_type"],
            "filename": normalized["file_name"],
            "file_type": normalized["file_type"],
            "owner_email": normalized.get("owner_email", ""),
            "modified_at": normalized.get("modified_at", ""),
            "file_path": normalized["path"],
            "parent_folder": normalized.get("parent_folder_id", ""),
            "web_url": normalized.get("web_url", ""),
            "folder_number": normalized["folder_number"],
        }

        chunks: list[ChunkPayload] = []
        chunk_index = 0

        for block in extracted:
            page_or_sheet = str(block.get("page_or_sheet", "null"))
            
            # Case 1: Tabular block (from XLSX/CSV)
            if "headers" in block and "rows" in block:
                texts = chunk_table_rows(block["headers"], block["rows"])
                
            # Case 2: Tabular PDF page
            elif block.get("is_tabular") is True and "text" in block:
                text = block["text"]
                lines = [l for l in text.split("\n") if l.strip()]
                # Fallback to a single-column representation
                headers = ["column"]
                rows = [[line] for line in lines]
                texts = chunk_table_rows(headers, rows)
                
            # Case 3: Prose block
            elif "text" in block:
                texts = chunk_text(block["text"])
                
            else:
                logger.warning(f"[build_chunks] Unknown block format: {block.keys()}")
                continue

            # Build final payload for each text segment
            for text_segment in texts:
                # Merge base payload with chunk-specific fields
                payload: ChunkPayload = {
                    **base_payload, # type: ignore
                    "chunk_id": make_chunk_id(),
                    "content": text_segment,
                    "page_or_sheet": page_or_sheet,
                    "chunk_index": chunk_index
                }
                chunks.append(payload)
                chunk_index += 1

        logger.info(f"[build_chunks] Produced {len(chunks)} chunks for document {document_id}")
        return chunks

    except Exception as e:
        logger.error(f"[build_chunks] Failed to build chunks: {e}")
        raise


def run_ingestion(folder_number: int, openai_client, qdrant_client) -> dict:
    """
    Orchestrate the full ingestion pipeline for one storage folder.
    
    SYNCHRONOUS — returns only after ingestion is fully complete.
    No background tasks, no async, no threading.

    Returns
    -------
    dict
        Result dictionary with "success" (bool), "error" (str, optional),
        "filename", "file_type", "chunks_count", "document_id", "folder_number".
    """
    try:
        logger.info(f"[run_ingestion] Starting ingestion for folder {folder_number}")
        
        # 1. Load normalized metadata and locate raw file
        normalized, raw_path = load_storage_folder(folder_number)

        # 2. Check content_status
        if normalized.get("content_status") != "accessible":
            status = normalized.get("content_status")
            msg = f"Skipped: content_status is '{status}'"
            logger.info(f"[run_ingestion] {msg}")
            return {
                "success": False,
                "error": msg
            }

        # 3. Generate deterministic document ID
        document_id = make_document_id(normalized["source_id"])

        # 4. Clean up existing Qdrant points for this source_id
        delete_by_source_id(normalized["source_id"], qdrant_client)

        # 5. Extract file
        extracted = extract_file(normalized["file_type"], raw_path, openai_client)

        # 6. Build chunks
        chunks = build_chunks(extracted, normalized, document_id)
        if len(chunks) == 0:
            msg = "No chunks produced from file"
            logger.warning(f"[run_ingestion] {msg}")
            return {
                "success": False,
                "error": msg
            }

        # 7. Embed chunks
        texts = [c["content"] for c in chunks]
        embeddings = embed_texts(texts, openai_client)

        # 8. Upsert to Qdrant
        upsert_chunks(chunks, embeddings, qdrant_client)

        logger.info(f"[run_ingestion] Successfully ingested folder {folder_number}")
        return {
            "success": True,
            "filename": normalized["file_name"],
            "file_type": normalized["file_type"],
            "chunks_count": len(chunks),
            "document_id": document_id,
            "folder_number": folder_number
        }

    except Exception as e:
        logger.error(f"[run_ingestion] Ingestion failed for folder {folder_number}: {e}")
        return {
            "success": False,
            "error": str(e)
        }
