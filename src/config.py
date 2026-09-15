"""Paths and constants for the KKBox churn feature-engineering pipeline.

All cutoff logic is anchored on the v2 competition round: users in
train_v2.csv are scored on churn during March 2017, so every feature must be
derived strictly from data known on or before CUTOFF_DATE (Feb 28, 2017).
Anything dated after that leaks the outcome.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DATA_DIR = PROJECT_ROOT / "data" / "kkbox-churn-prediction-challenge"

TRAIN_V2_PATH = RAW_DATA_DIR / "data" / "churn_comp_refresh" / "train_v2.csv"
MEMBERS_PATH = RAW_DATA_DIR / "members_v3.csv"
TRANSACTIONS_PATH = RAW_DATA_DIR / "transactions.csv"

OUTPUT_DIR = PROJECT_ROOT / "outputs"
INTERMEDIATE_DIR = OUTPUT_DIR / "intermediate"
LOG_DIR = OUTPUT_DIR / "logs"

MODELING_DATASET_PATH = OUTPUT_DIR / "kkbox_modeling_dataset_v2.csv"
TRANSACTION_FEATURES_CACHE = INTERMEDIATE_DIR / "transaction_features_v2.csv"
MEMBER_FEATURES_CACHE = INTERMEDIATE_DIR / "member_features_v2.csv"

# v2 observation cutoff: the last date any feature is allowed to see.
# transactions.csv independently ends on this exact date (verified 2017-02-28),
# so this filter is a defensive guard, not just documentation.
CUTOFF_DATE = 20170228

# bd (age) values outside this range are treated as data-entry garbage,
# per the audit: real values cluster 10-70, with 0s and negative/huge
# outliers making up the bulk of the corruption.
BD_MIN_VALID = 5
BD_MAX_VALID = 100

# registered_via sentinel for "unknown" (audit noted min value of -1).
REGISTERED_VIA_UNKNOWN = -1

# membership_expire_date sentinel guard: KKBox launched well after this date,
# so earlier values (observed: 19700101, a classic epoch placeholder) are
# garbage, not real expirations. Affects ~0.008% of transaction rows.
EXPIRE_DATE_MIN_VALID = 20100101
