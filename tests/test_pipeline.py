"""End-to-end tests on SYNTHETIC data using the standard-library sqlite3 driver.

Why sqlite3 and not SQLAlchemy: this suite checks the schema (PK/FK), every analysis query,
the statistical tests and the insight generator. The SQLAlchemy wiring (src/db.py,
src/load_to_sql.py) is a thin layer and is exercised by `python run_pipeline.py`.

Run:  python -m pytest tests -q        (or: python tests/test_pipeline.py)
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.make_synthetic_data import generate  # noqa: E402
from src import config  # noqa: E402
from src.cleaning import clean_all  # noqa: E402
from src.features import build_all_features  # noqa: E402
from src.insights import generate_insights, insights_to_markdown  # noqa: E402
from src.quality import run_quality_report  # noqa: E402
from src.reporting import INSIGHT_QUERIES, load_queries_module  # noqa: E402
from src.stats_tests import run_all_tests  # noqa: E402

q = load_queries_module()


# ----------------------------------------------------------------------------- fixtures
def _build():
    raw_files = generate(n_orders=3000, seed=7)
    raw = {}
    for name, df in raw_files.items():
        key = re.sub(r"^olist_|_dataset$", "", name)
        key = re.sub(r"_dataset$", "", key)
        raw[key] = df
    cleaned, log = clean_all(raw)
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    sql = re.sub(r"--[^\n]*", "", config.SCHEMA_FILE.read_text())
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        conn.execute(stmt)
    for name in config.TABLE_ORDER:
        df = cleaned[name].copy()
        for c in df.columns:
            if "date" in c or "timestamp" in c or c.endswith("_at"):
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        df.to_sql(name, conn, if_exists="append", index=False)
    features = build_all_features(cleaned)
    for name, df in features.items():
        df = df.copy()
        for c in df.columns:
            if "date" in c or "timestamp" in c:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        df.to_sql(name, conn, if_exists="append", index=False)
    return raw, cleaned, log, features, conn


RAW, CLEANED, LOG, FEATURES, CONN = _build()
OF = FEATURES["order_features"]


def run(sql, params=None):
    return pd.read_sql_query(sql, CONN, params=q.used_params(sql, params or {}))


def params(**over):
    months = sorted(OF["order_month"].unique())
    base = {"start_month": months[0], "end_month": months[-1], "state": "All", "category": "All",
            "min_orders": 5, "top_n": 10}
    base.update(over)
    return base


# ----------------------------------------------------------------------------- cleaning
def test_primary_keys_unique_after_cleaning():
    for name, pk in config.PRIMARY_KEYS.items():
        assert not CLEANED[name].duplicated(subset=pk).any(), name


def test_no_orphans_after_cleaning():
    for child, ccol, parent, pcol in config.FOREIGN_KEYS:
        assert CLEANED[child][ccol].isin(set(CLEANED[parent][pcol])).all(), (child, ccol)


def test_cleaning_fixes_injected_problems():
    assert CLEANED["order_reviews"]["review_score"].between(1, 5).all()
    assert (CLEANED["order_items"]["price"] > 0).all()
    assert CLEANED["order_reviews"]["order_id"].is_unique
    assert CLEANED["products"]["product_category_name_english"].notna().all()
    assert CLEANED["customers"]["customer_zip_code_prefix"].str.len().eq(5).all()
    assert (CLEANED["order_payments"]["payment_installments"] >= 1).all()
    assert len(RAW["orders"]) > len(CLEANED["orders"])  # duplicates removed


def test_quality_report_detects_injected_problems():
    rep = run_quality_report(RAW, save=False)
    assert rep["orders"]["duplicate_rows"] >= 20
    assert rep["order_reviews"]["invalid_values"]["score_outside_1_to_5"] >= 5
    assert rep["order_items"]["invalid_values"]["price_not_positive"] >= 3
    assert not rep["geolocation"]["primary_key_unique"]


# ----------------------------------------------------------------------------- features
def test_feature_definitions():
    d = OF[OF["delivery_status"].notna()]
    assert np.allclose(d["delivery_delay_days"] > 0, d["delivery_status"] == "Delayed")
    assert (OF["total_order_value"] - (OF["items_value"] + OF["freight_value"])).abs().max() < 0.01
    cf = FEATURES["customer_features"]
    assert (cf["is_repeat_customer"] == (cf["order_count"] > 1).astype(int)).all()
    assert OF["order_id"].is_unique


# ----------------------------------------------------------------------------- SQL
def test_foreign_keys_enforced_in_sql():
    assert CONN.execute("PRAGMA foreign_key_check").fetchall() == []


def test_row_counts_match():
    for name in config.TABLE_ORDER:
        n = CONN.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        assert n == len(CLEANED[name]), name


def test_every_dashboard_query_runs():
    for name in q.QUERIES:
        df = run(q.QUERIES[name], params())
        assert isinstance(df, pd.DataFrame), name
        assert len(df) > 0, f"{name} returned no rows"


def test_every_analysis_query_runs():
    for name, spec in q.ANALYSIS_QUERIES.items():
        df = run(spec["sql"])
        assert len(df) > 0, f"{name} returned no rows"


def test_filter_options_run():
    for key in ("months", "states", "categories"):
        assert len(run(q.FILTER_OPTIONS[key])) > 0, key


def test_kpis_match_pandas():
    k = run(q.QUERIES["kpis"], params()).iloc[0]
    v = OF[OF["is_valid_sale"] == 1]
    assert abs(k["total_revenue"] - v["total_order_value"].sum()) < 0.5
    assert k["total_orders"] == len(v)
    assert k["total_customers"] == v["customer_unique_id"].nunique()
    assert abs(k["avg_review_score"] - v["review_score"].mean()) < 1e-6
    sellers = run(q.QUERIES["total_sellers"], params()).iloc[0, 0]
    assert sellers == FEATURES["seller_features"]["seller_id"].nunique()


def test_revenue_by_category_sums_to_revenue():
    cat = run(q.QUERIES["revenue_by_category"], params())
    assert abs(cat["revenue"].sum() - OF.loc[OF["is_valid_sale"] == 1, "total_order_value"].sum()) < 0.5


def test_filters_change_results():
    state = OF["customer_state"].value_counts().index[0]
    all_k = run(q.QUERIES["kpis"], params()).iloc[0]
    st_k = run(q.QUERIES["kpis"], params(state=state)).iloc[0]
    assert 0 < st_k["total_orders"] < all_k["total_orders"]
    expected = ((OF["is_valid_sale"] == 1) & (OF["customer_state"] == state)).sum()
    assert st_k["total_orders"] == expected
    months = sorted(OF["order_month"].unique())
    narrow = run(q.QUERIES["monthly_revenue"], params(start_month=months[2], end_month=months[4]))
    assert list(narrow["order_month"]) == months[2:5]


def test_monthly_window_functions():
    m = run(q.QUERIES["monthly_revenue"], params())
    assert abs(m["cumulative_revenue"].iloc[-1] - m["revenue"].sum()) < 0.5
    manual = (m["revenue"].iloc[1] - m["revenue"].iloc[0]) / m["revenue"].iloc[0] * 100
    assert abs(m["mom_growth_pct"].iloc[1] - manual) < 0.01
    assert pd.isna(m["mom_growth_pct"].iloc[0])


def test_delay_buckets_cover_all_delivered_orders():
    d = run(q.QUERIES["delay_vs_review"], params())
    assert d["order_count"].sum() == OF["delivery_delay_days"].notna().sum()


def test_seller_ratings_having_clause():
    s = run(q.QUERIES["seller_ratings"], params(min_orders=20))
    assert (s["reviewed_orders"] >= 20).all()


def test_used_params_filters_extras():
    assert q.used_params("SELECT :a, :b", {"a": 1, "b": 2, "c": 3}) == {"a": 1, "b": 2}


# ----------------------------------------------------------------------------- statistics
def test_statistical_tests():
    orders = run(q.QUERIES["stats_orders"], params())
    res = run_all_tests(orders)
    t = res["t_test_delivery_vs_review"]
    assert t["mean_delayed"] < t["mean_on_time"]  # effect is seeded into the synthetic data
    assert t["significant"] and t["p_value"] < 0.05
    a = res["anova_category_vs_order_value"]
    assert 0 <= a["p_value"] <= 1 and 0 <= a["eta_squared"] <= 1
    c = res["chi_square_payment_vs_status"]
    assert 0 <= c["p_value"] <= 1 and c["dof"] > 0
    for r in res.values():
        assert "business_insight" in r and "assumptions" in r


def test_ttest_matches_scipy_reference():
    from scipy import stats

    orders = run(q.QUERIES["stats_orders"], params())
    d = orders.dropna(subset=["delivery_status", "review_score"])
    ref = stats.ttest_ind(d.loc[d.delivery_status == "Delayed", "review_score"],
                          d.loc[d.delivery_status == "On time", "review_score"],
                          equal_var=False, alternative="less")
    ours = run_all_tests(orders)["t_test_delivery_vs_review"]
    assert abs(ours["p_value"] - ref.pvalue) < 1e-12


# ----------------------------------------------------------------------------- insights
def test_insights_generated_from_data():
    p = params()
    data = {n: run(q.QUERIES[n], p) for n in INSIGHT_QUERIES}
    stats_res = run_all_tests(run(q.QUERIES["stats_orders"], p))
    ins = generate_insights(data, stats_res)
    assert len(ins) >= 8
    for i in ins:
        assert all(i[k] for k in ("observation", "interpretation", "business_impact", "recommendation"))
    md = insights_to_markdown(ins, banner="synthetic")
    assert "Observation" in md and "Business impact" in md


# ----------------------------------------------------------------------------- reports + deck
def _run_sql_for_reports(sql, params=None):
    return pd.read_sql_query(sql, CONN, params=q.used_params(sql, params or {}))


def test_generate_reports_and_presentation(tmp_path=None):
    import json
    import tempfile

    from src.reporting import generate_reports
    from src.quality import run_quality_report

    tmp = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    CONN.execute("INSERT OR REPLACE INTO pipeline_meta VALUES ('data_source', 'synthetic')")
    paths = generate_reports(_run_sql_for_reports, out_dir=tmp)
    assert all(p.exists() for p in paths)
    md_text = (tmp / "business_insights.md").read_text()
    assert "SYNTHETIC" in md_text and "Observation" in md_text   # banner + required structure
    summary = json.loads((tmp / "summary_data.json").read_text())
    assert summary["data_source"] == "synthetic" and len(summary["insights"]) >= 8
    kp = summary["kpis"]
    assert abs(kp["total_revenue"] - OF.loc[OF["is_valid_sale"] == 1, "total_order_value"].sum()) < 0.5

    # deck needs the quality report and cleaning log next to the other files
    (tmp / "data_quality_report.json").write_text(json.dumps(run_quality_report(RAW, save=False)))
    LOG.to_csv(tmp / "cleaning_log.csv", index=False)
    from scripts.build_presentation import build
    from pptx import Presentation

    out = build(tmp / "deck.pptx", reports_dir=tmp)
    prs = Presentation(str(out))
    assert len(prs.slides) >= 12
    all_text = " ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert "SYNTHETIC TEST DATA" in all_text
    assert "p-value" in all_text


if __name__ == "__main__":
    failures = 0
    for fn_name, fn in list(globals().items()):
        if fn_name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {fn_name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {fn_name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    raise SystemExit(1 if failures else 0)
