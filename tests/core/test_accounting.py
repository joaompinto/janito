"""
Tests for the SQLite-backed overall-use accounting.

``janito.tooling.accounting`` appends one row per completed LLM turn to an
``accounting.db`` SQLite database inside the Janito config directory (issue
#72). These tests point the config dir at a temporary directory and verify
the database is created with the expected schema, values round-trip and the
cost accessor returns numeric dollars.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
import janito.tooling.accounting as accounting
from janito.providers.costing import get_provider_cost_value

#: All columns of the ``accounting`` table (including the rowid alias).
EXPECTED_COLUMNS = {
    "id",
    "cwd",
    "timestamp",
    "provider",
    "model",
    "input_tokens",
    "cached_tokens",
    "output_tokens",
    "cost",
}


def _point_at(monkeypatch, tmp_path):
    """Point the global config dir at a temp directory and return it."""
    config_dir = tmp_path / "custom_janito"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_dir)
    return config_dir


if pytest is not None:

    def test_db_path_is_in_config_dir(monkeypatch, tmp_path):
        config_dir = _point_at(monkeypatch, tmp_path)
        assert accounting.get_db_path() == config_dir / "accounting.db"

    def test_record_creates_db_with_expected_schema(monkeypatch, tmp_path):
        config_dir = _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=1000,
            cached_tokens=200,
            output_tokens=300,
        )

        db_path = config_dir / "accounting.db"
        assert db_path.exists()

        conn = sqlite3.connect(str(db_path))
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(accounting)").fetchall()}
            assert cols == EXPECTED_COLUMNS
        finally:
            conn.close()

    def test_record_round_trips_values(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "deepseek",
            "deepseek-flash",
            input_tokens=180,
            cached_tokens=10,
            output_tokens=120,
            cost=0.0088,
        )

        records = accounting.get_records()
        assert len(records) == 1
        row = records[0]
        assert row["cwd"] == str(Path.cwd())
        assert row["timestamp"]
        assert row["provider"] == "deepseek"
        assert row["model"] == "deepseek-flash"
        assert row["input_tokens"] == 180
        assert row["cached_tokens"] == 10
        assert row["output_tokens"] == 120
        assert row["cost"] == pytest.approx(0.0088)

    def test_none_counters_stored_as_null(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "anthropic",
            "claude-x",
            input_tokens=None,
            cached_tokens=None,
            output_tokens=None,
            cost=None,
        )
        row = accounting.get_records()[0]
        assert row["input_tokens"] is None
        assert row["cached_tokens"] is None
        assert row["output_tokens"] is None
        assert row["cost"] is None

    def test_get_records_newest_first_with_limit(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        for i in range(5):
            accounting.record_turn("openai", "m", input_tokens=i, cached_tokens=0, output_tokens=i)
        limited = accounting.get_records(limit=2)
        assert [r["input_tokens"] for r in limited] == [4, 3]

    def test_empty_cwd_is_ignored(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn("openai", "m", input_tokens=1, cached_tokens=0, output_tokens=1, cwd="")
        assert accounting.get_records() == []

    def test_prune_removes_only_old_entries(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "old",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=(now - timedelta(days=30)).isoformat(),
        )
        accounting.record_turn(
            "openai",
            "recent",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=now.isoformat(),
        )

        deleted = accounting.prune_old_entries()
        assert deleted == 1
        records = accounting.get_records()
        assert len(records) == 1
        assert records[0]["model"] == "recent"

    def test_prune_keeps_entries_younger_than_cutoff(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "young",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=(now - timedelta(days=9)).isoformat(),
        )
        # Just under the 10-day cutoff (with margin so the test cannot race
        # against the "now" computed inside prune_old_entries).
        accounting.record_turn(
            "openai",
            "boundary",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=(now - timedelta(days=10) + timedelta(seconds=30)).isoformat(),
        )

        assert accounting.prune_old_entries() == 0
        assert len(accounting.get_records()) == 2

    def test_prune_empty_db_returns_zero(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        assert accounting.prune_old_entries() == 0

    def test_prune_custom_days(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "two-days",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=(now - timedelta(days=2)).isoformat(),
        )
        accounting.record_turn(
            "openai",
            "fresh",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=now.isoformat(),
        )

        assert accounting.prune_old_entries(days=1) == 1
        records = accounting.get_records()
        assert len(records) == 1
        assert records[0]["model"] == "fresh"

    def test_cost_value_from_known_provider():
        """get_provider_cost_value returns numeric dollars for known models."""
        # 100k input tokens (below OpenAI's high-context threshold) at the
        # $0.10/1M cache-miss rate -> $0.01.
        value = get_provider_cost_value("openai", "gpt-6-luna", 100_000, 0, 0)
        assert value == pytest.approx(0.01)

    def test_cost_value_none_for_unknown_provider():
        assert get_provider_cost_value("nope", "model", 1, 1, 0) is None

    def test_cost_value_none_for_unknown_model():
        assert get_provider_cost_value("openai", "not-a-real-model", 1, 1, 0) is None

    def test_daily_stats_groups_and_sums_by_day(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "m",
            input_tokens=1000,
            cached_tokens=100,
            output_tokens=500,
            cost=0.01,
            timestamp=(now - timedelta(days=1)).isoformat(),
        )
        accounting.record_turn(
            "openai",
            "m",
            input_tokens=2000,
            cached_tokens=200,
            output_tokens=600,
            cost=0.02,
            timestamp=(now - timedelta(days=1)).isoformat(),
        )
        accounting.record_turn(
            "openai",
            "m",
            input_tokens=3000,
            cached_tokens=300,
            output_tokens=700,
            cost=0.03,
            timestamp=now.isoformat(),
        )

        stats = accounting.get_daily_stats()
        assert [row["day"] for row in stats] == [
            now.date().isoformat(),
            (now - timedelta(days=1)).date().isoformat(),
        ]
        today, older = stats
        assert older["input_tokens"] == 3000
        assert older["cached_tokens"] == 300
        assert older["output_tokens"] == 1100
        assert older["cost"] == pytest.approx(0.03)
        assert today["cost"] == pytest.approx(0.03)

    def test_daily_stats_null_tokens_and_cost(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "anthropic",
            "claude-x",
            input_tokens=None,
            cached_tokens=None,
            output_tokens=None,
            cost=None,
        )
        row = accounting.get_daily_stats()[0]
        # Unknown token counters aggregate to 0; unknown cost stays None.
        assert row["input_tokens"] == 0
        assert row["cached_tokens"] == 0
        assert row["output_tokens"] == 0
        assert row["cost"] is None

    def test_daily_stats_limits_to_last_days(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        for offset in range(15):
            accounting.record_turn(
                "openai",
                "m",
                input_tokens=1,
                cached_tokens=0,
                output_tokens=1,
                timestamp=(now - timedelta(days=offset)).isoformat(),
            )

        stats = accounting.get_daily_stats(days=5)
        assert len(stats) == 5
        days = [row["day"] for row in stats]
        assert days == sorted(days, reverse=True)  # newest first
        assert days[0] == now.date().isoformat()

    def test_daily_stats_empty_db(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        assert accounting.get_daily_stats() == []

    def test_daily_stats_clamps_days_below_one(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "m",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=now.isoformat(),
        )
        stats = accounting.get_daily_stats(days=0)
        assert len(stats) == 1
        assert stats[0]["day"] == now.date().isoformat()

    def test_per_model_stats_groups_by_day_provider_model(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).isoformat()
        today = now.isoformat()
        # Two providers on yesterday, one provider/model on today, plus a
        # second turn that must be summed into the same group.
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=1000,
            cached_tokens=100,
            output_tokens=500,
            cost=0.01,
            timestamp=yesterday,
        )
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=2000,
            cached_tokens=200,
            output_tokens=600,
            cost=0.02,
            timestamp=yesterday,
        )
        accounting.record_turn(
            "deepseek",
            "deepseek-flash",
            input_tokens=300,
            cached_tokens=30,
            output_tokens=150,
            cost=0.003,
            timestamp=yesterday,
        )
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=4000,
            cached_tokens=400,
            output_tokens=700,
            cost=0.04,
            timestamp=today,
        )

        stats = accounting.get_per_model_stats()
        # Newest day first, then provider, then model (rows checked below).
        rows = [
            (
                r["day"],
                r["provider"],
                r["model"],
                r["input_tokens"],
                r["cached_tokens"],
                r["output_tokens"],
                r["cost"],
            )
            for r in stats
        ]
        assert rows == [
            (
                now.date().isoformat(),
                "openai",
                "gpt-6-luna",
                4000,
                400,
                700,
                pytest.approx(0.04),
            ),
            (
                (now - timedelta(days=1)).date().isoformat(),
                "deepseek",
                "deepseek-flash",
                300,
                30,
                150,
                pytest.approx(0.003),
            ),
            (
                (now - timedelta(days=1)).date().isoformat(),
                "openai",
                "gpt-6-luna",
                3000,
                300,
                1100,
                pytest.approx(0.03),
            ),
        ]

    def test_per_model_stats_null_tokens_and_cost(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "anthropic",
            "claude-x",
            input_tokens=None,
            cached_tokens=None,
            output_tokens=None,
            cost=None,
        )
        row = accounting.get_per_model_stats()[0]
        assert row["provider"] == "anthropic"
        assert row["model"] == "claude-x"
        # Unknown token counters aggregate to 0; unknown cost stays None.
        assert row["input_tokens"] == 0
        assert row["cached_tokens"] == 0
        assert row["output_tokens"] == 0
        assert row["cost"] is None

    def test_per_model_stats_unknown_provider_model_grouped(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            None,
            None,
            input_tokens=5,
            cached_tokens=1,
            output_tokens=2,
            cost=None,
        )
        accounting.record_turn(
            None,
            None,
            input_tokens=5,
            cached_tokens=1,
            output_tokens=2,
            cost=None,
        )
        rows = accounting.get_per_model_stats()
        assert len(rows) == 1
        assert rows[0]["provider"] is None
        assert rows[0]["model"] is None
        assert rows[0]["input_tokens"] == 10

    def test_per_model_stats_limits_to_last_days(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        for offset in range(15):
            accounting.record_turn(
                "openai",
                "m",
                input_tokens=1,
                cached_tokens=0,
                output_tokens=1,
                timestamp=(now - timedelta(days=offset)).isoformat(),
            )

        rows = accounting.get_per_model_stats(days=5)
        days = [r["day"] for r in rows]
        assert len(days) == 5
        assert days == sorted(days, reverse=True)  # newest first
        assert days[0] == now.date().isoformat()

    def test_per_model_stats_empty_db(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        assert accounting.get_per_model_stats() == []

    def test_per_model_stats_clamps_days_below_one(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        now = datetime.now(timezone.utc)
        accounting.record_turn(
            "openai",
            "m",
            input_tokens=1,
            cached_tokens=0,
            output_tokens=1,
            timestamp=now.isoformat(),
        )
        rows = accounting.get_per_model_stats(days=0)
        assert len(rows) == 1
        assert rows[0]["day"] == now.date().isoformat()

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        import tempfile

        class _MP:
            def setattr(self, obj, name, value):
                setattr(obj, name, value)

        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                with tempfile.TemporaryDirectory() as d:
                    if "tmp_path" in fn.__code__.co_varnames:
                        fn(_MP(), Path(d))
                    else:
                        fn()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
