"""Step 9: hypothesis tests.

Each test follows: hypothesis -> test selection -> assumption checks -> p-value ->
statistical decision -> business insight.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import ALPHA


def _fmt_p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def _shapiro(sample: np.ndarray, seed: int = 0) -> dict:
    """Shapiro-Wilk on at most 5000 points (scipy's reliable range)."""
    sample = np.asarray(sample, dtype=float)
    if len(sample) < 3 or np.ptp(sample) == 0:
        return {"tested": False, "note": "not enough variation to test"}
    if len(sample) > 5000:
        sample = np.random.default_rng(seed).choice(sample, 5000, replace=False)
    stat, p = stats.shapiro(sample)
    return {"tested": True, "statistic": float(stat), "p_value": float(p), "normal": bool(p > ALPHA)}


# --------------------------------------------------------------------------- t-test
def ttest_delivery_vs_review(df: pd.DataFrame) -> dict:
    """Do delayed orders receive significantly lower review scores than on-time orders?"""
    data = df[df["delivery_status"].isin(["On time", "Delayed"]) & df["review_score"].notna()]
    on_time = data.loc[data["delivery_status"] == "On time", "review_score"].astype(float).to_numpy()
    delayed = data.loc[data["delivery_status"] == "Delayed", "review_score"].astype(float).to_numpy()
    result: dict = {
        "test": "Independent two-sample t-test (Welch)",
        "question": "Do delayed orders receive significantly lower review scores than on-time orders?",
        "H0": "Mean review score of delayed orders >= mean review score of on-time orders.",
        "H1": "Mean review score of delayed orders < mean review score of on-time orders.",
        "alpha": ALPHA, "n_on_time": int(len(on_time)), "n_delayed": int(len(delayed)),
    }
    if len(on_time) < 2 or len(delayed) < 2:
        result["status"] = "insufficient data (need >= 2 reviewed orders in each group)"
        return result

    lev_stat, lev_p = stats.levene(on_time, delayed)
    equal_var = bool(lev_p > ALPHA)
    t_stat, p_less = stats.ttest_ind(delayed, on_time, equal_var=False, alternative="less")
    _, p_two = stats.ttest_ind(delayed, on_time, equal_var=False)
    mw_stat, mw_p = stats.mannwhitneyu(delayed, on_time, alternative="less")

    pooled_sd = np.sqrt(((len(delayed) - 1) * delayed.var(ddof=1)
                         + (len(on_time) - 1) * on_time.var(ddof=1))
                        / (len(delayed) + len(on_time) - 2))
    cohens_d = float((delayed.mean() - on_time.mean()) / pooled_sd) if pooled_sd > 0 else 0.0
    reject = bool(p_less < ALPHA)
    gap = float(delayed.mean() - on_time.mean())

    result.update({
        "mean_on_time": float(on_time.mean()), "mean_delayed": float(delayed.mean()),
        "mean_difference": gap,
        "assumptions": {
            "independence": "Each order is reviewed once, so groups are independent observations.",
            "normality": {
                "on_time": _shapiro(on_time), "delayed": _shapiro(delayed),
                "note": ("Review scores are discrete (1-5), so exact normality does not hold. "
                         "With large groups the t-test is robust (central limit theorem); the "
                         "Mann-Whitney U test below is reported as a non-parametric check."),
            },
            "equal_variance": {"levene_statistic": float(lev_stat), "p_value": float(lev_p),
                               "equal": equal_var,
                               "handling": "Welch's t-test used (does not assume equal variance)."},
        },
        "statistic": float(t_stat), "p_value": float(p_less), "p_value_two_sided": float(p_two),
        "mann_whitney_p_value_one_sided": float(mw_p),
        "cohens_d": cohens_d,
        "decision": ("Reject H0" if reject else "Fail to reject H0"),
        "significant": reject,
    })
    size = abs(cohens_d)
    magnitude = "negligible" if size < 0.2 else "small" if size < 0.5 else "medium" if size < 0.8 else "large"
    if reject:
        result["business_insight"] = (
            f"Delayed orders score {abs(gap):.2f} points lower on average "
            f"({delayed.mean():.2f} vs {on_time.mean():.2f}; p {_fmt_p(p_less)}, effect size "
            f"{magnitude}). Late delivery measurably hurts customer satisfaction, so on-time "
            f"performance is a lever for ratings.")
    else:
        result["business_insight"] = (
            f"No statistically significant rating penalty for delayed orders was found "
            f"({delayed.mean():.2f} vs {on_time.mean():.2f}; p {_fmt_p(p_less)}). Delivery delay "
            f"alone does not explain review scores in this data.")
    return result


# --------------------------------------------------------------------------- ANOVA
def anova_category_vs_order_value(df: pd.DataFrame, min_orders: int = 30, top_k: int = 15) -> dict:
    """Does average order value differ significantly across product categories?"""
    data = df[(df["is_valid_sale"] == 1) & (df["total_order_value"] > 0)]
    counts = data["primary_category"].value_counts()
    keep = counts[counts >= min_orders].head(top_k).index.tolist()
    result: dict = {
        "test": "One-way ANOVA (on log order value) with Kruskal-Wallis check",
        "question": "Does the average order value differ significantly across product categories?",
        "H0": "All product categories have the same mean order value.",
        "H1": "At least one category's mean order value differs.",
        "alpha": ALPHA, "categories_tested": keep,
        "min_orders_per_category": min_orders,
    }
    if len(keep) < 2:
        result["status"] = f"insufficient data (need >= 2 categories with >= {min_orders} orders)"
        return result
    sub = data[data["primary_category"].isin(keep)]
    groups_raw = [sub.loc[sub["primary_category"] == c, "total_order_value"].to_numpy() for c in keep]
    groups_log = [np.log1p(g) for g in groups_raw]

    raw_skew = float(stats.skew(np.concatenate(groups_raw)))
    log_skew = float(stats.skew(np.concatenate(groups_log)))
    lev_stat, lev_p = stats.levene(*groups_log)
    shapiro_resid = _shapiro(np.concatenate([g - g.mean() for g in groups_log]))
    f_stat, p_val = stats.f_oneway(*groups_log)
    kw_stat, kw_p = stats.kruskal(*groups_raw)

    grand = np.concatenate(groups_log)
    ss_between = sum(len(g) * (g.mean() - grand.mean()) ** 2 for g in groups_log)
    ss_total = float(((grand - grand.mean()) ** 2).sum())
    eta_sq = float(ss_between / ss_total) if ss_total > 0 else 0.0
    reject = bool(p_val < ALPHA)

    posthoc = None
    if reject and len(keep) <= 15:
        tk = stats.tukey_hsd(*groups_log)
        sig_pairs = int(((tk.pvalue < ALPHA).sum() - len(keep)) // 2)
        posthoc = {"method": "Tukey HSD on log values",
                   "significant_pairs": sig_pairs,
                   "total_pairs": len(keep) * (len(keep) - 1) // 2}

    cat_means = (sub.groupby("primary_category")["total_order_value"].mean()
                 .sort_values(ascending=False))
    result.update({
        "n_orders": int(len(sub)),
        "category_mean_order_value": {k: float(v) for k, v in cat_means.items()},
        "assumptions": {
            "independence": "Each order belongs to exactly one (primary) category.",
            "skewness": {"raw": raw_skew, "log": log_skew,
                         "handling": "Order values are right-skewed, so ANOVA runs on log1p(value)."},
            "normality_of_residuals": {**shapiro_resid,
                                       "note": "ANOVA is robust to mild non-normality with large groups."},
            "equal_variance": {"levene_statistic": float(lev_stat), "p_value": float(lev_p),
                               "equal": bool(lev_p > ALPHA)},
        },
        "statistic": float(f_stat), "p_value": float(p_val),
        "kruskal_wallis_p_value": float(kw_p), "eta_squared": eta_sq,
        "posthoc": posthoc,
        "decision": "Reject H0" if reject else "Fail to reject H0", "significant": reject,
    })
    if reject:
        hi, lo = cat_means.index[0], cat_means.index[-1]
        result["business_insight"] = (
            f"Order value differs significantly across categories (F={f_stat:.2f}, "
            f"p {_fmt_p(p_val)}; category explains {eta_sq * 100:.1f}% of log-value variance). "
            f"'{hi}' has the highest mean order value ({cat_means.iloc[0]:.2f}) and '{lo}' the "
            f"lowest ({cat_means.iloc[-1]:.2f}). Category mix is a real driver of basket size, "
            f"so cross-sell and promotion strategy should be category-specific.")
    else:
        result["business_insight"] = (
            f"No significant difference in order value across categories (p {_fmt_p(p_val)}). "
            f"Spending per order looks similar regardless of category.")
    return result


# --------------------------------------------------------------------------- chi-square
def chi_square_payment_vs_status(df: pd.DataFrame, min_expected: float = 5.0,
                                 min_level_count: int = 30) -> dict:
    """Is payment method associated with order status?"""
    data = df[df["primary_payment_type"].notna() & df["order_status"].notna()
              & (df["primary_payment_type"] != "unknown")].copy()
    result: dict = {
        "test": "Chi-square test of independence",
        "question": "Is there a significant association between payment method and order status?",
        "H0": "Payment method and order status are independent.",
        "H1": "Payment method and order status are associated.",
        "alpha": ALPHA,
    }
    # Pool very rare levels so expected counts stay valid.
    for col in ("primary_payment_type", "order_status"):
        vc = data[col].value_counts()
        rare = vc[vc < min_level_count].index
        data[col] = data[col].where(~data[col].isin(rare), "other")
    table = pd.crosstab(data["primary_payment_type"], data["order_status"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        result["status"] = "insufficient data (need at least 2 payment methods and 2 statuses)"
        return result

    chi2, p_val, dof, expected = stats.chi2_contingency(table)
    pct_low = float((expected < min_expected).mean() * 100)
    n = table.to_numpy().sum()
    cramers_v = float(np.sqrt(chi2 / (n * (min(table.shape) - 1))))
    reject = bool(p_val < ALPHA)

    std_resid = (table.to_numpy() - expected) / np.sqrt(expected)
    resid = pd.DataFrame(std_resid, index=table.index, columns=table.columns)
    top = resid.stack().abs().sort_values(ascending=False).head(3)
    drivers = [{"payment_type": i, "order_status": c,
                "standardised_residual": float(resid.loc[i, c])} for (i, c) in top.index]

    result.update({
        "n_orders": int(n), "contingency_table": table.to_dict(),
        "dof": int(dof),
        "assumptions": {
            "independence": "Each order is counted once (primary payment method only).",
            "expected_counts": {
                "pct_cells_below_5": pct_low,
                "ok": bool(pct_low <= 20),
                "handling": f"Levels with fewer than {min_level_count} orders were pooled as 'other'.",
            },
        },
        "statistic": float(chi2), "p_value": float(p_val), "cramers_v": cramers_v,
        "largest_residuals": drivers,
        "decision": "Reject H0" if reject else "Fail to reject H0", "significant": reject,
    })
    strength = "weak" if cramers_v < 0.1 else "modest" if cramers_v < 0.3 else "strong"
    if reject:
        d = drivers[0]
        direction = "more" if d["standardised_residual"] > 0 else "fewer"
        result["business_insight"] = (
            f"Payment method and order status are significantly associated "
            f"(chi2={chi2:.1f}, p {_fmt_p(p_val)}) but the association is {strength} "
            f"(Cramer's V={cramers_v:.3f}). The biggest deviation: '{d['payment_type']}' orders "
            f"have {direction} '{d['order_status']}' outcomes than expected. Monitor payment "
            f"methods whose orders end in non-delivered statuses.")
    else:
        result["business_insight"] = (
            f"No significant association between payment method and order status "
            f"(p {_fmt_p(p_val)}); order outcomes look similar across payment methods.")
    return result


def run_all_tests(df: pd.DataFrame) -> dict[str, dict]:
    """df: order-level frame (columns of the `stats_orders` query)."""
    return {
        "t_test_delivery_vs_review": ttest_delivery_vs_review(df),
        "anova_category_vs_order_value": anova_category_vs_order_value(df),
        "chi_square_payment_vs_status": chi_square_payment_vs_status(df),
    }
