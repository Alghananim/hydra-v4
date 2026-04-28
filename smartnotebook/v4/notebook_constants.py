"""SmartNoteBook V4 — constants.

All magic numbers / strings live here. Importing modules MUST NOT hardcode
these values; they should reference these constants by name.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
NOTEBOOK_NAME = "smartnotebook"
MODEL_VERSION = "v4.0.0"
SCHEMA_VERSION = "1"

# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------
DEFAULT_LEDGER_DIRNAME = "ledger"
JSONL_FILENAME_TEMPLATE = "{date}.jsonl"   # {date} = YYYY-MM-DD UTC date
SQLITE_FILENAME = "ledger.sqlite"
LEDGER_TABLE = "records"

# ---------------------------------------------------------------------------
# Chain hashing
# ---------------------------------------------------------------------------
GENESIS_PREV_HASH = "0" * 64   # sha256 width
HASH_ALGO = "sha256"

# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------
ATTRIBUTION_GRADE_FLOOR = "A"           # min grade to be "responsible" for a win
QUALITY_LUCKY = "lucky"
QUALITY_EARNED = "earned"
QUALITY_UNFORCED = "unforced_loss"
QUALITY_UNKNOWN = "unknown"
RESPONSIBLE_LUCK = "luck"
RESPONSIBLE_NEWS = "newsmind"
RESPONSIBLE_MARKET = "marketmind"
RESPONSIBLE_CHART = "chartmind"
RESPONSIBLE_GATE = "gatemind"

# ---------------------------------------------------------------------------
# Session windows (NY local)
# ---------------------------------------------------------------------------
SESSION_MORNING = "morning_3_5"
SESSION_PRE_OPEN = "pre_open_8_12"
SESSION_OUTSIDE = "outside"

# Session boundary hours (NY local). Half-open intervals: [start, end).
SESSION_MORNING_START_HOUR = 3
SESSION_MORNING_END_HOUR = 5
SESSION_PRE_OPEN_START_HOUR = 8
SESSION_PRE_OPEN_END_HOUR = 12

# ---------------------------------------------------------------------------
# HMAC chain authentication (S2 — forge-resistance)
# ---------------------------------------------------------------------------
# Environment variable holding the HMAC secret key. When present, the
# chain_hash is computed as HMAC-SHA256(key, prev_hash || canonical_payload)
# instead of plain sha256, which makes the chain forge-resistant (an
# attacker with write access to the JSONL CANNOT mint a valid chain_hash
# without the key).
#
# When unset: the system falls back to plain sha256, which provides
# tamper-detection only (anyone with write access to JSONL can forge a
# new record with valid prev_hash + chain_hash). A WARNING is logged at
# startup so operators are aware they are running in insecure mode.
HMAC_KEY_ENV = "HYDRA_NOTEBOOK_HMAC_KEY"

# ---------------------------------------------------------------------------
# Final status (DECISION_CYCLE)
# ---------------------------------------------------------------------------
FINAL_ENTER = "ENTER_CANDIDATE"
FINAL_WAIT = "WAIT"
FINAL_BLOCK = "BLOCK"

# ---------------------------------------------------------------------------
# Async writer (non-critical path)
# ---------------------------------------------------------------------------
NON_CRITICAL_QUEUE_MAX = 1024  # bounded queue; full queue raises, never silently drops

# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------
REDACTION_PLACEHOLDER = "[REDACTED]"
