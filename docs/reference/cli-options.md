# CLI Options

Complete reference for janito command-line options.

## Usage

```bash
janito [options] [prompt]
```

If no prompt is given, janito starts an interactive chat shell.

## Prompt

| Argument | Description |
|----------|-------------|
| `prompt` | The prompt to send to the AI. If omitted, interactive chat starts. |

## Configuration

| Option | Description |
|--------|-------------|
| `-c`, `--config-dir <dir>` | Directory for all janito config (config, auth, secrets, MCP, skills). Defaults to `~/.janito` |
| `-l`, `--local` | Use the project-local config directory `./.janito` (the current working directory) for `--set`, `--set-api-key`, `--set-secret`, etc. Reads resolve local values first and fall back to the global `~/.janito`; list operations show both |
| `--config` | Open the interactive configuration wizard |
| `--show-config` | Display the configured provider and model |
| `--info` | Print resolved configuration (provider, model, API key) and exit |
| `--set <key=value>` | Set one or more config values in `~/.janito/config.json` |
| `--unset <key>` | Remove one or more config keys from `~/.janito/config.json` |
| `--get <key>` | Get one or more config values from `~/.janito/config.json` |
| `--set-api-key <key>` | Set the API key for a provider. Uses `--provider`, or falls back to the configured default provider (`--set provider=<name>`) when `--provider` is omitted; errors if neither is available. If a key is already stored, janito warns and prompts for confirmation before overwriting; use `-f`/`--force` to overwrite without prompting. |
| `-f`, `--force` | Overwrite an existing API key without prompting (used with `--set-api-key`) |
| `-p`, `--provider <name>` | Provider name (e.g., `openai`, `custom`). Always validated against the supported providers; unknown names are rejected. |
| `-m`, `--model <name>` | Model name (overrides the provider's configured model). Validated against the provider's built-in models; `openrouter` and `custom` accept any name |
| `--list-keys` | List configured providers and keys (with `-l`/`--local`, shows both the local and the global auth files) |
| `--list-models` | List all config-available models for the active provider (`--provider`, or the provider defined in `config.json`) and exit |
| `--show-providers` | List all supported providers and their built-in defaults (model, API types, endpoint, token limits, thinking/reasoning, built-in tools per API type), followed by the registered provider variants |

> **Note:** `--set` and `--set-api-key` must be used in **separate commands**, not together on the same line.

## Provider Variants

| Option | Description |
|--------|-------------|
| `--create-variant <name>` | Register a provider variant `<provider>-<word>` (e.g. `alibaba-tokenplan`) in `config.json`. After creation the name behaves like any provider (`--provider`, `--set provider=`, `--set-api-key`), inheriting its base provider's built-in defaults with its own per-variant model/endpoint/API key |
| `--delete-variant <name>` | Delete a provider variant and its per-variant configuration (model, endpoint, API type, tokens, reasoning level, API key). Refuses to delete the configured default provider |

```bash
janito --create-variant alibaba-tokenplan
janito --provider alibaba-tokenplan --set model=qwen3.8-flash
janito --set-api-key sk-xxx --provider alibaba-tokenplan
janito --set provider=alibaba-tokenplan
janito --delete-variant alibaba-tokenplan
```

See [Provider Variants](../configuration/variants.md) for the full guide.

## Secrets

| Option | Description |
|--------|-------------|
| `--set-secret <key=value>` | Set one or more secrets in `~/.janito/secrets.json` |
| `--get-secret <key>` | Get one or more secret values |
| `--delete-secret <key>` | Delete one or more secrets |
| `--list-secrets` | List all configured secret keys (with `-l`/`--local`, shows both the local and the global secrets files) |

## System Prompt

| Option | Description |
|--------|-------------|
| `-Z`, `--no-system-prompt` | Do not set a system prompt and do not pass any tools |
| `-S`, `--system-prompt <prompt>` | Override the system prompt (tools stay enabled) |
| `--no-tools` | Do not load tools (disables built-in, skill, plugin, MCP and server-side tools) |
| `--no-tasks` | Do not load the tasks toolset (`StartTask`, `StopTask`, `WaitForTask`, `ListTasks`); all other tools stay enabled |
| `--show-system-prompt` | Display the resolved system prompt and exit |
| `-t`, `--thinking` | Enable thinking mode (sends `extra_body={'enable_thinking': True}`). DeepSeek, Alibaba/Qwen and MiniMax-M3 have thinking enabled by default. Gemini-flavored providers (google) do not accept this flag; thinking depth is controlled through `--reasoning-effort` instead. |
| `-e`, `--reasoning-effort <level>` | Set the reasoning depth for the API call (sends `reasoning_effort=<level>`). Overrides the provider's configured value and built-in default. Values: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. |

## API Type

| Option | Description |
|--------|-------------|
| `--api-type <type>` | Force the API type for the provider. Values: `Responses`, `Completions`, `Anthropic`, `DashScope`, `Gemini`. Overrides the provider's configured value (`--set api-type=...`) and the model's built-in default. `Anthropic` requires the optional `anthropic` package, `DashScope` the optional `dashscope` package (alibaba provider), and `Gemini` the optional `google-genai` package (google provider) — janito aborts the change with a message naming the missing package. |

## Privileges

| Option | Description |
|--------|-------------|
| `-r`, `--read` | Grant READ privilege |
| `-w`, `--write` | Grant WRITE privilege |
| `-x`, `--exec` | Grant EXEC privilege |
| `--set privileges=<rwx>` | Persist the session's default privileges in `config.json` (issue #89) |
| `--unset privileges` | Remove the configured default, restoring the built-in full-privileges default |

The default privileges can be persisted in `config.json` so every session
starts with them without repeating the flags:

```bash
janito --set privileges=rwx      # sessions default to full privileges
janito --set privileges=rw       # sessions default to read+write
janito --unset privileges        # back to the built-in full-privileges default
```

The value is a combination of `r` / `w` / `x` in any order and case
(`rwx`, `xwr`, `RW`, ...); it is canonicalized to the fixed `r`/`w`/`x`
order when stored and validated at set time — anything else (including an
empty value) is rejected. Like the flags, `privileges=w` means write-only
(it does **not** imply read).

Precedence: explicit `-r`/`-w`/`-x` flags always win over the configured
default, which wins over the built-in full-privileges default. If none of
`-r`, `-w`, `-x` are given and no `privileges` config is set, janito starts
with **full privileges** (READ/WRITE/EXEC granted) and prints a warning
right after the version banner:

```
Warning: running with full privileges (rwx). Use -r/-w/-x to restrict.
```

Explicit `-r`/`-w`/`-x` flags or a configured `privileges` value -- even
`rwx` -- print no warning. In the interactive shell, `/rwx` switches the
session to the full toolset.

## Tools

| Option | Description |
|--------|-------------|
| `--list-tools` | List all available built-in tools and exit |

## Skills

| Option | Description |
|--------|-------------|
| `--install-skill <url>` | Install a skill from a GitHub URL |
| `--list-skills` | List all installed skills |
| `--uninstall-skill <name>` | Uninstall a skill by name |

## MCP

| Option | Description |
|--------|-------------|
| `--list-mcp` | List all MCP services and their tools |

## Plugins

| Option | Description |
|--------|-------------|
| `--plugin <dir>` | Load a plugin package from `dir` (repeatable; its parent is temporarily added to `sys.path` so relative imports work). Plugin tools, commands and system-prompt sections are registered before the session starts |
| `--install-plugin <url>` | Install a plugin from a GitHub repository URL. Downloads the `master` zip and extracts it to `~/.janito/plugins/<repo-name>` |
| `--uninstall-plugin <name>` | Uninstall an installed plugin by its plugin name (the `name` the plugin exports, as shown by `--list-plugins`; e.g. `codesearch` for the `janito-codesearch-plugin`). Removes the plugin's directory from the plugins dir; broken plugins that cannot be imported are matched by their directory name |
| `--no-plugins` | Do not autoload plugins from `~/.janito/plugins` (plugins explicitly loaded with `--plugin DIR` are still loaded) |
| `--list-plugins` | List loaded plugins (from `--plugin` and autoloaded from `~/.janito/plugins`) and their `on_start` errors, then exit |

## Web UI (Alpha)

| Option | Description |
|--------|-------------|
| `--web` | Start the web UI server instead of the terminal chat (requires the `[web]` extra: `pip install janito[web]`) |
| `--web-port <port>` | Port for the web server (default: `8080`, used with `--web`) |
| `--web-host <host>` | Bind address for the web server (default: `127.0.0.1` — localhost only, used with `--web`) |
| `--no-web-open` | Don't automatically open the browser (used with `--web`) |

All other Janito flags still apply in `--web` mode (they configure the
sessions the server runs). See [Web UI](../usage/web-ui.md) for details.

## Logging & Output

| Option | Description |
|--------|-------------|
| `--log=<levels>` | Enable logging (e.g., `--log=info,debug` or `--log=warning,error`; valid levels: `debug`, `info`, `warning`, `error`, `critical`) |
| `-v`, `--verbose` | Enable verbose output: model/backend/MCP info plus the API call parameters (messages shown as tail only) and a response summary |
| `--no-history` | Don't persist interactive input history to file |
| `--version` | Show version information and exit |
| `--help` | Show help message and exit |

## Examples

### Configure

```bash
janito --config
janito --show-config
janito --info
janito --show-providers   # list every provider and variant with its defaults
janito --list-models      # models available for the active provider
janito --set provider=openai --set model=gpt-5.6-luna
janito --set-api-key sk-your-key --provider openai
janito --set-api-key sk-your-key   # uses the configured default provider
```

### Project-local configuration

With `-l`/`--local`, configuration is stored in `./.janito` (the current
working directory) instead of `~/.janito`. Reads resolve local values first
and fall back to the global directory, and `--list-keys` / `--list-secrets`
show both:

```bash
janito -l --set model=gpt-5.6-luna                  # store config in ./.janito
janito -l --set-api-key sk-your-key --provider openai   # store the key in ./.janito
janito -l --list-keys                        # show global and local keys
```

### Secrets

```bash
janito --set-secret gmail_username=user@gmail.com
janito --set-secret gmail_password="xxxx xxxx xxxx xxxx"
janito --get-secret gmail_username
janito --list-secrets
janito --delete-secret gmail_password
```

### Enable Tools

```bash
janito --list-tools
```

### Plugins

```bash
janito --plugin ../plugins/janito-gmail-plugin "Show my emails"
janito --plugin ../plugins/janito-onedrive-plugin "List my files"
janito --list-plugins
janito --install-plugin https://github.com/joaompinto/janito-codesearch-plugin
janito --uninstall-plugin codesearch
```

### System Prompt & Privileges

```bash
janito -Z "Simple prompt without tools"
janito -S "You are a concise coding assistant" "Explain recursion"
janito -r -w "Refactor this file"
```

### API Type

```bash
janito --api-type Completions "Your prompt"   # force Chat Completions for one call
janito --provider google --set api-type=Gemini # persist the native Gemini SDK type
```

### Logging

```bash
janito --log=info "prompt"
janito --log=debug "prompt"
janito --log=info,debug "prompt"
```

## Configuration Keys

Values stored in `~/.janito/config.json` via `--set`. Keys are scoped:

- **flat** keys live at the top level of `config.json`;
- **provider-scoped** keys are stored as `providers.<provider>.<key>` — the
  active provider is taken from `--provider` or the configured `provider`
  value (so each provider can keep its own model/endpoint);
- **model-scoped** keys are stored as
  `providers.<provider>.models.<model>.<key>` — the model is resolved from
  the provider's configured model, else its built-in default (so each
  provider/model pair keeps its own limits and options).

| Key | Scope | Description | Default |
|-----|-------|-------------|---------|
| `provider` | flat | Provider name (`openai`, `google`, `custom`, `alibaba`, `deepseek`, `minimax`, `xiaomi`, `moonshot`, `zai`, `xai`, `anthropic`, `atria`, `openrouter`) | `openai` |
| `model` | provider-scoped | Model name | provider built-in default |
| `endpoint` | provider-scoped | API endpoint URL (required for `custom`) | provider built-in default |
| `max-input-tokens` | model-scoped | Maximum input tokens (context window) | model built-in |
| `max-output-tokens` | model-scoped | Maximum output tokens | model built-in |
| `reasoning-effort` | model-scoped | Reasoning depth (`none`…`max`) | model built-in |
| `api-type` | model-scoped | API type (`Responses`, `Completions`, `Anthropic`, `DashScope`, `Gemini`) | model built-in default |
| `stateless-mode` | model-scoped | Whether the Responses API keeps conversation state server-side (bool) | model built-in default |
| `used-files` | flat | Whether the end-of-turn `Used files` report is printed by the CLI/shell (bool, opt-in) | `false` |
| `system-prompt` | flat | Literal text used as the system prompt's `start` section | built-in base prompt |
| `system-prompt-file` | flat | Path to a file whose content becomes the `start` section (`~` is expanded, relative paths resolve against the cwd); wins over `system-prompt` when both are set. Validated when set and at startup: janito fails (exit 1) with an actionable error when the file does not exist | unset |

See [Configuration — System prompt](../configuration/index.md#system-prompt-system-prompt--system-prompt-file)
for the full semantics (`-S`/`-Z` precedence, per-session file re-read, the
project-local trust note).
