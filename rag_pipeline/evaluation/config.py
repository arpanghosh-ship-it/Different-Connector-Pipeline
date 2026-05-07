"""
config.py
Central configuration for the RAGAS evaluation system.
Import this in all other evaluation files — never hardcode values.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load from rag_pipeline/.env (one level up from evaluation/)
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ── Directory paths ────────────────────────────────────────────────
EVAL_DIR     = Path(__file__).parent
HR_DOCS_DIR  = EVAL_DIR / "hr_documents"
REPORTS_DIR  = EVAL_DIR / "reports"

# ── Intermediate files ─────────────────────────────────────────────
TESTSET_FILE = EVAL_DIR / "testset.json"
RESULTS_FILE = EVAL_DIR / "pipeline_results.json"

# ── Models ────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JUDGE_MODEL    = "gpt-4o"
EMBED_MODEL    = "text-embedding-3-large"

# ── Qdrant (used by run_eval.py to init clients) ──────────────────
QDRANT_URL     = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# ── Test set ──────────────────────────────────────────────────────
TEST_QUESTIONS_COUNT = 50   # total synthetic questions to generate

# ── Evaluation ────────────────────────────────────────────────────
SCORE_THRESHOLD = 0.70      # flag any metric below this

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
