# CLI vs Web UI

janito ships with **two interfaces** that share the same engine, tools, and
configuration:

- **Terminal CLI/shell** — single-prompt mode (`janito "..."`), an interactive
  chat shell (`janito`), pipe input (`echo ... | janito`), and a rich set of
  `--flags` for configuration, secrets, authentication, and maintenance.
- **Web UI** — `janito --web` starts a browser-based chat server that reuses
  the same agentic loop and adds streaming responses, tool-call cards, session
  management, and dashboards.

Both interfaces are built on the **same core**: the agentic loop, the tools
(files, code search, web, plugins/Gmail/OneDrive, skills, MCP), privilege enforcement
(`-r`/`-w`/`-x`), provider/model resolution, and the system-prompt logic are
shared code paths. The differences are in *how you interact* — and which
shell- or browser-specific conveniences each surface offers.

> See [Web UI](web-ui.md) for the full web-server reference, and
> [Interactive Mode](interactive-mode.md) for the terminal shell.

## Feature Comparison

Legend: ✅ available · — not available

### Starting a Session

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| Single prompt: `janito "question"` | ✅ | — |
| Interactive chat shell: `janito` | ✅ | — |
| Pipe input: `echo "text" \| janito` | ✅ | — |
| Browser chat: `janito --web` | — | ✅ |
| Server binding (`--web-port`, `--web-host`, `--no-web-open`) | — | ✅ |

### Chat Experience

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| Responses printed to the terminal (progress indicator while the API responds) | ✅ | — |
| Live token streaming over WebSocket | — | ✅ |
| Thinking mode (`-t` / `--thinking`) | ✅ | ✅ |
| Reasoning depth (`--effort`) | ✅ | — (resolved from the provider's config) |
| Collapsible "Reasoning" panel | — | ✅ |
| Tool-call cards with permission badge, spinner, result preview and execution time | — | ✅ |
| Live tool output streaming into the card (`report_*()`, subprocess stdout/stderr) | — | ✅ |
| Tool progress messages on stderr | ✅ | — |
| Token usage bar after each turn | — | ✅ |
| Markdown rendering with syntax-highlighted code blocks | — | ✅ |
| Status bar (model, provider, active CLI flags, connection, tokens) | — | ✅ |

### Commands & Shortcuts

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| `/exit` | ✅ | — |
| `clear` | ✅ | — |
| `Ctrl+D` / `Ctrl+Z` (EOF), `Ctrl+C` (cancel + rollback), Enter (cancel, keep prompt) | ✅ | — |
| `F2` (clear conversation), `F12` (Do It / continue existing plan) | ✅ | — |
| `/help` | ✅ | — |
| `/skills` | ✅ | — |
| `/tools` | ✅ | ✅ (client-side card panel) |
| `/show_tools_stats` | ✅ | — |
| `/changes` (replay file-changing tool executions) | ✅ | — |
| `/mcp add` / `/mcp list` / `/mcp remove` | ✅ | — (use the MCP dashboard) |
| `/ask`, `/compact`, `/history`, `/multi`, `/notools`, `/plugins`, `/priv`, `/price`, `/prompt`, `/provider`, `/model`, `/api_types`, `/read`, `/rewind`, `/rw`, `/rwx`, `/rx`, `/status`, `/thinking`, `/write` | ✅ | — |
| `!<shell command>` (run a command directly) | ✅ | — |
| Command autocomplete for `/`-commands | ✅ | — |
| Enter to send, `Shift+Enter` for newline | — | ✅ |

> The web chat only handles `/tools` on the client (rendered as a card panel).
> Any other slash command typed into the web input box is sent to the model as
> ordinary text.

### Sessions & History

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| Conversation history kept in context during a session | ✅ | ✅ |
| Session sidebar (new chat, delete, rename, auto-naming) | — | ✅ |
| Session persistence to `./.janito/sessions/<id>/metadata.json` (survives restart) | — | ✅ |
| Conversation resume with `-C` / `--continue` (snapshot to `./.janito/session.json`) | ✅ | — |
| Interactive input-history file | ✅ | — |
| `--no-history` (disable persistence) | ✅ *input history + resume snapshot* | ✅ *session files* |

> Note: the same `--no-history` flag means different things in each interface —
> in the CLI it disables the input-history file **and** the conversation
> snapshot used by `-C`/`--continue`, in the web UI it disables
> session persistence to `.janito/sessions/`.

### Configuration & Secrets

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| `--config` wizard, `--set`, `--unset`, `--get`, `--show-config`, `--info` | ✅ | — |
| `--set-api-key`, `--list-keys`, `-f` / `--force` | ✅ | — |
| Secrets: `--set-secret`, `--get-secret`, `--delete-secret`, `--list-secrets` | ✅ | — |
| `-c` / `--config-dir`, `-l` / `--local` (project-local config) | ✅ | — |
| Settings drawer (runtime model, providers, API keys, endpoint, API type, ResponsesInServer) | — | ✅ |
| Provider switcher (session-only override, not persisted) | — | ✅ |
| Thinking toggle in the status bar (session-only override) | — | ✅ |

> The web Settings drawer persists changes to the same `~/.janito/config.json`
> store the CLI reads. Session-only overrides (provider switcher, thinking
> toggle) are kept in memory and lost on restart.

### Authentication & Security

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| `JANITO_WEB_TOKEN` bearer-token auth on `/api` endpoints | — | ✅ |
| Localhost-only binding by default (`127.0.0.1`) | — | ✅ |
| Privileges `-r` / `-w` / `-x` enforced on tools | ✅ | ✅ |

### Tools & Integrations

The shared toolsets are auto-loaded in **both** interfaces: `files`, `system`,
and `net` (web search / URL fetch / headless browse). Plugins loaded with
`--plugin DIR` (e.g. `../plugins/janito-gmail-plugin` or
`../plugins/janito-onedrive-plugin`) or autoloaded
from `~/.janito/plugins`
contribute their tools in both
interfaces too. Skills and
MCP tools work everywhere.

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| File tools, system tools, web tools, code search | ✅ | ✅ |
| Gmail tools (janito-gmail-plugin) | ✅ | ✅ |
| OneDrive tools (janito-onedrive-plugin) | ✅ | ✅ |
| Skills (`load_skill`, `read_skill_resource`) | ✅ | ✅ |
| MCP tools | ✅ | ✅ |
| `janitoweb` toolset (`CreateSVG`, `CreateImage`) | — | ✅ (always loaded) |
| `/mcp` commands to manage services | ✅ | — |
| MCP dashboard (connect / disconnect services) | — | ✅ |

### Observability & Maintenance

| Feature | CLI/shell | Web UI |
|---------|:---------:|:------:|
| `--log=info,debug,...` | ✅ | — |
| `-v` / `--verbose` | ✅ | ✅ (verbose backend logging) |
| Exit codes (`0`, `1`, `130`) | ✅ | — |
| `--list-tools`, `--list-mcp`, `--list-plugins` | ✅ | — |
| `--plugin DIR` (load plugins; plugin tools work in both interfaces) | ✅ | ✅ |
| `--install-plugin`, `--list-plugins`, `--no-plugins` | ✅ | — |
| `--install-skill`, `--list-skills`, `--uninstall-skill` | ✅ | — |
| `--version`, `--help` | ✅ | — |

## Which Interface Should I Use?

**Use the terminal CLI/shell when:**

- You want a quick single prompt or a scriptable pipeline (`janito "..."`, `| janito`).
- You're working in a terminal-first workflow and want to stay in it.
- You need to manage configuration, API keys, or secrets (`--set`, `--set-api-key`, `--set-secret`, ...).
- You need skill management or to configure plugin secrets (e.g. the OneDrive `azure_client_id` with `--set-secret`) from the command line.
- You want exit codes for scripting and automation.

**Use the web UI when:**

- You prefer a graphical chat with sessions, a sidebar, and instant switching between conversations.
- You want to watch tool calls, thinking, and token usage rendered as visual cards and panels.
- You want to manage providers, models, and API keys from a Settings drawer instead of flags.
- You run a shared/headless server (`--no-web-open`) that others (or you, from another machine) reach through a browser.

Both interfaces read the same configuration, so you can switch freely — for
example, set the OneDrive `azure_client_id` secret from the CLI once
(`janito --set-secret azure_client_id=your-client-id`); the plugin
authenticates automatically on startup and works in either interface.

## See Also

- [Web UI](web-ui.md) — server setup, CLI options, API endpoints, WebSocket protocol
- [Interactive Mode](interactive-mode.md) — the terminal shell in detail
- [Single Prompt](single-prompt.md) — one-shot and piped prompts
