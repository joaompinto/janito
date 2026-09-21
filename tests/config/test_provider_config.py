"""
Tests for provider name validation.

Whenever ``--provider <name>`` is used, the CLI must verify that the provider
is supported (i.e. it maps to an entry in the provider -> base URL mapping).
These tests cover the helper functions and the end-to-end CLI behaviour.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
from janito.providers import REQUIRES_BY_API_TYPE
from janito.providers.payloads import (
    apply_builtin_tools_to_extra_body,
    apply_thinking_to_extra_body,
    builtin_tools_enable_flags,
)
from janito.providers.registry import get_provider
from janito.providers.validation import (
    canonical_provider_name,
    ensure_api_type_available,
    get_all_api_types,
    get_required_package_for_api_type,
    is_api_type_available,
    is_supported_provider,
    list_supported_providers,
    validate_provider_name,
)

# ---------------------------------------------------------------------------
# Test-local mapping of the former ``provider_accessors`` helpers onto the
# the Provider accessors (``get_provider(name)`` -> ``Provider``).  These
# keep the table-driven assertions below readable; the package itself only
# exposes the typed API.
# ---------------------------------------------------------------------------


def get_provider_config(provider, model=None):
    """The provider info dict (or one model's entry); ``None`` when unknown."""
    found = get_provider(provider)
    if found is None:
        return None
    info = found.info
    if model is None:
        return info
    models = info.get("models", {})
    if not isinstance(models, dict):
        return None
    return models.get(model)


def get_base_url_from_provider(provider):
    """The provider's built-in ``endpoint`` entry, or ``None``."""
    found = get_provider(provider)
    return found.info.get("endpoint") if found is not None else None


def get_endpoint_by_api_type(provider):
    """The provider's ``endpoint_by_api_type`` map, or ``None``."""
    found = get_provider(provider)
    return found.info.get("endpoint_by_api_type") if found is not None else None


def get_endpoint_for_api_type(provider, api_type=None):
    """The provider's base URL for ``api_type``, or ``None``."""
    found = get_provider(provider)
    return found.endpoint_for(api_type) if found is not None else None


def get_default_model_from_provider(provider):
    """The provider's built-in default model, or ``None``."""
    found = get_provider(provider)
    return found.default_model() if found is not None else None


def get_default_max_output_tokens_from_provider(provider, model=None):
    """The model's built-in max output tokens, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("max_output_tokens") if found is not None else None


def get_default_max_input_tokens_from_provider(provider, model=None):
    """The model's built-in max input tokens, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("max_input_tokens") if found is not None else None


def get_default_reasoning_effort_from_provider(provider, model=None):
    """The model's built-in default reasoning effort, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("default_reasoning_effort") if found is not None else None


def get_supported_reasoning_efforts_from_provider(provider, model=None):
    """The model's supported reasoning efforts, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("supported_reasoning_efforts") if found is not None else None


def get_default_thinking_from_provider(provider, model=None):
    """The model's built-in thinking default (``True`` / dict / ``False``)."""
    found = get_provider(provider)
    return found.model_config(model).get("thinking", False) if found is not None else False


def get_preserve_thinking_from_provider(provider, model=None):
    """The model's built-in preserve_thinking default, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("preserve_thinking") if found is not None else None


def get_default_tools_from_provider(provider, model=None, api_type=None):
    """The model's built-in (native) tools for ``api_type``, or ``None``."""
    found = get_provider(provider)
    return found.tools(model, api_type=api_type) if found is not None else None


def get_gemini_flavor_from_provider(provider):
    """Whether the provider's API uses the Gemini (Google) flavor."""
    found = get_provider(provider)
    return found.gemini_flavor() if found is not None else False


def get_supported_api_types_from_provider(provider, model=None):
    """The API types the model supports, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("supported_api_types") if found is not None else None


def get_default_api_type_from_provider(provider, model=None):
    """The model's built-in default API type, or ``None``."""
    found = get_provider(provider)
    return found.model_config(model).get("default_api_type") if found is not None else None


def get_stateless_mode_from_provider(provider, model=None):
    """Whether the model's Responses API keeps server-side state."""
    from janito.llm_clients.openai.responses_state import stateless_mode

    return stateless_mode(provider, model)


if pytest is not None:

    def test_supported_providers_map_to_info():
        # Every supported provider has a full info entry.
        providers = list_supported_providers()
        assert "openai" in providers
        assert "custom" in providers
        for name in providers:
            info = get_provider_config(name)
            assert info is not None
            # Every entry carries the provider-level keys (default_model,
            # endpoint) and the model-level keys live under ``models``.
            assert "default_model" in info
            assert "endpoint" in info
            models = info.get("models", {})
            # The default model (when one exists) has a full built-in entry.
            if info["default_model"] is not None:
                assert info["default_model"] in models
                model_entry = models[info["default_model"]]
                assert "supported_api_types" in model_entry
                assert model_entry["supported_api_types"]

    def test_get_provider_config_and_base_url():
        info = get_provider_config("minimax")
        assert info is not None
        assert info["endpoint"] == "https://api.minimax.io/v1"
        # get_base_url_from_provider returns just the endpoint.
        assert get_base_url_from_provider("minimax") == "https://api.minimax.io/v1"
        # Standard OpenAI has no custom endpoint (None).
        assert get_base_url_from_provider("openai") is None
        # Case-insensitive lookups work.
        assert get_provider_config("MiniMax")["endpoint"] == "https://api.minimax.io/v1"
        # Unknown provider returns None everywhere.
        assert get_provider_config("bogus") is None
        assert get_base_url_from_provider("bogus") is None

    def test_get_provider_config_with_model():
        """``get_provider_config(provider, model)`` returns the config for that
        model *within* the provider instead of the whole provider entry."""
        # model=None returns the full provider entry.
        info = get_provider_config("openai")
        assert info["default_model"] == "gpt-5.6-luna"
        assert get_provider_config("openai") == info
        # model given returns that model's entry inside the provider.
        model_info = get_provider_config("openai", "gpt-5.6-luna")
        assert model_info == info["models"]["gpt-5.6-luna"]
        assert model_info["max_output_tokens"] == 128000
        # Case-insensitive provider lookup works with a model too.
        assert get_provider_config("MiniMax", "MiniMax-M3")["thinking"] == {"type": "adaptive"}
        assert get_provider_config("DeepSeek", "deepseek-flash")["stateless_mode"] is True
        # Unknown model -> None (no fallback to the default model's entry).
        assert get_provider_config("openai", "no-such-model") is None
        # Unknown provider -> None.
        assert get_provider_config("bogus") is None
        assert get_provider_config("bogus", "gpt-5.6-luna") is None
        # The "custom" provider has no built-in models.
        assert get_provider_config("custom", "any-model") is None

    def test_provider_info_is_package_config_dict():
        """The typed Provider's ``info`` is the same dict the package registry reads."""
        from janito.providers import _PROVIDER_CONFIGS as PACKAGE_PROVIDER_CONFIGS

        # The provider object's info entry is the package's config dict.
        assert get_provider("openai").info is PACKAGE_PROVIDER_CONFIGS["openai"]
        # Provider-level fields and per-model entries come from that dict.
        assert get_provider("minimax").info["endpoint"] == "https://api.minimax.io/v1"
        assert get_provider("openai").model_config("gpt-5.6-luna").get("max_output_tokens") == 128000
        assert get_provider("minimax").model_config("MiniMax-M3").get("thinking", False) == {"type": "adaptive"}
        # Case-insensitive provider lookup works.
        assert get_provider("MiniMax").default_model() == "MiniMax-M3"
        # Unknown provider -> None.
        assert get_provider("bogus") is None
        # The "custom" provider has no built-in models (empty config -> None).
        assert get_provider("custom").model_config("any-model").get("max_output_tokens") is None

    def test_deepseek_provider():
        info = get_provider_config("deepseek")
        assert info is not None
        assert info["default_model"] == "deepseek-flash"
        model_entry = info["models"]["deepseek-flash"]
        assert model_entry["max_input_tokens"] == 1048576  # 1M (2**20)
        assert model_entry["max_output_tokens"] == 393216
        assert info["endpoint"] == "https://api.deepseek.com"
        # OpenAI-compatible base URL for the OpenAI-SDK API types and the
        # Anthropic-compatible base URL for the native Anthropic SDK API type.
        assert model_entry["supported_api_types"] == [
            "Responses",
            "Completions",
            "Anthropic",
        ]
        assert info["endpoint_by_api_type"] == {
            "Completions": "https://api.deepseek.com",
            "Responses": "https://api.deepseek.com",
            "Anthropic": "https://api.deepseek.com/anthropic",
        }
        # Case-insensitive lookup.
        assert get_provider_config("DeepSeek")["endpoint"] == "https://api.deepseek.com"
        assert get_base_url_from_provider("deepseek") == "https://api.deepseek.com"
        assert get_default_model_from_provider("deepseek") == "deepseek-flash"
        assert get_default_max_input_tokens_from_provider("deepseek") == 1048576
        assert get_default_max_output_tokens_from_provider("deepseek") == 393216

    def test_anthropic_provider():
        info = get_provider_config("anthropic")
        assert info is not None
        assert info["default_model"] == "claude-sonnet-5"
        model_entry = info["models"]["claude-sonnet-5"]
        assert model_entry["max_input_tokens"] == 200000
        assert model_entry["max_output_tokens"] == 64000
        assert info["endpoint"] == "https://api.anthropic.com/v1/"
        # Completions (OpenAI-compatible) is the built-in default; the native
        # Anthropic SDK API type is the second supported type.
        assert model_entry["supported_api_types"] == ["Completions", "Anthropic"]
        # Per-API-type endpoints: the OpenAI-compatible Chat Completions URL
        # and the native Anthropic SDK base URL.
        assert info["endpoint_by_api_type"] == {
            "Completions": "https://api.anthropic.com/v1/",
            "Anthropic": "https://api.anthropic.com",
        }
        # Case-insensitive lookup.
        assert get_provider_config("Anthropic")["endpoint"] == "https://api.anthropic.com/v1/"
        assert get_base_url_from_provider("anthropic") == "https://api.anthropic.com/v1/"
        assert get_default_model_from_provider("anthropic") == "claude-sonnet-5"
        assert get_default_max_input_tokens_from_provider("anthropic") == 200000
        assert get_default_max_output_tokens_from_provider("anthropic") == 64000
        assert get_default_api_type_from_provider("anthropic") == "Completions"
        # claude-opus-5 and claude-fable-5-1 also ship built-in entries: both
        # support the Completions and native Anthropic SDK API types (default
        # Completions) and expose the 1M-token context window at standard
        # pricing.
        for name, max_input, max_output in (
            ("claude-opus-5", 1000000, 128000),
            ("claude-fable-5-1", 1000000, 128000),
        ):
            entry = info["models"][name]
            assert entry["supported_api_types"] == ["Completions", "Anthropic"]
            assert entry["default_api_type"] == "Completions"
            assert entry["max_input_tokens"] == max_input
            assert entry["max_output_tokens"] == max_output
            assert get_provider_config("anthropic", name)["max_input_tokens"] == max_input
            assert get_default_max_input_tokens_from_provider("anthropic", name) == max_input
            assert get_default_max_output_tokens_from_provider("anthropic", name) == max_output

    def test_meta_provider():
        info = get_provider_config("meta")
        assert info is not None
        assert info["default_model"] == "muse-spark-1.3"
        model_entry = info["models"]["muse-spark-1.3"]
        # 1M context window per the official model page.
        assert model_entry["max_input_tokens"] == 1048576  # 1M (2**20)
        # No built-in output limit: Meta does not publish one, so the
        # caller's own default applies.
        assert model_entry.get("max_output_tokens") is None
        assert info["endpoint"] == "https://api.meta.ai/v1"
        # Responses is the built-in default API type; the Chat Completions
        # API remains fully supported.  No per-API-type endpoint map: the
        # same base URL serves both OpenAI-compatible APIs.
        assert model_entry["supported_api_types"] == ["Responses", "Completions"]
        assert model_entry["default_api_type"] == "Responses"
        # Meta's /responses endpoint is stateless for cross-turn continuity
        # (the docs recommend store:false + encrypted reasoning replay, which
        # cannot be combined with previous_response_id), and the chain of
        # thought is only exposed in encrypted form.
        assert model_entry["stateless_mode"] is True
        assert model_entry["responses_include"] == ["reasoning.encrypted_content"]
        assert get_endpoint_by_api_type("meta") is None
        # No built-in thinking/preserve_thinking flags; the built-in default
        # reasoning effort is the standard level (medium).
        assert "thinking" not in model_entry
        assert "preserve_thinking" not in model_entry
        assert get_default_reasoning_effort_from_provider("meta") == "medium"
        # The contributor tier ships the same model capabilities under a
        # separate model ID; only the pricing differs.
        contributor_entry = info["models"]["muse-spark-1.3-contributor"]
        assert contributor_entry["supported_api_types"] == ["Responses", "Completions"]
        assert contributor_entry["default_api_type"] == "Responses"
        assert contributor_entry["stateless_mode"] is True
        assert contributor_entry["responses_include"] == ["reasoning.encrypted_content"]
        assert contributor_entry["max_input_tokens"] == 1048576
        # Case-insensitive lookups.
        assert get_provider_config("Meta")["endpoint"] == "https://api.meta.ai/v1"
        assert get_base_url_from_provider("meta") == "https://api.meta.ai/v1"
        assert get_default_model_from_provider("meta") == "muse-spark-1.3"
        assert get_default_max_input_tokens_from_provider("meta") == 1048576
        assert get_default_max_input_tokens_from_provider("meta", "muse-spark-1.3-contributor") == 1048576

    def test_google_provider():
        info = get_provider_config("google")
        assert info is not None
        assert info["default_model"] == "gemini-3.7-flash"
        model_entry = info["models"]["gemini-3.7-flash"]
        assert model_entry["max_input_tokens"] == 1048576  # 1M (2**20)
        assert model_entry["max_output_tokens"] == 65536
        assert info["endpoint"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
        # The provider is Gemini-flavored: Google's OpenAI-compatibility layer
        # does not accept the enable_thinking flag, so thinking is handled
        # through reasoning_effort instead.
        assert info["gemini_flavor"] is True
        assert get_gemini_flavor_from_provider("google") is True
        assert get_gemini_flavor_from_provider("Google") is True
        # Non-Gemini providers (and unknown names) are not flavored.
        assert get_gemini_flavor_from_provider("openai") is False
        assert get_gemini_flavor_from_provider("alibaba") is False
        assert get_gemini_flavor_from_provider("bogus") is False
        # Google's OpenAI-compatibility layer documents the Chat Completions
        # API only, so Completions is the built-in default; the native Gemini
        # API type (the optional google-genai package) is also supported.
        assert model_entry["supported_api_types"] == ["Completions", "Gemini"]
        assert model_entry["default_api_type"] == "Completions"
        # Per-API-type endpoints: the OpenAI-compatible Chat Completions URL
        # and the native Gemini SDK base URL.
        assert info["endpoint_by_api_type"] == {
            "Completions": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "Gemini": "https://generativelanguage.googleapis.com",
        }
        assert (
            get_endpoint_for_api_type("google", "Completions")
            == "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        assert get_endpoint_for_api_type("google", "Gemini") == "https://generativelanguage.googleapis.com"
        # Case-insensitive lookup.
        assert get_provider_config("Google")["endpoint"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert get_base_url_from_provider("google") == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert get_default_model_from_provider("google") == "gemini-3.7-flash"
        assert get_default_max_input_tokens_from_provider("google") == 1048576
        assert get_default_max_output_tokens_from_provider("google") == 65536
        # Gemini 3.x models reason by default; reasoning_effort maps to the
        # model's thinking_level (low/medium/high, default medium).
        assert get_default_reasoning_effort_from_provider("google") == "medium"
        # The built-in default lives under the single
        # "default_reasoning_effort" key (the old "reasoning_level" alias is
        # not supported).
        assert model_entry["default_reasoning_effort"] == "medium"
        assert "reasoning_level" not in model_entry
        supported = get_supported_reasoning_efforts_from_provider("google")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == [
            "low",
            "medium",
            "high",
        ]

    def test_default_model_and_max_tokens():
        # Providers expose built-in default models / max tokens.
        assert get_default_model_from_provider("openai") == "gpt-5.6-luna"
        assert get_default_model_from_provider("alibaba") == "qwen3.8-flash"
        assert get_default_max_input_tokens_from_provider("openai") == 1050000
        assert get_default_max_output_tokens_from_provider("openai") == 128000
        # Alibaba's built-in models declare their token limits (qwen3.8-max
        # 1M input / 131K output; qwen3.8-flash 991K input / 131K output).
        assert get_default_max_input_tokens_from_provider("alibaba", "qwen3.8-flash") == 991000
        assert get_default_max_output_tokens_from_provider("alibaba", "qwen3.8-flash") == 131072
        # Z.ai's default is the GLM-5.3-Flash model (1M input / 128K output).
        assert get_default_model_from_provider("zai") == "glm-5.3-flash"
        assert get_default_max_input_tokens_from_provider("zai") == 1000000
        assert get_default_max_output_tokens_from_provider("zai") == 128000
        # The "custom" provider has no built-in defaults.
        assert get_default_model_from_provider("custom") is None
        assert get_default_max_input_tokens_from_provider("custom") is None
        assert get_default_max_output_tokens_from_provider("custom") is None
        # Unknown provider returns None.
        assert get_default_model_from_provider("bogus") is None
        assert get_default_max_input_tokens_from_provider("bogus") is None
        assert get_default_max_output_tokens_from_provider("bogus") is None

    def test_default_and_supported_reasoning_efforts():
        # Both Alibaba Qwen models (the default qwen3.8-flash and the
        # flagship qwen3.8-max) declare configurable reasoning levels
        # (low/medium/xhigh per the QwenCloud API reference); the built-in
        # default is the standard level (medium) for both.
        assert get_default_reasoning_effort_from_provider("alibaba") == "medium"
        assert get_supported_reasoning_efforts_from_provider("alibaba") is not None
        assert [entry["effort"] for entry in get_supported_reasoning_efforts_from_provider("alibaba")] == [
            "low",
            "medium",
            "xhigh",
        ]
        assert get_default_reasoning_effort_from_provider("alibaba", "qwen3.8-max") == "medium"
        # The built-in default lives under the single
        # "default_reasoning_effort" key (the old "reasoning_level" alias is
        # not supported).
        qwen_entry = get_provider_config("alibaba")["models"]["qwen3.8-max"]
        assert qwen_entry["default_reasoning_effort"] == "medium"
        assert "reasoning_level" not in qwen_entry
        supported = get_supported_reasoning_efforts_from_provider("alibaba", "qwen3.8-max")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == ["low", "medium", "xhigh"]
        for entry in supported:
            assert "effort" in entry
            assert "description" in entry
        # qwen3.8-flash (the default model) declares the same levels.
        supported = get_supported_reasoning_efforts_from_provider("alibaba", "qwen3.8-flash")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == ["low", "medium", "xhigh"]
        for entry in supported:
            assert "effort" in entry
            assert "description" in entry
        # DeepSeek's default model (deepseek-flash) declares reasoning
        # levels too (low/high/max per the DeepSeek API reference).
        supported = get_supported_reasoning_efforts_from_provider("deepseek")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == ["low", "high", "max"]
        for entry in supported:
            assert "effort" in entry
            assert "description" in entry
        # Moonshot's default model (kimi-k3) declares reasoning levels
        # too (low/high/max per the Moonshot API reference, default max).
        assert get_default_reasoning_effort_from_provider("moonshot") == "max"
        kimi_entry = get_provider_config("moonshot")["models"]["kimi-k3"]
        assert kimi_entry["default_reasoning_effort"] == "max"
        assert "reasoning_level" not in kimi_entry
        supported = get_supported_reasoning_efforts_from_provider("moonshot")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == ["low", "high", "max"]
        for entry in supported:
            assert "effort" in entry
            assert "description" in entry
        # Case-insensitive lookup works.
        assert get_default_reasoning_effort_from_provider("Alibaba", "qwen3.8-max") == "medium"
        assert get_supported_reasoning_efforts_from_provider("DeepSeek") is not None
        assert get_supported_reasoning_efforts_from_provider("Moonshot") is not None
        # The OpenAI GPT models declare reasoning levels too
        # (low/medium/high), with medium as the built-in default.
        assert get_default_reasoning_effort_from_provider("openai") == "medium"
        assert get_supported_reasoning_efforts_from_provider("openai") is not None
        assert [entry["effort"] for entry in get_supported_reasoning_efforts_from_provider("openai")] == [
            "low",
            "medium",
            "high",
        ]
        for entry in get_supported_reasoning_efforts_from_provider("openai"):
            assert "effort" in entry
            assert "description" in entry
        # Meta's Muse Spark models declare reasoning levels too
        # (minimal/low/medium/high per the Meta Model API reasoning
        # cookbook), with medium as the built-in default.
        assert get_default_reasoning_effort_from_provider("meta") == "medium"
        assert get_supported_reasoning_efforts_from_provider("meta") is not None
        assert [entry["effort"] for entry in get_supported_reasoning_efforts_from_provider("meta")] == [
            "minimal",
            "low",
            "medium",
            "high",
        ]
        for entry in get_supported_reasoning_efforts_from_provider("meta"):
            assert "effort" in entry
            assert "description" in entry
        # The contributor-tier model declares the same levels.
        supported = get_supported_reasoning_efforts_from_provider("meta", "muse-spark-1.3-contributor")
        assert supported is not None
        assert [entry["effort"] for entry in supported] == [
            "minimal",
            "low",
            "medium",
            "high",
        ]
        # Providers without configurable reasoning expose None.
        assert get_default_reasoning_effort_from_provider("custom") is None
        # Unknown provider returns None.
        assert get_default_reasoning_effort_from_provider("bogus") is None
        assert get_supported_reasoning_efforts_from_provider("bogus") is None

    def test_default_thinking():
        # DeepSeek and Alibaba/Qwen reason by default (flag-style); MiniMax-M3
        # reasons by default with a structured thinking dict (adaptive).
        assert get_default_thinking_from_provider("deepseek") is True
        assert get_default_thinking_from_provider("alibaba") is True
        assert get_default_thinking_from_provider("minimax") == {"type": "adaptive"}
        assert get_default_thinking_from_provider("DeepSeek") is True
        assert get_default_thinking_from_provider("Alibaba") is True
        assert get_default_thinking_from_provider("MiniMax") == {"type": "adaptive"}
        # The model info entries carry the flag.
        assert get_provider_config("deepseek")["models"]["deepseek-flash"]["thinking"] is True
        assert get_provider_config("alibaba")["models"]["qwen3.8-max"]["thinking"] is True
        assert get_provider_config("alibaba")["models"]["qwen3.8-flash"]["thinking"] is True
        assert get_provider_config("minimax")["models"]["MiniMax-M3"]["thinking"] == {"type": "adaptive"}
        # Everyone else defaults to False (explicit or absent).
        for name in (
            "openai",
            "google",
            "meta",
            "xiaomi",
            "moonshot",
            "zai",
            "xai",
            "anthropic",
            "custom",
        ):
            assert get_default_thinking_from_provider(name) is False
        # Unknown provider returns False.
        assert get_default_thinking_from_provider("bogus") is False

    def test_preserve_thinking_default():
        # Alibaba's built-in Qwen models (hybrid-thinking) declare
        # preserve_thinking True: their API appends the assistant messages'
        # reasoning_content to the next input, so multi-turn reasoning stays
        # in context.  The no-model lookup resolves to the default model
        # (qwen3.8-flash), which declares it too.
        assert get_preserve_thinking_from_provider("alibaba") is True
        assert get_preserve_thinking_from_provider("alibaba", "qwen3.8-max") is True
        assert get_preserve_thinking_from_provider("alibaba", "qwen3.8-flash") is True
        assert get_provider_config("alibaba")["models"]["qwen3.8-max"]["preserve_thinking"] is True
        assert get_provider_config("alibaba")["models"]["qwen3.8-flash"]["preserve_thinking"] is True
        # Every other provider declares nothing (None) -> no flag is sent and
        # the API's own default applies.
        for name in (
            "openai",
            "deepseek",
            "minimax",
            "google",
            "meta",
            "xiaomi",
            "moonshot",
            "zai",
            "xai",
            "anthropic",
            "custom",
        ):
            assert get_preserve_thinking_from_provider(name) is None
        # Unknown provider returns None.
        assert get_preserve_thinking_from_provider("bogus") is None

    def test_apply_thinking_to_extra_body():
        # A plain True flag -> extra_body enable_thinking.
        kwargs = {}
        apply_thinking_to_extra_body(kwargs, True)
        assert kwargs["extra_body"]["enable_thinking"] is True

        # A structured dict is passed through verbatim as extra_body thinking
        # (e.g. MiniMax-M3's {"type": "adaptive"}).
        kwargs = {}
        apply_thinking_to_extra_body(kwargs, {"type": "adaptive"})
        assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}
        # The dict is copied, not held by reference.
        thinking = {"type": "adaptive"}
        apply_thinking_to_extra_body(kwargs, thinking)
        thinking["type"] = "disabled"
        assert kwargs["extra_body"]["thinking"] == {"type": "adaptive"}

        # Falsy values send nothing (extra_body is not even created).
        for falsy in (False, None):
            kwargs = {}
            apply_thinking_to_extra_body(kwargs, falsy)
            assert kwargs == {}

        # extra_body already holding a key is preserved.
        kwargs = {"extra_body": {"preserve_thinking": True}}
        apply_thinking_to_extra_body(kwargs, True)
        assert kwargs["extra_body"] == {
            "preserve_thinking": True,
            "enable_thinking": True,
        }

    def test_default_tools_from_provider():
        """Alibaba's qwen3.8-max enables its built-in tools per API type.

        The tools (code_interpreter / web_search / web_extractor) are
        declared under ``tools_by_api_type`` and enabled on the Responses
        API only: the qwen3.8-max deployment rejects them on the Completions
        API with ``400 ... The current model does not support the
        code_interpreter tool.`` (and DashScope is left off for the same
        reason).  The plain ``tools`` default is absent, so API types not in
        the map resolve to None.
        """
        assert get_default_tools_from_provider("alibaba", "qwen3.8-max") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-max", api_type="Completions") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-max", api_type="DashScope") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-max", api_type="Responses") == [
            {"type": "code_interpreter"},
            {"type": "web_search"},
            {"type": "web_extractor"},
        ]
        # The provider config entry carries the per-API-type map.
        model_entry = get_provider_config("alibaba")["models"]["qwen3.8-max"]
        assert "tools" not in model_entry
        assert model_entry["tools_by_api_type"] == {
            "Responses": [
                {"type": "code_interpreter"},
                {"type": "web_search"},
                {"type": "web_extractor"},
            ]
        }
        # Case-insensitive provider lookup works.
        assert get_default_tools_from_provider("Alibaba", "qwen3.8-max", api_type="Responses") == [
            {"type": "code_interpreter"},
            {"type": "web_search"},
            {"type": "web_extractor"},
        ]

    def test_default_tools_from_provider_qwen_flash():
        """Alibaba's qwen3.8-flash declares its built-in tools per API type.

        The official QwenCloud page advertises code_interpreter /
        i2i_search / t2i_search / web_extractor / web_search for the
        Responses API; like qwen3.8-max they are left off the Completions
        and native DashScope APIs until confirmed.  qwen3.8-flash is the
        provider's default model, so the no-model lookup resolves to it.
        """
        assert get_default_tools_from_provider("alibaba") is None
        assert get_default_tools_from_provider("alibaba", api_type="Completions") is None
        assert get_default_tools_from_provider("alibaba", api_type="DashScope") is None
        assert get_default_tools_from_provider("alibaba", api_type="Responses") == [
            {"type": "code_interpreter"},
            {"type": "i2i_search"},
            {"type": "t2i_search"},
            {"type": "web_extractor"},
            {"type": "web_search"},
        ]
        assert get_default_tools_from_provider("alibaba", "qwen3.8-flash") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-flash", api_type="Completions") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-flash", api_type="DashScope") is None
        assert get_default_tools_from_provider("alibaba", "qwen3.8-flash", api_type="Responses") == [
            {"type": "code_interpreter"},
            {"type": "i2i_search"},
            {"type": "t2i_search"},
            {"type": "web_extractor"},
            {"type": "web_search"},
        ]
        # Providers without built-in tools expose None.
        for name in ("openai", "deepseek", "minimax", "anthropic", "custom"):
            assert get_default_tools_from_provider(name) is None
            assert get_default_tools_from_provider(name, api_type="Responses") is None
        # Unknown provider returns None.
        assert get_default_tools_from_provider("bogus") is None
        assert get_default_tools_from_provider("bogus", api_type="Responses") is None

    def test_builtin_tools_enable_flags():
        """Each built-in tool type maps to its request-body enable_* flag."""
        tools = [
            {"type": "code_interpreter"},
            {"type": "web_search"},
            {"type": "web_extractor"},
        ]
        flags = builtin_tools_enable_flags(tools)
        # code_interpreter only supports calls in thinking mode, so it also
        # forces enable_thinking on.
        assert flags == {
            "enable_code_interpreter": True,
            "enable_thinking": True,
            "enable_search": True,
        }
        # No tools / None -> no flags.
        assert builtin_tools_enable_flags(None) == {}
        assert builtin_tools_enable_flags([]) == {}
        # Plain string entries are accepted too.
        assert builtin_tools_enable_flags(["code_interpreter"]) == {
            "enable_code_interpreter": True,
            "enable_thinking": True,
        }

    def test_apply_builtin_tools_to_extra_body():
        # The flags land in extra_body (created when needed).
        kwargs = {}
        tools = [
            {"type": "code_interpreter"},
            {"type": "web_search"},
        ]
        apply_builtin_tools_to_extra_body(kwargs, tools)
        assert kwargs["extra_body"] == {
            "enable_code_interpreter": True,
            "enable_thinking": True,
            "enable_search": True,
        }
        # No built-in tools -> nothing is sent (extra_body not even created).
        kwargs = {}
        apply_builtin_tools_to_extra_body(kwargs, None)
        assert kwargs == {}
        # An existing extra_body is preserved and extended.
        kwargs = {"extra_body": {"preserve_thinking": True}}
        apply_builtin_tools_to_extra_body(kwargs, [{"type": "web_search"}])
        assert kwargs["extra_body"] == {
            "preserve_thinking": True,
            "enable_search": True,
        }

    def test_supported_and_default_api_types():
        # OpenAI supports both APIs and defaults to the Responses API (the
        # default_api_type of its default model, the first supported type).
        assert get_supported_api_types_from_provider("openai") == [
            "Responses",
            "Completions",
        ]
        assert get_default_api_type_from_provider("openai") == "Responses"
        assert get_provider_config("openai")["models"]["gpt-5.6-luna"]["supported_api_types"] == [
            "Responses",
            "Completions",
        ]
        # Case-insensitive lookups work.
        assert get_default_api_type_from_provider("OpenAI") == "Responses"
        # Alibaba supports both APIs; Responses is the built-in default for
        # its default model qwen3.8-flash. The native DashScope SDK API type
        # is also supported.
        assert get_supported_api_types_from_provider("alibaba") == [
            "Completions",
            "Responses",
            "DashScope",
        ]
        assert get_default_api_type_from_provider("alibaba") == "Responses"
        assert get_provider_config("alibaba")["models"]["qwen3.8-max"]["supported_api_types"] == [
            "Completions",
            "Responses",
            "DashScope",
        ]
        # DeepSeek supports the Responses and Completions API types (Responses
        # first, the default) plus the Anthropic-compatible API (native
        # Anthropic SDK at https://api.deepseek.com/anthropic).
        assert get_supported_api_types_from_provider("deepseek") == [
            "Responses",
            "Completions",
            "Anthropic",
        ]
        assert get_default_api_type_from_provider("deepseek") == "Responses"
        # Anthropic supports Completions (the built-in default) plus the
        # native Anthropic SDK API type.
        assert get_supported_api_types_from_provider("anthropic") == [
            "Completions",
            "Anthropic",
        ]
        assert get_default_api_type_from_provider("anthropic") == "Completions"
        # MiniMax supports Completions (the built-in default) plus the
        # Anthropic-compatible API (native Anthropic SDK at
        # https://api.minimax.io/anthropic).
        assert get_supported_api_types_from_provider("minimax") == [
            "Completions",
            "Anthropic",
        ]
        assert get_default_api_type_from_provider("minimax") == "Completions"
        # Meta supports the Responses (built-in default) and Completions
        # API types against the single OpenAI-compatible base URL.
        assert get_supported_api_types_from_provider("meta") == [
            "Responses",
            "Completions",
        ]
        assert get_default_api_type_from_provider("meta") == "Responses"
        # Google's default model supports the native Gemini SDK API type too
        # (Completions stays the built-in default).
        assert get_supported_api_types_from_provider("google") == [
            "Completions",
            "Gemini",
        ]
        assert get_default_api_type_from_provider("google") == "Completions"
        # Every other provider is Completions-only for now.  The "custom"
        # provider has no built-in models, so it exposes no defaults.
        for name in (
            "xiaomi",
            "moonshot",
            "zai",
            "xai",
        ):
            assert get_supported_api_types_from_provider(name) == ["Completions"]
            assert get_default_api_type_from_provider(name) == "Completions"
        assert get_supported_api_types_from_provider("custom") is None
        assert get_default_api_type_from_provider("custom") is None
        # Unknown provider returns None.
        assert get_supported_api_types_from_provider("bogus") is None
        assert get_default_api_type_from_provider("bogus") is None

    # ---- endpoint_by_api_type (per-API-type endpoints) -------------------

    def test_endpoint_by_api_type_map():
        # Only providers that declare it expose a per-API-type endpoint map.
        assert get_endpoint_by_api_type("anthropic") == {
            "Completions": "https://api.anthropic.com/v1/",
            "Anthropic": "https://api.anthropic.com",
        }
        # Alibaba maps the OpenAI-compatible types to the compatible-mode
        # gateway and the native DashScope SDK to the native API base URL.
        assert get_endpoint_by_api_type("alibaba") == {
            "Completions": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "Responses": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "DashScope": "https://dashscope-intl.aliyuncs.com/api/v1",
        }
        # DeepSeek maps the OpenAI-compatible types to api.deepseek.com and
        # the native Anthropic SDK API type to the Anthropic-compatible URL.
        assert get_endpoint_by_api_type("deepseek") == {
            "Completions": "https://api.deepseek.com",
            "Responses": "https://api.deepseek.com",
            "Anthropic": "https://api.deepseek.com/anthropic",
        }
        # MiniMax maps the OpenAI-compatible types to api.minimax.io/v1 and
        # the native Anthropic SDK API type to the Anthropic-compatible URL.
        assert get_endpoint_by_api_type("minimax") == {
            "Completions": "https://api.minimax.io/v1",
            "Responses": "https://api.minimax.io/v1",
            "Anthropic": "https://api.minimax.io/anthropic",
        }
        # Providers without the map return None (single shared endpoint).
        assert get_endpoint_by_api_type("openai") is None
        # Unknown provider returns None.
        assert get_endpoint_by_api_type("bogus") is None

    def test_get_endpoint_for_api_type_multi_entry_map():
        """A multi-entry map picks the URL of the requested API type."""
        # Anthropic: the OpenAI-compatible Completions URL and the native SDK URL.
        assert get_endpoint_for_api_type("anthropic", "Completions") == "https://api.anthropic.com/v1/"
        assert get_endpoint_for_api_type("anthropic", "Anthropic") == "https://api.anthropic.com"
        # An API type absent from the map falls back to the single built-in endpoint.
        assert get_endpoint_for_api_type("anthropic", "Responses") == "https://api.anthropic.com/v1/"
        # Without an API type the single built-in endpoint applies.
        assert get_endpoint_for_api_type("anthropic") == "https://api.anthropic.com/v1/"
        # Alibaba: the OpenAI-compatible types keep the compatible-mode URL
        # and the native DashScope SDK type uses the native API base URL.
        assert (
            get_endpoint_for_api_type("alibaba", "Completions")
            == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        assert (
            get_endpoint_for_api_type("alibaba", "Responses")
            == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        assert get_endpoint_for_api_type("alibaba", "DashScope") == "https://dashscope-intl.aliyuncs.com/api/v1"
        # Without an API type the provider's single built-in endpoint applies.
        assert get_endpoint_for_api_type("alibaba") == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        # DeepSeek: the OpenAI-compatible types share api.deepseek.com and the
        # native Anthropic SDK type uses the Anthropic-compatible base URL.
        assert get_endpoint_for_api_type("deepseek", "Responses") == "https://api.deepseek.com"
        assert get_endpoint_for_api_type("deepseek", "Completions") == "https://api.deepseek.com"
        assert get_endpoint_for_api_type("deepseek", "Anthropic") == "https://api.deepseek.com/anthropic"
        # Without an API type the single built-in endpoint applies.
        assert get_endpoint_for_api_type("deepseek") == "https://api.deepseek.com"
        # MiniMax: the OpenAI-compatible types share api.minimax.io/v1 and the
        # native Anthropic SDK type uses the Anthropic-compatible base URL.
        assert get_endpoint_for_api_type("minimax", "Completions") == "https://api.minimax.io/v1"
        assert get_endpoint_for_api_type("minimax", "Responses") == "https://api.minimax.io/v1"
        assert get_endpoint_for_api_type("minimax", "Anthropic") == "https://api.minimax.io/anthropic"
        # Without an API type the single built-in endpoint applies.
        assert get_endpoint_for_api_type("minimax") == "https://api.minimax.io/v1"

    def test_get_endpoint_for_api_type_single_entry_fallback():
        """A single-entry endpoint_by_api_type dict is the default for ANY
        API type (the issue's requirement), unless a config endpoint is set."""
        import janito.providers as pvd

        # Inject a fake provider with a single-entry map to pin the rule.
        fake = {
            "default_model": "fake-model",
            "endpoint": "https://fallback.example/v1",
            "endpoint_by_api_type": {"Anthropic": "https://native.example"},
            "models": {
                "fake-model": {
                    "supported_api_types": ["Completions", "Anthropic"],
                }
            },
        }
        original = dict(pvd._PROVIDER_CONFIGS)
        pvd._PROVIDER_CONFIGS["fake-provider"] = fake
        try:
            # The single entry is used for any API type...
            assert get_endpoint_for_api_type("fake-provider", "Anthropic") == "https://native.example"
            assert get_endpoint_for_api_type("fake-provider", "Completions") == "https://native.example"
            assert get_endpoint_for_api_type("fake-provider", "Responses") == "https://native.example"
            assert get_endpoint_for_api_type("fake-provider") == "https://native.example"
        finally:
            pvd._PROVIDER_CONFIGS.clear()
            pvd._PROVIDER_CONFIGS.update(original)

    def test_get_endpoint_for_api_type_no_map_falls_back_to_endpoint():
        """Providers without the map keep their single built-in endpoint."""
        assert get_endpoint_for_api_type("openai") is None
        assert get_endpoint_for_api_type("openai", "Responses") is None
        assert get_endpoint_for_api_type("xiaomi", "Completions") == "https://api.xiaomimimo.com/v1"
        # Unknown provider returns None.
        assert get_endpoint_for_api_type("bogus", "Completions") is None

    # ---- REQUIRES_BY_API_TYPE (optional packages per API type) -----------

    def test_requires_by_api_type_structure():
        # The native Anthropic SDK API type requires the `anthropic` package,
        # the native DashScope SDK API type requires the `dashscope` package
        # and the native Gemini SDK API type requires the `google-genai`
        # package.
        assert REQUIRES_BY_API_TYPE == {
            "Anthropic": "anthropic",
            "DashScope": "dashscope",
            "Gemini": "google-genai",
        }
        assert get_required_package_for_api_type("Anthropic") == "anthropic"
        assert get_required_package_for_api_type("anthropic") == "anthropic"
        assert get_required_package_for_api_type("DashScope") == "dashscope"
        assert get_required_package_for_api_type("dashscope") == "dashscope"
        assert get_required_package_for_api_type("Gemini") == "google-genai"
        assert get_required_package_for_api_type("gemini") == "google-genai"
        # The OpenAI-SDK API types have no optional-package requirement.
        assert get_required_package_for_api_type("Responses") is None
        assert get_required_package_for_api_type("Completions") is None
        # Unknown API types have no requirement either.
        assert get_required_package_for_api_type("Bogus") is None
        assert get_required_package_for_api_type("") is None
        assert get_required_package_for_api_type(None) is None

    def test_get_all_api_types_includes_native_sdk_types():
        types = get_all_api_types()
        assert "Responses" in types
        assert "Completions" in types
        assert "Anthropic" in types
        assert "DashScope" in types

    def test_is_api_type_available(monkeypatch):
        # The OpenAI-SDK types are always available (hard dependency).
        assert is_api_type_available("Responses") is True
        assert is_api_type_available("Completions") is True
        # The native-SDK API types require optional packages; simulate a test
        # environment where neither is installed so the assertions hold even
        # when the packages are present on the machine running the suite.
        import importlib.util

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        assert is_api_type_available("Anthropic") is False
        assert is_api_type_available("DashScope") is False

    def test_ensure_api_type_available_aborts_when_package_missing(monkeypatch):
        """Setting the Anthropic API type without the `anthropic` package
        raises an actionable ValueError (the change is aborted)."""
        import importlib.util

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        with pytest.raises(ValueError) as exc:
            ensure_api_type_available("Anthropic")
        message = str(exc.value)
        assert "Anthropic" in message
        assert "anthropic" in message
        assert "pip install anthropic" in message

        # Same for the native DashScope SDK API type.
        with pytest.raises(ValueError) as exc:
            ensure_api_type_available("DashScope")
        message = str(exc.value)
        assert "DashScope" in message
        assert "dashscope" in message
        assert "pip install dashscope" in message

    def test_ensure_api_type_available_noop_without_requirement():
        # No requirement -> no error.
        ensure_api_type_available("Responses")
        ensure_api_type_available("Completions")
        ensure_api_type_available("Bogus")

    def test_stateless_mode_flag():
        """Providers whose /responses endpoint keeps server-side state chain
        with previous_response_id; stateless endpoints (DeepSeek) do not."""
        # OpenAI keeps the conversation server-side.
        assert get_stateless_mode_from_provider("openai") is False
        assert get_provider_config("openai")["models"]["gpt-5.6-luna"]["stateless_mode"] is False
        # DeepSeek's /responses endpoint is stateless.
        assert get_stateless_mode_from_provider("deepseek") is True
        assert get_provider_config("deepseek")["models"]["deepseek-flash"]["stateless_mode"] is True
        # Case-insensitive lookups work.
        assert get_stateless_mode_from_provider("DeepSeek") is True
        # Providers that do not declare the flag default to False (server-side,
        # the Responses API design).
        assert get_stateless_mode_from_provider("minimax") is False
        # Unknown provider defaults to False (server-side).
        assert get_stateless_mode_from_provider("bogus") is False

    def test_stateless_mode_flag_honors_config_override(monkeypatch, tmp_path):
        """A per-provider/model stateless-mode override in config.json
        wins over the built-in default (e.g. set from the web Settings
        drawer's Advanced section or ``--set stateless-mode=...``)."""
        import janito.config_store as gc

        monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)

        # OpenAI's built-in default is False (server-side); force stateless
        # on via a model-scoped config override (stored under
        # providers.openai.models.<model>.stateless-mode).
        gc.set_config_value("openai.models.gpt-5.6-luna.stateless-mode", True)
        assert get_stateless_mode_from_provider("openai") is True

        # Clearing the override falls back to the built-in default.
        gc.unset_config_value("openai.models.gpt-5.6-luna.stateless-mode")
        assert get_stateless_mode_from_provider("openai") is False

        # DeepSeek's built-in default is True (stateless); force server-side
        # via config.
        gc.set_config_value("deepseek.models.deepseek-flash.stateless-mode", False)
        assert get_stateless_mode_from_provider("deepseek") is False

        # Unknown providers still default to False regardless of config.
        assert get_stateless_mode_from_provider("bogus") is False

    # ---- Model-level fallback chain --------------------------------------

    def test_fallback_chain_unknown_model_uses_default_model_entry():
        """A model without its own built-in entry falls back to the default
        model's entry for its defaults."""
        # OpenAI has only one built-in model (gpt-5.6-luna); an unknown model
        # inherits its defaults (token limits, API types).
        assert get_default_max_output_tokens_from_provider("openai", "my-model") == (
            get_default_max_output_tokens_from_provider("openai")
        )
        assert get_default_max_input_tokens_from_provider("openai", "my-model") == (
            get_default_max_input_tokens_from_provider("openai")
        )
        assert get_supported_api_types_from_provider("openai", "my-model") == [
            "Responses",
            "Completions",
        ]
        assert get_default_api_type_from_provider("openai", "my-model") == "Responses"
        # An unknown provider still returns None.
        assert get_default_max_output_tokens_from_provider("bogus", "m") is None
        assert get_supported_api_types_from_provider("bogus", "m") is None

    def test_fallback_chain_explicit_model_beats_default_model():
        """When a provider ships multiple models, an explicitly requested
        model's built-in entry wins over the default model's entry."""
        import janito.providers as pvd

        # Inject a provider with two models (default + a smaller one) to pin
        # the per-model resolution rule.
        original = dict(pvd._PROVIDER_CONFIGS)
        pvd._PROVIDER_CONFIGS["multi-model"] = {
            "default_model": "big-model",
            "endpoint": None,
            "models": {
                "big-model": {
                    "supported_api_types": ["Responses"],
                    "max_output_tokens": 128000,
                },
                "small-model": {
                    "supported_api_types": ["Completions"],
                    "max_output_tokens": 16000,
                },
            },
        }
        try:
            # Explicit model -> its own entry wins.
            assert get_default_max_output_tokens_from_provider("multi-model", "small-model") == 16000
            assert get_supported_api_types_from_provider("multi-model", "small-model") == ["Completions"]
            # Default model (None) -> the default model's entry.
            assert get_default_max_output_tokens_from_provider("multi-model") == 128000
            assert get_supported_api_types_from_provider("multi-model") == ["Responses"]
            # Unknown model -> falls back to the default model's entry.
            assert get_default_max_output_tokens_from_provider("multi-model", "unknown-model") == 128000
        finally:
            pvd._PROVIDER_CONFIGS.clear()
            pvd._PROVIDER_CONFIGS.update(original)

    def test_custom_provider_empty_models():
        """The 'custom' provider has no built-in models: model-level accessors
        return None/empty, and there is no default model."""
        import janito.providers.models as pm

        assert get_provider_config("custom")["default_model"] is None
        assert get_provider_config("custom")["models"] == {}
        assert get_default_model_from_provider("custom") is None
        assert get_default_max_output_tokens_from_provider("custom") is None
        assert get_default_max_input_tokens_from_provider("custom") is None
        assert get_supported_api_types_from_provider("custom") is None
        assert get_default_api_type_from_provider("custom") is None
        assert get_default_reasoning_effort_from_provider("custom") is None
        assert get_supported_reasoning_efforts_from_provider("custom") is None
        assert get_default_thinking_from_provider("custom") is False
        # The Provider class exposes the same empties.
        provider = pm.Provider("custom")
        assert provider.model_names() == []
        assert provider.model_config("any-model").get("max_output_tokens") is None
        assert provider.model_config("any-model").get("supported_api_types") is None

    def test_canonical_provider_name_exact_and_case_insensitive():
        assert canonical_provider_name("openai") == "openai"
        assert canonical_provider_name("OpenAI") == "openai"
        assert canonical_provider_name("  MiniMax ") == "minimax"
        assert canonical_provider_name("XAI") == "xai"

    def test_canonical_provider_name_unknown_returns_none():
        assert canonical_provider_name("bogus") is None
        assert canonical_provider_name("") is None
        assert canonical_provider_name("   ") is None
        assert canonical_provider_name(None) is None

    def test_is_supported_provider():
        assert is_supported_provider("openai")
        assert is_supported_provider("Custom")
        assert is_supported_provider("alibaba")
        assert not is_supported_provider("does-not-exist")
        assert not is_supported_provider("")

    def test_validate_provider_name_returns_canonical():
        assert validate_provider_name("OpenAI") == "openai"
        assert validate_provider_name("xai") == "xai"

    def test_validate_provider_name_raises_for_unknown():
        with pytest.raises(ValueError) as exc:
            validate_provider_name("bogus")
        message = str(exc.value)
        assert "bogus" in message
        assert "Supported providers" in message
        # The message enumerates the supported providers.
        for name in list_supported_providers():
            assert name in message

    # ---- End-to-end CLI behaviour --------------------------------------

    def _run_main(monkeypatch, tmp_path, argv):
        """Run janito.__main__.main() with the given argv and a temp config dir.

        Returns the exit code produced by main(). The config dir global is
        restored automatically by monkeypatch on teardown.
        """
        from janito.__main__ import main

        monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)
        monkeypatch.setattr(sys, "argv", ["janito", "-c", str(tmp_path), *argv])
        return main()

    def test_cli_rejects_unknown_provider(monkeypatch, tmp_path):
        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "bogus", "--set", "model=gpt-4"],
        )
        assert rc == 1
        # Nothing should have been written for the bogus provider.
        config_path = tmp_path / "config.json"
        assert not config_path.exists()

    def test_cli_normalizes_provider_casing(monkeypatch, tmp_path):
        import json

        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "OpenAI", "--set", "model=gpt-5.6-luna"],
        )
        assert rc == 0
        config = json.loads((tmp_path / "config.json").read_text())
        # The provider was normalized to its canonical casing ("openai").
        assert config == {"providers": {"openai": {"model": "gpt-5.6-luna"}}}

    def test_cli_rejects_unknown_model_on_set(monkeypatch, tmp_path, capsys):
        """--set model=<unknown> exits 1 without writing anything."""
        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "openai", "--set", "model=gpt-4"],
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "Unknown model 'gpt-4' for provider 'openai'" in err
        assert "gpt-5.6-luna" in err  # available models are listed
        assert not (tmp_path / "config.json").exists()

    def test_cli_rejects_unknown_model_flag(monkeypatch, tmp_path, capsys):
        """--model <unknown> exits 1 before any command runs."""
        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "openai", "--model", "gpt-4", "--info"],
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "Unknown model 'gpt-4' for provider 'openai'" in err

    def test_cli_accepts_any_model_for_openrouter(monkeypatch, tmp_path):
        """openrouter has no built-in model list: any --set model name is accepted."""
        import json

        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "openrouter", "--set", "model=anthropic/claude-3.5-sonnet"],
        )
        assert rc == 0
        config = json.loads((tmp_path / "config.json").read_text())
        assert config == {"providers": {"openrouter": {"model": "anthropic/claude-3.5-sonnet"}}}

    def test_cli_canonicalizes_model_casing(monkeypatch, tmp_path):
        """--set model= with a case-insensitive match stores the canonical casing."""
        import json

        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--provider", "minimax", "--set", "model=minimax-m3"],
        )
        assert rc == 0
        config = json.loads((tmp_path / "config.json").read_text())
        assert config == {"providers": {"minimax": {"model": "MiniMax-M3"}}}

    def test_web_mode_without_extra_prints_actionable_error(monkeypatch, tmp_path, capsys):
        """`--web` without the optional [web] extra fails with the documented
        install hint instead of a defensive try/except ImportError fallback."""
        import importlib.util

        import janito.__main__ as main_mod

        # Skip runtime-config validation so we reach the web-mode branch
        # without needing an API key in the temp config dir.
        monkeypatch.setattr(main_mod, "validate_runtime_config", lambda args=None: None)
        # Simulate the optional [web] extra not being installed.
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

        rc = _run_main(monkeypatch, tmp_path, ["--web"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "the web UI requires optional dependencies" in err
        assert "pip install janito[web]" in err

    def test_cli_system_prompt_file_missing_fails_at_startup(monkeypatch, tmp_path, capsys):
        """A configured system-prompt-file that does not exist fails fast at
        startup (exit 1, actionable error) instead of a traceback from the
        prompt render."""
        import json

        import janito.__main__ as main_mod

        # Skip runtime-config validation so we reach the system-prompt-file
        # check without needing an API key in the temp config dir.
        monkeypatch.setattr(main_mod, "validate_runtime_config", lambda args=None: None)

        missing = tmp_path / "does-not-exist.md"
        (tmp_path / "config.json").write_text(json.dumps({"system-prompt-file": str(missing)}))

        with pytest.raises(SystemExit) as exc:
            _run_main(monkeypatch, tmp_path, ["hello"])
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "system-prompt-file" in err
        assert "does not exist" in err

    def test_cli_set_system_prompt_file_missing_fails(monkeypatch, tmp_path, capsys):
        """`--set system-prompt-file=<missing>` is rejected with exit 1 and the
        actionable error (same validation as at startup)."""
        missing = tmp_path / "does-not-exist.md"

        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--set", f"system-prompt-file={missing}"],
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "system-prompt-file" in err
        assert str(missing) in err
        assert "does not exist" in err

    def test_cli_set_system_prompt_file_existing_stores_value(monkeypatch, tmp_path):
        """`--set system-prompt-file=<existing>` stores the value (the file is
        validated when the value is set)."""
        import json

        prompt_file = tmp_path / "base-prompt.md"
        prompt_file.write_text("Be terse.", encoding="utf-8")

        rc = _run_main(
            monkeypatch,
            tmp_path,
            ["--set", f"system-prompt-file={prompt_file}"],
        )
        assert rc == 0
        config = json.loads((tmp_path / "config.json").read_text())
        assert config == {"system-prompt-file": str(prompt_file)}

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        import tempfile

        class _MP:
            def __init__(self):
                self._undo = []

            def setattr(self, obj, name, value):
                self._undo.append((obj, name, getattr(obj, name)))
                setattr(obj, name, value)

            def restore(self):
                for obj, name, value in reversed(self._undo):
                    setattr(obj, name, value)

        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                mp = _MP()
                try:
                    import inspect

                    params = inspect.signature(fn).parameters
                    with tempfile.TemporaryDirectory() as d:
                        if "tmp_path" in params:
                            fn(mp, Path(d))
                        else:
                            fn()
                finally:
                    mp.restore()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
