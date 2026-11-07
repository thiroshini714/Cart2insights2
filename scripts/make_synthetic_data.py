"""Generate SYNTHETIC e-commerce CSVs with the 9-table Cart2Insights/Olist-style schema.

*** This is TEST DATA ONLY. It exists so the pipeline can be exercised end to end when the
*** real dataset is not at hand. Nothing it produces is a real business result.
It deliberately injects messy records (missing values, duplicates, bad dates, invalid
scores...) so the quality-analysis and cleaning steps have something to find.

Usage:  python scripts/make_synthetic_data.py [--orders 6000] [--seed 42] [--out data/synthetic]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

CATEGORIES = {  # portuguese name -> (english name, typical price scale)
    "cama_mesa_banho": ("bed_bath_table", 90), "beleza_saude": ("health_beauty", 130),
    "informatica_acessorios": ("computers_accessories", 120), "esporte_lazer": ("sports_leisure", 110),
    "moveis_decoracao": ("furniture_decor", 95), "utilidades_domesticas": ("housewares", 85),
    "relogios_presentes": ("watches_gifts", 200), "telefonia": ("telephony", 60),
    "automotivo": ("auto", 115), "brinquedos": ("toys", 95), "cool_stuff": ("cool_stuff", 140),
    "ferramentas_jardim": ("garden_tools", 100), "perfumaria": ("perfumery", 105),
    "bebes": ("baby", 100), "eletronicos": ("electronics", 80), "papelaria": ("stationery", 70),
    "fashion_bolsas_e_acessorios": ("fashion_bags_accessories", 110), "pet_shop": ("pet_shop", 105),
    "livros_tecnicos": ("books_technical", 85), "eletrodomesticos": ("small_appliances", 190),
}
STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "GO", "PE", "CE"]
STATE_W = np.array([40, 13, 12, 6, 6, 5, 5, 4, 5, 4], dtype=float)
SLOW_STATES = {"BA", "PE", "CE"}
CITIES = {s: [f"{s.lower()} city {i}" for i in range(1, 4)] for s in STATES}
CITY_VARIANTS = lambda c, rng: rng.choice([c, c.upper(), f" {c} ", c.replace("city", "Cíty")])  # noqa: E731


def _hex(prefix: str, i: int) -> str:
    return hashlib.md5(f"{prefix}-{i}".encode()).hexdigest()


def generate(n_orders: int = 6000, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    fmt = "%Y-%m-%d %H:%M:%S"

    # ---- geography ---------------------------------------------------------------------
    zips = {s: rng.integers(1000, 99000, size=25) for s in STATES}  # ints: leading zeros get lost
    centres = {s: (rng.uniform(-30, -3), rng.uniform(-55, -35)) for s in STATES}

    # ---- sellers / products --------------------------------------------------------------
    n_sellers, n_products = 120, 800
    seller_state = rng.choice(STATES, n_sellers, p=STATE_W / STATE_W.sum())
    sellers = pd.DataFrame({
        "seller_id": [_hex("seller", i) for i in range(n_sellers)],
        "seller_zip_code_prefix": [rng.choice(zips[s]) for s in seller_state],
        "seller_city": [CITY_VARIANTS(rng.choice(CITIES[s]), rng) for s in seller_state],
        "seller_state": seller_state,
    })
    cat_names = list(CATEGORIES)
    prod_cat = rng.choice(cat_names, n_products)
    products = pd.DataFrame({
        "product_id": [_hex("product", i) for i in range(n_products)],
        "product_category_name": prod_cat,
        "product_name_lenght": rng.integers(20, 70, n_products).astype(float),
        "product_description_lenght": rng.integers(100, 1500, n_products).astype(float),
        "product_photos_qty": rng.integers(1, 8, n_products).astype(float),
        "product_weight_g": rng.integers(100, 8000, n_products).astype(float),
        "product_length_cm": rng.integers(10, 80, n_products).astype(float),
        "product_height_cm": rng.integers(5, 50, n_products).astype(float),
        "product_width_cm": rng.integers(8, 60, n_products).astype(float),
    })
    miss = rng.random(n_products)
    products.loc[miss < 0.015, ["product_category_name", "product_name_lenght",
                                "product_description_lenght", "product_photos_qty"]] = np.nan
    products.loc[rng.random(n_products) < 0.004, "product_weight_g"] = 0
    translation = pd.DataFrame(
        [(k, v[0]) for k, v in CATEGORIES.items() if k != "eletrodomesticos"],  # one left untranslated
        columns=["product_category_name", "product_category_name_english"])
    price_scale = np.array([CATEGORIES[c][1] if isinstance(c, str) else 90 for c in prod_cat])

    # ---- customers & orders ----------------------------------------------------------------
    n_unique = int(n_orders * 0.92)
    unique_state = rng.choice(STATES, n_unique, p=STATE_W / STATE_W.sum())
    unique_ids = [_hex("cust", i) for i in range(n_unique)]
    unique_zip = [rng.choice(zips[s]) for s in unique_state]
    unique_city = [rng.choice(CITIES[s]) for s in unique_state]
    assign, next_new = [], 0
    for _ in range(n_orders):
        if next_new < n_unique and (rng.random() > 0.06 or not assign):
            assign.append(next_new); next_new += 1
        else:
            assign.append(int(rng.choice(assign)))
    assign = np.array(assign)
    customers = pd.DataFrame({
        "customer_id": [_hex("order-cust", i) for i in range(n_orders)],
        "customer_unique_id": [unique_ids[a] for a in assign],
        "customer_zip_code_prefix": [unique_zip[a] for a in assign],
        "customer_city": [CITY_VARIANTS(unique_city[a], rng) for a in assign],
        "customer_state": [unique_state[a] for a in assign],
    })

    ptype = rng.choice(["credit_card", "boleto", "voucher", "debit_card"], n_orders,
                       p=[0.74, 0.20, 0.04, 0.02])
    cancel_p = np.where(ptype == "boleto", 0.03, 0.012)  # weak real dependency for the chi-square test
    r = rng.random(n_orders)
    status = np.where(r < cancel_p, "canceled",
             np.where(r < cancel_p + 0.006, "unavailable",
             np.where(r < cancel_p + 0.006 + 0.02, "shipped",
             np.where(r < cancel_p + 0.006 + 0.02 + 0.008, "processing", "delivered"))))
    month_idx = rng.choice(20, n_orders, p=np.linspace(1, 3, 20) / np.linspace(1, 3, 20).sum())
    purchase = (pd.Timestamp("2017-01-01") + pd.to_timedelta(month_idx * 30, unit="D")
                + pd.to_timedelta(rng.integers(0, 30 * 24 * 3600, n_orders), unit="s"))
    approved = purchase + pd.to_timedelta(rng.integers(300, 86400, n_orders), unit="s")
    carrier = approved + pd.to_timedelta(rng.integers(1, 4, n_orders), unit="D")
    slow = np.isin(customers["customer_state"].to_numpy(), list(SLOW_STATES))
    delivery_days = 7 + rng.gamma(3.0, 2.2, n_orders) + slow * 6
    delivered = purchase + pd.to_timedelta(delivery_days, unit="D")
    estimated = purchase + pd.to_timedelta(rng.integers(14, 36, n_orders), unit="D")

    is_delivered = status == "delivered"
    orders = pd.DataFrame({
        "order_id": [_hex("order", i) for i in range(n_orders)],
        "customer_id": customers["customer_id"],
        "order_status": status,
        "order_purchase_timestamp": purchase,
        "order_approved_at": pd.Series(approved).where(status != "created"),
        "order_delivered_carrier_date": pd.Series(carrier).where(np.isin(status, ["shipped", "delivered"])),
        "order_delivered_customer_date": pd.Series(delivered).where(is_delivered),
        "order_estimated_delivery_date": estimated,
    })
    delay_days = (delivered - estimated).total_seconds() / 86400

    # ---- items ----------------------------------------------------------------------------------
    rows = []
    for i in range(n_orders):
        if status[i] == "unavailable" and rng.random() < 0.7:
            continue
        for k in range(1, min(1 + rng.poisson(0.15), 4) + 1):
            p = int(rng.integers(0, n_products))
            price = round(float(rng.lognormal(np.log(price_scale[p]), 0.6)), 2)
            rows.append((orders.at[i, "order_id"], k, products.at[p, "product_id"],
                         sellers.at[int(rng.integers(0, n_sellers)), "seller_id"],
                         approved[i] + pd.Timedelta(days=3), price,
                         round(5 + 0.08 * price + float(rng.gamma(2, 3)) + (4 if slow[i] else 0), 2)))
    items = pd.DataFrame(rows, columns=["order_id", "order_item_id", "product_id", "seller_id",
                                        "shipping_limit_date", "price", "freight_value"])

    # ---- payments -------------------------------------------------------------------------------
    totals = (items.assign(t=items.price + items.freight_value).groupby("order_id")["t"].sum()
              .reindex(orders["order_id"]).fillna(0).to_numpy())
    pay_rows = []
    for i in range(n_orders):
        value = round(float(totals[i] if totals[i] > 0 else rng.uniform(20, 150)), 2)
        inst = int(rng.integers(1, 11)) if ptype[i] == "credit_card" else 1
        if rng.random() < 0.03:  # split payment: voucher + main method
            v = round(value * 0.3, 2)
            pay_rows.append((orders.at[i, "order_id"], 1, "voucher", 1, v))
            pay_rows.append((orders.at[i, "order_id"], 2, ptype[i], inst, round(value - v, 2)))
        else:
            pay_rows.append((orders.at[i, "order_id"], 1, ptype[i], inst, value))
    payments = pd.DataFrame(pay_rows, columns=["order_id", "payment_sequential", "payment_type",
                                               "payment_installments", "payment_value"])

    # ---- reviews (a genuine delay -> lower score effect is seeded) ---------------------------------
    rev_rows = []
    for i in range(n_orders):
        if rng.random() > 0.85 or status[i] == "created":
            continue
        late = is_delivered[i] and delay_days[i] > 0
        probs = [0.30, 0.15, 0.20, 0.20, 0.15] if late else [0.03, 0.03, 0.08, 0.20, 0.66]
        if status[i] in ("canceled", "unavailable"):
            probs = [0.45, 0.2, 0.15, 0.1, 0.1]
        score = int(rng.choice([1, 2, 3, 4, 5], p=probs))
        created = (delivered[i] if is_delivered[i] else approved[i]) + pd.Timedelta(days=1)
        for _ in range(2 if rng.random() < 0.03 else 1):
            rev_rows.append((_hex("review", len(rev_rows)), orders.at[i, "order_id"], score,
                             None, None if rng.random() < 0.58 else "texto de exemplo",
                             created, created + pd.Timedelta(days=int(rng.integers(0, 4)))))
    reviews = pd.DataFrame(rev_rows, columns=["review_id", "order_id", "review_score",
                                              "review_comment_title", "review_comment_message",
                                              "review_creation_date", "review_answer_timestamp"])

    # ---- geolocation (several noisy rows per zip) -----------------------------------------------------
    geo_rows = []
    for s in STATES:
        for z in zips[s]:
            for _ in range(int(rng.integers(1, 5))):
                lat, lng = centres[s]
                geo_rows.append((z, lat + rng.normal(0, 0.3), lng + rng.normal(0, 0.3),
                                 CITY_VARIANTS(rng.choice(CITIES[s]), rng), s))
    geolocation = pd.DataFrame(geo_rows, columns=["geolocation_zip_code_prefix", "geolocation_lat",
                                                  "geolocation_lng", "geolocation_city",
                                                  "geolocation_state"])

    # ---- inject messy records for the quality / cleaning steps ------------------------------------------
    for col in ("order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
                "order_delivered_customer_date", "order_estimated_delivery_date"):
        orders[col] = pd.to_datetime(orders[col]).dt.strftime(fmt)
    d_idx = orders.index[orders["order_status"] == "delivered"]
    orders.loc[rng.choice(d_idx, int(0.01 * len(d_idx)), replace=False), "order_delivered_customer_date"] = None
    orders.loc[rng.choice(d_idx, 5, replace=False), "order_delivered_customer_date"] = "2016-01-01 00:00:00"
    orders.loc[rng.choice(d_idx, 3, replace=False), "order_estimated_delivery_date"] = "not a date"
    orders = pd.concat([orders, orders.sample(20, random_state=1)], ignore_index=True)

    items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"]).dt.strftime(fmt)
    items.loc[items.sample(3, random_state=2).index, "price"] = -5.0
    items.loc[items.sample(15, random_state=3).index, "freight_value"] = np.nan
    items = pd.concat([items, items.sample(20, random_state=4)], ignore_index=True)

    payments.loc[payments.sample(2, random_state=5).index, ["payment_type", "payment_installments",
                                                            "payment_value"]] = ["not_defined", 0, 0.0]
    payments = pd.concat([payments, payments.sample(10, random_state=6)], ignore_index=True)

    for col in ("review_creation_date", "review_answer_timestamp"):
        reviews[col] = pd.to_datetime(reviews[col]).dt.strftime(fmt)
    reviews.loc[reviews.sample(5, random_state=7).index, "review_score"] = [0, 6, 7, 0, 9]
    reviews = pd.concat([reviews, reviews.sample(15, random_state=8)], ignore_index=True)

    geolocation.loc[geolocation.sample(5, random_state=9).index, "geolocation_lat"] = 95.0
    customers = pd.concat([customers, customers.sample(10, random_state=10)], ignore_index=True)

    return {
        "olist_customers_dataset": customers, "olist_geolocation_dataset": geolocation,
        "olist_order_items_dataset": items, "olist_order_payments_dataset": payments,
        "olist_order_reviews_dataset": reviews, "olist_orders_dataset": orders,
        "olist_products_dataset": products, "olist_sellers_dataset": sellers,
        "product_category_name_translation": translation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--orders", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "synthetic"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in generate(args.orders, args.seed).items():
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name}.csv: {len(df):,} rows")
    (out / "README_SYNTHETIC.txt").write_text(
        "SYNTHETIC TEST DATA generated by scripts/make_synthetic_data.py.\n"
        "Not real. Do not draw business conclusions from it.\n")
    print(f"Wrote synthetic test data to {out}")


if __name__ == "__main__":
    main()
