"""Main entry point: builds the leakage-safe v2 churn modeling dataset.

Pipeline:
    train_v2.csv (labels)
        + members_v3.csv  -> cleaned demographic/registration features
        + transactions.csv -> chunked, cutoff-filtered transaction/subscription features
    joined on msno -> outputs/kkbox_modeling_dataset_v2.csv

No modeling happens here. This script only builds and sanity-checks the
feature table. Raw source files under data/ are only ever read, never
modified.
"""

from __future__ import annotations

import gc
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.logging_utils import get_logger
from src.members_features import build_member_features
from src.transactions_features import build_transaction_features

logger = get_logger("build_dataset", log_file=config.LOG_DIR / "build_dataset.log")


def _load_or_build_transaction_features() -> pd.DataFrame:
    if config.TRANSACTION_FEATURES_CACHE.exists():
        logger.info("Found cached transaction features at %s — loading instead of re-scanning transactions.csv",
                     config.TRANSACTION_FEATURES_CACHE)
        return pd.read_csv(config.TRANSACTION_FEATURES_CACHE, dtype={"msno": "string"})

    t0 = time.time()
    features = build_transaction_features(
        transactions_path=config.TRANSACTIONS_PATH,
        cutoff_date=config.CUTOFF_DATE,
        logger=logger,
        duckdb_tmp_dir=config.INTERMEDIATE_DIR / "duckdb_tmp",
    )
    logger.info("Transaction feature build took %.1f seconds", time.time() - t0)

    config.INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    features.to_csv(config.TRANSACTION_FEATURES_CACHE, index=False)
    logger.info("Cached transaction features to %s", config.TRANSACTION_FEATURES_CACHE)
    return features


def _load_or_build_member_features() -> pd.DataFrame:
    if config.MEMBER_FEATURES_CACHE.exists():
        logger.info("Found cached member features at %s — loading instead of re-processing members_v3.csv",
                     config.MEMBER_FEATURES_CACHE)
        return pd.read_csv(config.MEMBER_FEATURES_CACHE, dtype={"msno": "string"})

    features = build_member_features(
        members_path=config.MEMBERS_PATH,
        cutoff_date=config.CUTOFF_DATE,
        logger=logger,
    )
    config.INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    features.to_csv(config.MEMBER_FEATURES_CACHE, index=False)
    logger.info("Cached member features to %s", config.MEMBER_FEATURES_CACHE)
    return features


def _log_missingness(df: pd.DataFrame) -> None:
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        logger.info("Missingness: no missing values in any column.")
        return
    logger.info("Missingness (columns with any NaN, %d of %d columns):", len(missing), df.shape[1])
    for col, n_missing in missing.items():
        logger.info("  %-35s %8d missing  (%.2f%%)", col, n_missing, 100 * n_missing / len(df))


def _run_sanity_checks(df: pd.DataFrame, train_v2: pd.DataFrame, txn_features: pd.DataFrame) -> None:
    logger.info("--- Sanity checks ---")

    ok = True

    if len(df) != len(train_v2):
        logger.error("FAIL: row count changed during joins (%d -> %d). Joins must be left joins on train_v2.",
                      len(train_v2), len(df))
        ok = False
    else:
        logger.info("PASS: row count preserved through joins (%d rows)", len(df))

    n_dupes = df["msno"].duplicated().sum()
    if n_dupes:
        logger.error("FAIL: %d duplicate msno rows in final dataset", n_dupes)
        ok = False
    else:
        logger.info("PASS: msno is unique in the final dataset")

    churn_rate = df["is_churn"].mean()
    logger.info("is_churn distribution: %d churned / %d total = %.2f%% churn rate",
                int(df["is_churn"].sum()), len(df), 100 * churn_rate)
    if not (0.05 < churn_rate < 0.15):
        logger.warning("is_churn rate %.2f%% is outside the expected ~9%% range reported in the audit for train_v2",
                        100 * churn_rate)

    # Leakage guard: re-derive the max raw transaction_date actually used and confirm <= cutoff.
    # We only have the aggregated last_transaction_date here (already filtered upstream), so this
    # re-checks the aggregation output rather than the raw file.
    if "last_transaction_date" in txn_features.columns:
        max_last_txn = pd.to_numeric(txn_features["last_transaction_date"], errors="coerce").max()
        if max_last_txn > config.CUTOFF_DATE:
            logger.error("FAIL: aggregated last_transaction_date=%s exceeds cutoff=%s — leakage in transaction features!",
                         max_last_txn, config.CUTOFF_DATE)
            ok = False
        else:
            logger.info("PASS: max last_transaction_date in features (%s) <= cutoff (%s)",
                        int(max_last_txn), config.CUTOFF_DATE)

    coverage_members = df["has_members_data"].mean()
    coverage_txn = df["has_transactions_data"].mean()
    logger.info("Coverage: %.1f%% of train_v2 users have member data, %.1f%% have transaction data (<=cutoff)",
                100 * coverage_members, 100 * coverage_txn)

    if "membership_remaining_days" in df.columns:
        col = df["membership_remaining_days"].dropna()
        logger.info("membership_remaining_days: min=%.0f, max=%.0f, mean=%.1f (negative = already expired before cutoff)",
                    col.min(), col.max(), col.mean())

    if "tenure_days_at_cutoff" in df.columns:
        col = df["tenure_days_at_cutoff"].dropna()
        logger.info("tenure_days_at_cutoff: min=%.0f, max=%.0f, mean=%.1f", col.min(), col.max(), col.mean())

    logger.info("--- Sanity checks %s ---", "PASSED" if ok else "FAILED (see errors above)")
    if not ok:
        raise AssertionError("One or more sanity checks failed — see log for details.")


def main() -> None:
    t_start = time.time()
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=== KKBox v2 leakage-safe feature pipeline ===")
    logger.info("Cutoff date (last date any feature may see): %d", config.CUTOFF_DATE)

    logger.info("Loading labels: %s", config.TRAIN_V2_PATH)
    train_v2 = pd.read_csv(config.TRAIN_V2_PATH, dtype={"msno": "string", "is_churn": "int8"})
    logger.info("train_v2: %d rows", len(train_v2))

    txn_features = _load_or_build_transaction_features()
    gc.collect()

    member_features = _load_or_build_member_features()
    gc.collect()

    logger.info("Joining train_v2 + member_features + transaction_features on msno")
    df = train_v2.merge(member_features, on="msno", how="left", indicator="_m_members")
    df["has_members_data"] = (df["_m_members"] == "both").astype("int8")
    df = df.drop(columns=["_m_members"])

    df = df.merge(txn_features, on="msno", how="left", indicator="_m_txn")
    df["has_transactions_data"] = (df["_m_txn"] == "both").astype("int8")
    df = df.drop(columns=["_m_txn"])

    # Count-type features are genuinely 0 for users with no transaction history
    # before the cutoff; ratio/recency/"latest value" features stay NaN because
    # they are undefined (not zero) for such users.
    zero_fill_cols = [
        "total_transactions", "total_cancellations", "total_auto_renew",
        "num_distinct_payment_methods",
    ]
    for col in zero_fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    logger.info("Final modeling table: %d rows x %d columns", df.shape[0], df.shape[1])
    _log_missingness(df)
    _run_sanity_checks(df, train_v2, txn_features)

    df.to_csv(config.MODELING_DATASET_PATH, index=False)
    logger.info("Saved modeling dataset to %s", config.MODELING_DATASET_PATH)

    logger.info("Feature columns (%d total, excluding msno/is_churn): %s",
                df.shape[1] - 2,
                [c for c in df.columns if c not in ("msno", "is_churn")])

    logger.info("=== Pipeline complete in %.1f seconds ===", time.time() - t_start)


if __name__ == "__main__":
    main()
