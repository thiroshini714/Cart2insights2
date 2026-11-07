"""Step 7: feature engineering. Builds order-, customer- and seller-level feature tables.

Definitions
-----------
total_order_value    = sum(item price) + sum(freight) for the order
delivery_days        = delivered_customer_date - purchase_timestamp (delivered orders only)
delivery_delay_days  = delivered_customer_date - estimated_delivery_date (>0 means late)
is_valid_sale        = order has items and status is not canceled/unavailable
customer             = customer_unique_id (customer_id is issued per order)
is_repeat_customer   = customer has more than one valid-sale order
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INVALID_SALE_STATUSES

ORDER_FEATURE_COLUMNS = [
    "order_id", "customer_id", "customer_unique_id", "customer_city", "customer_state",
    "order_status", "order_purchase_timestamp", "order_month", "items_value", "freight_value",
    "total_order_value", "n_items", "n_sellers", "primary_category", "primary_payment_type",
    "payment_value_total", "n_payment_methods", "max_installments", "review_score",
    "delivery_days", "delivery_delay_days", "is_delayed", "delivery_status", "is_valid_sale",
    "customer_order_count", "is_repeat_customer",
]
CUSTOMER_FEATURE_COLUMNS = [
    "customer_unique_id", "customer_city", "customer_state", "order_count", "total_spending",
    "avg_order_value", "first_order_date", "last_order_date", "is_repeat_customer",
    "spending_tier",
]
SELLER_FEATURE_COLUMNS = [
    "seller_id", "seller_city", "seller_state", "seller_revenue", "seller_order_count",
    "units_sold", "avg_item_price", "avg_review_score", "reviewed_orders",
]

_DATE_COLS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
}


def _prepare(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Defensive copy with dates parsed (tables read back from SQL may hold date strings)."""
    t = {k: v.copy() for k, v in tables.items()}
    for name, cols in _DATE_COLS.items():
        for c in cols:
            t[name][c] = pd.to_datetime(t[name][c], errors="coerce")
    return t


def _days(delta: pd.Series) -> pd.Series:
    return delta.dt.total_seconds() / 86400


def build_order_features(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    t = _prepare(tables)
    orders, items, products = t["orders"], t["order_items"], t["products"]
    payments, reviews, customers = t["order_payments"], t["order_reviews"], t["customers"]

    item_agg = items.groupby("order_id").agg(
        items_value=("price", "sum"), freight_value=("freight_value", "sum"),
        n_items=("order_item_id", "count"), n_sellers=("seller_id", "nunique")).reset_index()

    item_cat = items.merge(products[["product_id", "product_category_name_english"]],
                           on="product_id", how="left")
    primary_cat = (item_cat.sort_values(["order_id", "price", "order_item_id"],
                                        ascending=[True, False, True])
                   .drop_duplicates("order_id")[["order_id", "product_category_name_english"]]
                   .rename(columns={"product_category_name_english": "primary_category"}))

    primary_pay = (payments.sort_values(["order_id", "payment_value"], ascending=[True, False])
                   .drop_duplicates("order_id")[["order_id", "payment_type"]]
                   .rename(columns={"payment_type": "primary_payment_type"}))
    pay_agg = payments.groupby("order_id").agg(
        payment_value_total=("payment_value", "sum"),
        n_payment_methods=("payment_type", "nunique"),
        max_installments=("payment_installments", "max")).reset_index()

    cust = customers[["customer_id", "customer_unique_id", "customer_city", "customer_state"]]

    df = (orders.merge(cust, on="customer_id", how="left")
          .merge(item_agg, on="order_id", how="left")
          .merge(primary_cat, on="order_id", how="left")
          .merge(primary_pay, on="order_id", how="left")
          .merge(pay_agg, on="order_id", how="left")
          .merge(reviews[["order_id", "review_score"]], on="order_id", how="left"))

    for c in ("items_value", "freight_value", "payment_value_total"):
        df[c] = df[c].fillna(0.0)
    for c in ("n_items", "n_sellers", "n_payment_methods"):
        df[c] = df[c].fillna(0).astype(int)
    df["max_installments"] = df["max_installments"].astype("Int64")
    df["primary_category"] = df["primary_category"].fillna("unknown")
    df["primary_payment_type"] = df["primary_payment_type"].fillna("unknown")
    df["total_order_value"] = (df["items_value"] + df["freight_value"]).round(2)
    df["order_month"] = df["order_purchase_timestamp"].dt.strftime("%Y-%m")

    delivered = (df["order_status"].eq("delivered")
                 & df["order_delivered_customer_date"].notna())
    df["delivery_days"] = _days(df["order_delivered_customer_date"]
                                - df["order_purchase_timestamp"]).where(delivered).round(2)
    delay = _days(df["order_delivered_customer_date"]
                  - df["order_estimated_delivery_date"]).where(delivered).round(2)
    df["delivery_delay_days"] = delay
    df["is_delayed"] = (delay > 0).astype("Int64").where(delay.notna())
    df["delivery_status"] = pd.Series(
        np.where(delay.isna(), None, np.where(delay > 0, "Delayed", "On time")),
        index=df.index, dtype="object")

    df["is_valid_sale"] = ((~df["order_status"].isin(INVALID_SALE_STATUSES))
                           & (df["n_items"] > 0)).astype(int)

    # customer-level repeat information, based on valid sales only
    valid = df[df["is_valid_sale"] == 1]
    counts = valid.groupby("customer_unique_id")["order_id"].nunique().rename("customer_order_count")
    df = df.merge(counts, on="customer_unique_id", how="left")
    df["customer_order_count"] = df["customer_order_count"].fillna(0).astype(int)
    df["is_repeat_customer"] = (df["customer_order_count"] > 1).astype(int)

    return df[ORDER_FEATURE_COLUMNS].reset_index(drop=True)


def build_customer_features(order_features: pd.DataFrame) -> pd.DataFrame:
    valid = order_features[order_features["is_valid_sale"] == 1].sort_values(
        "order_purchase_timestamp")
    cf = valid.groupby("customer_unique_id").agg(
        customer_city=("customer_city", "last"), customer_state=("customer_state", "last"),
        order_count=("order_id", "nunique"), total_spending=("total_order_value", "sum"),
        avg_order_value=("total_order_value", "mean"),
        first_order_date=("order_purchase_timestamp", "min"),
        last_order_date=("order_purchase_timestamp", "max")).reset_index()
    cf["total_spending"] = cf["total_spending"].round(2)
    cf["avg_order_value"] = cf["avg_order_value"].round(2)
    cf["is_repeat_customer"] = (cf["order_count"] > 1).astype(int)
    if len(cf) >= 3:
        cf["spending_tier"] = pd.qcut(cf["total_spending"].rank(method="first"), 3,
                                      labels=["Low", "Medium", "High"]).astype(str)
    else:
        cf["spending_tier"] = "Low"
    return cf[CUSTOMER_FEATURE_COLUMNS]


def build_seller_features(tables: dict[str, pd.DataFrame],
                          order_features: pd.DataFrame) -> pd.DataFrame:
    t = _prepare(tables)
    valid_orders = order_features.loc[order_features["is_valid_sale"] == 1,
                                      ["order_id", "review_score"]]
    vi = t["order_items"].merge(valid_orders, on="order_id", how="inner")
    vi["gmv"] = vi["price"] + vi["freight_value"]
    agg = vi.groupby("seller_id").agg(
        seller_revenue=("gmv", "sum"), seller_order_count=("order_id", "nunique"),
        units_sold=("order_item_id", "count"), avg_item_price=("price", "mean")).reset_index()
    per_order = vi.drop_duplicates(["seller_id", "order_id"]).groupby("seller_id").agg(
        avg_review_score=("review_score", "mean"),
        reviewed_orders=("review_score", "count")).reset_index()
    sf = (agg.merge(per_order, on="seller_id", how="left")
          .merge(t["sellers"][["seller_id", "seller_city", "seller_state"]],
                 on="seller_id", how="left"))
    for c in ("seller_revenue", "avg_item_price", "avg_review_score"):
        sf[c] = sf[c].round(2)
    return sf[SELLER_FEATURE_COLUMNS]


def build_all_features(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    order_features = build_order_features(tables)
    return {
        "order_features": order_features,
        "customer_features": build_customer_features(order_features),
        "seller_features": build_seller_features(tables, order_features),
    }
