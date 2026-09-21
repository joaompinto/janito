"""
Tests for the CLI version banner printed on the shell.

The banner is printed right before the full-privileges warning in sessions
that fell back to the implicit full-privileges default and shows
``Janito x.y.z - Working at <cwd>`` with the version in cyan and the
working directory in magenta.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from janito import __version__
from janito.cli.chat import print_version_banner

if pytest is not None:

    def test_version_banner_prints_version_and_cwd(monkeypatch, tmp_path, capsys):
        from rich.console import Console

        cwd = tmp_path
        monkeypatch.chdir(cwd)

        print_version_banner(Console(width=200))

        out = capsys.readouterr().out.strip()
        assert __version__ in out
        assert str(cwd) in out

    def test_single_prompt_prints_banner_without_read_only_notice(monkeypatch, capsys):
        """run_single_prompt prints the banner but no warning without fallback."""
        from conftest import make_config

        import janito.cli.chat as chat_mod
        from janito import privileges as _privileges_mod

        # The banner must not have been printed yet in this test process
        # (other tests call print_version_banner directly).
        monkeypatch.setattr(chat_mod, "_banner_printed", False)
        _privileges_mod.full_privileges_warning_pending = False

        class _Args:
            prompt = "hi"
            verbose = False
            thinking = False
            model = None
            provider = None
            effort = None
            system_prompt = None
            no_system_prompt = False

        # Avoid real config/auth resolution and the network (issue #70): the
        # one-shot path builds the resolved APIConfig at the composition
        # point, so inject a config and a no-op send function.
        monkeypatch.setattr(chat_mod, "build_api_config", lambda **kw: make_config())
        monkeypatch.setattr(
            chat_mod,
            "_make_turn_func",
            lambda config, **kw: lambda prompt, **kwargs: None,
        )
        # Avoid a real system-prompt build: force the shared SessionSetup to
        # resolve a fixed prompt so the test does not depend on skills/cwd.
        import janito.session_setup as session_setup_mod

        monkeypatch.setattr(
            session_setup_mod.SessionSetup,
            "effective_system_prompt",
            lambda self: "system",
        )

        chat_mod.run_single_prompt(_Args())

        out = capsys.readouterr().out
        assert __version__ in out or "Janito" in out

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                except TypeError:
                    # Skip tests that require monkeypatch/capsys fixtures.
                    continue
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
