# Configuration

Learn how to configure janito for your needs.

## Topics

- [Providers](providers.md) - Configure OpenAI, local servers, or custom providers
- [Provider Variants](variants.md) - Multiple configurations for the same provider (`<provider>-<word>`)
- [Secrets](secrets.md) - Manage API keys and sensitive credentials

## Configuration File

janito stores your configuration in `~/.janito/`. The main configuration file is `~/.janito/config.json`.

> **Custom config directory:** Use `-c`/`--config-dir <dir>` to store *all* config
> (config, auth, secrets, MCP services and skills) in a different directory
> instead of `~/.janito`. For example: `janito -c ~/myconf --set provider=openai`.

> **Project-local config:** Use `-l`/`--local` to store config, API keys and
> secrets in `./.janito` (the current working directory) instead of
> `~/.janito`. Reads resolve local values first and fall back to the global
> directory, and `--list-keys` / `--list-secrets` show both. For example:
> `janito -l --set model=gpt-6-luna`.

### View Configuration

```bash
janito --show-config
```

### Configuration Options

These keys are stored in `~/.janito/config.json` (set them with `--set`).
Keys are *scoped* — `model`/`endpoint` live per provider and the model-level
keys per provider **and** model (see the note below and
[CLI Options — Configuration Keys](../reference/cli-options.md#configuration-keys)):

| Option | Scope | Description | Default |
|--------|-------|-------------|---------|
| `provider` | flat | Provider name (`openai`, `google`, `custom`, `alibaba`, `deepseek`, `minimax`, `xiaomi`, `moonshot`, `zai`, `xai`, `anthropic`, `atria`, `openrouter`) | `openai` |
| `model` | per provider | Model name | provider's built-in default model |
| `endpoint` | per provider | API endpoint URL (required for `custom` providers) | provider's built-in default |
| `max-input-tokens` | per provider/model | Maximum input tokens (context window) | model built-in |
| `max-output-tokens` | per provider/model | Maximum output tokens | model built-in |
| `effort` | per provider/model | Reasoning depth (`none`…`max`) | model built-in |
| `api-type` | per provider/model | API type (`Responses`, `Completions`, `Anthropic`, `DashScope`, `Gemini`) | model built-in default |
| `stateless-mode` | per provider/model | Whether the Responses API keeps conversation state server-side | model built-in default |
| `disabled-tools` | per provider/model | External tools hidden from the model (e.g. `WebSearch` when native server-side search exists; comma-separated or JSON list) | derived default (`WebSearch` for native-search models) |
| `used-files` | flat | Whether the end-of-turn `Used files` report is printed by the CLI/shell | `false` |
| `system-prompt` | flat | Literal text used as the system prompt's `start` section | built-in base prompt |
| `system-prompt-file` | flat | Path to a file whose content becomes the `start` section (`~` is expanded, relative paths resolve against the working directory); wins over `system-prompt` when both are set | unset |

### System prompt (`system-prompt` / `system-prompt-file`)

```bash
janito --set system-prompt="You are a terse assistant"
janito --set system-prompt-file=~/agents/base-prompt.md
```

When set, the configured text becomes the system prompt's `start` section;
the `skills`, `agents.md` and plugin sections stay unchanged. `-S`/`--system-prompt`
overrides the config value for that run (without changing it), and
`-Z`/`--no-system-prompt` disables the prompt entirely. `--show-system-prompt`
and the shell `/prompt` command show the configured `start` section as part
of the default section table.

The `start` row of that table is labelled with its source so you can tell
where the prompt came from: `built-in` for the packaged base prompt, `-S`
for a `--system-prompt` override, `(config) <file>` when
`system-prompt-file` is set, and `(config) <config-file>:system-prompt`
when the literal `system-prompt` key is used. Sections without a label
(`skills`, `agents.md`, `plugins:<name>`) keep showing their name.

By default (neither key set) the `start` section is the built-in base prompt,
shipped with janito as `janito/system-prompt.txt` — installed as package data
and read from the resource location each time the default prompt is built, so
editing the installed file (or the source-tree copy) is picked up without a
code change.

The file is read at session start (each new session re-reads it), so editing
the file is picked up by the next session. The path is validated when the
value is set (`janito --set system-prompt-file=...` rejects a missing file
with exit code 1) and again at startup, so a session never starts with a
broken path; the error names the key and path. An empty file falls back to the
built-in base prompt (like an empty `AGENTS.md`).

> **Note:** with `-l`/`--local`, `system-prompt-file` is resolved from the
> project-local config, so a checked-in `./.janito/config.json` can point the
> start section at a repository file. This mirrors the existing trust model
> that auto-loads a cwd `AGENTS.md` — only use local configs you trust.

At call time, when no model-scoped value is configured, janito falls back to
the provider/model's built-in limit (e.g. OpenAI's `gpt-6-luna`:
1,050,000 in / 128,000 out); the generic fallback used when even the model
has none is `128000` input / `100000` output.

> Provider base URLs are built in for known providers, so you normally only need `endpoint` for the `custom` provider. At runtime the endpoint is used directly as the API base URL. The model-level keys (`max-input-tokens`, `max-output-tokens`, `effort`, `api-type`, `stateless-mode`, `disabled-tools`) are stored per provider **and** model, under `providers.<provider>.models.<model>.<key>` in `config.json`.

### Disabled tools (`disabled-tools`)

```bash
janito --provider alibaba --set disabled-tools=WebSearch
janito --provider alibaba --set disabled-tools='["WebSearch"]'
janito --provider alibaba --unset disabled-tools
```

Models with native server-side search (Alibaba/Qwen, Meta Muse Spark) hide
the external `WebSearch` (Brave API) function tool by default so the model
uses its built-in search. Set `disabled-tools` to override per model (an
empty value re-enables every tool); the session tool list and the web
tool router both honor it.

### Used files report (`used-files`)

```bash
janito --set used-files=True
```

By default janito does **not** print the end-of-turn `Used files` report (the
list of files the tools read/wrote during the prompt). Set the flat
`used-files` key to `True` to enable it:

```bash
janito --set used-files=True   # or 1/yes/on
janito --unset used-files      # back to the default (off)
```

When enabled, the report is printed right before the token-usage summary at
the end of every turn (interactive shell, one-shot prompts, `/ask`). The
`/compact` compression call is the exception: it runs with the silent turn
observer, so it records the accounting row without rendering the used-files
report or the usage summary. The tracking itself always runs — the flag only
controls whether the report is displayed.

## Configuration Priority

Configuration is resolved from local files — janito does **not** read any
`OPENAI_*` environment variables. Values are resolved in this order (later
overrides earlier):

1. Provider's built-in default (endpoint) / no default (model)
2. Configuration file (`~/.janito/config.json`; with `-l`/`--local`, the
   project-local `./.janito/config.json` is consulted first and its values
   override the global ones)
3. Command-line arguments (`--model`, `--provider`, `--set endpoint=...`)

API keys are read from the per-provider key stored in `~/.janito/auth.json`
(set with `--set-api-key <key> --provider <name>`). There is no environment
variable fallback. With `-l`/`--local`, keys in `./.janito/auth.json` take
precedence over `~/.janito/auth.json`.

> **Note:** When using CLI arguments, `--set` and `--set-api-key` must be run as **separate commands**. They cannot be combined in a single invocation.

> **Note:** If an API key is already stored for a provider, `--set-api-key` warns you and asks for confirmation before overwriting it. Pass `-f`/`--force` to overwrite without prompting (useful for scripts and non-interactive use).

> **Note:** `--set-api-key` targets the provider given with `--provider`. When `--provider` is omitted, the configured default provider is used (the `provider` value from `config.json`); if none is configured, janito exits with an error.

## Next Steps

- [Configure providers](providers.md) for different AI services
- [Manage secrets](secrets.md) securely
