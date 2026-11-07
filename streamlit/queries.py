"""All SQL used for analysis. Portable across MySQL 8+ and SQLite 3.25+.

Filter parameters (named, bound - never string-formatted):
    :start_month, :end_month   'YYYY-MM' strings
    :state                     two-letter state or 'All'
    :category                  English product category or 'All'
Optional: :min_orders, :top_n

Revenue ("GMV") = item price + freight, over valid sales (not canceled / unavailable).
Category filter: order-level queries use the order's primary (highest-priced) category;
item-level queries use each item's own category.
"""
from __future__ import annotations

import re

VALID = "f.is_valid_sale = 1"

ORDER_FILTER = """f.order_month BETWEEN :start_month AND :end_month
      AND (:state = 'All' OR f.customer_state = :state)
      AND (:category = 'All' OR f.primary_category = :category)"""

ITEM_FILTER = """f.order_month BETWEEN :start_month AND :end_month
      AND (:state = 'All' OR f.customer_state = :state)
      AND (:category = 'All' OR p.product_category_name_english = :category)"""

# Delay buckets are shared by several queries (day boundaries are inclusive on the right).
DELAY_BUCKET = """CASE
        WHEN f.delivery_delay_days <= -7 THEN '1: 7+ days early'
        WHEN f.delivery_delay_days <= 0 THEN '2: 0-7 days early'
        WHEN f.delivery_delay_days <= 3 THEN '3: 1-3 days late'
        WHEN f.delivery_delay_days <= 7 THEN '4: 4-7 days late'
        WHEN f.delivery_delay_days <= 14 THEN '5: 8-14 days late'
        ELSE '6: 15+ days late' END"""

# --------------------------------------------------------------------------- metadata
FILTER_OPTIONS = {
    "months": "SELECT DISTINCT order_month FROM order_features ORDER BY order_month",
    "states": "SELECT DISTINCT customer_state FROM order_features "
              "WHERE customer_state IS NOT NULL ORDER BY customer_state",
    "categories": "SELECT DISTINCT primary_category FROM order_features "
                  "WHERE is_valid_sale = 1 ORDER BY primary_category",
    "data_source": "SELECT meta_value FROM pipeline_meta WHERE meta_key = 'data_source'",
}

# --------------------------------------------------------------------------- dashboard queries
QUERIES: dict[str, str] = {}

# 1. Business overview ---------------------------------------------------------------
QUERIES["kpis"] = f"""
SELECT COALESCE(SUM(f.total_order_value), 0) AS total_revenue,
       COUNT(*) AS total_orders,
       COUNT(DISTINCT f.customer_unique_id) AS total_customers,
       COALESCE(AVG(f.total_order_value), 0) AS avg_order_value,
       AVG(f.review_score) AS avg_review_score
FROM order_features f
WHERE {VALID} AND {ORDER_FILTER}
"""

QUERIES["total_sellers"] = f"""
SELECT COUNT(DISTINCT oi.seller_id) AS total_sellers
FROM order_items oi
JOIN order_features f ON f.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE {VALID} AND {ITEM_FILTER}
"""

# 2. Sales analysis ------------------------------------------------------------------
QUERIES["monthly_revenue"] = f"""
WITH monthly AS (
    SELECT f.order_month,
           SUM(f.total_order_value) AS revenue,
           COUNT(*) AS order_count
    FROM order_features f
    WHERE {VALID} AND {ORDER_FILTER}
    GROUP BY f.order_month
)
SELECT order_month, revenue, order_count,
       ROUND((revenue - LAG(revenue) OVER (ORDER BY order_month)) * 100.0
             / NULLIF(LAG(revenue) OVER (ORDER BY order_month), 0), 2) AS mom_growth_pct,
       SUM(revenue) OVER (ORDER BY order_month) AS cumulative_revenue
FROM monthly
ORDER BY order_month
"""

QUERIES["revenue_by_category"] = f"""
SELECT p.product_category_name_english AS category,
       SUM(oi.price + oi.freight_value) AS revenue,
       COUNT(*) AS units_sold,
       SUM(SUM(oi.price + oi.freight_value)) OVER () AS total_revenue
FROM order_items oi
JOIN order_features f ON f.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE {VALID} AND {ITEM_FILTER}
GROUP BY p.product_category_name_english
ORDER BY revenue DESC
"""

QUERIES["top_products"] = f"""
SELECT oi.product_id,
       p.product_category_name_english AS category,
       COUNT(*) AS units_sold,
       SUM(oi.price + oi.freight_value) AS revenue,
       RANK() OVER (ORDER BY SUM(oi.price + oi.freight_value) DESC) AS revenue_rank
FROM order_items oi
JOIN order_features f ON f.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE {VALID} AND {ITEM_FILTER}
GROUP BY oi.product_id, p.product_category_name_english
ORDER BY revenue DESC
LIMIT :top_n
"""

QUERIES["sales_by_state"] = f"""
SELECT f.customer_state AS state,
       SUM(f.total_order_value) AS revenue,
       COUNT(*) AS order_count,
       AVG(f.total_order_value) AS avg_order_value,
       SUM(f.total_order_value) * 100.0 / SUM(SUM(f.total_order_value)) OVER () AS revenue_share_pct
FROM order_features f
WHERE {VALID} AND {ORDER_FILTER}
GROUP BY f.customer_state
ORDER BY revenue DESC
"""

QUERIES["sales_by_city"] = f"""
SELECT f.customer_city AS city, f.customer_state AS state,
       SUM(f.total_order_value) AS revenue,
       COUNT(*) AS order_count
FROM order_features f
WHERE {VALID} AND {ORDER_FILTER}
GROUP BY f.customer_city, f.customer_state
ORDER BY revenue DESC
LIMIT :top_n
"""

# 3. Customer analysis ---------------------------------------------------------------
QUERIES["customer_distribution"] = f"""
SELECT f.customer_state AS state,
       COUNT(DISTINCT f.customer_unique_id) AS customers
FROM order_features f
WHERE {VALID} AND {ORDER_FILTER}
GROUP BY f.customer_state
ORDER BY customers DESC
"""

QUERIES["customer_spending"] = f"""
WITH cust AS (
    SELECT f.customer_unique_id, SUM(f.total_order_value) AS spend
    FROM order_features f
    WHERE {VALID} AND {ORDER_FILTER}
    GROUP BY f.customer_unique_id
)
SELECT CASE WHEN spend < 50 THEN '1: under 50'
            WHEN spend < 100 THEN '2: 50-99'
            WHEN spend < 200 THEN '3: 100-199'
            WHEN spend < 500 THEN '4: 200-499'
            WHEN spend < 1000 THEN '5: 500-999'
            ELSE '6: 1000+' END AS spend_bucket,
       COUNT(*) AS customers,
       SUM(spend) AS revenue
FROM cust
GROUP BY CASE WHEN spend < 50 THEN '1: under 50'
              WHEN spend < 100 THEN '2: 50-99'
              WHEN spend < 200 THEN '3: 100-199'
              WHEN spend < 500 THEN '4: 200-499'
              WHEN spend < 1000 THEN '5: 500-999'
              ELSE '6: 1000+' END
ORDER BY spend_bucket
"""

QUERIES["repeat_vs_new"] = f"""
WITH cust AS (
    SELECT f.customer_unique_id,
           COUNT(*) AS order_count,
           SUM(f.total_order_value) AS spend
    FROM order_features f
    WHERE {VALID} AND {ORDER_FILTER}
    GROUP BY f.customer_unique_id
)
SELECT CASE WHEN order_count > 1 THEN 'Repeat' ELSE 'New (one-time)' END AS customer_type,
       COUNT(*) AS customers,
       SUM(spend) AS revenue,
       AVG(spend) AS avg_spend_per_customer
FROM cust
GROUP BY CASE WHEN order_count > 1 THEN 'Repeat' ELSE 'New (one-time)' END
ORDER BY customers DESC
"""

QUERIES["top_customers"] = f"""
SELECT f.customer_unique_id,
       MAX(f.customer_state) AS state,
       COUNT(*) AS order_count,
       SUM(f.total_order_value) AS total_spending,
       AVG(f.total_order_value) AS avg_order_value
FROM order_features f
WHERE {VALID} AND {ORDER_FILTER}
GROUP BY f.customer_unique_id
ORDER BY total_spending DESC
LIMIT :top_n
"""

# 4. Seller & product analysis -------------------------------------------------------
QUERIES["top_sellers"] = f"""
SELECT oi.seller_id,
       MAX(s.seller_state) AS seller_state,
       SUM(oi.price + oi.freight_value) AS seller_revenue,
       COUNT(DISTINCT oi.order_id) AS order_count,
       SUM(oi.price + oi.freight_value) * 100.0
           / SUM(SUM(oi.price + oi.freight_value)) OVER () AS revenue_share_pct,
       RANK() OVER (ORDER BY SUM(oi.price + oi.freight_value) DESC) AS revenue_rank
FROM order_items oi
JOIN order_features f ON f.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN sellers s ON s.seller_id = oi.seller_id
WHERE {VALID} AND {ITEM_FILTER}
GROUP BY oi.seller_id
ORDER BY seller_revenue DESC
LIMIT :top_n
"""

QUERIES["category_performance"] = f"""
WITH cat_revenue AS (
    SELECT p.product_category_name_english AS category,
           SUM(oi.price + oi.freight_value) AS revenue,
           COUNT(*) AS units_sold,
           AVG(oi.price) AS avg_price
    FROM order_items oi
    JOIN order_features f ON f.order_id = oi.order_id
    JOIN products p ON p.product_id = oi.product_id
    WHERE {VALID} AND {ITEM_FILTER}
    GROUP BY p.product_category_name_english
),
cat_orders AS (
    SELECT DISTINCT p.product_category_name_english AS category, oi.order_id, f.review_score
    FROM order_items oi
    JOIN order_features f ON f.order_id = oi.order_id
    JOIN products p ON p.product_id = oi.product_id
    WHERE {VALID} AND {ITEM_FILTER}
),
cat_reviews AS (
    SELECT category, AVG(review_score) AS avg_review_score, COUNT(*) AS order_count
    FROM cat_orders
    GROUP BY category
)
SELECT r.category, r.revenue, r.units_sold, r.avg_price,
       v.order_count, v.avg_review_score
FROM cat_revenue r
JOIN cat_reviews v ON v.category = r.category
ORDER BY r.revenue DESC
"""

QUERIES["seller_ratings"] = f"""
WITH seller_orders AS (
    SELECT DISTINCT oi.seller_id, oi.order_id
    FROM order_items oi
    JOIN order_features f ON f.order_id = oi.order_id
    JOIN products p ON p.product_id = oi.product_id
    WHERE {VALID} AND {ITEM_FILTER}
)
SELECT so.seller_id,
       COUNT(*) AS order_count,
       COUNT(f.review_score) AS reviewed_orders,
       AVG(f.review_score) AS avg_review_score
FROM seller_orders so
JOIN order_features f ON f.order_id = so.order_id
GROUP BY so.seller_id
HAVING COUNT(f.review_score) >= :min_orders
ORDER BY avg_review_score DESC, reviewed_orders DESC
"""

# 5. Delivery analysis ---------------------------------------------------------------
QUERIES["delivery_summary"] = f"""
SELECT AVG(f.delivery_days) AS avg_delivery_days,
       AVG(f.delivery_delay_days) AS avg_delay_days,
       AVG(f.is_delayed) * 100.0 AS pct_delayed,
       COUNT(*) AS delivered_orders
FROM order_features f
WHERE f.delivery_delay_days IS NOT NULL AND {ORDER_FILTER}
"""

QUERIES["ontime_vs_delayed"] = f"""
SELECT f.delivery_status,
       COUNT(*) AS order_count,
       AVG(f.delivery_days) AS avg_delivery_days,
       AVG(f.review_score) AS avg_review_score
FROM order_features f
WHERE f.delivery_status IS NOT NULL AND {ORDER_FILTER}
GROUP BY f.delivery_status
ORDER BY f.delivery_status
"""

QUERIES["delivery_by_state"] = f"""
SELECT f.customer_state AS state,
       COUNT(*) AS delivered_orders,
       AVG(f.delivery_days) AS avg_delivery_days,
       AVG(f.is_delayed) * 100.0 AS pct_delayed,
       AVG(f.review_score) AS avg_review_score
FROM order_features f
WHERE f.delivery_delay_days IS NOT NULL AND {ORDER_FILTER}
GROUP BY f.customer_state
HAVING COUNT(*) >= :min_orders
ORDER BY avg_delivery_days DESC
"""

QUERIES["delay_vs_review"] = f"""
SELECT {DELAY_BUCKET} AS delay_bucket,
       COUNT(*) AS order_count,
       COUNT(f.review_score) AS reviewed_orders,
       AVG(f.review_score) AS avg_review_score
FROM order_features f
WHERE f.delivery_delay_days IS NOT NULL AND {ORDER_FILTER}
GROUP BY {DELAY_BUCKET}
ORDER BY delay_bucket
"""

# 6. Customer experience -------------------------------------------------------------
QUERIES["review_distribution"] = f"""
SELECT f.review_score,
       COUNT(*) AS review_count,
       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS pct_of_reviews
FROM order_features f
WHERE f.review_score IS NOT NULL AND {ORDER_FILTER}
GROUP BY f.review_score
ORDER BY f.review_score
"""

QUERIES["reviews_by_category"] = f"""
SELECT f.primary_category AS category,
       COUNT(f.review_score) AS review_count,
       AVG(f.review_score) AS avg_review_score,
       SUM(CASE WHEN f.review_score <= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(f.review_score)
           AS pct_negative
FROM order_features f
WHERE f.review_score IS NOT NULL AND {VALID} AND {ORDER_FILTER}
GROUP BY f.primary_category
HAVING COUNT(f.review_score) >= :min_orders
ORDER BY avg_review_score ASC
"""

QUERIES["rating_vs_delivery"] = f"""
SELECT f.delivery_status, f.review_score, COUNT(*) AS review_count
FROM order_features f
WHERE f.delivery_status IS NOT NULL AND f.review_score IS NOT NULL AND {ORDER_FILTER}
GROUP BY f.delivery_status, f.review_score
ORDER BY f.delivery_status, f.review_score
"""

# Order-level rows for the hypothesis tests (kept unaggregated on purpose).
QUERIES["stats_orders"] = f"""
SELECT f.order_id, f.order_status, f.delivery_status, f.review_score,
       f.total_order_value, f.primary_category, f.primary_payment_type, f.is_valid_sale
FROM order_features f
WHERE {ORDER_FILTER}
"""

# --------------------------------------------------------------------------- SQL showcase
# Queries on the BASE tables only (no engineered features), grouped by the SQL concept they
# demonstrate. Used by notebook 04 and the dashboard's "SQL Analysis" page.
ANALYSIS_QUERIES: dict[str, dict] = {
    "monthly_revenue_join": {
        "title": "Monthly revenue (JOIN + GROUP BY + ORDER BY)",
        "concepts": ["SELECT", "WHERE", "JOIN", "GROUP BY", "ORDER BY", "Aggregation"],
        "sql": """
SELECT SUBSTR(o.order_purchase_timestamp, 1, 7) AS order_month,
       COUNT(DISTINCT o.order_id) AS order_count,
       ROUND(SUM(oi.price + oi.freight_value), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY SUBSTR(o.order_purchase_timestamp, 1, 7)
ORDER BY order_month
""",
    },
    "sellers_with_volume": {
        "title": "Sellers with at least 20 orders (HAVING)",
        "concepts": ["JOIN", "GROUP BY", "HAVING", "Aggregation"],
        "sql": """
SELECT s.seller_id, s.seller_state,
       COUNT(DISTINCT oi.order_id) AS order_count,
       ROUND(SUM(oi.price), 2) AS item_revenue,
       ROUND(AVG(oi.price), 2) AS avg_item_price
FROM order_items oi
JOIN sellers s ON s.seller_id = oi.seller_id
GROUP BY s.seller_id, s.seller_state
HAVING COUNT(DISTINCT oi.order_id) >= 20
ORDER BY item_revenue DESC
LIMIT 20
""",
    },
    "customers_above_average": {
        "title": "Customers who spend above the average (subquery)",
        "concepts": ["Subquery", "JOIN", "GROUP BY", "HAVING"],
        "sql": """
SELECT c.customer_unique_id,
       ROUND(SUM(oi.price + oi.freight_value), 2) AS total_spending
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY c.customer_unique_id
HAVING SUM(oi.price + oi.freight_value) > (
    SELECT AVG(customer_total) FROM (
        SELECT SUM(oi2.price + oi2.freight_value) AS customer_total
        FROM customers c2
        JOIN orders o2 ON o2.customer_id = c2.customer_id
        JOIN order_items oi2 ON oi2.order_id = o2.order_id
        GROUP BY c2.customer_unique_id
    ) AS per_customer
)
ORDER BY total_spending DESC
LIMIT 20
""",
    },
    "top_category_per_state": {
        "title": "Best-selling category in each customer state (CTE + window RANK)",
        "concepts": ["CTE", "Window function", "PARTITION BY", "JOIN"],
        "sql": """
WITH state_category AS (
    SELECT c.customer_state AS state,
           p.product_category_name_english AS category,
           SUM(oi.price + oi.freight_value) AS revenue
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    JOIN customers c ON c.customer_id = o.customer_id
    JOIN products p ON p.product_id = oi.product_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_state, p.product_category_name_english
),
ranked AS (
    SELECT state, category, revenue,
           RANK() OVER (PARTITION BY state ORDER BY revenue DESC) AS category_rank
    FROM state_category
)
SELECT state, category, ROUND(revenue, 2) AS revenue
FROM ranked
WHERE category_rank = 1
ORDER BY revenue DESC
""",
    },
    "payment_mix": {
        "title": "Payment method mix and running share (aggregation + window SUM)",
        "concepts": ["Aggregation", "Window function", "GROUP BY"],
        "sql": """
SELECT payment_type,
       COUNT(*) AS payments,
       ROUND(SUM(payment_value), 2) AS total_value,
       ROUND(AVG(payment_installments), 2) AS avg_installments,
       ROUND(SUM(payment_value) * 100.0 / SUM(SUM(payment_value)) OVER (), 2) AS value_share_pct
FROM order_payments
GROUP BY payment_type
ORDER BY total_value DESC
""",
    },
    "review_score_by_status": {
        "title": "Average review score by order status (JOIN + conditional aggregation)",
        "concepts": ["JOIN", "GROUP BY", "CASE", "Aggregation"],
        "sql": """
SELECT o.order_status,
       COUNT(*) AS reviews,
       ROUND(AVG(r.review_score), 3) AS avg_score,
       ROUND(SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
           AS pct_negative
FROM order_reviews r
JOIN orders o ON o.order_id = r.order_id
GROUP BY o.order_status
ORDER BY reviews DESC
""",
    },
}

DEFAULT_TOP_N = 15
DEFAULT_MIN_ORDERS = 10


def used_params(sql: str, params: dict) -> dict:
    """Keep only the bind parameters that actually appear in the SQL text."""
    names = set(re.findall(r"(?<![:\w]):([A-Za-z_]\w*)", sql))
    return {k: v for k, v in params.items() if k in names}
