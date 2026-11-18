"""
Tests for the ToolsRegistry class (janito.tooling.tools_registry).

The registry's state intentionally lives at module level (AVAILABLE_TOOLS /
_tools_initialized / _loaded_toolsets / _skills_enabled) because the existing
tests monkeypatch those names directly.  These tests exercise the class API
over that state, isolating each test by monkeypatching the module state and
the discovery hooks (so no real filesystem scan ever runs).
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.tooling.tools_registry as tools_registry
from janito.tooling.tools_registry import ToolsRegistry


def _fake_tool(name, permissions="", hint=""):
    def fake(**kwargs):
        return {"success": True}

    fake.__name__ = name
    fake._tool_permissions = permissions
    fake._tool_system_prompt_hint = hint
    return fake


def _fresh_registry(monkeypatch, tools=None, skills_enabled=True):
    """Return a ToolsRegistry over isolated module state (no real discovery)."""
    tools = tools if tools is not None else {}
    monkeypatch.setattr(tools_registry, "AVAILABLE_TOOLS", dict(tools))
    monkeypatch.setattr(tools_registry, "_tools_initialized", False)
    monkeypatch.setattr(
        tools_registry,
        "_loaded_toolsets",
        set(tools_registry.AUTOLOAD_TOOLSETS),
    )
    monkeypatch.setattr(tools_registry, "_skills_enabled", skills_enabled)
    monkeypatch.setattr(tools_registry, "_tools_loading_enabled", True)
    monkeypatch.setattr(tools_registry, "_disabled_toolsets", set())
    monkeypatch.setattr(tools_registry, "discover_toolsets", lambda names: {})
    monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: {})
    monkeypatch.setattr(tools_registry, "get_skills_advertisement", lambda: "")
    return ToolsRegistry()


if pytest is not None:

    def test_ensure_initialized_runs_discovery_once(monkeypatch):
        calls = {"n": 0}

        def fake_discover(names):
            calls["n"] += 1
            return {"FakeTool": _fake_tool("FakeTool", "r")}

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)
        monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: {})
        monkeypatch.setattr(tools_registry, "AVAILABLE_TOOLS", {})
        monkeypatch.setattr(tools_registry, "_tools_initialized", False)
        monkeypatch.setattr(tools_registry, "_skills_enabled", False)

        registry = ToolsRegistry()
        registry.ensure_initialized()
        registry.ensure_initialized()
        assert calls["n"] == 1
        assert "FakeTool" in tools_registry.AVAILABLE_TOOLS

    def test_all_tools_and_schemas_and_permissions(monkeypatch):
        registry = _fresh_registry(
            monkeypatch,
            {
                "ReadFile": _fake_tool("ReadFile", "r"),
                "CreateFile": _fake_tool("CreateFile", "w"),
            },
        )
        assert set(registry.all_tools()) == {"ReadFile", "CreateFile"}
        schemas = registry.all_schemas()
        assert {s["function"]["name"] for s in schemas} == {"ReadFile", "CreateFile"}
        assert registry.all_permissions() == {"ReadFile": "r", "CreateFile": "w"}

    def test_get_schema_permissions(monkeypatch):
        registry = _fresh_registry(monkeypatch, {"ReadFile": _fake_tool("ReadFile", "r")})
        assert registry.get("ReadFile") is not None
        assert registry.schema("ReadFile")["function"]["name"] == "ReadFile"
        assert registry.permissions("ReadFile") == "r"
        with pytest.raises(KeyError):
            registry.get("Missing")
        with pytest.raises(KeyError):
            registry.schema("Missing")
        with pytest.raises(KeyError):
            registry.permissions("Missing")

    def test_add_toolset_loads_new_tools_once(monkeypatch):
        calls = {"n": 0}
        registry = _fresh_registry(monkeypatch, {})

        def fake_discover(names):
            calls["n"] += 1
            return {"ExtraTool": _fake_tool("ExtraTool", "r")} if "extra" in names else {}

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)

        assert registry.add_toolset("extra") is True
        assert "ExtraTool" in registry.all_tools()
        # Discovery ran once for the autoload toolsets and once for "extra".
        assert calls["n"] == 2
        # Already loaded: second call returns False without re-discovering.
        assert registry.add_toolset("extra") is False
        assert calls["n"] == 2

    def test_add_toolset_no_tools_returns_false(monkeypatch):
        registry = _fresh_registry(monkeypatch, {})
        monkeypatch.setattr(tools_registry, "discover_toolsets", lambda names: {})
        # discover_toolsets returns {} -> nothing added -> False.
        assert registry.add_toolset("empty_toolset") is False
        assert "empty_toolset" in tools_registry._loaded_toolsets

    def test_enable_disable_skills(monkeypatch):
        skill_tools = {
            "load_skill": _fake_tool("load_skill"),
            "read_skill_resource": _fake_tool("read_skill_resource"),
        }
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=True)
        monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: skill_tools)
        monkeypatch.setattr(tools_registry, "get_skills_advertisement", lambda: "## Available Skills")

        registry.ensure_initialized()
        assert "load_skill" in registry.all_tools()
        assert "## Available Skills" in registry.skills_section()

        registry.disable_skills()
        assert "load_skill" not in registry.all_tools()
        assert registry.skills_section() == ""

        registry.enable_skills()
        assert "load_skill" in registry.all_tools()

    def test_disable_tools_loading_skips_autoload_keeps_skills(monkeypatch):
        """--no-tools: autoload toolsets are skipped, skill tools stay loaded."""
        skill_tools = {
            "load_skill": _fake_tool("load_skill"),
            "read_skill_resource": _fake_tool("read_skill_resource"),
        }
        calls = {"n": 0}
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=True)
        monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: skill_tools)

        def fake_discover(names):
            calls["n"] += 1
            return {"ReadFile": _fake_tool("ReadFile", "r")}

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)
        monkeypatch.setattr(tools_registry, "_tools_loading_enabled", False)

        registry.ensure_initialized()

        # Autoload discovery never ran; only the skill tools are available.
        assert calls["n"] == 0
        assert set(registry.all_tools()) == {"load_skill", "read_skill_resource"}

    def test_disable_tools_loading_makes_add_toolset_noop(monkeypatch):
        calls = {"n": 0}
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=False)

        def fake_discover(names):
            calls["n"] += 1
            return {"ExtraTool": _fake_tool("ExtraTool", "r")}

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)
        monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: {})
        monkeypatch.setattr(tools_registry, "_tools_loading_enabled", False)

        # add_toolset is a no-op when loading is disabled...
        assert registry.add_toolset("extra") is False
        # ...and it must not have triggered discovery for the autoload
        # toolsets either (the early return skips ensure_initialized).
        assert calls["n"] == 0
        assert "ExtraTool" not in registry.all_tools()

    def test_disable_toolset_filters_autoload_discovery(monkeypatch):
        """--no-tasks: the disabled toolset is left out of autoload discovery."""
        skill_tools = {
            "load_skill": _fake_tool("load_skill"),
            "read_skill_resource": _fake_tool("read_skill_resource"),
        }
        discovered = {"names": []}
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=True)
        monkeypatch.setattr(tools_registry, "get_skills_tools", lambda: skill_tools)
        monkeypatch.setattr(tools_registry, "_disabled_toolsets", {"tasks"})

        def fake_discover(names):
            discovered["names"] = list(names)
            tools = {"ReadFile": _fake_tool("ReadFile", "r")}
            if "tasks" in names:
                tools.update(
                    {
                        "StartTask": _fake_tool("StartTask", "x"),
                        "StopTask": _fake_tool("StopTask", "x"),
                        "WaitForTask": _fake_tool("WaitForTask", "x"),
                    }
                )
            return tools

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)

        registry.ensure_initialized()

        # The disabled toolset was filtered out of the autoload list.
        assert "tasks" not in discovered["names"]
        assert discovered["names"] == ["files", "system", "net"]
        # The other toolsets and the skill tools still loaded.
        all_names = set(registry.all_tools())
        assert "ReadFile" in all_names
        assert {"load_skill", "read_skill_resource"} <= all_names
        assert not {"StartTask", "StopTask", "WaitForTask"} & all_names

    def test_disable_toolset_makes_add_toolset_noop(monkeypatch):
        """--no-tasks: add_toolset() refuses the disabled toolset."""
        calls = {"n": 0}
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=False)
        # "tasks" is not in _loaded_toolsets (fresh state), so the disabled
        # check -- not the already-loaded check -- must reject it.
        monkeypatch.setattr(
            tools_registry,
            "_loaded_toolsets",
            {"files", "system", "net"},
        )
        monkeypatch.setattr(tools_registry, "_disabled_toolsets", {"tasks"})

        def fake_discover(names):
            calls["n"] += 1
            return {"ExtraTool": _fake_tool("ExtraTool", "r")}

        monkeypatch.setattr(tools_registry, "discover_toolsets", fake_discover)

        assert registry.add_toolset("tasks") is False
        # The early return skips ensure_initialized -> no discovery at all.
        assert calls["n"] == 0
        assert "tasks" not in registry.all_tools()
        # A non-disabled toolset still loads normally.
        assert registry.add_toolset("extra") is True
        assert "ExtraTool" in registry.all_tools()

    def test_disable_toolset_and_disabled_toolsets_report(monkeypatch):
        """disable_toolset() registers the name; disabled_toolsets() copies it."""
        _fresh_registry(monkeypatch, {}, skills_enabled=False)
        registry = ToolsRegistry()
        assert registry.disabled_toolsets() == set()
        registry.disable_toolset("tasks")
        assert registry.disabled_toolsets() == {"tasks"}
        # The returned set is a copy: mutating it must not affect the registry.
        registry.disabled_toolsets().add("files")
        assert registry.disabled_toolsets() == {"tasks"}

    def test_register_plugin_tools_gated_by_no_tools(monkeypatch):
        """Plugin tools are NOT registered with --no-tools."""
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=False)
        monkeypatch.setattr(tools_registry, "_tools_loading_enabled", False)

        plugin_tool = _fake_tool("PluginTool", "r")
        registry.register_plugin_tools({"PluginTool": plugin_tool})

        assert "PluginTool" not in registry.all_tools()

    def test_tools_loading_flag_module_delegators(monkeypatch):
        """Module-level disable_tools_loading / tools_loading_enabled."""
        _fresh_registry(monkeypatch, {})
        assert tools_registry.tools_loading_enabled() is True
        tools_registry.disable_tools_loading()
        assert tools_registry.tools_loading_enabled() is False

    def test_skills_section_empty_when_disabled(monkeypatch):
        registry = _fresh_registry(monkeypatch, {}, skills_enabled=False)
        assert registry.skills_section() == ""

    def test_system_prompt_hints_collects_declared_hints(monkeypatch):
        """Only tools declaring a non-empty hint are returned, sorted by name."""
        registry = _fresh_registry(
            monkeypatch,
            {
                "Zeta": _fake_tool("Zeta", "r", "zeta hint"),
                "Alpha": _fake_tool("Alpha", "r", "alpha hint"),
                "NoHint": _fake_tool("NoHint", "r"),
                "BlankHint": _fake_tool("BlankHint", "r", "  \n "),
            },
        )

        assert registry.system_prompt_hints() == [
            ("Alpha", "alpha hint"),
            ("Zeta", "zeta hint"),
        ]

    def test_make_class_tool_propagates_system_prompt_hint():
        """Discovery copies `system_prompt_hint` onto the wrapper callable."""
        from janito.tooling.base_tool import BaseTool
        from janito.tooling.decorator import tool
        from janito.tooling.discovery import _make_class_tool

        @tool(permissions="x")
        class Hinted(BaseTool):
            """Tool with a hint."""

            system_prompt_hint = "prefer openpyxl for xlsx"

            def run(self, code: str) -> dict:
                return {"success": True}

        @tool(permissions="r")
        class Unhinted(BaseTool):
            """Tool without a hint."""

            def run(self, path: str) -> dict:
                return {"success": True}

        assert _make_class_tool(Hinted)._tool_system_prompt_hint == "prefer openpyxl for xlsx"
        # BaseTool defaults the attribute to empty, so tools opt in only by
        # declaring it.
        assert _make_class_tool(Unhinted)._tool_system_prompt_hint == ""

    def test_base_tool_hint_defaults_to_empty():
        from janito.tooling.base_tool import BaseTool

        assert BaseTool.system_prompt_hint == ""

    def test_module_functions_delegate_to_registry(monkeypatch):
        """The module-level functions behave identically to the class API."""
        registry = _fresh_registry(monkeypatch, {"ReadFile": _fake_tool("ReadFile", "r")})
        assert tools_registry.get_all_tools() == registry.all_tools()
        assert tools_registry.get_all_tool_schemas() == registry.all_schemas()
        assert tools_registry.get_all_tool_permissions() == registry.all_permissions()
        assert tools_registry.get_tool_by_name("ReadFile") == registry.get("ReadFile")
        assert tools_registry.get_tool_permissions("ReadFile") == registry.permissions("ReadFile")

    def test_module_singleton_is_a_registry():
        assert isinstance(tools_registry._registry, ToolsRegistry)

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
