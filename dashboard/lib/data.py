"""Cached, read-only access to notebooks 01-09's saved outputs.

Every function here only reads existing files under outputs/ and models/ -- nothing in this
dashboard retrains a model, recomputes a segment, or writes back to those directories. Small
aggregate files (all under ~10KB) power every page except Customer Lookup, which is the only
page that touches the large per-customer files, and only once a user explicitly requests it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MODELS_DIR = PROJECT_ROOT / "models"


class MissingOutputError(Exception):
    """Raised when an expected notebook output file can't be found."""


def _require(path: Path) -> Path:
    if not path.exists():
        raise MissingOutputError(
            f"Expected file not found: `{path.relative_to(PROJECT_ROOT)}`. "
            "This dashboard only reads outputs already produced by notebooks 01-09 -- "
            "run the relevant notebook first, or check you're launching the app from the "
            "project's `dashboard/` folder."
        )
    return path


def safe_load(loader, *args, **kwargs):
    """Call a loader function, surfacing a friendly Streamlit error instead of a traceback."""
    try:
        return loader(*args, **kwargs)
    except MissingOutputError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any failure here should stop the page cleanly
        st.error(f"Couldn't load this page's data ({type(e).__name__}: {e}).")
        st.stop()


# ---------------------------------------------------------------------------
# Small aggregate files -- these power every page except Customer Lookup
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_risk_summary() -> dict:
    return json.loads(_require(OUTPUTS_DIR / "risk_scoring_summary.json").read_text())


@st.cache_data(show_spinner=False)
def load_action_plan() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "marketing_action_plan.csv"))


@st.cache_data(show_spinner=False)
def load_value_analysis() -> dict:
    return json.loads(_require(OUTPUTS_DIR / "marketing_value_analysis_results.json").read_text())


@st.cache_data(show_spinner=False)
def load_value_by_tier() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "value_by_risk_tier.csv"), index_col=0)


@st.cache_data(show_spinner=False)
def load_value_by_segment() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "value_by_segment.csv"))


@st.cache_data(show_spinner=False)
def load_risk_value_matrix() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "risk_value_matrix.csv"), index_col=0)


@st.cache_data(show_spinner=False)
def load_threshold_analysis() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "risk_scoring_threshold_analysis.csv"))


@st.cache_data(show_spinner=False)
def load_shap_importance() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "shap_feature_importance.csv"))


@st.cache_data(show_spinner=False)
def load_segment_summary() -> pd.DataFrame:
    return pd.read_csv(_require(OUTPUTS_DIR / "segment_summary.csv"))


@st.cache_data(show_spinner=False)
def load_temporal_results() -> dict:
    return json.loads(_require(OUTPUTS_DIR / "temporal_validation_results.json").read_text())


@st.cache_data(show_spinner=False)
def load_model_comparison() -> pd.DataFrame:
    return pd.read_csv(_require(MODELS_DIR / "model_comparison_final.csv"), index_col=0)


# ---------------------------------------------------------------------------
# Large per-customer files -- loaded ONLY by the Customer Lookup page, on demand
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading customer-level data (~971K rows) -- this can take a moment...")
def load_customer_lookup_data() -> pd.DataFrame:
    base = pd.read_csv(_require(OUTPUTS_DIR / "customer_segments.csv"))
    risk = pd.read_csv(
        _require(OUTPUTS_DIR / "risk_scoring_predictions.csv"),
        usecols=["msno", "risk_score_full"],
    )
    value = pd.read_csv(
        _require(OUTPUTS_DIR / "customer_value_tiers.csv"),
        usecols=["msno", "total_revenue", "value_tier"],
    )
    calibrated = pd.read_csv(
        _require(OUTPUTS_DIR / "calibrated_probabilities.csv"),
        usecols=["msno", "calibrated_probability"],
    )

    df = (
        base.merge(risk, on="msno", how="left")
        .merge(value, on="msno", how="left")
        .merge(calibrated, on="msno", how="left")
    )

    # Memory-conscious downcasting -- this host has ~7.4GB RAM total.
    float_cols = df.select_dtypes("float64").columns
    df[float_cols] = df[float_cols].astype("float32")
    for col in ("risk_tier", "segment", "value_tier"):
        df[col] = df[col].astype("category")
    return df


# ---------------------------------------------------------------------------
# Derived helpers (pure computation on already-loaded small files, no new data)
# ---------------------------------------------------------------------------

def total_realized_revenue(value_by_tier: pd.DataFrame) -> float:
    return float(value_by_tier["total_HRR_sum"].sum())


def high_risk_historical_revenue_exposure(risk_value_matrix: pd.DataFrame) -> float:
    """Sum of HRR held by customers in the High risk tier, across all value tiers.

    Ticket A-01: `risk_tier` is a threshold bucket of `risk_score_full` (XGBoost's raw,
    uncalibrated predict_proba output -- see 06_risk_scoring.ipynb §7 for the calibration audit).
    This function sums each High-tier customer's actual historical revenue at 100% weight; it
    does NOT multiply by any score or probability. Deliberately named and documented as an
    exposure total, not `P(churn) x revenue` -- see caveats.py's "revenue_exposure" panel for the
    full methodology note shown on the dashboard.
    """
    row = risk_value_matrix.loc["High"]
    return float(sum(row[f"n_{v}"] * row[f"avg_hrr_{v}"] for v in ("Low", "Medium", "High")))


# Groups that are not a retention target (they're either the safe majority or the
# growth/advocacy segment) -- excluded when ranking "priority opportunities."
_NON_RETENTION_GROUPS = {"Engaged Low-Risk (Champions)", "Stable / Monitor"}


def priority_opportunities(action_plan: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """The at-risk priority groups from marketing_action_plan.csv, ranked by realized revenue
    at stake -- the same rows already in that file, just filtered and ordered for the summary
    views (Command Center, Action Center)."""
    opp = action_plan[~action_plan["priority_group"].isin(_NON_RETENTION_GROUPS)].copy()
    opp = opp.sort_values("total_HRR", ascending=False)
    return opp.head(top_n) if top_n else opp


def customers_requiring_intervention(action_plan: pd.DataFrame) -> int:
    return int(priority_opportunities(action_plan)["n_customers"].sum())


def highest_value_segment(value_by_segment: pd.DataFrame) -> dict:
    row = value_by_segment.loc[value_by_segment["total_HRR"].idxmax()]
    return {"segment": row["segment"], "total_hrr": float(row["total_HRR"])}


def high_value_customer_count(risk_value_matrix: pd.DataFrame) -> int:
    return int(sum(risk_value_matrix.loc[r, "n_High"] for r in ("Low", "Medium", "High")))


# Human-readable labels for raw feature/column names surfaced from the model's SHAP output --
# a presentation mapping only. It does not add, remove, or reinterpret any feature.
FEATURE_DISPLAY_NAMES = {
    "latest_is_auto_renew": "Auto-renew status (most recent)",
    "first_transaction_date": "Date of first transaction",
    "txn_span_days": "Days between first and last transaction",
    "latest_payment_method_id": "Payment method (most recent)",
    "total_auto_renew": "Historical auto-renew count",
    "cancel_rate": "Cancellation rate",
    "latest_plan_list_price": "List price (most recent plan)",
    "total_transactions": "Total number of transactions",
    "latest_actual_amount_paid": "Amount paid (most recent transaction)",
    "total_cancellations": "Total cancellations",
    "total_revenue": "Total historical revenue",
    "avg_revenue_per_txn": "Average revenue per transaction",
    "tenure_days_at_cutoff": "Tenure (days)",
    "total_list_price": "Total list price (pre-discount)",
    "registration_init_time": "Registration date",
    "auto_renew_pct": "Share of transactions with auto-renew on",
    "days_since_last_txn": "Days since last transaction",
    "discount_rate": "Average discount rate",
}


def feature_display_name(raw_name: str) -> str:
    return FEATURE_DISPLAY_NAMES.get(raw_name, raw_name.replace("_", " ").capitalize())


# Short, table-friendly action verbs -- a compression of each segment's existing
# `marketing_objective` sentence (see marketing_action_plan.csv), not a new recommendation.
SHORT_ACTION_BY_SEGMENT = {
    "At-Risk, Auto-Renew Off": "Re-engage",
    "At-Risk Veteran": "Loyalty outreach",
    "At-Risk Newcomer": "Onboarding nudge",
    "At-Risk, Price-Sensitive": "Pricing conversation",
    "Unmatched At-Risk (no segment)": "Standard outreach",
    "Engaged Low-Risk (Champions)": "Upsell / advocacy",
    "Stable / Monitor": "Monitor only",
}

# One-line, human-readable restatement of each segment's existing `rule_definition` /
# `defining_characteristics` (marketing_action_plan.csv) -- not a new causal claim, just a
# plain-English compression of a rule that already exists.
SHORT_WHY_BY_SEGMENT = {
    "At-Risk, Auto-Renew Off": "Customer subscription state indicates elevated retention risk.",
    "At-Risk Veteran": "Long-tenured customer showing risk signals despite auto-renew being on.",
    "At-Risk Newcomer": "New customer (under 6 months) already showing elevated risk -- likely an onboarding gap, not a price issue.",
    "At-Risk, Price-Sensitive": "Heavy historical discount usage alongside elevated risk.",
    "Unmatched At-Risk (no segment)": "Elevated risk without a clear single driver -- treated with the standard tier-based playbook.",
    "Engaged Low-Risk (Champions)": "Low risk and high historical value -- a growth, not retention, case.",
    "Stable / Monitor": "Low risk and no standout value signal to act on.",
}


# What NOT to do for a segment -- the inverse framing of the same already-validated
# `marketing_objective` / `intervention_intensity` fields (marketing_action_plan.csv), not a new
# claim about any individual customer. Used only to warn against a mismatched default response
# (e.g. reaching for a discount outside the one segment where the framework actually recommends
# one) -- never a causal statement about what will or won't work.
AVOID_BY_SEGMENT = {
    "At-Risk, Auto-Renew Off": "Don't lead with a discount -- the framework's highest-leverage response here is a low-cost auto-renew nudge, not a price concession.",
    "At-Risk Veteran": "Avoid a generic acquisition-style script -- this is a long-tenured customer with auto-renew already on; treat as loyalty/appreciation outreach, not a new-customer pitch.",
    "At-Risk Newcomer": "Avoid assuming a price problem -- the newcomer pattern (under 6 months) points to an onboarding gap, not price sensitivity, so a discount is not the framework's recommendation here.",
    "At-Risk, Price-Sensitive": "Avoid a high-touch, high-cost campaign -- this segment's defining signal is discount usage, so the framework calls for a pricing/plan-fit conversation, not premium outreach.",
    "Unmatched At-Risk (no segment)": "Avoid a specialized script -- this customer didn't match any defined segment pattern, so the standard tier-based playbook applies, not a customized one.",
    "Engaged Low-Risk (Champions)": "Avoid retention spend entirely -- this is a growth/advocacy case, not a churn risk, per the framework.",
    "Stable / Monitor": "Avoid proactive outreach -- no risk or value signal currently in the framework justifies spend on this customer.",
}


def key_risk_signal(latest_is_auto_renew, days_since_last_txn, cancel_rate) -> str:
    """One short, human-readable behavioral flag per customer -- a plain restatement of already-
    loaded columns, prioritized by the model's own SHAP ranking (auto-renew is the top driver;
    see Priority Customers' "why at risk" section). Not a new signal, not a new computation
    beyond picking which existing fact to surface first.

    `days_since_last_txn > 30` uses the exact breakpoint 01_eda.ipynb's findings already
    established (churn rate jumps from 5.8% to 55%+ past 30 days of inactivity) -- not an
    arbitrary new cutoff.

    A small subset of customers (~2,527 of 970,960) have no recorded transaction activity at
    all, so these inputs can legitimately be `None` rather than a real value -- never guessed as
    0/False, per `copilot_data.get_customer_context()`. Handled explicitly below rather than
    left to raise on a `None > 30` comparison.
    """
    if latest_is_auto_renew is None and days_since_last_txn is None and cancel_rate is None:
        return "Limited transaction history"
    if latest_is_auto_renew == 0:
        return "Auto-renew OFF"
    if days_since_last_txn is not None and days_since_last_txn > 30:
        return "Inactive 30+ days"
    if cancel_rate is not None and cancel_rate > 0.05:
        return "Elevated cancellation history"
    return "Multiple smaller signals"
