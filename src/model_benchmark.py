"""Temporal model benchmark (notebook 13): candidate models scored on the production temporal
holdout, one model per process, sized for a ~7.4 GB RAM machine.

    python -m src.model_benchmark --step holdout    # shared labels + calibration halves
    python -m src.model_benchmark --step rule_auto_renew_off
    python -m src.model_benchmark --step xgboost_tuned
    python -m src.model_benchmark --step logistic_regression
    python -m src.model_benchmark --step lightgbm
    python -m src.model_benchmark --step random_forest

Each step writes outputs/model_benchmark/<model>.npz (holdout scores, in the v2 file's row order)
and <model>.json (configuration, rows, runtime, status) the moment it finishes, and is skipped if
those already exist. `evaluate()` (called from notebooks/13_model_benchmark.ipynb) turns them into
outputs/model_benchmark_results.csv and outputs/model_benchmark_summary.json.

What is shared by every model:
  test population : outputs/kkbox_modeling_dataset_v2.csv -- train_v2.csv, Mar-2017 churn,
                    features cut off 2017-02-28; all 970,960 rows, never subsampled
  training data   : outputs/kkbox_modeling_dataset_v1_temporal_train.csv -- train.csv, Feb-2017
                    churn, features cut off 2017-01-31 (written by notebook 05)
  features        : notebook 05's full feature set and preprocessing (median impute + scale,
                    one-hot), fitted on the training data. The fitted output is held as a sparse
                    float32 matrix to fit in memory; the transformation itself is unchanged.
What differs: each model's training configuration (MODEL_SPECS), including the training sample
size for the resource-constrained Random Forest.

The tuned XGBoost is NOT retrained: its holdout scores are the production model's own,
read from outputs/risk_scoring_predictions.csv (notebook 06) and checked against notebook 05's
published ROC-AUC / PR-AUC before use.
"""
from __future__ import annotations

import argparse
import gc
import json
import time

import numpy as np
import pandas as pd
import psutil
from scipy import sparse

from src import config

RANDOM_STATE = 42
TRAIN_PATH = config.OUTPUT_DIR / "kkbox_modeling_dataset_v1_temporal_train.csv"
TEST_PATH = config.MODELING_DATASET_PATH
OUT_DIR = config.OUTPUT_DIR / "model_benchmark"
RESULTS_CSV = config.OUTPUT_DIR / "model_benchmark_results.csv"
SUMMARY_JSON = config.OUTPUT_DIR / "model_benchmark_summary.json"
SCORE_CHUNK = 100_000
MIN_FREE_MB_TO_START = 1500
MIN_FREE_MB_TO_FIT = 700

# --- notebook 05, cell 9 (verbatim definitions) ---------------------------------------------------
CAT_ONEHOT = ["city", "gender", "registered_via", "latest_payment_method_id",
              "registration_month", "num_distinct_payment_methods"]
BINARY_FLAGS = ["bd_missing", "gender_missing", "registered_via_missing", "has_members_data",
                "has_transactions_data", "latest_is_auto_renew", "latest_is_cancel",
                "membership_expire_date_invalid"]
NUMERIC_CONTINUOUS = ["bd_clean", "registration_init_time", "registration_year",
                      "tenure_days_at_cutoff", "total_transactions", "total_cancellations",
                      "total_auto_renew", "total_revenue", "total_list_price",
                      "first_transaction_date", "last_transaction_date",
                      "latest_payment_plan_days", "latest_plan_list_price",
                      "latest_actual_amount_paid", "latest_membership_expire_date",
                      "cancel_rate", "auto_renew_pct", "avg_payment_plan_days",
                      "avg_revenue_per_txn", "total_discount", "discount_rate",
                      "txn_span_days", "days_since_last_txn", "membership_remaining_days"]
ALL_FEATURES = CAT_ONEHOT + BINARY_FLAGS + NUMERIC_CONTINUOUS
# --------------------------------------------------------------------------------------------------

MODEL_SPECS = {
    "rule_auto_renew_off": {
        "label": "Rule: auto-renew off",
        "training_config": "flag = latest_is_auto_renew == 0 (missing -> training median, as the "
                           "preprocessor imputes); score = the training-set churn rate of the "
                           "customer's group, so the ranking is the rule itself",
        "notes": "Non-ML baseline built on the model's top SHAP driver.",
    },
    "logistic_regression": {
        "label": "Logistic Regression",
        "training_config": "LogisticRegression(class_weight='balanced', max_iter=1000, "
                           "random_state=42) -- notebook 02's settings; full temporal training set",
        "notes": "Untuned.",
    },
    "lightgbm": {
        "label": "LightGBM",
        "training_config": "LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, "
                           "max_depth=8, min_child_samples=100, subsample=0.8, subsample_freq=1, "
                           "colsample_bytree=0.8, scale_pos_weight=neg/pos, n_jobs=2, "
                           "random_state=42); full temporal training set",
        "notes": "Fixed, memory-conscious settings; no hyperparameter search.",
    },
    "random_forest": {
        "label": "Random Forest (resource-constrained)",
        "training_config": "RandomForestClassifier(n_estimators=150, max_depth=16, "
                           "min_samples_leaf=20, max_features='sqrt', class_weight='balanced', "
                           "n_jobs=2, random_state=42); trained on a stratified 300,000-row sample "
                           "of the temporal training set",
        "notes": "Resource-constrained configuration chosen for this machine's memory -- NOT the "
                 "200-tree, full-training-set Random Forest of notebook 03's random-split "
                 "experiment. Scored on the full holdout.",
    },
    "xgboost_tuned": {
        "label": "XGBoost (tuned, production)",
        "training_config": "models/xgboost_temporal_full.joblib -- hyperparameters tuned in "
                           "notebook 04 (random split), refit on the temporal training set in "
                           "notebook 05; not retrained here",
        "notes": "Holdout scores reused from outputs/risk_scoring_predictions.csv; the only tuned "
                 "model in this comparison.",
    },
}
RF_TRAIN_SAMPLE = 300_000


def free_mb() -> float:
    return psutil.virtual_memory().available / 2**20


def _paths(model):
    return OUT_DIR / f"{model}.npz", OUT_DIR / f"{model}.json"


def _record(model, status, **fields):
    rec = {"model": model, "label": MODEL_SPECS.get(model, {}).get("label", model), "status": status,
           "training_config": MODEL_SPECS.get(model, {}).get("training_config"),
           "notes": MODEL_SPECS.get(model, {}).get("notes"), **fields}
    _paths(model)[1].write_text(json.dumps(rec, indent=2, default=float))
    print(json.dumps(rec, indent=2, default=float), flush=True)


def _read(path, columns):
    df = pd.read_csv(path, usecols=columns)
    # Numerics stay float64: the yyyymmdd date features (~2.0e7) exceed float32's integer precision.
    for c in CAT_ONEHOT:
        if c in df:
            df[c] = df[c].astype(str).astype("category")  # notebook 05 casts these to str
    return df


def build_preprocessor():
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    categorical = Pipeline([("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=True))])
    # sparse_threshold=1.0: always return the (identical) output as a sparse matrix, to save memory
    return ColumnTransformer([("num", numeric, BINARY_FLAGS + NUMERIC_CONTINUOUS), ("cat", categorical, CAT_ONEHOT)],
                             sparse_threshold=1.0)


def step_holdout():
    npz = OUT_DIR / "holdout.npz"
    if npz.exists():
        print("holdout.npz exists, skipping")
        return
    ids = pd.read_csv(TEST_PATH, usecols=["msno", "is_churn"])
    calib = pd.read_csv(config.OUTPUT_DIR / "calibrated_probabilities.csv", usecols=["msno", "calib_split"])
    split = calib.set_index("msno")["calib_split"].reindex(ids["msno"])
    assert split.notna().all(), "calibration halves do not cover the holdout"
    hi = json.loads((config.OUTPUT_DIR / "risk_scoring_summary.json").read_text())["risk_tiers"]
    k = next(t["n_customers"] for t in hi if t["tier"] == "High")
    np.savez(npz, y=ids["is_churn"].to_numpy(np.int8), calib_eval=(split == "calib_eval").to_numpy(),
             calib_fit=(split == "calib_fit").to_numpy(), top_k=np.int64(k))
    print(f"holdout: {len(ids):,} rows, churn {ids['is_churn'].mean():.4f}, High-tier k = {k:,}")


def _holdout():
    h = np.load(OUT_DIR / "holdout.npz")
    return h["y"]


def step_rule():
    t0 = time.time()
    tr = pd.read_csv(TRAIN_PATH, usecols=["latest_is_auto_renew", "is_churn"])
    median = tr["latest_is_auto_renew"].median()
    flag_tr = (tr["latest_is_auto_renew"].fillna(median) == 0).to_numpy()
    y_tr = tr["is_churn"].to_numpy()
    rate_off, rate_on = float(y_tr[flag_tr].mean()), float(y_tr[~flag_tr].mean())
    n_train = len(tr)
    del tr
    te = pd.read_csv(TEST_PATH, usecols=["latest_is_auto_renew", "is_churn"])
    flag_te = (te["latest_is_auto_renew"].fillna(median) == 0).to_numpy()
    assert np.array_equal(te["is_churn"].to_numpy(np.int8), _holdout())
    scores = np.where(flag_te, rate_off, rate_on)
    np.savez(_paths("rule_auto_renew_off")[0], score=scores)
    _record("rule_auto_renew_off", "completed", train_rows_used=n_train, test_rows=len(te),
            fit_seconds=0.0, score_seconds=round(time.time() - t0, 1),
            group_train_churn_rate={"auto_renew_off": rate_off, "auto_renew_on_or_imputed": rate_on},
            share_flagged_in_holdout=float(flag_te.mean()))


def step_xgboost():
    from sklearn.metrics import average_precision_score, roc_auc_score
    t0 = time.time()
    order = pd.read_csv(TEST_PATH, usecols=["msno"])["msno"]
    preds = pd.read_csv(config.OUTPUT_DIR / "risk_scoring_predictions.csv",
                        usecols=["msno", "is_churn", "risk_score_full"]).set_index("msno")
    assert len(preds) == len(order) and preds.index.is_unique
    preds = preds.reindex(order)
    assert preds["risk_score_full"].notna().all(), "production scores do not cover the holdout"
    y = preds["is_churn"].to_numpy(np.int8)
    assert np.array_equal(y, _holdout()), "label mismatch between the two holdout files"
    s = preds["risk_score_full"].to_numpy(np.float64)
    published = json.loads((config.OUTPUT_DIR / "temporal_validation_results.json").read_text())
    pub = published["temporal_metrics"]["full_feature_set"]
    roc, pr = roc_auc_score(y, s), average_precision_score(y, s)
    assert abs(roc - pub["roc_auc"]) < 1e-4 and abs(pr - pub["pr_auc"]) < 1e-4, (roc, pr, pub)
    np.savez(_paths("xgboost_tuned")[0], score=s)
    _record("xgboost_tuned", "completed", train_rows_used=published["train_rows"], test_rows=len(y),
            fit_seconds=None, score_seconds=round(time.time() - t0, 1),
            reproduction_check={"published_roc_auc": pub["roc_auc"], "roc_auc_from_saved_scores": roc,
                                "published_pr_auc": pub["pr_auc"], "pr_auc_from_saved_scores": pr},
            published_threshold_metrics_at_0_5={k: pub[k] for k in ("precision", "recall", "f1")},
            runtime_note="Training runtime not re-measured: the model was trained in notebook 05.")


def _make_classifier(model, spw):
    if model == "logistic_regression":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    if model == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, max_depth=8,
                              min_child_samples=100, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, scale_pos_weight=spw, n_jobs=2,
                              random_state=RANDOM_STATE, verbose=-1)
    if model == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(n_estimators=150, max_depth=16, min_samples_leaf=20,
                                      max_features="sqrt", class_weight="balanced", n_jobs=2,
                                      random_state=RANDOM_STATE)
    raise ValueError(model)


def step_trained_model(model):
    start_free = free_mb()
    if start_free < MIN_FREE_MB_TO_START:
        _record(model, "not completed due to resource constraint",
                reason=f"only {start_free:.0f} MB free at start (needs {MIN_FREE_MB_TO_START} MB)")
        return
    try:
        t0 = time.time()
        train = _read(TRAIN_PATH, ALL_FEATURES + ["is_churn"])
        y = train["is_churn"].to_numpy()
        spw = float((y == 0).sum() / (y == 1).sum())
        n_train_full = len(train)
        pre = build_preprocessor()
        X = sparse.csr_matrix(pre.fit_transform(train[ALL_FEATURES]), dtype=np.float32)
        del train
        gc.collect()
        if model == "random_forest":
            from sklearn.model_selection import train_test_split
            idx, _ = train_test_split(np.arange(len(y)), train_size=RF_TRAIN_SAMPLE, stratify=y,
                                      random_state=RANDOM_STATE)
            idx.sort()
            X = X[idx].toarray()
            y = y[idx]
            gc.collect()
        if free_mb() < MIN_FREE_MB_TO_FIT:
            _record(model, "not completed due to resource constraint",
                    reason=f"only {free_mb():.0f} MB free after preprocessing (needs {MIN_FREE_MB_TO_FIT} MB to fit)")
            return
        clf = _make_classifier(model, spw)
        clf.fit(X, y)
        fit_s = time.time() - t0
        n_fit_rows = X.shape[0]
        del X
        gc.collect()

        t1 = time.time()
        test = _read(TEST_PATH, ALL_FEATURES + ["is_churn"])
        assert np.array_equal(test["is_churn"].to_numpy(np.int8), _holdout())
        scores = np.empty(len(test), dtype=np.float64)
        for i in range(0, len(test), SCORE_CHUNK):
            Xc = pre.transform(test.iloc[i:i + SCORE_CHUNK][ALL_FEATURES]).astype(np.float32)
            if model == "random_forest":
                Xc = Xc.toarray()
            scores[i:i + SCORE_CHUNK] = clf.predict_proba(Xc)[:, 1]
        n_test = len(test)
        del test
        gc.collect()
        np.savez(_paths(model)[0], score=scores)
        _record(model, "completed", train_rows_used=n_fit_rows, train_rows_available=n_train_full,
                test_rows=n_test, n_features_after_preprocessing=len(pre.get_feature_names_out()),
                scale_pos_weight=spw if model == "lightgbm" else None,
                lbfgs_iterations=int(clf.n_iter_[0]) if model == "logistic_regression" else None,
                fit_seconds=round(fit_s, 1), score_seconds=round(time.time() - t1, 1),
                free_mb_at_start=round(start_free))
    except MemoryError as e:
        _record(model, "not completed due to resource constraint", reason=f"MemoryError: {e}")


def precision_recall_at_k(y, s, k):
    """Precision and recall among the k highest-scored customers. A tie block straddling the
    cut-off contributes its positives in proportion -- the expectation under random tie-breaking
    (it matters for the two-valued rule baseline)."""
    order = np.argsort(-s, kind="stable")
    s_sorted, y_sorted = s[order], y[order]
    cutoff = s_sorted[k - 1]
    above, tied = s_sorted > cutoff, s_sorted == cutoff
    positives = y_sorted[above].sum() + (k - above.sum()) * y_sorted[tied].mean()
    return float(positives / k), float(positives / y.sum())


def _weighted_average_precision(y_sorted, w_sorted, last_of_tie):
    """sklearn's average_precision_score formula on pre-sorted (descending) scores, with sample
    weights: precision is evaluated at each distinct threshold (the last row of each tie block)."""
    tp = np.cumsum(w_sorted * y_sorted)[last_of_tie]
    fp = np.cumsum(w_sorted * (1 - y_sorted))[last_of_tie]
    # a leading block that a resample weights to zero has no precision (0/0); it adds no recall,
    # so its term is 0 either way
    precision = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) > 0)
    recall = tp / tp[-1]
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


def paired_bootstrap_pr_auc(y, scores: dict, reference: str, n_boot=500, seed=RANDOM_STATE):
    """Paired Poisson bootstrap of PR-AUC(model) - PR-AUC(reference): each resample's weights are
    applied to the same holdout rows for every model. Returns the observed difference and a 95%
    percentile interval per model. One weight vector exists at a time (memory)."""
    rng = np.random.default_rng(seed)
    prepared = {}
    for name, s in scores.items():
        order = np.argsort(-s, kind="stable")
        s_sorted = s[order]
        last = np.r_[np.flatnonzero(np.diff(s_sorted) != 0), len(s_sorted) - 1]
        prepared[name] = (order, y[order].astype(np.float64), last)

    def ap(name, w):
        order, ys, last = prepared[name]
        return _weighted_average_precision(ys, w[order], last)

    boot = {name: np.empty(n_boot) for name in scores}
    for b in range(n_boot):
        w = rng.poisson(1.0, size=len(y)).astype(np.float64)
        for name in scores:
            boot[name][b] = ap(name, w)
    ones = np.ones(len(y))
    out = {}
    for name in scores:
        if name == reference:
            continue
        lo, hi = np.percentile(boot[name] - boot[reference], [2.5, 97.5])
        out[name] = {"observed_diff": ap(name, ones) - ap(reference, ones),
                     "ci95_low": float(lo), "ci95_high": float(hi), "n_boot": n_boot}
    return out


def step_bootstrap():
    t0 = time.time()
    y = _holdout().astype(int)
    scores = {m: np.load(_paths(m)[0])["score"] for m in MODEL_SPECS if _paths(m)[0].exists()}
    res = paired_bootstrap_pr_auc(y, scores, reference="xgboost_tuned")
    (OUT_DIR / "bootstrap_pr_auc_vs_xgboost.json").write_text(json.dumps(
        {"reference": "xgboost_tuned", "method": "paired Poisson bootstrap over holdout rows, 95% percentile interval",
         "seconds": round(time.time() - t0, 1), "differences": res}, indent=2))
    print(json.dumps(res, indent=2))


def evaluate() -> pd.DataFrame:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    h = np.load(OUT_DIR / "holdout.npz")
    y, k = h["y"].astype(int), int(h["top_k"])
    fit_m, eval_m = h["calib_fit"], h["calib_eval"]
    rows = []
    for model, spec in MODEL_SPECS.items():
        npz, rec_path = _paths(model)
        rec = json.loads(rec_path.read_text()) if rec_path.exists() else {"status": "not run"}
        row = {"model": spec["label"], "model_key": model, "status": rec["status"],
               "training_config": spec["training_config"], "notes": spec["notes"],
               "train_rows_used": rec.get("train_rows_used"), "test_rows": rec.get("test_rows"),
               "fit_seconds": rec.get("fit_seconds"), "score_seconds": rec.get("score_seconds")}
        if rec["status"] == "completed" and npz.exists():
            s = np.load(npz)["score"]
            assert len(s) == len(y) and np.isfinite(s).all()
            p_k, r_k = precision_recall_at_k(y, s, k)
            iso = IsotonicRegression(out_of_bounds="clip").fit(s[fit_m], y[fit_m])
            row.update({
                "pr_auc": average_precision_score(y, s), "roc_auc": roc_auc_score(y, s),
                "brier": brier_score_loss(y, np.clip(s, 0, 1)),
                "brier_after_isotonic": brier_score_loss(y[eval_m], iso.predict(s[eval_m])),
                "precision_at_2_3pct": p_k, "recall_at_2_3pct": r_k,
            })
        rows.append(row)
    res = pd.DataFrame(rows)
    done = res[res["status"] == "completed"].sort_values("pr_auc", ascending=False)
    res = pd.concat([done, res[res["status"] != "completed"]], ignore_index=True)
    res.to_csv(RESULTS_CSV, index=False)
    SUMMARY_JSON.write_text(json.dumps({
        "statement": "Under the same temporal holdout and feature framework, the tested models "
                     "produced the following observed performance. This is not evidence of global "
                     "model superiority: training configurations differ by model (see "
                     "training_config), only XGBoost was tuned, and Random Forest ran in a "
                     "resource-constrained configuration.",
        "test_population": f"outputs/kkbox_modeling_dataset_v2.csv -- {len(y):,} customers, "
                           f"churn rate {y.mean():.4f}, not subsampled",
        "training_data": "outputs/kkbox_modeling_dataset_v1_temporal_train.csv",
        "primary_metric": "pr_auc",
        "operating_point": f"top {k:,} customers = {k / len(y):.3%} of the holdout = production High-tier size",
        "brier_note": "brier = raw model score on the full holdout. Class weighting / scale_pos_weight "
                      "inflate raw scores, so it is a calibration measure of the raw output only. "
                      "brier_after_isotonic = score isotonic-calibrated on notebook 10's calib_fit "
                      "half and evaluated on its calib_eval half.",
        "not_compared": "Fixed-threshold precision/recall/F1: the models' raw score scales differ.",
        "pr_auc_difference_vs_production_xgboost": (
            json.loads((OUT_DIR / "bootstrap_pr_auc_vs_xgboost.json").read_text())
            if (OUT_DIR / "bootstrap_pr_auc_vs_xgboost.json").exists() else None),
        "results": res.to_dict(orient="records"),
    }, indent=2, default=float))
    return res


STEPS = {"holdout": step_holdout, "rule_auto_renew_off": step_rule, "xgboost_tuned": step_xgboost,
         "bootstrap": step_bootstrap}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True, choices=list(STEPS) + ["logistic_regression", "lightgbm", "random_forest"])
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = _paths(args.step)[1]
    if args.step in MODEL_SPECS and rec_path.exists() and json.loads(rec_path.read_text())["status"] == "completed":
        print(f"{args.step}: already completed ({rec_path}), not rerun")
    elif args.step in STEPS:
        STEPS[args.step]()
    else:
        step_trained_model(args.step)
    print(f"free memory now: {free_mb():.0f} MB")
