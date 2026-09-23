"""
Tests for the -l/--local CLI switch (project-local configuration).

When ``-l`` / ``--local`` is active:

- ``--set`` / ``--set-api-key`` / ``--set-secret`` (and friends) write to the
  project-local ``./.janito`` directory instead of the base (global
  ``~/.janito`` or the ``-c`` / ``--config-dir`` override) directory.
- Reads resolve local values first and fall back to the base directory.
- List operations show both the local and the global configuration.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.auth_config as ac
import janito.config_cli as cc
import janito.config_dir as config_dir_mod
import janito.config_loaders as cl
import janito.config_store as cs
import janito.secrets_config as sc
from janito.cli.handlers.auth import handle_list_keys
from janito.cli.handlers.secrets import handle_list_secrets


def _use_temp_dirs(monkeypatch, tmp_path):
    """Point the base dir at tmp_path/global and cwd at tmp_path/project.

    Returns:
        tuple: (global_dir, project_dir) where project_dir is the cwd, so the
            local config dir resolves to ``project_dir/.janito``.
    """
    global_dir = tmp_path / "global_janito"
    project_dir = tmp_path / "project"
    project_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(config_dir_mod, "_config_dir", global_dir)
    monkeypatch.chdir(project_dir)
    return global_dir, project_dir


if pytest is not None:

    @pytest.fixture(autouse=True)
    def _reset_local_mode():
        """Ensure -l/--local mode never leaks into other test modules."""
        yield
        config_dir_mod.set_local_config_mode(False)

    def test_get_config_dirs_without_local(monkeypatch, tmp_path):
        global_dir, _ = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        assert config_dir_mod.get_config_dirs() == [global_dir]
        assert config_dir_mod.get_config_dir() == global_dir

    def test_get_config_dirs_with_local(monkeypatch, tmp_path):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(True)
        assert config_dir_mod.get_config_dirs() == [
            project_dir / ".janito",
            global_dir,
        ]
        assert config_dir_mod.get_config_dir() == project_dir / ".janito"

    def test_write_goes_to_local_in_local_mode(monkeypatch, tmp_path):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(True)
        cs.set_config_value("provider", "openai")
        ac.set_api_key("openai", "sk-local")
        sc.set_secret("token", "local")

        local = project_dir / ".janito"
        assert (local / "config.json").exists()
        assert (local / "auth.json").exists()
        assert (local / "secrets.json").exists()
        # Nothing is written to the global dir.
        assert not (global_dir / "config.json").exists()
        assert not (global_dir / "auth.json").exists()
        assert not (global_dir / "secrets.json").exists()
        # Reads resolve from the local files.
        assert cs.load_config()["provider"] == "openai"
        assert ac.get_api_key("openai") == "sk-local"
        assert sc.get_secret("token") == "local"

    def test_write_goes_to_global_without_local(monkeypatch, tmp_path):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        cs.set_config_value("provider", "openai")
        assert (global_dir / "config.json").exists()
        assert not (project_dir / ".janito" / "config.json").exists()

    def test_local_overrides_global_for_resolution(monkeypatch, tmp_path):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        # Seed global values.
        config_dir_mod.set_local_config_mode(False)
        cs.set_config_value("provider", "openai")
        cs.set_config_value("theme", "global")
        ac.set_api_key("openai", "sk-global")
        sc.set_secret("token", "global")

        # Local values override them.
        config_dir_mod.set_local_config_mode(True)
        cs.set_config_value("theme", "local")
        ac.set_api_key("openai", "sk-local")
        sc.set_secret("token", "local")

        assert cs.load_config()["theme"] == "local"
        # provider only exists globally -> fall back to it.
        assert cs.load_config()["provider"] == "openai"
        assert ac.get_api_key("openai") == "sk-local"
        assert sc.get_secret("token") == "local"

        # Writes never copy global entries into the local files.
        local_config = json.loads((project_dir / ".janito" / "config.json").read_text())
        assert "theme" in local_config
        assert "provider" not in local_config

    def test_provider_scoped_config_local_override(monkeypatch, tmp_path):
        _, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        cc.set_config_from_cli("model=gpt-6-luna", "openai")
        config_dir_mod.set_local_config_mode(True)
        cc.set_config_from_cli("model=gpt-6-sol", "openai")
        # The local model wins during resolution.
        assert cc.get_config_from_cli("model", "openai") == "gpt-6-sol"
        assert cl.load_model_from_config("openai") == "gpt-6-sol"
        # The local file stores only the overridden provider subkey.
        local_config = json.loads((project_dir / ".janito" / "config.json").read_text())
        assert local_config == {"providers": {"openai": {"model": "gpt-6-sol"}}}

    def test_get_config_from_cli_finds_global_file_in_local_mode(monkeypatch, tmp_path):
        global_dir, _ = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        cs.set_config_value("theme", "global")
        # Only the global file exists; --get must still resolve it in local mode.
        config_dir_mod.set_local_config_mode(True)
        assert cc.get_config_from_cli("theme") == "global"

    def test_list_keys_shows_both_global_and_local(monkeypatch, tmp_path, capsys):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        ac.set_api_key("openai", "sk-global")
        config_dir_mod.set_local_config_mode(True)
        ac.set_api_key("deepseek", "sk-local")

        rc = handle_list_keys(None)
        out = capsys.readouterr().out
        assert rc == 0
        assert out.strip() != ""
        assert "openai" in out
        assert "deepseek" in out

    def test_list_secrets_shows_both_global_and_local(monkeypatch, tmp_path, capsys):
        global_dir, project_dir = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(False)
        sc.set_secret("global_key", "1")
        config_dir_mod.set_local_config_mode(True)
        sc.set_secret("local_key", "2")

        rc = handle_list_secrets(None)
        out = capsys.readouterr().out
        assert rc == 0
        assert out.strip() != ""
        assert "global_key" in out
        assert "local_key" in out

    def test_local_mode_flag_resets(monkeypatch, tmp_path):
        global_dir, _ = _use_temp_dirs(monkeypatch, tmp_path)
        config_dir_mod.set_local_config_mode(True)
        config_dir_mod.set_local_config_mode(False)
        assert config_dir_mod.get_config_dir() == global_dir

else:  # pragma: no cover - fallback runner without pytest

    def _run_one(name, fn, tmp_path):
        """Run a single test function with a monkeypatch/capsys stand-in."""

        class _MP:
            def __init__(self):
                self._undo = []

            def setattr(self, obj, name, value):
                self._undo.append((obj, name, getattr(obj, name)))
                setattr(obj, name, value)

            def chdir(self, path):
                import os

                self._undo.append((os, "getcwd", None))
                os.chdir(path)

            def restore(self):
                for obj, name, value in reversed(self._undo):
                    if value is None:
                        continue
                    setattr(obj, name, value)

        class _Out:
            out = ""
            err = ""

        class _Cap:
            def readouterr(self):
                return _Out()

        mp = _MP()
        try:
            fn(mp, tmp_path, _Cap())
        except TypeError:
            fn(mp, tmp_path)
        mp.restore()
        config_dir_mod.set_local_config_mode(False)
        print(f"OK {name}")

    def _main():
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            for name, fn in sorted(globals().items()):
                if name.startswith("test_") and callable(fn):
                    _run_one(name, fn, Path(d))

    if __name__ == "__main__":
        _main()
