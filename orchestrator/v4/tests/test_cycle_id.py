"""HYDRA V4 — cycle_id minting tests."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from orchestrator.v4.cycle_id import mint_cycle_id
from orchestrator.v4.orchestrator_constants import CYCLE_ID_PREFIX


def test_cycle_id_has_expected_prefix():
    cid = mint_cycle_id()
    assert cid.startswith(f"{CYCLE_ID_PREFIX}-")


def test_cycle_id_format():
    cid = mint_cycle_id(datetime(2025, 7, 15, 14, 0, 0, tzinfo=timezone.utc))
    # hyd-YYYYMMDDTHHMMSS%fZ-<12 hex>
    pat = re.compile(r"^hyd-\d{8}T\d{6}\d+Z-[0-9a-f]{12}$")
    assert pat.match(cid), f"unexpected format: {cid}"


def test_cycle_id_unique_under_rapid_calls():
    ids = {mint_cycle_id() for _ in range(200)}
    assert len(ids) == 200, "duplicate cycle_id detected"


def test_cycle_id_uses_now_when_naive():
    cid = mint_cycle_id(datetime(2025, 7, 15, 14, 0, 0))  # naive
    assert cid.startswith(f"{CYCLE_ID_PREFIX}-")


def test_cycle_id_normalises_tz_to_utc():
    from zoneinfo import ZoneInfo
    ny = datetime(2025, 7, 15, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    cid = mint_cycle_id(ny)
    # 10:00 NY EDT == 14:00 UTC → cid should embed 20250715T140000…Z
    assert "20250715T1400" in cid
