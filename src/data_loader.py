"""Step 3: load the raw CSV files with Pandas and validate their structure."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import RAW_DIR, REQUIRED_COLUMNS, STRING_COLUMNS, TABLE_ORDER


def _normalised_stem(path: Path) -> str:
    stem = path.stem.lower()
    stem = re.sub(r"^olist_", "", stem)
    return re.sub(r"_dataset$", "", stem)


def find_csv(raw_dir: Path, table: str) -> Path:
    """Locate the CSV for a table, tolerating prefixes such as 'olist_' / '_dataset'."""
    files = sorted(Path(raw_dir).glob("*.csv"))
    exact = [f for f in files if _normalised_stem(f) == table]
    if exact:
        return exact[0]
    loose = [f for f in files if table in f.stem.lower()]
    if len(loose) == 1:
        return loose[0]
    raise FileNotFoundError(
        f"Could not find a CSV for table '{table}' in {raw_dir}. "
        f"Found: {[f.name for f in files] or 'no CSV files'}."
    )


def load_raw_tables(raw_dir: Path | str = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Load all 9 raw tables. IDs and zip codes are read as text; other types are inferred."""
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"Raw data folder not found: {raw_dir}. Place the 9 Cart2Insights CSV files there "
            "(or run `python scripts/make_synthetic_data.py` to generate test data)."
        )
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_ORDER:
        path = find_csv(raw_dir, name)
        dtype = {c: "string" for c in STRING_COLUMNS.get(name, [])}
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=dtype)
        df.columns = [c.strip() for c in df.columns]
        missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
        if missing:
            raise ValueError(
                f"{path.name}: missing expected columns {missing}. "
                f"Columns found: {list(df.columns)}"
            )
        tables[name] = df
    return tables


def describe_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Shape / columns / dtype overview of every table (Step 3 output)."""
    rows = []
    for name, df in tables.items():
        rows.append({
            "table": name,
            "rows": len(df),
            "columns": df.shape[1],
            "column_names": ", ".join(df.columns),
            "dtypes": ", ".join(f"{c}:{t}" for c, t in df.dtypes.astype(str).items()),
        })
    return pd.DataFrame(rows)
