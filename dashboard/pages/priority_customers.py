import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

theme.page_header(
    "PRIORITY CUSTOMERS",
    "Who should we save?",
    "The retention team's work queue -- customers ranked by risk and value, with the evidence "
    "and recommended action for each.",
)

risk_summary = data.safe_load(data.load_risk_summary)
threshold_df = data.safe_load(data.load_threshold_analysis)
shap_df = data.safe_load(data.load_shap_importance)
action_plan = data.safe_load(data.load_action_plan)
temporal_results = data.safe_load(data.load_temporal_results)

# ---------------------------------------------------------------------------
# The work queue -- this page's primary object is the table, not a chart.
# ---------------------------------------------------------------------------
df = data.safe_load(data.load_customer_lookup_data)

# A "View all matching customers ->" link from Retention Intelligence (lib.components.
# agent_response_block) can hand this page a starting filter via session state -- the same
# {"risk_tier": [...], "value_tier": [...], "segment": [...]} shape agent_tools.search_customers
# already accepts. Consumed once (popped) so it only affects the very next render, never
# silently re-overriding a filter the manager has since changed by hand.
_pending_filter = st.session_state.pop("pending_filter", {}) if "pending_filter" in st.session_state else {}

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
with f1:
    search = st.text_input("Search by Customer ID", placeholder="Paste or type a customer ID (msno)…", label_visibility="collapsed")
with f2:
    risk_choices = st.multiselect("Risk tier", ["High", "Medium", "Low"], default=_pending_filter.get("risk_tier", ["High", "Medium"]))
with f3:
    value_choices = st.multiselect("Value tier", sorted(df["value_tier"].cat.categories.tolist()), default=_pending_filter.get("value_tier"))
with f4:
    segment_choices = st.multiselect("Segment", sorted(df["segment"].cat.categories.tolist()), default=_pending_filter.get("segment"))

filtered = df
if search:
    filtered = filtered[filtered["msno"].str.contains(search, case=False, na=False, regex=False)]
if risk_choices:
    filtered = filtered[filtered["risk_tier"].isin(risk_choices)]
if value_choices:
    filtered = filtered[filtered["value_tier"].isin(value_choices)]
if segment_choices:
    filtered = filtered[filtered["segment"].isin(segment_choices)]

MAX_ROWS = 500
queue = filtered.sort_values("risk_score_full", ascending=False).head(MAX_ROWS).reset_index(drop=True)

queue_view = queue[["msno", "risk_tier", "calibrated_probability", "total_revenue", "segment"]].copy()
queue_view["total_revenue"] = theme.to_inr(queue_view["total_revenue"])
queue_view["calibrated_probability"] = queue["calibrated_probability"] * 100
queue_view["key_risk_signal"] = [
    data.key_risk_signal(ar, ds, cr)
    for ar, ds, cr in zip(queue["latest_is_auto_renew"], queue["days_since_last_txn"], queue["cancel_rate"])
]
queue_view["recommended_action"] = queue["segment"].map(data.SHORT_ACTION_BY_SEGMENT).fillna("Standard outreach")

st.caption(
    f"{len(filtered):,} customers match these filters -- showing the top {min(MAX_ROWS, len(filtered)):,} by Model Risk Score. "
    "Select a row to open that customer's full profile."
)

event = st.dataframe(
    queue_view,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "msno": st.column_config.TextColumn("Customer"),
        "risk_tier": st.column_config.TextColumn("Risk Tier"),
        "calibrated_probability": st.column_config.NumberColumn("Estimated Churn Probability", format="%.0f%%"),
        "total_revenue": st.column_config.NumberColumn("Historical Realized Revenue (₹)", format="₹%d"),
        "segment": st.column_config.TextColumn("Segment"),
        "key_risk_signal": st.column_config.TextColumn("Key Risk Signal"),
        "recommended_action": st.column_config.TextColumn("Recommended Action"),
    },
)

selected_rows = event.selection.rows if event and event.selection else []
if selected_rows:
    picked = queue.iloc[selected_rows[0]]
    st.session_state["cust360_search"] = picked["msno"]
    st.page_link(
        "pages/customer_360.py",
        label=f"Open full profile for {picked['msno'][:24]}… in Customer 360 →",
        icon=None,
    )

st.download_button(
    "Download this view (CSV)",
    data=queue[["msno", "risk_tier", "calibrated_probability", "risk_score_full", "total_revenue", "segment"]].to_csv(index=False).encode("utf-8"),
    file_name="priority_customers.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------------
# Why are these customers at risk? -- the model-explanation half of this page.
# ---------------------------------------------------------------------------
st.write("")
theme.divider()
tier_order = {"Low": 0, "Medium": 1, "High": 2}
tiers = sorted(risk_summary["risk_tiers"], key=lambda t: tier_order[t["tier"]])

fig_dist = go.Figure()
for t in tiers:
    pct = t["pct_of_base"]
    label = f"{t['tier']}<br>{pct:.0f}%" if pct >= 8 else ""
    fig_dist.add_trace(go.Bar(
        y=["Base"], x=[t["n_customers"]], name=t["tier"], orientation="h",
        marker_color=theme.RISK_COLOR_MAP[t["tier"]],
        text=label, textposition="inside", insidetextanchor="middle",
        textfont=dict(color="white", size=13, family="Inter"),
        hovertemplate=f"<b>{t['tier']} risk</b><br>%{{x:,}} customers ({pct:.1f}% of base)<br>{t['observed_churn_rate_in_tier']:.1f}% churn rate<extra></extra>",
    ))
theme.chart_layout(fig_dist, height=64, barmode="stack", showlegend=False,
                    xaxis=dict(visible=False), yaxis=dict(visible=False), margin=dict(l=0, r=0, t=4, b=4))
st.plotly_chart(fig_dist, width="stretch", config=theme.PLOTLY_CONFIG)

theme.stat_row([
    {"label": f"{t['tier']} risk", "value": f"{theme.fmt_count(t['n_customers'])} &middot; {t['observed_churn_rate_in_tier']:.1f}% churn"}
    for t in tiers
])

theme.eyebrow("Model explanation")
theme.section("Why are these customers at risk?", "Ranked by impact on Model Risk Score (mean |SHAP| value) -- higher means the model relies on it more.")

top_shap = shap_df.sort_values("mean_abs_shap", ascending=False).head(8).copy()
top_shap["display_name"] = top_shap["feature"].apply(data.feature_display_name)
max_shap = float(top_shap["mean_abs_shap"].max())

rows_html = []
for i, (_, r) in enumerate(top_shap.iterrows()):
    pct = max(4, r["mean_abs_shap"] / max_shap * 100)
    bar_color = theme.COLORS["accent"] if i == 0 else theme.COLORS["navy_soft"]
    rows_html.append(f"""
    <div style="display:flex; align-items:center; gap:1rem; padding:0.55rem 0; border-bottom:1px solid {theme.COLORS['card_border']};">
        <div style="width:2rem; font-size:1.3rem; font-weight:800; color:{theme.COLORS['card_border']}; flex-shrink:0;">{i + 1:02d}</div>
        <div style="flex:1;">
            <div style="display:flex; justify-content:space-between; font-size:0.92rem; color:{theme.COLORS['text']}; font-weight:600; margin-bottom:0.32rem;">
                <span>{r['display_name']}</span><span style="color:{theme.COLORS['text_muted']}; font-weight:500;">{r['mean_abs_shap']:.3f}</span>
            </div>
            <div style="background:{theme.COLORS['card_border']}; border-radius:3px; height:6px; overflow:hidden;">
                <div style="background:{bar_color}; width:{pct:.1f}%; height:100%;"></div>
            </div>
        </div>
    </div>""")
st.markdown("".join(rows_html), unsafe_allow_html=True)

top_driver = top_shap.iloc[0]
second_driver = top_shap.iloc[1]
theme.insight(
    f"<b>{top_driver['display_name']}</b> is the strongest signal the model relies on -- roughly "
    f"{top_driver['mean_abs_shap'] / second_driver['mean_abs_shap']:.1f}x the impact of the next "
    f"factor. It's the single highest-leverage lever for a retention campaign to target."
)

with st.expander("Advanced: model performance & threshold trade-off"):
    st.caption(
        "Drag to see the precision / recall / campaign-size trade-off at any Model Risk Score "
        "cutoff. This is the raw, uncalibrated score -- not a probability."
    )
    thresholds = threshold_df["threshold"].round(2).tolist()
    selected = st.select_slider("Model Risk Score threshold", options=thresholds, value=0.65)
    row = threshold_df.loc[threshold_df["threshold"].round(2) == selected].iloc[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precision", theme.fmt_pct(row["precision"] * 100))
    m2.metric("Recall", theme.fmt_pct(row["recall"] * 100))
    m3.metric("F1 score", f"{row['f1']:.3f}")
    m4.metric("% targeted", theme.fmt_pct(row["pct_targeted"]))

    fig = go.Figure()
    for col, label, color in [
        ("precision", "Precision", theme.COLORS["navy_soft"]),
        ("recall", "Recall", theme.COLORS["accent"]),
        ("f1", "F1", theme.COLORS["low"]),
    ]:
        fig.add_trace(go.Scatter(x=threshold_df["threshold"], y=threshold_df[col], mode="lines+markers", name=label, line=dict(color=color)))
    fig.add_vline(x=selected, line_dash="dash", line_color="#AAAAAA")
    theme.chart_layout(fig, xaxis_title="Model Risk Score threshold", yaxis_title="Score")
    st.plotly_chart(fig, width="stretch", config=theme.PLOTLY_CONFIG)
    st.caption("0.65 and 0.95 (the production Medium/High cutoffs) are a documented heuristic, not a statistically optimal pick -- see \"Why 0.65 and 0.95\" in Methodology below.")

st.write("")
caveats.render_caveats(
    ["calibration", "thresholds", "causal", "temporal"], risk_summary=risk_summary, temporal_results=temporal_results,
)
