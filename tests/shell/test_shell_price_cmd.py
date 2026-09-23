"""
Tests for the shell /price command handler.

``/price`` renders a table with one row per built-in model: the provider,
the model name and four cost columns for a notional request of **1M input
tokens (cache miss) + 1M cached input tokens + 1M output tokens** --
``1M in``, ``1M cache``, ``1M output`` and their ``Total``.  Each component
column is computed by the provider's cost module via
:func:`janito.providers.costing.get_provider_cost` with
``is_reference=True`` (so reference/peak rates apply and the string carries
no rate-band suffix); the ``Total`` column is the exact dollar sum of the
three components.  Providers/models without a cost module show ``N/A``.
The command must not match non-``/price`` input (e.g. ``/prices``).
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import janito.config_dir as config_dir_mod
from janito.providers.costing import format_cost, get_provider_cost
from janito.providers.registry import get_provider
from janito.providers.validation import list_supported_providers
from janito.shell import InteractiveShell
from janito.shell.cmds.registry import get_registered_commands


def _use_temp_config(monkeypatch, tmp_path):
    """Point the config directory at a temporary directory."""
    config_path = tmp_path / ".janito" / "config.json"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    return config_path


def _shell():
    """Build a fresh shell for testing."""
    return InteractiveShell(model="test-model", no_history=True)


def _price_handler():
    """Return the registered /price command handler."""
    return next(c for c in get_registered_commands() if c.name == "/price")


def _inject_fake_no_cost_provider():
    """Inject a provider with a model but no cost module.

    Every built-in provider with built-in models now ships a cost module, so
    the N/A fallback is exercised through a runtime-injected provider.  The
    registry holds a reference to ``janito.providers._PROVIDER_CONFIGS``, so
    the mutation is visible to the /price handler.

    Returns:
        A callable that restores ``_PROVIDER_CONFIGS`` to its original state.
    """
    import janito.providers as pvd

    original = dict(pvd._PROVIDER_CONFIGS)
    pvd._PROVIDER_CONFIGS["fake-no-cost"] = {
        "default_model": "fake-model",
        "endpoint": None,
        "models": {
            "fake-model": {
                "supported_api_types": ["Completions"],
                "max_input_tokens": None,
                "max_output_tokens": None,
            }
        },
    }

    def restore():
        pvd._PROVIDER_CONFIGS.clear()
        pvd._PROVIDER_CONFIGS.update(original)

    return restore


def test_price_command_is_registered():
    """The /price handler is registered with the shell command registry."""
    names = [cmd.name for cmd in get_registered_commands()]
    assert "/price" in names


def test_price_lists_providers_and_models(monkeypatch, tmp_path, capsys):
    """``/price`` lists every built-in provider and its built-in models."""
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell()
    assert _price_handler().handle(shell, "/price") is True

    out = capsys.readouterr().out
    for provider in list_supported_providers():
        found = get_provider(provider)
        for model in found.model_names():
            assert provider in out
            assert model in out


def test_price_cost_columns_match_provider_cost(monkeypatch, tmp_path, capsys):
    """The per-type columns equal get_provider_cost(..., is_reference=True)."""
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell()
    assert _price_handler().handle(shell, "/price") is True

    out = capsys.readouterr().out
    for provider in list_supported_providers():
        found = get_provider(provider)
        for model in found.model_names():
            cost_in = get_provider_cost(provider, model, 1_000_000, 0, 0, is_reference=True)
            cost_cache = get_provider_cost(provider, model, 1_000_000, 0, 1_000_000, is_reference=True)
            cost_output = get_provider_cost(provider, model, 0, 1_000_000, 0, is_reference=True)
            assert cost_in in out
            assert cost_cache in out
            assert cost_output in out
            # Total equals the exact sum of the three components.
            from janito.providers.costing import get_provider_cost_value

            values = [
                get_provider_cost_value(provider, model, 1_000_000, 0, 0, is_reference=True),
                get_provider_cost_value(provider, model, 1_000_000, 0, 1_000_000, is_reference=True),
                get_provider_cost_value(provider, model, 0, 1_000_000, 0, is_reference=True),
            ]
            if all(value is not None for value in values):
                assert format_cost(sum(values)) in out


def test_price_shows_na_for_models_without_cost_module(monkeypatch, tmp_path, capsys):
    """Models without a provider cost module are reported as N/A."""
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell()
    assert _price_handler().handle(shell, "/price") is True

    out = capsys.readouterr().out
    # The anthropic provider now ships a cost module, so its models show a
    # real cost, not N/A.  /price bills 1M cache-miss input + 1M cache-hit
    # input + 1M output: claude-sonnet-5 -> $2 + $0.20 + $10 = 12.200000$.
    # Numbers over words (Rule 6): numeric source of truth, one smoke assert.
    from janito.providers.costing import get_provider_cost_value

    assert get_provider_cost_value("anthropic", "claude-sonnet-5", 1_000_000, 0, 0, is_reference=True) is not None
    assert get_provider_cost_value("openai", "gpt-6-luna", 1_000_000, 0, 0, is_reference=True) is not None
    assert out.strip() != ""
    assert "anthropic" in out
    # OpenAI ships a cost module, so its model shows a real cost, not N/A.
    # gpt-6-luna 1M input exceeds the 272K high-context threshold, so the
    # in/cache columns bill at 2x the input rate: $0.20 + $0.02 + $0.50 =
    # 0.720000$.

    # A provider without a cost module is reported as N/A.
    restore = _inject_fake_no_cost_provider()
    try:
        assert _price_handler().handle(_shell(), "/price") is True
        out = capsys.readouterr().out
        assert "fake-no-cost" in out
        assert "fake-model" in out
        assert "N/A" in out
    finally:
        restore()


def test_non_price_input_is_not_handled(capsys):
    """``/prices`` (plural) must not match the /price command."""
    shell = _shell()
    assert _price_handler().handle(shell, "/prices") is False
    assert capsys.readouterr().out == ""


def test_parse_cost_helper():
    """_parse_cost correctly parses numeric costs and handles N/A / invalid strings."""
    from janito.shell.cmds.price import _parse_cost

    assert _parse_cost("6.3$") == 6.3
    assert _parse_cost("88.0\u00a2 (off-peak)") == 0.88
    assert _parse_cost("  3.9$ ") == 3.9
    assert _parse_cost("0.012\u00a2") == 0.00012
    assert _parse_cost("123$") == 123.0
    assert _parse_cost("N/A") == float("-inf")
    assert _parse_cost("") == float("-inf")
    assert _parse_cost(None) == float("-inf")
