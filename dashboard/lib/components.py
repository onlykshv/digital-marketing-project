"""Reusable, higher-level UI blocks shared across pages.

Deliberately NOT a card library -- `recommendation_block` / `play_card` are the single directive in
a panel ("do this"), `secondary_story` is the smaller note beside it, and `agent_response_block`
renders Retention Intelligence's already-structured answer as a decision brief. Each shows the
headline first and keeps the supporting detail one click away.
"""
from __future__ import annotations

import re

import streamlit as st

from lib import theme

_MARKER = "Based on observed historical association, not a causal guarantee:"


def _rationale_disclosure(rationale: str | None) -> str:
    if not rationale:
        return ""
    # P1-15: `rationale` comes from outputs/marketing_action_plan.csv -- a notebook-generated
    # sentence that embeds a raw "<number> NT$" mention directly in the prose, predating this
    # project's ₹ display convention and untouched by fmt_currency() (which only formats numeric
    # fields, not free text). Rewritten here, at render time only.
    rationale_display = theme.convert_ntd_mentions_in_text(rationale)
    return (
        '<details class="ri-disclosure"><summary>More detail on this recommendation</summary>'
        f"<p>{_MARKER} {rationale_display}</p></details>"
    )


def recommendation_block(
    *,
    eyebrow: str,
    title: str,
    stat_html: str,
    objective: str,
    intensity: str,
    why: str | None = None,
    rationale: str | None = None,
    size: str = "large",
) -> None:
    """The single most important recommendation in a panel -- the group, one line of numbers, and
    "Do this". `why` is a one-line plain-English restatement of the segment's existing rule, never a
    causal claim; `rationale` is the longer, stats-bearing version behind a disclosure."""
    why_html = f'<div class="recommendation-why"><b>Why:</b> {why}</div>' if why else ""
    title_size = "1.8rem" if size == "large" else "1.4rem"
    theme.md(
        f"""<div class="recommendation-block">
            <div class="recommendation-eyebrow">{eyebrow}</div>
            <div class="recommendation-title" style="font-size:{title_size};">{title}</div>
            <div class="recommendation-stats">{stat_html}</div>
            <div class="recommendation-action"><b>Do this &middot; {intensity}</b>{objective}</div>
            {why_html}
            {_rationale_disclosure(rationale)}
        </div>"""
    )


def play_card(
    *,
    eyebrow: str,
    row,
    why: str,
    avoid: str | None,
    base_churn_pct: float,
) -> None:
    """One play from the action framework, reduced to what a marketer needs first: who, how many,
    how likely they are to leave, and what to do. Why / value / what to avoid / how confident the
    framework is sit one click away. Every field is read from the action-plan row itself or the
    existing plain-English segment mappings -- nothing is derived beyond formatting."""
    intensity = row["intervention_intensity"]
    avoid_html = f"<p><b>Avoid:</b> {avoid}</p>" if avoid else ""
    theme.md(
        f"""<div class="ri-play">
            <div class="ri-play-k">{eyebrow}</div>
            <div class="ri-play-t">{row['priority_group']}</div>
            <div class="ri-play-s"><b>{theme.fmt_count(row['n_customers'])}</b> customers &middot;
                <b style="color:var(--high-text);">{row['churn_rate_pct']:.1f}%</b> churn (base {base_churn_pct:.1f}%) &middot;
                <b>{theme.fmt_currency(row['total_HRR'])}</b> revenue to date</div>
            <div class="recommendation-action"><b>Do this &middot; {intensity}</b>{row['marketing_objective']}</div>
            <details class="ri-disclosure"><summary>Why this group, and how sure we are</summary>
                <p><b>Who:</b> {why}</p>{avoid_html}
                <p><b>Confidence:</b> {row['pct_matching_dominant_recommendation']:.0f}% of this group sits in the risk &times; value
                cell that sets this intensity. An observed association from the validated framework &mdash; not a causal
                guarantee; no campaign-response data exists.</p>
                <p>{_MARKER} {theme.convert_ntd_mentions_in_text(row['rationale'])}</p>
            </details>
        </div>"""
    )


def copilot_answer_block(answer) -> None:
    """Renders a lib.copilot_engine.CopilotAnswer in the fixed decision format."""
    theme.md(
        f"""<div class="recommendation-block">
            <div class="recommendation-eyebrow">Recommendation</div>
            <div class="recommendation-title" style="font-size:1.5rem;">{answer.recommendation}</div>
            {f'<div class="recommendation-why"><b>Why:</b> {answer.why}</div>' if answer.why else ''}
        </div>"""
    )
    if answer.used_llm:
        st.caption("AI-synthesized from the evidence below.")
    elif answer.llm_unavailable_reason:
        st.caption(
            f"This is the deterministic, evidence-backed answer -- AI-assisted synthesis was "
            f"not used ({answer.llm_unavailable_reason})."
        )
    if answer.evidence:
        st.markdown("**Evidence**")
        st.markdown("\n".join(f"- {e}" for e in answer.evidence))
    if answer.what_to_do:
        st.markdown(f"**What to do**  \n{answer.what_to_do}")
    if answer.what_to_avoid:
        st.markdown(f"**What to avoid**  \n{answer.what_to_avoid}")
    if answer.confidence_basis:
        st.caption(f"**Confidence / basis:** {answer.confidence_basis}")
    if answer.caution:
        st.caption(f"**Caution:** {answer.caution}")
    if answer.sources:
        st.caption("Evidence used: " + " · ".join(answer.sources))


def priority_list(rows: list[dict], *, limit_shown: int = 5) -> None:
    """Compact, decision-focused customer rows -- Customer / Risk / Value / Recommended action --
    deliberately NOT a dataframe grid. Caps at `limit_shown`; the caller offers a "View all" deep
    link beyond that. Each row's "Open" action sets the shared `cust360_search` session key and
    navigates with `st.switch_page` -- the same mechanism every other cross-page handoff uses."""
    with st.container(key="ri_results"):
        for r in rows[:limit_shown]:
            c1, c2, c3, c4 = st.columns([2.5, 1.6, 2.2, 0.9], vertical_alignment="center")
            msno = r["msno"]
            with c1:
                short_id = msno if len(msno) <= 22 else msno[:22] + "…"
                st.markdown(
                    f'<div class="ri-qrow-id">{theme.esc(short_id)}</div>'
                    f'<div class="ri-qrow-sig">{r.get("key_risk_signal") or ""}</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(theme.risk_chip(r["risk_tier"]) + theme.value_chip(r["value_tier"]), unsafe_allow_html=True)
            with c3:
                st.markdown(
                    f'<div class="ri-qrow-act">{r.get("recommended_action") or "—"}</div>'
                    f'<div class="ri-qrow-seg">{r.get("segment") or ""}</div>',
                    unsafe_allow_html=True,
                )
            with c4:
                if st.button("Open →", key=f"priority_open_{msno}", width="stretch"):
                    st.session_state["cust360_search"] = msno
                    st.switch_page("pages/customer_360.py")


# The answer text `agent.py` produces always uses a small, known set of leading labels (see
# agent._render_copilot_answer / _format_aggregate_answer / _format_search_customers_answer /
# _format_rank_segments_answer) -- never invented per question type. Classifying by label name
# gives a real Finding / Evidence / Action / Confidence hierarchy without parsing or re-deriving
# anything: the finding is the one line worth reading at a glance, the confidence/caution lines
# are real information that should stay visible but not compete with it.
_FINDING_LABELS = {"recommendation", "headline"}
_MUTED_LABELS = {"confidence/basis", "confidence", "caution", "confidence/limitations"}
_ROLE_BY_LABEL = {
    "evidence": "evidence",
    "why it matters": "why", "why": "why", "result summary": "why", "also worth attention": "why",
    "recommended action": "action", "what to do": "action",
    "avoid": "avoid", "what to avoid": "avoid",
    "recommended next step": "next", "next step": "next",
}

# Human-readable names for the nine allow-listed tools -- display only, used for the provenance row.
TOOL_DISPLAY_NAMES = {
    "get_customer": "Customer profile",
    "search_customers": "Customer search",
    "get_aggregate_metrics": "Portfolio metrics",
    "get_segment": "Segment profile",
    "explain_customer_risk": "Customer risk explanation",
    "recommend_action": "Action framework",
    "compare_to_champions": "Champions benchmark",
    "rank_segments_by_priority": "Segment ranking",
    "build_dashboard_deep_link": "Dashboard link",
}


def _evidence_items(text: str) -> list[str]:
    """Split an Evidence value into its already-present '; '-separated facts for display as a list.
    A fragment with no label of its own (e.g. the second clause of 'Defining characteristics')
    stays attached to the fact it belongs to, so no fact is separated from its label."""
    items: list[str] = []
    for frag in (f.strip() for f in text.split("; ")):
        if not frag:
            continue
        if items and ":" not in frag:
            items[-1] = f"{items[-1]}; {frag}"
        else:
            items.append(frag)
    return [re.sub(r"^(\d+)\.", r"\1\\.", it) for it in items]


def agent_response_block(response, *, show_results: bool = True) -> None:
    """Renders a `lib.agent.AgentResponse` as a decision brief: Finding -> Evidence -> Why it
    matters -> Recommended action -> Avoid -> Confidence -> Next step, each line in a role-keyed
    container so the design system can give it its own treatment. Lines are the agent's own,
    already-structured text -- displayed, never re-derived. The evidence list sits behind a toggle
    (the finding, why and action are what a manager reads first). A quiet provenance row names the
    analytical tools the answer came from (never chain-of-thought, never a raw tool/JSON dump), and
    a compact priority list appears only when a tool call actually returned customers.

    Deliberately duck-typed (no `lib.agent` import) -- `response` only needs `.answer`,
    `.tools_used`, `.used_llm`, `.grounded`, `.fallback_reason` and `.tool_calls` (each with
    `.tool`, `.ok`, `.result`).
    """
    lines = [ln.strip() for ln in response.answer.splitlines() if ln.strip()]
    pending_facts: list[str] = []

    def flush_facts(idx: int) -> None:
        if not pending_facts:
            return
        with st.container(key=f"ri-facts-{idx}", horizontal=True, gap="large"):
            for fact in pending_facts:
                st.markdown(fact)
        pending_facts.clear()

    for i, line in enumerate(lines):
        label, sep, rest = line.partition(":")
        label_key = label.strip().lower()
        is_labeled = bool(sep) and 0 < len(label) < 40 and "[" not in label

        if line.startswith("[") and line.endswith("]"):
            flush_facts(i)
            st.markdown(
                f'<div class="ri-mode-banner"><span class="k">Answer mode</span><span>{line[1:-1]}</span></div>',
                unsafe_allow_html=True,
            )
        elif sep and label_key in _FINDING_LABELS:
            flush_facts(i)
            st.markdown(
                f'<div class="ri-brief-in" style="font-size:1.18rem; font-weight:600; color:var(--ink); '
                f'line-height:1.4; margin:0.35rem 0 0.75rem 0; max-width:52rem;">{rest.strip()}</div>',
                unsafe_allow_html=True,
            )
        elif sep and label_key in _MUTED_LABELS:
            flush_facts(i)
            st.caption(f"{label.strip()}: {rest.strip()}")
        elif is_labeled and _ROLE_BY_LABEL.get(label_key) == "evidence":
            flush_facts(i)
            items = _evidence_items(rest.strip())
            with st.expander(f"Evidence behind this answer ({len(items)} fact{'s' if len(items) != 1 else ''})"):
                with st.container(key=f"ri-l-evidence-{i}"):
                    if len(items) > 1:
                        st.markdown(f"**{label.strip()}:**\n\n" + "\n".join(f"- {it}" for it in items))
                    else:
                        st.markdown(f"**{label.strip()}:** {rest.strip()}")
        elif is_labeled and label_key in _ROLE_BY_LABEL:
            flush_facts(i)
            with st.container(key=f"ri-l-{_ROLE_BY_LABEL[label_key]}-{i}"):
                st.markdown(f"**{label.strip()}:** {rest.strip()}")
        elif is_labeled:
            pending_facts.append(f"**{label.strip()}:** {rest.strip()}")
        else:
            flush_facts(i)
            st.markdown(line)
    flush_facts(len(lines))

    n_tools = len(set(response.tools_used))
    if response.used_llm and n_tools:
        st.caption(f"Grounded in {n_tools} analytical tool{'s' if n_tools != 1 else ''}.")
    elif response.used_llm:
        st.caption("AI-synthesized.")
    elif response.grounded:
        st.caption(f"Deterministic answer -- AI synthesis not used ({response.fallback_reason}).")
    elif response.fallback_reason:
        st.caption(f"AI synthesis unavailable ({response.fallback_reason}).")

    used = [TOOL_DISPLAY_NAMES.get(t, t) for t in dict.fromkeys(response.tools_used)]
    if used:
        st.markdown(
            '<div class="ri-prov">Evidence from '
            + "".join(f"<span>{theme.esc(u)}</span>" for u in used)
            + "</div>",
            unsafe_allow_html=True,
        )

    if not show_results:
        return

    for call in response.tool_calls:
        if call.tool == "search_customers" and call.ok:
            rows = (call.result.get("data") or {}).get("rows") or []
            total = (call.result.get("data") or {}).get("total_matches", len(rows))
            if rows:
                st.markdown('<div class="ri-eyebrow" style="margin-top:1.2rem;">Customers returned by the search</div>', unsafe_allow_html=True)
                priority_list(rows)
                if total > len(rows[:5]):
                    pending = {k: v for k, v in call.arguments.items() if k in ("risk_tier", "value_tier", "segment") and v}
                    if pending:
                        st.session_state["pending_filter"] = pending
                    st.page_link("pages/priority_customers.py", label=f"View all {total:,} matching customers →")
            break


def secondary_story(*, eyebrow: str, title: str, stat_html: str, objective: str, color: str) -> None:
    """A quiet note beside a directive -- a status dot, a small title, one line of numbers."""
    theme.md(
        f"""<div class="ri-story-card">
            <div class="ri-story-eyebrow" style="color:{color};">{theme.dot(color)}{eyebrow}</div>
            <div class="ri-story-title">{title}</div>
            <div class="ri-story-stats">{stat_html}</div>
            <div class="ri-story-body">{objective}</div>
        </div>"""
    )
