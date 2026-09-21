# Architecture

This document summarizes the architecture of **janito**, a development agent
with function calling, MCP support and skills. It runs through two interfaces
built on the same engine: a terminal CLI/shell and an (alpha) browser-based
web UI.

---

## Overview

Janito is a Python 3.10+ application organized as a single `janito` package
plus a `tests/` suite. At a high level it is a loop:

```
user prompt ──► stream model response
                       │
       model wants tools? │
                       ▼
              execute tools
                       │
                       ▼
            append results, loop
                       │
       no more tools?   │
                       ▼
               display final answer
```

Everything else — CLI parsing, tool discovery, MCP, skills, the web UI,
configuration — exists to feed or present this loop. The per-session
configuration (provider, model, endpoint, api key, token limits, reasoning
level) is resolved **once** into an immutable `APIConfig`
(`llm_clients/api_config.py` → `build_api_config`) at the composition
point; the turn pipeline is a pure function of `(config, request)`.

### Top-level layout

| Path | Responsibility |
|------|----------------|
| `janito/__main__.py` | Entry point: argument parsing, dispatch, runtime setup |
| `janito/cli/` | CLI parsing, chat modes, flag-driven command handlers |
| `janito/shell/` | Interactive prompt_toolkit shell, `/`-commands and CLI conversation persistence (`persistence.py`: the `./.janito/session.json` snapshot behind `-C/--continue`) |
| `janito/llm_adapters/` | Shared per-API adapters used by both the CLI and web loops |
| `janito/llm_clients/` | API clients and the shared agent-loop pipeline |
| `janito/ui/` | Rich terminal presentation of the agent loop (turn observer, per-round stream runner, `UIConfig` bundle, usage/error rendering) |
| `janito/tooling/` | Tool framework: discovery + privilege gating (`discovery.py`), registry, executor, skills, tracking |
| `janito/tools/` | Built-in tool implementations, organized in toolsets (depends one-way on `tooling`) |
| `janito/mcp_client/` + `mcp_manager.py` | MCP server connections and tool routing |
| `janito/taskmanager/` | Parallel-task manager (issue #94): spawns each task as a child `janito` process and tracks its exit status (`constants`/`process`/`command`/`task`/`manager` modules, re-exported from `janito.taskmanager`) |
| `janito/conversation_utils.py`, `janito/optional_packages.py` | Root-level helpers shared across domains: turn truncation/rollback (`truncate_to_last_turn`, `rollback_to_last_turn`) and the optional-SDK install guards (`require_optional_package`) |
| `janito/web/` | FastAPI web backend + plain HTML/JS/CSS frontend |
| `janito/session_setup.py` | Shared system-prompt/toolset selection for the CLI and web entry points (outside `cli/` so the web backend never imports from the CLI package) |
| `janito/plugin_manager.py` | Plugin loader: contract validation, scoped `sys.path`, registration |
| `../plugins/` (outside the repo) | Optional plugins (e.g. `janito-codesearch-plugin/`) loaded with `--plugin DIR` |
| `janito/*config*.py`, `provider_*.py` | Configuration storage, loaders, provider registry |
| `docs/`, `mkdocs.yml` | MkDocs documentation site |

---

## Domains & boundaries

The codebase is organized into **domains** (the root package plus the
subpackages below), and the cross-domain import edges are a deliberate,
enforced contract.  The allowed directed edges (source ->
targets, same-domain imports always allowed) are:

| source \ target | llm_adapters | cli | llm_clients | mcp_client | providers | root | shell | tooling | tools | ui | web |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **root** | | ✓ | | ✓ | ✓ | — | ✓ | ✓ | ✓ | | ✓ |
| **llm_adapters** | — | | | | ✓ | | | | | | |
| **llm_clients** | ✓ | | — | | ✓ | ✓ | | ✓ | | | |
| **mcp_client** | | | | — | | | | | | | |
| **providers** | | | | | — | ✓ | | | | | |
| **shell** | | | ✓ | | ✓ | ✓ | — | ✓ | ✓ | | |
| **tooling** | | | | | | ✓ | | — | | | |
| **tools** | | | | | ✓ | ✓ | | ✓ | — | | |
| **ui** | ✓ | | ✓ | | ✓ | ✓ | | ✓ | | — | |
| **cli** | | — | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| **web** | ✓ | | | | ✓ | ✓ | | ✓ | ✓ | | — |

The intended layering:

- **`ui` / `shell` / `cli` / `web` are the outer presentation / entry
  layers** — they may depend on anything below them, and nothing below may
  depend on them.  In particular `web` never imports from `cli` (the shared
  `SessionSetup` lives at the package root), and — like `llm_adapters` —
  `web` never imports from `llm_clients` either: every per-API piece the
  web loop needs (call-kwargs builders, accumulators, the DashScope
  endpoint-routing helpers) lives in the shared `llm_adapters` layer, so
  the web agent runners stay thin async glue.  The API clients likewise
  never import the concrete `UIConfig` (they depend on the structural
  protocol in `llm_clients/base_client.py`; the frozen bundle is composed
  by the CLI in `janito/ui/config.py`).
- **`llm_adapters` is the shared adapter layer** — both agent loops (CLI and web)
  build on it; `llm_clients`, `ui` and `web` depend on it, and it must
  **never** import from `llm_clients` (the stream converters /
  `GeminiStreamConsumer` / `_ModelEndpointMismatch` / `_is_multimodal_model`
  / `_to_multimodal_messages` / raw-attrs helpers moved
  here for that reason).
- **`llm_clients` depends one-way on `llm_adapters`**, `tooling`,
  `providers` and the root config layer.
- **`tooling` is the tool framework** — `tools` (the built-in
  implementations) depends on it, never the other way round; tool discovery
  and the privilege predicates live in `tooling/discovery.py`.
- **`providers` and the root config stores are leaves.**
- The one remaining cycle — **root <-> providers** (config-store /
  variant-name resolution vs. the provider registry) — is accepted and kept
  contained with lazy imports on both sides; each site carries a
  comment to that effect.  `tests/test_import_graph.py` statically enforces
  this matrix, so any new cycle or wrong-direction edge fails the suite.

## Entry point & CLI dispatch

`janito/__main__.py` (`main()`) is the single entry point (also registered as
the `janito` console script). Flow:

1. **Parse args** with `janito/cli/parser.py` (argparse).
2. **Setup runtime** (`_setup_runtime`): apply `-c/--config-dir`, `--local`,
   logging, normalize `--provider`, and apply `-r/-w/-x` privilege flags into
   the module-level `running_privileges` (used later by tool discovery). With
   no `-r/-w/-x` flag the default is **read-only**: READ is
   granted, WRITE/EXEC are not; explicit flags take priority.
3. **Batch config ops** (`--set/--unset/--get/--set-secret/--delete-secret`)
   via `_handle_batch_config`.
4. **Load plugins** via `janito/plugin_manager.py`: plugins autoloaded from
   `~/.janito/plugins` (`load_installed_plugins`, unless `--no-plugins`) plus
   those requested with `--plugin DIR` (`load_plugins`, repeatable). For each
   plugin, its parent dir is temporarily added to `sys.path`, the package is
   imported, the contract is validated, `on_start` is called, and its tools,
   `/`-commands and system-prompt sections are registered — all before any
   registry/shell access. Plugin tools are **not** gated by `--no-tools`;
   use `--no-plugins` to disable autoloading.
5. **Flag-driven commands** (`--info`, `--config`, `--list-*`,
   `--set-api-key`, `--install-skill`, ...) via
   `_dispatch_flag_command` → handlers in `janito/cli/handlers/`.
6. **Validate runtime config** (`validate_runtime_config`) — API key, endpoint
   and model must resolve before any session starts.
7. **Dispatch to a mode**:
   - `--web` → `janito/web/backend/app.py:run_web` (checks the optional
     `[web]` extras first);
   - stdin pipe → the piped text replaces the prompt argument;
   - prompt argument present (positional, or piped) → `run_single_prompt`;
     otherwise `run_interactive_chat` (both in `janito/cli/chat.py`).

`janito/cli/chat.py` builds the per-session `APIConfig` via
`build_api_config` and returns a `turn_func` bound to the resolved API
type (Responses / Completions / Anthropic / DashScope / Gemini); it drives
either the interactive shell or a single prompt.
`janito/session_setup.py` (`SessionSetup`) decides the effective system
prompt and which toolsets to enable — shared with the web backend, which
imports it from the package root instead of from `cli/`.

---

## Interfaces

### Terminal CLI / shell

- **Single prompt**: one turn, exit. `echo ... | janito` and `janito "..."`.
- **Interactive chat** (`janito/shell/interactive.py`): prompt_toolkit-based
  shell with file-backed history, a bottom toolbar (model/provider), key
  bindings (clear, "do it", cancel), a command completer, and `/`-commands
  (`janito/shell/cmds/`): `/rewind`, `/history`, `/priv`, `/mcp`, `/skills`,
  `/tools`, `/changes`, `/ask`, `/multi`, ... Commands are registered through
  a small registry (`cmds/registry.py`).
- **`janito/shell/conversation.py`** — the single home for "where does the
  conversation live" (Completions-style `messages_history` vs stateless /
  server-side Responses items) and the `(role, content)` display rows
  `/history` renders. `/history`, `/compact` and the interactive shell's
  `_history_row_count` all delegate to it, so a new API mode is taught once.

### Web UI (alpha)

`janito --web` runs a FastAPI server (see [Web backend](#web-backend)) with a
browser chat interface served as static HTML/JS/CSS (no build step).

---

## Agent loop & API clients

The heart of the engine is a **template-method turn pipeline** defined in
`janito/llm_clients/base_client.py` (`Client.run_turn`), shared by five clients:

| Client | API type | File |
|--------|----------|------|
| Completions | `chat.completions` | `llm_clients/openai/completions_api.py` |
| Responses | `/responses` | `llm_clients/openai/conversations_api.py` |
| Anthropic | native `anthropic` SDK | `llm_clients/anthropic/anthropic_api.py` |
| DashScope | native `dashscope` SDK | `llm_clients/dashscope/dashscope_api.py` + `llm_clients/dashscope/dashscope_stream.py` |
| Gemini | native `google-genai` SDK | `llm_clients/gemini/gemini_api.py` + `llm_clients/gemini/gemini_stream.py` |

**Configuration is resolved once, not per turn**. The immutable
`APIConfig` dataclass (`llm_clients/api_config.py`) carries everything a
turn needs that can be decided before the call starts — provider, API type,
model, base URL, api key, resolved max-output/input tokens, reasoning level,
thinking mode, `preserve_thinking`, `use_mcp`. The UI-side behaviour
(per-round stream runner + turn observer) is carried separately by the
frozen `UIConfig` (`janito/ui/config.py`), injected at the same composition
point.  The pipeline depends only on the structural `UIConfig` protocol in
`llm_clients/base_client.py` (`stream_runner` + `observer`), so the API
clients never import the UI package.
`build_api_config` is the **single resolution point**: the only place that
touches the config store / auth store / provider registry. It is called at
the composition point (`cli/chat.py`'s `_make_turn_factory`, which rebuilds
it on every `/provider` / `/model` / `/thinking` switch) and handed to the
client constructor. The concrete client class is picked from the resolved
`APIConfig` by `llm_clients/factory.py` (`create_client`) — the single
`api_type` → class mapping, mirroring `mcp_client/factory.py`. The five
module-level `run_turn(config, prompt, *, ...)`
functions and `Client.run_turn` therefore make **no** config-store or auth-store
reads — the turn pipeline is a pure function of `(config, request)`.
The Responses `message` input-item shape is built by the shared
`llm_clients/openai/responses_items.py` (`message_item`) used by the clients
and the shell; `_resolve_model_settings` has a base default in `Client`
(reading the resolved `APIConfig`), with per-API overrides only when an API
drops a value (e.g. DashScope drops `reasoning_effort`).
Thinking mode is resolved into `config.thinking` at build time too (the
`--thinking` flag, or the provider's *static* built-in default — a `True`
flag or a pass-through dict such as MiniMax-M3's `{'type': 'adaptive'}`);
the shell's `/thinking` toggle flips it mid-session by re-invoking the send
factory with the shell's current flag, so no resolution is left inside the
pipeline (the web backend keeps its own `WebServerConfig` and
`effective_thinking`; see [Web backend](#web-backend)).

The pipeline per turn:

1. Reset per-prompt tracking (`clear_changes`, `reset_used_files`).
2. Read `(base_url, api_key, model)` straight from the config.
3. Create the SDK client; load MCP services and tools (if enabled).
4. Create a `ToolExecutor` (tool-call routing + bookkeeping).
5. Resolve tool schemas (built-in registry + MCP); model settings come from
   the config (max tokens, reasoning level, thinking).
6. Loop: stream a response → display reasoning/content (routed through the
   injected `TurnObserver`, see below) → if tool calls were
   requested, execute them (see [Tool execution](#tool-execution)) and loop
   again; otherwise finalize (record the assistant message, return value).
   Each round's usage is folded into a `TurnInfo` (`janito/llm_adapters/usage.py`);
   `Client.run_turn` itself delivers the end-of-turn reports (used files +
   token-usage summary) to the injected observer's `on_turn_complete` when
   the turn finishes, passing the `TurnInfo` together with the turn's
   resolved `APIConfig` (provider / model / max tokens come from the config)
   -- there is no caller-supplied out-param -- so the `_finalize`
   hooks stay display-free and every CLI entry point (interactive shell,
   `/ask`, `/compact`, one-shot prompt) gets the same reports (the `/compact`
   compression call swaps in the silent observer -- see below -- so it
   records the accounting row without rendering).

The blocking work of each streaming round — thread creation, the Rich spinner
and Enter-to-cancel detection — lives in a **per-round stream runner**
(`_run_with_progress_bar` + its `_is_enter_pressed` stdin poller, in
`janito/ui/stream_runner.py`). It is a UI-side concern **injected** by
the caller through the `UIConfig` (`stream_runner`): `None` runs each
stream worker directly in the calling thread — no thread, no spinner, no
Enter-to-cancel — keeping `run_turn`/`Client.run_turn` purely API-side.
`_make_turn_factory` in `cli/chat.py` (the same composition point that
injects the turn observer) wires in the TUI runner when it builds
the `UIConfig`, so every CLI entry point (interactive shell, `/ask`, `/compact`,
one-shot prompt) keeps the spinner. Because the runner is invoked **per
round** from inside the `Client.run_turn` loop, the spinner is only visible while
the API stream is in flight — never during tool execution.

All other user-visible output of the turn is routed through a **turn
observer** (`TurnObserver` protocol in `janito/llm_adapters/observer.py`), injected
through the `UIConfig` the same way as the stream runner: `on_reasoning` /
`on_message` (per-round reasoning/content fragments), the verbose
call/response dumps (`on_verbose_info` / `on_verbose_call` /
`on_verbose_response`), the error explainers (`on_error`, dispatched by an
explicit `error_kind` -- `"not_found"` / `"auth"` -- passed by the OpenAI
SDK clients' typed `except` blocks or derived for the native-SDK clients by
`_classify_error` in `llm_clients/client_support.py`; the exception is always
re-raised)
and the rate-limit wait (`on_limits`, issue #116 -- `Client.run_turn`
retries a 429 round after the observer's wait instead of failing the turn)
and the end-of-turn report (`on_turn_complete`, invoked by
`Client.run_turn` when the turn finishes -- the CLI's `RichTurnObserver`
renders the usage summary *and* records the overall-use accounting row from
that call). The
default is the headless `NullObserver`, so
`run_turn`/`Client.run_turn` produce no terminal output (the web loop emits
its own structured events instead); the CLI injects the
`RichTurnObserver` (`janito/ui/observer.py`) when it builds the
config through `_make_turn_factory`, keeping today's rendered output
byte-for-byte. `verbose` is an explicit per-call emission gate on
`Client.run_turn(verbose=...)` (used by `/ask` and `/compact`); the CLI's
session default is captured in the turn closure built by `_make_turn_factory`,
not on the config. The `/compact` compression call re-invokes the session's
turn factory with `silent=True` (see `compact.py`'s `_compaction_turn_func`),
which swaps the observer for `SilentTurnObserver` (`janito/ui/observer.py`):
every render is dropped -- the raw recap JSON is never echoed -- while the
injected TUI stream runner keeps the spinner / Enter-to-cancel and
`on_turn_complete` still records the accounting row.

The web loop (`janito/web/backend/agent/loop.py`) drives the **same turn
pipeline asynchronously**, yielding structured events instead of printing
Rich output. Both loops share the per-API adapter layer in
`janito/llm_adapters/` (`completions.py`, `responses.py`, `anthropic.py`,
`dashscope.py`, `gemini.py`, `usage.py`); the web loop's wire-format events
live in `janito/web/backend/events.py`. API-specific call-kwargs building,
stream accumulation and history conversion are implemented once.

---

## Two runtimes, one engine: sync CLI, async web

The CLI and the web UI drive the same turn pipeline on two different
runtimes: the CLI is **fully synchronous**, the web backend is **fully
asyncio**. The split is deliberate and visible in the code layout — there is
no `async def` anywhere in the package except under `janito/web/` (the few
`asyncio` mentions in `llm_adapters` / `tooling` docstrings all describe the
web loop bridging back *into* that sync code, below).

**Why the CLI stays sync.** A terminal session has one foreground user who
submits one turn at a time — there is no second stream of work to interleave,
so an event loop would buy nothing. The only concurrency the CLI needs is
"keep the UI alive while the API stream blocks": the spinner and
Enter-to-cancel, solved with one worker thread and a `cancel_event` in the
injected per-round stream runner (`ui/stream_runner.py`). The whole CLI stack
is synchronous by nature: Rich and prompt_toolkit drive the TTY with blocking
reads, Enter-to-cancel polls stdin with `select` / `msvcrt` (only meaningful
in blocking, canonical mode), and scripting use (piped prompts, exit codes)
wants straight-line blocking semantics. The five API clients therefore wrap
the **sync** SDK surfaces.

**Why the web must be async.** `janito --web` serves many concurrent sessions
from one process on uvicorn's event loop; a blocking LLM stream inside a
request handler would stall every other session and every HTTP endpoint.
Async lets N sessions interleave on a single thread, and it gives the router
something the CLI never needs: the per-connection turn is a task it can
*race* against cancellation. `_run_turn` (`web/backend/routers/chat_helpers.py`)
runs `asyncio.wait(..., return_when=FIRST_COMPLETED)` over the stream task
and the WebSocket receive loop (`_await_cancel`), rolls the conversation back
to a known-good state on a client cancel or disconnect (`_rollback`), and
collects prompts that arrive mid-turn into `pending_prompts` instead of
dropping them. Output is `await websocket.send_json(...)` of the structured
events in `web/backend/events.py` — the browser does the rendering a
`RichTurnObserver` does in the CLI, so the web loop never needs a terminal
observer at all.

**Where the two worlds meet.** The shared engine below `web/` stays sync;
the web loop bridges back into it at three seams, each one a thread hop:

1. **Streams with no async API** — the DashScope and Gemini runners pump the
   *sync* SDK stream chunk-by-chunk through
   `chunk = await asyncio.to_thread(_next_or_none, stream)` so the event loop
   stays responsive mid-stream.
2. **Tool execution** — built-in and MCP tools are plain sync functions;
   `web/backend/agent/tooling.py` runs `run_tool()` and MCP
   `load_services()` via `asyncio.to_thread`, so tools (and their subprocess
   instincts) never learn about asyncio.
3. **User prompting** — `AskUser` blocks its worker thread on a
   `threading.Event` while `WebPromptHandler` (`web/backend/prompts.py`)
   posts the question to the browser with `run_coroutine_threadsafe` and the
   WebSocket receive loop resolves it — a full thread → loop → browser → loop
   → thread round trip.

**The payoff.** Because async is confined to `janito/web/`, everything the
two loops share — `llm_adapters` (call-kwargs builders,
accumulators, the DashScope endpoint-routing helpers, `TurnInfo`),
`tooling`, the `TurnObserver` protocol — is
sync-pure and usable without an event loop anywhere in sight. That is what
makes the adapter layer genuinely shared — shared to the point that `web`
depends only on `llm_adapters` for its per-API code, never on the CLI's
`llm_clients` — and it mirrors the import matrix of
[Domains & boundaries](#domains--boundaries): `web` is just
another outer presentation layer depending inward, and its async-ness never
propagates below it. For the user-visible consequences of the split see
`docs/usage/cli-vs-web.md` — that doc is the *what*, this section is the
*why*.

---

## Tooling system

### Discovery & registry (`janito/tooling/`)

- **`tools_registry.py`** — lazy, module-level `ToolsRegistry` singleton:
  - `ensure_initialized()` runs discovery on first access so privilege flags
    are set before tools are filtered;
  - autoloads the `files`, `system`, `net`, `tasks` toolsets;
  - schema generation (`get_function_schema()` in `schema.py`) produces
    OpenAI-compatible JSON schemas from a tool's type hints and docstring;
  - `add_toolset()` enables on-demand toolsets (janitoweb);
  - `register_plugin_tools()` registers tool classes contributed by plugins
    (**not** gated by `--no-tools`, unlike built-in discovery — plugins are
    disabled independently via `--no-plugins`);
  - `enable_skills()/disable_skills()` toggle skill tools.

- **`executor.py`** — `ToolExecutor` + shared `run_tool()` core (the
  single tool-execution path used by both the CLI and web loops):
  - routes each call to the MCP manager (tools prefixed with a `service_`
    name) or the built-in registry;
  - tracks tool usage, used files and changes (best-effort);
  - never raises: failures become `{"success": False, "error": ...}` results
    so the model can react.

- **`base_tool.py` / `decorator.py`** — `BaseTool` ABC and the
  `@tool(permissions="...")` decorator marking a class as a tool.

- **`reporter.py` / `prompting.py`** — pluggable progress-report and
  user-prompt handlers (Rich console in the CLI, WebSocket frames in web
  mode).

- **`skills_provider.py`** — progressive-disclosure skills: advertise
  (~100 tokens) in the system prompt, load full `SKILL.md` when activated,
  read resources on demand. Skills are discovered from `~/.janito/skills`,
  `.agents/skills`, and `.janito/skills` (project-local wins, with
  `.janito/skills` taking precedence
  over `.agents/skills`).

- **`changes.py`, `used_files.py`, `tools_usage.py`** — per-prompt tracking
  feeding `/changes`, "Used files" reports and tool stats.

### Toolsets (`janito/tools/`)

Tools are grouped in directories (`files/`, `system/`, `net/`, `tasks/`,
`janitoweb/`). `discover_toolsets()` in
`janito/tools/__init__.py` scans each toolset for `@tool`-marked classes,
runs their `should_load()` gate (missing binaries, credentials, platform)
and wraps each class as a callable with the `run()` signature. Privilege
restrictions are **not** applied at discovery time (everything is loaded so
the session privilege switches can move beyond the startup privileges);
the session tool selector applies them instead (see
[Privileges](#privileges)). `wrap_tool_class()` / `discover_module_tools()`
expose the same pipeline for arbitrary modules so the plugin manager can
register tools from `plugins/*/tools/`.

### Plugins (`janito/plugin_manager.py`)

`load_plugin()` temporarily adds the plugin's **parent directory** to
`sys.path`, imports the package (enabling relative imports inside the
plugin), validates the contract (`name`, `on_start`, `SYSTEM_PROMPT`,
`TOOLS`, `CMD_HANDLERS`), calls `on_start`, and registers the contributed
tools (`ToolsRegistry.register_plugin_tools`), commands
(`shell/cmds/registry.register_command`) and system-prompt sections
(`system_prompt.SYSTEM_PROMPT_MANAGER.add_section`). `load_installed_plugins()`
autoloads every package directory under `~/.janito/plugins` (installed with
`janito --install-plugin <github_url>`); `--no-plugins` skips this autoload
but still loads `--plugin DIR` requests. Plugin tool registration is
**not** gated by `--no-tools` (the `--no-tools` flag only disables built-in
tools). See `docs/PLUGINS.md`.

### Privileges

`janito/privileges.py` defines a `Privileges` dataclass (READ/WRITE/EXEC), a
module-level `running_privileges`, and the `parse_privileges()` /
`format_privileges()` helpers that convert between the `r`/`w`/`x` string
form and a `Privileges` instance. `_setup_privileges` in
`janito/__main__.py` resolves the running privileges with this precedence:

1. explicit `-r`/`-w`/`-x` CLI flags (they override the configured default,
   so `-w` alone grants write-only, ...);
2. the `privileges` config key (`--set privileges=rwx`) -- the
   session default when no flag is given; validated/canonicalized at set
   time in `set_config_from_cli`, read at startup by
   `load_privileges_from_config` in `janito/config_loaders.py` (an invalid
   hand-written value is logged and ignored, falling back to read-only);
3. the built-in default **read-only**: READ granted, WRITE/EXEC
   not.

`running_privileges` is `None` only when no restrictions were configured
(outside the CLI, e.g. direct registry/web use), in which case everything is
allowed.

Discovery loads every tool whose `should_load()` gate passes; the *session
tool selector* (`get_session_tool_schemas` / `get_session_tool_names` in
`janito/tooling/tools_registry.py`) applies the privilege filter to what a
normal prompt may offer, and the session privilege switches (`/read`
`/write` `/rx` `/rw` `/rwx`, issue #141) can move it beyond the privileges
the session started with. The
interactive CLI prints a startup hint (`Started read-only, use /rwx
...with full privileges..`) after the version banner
when running with read-only privileges (the default or an explicit `-r`);
sessions that grant WRITE or EXEC skip the hint, and single-prompt runs
(`janito "prompt"` or piped stdin) skip it too, since `/rwx` is an
interactive-shell command.

---

## MCP support

- **`janito/mcp_manager.py`** — `MCPManager` manages multiple connected
  services: `load_services()`, transport lifecycle, tool listing/caching,
  and `call_tool()` routing by service prefix.
- **`janito/mcp_client/`** — transport layer: `stdio.py` (subprocess) and
  `http.py` (streamable HTTP), with a `factory.py` selecting the transport
  from `mcp_config.py` service definitions.
- **`janito/mcp_transports.py`** — the transport-type registry the CLI
  layers use to *build* (`/mcp add`) and *display* (`/mcp list`,
  `--list-mcp`) service configs, so the `stdio`/`http` knowledge lives in
  one root-level place (the shell/CLI layers may not import `mcp_client`;
  see the dependency matrix).
- Services are configured interactively via the `/mcp` shell command or
  `--list-mcp`, stored in the config store, and loaded at the start of every
  turn when MCP is enabled.

---

## Web backend

`janito/web/backend/` (FastAPI + uvicorn, optional `[web]` extras):

- **`app.py`** — app factory: mounts API routers (`/api/chat`, `/api/config`,
  `/api/tools`, `/api/mcp`, `/api/images`, `/api/health`), session manager,
  token-auth middleware and CORS, and serves the frontend via Jinja2
  templates + static files.
- **`session.py` / `session_store.py`** — `SessionManager` with optional
  TTL-based expiry (`--web-session-ttl`, lazy reaping + disk reload; disabled
  by default) and conversations persisted to `.janito/sessions/` so they
  survive restarts.
- **`security.py`** — optional bearer-token auth (`JANITO_WEB_TOKEN`) and CORS.
- **`agent/`** — the async agent loop (`loop.py` orchestrates; `turn.py`
  runs tool turns; `completions.py`, `responses.py`, `anthropic.py`,
  `dashscope.py`, `gemini.py` are the per-API-type runners — one module
  each, Completions included; `stream_utils.py` holds the shared stream
  consumption helpers (`_next_or_none`, `emit_stream_events`) the runners
  all delegate to; `tooling.py` resolves tools and executes
  calls). Tool calls run
  through the shared `run_tool` core in a worker thread
  (`asyncio.to_thread`).
- **`events.py` / `prompts.py`** — structured SSE/WebSocket events and the
  web AskUser prompt handler.
- **Frontend** (`janito/web/frontend/`): plain HTML/JS/CSS (Alpine.js) with
  WebSocket chat, session list, settings drawer, tool-call cards and a prompt
  modal.

---

## Code search

`../plugins/janito-codesearch-plugin/` powers the `CodeSearch`
tool with a **SQLite-based
inverted trigram index**:

- `index.py` — schema (files, trigrams posting lists) and the `Index` class;
- `trigram.py` — trigram extraction;
- `candidates.py` — candidate file scoring/ranking;
- `code_search.py` — the query layer (and the tool wraps it).

The plugin's `on_start()` creates the index at `.janito/codesearch.db`
when it is missing; the `/codesearch` shell command maintains it
(`/codesearch update` / `/codesearch recreate`). Load with
`janito --plugin ../plugins/janito-codesearch-plugin`.

---

## Configuration

Configuration lives in the config dir (default `~/.janito/`, overridable with
`-c/--config-dir` or local `.janito/` with `--local`):

| Store | File | Contents |
|-------|------|----------|
| Config | `config.json` | provider, model, tokens, api-type, endpoint, MCP services, ... |
| Auth | `auth.json` | API keys per provider |
| Secrets | `secrets.json` | additional named secrets |

Key modules:

- **`config_dir.py`** — config-dir resolution and local-mode flag.
- **`json_store.py`** — shared `JsonFileStore` base class (path resolution, local-merge reads, 0600 perms) plus the auth/secrets/MCP store subclasses.
- **`general_config.py`** — config-resolution helpers (`load_provider_from_config`,
  `determine_provider`, `get_active_provider`, `resolve_api_type()`).
  Config keys are scoped: flat keys (e.g. `provider`), **provider-scoped** keys
  (`model`, `endpoint` under `providers.<name>.<key>`) and **model-scoped**
  keys (`max-input-tokens`, `max-output-tokens`, `effort`, `api-type`,
  `stateless-mode` under `providers.<name>.models.<model>.<key>`).  The
  storage and per-key logic live in the focused modules below.
- **`config_keys.py`** — key constants (`PROVIDER_SCOPED_KEYS`,
  `MODEL_SCOPED_KEYS`) and the helpers that build/parse dotted keys
  (`model_config_key`, `model_scoped_config_key`, `normalize_api_type`,
  `get_masked_api_key`, ...).
- **`config_store.py`** — `ConfigStore` read/write primitives plus the
  `load_config` / `get_config_value` / `set_config_value` ... delegators.
- **`config_loaders.py`** — per-provider loaders (`load_model_from_config`,
  `load_max_output_tokens`, ...).
- **`config_cli.py`** — CLI helpers for the `--set/--get/--unset` family
  (provider-scoped and model-scoped key resolution).
- **`config_variants.py`** — provider variant management (`load_variants`,
  `create_variant`, `delete_variant`, ...).
- **`providers/`** — per-provider configuration package. The static
  provider registry is split into one `config.py` module per provider
  (`janito/providers/<name>/config.py`, each exporting that provider's
  `PROVIDER_CONFIG` entry); the package `__init__.py` assembles them into
  the internal `_PROVIDER_CONFIGS` dict, keeps the `REQUIRES_BY_API_TYPE`
  optional-package map and the `CUSTOM_ENDPOINT` marker, and exposes
  `get_provider_config(provider, model=None)` for direct (model-scoped)
  lookups. Each provider entry carries provider-level fields
  (`default_model`, `endpoint`, `endpoint_by_api_type`) plus a per-provider
  **`models`** dict with the model-level fields (`supported_api_types`,
  `default_api_type`, token limits, reasoning levels, `thinking`,
  `stateless_mode`). The `custom`
  provider ships no models (`default_model: None`, `models: {}`).
  `janito/providers/template/config.py` is the documentation template for
  these entries: it is not a real provider (never registered in
  `_PROVIDER_CONFIGS`) and comments every possible CONFIG option, so new
  providers are written by copying it and filling in the values.
- **`providers/models.py`** — the typed accessors: `Provider` (with
  `model_config(model)` and the routing helpers `tools` / `endpoint_for`)
  and `ModelConfig` (raw `get(key)` over one model entry plus the
  `tools(api_type)` routing helper). Accessor policy: plain model keys go
  through `model_config(model).get("...")` — a dedicated method exists
  only for routing/fallback logic (`tools`, `model_config`,
  `endpoint_for`, `has_usable_builtin_models`); no new `Provider`
  model-level pass-throughs.
- **`providers/registry.py`** — `ProviderRegistry` (case-insensitive lookup
  over `janito.providers._PROVIDER_CONFIGS`, including registered variants),
  the `parse_variant_name` / `is_variant_style_name` helpers, and the
  module-level `get_provider(name)` entry point that callers use to obtain a
  typed `Provider` (the former `get_*_from_provider` facade).
- **`providers/payloads.py`** — pure request-payload helpers
  (`apply_thinking_to_extra_body`, `apply_builtin_tools_to_extra_body`,
  `builtin_tools_enable_flags`, `format_thinking_display`).
- **`providers/costing.py`** — cost estimation (`get_provider_cost`,
  `get_provider_cost_value`, adaptive `format_cost`).
- **`providers/validation.py`** — provider name validation / listing helpers
  (`validate_provider_name`, `is_supported_provider`, `list_variants`, ...)
  and API-type availability (`get_all_api_types`,
  `ensure_api_type_available`, ...).
- **`auth_config.py`, `secrets_config.py`, `mcp_config.py`** — auth, secrets
  and MCP service stores.

The system prompt (`janito/system_prompt.py`) composes the base prompt, the
skills advertisement section, the current project's `AGENTS.md` content, and
any loaded plugins' `SYSTEM_PROMPT` sections. The base prompt is the packaged
resource `janito/system-prompt.txt` (installed as package data), read lazily
from the resource location when the default prompt is resolved. The
composition is built from ordered sections (`start`, `skills`, `agents.md`,
`plugins:<name>`) stored in a shared `SysPromptManager`; each section is a
`Section` dataclass carrying its name, text and an optional display `label`
(issue #86) — `built-in` for the packaged base prompt, `-S` for a
`--system-prompt` override, and `(config) ...` labels for the
`system-prompt` / `system-prompt-file` config keys (resolved by
`load_system_prompt_start`, which returns `(text, label)`).
`sync_default_sections()` keeps the dynamic `skills`/`agents.md` sections in
sync and `render()` joins every section with a trailing newline. The shell
`/prompt` command and `janito --show-system-prompt` display each section as a
row of a rich table (Section, Lines, Content) via `get_all_sections()`,
showing the label when set and falling back to the section name.

---

## A typical turn (end to end)

1. User runs `janito "fix the test"` (or chats in the shell / web UI).
2. `__main__` resolves config, validates runtime, dispatches to
   `run_single_prompt` / `run_interactive_chat`.
3. The chosen API client (`Client.run_turn` pipeline) streams the model response.
4. If the model emits tool calls, `ToolExecutor` → `run_tool()` executes them
   (built-in registry or MCP), tracking usage/used-files/changes, and the
   results are appended to the conversation.
5. The loop repeats until the model answers; the final answer is displayed
   (Rich in the CLI, events/WebSocket in web mode) with a token-usage summary.

---

## Testing & quality

- `tests/` — pytest suite covering clients, tooling, config, shell commands,
  skills, the plugin framework and web (`tests/web/`); the codesearch plugin
  carries its own tests under
  `../plugins/janito-codesearch-plugin/tests/`.
- `tox.ini` + `pyproject.toml` — tox environments, ruff linting/isort.
- `.pre-commit-config.yaml` + `.secrets.baseline` — pre-commit hooks and
  detect-secrets baseline.
