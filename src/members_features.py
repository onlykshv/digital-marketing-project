"""Cleans members_v3.csv demographics and derives registration/tenure features.

members_v3.csv is small enough (~427MB, 6.77M rows) to load in full — no
chunking needed here, per the computational-feasibility notes in the dataset
audit. All engineered values are anchored on cutoff_date (never a "today"
value), since tenure_days is itself a model feature and must not encode the
current wall-clock date.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src import config

MEMBERS_DTYPES = {
    "msno": "string",
    "city": "int8",
    "bd": "int32",
    "gender": "string",
    "registered_via": "int8",
    "registration_init_time": "int32",
}


def build_member_features(
    members_path: Path,
    cutoff_date: int,
    logger: logging.Logger,
) -> pd.DataFrame:
    logger.info("Loading %s", members_path)
    members = pd.read_csv(members_path, dtype=MEMBERS_DTYPES)
    logger.info("Loaded members_v3.csv: %d rows x %d columns", members.shape[0], members.shape[1])

    n_total = len(members)

    # --- bd (age): audit found heavy corruption (0s, negative years, future years) ---
    bd_invalid_mask = (members["bd"] < config.BD_MIN_VALID) | (members["bd"] > config.BD_MAX_VALID)
    n_bd_invalid = int(bd_invalid_mask.sum())
    members["bd_missing"] = bd_invalid_mask.astype("int8")
    members["bd_clean"] = members["bd"].where(~bd_invalid_mask)
    logger.info(
        "bd cleaning: %d / %d (%.2f%%) values outside [%d, %d] set to NaN",
        n_bd_invalid, n_total, 100 * n_bd_invalid / n_total, config.BD_MIN_VALID, config.BD_MAX_VALID,
    )

    # --- gender: genuinely missing for most users, not "invalid" — just flag it ---
    members["gender_missing"] = members["gender"].isna().astype("int8")

    # --- registered_via: -1 observed as a sentinel/unknown code ---
    via_unknown_mask = members["registered_via"] == config.REGISTERED_VIA_UNKNOWN
    n_via_unknown = int(via_unknown_mask.sum())
    members["registered_via_missing"] = via_unknown_mask.astype("int8")
    logger.info("registered_via: %d / %d (%.2f%%) rows have the unknown sentinel (-1)",
                n_via_unknown, n_total, 100 * n_via_unknown / n_total)

    # --- registration recency / tenure, anchored on cutoff_date ---
    cutoff_ts = pd.to_datetime(str(cutoff_date), format="%Y%m%d")
    reg_ts = pd.to_datetime(members["registration_init_time"].astype("string"), format="%Y%m%d")
    members["tenure_days_at_cutoff"] = (cutoff_ts - reg_ts).dt.days
    members["registration_year"] = reg_ts.dt.year.astype("Int16")
    members["registration_month"] = reg_ts.dt.month.astype("Int8")

    n_future_reg = int((reg_ts > cutoff_ts).sum())
    if n_future_reg:
        logger.warning(
            "%d members have registration_init_time AFTER the cutoff (%d) — "
            "tenure_days_at_cutoff will be negative for these rows; leaving as-is for visibility, "
            "not silently clipping.",
            n_future_reg, cutoff_date,
        )

    out_cols = [
        "msno", "city", "bd_clean", "bd_missing", "gender", "gender_missing",
        "registered_via", "registered_via_missing", "registration_init_time",
        "registration_year", "registration_month", "tenure_days_at_cutoff",
    ]
    features = members[out_cols].copy()

    logger.info("Member feature table built: %d users x %d columns", features.shape[0], features.shape[1])
    return features
