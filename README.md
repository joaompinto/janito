# janito - a development agent with function calling, MCP and skills

![Console vs Web](https://raw.githubusercontent.com/joaompinto/janito/main/docs/imgs/console_vs_web.png)

> 📖 **Full documentation available at [https://joaompinto.github.io/janito/](https://joaompinto.github.io/janito/)**

> ⚠️ **Disclaimer:** The code on this repo has been developed mostly using AI.

## Features

- 🔧 **Function Calling** - Built-in tools for file operations, web search, and more
- 🔌 **Plugins** - Gmail, code search, OneDrive, and more via the plugin system
- 🔌 **MCP Support** - Connect to Model Context Protocol servers
- 🧩 **Skills** - Install and use task-specific skills from GitHub
- 🌐 **Web UI (Alpha)** - Chat through a browser instead of the terminal with `--web`
- ↪️ **Session Resume** - Exit a terminal chat and reopen it with `janito -C` (full conversation restored)
- 📊 **Real-time Progress** - Watch tool execution progress as it happens
- 🚀 **Easy Setup** - Interactive configuration with `--config` or quick setup with `--set` flags
- 🔗 **OpenAI-Compatible & Native APIs** - Works with any OpenAI-compatible endpoint (OpenAI, LM Studio, Ollama, custom) and native SDKs (Anthropic, DashScope)

 NOTE: Janito should be used on development systems on which data loss is tolerable and there are no critical secrets

## Quick Start

```bash
# Install
pip install janito

# Or, with uv (recommended)
uv tool install janito

# Configure interactively
janito --config

# Or set options directly (two steps: config, then API key)
janito --set provider=openai --set model=gpt-6-luna
janito --set-api-key="sk-your-key" --provider openai

# Start chatting
janito "Hello!"
```

## Installation

### From PyPI

```bash
pip install janito
```

Or, with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install janito
```

For development setup, see [README_DEV.md](dev-docs/README_DEV.md).

## Configuration

### Interactive Setup

```bash
janito --config
```

You'll be prompted for:
- **Provider** - `openai` or `custom`
- **API Key** - Masked for security
- **Model** - e.g., `gpt-6-luna`
- **Max Output Tokens** - Maximum output tokens (default: 65536)
- **Max Input Tokens** - Maximum input tokens / context window (default: 128000)

### Quick Configuration with `--set`

Set options directly from the command line:

```bash
# Single key-value
janito --set model=gpt-6-luna
```

You can also use `--get`, `--unset`, and `--set-secret` with multiple values.

### View Configuration

```bash
janito --show-config
```

### Costs per provider

| Provider | Last Model | Price |
|----------|-------------|---------|
| Alibaba  | qwen3.8-flash | Pay as you go |
| Moonshot | kimi-k3 | $15/month (Moderato)|
| z.ai     | glm-5.3-flash | $12.6/month (Lite)|
| openai   | gpt-6 | Pay as you go |


For custom endpoints (base-url), see [README_custom.md](README_custom.md).

## Usage

### Single Prompt

```bash
janito "What is the capital of France?"
```

### Pipe Input

```bash
echo "Tell me a joke" | janito
```

### Interactive Chat

```bash
janito
```

Commands in chat mode:
- `/exit` - End the session
- `clear` - Clear conversation and start a new one
- `Ctrl+D` / `Ctrl+Z` then Enter - Exit (EOF)
- `/help` - List all commands (with descriptions) and shortcuts

### Web UI (Alpha)

> ⚠️ **Alpha** — The `--web` mode is currently in alpha. It works, but the
> interface, CLI flags, and API may change between releases.

Janito can serve a browser-based chat interface instead of the terminal. This
requires optional dependencies that are **not** part of the core install:

```bash
# Install with the web extra
pip install janito[web]
# or
uv tool install janito[web]
```

Then start the server (opens your browser automatically):

```bash
janito --web

# All normal Janito flags still apply, plus web-specific ones:
janito --web -r -w --web-port 9090    # privileges + web, custom port
janito --web --no-web-open                      # don't auto-open the browser
```

The server binds to `127.0.0.1` by default (localhost only). For full details
(features, security, API endpoints, architecture), see the
[Web UI documentation](https://joaompinto.github.io/janito/usage/web-ui/).

### System Prompt Options

Control how the system prompt is handled:

```bash
# Use default system prompt (with tools enabled)
janito "What can you do?"

# Disable system prompt entirely (no tools at all)
janito -Z "Simple prompt without system context"

# Override with a custom system prompt (tools stay enabled)
janito -S "You are a concise coding assistant" "Explain recursion"

# Keep the system prompt but skip tool loading (skill tools stay enabled)
janito --no-tools "Explain recursion"

# Skip only the parallel-tasks toolset (StartTask/StopTask/WaitForTask/ListTasks)
janito --no-tasks "Refactor this file"
```

| Flag | Description |
|------|-------------|
| `-Z`, `--no-system-prompt` | Skip system prompt and disable tools |
| `-S`, `--system-prompt` | Custom system prompt |
| `--no-tools` | Do not load tools (skill tools stay enabled) |
| `--no-tasks` | Do not load the tasks toolset (`StartTask`, `StopTask`, `WaitForTask`, `ListTasks`); all other tools stay enabled |

> **Note:** When using `-Z`, built-in tools (file operations, MCP) are disabled. Use the default mode or `-S` flag when you need tool access.
>
> **Note:** `--no-tools` disables loading of all non-skill tools (file operations, MCP) while keeping the skill tools (`load_skill`, `read_skill_resource`) available, so the model can still load installed skills on demand.
>
> **Note:** `--no-tasks` disables only the tasks toolset (the `StartTask` / `StopTask` / `WaitForTask` / `ListTasks` tools that spawn parallel child processes). File, system, net and skill tools stay available.

### Logging

```bash
janito --log=info "Your prompt"      # Info level
janito --log=debug "Your prompt"     # Debug level
janito --log=info,debug "Your prompt" # Multiple levels
```

## Examples

### OpenAI

```bash
# Step 1: Set provider and model
janito --set provider=openai --set model=gpt-6-luna
# Step 2: Store API key
janito --set-api-key="sk-your-key" --provider openai

# Then run any prompt
janito "Explain quantum computing"
```

### Alibaba (Qwen)

```bash
# Step 1: Set provider and model
janito --set provider=alibaba --set model=qwen3.8-flash
# Step 2: Store API key
janito --set-api-key="your-dashscope-api-key" --provider alibaba

# Then run any prompt
janito "Explain quantum computing"
```

### Custom Endpoint

```bash
janito --set provider=custom --set base-url=http://localhost:8000/v1
```

## Built-in Tools

janito includes tools for common tasks:

### File Operations

```bash
# List files
python -m janito.tools.files.list_files . --recursive --pattern "*.py"

# Read file
python -m janito.tools.files.read_file README.md --max-lines 20
```

### MCP Tools

Connect to MCP servers using the `/mcp` command inside the interactive shell:

```bash
# Add a stdio-based MCP server
/mcp add myserver stdio python -m mcp.server

# Add an HTTP-based MCP server
/mcp add remote http https://api.example.com/mcp

# List configured servers
/mcp list
```

For full MCP documentation, see [README_MCP.md](README_MCP.md).

## Tool Progress Reporting

Tools report progress in real-time:

```
🔄 Reading files...
📊 Processing: 50/100 files
✅ Completed: 100 files (2.3MB)
```

Progress messages go to stderr so they don't interfere with tool output.

## Error Handling

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | Configuration or runtime error |
| `130` | User cancelled (Ctrl+C or Enter) |

## Dependencies

- Python 3.10+
- `openai>=1.0.0`
- `rich>=10.0.0`
- `prompt-toolkit>=3.0.0`
- `requests>=2.28.0` (for MCP support)
- `pathspec>=0.11.0` (for `.gitignore`-aware file listing)
- `questionary>=2.1.1` (for the interactive `--config` wizard)

Optional extras: `janito[web]` adds `fastapi`/`uvicorn` (for `--web`); the
native API types need `anthropic` (`--api-type Anthropic`), `dashscope`
(`DashScope`) or `google-genai` (`Gemini`).

## License

MIT License
