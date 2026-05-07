"""
ids.py — Deterministic and random ID generators for the RAG pipeline.

Design principles
-----------------
document_id  — deterministic (uuid5) so that re-ingesting the same file
               always produces the same document_id. This allows the
               delete-before-upsert dedup strategy to work correctly:
               all old Qdrant points for a file are deleted by source_id,
               and the new points land under the same document_id.

chunk_id     — random (uuid4) so that each chunk is unique even across
               re-ingestions of the same document.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def make_document_id(source_id: str) -> str:
    """
    Generate a deterministic document ID from a source_id string.

    Uses uuid5 with NAMESPACE_DNS so the same source_id always
    produces the same document_id, across restarts and re-ingestions.

    Parameters
    ----------
    source_id : str
        The stable unique file identifier from Google Drive or Dropbox
        (never changes even if the file is renamed or moved).

    Returns
    -------
    str
        A UUID5 string (e.g. "550e8400-e29b-41d4-a716-446655440000").

    Raises
    ------
    ValueError
        If source_id is empty or not a string.
    """
    try:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f"source_id must be a non-empty string, got: {source_id!r}")
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, source_id))
        logger.debug(f"[make_document_id] source_id={source_id!r} → document_id={doc_id}")
        return doc_id
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"[make_document_id] Unexpected error for source_id={source_id!r}: {e}")
        raise


def make_chunk_id() -> str:
    """
    Generate a unique random ID for a single chunk.

    Uses uuid4 — not deterministic. Each call returns a different value.
    Chunk IDs are used as the Qdrant point ID and are not meant to be
    stable across re-ingestions (the whole document is deleted and
    re-inserted on each ingestion cycle).

    Returns
    -------
    str
        A UUID4 string.
    """
    try:
        return str(uuid.uuid4())
    except Exception as e:
        logger.error(f"[make_chunk_id] Failed to generate chunk ID: {e}")
        raise
