import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import caveats, components, data, theme

theme.apply_page_style()

risk_summary = data.safe_load(data.load_risk_summary)
action_plan = data.safe_load(data.load_action_plan)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)
temporal_results = data.safe_load(data.load_temporal_results)

tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
thresholds = risk_summary["recommended_thresholds"]
intervention_needed = data.customers_requiring_intervention(action_plan)
opportunities = data.priority_opportunities(action_plan, top_n=1)
top_opportunity = opportunities.iloc[0]

n_scored = risk_summary["n_customers_scored"]
n_high = tiers_by_name["High"]["n_customers"]
hh = risk_value_matrix.loc["High"]
n_zone = int(hh["n_High"])
zone_churn = float(hh["churn_rate_pct_High"])
zone_avg_hrr = float(hh["avg_hrr_High"])
base_churn_pct = risk_summary["actual_churn_rate"] * 100

with st.container(key="ov_head"):  # scopes the Overview's more compact header (theme._COMPONENT_CSS)
    theme.masthead(
        "pages/overview.py", "Retention overview", "Where should KKBOX act?",
        f"{theme.fmt_count(n_scored)} KKBOX subscribers, scored for how likely they are to leave.",
    )


def _share_txt(share: float) -> str:
    return f"{share:.0f}%" if share >= 99.5 else (f"{share:.1f}%" if share >= 1 else f"{share:.2f}%")


# ---------------------------------------------------------------------------
# The three numbers the whole product rests on, read left to right: everyone -> those showing risk
# signals -> the few to save first. The stat cards double as the attention funnel: each carries a
# bar drawn to its linear share of the scored base (no scale distortion), and each stage is a
# genuine subset of the one before it -- so the numbers are shown once, not in a card and again in
# a funnel.
# ---------------------------------------------------------------------------
stages = [
    {"n": n_scored, "label": "Customers analyzed", "color": theme.COLORS["neutral"],
     "note": f"{base_churn_pct:.1f}% churn rate across the base"},
    {"n": intervention_needed, "label": "Showing risk signals", "color": theme.COLORS["medium"],
     "note": f"{theme.fmt_count(n_high)} of them at the highest risk"},
    {"n": n_zone, "label": "Save first", "color": theme.COLORS["high"],
     "note": "High risk and high value"},
]
cards = []
for s in stages:
    share = s["n"] / n_scored * 100
    cards.append(
        f'<div class="ri-kpi" data-n="{s["n"]}" data-share="{share:.4f}">'
        f'<span class="ri-kpi-dot" style="background:{s["color"]};"></span>'
        f'<div class="ri-kpi-label">{s["label"]}</div>'
        f'<div class="ri-kpi-value">{theme.fmt_count(s["n"])}</div>'
        f'<div class="ri-kpi-note">{s["note"]}</div>'
        f'<div class="share"><div class="bar"><i style="width:{share:.4f}%; background:{s["color"]};"></i></div>'
        f'<span>{_share_txt(share)} of customers</span></div></div>'
    )
st.markdown(f'<div class="ri-funnel">{"<b class=step>&rsaquo;</b>".join(cards)}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Start here -- the single biggest actionable play, and the page's one primary action: open that
# group in Priority Customers (P1-08: the page's portfolio signal carries into the work queue as a
# starting filter). The assistant (P1-13: Retention Intelligence reachable from the first screen, on
# the very segment this panel names) stays one quiet link below it.
# ---------------------------------------------------------------------------
with st.container(key="rp_start"):
    theme.panel_head("Start here", dot=theme.COLORS["cyan"], right="largest at-risk group")
    rec_col, cta_col = st.columns([1.7, 1], gap="large", vertical_alignment="center")
    with rec_col:
        components.recommendation_block(
            eyebrow="Biggest opportunity",
            title=top_opportunity["priority_group"],
            stat_html=(
                f"<b>{theme.fmt_count(top_opportunity['n_customers'])}</b> customers &middot; "
                f"<b style='color:{theme.COLORS['high_text']};'>{top_opportunity['churn_rate_pct']:.1f}%</b> churn &middot; "
                f"<b>{theme.fmt_currency(top_opportunity['total_HRR'])}</b> revenue to date"
            ),
            objective=top_opportunity["marketing_objective"],
            intensity=top_opportunity["intervention_intensity"],
            rationale=top_opportunity["rationale"],
        )
    with cta_col:
        if st.button(
            f"View {top_opportunity['priority_group']} customers in Priority Customers →",
            key="view_priority_customers_overview", type="primary", width="stretch",
        ):
            st.session_state["pending_filter"] = {"segment": [top_opportunity["priority_group"]]}
            st.switch_page("pages/priority_customers.py")
        if st.button(
            f"Ask Retention Intelligence: why does {top_opportunity['priority_group']} need attention? →",
            key="hero_ask_ri", type="tertiary",
        ):
            st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]
            st.session_state["cust360_search"] = ""  # a segment question must not land on an earlier customer
            st.switch_page("pages/retention_copilot.py")

# ---------------------------------------------------------------------------
# Secondary detail, collapsed: how the groups are defined, and the high-risk + high-value zone --
# with its own (secondary) drill-down, so it no longer competes with the primary action above.
# ---------------------------------------------------------------------------
with st.expander("How these groups are defined"):
    st.markdown(
        f"Every customer gets a **Model Risk Score** from the churn model. **Showing risk signals** "
        f"means a score of {thresholds['medium_risk_threshold']:.2f} or more (the Medium and High "
        f"tiers); **highest risk** means {thresholds['high_risk_threshold']:.2f} or more, where "
        f"{tiers_by_name['High']['observed_churn_rate_in_tier']:.1f}% actually churned. **High value** "
        "is the top tier of Historical Realized Revenue &mdash; money already collected, not a forecast."
    )
    theme.insight(
        f"The last group is small &mdash; <b>{theme.fmt_count(n_zone)}</b> customers &mdash; but "
        f"<b>{zone_churn:.1f}%</b> of them churn, and each has already spent "
        f"<b>{theme.fmt_currency(zone_avg_hrr)}</b> on average. That is where personal outreach is most worth considering."
    )
    if st.button(
        f"Review the {theme.fmt_count(n_zone)} high-risk, high-value customers →",
        key="ov_zone_to_priority",
    ):
        st.session_state["pending_filter"] = {"risk_tier": ["High"], "value_tier": ["High"]}
        st.switch_page("pages/priority_customers.py")

theme.journey_next("pages/overview.py", key="next_overview")

st.write("")
caveats.render_caveats(
    ["temporal", "calibration", "reusability"], risk_summary=risk_summary, temporal_results=temporal_results,
)
