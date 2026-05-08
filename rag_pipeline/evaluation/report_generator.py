"""
report_generator.py
Step 5 (final) — generate human-readable reports from pipeline_results.json.

Output:
    evaluation/reports/evaluation_YYYY-MM-DD_HH-MM.csv
    evaluation/reports/evaluation_YYYY-MM-DD_HH-MM.json

Run from rag_pipeline/ root:
    python evaluation/report_generator.py
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

EVAL_DIR = Path(__file__).parent
RAG_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(RAG_ROOT))

from evaluation.config import RESULTS_FILE, REPORTS_DIR, SCORE_THRESHOLD

logger = logging.getLogger(__name__)

METRIC_COLS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]


def build_dataframe(results: list[dict]) -> pd.DataFrame:
    """
    Build a flat DataFrame from pipeline results with RAGAS scores.

    Columns: index, question, question_type, answer, reference,
             faithfulness, answer_relevancy, context_precision,
             context_recall, overall_score, passed,
             response_time_ms, contexts_count, pipeline_success

    Sorted worst-first so reviewer sees failures immediately.

    Args:
        results: list of result dicts from pipeline_results.json

    Returns:
        pd.DataFrame sorted by overall_score ascending
    """
    rows = []
    for i, r in enumerate(results, 1):
        ragas = r.get("ragas_scores", {})
        metric_vals = {col: ragas.get(col) for col in METRIC_COLS}

        valid_vals = [v for v in metric_vals.values() if v is not None]
        overall_score = (
            round(sum(valid_vals) / len(valid_vals), 4) if valid_vals else None
        )
        passed = (
            all(v >= SCORE_THRESHOLD for v in metric_vals.values() if v is not None)
            if valid_vals else False
        )

        rows.append({
            "index":             i,
            "question":          r.get("user_input", ""),
            "question_type":     r.get("synthesizer_name", ""),
            "answer":            r.get("answer", ""),
            "reference":         r.get("reference", ""),
            "faithfulness":      metric_vals["faithfulness"],
            "answer_relevancy":  metric_vals["answer_relevancy"],
            "context_precision": metric_vals["context_precision"],
            "context_recall":    metric_vals["context_recall"],
            "overall_score":     overall_score,
            "passed":            passed,
            "response_time_ms":  r.get("response_time_ms", 0),
            "contexts_count":    len(r.get("retrieved_contexts", [])),
            "pipeline_success":  r.get("success", False),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("overall_score", ascending=True, na_position="first")
    return df


def generate_csv(df: pd.DataFrame, output_path: Path) -> None:
    """Save the evaluation DataFrame to a UTF-8 CSV file.

    Args:
        df: evaluation DataFrame
        output_path: destination path for the CSV
    """
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info(f"CSV saved: {output_path}")


def generate_json_summary(
    data: dict,
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    Generate a JSON summary with overall scores, pass rates,
    failed queries, best queries, and score distribution.

    Args:
        data: raw dict from pipeline_results.json
        df:   evaluation DataFrame from build_dataframe()
        output_path: destination path for the JSON
    """
    overall = data.get("overall_ragas_scores", {})

    # Pass rates per metric
    pass_rates: dict = {}
    for col in METRIC_COLS:
        valid = df[col].dropna()
        if len(valid) == 0:
            pass_rates[col] = "N/A"
        else:
            passed = int((valid >= SCORE_THRESHOLD).sum())
            pct    = round(passed / len(valid) * 100, 1)
            pass_rates[col] = f"{passed}/{len(valid)} ({pct}%)"

    # Failed queries: any metric below threshold
    failed_mask = df[METRIC_COLS].apply(
        lambda row: any(
            v < SCORE_THRESHOLD for v in row if pd.notna(v)
        ),
        axis=1,
    )
    failed_rows = df[failed_mask]

    failed_queries: list[dict] = []
    for _, row in failed_rows.iterrows():
        failing = [
            col for col in METRIC_COLS
            if row[col] == row[col] and row[col] < SCORE_THRESHOLD
        ]
        failed_queries.append({
            "question":          row["question"],
            "question_type":     row["question_type"],
            "faithfulness":      row["faithfulness"],
            "answer_relevancy":  row["answer_relevancy"],
            "context_precision": row["context_precision"],
            "context_recall":    row["context_recall"],
            "overall_score":     row["overall_score"],
            "failing_metrics":   failing,
            "answer":            str(row["answer"])[:300],
            "reference":         str(row["reference"])[:300],
        })

    # Best 5 queries
    best_rows = df.nlargest(5, "overall_score")
    best_queries: list[dict] = [
        {"question": r["question"], "overall_score": r["overall_score"]}
        for _, r in best_rows.iterrows()
    ]

    # Score distribution
    def dist_count(lo: float, hi: float) -> int:
        return int(
            df["overall_score"]
            .dropna()
            .between(lo, hi, inclusive="left")
            .sum()
        )

    summary: dict = {
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_questions":      int(data.get("total_questions", 0)),
        "successful_pipeline":  int(data.get("successful_pipeline", 0)),
        "failed_pipeline":      int(data.get("failed_pipeline", 0)),
        "overall_scores":       overall,
        "threshold":            SCORE_THRESHOLD,
        "pass_rates":           pass_rates,
        "failed_queries_count": len(failed_queries),
        "failed_queries":       failed_queries,
        "best_queries":         best_queries,
        "score_distribution": {
            "above_0.9":  dist_count(0.9, 1.01),
            "0.8_to_0.9": dist_count(0.8, 0.9),
            "0.7_to_0.8": dist_count(0.7, 0.8),
            "below_0.7":  dist_count(0.0, 0.7),
        },
    }

    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"JSON summary saved: {output_path}")


if __name__ == "__main__":

    if not RESULTS_FILE.exists():
        print(
            f"ERROR: {RESULTS_FILE} not found.\n"
            "Run: python evaluation/run_eval.py first."
        )
        sys.exit(1)

    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    if "overall_ragas_scores" not in data:
        print(
            "ERROR: pipeline_results.json has no ragas_scores.\n"
            "Run: python evaluation/run_eval.py first."
        )
        sys.exit(1)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ts        = datetime.now().strftime("%Y-%m-%d_%H-%M")
    csv_path  = REPORTS_DIR / f"evaluation_{ts}.csv"
    json_path = REPORTS_DIR / f"evaluation_{ts}.json"

    df = build_dataframe(data["results"])
    generate_csv(df, csv_path)
    generate_json_summary(data, df, json_path)

    overall = data.get("overall_ragas_scores", {})
    n_failed = int(
        df[METRIC_COLS]
        .apply(lambda row: any(v < SCORE_THRESHOLD for v in row if pd.notna(v)), axis=1)
        .sum()
    )

    print("\n" + "═" * 55)
    print("  FINAL EVALUATION REPORT")
    print("═" * 55)
    for col in METRIC_COLS:
        val = overall.get(col)
        if val is None:
            print(f"  {col:<22} N/A")
        else:
            status = "✓" if val >= SCORE_THRESHOLD else "✗"
            print(f"  {col:<22} {val:.4f}  {status}")
    print("─" * 55)
    print(f"  Average               {overall.get('average', 0):.4f}")
    print(f"  Failed queries        {n_failed}/{len(df)}")
    print("═" * 55)
    print(f"\n  CSV  → {csv_path}")
    print(f"  JSON → {json_path}")

    if n_failed > 0:
        print(f"\n  {n_failed} question(s) have at least one metric")
        print(f"  below {SCORE_THRESHOLD}. Check the CSV (sorted worst-first).")
