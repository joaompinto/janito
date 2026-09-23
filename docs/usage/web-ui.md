# Janito Web UI

> **⚠️ Alpha** — The `--web` mode is currently in **alpha**. It is functional
> and actively developed, but the interface, CLI flags, API endpoints, and
> WebSocket protocol may change in incompatible ways between releases. Pin a
> specific version if you depend on its current behaviour, and please report
> any issues you encounter.

A browser-based chat interface for Janito that exposes the full agentic
tool-calling experience — streaming responses, tool execution, MCP services,
and skills — through any modern web browser.

The web server reuses ~80% of the existing Janito Python codebase. The one
critical new piece is a **headless agentic loop** (the
`janito/web/backend/agent/` package, orchestrated by `loop.py`)
that yields structured events instead of printing to a terminal.

---

## CLI vs Web UI

The web UI and the terminal CLI/shell share the same engine, tools, and
configuration, but each surface has interface-specific features. The full
feature-by-feature breakdown is on [CLI vs Web UI](cli-vs-web.md); in short:

**Web-only features**

- Session sidebar (new chat, delete, rename, auto-naming) with persistence to
  `./.janito/sessions/`
- Settings drawer and provider switcher (runtime model / providers / API keys)
- MCP dashboard (connect / disconnect services)
- `/tools` rendered as a client-side card panel (the only slash command the web
  chat handles locally)
- Tool-call cards, collapsible Reasoning panel, token usage bar, status bar
- The `janitoweb` toolset (`CreateSVG`, `CreateImage`) — always loaded in `--web` mode
- `JANITO_WEB_TOKEN` bearer-token auth and the `--web*` server flags

**CLI-only features**

- Single-prompt and pipe input (`janito "..."`, `echo ... | janito`)
- The interactive shell (`/exit`, `clear`, `/changes`, `/skills`,
  `/show_tools_stats`, `/mcp add|list|remove`, `!<command>`, `Ctrl+D`/`Ctrl+C`,
  `F2`/`F12`, ...)
- Configuration & secrets maintenance (`--config`, `--set`, `--set-api-key`,
  `--set-secret`, `--list-keys`, ...)
- Skill management (`--install-skill`, `--list-skills`, `--uninstall-skill`)
- `--plugin DIR` / `--install-plugin` / `--no-plugins` / `--list-plugins`,
  `--list-tools`, `--list-mcp`, `--log=...`, exit codes

Everything else — the tools, privileges (`-r`/`-w`/`-x`), providers, models,
plugins (Gmail, code search, OneDrive), skills, MCP tools, and
`--no-history` — works in both.

---

## Installation

The web UI requires optional dependencies (FastAPI + Uvicorn) that are **not**
part of the core install, keeping `janito` itself dependency-light:

```bash
# pip
pip install janito[web]
# or uv
uv tool install janito[web]
```

If you run `janito --web` without the `[web]` extra installed, you'll get a
clear error message instead of a traceback:

```
Error: the web UI requires optional dependencies that are not installed.
Install them with:

    pip install janito[web]
```

---

## Quick Start

```bash
# Basic web server (opens your browser automatically)
janito --web

# Full-featured: read+write privileges, thinking mode, specific model
janito --web -r -w -t --model gpt-6-luna

# With a plugin (e.g. Gmail)
janito --web --plugin ../plugins/janito-gmail-plugin

# With the OneDrive plugin
janito --web --plugin ../plugins/janito-onedrive-plugin

# Custom provider + endpoint
janito --web --provider custom --set endpoint=https://api.example.com/v1

# Restricted: read-only, no system prompt, no tools, custom port
janito --web -r -Z --web-port 9090

# Don't auto-open the browser (headless / SSH sessions)
janito --web --no-web-open
```

The server prints the URL it's listening on, then opens your default browser
(unless `--no-web-open` is passed). Press `Ctrl+C` to stop.

---

## CLI Options

`--web` inherits **all** existing Janito CLI options as runtime configuration:

| Flag | Effect on the web server |
|---|---|
| `--web` | Start the web UI instead of the terminal chat (alpha) |
| `--web-port PORT` | Bind port (default `8080`) |
| `--web-host HOST` | Bind address (default `127.0.0.1` — localhost only) |
| `--no-web-open` | Don't auto-open the browser |
| `--web-session-ttl SECONDS` | Evict sessions idle longer than `SECONDS` from memory (lazy TTL: dropped on access, reloaded from disk on demand; `0` disables — the default). Ignored with `--no-history` |
| `-r` / `-w` / `-x` | Privileges (READ / WRITE / EXEC), enforced exactly like the CLI |
| `--provider` | Provider name (resolved into env before dispatch) |
| `-m`, `--model` | Model name (resolved into env before dispatch) |
| `--plugin DIR` | Load a plugin (e.g. the Gmail plugin: `--plugin ../plugins/janito-gmail-plugin`) |
| `-t, --thinking` | Enable thinking/reasoning mode for all sessions (DeepSeek, Alibaba/Qwen and MiniMax-M3 have it on by default) |
| `-S "prompt"` | Override system prompt (tools stay enabled) |
| `-Z, --no-system-prompt` | No system prompt, no tools |
| `--no-tools` | Do not load tools (disables built-in, skill, plugin, MCP and server-side tools) |
| `--no-tasks` | Do not load the tasks toolset (`StartTask`, `StopTask`, `WaitForTask`, `ListTasks`); all other tools stay enabled |
| `-v, --verbose` | Verbose backend logging |
| `--no-history` | Don't persist session history to disk (`./.janito/sessions/` is neither written nor read) |

---

## Features

- **Streaming text** — tokens appear in real time over WebSocket
- **Reasoning / thinking panel** — collapsible `💭 Reasoning` section that grows
  vertically to fit the entire thinking content (no height cap)
- **Tool call cards** — tool name, arguments, permission badge
  (🟢 read / 🟡 write / 🔴 exec), live spinner, result preview, execution time
- **Live tool output** — `report_*()` calls and subprocess stdout/stderr stream
  into the tool card in real time (rendered in a monospace block)
- **Token usage bar** — total / in / out / cached after each turn
- **Markdown rendering** — with syntax-highlighted code blocks
- **Session management** — sidebar with conversation list, new chat, delete, rename.
  New empty conversations are auto-named from the start of the first message you
  send (first 60 characters, replacing the default "New conversation" label).
- **Session persistence** — every conversation is stored to
  `./.janito/sessions/<session_id>/metadata.json` (single JSON object with
  metadata plus `messages`, relative to the working directory) and restored when
  the server starts, so conversations **survive a restart**. When the page
  loads, the frontend triggers the load of *all* sessions and replays their
  stored history into the UI, so switching tabs is instant. Pass `--no-history`
  to disable disk persistence entirely (sessions stay in memory only). With
  `--web-session-ttl SECONDS`, sessions idle longer than that are dropped from
  memory lazily (no background task) and transparently reloaded from disk when
  reopened, so the sidebar list shrinks without ever losing a conversation.
- **Provider switcher** — combo in the topbar lists the providers that have an
  API key set; picking one switches the provider for the **current browser /
  server session only** — it is applied to the running server (the very next
  prompt uses it, no restart needed) but is **not** persisted to
  `~/.janito/config.json`, so it does not leak into future CLI/web runs and is
  lost when the server restarts. To make a provider the permanent default, use
  the Settings drawer's "Set Default" button and then Save.
- **Settings drawer** — edit the model at runtime and manage providers/API
  keys. Nothing is written until the **Save** button is clicked: the Model
  field, a provider promoted via "Set Default", and a key entered via
  "Set API Key" are all *staged* (dirty) changes that arm the Save button
  (shown with yellow "pending" badges/notes); a single Save click persists
  them together and disables Save again. Closing the drawer discards staged
  changes. A collapsible **Advanced** section (closed by default) adds three
  per-provider fields saved the same way: **Endpoint** (base-URL override,
  empty = built-in), **API Type** (a combobox with one option per supported
  type, bound to the effective value), and a
  togglable **ResponsesInServer** switch that only appears while the API type
  is "Responses" (whether the Responses API keeps the conversation
  server-side via `previous_response_id`).
- **MCP dashboard** — see connected services, connect/disconnect
- **Status bar** — model, provider, active CLI flags, connection state, tokens
- **`/tools` command** — typing `/tools` in the chat input renders a formatted,
  card-based listing of every loaded tool (built-in tools with their permission
  badges, collapsible skipped tools with reasons, and connected MCP tools),
  plus a totals footer. Handled entirely on the client — no tokens spent.
- **Keyboard shortcuts** — Enter to send, Shift+Enter for newline

---

## Security

- **Localhost-only by default.** The server binds to `127.0.0.1`. Only bind to
  a public address (`--web-host 0.0.0.0`) if you understand the risks — Janito tools
  can read/write files and execute code.
- **Privileges are enforced.** Tools are filtered by `-r/-w/-x` exactly as in the
  CLI. With no privilege flags, both the CLI and the web server start
  **read-only** (issue #85): only the READ tools are offered, and the status
  bar shows the read badge active with write/exec off. Explicit `-r`/`-w`/`-x`
  flags take priority (`-r -w` grants read + write, `-r -w -x` everything).
- **Optional bearer-token auth.** Set the `JANITO_WEB_TOKEN` environment variable
  to require a token on all `/api` requests:

  ```bash
  export JANITO_WEB_TOKEN=my-secret-token
  janito --web --web-host 0.0.0.0
  ```

  The token is sent via `Authorization: Bearer <token>` (REST) or
  `?token=<token>` (WebSocket).

---

## Architecture

```
janito --web [options]
   │
   ▼  (existing __main__.py pipeline — unchanged)
   parse → logging → privileges → env setup → api key → validate
   │
   ▼  if args.web: run_web(args)        ← new dispatch point
janito/web/backend/
   config.py     WebServerConfig (built from argparse)
   app.py        create_app(config) + run_web(args)  [FastAPI + uvicorn]
   templating.py Jinja2 environment for the page templates (base + partials)
   agent/        loop.py — async event generator (headless agentic loop);
                 completions.py/turn.py/responses.py/anthropic.py/dashscope.py/gemini.py
   events.py     TokenEvent, ToolCallEvent, ToolProgressEvent, …
   session.py    ConversationSession + SessionManager (optional lazy TTL + persistence hooks)
   session_store.py  .janito/sessions/<id>/metadata.json read/write (issue #36)
   security.py   Token auth middleware + CORS
   routers/
     chat.py     WS /api/chat/ws/{session} + REST session CRUD + SSE
     config.py   GET/PATCH /api/config, /status, /providers, /cli
     tools.py    GET /api/tools, /skipped, POST /toolsets/{name}
     mcp.py      GET/POST /api/mcp/services/*
     images.py   GET /api/images/{filename} (serve CreateImage PNGs)
   │
   ▼  reuses (unchanged)
llm_adapters • tooling/* • tools/* • mcp_manager • general_config • …

janito/web/backend/templates/   (Jinja2 — composed server-side by app.py)
   base.html  •  partials/{sidebar,topbar,chat,chat_banner,chat_messages,
   input_area,status_bar,tools_dialog,settings_drawer,mcp_drawer,toast}.html

janito/web/frontend/   (Alpine.js — no build step)
   css/theme.css • js/{app,chat,chatCommands,websocket,sessions,
   settings,mcp,statusBar,providerSwitcher,markdown,api}.js
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/chat/sessions` | Create a session |
| `GET` | `/api/chat/sessions` | List sessions |
| `GET` | `/api/chat/sessions/{id}` | Get session history |
| `PATCH` | `/api/chat/sessions/{id}` | Rename a session |
| `DELETE` | `/api/chat/sessions/{id}` | Delete a session |
| `WS` | `/api/chat/ws/{id}` | Bidirectional streaming chat |
| `POST` | `/api/chat/prompt` | One-shot SSE streaming |
| `GET` | `/api/config` | Runtime config |
| `PATCH` | `/api/config` | Update mutable config (`model`, `endpoint`, `api_type`, `stateless_mode`; per-provider, persisted) |
| `GET` | `/api/config/providers` | Supported providers (incl. `api_key_set`, `active`, `effective`) |
| `GET` | `/api/config/status` | API key status, provider, privileges |
| `POST` | `/api/config/session-provider` | Switch provider for this session only (in memory; not persisted) |
| `POST` | `/api/config/default-provider` | Promote a provider to the persisted default (requires an API key) |
| `POST` | `/api/config/api-key` | Store an API key for a provider |
| `POST` | `/api/config/thinking` | Toggle runtime thinking for this server only (status-bar toggle) |
| `GET` | `/api/config/cli` | CLI args the server started with |
| `GET` | `/api/tools` | Loaded tools + schemas + permissions |
| `GET` | `/api/tools/skipped` | Skipped tools + reasons |
| `POST` | `/api/tools/toolsets/{name}` | Add a toolset |
| `GET` | `/api/mcp/services` | MCP services + status |
| `POST` | `/api/mcp/services/{name}/connect` | Connect a service |
| `POST` | `/api/mcp/services/{name}/disconnect` | Disconnect a service |
| `GET` | `/api/mcp/tools` | All MCP tools |
| `GET` | `/api/images/{filename}` | Serve a `CreateImage` PNG (temp dir only, `.png` only) |

### WebSocket Protocol

```
Client → Server:  {"type": "prompt", "content": "list files"}
Server → Client:  {"type": "waiting", "phase": "initial"}
Server → Client:  {"type": "token", "content": "Here"}
Server → Client:  {"type": "reasoning", "content": "Let me check..."}
Server → Client:  {"type": "tool_call", "id": "tc_1", "name": "ListFiles", "args": {...}, "permissions": "r"}
Server → Client:  {"type": "tool_progress", "id": "tc_1", "level": "start", "message": "📁 Listing..."}
Server → Client:  {"type": "tool_result", "id": "tc_1", "name": "ListFiles", "result": "..."}
Server → Client:  {"type": "usage", "total": 1234, "input": 1000, "output": 234}
Server → Client:  {"type": "done", "content": "Here are the files..."}
Server → Client:  {"type": "error", "message": "API key invalid"}
```

---

## Frontend

The frontend is **plain HTML + Alpine.js + CSS** with **no build step**. The page
shell (`janito/web/backend/templates/base.html`) and its partials are composed
server-side with Jinja2, so the markup stays declarative and split into
manageable files; the static assets (CSS/JS) are served from
`janito/web/frontend/` via `StaticFiles`. Libraries (Alpine.js, marked.js,
highlight.js) load from a CDN, so installing the `[web]` extra (see
[Installation](#installation) above) makes the UI work immediately — no `npm`,
no bundler.

> To run fully offline, vendor the CDN libraries into
> `frontend/js/vendor/` and update the `<script>` tags in
> `backend/templates/base.html`.

---

## Development

Run the server in development:

```bash
janito --web --no-web-open -v
```

The frontend is served live from source — edit files under
`janito/web/frontend/` and refresh the browser (no rebuild needed).
