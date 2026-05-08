"""
run_eval.py
Steps 2, 3 and 4 of RAGAS evaluation.

Step 2: Run every question from testset.json through the RAG pipeline
Step 3: Build RAGAS-compatible Dataset with retrieved_contexts
Step 4: Evaluate with 4 metrics + save results

Metrics: Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

Run from rag_pipeline/ root:
    python evaluation/run_eval.py

Prerequisites:
    - testset.json must exist (run create_dataset.py first)
    - OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY in .env
"""

import json
import logging
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Corporate-network SSL bypass ───────────────────────────────────
# Prevents SSLCertVerificationError when tiktoken downloads encodings
# through a proxy that injects a self-signed certificate.
os.environ.setdefault("CURL_CA_BUNDLE", "")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
os.environ.setdefault("HTTPX_VERIFY", "false")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]
# ──────────────────────────────────────────────────────────────────

EVAL_DIR = Path(__file__).parent
RAG_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(RAG_ROOT))

from evaluation.config import (
    TESTSET_FILE, RESULTS_FILE, REPORTS_DIR,
    OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY,
    JUDGE_MODEL, EMBED_MODEL,
    SCORE_THRESHOLD,
)

logger = logging.getLogger(__name__)


def run_pipeline_queries(questions: list[dict]) -> list[dict]:
    """
    Run each question through the RAG pipeline via direct import.

    Args:
        questions: list of question dicts from testset.json

    Returns:
        list of result dicts with answer, retrieved_contexts,
        response_time_ms, success, error fields added.
    """
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from retrieval.rag_query import run_query

    logger.info("Initializing OpenAI and Qdrant clients...")
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    results: list[dict] = []
    total = len(questions)
    logger.info(f"Running {total} questions through RAG pipeline...")

    for idx, q in enumerate(questions, 1):
        question_text: str = q["user_input"]
        print(f"\n[{idx}/{total}] {question_text[:80]}...")
        start_ms = int(time.time() * 1000)

        try:
            query_result = run_query(question_text, openai_client, qdrant_client)
            elapsed_ms = int(time.time() * 1000) - start_ms
            answer: str = query_result.get("answer", "")
            retrieved_contexts: list[str] = query_result.get("retrieved_contexts", [])

            if not retrieved_contexts:
                logger.warning(
                    f"[{idx}] No retrieved_contexts returned — "
                    "context metrics will be skipped. "
                    "Ensure rag_query.py was updated."
                )

            result: dict = {
                **q,
                "answer":             answer,
                "retrieved_contexts": retrieved_contexts,
                "response_time_ms":   elapsed_ms,
                "success":            True,
                "error":              None,
            }
            print(f"    Answer: {answer[:100]}...")
            print(f"    Contexts retrieved: {len(retrieved_contexts)}")

        except Exception as e:
            elapsed_ms = int(time.time() * 1000) - start_ms
            logger.error(f"[{idx}] Query failed: {e}")
            result = {
                **q,
                "answer":             "",
                "retrieved_contexts": [],
                "response_time_ms":   elapsed_ms,
                "success":            False,
                "error":              str(e),
            }
            print(f"    ERROR: {e}")

        results.append(result)
        time.sleep(0.3)

    succeeded = sum(1 for r in results if r["success"])
    failed    = total - succeeded
    avg_ms    = sum(r["response_time_ms"] for r in results) // total
    logger.info(
        f"Pipeline run complete: {succeeded}/{total} successful, "
        f"{failed} failed, avg {avg_ms}ms"
    )
    return results


def build_ragas_dataset(results: list[dict]):
    """
    Convert pipeline results to a RAGAS-compatible HuggingFace Dataset.

    RAGAS 0.2.x required fields:
        user_input         list[str]
        response           list[str]
        retrieved_contexts list[list[str]]
        reference          list[str]

    Failed rows are excluded; rows with no contexts get [""] so RAGAS
    returns NaN for context metrics rather than crashing.

    Returns:
        datasets.Dataset
    """
    from datasets import Dataset

    valid = [r for r in results if r["success"]]
    skipped = len(results) - len(valid)
    if skipped:
        logger.warning(f"{skipped} failed pipeline rows excluded from evaluation")

    data: dict = {
        "user_input": [r["user_input"] for r in valid],
        "response":   [r["answer"] for r in valid],
        "retrieved_contexts": [
            r["retrieved_contexts"] if r["retrieved_contexts"] else [""]
            for r in valid
        ],
        "reference":  [r["reference"] for r in valid],
    }

    avg_ctx = (
        sum(len(c) for c in data["retrieved_contexts"]) // max(len(valid), 1)
    )
    logger.info(
        f"RAGAS dataset built: {len(valid)} rows, avg contexts/row: {avg_ctx}"
    )
    return Dataset.from_dict(data)


def run_ragas_evaluation(dataset) -> dict:
    """
    Run 4 RAGAS metrics on the dataset using GPT-4o as judge.

    Returns:
        dict with keys "overall" (metric averages) and
        "per_question" (list of per-row scores).
    """
    from ragas import evaluate
    from ragas.metrics import (
        Faithfulness,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    logger.info("Initializing RAGAS evaluator with GPT-4o judge...")

    judge_llm = LangchainLLMWrapper(
        ChatOpenAI(model=JUDGE_MODEL, api_key=OPENAI_API_KEY, temperature=0)
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=EMBED_MODEL, api_key=OPENAI_API_KEY)
    )

    metrics = [
        Faithfulness(llm=judge_llm),
        AnswerRelevancy(llm=judge_llm, embeddings=judge_embeddings),
        ContextPrecision(llm=judge_llm),
        ContextRecall(llm=judge_llm),
    ]

    logger.info(
        f"Running RAGAS evaluate() on {len(dataset)} rows with 4 metrics..."
    )

    try:
        result = evaluate(dataset=dataset, metrics=metrics)
        results_df = result.to_pandas()

        metric_cols = [
            "faithfulness", "answer_relevancy",
            "context_precision", "context_recall",
        ]

        overall: dict = {}
        for col in metric_cols:
            if col in results_df.columns:
                overall[col] = round(float(results_df[col].mean(skipna=True)), 4)
            else:
                overall[col] = None
                logger.warning(f"Metric column '{col}' not found in results")

        # Filter out both None and NaN before computing the average
        import math
        valid_vals = [
            v for v in overall.values()
            if v is not None and not math.isnan(v)
        ]
        overall["average"] = (
            round(sum(valid_vals) / len(valid_vals), 4)
            if valid_vals else None
        )

        per_question: list[dict] = []
        for _, row in results_df.iterrows():
            pq: dict = {"user_input": str(row.get("user_input", ""))}
            for col in metric_cols:
                pq[col] = (
                    round(float(row[col]), 4)
                    if col in row and row[col] == row[col]
                    else None
                )
            per_question.append(pq)

        logger.info(f"RAGAS evaluation complete. Overall: {overall}")
        return {"overall": overall, "per_question": per_question}

    except Exception as e:
        logger.error(f"RAGAS evaluation failed: {e}")
        raise


if __name__ == "__main__":

    if not TESTSET_FILE.exists():
        print(
            f"ERROR: {TESTSET_FILE} not found.\n"
            "Run: python evaluation/create_dataset.py first."
        )
        sys.exit(1)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    testset_data = json.loads(TESTSET_FILE.read_text(encoding="utf-8"))
    questions: list[dict] = testset_data["questions"]
    logger.info(f"Loaded {len(questions)} questions from {TESTSET_FILE}")

    results      = run_pipeline_queries(questions)
    dataset      = build_ragas_dataset(results)
    scores       = run_ragas_evaluation(dataset)

    score_map: dict = {
        pq["user_input"]: pq for pq in scores["per_question"]
    }
    for r in results:
        r["ragas_scores"] = score_map.get(r["user_input"], {})

    output = {
        "run_at":               datetime.now(timezone.utc).isoformat(),
        "total_questions":      len(questions),
        "successful_pipeline":  sum(1 for r in results if r["success"]),
        "failed_pipeline":      sum(1 for r in results if not r["success"]),
        "overall_ragas_scores": scores["overall"],
        "score_threshold":      SCORE_THRESHOLD,
        "results":              results,
    }

    RESULTS_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Results saved to: {RESULTS_FILE}")

    overall   = scores["overall"]
    threshold = SCORE_THRESHOLD

    def score_line(label: str, key: str) -> str:
        import math
        val = overall.get(key)
        # Treat both None and NaN as N/A
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return f"  {label:<22} N/A"
        status = "✓ PASS" if val >= threshold else "✗ FAIL"
        bar    = "█" * int(val * 10) + "░" * (10 - int(val * 10))
        return f"  {label:<22} {val:.4f}  {bar}  {status}"

    print("\n" + "═" * 55)
    print("  RAGAS EVALUATION RESULTS")
    print("═" * 55)
    print(score_line("Faithfulness",      "faithfulness"))
    print(score_line("Answer Relevancy",  "answer_relevancy"))
    print(score_line("Context Precision", "context_precision"))
    print(score_line("Context Recall",    "context_recall"))
    print("─" * 55)
    print(score_line("AVERAGE",           "average"))
    print("═" * 55)
    print(f"\n  Results saved: {RESULTS_FILE}")
    print("  Next step:     python evaluation/report_generator.py")