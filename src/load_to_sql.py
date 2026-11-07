"""Step 6: create the database schema, load cleaned data and verify it (SQLAlchemy)."""
from __future__ import annotations

import re

import pandas as pd
from sqlalchemy import text

from .config import FEATURE_TABLES, FOREIGN_KEYS, SCHEMA_FILE, TABLE_ORDER

ALL_TABLES = TABLE_ORDER + FEATURE_TABLES + ["pipeline_meta"]
DATE_COLUMNS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
    "order_features": ["order_purchase_timestamp"],
    "customer_features": ["first_order_date", "last_order_date"],
}


def _statements(sql_text: str) -> list[str]:
    no_comments = re.sub(r"--[^\n]*", "", sql_text)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def create_schema(engine, drop_existing: bool = True) -> None:
    """Run sql/schema.sql (tables with primary and foreign keys)."""
    with engine.begin() as conn:
        if drop_existing:
            if engine.dialect.name == "mysql":
                conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in reversed(ALL_TABLES):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            if engine.dialect.name == "mysql":
                conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        for stmt in _statements(SCHEMA_FILE.read_text()):
            conn.execute(text(stmt))


def _write(engine, table: str, df: pd.DataFrame, chunksize: int = 5000) -> None:
    df = df.copy()
    for col in DATE_COLUMNS.get(table, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df.to_sql(table, engine, if_exists="append", index=False, chunksize=chunksize)


def load_tables(engine, tables: dict[str, pd.DataFrame]) -> None:
    """Load base tables in FK-safe order."""
    for name in TABLE_ORDER:
        _write(engine, name, tables[name])


def load_features(engine, features: dict[str, pd.DataFrame]) -> None:
    for name in FEATURE_TABLES:
        _write(engine, name, features[name])


def write_meta(engine, data_source: str, extra: dict[str, str] | None = None) -> None:
    """Record whether the data is 'real' or 'synthetic' so the dashboard can warn."""
    from datetime import datetime, timezone

    meta = {"data_source": data_source,
            "loaded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            **(extra or {})}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_meta"))
        for k, v in meta.items():
            conn.execute(text("INSERT INTO pipeline_meta (meta_key, meta_value) VALUES (:k, :v)"),
                         {"k": k, "v": str(v)})


def read_tables(engine) -> dict[str, pd.DataFrame]:
    """Bring the base tables back from SQL into Pandas (Step 8 starting point)."""
    with engine.connect() as conn:
        return {name: pd.read_sql(text(f"SELECT * FROM {name}"), conn) for name in TABLE_ORDER}


def verify_load(engine, expected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compare row counts with the DataFrames loaded and count orphaned foreign keys."""
    rows = []
    with engine.connect() as conn:
        for name, df in expected.items():
            n_sql = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            rows.append({"check": f"row count: {name}", "expected": len(df),
                         "actual": int(n_sql), "ok": len(df) == int(n_sql)})
        for child, ccol, parent, pcol in FOREIGN_KEYS:
            orphans = conn.execute(text(
                f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{ccol} = p.{pcol} "
                f"WHERE p.{pcol} IS NULL")).scalar()
            rows.append({"check": f"orphans: {child}.{ccol} -> {parent}.{pcol}", "expected": 0,
                         "actual": int(orphans), "ok": int(orphans) == 0})
    result = pd.DataFrame(rows)
    return result
