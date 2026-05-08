"""
api_routes.py — FastAPI routers for the RAG pipeline.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ingestion.ingestion_pipeline import run_ingestion
from retrieval.rag_query import run_query
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryRequest(BaseModel):
    question: str


class UserDetails(BaseModel):
    """
    Optional user profile context passed with a global query.
    All fields accept empty string or None.
    Captured for future use (audit logging, personalization).
    Not used in current RAG query logic.
    """
    user_name:  Optional[str] = ""
    user_role:  Optional[str] = ""
    user_email: Optional[str] = ""


class GlobalQueryRequest(BaseModel):
    """
    Extended request body for POST /query-global.

    Required:
        question: The natural language question to answer

    Optional (all default to empty string -- reserved for future use):
        user_id:      Unique identifier for the calling user
        session_id:   Conversation/session identifier for continuity
        user_details: User profile context (name, role, email)

    Note: /query endpoint uses the simpler QueryRequest model
    (question only). This model is for the /query-global endpoint.
    """
    question:     str
    user_id:      Optional[str] = ""
    session_id:   Optional[str] = ""
    user_details: Optional[UserDetails] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_id":    "",
                "session_id": "",
                "question":   "Who is eligible to work from home under the policy?",
                "user_details": {
                    "user_name":  "",
                    "user_role":  "",
                    "user_email": ""
                }
            }
        }


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
            return error_response(
                message=result.get("error", "Ingestion failed"),
                data={"folder_number": folder_number},
                status_code=422
            )
            
        logger.info(f"[API] Ingestion successful for folder_number={folder_number}")
        return success_response(
            message=f"Folder {folder_number} ingested successfully",
            data=result
        )
        
    except Exception as e:
        logger.error(f"[API] Unexpected error during ingestion: {e}")
        return error_response(
            message=str(e),
            status_code=500
        )


@router.post("/ingest/all")
def ingest_all_folders(request: Request):
    """
    Re-ingest all existing folders to populate missing metadata.
    """
    try:
        logger.info("[API] Received request to re-ingest all folders")
        
        openai_client = request.app.state.openai_client
        qdrant_client = request.app.state.qdrant_client
        
        base_path_str = os.getenv("STORAGE_BASE_PATH")
        if not base_path_str:
            return error_response(
                message="STORAGE_BASE_PATH is not set",
                status_code=500
            )
            
        base_path = Path(base_path_str).resolve()
        
        if not base_path.exists():
            return error_response(
                message=f"STORAGE_BASE_PATH does not exist: {base_path}",
                status_code=500
            )
            
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
        return success_response(
            message=f"Bulk ingestion complete: {succeeded}/{total} folders succeeded",
            data=summary
        )

    except Exception as e:
        logger.error(f"[API] Unexpected error during bulk ingestion: {e}")
        return error_response(
            message=str(e),
            status_code=500
        )


@router.post("/query")
def query_documents(query_req: QueryRequest, request: Request):
    """
    Answer a natural language question using the ingested documents.
    """
    question = query_req.question
    logger.info(f"[API] Received query request (query len: {len(question)})")
    
    if not question or not question.strip():
        logger.warning("[API] Received empty question")
        return error_response(
            message="Question cannot be empty",
            status_code=400
        )
        
    openai_client = request.app.state.openai_client
    qdrant_client = request.app.state.qdrant_client
    
    try:
        result = run_query(question, openai_client, qdrant_client)
        logger.info("[API] Query successfully answered")
        return success_response(
            message="Query answered successfully",
            data=result
        )
        
    except Exception as e:
        logger.error(f"[API] Unexpected error during query: {e}")
        return error_response(
            message=str(e),
            status_code=500
        )


@router.post("/query-global")
def query_documents_global(
    query_req: GlobalQueryRequest,
    request: Request
):
    """
    Answer a natural language question using the ingested documents.

    Extended version of /query that accepts optional user context fields
    (user_id, session_id, user_details) for future personalization and
    audit logging. The underlying RAG logic is identical to /query --
    only the question field is passed to the query engine.

    Request body:
        question:     required -- the question to answer
        user_id:      optional -- calling user identifier
        session_id:   optional -- session/conversation identifier
        user_details: optional -- user profile (name, role, email)

    All optional fields accept empty string or null.
    """
    question = query_req.question.strip() if query_req.question else ""
    user_details = query_req.user_details or UserDetails()

    logger.info(
        f"[API] Global query received -- "
        f"user_id={query_req.user_id!r} "
        f"session_id={query_req.session_id!r} "
        f"user_name={user_details.user_name!r} "
        f"user_role={user_details.user_role!r} "
        f"question_len={len(question)}"
    )

    if not question:
        logger.warning("[API] Empty question received on /query-global")
        return error_response(
            message="Question cannot be empty",
            status_code=400
        )

    openai_client = request.app.state.openai_client
    qdrant_client = request.app.state.qdrant_client

    try:
        # run_query() is called with only the question -- same as /query.
        # user_id, session_id, user_details are not passed to run_query()
        # and do not affect the RAG logic. They are logged above for
        # future use.
        result = run_query(question, openai_client, qdrant_client)
        logger.info("[API] Global query answered successfully")
        return success_response(
            message="Query answered successfully",
            data=result
        )

    except Exception as e:
        logger.error(f"[API] Unexpected error during global query: {e}")
        return error_response(
            message=str(e),
            status_code=500
        )
