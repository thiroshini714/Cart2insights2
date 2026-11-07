"""Cart2Insights - interactive e-commerce analytics dashboard.

Run from the project root:   streamlit run streamlit/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))

import queries as q  # noqa: E402
import utils as ui  # noqa: E402
from database import database_ready, initialise_database, run_query, to_params  # noqa: E402
from src.insights import generate_insights  # noqa: E402
from src.stats_tests import run_all_tests  # noqa: E402

st.set_page_config(page_title="Cart2Insights", page_icon="🛒", layout="wide")

try:
    data_source = initialise_database()
except Exception as exc:  # surface startup failures with captured pipeline diagnostics
    st.title("Cart2Insights")
    st.error(f"Database initialisation failed: {type(exc).__name__}: {exc}")
    st.stop()

ok, problem = database_ready()
if not ok:
    st.title("Cart2Insights")
    st.error(problem)
    st.stop()


def fetch(name_or_sql: str, params: dict | None = None) -> pd.DataFrame:
    sql = q.QUERIES.get(name_or_sql, name_or_sql)
    return run_query(sql, to_params(params or {}))


# ------------------------------------------------------------------------------ sidebar
months = fetch(q.FILTER_OPTIONS["months"])["order_month"].tolist()
states = ["All"] + fetch(q.FILTER_OPTIONS["states"])["customer_state"].tolist()
categories = ["All"] + fetch(q.FILTER_OPTIONS["categories"])["primary_category"].tolist()

st.sidebar.title("🛒 Cart2Insights")
SECTIONS = ["Business Overview", "Sales Analysis", "Customer Analysis", "Seller & Product Analysis",
            "Delivery Analysis", "Customer Experience", "Statistical Tests", "Business Insights",
            "SQL Analysis"]
section = st.sidebar.radio("Section", SECTIONS)

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")
start_month, end_month = st.sidebar.select_slider(
    "Purchase month range", options=months, value=(months[0], months[-1]))
state = st.sidebar.selectbox("Customer state", states)
category = st.sidebar.selectbox("Product category", categories)
top_n = st.sidebar.slider("Top-N lists", 5, 30, q.DEFAULT_TOP_N)
min_orders = st.sidebar.slider("Minimum orders for ratings/rankings", 1, 100, q.DEFAULT_MIN_ORDERS)
st.sidebar.caption("Category filter: order-level views use an order's highest-priced item's "
                   "category; item-level views use each item's own category.")

P = {"start_month": start_month, "end_month": end_month, "state": state, "category": category,
     "top_n": top_n, "min_orders": min_orders}

source = fetch(q.FILTER_OPTIONS["data_source"])
if not source.empty and source.iloc[0, 0] == "synthetic":
    st.warning("⚠️ This dashboard is showing **synthetic test data**, not the real dataset. "
               "Re-run `python run_pipeline.py` with the real CSVs in `data/raw/` to replace it.")

st.title(section)
st.caption(f"Purchases {start_month} → {end_month} · State: {state} · Category: {category} · "
           f"Revenue = item price + freight, excluding canceled/unavailable orders")


# ------------------------------------------------------------------------------ pages
def page_overview():
    k = fetch("kpis", P)
    sellers = fetch("total_sellers", P)
    if ui.empty_notice(k) or k["total_orders"].iloc[0] == 0:
        st.info("No orders match the current filters.")
        return
    r = k.iloc[0]
    c = st.columns(3)
    c[0].metric("Total Revenue", ui.money(r["total_revenue"], compact=True))
    c[1].metric("Total Orders", ui.number(r["total_orders"]))
    c[2].metric("Total Customers", ui.number(r["total_customers"]))
    c = st.columns(3)
    c[0].metric("Total Sellers", ui.number(sellers["total_sellers"].iloc[0]))
    c[1].metric("Average Order Value", ui.money(r["avg_order_value"]))
    c[2].metric("Average Review Score",
                "n/a" if pd.isna(r["avg_review_score"]) else f"{r['avg_review_score']:.2f} / 5")

    left, right = st.columns(2)
    monthly = fetch("monthly_revenue", P)
    if not monthly.empty:
        left.plotly_chart(ui.line_chart(monthly, "order_month", "revenue", "Monthly revenue",
                                        f"Revenue ({ui.CURRENCY})"), width="stretch")
    cat = fetch("revenue_by_category", P).head(8)
    if not cat.empty:
        right.plotly_chart(ui.bar_chart(cat, "category", "revenue", "Top categories by revenue",
                                        horizontal=True), width="stretch")


def page_sales():
    monthly = fetch("monthly_revenue", P)
    if not ui.empty_notice(monthly, "monthly revenue"):
        ui.show(ui.line_chart(monthly, "order_month", "revenue", "Monthly revenue trend",
                              f"Revenue ({ui.CURRENCY})"))
        fig = px.bar(monthly, x="order_month", y="mom_growth_pct",
                     title="Month-over-month revenue growth (%)", color_discrete_sequence=[ui.ACCENT])
        ui.show(ui.style(fig, 300))
    left, right = st.columns(2)
    with left:
        cat = fetch("revenue_by_category", P).head(top_n)
        if not ui.empty_notice(cat, "revenue by category"):
            ui.show(ui.bar_chart(cat, "category", "revenue", f"Revenue by category (top {top_n})",
                                 horizontal=True, height=420))
    with right:
        state_sales = fetch("sales_by_state", P)
        if not ui.empty_notice(state_sales, "sales by state"):
            ui.show(ui.bar_chart(state_sales, "state", "revenue", "Revenue by customer state",
                                 height=420))
    st.subheader("Top-selling products")
    products = fetch("top_products", P)
    if not ui.empty_notice(products, "top products"):
        products = products.assign(product_id=products["product_id"].str[:10] + "…")
        ui.table(products)
    st.subheader("Sales by city")
    cities = fetch("sales_by_city", P)
    if not ui.empty_notice(cities, "sales by city"):
        ui.show(ui.bar_chart(cities, "city", "revenue", f"Top {top_n} cities by revenue",
                             horizontal=True, height=440))


def page_customers():
    left, right = st.columns(2)
    with left:
        dist = fetch("customer_distribution", P)
        if not ui.empty_notice(dist, "customer distribution"):
            ui.show(ui.bar_chart(dist, "state", "customers", "Customers by state"))
    with right:
        spend = fetch("customer_spending", P)
        if not ui.empty_notice(spend, "customer spending"):
            spend = spend.assign(spend_bucket=spend["spend_bucket"].str[3:])
            ui.show(ui.bar_chart(spend, "spend_bucket", "customers",
                                 f"Customers by total spending ({ui.CURRENCY})"))
    rep = fetch("repeat_vs_new", P)
    if not ui.empty_notice(rep, "repeat vs new customers"):
        c1, c2 = st.columns(2)
        fig = px.pie(rep, names="customer_type", values="customers", hole=0.5,
                     title="Repeat vs new customers", color_discrete_sequence=ui.SEQUENCE)
        c1.plotly_chart(ui.style(fig), width="stretch")
        fig = px.pie(rep, names="customer_type", values="revenue", hole=0.5,
                     title="Revenue share: repeat vs new", color_discrete_sequence=ui.SEQUENCE)
        c2.plotly_chart(ui.style(fig), width="stretch")
        ui.table(rep)
    st.subheader("Top customers")
    top = fetch("top_customers", P)
    if not ui.empty_notice(top, "top customers"):
        top = top.assign(customer_unique_id=top["customer_unique_id"].str[:10] + "…")
        ui.table(top)


def page_sellers_products():
    sellers = fetch("top_sellers", P)
    left, right = st.columns(2)
    with left:
        if not ui.empty_notice(sellers, "top sellers"):
            s = sellers.assign(seller=sellers["seller_id"].str[:8] + "…")
            ui.show(ui.bar_chart(s, "seller", "seller_revenue", f"Top {top_n} sellers by revenue",
                                 horizontal=True, height=440))
    with right:
        cat = fetch("category_performance", P)
        if not ui.empty_notice(cat, "category performance"):
            fig = px.scatter(cat, x="revenue", y="avg_review_score", size="units_sold",
                             hover_name="category", title="Category revenue vs average review score",
                             color_discrete_sequence=[ui.PRIMARY])
            ui.show(ui.style(fig, 440))
    st.subheader("Seller revenue and share")
    if not sellers.empty:
        ui.table(sellers)
    st.subheader(f"Seller ratings (sellers with ≥ {min_orders} reviewed orders)")
    ratings = fetch("seller_ratings", P)
    if not ui.empty_notice(ratings, "seller ratings"):
        c1, c2 = st.columns(2)
        fig = px.histogram(ratings, x="avg_review_score", nbins=20, title="Distribution of seller ratings",
                           color_discrete_sequence=[ui.PRIMARY])
        c1.plotly_chart(ui.style(fig), width="stretch")
        worst = ratings.sort_values("avg_review_score").head(10)
        c2.markdown("**Lowest-rated sellers**")
        c2.dataframe(worst.assign(seller_id=worst["seller_id"].str[:10] + "…"),
                     width="stretch", hide_index=True)
    st.subheader("Product / category performance")
    if not cat.empty:
        ui.table(cat)


def page_delivery():
    summary = fetch("delivery_summary", P)
    if ui.empty_notice(summary, "delivery") or summary["delivered_orders"].iloc[0] == 0:
        st.info("No delivered orders with valid dates match the current filters.")
        return
    s = summary.iloc[0]
    c = st.columns(4)
    c[0].metric("Average delivery time", f"{s['avg_delivery_days']:.1f} days")
    c[1].metric("Average delay vs estimate", f"{s['avg_delay_days']:+.1f} days")
    c[2].metric("Delayed orders", f"{s['pct_delayed']:.1f}%")
    c[3].metric("Delivered orders analysed", ui.number(s["delivered_orders"]))

    left, right = st.columns(2)
    ontime = fetch("ontime_vs_delayed", P)
    with left:
        fig = px.pie(ontime, names="delivery_status", values="order_count", hole=0.5,
                     title="On-time vs delayed orders",
                     color="delivery_status",
                     color_discrete_map={"On time": ui.PRIMARY, "Delayed": ui.BAD})
        ui.show(ui.style(fig))
    with right:
        fig = px.bar(ontime, x="delivery_status", y="avg_review_score", text_auto=".2f",
                     title="Average review score: on time vs delayed", color="delivery_status",
                     color_discrete_map={"On time": ui.PRIMARY, "Delayed": ui.BAD})
        fig.update_yaxes(range=[0, 5])
        ui.show(ui.style(fig))

    st.subheader("Delivery performance by location")
    by_state = fetch("delivery_by_state", P)
    if not ui.empty_notice(by_state, "delivery by state"):
        c1, c2 = st.columns(2)
        c1.plotly_chart(ui.bar_chart(by_state, "state", "avg_delivery_days",
                                     "Average delivery days by state"), width="stretch")
        c2.plotly_chart(ui.bar_chart(by_state.sort_values("pct_delayed", ascending=False),
                                     "state", "pct_delayed", "% delayed by state"), width="stretch")

    st.subheader("Delivery delay vs review score")
    dr = fetch("delay_vs_review", P)
    if not ui.empty_notice(dr, "delay vs review"):
        dr = dr.assign(delay_bucket=dr["delay_bucket"].str[3:])
        fig = px.bar(dr, x="delay_bucket", y="avg_review_score", text_auto=".2f",
                     title="Average review score by delivery delay",
                     color_discrete_sequence=[ui.PRIMARY])
        fig.update_yaxes(range=[0, 5])
        ui.show(ui.style(fig))
        ui.table(dr)


def page_experience():
    left, right = st.columns(2)
    dist = fetch("review_distribution", P)
    with left:
        if not ui.empty_notice(dist, "review distribution"):
            fig = px.bar(dist, x="review_score", y="review_count", text_auto=True,
                         title="Review score distribution", color_discrete_sequence=[ui.PRIMARY])
            ui.show(ui.style(fig))
    with right:
        rd = fetch("rating_vs_delivery", P)
        if not ui.empty_notice(rd, "rating vs delivery"):
            rd = rd.assign(share=rd["review_count"] / rd.groupby("delivery_status")["review_count"]
                           .transform("sum") * 100)
            fig = px.bar(rd, x="review_score", y="share", color="delivery_status", barmode="group",
                         title="Rating mix: on time vs delayed (% of each group)",
                         color_discrete_map={"On time": ui.PRIMARY, "Delayed": ui.BAD})
            ui.show(ui.style(fig))
    st.subheader(f"Reviews by category (≥ {min_orders} reviews)")
    cat = fetch("reviews_by_category", P)
    if not ui.empty_notice(cat, "reviews by category"):
        fig = px.bar(cat.head(top_n), x="avg_review_score", y="category", orientation="h",
                     title=f"Lowest-rated categories (bottom {min(top_n, len(cat))})",
                     color_discrete_sequence=[ui.BAD])
        fig.update_yaxes(autorange="reversed")
        ui.show(ui.style(fig, 440))
        ui.table(cat)


@st.cache_data(ttl=600, show_spinner="Running statistical tests…")
def cached_stats(params_tuple: tuple) -> dict:
    orders = run_query(q.QUERIES["stats_orders"], params_tuple)
    return run_all_tests(orders)


def _render_test(result: dict, title: str) -> None:
    st.subheader(title)
    if "p_value" not in result:
        st.warning(f"Not enough data to run this test with the current filters: "
                   f"{result.get('status', 'unknown reason')}.")
        return
    st.markdown(f"**Question:** {result['question']}")
    st.markdown(f"**H₀:** {result['H0']}  \n**H₁:** {result['H1']}  \n**Test:** {result['test']} "
                f"(α = {result['alpha']})")
    c = st.columns(3)
    c[0].metric("Test statistic", f"{result['statistic']:.3f}")
    c[1].metric("p-value", ui.p_value_text(result["p_value"]))
    c[2].metric("Decision", result["decision"])
    with st.expander("Assumption checks and details"):
        st.json(result["assumptions"])
        extras = {k: v for k, v in result.items()
                  if k in ("cohens_d", "eta_squared", "cramers_v", "mean_on_time", "mean_delayed",
                           "mann_whitney_p_value_one_sided", "kruskal_wallis_p_value", "n_on_time",
                           "n_delayed", "n_orders", "dof", "posthoc")}
        st.json(extras)
    st.success(f"**Business insight:** {result['business_insight']}")


def page_stats():
    st.write("Each test follows: hypothesis → test selection → assumption checks → p-value → "
             "decision → business insight. Tests respect the sidebar filters.")
    res = cached_stats(to_params(P))
    _render_test(res["t_test_delivery_vs_review"], "1 · T-test: delivery delay vs review score")
    st.divider()
    _render_test(res["anova_category_vs_order_value"], "2 · ANOVA: order value across categories")
    a = res["anova_category_vs_order_value"]
    if "category_mean_order_value" in a:
        means = pd.Series(a["category_mean_order_value"]).rename("mean_order_value").reset_index()
        means.columns = ["category", "mean_order_value"]
        ui.show(ui.bar_chart(means, "category", "mean_order_value",
                             "Mean order value by category (tested categories)", horizontal=True,
                             height=440))
    st.divider()
    _render_test(res["chi_square_payment_vs_status"], "3 · Chi-square: payment method vs order status")
    c = res["chi_square_payment_vs_status"]
    if "contingency_table" in c:
        st.markdown("**Observed counts**")
        st.dataframe(pd.DataFrame(c["contingency_table"]), width="stretch")


def page_insights():
    keys = ["kpis", "monthly_revenue", "revenue_by_category", "sales_by_state", "repeat_vs_new",
            "top_sellers", "delivery_summary", "ontime_vs_delayed", "delivery_by_state",
            "delay_vs_review", "review_distribution", "reviews_by_category"]
    data = {k: fetch(k, P) for k in keys}
    insights = generate_insights(data, cached_stats(to_params(P)))
    if not insights:
        st.info("Not enough data under the current filters to derive insights.")
        return
    st.write("Generated from the filtered data: **Observation → Interpretation → Business impact "
             "→ Recommendation**.")
    areas = sorted({i["area"] for i in insights})
    chosen = st.multiselect("Show areas", areas, default=areas)
    for ins in insights:
        if ins["area"] in chosen:
            ui.insight_card(ins)


def page_sql():
    st.write("SQL used for the analysis, run live against the database. These queries use only "
             "the base tables and demonstrate the required SQL constructs.")
    names = list(q.ANALYSIS_QUERIES)
    choice = st.selectbox("Query", names, format_func=lambda n: q.ANALYSIS_QUERIES[n]["title"])
    spec = q.ANALYSIS_QUERIES[choice]
    st.markdown("**Concepts:** " + " · ".join(f"`{c}`" for c in spec["concepts"]))
    st.code(spec["sql"].strip(), language="sql")
    result = run_query(spec["sql"], None)
    st.caption(f"{len(result):,} rows")
    ui.table(result)
    with st.expander("Dashboard queries (parameterised, run on engineered feature tables)"):
        key = st.selectbox("Dashboard query", list(q.QUERIES))
        st.code(q.QUERIES[key].strip(), language="sql")


PAGES = {
    "Business Overview": page_overview, "Sales Analysis": page_sales,
    "Customer Analysis": page_customers, "Seller & Product Analysis": page_sellers_products,
    "Delivery Analysis": page_delivery, "Customer Experience": page_experience,
    "Statistical Tests": page_stats, "Business Insights": page_insights, "SQL Analysis": page_sql,
}
try:
    PAGES[section]()
except Exception as exc:  # noqa: BLE001 - surface the cause instead of a raw traceback wall
    st.error(f"Something went wrong while building this page: {type(exc).__name__}: {exc}")
    st.exception(exc)
