"""Tests for the ``thinking_summary`` provider/model config option (issue #134).

When ``True`` (Meta's Muse Spark), Responses calls request
``reasoning.summary="auto"`` so the private chain of thought is returned
as summary text streamed via ``response.reasoning_summary_text`` deltas
and surfaced through the existing ``on_reasoning`` observer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from janito.providers.registry import get_provider


def test_meta_models_request_thinking_summary():
    found = get_provider("meta")
    assert found is not None
    for model in ("muse-spark-1.3", "muse-spark-1.3-contributor"):
        assert bool(found.model_config(model).get("thinking_summary", False)) is True


def test_models_without_declaration_default_to_false():
    found = get_provider("openai")
    assert found is not None
    assert bool(found.model_config("gpt-6-luna").get("thinking_summary", False)) is False


def _cli_kwargs(provider, model, effort):
    import janito.llm_clients.openai.responses_state as state_mod

    return state_mod._build_call_kwargs(
        model,
        [{"type": "message", "role": "user", "content": []}],
        None,
        effort,
        None,
        False,
        None,
        True,
        None,
        provider=provider,
    )


def test_cli_kwargs_merge_effort_and_summary_for_meta():
    kwargs = _cli_kwargs("meta", "muse-spark-1.3", "minimal")
    assert kwargs["reasoning"] == {"effort": "minimal", "summary": "auto"}


def test_cli_kwargs_summary_without_effort_for_meta():
    kwargs = _cli_kwargs("meta", "muse-spark-1.3", None)
    assert kwargs["reasoning"] == {"summary": "auto"}


def test_cli_kwargs_omit_reasoning_for_plain_models():
    kwargs = _cli_kwargs("openai", "gpt-6-luna", None)
    assert "reasoning" not in kwargs


def test_web_adapter_kwargs_merge_effort_and_summary_for_meta():
    from janito.llm_adapters.responses import build_call_kwargs

    class _Config:
        effective_provider = "meta"
        effective_thinking = False

        def effective_tools_for(self, api_type):
            return []

    kwargs = build_call_kwargs("muse-spark-1.3", [], None, _Config(), None, None, "minimal")
    assert kwargs["reasoning"] == {"effort": "minimal", "summary": "auto"}


def test_summary_deltas_surface_via_reasoning_buffer():
    from types import SimpleNamespace

    from janito.llm_clients.openai.responses_stream import ResponsesStreamConsumer

    c = ResponsesStreamConsumer()
    c.handle_event(SimpleNamespace(type="response.reasoning_summary_text.delta", delta="thought "))
    c.handle_event(SimpleNamespace(type="response.reasoning_summary_text.delta", delta="summary"))
    assert c.reasoning_content == "thought summary"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__]))
