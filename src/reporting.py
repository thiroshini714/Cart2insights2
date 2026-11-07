"""Runs the standard queries, statistical tests and insight generation; writes reports/."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from .config import REPORTS_DIR, ROOT
from .insights import generate_insights, insights_to_markdown
from .stats_tests import run_all_tests

RunSql = Callable[[str, dict | None], pd.DataFrame]


def load_queries_module():
    """Import streamlit/queries.py by path (the folder name shadows the real package name)."""
    spec = importlib.util.spec_from_file_location("c2i_queries", ROOT / "streamlit" / "queries.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def default_params(run_sql: RunSql, q) -> dict:
    months = run_sql(q.FILTER_OPTIONS["months"], None)["order_month"].tolist()
    return {"start_month": months[0], "end_month": months[-1], "state": "All", "category": "All",
            "min_orders": q.DEFAULT_MIN_ORDERS, "top_n": q.DEFAULT_TOP_N}


def run_named(run_sql: RunSql, q, name: str, params: dict) -> pd.DataFrame:
    sql = q.QUERIES[name]
    return run_sql(sql, q.used_params(sql, params))


INSIGHT_QUERIES = [
    "kpis", "monthly_revenue", "revenue_by_category", "sales_by_state", "repeat_vs_new",
    "top_sellers", "delivery_summary", "ontime_vs_delayed", "delivery_by_state", "delay_vs_review",
    "review_distribution", "reviews_by_category",
]


def collect_insight_data(run_sql: RunSql, q, params: dict) -> dict[str, pd.DataFrame]:
    return {name: run_named(run_sql, q, name, params) for name in INSIGHT_QUERIES}


def generate_reports(run_sql: RunSql, out_dir: Path = REPORTS_DIR) -> list[Path]:
    """Statistical results (JSON) and business insights (Markdown) for the full dataset."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    q = load_queries_module()
    params = default_params(run_sql, q)

    orders = run_named(run_sql, q, "stats_orders", params)
    stats_results = run_all_tests(orders)
    stats_path = out_dir / "statistical_results.json"
    stats_path.write_text(json.dumps(stats_results, indent=2, default=_json_default))

    data = collect_insight_data(run_sql, q, params)
    insights = generate_insights(data, stats_results)
    source = run_sql(q.FILTER_OPTIONS["data_source"], None)
    is_synthetic = (not source.empty) and source.iloc[0, 0] == "synthetic"
    banner = ("WARNING: generated from SYNTHETIC TEST DATA. These are not real business findings."
              if is_synthetic else None)
    md_path = out_dir / "business_insights.md"
    md_path.write_text(insights_to_markdown(insights, banner=banner))

    # Compact, chart-ready summary consumed by scripts/build_presentation.py
    summary = {
        "data_source": "synthetic" if is_synthetic else "real",
        "period": {"start": params["start_month"], "end": params["end_month"]},
        "kpis": json.loads(data["kpis"].to_json(orient="records"))[0],
        "total_sellers": int(run_named(run_sql, q, "total_sellers", params).iloc[0, 0]),
        "monthly_revenue": json.loads(data["monthly_revenue"][["order_month", "revenue"]]
                                      .to_json(orient="records")),
        "top_categories": json.loads(data["revenue_by_category"].head(8)[["category", "revenue"]]
                                     .to_json(orient="records")),
        "delivery": json.loads(data["delivery_summary"].to_json(orient="records"))[0],
        "ontime_vs_delayed": json.loads(data["ontime_vs_delayed"].to_json(orient="records")),
        "review_distribution": json.loads(data["review_distribution"].to_json(orient="records")),
        "insights": insights,
    }
    summary_path = out_dir / "summary_data.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=_json_default))
    return [stats_path, md_path, summary_path]


def _json_default(obj):
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return str(obj)
