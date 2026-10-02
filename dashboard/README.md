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
| 01 | Overview | Where should KKBOX act? | `risk_scoring_summary.json`, `marketing_action_plan.csv`, `risk_value_matrix.csv`, `temporal_validation_results.json` |
| 02 | Priority Customers | Who should we save? | customer tables (below), `shap_feature_importance.csv`, `risk_scoring_threshold_analysis.csv` |
| 03 | Customer Value | Who is worth saving? | `risk_value_matrix.csv`, `value_by_segment.csv`, `value_by_risk_tier.csv` |
| 04 | Action Center | What should we do? | `marketing_action_plan.csv` |
| 05 | Customer 360 | What should we do for this customer? | `customer_segments.csv`, `risk_scoring_predictions.csv`, `customer_value_tiers.csv`, `calibrated_probabilities.csv` (loaded on demand only) |
| 06 | Retention Intelligence | Why? Ask the intelligence layer. | the agent's nine read-only tools over the files above |

The demo journey is Overview → Priority Customers → Customer 360 → Retention Intelligence; the
customer or segment in focus is carried between pages through session state. Start the demo from
the root URL (`http://localhost:8501/`).

## Design system

A dark "command dashboard" layout adapted from the Romer SaaS template on Stitch (`lib/theme.py`):

- **App shell**: a fixed left navigation rail (`st.navigation(position="sidebar")`) with icons and
  uppercase labels; the active page is marked in cyan.
- **One idea per page**: a page title that is the page's question, one sentence of context, at
  most three stat cards, then one main panel and one side panel (`st.container(key="rp_...")`).
- **Plain marketing language first**: customers, churn rate, revenue to date, campaigns. Model
  scores, probabilities, drivers, thresholds and methodology sit behind "Details" toggles and the
  "Methodology & limitations" panel at the bottom of each page.
- **Colour means something**: near-black surfaces; the only bright elements are small status dots
  and badges — coral (high risk), amber (medium), green (low / growth) — plus indigo for actions.
- **Type**: Manrope for headings and big numbers (tight tracking), Inter for everything else.
- **Charts**: one shared dark Plotly template, no toolbar, every chart answers a specific question.

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
  .streamlit/config.toml     # forces the dark theme regardless of the viewer's OS setting
  pages/
    overview.py              # 01 — Overview
    priority_customers.py    # 02 — Priority Customers
    customer_value.py        # 03 — Customer Value
    action_center.py         # 04 — Action Center
    customer_360.py          # 05 — Customer 360
    retention_copilot.py     # 06 — Retention Intelligence
  lib/
    data.py                  # cached, read-only loaders + small derived aggregates
    theme.py                 # design system: tokens, CSS, Plotly template, page/panel/stat helpers
    components.py            # shared UI: recommendation + play blocks, the answer renderer
    caveats.py               # the methodology/limitations panels shown on each page
    agent*.py, copilot_*.py, llm_provider.py   # Retention Intelligence (unchanged by UI work)
  requirements.txt
  README.md
```
