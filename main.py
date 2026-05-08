"""
Root ASGI entrypoint for the RAG pipeline.

This lets `uvicorn main:app --reload --port 8001` work from the project root
while keeping the actual application code in `rag_pipeline/main.py`.
"""

import sys
from pathlib import Path


RAG_PIPELINE_DIR = Path(__file__).resolve().parent / "rag_pipeline"
if str(RAG_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_PIPELINE_DIR))

RAG_SITE_PACKAGES = (
    RAG_PIPELINE_DIR
    / ".venv"
    / "Lib"
    / "site-packages"
)
if RAG_SITE_PACKAGES.exists() and str(RAG_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(RAG_SITE_PACKAGES))

from rag_pipeline.main import app  # noqa: E402,F401
