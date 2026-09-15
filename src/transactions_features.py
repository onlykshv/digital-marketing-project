"""Leakage-safe aggregation of transactions.csv into per-user features.

transactions.csv is ~1.7GB / 21.5M rows. This host has only ~7.4GB of RAM
(often under 1.5GB free), so it cannot be loaded in full.

An earlier version of this module streamed the file with pandas'
chunked reader and folded each chunk into a growing Python-side
accumulator (dict/DataFrame merges). That worked logically but degraded
into severe memory-pressure thrashing partway through the file (a 5-chunk
batch that took ~3 minutes early on took over an hour once the running
state grew large) — repeatedly reindexing an ever-growing state object
on a memory-starved machine causes exactly this kind of collapse.

This version instead hands the whole aggregation to DuckDB, an embedded
OLAP engine that streams and aggregates CSV data directly off disk with a
bounded memory budget, spilling to disk instead of failing or thrashing
when data exceeds that budget. Only the final, tiny (~2.36M row) per-user
result is ever pulled into a pandas DataFrame.

Every row is filtered to transaction_date <= cutoff_date before it
contributes to any aggregate, which is the leakage boundary for the v2
prediction round (cutoff = 2017-02-28, predicting March 2017 churn).
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src import config

# Conservative for a ~7.4GB-RAM host: leaves headroom for pandas/Python
# itself and lets DuckDB spill to disk instead of competing for RAM.
DUCKDB_MEMORY_LIMIT = "2GB"
DUCKDB_THREADS = 2

# Explicit schema (rather than read_csv_auto's sniffed types) so DuckDB
# doesn't have to guess from a sample of a 21.5M-row file.
_DUCKDB_COLUMN_TYPES = {
    "msno": "VARCHAR",
    "payment_method_id": "SMALLINT",
    "payment_plan_days": "SMALLINT",
    "plan_list_price": "INTEGER",
    "actual_amount_paid": "INTEGER",
    "is_auto_renew": "TINYINT",
    "transaction_date": "INTEGER",
    "membership_expire_date": "INTEGER",
    "is_cancel": "TINYINT",
}
_DUCKDB_COLUMNS_CLAUSE = "{" + ", ".join(f"'{k}': '{v}'" for k, v in _DUCKDB_COLUMN_TYPES.items()) + "}"


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.astype("float64")
    return numerator.astype("float64") / denom.replace(0, np.nan)


def build_transaction_features(
    transactions_path: Path,
    cutoff_date: int,
    logger: logging.Logger,
    duckdb_tmp_dir: Path | None = None,
) -> pd.DataFrame:
    logger.info("Starting DuckDB aggregation of %s (cutoff_date=%d)", transactions_path, cutoff_date)

    if duckdb_tmp_dir is not None:
        duckdb_tmp_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    con.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"SET threads={DUCKDB_THREADS}")
    if duckdb_tmp_dir is not None:
        con.execute(f"SET temp_directory='{duckdb_tmp_dir.as_posix()}'")

    csv_path = transactions_path.as_posix()
    read_csv_expr = f"read_csv('{csv_path}', columns={_DUCKDB_COLUMNS_CLAUSE}, header=true)"

    # Parse the CSV exactly once: one combined pass gets both the raw stats
    # (for the leakage sanity log) and the cutoff-filtered row count via a
    # FILTER clause, so it's a single full scan rather than two.
    logger.info("Scanning transactions.csv once for raw stats + cutoff row count...")
    stats = con.execute(
        f"""
        SELECT
            COUNT(*),
            MIN(transaction_date),
            MAX(transaction_date),
            COUNT(*) FILTER (WHERE transaction_date <= {cutoff_date})
        FROM {read_csv_expr}
        """
    ).fetchone()
    n_raw, raw_min, raw_max, n_used = stats
    logger.info("Raw transactions.csv: %d rows, transaction_date range [%d, %d]", n_raw, raw_min, raw_max)
    logger.info("Rows with transaction_date <= cutoff (%d): %d used out of %d raw rows", cutoff_date, n_used, n_raw)

    # Materialize the filtered rows into an actual DuckDB table (one more
    # full CSV parse) so every query below hits DuckDB's own columnar
    # storage instead of re-parsing the 1.7GB CSV from scratch each time.
    logger.info("Materializing cutoff-filtered rows into a DuckDB table...")
    con.execute(
        f"""
        CREATE TABLE filtered AS
        SELECT * FROM {read_csv_expr}
        WHERE transaction_date <= {cutoff_date}
        """
    )
    logger.info("Materialized 'filtered' table: %d rows", con.execute("SELECT COUNT(*) FROM filtered").fetchone()[0])

    logger.info("Running grouped aggregation (counts, sums, distinct payment methods)...")
    agg_query = """
        SELECT
            msno,
            CAST(COUNT(*) AS BIGINT)                          AS total_transactions,
            CAST(SUM(is_cancel) AS BIGINT)                    AS total_cancellations,
            CAST(SUM(is_auto_renew) AS BIGINT)                AS total_auto_renew,
            CAST(SUM(payment_plan_days) AS BIGINT)            AS sum_payment_plan_days,
            CAST(SUM(actual_amount_paid) AS BIGINT)           AS total_revenue,
            CAST(SUM(plan_list_price) AS BIGINT)              AS total_list_price,
            CAST(MIN(transaction_date) AS INTEGER)            AS first_transaction_date,
            CAST(MAX(transaction_date) AS INTEGER)            AS last_transaction_date,
            CAST(COUNT(DISTINCT payment_method_id) AS BIGINT) AS num_distinct_payment_methods
        FROM filtered
        GROUP BY msno
    """
    agg_df = con.execute(agg_query).df()
    logger.info("Aggregated counts/sums: %d distinct users", len(agg_df))

    logger.info("Running window query for each user's most-recent transaction...")
    latest_query = """
        SELECT
            msno,
            payment_method_id      AS latest_payment_method_id,
            payment_plan_days      AS latest_payment_plan_days,
            plan_list_price        AS latest_plan_list_price,
            actual_amount_paid     AS latest_actual_amount_paid,
            is_auto_renew          AS latest_is_auto_renew,
            is_cancel              AS latest_is_cancel,
            membership_expire_date AS latest_membership_expire_date
        FROM filtered
        QUALIFY ROW_NUMBER() OVER (PARTITION BY msno ORDER BY transaction_date DESC) = 1
    """
    latest_df = con.execute(latest_query).df()
    logger.info("Latest-transaction rows: %d distinct users", len(latest_df))

    con.close()

    features = agg_df.merge(latest_df, on="msno", how="left")
    del agg_df, latest_df

    # Derived ratios (safe division: undefined -> NaN, not 0)
    features["cancel_rate"] = _safe_divide(features["total_cancellations"], features["total_transactions"])
    features["auto_renew_pct"] = _safe_divide(features["total_auto_renew"], features["total_transactions"])
    features["avg_payment_plan_days"] = _safe_divide(features["sum_payment_plan_days"], features["total_transactions"])
    features["avg_revenue_per_txn"] = _safe_divide(features["total_revenue"], features["total_transactions"])
    features["total_discount"] = features["total_list_price"] - features["total_revenue"]
    features["discount_rate"] = _safe_divide(features["total_discount"], features["total_list_price"])

    # Date-based features, all relative to the fixed cutoff (never "today")
    cutoff_ts = pd.to_datetime(str(cutoff_date), format="%Y%m%d")
    first_ts = pd.to_datetime(features["first_transaction_date"].astype("Int64").astype("string"), format="%Y%m%d")
    last_ts = pd.to_datetime(features["last_transaction_date"].astype("Int64").astype("string"), format="%Y%m%d")

    # latest_membership_expire_date sentinel guard (e.g. 19700101 epoch placeholder):
    # treat as missing rather than a real (wildly negative) remaining-days value.
    expire_invalid_mask = features["latest_membership_expire_date"] < config.EXPIRE_DATE_MIN_VALID
    n_expire_invalid = int(expire_invalid_mask.sum())
    if n_expire_invalid:
        logger.warning(
            "%d / %d (%.4f%%) latest_membership_expire_date values are before %d (sentinel garbage) — "
            "membership_remaining_days set to NaN for these",
            n_expire_invalid, len(features), 100 * n_expire_invalid / len(features), config.EXPIRE_DATE_MIN_VALID,
        )
    features["membership_expire_date_invalid"] = expire_invalid_mask.astype("int8")
    expire_ts = pd.to_datetime(
        features["latest_membership_expire_date"].where(~expire_invalid_mask).astype("Int64").astype("string"),
        format="%Y%m%d",
    )

    features["txn_span_days"] = (last_ts - first_ts).dt.days
    features["days_since_last_txn"] = (cutoff_ts - last_ts).dt.days
    features["membership_remaining_days"] = (expire_ts - cutoff_ts).dt.days

    features = features.drop(columns=["sum_payment_plan_days"])

    logger.info("Transaction feature table built: %d users x %d columns", features.shape[0], features.shape[1])
    return features
