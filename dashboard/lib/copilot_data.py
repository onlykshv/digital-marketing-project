"""Deterministic retrieval layer for Retention Copilot.

Every function here reads only already-loaded, already-validated project outputs (via the same
loaders `lib.data` uses everywhere else in this dashboard) and returns a small, structured dict of
exactly the fields relevant to one question -- never a full dataframe, never all 971K customer
rows. This is the "structured retrieval" step the Copilot's architecture requires before any LLM
synthesis: the LLM (when configured) only ever sees what these functions return as a compact
evidence bundle, never raw customer data. Customer lookup is exact-ID equality match, never
semantic/fuzzy retrieval, per the project's explicit architecture requirement.
"""
from __future__ import annotations

import pandas as pd

# The 7 validated segments, in the same order used across the rest of the dashboard.
SEGMENTS = [
    "At-Risk, Auto-Renew Off",
    "At-Risk Veteran",
    "At-Risk Newcomer",
    "At-Risk, Price-Sensitive",
    "Unmatched At-Risk (no segment)",
    "Engaged Low-Risk (Champions)",
    "Stable / Monitor",
]

# segment_summary.csv labels one segment differently than marketing_action_plan.csv /
# value_by_segment.csv -- a documented mapping, not a new grouping.
_SEGMENT_SUMMARY_LABEL = {
    "Unmatched At-Risk (no segment)": "UNMATCHED (Medium/High risk, no segment)",
}


def get_customer_context(df: pd.DataFrame, msno: str) -> dict | None:
    """Exact-ID customer lookup. Returns None (never a fabricated partial record) if not found.

    Only returns fields that actually exist in `customer_segments.csv` / the merged lookup
    frame -- notably, no payment method, no demographics, no listening behavior are included
    because none of those exist in this project's data. A question requiring one of those fields
    must fall back to "that information is not available for this customer," never a guess.
    """
    match = df[df["msno"] == msno]
    if match.empty:
        return None
    row = match.iloc[0]
    # ~2,527 customers (of 970,960) have no recorded transaction activity at all -- every
    # transaction-derived field below is NaN for them in customer_segments.csv itself (not a
    # merge artifact). They still have a valid risk_tier/model_risk_score/calibrated_probability
    # (the model scores them from non-transaction features), so they are real, existing
    # customers -- never treat them as "not found." Every nullable field below is guarded the
    # same way `calibrated_probability`/`historical_realized_revenue_ntd`/`tenure_days` already
    # were, so a lookup never raises and never fabricates a 0/False in place of "unknown."
    return {
        "msno": row["msno"],
        "risk_tier": row["risk_tier"],
        "value_tier": row["value_tier"],
        "segment": row["segment"],
        "model_risk_score": float(row["risk_score_full"]),
        "calibrated_probability": float(row["calibrated_probability"]) if pd.notna(row["calibrated_probability"]) else None,
        "historical_realized_revenue_ntd": float(row["total_revenue"]) if pd.notna(row["total_revenue"]) else None,
        "latest_is_auto_renew": int(row["latest_is_auto_renew"]) if pd.notna(row["latest_is_auto_renew"]) else None,
        "auto_renew_pct": float(row["auto_renew_pct"]) if pd.notna(row["auto_renew_pct"]) else None,
        "tenure_days": float(row["tenure_days_at_cutoff"]) if pd.notna(row["tenure_days_at_cutoff"]) else None,
        "total_transactions": float(row["total_transactions"]) if pd.notna(row["total_transactions"]) else None,
        "avg_revenue_per_txn_ntd": float(row["avg_revenue_per_txn"]) if pd.notna(row["avg_revenue_per_txn"]) else None,
        "discount_rate": float(row["discount_rate"]) if pd.notna(row["discount_rate"]) else None,
        "cancel_rate": float(row["cancel_rate"]) if pd.notna(row["cancel_rate"]) else None,
        "days_since_last_txn": float(row["days_since_last_txn"]) if pd.notna(row["days_since_last_txn"]) else None,
    }


def get_population_baselines(df: pd.DataFrame) -> dict:
    """Base-rate averages used for 'this customer vs. the population' comparisons -- plain
    aggregates of columns already loaded, computed once per session (cheap relative to the
    971K-row load itself, not re-run per chat message thanks to Streamlit's cache on the load)."""
    return {
        "auto_renew_pct": float(df["latest_is_auto_renew"].mean()),
        "tenure_days_median": float(df["tenure_days_at_cutoff"].median()),
        "total_transactions_mean": float(df["total_transactions"].mean()),
        "cancel_rate_mean": float(df["cancel_rate"].mean()),
        "discount_rate_mean": float(df["discount_rate"].mean()),
        "days_since_last_txn_mean": float(df["days_since_last_txn"].mean()),
    }


def get_segment_context(action_plan: pd.DataFrame, segment_summary: pd.DataFrame, segment: str) -> dict | None:
    """Segment-level statistics for the Copilot's segment/general mode. Combines
    `marketing_action_plan.csv` (financial + recommendation fields, present for all 7 segments)
    with `segment_summary.csv` (behavioral medians, present for 6 of 7 -- absent for
    Stable / Monitor, in which case those specific fields come back as None and must be
    surfaced as 'not available', never guessed)."""
    plan_rows = action_plan[action_plan["priority_group"] == segment]
    if plan_rows.empty:
        return None
    plan = plan_rows.iloc[0]

    summary_label = _SEGMENT_SUMMARY_LABEL.get(segment, segment)
    summary_rows = segment_summary[segment_summary["segment"] == summary_label]
    summary = summary_rows.iloc[0] if not summary_rows.empty else None

    return {
        "segment": segment,
        "n_customers": int(plan["n_customers"]),
        "pct_of_base": float(plan["pct_of_base"]),
        "churn_rate_pct": float(plan["churn_rate_pct"]),
        "total_hrr_ntd": float(plan["total_HRR"]),
        "median_hrr_ntd": float(plan["median_HRR"]),
        "marketing_objective": plan["marketing_objective"],
        "intervention_intensity": plan["intervention_intensity"],
        "rationale": plan["rationale"],
        "defining_characteristics": plan["defining_characteristics"],
        "rule_definition": plan["rule_definition"],
        "median_days_since_last_txn": float(summary["median_days_since_last_txn"]) if summary is not None else None,
        "median_tenure_days": float(summary["median_tenure_days"]) if summary is not None else None,
        "auto_renew_rate_pct": float(summary["auto_renew_rate_pct"]) if summary is not None else None,
    }


def get_champions_context(action_plan: pd.DataFrame, value_by_segment: pd.DataFrame) -> dict:
    """Champions' key figures, used for 'compare with Champions' questions -- same source files
    as everywhere else Champions is shown (Overview, Action Center)."""
    plan = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
    vbs_rows = value_by_segment[value_by_segment["segment"] == "Engaged Low-Risk (Champions)"]
    vbs = vbs_rows.iloc[0] if not vbs_rows.empty else None
    return {
        "n_customers": int(plan["n_customers"]),
        "churn_rate_pct": float(plan["churn_rate_pct"]),
        "total_hrr_ntd": float(plan["total_HRR"]),
        "median_hrr_ntd": float(vbs["median_HRR"]) if vbs is not None else None,
    }


def get_top_drivers(shap_df: pd.DataFrame, feature_display_name_fn, n: int = 5) -> list[dict]:
    """Top-N global model drivers by mean |SHAP| -- the same ranking Priority Customers shows,
    reused here rather than recomputed."""
    top = shap_df.sort_values("mean_abs_shap", ascending=False).head(n)
    return [
        {"feature": r["feature"], "display_name": feature_display_name_fn(r["feature"]), "mean_abs_shap": float(r["mean_abs_shap"])}
        for _, r in top.iterrows()
    ]
