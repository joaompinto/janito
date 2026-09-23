"""Tests for per-model disabled_tools (issue #144)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
from janito.config_cli import _coerce_list_value, set_config_from_cli
from janito.config_loaders import (
    load_disabled_tools_from_config,
    resolve_disabled_tools,
)
from janito.providers.models import ModelConfig


def _use_temp_config(monkeypatch, tmp_path):
    config_path = tmp_path / ".janito" / "config.json"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    return config_path


if pytest is not None:

    def test_model_config_disabled_tools():
        assert ModelConfig({"disabled_tools": ["WebSearch"]}).get("disabled_tools") == ["WebSearch"]
        assert ModelConfig({}).get("disabled_tools") is None

    def test_resolve_derived_default_native_search():
        assert resolve_disabled_tools("alibaba", "qwen3.8-flash") == ["WebSearch"]
        assert resolve_disabled_tools("meta", "muse-spark-1.3") == ["WebSearch"]

    def test_resolve_no_native_search_empty():
        assert resolve_disabled_tools("openai", "gpt-6-luna") == []

    def test_override_wins_over_derived(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        set_config_from_cli("provider=alibaba")
        set_config_from_cli(
            "model=qwen3.8-flash",
            "alibaba",
        )
        set_config_from_cli("disabled-tools=", "alibaba")
        assert load_disabled_tools_from_config("alibaba", "qwen3.8-flash") == []
        assert resolve_disabled_tools("alibaba", "qwen3.8-flash") == []

    def test_coerce_list_value():
        assert _coerce_list_value("disabled-tools", "WebSearch, Foo") == [
            "WebSearch",
            "Foo",
        ]
        assert _coerce_list_value("disabled-tools", '["WebSearch"]') == ["WebSearch"]
        assert _coerce_list_value("disabled-tools", "") == []

    def test_session_schemas_hide_disabled(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        from janito.tooling import tools_registry as registry_mod

        monkeypatch.setattr(registry_mod, "AVAILABLE_TOOLS", {})
        monkeypatch.setattr(registry_mod, "_tools_initialized", True)

        def _fake_tool(name):
            def _fn():
                return {"success": True}

            _fn._tool_permissions = ""
            _fn.__name__ = name
            return _fn

        registry_mod.AVAILABLE_TOOLS["WebSearch"] = _fake_tool("WebSearch")
        registry_mod.AVAILABLE_TOOLS["Other"] = _fake_tool("Other")
        monkeypatch.setattr(
            registry_mod.ToolsRegistry,
            "_disabled_tool_names",
            lambda self: {"WebSearch"},
        )
        assert registry_mod._registry.session_tool_names() == {"Other"}
        schemas = registry_mod._registry.session_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert names == {"Other"}
        # Full registry still holds the disabled tool.
        assert set(registry_mod._registry.all_tools()) == {"WebSearch", "Other"}
