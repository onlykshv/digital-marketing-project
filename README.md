# KKBox Retention Intelligence

Churn prediction + retention-intelligence dashboard built on the [KKBox Churn Prediction Challenge](https://www.kaggle.com/c/kkbox-churn-prediction-challenge) dataset. Includes a feature-engineering pipeline, trained models (LogReg / Random Forest / XGBoost), a full modeling notebook series, and a Streamlit dashboard with an optional LLM-powered "Retention Copilot".

## Repo layout

```
src/            Feature engineering pipeline (build_dataset.py + feature builders)
notebooks/      01-12, ordered: EDA -> baseline -> tree models -> tuning -> temporal
                validation -> risk scoring -> segments -> value analysis -> action
                plan -> calibration -> threshold rationale -> error analysis
models/         Trained model artifacts (.joblib) + comparison metrics  [in git]
dashboard/      Streamlit app (app.py, lib/, pages/)
tests/          pytest suite for the dashboard
test_cases/     Manual validation reports (A-xx, D-xx, TASK_xx)
task_1/         Task tracker + P1/P2 validation reports
data/           Raw KKBox dataset                                       [NOT in git]
outputs/        Generated features / model outputs the dashboard reads  [NOT in git]
```

## What's not in git, and why

`data/` (~12GB raw + archives) and `outputs/` (~2.6GB generated) are excluded via `.gitignore` — several individual files exceed GitHub's 100MB limit. Get them one of two ways:

### Option A — download the zips (fastest, no pipeline run needed)
Ask whoever set up the repo for the Drive links, then unzip so contents land exactly here:

| Zip | Extract to |
|---|---|
| `data.zip` | `data/` (so you end up with `data/kkbox-churn-prediction-challenge/...`) |
| `outputs.zip` | `outputs/` (so you end up with `outputs/kkbox_modeling_dataset_v2.csv`, `outputs/intermediate/...`, etc.) |

Both folders sit at the repo root, same level as `src/`.

**Drive links:**
- Raw data (`data.zip`): `<PASTE LINK HERE>`
- Generated outputs (`outputs.zip`): `<PASTE LINK HERE>`

If `outputs.zip` isn't available, regenerate it yourself with Option B step 3 below (needs `data/` first).

### Option B — rebuild from scratch
1. Download the raw KKBox dataset from Kaggle (or the `data.zip` above) into `data/kkbox-churn-prediction-challenge/`
2. Install deps (see Setup below)
3. Run the pipeline:
   ```
   python -m src.build_dataset
   ```
   This reads `data/kkbox-churn-prediction-challenge/` and writes the modeling dataset + intermediate feature caches into `outputs/`. Paths are all defined in `src/config.py` — nothing is hardcoded outside it.
4. Model artifacts in `models/` are already in git, so you don't need to re-run the notebooks unless you're retraining.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt              # src/ pipeline + notebooks
pip install -r dashboard/requirements.txt     # Streamlit dashboard
```

## Running the dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard only reads from `models/` and `outputs/` (see `dashboard/lib/data.py`) — it never touches raw `data/`, so Option A alone is enough to run it.

**Optional — Retention Copilot LLM synthesis:** set `ANTHROPIC_API_KEY` in your environment. Without it, the Copilot falls back to a deterministic, non-LLM answer path automatically — the app works either way.

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "your-key-here"
```

## Running notebooks

```bash
jupyter notebook notebooks/
```

Run in order (01 → 12). Notebooks 01-06 need `data/` (raw) and `outputs/`; 07 onward mostly consume earlier notebooks' outputs and the trained models in `models/`.

## Running tests

```bash
pytest tests/
```

## Data notes

- Feature cutoff: `CUTOFF_DATE = 2017-02-28` (`src/config.py`) — every feature is derived strictly from data on or before this date to avoid label leakage into the March 2017 churn window.
- See `FEATURE_AUDIT.md` for the full feature-quality audit and `data/kkbox-churn-prediction-challenge/kkbox_dataset_audit.md` for raw data quality notes.
