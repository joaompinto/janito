"""
Tests for SessionSetup (janito.session_setup).

SessionSetup centralizes the system-prompt and toolset selection that was
previously duplicated between ``cli/chat.py`` and
``janito.web.backend.config.WebServerConfig``.  These tests verify the
resolution chain, the tools suppression rules, and that the CLI and web
entry points produce identical results for the same flags.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from janito.session_setup import SessionSetup


def _args(**overrides):
    """Build a minimal argparse-like object with the session flags."""
    defaults = {
        "system_prompt": None,
        "no_system_prompt": False,
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()


def _patch_config_start(monkeypatch, start):
    """Pin load_system_prompt_start so tests never touch the real config."""
    import janito.config_loaders as config_loaders_mod

    monkeypatch.setattr(config_loaders_mod, "load_system_prompt_start", lambda: (start, None))


@pytest.fixture(autouse=True)
def _no_tool_hints(monkeypatch):
    """Keep the real tools' system prompt hints out of the resolved prompt."""
    import janito.tooling.tools_registry as tools_registry

    monkeypatch.setattr(tools_registry, "get_system_prompt_hints", lambda: [])


if pytest is not None:
    # ---- resolution chain ----------------------------------------------

    def test_default_uses_skills_prompt(monkeypatch):
        _patch_config_start(monkeypatch, None)
        setup = SessionSetup()
        from janito.system_prompt import default_system_prompt_manager

        assert setup.effective_system_prompt() == default_system_prompt_manager().render()
        assert setup.no_tools is False

    def test_custom_system_prompt_wins():
        setup = SessionSetup(system_prompt="You are a cow")
        assert setup.effective_system_prompt() == "You are a cow"
        assert setup.no_tools is False

    def test_no_system_prompt_yields_none():
        setup = SessionSetup(no_system_prompt=True)
        assert setup.effective_system_prompt() is None
        assert setup.no_tools is True

    # ---- configured start (system-prompt / system-prompt-file) ----------

    def test_config_system_prompt_applies_to_default(monkeypatch):
        """The configured start replaces the base prompt in the default prompt."""
        _patch_config_start(monkeypatch, "configured start text")
        setup = SessionSetup()
        prompt = setup.effective_system_prompt()
        assert "configured start text" in prompt
        assert prompt.startswith("configured start text\n")

    def test_config_start_does_not_mutate_shared_manager(monkeypatch):
        """Applying the config start per call leaves SYSTEM_PROMPT_MANAGER intact."""
        from janito.system_prompt import SYSTEM_PROMPT_MANAGER

        _patch_config_start(monkeypatch, "configured start text")
        SessionSetup().effective_system_prompt()
        SessionSetup().effective_system_prompt()
        sections = {section.name: section for section in SYSTEM_PROMPT_MANAGER.get_all_sections()}
        # The shared manager's start stays at its lazy empty seed: the
        # configured (or built-in resource) start is only applied to a
        # per-call copy.
        assert sections["start"].text == ""

    def test_cli_system_prompt_wins_over_config(monkeypatch):
        """-S overrides the configured start without touching the config."""
        _patch_config_start(monkeypatch, "configured start text")
        setup = SessionSetup(system_prompt="custom")
        assert setup.effective_system_prompt() == "custom"

    def test_no_system_prompt_disables_config(monkeypatch):
        """-Z yields None even when a configured start is set."""
        _patch_config_start(monkeypatch, "configured start text")
        setup = SessionSetup(no_system_prompt=True)
        assert setup.effective_system_prompt() is None

    def test_messages_context_uses_config_start(monkeypatch, tmp_path):
        """The seeded system message carries the configured start."""
        import janito.tooling.tools_registry as tools_registry

        _patch_config_start(monkeypatch, "configured start text")
        monkeypatch.setattr(tools_registry, "get_skills_section", lambda: "")
        monkeypatch.chdir(tmp_path)
        messages = SessionSetup().messages_context()
        assert messages == [{"role": "system", "content": "configured start text\n"}]

    # ---- single-prompt context -----------------------------------------

    def test_messages_and_tools_context(monkeypatch):
        _patch_config_start(monkeypatch, None)
        # Default: seeded system message, tools=None (use all).
        setup = SessionSetup()
        messages, tools = setup.messages_context(), setup.tools_arg()
        assert len(messages) == 1 and messages[0]["role"] == "system"
        assert tools is None

        # Custom prompt: seeded message, tools=None (use all).
        setup = SessionSetup(system_prompt="custom")
        assert setup.messages_context() == [{"role": "system", "content": "custom"}]
        assert setup.tools_arg() is None

        # No system prompt: no seed, tools=[].
        setup = SessionSetup(no_system_prompt=True)
        assert setup.messages_context() == []
        assert setup.tools_arg() == []

    # ---- toolset enablement --------------------------------------------

    def test_enable_toolsets_extra(monkeypatch):
        import janito.tooling.tools_registry as tools_registry

        added = []
        monkeypatch.setattr(tools_registry, "add_toolset", lambda name: added.append(name))
        SessionSetup().enable_toolsets(extra=["janitoweb"])
        assert added == ["janitoweb"]

    def test_enable_toolsets_nothing_when_not_requested(monkeypatch):
        import janito.tooling.tools_registry as tools_registry

        added = []
        monkeypatch.setattr(tools_registry, "add_toolset", lambda name: added.append(name))
        SessionSetup().enable_toolsets()
        assert added == []

    # ---- CLI <-> web parity --------------------------------------------

    def test_cli_and_web_resolve_identical_prompts(monkeypatch):
        """The same flags produce the same prompt from cli/chat.py and WebServerConfig."""
        _patch_config_start(monkeypatch, None)
        import janito.cli.chat as chat_mod
        from janito.web.backend.config import WebServerConfig

        for flags in (
            {},
            {"system_prompt": "custom"},
            {"no_system_prompt": True},
        ):
            cli_prompt, _ = chat_mod._resolve_system_prompt(_args(**flags))
            config = WebServerConfig(
                system_prompt=flags.get("system_prompt"),
                no_system_prompt=flags.get("no_system_prompt", False),
            )
            assert config.get_effective_system_prompt() == cli_prompt

    def test_cli_and_web_resolve_config_start_identically(monkeypatch):
        """A configured start is applied by both the CLI and the web entry point."""
        _patch_config_start(monkeypatch, "configured start text")
        import janito.cli.chat as chat_mod
        from janito.web.backend.config import WebServerConfig

        cli_prompt, _ = chat_mod._resolve_system_prompt(_args())
        assert "configured start text" in cli_prompt
        assert WebServerConfig().get_effective_system_prompt() == cli_prompt

    def test_cli_and_web_enable_same_toolsets(monkeypatch):
        """cli/chat.py and WebServerConfig call add_toolset with the same names."""
        import janito.cli.chat as chat_mod
        import janito.tooling.tools_registry as tools_registry
        from janito.web.backend.config import WebServerConfig

        added = []
        monkeypatch.setattr(tools_registry, "add_toolset", lambda name: added.append(name))

        chat_mod._enable_requested_toolsets(_args())
        cli_added = list(added)
        added.clear()

        WebServerConfig().apply_toolsets()
        web_added = list(added)

        # The web mode additionally loads the web-only toolset.
        assert cli_added == []
        assert web_added == ["janitoweb"]

else:  # pragma: no cover - fallback runner without pytest

    def _main():
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
                    fn(mp)
                finally:
                    mp.restore()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
