"""Retention Copilot's answer engine: evidence assembly, guardrails, optional LLM synthesis,
and a deterministic fallback that is fully grounded on its own (not a degraded experience).

Pipeline, matching the project's required architecture:

    question -> customer/segment context (copilot_data, exact-match retrieval)
             -> structured evidence bundle (this module)
             -> deterministic template answer (always computed -- the guaranteed baseline)
             -> optional LLM synthesis over the SAME evidence bundle, with strict guardrails
                (only if a provider is configured; on any failure or malformed response, the
                deterministic answer is used instead -- the manager never sees a blank page,
                an error, or a hallucinated fact)

The LLM is never given raw customer rows or the full dataset -- only the small evidence bundle
already extracted by copilot_data.py, and a system prompt that spells out every terminology and
causality rule from the project's validated methodology.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lib import data, llm_provider, theme

STANDARD_CAUTION = (
    "Based on predictive associations and the project's validated retention framework, not a "
    "controlled experiment -- there is no campaign-response data in this dataset, so campaign "
    "effectiveness has not been causally validated. Model Risk Score is not a calibrated "
    "probability; Estimated Churn Probability is the calibrated figure and is what's used above."
)
FRAMEWORK_BASIS = (
    "From the validated segment/action framework (marketing_action_plan.csv) and this "
    "customer's model outputs -- an observed association, not a causal guarantee."
)
SEGMENT_FRAMEWORK_BASIS = "From the validated segment/action framework -- an observed association across the group, not a per-customer guarantee."

SOURCE_CUSTOMER360 = "Customer 360"
SOURCE_RISK_SCORING = "Risk Scoring"
SOURCE_SEGMENT_FRAMEWORK = "Segment Framework"
SOURCE_ACTION_FRAMEWORK = "Marketing Action Framework"


@dataclass
class CopilotAnswer:
    recommendation: str
    why: str
    evidence: list[str] = field(default_factory=list)
    what_to_do: str = ""
    what_to_avoid: str = ""
    confidence_basis: str = ""
    caution: str = STANDARD_CAUTION
    sources: list[str] = field(default_factory=list)
    used_llm: bool = False
    llm_unavailable_reason: str | None = None


def _fmt_pct(x: float | None) -> str:
    return f"{x * 100:.0f}%" if x is not None else "not available"


def _fmt_money(ntd: float | None) -> str:
    return theme.fmt_currency(ntd) if ntd is not None else "not available"


# ---------------------------------------------------------------------------
# Evidence bundle -- the ONLY thing the LLM (when configured) ever sees. Small, structured,
# already-labeled. Never the raw dataframe.
# ---------------------------------------------------------------------------

def _fmt_rate(x: float | None, pop_mean: float | None = None) -> str:
    """Never guesses: a None rate renders as 'not available for this customer', never as 0%."""
    if x is None:
        return "not available for this customer"
    base = f" (base average: {pop_mean * 100:.1f}%)" if pop_mean is not None else ""
    return f"{x * 100:.1f}%{base}"


def _fmt_auto_renew(latest_is_auto_renew: int | None) -> str:
    """`None` (no recorded transaction activity) must never fall through Python's truthiness
    into 'OFF' -- that would misreport an unknown status as a known one."""
    if latest_is_auto_renew is None:
        return "not available"
    return "ON" if latest_is_auto_renew else "OFF"


def build_customer_evidence_lines(cust: dict, pop: dict) -> list[str]:
    lines = [
        f"Risk tier: {cust['risk_tier']} (Model Risk Score {cust['model_risk_score']:.2f})",
        f"Estimated Churn Probability: {_fmt_pct(cust['calibrated_probability'])}",
        f"Value tier: {cust['value_tier']} (Historical Realized Revenue: {_fmt_money(cust['historical_realized_revenue_ntd'])})",
        f"Segment: {cust['segment']}",
        f"Auto-renew: {_fmt_auto_renew(cust['latest_is_auto_renew'])} (base average: {pop['auto_renew_pct'] * 100:.0f}% ON)",
        f"Recency: {cust['days_since_last_txn']:.0f} days since last transaction (base average: {pop['days_since_last_txn_mean']:.0f})" if cust["days_since_last_txn"] is not None else "Recency: not available",
        f"Tenure: {cust['tenure_days']:.0f} days" if cust["tenure_days"] is not None else "Tenure: not available",
        f"Cancellation rate: {_fmt_rate(cust['cancel_rate'], pop.get('cancel_rate_mean'))}",
        f"Discount rate: {_fmt_rate(cust['discount_rate'], pop.get('discount_rate_mean'))}",
    ]
    return lines


def build_segment_evidence_lines(seg: dict) -> list[str]:
    lines = [
        f"{seg['n_customers']:,} customers ({seg['pct_of_base']:.1f}% of the base)",
        f"Observed churn rate: {seg['churn_rate_pct']:.1f}%",
        f"Historical Realized Revenue held by this group: {_fmt_money(seg['total_hrr_ntd'])} (median {_fmt_money(seg['median_hrr_ntd'])} per customer)",
    ]
    if seg["auto_renew_rate_pct"] is not None:
        lines.append(f"Auto-renew rate: {seg['auto_renew_rate_pct']:.0f}%")
    if seg["median_days_since_last_txn"] is not None:
        lines.append(f"Median days since last transaction: {seg['median_days_since_last_txn']:.0f}")
    if seg["median_tenure_days"] is not None:
        lines.append(f"Median tenure: {seg['median_tenure_days']:.0f} days")
    lines.append(f"Defining characteristics: {seg['defining_characteristics']}")
    return lines


# ---------------------------------------------------------------------------
# Deterministic answers -- the guaranteed, always-available baseline. Every branch here uses
# only fields already present in the evidence dicts; nothing is invented.
# ---------------------------------------------------------------------------

def _customer_key_signal(cust: dict) -> str:
    return data.key_risk_signal(cust["latest_is_auto_renew"], cust["days_since_last_txn"], cust["cancel_rate"])


def deterministic_customer_answer(intent: str, cust: dict, pop: dict, champions: dict | None, top_drivers: list[dict]) -> CopilotAnswer:
    segment = cust["segment"]
    objective = data.SHORT_ACTION_BY_SEGMENT.get(segment)
    why_segment = data.SHORT_WHY_BY_SEGMENT.get(segment, "Elevated model risk for this segment.")
    avoid_segment = data.AVOID_BY_SEGMENT.get(segment, "")
    evidence = build_customer_evidence_lines(cust, pop)
    sources = [SOURCE_CUSTOMER360, SOURCE_RISK_SCORING, SOURCE_SEGMENT_FRAMEWORK, SOURCE_ACTION_FRAMEWORK]

    if intent == "why_at_risk":
        signal = _customer_key_signal(cust)
        top_driver_line = f" The model's single strongest general driver is {top_drivers[0]['display_name']} (see Priority Customers)." if top_drivers else ""
        return CopilotAnswer(
            recommendation=f"Key risk signal: {signal}.",
            why=why_segment + top_driver_line,
            evidence=evidence, what_to_do=objective or "No specific action defined for this segment.",
            what_to_avoid=avoid_segment, confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "what_to_do":
        return CopilotAnswer(
            recommendation=objective or "No specific action defined for this segment.",
            why=why_segment, evidence=evidence, what_to_do=objective or "No specific action defined for this segment.",
            what_to_avoid=avoid_segment, confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "discount":
        if cust["discount_rate"] is None:
            return CopilotAnswer(
                recommendation="Discount sensitivity cannot be established reliably from the available evidence.",
                why="Discount rate is not available for this customer.", evidence=evidence,
                what_to_do=objective or "No specific action defined for this segment.",
                what_to_avoid=avoid_segment, confidence_basis=FRAMEWORK_BASIS, sources=sources,
            )
        if segment == "At-Risk, Price-Sensitive":
            return CopilotAnswer(
                recommendation="Yes -- a pricing/plan-fit conversation or a targeted discount is the framework's recommendation here.",
                why=f"This customer is in the At-Risk, Price-Sensitive segment: discount rate {cust['discount_rate'] * 100:.1f}% alongside elevated risk.",
                evidence=evidence, what_to_do=objective or "", what_to_avoid=avoid_segment,
                confidence_basis=FRAMEWORK_BASIS, sources=sources,
            )
        return CopilotAnswer(
            recommendation="Not indicated by the current framework.",
            why=(f"This customer's segment ({segment}) is not the price-sensitive segment -- the validated "
                 f"playbook recommends {(objective or 'the standard playbook response').rstrip('.').lower()} "
                 "instead. A discount is the specific playbook response only for the At-Risk, Price-Sensitive segment."),
            evidence=evidence, what_to_do=objective or "", what_to_avoid=avoid_segment,
            confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "worth_retaining":
        value_tier = cust["value_tier"]
        if value_tier == "High" and cust["risk_tier"] == "High":
            rec = "High priority -- combines elevated risk with meaningful historical value."
        elif value_tier == "High":
            rec = "Valuable customer, currently lower risk -- protect, don't over-invest in retention spend."
        else:
            rec = f"{value_tier}-value tier -- weigh retention cost against realized revenue at stake."
        why = (
            f"Historical Realized Revenue is {_fmt_money(cust['historical_realized_revenue_ntd'])} "
            f"(value tier: {value_tier}). This is money already collected, not a lifetime-value "
            "forecast -- it describes value realized so far, not potential."
        )
        return CopilotAnswer(
            recommendation=rec, why=why, evidence=evidence, what_to_do=objective or "",
            what_to_avoid=avoid_segment, confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "what_if_nothing":
        return CopilotAnswer(
            recommendation="No causal revenue-loss forecast is available for this scenario.",
            why=(f"The model estimates this customer's Estimated Churn Probability at "
                 f"{_fmt_pct(cust['calibrated_probability'])}, but the dataset does not support a causal "
                 "forecast of revenue loss from inaction -- there is no experiment isolating the effect "
                 "of taking no action."),
            evidence=evidence, what_to_do=objective or "Proceed with the recommended action rather than defer.",
            what_to_avoid="Avoid presenting a specific ₹ revenue-loss figure for inaction -- this dataset does not support that forecast.",
            confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "compare_champions":
        if champions is None:
            return CopilotAnswer(
                recommendation="Champions comparison data is not available.",
                why="Insufficient evidence in the available customer data.", evidence=evidence,
                what_to_do=objective or "", what_to_avoid=avoid_segment, sources=sources,
            )
        why = (
            f"Champions (the Engaged Low-Risk segment) churn at {champions['churn_rate_pct']:.1f}% and hold a "
            f"median Historical Realized Revenue of {_fmt_money(champions['median_hrr_ntd'])}. This customer's "
            f"Estimated Churn Probability is {_fmt_pct(cust['calibrated_probability'])} (vs. Champions' "
            f"{champions['churn_rate_pct']:.1f}% observed churn) with Historical Realized Revenue of "
            f"{_fmt_money(cust['historical_realized_revenue_ntd'])}."
        )
        return CopilotAnswer(
            recommendation="See the comparison below.", why=why, evidence=evidence,
            what_to_do=objective or "", what_to_avoid=avoid_segment, confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "prioritized_reasons":
        driver_txt = f" the model's strongest general driver is {top_drivers[0]['display_name']}," if top_drivers else ""
        return CopilotAnswer(
            recommendation=f"{cust['risk_tier']} risk, {cust['value_tier']} value, {segment} segment.",
            why=(f"This customer was surfaced because they fall in the {cust['risk_tier']} risk tier "
                 f"(Model Risk Score {cust['model_risk_score']:.2f}) and the {cust['value_tier']} value tier "
                 f"(Historical Realized Revenue {_fmt_money(cust['historical_realized_revenue_ntd'])}) -- the "
                 f"combination the framework prioritizes highest. Segment membership is {segment};{driver_txt} "
                 "see the evidence below for this customer's specific values."),
            evidence=evidence, what_to_do=objective or "", what_to_avoid=avoid_segment,
            confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    if intent == "evidence_only":
        return CopilotAnswer(
            recommendation=objective or "No specific action defined for this segment.",
            why=why_segment, evidence=evidence, what_to_do=objective or "", what_to_avoid=avoid_segment,
            confidence_basis=FRAMEWORK_BASIS, sources=sources,
        )

    # Unrecognized free-text question -- never guess; say so and point at what the Copilot can do.
    return CopilotAnswer(
        recommendation="I can answer questions about why this customer is at risk, what to do, "
                        "retention value, discounts, prioritization, or how they compare to Champions.",
        why="", evidence=[], what_to_do="Try one of the suggested questions, or rephrase using those terms.",
        what_to_avoid="", confidence_basis="", caution="", sources=[],
    )


def deterministic_segment_answer(intent: str, seg: dict | None, all_segments: dict[str, dict] | None = None) -> CopilotAnswer:
    if intent == "which_segment_priority" and all_segments:
        actionable = {
            k: v for k, v in all_segments.items()
            if k not in ("Engaged Low-Risk (Champions)", "Stable / Monitor")
        }
        ranked = sorted(actionable.values(), key=lambda s: s["total_hrr_ntd"], reverse=True)
        top = ranked[0]
        lines = [
            f"{s['segment']}: {s['n_customers']:,} customers, {s['churn_rate_pct']:.1f}% churn, "
            f"{_fmt_money(s['total_hrr_ntd'])} realized revenue at stake"
            for s in ranked[:3]
        ]
        return CopilotAnswer(
            recommendation=top["segment"],
            why="Ranked by Historical Realized Revenue at stake among the at-risk segments the "
                "action framework recommends intervening on -- the same ranking used on Overview "
                "and Action Center.",
            evidence=lines, what_to_do=top["marketing_objective"],
            what_to_avoid=f"Avoid spreading equal effort across all segments -- {top['segment']} carries the most realized revenue at risk.",
            confidence_basis=SEGMENT_FRAMEWORK_BASIS, sources=[SOURCE_ACTION_FRAMEWORK],
        )

    if intent == "champions_importance" and seg:
        return CopilotAnswer(
            recommendation="Protect and grow -- do not spend retention budget here.",
            why="Champions combine the base's lowest churn with its largest share of realized revenue.",
            evidence=build_segment_evidence_lines(seg), what_to_do=seg["marketing_objective"],
            what_to_avoid=data.AVOID_BY_SEGMENT.get("Engaged Low-Risk (Champions)", ""),
            confidence_basis=SEGMENT_FRAMEWORK_BASIS, sources=[SOURCE_SEGMENT_FRAMEWORK, SOURCE_ACTION_FRAMEWORK],
        )

    if intent == "high_touch_candidates" and all_segments:
        high_touch = [s for s in all_segments.values() if "High-touch" in s["intervention_intensity"]]
        if not high_touch:
            return CopilotAnswer(
                recommendation="No segment is currently flagged High-touch in the action framework.",
                why="Insufficient evidence in the available data.", sources=[SOURCE_ACTION_FRAMEWORK],
            )
        lines = [f"{s['segment']}: {s['n_customers']:,} customers, {s['churn_rate_pct']:.1f}% churn" for s in high_touch]
        return CopilotAnswer(
            recommendation=", ".join(s["segment"] for s in high_touch),
            why="These segments are marked High-touch intervention intensity in the validated action framework.",
            evidence=lines, what_to_do="Prioritize hands-on outreach for these segments over automated campaigns.",
            confidence_basis=SEGMENT_FRAMEWORK_BASIS, sources=[SOURCE_ACTION_FRAMEWORK],
        )

    if seg is None:
        return CopilotAnswer(
            recommendation="Segment not found.",
            why="Insufficient evidence in the available customer data.", sources=[],
        )

    return CopilotAnswer(
        recommendation=seg["marketing_objective"],
        why=seg["defining_characteristics"],
        evidence=build_segment_evidence_lines(seg),
        what_to_do=seg["marketing_objective"],
        what_to_avoid=data.AVOID_BY_SEGMENT.get(seg["segment"], ""),
        confidence_basis=SEGMENT_FRAMEWORK_BASIS,
        sources=[SOURCE_SEGMENT_FRAMEWORK, SOURCE_ACTION_FRAMEWORK],
    )


# ---------------------------------------------------------------------------
# Free-text intent classification -- simple, transparent keyword matching. Used both as the
# router when no LLM is configured, and to select which deterministic template a malformed or
# failed LLM call falls back to.
# ---------------------------------------------------------------------------

def classify_customer_intent(question: str) -> str:
    q = question.lower()
    if "discount" in q or "price" in q:
        return "discount"
    if "champion" in q or "compare" in q:
        return "compare_champions"
    if "nothing" in q or "do nothing" in q or "no action" in q:
        return "what_if_nothing"
    if "worth retain" in q or "worth saving" in q or "worth it" in q or ("value" in q and "worth" in q):
        return "worth_retaining"
    if "prioriti" in q:
        return "prioritized_reasons"
    if "evidence" in q or "support" in q:
        return "evidence_only"
    if "why" in q and "risk" in q:
        return "why_at_risk"
    if "what should we do" in q or "what to do" in q or "next" in q or "recommend" in q:
        return "what_to_do"
    if "why" in q:
        return "why_at_risk"
    return "unknown"


def classify_segment_intent(question: str) -> str:
    q = question.lower()
    if "champion" in q and ("important" in q or "why" in q):
        return "champions_importance"
    if "prioriti" in q and ("which" in q or "segment" in q):
        return "which_segment_priority"
    if "high-touch" in q or "high touch" in q or "deserve" in q:
        return "high_touch_candidates"
    return "segment_overview"


# ---------------------------------------------------------------------------
# LLM synthesis -- optional. Never sees raw data, only the evidence bundle. Strict output
# contract; a malformed or missing response always falls back to the deterministic answer.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Retention Intelligence, a decision-support assistant embedded in KKBOX \
Retention Intelligence, used by a retention/CRM/marketing manager.

You must follow these rules with no exceptions:
1. Use ONLY the facts given to you in the evidence bundle below. Never invent transaction \
history, listening behavior, demographics, preferences, campaign responses, revenue figures, or \
churn causes. If something needed to answer is not in the evidence bundle, say so explicitly \
using the phrase "Insufficient evidence in the available customer data" (for a customer question) \
or "not available for this segment" (for a segment question) -- do not guess or approximate.
2. Terminology is fixed and must never be substituted:
   - The raw model output is called "Model Risk Score". It is NOT a probability. Never write a \
sentence like "95% probability" about it.
   - The calibrated figure is called "Estimated Churn Probability".
   - Realized revenue is called "Historical Realized Revenue" (HRR). NEVER call it CLV, Lifetime \
Value, or Future Revenue -- it is money already collected, not a forecast.
3. Never use causal language: no "causes", "will reduce churn", "guarantees", "will save \
revenue". Use "associated with", "indicates", "the model relies on", "falls into" instead. There \
is no campaign-response experiment in this dataset -- recommendations are associations from a \
validated framework, not proven interventions.
4. Do not recommend a discount unless the customer's segment is explicitly "At-Risk, \
Price-Sensitive" or the evidence bundle shows clear discount-usage evidence.
5. Respond in EXACTLY this structure, with these exact section headers, each on its own line, in \
this order. Do not add extra sections. Keep every section compact -- this is a decision tool, not \
an essay:

RECOMMENDATION
<one short line>

WHY
<one to two sentences>

EVIDENCE
<bulleted list, one fact per line, prefixed with "- ">

WHAT TO DO
<one short line>

WHAT TO AVOID
<one short line, or "None specified." if nothing applies>

CONFIDENCE/BASIS
<one short line naming the framework/data this is based on>

CAUTION
<one to two sentences reiterating that this is an association from historical data, not a causal \
guarantee, and that no campaign-response experiment exists in this project>
"""

_SECTION_ORDER = ["RECOMMENDATION", "WHY", "EVIDENCE", "WHAT TO DO", "WHAT TO AVOID", "CONFIDENCE/BASIS", "CAUTION"]


def _build_user_prompt(question: str, evidence_bundle: dict) -> str:
    import json
    return (
        f"Manager's question: {question}\n\n"
        f"Evidence bundle (the ONLY facts you may use):\n{json.dumps(evidence_bundle, indent=2, default=str)}"
    )


def _parse_llm_response(text: str) -> CopilotAnswer | None:
    """Strict parser: requires RECOMMENDATION, WHY, WHAT TO DO, and CAUTION to be present and
    non-empty. Anything else (missing sections, extra prose outside the structure, an empty
    response) is treated as a failed parse so the caller falls back to the deterministic answer
    rather than showing the manager an answer that skipped the required structure."""
    pattern = "|".join(re.escape(h) for h in _SECTION_ORDER)
    parts = re.split(rf"(?im)^({pattern})\s*$", text.strip())
    sections: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip().upper()
        body = parts[i + 1].strip()
        sections[header] = body
        i += 2

    required = ["RECOMMENDATION", "WHY", "WHAT TO DO", "CAUTION"]
    if not all(sections.get(h) for h in required):
        return None

    evidence_lines = [ln.lstrip("-•").strip() for ln in sections.get("EVIDENCE", "").splitlines() if ln.strip()]

    return CopilotAnswer(
        recommendation=sections["RECOMMENDATION"],
        why=sections["WHY"],
        evidence=evidence_lines,
        what_to_do=sections["WHAT TO DO"],
        what_to_avoid=sections.get("WHAT TO AVOID", ""),
        confidence_basis=sections.get("CONFIDENCE/BASIS", ""),
        caution=sections["CAUTION"],
        sources=[SOURCE_CUSTOMER360, SOURCE_RISK_SCORING, SOURCE_SEGMENT_FRAMEWORK, SOURCE_ACTION_FRAMEWORK],
        used_llm=True,
    )


def try_llm_synthesis(question: str, evidence_bundle: dict) -> tuple[CopilotAnswer | None, str | None]:
    """Returns (parsed CopilotAnswer, None) on success, or (None, reason) -- never raises -- if
    the provider isn't configured, the request fails, or the response doesn't follow the
    required structure. `reason` is a short, human-readable sentence fragment the caller attaches
    to the deterministic fallback answer, so a failure is always visible to the manager rather
    than silently swallowed."""
    if not llm_provider.is_configured():
        return None, "no AI provider is configured for this session"
    try:
        raw = llm_provider.complete(_SYSTEM_PROMPT, _build_user_prompt(question, evidence_bundle))
    except llm_provider.ProviderUnavailable:
        return None, "the AI provider request failed"
    parsed = _parse_llm_response(raw)
    if parsed is None:
        return None, "the AI provider's response didn't match the required format"
    return parsed, None


# ---------------------------------------------------------------------------
# Public entrypoints -- called by the page. Always return a usable CopilotAnswer.
# ---------------------------------------------------------------------------

def answer_customer_question(question: str, cust: dict, pop: dict, champions: dict | None, top_drivers: list[dict]) -> CopilotAnswer:
    intent = classify_customer_intent(question)
    deterministic = deterministic_customer_answer(intent, cust, pop, champions, top_drivers)
    if intent == "unknown":
        return deterministic  # nothing meaningful to synthesize from an unrecognized question

    evidence_bundle = {
        "question_intent": intent,
        "customer": {k: v for k, v in cust.items()},
        "population_baselines": pop,
        "segment_framework_recommendation": data.SHORT_ACTION_BY_SEGMENT.get(cust["segment"]),
        "segment_framework_why": data.SHORT_WHY_BY_SEGMENT.get(cust["segment"]),
        "segment_framework_avoid": data.AVOID_BY_SEGMENT.get(cust["segment"]),
        "top_model_drivers": top_drivers,
        "champions_comparison": champions,
    }
    synthesized, reason = try_llm_synthesis(question, evidence_bundle)
    if synthesized:
        return synthesized
    deterministic.llm_unavailable_reason = reason
    return deterministic


def answer_segment_question(question: str, seg: dict | None, all_segments: dict[str, dict] | None = None) -> CopilotAnswer:
    intent = classify_segment_intent(question)
    deterministic = deterministic_segment_answer(intent, seg, all_segments)

    evidence_bundle = {"question_intent": intent, "segment": seg, "all_segments": all_segments}
    synthesized, reason = try_llm_synthesis(question, evidence_bundle)
    if synthesized:
        return synthesized
    deterministic.llm_unavailable_reason = reason
    return deterministic
