"""Tests for the ``responses_include`` provider/model config option and its
wiring into the Responses API call kwargs.

``responses_include`` declares extra ``include`` values to request on every
Responses API call (e.g. ``["reasoning.encrypted_content"]`` for Meta's Muse
Spark, whose chain of thought is only exposed in encrypted form so it can be
replayed across turns).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from janito.llm_clients.openai.responses_state import _build_call_kwargs
from janito.providers.models import Provider
from janito.providers.registry import get_provider

# ---- ModelConfig / Provider accessors ------------------------------------


def test_meta_models_declare_stateless_and_include():
    found = get_provider("meta")
    assert found is not None
    for model in ("muse-spark-1.3", "muse-spark-1.3-contributor"):
        assert bool(found.model_config(model).get("stateless_mode", False)) is True
        assert found.model_config(model).get("responses_include") == ["reasoning.encrypted_content"]


def test_models_without_declaration_default_to_no_include():
    found = get_provider("openai")
    assert found is not None
    # OpenAI models declare no include values (the API default applies).
    assert found.model_config("gpt-6-luna").get("responses_include") is None
    assert bool(found.model_config("gpt-6-luna").get("stateless_mode", False)) is False


def test_responses_include_malformed_value_returns_none():
    import janito.llm_clients.openai.responses_state as state_mod
    from janito.llm_clients.openai.responses_state import _responses_include

    provider = Provider(
        "test-include",
        data={
            "test-include": {
                "default_model": "m",
                "models": {"m": {"responses_include": "not-a-list"}},
            }
        },
    )
    # Raw get() passes the value through; the call-site normalizer drops it.
    assert provider.model_config("m").get("responses_include") == "not-a-list"
    original = state_mod.get_provider
    state_mod.get_provider = lambda p: provider
    try:
        assert _responses_include("test-include", "m") is None
    finally:
        state_mod.get_provider = original


def test_responses_include_normalizes_entries_to_strings():
    import janito.llm_clients.openai.responses_state as state_mod
    from janito.llm_clients.openai.responses_state import _responses_include

    provider = Provider(
        "test-include",
        data={
            "test-include": {
                "default_model": "m",
                "models": {"m": {"responses_include": ["a", 42]}},
            }
        },
    )
    assert provider.model_config("m").get("responses_include") == ["a", 42]
    original = state_mod.get_provider
    state_mod.get_provider = lambda p: provider
    try:
        assert _responses_include("test-include", "m") == ["a", "42"]
    finally:
        state_mod.get_provider = original


# ---- Call kwargs wiring ---------------------------------------------------


def _kwargs(stateless_mode, include=None):
    from janito.providers.models import ModelConfig

    class _Found:
        def model_config(self, model=None):
            return ModelConfig({"responses_include": include})

    import janito.llm_clients.openai.responses_state as state_mod

    original = state_mod.get_provider
    state_mod.get_provider = lambda p: _Found() if p == "meta" else None
    try:
        return _build_call_kwargs(
            "muse-spark-1.3",
            [{"type": "message", "role": "user", "content": []}],
            None,
            None,
            None,
            False,
            None,
            stateless_mode,
            None,
            provider="meta" if include is not None else "openai",
        )
    finally:
        state_mod.get_provider = original


def test_stateless_kwargs_send_store_false_and_include():
    kwargs = _kwargs(True, include=["reasoning.encrypted_content"])
    assert kwargs["store"] is False
    assert kwargs["include"] == ["reasoning.encrypted_content"]


def test_server_side_kwargs_send_neither_store_nor_include():
    kwargs = _kwargs(False, include=["reasoning.encrypted_content"])
    assert "store" not in kwargs
    assert "include" not in kwargs


def test_stateless_kwargs_without_declared_include_omit_it():
    kwargs = _kwargs(True, include=None)
    assert kwargs["store"] is False
    assert "include" not in kwargs


def test_stateless_kwargs_send_instructions_in_history_not_param():
    """Stateless providers fold instructions into the items history, so no
    separate ``instructions`` parameter is sent."""
    kwargs = _kwargs(True, include=None)
    assert "instructions" not in kwargs
    assert "previous_response_id" not in kwargs


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__]))
