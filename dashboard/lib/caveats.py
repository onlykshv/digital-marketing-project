"""Reusable, data-grounded caveat panels.

Every number quoted inside these panels is read from the same outputs/*.json files the rest of
the dashboard uses -- nothing here is a new claim, it's a restatement of what notebooks 05, 06,
08, and 09 already established (and, per that work, explicitly did NOT establish -- e.g. no
campaign-response data exists anywhere in this project).
"""
from __future__ import annotations

import streamlit as st

from lib import theme


def _calibration_body(risk_summary: dict | None) -> str:
    if risk_summary:
        brier = risk_summary.get("brier_score_full")
        brier_txt = f" (Brier score: {brier:.3f} on this dataset)" if brier is not None else ""
    else:
        brier_txt = ""
    return (
        "**Model Risk Score** ranks customers well but is not a literal probability" + brier_txt + ". "
        "A score of 0.90 does not mean a 90% chance of churning -- the raw score is systematically "
        "inflated by the class-imbalance correction used during model training. Safe to use for "
        "**ranking and tiering** (as this dashboard does); not safe to plug directly into "
        "`expected revenue lost = score x revenue`. A calibrated version (`calibrated_probability`, "
        "in `outputs/calibrated_probabilities.csv`) now exists from a separate calibration step, but "
        "no calculation on this dashboard uses it yet -- if one does in the future, it will be "
        "labeled **Estimated Churn Probability**, never Model Risk Score."
    )


def _temporal_body(temporal_results: dict | None) -> str:
    if temporal_results:
        rs = temporal_results["random_split_metrics_for_reference"]["full_feature_set"]
        tp = temporal_results["temporal_metrics"]["full_feature_set"]
        detail = (
            f" On a genuinely future test period, ROC-AUC fell from {rs['roc_auc']:.3f} to "
            f"{tp['roc_auc']:.3f} and PR-AUC from {rs['pr_auc']:.3f} to {tp['pr_auc']:.3f}."
        )
    else:
        detail = ""
    return (
        "This model was validated on a genuinely future period -- trained on January-cutoff data, "
        "tested against actual March outcomes a month later -- and accuracy measurably dropped "
        "versus a same-period random split." + detail + " The numbers on this dashboard reflect "
        "that realistic forward-looking test, not an optimistic same-period estimate."
    )


def _hrr_body(value_analysis: dict | None) -> str:
    return (
        "**\"Value\" here means Historical Realized Revenue (HRR)** -- money already collected "
        "from a customer, not a lifetime value forecast. There is no projection of future spend, "
        "no survival/retention modeling, and no discounting of future cash flows. A brand-new "
        "customer will always show low HRR regardless of how valuable they may become -- HRR "
        "describes value realized *so far*, not potential.\n\n"
        "**Figures are displayed in ₹ (INR)** for readability, converted from the source data's "
        "native NT$ (New Taiwan Dollar) at a fixed rate of 1 NT$ = ₹2.62. This is a constant "
        "display-only conversion, not a live exchange rate -- every underlying file, model, and "
        "calculation remains in NT$."
    )


def _revenue_exposure_body() -> str:
    return (
        "**\"High-Risk Historical Revenue Exposure\" is a headcount sum, not a probability-weighted "
        "estimate.** It equals the full Historical Realized Revenue (HRR) already collected from "
        "every customer whose **Model Risk Score** crossed the High-risk threshold (&ge;0.95) -- "
        "each customer's revenue counts at 100% weight, regardless of where their individual score "
        "sits within that tier. Model Risk Score comes directly from XGBoost's `predict_proba` and "
        "is **not calibrated**: `scale_pos_weight` (used to handle class imbalance during training) "
        "systematically inflates it, so `P(churn) x revenue` is not a valid calculation on top of it "
        "(see `06_risk_scoring.ipynb`, §7, for the calibration audit this restates). A calibrated "
        "**Estimated Churn Probability** now exists as a separate output "
        "(`outputs/calibrated_probabilities.csv`) but is not used in this specific calculation -- "
        "until it is, this metric is deliberately named and computed as an exposure total, not an "
        "expected loss."
    )


def _thresholds_body() -> str:
    return (
        "**0.65 and 0.95 are a heuristic, not a statistically optimal cutoff.** High = the lowest "
        "score where precision first reaches 55% on the validation sweep; Medium = the F1-maximizing "
        "score. Both are chosen targets, not derived from a cost model -- this project has no "
        "campaign-response data to price a missed churner against a wasted retention touch. A "
        "sensitivity check (`11_threshold_rationale.ipynb`) found the High cutoff is robust to the "
        "exact precision target above ~50% (precision jumps sharply between 0.90 and 0.95, so most "
        "reasonable targets land on 0.95 anyway), while the Medium cutoff sits inside a band "
        "(0.55-0.85) where F1 barely moves (<1%) even though precision and recall individually trade "
        "off substantially -- the real choice there is a business preference, not a sharp optimum. "
        "**Both thresholds are specific to the raw Model Risk Score and do not transfer to "
        "calibrated_probability** -- applying them directly to the calibrated scale would flag only "
        "2.9% and 0.3% of customers (vs. 13.4% and 2.3% today), because the calibrated scale is "
        "honest about how rare a genuinely high churn probability is. The tiers remain valid for "
        "their actual purpose (ranking/prioritization: mean calibrated probability still rises "
        "sharply Low&rarr;Medium&rarr;High), just not as literal calibrated cutoffs. No threshold "
        "was changed by this analysis."
    )


def _causal_body() -> str:
    return (
        "Segments, drivers, and recommended actions on this dashboard are based on **observed "
        "statistical associations** in historical data (correlation, SHAP importance) -- not a "
        "controlled experiment. **No campaign-response data exists in this project.** A pattern "
        "like \"auto-renew off correlates with higher churn\" is a strong association, not proof "
        "that changing the setting alone causes retention. Treat these as prioritization guidance, "
        "not guaranteed outcomes."
    )


def _reusability_body() -> str:
    # P1-14: every fact stated here is source-verified (not inferred) -- see this ticket's
    # validation report for the exact grep/inspection each line is based on. The concluding claim
    # is deliberately the precise, non-rounded-up version: schema-portable architecture, KKBox-
    # specific data pipeline, never "this is a reusable platform" without that qualification.
    return (
        "**KKBox is this project's validation use case, not a hardcoded destination.** The "
        "underlying data is KKBox's own real, anonymized subscriber data, released for the WSDM "
        "2018 Cup Challenge -- a genuine production dataset, not synthetic.\n\n"
        "**What is KKBox-specific:** the feature-engineering pipeline (`src/`) reads KKBox's exact "
        "Kaggle-schema columns (`msno`, `is_cancel`, `payment_method_id`, `membership_expire_date`, "
        "etc.) and is not reusable as-is -- onboarding a different subscription business would "
        "require rebuilding that pipeline against that business's own schema, a real, non-trivial "
        "effort. A handful of literal strings in this dashboard (page title, hero text, a CSS brand "
        "mark, the AI assistant's system-prompt opening line) also name KKBox directly -- these are "
        "cosmetic, not structural.\n\n"
        "**What is reusable:** everything above the pipeline's output -- the deterministic tool "
        "layer, the AI orchestrator, and every dashboard page -- operates only on the generic "
        "*shape* of the scoring outputs (a customer ID, a risk score, a calibrated probability, a "
        "value tier, a segment label, a realized-revenue figure), not on any KKBox-only business "
        "rule. The four-term terminology discipline (Model Risk Score / Estimated Churn Probability "
        "/ HRR / High-Risk Historical Revenue Exposure) is itself domain-general and would apply "
        "unchanged to any subscription-churn business, only the underlying numbers would differ.\n\n"
        "**The precise, non-overclaimed statement:** the retention-intelligence layer above the "
        "data -- scoring outputs &rarr; tools &rarr; agent &rarr; UI -- is designed narrowly enough "
        "to be schema-portable. The path from a different business's raw transactional data to that "
        "same shape is not built today and would need to be rebuilt per business. This has **not** "
        "been validated on any dataset other than KKBox's -- that broader claim is not made here."
    )


CAVEAT_DEFS = {
    "calibration": ("Model Risk Score isn't a literal probability", _calibration_body),
    "temporal": ("Performance is measured on genuinely future data", _temporal_body),
    "hrr": ("\"Value\" is realized revenue, not lifetime value (CLV)", _hrr_body),
    "revenue_exposure": ("\"Revenue Exposure\" is a headcount sum, not an expected loss", _revenue_exposure_body),
    "thresholds": ("Why 0.65 and 0.95 -- and their limits", _thresholds_body),
    "causal": ("Associations, not proven causes", _causal_body),
    "reusability": ("Why KKBox, and what would carry over to another business", _reusability_body),
}


def render_caveats(
    keys: list[str],
    *,
    risk_summary: dict | None = None,
    temporal_results: dict | None = None,
    value_analysis: dict | None = None,
    expanded: bool = False,
) -> None:
    with st.expander("Methodology & limitations", expanded=expanded):
        for i, key in enumerate(keys):
            title, body_fn = CAVEAT_DEFS[key]
            st.markdown(f"**{title}**")
            if key == "calibration":
                st.markdown(body_fn(risk_summary))
            elif key == "temporal":
                st.markdown(body_fn(temporal_results))
            elif key == "hrr":
                st.markdown(body_fn(value_analysis))
            else:
                st.markdown(body_fn())
            if i < len(keys) - 1:
                st.markdown("---")
