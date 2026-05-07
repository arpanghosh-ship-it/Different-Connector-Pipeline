"""
schema.py — Canonical chunk payload definition.

Every chunk produced by the RAG ingestion pipeline must populate ALL fields
below. No field may be None unless explicitly documented as nullable.

This TypedDict is passed as the `payload` argument to Qdrant PointStruct,
so every key here becomes a searchable/filterable Qdrant payload field.
"""

from typing import TypedDict


class ChunkPayload(TypedDict):
    """
    Fully-populated metadata + content payload stored per Qdrant point.

    Field origins
    -------------
    chunk_id        : Generated fresh per chunk — uuid4 string.
                      Unique across the entire collection.

    document_id     : uuid5(NAMESPACE_DNS, source_id).
                      Deterministic — same file always produces the same
                      document_id regardless of how many times it is
                      re-ingested. Groups all chunks of the same file.

    source_id       : The stable unique identifier from Google Drive or
                      Dropbox (e.g. "1BxiMVs…" for Drive, "id:GQvQ…"
                      for Dropbox). Never changes even on rename/move.
                      Stored in normalized.json → "source_id".

    source_type     : "drive" | "dropbox".
                      Stored in normalized.json → "source_type".

    filename        : Human-readable file name with extension.
                      Stored in normalized.json → "file_name".

    file_type       : Lowercase extension without dot: "pdf", "xlsx",
                      "csv", "txt", "png", "jpg".
                      Stored in normalized.json → "file_type".

    content         : Extracted text for this specific chunk.
                      Varies per chunk even within the same document.

    page_or_sheet   : Human-readable location label within the document.
                      "page 1", "page 2", … for PDFs.
                      "Sheet1", "Sheet2", … for XLSX.
                      "csv" for CSV files.
                      "image" for PNG/JPG.
                      "null" for plain-text TXT files.

    owner_email     : Email of the file owner.
                      Stored in normalized.json → "owner_email".

    modified_at     : ISO-8601 timestamp of last modification in the
                      source system.
                      Stored in normalized.json → "modified_at".

    file_path       : Full path of the file in the source system
                      (e.g. "/Folder A/subfolder/report.pdf").
                      Used to answer "where is this file?" queries.
                      Stored in normalized.json → "path".

    parent_folder   : Path of the immediate parent folder.
                      Stored in normalized.json → "parent_folder_id".

    web_url         : Direct link to the file in Google Drive or Dropbox.
                      Stored in normalized.json → "web_url".

    folder_number   : Integer folder number in the local storage directory
                      (e.g. 52 → storage/52/).
                      Stored in normalized.json → "folder_number".

    chunk_index     : 0-based index of this chunk within the document.
                      Increments continuously across all pages/sheets —
                      never resets per page or per sheet.
    """

    chunk_id: str
    document_id: str
    source_id: str
    source_type: str
    filename: str
    file_type: str
    content: str
    page_or_sheet: str
    owner_email: str
    modified_at: str
    file_path: str
    parent_folder: str
    web_url: str
    folder_number: int
    chunk_index: int
