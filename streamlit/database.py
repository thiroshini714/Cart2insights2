"""Database access for the dashboard. Connection details come from .env / environment only."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # appended, so it can never shadow the real `streamlit` package

from src.db import get_engine  # noqa: E402
from queries import used_params  # noqa: E402


@st.cache_resource(show_spinner="Preparing Cart2Insights database…")
def initialise_database() -> str:
    """Ensure the dashboard database is populated before any dashboard query runs.

    Uses the same environment and database configuration as the pipeline. If all
    nine real CSV files are not available/valid, creates clearly-labelled synthetic
    test data so a fresh Streamlit Cloud deployment can start.
    """
    import os
    import subprocess

    from sqlalchemy import inspect
    from src import config
    from src.data_loader import load_raw_tables

    required_tables = {
        "order_features", "customer_features", "seller_features", "pipeline_meta"
    }
    db_engine = get_engine()

    try:
        inspector = inspect(db_engine)
        existing = set(inspector.get_table_names())
        if required_tables.issubset(existing):
            with db_engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM order_features")).scalar() or 0
            if count > 0:
                return "existing"

        # Prefer real data only when all nine CSVs are present and pass schema validation.
        try:
            load_raw_tables(config.RAW_DIR)
            raw_dir = str(config.RAW_DIR)
            synthetic = False
        except Exception:
            raw_dir = str(config.SYNTHETIC_DIR)
            synthetic = True
            generator = [
                sys.executable, str(ROOT / "scripts" / "make_synthetic_data.py"),
                "--out", raw_dir,
            ]
            generated = subprocess.run(
                generator, cwd=str(ROOT), capture_output=True, text=True, timeout=300,
                env=os.environ.copy(),
            )
            if generated.returncode != 0:
                raise RuntimeError(
                    "Synthetic data generation failed.\n"
                    f"STDOUT:\n{generated.stdout[-5000:]}\n"
                    f"STDERR:\n{generated.stderr[-5000:]}"
                )

        command = [sys.executable, str(ROOT / "run_pipeline.py"),
                   "--raw-dir", raw_dir]
        if synthetic:
            command.append("--synthetic")

        completed = subprocess.run(
            command, cwd=str(ROOT), capture_output=True, text=True, timeout=900,
            env=os.environ.copy(),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "The Cart2Insights data pipeline failed.\n"
                f"STDOUT:\n{completed.stdout[-7000:]}\n"
                f"STDERR:\n{completed.stderr[-7000:]}"
            )

        # Re-inspect the same configured database after the pipeline has completed.
        inspector = inspect(db_engine)
        missing = required_tables - set(inspector.get_table_names())
        if missing:
            raise RuntimeError(
                "Pipeline completed but these required tables are missing: "
                + ", ".join(sorted(missing))
            )
        with db_engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM order_features")).scalar() or 0
        if count == 0:
            raise RuntimeError("Pipeline completed but order_features contains no rows.")

        return "synthetic" if synthetic else "real"
    finally:
        db_engine.dispose()


@st.cache_resource(show_spinner=False)
def engine():
    return get_engine()


@st.cache_data(ttl=600, show_spinner=False)
def run_query(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Execute a parameterised SELECT. `params` is a tuple of (key, value) pairs (hashable)."""
    bound = used_params(sql, dict(params or ()))
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=bound)


def to_params(params: dict) -> tuple:
    return tuple(sorted(params.items()))


def database_ready() -> tuple[bool, str]:
    """True when the feature tables exist and contain data."""
    try:
        with engine().connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM order_features")).scalar()
        if not n:
            return False, "The database is reachable but the tables are empty. Run `python run_pipeline.py`."
        return True, ""
    except Exception as exc:  # noqa: BLE001 - shown to the user, not swallowed silently
        return False, (f"Could not read the database ({type(exc).__name__}: {exc}). "
                       "Check your .env settings and run `python run_pipeline.py` first.")
