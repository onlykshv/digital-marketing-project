"""Anthropic tool-use schemas for the 9 deterministic tools in `agent_tools.py`.

Every description below is written for the LLM, not for a human reader of this file -- it
exists to make tool selection unambiguous and to prevent the exact mistakes this project has
explicitly guarded against everywhere else: treating Model Risk Score as a probability, treating
Historical Realized Revenue as CLV, treating High-Risk Historical Revenue Exposure as an expected
loss figure, and inventing a customer or numeric value that didn't come back from a tool call.

These schemas describe the LLM-FACING tool surface, which is not always identical to
`agent_tools.py`'s raw Python signatures: any tool that operates on "a customer" takes a
`customer_id` string here (never a customer object) -- `agent.py`'s dispatcher resolves that ID
to a full record via `get_customer` internally before calling the underlying function. This means
the model can never construct or guess a customer's field values; it can only ever name a
customer by ID and receive back whatever the deterministic layer actually knows about them.

The `{"type": "object", "properties": {...}}` shape is plain JSON Schema, not an Anthropic-
specific format -- see `llm_provider.py`'s module docstring for why that keeps this file
provider-agnostic in spirit even though it's currently only wired to Anthropic's API.
"""
from __future__ import annotations

_SEGMENT_ENUM = [
    "At-Risk, Auto-Renew Off",
    "At-Risk Veteran",
    "At-Risk Newcomer",
    "At-Risk, Price-Sensitive",
    "Unmatched At-Risk (no segment)",
    "Engaged Low-Risk (Champions)",
    "Stable / Monitor",
]

_TERMINOLOGY_NOTE = (
    "Terminology reminder: 'model_risk_score' is the RAW model output and is NOT a calibrated "
    "probability -- never describe it as one. 'calibrated_probability' is the Estimated Churn "
    "Probability -- the only one of the two safe to call a probability. Any "
    "'historical_realized_revenue_ntd' / 'total_hrr_ntd' field is money already collected "
    "(Historical Realized Revenue, HRR) -- NEVER call it CLV, lifetime value, or a revenue "
    "forecast. Any 'high_risk_historical_revenue_exposure_ntd' field is a headcount exposure "
    "sum, NOT a probability-weighted expected loss."
)

TOOL_SCHEMAS = [
    {
        "name": "get_customer",
        "description": (
            "Retrieve the complete grounded profile for ONE customer by their exact customer ID "
            "(msno). Use this whenever the manager asks about a specific, named customer -- "
            "\"why is customer X at risk\", \"what should we do about X\", \"tell me about X\". "
            "Returns risk tier, Model Risk Score, Estimated Churn Probability (if available), "
            "Historical Realized Revenue (if available), segment, tenure, and behavioral facts. "
            "If the customer ID does not exist in the scored customer base, this tool returns "
            "ok=false with an explicit error -- you MUST tell the manager the customer was not "
            "found, never guess or invent a profile. Do NOT use this to search for customers "
            "matching criteria -- use search_customers for that. " + _TERMINOLOGY_NOTE
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The exact customer ID (msno) to look up. Must be an ID the manager gave you or that came back from a prior search_customers call -- never invent one.",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_customers",
        "description": (
            "Find customers matching filter criteria and return a ranked list. Use this for "
            "questions like \"top 20 high-risk customers\", \"high-risk high-value customers\", "
            "\"customers in the At-Risk Veteran segment\", \"customers with significant "
            "historical revenue who are at high risk\". Do NOT use this to look up one specific "
            "known customer by ID -- use get_customer for that. Results are capped at 200 rows "
            "and sorted by the field you choose (default: Model Risk Score, descending). "
            "'min_calibrated_probability'/'max_calibrated_probability' filter on Estimated Churn "
            "Probability (the calibrated figure); 'min_risk_score'/'max_risk_score' filter on the "
            "raw Model Risk Score -- these are NOT interchangeable, pick the one the manager "
            "actually means. If the filters match zero customers, that is a valid, real answer "
            "(e.g. Champions are never High risk by definition) -- report zero, do not invent "
            "results to fill the gap. " + _TERMINOLOGY_NOTE
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_tier": {
                    "type": "array", "items": {"type": "string", "enum": ["Low", "Medium", "High"]},
                    "description": "One or more risk tiers to include. Omit for all tiers.",
                },
                "value_tier": {
                    "type": "array", "items": {"type": "string", "enum": ["Low", "Medium", "High"]},
                    "description": "One or more value tiers (based on Historical Realized Revenue) to include. Omit for all tiers.",
                },
                "segment": {
                    "type": "array", "items": {"type": "string", "enum": _SEGMENT_ENUM},
                    "description": "One or more of the 7 validated segments to include. Omit for all segments.",
                },
                "min_risk_score": {"type": "number", "description": "Minimum raw Model Risk Score (0-1), inclusive. NOT a probability filter."},
                "max_risk_score": {"type": "number", "description": "Maximum raw Model Risk Score (0-1), inclusive."},
                "min_calibrated_probability": {"type": "number", "description": "Minimum Estimated Churn Probability (0-1), inclusive. This IS the calibrated probability filter."},
                "max_calibrated_probability": {"type": "number", "description": "Maximum Estimated Churn Probability (0-1), inclusive."},
                "min_hrr_ntd": {"type": "number", "description": "Minimum Historical Realized Revenue in NT$ (the source currency), inclusive."},
                "max_hrr_ntd": {"type": "number", "description": "Maximum Historical Realized Revenue in NT$, inclusive."},
                "auto_renew": {"type": "boolean", "description": "true = only customers with auto-renew currently on; false = only auto-renew off. Omit for both."},
                "sort_by": {
                    "type": "string", "enum": ["risk_score_full", "calibrated_probability", "total_revenue"],
                    "description": "Field to sort by: risk_score_full (Model Risk Score), calibrated_probability (Estimated Churn Probability), or total_revenue (HRR). Default risk_score_full.",
                },
                "ascending": {"type": "boolean", "description": "Sort ascending instead of descending. Default false (highest first)."},
                "limit": {"type": "integer", "description": "Maximum rows to return, 1-200. Default 20. Use a small number unless the manager asks for more."},
            },
            "required": [],
        },
    },
    {
        "name": "get_aggregate_metrics",
        "description": (
            "Get base-rate, business-level numbers about the WHOLE scored customer population: "
            "total customers scored, overall churn rate, counts by risk tier, the High-risk x "
            "High-value population size, total Historical Realized Revenue, High-Risk Historical "
            "Revenue Exposure, and Historical Realized Revenue by segment. Use this for questions "
            "like \"how many customers are at elevated risk\", \"what's the churn rate\", \"how "
            "much revenue is at high risk\". Takes no arguments -- it always returns the full "
            "current snapshot. Do NOT use this for a specific customer or a filtered customer "
            "list -- use get_customer or search_customers for those. " + _TERMINOLOGY_NOTE
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_segment",
        "description": (
            "Get the definition and observed profile of ONE of the 7 validated customer segments "
            "-- population, churn rate, Historical Realized Revenue, and behavioral medians where "
            "available. Use this for \"tell me about the At-Risk Veteran segment\" style "
            "questions. The segment name must be one of the 7 exact names in the enum -- there "
            "are no other segments and you must not invent one. Some behavioral fields (median "
            "tenure, median recency) are legitimately unavailable for the Stable / Monitor "
            "segment -- if a field comes back null, tell the manager it is not available, do not "
            "guess a number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_name": {"type": "string", "enum": _SEGMENT_ENUM, "description": "The exact segment name to look up."},
            },
            "required": ["segment_name"],
        },
    },
    {
        "name": "explain_customer_risk",
        "description": (
            "Get the evidence explaining why ONE specific customer has elevated risk: their key "
            "risk signal, the model's top global risk drivers (a population-wide ranking, NOT "
            "this customer's individual SHAP breakdown -- this project does not store per-"
            "customer SHAP values), and the specific ways this customer's own behavior deviates "
            "from the population average. Use this for \"why is customer X at risk\" / \"explain "
            "this customer's risk\" questions -- it is more detailed than get_customer's plain "
            "profile. CRITICAL: everything this tool returns is an ASSOCIATION, never a cause. "
            "When you use this tool's output, phrase it as 'Auto-renew is off, which is one of "
            "the strongest model-associated risk signals for this customer' -- never 'this "
            "customer will churn because auto-renew is off' or any other causal claim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The exact customer ID (msno) to explain."},
                "n_drivers": {"type": "integer", "description": "How many top global drivers to include. Default 5."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "recommend_action",
        "description": (
            "Get the existing, evidence-backed retention recommendation for a customer or a "
            "segment: the recommended action, the objective, the intervention intensity, why "
            "(the segment rationale), and what to avoid. Recommendations are always segment-"
            "level -- pass EITHER customer_id (to get that customer's segment's recommendation) "
            "OR segment (to get it directly), never both. This tool never invents a marketing "
            "campaign and never claims an intervention WILL work -- treat its output as a "
            "suggested/recommended/priority action, never a guarantee. Use 'recommended action' "
            "or 'suggested treatment' language, never 'this will reduce churn' or 'this will save "
            "revenue'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "A customer ID -- get the recommendation for their segment. Provide this OR segment, not both."},
                "segment": {"type": "string", "enum": _SEGMENT_ENUM, "description": "A segment name -- get the recommendation directly. Provide this OR customer_id, not both."},
            },
            "required": [],
        },
    },
    {
        "name": "compare_to_champions",
        "description": (
            "Compare a customer or a segment against the Engaged Low-Risk (Champions) benchmark "
            "-- the base's lowest-churn, highest-realized-revenue group. Use this for \"how does "
            "X compare to Champions\" / \"how does this segment compare to our best customers\" "
            "questions. Pass EITHER customer_id OR segment, not both. Only returns benchmark "
            "dimensions that actually exist (churn rate, Historical Realized Revenue) -- never "
            "fabricates a missing comparison point."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "A customer ID to compare. Provide this OR segment, not both."},
                "segment": {"type": "string", "enum": _SEGMENT_ENUM, "description": "A segment name to compare. Provide this OR customer_id, not both."},
            },
            "required": [],
        },
    },
    {
        "name": "rank_segments_by_priority",
        "description": (
            "Get the at-risk segments ranked by the current analytical priority framework "
            "(Historical Realized Revenue, money already collected) -- the same ranking used on the Overview and "
            "Action Center dashboard pages. Use this for \"which segment should we prioritize\" / "
            "\"which segments need attention\" questions. Excludes Engaged Low-Risk (Champions) "
            "and Stable / Monitor, since neither is a retention target. Does not recompute "
            "anything -- it only reshapes the existing, already-validated ranking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "Return only the top N segments. Omit for all ranked segments."},
            },
            "required": [],
        },
    },
    {
        "name": "build_dashboard_deep_link",
        "description": (
            "Build a safe link description for sending the manager to a specific dashboard page "
            "(e.g. to view a customer's full profile in Customer 360, or a filtered list in "
            "Priority Customers). Use this at the end of an answer when a dashboard page would "
            "let the manager see or act on something directly. This does not navigate anywhere "
            "itself and does not execute any code -- it only returns a validated page name and a "
            "label; the surrounding application decides whether and how to render it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_page": {
                    "type": "string",
                    "enum": ["overview", "priority_customers", "customer_value", "action_center", "customer_360", "retention_copilot"],
                    "description": "Which dashboard page to link to.",
                },
                "customer_id": {"type": "string", "description": "If linking to a specific customer's profile, their exact customer ID."},
            },
            "required": ["target_page"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOL_SCHEMAS]
