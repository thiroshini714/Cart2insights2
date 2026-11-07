"""Step 4: data quality analysis (read-only; nothing is modified here)."""
from __future__ import annotations

import json
import unicodedata

import numpy as np
import pandas as pd

from .config import PRIMARY_KEYS, REPORTS_DIR, VALID_ORDER_STATUSES, VALID_PAYMENT_TYPES

DATE_COLUMNS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def _ascii_lower(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def invalid_value_checks(name: str, df: pd.DataFrame) -> dict[str, int]:
    """Count rule violations per table (types are coerced first, never modified in place)."""
    out: dict[str, int] = {}
    if name == "orders":
        dates = {c: pd.to_datetime(df[c], errors="coerce") for c in DATE_COLUMNS["orders"]}
        for c, parsed in dates.items():
            out[f"unparseable_{c}"] = int((parsed.isna() & df[c].notna()).sum())
        out["delivered_before_purchase"] = int(
            (dates["order_delivered_customer_date"] < dates["order_purchase_timestamp"]).sum())
        out["approved_before_purchase"] = int(
            (dates["order_approved_at"] < dates["order_purchase_timestamp"]).sum())
        status = df["order_status"].astype("string").str.strip().str.lower()
        out["unknown_order_status"] = int((~status.isin(VALID_ORDER_STATUSES) & status.notna()).sum())
        out["delivered_without_delivery_date"] = int(
            (status.eq("delivered") & dates["order_delivered_customer_date"].isna()).sum())
    elif name == "order_items":
        out["price_not_positive"] = int((_num(df, "price") <= 0).sum())
        out["freight_negative"] = int((_num(df, "freight_value") < 0).sum())
    elif name == "order_payments":
        out["payment_value_negative"] = int((_num(df, "payment_value") < 0).sum())
        out["installments_below_1"] = int((_num(df, "payment_installments") < 1).sum())
        ptype = df["payment_type"].astype("string").str.strip().str.lower()
        out["unknown_payment_type"] = int((~ptype.isin(VALID_PAYMENT_TYPES) & ptype.notna()).sum())
    elif name == "order_reviews":
        score = _num(df, "review_score")
        out["score_outside_1_to_5"] = int(((score < 1) | (score > 5) | score.isna()).sum())
    elif name == "products":
        for c in ("product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"):
            out[f"{c}_not_positive"] = int((_num(df, c) <= 0).sum())
    elif name == "geolocation":
        lat, lng = _num(df, "geolocation_lat"), _num(df, "geolocation_lng")
        out["lat_out_of_range"] = int(((lat < -90) | (lat > 90)).sum())
        out["lng_out_of_range"] = int(((lng < -180) | (lng > 180)).sum())
    elif name in ("customers", "sellers"):
        col = "customer_state" if name == "customers" else "seller_state"
        state = df[col].astype("string").str.strip()
        out["state_not_two_letters"] = int((state.str.len() != 2).sum())
    return out


def inconsistent_categories(df: pd.DataFrame) -> dict[str, int]:
    """Text columns whose distinct raw values collapse after trim/case/accent normalisation."""
    out = {}
    for col in df.columns:
        if str(df[col].dtype) in ("object", "string", "str") and df[col].nunique() < 5000:
            raw = df[col].dropna().astype(str).unique()
            collapsed = {_ascii_lower(v) for v in raw}
            if len(raw) > len(collapsed):
                out[col] = int(len(raw) - len(collapsed))
    return out


def iqr_outliers(df: pd.DataFrame) -> dict[str, int]:
    out = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) < 10:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        out[col] = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
    return out


def profile_table(name: str, df: pd.DataFrame) -> dict:
    """Full quality profile of one table."""
    pk = PRIMARY_KEYS[name]
    missing = df.isna().sum()
    pk_dupes = int(df.duplicated(subset=pk).sum()) if all(c in df.columns for c in pk) else None
    return {
        "table": name,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing_values": {c: int(n) for c, n in missing.items() if n > 0},
        "missing_pct": {c: round(float(n) / max(len(df), 1) * 100, 2)
                        for c, n in missing.items() if n > 0},
        "duplicate_rows": int(df.duplicated().sum()),
        "primary_key": pk,
        "primary_key_duplicates": pk_dupes,
        "primary_key_unique": pk_dupes == 0,
        "invalid_values": {k: v for k, v in invalid_value_checks(name, df).items() if v},
        "inconsistent_categorical_variants": inconsistent_categories(df),
        "iqr_outliers": iqr_outliers(df),
    }


def run_quality_report(tables: dict[str, pd.DataFrame], save: bool = True) -> dict[str, dict]:
    report = {name: profile_table(name, df) for name, df in tables.items()}
    if save:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "data_quality_report.json").write_text(json.dumps(report, indent=2))
    return report


def quality_summary(report: dict[str, dict]) -> pd.DataFrame:
    """One row per table: headline quality counts."""
    rows = []
    for name, r in report.items():
        rows.append({
            "table": name,
            "rows": r["rows"],
            "columns_with_missing": len(r["missing_values"]),
            "total_missing_cells": sum(r["missing_values"].values()),
            "duplicate_rows": r["duplicate_rows"],
            "pk_duplicates": r["primary_key_duplicates"],
            "invalid_value_rules_hit": len(r["invalid_values"]),
            "invalid_records": sum(r["invalid_values"].values()),
            "text_cols_with_variants": len(r["inconsistent_categorical_variants"]),
            "numeric_cols_with_outliers": sum(1 for v in r["iqr_outliers"].values() if v),
        })
    return pd.DataFrame(rows)
