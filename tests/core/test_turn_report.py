"""
Tests for the end-of-turn report.

The CLI no longer prints the token-usage summary inside the per-client
``_finalize`` helpers.  Instead ``Client.run_turn`` builds a
:class:`~janito.llm_adapters.usage.TurnInfo` per turn, folds every round's usage
into it (tool-call rounds included), and delivers it -- together with the
turn's resolved ``APIConfig``, whose provider / model / max tokens feed the
report -- to the injected observer's ``on_turn_complete`` when the turn
finishes (the CLI's ``RichTurnObserver`` renders it via
:func:`~janito.ui.usage.display_turn_usage` and records
the overall-use accounting row).  These tests pin that contract.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from io import StringIO  # noqa: E402

import pytest  # noqa: E402
from rich.console import Console  # noqa: E402

import janito.config_dir as config_dir_mod  # noqa: E402
import janito.tooling.tools_registry as tools_registry  # noqa: E402
import janito.tooling.used_files as used_files  # noqa: E402
from janito.llm_adapters.usage import (  # noqa: E402
    TurnInfo,
    format_elapsed,
    format_tokens,
    normalize_usage,
)
from janito.ui.usage import display_turn_usage  # noqa: E402


def _usage_parts(console_output: str) -> dict[str, str]:
    """Parse the ``=== Time | In | Out | Cached | Cost ===`` line into parts.

    The expected part *values* are composed from the source-of-truth
    formatters (:func:`format_tokens` / :func:`format_elapsed`) per
    dev-docs/testing.md Rule 6 (numbers over words): the labels and order
    are structural, the numbers come from the real formatting code.
    """
    for line in console_output.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            body = line[len("=== ") : -len(" ===")]
            return {part.split(": ", 1)[0]: part.split(": ", 1)[1] for part in body.split(" | ")}
    raise AssertionError(f"no '=== ... ===' usage summary line in:\n{console_output}")


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch):
    """Point the config dir at a temp dir so accounting.db writes stay local."""
    monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path / "janito")


def _register(monkeypatch, name, permissions):
    """Register a fake tool so the used-files tracker knows its permission."""
    monkeypatch.setattr(tools_registry, "_tools_initialized", True)
    fake = lambda **kwargs: {"success": True}  # noqa: E731
    fake._tool_permissions = permissions
    monkeypatch.setitem(tools_registry.AVAILABLE_TOOLS, name, fake)


def _token_stats(**kw):
    defaults = dict(
        total=100,
        last_input=60,
        last_output=40,
        last_cached=5,
        turn_input=180,
        turn_cached=10,
        turn_output=120,
    )
    defaults.update(kw)
    return TurnInfo(**defaults)


def _config(**kw):
    """Build the resolved APIConfig the turn report renders with."""
    from conftest import make_config

    defaults = dict(
        provider="deepseek",
        model="deepseek-flash",
        max_input_tokens=65536,
        max_output_tokens=8192,
    )
    defaults.update(kw)
    return make_config(**defaults)


class TestNormalizeUsageWithTurnInfo:
    def test_passes_token_stats_through(self):
        stats = _token_stats()
        assert normalize_usage(stats) == {
            "total": 100,
            "input": 60,
            "output": 40,
            "cached": 5,
        }

    def test_raw_usage_still_normalizes(self):
        raw = SimpleNamespace(
            prompt_tokens=60,
            completion_tokens=40,
            total_tokens=100,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5),
        )
        assert normalize_usage(raw) == {
            "total": 100,
            "input": 60,
            "output": 40,
            "cached": 5,
        }


class TestDisplayTurnUsage:
    def _render(self, token_stats, api_config=None):
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        display_turn_usage(
            token_stats,
            api_config or _config(),
            console=console,
        )
        return buf.getvalue()

    def test_renders_usage_line_from_populated_turn_stats(self):
        # The provider/model/max-token metadata comes from the APIConfig.
        u = _token_stats(elapsed_time=12.34)
        text = self._render(
            u,
            _config(
                provider="deepseek",
                model="deepseek-flash",
                max_input_tokens=65536,
                max_output_tokens=8192,
            ),
        )
        # "Total" was replaced by the turn's elapsed time (issue #99): the
        # elapsed part renders via format_elapsed, the token parts via
        # format_tokens (Rule 6 -- labels structurally, numbers from the
        # source of truth).
        parts = _usage_parts(text)
        assert parts == {
            "Time": format_elapsed(12.34),
            "In": f"{format_tokens(60)}/{format_tokens(65536)}",
            "Out": format_tokens(40),
            "Cached": format_tokens(5),
            "Cost": parts["Cost"],
        }
        assert "Total" not in parts
        # The conversation turn number is no longer part of the summary
        # (it lives in the shell's pre-prompt rule instead).
        assert "Turn" not in parts

    def test_time_part_omitted_without_elapsed_time(self):
        # Without an elapsed time (no measurement) the summary line keeps
        # the historical shape minus the Total part.
        u = _token_stats()
        config = _config()
        parts = _usage_parts(self._render(u, config))
        assert "Time" not in parts
        assert "Total" not in parts
        assert parts["In"] == f"{format_tokens(60)}/{format_tokens(config.max_input_tokens)}"

    def test_cached_omitted_when_stats_report_no_cached_tokens(self):
        # The cached part is driven by the normalized stats: APIs that do not
        # report cached-token details (native Anthropic / DashScope / Gemini
        # SDKs) carry ``last_cached``/``turn_cached`` of ``None``.
        u = _token_stats(last_cached=None, turn_cached=None)
        text = self._render(u)
        assert "Cached" not in _usage_parts(text)

    def test_prints_used_files_before_usage_line(self, monkeypatch):
        from janito.config_store import set_config_value, unset_config_value

        _register(monkeypatch, "ReadFile", "r")
        used_files.reset_used_files()
        used_files.record_used_file("ReadFile", {"filepath": "/a.py"})
        set_config_value("used-files", True)
        try:
            u = _token_stats()
            text = self._render(u)
            assert text.index("Used files") < text.index("===")
            assert "1 read : /a.py" in text
        finally:
            used_files.reset_used_files()
            unset_config_value("used-files")

    def test_used_files_report_suppressed_when_disabled(self, monkeypatch):
        """The used-files report is hidden by default (issue #74)."""
        from janito.config_store import unset_config_value

        _register(monkeypatch, "ReadFile", "r")
        used_files.reset_used_files()
        used_files.record_used_file("ReadFile", {"filepath": "/a.py"})
        unset_config_value("used-files")
        try:
            u = _token_stats()
            text = self._render(u)
            assert "Used files" not in text
            assert "1 read : /a.py" not in text
            # The token-usage summary is still printed.
            assert "===" in text
        finally:
            used_files.reset_used_files()

    def test_used_files_report_printed_when_enabled(self, monkeypatch):
        """With ``used-files=True`` the report is printed (issue #74)."""
        from janito.config_store import set_config_value, unset_config_value

        _register(monkeypatch, "ReadFile", "r")
        used_files.reset_used_files()
        used_files.record_used_file("ReadFile", {"filepath": "/a.py"})
        set_config_value("used-files", True)
        try:
            u = _token_stats()
            text = self._render(u)
            assert "Used files" in text
            assert "1 read : /a.py" in text
        finally:
            used_files.reset_used_files()
            unset_config_value("used-files")

    def test_no_usage_prints_nothing(self):
        used_files.reset_used_files()
        assert self._render(None) == ""


class TestRunTurnDeliversTurnReport:
    """``Client.run_turn`` delivers the end-of-turn report to the injected
    observer's ``on_turn_complete`` when the turn finishes (the CLI wrapper
    that used to do it is gone, and the client owns the TurnInfo -- there
    is no caller-supplied out-param, issue #82)."""

    def _client(self, monkeypatch, observer):
        from conftest import make_config, make_ui_config

        from janito.llm_clients.openai.completions_api import CompletionsClient

        def fake_run(func, client, call_kwargs, tools_schemas):
            return (
                "final answer",
                None,
                {},
                SimpleNamespace(
                    prompt_tokens=60,
                    completion_tokens=40,
                    total_tokens=100,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=5),
                ),
                {"id": "chatcmpl-1"},
            )

        monkeypatch.setattr(
            "janito.llm_clients.client_support._load_mcp",
            lambda use_mcp: (None, []),
        )
        return CompletionsClient(
            make_config(model="gpt-4", use_mcp=False),
            make_ui_config(stream_runner=fake_run, observer=observer),
        )

    def test_run_turn_calls_on_turn_complete_with_populated_usage(self, monkeypatch):
        recorded = []

        class Obs:
            def on_reasoning(self, content):
                pass

            def on_message(self, content):
                pass

            def on_turn_complete(self, token_stats, api_config):
                recorded.append((token_stats, api_config))

        client = self._client(monkeypatch, Obs())
        result = client.run_turn("hi", tools=[])
        assert result == "final answer"
        # on_turn_complete was invoked exactly once, with the client-built
        # TurnInfo (usage folded from the stream round), the client's
        # resolved APIConfig (provider/model come from the config) and the
        # turn's elapsed wall-clock time (issue #99).
        assert len(recorded) == 1
        u, api_config = recorded[0]
        assert isinstance(u, TurnInfo)
        assert u.turn_input == 60
        assert u.turn_output == 40
        assert api_config.provider == "openai"
        assert api_config.model == "gpt-4"
        assert isinstance(u.elapsed_time, float)
        assert u.elapsed_time >= 0

    def test_run_turn_always_delivers_turn_report(self, monkeypatch):
        """The report is always delivered -- the client owns the TurnInfo
        and does not opt in through a caller-supplied out-param (issue #82)."""
        called = []

        class Obs:
            def on_reasoning(self, content):
                pass

            def on_message(self, content):
                pass

            def on_turn_complete(self, token_stats, api_config):
                called.append((token_stats, api_config))

        client = self._client(monkeypatch, Obs())
        client.run_turn("hi", tools=[])
        assert len(called) == 1
        u, api_config = called[0]
        assert isinstance(u, TurnInfo)
        assert api_config.model == "gpt-4"
        # The fake stream reported usage, so the report is populated.
        assert u.total is not None

    def test_rich_observer_on_turn_complete_renders_report(self):
        """The CLI's RichTurnObserver renders the report through
        display_turn_usage (byte-for-byte the historical output)."""
        from janito.ui.observer import RichTurnObserver

        buf = StringIO()
        observer = RichTurnObserver(console=Console(file=buf, width=120, force_terminal=False))
        u = _token_stats(elapsed_time=12.34)
        observer.on_turn_complete(
            u,
            _config(
                provider="deepseek",
                model="deepseek-flash",
                max_input_tokens=65536,
                max_output_tokens=8192,
            ),
        )
        text = buf.getvalue()
        parts = _usage_parts(text)
        assert parts["Time"] == format_elapsed(12.34)
        assert parts["In"] == f"{format_tokens(60)}/{format_tokens(65536)}"

    def test_rich_observer_on_turn_complete_records_accounting(self):
        """The observer's on_turn_complete also writes the overall-use
        accounting row (the end-of-turn bookkeeping lives in the observer,
        mirroring the web loop's own accounting)."""
        import janito.tooling.accounting as accounting
        from janito.ui.observer import RichTurnObserver

        buf = StringIO()
        observer = RichTurnObserver(console=Console(file=buf, width=120, force_terminal=False))
        u = _token_stats()
        observer.on_turn_complete(u, _config(provider="deepseek", model="deepseek-flash"))
        records = accounting.get_records()
        assert len(records) == 1
        row = records[0]
        # The turn-wide cumulative counters (tool-call rounds included).
        assert row["provider"] == "deepseek"
        assert row["model"] == "deepseek-flash"
        assert row["input_tokens"] == 180
        assert row["cached_tokens"] == 10
        assert row["output_tokens"] == 120

    def test_rich_observer_on_turn_complete_without_usage_records_nothing(self):
        """No usage reported -> no accounting row and no rendering."""
        import janito.tooling.accounting as accounting
        from janito.ui.observer import RichTurnObserver

        buf = StringIO()
        observer = RichTurnObserver(console=Console(file=buf, width=120, force_terminal=False))
        observer.on_turn_complete(None, _config())
        assert accounting.get_records() == []
        assert buf.getvalue() == ""
