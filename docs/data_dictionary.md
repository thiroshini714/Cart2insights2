# Data dictionary

Written from the database schema in `sql/schema.sql`, which assumes the standard 9-table e-commerce layout.
The real dataset was not available during the build, so confirm descriptions against your CSVs.

## Source tables

### customers (PK `customer_id`)
| Column | Type | Description |
|---|---|---|
| customer_id | VARCHAR | Key for an order's customer record (one per order) |
| customer_unique_id | VARCHAR | Identifies the actual person across orders |
| customer_zip_code_prefix | VARCHAR(10) | First digits of zip code (text, zero-padded to 5) |
| customer_city | VARCHAR | City (normalised: lowercase, no accents) |
| customer_state | VARCHAR(5) | State code (uppercase) |

### geolocation (PK `geolocation_zip_code_prefix`)
One row per zip prefix after cleaning (mean latitude/longitude, modal city/state).
| Column | Type | Description |
|---|---|---|
| geolocation_zip_code_prefix | VARCHAR(10) | Zip prefix |
| geolocation_lat / geolocation_lng | DOUBLE | Mean coordinates |
| geolocation_city / geolocation_state | VARCHAR | Modal city / state |

### sellers (PK `seller_id`)
| Column | Type | Description |
|---|---|---|
| seller_id | VARCHAR | Seller key |
| seller_zip_code_prefix, seller_city, seller_state | VARCHAR | Seller location |

### products (PK `product_id`)
| Column | Type | Description |
|---|---|---|
| product_id | VARCHAR | Product key |
| product_category_name | VARCHAR | Original category name (`unknown` when missing) |
| product_category_name_english | VARCHAR | Translated category (falls back to original name) |
| product_name_length, product_description_length | INT | Characters (renamed from the misspelled `…_lenght`) |
| product_photos_qty | INT | Number of photos |
| product_weight_g, product_length_cm, product_height_cm, product_width_cm | DOUBLE | Physical attributes (non-positive values treated as missing and imputed) |

### product_category_name_translation (PK `product_category_name`)
Maps original category names to English.

### orders (PK `order_id`; FK `customer_id` → customers)
| Column | Type | Description |
|---|---|---|
| order_id | VARCHAR | Order key |
| customer_id | VARCHAR | FK to customers |
| order_status | VARCHAR | created, approved, invoiced, processing, shipped, delivered, canceled, unavailable |
| order_purchase_timestamp | DATETIME | Purchase time |
| order_approved_at | DATETIME | Payment approval time |
| order_delivered_carrier_date | DATETIME | Handed to carrier |
| order_delivered_customer_date | DATETIME | Delivered to customer |
| order_estimated_delivery_date | DATETIME | Promised delivery date |

### order_items (PK `order_id`+`order_item_id`; FKs → orders, products, sellers)
| Column | Type | Description |
|---|---|---|
| order_item_id | INT | Sequence of the item within the order |
| product_id, seller_id | VARCHAR | FKs |
| shipping_limit_date | DATETIME | Seller's shipping deadline |
| price | DOUBLE | Item price (must be > 0) |
| freight_value | DOUBLE | Freight charge (missing → 0) |

### order_payments (PK `order_id`+`payment_sequential`; FK → orders)
| Column | Type | Description |
|---|---|---|
| payment_sequential | INT | Payment sequence within the order |
| payment_type | VARCHAR | credit_card, boleto, voucher, debit_card, not_defined |
| payment_installments | INT | Installments (minimum 1) |
| payment_value | DOUBLE | Amount paid |

### order_reviews (PK `review_id`+`order_id`; FK → orders)
One review per order after cleaning (latest kept).
| Column | Type | Description |
|---|---|---|
| review_id | VARCHAR | Review identifier |
| review_score | INT | 1–5 |
| review_comment_title / review_comment_message | TEXT | Optional text |
| has_comment | INT | 1 if a comment message exists (added in cleaning) |
| review_creation_date / review_answer_timestamp | DATETIME | Survey sent / answered |

## Engineered tables

### order_features (PK `order_id`)
| Column | Description |
|---|---|
| customer_unique_id, customer_city, customer_state | Joined from customers |
| order_month | `YYYY-MM` of purchase (used for portable monthly SQL) |
| items_value, freight_value, total_order_value | Sum of prices, sum of freight, and their total |
| n_items, n_sellers | Items and distinct sellers in the order |
| primary_category | Category of the highest-priced item (`unknown` if no items) |
| primary_payment_type, payment_value_total, n_payment_methods, max_installments | Payment summary |
| review_score | The order's review score (NULL if none) |
| delivery_days | Delivered − purchase, in days (delivered orders only) |
| delivery_delay_days | Delivered − estimated, in days (> 0 means late) |
| is_delayed / delivery_status | 1/0 and `Delayed`/`On time` (NULL when not computable) |
| is_valid_sale | 1 if the order has items and is not canceled/unavailable |
| customer_order_count, is_repeat_customer | Customer's valid-sale order count; repeat flag |

### customer_features (PK `customer_unique_id`)
order_count, total_spending, avg_order_value, first/last_order_date, is_repeat_customer, spending_tier (Low/Medium/High terciles) — valid sales only.

### seller_features (PK `seller_id`)
seller_revenue, seller_order_count, units_sold, avg_item_price, avg_review_score, reviewed_orders — valid sales only.

### pipeline_meta
Key/value metadata; `data_source` is `real` or `synthetic` (the dashboard warns on `synthetic`).
