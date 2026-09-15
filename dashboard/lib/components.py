"""Reusable, higher-level UI blocks shared across pages.

Deliberately NOT another card library -- `recommendation_block` and `secondary_story` are the
two ways this dashboard shows "here's the one thing that matters" vs. "here's the smaller story
next to it," without falling back into a grid of equal-weight bordered boxes.
"""
from __future__ import annotations

import streamlit as st

from lib import theme


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
    """The single most important recommendation on a page -- deliberately NOT a bordered card.
    An oversized headline and a left accent rule read as an editorial directive ("do this"),
    not one box among several equal-weight boxes. Reserve for exactly one block per page.

    `why` is a short, always-visible one-line reason (a plain-English restatement of the
    segment's existing rule, not a causal claim). `rationale`, if given, is the longer,
    stats-bearing version, tucked into a "Why this recommendation?" expander for anyone who
    wants the detail.
    """
    color = theme.intensity_color(intensity)
    why_html = f'<div class="recommendation-why"><b>Why:</b> {why}</div>' if why else ""
    rationale_html = ""
    if rationale:
        # P1-15: `rationale` comes from outputs/marketing_action_plan.csv -- a notebook-generated
        # sentence that embeds a raw "<number> NT$" mention directly in the prose, predating this
        # project's ₹ display convention and untouched by fmt_currency() (which only formats
        # numeric fields, not free text). Rewritten here, at render time only, so this expander
        # never shows a manager the one raw NT$ figure left in the product.
        rationale_display = theme.convert_ntd_mentions_in_text(rationale)
        rationale_html = f"""
        <details style="margin-top:0.7rem;">
            <summary style="color:{theme.COLORS['accent']}; font-size:0.83rem; font-weight:600;">More detail on this recommendation</summary>
            <p style="margin:0.5rem 0 0 0; color:{theme.COLORS['text_muted']}; font-size:0.85rem; line-height:1.55; max-width:640px;">
                Based on observed historical association, not a causal guarantee: {rationale_display}
            </p>
        </details>
        """
    title_size = "2.1rem" if size == "large" else "1.5rem"
    st.markdown(
        f"""
        <div class="recommendation-block">
            <div class="recommendation-eyebrow">{eyebrow}</div>
            <div class="recommendation-title" style="font-size:{title_size};">{title}</div>
            <div class="recommendation-stats">{stat_html}</div>
            <div class="recommendation-action"><b>Do this:</b> {objective}</div>
            {why_html}
            <div style="margin-top:0.5rem;">{theme.badge(intensity, color)}</div>
            {rationale_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def copilot_answer_block(answer) -> None:
    """Renders a lib.copilot_engine.CopilotAnswer in the fixed decision format: RECOMMENDATION /
    WHY / EVIDENCE / WHAT TO DO / WHAT TO AVOID / CONFIDENCE-BASIS / CAUTION, plus a compact
    'Evidence used' source line. Deliberately not a chat bubble -- this is a decision card, meant
    to be scanned in seconds, not read as conversation."""
    st.markdown(
        f"""
        <div class="recommendation-block">
            <div class="recommendation-eyebrow">Recommendation</div>
            <div class="recommendation-title" style="font-size:1.35rem;">{answer.recommendation}</div>
            {f'<div class="recommendation-why" style="margin-top:0.5rem;"><b>Why:</b> {answer.why}</div>' if answer.why else ''}
        </div>
        """,
        unsafe_allow_html=True,
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
    """Compact, decision-focused customer list -- Customer / Risk / Value / Segment /
    Recommended action -- deliberately NOT a dataframe grid. Caps at `limit_shown` rows; the
    caller is expected to offer a "View all matching customers" deep link for anything beyond
    that (see pages/retention_copilot.py). Each row's "Open" action uses `st.switch_page` (a
    native, non-fragile Streamlit mechanism) to set the shared `cust360_search` session key and
    navigate -- the exact same mechanism already proven for Priority Customers' and Customer
    360's cross-page handoffs, not a new one.
    """
    for r in rows[:limit_shown]:
        c1, c2, c3, c4, c5 = st.columns([2.4, 0.9, 0.9, 1.7, 0.9])
        msno = r["msno"]
        with c1:
            short_id = msno if len(msno) <= 26 else msno[:26] + "…"
            st.markdown(
                f'<div style="font-weight:700; color:{theme.COLORS["navy"]}; font-size:0.9rem; word-break:break-all;">{short_id}</div>'
                f'<div style="font-size:0.78rem; color:{theme.COLORS["text_muted"]};">{r.get("key_risk_signal") or ""}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(theme.badge(r["risk_tier"] + " risk", theme.RISK_COLOR_MAP.get(r["risk_tier"], theme.COLORS["neutral"])), unsafe_allow_html=True)
        with c3:
            st.markdown(theme.badge(r["value_tier"] + " value", theme.COLORS["navy_soft"]), unsafe_allow_html=True)
        with c4:
            st.markdown(
                f'<div style="font-size:0.85rem; color:{theme.COLORS["text"]};">{r.get("recommended_action") or "—"}</div>'
                f'<div style="font-size:0.76rem; color:{theme.COLORS["text_muted"]};">{r.get("segment") or ""}</div>',
                unsafe_allow_html=True,
            )
        with c5:
            if st.button("Open →", key=f"priority_open_{msno}", width="stretch"):
                st.session_state["cust360_search"] = msno
                st.switch_page("pages/customer_360.py")


# The answer text `agent.py` produces always uses a small, known set of leading labels (see
# agent._render_copilot_answer / _format_aggregate_answer / _format_search_customers_answer /
# _format_rank_segments_answer) -- never invented per question type. Classifying by label name
# gives a real Finding/Evidence/Confidence visual hierarchy without parsing or re-deriving
# anything: the finding is the one line worth reading at a glance, the confidence/caution lines
# are real information that should stay visible but not compete with it.
_FINDING_LABELS = {"recommendation", "headline"}
_MUTED_LABELS = {"confidence/basis", "confidence", "caution", "confidence/limitations"}


def agent_response_block(response, *, show_results: bool = True) -> None:
    """Renders a `lib.agent.AgentResponse` for Retention Intelligence with a real Finding ->
    Evidence/Action -> Confidence/Caution visual hierarchy (already-structured plain text lines,
    never re-parsed or re-derived from raw data), a quiet provenance line (never chain-of-
    thought, never a raw tool/JSON dump -- see `lib.agent`'s own docstring on what `tool_calls`
    deliberately does not expose), and -- only when the underlying tool call actually returned
    one -- a compact priority list.

    Deliberately duck-typed (no `lib.agent` import here) so this module's dependency footprint
    stays exactly what it was before this page: `response` only needs `.answer`, `.tools_used`,
    `.used_llm`, `.grounded`, `.fallback_reason`, and `.tool_calls` (each with `.tool`, `.ok`,
    `.result`).
    """
    for line in response.answer.splitlines():
        line = line.strip()
        if not line:
            continue
        label, sep, rest = line.partition(":")
        label_key = label.strip().lower()
        if sep and label_key in _FINDING_LABELS:
            st.markdown(
                f'<div style="font-size:1.18rem; font-weight:700; color:{theme.COLORS["navy"]}; '
                f'line-height:1.35; margin:0.1rem 0 0.5rem 0;">{rest.strip()}</div>',
                unsafe_allow_html=True,
            )
        elif sep and label_key in _MUTED_LABELS:
            st.caption(f"{label.strip()}: {rest.strip()}")
        elif sep and 0 < len(label) < 40 and "[" not in label:
            st.markdown(f"**{label.strip()}:** {rest.strip()}")
        else:
            st.markdown(line)

    n_tools = len(set(response.tools_used))
    if response.used_llm and n_tools:
        st.caption(f"Grounded in {n_tools} analytical tool{'s' if n_tools != 1 else ''}.")
    elif response.used_llm:
        st.caption("AI-synthesized.")
    elif response.grounded:
        st.caption(f"Deterministic answer -- AI synthesis not used ({response.fallback_reason}).")
    elif response.fallback_reason:
        st.caption(f"AI synthesis unavailable ({response.fallback_reason}).")

    if not show_results:
        return

    for call in response.tool_calls:
        if call.tool == "search_customers" and call.ok:
            rows = (call.result.get("data") or {}).get("rows") or []
            total = (call.result.get("data") or {}).get("total_matches", len(rows))
            if rows:
                st.write("")
                priority_list(rows)
                if total > len(rows[:5]):
                    pending = {k: v for k, v in call.arguments.items() if k in ("risk_tier", "value_tier", "segment") and v}
                    if pending:
                        st.session_state["pending_filter"] = pending
                    st.page_link("pages/priority_customers.py", label=f"View all {total:,} matching customers →")
            break


def secondary_story(*, eyebrow: str, title: str, stat_html: str, objective: str, color: str) -> None:
    """A quiet, box-free 'second story' -- for content that should visibly recede next to a
    recommendation_block (e.g. Champions next to the top priority): smaller type, no border,
    no card, no badge-heavy chrome."""
    st.markdown(
        f"""
        <div style="padding:0.1rem 0 0.2rem 0;">
            <div style="color:{color}; font-size:0.68rem; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:0.35rem;">{eyebrow}</div>
            <div style="font-size:1.35rem; font-weight:700; color:{theme.COLORS['navy']}; margin-bottom:0.35rem; letter-spacing:-0.01em;">{title}</div>
            <div style="font-size:0.87rem; color:{theme.COLORS['text_muted']}; margin-bottom:0.55rem;">{stat_html}</div>
            <div style="font-size:0.92rem; color:{theme.COLORS['text']};">{objective}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
