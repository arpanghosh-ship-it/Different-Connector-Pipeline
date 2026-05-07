"""
create_dataset.py
Step 1 of RAGAS evaluation.

Reads evaluation questions from evaluation/hr_documents/questions.txt
and saves them to testset.json in the RAGAS-compatible format.

────────────────────────────────────────────────────────────────────
questions.txt FORMAT
────────────────────────────────────────────────────────────────────
  # Lines starting with # are comments — ignored
  # Blank lines are ignored
  # Group questions by source PDF with [filename.pdf] headers
  # Each question line: just the question text
  # Optional ground truth answer: append  ||  after the question

  Example:
    [1.pdf]
    What is the annual leave entitlement?
    How many sick days per year? || Employees get 12 sick days per year.

    [2.pdf]
    What is the probation period for new hires?
────────────────────────────────────────────────────────────────────

Run from rag_pipeline/ root:
    python evaluation/create_dataset.py

Prerequisites:
    - Place questions.txt in evaluation/hr_documents/
"""

import json
import logging
import os
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Corporate-network SSL bypass ───────────────────────────────────
os.environ.setdefault("CURL_CA_BUNDLE", "")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
os.environ.setdefault("HTTPX_VERIFY", "false")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]
# ──────────────────────────────────────────────────────────────────

# ── Path setup ─────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).parent
RAG_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(RAG_ROOT))

from evaluation.config import (
    HR_DOCS_DIR, TESTSET_FILE, REPORTS_DIR,
)

logger = logging.getLogger(__name__)

QUESTIONS_FILE = HR_DOCS_DIR / "questions.txt"


# ── Parser ─────────────────────────────────────────────────────────

def parse_questions_file(path: Path) -> list[dict]:
    """
    Parse evaluation/hr_documents/questions.txt into RAGAS records.

    Format rules:
      - Lines starting with #  → comments, skipped
      - Blank lines            → skipped
      - Lines like [file.pdf]  → set the current source PDF label
      - Other lines            → treated as a question
          optional ground truth: append  ||  after the question text
          e.g.  What is the leave policy? || Employees get 20 days.

    Returns:
        list of dicts:
        {
            "user_input":         str,   ← the question
            "reference":          str,   ← ground truth (or "" if absent)
            "reference_contexts": list,  ← always [] — filled by run_eval
            "synthesizer_name":   str,   ← source PDF name or "manual"
        }

    Raises:
        SystemExit if the file is missing or has no parseable questions.
    """
    if not path.exists():
        logger.error(
            f"questions.txt not found at {path}\n"
            f"Create the file with your questions and re-run."
        )
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    current_source = "manual"

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()

        # Skip comments and blanks
        if not line or line.startswith("#"):
            continue

        # PDF section header: [1.pdf]
        if line.startswith("[") and line.endswith("]"):
            current_source = line[1:-1].strip()
            logger.info(f"  Section: [{current_source}]")
            continue

        # Question line — split on || for optional ground truth
        if "||" in line:
            parts = line.split("||", 1)
            question  = parts[0].strip()
            reference = parts[1].strip()
        else:
            question  = line
            reference = ""

        if not question:
            logger.warning(f"  Line {lineno}: empty question after stripping — skipped.")
            continue

        records.append({
            "user_input":         question,
            "reference":          reference,
            "reference_contexts": [],
            "synthesizer_name":   current_source,
        })

    logger.info(f"Parsed {len(records)} question(s) from {path.name}")

    if not records:
        logger.error(
            f"No questions found in {path}\n"
            f"Add questions in the format described at the top of create_dataset.py."
        )
        sys.exit(1)

    return records


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    HR_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse questions.txt
    records = parse_questions_file(QUESTIONS_FILE)

    # Count questions with and without ground truth
    with_ref    = sum(1 for r in records if r["reference"])
    without_ref = len(records) - with_ref

    # Save testset.json
    output = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "total_questions": len(records),
        "source_pdfs":     sorted({r["synthesizer_name"] for r in records}),
        "questions":       records,
    }

    TESTSET_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Testset saved to: {TESTSET_FILE}")

    # ── Terminal summary ───────────────────────────────────────────
    print("\n" + "═" * 55)
    print("  TESTSET CREATION COMPLETE")
    print("═" * 55)
    print(f"  Total questions      : {len(records)}")
    print(f"  With ground truth    : {with_ref}  (used by ContextRecall)")
    print(f"  Without ground truth : {without_ref}  (ContextRecall → N/A)")
    print(f"  Saved to             : {TESTSET_FILE}")
    print("═" * 55)

    print("\n── PREVIEW (first 5 questions) ──")
    for i, q in enumerate(records[:5], 1):
        ref_preview = f" || {q['reference'][:60]}..." if q["reference"] else " (no ground truth)"
        print(f"  [{i}] [{q['synthesizer_name']}] {q['user_input']}{ref_preview}")

    if without_ref > 0:
        print(
            f"\n  TIP: Add ground truth answers after  ||  on each question line\n"
            f"  to enable ContextRecall scoring in run_eval.py."
        )

    print(f"\n  Next step: python evaluation/run_eval.py")