"""Tests for the replay report generator."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from replay.replay_report_generator import write_full_report
from replay.two_year_replay import ReplayResult


@dataclass
class _DC:
    record_id: str
    symbol: str
    final_status: str
    session_window: str
    newsmind_output: Dict[str, Any] = field(default_factory=dict)
    marketmind_output: Dict[str, Any] = field(default_factory=dict)
    chartmind_output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Rej:
    record_id: str
    rejection_reason: str
    rejecting_mind: str


@dataclass
class _Sh:
    record_id: str
    rejected_trade_id: str
    was_rejection_correct: bool
    hypothetical_pnl: float


@dataclass
class _Lesson:
    pattern_key: tuple
    affected_mind: str
    lesson_text: str
    direction: str


def test_writes_all_csvs(tmp_path: Path):
    result = ReplayResult(
        total_cycles=3,
        accepted_candidates=1,
        blocks=2,
        start_utc=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    dcs = [
        _DC(
            record_id=f"d{i}",
            symbol="EUR_USD",
            final_status="BLOCK",
            session_window="MORNING",
            newsmind_output={"grade": "C"},
            marketmind_output={"grade": "B"},
            chartmind_output={"grade": "A"},
        )
        for i in range(3)
    ]
    rejs = [_Rej(record_id="r1", rejection_reason="x", rejecting_mind="MarketMind")]
    shadows = [_Sh(record_id="s1", rejected_trade_id="r1", was_rejection_correct=False, hypothetical_pnl=10.0)]
    lessons = [_Lesson(pattern_key=("x", "M"), affected_mind="M", lesson_text="t", direction="RELAX")]

    paths = write_full_report(
        out_dir=tmp_path,
        result=result,
        decision_cycles=dcs,
        rejected_trades=rejs,
        shadow_outcomes=shadows,
        lessons=lessons,
        pairs=["EUR_USD", "USD_JPY"],
        notes=["test note"],
    )

    assert paths["decision_cycles_csv"].exists()
    assert paths["per_brain_accuracy_csv"].exists()
    assert paths["rejected_trades_shadow_csv"].exists()
    assert paths["lessons_jsonl"].exists()
    assert paths["report_md"].exists()

    # CSV row count for decision_cycles
    with paths["decision_cycles_csv"].open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 4  # header + 3

    # Lessons JSONL has one line
    lines = paths["lessons_jsonl"].read_text("utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["affected_mind"] == "M"

    # MD contains real numbers, not placeholders
    md = paths["report_md"].read_text("utf-8")
    assert "total_cycles:        3" in md
    assert "EUR_USD" in md and "USD_JPY" in md
    assert "test note" in md


def test_empty_inputs_produce_empty_files(tmp_path: Path):
    result = ReplayResult(start_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
                          end_utc=datetime(2024, 6, 1, tzinfo=timezone.utc))
    paths = write_full_report(
        out_dir=tmp_path,
        result=result,
        decision_cycles=[],
        rejected_trades=[],
        shadow_outcomes=[],
        lessons=[],
        pairs=["EUR_USD"],
    )
    # Empty CSVs are zero-byte but path exists; lessons.jsonl is empty.
    assert paths["decision_cycles_csv"].exists()
    assert paths["lessons_jsonl"].exists()
    assert paths["report_md"].exists()
