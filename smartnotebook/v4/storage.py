"""SmartNoteBook V4 — storage (JSONL + SQLite dual-write).

Design:
  * JSONL is Source-Of-Truth (R8). Every record is appended as one line.
  * SQLite is a derived index. Queries hit SQLite; writes hit BOTH.
    SQLite is a query INDEX. JSONL is SOT. After mutation, run
    rebuild_sqlite_from_jsonl().
  * Append-only — there is NO `update_record` / `delete_record` method.
    Corrections are a NEW record with parent_record_id pointing at the
    original.
  * fail-loud: any OS error during JSONL write raises LedgerWriteError.
    SQLite write errors also raise; the JSONL line written first is the
    canonical record so the system can still rebuild SQLite.
  * Secret redaction at the record boundary (R6).

The JSONL filename is sharded by UTC date: {date}.jsonl. SQLite holds the
union of all days for fast queries.

S1 — concurrent write hardening:
  ALL chain-hash computation happens INSIDE _lock. The caller hands us a
  record (or partial dict); we read the prev_hash off disk and compute
  chain_hash atomically with the file append. This prevents two threads
  from reading the SAME prev_hash and forking the chain.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4 import secret_redactor as _redactor
from smartnotebook.v4 import time_integrity as _time
from smartnotebook.v4.error_handling import (
    AppendOnlyViolation,
    LedgerWriteError,
    NonMonotonicTimestampError,
    StorageConsistencyError,
)
from smartnotebook.v4.models import BaseRecord
from smartnotebook.v4.notebook_constants import (
    JSONL_FILENAME_TEMPLATE,
    LEDGER_TABLE,
    SQLITE_FILENAME,
)
from smartnotebook.v4.record_types import RecordType
from smartnotebook.v4.time_integrity import to_iso_utc

_log = logging.getLogger("smartnotebook")


# ---------------------------------------------------------------------------
# Helper — record_dict_for_persistence
# ---------------------------------------------------------------------------
def _record_to_dict(rec: BaseRecord) -> Dict[str, Any]:
    """Serialize a frozen dataclass record to a JSON-compatible dict.

    - datetimes → ISO 8601 with Z
    - enums → .value
    - nested dataclasses → asdict
    """
    if not is_dataclass(rec):
        raise TypeError(f"expected dataclass, got {type(rec).__name__}")

    out: Dict[str, Any] = {}
    for f in fields(rec):
        v = getattr(rec, f.name)
        out[f.name] = _coerce_value(v)
    return out


def _coerce_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, datetime):
        return to_iso_utc(v) if v.utcoffset() is not None and v.utcoffset().total_seconds() == 0 else v.isoformat()
    if hasattr(v, "value") and isinstance(v, RecordType.__mro__[0]):
        return v.value
    if hasattr(v, "value") and isinstance(getattr(v, "value", None), str):
        # generic enum
        return v.value
    if is_dataclass(v):
        return {fk.name: _coerce_value(getattr(v, fk.name)) for fk in fields(v)}
    if isinstance(v, dict):
        return {k: _coerce_value(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_coerce_value(x) for x in v]
    if isinstance(v, tuple):
        return [_coerce_value(x) for x in v]
    return v


# ---------------------------------------------------------------------------
# Storage class
# ---------------------------------------------------------------------------
class Storage:
    """JSONL+SQLite append-only ledger.

    Threading: a single per-instance Lock serializes appends.

    Critical invariants:
      * NO update_record method — append-only ledger
      * NO delete_record method
      * All append errors raise LedgerWriteError
      * S1 — chain_hash is computed under _lock; concurrent appends never fork
    """

    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sqlite_path = self._base / SQLITE_FILENAME
        self._init_sqlite()
        # Cache of last chain_hash per JSONL day file
        self._last_hash_per_day: Dict[str, str] = {}
        # Cache of last timestamp_utc per day file (for S5 monotonicity)
        self._last_ts_per_day: Dict[str, str] = {}
        # S7 — Seed the global sequence counter from MAX(sequence_id)
        # in the SQLite mirror so a second notebook process opening the
        # same base_dir does not reuse sequence_ids 1..N.
        self._seed_sequence_counter()

    # ------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        # Defense against dynamic attribute access for forbidden mutations
        if name in ("update_record", "delete_record", "modify_record",
                    "remove_record", "drop_record"):
            raise AppendOnlyViolation(
                f"Storage is append-only (R1); '{name}' is not allowed"
            )
        raise AttributeError(name)

    # ------------------------------------------------------------------
    def _init_sqlite(self) -> None:
        try:
            with sqlite3.connect(str(self._sqlite_path)) as conn:
                conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
                        record_id TEXT PRIMARY KEY,
                        record_type TEXT NOT NULL,
                        timestamp_utc TEXT NOT NULL,
                        sequence_id INTEGER NOT NULL,
                        parent_record_id TEXT,
                        prev_record_id TEXT,
                        prev_hash TEXT NOT NULL,
                        chain_hash TEXT NOT NULL,
                        symbol TEXT,
                        date_utc TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )"""
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_records_date ON {LEDGER_TABLE}(date_utc)"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_records_type ON {LEDGER_TABLE}(record_type)"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_records_parent ON {LEDGER_TABLE}(parent_record_id)"
                )
                conn.commit()
        except sqlite3.Error as e:
            raise LedgerWriteError(f"sqlite init failed: {e}") from e

    # ------------------------------------------------------------------
    def _seed_sequence_counter(self) -> None:
        """S7 — Read MAX(sequence_id) from SQLite and bump global counter.

        This prevents two notebook instances pointed at the same base_dir
        from reusing sequence_ids 1, 2, 3, ... Idempotent.
        """
        try:
            with sqlite3.connect(str(self._sqlite_path)) as conn:
                cur = conn.execute(
                    f"SELECT COALESCE(MAX(sequence_id), 0) FROM {LEDGER_TABLE}"
                )
                row = cur.fetchone()
                max_seq = int(row[0]) if row and row[0] is not None else 0
        except sqlite3.Error:
            max_seq = 0
        if max_seq > 0:
            _time.set_counter_floor(max_seq)

    # ------------------------------------------------------------------
    def jsonl_path_for(self, when_utc: datetime) -> Path:
        date_str = when_utc.strftime("%Y-%m-%d")
        return self._base / JSONL_FILENAME_TEMPLATE.format(date=date_str)

    # ------------------------------------------------------------------
    def last_chain_hash_for_day(self, when_utc: datetime) -> str:
        """Read the last chain_hash from the day's JSONL.

        Returns GENESIS prev_hash for empty / missing files.

        NOTE: Callers should NOT use this to pre-compute a chain_hash and
        then submit a record. That pattern is racy under concurrent
        writes (S1). `append_record` reads the prev_hash atomically
        under the write lock and recomputes chain_hash itself.
        This method remains for back-compat with the test conftest and
        for verification flows.
        """
        path = self.jsonl_path_for(when_utc)
        date_key = when_utc.strftime("%Y-%m-%d")
        if date_key in self._last_hash_per_day:
            return self._last_hash_per_day[date_key]
        if not path.exists():
            self._last_hash_per_day[date_key] = _chain.first_prev_hash()
            return self._last_hash_per_day[date_key]
        last = _chain.first_prev_hash()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = rec.get("chain_hash", last)
        self._last_hash_per_day[date_key] = last
        return last

    # ------------------------------------------------------------------
    def _last_timestamp_for_day_locked(self, date_key: str, path: Path) -> Optional[str]:
        """Return the last record's timestamp_utc string for `date_key`.

        Caller MUST hold self._lock. Result is cached.
        """
        if date_key in self._last_ts_per_day:
            return self._last_ts_per_day[date_key]
        if not path.exists():
            return None
        last_ts: Optional[str] = None
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp_utc")
                if ts:
                    last_ts = ts
        if last_ts is not None:
            self._last_ts_per_day[date_key] = last_ts
        return last_ts

    # ------------------------------------------------------------------
    def _last_chain_hash_for_day_locked(self, date_key: str, path: Path) -> str:
        """Return the day's last chain_hash, reading from disk if not cached.

        Caller MUST hold self._lock. This is the canonical, atomic-relative-
        to-the-write read used by append_record (S1).
        """
        if date_key in self._last_hash_per_day:
            return self._last_hash_per_day[date_key]
        if not path.exists():
            self._last_hash_per_day[date_key] = _chain.first_prev_hash()
            return self._last_hash_per_day[date_key]
        last = _chain.first_prev_hash()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = rec.get("chain_hash", last)
        self._last_hash_per_day[date_key] = last
        return last

    # ------------------------------------------------------------------
    def append_record(self, record: BaseRecord) -> Dict[str, Any]:
        """Append a frozen record. R1, R2, R4, R6, R8 invariants enforced.

        S1 — chain_hash is RECOMPUTED inside the lock from the freshly-
        read prev_hash. The chain_hash on the incoming record is
        IGNORED for the JSONL line; we use our atomic value instead.
        Callers can pass any non-empty placeholder for chain_hash on
        the dataclass (BaseRecord.__post_init__ requires it non-empty);
        the canonical value goes into JSONL+SQLite.

        S5 — rejects records whose timestamp_utc is strictly older than
        the prior record in the same day file (NonMonotonicTimestampError).

        Returns the persisted dict (post-redaction) for caller bookkeeping.
        Raises:
            LedgerWriteError on any OS / SQLite failure
            SecretLeakError if redaction missed something
            NonMonotonicTimestampError on backwards timestamp
        """
        if not isinstance(record, BaseRecord):
            raise TypeError(
                f"append_record expects BaseRecord, got {type(record).__name__}"
            )

        with self._lock:
            # 1) Serialize
            rec_dict = _record_to_dict(record)
            # 2) Redact (R6) — operate on the dict, not the frozen record
            rec_dict = _redactor.redact(rec_dict)
            # 3) Final boundary assertion — anything suspicious left = LOUD
            _redactor.assert_clean(rec_dict)

            # 4) S1 — read prev_hash + recompute chain_hash atomically.
            path = self.jsonl_path_for(record.timestamp_utc)
            date_key = record.timestamp_utc.strftime("%Y-%m-%d")
            atomic_prev = self._last_chain_hash_for_day_locked(date_key, path)
            rec_dict["prev_hash"] = atomic_prev
            atomic_chain = _chain.compute_chain_hash(atomic_prev, rec_dict)
            rec_dict["chain_hash"] = atomic_chain

            # 5) S5 — monotonic timestamp check
            new_ts_str = rec_dict.get("timestamp_utc", "")
            last_ts_str = self._last_timestamp_for_day_locked(date_key, path)
            if last_ts_str and new_ts_str and new_ts_str < last_ts_str:
                raise NonMonotonicTimestampError(
                    f"timestamp_utc went backwards: new={new_ts_str} "
                    f"last={last_ts_str} record_id={rec_dict.get('record_id')}"
                )

            # 6) JSONL append (FAIL LOUD)
            try:
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec_dict, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                _log.error(
                    "fail-closed mode: JSONL append failed for %s: %s",
                    path, e,
                )
                raise LedgerWriteError(
                    f"JSONL append failed for {path}: {e}"
                ) from e

            # 7) SQLite mirror (FAIL LOUD)
            date_str = record.timestamp_utc.strftime("%Y-%m-%d")
            symbol = rec_dict.get("symbol", "")
            try:
                with sqlite3.connect(str(self._sqlite_path)) as conn:
                    conn.execute(
                        f"INSERT INTO {LEDGER_TABLE} "
                        f"(record_id, record_type, timestamp_utc, sequence_id, "
                        f" parent_record_id, prev_record_id, prev_hash, chain_hash, "
                        f" symbol, date_utc, payload_json) "
                        f"VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            rec_dict["record_id"],
                            rec_dict["record_type"],
                            rec_dict["timestamp_utc"],
                            rec_dict["sequence_id"],
                            rec_dict.get("parent_record_id"),
                            rec_dict.get("prev_record_id"),
                            rec_dict["prev_hash"],
                            rec_dict["chain_hash"],
                            symbol if isinstance(symbol, str) else "",
                            date_str,
                            json.dumps(rec_dict, ensure_ascii=False),
                        ),
                    )
                    conn.commit()
            except sqlite3.Error as e:
                _log.error(
                    "fail-closed mode: SQLite mirror failed for record_id=%s: %s",
                    rec_dict['record_id'], e,
                )
                raise LedgerWriteError(
                    f"SQLite mirror failed for record_id={rec_dict['record_id']}: {e}"
                ) from e

            # 8) Update caches
            self._last_hash_per_day[date_key] = rec_dict["chain_hash"]
            if new_ts_str:
                self._last_ts_per_day[date_key] = new_ts_str
            return rec_dict

    # ------------------------------------------------------------------
    def iter_records_for_day(self, when_utc: datetime) -> Iterator[Dict[str, Any]]:
        """Iterate JSONL records for the day. SOT — JSONL not SQLite."""
        path = self.jsonl_path_for(when_utc)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    # ------------------------------------------------------------------
    def all_records(self) -> Iterator[Dict[str, Any]]:
        """All JSONL records across all days, sorted by filename (UTC date)."""
        for path in sorted(self._base.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    # ------------------------------------------------------------------
    def query_by_type(self, record_type: RecordType) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(self._sqlite_path)) as conn:
            cur = conn.execute(
                f"SELECT payload_json FROM {LEDGER_TABLE} "
                f"WHERE record_type = ? ORDER BY sequence_id",
                (record_type.value,),
            )
            return [json.loads(r[0]) for r in cur.fetchall()]

    def query_by_parent(self, parent_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(self._sqlite_path)) as conn:
            cur = conn.execute(
                f"SELECT payload_json FROM {LEDGER_TABLE} "
                f"WHERE parent_record_id = ? ORDER BY sequence_id",
                (parent_id,),
            )
            return [json.loads(r[0]) for r in cur.fetchall()]

    def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(self._sqlite_path)) as conn:
            cur = conn.execute(
                f"SELECT payload_json FROM {LEDGER_TABLE} WHERE record_id = ?",
                (record_id,),
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None

    # ------------------------------------------------------------------
    def rebuild_sqlite_from_jsonl(self) -> int:
        """Drop the SQLite table and rebuild it from the JSONL ledger.

        R8 — JSONL is SOT. Returns the number of rows written.
        """
        try:
            with sqlite3.connect(str(self._sqlite_path)) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {LEDGER_TABLE}")
                conn.commit()
        except sqlite3.Error as e:
            raise LedgerWriteError(f"sqlite drop failed: {e}") from e
        self._init_sqlite()
        n = 0
        with sqlite3.connect(str(self._sqlite_path)) as conn:
            for rec in self.all_records():
                date_str = rec["timestamp_utc"][:10]
                conn.execute(
                    f"INSERT INTO {LEDGER_TABLE} "
                    f"(record_id, record_type, timestamp_utc, sequence_id, "
                    f" parent_record_id, prev_record_id, prev_hash, chain_hash, "
                    f" symbol, date_utc, payload_json) "
                    f"VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        rec["record_id"],
                        rec["record_type"],
                        rec["timestamp_utc"],
                        rec["sequence_id"],
                        rec.get("parent_record_id"),
                        rec.get("prev_record_id"),
                        rec["prev_hash"],
                        rec["chain_hash"],
                        rec.get("symbol", "") if isinstance(rec.get("symbol", ""), str) else "",
                        date_str,
                        json.dumps(rec, ensure_ascii=False),
                    ),
                )
                n += 1
            conn.commit()
        return n

    # ------------------------------------------------------------------
    def verify_chain_for_day(self, when_utc: datetime) -> None:
        """Replay the chain for one JSONL day. Raises ChainBrokenError on bad chain."""
        records = list(self.iter_records_for_day(when_utc))
        _chain.verify_chain(records)

    def verify_full_chain(self) -> None:
        """Replay the entire ledger across all day files."""
        records = list(self.all_records())
        _chain.verify_chain(records)

    # ------------------------------------------------------------------
    def verify_storage_consistency(self) -> None:
        """S6 — Walk JSONL and verify each record exists in SQLite with the
        same chain_hash. Raises StorageConsistencyError on any mismatch.

        SQLite-only mutations (an attacker UPDATEing a row directly) are
        invisible to verify_chain (which only reads JSONL). This method
        is the cross-check.
        """
        try:
            conn = sqlite3.connect(str(self._sqlite_path))
        except sqlite3.Error as e:
            raise StorageConsistencyError(f"sqlite open failed: {e}") from e

        try:
            jsonl_ids: List[str] = []
            for rec in self.all_records():
                rid = rec.get("record_id")
                jsonl_ids.append(rid)
                cur = conn.execute(
                    f"SELECT chain_hash, prev_hash, payload_json FROM {LEDGER_TABLE} "
                    f"WHERE record_id = ?",
                    (rid,),
                )
                row = cur.fetchone()
                if row is None:
                    raise StorageConsistencyError(
                        f"record_id={rid} present in JSONL but missing in SQLite"
                    )
                sq_chain, sq_prev, _payload = row
                if sq_chain != rec.get("chain_hash"):
                    raise StorageConsistencyError(
                        f"chain_hash mismatch for record_id={rid}: "
                        f"jsonl={rec.get('chain_hash')[:16]}... sqlite={sq_chain[:16]}..."
                    )
                if sq_prev != rec.get("prev_hash"):
                    raise StorageConsistencyError(
                        f"prev_hash mismatch for record_id={rid}"
                    )
            # Also assert SQLite has no extras
            cur = conn.execute(f"SELECT COUNT(*) FROM {LEDGER_TABLE}")
            (n_sqlite,) = cur.fetchone()
            if n_sqlite != len(jsonl_ids):
                raise StorageConsistencyError(
                    f"SQLite has {n_sqlite} records but JSONL has {len(jsonl_ids)}"
                )
        finally:
            conn.close()
