# TOOL.md — Guide to Implementing a New Tool

This document explains how to create a new tool for the **janito** framework.
It covers the architecture, the required specification, and a complete
step-by-step walkthrough with a working example.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Key Source Files](#key-source-files)
3. [The Tool Specification](#the-tool-specification)
4. [Step-by-Step: Create a New Tool](#step-by-step-create-a-new-tool)
5. [Schema Generation (How the LLM Sees Your Tool)](#schema-generation-how-the-llm-sees-your-tool)
6. [The Permission System](#the-permission-system)
7. [The `should_load()` Gate](#the-should_load-gate)
8. [Contributing to the System Prompt](#contributing-to-the-system-prompt)
9. [Progress Reporting](#progress-reporting)
10. [Toolset Organization and Discovery](#toolset-organization-and-discovery)
11. [Return Value Contract](#return-value-contract)
12. [CLI Testing Harness](#cli-testing-harness)
13. [Complete Worked Example](#complete-worked-example)
14. [Checklist Before Submitting](#checklist-before-submitting)

---

## Architecture Overview

```
janito/
├── tooling/                    # Framework / infrastructure
│   ├── base_tool.py            # BaseTool ABC — every tool inherits this
│   ├── decorator.py            # @tool(permissions="…") decorator
│   ├── schema.py               # get_function_schema() — OpenAI-compatible schema gen
│   ├── executor.py             # run_tool() — shared tool-execution core (try/except safety net)
│   ├── tools_registry.py       # Registry: discovery, toolset management, lookup
│   ├── reporter.py             # Standalone progress-report helpers
│   └── path_utils.py           # norm_path() helper
│
├── tools/                      # Actual tool implementations
│   ├── files/                  # "files" toolset  (autoloaded)
│   │   ├── create_file.py
│   │   ├── read_file.py
│   │   └── …
│   ├── system/                 # "system" toolset (autoloaded)
│   │   ├── run_python_code.py
│   │   ├── run_bash_code.py
│   │   └── …
│   ├── net/                    # "net" toolset  (autoloaded)
│   │   ├── get_url.py
│   │   └── headless_browse.py
│   │   └── janitoweb/              # "janitoweb" toolset (web-only, loaded on demand)
│
└── privileges.py               # Runtime privilege flags (-r / -w / -x)
```

**Lifecycle of a tool call:**

1. **Discovery** — `discover_toolsets()` scans a toolset directory, imports
   every `.py` module, and finds classes decorated with `@tool`.
2. **Gating** — each candidate is checked via `should_load()` (environment
   sanity) and `_check_tool_privileges()` (CLI privilege flags).
3. **Wrapping** — the class is wrapped in a callable whose `__name__`,
   `__doc__`, `__signature__`, and `__annotations__` mirror the class and its
   `run()` method. The wrapper is stored in `AVAILABLE_TOOLS[ClassName]`.
4. **Schema export** — `get_function_schema()` reads the wrapper's metadata
   and produces an OpenAI-compatible function-calling schema.
5. **Invocation** — when the LLM calls the tool, the wrapper instantiates
   the class and calls `instance.run(**kwargs)`.

---

## Key Source Files

| File | Purpose |
|---|---|
| `janito/tooling/base_tool.py` | `BaseTool` abstract base class with `run()` and progress-reporting methods |
| `janito/tooling/decorator.py` | `@tool(permissions="…")` decorator — marks a class as a discoverable tool |
| `janito/tools/__init__.py` | `discover_toolsets()` — auto-discovery engine |
| `janito/tooling/schema.py` | `get_function_schema()` — OpenAI-compatible schema generation |
| `janito/tooling/executor.py` | `run_tool()` — shared tool-execution core; converts a raising tool into a structured `success: False` result |
| `janito/tooling/tools_registry.py` | Registry, `AUTOLOAD_TOOLSETS`, lazy init, toolset management, lookups |
| `janito/tooling/reporter.py` | Standalone `report_start / report_progress / report_output / report_result / report_error / report_warning / report_info / report_diff` functions |
| `janito/tooling/path_utils.py` | `norm_path()` — normalises paths relative to CWD for display |
| `janito/privileges.py` | `Privileges` dataclass and `running_privileges` global |

---

## The Tool Specification

Every tool **must** satisfy the following contract:

### 1. Class-based, inherits `BaseTool`

```python
from janito.tooling import BaseTool
```

### 2. Decorated with `@tool`

```python
from janito.tooling.decorator import tool

@tool(permissions="r")          # "r", "w", "x", or combinations like "rw", "rwx"
class MyTool(BaseTool):
    ...
```

The decorator sets two attributes on the class:

- `_is_tool = True` — discovery filter
- `_tool_permissions = "<perms>"` — used by privilege gating and colour-coded reporting

### 3. Implements `run(self, **kwargs) -> Dict[str, Any]`

- The **first line of the class docstring** becomes the tool *description* the
  LLM sees.
- Parameter **types** are inferred from `run()`'s type hints
  (`str`, `int`, `float`, `bool`, `Optional[T]`, `List[T]`).
- Parameters **without a default value** become *required* in the schema.
- The method must **always** return a `Dict[str, Any]` containing at minimum a
  `"success"` boolean key (see [Return Value Contract](#return-value-contract)).

### 4. (Optional) Overrides `should_load(cls) -> bool`

A `@classmethod` that returns `False` when the tool's runtime requirements are
not met (missing binary, unsupported OS, absent credentials, …). Set
`cls._load_skip_reason` to a human-readable explanation before returning
`False`.

### 5. (Optional) Declares a `system_prompt_hint`

```python
system_prompt_hint = "one short paragraph of usage guidance for the LLM"
```

Text contributed to the system prompt as the tool's own `tools:<Toolname>`
section (under the `tools` header), shown only when the session may actually
use the tool — see
[Contributing to the System Prompt](#contributing-to-the-system-prompt).

### 6. (Recommended) Provides a `main()` CLI harness

A `main()` function guarded by `if __name__ == "__main__"` allows developers
to test the tool directly from the command line.

---

## Step-by-Step: Create a New Tool

We will create a **WordCount** tool inside the existing `files` toolset.

### Step 1 — Pick (or create) a toolset directory

Existing toolsets live under `janito/tools/<toolset>/`.
For a brand-new toolset, create the directory **and** an `__init__.py`:

```bash
mkdir janito/tools/mytoolset
touch janito/tools/mytoolset/__init__.py   # can be an empty docstring module
```

For our example we reuse `janito/tools/files/`.

### Step 2 — Create the tool module

Create `janito/tools/files/word_count.py`:

```python
#!/usr/bin/env python3
"""
Word Count Tool - Counts words, lines, and characters in a file.
"""

import os
import json
from typing import Dict, Any
from ...tooling import BaseTool, norm_path
from ...tooling.decorator import tool


@tool(permissions="r")                       # read-only → "r"
class WordCount(BaseTool):
    """
    Tool for counting words, lines, and characters in a text file.
    """

    def run(self, filepath: str) -> Dict[str, Any]:
        """
        Count words, lines, and characters in a text file.

        Args:
            filepath (str): Path to the text file to analyse.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - 'success': bool
                - 'filepath': the file that was analysed
                - 'words': word count
                - 'lines': line count
                - 'characters': character count
                - 'error': error message (only if success is False)
        """
        try:
            abs_filepath = os.path.abspath(filepath)
            norm = norm_path(abs_filepath)

            self.report_start(f"Counting words in {norm}", end="")

            if not os.path.isfile(abs_filepath):
                self.report_error(f"Not a file: {norm}")
                return {"success": False, "error": f"Not a file: {norm}",
                        "filepath": filepath}

            with open(abs_filepath, "r", encoding="utf-8") as fh:
                text = fh.read()

            words = len(text.split())
            lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            chars = len(text)

            self.report_result(f"{words} words, {lines} lines, {chars} chars")

            return {
                "success": True,
                "filepath": filepath,
                "words": words,
                "lines": lines,
                "characters": chars,
            }

        except Exception as e:
            self.report_error(f"Error: {e}")
            return {"success": False, "error": str(e), "filepath": filepath}


# ── CLI testing harness ──────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Word count tool")
    parser.add_argument("filepath", help="File to analyse")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    result = WordCount().run(filepath=args.filepath)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(f"{result['words']} words, "
                  f"{result['lines']} lines, "
                  f"{result['characters']} characters")
        else:
            print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
```

### Step 3 — Verify discovery

```python
from janito.tools import discover_toolsets
tools = discover_toolsets(["files"])
assert "WordCount" in tools, "Tool was not discovered!"
```

Or from the command line:

```bash
python -m janito.tools.files.word_count myfile.txt --json
```

### Step 4 — (Optional) Register a new toolset for auto-loading

If you created a **new** toolset directory, add its name to the
`AUTOLOAD_TOOLSETS` list in `janito/tooling/tools_registry.py`:

```python
AUTOLOAD_TOOLSETS = ["files", "system", "mytoolset"]
```

Toolsets *not* in this list can still be loaded at runtime via:

```python
from janito.tooling.tools_registry import add_toolset
add_toolset("mytoolset")
```

That is how `janitoweb` works — it is loaded on demand (it is web-only
and enabled by the web backend via `extra=["janitoweb"]`).

---

## Schema Generation (How the LLM Sees Your Tool)

`get_function_schema()` in `schema.py` auto-generates an
OpenAI function-calling schema from the wrapper's metadata:

| Schema field | Source |
|---|---|
| `function.name` | The **class name** (e.g. `WordCount`) |
| `function.description` | First line of the **class docstring** |
| `parameters.properties.<p>.type` | Type hint on `run()` parameter: `str→string`, `int→integer`, `float→number`, `bool→boolean`, `List[T]→array` |
| `parameters.properties.<p>.description` | Parsed from the `Args:` block of the docstring on the **wrapper** (which is the class docstring, *not* the `run()` docstring) — see note below |
| `parameters.required` | Parameters that have **no default value** |
| `Optional[T]` / `T \| None` | Unwrapped; the inner type is used. Required-ness is decided solely by whether the parameter has a default value (no default → required), so declare `T \| None = None` for optional parameters |

> **Important note on parameter descriptions.**
> The discovery wrapper copies `cls.__doc__` (the class docstring) onto the
> callable. `get_function_schema()` parses the `Args:` section of *that*
> docstring for per-parameter descriptions. Because the detailed `Args:`
> block typically lives in the `run()` method's docstring, per-parameter
> descriptions are **not** propagated to the schema by default. The LLM
> still receives correct parameter *names*, *types*, and *required* flags.
> If you want per-parameter descriptions visible to the LLM, add an
> `Args:` section to the **class docstring** as well.

### Example generated schema

For the `WordCount` tool above the registry produces:

```json
{
  "type": "function",
  "function": {
    "name": "WordCount",
    "description": "Tool for counting words, lines, and characters in a text file.",
    "parameters": {
      "type": "object",
      "properties": {
        "filepath": { "type": "string" }
      },
      "required": ["filepath"]
    }
  }
}
```

---

## The Permission System

The `permissions` string on `@tool(permissions="…")` uses single-character
flags:

| Char | Meaning | Example tools |
|---|---|---|
| `r` | **Read** — reads files, directories, network, system info | `ReadFile`, `ListFiles`, `GetUrl` |
| `w` | **Write** — creates, modifies, or deletes files/dirs | `CreateFile`, `DeleteFile`, `MoveFile` |
| `x` | **Execute** — runs commands, scripts, programs | `RunPythonCode`, `RunBashCode` |

Flags can be combined: `"rw"`, `"rx"`, `"rwx"`.

### How permissions affect behaviour

1. **Privilege gating** — when the user starts janito with `-r`, `-w`, `-x`
   flags (`janito/privileges.py`), only tools whose permission characters are
   all satisfied are loaded. If no flags are passed, *all* tools load.
2. **Colour-coded reporting** — `report_start()` picks an ANSI colour based
   on the permission string: green for read-only, yellow for write, yellow
   for execute.
3. **Introspection** — `get_all_tool_permissions()` / `get_tool_permissions()`
   expose permissions at runtime (used by the `/tools` shell command).

Choose the **least-privilege** string that covers your tool's behaviour.

---

## The `should_load()` Gate

Override the class method to perform runtime checks *before* the tool is
registered:

```python
@tool(permissions="x")
class RunBashCode(BaseTool):

    @classmethod
    def should_load(cls) -> bool:
        if os.name == "nt":
            cls._load_skip_reason = "Bash execution is not supported on Windows"
            return False
        shell = cls._find_shell()
        if shell is None:
            cls._load_skip_reason = "No Bash or POSIX shell found on this system"
            return False
        return True
```

`RunBashCode` is not loaded on Windows, even if Git Bash or WSL is installed.
Use `RunPowerShellCode` for shell execution on Windows. On non-Windows systems,
Bash detection and the POSIX `sh` fallback remain available. This loading gate
applies to both CLI and web sessions.

Rules:

- Must be a `@classmethod`.
- Return `True` to allow loading (default), `False` to skip.
- Set `cls._load_skip_reason` to a human-readable string before returning
  `False` (shown by the `/tools` diagnostic command).
- Must **not** raise; exceptions are caught and recorded as skip reasons.
- Common checks: binary on `PATH`, platform / OS, environment variables,
  credentials in the secrets store.

---

## Contributing to the System Prompt

A tool can advertise *usage guidance* for the LLM by declaring the optional
`system_prompt_hint` class attribute on its `BaseTool` subclass:

```python
@tool(permissions="x")
class RunPythonCode(BaseTool):
    """Tool for executing Python code and scripts."""

    system_prompt_hint = (
        "Read binary documents with Python libraries instead of manual "
        "parsing: read .docx with python-docx, .xlsx/.xlsm with openpyxl or "
        "pandas.read_excel, legacy .xls with xlrd, and PDFs with pdfplumber "
        "or pypdf."
    )
```

How the hint reaches the model:

1. Discovery copies `system_prompt_hint` onto the wrapped callable as
   `_tool_system_prompt_hint` (`janito/tooling/discovery.py`).
2. `ToolsRegistry.system_prompt_hints()` (module function
   `get_system_prompt_hints()`) collects the non-empty hints of the tools the
   **current session may actually use** — the same privilege
   (`-r`/`-w`/`-x`) and model-disabled filtering as the session tool schemas —
   sorted by tool name.
3. `janito.system_prompt.get_tools_section()` provides the header-only
   `tools` section (`## Tool Usage Notes`), and each hint becomes its own
   `tools:<Toolname>` section whose text is the hint alone.
   `sync_default_sections()` keeps them in sync (all omitted when no
   available tool declares a hint). The rendered prompt looks like:

   ```text
   ## Tool Usage Notes
   Read binary documents with Python libraries instead of manual parsing: ...
   ```

Guidelines:

- Keep it to **one short paragraph**, plain text (no markdown headings and
  no tool-name prefix — the tool name lives in the section name,
  `tools:<Toolname>`).
- Write the hint **function-first**, mentioning the tool inline where it
  matters, e.g. "Read PDFs using RunPythonCode with pdfplumber or pypdf".
- Hint at *how to use the tool well* (preferred libraries, formats, gotchas),
  not at *what the tool does* — that is the class docstring's job, already in
  the tool schema.
- `BaseTool.system_prompt_hint` defaults to `""`, so opting in means declaring
  it; plugin tools (`docs/PLUGINS.md`) work exactly the same way.
- Verify the result with `janito --show-system-prompt` or the shell `/prompt`
  command: both list the `tools` header and each `tools:<Toolname>` section
  as table rows.

---

## Progress Reporting

There are **two** reporting APIs. Both write to **stderr** (never stdout,
so they don't pollute the JSON result), but they serve different contexts.

### When to use which

| Context | API | Import |
|---|---|---|
| Inside a tool's `run()` method (you inherit `BaseTool`) | `self.report_*()` instance methods | Inherited — no import needed |
| Outside a tool class — MCP integrations, skills provider, CLI utilities, any helper code | `report_*()` standalone functions | `from janito.tooling.reporter import report_start, …` or `from janito.tooling import report_start, …` |

**Rule of thumb:** if you are writing a `BaseTool` subclass, always use
`self.report_*()`. The standalone functions exist for code that *cannot*
inherit from `BaseTool` (it has no `run()` method, no permissions, etc.).

### BaseTool instance methods (`self.report_*`)

These are **permission-aware**: `report_start()` automatically picks an ANSI
colour based on the tool's `@tool(permissions="…")` string, so the user can
see at a glance whether a tool is read-only (green), write (yellow), or
execute (yellow).

```python
def report_start(self, message: str, end: str = "\n") -> None
def report_progress(self, message: str, end: str = "\n") -> None
def report_output(self, message: str, end: str = "\n") -> None
def report_diff(self, old_str: str, new_str: str, end: str = "\n") -> None
def report_result(self, message: str, end: str = "\n") -> None
def report_error(self, message: str, end: str = "\n") -> None
def report_warning(self, message: str, end: str = "\n") -> None
```

| Method | Visual | Use for |
|---|---|---|
| `self.report_start(msg, end="\n")` | Colour by permissions: 🟢 `r`, 🟡 `w`/`x`, 🔵 none | Announce the operation is beginning |
| `self.report_progress(msg, end="\n")` | Plain text (no colour) | Intermediate progress updates |
| `self.report_output(msg, end="\n")` | Raw text (no emoji, no colour) | Stream subprocess stdout/stderr lines (used by `RunBashCode`, `RunPythonCode`, `RunGitHubCLI`) |
| `self.report_diff(old_str, new_str, end="\n")` | Unified diff, syntax-highlighted (`diff` lexer) | Show what a change does (e.g. `ReplaceTextInFile` before `report_result`) |
| `self.report_result(msg, end="\n")` | White + ✅ prefix | Final success summary |
| `self.report_error(msg, end="\n")` | ❌ prefix | Errors |
| `self.report_warning(msg, end="\n")` | ⚠️ prefix | Non-fatal warnings |

### Standalone functions (`janito.tooling.reporter`)

For code **outside** `BaseTool` subclasses — e.g. `mcp_manager.py`,
`skills_provider.py`, CLI helpers. These are *not* permission-aware; instead
`report_start` accepts an explicit `color` parameter.

```python
from janito.tooling.reporter import (
    report_start, report_progress, report_output,
    report_result, report_error, report_warning,
    report_info, report_diff, build_diff,
)
```

```python
def report_start(message: str, end: str = "\n", color: str = Colors.CYAN) -> None
def report_progress(message: str, end: str = "\n") -> None
def report_output(message: str, end: str = "\n") -> None
def report_diff(old_str: str, new_str: str, end: str = "\n") -> None
def report_result(message: str, end: str = "\n") -> None
def report_error(message: str, end: str = "\n") -> None
def report_warning(message: str, end: str = "\n") -> None
def report_info(message: str, end: str = "\n") -> None      # ← only here, not on BaseTool
def build_diff(old_str: str, new_str: str) -> str           # ← raw diff text, no printing
```

Key differences from the BaseTool methods:

| | `BaseTool.report_start` | `reporter.report_start` |
|---|---|---|
| Colour | Auto from `_tool_permissions` | Explicit `color` param (default `CYAN`) |
| Prefix | Leading space (to separate from LLM output) | Leading space + 🔄 emoji |
| Extra functions | `prompt_user()` (interactive Q&A) | `report_info()` (ℹ️ prefix, cyan), `build_diff()` (raw diff text) |

A `Colors` helper class is also available:

```python
from janito.tooling.reporter import Colors
# Colors.CYAN, Colors.GREEN, Colors.YELLOW, Colors.RED, Colors.WHITE, Colors.RESET
```

### Incremental progress lines

Both APIs support the `end=""` trick to build a single line step by step:

```python
# Inside a BaseTool.run():
self.report_start(f"📖 Reading {norm}", end="")   # no newline
self.report_progress(f" ({size} bytes)", end="")   # appended to same line
self.report_result(f"Read {n} lines")              # newline + ✅

# Outside a tool class:
report_start(f"Loading skill '{name}'", end="")
report_progress(" …", end="")
report_result("Done")
```

---

## Toolset Organization and Discovery

### Directory layout

```
janito/tools/<toolset_name>/
    __init__.py          # package marker (docstring-only is fine)
    tool_a.py            # one class per file (convention)
    tool_b.py
    …
```

### Discovery rules (`discover_toolsets`)

1. Each `.py` file in the toolset directory (except `__init__.py`) is
   imported.
2. Every **class** defined in that module (checked via `__module__`) that
   carries `_is_tool = True` (set by `@tool`) is a candidate.
3. Candidates pass through `should_load()` and privilege checks.
4. Surviving classes are wrapped and registered under their **class name**.

### Auto-loading vs. on-demand

- **Auto-loaded** toolsets are listed in `AUTOLOAD_TOOLSETS` in
  `janito/tooling/tools_registry.py` (currently `["files", "system", "net",
  "tasks"]`).
  They are discovered lazily on first registry access.
- **On-demand** toolsets (e.g. `janitoweb`) are loaded
  by calling `add_toolset("janitoweb")` at runtime (`janitoweb` is enabled only
  in web mode via the backend's `extra=["janitoweb"]`).
- **Plugin tools** are registered from a plugin's `TOOLS` list (or its
  `tools/` subpackage) via `wrap_tool_class()` / `discover_module_tools()`
  in `janito/tools/__init__.py`, using the same `should_load()` and
  privilege checks as built-in tools. See `docs/PLUGINS.md`.

### Naming conventions

- File name: `snake_case.py` (e.g. `word_count.py`)
- Class name: `PascalCase` (e.g. `WordCount`) — this becomes the tool name
  visible to the LLM
- One tool class per file (strong convention in this codebase)

---

## Return Value Contract

`run()` must **always** return a `Dict[str, Any]`.

### Required keys

| Key | Type | Description |
|---|---|---|
| `success` | `bool` | `True` if the operation succeeded, `False` otherwise |

### On success — include meaningful result data

```python
return {
    "success": True,
    "filepath": filepath,
    "words": 42,
    "lines": 7,
}
```

### On failure — include an `error` message

```python
return {
    "success": False,
    "error": "File not found: ./missing.txt",
    "filepath": filepath,
}
```

### Guidelines

- **Never raise** from `run()`. Catch all exceptions and return a
  `success: False` dict. (The framework's tool executor also wraps every call
  in a try/except — see `janito/tooling/executor.py` — so a raising tool
  never aborts the agent loop; the exception is turned into a generic
  `{"success": False, "error": ...}` result. Handling errors inside `run()`
  still yields richer, more accurate error dicts.)
- Echo back input parameters so the LLM can correlate the result with the
  call.
- Keep values JSON-serialisable (strings, numbers, bools, lists, dicts).
- For large outputs consider truncation parameters (see `ReadFile.max_lines`,
  `GetUrl.max_length`).
- The system exec tools (`RunBashCode`, `RunPythonCode`, `RunPythonFile`,
  `RunPowerShellCode`, `RunGitHubCLI`) return the full captured
  `stdout`/`stderr` inline in the result dict (in addition to streaming it to
  the screen in real-time via `report_output()`).

---

## CLI Testing Harness

`RunGitHubCLI` passes the discovered `gh` executable and parsed command arguments
directly to the subprocess runner rather than invoking a shell. This avoids
shell interpretation of executable paths (notably Windows paths containing
spaces). Quote command arguments containing spaces in the `cmdline` string.

Every tool module should include a `main()` function so it can be tested
standalone:

```bash
# Direct module execution
python -m janito.tools.files.word_count myfile.txt
python -m janito.tools.files.word_count myfile.txt --json

# Or via the tool registry
python -c "
from janito.tools import discover_toolsets
tools = discover_toolsets(['files'])
result = tools['WordCount'](filepath='myfile.txt')
print(result)
"
```

The convention is:

```python
def main():
    import argparse
    parser = argparse.ArgumentParser(description="…")
    # … define arguments mirroring run() parameters …
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output in JSON format")
    args = parser.parse_args()

    result = MyTool().run(…)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # human-friendly output
        …

if __name__ == "__main__":
    main()
```

---

## Complete Worked Example

Below is the full, copy-paste-ready source for a `WordCount` tool placed at
`janito/tools/files/word_count.py`.

```python
#!/usr/bin/env python3
"""
Word Count Tool - Counts words, lines, and characters in a file.

Note: This tool requires the progress reporting system from the tooling package.
For direct execution, use: python -m janito.tools.files.word_count [args]
For AI function calling, use through the tool registry (tooling.tools_registry).
"""

import os
import json
from typing import Dict, Any
from ...tooling import BaseTool, norm_path
from ...tooling.decorator import tool


@tool(permissions="r")
class WordCount(BaseTool):
    """
    Tool for counting words, lines, and characters in a text file.
    """

    def run(self, filepath: str) -> Dict[str, Any]:
        """
        Count words, lines, and characters in a text file.

        Args:
            filepath (str): Path to the text file to analyse.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - 'success': bool
                - 'filepath': the file that was analysed
                - 'words': total word count
                - 'lines': total line count
                - 'characters': total character count
                - 'error': error message (only present if success is False)
        """
        try:
            abs_filepath = os.path.abspath(filepath)
            norm = norm_path(abs_filepath)

            # 1. Report start (no newline yet — we append progress)
            self.report_start(f"Counting words in {norm}", end="")

            # 2. Validate input
            if not os.path.isfile(abs_filepath):
                self.report_error(f" Not a file: {norm}")
                return {
                    "success": False,
                    "error": f"Not a file: {norm}",
                    "filepath": filepath,
                }

            # 3. Do the work
            size = os.path.getsize(abs_filepath)
            self.report_progress(f" ({size} bytes)", end="")

            with open(abs_filepath, "r", encoding="utf-8") as fh:
                text = fh.read()

            words = len(text.split())
            lines = text.count("\n") + (
                1 if text and not text.endswith("\n") else 0
            )
            chars = len(text)

            # 4. Report success
            self.report_result(f"{words} words, {lines} lines, {chars} chars")

            # 5. Return structured result
            return {
                "success": True,
                "filepath": filepath,
                "words": words,
                "lines": lines,
                "characters": chars,
            }

        except Exception as e:
            self.report_error(f"Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "filepath": filepath,
            }


# ── CLI testing harness ──────────────────────────────────────────────────────
def main():
    """Command line interface for testing the WordCount tool."""
    import argparse

    parser = argparse.ArgumentParser(description="Word count tool")
    parser.add_argument("filepath", help="Path to the text file")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output in JSON format")
    args = parser.parse_args()

    result = WordCount().run(filepath=args.filepath)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["success"]:
            print(f"  Words:      {result['words']}")
            print(f"  Lines:      {result['lines']}")
            print(f"  Characters: {result['characters']}")
        else:
            print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
```

---

## Checklist Before Submitting

- [ ] **File placement** — one tool class per `.py` file inside a
      `janito/tools/<toolset>/` directory.
- [ ] **`__init__.py`** — toolset directory has an `__init__.py` (even if it
      only contains a docstring).
- [ ] **Inherits `BaseTool`** — `from ...tooling import BaseTool`.
- [ ] **Decorated** — `@tool(permissions="…")` with the minimal permission
      string.
- [ ] **Class docstring** — first line is a clear, concise description (this
      is what the LLM sees).
- [ ] **`run()` method** — typed parameters, `Dict[str, Any]` return,
      Google-style docstring with `Args:` and `Returns:` sections.
- [ ] **No exceptions escape `run()`** — wrap everything in try/except,
      return `{"success": False, "error": "…"}`.
- [ ] **`success` key** — always present in the returned dict.
- [ ] **Progress reporting** — use `report_start` / `report_progress` /
      `report_result` / `report_error` for user-visible feedback.
- [ ] **`norm_path()`** — use for any paths shown to the user.
- [ ] **`should_load()`** — override if the tool has runtime dependencies
      (binaries, credentials, platform). Set `_load_skip_reason`.
- [ ] **`system_prompt_hint`** — (optional) declare usage guidance for the
      system prompt and check it renders with
      `janito --show-system-prompt` / the shell `/prompt`.
- [ ] **CLI `main()`** — include an argparse-based test harness under
      `if __name__ == "__main__"`.
- [ ] **Autoload / on-demand** — if new toolset, decide whether to add it to
      `AUTOLOAD_TOOLSETS` or leave it for `add_toolset()`.
- [ ] **Test** — run the module directly *and* verify discovery via
      `discover_toolsets()`.
