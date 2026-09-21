"""
Tests for the ProviderConfigLoader class (janito.config_loaders).

Covers the class-level API (load_model / load_max_output_tokens /
load_effort / load_api_type / load_stateless_mode / load_endpoint)
including the legacy key chain and the boolean-string tolerance.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
from janito.config_cli import set_config_from_cli
from janito.config_loaders import ProviderConfigLoader


def _use_temp_config(monkeypatch, tmp_path):
    """Point the config directory at a temporary directory."""
    config_path = tmp_path / ".janito" / "config.json"
    monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
    return config_path


if pytest is not None:

    def test_load_model(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        set_config_from_cli("model=gpt-5.6-luna", "openai")
        assert loader.load_model("openai") == "gpt-5.6-luna"
        assert loader.load_model("unknown") is None
        assert loader.load_model() is None  # no configured provider

    def test_load_max_output_tokens_legacy_keys_ignored(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "openai": {"context-window-size": 65536},
                        "minimax": {"context_window_size": 4096},
                        "alibaba": {"max-output-tokens": 8192},
                    }
                }
            )
        )
        # Legacy provider-scoped keys are NO LONGER read: the loaders only
        # look at the model-scoped path (providers.<p>.models.<m>.<key>).
        assert loader.load_max_output_tokens("alibaba") is None
        assert loader.load_max_output_tokens("openai") is None
        assert loader.load_max_output_tokens("minimax") is None
        assert loader.load_max_output_tokens("missing") is None
        assert loader.load_max_output_tokens() is None

    def test_load_max_input_tokens(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "openai": {"models": {"gpt-5.6-luna": {"max-input-tokens": 128000}}},
                        "minimax": {"models": {"MiniMax-M3": {"max_input_tokens": 4096}}},
                    }
                }
            )
        )
        # The model-scoped path is read; the underscore variant is NOT
        # honored (no backward compatibility for legacy key variants).
        assert loader.load_max_input_tokens("openai") == 128000
        assert loader.load_max_input_tokens("minimax") is None
        assert loader.load_max_input_tokens("missing") is None
        assert loader.load_max_input_tokens() is None

    def test_load_effort_coerces_to_str(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        set_config_from_cli("effort=xhigh", "alibaba")
        assert loader.load_effort("alibaba") == "xhigh"

    def test_load_api_type_coerces_to_str(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        set_config_from_cli("api-type=Responses", "openai")
        assert loader.load_api_type("openai") == "Responses"
        assert loader.load_api_type("unknown") is None

    def test_load_stateless_mode_bool_tolerance(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Hand-written string forms are tolerated (model-scoped path).
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "openai": {"models": {"gpt-5.6-luna": {"stateless-mode": "true"}}},
                        "deepseek": {"models": {"deepseek-flash": {"stateless-mode": "FALSE"}}},
                        "xai": {"models": {"grok-4.6": {"stateless-mode": True}}},
                        "zai": {"models": {"glm-5.3-flash": {"stateless-mode": False}}},
                    }
                }
            )
        )
        assert loader.load_stateless_mode("openai") is True
        assert loader.load_stateless_mode("deepseek") is False
        assert loader.load_stateless_mode("xai") is True
        assert loader.load_stateless_mode("zai") is False
        # No override -> None.
        assert loader.load_stateless_mode("moonshot") is None
        assert loader.load_stateless_mode() is None

    def test_load_endpoint_provider_scoped_only(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        loader = ProviderConfigLoader()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "providers": {"custom": {"endpoint": "http://a/v1"}},
                    "endpoint": "http://legacy/v1",
                }
            )
        )
        # Provider-scoped endpoint is read.
        assert loader.load_endpoint("custom") == "http://a/v1"
        # Top-level 'endpoint' is ignored (no backward compatibility).
        assert loader.load_endpoint("openai") is None
        assert loader.load_endpoint("bogus") is None

    # ---- flat system-prompt / system-prompt-file keys --------------------

    def test_load_system_prompt_start_none_when_unset(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        assert load_system_prompt_start() == (None, None)

    def test_load_system_prompt_start_literal(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import _display_config_path, load_system_prompt_start

        set_config_from_cli("system-prompt=You are a cow")
        text, label = load_system_prompt_start()
        assert text == "You are a cow"
        # The literal key's label points at the config file:key (issue #86).
        assert label == f"(config) {_display_config_path(config_path)}:system-prompt"

    def test_load_system_prompt_start_file(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        prompt_file = tmp_path / "base-prompt.md"
        prompt_file.write_text("Be terse.", encoding="utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"system-prompt-file": str(prompt_file)}))
        assert load_system_prompt_start() == ("Be terse.", f"(config) {prompt_file}")

    def test_load_system_prompt_start_file_wins_over_literal(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        prompt_file = tmp_path / "base-prompt.md"
        prompt_file.write_text("from the file", encoding="utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "system-prompt": "from the literal",
                    "system-prompt-file": str(prompt_file),
                }
            )
        )
        # system-prompt-file is the more specific form and wins.
        assert load_system_prompt_start() == (
            "from the file",
            f"(config) {prompt_file}",
        )

    def test_load_system_prompt_start_relative_path_resolved_against_cwd(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        monkeypatch.chdir(tmp_path)
        (tmp_path / "prompt.md").write_text("relative", encoding="utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"system-prompt-file": "prompt.md"}))
        # The label keeps the key's value as written (issue #86).
        assert load_system_prompt_start() == ("relative", "(config) prompt.md")

    def test_load_system_prompt_start_empty_file_falls_back_to_default(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        prompt_file = tmp_path / "empty.md"
        prompt_file.write_text("   \n\n  ", encoding="utf-8")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"system-prompt-file": str(prompt_file)}))
        # Empty (whitespace-only) file -> default start, like an empty
        # AGENTS.md; the label still records the configured source.
        assert load_system_prompt_start() == (None, f"(config) {prompt_file}")

    def test_load_system_prompt_start_missing_file_raises(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_system_prompt_start

        missing = tmp_path / "does-not-exist.md"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"system-prompt-file": str(missing)}))
        with pytest.raises(ValueError, match="system-prompt-file"):
            load_system_prompt_start()

    def test_validate_system_prompt_file_path_returns_resolved_path(tmp_path):
        from janito.config_loaders import validate_system_prompt_file_path

        prompt_file = tmp_path / "base-prompt.md"
        prompt_file.write_text("Be terse.", encoding="utf-8")
        assert validate_system_prompt_file_path(str(prompt_file)) == str(prompt_file)

    def test_validate_system_prompt_file_path_missing_raises(tmp_path):
        from janito.config_loaders import validate_system_prompt_file_path

        missing = tmp_path / "does-not-exist.md"
        with pytest.raises(ValueError, match="system-prompt-file") as exc:
            validate_system_prompt_file_path(str(missing))
        assert str(missing) in str(exc.value)
        assert "does not exist" in str(exc.value)

    # ---- flat used-files flag --------------------------------------------

    def test_load_used_files_enabled_defaults_to_false(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_used_files_enabled

        assert load_used_files_enabled() is False

    def test_load_used_files_enabled_coerced_via_set(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_used_files_enabled

        # --set used-files=True stores a real boolean (BOOL_VALUED_KEYS).
        key, value = set_config_from_cli("used-files=True")
        assert key == "used-files"
        assert value is True
        assert load_used_files_enabled() is True

        key, value = set_config_from_cli("used-files=off")
        assert value is False
        assert load_used_files_enabled() is False

    def test_load_used_files_enabled_string_tolerance(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_used_files_enabled

        # Hand-written string forms are tolerated (flat key).
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"used-files": "TRUE"}))
        assert load_used_files_enabled() is True
        config_path.write_text(json.dumps({"used-files": "false"}))
        assert load_used_files_enabled() is False
        config_path.write_text(json.dumps({"used-files": "1"}))
        assert load_used_files_enabled() is True

    def test_load_used_files_enabled_non_bool_value_is_falsy(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_used_files_enabled

        config_path.parent.mkdir(parents=True, exist_ok=True)
        # A string that is not a known true form is treated as False
        # (mirrors load_stateless_mode); a numeric 0 is falsy too.
        config_path.write_text(json.dumps({"used-files": "x"}))
        assert load_used_files_enabled() is False
        config_path.write_text(json.dumps({"used-files": 0}))
        assert load_used_files_enabled() is False
        # A truthy non-string (e.g. a numeric 1 written by hand) is True.
        config_path.write_text(json.dumps({"used-files": 1}))
        assert load_used_files_enabled() is True

    # ---- flat privileges key (issue #89) ----------------------------------

    def test_set_privileges_canonicalized(monkeypatch, tmp_path):
        from janito.privileges import Privileges

        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_privileges_from_config

        # Any order/case is accepted and canonicalized to the r/w/x order.
        key, value = set_config_from_cli("privileges=xwr")
        assert key == "privileges"
        assert value == "rwx"
        assert load_privileges_from_config() == Privileges(True, True, True)

    def test_set_privileges_write_only_does_not_imply_read(monkeypatch, tmp_path):
        from janito.privileges import Privileges

        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_privileges_from_config

        # Flag-semantics parity: 'w' alone is write-only, like `janito -w`.
        key, value = set_config_from_cli("privileges=w")
        assert value == "w"
        assert load_privileges_from_config() == Privileges(False, True, False)

    def test_set_privileges_rejects_invalid_values(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)

        with pytest.raises(ValueError, match="privileges"):
            set_config_from_cli("privileges=rxz")
        # An empty value is rejected too: --unset privileges is the way back.
        with pytest.raises(ValueError, match="privileges"):
            set_config_from_cli("privileges=")

    def test_load_privileges_from_config_none_when_unset(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_privileges_from_config

        assert load_privileges_from_config() is None

    def test_load_privileges_from_config_invalid_handwritten_returns_none(monkeypatch, tmp_path):
        config_path = _use_temp_config(monkeypatch, tmp_path)
        from janito.config_loaders import load_privileges_from_config

        config_path.parent.mkdir(parents=True, exist_ok=True)
        # A hand-written invalid value is ignored (read-only default applies)
        # instead of raising at startup; --set validates strictly.
        config_path.write_text(json.dumps({"privileges": "rxz"}))
        assert load_privileges_from_config() is None
        config_path.write_text(json.dumps({"privileges": "rw"}))
        from janito.privileges import Privileges

        assert load_privileges_from_config() == Privileges(True, True, False)

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        import tempfile

        class _MP:
            def setattr(self, obj, name, value):
                setattr(obj, name, value)

        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                with tempfile.TemporaryDirectory() as d:
                    fn(_MP(), Path(d))
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
