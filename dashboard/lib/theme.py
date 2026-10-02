"""Visual identity: one design system reused across every page.

KKBOX Retention Intelligence uses a calm, dark "command dashboard" layout (adapted from the Romer
SaaS template on Stitch): a fixed left navigation rail, a page title with one line of context, at
most three stat cards, one main panel and one side panel. Everything else -- scores, model detail,
methodology -- sits behind a "Details" toggle, so the first read of every page is plain marketing
language and a handful of numbers.

Principles (in priority order):
1. Few things on screen. One question per page, up to three headline numbers, one main object.
2. Colour means something. Surfaces are near-black steps; the only bright elements are small
   status dots and badges -- coral for high risk, amber for medium, green for low -- plus one
   indigo for actions and one cyan for the active place in the app.
3. Hierarchy through type and spacing, not boxes on boxes: Manrope headings with tight tracking,
   Inter for everything else, uppercase tracked labels for panel titles.

Every formatting helper at the bottom of this module is part of the analytical contract (the
agent, the tests and every page format money/counts through them) and is intentionally unchanged.
"""
from __future__ import annotations

import html as _html
import re

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

COLORS = {
    # structure (dark)
    "ink": "#F0F1F2",           # strongest text
    "ink_2": "#C9CBD0",
    "ink_3": "#4A4D55",
    "paper": "#0A0A0B",         # page
    "surface": "#111214",       # panels
    "surface_2": "#16171A",     # raised / hover
    "rule": "#1E1F22",
    "rule_strong": "#2A2B2F",
    "text": "#E3E4E7",
    "text_muted": "#9A9DA3",
    "text_faint": "#6B6E76",
    # semantics
    "accent": "#5563F5",        # action: primary buttons, selection
    "accent_ink": "#7A85FF",
    "accent_soft": "rgba(94,107,255,0.14)",
    "accent_on_dark": "#8B95FF",
    "cyan": "#50D8E9",          # where you are: active navigation, live state
    "high": "#FF7B6E",          # high risk
    "high_text": "#FF8F84",
    "high_soft": "rgba(255,123,110,0.12)",
    "medium": "#F5A524",        # elevated risk
    "medium_text": "#F7B955",
    "medium_soft": "rgba(245,165,36,0.12)",
    "low": "#3DD68C",           # stable / low risk / growth
    "low_text": "#5BE0A0",
    "low_soft": "rgba(61,214,140,0.12)",
    "neutral": "#6B6E76",       # no action, de-emphasised series
    "info": "#8A8F98",          # methodology / confidence
    # aliases kept for existing call sites
    "navy": "#F0F1F2",
    "navy_soft": "#4A4D55",
    "bg": "#0A0A0B",
    "card_border": "#1E1F22",
}

RISK_COLOR_MAP = {"Low": COLORS["low"], "Medium": COLORS["medium"], "High": COLORS["high"]}
RISK_TEXT_COLOR_MAP = {"Low": COLORS["low_text"], "Medium": COLORS["medium_text"], "High": COLORS["high_text"]}

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

CHART_HEIGHT = 340
CHART_HEIGHT_LARGE = 440

# The product's journey, in navigation order. Used by every page's "next step" row so the six
# pages read as one sequence rather than six unrelated screens.
JOURNEY = [
    {"step": "01", "stage": "Predict", "page": "pages/overview.py", "name": "Overview", "question": "Where should KKBOX act?"},
    {"step": "02", "stage": "Prioritize", "page": "pages/priority_customers.py", "name": "Priority Customers", "question": "Who should we save?"},
    {"step": "03", "stage": "Prioritize", "page": "pages/customer_value.py", "name": "Customer Value", "question": "Who is worth saving?"},
    {"step": "04", "stage": "Act", "page": "pages/action_center.py", "name": "Action Center", "question": "What should we do?"},
    {"step": "05", "stage": "Act", "page": "pages/customer_360.py", "name": "Customer 360", "question": "What should we do for this customer?"},
    {"step": "06", "stage": "Why", "page": "pages/retention_copilot.py", "name": "Retention Intelligence", "question": "Why? Ask the intelligence layer."},
]

_FONTS = (
    "https://fonts.googleapis.com/css2?family=Manrope:wght@400..700"
    "&family=Inter:wght@400;500;600&display=swap"
)

_TOKENS = f"""
:root {{
  --bg: {COLORS['paper']}; --rail: #070708; --panel: {COLORS['surface']}; --panel-2: {COLORS['surface_2']}; --sunken: #0D0E10;
  --line: {COLORS['rule']}; --line-2: {COLORS['rule_strong']};
  --text: {COLORS['text']}; --strong: {COLORS['ink']}; --muted: {COLORS['text_muted']}; --faint: {COLORS['text_faint']};
  --accent: {COLORS['accent']}; --accent-2: {COLORS['accent_ink']}; --accent-soft: {COLORS['accent_soft']}; --accent-text: {COLORS['accent_on_dark']};
  --cyan: {COLORS['cyan']};
  --high: {COLORS['high']}; --high-text: {COLORS['high_text']}; --high-soft: {COLORS['high_soft']};
  --medium: {COLORS['medium']}; --medium-text: {COLORS['medium_text']}; --medium-soft: {COLORS['medium_soft']};
  --low: {COLORS['low']}; --low-text: {COLORS['low_text']}; --low-soft: {COLORS['low_soft']};
  --neutral: {COLORS['neutral']}; --info: {COLORS['info']};
  --head: 'Manrope', 'Inter', 'Segoe UI', system-ui, sans-serif;
  --sans: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  --mono: 'Inter', 'Segoe UI', sans-serif;
}}
"""

# Plain (non f-string) stylesheet: every value comes from the custom properties above.
_CSS = """
/* ============================== base ============================== */
html, body, .stApp, [data-testid="stAppViewContainer"] { background: var(--bg); }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button { font-family: var(--sans); }
.stApp { color: var(--text); }
.stApp ::selection { background: rgba(94,107,255,0.35); }
[data-testid="stHeaderActionElements"], [data-testid="stDecoration"], #MainMenu, [data-testid="stMainMenu"],
[data-testid="stAppDeployButton"], footer { display: none !important; }
header[data-testid="stHeader"] { background: transparent; height: 2.75rem; }
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 1280px; padding-top: 2.4rem; padding-bottom: 4rem; padding-left: 2.6rem; padding-right: 2.6rem;
}
[data-testid="stMarkdownContainer"] p { line-height: 1.55; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--faint); font-size: 0.8rem; line-height: 1.5; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: var(--head); letter-spacing: -0.03em; color: var(--strong); }

/* ============================== app shell: the left navigation rail ============================== */
section[data-testid="stSidebar"] { background: var(--rail); border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0.4rem; }
[data-testid="stSidebarNav"]::before {
  content: "KKBOX\\A Retention Intelligence"; white-space: pre; display: block;
  font: 600 1.02rem/1.25 var(--head); letter-spacing: -0.02em; color: var(--strong);
  padding: 0.2rem 1rem 1.5rem 3.25rem; margin-top: -2.2rem; margin-bottom: 0.4rem;
  border-bottom: 1px solid var(--line); position: relative;
}
[data-testid="stSidebarNav"]::after {
  content: "KK"; position: absolute; left: 1rem; top: 0.35rem; width: 1.75rem; height: 1.75rem; border-radius: 6px;
  background: var(--cyan); color: #06222A; font: 700 0.72rem/1.75rem var(--head); text-align: center;
}
[data-testid="stSidebarNav"] { position: relative; padding-top: 2.4rem; }
a[data-testid="stSidebarNavLink"] { border-radius: 0; padding: 0.55rem 1rem !important; margin: 1px 0; position: relative; align-items: center; transition: background-color .15s ease, color .15s ease; }
a[data-testid="stSidebarNavLink"] span[label] p { font: 500 0.74rem var(--sans) !important; letter-spacing: 0.11em; text-transform: uppercase; color: var(--muted) !important; }
a[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] { color: var(--faint) !important; }
a[data-testid="stSidebarNavLink"]:hover { background: var(--panel) !important; }
a[data-testid="stSidebarNavLink"]:hover span[label] p, a[data-testid="stSidebarNavLink"]:hover [data-testid="stIconMaterial"] { color: var(--strong) !important; }
a[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--panel) !important; box-shadow: inset -2px 0 0 var(--cyan); outline: none; }
a[data-testid="stSidebarNavLink"][aria-current="page"] span[label] p, a[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] { color: var(--cyan) !important; }
.rb-side { border-top: 1px solid var(--line); margin-top: 1.2rem; padding-top: 1rem; font-size: 0.78rem; color: var(--faint); line-height: 1.5; }
.rb-side .row { display: flex; align-items: center; gap: 0.5rem; color: var(--muted); margin-bottom: 0.35rem; }
.rb-side .row i { width: 6px; height: 6px; border-radius: 50%; background: var(--low); display: inline-block; }

/* ============================== page header ============================== */
.ri-mast { display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem; padding: 0 0 1.6rem 0; }
.ri-eyeline { font: 500 0.7rem var(--sans); letter-spacing: 0.14em; text-transform: uppercase; color: var(--faint); margin-bottom: 0.6rem; }
.ri-display { font: 520 3rem/1.05 var(--head); letter-spacing: -0.05em; color: var(--strong); margin: 0; text-wrap: balance; }
.ri-deck { font-size: 1.02rem; line-height: 1.5; color: var(--muted); max-width: 44rem; margin: 0.7rem 0 0 0; }
.ri-stats { display: flex; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); flex-shrink: 0; }
.ri-stats > div { padding: 0.8rem 1.3rem; }
.ri-stats > div + div { border-left: 1px solid var(--line); }
.ri-stats .l { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); }
.ri-stats .v { font: 520 1.75rem/1.1 var(--head); letter-spacing: -0.03em; color: var(--strong); margin-top: 0.35rem; font-variant-numeric: tabular-nums; display: flex; align-items: center; gap: 0.5rem; }
.ri-stats .v i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }

/* ============================== sections & panels ============================== */
.ri-sec { display: flex; align-items: baseline; gap: 1rem; margin: 2.2rem 0 0.8rem 0; }
.ri-sec-title { font: 520 1.35rem/1.2 var(--head); letter-spacing: -0.03em; color: var(--strong); }
.ri-sec-note { margin-left: auto; font-size: 0.84rem; color: var(--faint); max-width: 32rem; text-align: right; line-height: 1.45; }
.ri-sec-num { display: none; }
.ri-eyebrow { font: 500 0.68rem/1.2 var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); margin: 1.1rem 0 0.5rem 0; }
.section-title { font: 520 1.1rem/1.3 var(--head); letter-spacing: -0.02em; color: var(--strong); margin: 0.2rem 0 0.3rem 0; }
.section-subtitle { font-size: 0.86rem; color: var(--muted); margin: 0 0 0.8rem 0; }

[class*="st-key-rp_"] { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 0 1.15rem 1.1rem 1.15rem; gap: 0.75rem; }
.rp-h { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0 -1.15rem 0.2rem -1.15rem; padding: 0.95rem 1.15rem 0.85rem 1.15rem; border-bottom: 1px solid var(--line); }
.rp-h .t { font: 500 0.72rem var(--sans); letter-spacing: 0.14em; text-transform: uppercase; color: var(--strong); display: flex; align-items: center; gap: 0.6rem; }
.rp-h .t i { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.rp-h .r { font-size: 0.78rem; color: var(--faint); text-align: right; }

/* ============================== stat cards (KPI row) ============================== */
.ri-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 1rem; margin: 0.2rem 0 0.4rem 0; }
.ri-kpi { position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1.1rem 1.2rem 1.15rem 1.2rem; }
.ri-kpi-label { font: 500 0.7rem/1.3 var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); padding-right: 1rem; }
.ri-kpi-dot { position: absolute; top: 1.2rem; right: 1.2rem; width: 6px; height: 6px; border-radius: 50%; }
.ri-kpi-value { font: 520 2.2rem/1.1 var(--head); letter-spacing: -0.05em; color: var(--strong); font-variant-numeric: tabular-nums; margin-top: 0.7rem; }
.ri-kpi-value.sm { font-size: 1.25rem; line-height: 1.3; letter-spacing: -0.02em; }
.ri-kpi-note { font-size: 0.84rem; color: var(--muted); margin-top: 0.45rem; line-height: 1.4; }

/* ============================== badges & dots ============================== */
.ri-chip { display: inline-flex; align-items: center; gap: 0.4rem; white-space: nowrap; font: 500 0.72rem/1 var(--sans);
  color: var(--ink-2, #C9CBD0); background: var(--panel-2); border: 1px solid var(--line-2); border-radius: 4px;
  padding: 0.3rem 0.5rem; margin: 0 0.3rem 0.3rem 0; vertical-align: middle; }
.ri-chip i { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.ri-chip.dark { background: var(--panel-2); }
.ri-badge { display: inline-block; font: 600 0.64rem/1 var(--sans); letter-spacing: 0.08em; text-transform: uppercase; padding: 0.3rem 0.45rem; border-radius: 3px; }
.ri-badge.High { background: rgba(214,52,40,0.55); color: #FFE3DF; }
.ri-badge.Medium { background: rgba(245,165,36,0.18); color: var(--medium-text); }
.ri-badge.Low { background: rgba(61,214,140,0.14); color: var(--low-text); }
.ri-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }

/* ============================== status list (side panels) ============================== */
.ri-list > div { display: flex; align-items: center; gap: 0.7rem; padding: 0.7rem 0; border-bottom: 1px solid var(--line); font-size: 0.9rem; color: var(--text); }
.ri-list > div:last-child { border-bottom: none; }
.ri-list .nm { flex: 1; min-width: 0; }
.ri-list .nm small { display: block; font-size: 0.76rem; color: var(--faint); margin-top: 0.1rem; }
.ri-list .rt { text-align: right; font-size: 0.84rem; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
.ri-list .rt b { color: var(--strong); font-weight: 600; }
.ri-list > div.hot { background: rgba(255,123,110,0.07); margin: 0 -1.15rem; padding-left: 1.15rem; padding-right: 1.15rem; }
.ri-list > div.hot .nm { color: var(--high-text); }
.ri-list > div.mute .nm, .ri-list > div.mute .rt { color: var(--faint); }

/* ============================== buttons, links, inputs, expanders ============================== */
button[data-testid^="stBaseButton"] { transition: background-color .15s ease, border-color .15s ease, color .15s ease; }
button[data-testid="stBaseButton-secondary"] { background: transparent; border: 1px solid var(--line-2); color: var(--text); }
button[data-testid="stBaseButton-secondary"]:hover { background: var(--panel-2); border-color: #3A3B40; color: var(--strong); }
button[data-testid="stBaseButton-secondary"]:focus:not(:active) { border-color: var(--accent); color: var(--strong); }
button[data-testid="stBaseButton-primary"] { background: var(--accent); border: 1px solid var(--accent); color: #FFFFFF; }
button[data-testid="stBaseButton-primary"]:hover { background: #6673FF; border-color: #6673FF; }
button[data-testid="stBaseButton-tertiary"] { color: var(--accent-text); padding-left: 0; padding-right: 0; }
button[data-testid^="stBaseButton"] p { font-weight: 500; font-size: 0.88rem; }
a[data-testid="stPageLink-NavLink"] { padding-left: 0; }
a[data-testid="stPageLink-NavLink"] p, a[data-testid="stPageLink-NavLink"] span { color: var(--accent-text) !important; font-weight: 500 !important; font-size: 0.9rem; }
a[data-testid="stPageLink-NavLink"]:hover { background: transparent !important; }
a[data-testid="stPageLink-NavLink"]:hover p { text-decoration: underline; text-underline-offset: 3px; }
[data-testid="stDownloadButton"] button { background: transparent; border: 1px solid var(--line-2); }
[data-testid="stWidgetLabel"] p { font: 500 0.68rem var(--sans) !important; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted) !important; }
[data-testid="stExpander"] details { border: 1px solid var(--line); border-radius: 8px; background: var(--sunken); }
[data-testid="stExpander"] summary p { font-weight: 500; font-size: 0.88rem; color: var(--muted); }
[data-testid="stExpander"] summary:hover p, [data-testid="stExpander"] summary:hover svg { color: var(--strong); fill: var(--strong); }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
[data-testid="stSpinner"] p { font-size: 0.82rem; color: var(--muted); }

/* ============================== quiet text, callouts, empty states ============================== */
hr.divider { border: none; border-top: 1px solid var(--line); margin: 1.6rem 0 0 0; }
[class*="st-key-rp_"] [data-testid="stPageLink"] { margin-top: 0.9rem; }
.recede { color: var(--faint); font-size: 0.86rem; margin: 0.3rem 0; line-height: 1.5; }
.insight { color: var(--muted); font-size: 0.9rem; line-height: 1.55; margin: 0.6rem 0; max-width: 52rem; }
.insight b { color: var(--strong); font-weight: 600; }
.ri-note { font-size: 0.78rem; color: var(--info); line-height: 1.5; margin-top: 0.5rem; }
.ri-note b { color: var(--text); font-weight: 600; }
.ri-handoff { display: inline-flex; align-items: center; gap: 0.7rem; background: var(--accent-soft); border: 1px solid rgba(94,107,255,0.35);
  border-radius: 6px; padding: 0.45rem 0.8rem; margin: 0 0 0.9rem 0; font-size: 0.85rem; color: var(--text); }
.ri-handoff .k { font: 600 0.64rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-text); }
.ri-gap-note { display: flex; gap: 0.6rem; align-items: baseline; background: var(--medium-soft); border-radius: 6px; padding: 0.55rem 0.75rem; font-size: 0.8rem; line-height: 1.45; color: var(--text); margin: 0.6rem 0 0.2rem 0; }
.ri-gap-note .k { font: 600 0.62rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--medium-text); white-space: nowrap; }
.empty-state { padding: 2rem 1.5rem; border: 1px dashed var(--line-2); border-radius: 8px; margin-top: 0.4rem; background: var(--sunken); }
.empty-state-eyebrow { font: 500 0.68rem var(--sans); letter-spacing: 0.14em; text-transform: uppercase; color: var(--cyan); margin-bottom: 0.7rem; }
.empty-state-title { font: 520 1.6rem/1.2 var(--head); letter-spacing: -0.04em; color: var(--strong); margin-bottom: 0.5rem; }
.empty-state-subtitle { color: var(--muted); font-size: 0.93rem; max-width: 40rem; line-height: 1.55; }

/* ============================== recommendation (the one directive on a panel) ============================== */
.recommendation-block { padding: 0; margin: 0.2rem 0 1.1rem 0; }
.recommendation-eyebrow { font: 500 0.68rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.5rem; }
.recommendation-title { font: 520 1.8rem/1.1 var(--head); letter-spacing: -0.04em; color: var(--strong); margin-bottom: 0.5rem; }
.recommendation-stats { font-size: 0.92rem; color: var(--muted); margin-bottom: 0.9rem; }
.recommendation-stats b { color: var(--strong); font-weight: 600; font-variant-numeric: tabular-nums; }
.recommendation-action { font-size: 1rem; color: var(--strong); line-height: 1.5; background: var(--sunken); border: 1px solid var(--line); border-left: 2px solid var(--accent); border-radius: 6px; padding: 0.75rem 0.9rem; }
.recommendation-action b { display: block; font: 600 0.64rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--accent-text); margin-bottom: 0.3rem; }
.recommendation-why { font-size: 0.88rem; color: var(--muted); margin-top: 0.6rem; }
.recommendation-why b { color: var(--text); font-weight: 600; }
.ri-disclosure { margin-top: 0.7rem; }
.ri-disclosure summary { cursor: pointer; color: var(--muted); font-size: 0.82rem; font-weight: 500; list-style: none; }
.ri-disclosure summary:hover { color: var(--strong); }
.ri-disclosure summary::-webkit-details-marker { display: none; }
.ri-disclosure summary::before { content: "+ "; }
.ri-disclosure[open] summary::before { content: "\\2212  "; }
.ri-disclosure p { margin: 0.5rem 0 0 0; color: var(--faint); font-size: 0.84rem; line-height: 1.55; max-width: 44rem; }
.ri-story-card { padding: 0.2rem 0; }
.ri-story-eyebrow { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; margin-bottom: 0.35rem; display: flex; align-items: center; gap: 0.45rem; }
.ri-story-title { font: 520 1.2rem/1.2 var(--head); letter-spacing: -0.03em; color: var(--strong); margin-bottom: 0.3rem; }
.ri-story-stats { font-size: 0.86rem; color: var(--muted); margin-bottom: 0.4rem; }
.ri-story-stats b { color: var(--strong); font-weight: 600; font-variant-numeric: tabular-nums; }
.ri-story-body { font-size: 0.88rem; color: var(--muted); line-height: 1.5; }

/* ============================== next step ============================== */
.st-key-ri_upnext { border-top: 1px solid var(--line); padding-top: 1.2rem; margin-top: 2.4rem; }
.ri-upnext .k { font: 500 0.68rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); }
.ri-upnext .q { font: 520 1.15rem/1.3 var(--head); color: var(--strong); letter-spacing: -0.02em; margin-top: 0.2rem; }

/* ============================== context strip ("in focus") ============================== */
.context-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 0.65rem; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 0.7rem 1rem; margin: 0 0 0.4rem 0; font-size: 0.9rem; color: var(--text); }
.context-strip b { color: var(--strong); font-weight: 600; font-variant-numeric: tabular-nums; }
.context-strip .k { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); }
.context-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

/* ============================== Q/A ============================== */
.qa-question { font: 500 0.68rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); margin: 0.9rem 0 0.35rem 0; }
.qa-question-text { font: 520 1.5rem/1.25 var(--head); letter-spacing: -0.035em; color: var(--strong); margin-bottom: 0.4rem; }
.profile-panel { margin-top: 0.1rem; }

/* ============================== data bands, ranked bars ============================== */
.ri-band { display: flex; height: 0.7rem; width: 100%; border-radius: 3px; overflow: hidden; background: var(--line); gap: 2px; }
.ri-band > div { height: 100%; min-width: 2px; }
.ri-band > div span { display: none; }
.ri-legend { display: flex; flex-wrap: wrap; gap: 0.4rem 1.4rem; margin-top: 0.7rem; }
.ri-legend div { display: flex; align-items: center; gap: 0.45rem; font-size: 0.82rem; color: var(--muted); }
.ri-legend i { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.ri-legend b { color: var(--strong); font-variant-numeric: tabular-nums; font-weight: 600; }
.ri-legend .hot b { color: var(--high-text); }
.ri-rank { display: flex; align-items: center; gap: 0.9rem; padding: 0.55rem 0; border-bottom: 1px solid var(--line); }
.ri-rank:last-child { border-bottom: none; }
.ri-rank .n { font-size: 0.76rem; color: var(--faint); width: 1.4rem; flex-shrink: 0; }
.ri-rank .body { flex: 1; min-width: 0; }
.ri-rank .top { display: flex; justify-content: space-between; gap: 1rem; font-size: 0.9rem; color: var(--text); margin-bottom: 0.35rem; }
.ri-rank .top span:last-child { font-size: 0.78rem; color: var(--faint); }
.ri-rank .track { height: 4px; background: var(--line); border-radius: 2px; overflow: hidden; }
.ri-rank .fill { height: 100%; background: var(--line-2); }
.ri-rank.lead .fill { background: var(--accent); }

/* ============================== motion: short entrances only, off under reduced motion ============================== */
@media (prefers-reduced-motion: no-preference) {
  @keyframes riRise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  @keyframes riGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
  .ri-kpi, [class*="st-key-rp_"] { animation: riRise .35s ease-out both; }
  .ri-kpi:nth-child(2) { animation-delay: .05s; } .ri-kpi:nth-child(3) { animation-delay: .1s; }
  .ri-funnel .bar i { transform-origin: left; animation: riGrow .7s cubic-bezier(.2,.7,.2,1) both; }
}
"""


def _leave_legacy_page_mode() -> None:
    """Hand a page opened by direct URL back to app.py's navigation.

    Streamlit keeps a process-wide flag (`PagesManager.uses_pages_directory`) that starts True
    whenever a `pages/` folder exists and only turns False once app.py calls `st.navigation`. If the
    very first request after a server start is a sub-page URL (a bookmark or a refresh), Streamlit's
    legacy mode runs that page file directly -- app.py never runs, and the sidebar shows raw file
    names instead of the app's navigation for every session until someone opens the root URL.
    Clearing the flag and rerunning makes that same request go through app.py like every other.
    Internal attribute, verified against the pinned streamlit==1.63.0 (runtime/pages_manager.py,
    scriptrunner/script_runner.py); a no-op if it is ever absent.
    """
    try:
        from streamlit.runtime.pages_manager import PagesManager
    except ImportError:  # pragma: no cover -- a future Streamlit without this internal
        return
    if getattr(PagesManager, "uses_pages_directory", False):
        PagesManager.uses_pages_directory = False
        st.rerun()


def apply_page_style() -> None:
    _leave_legacy_page_mode()
    st.markdown(
        f"<style>@import url('{_FONTS}');{_TOKENS}{_CSS}{_COMPONENT_CSS}</style>",
        unsafe_allow_html=True,
    )
    sidebar_footer()
    _register_plotly_template()


def _register_plotly_template() -> None:
    # One chart language for every figure -- presentation only; no chart's data, aggregation or
    # calculation is touched by this template.
    axis = dict(
        gridcolor=COLORS["rule"], gridwidth=1, zeroline=False, showline=False,
        ticks="", tickfont=dict(size=11, color=COLORS["text_faint"], family="Inter, Segoe UI, sans-serif"),
        title=dict(font=dict(size=11, color=COLORS["text_muted"], family="Inter, Segoe UI, sans-serif"), standoff=12),
        automargin=True,
    )
    template = go.layout.Template()
    template.layout.font = dict(family="Inter, Segoe UI, sans-serif", size=12, color=COLORS["text"])
    template.layout.colorway = [
        COLORS["accent"], COLORS["high"], COLORS["medium"], COLORS["low"], COLORS["neutral"], COLORS["cyan"],
    ]
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.margin = dict(l=8, r=8, t=24, b=8)
    template.layout.title = dict(x=0, xanchor="left", font=dict(size=13, color=COLORS["ink"]))
    template.layout.legend = dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=11, color=COLORS["text_muted"]), bgcolor="rgba(0,0,0,0)",
    )
    template.layout.xaxis = axis
    template.layout.yaxis = axis
    template.layout.hoverlabel = dict(
        bgcolor="#1A1B1E", bordercolor="#2A2B2F", align="left",
        font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#F0F1F2"),
    )
    pio.templates["retention"] = template
    pio.templates.default = "plotly_dark+retention"


def squash(html_str: str) -> str:
    """Collapse a multi-line HTML snippet onto one line. Markdown ends a raw-HTML block at the first
    blank line and renders any 4-space-indented line after it as a code block -- so an optional
    fragment that renders empty inside an indented f-string would otherwise leak literal markup."""
    return " ".join(line.strip() for line in html_str.splitlines() if line.strip())


def md(html_str: str) -> None:
    """Render a raw HTML snippet (squashed -- see `squash`)."""
    st.markdown(squash(html_str), unsafe_allow_html=True)


def plot(fig: go.Figure, *, key: str | None = None, **kwargs):
    """Render a Plotly figure with the product's own template (not Streamlit's chart theme, which
    would override fonts and colours) and without the Plotly toolbar. Backgrounds are set on the
    figure itself because the frontend otherwise fills them from the app theme."""
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, theme=None, key=key, **kwargs)


# ---------------------------------------------------------------------------
# Page structure
# ---------------------------------------------------------------------------

def _journey_entry(page: str) -> dict:
    return next(j for j in JOURNEY if j["page"] == page)


def masthead(page: str, eyebrow: str, title: str, deck: str, *, aside_value: str | None = None,
             aside_label: str | None = None, stats: list[dict] | None = None) -> None:
    """The top of every page: a small label, the one question the page answers, one sentence of
    context, and optionally a compact stat group on the right -- stats: [{"label", "value", "dot"?}]
    (the older single `aside_value` / `aside_label` pair is still accepted)."""
    _journey_entry(page)  # keeps every page registered in JOURNEY
    if stats is None and aside_value:
        stats = [{"label": aside_label or "", "value": aside_value}]
    stats_html = ""
    if stats:
        cells = []
        for s in stats:
            dot_html = f'<i style="background:{s["dot"]};"></i>' if s.get("dot") else ""
            cells.append(f'<div><div class="l">{s["label"]}</div><div class="v">{dot_html}{s["value"]}</div></div>')
        stats_html = f'<div class="ri-stats">{"".join(cells)}</div>'
    md(
        f"""<div class="ri-mast">
            <div><div class="ri-eyeline">{eyebrow}</div><div class="ri-display">{title}</div><p class="ri-deck">{deck}</p></div>
            {stats_html}
        </div>"""
    )


def section_header(title: str, *, num: str | None = None, note: str | None = None) -> None:
    """A section title between panels -- a heading and an optional one-line note on the right."""
    note_html = f'<span class="ri-sec-note">{note}</span>' if note else ""
    st.markdown(f'<div class="ri-sec"><span class="ri-sec-title">{title}</span>{note_html}</div>', unsafe_allow_html=True)


def panel_head(title: str, *, right: str | None = None, dot: str | None = None) -> None:
    """The header row of a panel (call first inside an `st.container(key="rp_...")`): an uppercase
    tracked title, an optional status dot, and optional quiet text on the right."""
    dot_html = f'<i style="background:{dot};"></i>' if dot else ""
    right_html = f'<span class="r">{right}</span>' if right else ""
    st.markdown(f'<div class="rp-h"><span class="t">{dot_html}{title}</span>{right_html}</div>', unsafe_allow_html=True)


def journey_next(current_page: str, *, key: str) -> None:
    """A quiet 'next step' row at the end of a page, so the demo reads as one journey."""
    idx = next(i for i, j in enumerate(JOURNEY) if j["page"] == current_page)
    if idx + 1 >= len(JOURNEY):
        return
    nxt = JOURNEY[idx + 1]
    with st.container(key="ri_upnext"):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
        with c1:
            st.markdown(
                f'<div class="ri-upnext"><div class="k">Next step</div><div class="q">{nxt["question"]}</div></div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button(f"Continue to {nxt['name']} →", key=key, width="stretch"):
                st.switch_page(nxt["page"])


def sidebar_footer() -> None:
    """A quiet status note under the navigation rail -- what every number in the app rests on."""
    st.sidebar.markdown(
        '<div class="rb-side"><div class="row"><i></i>Model validated on future data</div>'
        "Built on KKBOX's subscriber history. Revenue shown in ₹.</div>",
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    """A small uppercase label marking a shift in kind of content -- a signpost, not a heading."""
    st.markdown(f'<div class="ri-eyebrow">{text}</div>', unsafe_allow_html=True)


def section(title: str, subtitle: str | None = None, number: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def kpi_strip(items: list[dict]) -> None:
    """A row of stat cards -- items: [{"label", "value", "note"?, "small"?, "dot"?, "note_color"?}].
    At most three or four per page: the headline numbers, nothing else."""
    cells = []
    for it in items:
        dot = f'<span class="ri-kpi-dot" style="background:{it["dot"]};"></span>' if it.get("dot") else ""
        note_style = f' style="color:{it["note_color"]};"' if it.get("note_color") else ""
        note = f'<div class="ri-kpi-note"{note_style}>{it["note"]}</div>' if it.get("note") else ""
        size = " sm" if it.get("small") else ""
        cells.append(
            f'<div class="ri-kpi">{dot}<div class="ri-kpi-label">{it["label"]}</div>'
            f'<div class="ri-kpi-value{size}">{it["value"]}</div>{note}</div>'
        )
    st.markdown(f'<div class="ri-kpis">{"".join(cells)}</div>', unsafe_allow_html=True)


def stat_row(items: list[dict]) -> None:
    """Compact secondary figures -- the same stat cards as kpi_strip."""
    kpi_strip(items)


def divider() -> None:
    st.markdown('<hr class="divider"/>', unsafe_allow_html=True)


def recede(html: str) -> None:
    """De-emphasised text for states that deliberately should not draw the eye."""
    st.markdown(f'<p class="recede">{html}</p>', unsafe_allow_html=True)


def badge(label: str, color: str, *, dark: bool = False) -> str:
    """A small chip with a status dot -- returns HTML, doesn't render. The dot carries the meaning
    (risk tier, intensity); the label stays readable."""
    return f'<span class="ri-chip{" dark" if dark else ""}"><i style="background:{color};"></i>{label}</span>'


def risk_chip(tier: str, *, dark: bool = False) -> str:
    return badge(f"{tier} risk", RISK_COLOR_MAP.get(tier, COLORS["neutral"]), dark=dark)


def value_chip(tier: str, *, dark: bool = False) -> str:
    shade = {"High": COLORS["ink"], "Medium": "#8A8F98", "Low": "#4A4D55"}.get(tier, COLORS["neutral"])
    return badge(f"{tier} value", shade, dark=dark)


def risk_badge(tier: str) -> str:
    """A solid, uppercase severity badge (HIGH / MEDIUM / LOW) -- returns HTML."""
    return f'<span class="ri-badge {esc(tier)}">{esc(tier)}</span>'


def dot(color: str) -> str:
    return f'<span class="ri-dot" style="background:{color};"></span>'


def status_list(rows: list[dict]) -> str:
    """A side-panel list -- rows: [{"dot", "name", "sub"?, "right"?, "state"? ("hot"|"mute")}].
    Returns HTML."""
    out = []
    for r in rows:
        sub = f"<small>{r['sub']}</small>" if r.get("sub") else ""
        right = f'<span class="rt">{r["right"]}</span>' if r.get("right") else ""
        out.append(
            f'<div class="{r.get("state", "")}">{dot(r["dot"])}<span class="nm">{r["name"]}{sub}</span>{right}</div>'
        )
    return f'<div class="ri-list">{"".join(out)}</div>'


def empty_state(eyebrow_text: str, title: str, subtitle: str) -> None:
    """A state that always tells the manager what to do next -- never a blank block."""
    md(
        f"""<div class="empty-state">
            <div class="empty-state-eyebrow">{eyebrow_text}</div>
            <div class="empty-state-title">{title}</div>
            <div class="empty-state-subtitle">{subtitle}</div>
        </div>"""
    )


def context_strip(html: str, *, dot_color: str | None = None) -> None:
    """The 'who/what is in focus' indicator -- reads as live system state."""
    dot_html = f'<span class="context-dot" style="background:{dot_color};"></span>' if dot_color else ""
    st.markdown(f'<div class="context-strip">{dot_html}{html}</div>', unsafe_allow_html=True)


def insight(html: str) -> None:
    st.markdown(f'<div class="insight">{html}</div>', unsafe_allow_html=True)


def note(html: str) -> None:
    """A methodology / confidence note -- visibly secondary."""
    st.markdown(f'<div class="ri-note">{html}</div>', unsafe_allow_html=True)


def handoff_note(label: str, html: str) -> None:
    """Visible feedback that context arrived from a previous step (a carried filter or customer)."""
    st.markdown(f'<div class="ri-handoff"><span class="k">{label}</span><span>{html}</span></div>', unsafe_allow_html=True)


def band(parts: list[dict], *, thin: bool = False, label_min_pct: float = 7) -> str:
    """Proportional stacked data band -- parts: [{"value", "color", "label"?, "title"?}]. Widths are
    linear in value (no scale distortion); the legend carries the labels. Returns HTML."""
    total = sum(p["value"] for p in parts) or 1
    segs = []
    for p in parts:
        pct = p["value"] / total * 100
        if pct <= 0:
            continue
        inner = f"<span>{p['label']}</span>" if p.get("label") and pct >= label_min_pct else ""
        title = _html.escape(p.get("title", ""), quote=True)
        segs.append(f'<div style="width:{pct:.4f}%; background:{p["color"]};" title="{title}">{inner}</div>')
    return f'<div class="ri-band{" thin" if thin else ""}">{"".join(segs)}</div>'


def intensity_color(intensity: str) -> str:
    if "High-touch" in intensity:
        return COLORS["high"]
    if "Moderate" in intensity:
        return COLORS["medium"]
    if "Advocacy" in intensity or "Upsell" in intensity:
        return COLORS["low"]
    if "Low-cost" in intensity:
        return COLORS["accent_on_dark"]
    return COLORS["neutral"]


def chart_layout(fig: go.Figure, height: int = CHART_HEIGHT, **kwargs) -> go.Figure:
    fig.update_layout(height=height, **kwargs)
    return fig


def esc(text) -> str:
    """HTML-escape a data value before it is placed inside markup."""
    return _html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# Page-specific compositions share the same token system; kept here so the whole visual language
# lives in one stylesheet rather than being scattered across page files.
# ---------------------------------------------------------------------------

_COMPONENT_CSS = """
/* ---------- attention funnel (Overview) ---------- */
.ri-funnel { display: flex; flex-direction: column; gap: 1.05rem; padding: 0.4rem 0 0.2rem 0; }
.ri-funnel .row { display: grid; grid-template-columns: 5.2rem 1fr; gap: 1.1rem; align-items: center; }
.ri-funnel .n { font: 520 1.45rem/1 var(--head); letter-spacing: -0.04em; color: var(--strong); font-variant-numeric: tabular-nums; text-align: right; }
.ri-funnel .what { display: flex; justify-content: space-between; gap: 1rem; font-size: 0.88rem; color: var(--muted); margin-bottom: 0.4rem; }
.ri-funnel .what b { color: var(--text); font-weight: 500; }
.ri-funnel .bar { height: 10px; background: var(--sunken); border-radius: 3px; overflow: hidden; }
.ri-funnel .bar i { display: block; height: 100%; border-radius: 3px; min-width: 3px; }
.ri-funnel .row.focus .n { color: var(--high-text); }
.ri-funnel .row.focus .what b { color: var(--high-text); }

/* ---------- risk x value grid (Customer Value) ---------- */
.ri-matrix { display: grid; grid-template-columns: 4.6rem repeat(3, 1fr); grid-template-rows: auto repeat(3, 1fr); gap: 6px; }
.ri-mx-h { font: 500 0.66rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); display: flex; align-items: flex-end; padding: 0 0 0.35rem 0.1rem; }
.ri-mx-r { font: 500 0.66rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); display: flex; align-items: center; }
.ri-mx-r b { display: block; font: 520 0.98rem var(--head); letter-spacing: -0.02em; text-transform: none; margin-top: 0.15rem; }
.ri-cell { position: relative; background: var(--sunken); border: 1px solid var(--line); border-radius: 6px; padding: 0.8rem 0.9rem; min-height: 5.6rem; display: flex; flex-direction: column; justify-content: space-between; transition: border-color .15s ease; }
.ri-cell:hover { border-color: #3A3B40; }
.ri-cell .n { font: 520 1.45rem/1 var(--head); color: var(--strong); font-variant-numeric: tabular-nums; letter-spacing: -0.04em; }
.ri-cell .churn { font-size: 0.8rem; font-variant-numeric: tabular-nums; margin-top: 0.45rem; }
.ri-cell .tag { display: block; margin-bottom: 0.45rem; }
.ri-cell .tag .ri-badge { font-size: 0.58rem; }
.ri-cell.zone { border-color: rgba(255,123,110,0.6); }
.ri-cell.sel { outline: 1px solid var(--accent); outline-offset: 2px; }
.ri-mx-axis { font: 500 0.64rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); text-align: center; margin-top: 0.6rem; }

/* ---------- inspector / detail panel facts ---------- */
.ri-inspect .t { font: 520 1.35rem/1.2 var(--head); letter-spacing: -0.03em; color: var(--strong); margin: 0.2rem 0 0.8rem 0; }
.ri-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 0 1rem; }
.ri-facts div { padding: 0.55rem 0; border-bottom: 1px solid var(--line); }
.ri-facts .l { font: 500 0.64rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); }
.ri-facts .v { font: 520 1.15rem var(--head); color: var(--strong); font-variant-numeric: tabular-nums; margin-top: 0.25rem; letter-spacing: -0.02em; }
.ri-kv > div { display: flex; justify-content: space-between; gap: 1rem; padding: 0.5rem 0; font-size: 0.88rem; border-bottom: 1px solid var(--line); }
.ri-kv > div:last-child { border-bottom: none; }
.ri-kv .k { color: var(--muted); }
.ri-kv .v { color: var(--strong); text-align: right; font-variant-numeric: tabular-nums; }

/* ---------- playbook list (Action Center) ---------- */
.ri-pb { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--panel); }
.ri-pb-row { display: grid; grid-template-columns: 1.6rem minmax(14rem, 2.4fr) 1fr 1fr minmax(10rem, 1.5fr) 1rem; gap: 1rem; align-items: center; padding: 0.8rem 1.1rem; border-bottom: 1px solid var(--line); }
.ri-pb-row.head { padding: 0.65rem 1.1rem; font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--muted); background: var(--sunken); }
.ri-pb-band { font: 500 0.66rem var(--sans); letter-spacing: 0.14em; text-transform: uppercase; padding: 0.7rem 1.1rem 0.5rem 1.1rem; border-bottom: 1px solid var(--line); display: flex; gap: 0.7rem; align-items: center; background: var(--sunken); }
.ri-pb-band span { font: 400 0.8rem var(--sans); letter-spacing: 0; text-transform: none; color: var(--faint); }
.ri-pb-row .rk { font-size: 0.76rem; color: var(--faint); }
.ri-pb-row .nm { font-weight: 500; color: var(--strong); font-size: 0.93rem; line-height: 1.3; display: flex; align-items: center; gap: 0.6rem; }
.ri-pb-row .fig { font-variant-numeric: tabular-nums; font-size: 0.92rem; color: var(--text); }
.ri-pb-row .act { font-size: 0.88rem; color: var(--text); }
.ri-pb-row .chev { color: var(--faint); transition: transform .2s ease, color .15s ease; }
details.ri-pb-item > summary { list-style: none; cursor: pointer; transition: background-color .15s ease; }
details.ri-pb-item > summary::-webkit-details-marker { display: none; }
details.ri-pb-item > summary:hover { background: var(--panel-2); }
details.ri-pb-item[open] > summary { background: var(--panel-2); border-bottom-color: transparent; }
details.ri-pb-item[open] .chev { transform: rotate(90deg); color: var(--strong); }
.ri-pb-detail { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem 2rem; padding: 0.2rem 1.1rem 1.1rem 3.7rem; background: var(--panel-2); border-bottom: 1px solid var(--line); }
.ri-pb-detail div { font-size: 0.86rem; line-height: 1.5; color: var(--muted); }
.ri-pb-detail b { color: var(--strong); font-weight: 600; }
.ri-pb-detail .l { display: block; font: 500 0.62rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); margin-bottom: 0.15rem; }
.ri-pb-detail .action { grid-column: 1 / -1; color: var(--strong); }

/* ---------- play cards (Action Center) ---------- */
.ri-play { padding: 0.2rem 0 0 0; margin-bottom: 1.1rem; }
.ri-play-k { font: 500 0.66rem var(--sans); letter-spacing: 0.14em; text-transform: uppercase; color: var(--cyan); }
.ri-play-t { font: 520 1.6rem/1.1 var(--head); letter-spacing: -0.04em; color: var(--strong); margin: 0.4rem 0 0.4rem 0; }
.ri-play-s { font-size: 0.9rem; color: var(--muted); margin-bottom: 0.9rem; }
.ri-play-s b { color: var(--strong); font-weight: 600; font-variant-numeric: tabular-nums; }
.ri-play-grid { display: none; }

/* ---------- selected-item header (Priority Customers, Customer 360) ---------- */
.ri-id .who { font: 500 1.02rem/1.35 var(--sans); color: var(--strong); word-break: break-all; margin: 0.2rem 0 0.6rem 0; font-variant-numeric: tabular-nums; }
.ri-id .kick { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); }

/* ---------- customer brief (Customer 360) ---------- */
.ri-brief { font-size: 1.02rem; line-height: 1.7; color: var(--text); max-width: 46rem; }
.ri-brief b { color: var(--strong); font-weight: 600; }
.ri-brief .hi { color: var(--high-text); }
.ri-sig > div { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 0.65rem 0; border-bottom: 1px solid var(--line); }
.ri-sig > div:last-child { border-bottom: none; }
.ri-sig .l { font-size: 0.86rem; color: var(--muted); display: flex; align-items: center; gap: 0.55rem; }
.ri-sig .v { font-size: 0.92rem; color: var(--strong); text-align: right; font-variant-numeric: tabular-nums; }
.ri-sig .b { display: block; font-size: 0.74rem; color: var(--faint); margin-top: 0.1rem; }
.ri-sig > div.flag .v { color: var(--high-text); }
.ri-why { padding-left: 1.1rem; margin: 0.2rem 0 0.4rem 0; }
.ri-why li { margin-bottom: 0.45rem; line-height: 1.5; font-size: 0.92rem; color: var(--text); }
.ri-act-verb { font: 520 1.6rem/1.15 var(--head); letter-spacing: -0.04em; color: var(--strong); margin: 0.3rem 0 0.5rem 0; }
.ri-act-obj { font-size: 0.95rem; line-height: 1.55; color: var(--text); }
.ri-act-avoid { font-size: 0.86rem; line-height: 1.5; color: var(--muted); margin-top: 0.7rem; }
.ri-act-avoid b { color: var(--text); font-weight: 600; }
.ri-inherit .k { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); }
.ri-inherit .o { font-size: 0.95rem; line-height: 1.5; color: var(--text); margin: 0.4rem 0 0.2rem 0; }

/* ---------- Retention Intelligence ---------- */
.ri-pipe { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.8rem; }
.ri-pipe > div .k { font: 500 0.66rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--cyan); }
.ri-pipe > div .d { font-size: 0.84rem; color: var(--muted); margin-top: 0.3rem; line-height: 1.4; }
.ri-pipe > div.mode { grid-column: 1 / -1; border-top: 1px solid var(--line); padding-top: 0.7rem; }
.ri-pipe > div.mode .d { color: var(--info); }
.ri-mode { display: inline-flex; align-items: center; gap: 0.5rem; font: 500 0.66rem var(--sans); letter-spacing: 0.1em; text-transform: uppercase; color: var(--info); }
.ri-mode i { width: 6px; height: 6px; border-radius: 50%; display: inline-block; background: var(--low); }
.ri-mode.det i { background: var(--neutral); }
[class*="st-key-suggested_"] button { justify-content: flex-start; text-align: left; min-height: 2.8rem; background: var(--panel); border-color: var(--line); }
[class*="st-key-suggested_"] button > div { flex: 1; justify-content: flex-start; }
[class*="st-key-suggested_"] button > div > span { justify-content: flex-start; }
[class*="st-key-suggested_"] button p { text-align: left; font-size: 0.9rem; font-weight: 400; white-space: normal; overflow: visible; text-overflow: clip; }
[class*="st-key-suggested_"] button::after { content: "\\2192"; margin-left: auto; padding-left: 0.8rem; color: var(--faint); transition: transform .15s ease, color .15s ease; }
[class*="st-key-suggested_"] button:hover::after { color: var(--accent-text); transform: translateX(3px); }
[class*="st-key-suggested_"] button:hover { border-color: var(--accent); background: var(--panel-2); }
.st-key-copilot_freetext input { font-size: 0.98rem; padding-top: 0.7rem; padding-bottom: 0.7rem; }
.ri-mode-banner { display: flex; gap: 0.6rem; align-items: baseline; font-size: 0.78rem; color: var(--faint); margin-bottom: 0.7rem; }
.ri-mode-banner .k { font: 500 0.62rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); white-space: nowrap; }
.st-key-ri_answer { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 0.3rem 1.3rem 1.1rem 1.3rem; }
.ri-brief-in { font-family: var(--head) !important; font-weight: 520 !important; letter-spacing: -0.02em; color: var(--strong) !important; }
[class*="st-key-ri-l-"] { border-top: 1px solid var(--line); padding-top: 0.6rem; }
[class*="st-key-ri-l-"] p > strong:first-child { display: block; font: 500 0.64rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); margin-bottom: 0.25rem; }
[class*="st-key-ri-l-"] p, [class*="st-key-ri-l-"] li { font-size: 0.93rem; color: var(--text); }
[class*="st-key-ri-l-evidence"] { border-top: none; padding-top: 0; }
[class*="st-key-ri-l-evidence"] ul { margin: 0.1rem 0 0 0; padding-left: 1.05rem; columns: 2; column-gap: 2rem; }
[class*="st-key-ri-l-evidence"] li { break-inside: avoid; margin-bottom: 0.25rem; font-size: 0.86rem; color: var(--muted); }
[class*="st-key-ri-l-action"] { border-top: none; background: var(--sunken); border: 1px solid var(--line); border-left: 2px solid var(--accent); border-radius: 6px; padding: 0.65rem 0.9rem; }
[class*="st-key-ri-l-action"] p > strong:first-child { color: var(--accent-text); }
[class*="st-key-ri-l-action"] p { color: var(--strong); font-size: 0.98rem; }
[class*="st-key-ri-l-avoid"] p { color: var(--muted); }
[class*="st-key-ri-l-next"] p > strong:first-child { color: var(--cyan); }
[class*="st-key-ri-facts"] > div { gap: 0 2.2rem; }
[class*="st-key-ri-facts"] [data-testid="stElementContainer"] { width: auto !important; }
[class*="st-key-ri-facts"] p > strong:first-child { display: block; font: 500 0.64rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--faint); margin-bottom: 0.2rem; }
[class*="st-key-ri-facts"] p { font-size: 0.95rem; color: var(--strong); }
[class*="st-key-ri-facts"] { border-top: 1px solid var(--line); padding-top: 0.6rem; }
.st-key-ri_answer [data-testid="stCaptionContainer"] p { color: var(--faint); }
.ri-prov { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; font: 500 0.62rem var(--sans); letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); margin-top: 0.6rem; }
.ri-prov span { border: 1px solid var(--line-2); padding: 0.2rem 0.5rem; color: var(--muted); letter-spacing: 0; text-transform: none; font-size: 0.76rem; border-radius: 4px; }

/* ---------- compact customer rows (Retention Intelligence results) ---------- */
.ri-qrow-id { font-size: 0.86rem; color: var(--strong); word-break: break-all; }
.ri-qrow-sig { font-size: 0.78rem; color: var(--high-text); margin-top: 0.15rem; }
.ri-qrow-act { font-size: 0.86rem; color: var(--strong); }
.ri-qrow-seg { font-size: 0.76rem; color: var(--faint); }
.st-key-ri_results { gap: 0; }
.st-key-ri_results [data-testid="stHorizontalBlock"] { border-bottom: 1px solid var(--line); padding: 0.45rem 0; align-items: center; }
.st-key-ri_results [data-testid="stHorizontalBlock"]:hover { background: var(--panel-2); }

/* ---------- data-load gate ---------- */
.ri-gate { display: flex; gap: 1rem; align-items: baseline; }
.ri-gate .k { font: 500 0.64rem var(--sans); letter-spacing: 0.13em; text-transform: uppercase; color: var(--cyan); white-space: nowrap; }
.ri-gate p { margin: 0; font-size: 0.88rem; color: var(--muted); }
[class*="st-key-gate_"] { border: 1px solid var(--line); background: var(--panel); padding: 0.8rem 1.1rem; border-radius: 8px; }
"""


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
