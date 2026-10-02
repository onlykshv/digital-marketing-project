import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

# The page header carries the live list size, which is only known once the filters below have run --
# so its position is reserved now and filled in afterwards.
mast_slot = st.container()

risk_summary = data.safe_load(data.load_risk_summary)
threshold_df = data.safe_load(data.load_threshold_analysis)
shap_df = data.safe_load(data.load_shap_importance)
action_plan = data.safe_load(data.load_action_plan)
temporal_results = data.safe_load(data.load_temporal_results)

# ---------------------------------------------------------------------------
# The work list -- this page's primary object is the list itself, not a chart.
# ---------------------------------------------------------------------------
df = data.safe_load(data.load_customer_lookup_data)
# The full customer table is now in memory for this session, so Customer 360 and Retention
# Intelligence must not ask the manager to load it a second time.
st.session_state["lookup_loaded"] = True

# A "View all matching customers ->" link from Retention Intelligence (lib.components.
# agent_response_block) can hand this page a starting filter via session state -- the same
# {"risk_tier": [...], "value_tier": [...], "segment": [...]} shape agent_tools.search_customers
# already accepts. Consumed once (popped) so it only affects the very next render, never
# silently re-overriding a filter the manager has since changed by hand.
_pending_filter = st.session_state.pop("pending_filter", {}) if "pending_filter" in st.session_state else {}


def _incoming(key: str, options: list, fallback: list | None = None) -> list | None:
    """A handed-over filter value, restricted to what this page can actually offer.

    The segment vocabulary is wider than this table's: `copilot_data.SEGMENTS` carries all seven
    groups from marketing_action_plan.csv, while outputs/customer_segments.csv labels customers
    with only six (the "Unmatched At-Risk (no segment)" group is not present as a per-customer
    label). Passing a value Streamlit can't find in `options` is a hard StreamlitAPIException, so
    an unrepresented group must degrade to "no filter" rather than take the page down.
    """
    incoming = _pending_filter.get(key)
    if incoming is None:
        return fallback
    kept = [v for v in incoming if v in options]
    return kept or fallback


_risk_options = ["High", "Medium", "Low"]
_value_options = sorted(df["value_tier"].cat.categories.tolist())
_segment_options = sorted(df["segment"].cat.categories.tolist())

# The filters are keyed widgets whose state belongs to the manager. A carried filter is written into
# that state exactly once, on arrival, and is then just the current filter -- so the next unrelated
# rerun (selecting a row, typing a search) keeps it, and a filter changed by hand is never
# overridden. (Unkeyed widgets fed only through `default=` silently reset to the page default on
# the first rerun after the one-time `pending_filter` was consumed, dropping the carried filter and
# the row selection with it.)
_RISK_KEY, _VALUE_KEY, _SEGMENT_KEY = "pc_filter_risk", "pc_filter_value", "pc_filter_segment"
st.session_state.setdefault(_RISK_KEY, ["High", "Medium"])
st.session_state.setdefault(_VALUE_KEY, [])
st.session_state.setdefault(_SEGMENT_KEY, [])
if _pending_filter:
    st.session_state[_RISK_KEY] = _incoming("risk_tier", _risk_options, ["High", "Medium"])
    st.session_state[_VALUE_KEY] = _incoming("value_tier", _value_options) or []
    st.session_state[_SEGMENT_KEY] = _incoming("segment", _segment_options) or []
    carried = " &middot; ".join(
        f"{k.replace('_', ' ').capitalize()}: <b>{', '.join(v)}</b>" for k, v in _pending_filter.items() if v
    )
    theme.handoff_note("Filter carried over", f"{carried} &mdash; applied from your previous step.")

f1, f2, f3, f4 = st.columns([2, 1, 1, 1.2], vertical_alignment="bottom")
with f1:
    search = st.text_input("Search by Customer ID", placeholder="Search by customer ID…", label_visibility="collapsed")
with f2:
    risk_choices = st.multiselect("Risk tier", _risk_options, key=_RISK_KEY)
with f3:
    value_choices = st.multiselect("Value tier", _value_options, key=_VALUE_KEY)
with f4:
    segment_choices = st.multiselect("Segment", _segment_options, key=_SEGMENT_KEY)

filtered = df
if search:
    filtered = filtered[filtered["msno"].str.contains(search, case=False, na=False, regex=False)]
if risk_choices:
    filtered = filtered[filtered["risk_tier"].isin(risk_choices)]
if value_choices:
    filtered = filtered[filtered["value_tier"].isin(value_choices)]
if segment_choices:
    filtered = filtered[filtered["segment"].isin(segment_choices)]

n_high_in_list = int((filtered["risk_tier"] == "High").sum())
with mast_slot:
    theme.masthead(
        "pages/priority_customers.py", "Priority customers", "Who should we save?",
        "Customers ranked by how likely they are to leave. Select one to see why they were flagged "
        "and what to do next.",
        stats=[
            {"label": "In this list", "value": f"{len(filtered):,}"},
            {"label": "High risk", "value": f"{n_high_in_list:,}", "dot": theme.COLORS["high"]},
        ],
    )

MAX_ROWS = 500
queue = filtered.sort_values("risk_score_full", ascending=False).head(MAX_ROWS).reset_index(drop=True)

queue_view = pd.DataFrame({
    "msno": queue["msno"],
    "risk_tier": queue["risk_tier"],
    "value_tier": queue["value_tier"],
    "key_risk_signal": [
        data.key_risk_signal(ar, ds, cr)
        for ar, ds, cr in zip(queue["latest_is_auto_renew"], queue["days_since_last_txn"], queue["cancel_rate"])
    ],
    "recommended_action": queue["segment"].map(data.SHORT_ACTION_BY_SEGMENT).fillna("Standard outreach").astype(str),
})
# Customers in an elevated risk tier who carry the Stable / Monitor label inherit that label's
# "Monitor only" action -- marked so the list never silently presents them as low-risk.
gap_mask = [data.segment_label_gap(rt, sg) for rt, sg in zip(queue["risk_tier"], queue["segment"])]
queue_view.loc[gap_mask, "recommended_action"] = queue_view.loc[gap_mask, "recommended_action"] + " †"

list_col, detail_col = st.columns([1.75, 1], gap="medium")

with list_col:
    styled_queue = queue_view.style.map(
        lambda v: f"color: {theme.RISK_TEXT_COLOR_MAP.get(v, theme.COLORS['text'])}; font-weight: 600;", subset=["risk_tier"]
    )
    event = st.dataframe(
        styled_queue,
        hide_index=True,
        width="stretch",
        height=440,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "msno": st.column_config.TextColumn("Customer", width=165),
            "risk_tier": st.column_config.TextColumn("Risk", width=62),
            "value_tier": st.column_config.TextColumn("Value", width=66),
            "key_risk_signal": st.column_config.TextColumn("Why flagged", width=165),
            "recommended_action": st.column_config.TextColumn("Recommended action", width=150),
        },
    )
    st.caption(
        f"{len(filtered):,} customers match these filters -- showing the {min(MAX_ROWS, len(filtered)):,} most at risk. "
        "Select a row to see why that customer was flagged."
        + (" † = in an elevated risk tier but labelled Stable / Monitor (see the customer's profile)." if any(gap_mask) else "")
    )

selected_rows = event.selection.rows if event and event.selection else []

with detail_col:
    with st.container(key="rp_selected"):
        if selected_rows:
            picked = queue.iloc[selected_rows[0]]
            st.session_state["cust360_search"] = picked["msno"]
            signal = data.key_risk_signal(picked["latest_is_auto_renew"], picked["days_since_last_txn"], picked["cancel_rate"])
            action = data.SHORT_ACTION_BY_SEGMENT.get(picked["segment"], "Standard outreach")
            prob = f"{picked['calibrated_probability'] * 100:.0f}%" if pd.notna(picked["calibrated_probability"]) else "—"
            hrr = theme.fmt_currency(picked["total_revenue"]) if pd.notna(picked["total_revenue"]) else "—"
            theme.panel_head("Selected customer", dot=theme.RISK_COLOR_MAP.get(picked["risk_tier"]), right=f"#{selected_rows[0] + 1} in this list")
            gap_html = (
                '<div class="ri-gap-note"><span class="k">Label gap</span><span>High on risk, but labelled Stable / Monitor '
                "&mdash; so the action shown is that label's, not a risk-based one.</span></div>"
            ) if data.segment_label_gap(picked["risk_tier"], picked["segment"]) else ""
            theme.md(
                f"""<div class="ri-id"><div class="who">{theme.esc(picked['msno'])}</div>
                    <div>{theme.risk_badge(picked['risk_tier'])} &nbsp;{theme.value_chip(picked['value_tier'])}</div></div>
                <div class="ri-kv" style="margin-top:0.6rem;">
                    <div><span class="k">Why flagged</span><span class="v">{signal}</span></div>
                    <div><span class="k">Recommended action</span><span class="v">{action}</span></div>
                    <div><span class="k">Segment</span><span class="v">{picked['segment']}</span></div>
                    <div><span class="k">Revenue to date</span><span class="v">{hrr}</span></div>
                </div>{gap_html}"""
            )
            if st.button("Open full customer profile →", key="pc_open_profile", type="primary", width="stretch"):
                st.switch_page("pages/customer_360.py")
            if st.button("Ask Retention Intelligence about this customer →", key="pc_ask_ri", width="stretch"):
                st.switch_page("pages/retention_copilot.py")
            with st.expander("Model details"):
                st.markdown(
                    f"Estimated Churn Probability **{prob}** (calibrated) &middot; Model Risk Score "
                    f"**{picked['risk_score_full']:.2f}** (a ranking score, not a probability)."
                )
        else:
            # Nothing selected yet: who is in this list, by risk x value (linear widths, real counts),
            # so the manager sees the list's make-up before picking a customer.
            theme.panel_head("Who is in this list", right="risk &times; value")
            combo = filtered.groupby(["risk_tier", "value_tier"], observed=True).size()
            legend = []
            for rt in ["High", "Medium", "Low"]:
                for vt in ["High", "Medium", "Low"]:
                    n = int(combo.get((rt, vt), 0))
                    if not n:
                        continue
                    is_zone = rt == "High" and vt == "High"
                    legend.append({
                        "dot": theme.RISK_COLOR_MAP[rt], "name": f"{rt} risk &middot; {vt} value",
                        "sub": "save first" if is_zone else None, "right": f"<b>{n:,}</b>", "state": "hot" if is_zone else "",
                    })
            st.markdown(theme.status_list(legend) if legend else '<p class="recede">No customers match these filters.</p>', unsafe_allow_html=True)
            theme.recede("Select a customer in the list to see why they were flagged and what to do.")

st.download_button(
    "Download this list (CSV)",
    data=queue[["msno", "risk_tier", "calibrated_probability", "risk_score_full", "total_revenue", "segment"]].to_csv(index=False).encode("utf-8"),
    file_name="priority_customers.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------------
# Details, for whoever asks: what drives the risk score, and how the tiers are cut.
# ---------------------------------------------------------------------------
theme.section_header("Why are these customers at risk?", note="Model detail, for anyone who asks.")
with st.expander("What drives the risk score"):
    top_shap = shap_df.sort_values("mean_abs_shap", ascending=False).head(8).copy()
    top_shap["display_name"] = top_shap["feature"].apply(data.feature_display_name)
    max_shap = float(top_shap["mean_abs_shap"].max())
    rows_html = []
    for i, (_, r) in enumerate(top_shap.iterrows()):
        pct = max(4, r["mean_abs_shap"] / max_shap * 100)
        rows_html.append(
            f'<div class="ri-rank{" lead" if i == 0 else ""}"><div class="n">{i + 1:02d}</div><div class="body">'
            f'<div class="top"><span>{r["display_name"]}</span><span>{r["mean_abs_shap"]:.3f}</span></div>'
            f'<div class="track"><div class="fill" style="width:{pct:.1f}%;"></div></div></div></div>'
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)
    top_driver = top_shap.iloc[0]
    second_driver = top_shap.iloc[1]
    theme.insight(
        f"<b>{top_driver['display_name']}</b> is the strongest signal the model relies on -- roughly "
        f"{top_driver['mean_abs_shap'] / second_driver['mean_abs_shap']:.1f}x the impact of the next "
        f"factor. Ranked by impact on Model Risk Score (mean |SHAP| value); associations, not causes."
    )

with st.expander("Risk tiers and model performance"):
    tier_order = {"Low": 0, "Medium": 1, "High": 2}
    tiers = sorted(risk_summary["risk_tiers"], key=lambda t: tier_order[t["tier"]])
    st.markdown(
        theme.band([
            {"value": t["n_customers"], "color": theme.RISK_COLOR_MAP[t["tier"]],
             "title": f"{t['tier']} risk: {t['n_customers']:,} customers ({t['pct_of_base']:.1f}% of base), {t['observed_churn_rate_in_tier']:.1f}% churn"}
            for t in tiers
        ])
        + '<div class="ri-facts" style="grid-template-columns: repeat(3, 1fr); margin-top:0.9rem;">'
        + "".join(
            f'<div><div class="l">{t["tier"]} risk &middot; {t["score_range"]}</div>'
            f'<div class="v">{theme.fmt_count(t["n_customers"])}</div>'
            f'<div style="font-size:0.8rem; color:{theme.RISK_TEXT_COLOR_MAP[t["tier"]]};">{t["observed_churn_rate_in_tier"]:.1f}% churn</div></div>'
            for t in tiers
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    theme.note(
        "Tiers are cut on the raw <b>Model Risk Score</b> (0.65 / 0.95) -- a ranking score, not a probability. "
        "The list above holds the Medium and High tiers by default."
    )
    st.caption(
        "Drag to see the precision / recall / campaign-size trade-off at any Model Risk Score "
        "cutoff. This is the raw, uncalibrated score -- not a probability."
    )
    thresholds = threshold_df["threshold"].round(2).tolist()
    selected = st.select_slider("Model Risk Score threshold", options=thresholds, value=0.65)
    row = threshold_df.loc[threshold_df["threshold"].round(2) == selected].iloc[0]
    theme.kpi_strip([
        {"label": "Precision", "value": theme.fmt_pct(row["precision"] * 100)},
        {"label": "Recall", "value": theme.fmt_pct(row["recall"] * 100)},
        {"label": "F1 score", "value": f"{row['f1']:.3f}"},
        {"label": "% targeted", "value": theme.fmt_pct(row["pct_targeted"])},
    ])
    fig = go.Figure()
    for col, label, color in [
        ("precision", "Precision", theme.COLORS["text_muted"]),
        ("recall", "Recall", theme.COLORS["accent_on_dark"]),
        ("f1", "F1", theme.COLORS["low"]),
    ]:
        fig.add_trace(go.Scatter(
            x=threshold_df["threshold"], y=threshold_df[col], mode="lines", name=label,
            line=dict(color=color, width=2),
            hovertemplate=f"{label}: %{{y:.3f}} at threshold %{{x:.2f}}<extra></extra>",
        ))
    fig.add_vline(x=selected, line=dict(color=theme.COLORS["ink"], width=1, dash="dot"))
    theme.chart_layout(fig, height=280, xaxis_title="Model Risk Score threshold", yaxis_title="Score", hovermode="x unified")
    theme.plot(fig)
    st.caption("0.65 and 0.95 (the production Medium/High cutoffs) are a documented heuristic, not a statistically optimal pick -- see \"Why 0.65 and 0.95\" in Methodology below.")

theme.journey_next("pages/priority_customers.py", key="next_priority_customers")

st.write("")
caveats.render_caveats(
    ["calibration", "thresholds", "causal", "temporal"], risk_summary=risk_summary, temporal_results=temporal_results,
)
