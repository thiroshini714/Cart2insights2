# ER diagram

Relationships implemented in `sql/schema.sql`. (The brief links an official ER diagram that could not be
opened during the build; compare this one against it.)

```mermaid
erDiagram
    customers ||--o{ orders : places
    orders ||--|{ order_items : contains
    orders ||--o{ order_payments : "paid by"
    orders ||--o| order_reviews : "reviewed in"
    products ||--o{ order_items : "sold as"
    sellers ||--o{ order_items : "sold by"
    product_category_name_translation ||--o{ products : translates
    geolocation ||--o{ customers : "zip prefix (not enforced)"
    geolocation ||--o{ sellers : "zip prefix (not enforced)"

    customers {
        varchar customer_id PK
        varchar customer_unique_id
        varchar customer_zip_code_prefix
        varchar customer_city
        varchar customer_state
    }
    orders {
        varchar order_id PK
        varchar customer_id FK
        varchar order_status
        datetime order_purchase_timestamp
        datetime order_delivered_customer_date
        datetime order_estimated_delivery_date
    }
    order_items {
        varchar order_id PK, FK
        int order_item_id PK
        varchar product_id FK
        varchar seller_id FK
        double price
        double freight_value
    }
    order_payments {
        varchar order_id PK, FK
        int payment_sequential PK
        varchar payment_type
        int payment_installments
        double payment_value
    }
    order_reviews {
        varchar review_id PK
        varchar order_id PK, FK
        int review_score
    }
    products {
        varchar product_id PK
        varchar product_category_name
        varchar product_category_name_english
    }
    sellers {
        varchar seller_id PK
        varchar seller_city
        varchar seller_state
    }
    product_category_name_translation {
        varchar product_category_name PK
        varchar product_category_name_english
    }
    geolocation {
        varchar geolocation_zip_code_prefix PK
        double geolocation_lat
        double geolocation_lng
    }
```

Zip-prefix links to `geolocation` are not enforced as foreign keys because some customer/seller prefixes
have no geolocation row. Engineered tables (`order_features`, `customer_features`, `seller_features`) are
derived from these tables.
