"""Central configuration: paths, table metadata and business rules."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

RAW_DIR = Path(os.getenv("RAW_DATA_DIR") or ROOT / "data" / "raw")
CLEAN_DIR = Path(os.getenv("CLEAN_DATA_DIR") or ROOT / "data" / "cleaned")
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
REPORTS_DIR = ROOT / "reports"
SCHEMA_FILE = ROOT / "sql" / "schema.sql"

# Tables in foreign-key-safe load order (parents before children).
TABLE_ORDER = [
    "geolocation",
    "product_category_name_translation",
    "customers",
    "sellers",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
]

FEATURE_TABLES = ["order_features", "customer_features", "seller_features"]

PRIMARY_KEYS = {
    "geolocation": ["geolocation_zip_code_prefix"],
    "product_category_name_translation": ["product_category_name"],
    "customers": ["customer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id"],
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["review_id", "order_id"],
}

# (child_table, child_column, parent_table, parent_column)
FOREIGN_KEYS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("order_payments", "order_id", "orders", "order_id"),
    ("order_reviews", "order_id", "orders", "order_id"),
]

# Columns that must be read as text so IDs and zip codes keep leading zeros.
STRING_COLUMNS = {
    "customers": ["customer_id", "customer_unique_id", "customer_zip_code_prefix"],
    "geolocation": ["geolocation_zip_code_prefix"],
    "orders": ["order_id", "customer_id"],
    "order_items": ["order_id", "product_id", "seller_id"],
    "order_payments": ["order_id"],
    "order_reviews": ["review_id", "order_id"],
    "products": ["product_id"],
    "sellers": ["seller_id", "seller_zip_code_prefix"],
}

# Columns every raw table must contain. (The misspelled "lenght" columns of the
# original product table are handled in cleaning, so they are not required here.)
REQUIRED_COLUMNS = {
    "customers": ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                  "customer_city", "customer_state"],
    "geolocation": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
                    "geolocation_city", "geolocation_state"],
    "orders": ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
               "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id",
                    "shipping_limit_date", "price", "freight_value"],
    "order_payments": ["order_id", "payment_sequential", "payment_type",
                       "payment_installments", "payment_value"],
    "order_reviews": ["review_id", "order_id", "review_score", "review_comment_title",
                      "review_comment_message", "review_creation_date",
                      "review_answer_timestamp"],
    "products": ["product_id", "product_category_name", "product_photos_qty",
                 "product_weight_g", "product_length_cm", "product_height_cm",
                 "product_width_cm"],
    "sellers": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "product_category_name_translation": ["product_category_name",
                                          "product_category_name_english"],
}

# Business rules
INVALID_SALE_STATUSES = ("canceled", "unavailable")  # excluded from revenue
VALID_ORDER_STATUSES = ("created", "approved", "invoiced", "processing", "shipped",
                        "delivered", "canceled", "unavailable")
VALID_PAYMENT_TYPES = ("credit_card", "boleto", "voucher", "debit_card", "not_defined")
ALPHA = 0.05  # significance level for hypothesis tests
