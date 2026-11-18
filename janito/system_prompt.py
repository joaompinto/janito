"""System prompt assembly.

The system prompt is an ordered list of named :class:`Section` objects
(``name``, ``text`` and an optional ``label``) owned by a
:class:`SysPromptManager`.  The shared manager (:data:`SYSTEM_PROMPT_MANAGER`)
is seeded with an empty ``start`` section; the built-in base prompt is read
lazily from the packaged resource ``janito/system-prompt.txt`` by
:func:`get_builtin_system_prompt` when the default prompt is resolved
(:func:`default_system_prompt_manager`).  :func:`sync_default_sections` keeps
the ``tools``, ``skills`` and ``agents.md`` sections in sync with the tool
registry (tools advertise usage hints through their ``system_prompt_hint``
class attribute) and the cwd ``AGENTS.md``; plugins register ``plugins:<name>``
sections at load time (see ``janito.plugin_manager``).

Every consumer (``janito.cli.session_setup.SessionSetup``, the shell ``/prompt``
command, ``--show-system-prompt`` and the web backend) manipulates the prompt
through this shared manager so the sections stay consistent.  The configured
``start`` section (``system-prompt`` / ``system-prompt-file`` config keys) is
applied **per call** through :func:`default_system_prompt_manager`, which
builds a fresh manager via :func:`apply_start_section` so the shared
singleton is never mutated (a config start would otherwise leak across
sessions in web mode).

Each section carries a ``label`` describing where it came from (issue #86):
the ``start`` section is labelled :data:`LABEL_BUILTIN` for the built-in
resource, :data:`LABEL_CLI` for a ``-S`` prompt, or a ``(config) ...`` label
for the configured keys (see :func:`janito.config_loaders.load_system_prompt_start`).
The display paths (``/prompt``, ``--show-system-prompt``) show the label when
set and fall back to the section name otherwise.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files

from .system_labels import LABEL_BUILTIN

# The packaged resource holding the built-in base prompt (the ``start``
# section used when no ``system-prompt`` / ``system-prompt-file`` config is
# set).  Installed as package data; read lazily via
# :func:`get_builtin_system_prompt` so importing this module never reads it.
BUILTIN_SYSTEM_PROMPT_RESOURCE = "system-prompt.txt"


def get_builtin_system_prompt(role: str | None = None) -> str:
    """Return the packaged base prompt with the resolved role interpolated.

    The text lives in ``janito/system-prompt.txt`` (installed as package
    data) and is read from the resource location on every call, so the
    default prompt always reflects the shipped file.  The content is
    interpolated only for the ``{role}`` placeholder (CLI, config, default),
    then stripped of leading/trailing whitespace, keeping the ``start`` section
    without its own newlines: :meth:`SysPromptManager.render` appends one
    newline at the end of every section for visual separation.
    """
    from .config_loaders import load_role

    template = files("janito").joinpath(BUILTIN_SYSTEM_PROMPT_RESOURCE).read_text(encoding="utf-8").strip()
    return template.replace("{role}", load_role(role))


# Section names used when building the default prompt.
SECTION_START = "start"
SECTION_TOOLS = "tools"
SECTION_SKILLS = "skills"
SECTION_AGENTS_MD = "agents.md"
SECTION_PLUGINS = "plugins"

# Labels describing where the ``start`` section came from live in the leaf
# :mod:`janito.system_labels` (issue #86 for the labels, #110 for the
# location): ``LABEL_BUILTIN`` marks the packaged base prompt, ``LABEL_CLI``
# a ``-S`` override, and config-sourced starts carry a ``(config) ...`` label
# built by :func:`janito.config_loaders.load_system_prompt_start`.


@dataclass(frozen=True)
class Section:
    """A named system prompt section with an optional display label.

    Attributes:
        name: Unique section name (used by the manager API).
        text: Section content.
        label: Optional display label shown by ``/prompt`` and
            ``--show-system-prompt``; ``None`` falls back to ``name``.
    """

    name: str
    text: str
    label: str | None = None


class SysPromptManager:
    """Manage the system prompt as an ordered list of named sections.

    A section is a :class:`Section` (name, text, optional label).  The
    ``start`` section is created in :meth:`__init__`, always stays first and
    cannot be deleted; every other section name must be unique.
    """

    def __init__(self, start_prompt: str, start_label: str | None = None) -> None:
        self._sections: list[Section] = [Section(SECTION_START, start_prompt, start_label)]

    def add_section(self, name: str, prompt: str, label: str | None = None) -> None:
        """Append a new section.

        Args:
            name: Unique section name.
            prompt: Section text.
            label: Optional display label (``None`` falls back to ``name``).

        Raises:
            ValueError: if a section named ``name`` already exists.
        """
        if self._find(name) is not None:
            raise ValueError(f"a section named {name!r} already exists")
        self._sections.append(Section(name, prompt, label))

    def update_section(self, name: str, prompt: str) -> None:
        """Replace the text of an existing section, keeping its label.

        Args:
            name: Section name.
            prompt: New section text.

        Raises:
            ValueError: if no section named ``name`` exists.
        """
        index = self._find(name)
        if index is None:
            raise ValueError(f"no section named {name!r} to update")
        existing = self._sections[index]
        self._sections[index] = Section(existing.name, prompt, existing.label)

    def del_section(self, name: str) -> None:
        """Remove a section.

        Args:
            name: Section name.

        Raises:
            ValueError: if ``name`` is the ``start`` section or no section
                named ``name`` exists.
        """
        if name == SECTION_START:
            raise ValueError("the 'start' section cannot be deleted")
        index = self._find(name)
        if index is None:
            raise ValueError(f"no section named {name!r} to delete")
        del self._sections[index]

    def render(self) -> str:
        """Assemble the full prompt from all sections.

        A newline is appended at the end of every section to provide a visual
        context separation between sections.
        """
        return "".join(section.text + "\n" for section in self._sections)

    def get_all_sections(self) -> Iterator[Section]:
        """Yield every section as a :class:`Section` (name, text, label)."""
        return iter(self._sections)

    def _find(self, name: str) -> int | None:
        """Return the index of the section named ``name``, or ``None``."""
        for index, section in enumerate(self._sections):
            if section.name == name:
                return index
        return None


# The shared manager used across the app (CLI, shell and web).  The ``start``
# section is seeded empty and only populated lazily by
# :func:`default_system_prompt_manager` (with the built-in resource prompt or
# the configured start), so importing this module never reads
# ``system-prompt.txt`` and the manager is never mutated by session-specific
# starts.
SYSTEM_PROMPT_MANAGER = SysPromptManager("")


def _load_agents_md() -> str | None:
    """Read the cwd ``AGENTS.md``, returning its stripped content.

    Returns ``None`` when the file is missing, unreadable or empty
    (whitespace-only).
    """
    agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
    if os.path.isfile(agents_md_path):
        try:
            with open(agents_md_path, encoding="utf-8") as f:
                agents_content = f.read().strip()
            if agents_content:
                return agents_content
        except OSError:
            pass
    return None


def _set_section(manager: SysPromptManager, name: str, text: str | None) -> None:
    """Set ``name`` on ``manager`` to ``text``; ``None``/empty removes it."""
    if manager._find(name) is not None:
        if text:
            manager.update_section(name, text)
        else:
            manager.del_section(name)
    elif text:
        manager.add_section(name, text)


def get_tools_section() -> str | None:
    """Build the ``tools`` section from the tools' system prompt hints.

    Tools contribute usage guidance through their ``system_prompt_hint``
    class attribute (see :class:`janito.tooling.base_tool.BaseTool`); the
    registry returns the hints of the tools the session may actually use.
    The section renders as a bullet list grouped under a single heading::

        ## Tool Usage Notes
        - RunPythonCode: ...
        - ReadFile: ...

    Returns:
        The section text, or ``None`` when no available tool contributes a
        hint (the section is then omitted from the prompt).
    """
    from .tooling.tools_registry import get_system_prompt_hints

    hints = get_system_prompt_hints()
    if not hints:
        return None
    lines = ["## Tool Usage Notes"]
    lines += [f"- {name}: {hint}" for name, hint in hints]
    return "\n".join(lines)


def sync_default_sections(
    manager: SysPromptManager | None = None,
) -> SysPromptManager:
    """Sync the ``tools``, ``skills`` and ``agents.md`` sections and return the manager.

    The ``tools`` section mirrors the hints contributed by the tools the
    session may use, the ``skills`` section mirrors the current tool registry
    advertisement and the ``agents.md`` section mirrors the cwd ``AGENTS.md``;
    sections that no longer apply are removed.  Uses the shared
    :data:`SYSTEM_PROMPT_MANAGER` when ``manager`` is ``None``.  Plugin
    sections are never touched here; they are registered at load time by
    ``janito.plugin_manager``.
    """
    from .tooling.tools_registry import get_skills_section

    target = manager if manager is not None else SYSTEM_PROMPT_MANAGER

    _set_section(target, SECTION_TOOLS, get_tools_section())
    _set_section(target, SECTION_SKILLS, get_skills_section())
    _set_section(target, SECTION_AGENTS_MD, _load_agents_md())

    return target


def apply_start_section(
    manager: SysPromptManager,
    start_prompt: str | None,
    start_label: str | None = None,
) -> SysPromptManager:
    """Return ``manager`` with the ``start`` section replaced by ``start_prompt``.

    The shared :data:`SYSTEM_PROMPT_MANAGER` is **never** mutated: when
    ``start_prompt`` is ``None`` the given manager is returned as-is;
    otherwise a fresh manager is built with the same sections (labels
    included) and the ``start`` section replaced.  This keeps a
    config-provided start from leaking across sessions (e.g. long-lived web
    mode, where ``effective_system_prompt()`` is called once per session)
    while keeping every other section (``tools``, ``skills``, ``agents.md``,
    ``plugins:...``) unchanged.

    Args:
        manager: The synced manager whose sections are reused.
        start_prompt: The text for the ``start`` section, or ``None`` to
            keep the manager unchanged.
        start_label: The display label for the ``start`` section (e.g.
            :data:`LABEL_BUILTIN` or a ``(config) ...`` label).

    Returns:
        The manager to render: ``manager`` itself when ``start_prompt`` is
        ``None``, otherwise a fresh copy with the ``start`` section replaced.
    """
    if start_prompt is None:
        return manager
    copy = SysPromptManager(start_prompt, start_label=start_label)
    for section in manager.get_all_sections():
        if section.name == SECTION_START:
            continue
        copy.add_section(section.name, section.text, label=section.label)
    return copy


def default_system_prompt_manager(role: str | None = None) -> SysPromptManager:
    """Return the default prompt manager with the configured ``start`` applied.

    ``role`` overrides configuration only for the built-in prompt; custom
    prompt text is never interpolated.

    The ``tools`` / ``skills`` / ``agents.md`` sections are synced as usual; the
    ``start`` section comes from config (``system-prompt-file`` /
    ``system-prompt``, see
    :func:`janito.config_loaders.load_system_prompt_start`) when set, else
    the built-in base prompt, read **lazily** from the packaged
    ``janito/system-prompt.txt`` resource via
    :func:`get_builtin_system_prompt` (one resource read per call, so the
    shipped file is always current and importing ``janito`` never reads it).
    The ``start`` section's display label records the source (issue #86):
    :data:`LABEL_BUILTIN` for the built-in prompt, or the ``(config) ...``
    label returned by the config loader.  Never mutates the shared
    :data:`SYSTEM_PROMPT_MANAGER`.

    This is the single "default prompt" resolver shared by
    :class:`janito.cli.session_setup.SessionSetup` and the display paths
    (``--show-system-prompt``, the shell ``/prompt`` command) so a
    config-provided ``start`` renders consistently everywhere.
    """
    from .config_loaders import load_system_prompt_start

    start, label = load_system_prompt_start()
    if start is None:
        start = get_builtin_system_prompt(role)
        label = LABEL_BUILTIN
    return apply_start_section(sync_default_sections(), start, start_label=label)
