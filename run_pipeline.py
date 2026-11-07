"""End-to-end pipeline: raw CSVs -> quality report -> cleaning -> SQL -> features -> stats -> insights.

Usage
-----
    python run_pipeline.py                         # uses data/raw
    python run_pipeline.py --raw-dir data/synthetic --synthetic   # test data (flagged in the DB)
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
from sqlalchemy import text

from src import config
from src.cleaning import clean_all, save_cleaned
from src.data_loader import describe_tables, load_raw_tables
from src.db import create_mysql_database_if_missing, get_engine
from src.features import build_all_features
from src.load_to_sql import (create_schema, load_features, load_tables, read_tables,
                             verify_load, write_meta)
from src.quality import quality_summary, run_quality_report
from src.reporting import generate_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--raw-dir", default=str(config.RAW_DIR))
    parser.add_argument("--synthetic", action="store_true",
                        help="Mark the loaded data as synthetic test data (dashboard shows a warning).")
    args = parser.parse_args(argv)

    print(f"[1/7] Loading raw CSVs from {args.raw_dir}")
    raw = load_raw_tables(args.raw_dir)
    print(describe_tables(raw)[["table", "rows", "columns"]].to_string(index=False))

    print("[2/7] Data quality analysis")
    quality = run_quality_report(raw)
    print(quality_summary(quality).to_string(index=False))

    print("[3/7] Cleaning and preprocessing")
    cleaned, log = clean_all(raw)
    save_cleaned(cleaned, log)
    print(f"      {len(log)} cleaning actions logged -> reports/cleaning_log.csv")

    print("[4/7] Creating database and loading cleaned data")
    create_mysql_database_if_missing()
    engine = get_engine()
    create_schema(engine)
    load_tables(engine, cleaned)
    checks = verify_load(engine, cleaned)
    print(checks.to_string(index=False))
    if not checks["ok"].all():
        print("Verification FAILED - see table above.", file=sys.stderr)
        return 1

    print("[5/7] Feature engineering (from data read back out of SQL)")
    from_sql = read_tables(engine)
    features = build_all_features(from_sql)
    load_features(engine, features)
    write_meta(engine, "synthetic" if args.synthetic else "real")
    for name, df in features.items():
        print(f"      {name}: {len(df):,} rows")

    print("[6/7] Statistical tests and [7/7] business insights")
    def run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    outputs = generate_reports(run_sql)
    print(f"      wrote {', '.join(str(p.relative_to(config.ROOT)) for p in outputs)}")
    print("Pipeline complete. Launch the dashboard with: streamlit run streamlit/app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
