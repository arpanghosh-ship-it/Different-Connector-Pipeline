"""
api_routes.py — FastAPI routers for the RAG pipeline.
"""

import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ingestion.ingestion_pipeline import run_ingestion
from retrieval.rag_query import run_query

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryRequest(BaseModel):
    question: str

@router.post("/ingest/{folder_number}")
def ingest_folder(folder_number: int, request: Request):
    """
    Ingest a synchronized folder from the connector storage into Qdrant.
    """
    logger.info(f"[API] Received ingest request for folder_number={folder_number}")
    
    # Extract clients injected during app startup
    openai_client = request.app.state.openai_client
    qdrant_client = request.app.state.qdrant_client
    
    try:
        result = run_ingestion(folder_number, openai_client, qdrant_client)
        if not result.get("success"):
            error_msg = result.get("error", "Unknown ingestion error")
            logger.error(f"[API] Ingestion failed: {error_msg}")
            raise HTTPException(status_code=422, detail=error_msg)
            
        logger.info(f"[API] Ingestion successful for folder_number={folder_number}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Unexpected error during ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/all")
def ingest_all_folders(request: Request):
    """
    Re-ingest all existing folders to populate missing metadata.
    """
    logger.info("[API] Received request to re-ingest all folders")
    
    openai_client = request.app.state.openai_client
    qdrant_client = request.app.state.qdrant_client
    
    base_path_str = os.getenv("STORAGE_BASE_PATH")
    if not base_path_str:
        raise HTTPException(status_code=500, detail="STORAGE_BASE_PATH is not set")
        
    base_path = Path(base_path_str).resolve()
    
    if not base_path.exists():
        raise HTTPException(status_code=500, detail=f"STORAGE_BASE_PATH does not exist: {base_path}")
        
    folders = [
        d for d in base_path.iterdir()
        if d.is_dir() and d.name.isdigit()
    ]
    
    total = len(folders)
    succeeded = 0
    failed = 0
    skipped = 0
    results = []
    
    logger.info(f"[API] Found {total} folders to process in {base_path}")
    
    for idx, folder in enumerate(folders, 1):
        folder_number = int(folder.name)
        logger.info(f"[API] Re-ingesting folder {folder_number} ({idx} of {total})...")
        
        try:
            result = run_ingestion(folder_number, openai_client, qdrant_client)
            if result.get("success"):
                succeeded += 1
            else:
                if "content_status is" in str(result.get("error", "")):
                    skipped += 1
                else:
                    failed += 1
                    
            results.append({
                "folder_number": folder_number,
                "success": result.get("success", False),
                "filename": result.get("filename"),
                "chunks_count": result.get("chunks_count"),
                "error": result.get("error")
            })
            
        except Exception as e:
            logger.error(f"[API] Unexpected error processing folder {folder_number}: {e}")
            failed += 1
            results.append({
                "folder_number": folder_number,
                "success": False,
                "filename": None,
                "chunks_count": None,
                "error": str(e)
            })
            
    summary = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "results": results
    }
    
    logger.info(f"[API] Re-ingestion complete. Success: {succeeded}, Failed: {failed}, Skipped: {skipped}")
    return summary


@router.post("/query")
def query_documents(query_req: QueryRequest, request: Request):
    """
    Answer a natural language question using the ingested documents.
    """
    question = query_req.question
    logger.info(f"[API] Received query request (query len: {len(question)})")
    
    if not question or not question.strip():
        logger.warning("[API] Received empty question")
        raise HTTPException(status_code=400, detail="question cannot be empty")
        
    openai_client = request.app.state.openai_client
    qdrant_client = request.app.state.qdrant_client
    
    try:
        result = run_query(question, openai_client, qdrant_client)
        logger.info("[API] Query successfully answered")
        return result
        
    except Exception as e:
        logger.error(f"[API] Unexpected error during query: {e}")
        raise HTTPException(status_code=500, detail=str(e))
