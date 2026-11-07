-- Cart2Insights schema. Portable across MySQL 8+ and SQLite 3.25+.
-- Statements are separated by semicolons; "--" comment lines are ignored by the loader.

CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(10) NOT NULL PRIMARY KEY,
    geolocation_lat DOUBLE,
    geolocation_lng DOUBLE,
    geolocation_city VARCHAR(100),
    geolocation_state VARCHAR(5)
);

CREATE TABLE product_category_name_translation (
    product_category_name VARCHAR(100) NOT NULL PRIMARY KEY,
    product_category_name_english VARCHAR(100)
);

CREATE TABLE customers (
    customer_id VARCHAR(50) NOT NULL PRIMARY KEY,
    customer_unique_id VARCHAR(50) NOT NULL,
    customer_zip_code_prefix VARCHAR(10),
    customer_city VARCHAR(100),
    customer_state VARCHAR(5)
);

CREATE TABLE sellers (
    seller_id VARCHAR(50) NOT NULL PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city VARCHAR(100),
    seller_state VARCHAR(5)
);

CREATE TABLE products (
    product_id VARCHAR(50) NOT NULL PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_category_name_english VARCHAR(100),
    product_name_length INT,
    product_description_length INT,
    product_photos_qty INT,
    product_weight_g DOUBLE,
    product_length_cm DOUBLE,
    product_height_cm DOUBLE,
    product_width_cm DOUBLE
);

CREATE TABLE orders (
    order_id VARCHAR(50) NOT NULL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp DATETIME NOT NULL,
    order_approved_at DATETIME,
    order_delivered_carrier_date DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME,
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE TABLE order_items (
    order_id VARCHAR(50) NOT NULL,
    order_item_id INT NOT NULL,
    product_id VARCHAR(50) NOT NULL,
    seller_id VARCHAR(50) NOT NULL,
    shipping_limit_date DATETIME,
    price DOUBLE NOT NULL,
    freight_value DOUBLE NOT NULL,
    PRIMARY KEY (order_id, order_item_id),
    FOREIGN KEY (order_id) REFERENCES orders (order_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id),
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id)
);

CREATE TABLE order_payments (
    order_id VARCHAR(50) NOT NULL,
    payment_sequential INT NOT NULL,
    payment_type VARCHAR(20) NOT NULL,
    payment_installments INT,
    payment_value DOUBLE NOT NULL,
    PRIMARY KEY (order_id, payment_sequential),
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);

CREATE TABLE order_reviews (
    review_id VARCHAR(50) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    review_score INT NOT NULL,
    review_comment_title TEXT,
    review_comment_message TEXT,
    has_comment INT,
    review_creation_date DATETIME,
    review_answer_timestamp DATETIME,
    PRIMARY KEY (review_id, order_id),
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);

-- Engineered feature tables (populated by the feature-engineering step) ---------------

CREATE TABLE order_features (
    order_id VARCHAR(50) NOT NULL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    customer_unique_id VARCHAR(50) NOT NULL,
    customer_city VARCHAR(100),
    customer_state VARCHAR(5),
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp DATETIME NOT NULL,
    order_month VARCHAR(7) NOT NULL,
    items_value DOUBLE,
    freight_value DOUBLE,
    total_order_value DOUBLE,
    n_items INT,
    n_sellers INT,
    primary_category VARCHAR(100),
    primary_payment_type VARCHAR(20),
    payment_value_total DOUBLE,
    n_payment_methods INT,
    max_installments INT,
    review_score INT,
    delivery_days DOUBLE,
    delivery_delay_days DOUBLE,
    is_delayed INT,
    delivery_status VARCHAR(10),
    is_valid_sale INT,
    customer_order_count INT,
    is_repeat_customer INT,
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);

CREATE TABLE customer_features (
    customer_unique_id VARCHAR(50) NOT NULL PRIMARY KEY,
    customer_city VARCHAR(100),
    customer_state VARCHAR(5),
    order_count INT,
    total_spending DOUBLE,
    avg_order_value DOUBLE,
    first_order_date DATETIME,
    last_order_date DATETIME,
    is_repeat_customer INT,
    spending_tier VARCHAR(10)
);

CREATE TABLE seller_features (
    seller_id VARCHAR(50) NOT NULL PRIMARY KEY,
    seller_city VARCHAR(100),
    seller_state VARCHAR(5),
    seller_revenue DOUBLE,
    seller_order_count INT,
    units_sold INT,
    avg_item_price DOUBLE,
    avg_review_score DOUBLE,
    reviewed_orders INT,
    FOREIGN KEY (seller_id) REFERENCES sellers (seller_id)
);

-- Metadata: records whether the loaded data is real or synthetic test data.
CREATE TABLE pipeline_meta (
    meta_key VARCHAR(50) NOT NULL PRIMARY KEY,
    meta_value VARCHAR(255)
);

CREATE INDEX idx_customers_unique ON customers (customer_unique_id);
CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_orders_status ON orders (order_status);
CREATE INDEX idx_items_product ON order_items (product_id);
CREATE INDEX idx_items_seller ON order_items (seller_id);
CREATE INDEX idx_reviews_order ON order_reviews (order_id);
CREATE INDEX idx_of_month ON order_features (order_month);
CREATE INDEX idx_of_state ON order_features (customer_state);
CREATE INDEX idx_of_category ON order_features (primary_category);
CREATE INDEX idx_of_customer ON order_features (customer_unique_id);
