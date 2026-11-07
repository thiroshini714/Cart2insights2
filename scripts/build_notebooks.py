"""Generate notebooks/01..07 as .ipynb files (no Jupyter needed to build them).

The notebooks are saved WITHOUT outputs: run them (Kernel > Restart & Run All) after the real
dataset is in data/raw/ to produce the outputs and charts.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"

SETUP = dedent('''
    import sys, warnings
    from pathlib import Path

    ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
    sys.path.insert(0, str(ROOT))
    warnings.filterwarnings("ignore", category=FutureWarning)

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display

    from src import config
    pd.set_option("display.max_columns", 60)
    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")
    sns.set_theme(style="whitegrid", palette="viridis")

    # Where the raw CSVs live. To rehearse on generated test data instead, use:
    #   RAW_DIR = config.SYNTHETIC_DIR   (run `python scripts/make_synthetic_data.py` first)
    RAW_DIR = config.RAW_DIR
''').strip()

SQL_SETUP = dedent('''
    from src.db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    print("Connected:", engine.url.render_as_string(hide_password=True))


    def query(sql, params=None):
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)
''').strip()


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": dedent(text).strip().splitlines(True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": dedent(text).strip().splitlines(True)}


def save(name: str, cells: list[dict]) -> None:
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                      "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 4}
    NB_DIR.mkdir(exist_ok=True)
    (NB_DIR / name).write_text(json.dumps(nb, indent=1))


# ---------------------------------------------------------------------------------- 01
save("01_data_understanding.ipynb", [
    md("""
    # 01 · Data understanding
    **Steps 1–3:** business problem, dataset + ER diagram, loading the raw data.

    ## Business problem
    An e-commerce platform stores orders, products, sellers, payments, deliveries and reviews
    across 9 related tables, which makes performance and customer behaviour hard to see in raw form.
    The goal is to turn that data into insights on sales, customers, products, sellers, payments,
    delivery performance and customer satisfaction.

    ## Questions this analysis answers
    1. How are revenue, orders and average order value trending, and which categories/states drive them?
    2. Who are our customers, how much do they spend and how many come back?
    3. Which sellers and products perform best, and how are they rated?
    4. How fast are deliveries, how often are they late, and where?
    5. Does late delivery hurt review scores? Does spend differ by category? Is payment method linked to order outcome?
    """),
    code(SETUP),
    md("## Load all 9 CSV files with Pandas"),
    code("""
    from src.data_loader import load_raw_tables, describe_tables

    raw = load_raw_tables(RAW_DIR)
    display(describe_tables(raw)[["table", "rows", "columns"]])
    """),
    md("## Shape, columns and data types of each table"),
    code("""
    for name, df in raw.items():
        print(f"\\n=== {name}: {df.shape[0]:,} rows x {df.shape[1]} columns ===")
        display(df.dtypes.rename("dtype").to_frame().T)
        display(df.head(3))
    """),
    md("""
    ## Keys and relationships (ER diagram)
    The ER diagram is in `docs/er_diagram.md`; the full data dictionary is in `docs/data_dictionary.md`.
    """),
    code("""
    pk = pd.DataFrame([(t, ", ".join(c)) for t, c in config.PRIMARY_KEYS.items()],
                      columns=["table", "primary_key"])
    fk = pd.DataFrame(config.FOREIGN_KEYS,
                      columns=["child_table", "child_column", "parent_table", "parent_column"])
    display(pk)
    display(fk)
    """),
    code("""
    # Quick sanity check of the relationships on the raw data (share of child rows with a parent)
    rows = []
    for child, ccol, parent, pcol in config.FOREIGN_KEYS:
        match = raw[child][ccol].isin(set(raw[parent][pcol])).mean() * 100
        rows.append({"relationship": f"{child}.{ccol} -> {parent}.{pcol}", "pct_rows_with_parent": match})
    display(pd.DataFrame(rows))
    """),
])

# ---------------------------------------------------------------------------------- 02
save("02_data_quality_analysis.ipynb", [
    md("""
    # 02 · Data quality analysis
    **Step 4:** missing values, duplicates, incorrect types, inconsistent/invalid values, outliers
    and primary-key uniqueness. This notebook only *inspects*; nothing is changed until notebook 03.
    """),
    code(SETUP),
    code("""
    from src.data_loader import load_raw_tables
    from src.quality import run_quality_report, quality_summary

    raw = load_raw_tables(RAW_DIR)
    report = run_quality_report(raw)      # also saved to reports/data_quality_report.json
    display(quality_summary(report))
    """),
    md("## Missing values"),
    code("""
    miss = pd.DataFrame([(t, c, n, r["missing_pct"][c]) for t, r in report.items()
                         for c, n in r["missing_values"].items()],
                        columns=["table", "column", "missing", "pct"]).sort_values("pct", ascending=False)
    display(miss)
    if len(miss):
        top = miss.head(15).assign(label=lambda d: d["table"] + "." + d["column"])
        sns.barplot(data=top, x="pct", y="label", color="#1b7f5c")
        plt.xlabel("% missing"); plt.ylabel(""); plt.title("Columns with the most missing values")
        plt.show()
    """),
    md("## Duplicates and primary-key uniqueness"),
    code("""
    display(pd.DataFrame([{"table": t, "primary_key": ", ".join(r["primary_key"]),
                           "duplicate_rows": r["duplicate_rows"],
                           "pk_duplicates": r["primary_key_duplicates"],
                           "pk_unique": r["primary_key_unique"]} for t, r in report.items()]))
    """),
    md("## Incorrect data types and invalid values"),
    code("""
    for t, r in report.items():
        print(f"\\n--- {t} ---")
        print("dtypes:", r["dtypes"])
        print("invalid values:", r["invalid_values"] or "none found")
    """),
    md("## Inconsistent categorical values and outliers (IQR rule)"),
    code("""
    for t, r in report.items():
        print(f"\\n--- {t} ---")
        print("text columns whose spellings collapse after trim/case/accent normalisation:",
              r["inconsistent_categorical_variants"] or "none")
        flagged = {c: n for c, n in r["iqr_outliers"].items() if n}
        print("IQR outlier counts:", flagged or "none")
    """),
    md("""
    ### Reading the results
    Record here which issues you found and the handling you choose in notebook 03
    (drop, impute, correct, or keep and flag).
    """),
])

# ---------------------------------------------------------------------------------- 03
save("03_data_cleaning.ipynb", [
    md("""
    # 03 · Data cleaning and preprocessing
    **Step 5:** handle missing values, duplicates, types, dates, categorical values, invalid records
    and column names. Every action is recorded in a cleaning log (`reports/cleaning_log.csv`).
    """),
    code(SETUP),
    code("""
    from src.data_loader import load_raw_tables
    from src.cleaning import clean_all, save_cleaned

    raw = load_raw_tables(RAW_DIR)
    cleaned, log = clean_all(raw)
    display(log)
    """),
    md("## Rows before vs after cleaning"),
    code("""
    display(pd.DataFrame({"raw_rows": {t: len(df) for t, df in raw.items()},
                          "clean_rows": {t: len(df) for t, df in cleaned.items()}})
            .assign(removed=lambda d: d.raw_rows - d.clean_rows))
    """),
    md("## Validate the cleaned data"),
    code("""
    checks = []
    for t, pk in config.PRIMARY_KEYS.items():
        checks.append((f"{t}: primary key unique", not cleaned[t].duplicated(subset=pk).any()))
    for child, ccol, parent, pcol in config.FOREIGN_KEYS:
        checks.append((f"{child}.{ccol} has a parent in {parent}",
                       bool(cleaned[child][ccol].isin(set(cleaned[parent][pcol])).all())))
    checks.append(("review scores within 1-5", bool(cleaned["order_reviews"]["review_score"].between(1, 5).all())))
    checks.append(("item prices positive", bool((cleaned["order_items"]["price"] > 0).all())))
    display(pd.DataFrame(checks, columns=["check", "passed"]))
    """),
    md("## Save cleaned tables to `data/cleaned/`"),
    code("""
    save_cleaned(cleaned, log)
    print("Saved to", config.CLEAN_DIR)
    """),
])

# ---------------------------------------------------------------------------------- 04
save("04_sql_analysis.ipynb", [
    md("""
    # 04 · SQL storage and SQL analysis
    **Step 6 & 10 (SQL part):** create the database from the ER design, load the cleaned data,
    apply primary/foreign keys, verify, then answer business questions with SQL
    (SELECT/WHERE/ORDER BY, GROUP BY/HAVING, joins, subqueries, CTEs, window functions, aggregations).

    Connection settings come from `.env` (copy `.env.example`). Nothing is hardcoded.
    """),
    code(SETUP),
    code(SQL_SETUP),
    md("## Create the database and tables (`sql/schema.sql`)"),
    code("""
    from src.db import create_mysql_database_if_missing
    from src.load_to_sql import create_schema, load_tables, verify_load

    create_mysql_database_if_missing()     # no-op for SQLite
    create_schema(engine)
    print("Schema created")
    """),
    md("## Load cleaned data (from `data/cleaned/`) and verify"),
    code("""
    cleaned = {t: pd.read_csv(config.CLEAN_DIR / f"{t}.csv",
                              dtype={c: "string" for c in config.STRING_COLUMNS.get(t, [])},
                              keep_default_na=True)
               for t in config.TABLE_ORDER}
    # empty comments/titles come back as NaN, which SQL stores as NULL
    load_tables(engine, cleaned)
    display(verify_load(engine, cleaned))
    """),
    md("""
    ## Business questions answered in SQL
    Each query below uses base tables only. The same queries appear on the dashboard's
    **SQL Analysis** page (`streamlit/queries.py`).
    """),
    code("""
    import importlib.util
    spec = importlib.util.spec_from_file_location("c2i_queries", ROOT / "streamlit" / "queries.py")
    q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)

    for name, spec_ in q.ANALYSIS_QUERIES.items():
        print(f"\\n### {spec_['title']}\\nConcepts: {', '.join(spec_['concepts'])}")
        print(spec_["sql"].strip())
        display(query(spec_["sql"]).head(15))
    """),
])

# ---------------------------------------------------------------------------------- 05
save("05_feature_engineering.ipynb", [
    md("""
    # 05 · Feature engineering
    **Step 7:** build business features from the data **read back out of SQL**:

    | Level | Features |
    |---|---|
    | Order | total order value, delivery days, delivery delay, delayed flag, order month, primary category / payment type |
    | Customer | order count, total spending, average order value, repeat-customer indicator, spending tier |
    | Seller | revenue, order count, units sold, average item price, average review score |

    Definitions are documented at the top of `src/features.py`.
    """),
    code(SETUP),
    code(SQL_SETUP),
    code("""
    from src.load_to_sql import read_tables, load_features, write_meta
    from src.features import build_all_features

    tables = read_tables(engine)
    features = build_all_features(tables)
    for name, df in features.items():
        print(name, df.shape)
    """),
    code("""
    of = features["order_features"]
    display(of.head())
    display(of[["total_order_value", "delivery_days", "delivery_delay_days"]].describe())
    """),
    code("""
    display(features["customer_features"].describe(include="all").T.head(12))
    display(features["seller_features"].sort_values("seller_revenue", ascending=False).head(10))
    """),
    md("## Store the feature tables in SQL"),
    code("""
    DATA_SOURCE = "real"      # use "synthetic" if you loaded generated test data
    load_features(engine, features)
    write_meta(engine, DATA_SOURCE)
    display(query("SELECT COUNT(*) AS order_features FROM order_features"))
    """),
])

# ---------------------------------------------------------------------------------- 06
save("06_eda.ipynb", [
    md("""
    # 06 · Exploratory data analysis
    **Step 8:** bring the data from SQL into Python and run univariate, bivariate, multivariate,
    trend, correlation and distribution analysis. Write what you observe under each chart.
    """),
    code(SETUP),
    code(SQL_SETUP),
    code("""
    of = query("SELECT * FROM order_features")
    of["order_purchase_timestamp"] = pd.to_datetime(of["order_purchase_timestamp"])
    valid = of[of["is_valid_sale"] == 1]
    cf = query("SELECT * FROM customer_features")
    sf = query("SELECT * FROM seller_features")
    print(of.shape, cf.shape, sf.shape)
    """),
    md("## Univariate analysis"),
    code("""
    fig, ax = plt.subplots(2, 2, figsize=(13, 8))
    sns.histplot(valid["total_order_value"], bins=50, ax=ax[0, 0]); ax[0, 0].set_title("Order value")
    sns.histplot(np.log1p(valid["total_order_value"]), bins=50, ax=ax[0, 1]); ax[0, 1].set_title("log(1 + order value)")
    sns.countplot(x="review_score", data=of.dropna(subset=["review_score"]), ax=ax[1, 0]); ax[1, 0].set_title("Review scores")
    sns.histplot(of["delivery_days"].dropna(), bins=50, ax=ax[1, 1]); ax[1, 1].set_title("Delivery days")
    plt.tight_layout(); plt.show()
    """),
    code("""
    fig, ax = plt.subplots(1, 3, figsize=(16, 4))
    valid["primary_category"].value_counts().head(12).plot.barh(ax=ax[0], color="#1b7f5c"); ax[0].set_title("Top categories (orders)"); ax[0].invert_yaxis()
    of["order_status"].value_counts().plot.bar(ax=ax[1], color="#1b7f5c"); ax[1].set_title("Order status")
    of["primary_payment_type"].value_counts().plot.bar(ax=ax[2], color="#1b7f5c"); ax[2].set_title("Payment method")
    plt.tight_layout(); plt.show()
    """),
    md("## Bivariate analysis"),
    code("""
    fig, ax = plt.subplots(1, 3, figsize=(17, 5))
    d = of.dropna(subset=["delivery_status", "review_score"])
    sns.boxplot(data=d, x="delivery_status", y="review_score", ax=ax[0]); ax[0].set_title("Review score by delivery status")
    top_cats = valid["primary_category"].value_counts().head(10).index
    sns.boxplot(data=valid[valid["primary_category"].isin(top_cats)], y="primary_category",
                x=np.log1p(valid["total_order_value"]), ax=ax[1]); ax[1].set_title("log order value by category")
    sns.scatterplot(data=d.sample(min(5000, len(d)), random_state=0), x="delivery_delay_days",
                    y="review_score", alpha=0.2, ax=ax[2]); ax[2].set_title("Delay (days) vs review score")
    plt.tight_layout(); plt.show()
    """),
    md("## Multivariate analysis"),
    code("""
    cols = ["total_order_value", "freight_value", "n_items", "delivery_days", "delivery_delay_days", "review_score"]
    sample = valid[cols].dropna().sample(min(3000, len(valid[cols].dropna())), random_state=0)
    sns.pairplot(sample, corner=True, plot_kws={"alpha": 0.3, "s": 12})
    plt.show()
    """),
    code("""
    pivot = valid.dropna(subset=["review_score"]).pivot_table(
        index="customer_state", columns="delivery_status", values="review_score", aggfunc="mean")
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="viridis"); plt.title("Mean review score: state x delivery status")
    plt.show()
    """),
    md("## Trend analysis"),
    code("""
    monthly = valid.groupby("order_month").agg(revenue=("total_order_value", "sum"),
                                               orders=("order_id", "count")).reset_index()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(monthly["order_month"], monthly["revenue"], marker="o", color="#1b7f5c"); ax.set_ylabel("Revenue")
    ax2 = ax.twinx(); ax2.bar(monthly["order_month"], monthly["orders"], alpha=0.25, color="#d97706"); ax2.set_ylabel("Orders")
    plt.xticks(rotation=60); plt.title("Monthly revenue and orders"); plt.show()
    """),
    md("## Correlation analysis"),
    code("""
    num = of[["total_order_value", "freight_value", "n_items", "max_installments", "delivery_days",
              "delivery_delay_days", "review_score", "customer_order_count"]].astype(float)
    corr = num.corr(method="spearman")
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="vlag", center=0); plt.title("Spearman correlation"); plt.show()
    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), 1)).stack().sort_values(key=abs, ascending=False)
    display(pairs.head(8).rename("spearman_rho"))
    """),
    md("## Distribution analysis"),
    code("""
    desc = valid[["total_order_value", "freight_value", "delivery_days"]].describe().T
    desc["skew"] = valid[["total_order_value", "freight_value", "delivery_days"]].skew()
    desc["kurtosis"] = valid[["total_order_value", "freight_value", "delivery_days"]].kurt()
    display(desc)
    """),
    md("## Data-driven summary of what the data shows"),
    code("""
    import importlib.util
    from src.reporting import load_queries_module, default_params, collect_insight_data
    from src.insights import generate_insights

    q = load_queries_module()
    run_sql = lambda sql, params=None: query(sql, params)
    data = collect_insight_data(run_sql, q, default_params(run_sql, q))
    for i in generate_insights(data):
        print(f"[{i['area']}] {i['observation']}\\n   -> {i['interpretation']}\\n")
    """),
])

# ---------------------------------------------------------------------------------- 07
save("07_statistical_analysis.ipynb", [
    md("""
    # 07 · Statistical analysis
    **Step 9.** For each problem: hypothesis → test → assumptions → p-value → decision → business insight.

    | Test | Question |
    |---|---|
    | Independent two-sample t-test | Do delayed orders receive significantly lower review scores than on-time orders? |
    | One-way ANOVA | Does order value differ significantly across product categories? |
    | Chi-square test of independence | Is payment method associated with order status? |

    Implementation: `src/stats_tests.py`. α = 0.05.
    """),
    code(SETUP),
    code(SQL_SETUP),
    code("""
    from src.reporting import load_queries_module, default_params
    from src.stats_tests import ttest_delivery_vs_review, anova_category_vs_order_value, chi_square_payment_vs_status

    q = load_queries_module()
    params = default_params(lambda s, p=None: query(s, p), q)
    orders = query(q.QUERIES["stats_orders"], q.used_params(q.QUERIES["stats_orders"], params))
    print(orders.shape)
    """),
    md("## 1 · T-test: delivery delay vs review score"),
    code("""
    t = ttest_delivery_vs_review(orders)
    import json; print(json.dumps({k: v for k, v in t.items() if k != "assumptions"}, indent=2, default=str))
    display(pd.json_normalize(t["assumptions"]).T)
    d = orders.dropna(subset=["delivery_status", "review_score"])
    sns.barplot(data=d, x="delivery_status", y="review_score", errorbar=("ci", 95)); plt.ylim(0, 5)
    plt.title("Mean review score (95% CI)"); plt.show()
    print("Business insight:", t["business_insight"])
    """),
    md("## 2 · ANOVA: category vs order value"),
    code("""
    a = anova_category_vs_order_value(orders)
    print(json.dumps({k: v for k, v in a.items() if k not in ("assumptions", "category_mean_order_value")}, indent=2, default=str))
    display(pd.json_normalize(a["assumptions"]).T)
    sub = orders[(orders.is_valid_sale == 1) & orders.primary_category.isin(a["categories_tested"])]
    sns.boxplot(data=sub, y="primary_category", x=np.log1p(sub["total_order_value"]), order=a["categories_tested"])
    plt.xlabel("log(1 + order value)"); plt.title("Order value by category"); plt.show()
    print("Business insight:", a["business_insight"])
    """),
    md("## 3 · Chi-square: payment method vs order status"),
    code("""
    c = chi_square_payment_vs_status(orders)
    print(json.dumps({k: v for k, v in c.items() if k not in ("assumptions", "contingency_table")}, indent=2, default=str))
    display(pd.DataFrame(c["contingency_table"]))
    display(pd.json_normalize(c["assumptions"]).T)
    print("Business insight:", c["business_insight"])
    """),
])

if __name__ == "__main__":
    print("Wrote", len(list(NB_DIR.glob("*.ipynb"))), "notebooks to", NB_DIR)
