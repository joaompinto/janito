"""
Tests for the system prompt management in ``janito/system_prompt.py``.

The system prompt is assembled from named sections via
:class:`SysPromptManager`.  These tests cover the manager's section operations
(add/update/delete, label handling), rendering, and the default prompt
resolved by ``default_system_prompt_manager`` (built-in base prompt read from
the packaged ``janito/system-prompt.txt`` resource + skills + optional
``AGENTS.md``).
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.tooling.tools_registry as tools_registry_mod
from janito.system_labels import LABEL_BUILTIN
from janito.system_prompt import (
    SECTION_START,
    SYSTEM_PROMPT_MANAGER,
    TOOLS_HEADER,
    Section,
    SysPromptManager,
    apply_start_section,
    default_system_prompt_manager,
    get_builtin_system_prompt,
    sync_default_sections,
)

SKILLS_SECTION = "## Available Skills\n(fake skills section)"


def _patch_skills_section(monkeypatch):
    """Patch the skills section so the test is isolated from the tool registry."""
    monkeypatch.setattr(tools_registry_mod, "get_skills_section", lambda: SKILLS_SECTION)


def _patch_tool_hints(monkeypatch, hints):
    """Patch the tools' system prompt hints (the ``tools`` section source).

    ``hints`` is the list of ``(tool name, hint)`` pairs the registry would
    return; ``[]`` means no tool contributes anything.
    """
    monkeypatch.setattr(tools_registry_mod, "get_system_prompt_hints", lambda: list(hints))


@pytest.fixture(autouse=True)
def _no_tool_hints(monkeypatch):
    """Keep the real tool hints out of the default prompt by default.

    Tests that exercise the ``tools`` section re-patch
    ``get_system_prompt_hints`` (last monkeypatch wins).
    """
    _patch_tool_hints(monkeypatch, [])


# --- SysPromptManager unit tests -------------------------------------------


def test_init_seeds_start_section():
    """__init__ stores ('start', start_prompt) as the first section."""
    manager = SysPromptManager("start text")
    assert list(manager.get_all_sections()) == [Section(SECTION_START, "start text")]


def test_init_accepts_start_label():
    """__init__ stores the start section with its optional label."""
    manager = SysPromptManager("start text", start_label=LABEL_BUILTIN)
    assert list(manager.get_all_sections()) == [Section(SECTION_START, "start text", LABEL_BUILTIN)]


def test_add_section_appends():
    """add_section appends the (name, text) pair after the start section."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")
    assert list(manager.get_all_sections()) == [
        Section(SECTION_START, "start text"),
        Section("extra", "extra text"),
    ]


def test_add_section_with_label():
    """add_section stores the optional label."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text", label="(config) ~/base.md")
    assert list(manager.get_all_sections())[1] == Section("extra", "extra text", "(config) ~/base.md")


def test_add_section_duplicate_name_raises():
    """add_section raises ValueError when the name is already used."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")
    with pytest.raises(ValueError):
        manager.add_section("extra", "other text")


def test_add_section_at_index_inserts_in_place():
    """add_section(index=...) inserts at the given position."""
    manager = SysPromptManager("start text")
    manager.add_section("first", "first text")
    manager.add_section("last", "last text")
    manager.add_section("middle", "middle text", index=2)
    assert [section.name for section in manager.get_all_sections()] == ["start", "first", "middle", "last"]


def test_add_section_index_clamped_keeps_start_first():
    """An index below 1 never displaces the start section."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text", index=0)
    assert [section.name for section in manager.get_all_sections()] == ["start", "extra"]


def test_add_section_duplicate_start_name_raises():
    """'start' is reserved; adding a second section named 'start' raises."""
    manager = SysPromptManager("start text")
    with pytest.raises(ValueError):
        manager.add_section(SECTION_START, "other start")


def test_update_section_replaces_text():
    """update_section replaces the text of an existing section."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")
    manager.update_section("extra", "updated text")
    assert list(manager.get_all_sections())[1] == Section("extra", "updated text")


def test_update_section_preserves_label():
    """update_section keeps the section's label unchanged."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text", label="(config) ~/base.md")
    manager.update_section("extra", "updated text")
    assert list(manager.get_all_sections())[1] == Section("extra", "updated text", "(config) ~/base.md")


def test_update_section_missing_raises():
    """update_section raises ValueError for an unknown section."""
    manager = SysPromptManager("start text")
    with pytest.raises(ValueError):
        manager.update_section("missing", "text")


def test_del_section_removes():
    """del_section removes a non-start section."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")
    manager.del_section("extra")
    assert list(manager.get_all_sections()) == [Section(SECTION_START, "start text")]


def test_del_start_section_raises():
    """del_section raises ValueError when asked to delete 'start'."""
    manager = SysPromptManager("start text")
    with pytest.raises(ValueError):
        manager.del_section(SECTION_START)


def test_del_missing_section_raises():
    """del_section raises ValueError for an unknown section."""
    manager = SysPromptManager("start text")
    with pytest.raises(ValueError):
        manager.del_section("missing")


def test_render_appends_newline_after_each_section():
    """render joins sections with a trailing newline per section."""
    manager = SysPromptManager("first")
    manager.add_section("second", "second text")
    assert manager.render() == "first\nsecond text\n"


def test_render_without_sections_beyond_start():
    """A manager with only the start section renders start + newline."""
    manager = SysPromptManager("only start")
    assert manager.render() == "only start\n"


def test_get_all_sections_returns_iterator():
    """get_all_sections returns an iterator over Section objects."""
    manager = SysPromptManager("start text")
    iterator = manager.get_all_sections()
    assert iter(iterator) is iterator
    assert list(iterator) == [Section(SECTION_START, "start text")]


# --- default prompt building -----------------------------------------------


def test_system_prompt_content():
    """get_builtin_system_prompt returns the packaged base prompt text."""
    prompt = get_builtin_system_prompt()
    assert ("Explore the current directory for potential content related to the question") in prompt
    assert not prompt.startswith("\n")
    assert not prompt.endswith("\n")


def test_builtin_prompt_encourages_parallel_starttask():
    """Built-in prompt guides parallel background tasks via StartTask (#107)."""
    prompt = get_builtin_system_prompt()
    assert "StartTask" in prompt
    assert "parallel" in prompt.lower()


def test_builtin_prompt_is_packaged_resource():
    """The built-in prompt ships as janito/system-prompt.txt (package data)."""
    from importlib.resources import files

    resource = files("janito").joinpath("system-prompt.txt")
    assert resource.is_file()
    from janito.config_loaders import DEFAULT_ROLE

    assert get_builtin_system_prompt(DEFAULT_ROLE) == resource.read_text(encoding="utf-8").strip().replace(
        "{role}", DEFAULT_ROLE
    )


def test_prompt_without_agents_md(monkeypatch, tmp_path):
    """No AGENTS.md -> prompt is base + skills, one newline-separated section each."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    manager = SysPromptManager(get_builtin_system_prompt())
    prompt = sync_default_sections(manager).render()

    assert prompt == get_builtin_system_prompt() + "\n" + SKILLS_SECTION + "\n"
    assert "AGENTS.md" not in prompt


def test_prompt_with_agents_md(monkeypatch, tmp_path):
    """An AGENTS.md in cwd appears as its own section in the prompt."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    agents_content = "Always answer in rhyming couplets."
    (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    manager = SysPromptManager(get_builtin_system_prompt())
    prompt = sync_default_sections(manager).render()

    assert prompt == (get_builtin_system_prompt() + "\n" + SKILLS_SECTION + "\n" + agents_content + "\n")


def test_prompt_with_empty_agents_md(monkeypatch, tmp_path):
    """An empty (or whitespace-only) AGENTS.md is ignored."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "AGENTS.md").write_text("   \n\n  ", encoding="utf-8")

    manager = SysPromptManager(get_builtin_system_prompt())
    prompt = sync_default_sections(manager).render()

    assert prompt == get_builtin_system_prompt() + "\n" + SKILLS_SECTION + "\n"
    assert "AGENTS.md" not in prompt


def test_agents_md_in_a_different_directory_is_ignored(monkeypatch, tmp_path):
    """Only an AGENTS.md in the *current* directory is picked up."""
    _patch_skills_section(monkeypatch)

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "AGENTS.md").write_text("should not appear", encoding="utf-8")

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    manager = SysPromptManager(get_builtin_system_prompt())
    prompt = sync_default_sections(manager).render()

    assert "should not appear" not in prompt
    assert "AGENTS.md" not in prompt


def test_sections_without_agents_md(monkeypatch, tmp_path):
    """No AGENTS.md -> sections are (start, skills) in order."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    manager = SysPromptManager(get_builtin_system_prompt())
    sections = list(sync_default_sections(manager).get_all_sections())

    assert [section.name for section in sections] == ["start", "skills"]
    assert sections[0] == Section("start", get_builtin_system_prompt())
    assert sections[1] == Section("skills", SKILLS_SECTION)


def test_sections_with_agents_md(monkeypatch, tmp_path):
    """An AGENTS.md in cwd adds an agents.md section after the skills one."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    agents_content = "Always answer in rhyming couplets."
    (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    manager = SysPromptManager(get_builtin_system_prompt())
    sections = list(sync_default_sections(manager).get_all_sections())

    assert [section.name for section in sections] == ["start", "skills", "agents.md"]
    assert sections[2].name == "agents.md"
    assert agents_content in sections[2].text


def test_sections_concatenation_reproduces_full_prompt(monkeypatch, tmp_path):
    """Rendering equals start text + newline + each section text + newline."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    agents_content = "agent line"
    (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    manager = SysPromptManager(get_builtin_system_prompt())
    sections = list(sync_default_sections(manager).get_all_sections())

    assert manager.render() == "".join(section.text + "\n" for section in sections)


def test_sync_removes_sections_that_no_longer_apply(monkeypatch, tmp_path):
    """When AGENTS.md disappears, the agents.md section is removed."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    manager = SysPromptManager(get_builtin_system_prompt())
    (tmp_path / "AGENTS.md").write_text("agent line", encoding="utf-8")
    assert [section.name for section in sync_default_sections(manager).get_all_sections()] == [
        "start",
        "skills",
        "agents.md",
    ]

    (tmp_path / "AGENTS.md").unlink()
    assert [section.name for section in sync_default_sections(manager).get_all_sections()] == ["start", "skills"]


# --- tool-contributed hints (tools header + tools:<Toolname> sections) -----


def test_tools_sections_built_from_hints(monkeypatch, tmp_path):
    """The tools section is header-only; each hint gets its own tools:<Toolname> section."""
    _patch_skills_section(monkeypatch)
    _patch_tool_hints(
        monkeypatch,
        [("ReadFile", "read large files with max_lines"), ("RunPythonCode", "read xlsx with openpyxl")],
    )
    monkeypatch.chdir(tmp_path)

    manager = sync_default_sections(SysPromptManager("start text"))
    sections = {section.name: section for section in manager.get_all_sections()}

    assert sections["tools"].text == TOOLS_HEADER
    assert sections["tools:ReadFile"].text == "read large files with max_lines"
    assert sections["tools:RunPythonCode"].text == "read xlsx with openpyxl"


def test_tools_section_absent_without_hints(monkeypatch, tmp_path):
    """No tool contributes a hint -> no tools header or per-tool sections."""
    _patch_skills_section(monkeypatch)
    _patch_tool_hints(monkeypatch, [])
    monkeypatch.chdir(tmp_path)

    manager = sync_default_sections(SysPromptManager("start text"))

    assert [section.name for section in manager.get_all_sections()] == ["start", "skills"]
    assert TOOLS_HEADER not in manager.render()


def test_tools_sections_order_and_render(monkeypatch, tmp_path):
    """The header and per-tool sections come after start, before skills/agents.md."""
    _patch_skills_section(monkeypatch)
    _patch_tool_hints(monkeypatch, [("RunPythonCode", "read xlsx with openpyxl")])
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("agent line", encoding="utf-8")

    manager = sync_default_sections(SysPromptManager("start text"))

    assert [section.name for section in manager.get_all_sections()] == [
        "start",
        "tools",
        "tools:RunPythonCode",
        "skills",
        "agents.md",
    ]
    assert manager.render() == (
        "start text\n" + TOOLS_HEADER + "\n" + "read xlsx with openpyxl\n" + SKILLS_SECTION + "\nagent line\n"
    )


def test_tools_sections_removed_when_hints_disappear(monkeypatch, tmp_path):
    """Re-syncing with no hints drops the header and per-tool sections."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    _patch_tool_hints(monkeypatch, [("RunPythonCode", "read docx with python-docx")])
    manager = sync_default_sections(SysPromptManager("start text"))
    assert "tools:RunPythonCode" in [section.name for section in manager.get_all_sections()]

    _patch_tool_hints(monkeypatch, [])
    manager = sync_default_sections(manager)
    assert [section.name for section in manager.get_all_sections()] == ["start", "skills"]


def test_tools_sections_resync_keeps_registry_order(monkeypatch, tmp_path):
    """Hints appearing/disappearing between syncs keep the sorted per-tool order."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    _patch_tool_hints(monkeypatch, [("Zebra", "z hint"), ("Middle", "m hint")])
    manager = sync_default_sections(SysPromptManager("start text"))

    # A new tool sorts before the existing ones; another one disappears.
    _patch_tool_hints(monkeypatch, [("Alpha", "a hint"), ("Zebra", "z hint updated")])
    manager = sync_default_sections(manager)

    names = [section.name for section in manager.get_all_sections()]
    assert names == ["start", "tools", "tools:Alpha", "tools:Zebra", "skills"]
    sections = {section.name: section for section in manager.get_all_sections()}
    assert sections["tools:Zebra"].text == "z hint updated"


def test_tools_sections_inserted_before_plugin_sections(monkeypatch, tmp_path):
    """New per-tool sections land after the tools header, not after plugins."""
    _patch_skills_section(monkeypatch)
    monkeypatch.chdir(tmp_path)

    manager = SysPromptManager("start text")
    manager.add_section("plugins:testplugin", "plugin text")
    _patch_tool_hints(monkeypatch, [("RunPythonCode", "read xlsx with openpyxl")])
    manager = sync_default_sections(manager)

    names = [section.name for section in manager.get_all_sections()]
    assert names.index("tools") == 1
    assert names.index("tools:RunPythonCode") == 2
    assert names.index("tools:RunPythonCode") < names.index("plugins:testplugin")


def test_get_tools_section_none_without_hints(monkeypatch):
    """get_tools_section returns None when the registry has no hints."""
    _patch_tool_hints(monkeypatch, [])
    from janito.system_prompt import get_tools_section

    assert get_tools_section() is None


def test_get_tools_section_header_only_with_hints(monkeypatch):
    """get_tools_section returns just the heading when hints exist."""
    _patch_tool_hints(monkeypatch, [("RunPythonCode", "read xlsx with openpyxl")])
    from janito.system_prompt import get_tools_section

    assert get_tools_section() == TOOLS_HEADER


def test_run_python_code_advertises_office_libraries():
    """RunPythonCode hints at libraries for Word/Excel/PDF (issue-driven)."""
    from janito.tools.system.run_python_code import RunPythonCode

    hint = RunPythonCode.system_prompt_hint
    assert "python-docx" in hint
    assert "openpyxl" in hint


# --- configured start section (system-prompt / system-prompt-file) ---------


def _patch_config_start(monkeypatch, start, label=None):
    """Patch load_system_prompt_start so tests never touch the real config."""
    import janito.config_loaders as config_loaders_mod

    monkeypatch.setattr(config_loaders_mod, "load_system_prompt_start", lambda: (start, label))


def test_apply_start_section_none_returns_same_manager():
    """start_prompt=None returns the manager unchanged (no copy)."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")
    assert apply_start_section(manager, None) is manager


def test_apply_start_section_replaces_start_without_mutating_original():
    """A non-None start builds a fresh manager; the original is untouched."""
    manager = SysPromptManager("start text")
    manager.add_section("extra", "extra text")

    copy = apply_start_section(manager, "configured start")

    assert copy is not manager
    assert list(copy.get_all_sections()) == [
        Section(SECTION_START, "configured start"),
        Section("extra", "extra text"),
    ]
    # The original manager keeps its base start (the shared singleton must
    # never be mutated by the config application).
    assert list(manager.get_all_sections()) == [
        Section(SECTION_START, "start text"),
        Section("extra", "extra text"),
    ]


def test_apply_start_section_sets_start_label():
    """apply_start_section sets the start section's display label."""
    manager = SysPromptManager("start text")
    copy = apply_start_section(manager, "configured start", start_label=LABEL_BUILTIN)
    assert list(copy.get_all_sections()) == [Section(SECTION_START, "configured start", LABEL_BUILTIN)]


def test_apply_start_section_copies_section_labels():
    """The fresh copy keeps the labels of the non-start sections."""
    manager = SysPromptManager("start text")
    manager.add_section("plugins:testplugin", "plugin text", label="plugins:testplugin")
    copy = apply_start_section(manager, "configured start", start_label=LABEL_BUILTIN)
    assert list(copy.get_all_sections()) == [
        Section(SECTION_START, "configured start", LABEL_BUILTIN),
        Section("plugins:testplugin", "plugin text", "plugins:testplugin"),
    ]


def test_default_system_prompt_manager_applies_config_start(monkeypatch, tmp_path):
    """The configured start replaces the base prompt, skills/agents.md stay."""
    _patch_skills_section(monkeypatch)
    _patch_config_start(monkeypatch, "configured start text")
    monkeypatch.chdir(tmp_path)

    manager = default_system_prompt_manager()
    sections = list(manager.get_all_sections())

    assert sections[0] == Section(SECTION_START, "configured start text")
    assert [section.name for section in sections] == ["start", "skills"]
    assert "configured start text" in manager.render()
    assert SKILLS_SECTION in manager.render()
    assert get_builtin_system_prompt() not in manager.render()


def test_default_system_prompt_manager_without_config_uses_base(monkeypatch, tmp_path):
    """No configured start -> the built-in base prompt is used."""
    _patch_skills_section(monkeypatch)
    _patch_config_start(monkeypatch, None)
    monkeypatch.chdir(tmp_path)

    manager = default_system_prompt_manager()
    sections = list(manager.get_all_sections())

    assert sections[0] == Section(SECTION_START, get_builtin_system_prompt(), LABEL_BUILTIN)
    assert [section.name for section in sections] == ["start", "skills"]


def test_default_system_prompt_manager_uses_config_label(monkeypatch, tmp_path):
    """The configured start carries the loader's (config) ... label."""
    _patch_skills_section(monkeypatch)
    _patch_config_start(monkeypatch, "configured start text", label="(config) ~/base-prompt.md")
    monkeypatch.chdir(tmp_path)

    manager = default_system_prompt_manager()
    sections = list(manager.get_all_sections())

    assert sections[0] == Section(SECTION_START, "configured start text", "(config) ~/base-prompt.md")


def test_default_system_prompt_manager_preserves_plugin_sections(monkeypatch, tmp_path):
    """The config start copy keeps plugin sections registered on the shared manager."""
    _patch_skills_section(monkeypatch)
    _patch_config_start(monkeypatch, "configured start text")
    monkeypatch.chdir(tmp_path)

    SYSTEM_PROMPT_MANAGER.add_section("plugins:testplugin", "plugin section text")
    try:
        manager = default_system_prompt_manager()
        sections = {section.name: section for section in manager.get_all_sections()}
        assert sections["start"].text == "configured start text"
        assert sections["plugins:testplugin"].text == "plugin section text"
        # The shared manager's start stays at its lazy empty seed: the
        # config application (and the built-in resource prompt) is only ever
        # applied to a per-call copy, never to the shared singleton.
        shared_sections = {section.name: section for section in SYSTEM_PROMPT_MANAGER.get_all_sections()}
        assert shared_sections["start"].text == ""
        assert shared_sections["plugins:testplugin"].text == "plugin section text"
    finally:
        SYSTEM_PROMPT_MANAGER.del_section("plugins:testplugin")


# --- load_system_prompt_start labels (issue #86) ---------------------------


def _patch_config_store(monkeypatch, getter, config_path=None):
    """Patch config_store.get_config_value (and get_config_path) for the loader."""
    import janito.config_store as config_store_mod

    monkeypatch.setattr(config_store_mod, "get_config_value", getter)
    if config_path is not None:
        monkeypatch.setattr(config_store_mod, "get_config_path", lambda: config_path)


def test_load_system_prompt_start_file_label(monkeypatch, tmp_path):
    """system-prompt-file -> (content, '(config) <value>')."""
    import janito.config_loaders as config_loaders_mod

    prompt_file = tmp_path / "base.md"
    prompt_file.write_text("start text", encoding="utf-8")

    def getter(key):
        return str(prompt_file) if key == "system-prompt-file" else None

    _patch_config_store(monkeypatch, getter)
    text, label = config_loaders_mod.load_system_prompt_start()
    assert text == "start text"
    assert label == f"(config) {prompt_file}"


def test_load_system_prompt_start_empty_file_falls_back(monkeypatch, tmp_path):
    """An empty system-prompt-file still yields the (config) label with None text."""
    import janito.config_loaders as config_loaders_mod

    prompt_file = tmp_path / "empty.md"
    prompt_file.write_text("   \n", encoding="utf-8")

    def getter(key):
        return str(prompt_file) if key == "system-prompt-file" else None

    _patch_config_store(monkeypatch, getter)
    assert config_loaders_mod.load_system_prompt_start() == (
        None,
        f"(config) {prompt_file}",
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Windows path/console compat")
def test_load_system_prompt_start_literal_label(monkeypatch, tmp_path):
    """system-prompt -> (literal, '(config) <config-file>:system-prompt')."""
    import janito.config_loaders as config_loaders_mod

    config_file = tmp_path / "config.json"

    def getter(key):
        return "my start" if key == "system-prompt" else None

    _patch_config_store(monkeypatch, getter, config_path=config_file)
    text, label = config_loaders_mod.load_system_prompt_start()
    assert text == "my start"
    assert label == f"(config) {config_file}:system-prompt"


def test_load_system_prompt_start_none_when_unset(monkeypatch):
    """Neither key set -> (None, None) (the built-in base prompt applies)."""
    import janito.config_loaders as config_loaders_mod

    _patch_config_store(monkeypatch, lambda key: None)
    assert config_loaders_mod.load_system_prompt_start() == (None, None)


def test_display_config_path_shortens_home(monkeypatch):
    """A config file under home is displayed as ~/... (the form users write)."""
    import janito.config_loaders as config_loaders_mod

    home = Path.home()
    assert config_loaders_mod._display_config_path(home / ".janito" / "config.json") == "~/.janito/config.json"


if __name__ == "__main__":  # pragma: no cover
    if pytest is not None:
        raise SystemExit(pytest.main([__file__, "-v"]))
