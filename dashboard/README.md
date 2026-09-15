# KKBox Retention Intelligence

A marketing-facing decision platform for the KKBox churn project — built entirely on the
validated outputs of notebooks `01`–`09`. It reads pre-computed CSV/JSON files only; it does not
retrain any model, recompute any segment, or modify anything under `data/`, `models/`, or
`outputs/`.

## Install

From the `dashboard/` folder:

```bash
pip install -r requirements.txt
```

This installs `streamlit` and `plotly`. Everything else (pandas, etc.) is already part of the
project's existing environment.

## Run

```bash
cd dashboard
streamlit run app.py
```

Streamlit will open the dashboard in your browser (default: `http://localhost:8501`).

## Pages

| # | Page | Question it answers | Data source(s) |
|---|---|---|---|
| 01 | Command Center | What's happening, and where should we act first? | `risk_scoring_summary.json`, `marketing_action_plan.csv`, `value_by_risk_tier.csv`, `risk_value_matrix.csv` |
| 02 | Risk Intelligence | Why are customers at risk? | `risk_scoring_threshold_analysis.csv`, `shap_feature_importance.csv`, `marketing_action_plan.csv` |
| 03 | Customer Value | Where is the economic value concentrated? | `risk_value_matrix.csv`, `value_by_segment.csv`, `value_by_risk_tier.csv` |
| 04 | Action Center | What should we do, and for whom? | `marketing_action_plan.csv` / `.json` |
| 05 | Customer 360 | Find a customer — then see their full profile | `customer_segments.csv`, `risk_scoring_predictions.csv`, `customer_value_tiers.csv` (loaded on demand only) |

## Design system

- **Hierarchy over inventory**: each page leads with the one number or chart that answers its
  question, not a row of equally-weighted KPI cards. Secondary numbers use `theme.stat_row` (a
  quiet inline row, no card/border) instead of `st.metric` widgets; low-priority items (e.g. the
  Stable segment on Action Center) deliberately recede via `theme.recede`.
- **Palette**: one dark navy for structural chrome (headers, sidebar, selected nav), one accent
  (amber/orange) for actions and priority callouts, and three semantic colors reserved
  exclusively for risk — green (low), amber (medium), red (high). No rainbow charts.
- **Typography**: Inter, with a strict hierarchy (hero/page header → section title → stat →
  supporting text). Labels are uppercase/muted; the one number that matters per page is large
  and bold — everything else is deliberately smaller.
- **Cards, sparingly**: white background, thin border, no hover animation — reserved for the
  handful of items that genuinely warrant full visual containment (the top 1-2 priority
  opportunities, the risk/value quadrants). Ranked lists (churn drivers, secondary segments) use
  large numerals or a plain table instead of another card grid.
- **Badges**: tinted outline chips (`theme.badge`), not solid pill fills — color still carries
  meaning (risk tier, intervention intensity) without the "sticker" look.
- **Charts**: one shared Plotly template (`lib/theme.py`), fixed height tiers, no default
  toolbar clutter, consistent hover styling. Every chart on the dashboard answers a specific
  question (concentration, ranking, risk x value) — none exist just because the data was there.
- **Progressive disclosure**: every page follows *what's happening → where → why → who → what to
  do*. Methodology, model metrics, and caveats are collapsed by default at the bottom of each
  page, not the top.

## Design notes

- **Memory-conscious by construction**: every page except Customer 360 runs entirely on
  aggregate files under ~10KB each. The three large per-customer files (~300MB combined) are
  only read if you click "Load customer data" on Customer 360, and are cached for the rest of
  that session once loaded.
- **Caveats are not hidden, just not first**: each page carries a collapsed "Methodology &
  limitations" panel covering whichever of these apply — risk-score miscalibration, the
  temporal-validation performance drop, HRR ≠ CLV, and the observational (not causal) nature of
  the segments and recommendations. None of this is new; it restates what notebooks 05, 06, 08,
  and 09 already established.
- **No fabricated numbers, no causal claims**: every figure is read from an existing
  `outputs/*.csv`/`*.json` file. Every "why" explanation on a recommendation is framed as an
  observed historical association, never a promised outcome.

## If something doesn't load

The dashboard checks for each expected file and shows a specific error naming the missing file
rather than a raw traceback. If you see one, it usually means a required notebook (01–09) hasn't
been run yet, or the app isn't being launched from inside the project's `dashboard/` folder.

## Project structure

```
dashboard/
  app.py                     # entry point — run this with `streamlit run`
  .streamlit/config.toml     # forces a consistent light theme regardless of viewer's OS setting
  pages/
    command_center.py        # 01 — Command Center
    risk_intelligence.py     # 02 — Risk Intelligence
    customer_value.py        # 03 — Customer Value
    action_center.py         # 04 — Action Center
    customer_360.py          # 05 — Customer 360
  lib/
    data.py                  # cached, read-only loaders + small derived aggregates
    theme.py                 # design system: palette, CSS, Plotly template, hero/stat/rank helpers
    components.py            # shared UI: priority opportunity cards, risk/value quadrant cards
    caveats.py                # the methodology/limitations panels shown on each page
  requirements.txt
  README.md
```
