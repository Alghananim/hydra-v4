"""Tests for audit log reproducibility, uniqueness, bound, and immutability."""

from __future__ import annotations

import json

import pytest

from gatemind.v4 import GateMindV4
from gatemind.v4 import audit_log as audit_log_mod
from gatemind.v4.audit_log import (
    audit_store_size,
    clear_audit_store,
    fetch_audit,
    make_audit_id,
    record_audit,
    to_json,
)
from gatemind.v4.gatemind_constants import MAX_AUDIT_ENTRIES

from .conftest import (
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    now_in_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


def test_audit_id_format():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    aid = make_audit_id(now_in_ny_window(2), "EUR_USD", n, m, c)
    assert aid.startswith("gm-")
    assert "EUR_USD" in aid


def test_audit_id_changes_with_inputs():
    now = now_in_ny_window(2)
    a = make_audit_id(now, "EUR_USD",
                      make_brain_output_aplus_buy("NewsMind"),
                      make_brain_output_aplus_buy("MarketMind"),
                      make_brain_output_aplus_buy("ChartMind"))
    b = make_audit_id(now, "EUR_USD",
                      make_brain_output_aplus_sell("NewsMind"),
                      make_brain_output_aplus_sell("MarketMind"),
                      make_brain_output_aplus_sell("ChartMind"))
    assert a != b


def test_audit_id_in_decision_matches_store(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    snap = fetch_audit(decision.audit_id)
    assert snap is not None
    assert snap["audit_id"] == decision.audit_id
    assert snap["decision"]["gate_decision"] == "ENTER_CANDIDATE"


def test_audit_snapshot_captures_all_inputs(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    snap = fetch_audit(decision.audit_id)
    for brain_key in ("news", "market", "chart"):
        assert brain_key in snap["inputs"]
        assert snap["inputs"][brain_key]["decision"] == "BUY"
        assert snap["inputs"][brain_key]["grade"] == "A+"


def test_audit_snapshot_serialisable(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    snap = fetch_audit(decision.audit_id)
    blob = to_json(snap)
    parsed = json.loads(blob)
    assert parsed["audit_id"] == decision.audit_id


def test_audit_trail_has_rule_entries(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    rule_tags = [t.split(":")[0] for t in decision.audit_trail]
    for required in ("R1_schema", "R2_session", "R3_grade", "R4_brain_block",
                      "R5_kill_flag", "R6_direction", "R7_unanimous_wait", "R8_enter"):
        assert required in rule_tags


def test_same_inputs_produce_same_audit_id(gate):
    """Determinism — same inputs at same time → same audit_id."""
    now = now_in_ny_window(2)
    n = make_brain_output_aplus_buy("NewsMind", now_utc=now)
    m = make_brain_output_aplus_buy("MarketMind", now_utc=now)
    c = make_brain_output_aplus_buy("ChartMind", now_utc=now)
    a = make_audit_id(now, "EUR_USD", n, m, c)
    b = make_audit_id(now, "EUR_USD", n, m, c)
    assert a == b


def test_clear_audit_store_works():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    aid = make_audit_id(now_in_ny_window(2), "EUR_USD", n, m, c)
    # We need a decision object to call record_audit; use the gate
    gate = GateMindV4()
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert fetch_audit(decision.audit_id) is not None
    clear_audit_store()
    assert fetch_audit(decision.audit_id) is None


# ---------------------------------------------------------------------------
# G1 — bounded LRU
# ---------------------------------------------------------------------------
def test_audit_store_bounded(monkeypatch):
    """Inserting MAX_AUDIT_ENTRIES + 1 entries must evict the oldest."""
    # Lower the cap for test speed; library uses MAX_AUDIT_ENTRIES from
    # gatemind_constants. Patch in-place on the audit_log module.
    cap = 50
    monkeypatch.setattr(audit_log_mod, "MAX_AUDIT_ENTRIES", cap, raising=True)
    clear_audit_store()

    gate = GateMindV4()
    # Build cap+1 unique decisions by varying confidence (-> distinct audit_ids).
    decisions = []
    base_now = now_in_ny_window(2)
    for i in range(cap + 1):
        # Use distinct microsecond offsets to get distinct timestamps + ids.
        from datetime import timedelta
        now_i = base_now + timedelta(microseconds=i * 1000)
        n = make_brain_output_aplus_buy("NewsMind", now_utc=now_i)
        m = make_brain_output_aplus_buy("MarketMind", now_utc=now_i)
        c = make_brain_output_aplus_buy("ChartMind", now_utc=now_i)
        decisions.append(gate.evaluate(n, m, c, now_utc=now_i))

    assert audit_store_size() == cap, (
        f"expected size capped at {cap}, got {audit_store_size()}"
    )
    # Oldest should be evicted; newest should be present.
    assert fetch_audit(decisions[0].audit_id) is None
    assert fetch_audit(decisions[-1].audit_id) is not None


def test_audit_store_bounded_default_cap_is_10000():
    """The locked default cap is 10_000 entries."""
    assert MAX_AUDIT_ENTRIES == 10_000


# ---------------------------------------------------------------------------
# G3 — fetch returns deep copy
# ---------------------------------------------------------------------------
def test_fetch_audit_returns_immutable_copy(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    snap1 = fetch_audit(decision.audit_id)
    assert snap1 is not None

    # Mutate the returned snapshot aggressively.
    snap1["audit_id"] = "TAMPERED"
    snap1["decision"]["gate_decision"] = "ENTER_CANDIDATE_FAKE"
    snap1["inputs"]["news"]["grade"] = "F"
    snap1["decision"]["audit_trail"].append("INJECTED")

    # Re-fetch — original must be untouched.
    snap2 = fetch_audit(decision.audit_id)
    assert snap2["audit_id"] == decision.audit_id
    assert snap2["audit_id"] != "TAMPERED"
    assert snap2["decision"]["gate_decision"] == "ENTER_CANDIDATE"
    assert snap2["inputs"]["news"]["grade"] == "A+"
    assert "INJECTED" not in snap2["decision"]["audit_trail"]
    # And the two fetched objects are distinct instances.
    assert snap1 is not snap2


# ---------------------------------------------------------------------------
# G5 — audit_id format consistency
# ---------------------------------------------------------------------------
def test_audit_id_format_consistent_across_outcomes(gate):
    """ENTER, BLOCK (rule), and BLOCK (schema-fail) all share `gm-` prefix."""
    # ENTER path
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    enter_dec = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert enter_dec.audit_id.startswith("gm-")

    # BLOCK at R2 (outside session)
    from .conftest import now_outside_ny_window
    block_dec = gate.evaluate(n, m, c, now_utc=now_outside_ny_window())
    assert block_dec.audit_id.startswith("gm-")

    # BLOCK at R1 (schema fail) — pass a non-BrainOutput
    from .conftest import make_brain_output_invalid_schema
    fake = make_brain_output_invalid_schema("NewsMind")
    schemafail_dec = gate.evaluate(fake, m, c, now_utc=now_in_ny_window(2))
    assert schemafail_dec.audit_id.startswith("gm-")

    # All three share the SAME `gm-` prefix; the outcome is conveyed through
    # `.gate_decision` / `.blocking_reason`, NOT through the audit_id format.
    for dec in (enter_dec, block_dec, schemafail_dec):
        assert dec.audit_id.startswith("gm-")
