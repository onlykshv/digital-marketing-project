"""Visual identity: one coherent design system reused across every page.

Palette is deliberately small: a dark navy for structural chrome, one accent for actions/
attention, and three semantic colors for risk (never reused elsewhere). No rainbow charts,
no gradients beyond a single flat header treatment, no glassmorphism, no hover animation on
static (non-interactive) elements.

Typographic hierarchy does most of the work: a hero number/line for the one thing a page needs
to say in five seconds, a quiet inline stat row for supporting numbers, ranked lists with large
faint numerals instead of another chart, and hairline dividers instead of another bordered card.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

COLORS = {
    "navy": "#0F2138",          # structural chrome: headers, selected nav, primary text accents
    "navy_soft": "#1D3A5F",     # secondary navy for supporting chrome
    "accent": "#C8722C",        # the ONE accent: actions, priority callouts, CTAs
    "high": "#C94A4A",          # High risk -- semantic only, never reused decoratively
    "medium": "#D69A3B",        # Medium risk
    "low": "#2E8B63",           # Low risk / positive
    "neutral": "#8992A3",       # muted grey for de-emphasized series/text
    "bg": "#F5F6F8",
    "card_border": "#E4E7EC",
    "text": "#1A2433",
    "text_muted": "#5C6675",
}

RISK_COLOR_MAP = {"Low": COLORS["low"], "Medium": COLORS["medium"], "High": COLORS["high"]}

# Passed to every st.plotly_chart call -- removes the toolbar clutter in the default view.
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

CHART_HEIGHT = 340
CHART_HEIGHT_LARGE = 440


def apply_page_style() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}

        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}

        .block-container {{
            padding-top: 1.75rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }}

        /* ---- Top navigation -- no sidebar anywhere in this app. Streamlit's native
               position="top" nav renders as a row of link-buttons in the header; restyled
               here as a quiet underline-on-active bar, not a row of filled pills. ---- */
        header[data-testid="stHeader"] {{
            background-color: white;
            border-bottom: 1px solid {COLORS['card_border']};
            height: 3.4rem;
        }}
        div[data-testid="stAppViewBlockContainer"] {{
            padding-top: 1.5rem;
        }}
        div[data-testid="stToolbar"] {{
            padding-left: 15.5rem;
        }}
        a[data-testid="stTopNavLink"] {{
            border-radius: 4px;
            font-size: 0.86rem;
            font-weight: 600;
            color: {COLORS['text_muted']} !important;
            padding: 0.4rem 0.7rem !important;
            border-bottom: 2px solid transparent;
            transition: color 0.16s ease, background-color 0.16s ease, border-color 0.16s ease;
        }}
        a[data-testid="stTopNavLink"]:hover {{
            background-color: {COLORS['bg']} !important;
            color: {COLORS['navy']} !important;
        }}
        a[data-testid="stTopNavLink"][aria-current="page"] {{
            background-color: transparent !important;
            color: {COLORS['navy']} !important;
            border-bottom: 2px solid {COLORS['accent']};
            font-weight: 700;
        }}
        /* Brand mark, injected via ::before on the header itself -- pure CSS, no JS, so it
           can never desync from a rerun. */
        header[data-testid="stHeader"]::before {{
            content: "KKBOX RETENTION INTELLIGENCE";
            position: absolute;
            left: 1.25rem;
            top: 0;
            height: 3.4rem;
            display: flex;
            align-items: center;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            color: {COLORS['navy']};
            pointer-events: none;
        }}

        /* ---- KPI metric widgets (used sparingly -- small, in-context numbers only) ---- */
        [data-testid="stMetric"] {{
            background-color: transparent;
            padding: 0;
        }}
        [data-testid="stMetricLabel"] {{
            font-weight: 600;
            font-size: 0.74rem;
            letter-spacing: 0.03em;
            color: {COLORS['text_muted']};
            text-transform: uppercase;
        }}
        [data-testid="stMetricValue"] {{
            color: {COLORS['text']};
            font-weight: 700;
        }}
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {{
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
            font-size: 1.4rem !important;
            line-height: 1.25 !important;
        }}

        /* ---- Page header -- editorial, box-free: oversized type on the page's own ground,
               not a colored block. The one full-color block (.hero-header) is reserved
               entirely for Command Center, so only one of five pages repeats that motif. ---- */
        .dash-header {{
            padding: 0 0 1.5rem 0;
            border-bottom: 1px solid {COLORS['card_border']};
            margin-bottom: 1.75rem;
        }}
        .dash-header .eyebrow {{
            color: {COLORS['accent']};
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }}
        .dash-header h1 {{
            color: {COLORS['navy']};
            margin: 0;
            font-size: 2.6rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.08;
        }}
        .dash-header p {{
            color: {COLORS['text_muted']};
            margin: 0.6rem 0 0 0;
            font-size: 1.02rem;
            max-width: 620px;
        }}

        /* ---- Hero header (Command Center only) -- the single colored block in the whole
               app, and one headline number instead of five KPI cards ---- */
        .hero-header {{
            padding: 1.5rem 1.7rem;
            background-color: {COLORS['navy']};
            border-bottom: 3px solid {COLORS['accent']};
            border-radius: 10px;
            margin-bottom: 1.5rem;
        }}
        .hero-header .eyebrow {{
            color: {COLORS['accent']};
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }}
        .hero-header .hero-line {{
            color: white;
            font-size: 2.05rem;
            font-weight: 800;
            letter-spacing: -0.015em;
            margin: 0.25rem 0 0.5rem 0;
            line-height: 1.18;
        }}
        .hero-header .hero-line .accent-num {{
            color: {COLORS['accent']};
        }}
        .hero-header .hero-sub {{
            color: #C3CCDA;
            font-size: 1rem;
            margin: 0;
            max-width: 640px;
        }}

        /* ---- Section headers ---- */
        .section-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: {COLORS['text']};
            margin: 0.3rem 0 0.15rem 0;
        }}
        .section-title .section-num {{
            color: {COLORS['neutral']};
            font-weight: 700;
            margin-right: 0.5rem;
        }}
        .section-subtitle {{
            font-size: 0.86rem;
            color: {COLORS['text_muted']};
            margin: 0 0 0.8rem 0;
        }}

        /* ---- Cards -- used only where something genuinely needs visual containment ---- */
        .card {{
            background: white;
            border: 1px solid {COLORS['card_border']};
            border-radius: 8px;
            padding: 1.1rem 1.3rem;
            margin-bottom: 0.85rem;
        }}
        .card.card-accent {{
            border-left: 3px solid {COLORS['accent']};
        }}
        .badge {{
            display: inline-block;
            padding: 0.16rem 0.55rem;
            border-radius: 4px;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }}

        /* ---- "So what" insight callouts ---- */
        .insight {{
            background: #FBF3EB;
            border-left: 3px solid {COLORS['accent']};
            border-radius: 4px;
            padding: 0.7rem 1rem;
            margin: 0.5rem 0 1.1rem 0;
            font-size: 0.9rem;
            color: {COLORS['text']};
        }}
        .insight b {{ color: {COLORS['navy']}; }}

        /* ---- Inline stat row -- quiet secondary numbers, not another KPI card ---- */
        .stat-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 2rem;
            margin: 0.9rem 0 1.3rem 0;
        }}
        .stat-row .stat-label {{
            color: {COLORS['text_muted']};
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.15rem;
        }}
        .stat-row .stat-value {{
            color: {COLORS['text']};
            font-size: 1.2rem;
            font-weight: 700;
        }}

        /* ---- Ranked list rows (drivers, priorities) -- numeral does the hierarchy work ---- */
        .rank-row {{
            display: flex;
            align-items: baseline;
            gap: 0.9rem;
            padding: 0.55rem 0;
            border-bottom: 1px solid {COLORS['card_border']};
        }}
        .rank-row:last-child {{ border-bottom: none; }}
        .rank-row .rank-num {{
            font-size: 1.4rem;
            font-weight: 800;
            color: {COLORS['card_border']};
            width: 2rem;
            flex-shrink: 0;
        }}

        /* ---- Hairline divider + de-emphasized text ---- */
        hr.divider {{
            border: none;
            border-top: 1px solid {COLORS['card_border']};
            margin: 0.9rem 0;
        }}
        .recede {{
            color: {COLORS['text_muted']};
            font-size: 0.88rem;
            margin: 0.4rem 0;
        }}

        details > summary {{ cursor: pointer; }}

        /* ---- Recommendation block -- an editorial directive, not another bordered card.
               Reserve for exactly one block per page: the single thing to act on. ---- */
        .recommendation-block {{
            border-left: 4px solid {COLORS['accent']};
            padding: 0.3rem 0 0.3rem 1.5rem;
            margin: 0.6rem 0 1.3rem 0;
        }}
        .recommendation-eyebrow {{
            color: {COLORS['accent']};
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }}
        .recommendation-title {{
            font-weight: 800;
            color: {COLORS['navy']};
            letter-spacing: -0.015em;
            line-height: 1.12;
            margin-bottom: 0.6rem;
        }}
        .recommendation-stats {{
            font-size: 0.95rem;
            color: {COLORS['text_muted']};
            margin-bottom: 0.8rem;
        }}
        .recommendation-stats b {{ color: {COLORS['text']}; }}
        .recommendation-action {{
            font-size: 1.08rem;
            color: {COLORS['text']};
        }}
        .recommendation-why {{
            font-size: 0.9rem;
            color: {COLORS['text_muted']};
            margin-top: 0.35rem;
        }}
        .recommendation-why b {{ color: {COLORS['text']}; }}

        /* ---- Profile panel (Customer 360) -- a distinct wrapper only so it can carry its own
               entrance transition when a customer is selected; no visual box of its own. ---- */
        .profile-panel {{ margin-top: 0.2rem; }}

        /* ---- CTA links (st.page_link) -- an arrow that nudges forward on hover instead of a
               filled button; used for every cross-page handoff in the app. ---- */
        a[data-testid="stPageLink-NavLink"] {{
            font-weight: 700 !important;
            transition: gap 0.15s ease, color 0.15s ease;
        }}
        a[data-testid="stPageLink-NavLink"]:hover {{
            color: {COLORS['navy']} !important;
        }}

        /* ---- Empty states -- tell the manager what to do next; never a blank block. ---- */
        .empty-state {{
            padding: 2.2rem 0 2.6rem 0;
            border-top: 1px solid {COLORS['card_border']};
            margin-top: 0.4rem;
        }}
        .empty-state-eyebrow {{
            color: {COLORS['accent']};
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.6rem;
        }}
        .empty-state-title {{
            color: {COLORS['navy']};
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: -0.01em;
            margin-bottom: 0.5rem;
        }}
        .empty-state-subtitle {{
            color: {COLORS['text_muted']};
            font-size: 0.95rem;
            max-width: 560px;
            line-height: 1.5;
        }}

        /* ---- Context strip (Retention Intelligence) -- a quiet, always-present indicator of
               who/what the assistant is currently grounded to. Not a card, not a banner --
               a thin tinted rule that reads as system state, not as decoration. ---- */
        .context-strip {{
            display: flex;
            align-items: center;
            gap: 0.6rem;
            background: {COLORS['bg']};
            border-left: 3px solid {COLORS['accent']};
            border-radius: 4px;
            padding: 0.55rem 0.9rem;
            margin: 0 0 1.1rem 0;
            font-size: 0.86rem;
            color: {COLORS['text']};
        }}
        .context-strip b {{ color: {COLORS['navy']}; }}
        .context-dot {{
            width: 7px; height: 7px; border-radius: 50%;
            background: {COLORS['low']}; flex-shrink: 0;
        }}

        /* ---- Question / answer distinction -- an editorial console, not chat bubbles. The
               question reads as a quiet label; the answer is the actual content. ---- */
        .qa-question {{
            color: {COLORS['text_muted']};
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin: 1.4rem 0 0.3rem 0;
        }}
        .qa-question-text {{
            color: {COLORS['navy']};
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 0.9rem;
        }}

        /* ---- Priority list rows (Retention Intelligence result presentation) -- compact,
               scannable, never a dataframe grid. ---- */
        .priority-row {{
            padding: 0.6rem 0;
            border-bottom: 1px solid {COLORS['card_border']};
        }}
        .priority-row:last-child {{ border-bottom: none; }}

        /* ---- Field status badge -- the one place motion is used to communicate importance
               (the primary risk x value field), a real DOM element with a restrained pulse,
               never an animation inside the chart itself. ---- */
        .field-status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 0.76rem;
            font-weight: 800;
            color: {COLORS['high']};
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0.1rem 0 0.9rem 0;
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: {COLORS['high']};
            flex-shrink: 0;
        }}

        /* ---- Motion -- short entrance transitions and a quiet hover response only;
               fully disabled for anyone who has asked for reduced motion. ---- */
        @media (prefers-reduced-motion: no-preference) {{
            @keyframes fieldFadeIn {{
                from {{ opacity: 0; transform: translateY(6px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            .dash-header, .hero-header, .recommendation-block, .card, .profile-panel {{
                animation: fieldFadeIn 0.4s ease-out;
            }}
            .card {{ transition: box-shadow 0.15s ease; }}
            .card:hover {{ box-shadow: 0 4px 16px rgba(15,33,56,0.10); }}

            a[data-testid="stPageLink-NavLink"]:hover {{
                text-decoration-thickness: 2px;
            }}

            @keyframes pulseDot {{
                0%, 100% {{ box-shadow: 0 0 0 0 rgba(201,74,74,0.45); }}
                50% {{ box-shadow: 0 0 0 6px rgba(201,74,74,0); }}
            }}
            .pulse-dot {{ animation: pulseDot 2.4s ease-in-out infinite; }}
        }}

        /* ---- Buttons + expanders -- quiet hover feedback, always on (not gated behind
               reduced-motion since these are simple color/elevation shifts, not movement). ---- */
        button[data-testid^="stBaseButton"] {{
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        }}
        button[data-testid^="stBaseButton"]:hover {{
            box-shadow: 0 3px 10px rgba(15,33,56,0.10);
        }}
        details[data-testid="stExpander"] summary {{
            transition: color 0.15s ease;
        }}
        details[data-testid="stExpander"] summary:hover {{
            color: {COLORS['accent']};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # One coherent chart language, applied globally so every chart on every page inherits it
    # without per-chart styling code -- restrained gridlines, consistent axis/tick treatment,
    # a quiet hover card, minimal legend. Presentation only: no chart's underlying data,
    # aggregation, or calculation is touched by this template.
    axis_style = dict(
        gridcolor=COLORS["card_border"],
        gridwidth=1,
        zeroline=False,
        showline=True,
        linecolor=COLORS["card_border"],
        linewidth=1,
        ticks="outside",
        tickcolor=COLORS["card_border"],
        ticklen=5,
        tickfont=dict(size=11, color=COLORS["text_muted"]),
        title=dict(font=dict(size=12, color=COLORS["text_muted"])),
    )
    template = go.layout.Template()
    template.layout.font = dict(family="Inter, -apple-system, sans-serif", size=12, color=COLORS["text"])
    template.layout.colorway = [
        COLORS["navy_soft"], COLORS["accent"], COLORS["low"], COLORS["medium"], COLORS["high"], COLORS["neutral"],
    ]
    template.layout.plot_bgcolor = "white"
    template.layout.paper_bgcolor = "white"
    template.layout.margin = dict(l=10, r=10, t=44, b=10)
    template.layout.title = dict(x=0, xanchor="left", y=0.96, yanchor="top", font=dict(size=14, color=COLORS["navy"]))
    template.layout.legend = dict(
        orientation="h", yanchor="bottom", y=1.06, xanchor="left", x=0,
        font=dict(size=11, color=COLORS["text_muted"]),
    )
    template.layout.xaxis = axis_style
    template.layout.yaxis = axis_style
    template.layout.hoverlabel = dict(
        bgcolor="white", bordercolor=COLORS["card_border"], font_size=12,
        font=dict(family="Inter, -apple-system, sans-serif"),
    )
    pio.templates["marketing"] = template
    pio.templates.default = "plotly_white+marketing"


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""<div class="dash-header">
            <div class="eyebrow">{eyebrow}</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def hero_header(eyebrow: str, headline_html: str, subtext: str) -> None:
    """The Command Center's header: one headline sentence with the number that matters
    emphasized inline (wrap it in <span class="accent-num">...</span>), not a title plus a
    row of equally-weighted KPI cards."""
    st.markdown(
        f"""<div class="hero-header">
            <div class="eyebrow">{eyebrow}</div>
            <div class="hero-line">{headline_html}</div>
            <p class="hero-sub">{subtext}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """A small uppercase label marking a shift in kind of content (e.g. 'model explanation' vs.
    'business recommendation') -- not a heading, just a signpost above one."""
    st.markdown(
        f'<div style="color:{COLORS["accent"]}; font-size:0.7rem; font-weight:800; '
        f'letter-spacing:0.12em; text-transform:uppercase; margin:1.3rem 0 0.3rem 0;">{text}</div>',
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None, number: str | None = None) -> None:
    num_html = f'<span class="section-num">{number}</span>' if number else ""
    st.markdown(f'<div class="section-title">{num_html}{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def stat_row(items: list[dict]) -> None:
    """Compact, non-card secondary numbers -- items: [{"label": str, "value": str}, ...].
    Use this instead of st.metric/KPI cards for anything that isn't the one number a page
    leads with."""
    cells = "".join(
        f'<div><div class="stat-label">{it["label"]}</div><div class="stat-value">{it["value"]}</div></div>'
        for it in items
    )
    st.markdown(f'<div class="stat-row">{cells}</div>', unsafe_allow_html=True)


def rank_row(rank: int, title: str, meta_html: str) -> None:
    """One row in a ranked list (churn drivers, priority segments) -- a large faint numeral
    replaces a badge/card as the hierarchy signal."""
    st.markdown(
        f"""<div class="rank-row">
            <div class="rank-num">{rank:02d}</div>
            <div><div style="font-weight:600; color:{COLORS['text']};">{title}</div>
            <div style="font-size:0.85rem; color:{COLORS['text_muted']};">{meta_html}</div></div>
        </div>""",
        unsafe_allow_html=True,
    )


def divider() -> None:
    st.markdown('<hr class="divider"/>', unsafe_allow_html=True)


def recede(html: str) -> None:
    """De-emphasized text for segments/states that deliberately should not draw the eye
    (e.g. 'Stable -- no action needed')."""
    st.markdown(f'<p class="recede">{html}</p>', unsafe_allow_html=True)


def badge(label: str, color: str) -> str:
    """A tinted outline chip -- returns HTML, doesn't render. Color still carries meaning
    (risk tier, intervention intensity) without the solid-fill "sticker" look."""
    return (
        f'<span class="badge" style="background:{color}1A; color:{color}; '
        f'border:1px solid {color}55;">{label}</span>'
    )


def empty_state(eyebrow_text: str, title: str, subtitle: str) -> None:
    """A state that always tells the manager what to do next -- never a blank block. Use for
    'nothing selected yet' / 'no matches' states instead of a bare recede() line or empty space."""
    st.markdown(
        f"""<div class="empty-state">
            <div class="empty-state-eyebrow">{eyebrow_text}</div>
            <div class="empty-state-title">{title}</div>
            <div class="empty-state-subtitle">{subtitle}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def context_strip(html: str, *, dot_color: str | None = None) -> None:
    """The quiet 'who/what am I currently grounded to' indicator used at the top of Retention
    Intelligence -- e.g. 'Analysing customer XXXX' or 'Segment: At-Risk Veteran'. Not a card, not
    an alert -- a thin tinted rule that reads as live system state."""
    dot = f'<span class="context-dot" style="background:{dot_color};"></span>' if dot_color else ""
    st.markdown(f'<div class="context-strip">{dot}{html}</div>', unsafe_allow_html=True)


def field_status_badge(text: str) -> None:
    """A small, real DOM element with a restrained pulse -- the one place in the app motion is
    used to communicate importance. Reserved for the primary risk x value field (Overview only);
    never applied inside a Plotly chart itself, so it can never desync from a chart re-render."""
    st.markdown(
        f'<div class="field-status-badge"><span class="pulse-dot"></span>{text}</div>',
        unsafe_allow_html=True,
    )


def insight(html: str) -> None:
    st.markdown(f'<div class="insight">{html}</div>', unsafe_allow_html=True)


def intensity_color(intensity: str) -> str:
    if "High-touch" in intensity:
        return COLORS["high"]
    if "Moderate" in intensity:
        return COLORS["medium"]
    if "Advocacy" in intensity or "Upsell" in intensity:
        return COLORS["navy_soft"]
    if "Low-cost" in intensity:
        return COLORS["accent"]
    return COLORS["neutral"]


def chart_layout(fig: go.Figure, height: int = CHART_HEIGHT, **kwargs) -> go.Figure:
    fig.update_layout(height=height, **kwargs)
    return fig


# ---------------------------------------------------------------------------
# Number formatting -- plain-English, not raw floats
# ---------------------------------------------------------------------------

def fmt_count(n: float) -> str:
    n = float(n)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


# ---------------------------------------------------------------------------
# Currency display -- NT$ -> INR
#
# Every HRR/revenue figure in outputs/*.csv and outputs/*.json is denominated in NT$ (New
# Taiwan Dollar), KKBox's native currency -- that data is never touched. This is a *display-only*
# conversion applied at render time, using one fixed rate rather than a live FX lookup, so figures
# stay reproducible run-to-run. To refresh it, change this single constant.
# ---------------------------------------------------------------------------

NTD_TO_INR = 2.62  # fixed display rate: 1 NT$ = INR 2.62 (not a live exchange rate)
CURRENCY_SYMBOL = "₹"  # INR sign


def to_inr(ntd_amount):
    """Convert an NT$ amount (scalar or pandas Series) to its INR display equivalent."""
    return ntd_amount * NTD_TO_INR


def from_inr(inr_amount):
    """Inverse of to_inr -- for converting an INR-space UI value back to NT$ before filtering."""
    return inr_amount / NTD_TO_INR


def fmt_currency(n: float) -> str:
    return f"{CURRENCY_SYMBOL}{fmt_count(to_inr(n))}"


# P1-15: some free-text fields sourced from outputs/*.csv (e.g. marketing_action_plan.csv's
# `rationale` column) are notebook-generated natural-language strings that embed a raw "<number>
# NT$" mention directly in the sentence -- written before this project's ₹ display convention
# existed, and outside the reach of fmt_currency() because they're prose, not a numeric field.
# Editing outputs/*.csv is out of scope (protected, and would be an analytical change to a
# generated file); this rewrites any such mention to the same ₹ figure fmt_currency() would show
# for that NT$ amount, at render time only -- the source file, and the number itself, are
# untouched.
_NTD_MENTION_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*NT\$")


def convert_ntd_mentions_in_text(text: str) -> str:
    """Rewrite every "<number> NT$" mention inside a free-text string into the ₹ figure
    fmt_currency() would show for that same NT$ amount. Display-only -- never call this on
    anything that will be re-parsed as a number afterward."""
    def _replace(match: "re.Match[str]") -> str:
        try:
            ntd_value = float(match.group(1).replace(",", ""))
        except ValueError:
            return match.group(0)
        return fmt_currency(ntd_value)
    return _NTD_MENTION_RE.sub(_replace, text)


def fmt_pct(n: float, decimals: int = 1) -> str:
    return f"{n:.{decimals}f}%"
