"""Step 5: data cleaning and preprocessing.

Every table has its own function. All changes are recorded in a cleaning log
(table, step, rows affected, detail) so decisions are auditable.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (CLEAN_DIR, FOREIGN_KEYS, REPORTS_DIR, TABLE_ORDER, VALID_ORDER_STATUSES,
                     VALID_PAYMENT_TYPES)

Log = list[dict]


def _log(log: Log, table: str, step: str, n: int, detail: str = "") -> None:
    if n:
        log.append({"table": table, "step": step, "rows_affected": int(n), "detail": detail})


# ----------------------------------------------------------------------------- helpers
def _ascii_lower(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def normalize_text(series: pd.Series) -> pd.Series:
    """Trim, lowercase, strip accents and collapse spaces (applied to unique values only)."""
    s = series.astype("object")
    mapping = {v: _ascii_lower(v) for v in s.dropna().unique()}
    return s.map(mapping)


def pad_zip(series: pd.Series) -> pd.Series:
    """Zip-code prefixes as 5-character text (restores leading zeros lost in CSV round-trips)."""
    s = series.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True)
    return s.str.zfill(5)


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Plain Python/NumPy types so every SQL driver stores NULLs correctly."""
    df = df.reset_index(drop=True).copy()
    for col in df.columns:
        if str(df[col].dtype) in ("string", "str", "object"):
            df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def _drop_missing(df: pd.DataFrame, cols: list[str], table: str, log: Log) -> pd.DataFrame:
    mask = df[cols].isna().any(axis=1)
    _log(log, table, "drop rows missing key columns", mask.sum(), ", ".join(cols))
    return df.loc[~mask]


def _drop_dupes(df: pd.DataFrame, subset: list[str] | None, table: str, log: Log,
                keep: str = "first") -> pd.DataFrame:
    mask = df.duplicated(subset=subset, keep=keep)
    _log(log, table, "remove duplicates", mask.sum(), f"subset={subset or 'all columns'}")
    return df.loc[~mask]


# ----------------------------------------------------------------------------- tables
def clean_translation(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    for c in ("product_category_name", "product_category_name_english"):
        df[c] = normalize_text(df[c])
    df = _drop_missing(df, ["product_category_name"], "product_category_name_translation", log)
    df = _drop_dupes(df, ["product_category_name"], "product_category_name_translation", log)
    return _finalize(df)


def clean_customers(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = _drop_missing(df, ["customer_id", "customer_unique_id"], "customers", log)
    df["customer_zip_code_prefix"] = pad_zip(df["customer_zip_code_prefix"])
    before = df["customer_city"].nunique()
    df["customer_city"] = normalize_text(df["customer_city"])
    _log(log, "customers", "standardise city names", before - df["customer_city"].nunique(),
         "distinct spellings merged (trim/case/accents)")
    df["customer_state"] = df["customer_state"].astype("string").str.strip().str.upper()
    df = _drop_dupes(df, ["customer_id"], "customers", log)
    return _finalize(df)


def clean_sellers(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = _drop_missing(df, ["seller_id"], "sellers", log)
    df["seller_zip_code_prefix"] = pad_zip(df["seller_zip_code_prefix"])
    before = df["seller_city"].nunique()
    df["seller_city"] = normalize_text(df["seller_city"])
    _log(log, "sellers", "standardise city names", before - df["seller_city"].nunique(),
         "distinct spellings merged")
    df["seller_state"] = df["seller_state"].astype("string").str.strip().str.upper()
    df = _drop_dupes(df, ["seller_id"], "sellers", log)
    return _finalize(df)


def clean_geolocation(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    """Collapse the many coordinate rows per zip prefix to one row (mean lat/lng, modal city)."""
    df = df.copy()
    df["geolocation_zip_code_prefix"] = pad_zip(df["geolocation_zip_code_prefix"])
    for c in ("geolocation_lat", "geolocation_lng"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = (df["geolocation_lat"].between(-90, 90) & df["geolocation_lng"].between(-180, 180)) == False  # noqa: E712
    _log(log, "geolocation", "drop invalid coordinates", bad.sum(), "lat/lng out of range or missing")
    df = df.loc[~bad & df["geolocation_zip_code_prefix"].notna()].copy()
    df["geolocation_city"] = normalize_text(df["geolocation_city"])
    df["geolocation_state"] = df["geolocation_state"].astype("string").str.strip().str.upper()

    n_before = len(df)
    coords = df.groupby("geolocation_zip_code_prefix", as_index=False).agg(
        geolocation_lat=("geolocation_lat", "mean"), geolocation_lng=("geolocation_lng", "mean"))
    modal = (df.groupby(["geolocation_zip_code_prefix", "geolocation_city", "geolocation_state"],
                        as_index=False, dropna=False).size()
             .sort_values(["geolocation_zip_code_prefix", "size"], ascending=[True, False])
             .drop_duplicates("geolocation_zip_code_prefix")
             .drop(columns="size"))
    out = coords.merge(modal, on="geolocation_zip_code_prefix", how="left")
    _log(log, "geolocation", "aggregate to one row per zip prefix", n_before - len(out),
         "duplicate zip rows collapsed (mean coordinates)")
    return _finalize(out)


def clean_products(df: pd.DataFrame, translation: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns={"product_name_lenght": "product_name_length",
                            "product_description_lenght": "product_description_length"})
    df = _drop_missing(df, ["product_id"], "products", log)
    df = _drop_dupes(df, ["product_id"], "products", log)

    df["product_category_name"] = normalize_text(df["product_category_name"])
    n_missing_cat = df["product_category_name"].isna().sum()
    df["product_category_name"] = df["product_category_name"].fillna("unknown")
    _log(log, "products", "fill missing category", n_missing_cat, "set to 'unknown'")

    numeric = ["product_name_length", "product_description_length", "product_photos_qty",
               "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
    for c in numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"):
        bad = df[c] <= 0
        _log(log, "products", f"invalid {c} set to missing", bad.sum(), "value <= 0")
        df.loc[bad, c] = np.nan
    for c in [c for c in numeric if c in df.columns]:
        n_missing = df[c].isna().sum()
        by_cat = df.groupby("product_category_name")[c].transform("median")
        df[c] = df[c].fillna(by_cat).fillna(df[c].median())
        _log(log, "products", f"impute {c}", n_missing, "category median, then global median")
    for c in ("product_name_length", "product_description_length", "product_photos_qty"):
        if c in df.columns:
            df[c] = df[c].round().astype("Int64")

    lookup = dict(zip(translation["product_category_name"],
                      translation["product_category_name_english"]))
    english = df["product_category_name"].map(lookup)
    n_untranslated = (english.isna() & (df["product_category_name"] != "unknown")).sum()
    df["product_category_name_english"] = english.fillna(df["product_category_name"])
    _log(log, "products", "category without English translation", n_untranslated,
         "fell back to the original category name")
    return _finalize(df)


def clean_orders(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = _drop_missing(df, ["order_id", "customer_id"], "orders", log)
    df = _drop_dupes(df, ["order_id"], "orders", log)

    status = normalize_text(df["order_status"]).replace({"cancelled": "canceled"})
    unknown = ~status.isin(VALID_ORDER_STATUSES)
    _log(log, "orders", "unknown order status", unknown.sum(), "rows dropped")
    df["order_status"] = status
    df = df.loc[~unknown].copy()

    date_cols = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                 "order_delivered_customer_date", "order_estimated_delivery_date"]
    for c in date_cols:
        parsed = pd.to_datetime(df[c], errors="coerce")
        _log(log, "orders", f"unparseable {c} set to missing", (parsed.isna() & df[c].notna()).sum())
        df[c] = parsed

    df = _drop_missing(df, ["order_purchase_timestamp"], "orders", log)

    bad = df["order_delivered_customer_date"] < df["order_purchase_timestamp"]
    _log(log, "orders", "delivered before purchase -> delivery date set to missing", bad.sum(),
         "impossible timeline")
    df.loc[bad, "order_delivered_customer_date"] = pd.NaT

    n_no_date = (df["order_status"].eq("delivered") & df["order_delivered_customer_date"].isna()).sum()
    _log(log, "orders", "delivered orders without delivery date (kept)", n_no_date,
         "excluded from delivery metrics only")
    return _finalize(df)


def clean_order_items(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = _drop_missing(df, ["order_id", "order_item_id", "product_id", "seller_id"],
                       "order_items", log)
    df["order_item_id"] = pd.to_numeric(df["order_item_id"], errors="coerce").astype("Int64")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce")
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    df = _drop_dupes(df, ["order_id", "order_item_id"], "order_items", log)

    bad_price = df["price"].isna() | (df["price"] <= 0)
    _log(log, "order_items", "drop invalid price", bad_price.sum(), "missing or <= 0")
    df = df.loc[~bad_price].copy()
    bad_freight = df["freight_value"] < 0
    _log(log, "order_items", "drop negative freight", bad_freight.sum())
    df = df.loc[~bad_freight].copy()
    _log(log, "order_items", "fill missing freight with 0", df["freight_value"].isna().sum())
    df["freight_value"] = df["freight_value"].fillna(0.0)
    df["order_item_id"] = df["order_item_id"].astype(int)
    return _finalize(df)


def clean_order_payments(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    df = df.copy()
    df = _drop_missing(df, ["order_id", "payment_sequential"], "order_payments", log)
    df["payment_sequential"] = pd.to_numeric(df["payment_sequential"], errors="coerce").astype("Int64")
    df["payment_type"] = normalize_text(df["payment_type"]).str.replace(" ", "_", regex=False)
    unknown = ~df["payment_type"].isin(VALID_PAYMENT_TYPES)
    _log(log, "order_payments", "unknown/missing payment type -> 'not_defined'", unknown.sum())
    df.loc[unknown, "payment_type"] = "not_defined"
    df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce")
    bad = df["payment_value"].isna() | (df["payment_value"] < 0)
    _log(log, "order_payments", "drop invalid payment_value", bad.sum(), "missing or negative")
    df = df.loc[~bad].copy()
    df["payment_installments"] = pd.to_numeric(df["payment_installments"], errors="coerce")
    low = df["payment_installments"].isna() | (df["payment_installments"] < 1)
    _log(log, "order_payments", "installments < 1 set to 1", low.sum())
    df.loc[low, "payment_installments"] = 1
    df["payment_installments"] = df["payment_installments"].astype(int)
    df = _drop_dupes(df, ["order_id", "payment_sequential"], "order_payments", log)
    df["payment_sequential"] = df["payment_sequential"].astype(int)
    return _finalize(df)


def clean_order_reviews(df: pd.DataFrame, log: Log) -> pd.DataFrame:
    """Keep one review per order (the latest answered), with valid 1-5 scores only."""
    df = df.copy()
    df = _drop_missing(df, ["review_id", "order_id"], "order_reviews", log)
    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    bad = ~df["review_score"].isin([1, 2, 3, 4, 5])
    _log(log, "order_reviews", "drop invalid review_score", bad.sum(), "not an integer 1-5")
    df = df.loc[~bad].copy()
    df["review_score"] = df["review_score"].astype(int)
    for c in ("review_creation_date", "review_answer_timestamp"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = _drop_dupes(df, None, "order_reviews", log)
    df = df.sort_values(["order_id", "review_answer_timestamp"], na_position="first")
    dup_orders = df.duplicated("order_id", keep="last")
    _log(log, "order_reviews", "keep latest review per order", dup_orders.sum(),
         "older reviews of the same order dropped")
    df = df.loc[~dup_orders].copy()
    for c in ("review_comment_title", "review_comment_message"):
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    df["has_comment"] = df["review_comment_message"].notna().astype(int)
    return _finalize(df)


# ----------------------------------------------------------------------------- integrity
def enforce_referential_integrity(tables: dict[str, pd.DataFrame], log: Log) -> dict[str, pd.DataFrame]:
    """Drop child rows whose parent key no longer exists, in dependency order."""
    for child, child_col, parent, parent_col in FOREIGN_KEYS:
        valid = set(tables[parent][parent_col])
        orphan = ~tables[child][child_col].isin(valid)
        _log(log, child, f"orphan rows removed (no matching {parent}.{parent_col})", orphan.sum())
        if orphan.any():
            tables[child] = tables[child].loc[~orphan].reset_index(drop=True)
    return tables


# ----------------------------------------------------------------------------- orchestration
def clean_all(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Clean all 9 tables. Returns (cleaned tables in load order, cleaning log DataFrame)."""
    log: Log = []
    t: dict[str, pd.DataFrame] = {}
    t["product_category_name_translation"] = clean_translation(
        raw["product_category_name_translation"], log)
    t["geolocation"] = clean_geolocation(raw["geolocation"], log)
    t["customers"] = clean_customers(raw["customers"], log)
    t["sellers"] = clean_sellers(raw["sellers"], log)
    t["products"] = clean_products(raw["products"], t["product_category_name_translation"], log)
    t["orders"] = clean_orders(raw["orders"], log)
    t["order_items"] = clean_order_items(raw["order_items"], log)
    t["order_payments"] = clean_order_payments(raw["order_payments"], log)
    t["order_reviews"] = clean_order_reviews(raw["order_reviews"], log)
    t = enforce_referential_integrity(t, log)
    ordered = {name: t[name] for name in TABLE_ORDER}
    return ordered, pd.DataFrame(log, columns=["table", "step", "rows_affected", "detail"])


def save_cleaned(tables: dict[str, pd.DataFrame], log: pd.DataFrame,
                 out_dir: Path = CLEAN_DIR) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log.to_csv(REPORTS_DIR / "cleaning_log.csv", index=False)
    (REPORTS_DIR / "cleaning_log.json").write_text(json.dumps(log.to_dict("records"), indent=2))
