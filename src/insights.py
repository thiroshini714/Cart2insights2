"""Step 11: turn query results into Observation -> Interpretation -> Business Impact insights.

Every number is computed from the frames passed in; nothing is hardcoded. An insight is
skipped when the data needed for it is missing or empty.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

CURRENCY = os.getenv("CURRENCY_SYMBOL", "R$")


def _money(x: float) -> str:
    return f"{CURRENCY} {x:,.0f}"


def _ok(df) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty


def _insight(area, observation, interpretation, impact, recommendation) -> dict:
    return {"area": area, "observation": observation, "interpretation": interpretation,
            "business_impact": impact, "recommendation": recommendation}


def generate_insights(data: dict, stats_results: dict | None = None) -> list[dict]:
    out: list[dict] = []
    kpis = data.get("kpis")
    total_rev = float(kpis["total_revenue"].iloc[0]) if _ok(kpis) else None

    # 1. Revenue trend ------------------------------------------------------------------
    m = data.get("monthly_revenue")
    if _ok(m) and len(m) >= 3:
        peak = m.loc[m["revenue"].idxmax()]
        slope = float(np.polyfit(np.arange(len(m)), m["revenue"].astype(float), 1)[0])
        growth = m["mom_growth_pct"].dropna()
        direction = "upward" if slope > 0 else "downward"
        out.append(_insight(
            "Sales",
            f"Monthly revenue peaked at {_money(peak['revenue'])} in {peak['order_month']}. Across "
            f"{len(m)} months the fitted trend is {direction} ({_money(abs(slope))} per month); the "
            f"median month-over-month change is {growth.median():+.1f}%." if len(growth) else
            f"Monthly revenue peaked at {_money(peak['revenue'])} in {peak['order_month']}.",
            ("Revenue is growing steadily, with month-to-month swings around that trend."
             if slope > 0 else "Revenue is flat or declining over the selected period."),
            ("The business is scaling; capacity (logistics, support) must keep pace with the peak."
             if slope > 0 else "Sustained decline puts targets at risk and needs investigation."),
            "Plan inventory and delivery capacity around peak months; check first/last months "
            "for partial-period effects before reading growth rates literally."))

    # 2. Category concentration ---------------------------------------------------------
    c = data.get("revenue_by_category")
    if _ok(c) and len(c) >= 3:
        k = min(5, len(c))
        share = float(c["revenue"].head(k).sum() / c["revenue"].sum() * 100)
        top = ", ".join(c["category"].head(3))
        out.append(_insight(
            "Products",
            f"The top {k} categories generate {share:.0f}% of revenue; the leaders are {top}.",
            "Revenue is concentrated in a handful of categories." if share >= 50 else
            "Revenue is spread fairly evenly across categories.",
            "Performance of a few categories dominates the top line." if share >= 50 else
            "The business is not overly exposed to any single category.",
            "Protect stock and seller quality in top categories; test growth bets in the long tail."
            if share >= 50 else "Prioritise categories by margin and review score, not just volume."))

    # 3. Geography ----------------------------------------------------------------------
    s = data.get("sales_by_state")
    if _ok(s) and len(s) >= 3:
        top3 = s.head(3)
        share = float(top3["revenue_share_pct"].sum())
        out.append(_insight(
            "Sales",
            f"{', '.join(top3['state'])} together account for {share:.0f}% of revenue.",
            "Demand is geographically concentrated." if share >= 50 else "Demand is geographically spread.",
            "Regional disruption in the leading states would hit revenue hardest."
            if share >= 50 else "Regional risk is diversified.",
            "Focus fulfilment investment (warehouses, carrier SLAs) on the leading states; "
            "assess marketing for under-penetrated states."))

    # 4. Repeat customers ---------------------------------------------------------------
    r = data.get("repeat_vs_new")
    if _ok(r) and "Repeat" in set(r["customer_type"]):
        tot_c = r["customers"].sum()
        rep = r[r["customer_type"] == "Repeat"].iloc[0]
        rep_pct = float(rep["customers"] / tot_c * 100)
        rev_pct = float(rep["revenue"] / r["revenue"].sum() * 100)
        out.append(_insight(
            "Customers",
            f"Only {rep_pct:.1f}% of customers ordered more than once; they contribute "
            f"{rev_pct:.1f}% of revenue.",
            "Most customers buy once and do not return." if rep_pct < 20 else
            "A meaningful share of customers returns.",
            "Growth depends mainly on acquiring new customers, which is costlier than retention."
            if rep_pct < 20 else "Retention is already contributing materially to revenue.",
            "Introduce post-purchase re-engagement (coupons, recommendations) aimed at second orders."))

    # 5. Delivery vs review -------------------------------------------------------------
    o = data.get("ontime_vs_delayed")
    ds = data.get("delivery_summary")
    if _ok(o) and {"On time", "Delayed"} <= set(o["delivery_status"]):
        on = o[o["delivery_status"] == "On time"].iloc[0]
        late = o[o["delivery_status"] == "Delayed"].iloc[0]
        gap = float(late["avg_review_score"] - on["avg_review_score"])
        pct_late = float(ds["pct_delayed"].iloc[0]) if _ok(ds) else float(
            late["order_count"] / o["order_count"].sum() * 100)
        sig = ""
        t = (stats_results or {}).get("t_test_delivery_vs_review")
        if t and "p_value" in t:
            sig = (" The one-sided t-test is significant." if t["significant"]
                   else " The one-sided t-test is not significant.")
        out.append(_insight(
            "Delivery",
            f"{pct_late:.1f}% of delivered orders arrived after the estimated date. Delayed orders "
            f"average {late['avg_review_score']:.2f} stars vs {on['avg_review_score']:.2f} for "
            f"on-time orders (gap {gap:+.2f}).{sig}",
            "Late delivery is associated with lower ratings." if gap < 0 else
            "Delayed orders are not rated lower in this data.",
            "Delivery performance directly influences customer satisfaction and public ratings."
            if gap < 0 else "Delivery delay does not appear to be driving ratings.",
            "Set tighter carrier SLAs and proactive delay notifications; "
            "prioritise the slowest regions."))

    # 6. Delay severity -----------------------------------------------------------------
    d = data.get("delay_vs_review")
    if _ok(d) and len(d) >= 3 and d["avg_review_score"].notna().sum() >= 3:
        best = d.loc[d["avg_review_score"].idxmax()]
        worst = d.loc[d["avg_review_score"].idxmin()]
        out.append(_insight(
            "Delivery",
            f"Average rating ranges from {best['avg_review_score']:.2f} ('{best['delay_bucket'][3:]}') "
            f"to {worst['avg_review_score']:.2f} ('{worst['delay_bucket'][3:]}').",
            "Rating depends on how late an order is, not only whether it is late.",
            "Long delays are disproportionately costly in satisfaction.",
            "Escalate orders that are already more than a few days late (refunds, outreach)."))

    # 7. Regional delivery --------------------------------------------------------------
    dstate = data.get("delivery_by_state")
    if _ok(dstate) and len(dstate) >= 3:
        worst = dstate.iloc[0]
        best = dstate.sort_values("avg_delivery_days").iloc[0]
        out.append(_insight(
            "Delivery",
            f"Delivery is slowest in {worst['state']} ({worst['avg_delivery_days']:.1f} days, "
            f"{worst['pct_delayed']:.1f}% delayed) and fastest in {best['state']} "
            f"({best['avg_delivery_days']:.1f} days).",
            "Delivery performance varies materially by region.",
            "Slow regions add delay risk and drag down ratings.",
            f"Review carrier coverage and delivery estimates for {worst['state']}."))

    # 8. Seller concentration -----------------------------------------------------------
    sel = data.get("top_sellers")
    if _ok(sel) and total_rev:
        n = min(10, len(sel))
        share = float(sel["seller_revenue"].head(n).sum() / total_rev * 100)
        out.append(_insight(
            "Sellers",
            f"The top {n} sellers generate {share:.0f}% of revenue.",
            "Revenue is concentrated among a few sellers." if share >= 30 else
            "Revenue is distributed across many sellers.",
            "Losing a top seller would noticeably dent revenue." if share >= 30 else
            "Seller-concentration risk is low.",
            "Run a key-seller programme (SLAs, quality coaching) for the top group."
            if share >= 30 else "Focus on lifting the median seller's quality and volume."))

    # 9. Review distribution ------------------------------------------------------------
    rd = data.get("review_distribution")
    if _ok(rd):
        neg = float(rd.loc[rd["review_score"] <= 2, "pct_of_reviews"].sum())
        five = float(rd.loc[rd["review_score"] == 5, "pct_of_reviews"].sum())
        out.append(_insight(
            "Customer experience",
            f"{five:.0f}% of reviews are 5 stars and {neg:.0f}% are 1-2 stars.",
            "Satisfaction is generally high with a tail of dissatisfied customers."
            if five > neg else "Dissatisfaction is a substantial share of reviews.",
            "Each negative review is public and reduces conversion for the seller and platform.",
            "Analyse 1-2 star orders for root causes (delay, product, seller) and act on the top one."))

    # 10. Categories with worst reviews -------------------------------------------------
    rc = data.get("reviews_by_category")
    if _ok(rc) and len(rc) >= 3:
        low = rc.iloc[0]
        out.append(_insight(
            "Customer experience",
            f"'{low['category']}' has the lowest average rating ({low['avg_review_score']:.2f}, "
            f"{low['pct_negative']:.0f}% negative) among categories with enough reviews.",
            "Satisfaction differs by category, pointing to category-specific issues.",
            "Weak categories can erode trust in the whole marketplace.",
            f"Audit product quality, descriptions and sellers in '{low['category']}'."))

    # 11. Remaining statistical tests ---------------------------------------------------
    for key, area in (("anova_category_vs_order_value", "Products"),
                      ("chi_square_payment_vs_status", "Payments")):
        res = (stats_results or {}).get(key)
        if res and "business_insight" in res:
            out.append(_insight(
                area,
                f"{res['test']}: statistic={res['statistic']:.2f}, p-value={res['p_value']:.4g} "
                f"-> {res['decision']} at alpha={res['alpha']}.",
                res["business_insight"],
                "Evidence-based: derived from a formal hypothesis test, not just a chart.",
                "Use this result to prioritise category strategy." if area == "Products" else
                "Track payment methods whose orders more often fail to complete."))
    return out


def insights_to_markdown(insights: list[dict], title: str = "Business Insights & Recommendations",
                         banner: str | None = None) -> str:
    lines = [f"# {title}", ""]
    if banner:
        lines += [f"> {banner}", ""]
    for i, ins in enumerate(insights, 1):
        lines += [f"## {i}. {ins['area']}",
                  f"- **Observation:** {ins['observation']}",
                  f"- **Interpretation:** {ins['interpretation']}",
                  f"- **Business impact:** {ins['business_impact']}",
                  f"- **Recommendation:** {ins['recommendation']}", ""]
    return "\n".join(lines)
