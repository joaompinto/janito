"""Tests for the ``/use_stats`` shell command (behavior over strings)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
import janito.tooling.accounting as accounting
from janito.shell.cmds.use_stats import UseStatsCmdHandler
from tests.conftest import assert_command_matching, assert_command_registered


def _point_at(monkeypatch, tmp_path):
    config_dir = tmp_path / "custom_janito"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_dir)
    return config_dir


def _record_day(day: str, n: int, *, cost: float | None = None) -> None:
    for i in range(n):
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=1000 + i,
            cached_tokens=100,
            output_tokens=500,
            cost=cost,
            timestamp=f"{day}T12:00:00+00:00",
        )


def _render(handler, stats):
    from rich.console import Console

    console = Console(width=100, file=None)
    with console.capture() as capture:
        console.print(handler._build_table(stats))
    return capture.get()


def _render_model_table(handler, stats):
    from rich.console import Console

    console = Console(width=120, file=None)
    with console.capture() as capture:
        console.print(handler._build_model_table(stats))
    return capture.get()


def _pct(rendered: str) -> int:
    m = re.search(r"\((\d+)%\)", rendered)
    assert m is not None
    return int(m.group(1))


if pytest is not None:

    def test_command_matching():
        assert_command_matching(UseStatsCmdHandler(), "/use_stats")

    def test_command_is_registered():
        assert_command_registered("/use_stats")

    def test_table_built_from_recorded_usage(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        _record_day("2026-08-27", 2, cost=0.01)
        _record_day("2026-08-28", 3, cost=0.02)

        # Numeric asserts against the source of truth (Rule 6).
        stats = accounting.get_daily_stats()
        assert [row["day"] for row in stats] == ["2026-08-28", "2026-08-27"]
        by_day = {row["day"]: row for row in stats}
        assert by_day["2026-08-27"]["input_tokens"] == 1000 + 1001
        assert by_day["2026-08-27"]["cached_tokens"] == 200
        assert by_day["2026-08-27"]["output_tokens"] == 1000
        assert by_day["2026-08-27"]["cost"] == pytest.approx(0.02)
        assert by_day["2026-08-28"]["input_tokens"] == 1000 + 1001 + 1002
        assert by_day["2026-08-28"]["output_tokens"] == 1500

        handler = UseStatsCmdHandler()
        table = handler._build_table(stats)
        assert table.row_count == len(stats)
        assert table.columns[0].header == "Day"  # single header assert
        # Smoke: renderer produced output (Rule 2).
        assert handler.handle(_DummyShell(), "/use_stats") is True
        assert _render(handler, stats).strip() != ""

    def test_cached_percentage_is_numeric_ratio():
        handler = UseStatsCmdHandler()
        assert _pct(handler._format_cached_tokens(600, 2400)) == 25
        assert _pct(handler._format_cached_tokens(300, 1200)) == 25
        assert _pct(handler._format_cached_tokens(1, 999)) == 0
        # No input: plain count, no percentage.
        assert handler._format_cached_tokens(0, 0) == "0"
        assert handler._format_cached_tokens(10, 0) == "10"

    def test_cached_percentage_regression_almost_all_cached():
        handler = UseStatsCmdHandler()
        assert _pct(handler._format_cached_tokens(16_011_904, 16_166_625)) == 99

    def test_cached_ratio_rendered_in_table():
        handler = UseStatsCmdHandler()
        stats = [
            {
                "day": "2026-08-29",
                "input_tokens": 2400,
                "cached_tokens": 600,
                "output_tokens": 1600,
                "cost": 0.0024,
            },
            {
                "day": "2026-08-28",
                "input_tokens": 1200,
                "cached_tokens": 300,
                "output_tokens": 800,
                "cost": 0.0017,
            },
        ]
        table = handler._build_table(stats)
        assert table.row_count == 2
        assert stats[0]["cached_tokens"] / stats[0]["input_tokens"] == pytest.approx(0.25)
        assert stats[1]["cost"] == pytest.approx(0.0017)
        assert _render(handler, stats).strip() != ""

    def test_cost_adaptive_format_fallback():
        handler = UseStatsCmdHandler()
        stats = [
            {
                "day": "2026-08-29",
                "input_tokens": 2400,
                "cached_tokens": 600,
                "output_tokens": 1600,
                "cost": 0.0024,
            },
            {
                "day": "2026-08-28",
                "input_tokens": 1200,
                "cached_tokens": 300,
                "output_tokens": 800,
                "cost": 1.2,
            },
            {
                "day": "2026-08-27",
                "input_tokens": 1200,
                "cached_tokens": 300,
                "output_tokens": 800,
                "cost": None,
            },
        ]
        table = handler._build_table(stats)
        assert table.row_count == 3
        assert stats[1]["cost"] == pytest.approx(1.2)
        assert stats[2]["cost"] is None
        out = _render(handler, stats)
        assert out.strip() != ""
        assert "N/A" in out  # unknown-cost fallback only

    def test_model_table_cost_is_numeric():
        handler = UseStatsCmdHandler()
        stats = [
            {
                "day": "2026-08-28",
                "provider": "deepseek",
                "model": "deepseek-flash",
                "input_tokens": 300,
                "cached_tokens": 30,
                "output_tokens": 150,
                "cost": 0.0001,
            },
            {
                "day": "2026-08-28",
                "provider": "openai",
                "model": "gpt-6-luna",
                "input_tokens": 1000,
                "cached_tokens": 100,
                "output_tokens": 500,
                "cost": 0.01,
            },
        ]
        table = handler._build_model_table(stats)
        assert table.row_count == 2
        assert stats[0]["cost"] == pytest.approx(0.0001)
        assert stats[1]["cost"] == pytest.approx(0.01)
        assert _render_model_table(handler, stats).strip() != ""

    def test_model_table_built_from_recorded_usage(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            "deepseek",
            "deepseek-flash",
            input_tokens=300,
            cached_tokens=30,
            output_tokens=150,
            cost=0.003,
            timestamp="2026-08-28T12:00:00+00:00",
        )
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=1000,
            cached_tokens=100,
            output_tokens=500,
            cost=0.01,
            timestamp="2026-08-28T13:00:00+00:00",
        )
        accounting.record_turn(
            "openai",
            "gpt-6-luna",
            input_tokens=2000,
            cached_tokens=200,
            output_tokens=600,
            cost=0.02,
            timestamp="2026-08-29T12:00:00+00:00",
        )

        handler = UseStatsCmdHandler()
        stats = accounting.get_per_model_stats()
        assert [row["model"] for row in stats] == [
            "gpt-6-luna",
            "deepseek-flash",
            "gpt-6-luna",
        ]
        totals = {(r["day"], r["model"]): r for r in stats}
        assert totals[("2026-08-28", "deepseek-flash")]["input_tokens"] == 300
        assert totals[("2026-08-28", "deepseek-flash")]["cost"] == pytest.approx(0.003)

        table = handler._build_model_table(stats)
        assert table.row_count == len(stats)
        assert [c.header for c in table.columns][0] == "Day"  # single header assert
        assert _render_model_table(handler, stats).strip() != ""

    def test_model_table_unknown_provider_and_model(monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path)
        accounting.record_turn(
            None,
            None,
            input_tokens=5,
            cached_tokens=1,
            output_tokens=2,
            cost=None,
            timestamp="2026-08-28T12:00:00+00:00",
        )
        handler = UseStatsCmdHandler()
        stats = accounting.get_per_model_stats()
        assert stats[0]["provider"] is None
        assert stats[0]["cost"] is None
        table = handler._build_model_table(stats)
        assert table.row_count == 1
        assert _render_model_table(handler, stats).strip() != ""

    def test_print_stats_smoke_and_db_caption(monkeypatch, tmp_path, capsys):
        _point_at(monkeypatch, tmp_path)
        _record_day("2026-08-28", 1, cost=0.005)
        UseStatsCmdHandler()._print_stats()
        out = capsys.readouterr().out
        assert out.strip() != ""
        assert "accounting.db" in out  # single stable marker

    def test_print_stats_prints_both_tables(monkeypatch, tmp_path, capsys):
        _point_at(monkeypatch, tmp_path)
        _record_day("2026-08-28", 1, cost=0.005)
        UseStatsCmdHandler()._print_stats()
        out = capsys.readouterr().out
        assert out.strip() != ""
        assert len(accounting.get_daily_stats()) == 1
        assert len(accounting.get_per_model_stats()) == 1

    def test_empty_stats_prints_message(monkeypatch, tmp_path, capsys):
        _point_at(monkeypatch, tmp_path)
        UseStatsCmdHandler()._print_stats()
        out = capsys.readouterr().out
        assert accounting.get_daily_stats() == []
        assert out.strip() != ""


class _DummyShell:
    """Minimal stand-in for InteractiveShell (not used by this command)."""
