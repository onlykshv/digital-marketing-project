"""Deterministic tool layer for the future AI orchestrator (Retention Operations Assistant).

PRODUCT PRINCIPLE (KKBox Retention Intelligence: Predict -> Prioritize -> Act):
The existing ML/analytics pipeline (notebooks 01-12, src/, models/, outputs/) is the engine.
An AI assistant will eventually orchestrate these tools; this module IS that orchestration
surface, but contains NO LLM code and NO UI code. Every function here is a plain, synchronous,
side-effect-free Python function over already-loaded pandas/dict data. Nothing here retrains a
model, recomputes a segment, writes to disk, or calls out to any network service.

Every tool returns the same predictable shape:

    {"ok": True,  "data": <result>, "error": None}
    {"ok": False, "data": None,     "error": "<human-readable reason>"}

A tool NEVER silently turns missing data into an invented value. A customer or segment that
doesn't exist returns `ok=False` with an explicit error -- never a fabricated partial record.

This module deliberately does not duplicate business logic that already lives elsewhere:
- `lib.data` is the sole reader of `outputs/*.csv` / `outputs/*.json` (unchanged, not touched).
- `lib.copilot_data` already implements exact-ID customer/segment retrieval (unchanged, reused).
- `lib.copilot_engine` already implements the segment-priority ranking and the SHORT_*_BY_SEGMENT
  / AVOID_BY_SEGMENT action-framework mappings (via `lib.data`, unchanged, reused).
Every tool below is a thin, testable wrapper that composes those existing functions into the
shape an agent orchestrator needs, or -- only where no reusable function existed yet
(`search_customers`, `get_aggregate_metrics`, `build_dashboard_deep_link`) -- new code written in
the same style and against the same already-cached dataframes those pages already load.

TERMINOLOGY (do not rename or reinterpret -- see docstrings below for exact provenance):
    Model Risk Score                    != Estimated Churn Probability
    Historical Realized Revenue (HRR)   != CLV / Lifetime Value / Future Revenue
    High-Risk Historical Revenue Exposure != Expected Revenue Loss (P(churn) x revenue)
"""
from __future__ import annotations

import pandas as pd

from lib import copilot_data, data

# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def _ok(result) -> dict:
    return {"ok": True, "data": result, "error": None}


def _err(message: str) -> dict:
    return {"ok": False, "data": None, "error": message}


_KNOWN_SEGMENTS = copilot_data.SEGMENTS  # the 7 validated segments -- do not invent new ones
_SORTABLE_COLUMNS = ("risk_score_full", "calibrated_probability", "total_revenue")
_RISK_TIERS = ("Low", "Medium", "High")
_VALUE_TIERS = ("Low", "Medium", "High")


def _as_list(value) -> list | None:
    """Normalizes a single string or a list of strings into a list, or None if not given."""
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return list(value)


# ---------------------------------------------------------------------------
# 1. get_customer
# ---------------------------------------------------------------------------


def get_customer(df: pd.DataFrame, customer_id: str) -> dict:
    """Retrieve the complete grounded profile for one customer, by exact ID.

    Source of truth: `lib.copilot_data.get_customer_context()`, which merges
    outputs/customer_segments.csv + risk_scoring_predictions.csv + customer_value_tiers.csv +
    calibrated_probabilities.csv (the same merge `data.load_customer_lookup_data()` performs).
    Lookup is EXACT `msno` equality -- never fuzzy/substring/semantic matching -- so a mistyped
    or fabricated ID reliably returns "not found" rather than a wrong customer.

    Fields NOT included because they do not exist anywhere in this project's processed data
    (never fabricated to fill the gap): payment method, membership expiry state, demographics,
    listening/content-consumption behavior. A caller asking for one of these must be told it is
    not available, not given a guess.

    Returns (on success) a dict with:
        msno, risk_tier, value_tier, segment,
        model_risk_score              (raw XGBoost score -- NOT a probability, see module docstring)
        calibrated_probability        (Estimated Churn Probability; None if unavailable)
        historical_realized_revenue_ntd (HRR -- money already collected, NOT CLV; None if unavailable)
        latest_is_auto_renew, auto_renew_pct, tenure_days, total_transactions,
        avg_revenue_per_txn_ntd, discount_rate, cancel_rate, days_since_last_txn,
        key_risk_signal                (one short behavioral flag -- see `data.key_risk_signal`)
    """
    if not customer_id or not isinstance(customer_id, str):
        return _err("customer_id must be a non-empty string")

    ctx = copilot_data.get_customer_context(df, customer_id)
    if ctx is None:
        return _err("Customer not found in the scored customer base")

    ctx = dict(ctx)
    ctx["key_risk_signal"] = data.key_risk_signal(
        ctx["latest_is_auto_renew"], ctx["days_since_last_txn"], ctx["cancel_rate"]
    )
    return _ok(ctx)


# ---------------------------------------------------------------------------
# 2. search_customers
# ---------------------------------------------------------------------------


def search_customers(
    df: pd.DataFrame,
    *,
    risk_tier: str | list[str] | None = None,
    value_tier: str | list[str] | None = None,
    segment: str | list[str] | None = None,
    min_risk_score: float | None = None,
    max_risk_score: float | None = None,
    min_calibrated_probability: float | None = None,
    max_calibrated_probability: float | None = None,
    min_hrr_ntd: float | None = None,
    max_hrr_ntd: float | None = None,
    auto_renew: bool | None = None,
    sort_by: str = "risk_score_full",
    ascending: bool = False,
    limit: int = 20,
) -> dict:
    """Return customers matching manager-defined criteria (e.g. "top 20 high-risk customers",
    "high-risk high-value customers", "customers in At-Risk Veteran segment").

    Source of truth: the same cached, merged customer frame every dashboard page already reads
    (`data.load_customer_lookup_data()`). No raw log file is read -- this filters the already
    processed ~971K-row output the dashboard has always used, in memory, the same way
    `pages/priority_customers.py` already filters it (this function generalizes that page's
    inline filter logic into one reusable, independently-testable function).

    All range filters are inclusive and optional; omitted bounds are unconstrained. `risk_tier`,
    `value_tier`, and `segment` accept either a single string or a list of strings. `sort_by`
    must be one of "risk_score_full" (Model Risk Score), "calibrated_probability" (Estimated
    Churn Probability), or "total_revenue" (HRR). `limit` is capped at 200 to keep results
    small and reviewable -- this tool is for a prioritized work list, not a bulk export (the
    dashboard's own CSV download already covers that).

    Returns a dict with:
        total_matches: int   -- how many rows matched before `limit` was applied
        rows: list[dict]     -- up to `limit` rows, each with msno, risk_tier, value_tier,
                                 model_risk_score, calibrated_probability,
                                 historical_realized_revenue_ntd, segment, key_risk_signal,
                                 recommended_action
    """
    if sort_by not in _SORTABLE_COLUMNS:
        return _err(f"sort_by must be one of {_SORTABLE_COLUMNS}, got {sort_by!r}")
    if limit <= 0:
        return _err("limit must be a positive integer")
    limit = min(limit, 200)

    risk_tiers = _as_list(risk_tier)
    if risk_tiers is not None:
        bad = [t for t in risk_tiers if t not in _RISK_TIERS]
        if bad:
            return _err(f"Unknown risk_tier value(s) {bad}; must be from {_RISK_TIERS}")
    value_tiers = _as_list(value_tier)
    if value_tiers is not None:
        bad = [t for t in value_tiers if t not in _VALUE_TIERS]
        if bad:
            return _err(f"Unknown value_tier value(s) {bad}; must be from {_VALUE_TIERS}")
    segments = _as_list(segment)
    if segments is not None:
        bad = [s for s in segments if s not in _KNOWN_SEGMENTS]
        if bad:
            return _err(f"Unknown segment value(s) {bad}; must be from the 7 validated segments")

    filtered = df
    if risk_tiers:
        filtered = filtered[filtered["risk_tier"].isin(risk_tiers)]
    if value_tiers:
        filtered = filtered[filtered["value_tier"].isin(value_tiers)]
    if segments:
        filtered = filtered[filtered["segment"].isin(segments)]
    if min_risk_score is not None:
        filtered = filtered[filtered["risk_score_full"] >= min_risk_score]
    if max_risk_score is not None:
        filtered = filtered[filtered["risk_score_full"] <= max_risk_score]
    if min_calibrated_probability is not None:
        filtered = filtered[filtered["calibrated_probability"] >= min_calibrated_probability]
    if max_calibrated_probability is not None:
        filtered = filtered[filtered["calibrated_probability"] <= max_calibrated_probability]
    if min_hrr_ntd is not None:
        filtered = filtered[filtered["total_revenue"] >= min_hrr_ntd]
    if max_hrr_ntd is not None:
        filtered = filtered[filtered["total_revenue"] <= max_hrr_ntd]
    if auto_renew is not None:
        filtered = filtered[filtered["latest_is_auto_renew"] == int(auto_renew)]

    total_matches = int(len(filtered))
    top = filtered.sort_values(sort_by, ascending=ascending).head(limit)

    rows = []
    for _, r in top.iterrows():
        rows.append({
            "msno": r["msno"],
            "risk_tier": r["risk_tier"],
            "value_tier": r["value_tier"],
            "model_risk_score": float(r["risk_score_full"]),
            "calibrated_probability": float(r["calibrated_probability"]) if pd.notna(r["calibrated_probability"]) else None,
            "historical_realized_revenue_ntd": float(r["total_revenue"]) if pd.notna(r["total_revenue"]) else None,
            "segment": r["segment"],
            "key_risk_signal": data.key_risk_signal(
                r["latest_is_auto_renew"] if pd.notna(r["latest_is_auto_renew"]) else None,
                r["days_since_last_txn"] if pd.notna(r["days_since_last_txn"]) else None,
                r["cancel_rate"] if pd.notna(r["cancel_rate"]) else None,
            ),
            "recommended_action": data.SHORT_ACTION_BY_SEGMENT.get(r["segment"], "Standard outreach"),
        })

    return _ok({"total_matches": total_matches, "rows": rows})


# ---------------------------------------------------------------------------
# 3. get_aggregate_metrics
# ---------------------------------------------------------------------------


def get_aggregate_metrics(
    risk_summary: dict,
    value_by_tier: pd.DataFrame,
    risk_value_matrix: pd.DataFrame,
    action_plan: pd.DataFrame,
    value_by_segment: pd.DataFrame,
) -> dict:
    """Answer business-level quantitative questions ("how many customers are at elevated risk",
    "churn rate", "HRR by segment", "high-risk/high-value population") without touching the
    971K-row customer table -- every one of these numbers already lives in a small, pre-aggregated
    output file.

    Source of truth (all unchanged, all already used elsewhere in the dashboard):
        outputs/risk_scoring_summary.json    -> data.load_risk_summary()
        outputs/value_by_risk_tier.csv       -> data.load_value_by_tier()   (+ data.total_realized_revenue)
        outputs/risk_value_matrix.csv        -> data.load_risk_value_matrix() (+ data.high_risk_historical_revenue_exposure)
        outputs/marketing_action_plan.csv    -> data.load_action_plan()
        outputs/value_by_segment.csv         -> data.load_value_by_segment()

    Returns a dict with:
        n_customers_scored, overall_churn_rate_pct
        risk_tiers: list of {tier, n_customers, pct_of_base, observed_churn_rate_pct}
        elevated_risk_customers   (Medium + High tier count -- "at elevated churn risk")
        high_risk_customers       (High tier count only)
        high_risk_high_value_customers  (the High-risk x High-value population specifically)
        total_realized_revenue_ntd
        high_risk_historical_revenue_exposure_ntd  (see module docstring: NOT an expected-loss figure)
        by_segment: list of {segment, n_customers, churn_rate_pct, total_hrr_ntd}
    """
    tiers = risk_summary["risk_tiers"]
    by_tier_name = {t["tier"]: t for t in tiers}
    elevated = sum(t["n_customers"] for t in tiers if t["tier"] in ("Medium", "High"))
    high_risk_high_value = int(risk_value_matrix.loc["High", "n_High"])

    by_segment = [
        {
            "segment": r["priority_group"],
            "n_customers": int(r["n_customers"]),
            "churn_rate_pct": float(r["churn_rate_pct"]),
            "total_hrr_ntd": float(r["total_HRR"]),
        }
        for _, r in action_plan.iterrows()
    ]

    return _ok({
        "n_customers_scored": int(risk_summary["n_customers_scored"]),
        "overall_churn_rate_pct": float(risk_summary["actual_churn_rate"] * 100),
        "risk_tiers": [
            {
                "tier": t["tier"],
                "n_customers": int(t["n_customers"]),
                "pct_of_base": float(t["pct_of_base"]),
                "observed_churn_rate_pct": float(t["observed_churn_rate_in_tier"]),
            }
            for t in tiers
        ],
        "elevated_risk_customers": int(elevated),
        "high_risk_customers": int(by_tier_name["High"]["n_customers"]),
        "high_risk_high_value_customers": high_risk_high_value,
        "total_realized_revenue_ntd": data.total_realized_revenue(value_by_tier),
        "high_risk_historical_revenue_exposure_ntd": data.high_risk_historical_revenue_exposure(risk_value_matrix),
        "by_segment": by_segment,
    })


# ---------------------------------------------------------------------------
# 4. get_segment
# ---------------------------------------------------------------------------


def get_segment(action_plan: pd.DataFrame, segment_summary: pd.DataFrame, segment_name: str) -> dict:
    """Return the definition and observed profile of one of the 7 already-validated segments.

    Source of truth: `lib.copilot_data.get_segment_context()` (unchanged, reused directly) --
    combines outputs/marketing_action_plan.csv (population, churn, HRR, recommended objective;
    present for all 7 segments) with outputs/segment_summary.csv (behavioral medians; present
    for 6 of 7 -- Stable / Monitor has no row there, and those specific fields come back as
    `None`, never guessed).

    Does not invent new segments: `segment_name` must be one of the 7 names in
    `copilot_data.SEGMENTS`.
    """
    if segment_name not in _KNOWN_SEGMENTS:
        return _err(f"Unknown segment {segment_name!r}; must be one of the 7 validated segments: {_KNOWN_SEGMENTS}")

    ctx = copilot_data.get_segment_context(action_plan, segment_summary, segment_name)
    if ctx is None:
        return _err(f"Segment {segment_name!r} not found in the action plan")
    return _ok(ctx)


# ---------------------------------------------------------------------------
# 5. explain_customer_risk
# ---------------------------------------------------------------------------


def explain_customer_risk(df: pd.DataFrame, shap_df: pd.DataFrame, customer_id: str, n_drivers: int = 5) -> dict:
    """Return the evidence explaining why a specific customer has elevated risk.

    Source of truth: `copilot_data.get_customer_context()` for the customer's own field values,
    and outputs/shap_feature_importance.csv (via `copilot_data.get_top_drivers()`) for the
    model's GLOBAL driver ranking (mean |SHAP| across the whole scored population -- this
    project does not store a per-customer SHAP breakdown, only the global ranking; that
    distinction is preserved here, never blurred into "this customer's personal SHAP values").

    CRITICAL -- association, not causation. This function returns evidence, never a causal
    claim:
        BAD  (never produced by this tool): "Customer will churn because auto-renew is off."
        GOOD (what this tool actually returns): "Auto-renew is off, which is one of the
             strongest model-associated risk signals for this customer."

    Returns a dict with:
        msno, risk_tier, model_risk_score, calibrated_probability, segment
        key_risk_signal            (data.key_risk_signal -- the single most notable deviation)
        top_global_drivers: list of {feature, display_name, mean_abs_shap} -- the model's
            overall top N drivers (NOT specific to this customer's individual contribution)
        customer_deviations: list of short strings describing where this customer's own values
            sit relative to the population baseline (auto-renew, recency, cancellation rate) --
            observed deviations, explicitly framed as associations
    """
    ctx = copilot_data.get_customer_context(df, customer_id)
    if ctx is None:
        return _err("Customer not found in the scored customer base")

    pop = copilot_data.get_population_baselines(df)
    top_drivers = copilot_data.get_top_drivers(shap_df, data.feature_display_name, n=n_drivers)

    deviations = []
    if ctx["latest_is_auto_renew"] == 0:
        deviations.append(
            f"Auto-renew is off, while {pop['auto_renew_pct'] * 100:.0f}% of the population has it on -- "
            "the model's strongest general driver, associated with elevated risk for this customer."
        )
    if ctx["days_since_last_txn"] is not None and ctx["days_since_last_txn"] > pop["days_since_last_txn_mean"] * 1.5:
        deviations.append(
            f"Last transaction was {ctx['days_since_last_txn']:.0f} days ago, well above the "
            f"{pop['days_since_last_txn_mean']:.0f}-day population average."
        )
    if ctx["cancel_rate"] is not None and ctx["cancel_rate"] > pop["cancel_rate_mean"] * 1.5:
        deviations.append(
            f"Cancellation rate ({ctx['cancel_rate'] * 100:.1f}%) is well above the "
            f"{pop['cancel_rate_mean'] * 100:.1f}% population average."
        )
    if not deviations:
        deviations.append(
            "No single behavioral flag stands out sharply from the population average -- the "
            "Model Risk Score reflects a combination of smaller signals, not one dominant factor."
        )

    return _ok({
        "msno": ctx["msno"],
        "risk_tier": ctx["risk_tier"],
        "model_risk_score": ctx["model_risk_score"],
        "calibrated_probability": ctx["calibrated_probability"],
        "segment": ctx["segment"],
        "key_risk_signal": data.key_risk_signal(ctx["latest_is_auto_renew"], ctx["days_since_last_txn"], ctx["cancel_rate"]),
        "top_global_drivers": top_drivers,
        "customer_deviations": deviations,
    })


# ---------------------------------------------------------------------------
# 6. recommend_action
# ---------------------------------------------------------------------------


def recommend_action(action_plan: pd.DataFrame, *, segment: str | None = None, customer: dict | None = None) -> dict:
    """Return the existing, evidence-backed retention recommendation for a customer or a segment.

    Pass exactly one of `segment` (a segment name) or `customer` (a `get_customer()`-shaped dict,
    or any dict with a "segment" key) -- the recommendation is always segment-level, since that is
    what the action framework defines; a customer argument is just a convenience to avoid the
    caller re-looking-up which segment the customer belongs to.

    Source of truth: outputs/marketing_action_plan.csv (`marketing_objective`,
    `intervention_intensity`, `rationale`) plus `data.SHORT_WHY_BY_SEGMENT` and
    `data.AVOID_BY_SEGMENT` -- both already-validated, plain-English restatements of that same
    file's `rule_definition` / `defining_characteristics` (see data.py's own docstrings), not new
    claims. Does not invent a marketing campaign and does not claim causal uplift -- `rationale`
    and the caution the caller renders alongside this (see `copilot_engine.STANDARD_CAUTION`)
    already state this is an observed association from historical data.
    """
    if (segment is None) == (customer is None):
        return _err("Pass exactly one of segment= or customer=")
    if customer is not None:
        segment = customer.get("segment")
    if segment not in _KNOWN_SEGMENTS:
        return _err(f"Unknown segment {segment!r}; must be one of the 7 validated segments: {_KNOWN_SEGMENTS}")

    rows = action_plan[action_plan["priority_group"] == segment]
    if rows.empty:
        return _err(f"Segment {segment!r} not found in the action plan")
    row = rows.iloc[0]

    return _ok({
        "segment": segment,
        "recommended_action": data.SHORT_ACTION_BY_SEGMENT.get(segment, "Standard outreach"),
        "objective": row["marketing_objective"],
        "intervention_intensity": row["intervention_intensity"],
        "rationale": row["rationale"],
        "why": data.SHORT_WHY_BY_SEGMENT.get(segment, "Elevated model risk for this segment."),
        "avoid": data.AVOID_BY_SEGMENT.get(segment, ""),
    })


# ---------------------------------------------------------------------------
# 7. compare_to_champions
# ---------------------------------------------------------------------------


def compare_to_champions(
    action_plan: pd.DataFrame,
    value_by_segment: pd.DataFrame,
    *,
    customer: dict | None = None,
    segment: str | None = None,
) -> dict:
    """Compare a customer or a segment against the existing Champions (Engaged Low-Risk) benchmark.

    Pass exactly one of `customer` (a `get_customer()`-shaped dict) or `segment` (a segment name).

    Source of truth: `copilot_data.get_champions_context()` (outputs/marketing_action_plan.csv +
    outputs/value_by_segment.csv, unchanged, reused directly). Only returns benchmark dimensions
    that actually exist in those files (churn rate, HRR) -- never fabricates a missing one.
    """
    if (segment is None) == (customer is None):
        return _err("Pass exactly one of segment= or customer=")

    champions = copilot_data.get_champions_context(action_plan, value_by_segment)

    if customer is not None:
        return _ok({
            "subject": "customer",
            "msno": customer.get("msno"),
            "champions_churn_rate_pct": champions["churn_rate_pct"],
            "champions_median_hrr_ntd": champions["median_hrr_ntd"],
            "subject_calibrated_probability": customer.get("calibrated_probability"),
            "subject_hrr_ntd": customer.get("historical_realized_revenue_ntd"),
        })

    if segment not in _KNOWN_SEGMENTS:
        return _err(f"Unknown segment {segment!r}; must be one of the 7 validated segments: {_KNOWN_SEGMENTS}")
    seg_row = action_plan[action_plan["priority_group"] == segment]
    if seg_row.empty:
        return _err(f"Segment {segment!r} not found in the action plan")
    seg_row = seg_row.iloc[0]

    return _ok({
        "subject": "segment",
        "segment": segment,
        "champions_churn_rate_pct": champions["churn_rate_pct"],
        "champions_median_hrr_ntd": champions["median_hrr_ntd"],
        "subject_churn_rate_pct": float(seg_row["churn_rate_pct"]),
        "subject_total_hrr_ntd": float(seg_row["total_HRR"]),
    })


# ---------------------------------------------------------------------------
# 8. rank_segments_by_priority
# ---------------------------------------------------------------------------


def rank_segments_by_priority(action_plan: pd.DataFrame, top_n: int | None = None) -> dict:
    """Rank the at-risk segments by the current analytical priority framework.

    Source of truth: `data.priority_opportunities()` (unchanged, reused directly) -- the exact
    same ranking Overview and Action Center already display (sorted by Historical Realized
    Revenue at stake, excluding Engaged Low-Risk (Champions) and Stable / Monitor, which are not
    retention targets). This function does not recompute or reorder anything itself; it only
    reshapes that existing ranking into tool-friendly rows.

    Returns a dict with `rows`: a list of, in priority order:
        {priority, segment, n_customers, churn_rate_pct, total_hrr_ntd,
         intervention_intensity, recommended_action}
    """
    ranked = data.priority_opportunities(action_plan, top_n=top_n)
    rows = [
        {
            "priority": i + 1,
            "segment": r["priority_group"],
            "n_customers": int(r["n_customers"]),
            "churn_rate_pct": float(r["churn_rate_pct"]),
            "total_hrr_ntd": float(r["total_HRR"]),
            "intervention_intensity": r["intervention_intensity"],
            "recommended_action": data.SHORT_ACTION_BY_SEGMENT.get(r["priority_group"], "Standard outreach"),
        }
        for i, (_, r) in enumerate(ranked.iterrows())
    ]
    return _ok({"rows": rows})


# ---------------------------------------------------------------------------
# 9. build_dashboard_deep_link
# ---------------------------------------------------------------------------

# The only pages a deep link may target -- matches app.py's st.Page registry exactly. Keeping
# this an explicit whitelist (rather than accepting an arbitrary path) is what makes this "safe
# internal navigation" rather than an open redirect into an arbitrary file path.
_DEEP_LINK_PAGES = {
    "overview": ("pages/overview.py", "Overview"),
    "priority_customers": ("pages/priority_customers.py", "Priority Customers"),
    "customer_value": ("pages/customer_value.py", "Customer Value"),
    "action_center": ("pages/action_center.py", "Action Center"),
    "customer_360": ("pages/customer_360.py", "Customer 360"),
    "retention_copilot": ("pages/retention_copilot.py", "Retention Intelligence"),
}


def build_dashboard_deep_link(target_page: str, *, customer_id: str | None = None, filters: dict | None = None) -> dict:
    """Build a safe, structured description of where to send the manager next in the dashboard,
    for the UI layer (not built in this task) to turn into an `st.page_link` CTA.

    This function does NOT touch Streamlit, does NOT render anything, and does NOT introduce any
    JavaScript routing -- it only validates `target_page` against the app's actual page registry
    (`_DEEP_LINK_PAGES`, mirroring `app.py`'s `st.Page` list exactly) and returns the plain-data
    payload a future page could use to pre-fill itself.

    `customer_id`, when given, is carried under the key `"cust360_search"` -- the EXACT session-
    state key `pages/customer_360.py` and `pages/retention_copilot.py` already read (proven
    working cross-page mechanism; this function does not invent a new one).

    `filters`, when given, is carried as-is under `"pending_filter"`. NOTE: as of this task, no
    page yet reads `st.session_state["pending_filter"]` -- Priority Customers' risk/value/segment
    widgets are still local/unkeyed (see AGENT_ARCHITECTURE_PLAN.md section H). Wiring a page to
    consume this payload is explicitly out of scope for this task; this function only produces
    the (validated, safe) data half of that future feature.
    """
    if target_page not in _DEEP_LINK_PAGES:
        return _err(f"Unknown target_page {target_page!r}; must be one of {sorted(_DEEP_LINK_PAGES)}")

    page_path, page_title = _DEEP_LINK_PAGES[target_page]
    session_state_updates = {}
    if customer_id:
        session_state_updates["cust360_search"] = customer_id
    if filters:
        session_state_updates["pending_filter"] = filters

    label = f"Open in {page_title} →"
    if customer_id:
        label = f"Open {customer_id[:24]}… in {page_title} →"

    return _ok({
        "page_path": page_path,
        "page_title": page_title,
        "label": label,
        "session_state_updates": session_state_updates,
    })
