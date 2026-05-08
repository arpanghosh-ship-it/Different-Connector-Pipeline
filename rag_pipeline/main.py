"""
main.py — Application entrypoint for the standalone RAG pipeline.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RAG_SITE_PACKAGES = BASE_DIR / ".venv" / "Lib" / "site-packages"
if RAG_SITE_PACKAGES.exists() and str(RAG_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(RAG_SITE_PACKAGES))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from openai import OpenAI
from qdrant_client import QdrantClient
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

from store.qdrant_store import init_collection
from api_routes import router
from utils.response import error_response

# Configure logging at module level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Load environment variables
    load_dotenv(BASE_DIR / ".env")
    
    # 2. Initialize OpenAI client once
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.warning("OPENAI_API_KEY is not set. OpenAI calls will fail.")
    openai_client = OpenAI(api_key=openai_key)
    
    # 3. Initialize Qdrant client once
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if not qdrant_url:
        logger.warning("QDRANT_URL is not set. Qdrant calls will fail.")
    q_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    
    # 4. Initialize Qdrant collection
    init_collection(q_client)
    
    # 5. Inject clients into app state for router access
    app.state.openai_client = openai_client
    app.state.qdrant_client = q_client
    
    # 6. Log startup success
    logger.info("RAG pipeline started — Qdrant collection ready")
    
    yield
    
    # Cleanup (optional, but good practice)
    logger.info("RAG pipeline shutting down")


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return error_response(
        message="Request validation failed",
        data={"errors": exc.errors()},
        status_code=422
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return error_response(
        message=str(exc.detail),
        status_code=exc.status_code
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
