# Providers

janito supports multiple AI providers. This guide covers configuration for each.

janito talks to models through **two kinds of API**:

- **OpenAI-compatible APIs** — the `Responses` and `Completions` API types,
  driven by the `openai` package. This is the default for OpenAI and for any
  provider or local server (LM Studio, Ollama, the `custom` provider) that
  exposes an OpenAI-compatible endpoint.
- **Native APIs** — the providers' official SDKs, selectable through API
  types such as `Anthropic` (native Anthropic SDK), `DashScope` (native
  DashScope SDK) and `Gemini` (native Gemini SDK). These talk directly to the
  provider's native API instead of its OpenAI-compatible gateway.

The API type is selected per provider with `--set api-type=...` (see the
[`Anthropic`](#native-anthropic-sdk-optional),
[`DashScope`](#native-dashscope-sdk-optional) and
[`Gemini`](#native-gemini-api-optional) sections below).

## Supported Providers

| Provider | Description |
|----------|-------------|
| `openai` | OpenAI API |
| `google` | Google Gemini (Gemini models) |
| `custom` | Any OpenAI-compatible API (local servers, third-party) |
| `alibaba` | Alibaba Cloud DashScope (Qwen models) |
| `deepseek` | DeepSeek |
| `minimax` | MiniMax AI (MiniMax models) |
| `meta` | Meta Model API (Muse Spark models) |
| `xiaomi` | Xiaomi AI (Mimo models) |
| `moonshot` | Moonshot AI (Kimi models) |
| `zai` | Z.AI (GLM models) |
| `xai` | xAI (Grok models) |
| `anthropic` | Anthropic (Claude models) |
| `apertus` | Apertus (Swiss AI Initiative models via Swisscom) |
| `openrouter` | OpenRouter (aggregator of many models) |

!!! note
    The provider name is always validated against this list. Whenever you pass
    `--provider <name>` (or set `provider=<name>` in the config), janito checks
    that it is a supported provider — one that maps to an API base URL — and
    rejects unknown names with an error enumerating the supported providers.

!!! note
    The model name is validated the same way. For providers with built-in
    model entries (every provider except `openrouter` and `custom`), `--model`
    and `--set model=...` accept only the provider's built-in models; an
    unknown name is rejected with the available models listed. Model-scoped
    settings (`--set max-output-tokens=...`, `--set reasoning-effort=...`, ...)
    are likewise only available for those built-in models — arbitrary model
    names cannot be configured for these providers. `openrouter` (an
    aggregator) and `custom` (any OpenAI-compatible endpoint) have no built-in
    model list, so **any** model name and its settings are accepted there.
    `janito --list-models` shows the accepted names for the active provider.

## Listing providers

`janito --show-providers` prints every supported provider with its built-in
defaults — default model, API types (with the built-in default marked),
effective endpoint, masked API key, thinking/reasoning defaults, token limits
and any built-in (native) tools per API type — followed by the registered
[provider variants](variants.md), each marked with its base provider. The
configured default provider is flagged `[active]`:

```bash
janito --show-providers
```

```
Supported Providers (13):
============================================================
  openai [active]
    Model:         gpt-5.6-luna (default)
    API types:     Responses (default), Completions
    Endpoint:      default OpenAI (no custom base URL)
    API key:       (not set)
    Thinking:      disabled
    Reasoning:     low (default)
    Max tokens:    1,050,000 in / 128,000 out
  ...
  alibaba
    Model:         qwen3.8-flash (default)
    API types:     Completions, Responses (default), DashScope
    Tools:         code_interpreter, i2i_search, t2i_search, web_extractor, web_search (Responses)
    ...
  alibaba-tokenplan (variant of alibaba)
    Model:         qwen3.8-max (configured; default qwen3.8-flash)
    ...
```

Configured per-provider overrides (e.g. a variant's model or endpoint) are
shown where set, so you can see at a glance which providers are configured
and which still need a key or an endpoint.

## OpenAI

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=openai --set model=gpt-5.6-luna
# Step 2: Store API key
janito --set-api-key="sk-your-key" --provider openai
```

Or interactively:

```bash
janito --config
```

> API keys are stored in `~/.janito/auth.json`; the model is stored in
> `~/.janito/config.json`. janito does not read `OPENAI_*` environment
> variables. See [Configuration Priority](index.md#configuration-priority).

### Reasoning Level

The GPT-5.x models support configurable reasoning depth via the
OpenAI-compatible `reasoning_effort` parameter. The supported levels are
`low`, `medium` and `high`; the built-in default is the lowest supported
level (`low`).

```bash
# Override the reasoning depth for a single call
janito --reasoning-effort high "Your prompt"

# Set a per-provider default in the config
janito --provider openai --set reasoning-effort=medium
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > the model's own default level (`low` for the
GPT-5.x models).

## Google (Gemini)

Use Google Gemini models through their OpenAI-compatible API.

> **Get an API key:** Visit [Google AI Studio](https://aistudio.google.com/apikey) to create an account and generate a Gemini API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=google --set model=gemini-3.7-flash
# Step 2: Store API key
janito --set-api-key="your-gemini-api-key" --provider google
```

The `google` provider talks to Gemini through Google's OpenAI-compatibility
layer (`https://generativelanguage.googleapis.com/v1beta/openai/`, see the
[Gemini API OpenAI compatibility docs](https://ai.google.dev/gemini-api/docs/openai)),
so it uses the standard **Chat Completions** API out of the box.

### Native Gemini API (optional)

Besides the OpenAI-compatibility layer (the `Completions` API type, the
built-in default), the `google` provider also supports the **native Gemini
API** through the `Gemini` API type. It talks to the Gemini API directly
(`https://generativelanguage.googleapis.com`) using the official
[`google-genai`](https://ai.google.dev/gemini-api/docs/libraries) package:

```bash
# Install the optional package
pip install google-genai

# Use the native Gemini API for a single call
janito --api-type Gemini "Explain quantum computing"

# ...or set it as the per-provider default
janito --provider google --set api-type=Gemini
```

Gemini 3.x models reason by default on the native API too; reasoning depth is
controlled through `--reasoning-effort`, sent as `thinking_level`. Thought
summaries stream into the reasoning panel, and function/tool calls work
exactly like the other API types (MCP included).

### Popular Models

| Model | Description |
|-------|-------------|
| `gemini-3.7-flash` | Latest Gemini Flash model (default, built-in) |

Model selection is restricted to the built-in models above; other Gemini
names such as `gemini-2.5-pro` are not accepted for this provider.
`janito --list-models` shows the accepted names.

### Reasoning Level

Gemini models reason by default (thinking cannot be disabled for Gemini 3.x
models). The OpenAI-compatible `reasoning_effort` parameter maps to the
model's `thinking_level`, which accepts `minimal`, `low`, `medium` and
`high`:

```bash
# Override the reasoning depth for a single call
janito --reasoning-effort high "Your prompt"

# Set a per-provider default in the config
janito --provider google --set reasoning-effort=medium
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > the model's own default level (`medium` for
`gemini-3.7-flash`).

### Thinking Mode

The `google` provider is **Gemini-flavored**: the `enable_thinking`
extra-body flag is **not** sent to Google's OpenAI-compatibility layer
(because the field does not exist and Gemini 3.x models reason by default).
Thinking depth is instead controlled through `--reasoning-effort`, sent as
`reasoning_effort` (the API maps it to the model's `thinking_level`).
Using `/thinking on` or `-t`/`--thinking` is therefore a no-op for the
request body.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=google --set model=gemini-3.7-flash
# Step 2: Store API key
janito --set-api-key="your-gemini-api-key" --provider google
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Custom Providers (OpenAI-Compatible)

Use any OpenAI-compatible API, including local servers like LM Studio, Ollama, or third-party providers.

### Configuration

```bash
# Step 1: Set provider, endpoint, and model
janito --set provider=custom --set endpoint="http://localhost:8000/v1" --set model="my-model"
# Step 2: Store API key (optional)
janito --set-api-key="optional-key" --provider custom
```

### Common Endpoints

| Provider | Endpoint Example |
|----------|------------------|
| LM Studio | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |
| LocalAI | `http://localhost:8080/v1` |

### Example: LM Studio

```bash
# Step 1: Configure provider
janito --set provider=custom \
        --set endpoint="http://localhost:1234/v1" \
        --set model="local-model-name"
# Step 2: Set placeholder API key
janito --set-api-key="not-needed" --provider custom
# Step 3: Run prompt
janito "Hello"
```

## Alibaba (Qwen)

Use Alibaba Cloud DashScope to access Qwen models.

> **Get an API key:** Visit [Alibaba Cloud Model Studio](https://modelstudio.alibabacloud.com/) to create an account and generate a DashScope API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=alibaba --set model=qwen3.8-flash
# Step 2: Store API key
janito --set-api-key="your-dashscope-api-key" --provider alibaba
```

### Popular Models

| Model | Description |
|-------|-------------|
| `qwen3.8-flash` | Default model: fast and cost-effective, with built-in token limits, reasoning levels and tools |
| `qwen3.8-max` | Flagship model with built-in token limits, reasoning levels and tools |
| `qwen3.8-max-0902` | Dated flagship snapshot, same limits/reasoning/tools as `qwen3.8-max` |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Reasoning Level

Both Qwen models (`qwen3.8-max` and the default `qwen3.8-flash`) support
configurable reasoning depth via the OpenAI-compatible `reasoning_effort`
parameter. The supported levels are `low`, `medium` and `xhigh`; the
built-in default is the lowest supported level (`low`).

```bash
# Override the reasoning depth for a single call (qwen3.8-max)
janito --model qwen3.8-max --reasoning-effort medium "Your prompt"

# Set a per-provider default in the config (qwen3.8-max)
janito --provider alibaba --set model=qwen3.8-max
janito --provider alibaba --set reasoning-effort=medium
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > built-in default (`low` for the Qwen models).

### Thinking Mode

Qwen models reason by default, so thinking mode is enabled out of the box for
the `alibaba` provider: every call sends
`extra_body={'enable_thinking': True}`. Pass `-t` / `--thinking` to force it
on for any provider.

Both built-in Qwen models (`qwen3.8-max` and the default `qwen3.8-flash`)
also send `extra_body={'preserve_thinking': True}` on the OpenAI-compatible
Completions / Responses calls. `preserve_thinking` is a Qwen extension (not
an OpenAI standard parameter): it makes the API append the assistant
messages' `reasoning_content` to the next input in multi-turn conversations,
so the model can reference its own prior reasoning across turns. It is a
built-in model default in janito, not a configurable setting.

### API Type

The `alibaba` provider defaults to the Responses API for its built-in default
model `qwen3.8-flash`. The Chat Completions API remains fully supported and can
be selected per provider or per call with:

```bash
# Per provider (persisted)
janito --provider alibaba --set api-type=Completions

# Per call
janito --provider alibaba --api-type completions "Your prompt"
```

### Built-in Tools

The default model `qwen3.8-flash` declares **built-in (native) tools** —
`code_interpreter`, `i2i_search`, `t2i_search`, `web_extractor` and
`web_search` — enabled **per API type** (the `tools_by_api_type` model-config
field); the flagship `qwen3.8-max` declares `code_interpreter`, `web_search`
and `web_extractor`. These are *not* function tools: each `type` is a model
capability enabled through request-body flags on the API call, so they are
always on whenever the model declares them for an API type — even with
`--no-tools` / an empty function-tools list (mirroring the Responses
`image_generation` tool for gpt-5+).

Currently they are declared for the **Responses API type only**: the CLI
Responses client and the [web agent](../usage/web-ui.md) resolve them per
model (`get_default_tools_from_provider(provider, model,
api_type="Responses")`) and append them to the `tools` array after any
converted function-tool schemas. Note that DashScope's `/responses` endpoint
did not accept `qwen3.8-max` at the time of writing (see [API Type](#api-type)
above), so the built-in tools are picked up automatically by the Responses
client and the web agent as soon as the endpoint supports the model. They are
left off the Completions API and the native DashScope API because the
qwen3.8-max deployment rejects `code_interpreter` there with
`400 InternalError.Algo.InvalidParameter: The current model does not support
the code_interpreter tool.`; API types not listed in `tools_by_api_type` send
no built-in tools (the plain `tools` default still applies when present).

`janito --show-providers` surfaces them per model, annotated with the API type
that enables them:

```
  alibaba
    Model:         qwen3.8-flash (default)
    Tools:         code_interpreter, i2i_search, t2i_search, web_extractor, web_search (Responses)
```

### Native DashScope SDK (optional)

By default the `alibaba` provider talks to DashScope's OpenAI-compatible
endpoint through the **Responses** API (the built-in default API type for
`qwen3.8-flash`; the Chat Completions API is also fully supported — see
[API Type](#api-type)). A **native DashScope SDK** API type (`DashScope`) is
also available: it uses the official `dashscope` Python package against the
DashScope native API (`https://dashscope-intl.aliyuncs.com/api/v1`,
per-API-type endpoint, see `endpoint_by_api_type`).

The `dashscope` package is **optional**; janito aborts the change (with a
message naming the package) if you try to select the `DashScope` API type
without it:

```bash
# Install the optional package first
pip install dashscope

# Then select the native SDK API type
janito --provider alibaba --set api-type=DashScope

# Per call
janito --provider alibaba --api-type DashScope "Explain quantum computing"
```

Thinking mode is enabled out of the box here too: the native SDK receives
`enable_thinking=True` (Qwen models reason by default). The `dashscope`
package does not use `reasoning_effort`, so `--reasoning-effort` is accepted
for parity but not mapped to a DashScope parameter.

The DashScope native API serves models from two generation endpoints:
`text-generation` for plain-text models and
`multimodal-generation` for multimodal models (Qwen-VL / Qwen-Omni, the
`qwen3.x-plus` generation, and the `qwen3.8-max` flagship). janito picks
the endpoint from the model name automatically and, if the API ever rejects
the model for that endpoint (`InvalidParameter: url error, please check
url`), retries once on the other endpoint — so models work out of the box
here too.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=alibaba --set model=qwen3.8-flash
# Step 2: Store API key
janito --set-api-key="your-dashscope-api-key" --provider alibaba
# Step 3: Run prompt
janito "Explain quantum computing"
```

## DeepSeek

Use DeepSeek models.

> **Get an API key:** Visit [DeepSeek Platform](https://platform.deepseek.com/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=deepseek --set model=deepseek-flash
# Step 2: Store API key
janito --set-api-key="your-deepseek-api-key" --provider deepseek
```

### API Types and Base URLs

The `deepseek` provider supports the OpenAI-compatible **Responses** and
**Completions** API types (Responses is the built-in default) against the
OpenAI-compatible base URL `https://api.deepseek.com`, plus a native
**Anthropic** SDK API type against DeepSeek's Anthropic-compatible base URL
`https://api.deepseek.com/anthropic` (per-API-type endpoint, see
`endpoint_by_api_type`).

The `anthropic` package is **optional**; janito aborts the change (with a
message naming the package) if you try to select the `Anthropic` API type
without it:

```bash
# Install the optional package first
pip install anthropic

# Then select the native Anthropic SDK API type
janito --provider deepseek --set api-type=Anthropic

# Per call
janito --provider deepseek --api-type Anthropic "Explain quantum computing"
```

### Reasoning Level

The default model `deepseek-flash` supports configurable reasoning depth via
the OpenAI-compatible `reasoning_effort` parameter. The supported levels are
`low`, `high` and `max` (the API's default is `high`; `medium`/`xhigh` are
mapped to `high` for compatibility, and `deepseek-v4-pro` currently supports
only `high`/`max`).

```bash
# Override the reasoning depth for a single call
janito --reasoning-effort max "Your prompt"

# Set a per-provider default in the config
janito --provider deepseek --set reasoning-effort=high
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > built-in default (none: the API's own default
`high` applies).

### Thinking Mode

DeepSeek models reason by default, so thinking mode is enabled out of the box
for the `deepseek` provider: every call sends
`extra_body={'enable_thinking': True}`. Pass `-t` / `--thinking` to force it
on for any provider.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=deepseek --set model=deepseek-flash
# Step 2: Store API key
janito --set-api-key="your-deepseek-api-key" --provider deepseek
# Step 3: Run prompt
janito "Explain quantum computing"
```

## MiniMax

Use MiniMax AI to access MiniMax models.

> **Get an API key:** Visit [MiniMax Open Platform](https://platform.minimax.io/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=minimax --set model=MiniMax-M3
# Step 2: Store API key
janito --set-api-key="your-minimax-api-key" --provider minimax
```

### API Types and Base URLs

The `minimax` provider supports the OpenAI-compatible **Completions** API type
(the built-in default) against the OpenAI-compatible base URL
`https://api.minimax.io/v1`, plus a native **Anthropic** SDK API type against
MiniMax's Anthropic-compatible base URL `https://api.minimax.io/anthropic`
(per-API-type endpoint, see `endpoint_by_api_type`).

The `anthropic` package is **optional**; janito aborts the change (with a
message naming the package) if you try to select the `Anthropic` API type
without it:

```bash
# Install the optional package first
pip install anthropic

# Then select the native Anthropic SDK API type
janito --provider minimax --set api-type=Anthropic

# Per call
janito --provider minimax --api-type Anthropic "Explain quantum computing"
```

### Thinking Mode

The default model `MiniMax-M3` reasons by default. Its OpenAI-compatible API
controls thinking with a structured `thinking` parameter
(`type` can be `disabled` or `adaptive`; `adaptive` is equivalent to thinking
on), so janito sends `extra_body={'thinking': {'type': 'adaptive'}}` out of
the box. Pass `-t` / `--thinking` to force thinking on for any provider.

### Popular Models

| Model | Description |
|-------|-------------|
| `MiniMax-M3` | Default model; reasoning by default (built-in) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=minimax --set model=MiniMax-M3
# Step 2: Store API key
janito --set-api-key="your-minimax-api-key" --provider minimax
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Meta (Muse Spark)

Use Meta Model API to access Muse Spark models.

> **Get an API key:** Visit [dev.meta.ai](https://dev.meta.ai/) to create an account and generate a Model API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=meta --set model=muse-spark-1.3
# Step 2: Store API key
janito --set-api-key="your-model-api-key" --provider meta
```

### API Types and Base URLs

Meta Model API is drop-in compatible with the OpenAI SDK: the single base
URL `https://api.meta.ai/v1` serves both the OpenAI-compatible **Responses**
API (the built-in default) and the **Chat Completions** API. The Chat
Completions API can be selected per provider or per call with:

```bash
# Per provider (persisted)
janito --provider meta --set api-type=Completions

# Per call
janito --provider meta --api-type completions "Your prompt"
```

### Stateless Responses Handling

Muse Spark's Responses endpoint is handled **statelessly**: janito re-sends
the full conversation as typed input items on every request and never
chains with `previous_response_id` (per [Meta's
docs](https://dev.meta.ai/docs/protocols/responses), the stateless
encrypted-replay path — `store: false` + `include:
reasoning.encrypted_content` — is the recommended agentic mode and cannot
be combined with `previous_response_id`). Every request sends:

- `store: false` — the server keeps no copy of the conversation;
- `include: ["reasoning.encrypted_content"]` — the chain of thought is only
  exposed in encrypted form; the `reasoning` output items returned in each
  response are replayed verbatim in the next request's `input`, preserving
  cross-turn reasoning for tool loops.

You can inspect the resolved mode with `janito --info` or `/status`
(`Stateless Mode: stateless (client re-sends history)`).

### Popular Models

| Model | Description |
|-------|-------------|
| `muse-spark-1.3` | Default model, trained for agentic workflows (1M context, built-in) |
| `muse-spark-1.3-contributor` | Cheaper contributor tier of the same model |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Reasoning Level

Muse Spark is a reasoning model: it works through a problem internally
before producing an answer. Reasoning depth is configured via the
OpenAI-compatible `reasoning_effort` parameter, which accepts `minimal`,
`low`, `medium` and `high` (Meta also accepts `xhigh`, but it maps to the
same reasoning strength as `high`).

```bash
# Override the reasoning depth for a single call
janito --reasoning-effort high "Your prompt"

# Set a per-provider default in the config
janito --provider meta --set reasoning-effort=medium
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > the API's own default (Meta has not
finalized its default effort, so janito declares none and the API's default
applies).

### Reasoning Summaries

The raw chain of thought stays private, but janito requests a
human-readable summary on the Responses API
(`reasoning.summary="auto"`, merged with `reasoning.effort` when set).
The summary streams as `response.reasoning_summary_text` deltas and is
shown in the reasoning panel (the existing `on_reasoning` observer). A
summary is optional: when the model does little reasoning the summary is
empty. Chat Completions has no reasoning summary.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=meta --set model=muse-spark-1.3
# Step 2: Store API key
janito --set-api-key="your-model-api-key" --provider meta
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Xiaomi (Mimo)

Use Xiaomi AI to access Mimo models.

> **Get an API key:** Visit [XiaoAI Open Platform](https://api.xiaomimimo.com/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=xiaomi --set model=mimo-v2.5
# Step 2: Store API key
janito --set-api-key="your-xiaomi-api-key" --provider xiaomi
```

### Popular Models

| Model | Description |
|-------|-------------|
| `mimo-v2.5` | Latest Xiaomi language model (default, built-in) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=xiaomi --set model=mimo-v2.5
# Step 2: Store API key
janito --set-api-key="your-xiaomi-api-key" --provider xiaomi
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Moonshot (Kimi)

Use Moonshot AI to access Kimi models.

> **Get an API key:** Visit [Moonshot AI Open Platform](https://platform.moonshot.cn/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=moonshot --set model=kimi-k3
# Step 2: Store API key
janito --set-api-key="your-moonshot-api-key" --provider moonshot
```

### Popular Models

| Model | Description |
|-------|-------------|
| `kimi-k3` | Latest Kimi model with configurable reasoning (default, built-in) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Reasoning Level

The default model `kimi-k3` supports configurable reasoning depth via the
OpenAI-compatible `reasoning_effort` parameter. The supported levels are
`low`, `high` and `max`, and the built-in default is `max` (the API's own
default).

```bash
# Override the reasoning depth for a single call
janito --reasoning-effort low "Your prompt"

# Set a per-provider default in the config
janito --provider moonshot --set reasoning-effort=high
```

Resolution order: `--reasoning-effort` > per-provider config value
(`--set reasoning-effort=...`) > built-in default (`max`).

### Example

```bash
# Step 1: Set provider and model
janito --set provider=moonshot --set model=kimi-k3
# Step 2: Store API key
janito --set-api-key="your-moonshot-api-key" --provider moonshot
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Z.AI (GLM)

Use Z.AI to access GLM models (Zhipu AI).

> **Get an API key:** Visit [Z.AI Open Platform](https://open.bigmodel.cn/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=zai --set model=glm-5.3-flash
# Step 2: Store API key
janito --set-api-key="your-zai-api-key" --provider zai
```

### Popular Models

| Model | Description |
|-------|-------------|
| `glm-5.3-flash` | GLM-5.3-Flash, the fast/cheap GLM-5 model (default, built-in) |
| `glm-5.3` | Full-size GLM-5.3 model |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=zai --set model=glm-5.3-flash
# Step 2: Store API key
janito --set-api-key="your-zai-api-key" --provider zai
# Step 3: Run prompt
janito "Explain quantum computing"
```

## xAI (Grok)

Use xAI to access Grok models.

> **Get an API key:** Visit [xAI Console](https://console.x.ai/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=xai --set model=grok-4.6
# Step 2: Store API key
janito --set-api-key="your-xai-api-key" --provider xai
```

### Popular Models

| Model | Description |
|-------|-------------|
| `grok-4.6` | Latest flagship model (default, built-in) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=xai --set model=grok-4.6
# Step 2: Store API key
janito --set-api-key="your-xai-api-key" --provider xai
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Anthropic (Claude)

Use Anthropic to access Claude models through their OpenAI-compatible API.

> **Get an API key:** Visit [Anthropic Console](https://console.anthropic.com/) to create an account and generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=anthropic --set model=claude-sonnet-5
# Step 2: Store API key
janito --set-api-key="your-anthropic-api-key" --provider anthropic
```

### Popular Models

| Model | Description |
|-------|-------------|
| `claude-fable-5-1` | Newest frontier model (1M context) |
| `claude-opus-5` | Highest capability model (1M context) |
| `claude-sonnet-5` | Latest flagship model (200K context; default) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Native Anthropic SDK (optional)

By default the `anthropic` provider talks to Anthropic's OpenAI-compatible
endpoint (`https://api.anthropic.com/v1/`) through the **Chat Completions**
API. A **native Anthropic SDK** API type (`Anthropic`) is also available: it
uses the official `anthropic` Python package against
`https://api.anthropic.com` (per-API-type endpoint, see
`endpoint_by_api_type`).

The `anthropic` package is **optional**; janito aborts the change (with a
message naming the package) if you try to select the `Anthropic` API type
without it:

```bash
# Install the optional package first
pip install anthropic

# Then select the native SDK API type
janito --provider anthropic --set api-type=Anthropic

# Per call
janito --provider anthropic --api-type Anthropic "Explain quantum computing"
```

### Example

```bash
# Step 1: Set provider and model
janito --set provider=anthropic --set model=claude-sonnet-5
# Step 2: Store API key
janito --set-api-key="your-anthropic-api-key" --provider anthropic
# Step 3: Run prompt
janito "Explain quantum computing"
```

## Apertus

Use Swisscom's OpenAI-compatible gateway to access Apertus models (Swiss AI
Initiative, e.g. Apertus 1.5 70B with a 262K-token context window).

> **Get an API key:** Visit [The Keymaker](https://keymaker.ai-weeks.ch/) to
> generate an API key.

### Configuration

```bash
# Step 1: Set provider and model
janito --set provider=apertus --set model=swiss-ai/Apertus-v1.5-70B
# Step 2: Store API key
janito --set-api-key="your-apertus-api-key" --provider apertus
```

### Popular Models

| Model | Description |
|-------|-------------|
| `swiss-ai/Apertus-v1.5-70B` | Apertus 1.5 70B via Swisscom (default, built-in) |

Model selection is restricted to the built-in models above.
`janito --list-models` shows the accepted names.

### Example

```bash
# Step 1: Set provider and model
janito --set provider=apertus --set model=swiss-ai/Apertus-v1.5-70B
# Step 2: Store API key
janito --set-api-key="your-apertus-api-key" --provider apertus
# Step 3: Run prompt
janito "Explain quantum computing"
```

## OpenRouter

Use [OpenRouter](https://openrouter.ai) to access models from many providers
(OpenAI, Anthropic, Google, Meta, DeepSeek, ...) behind a single
OpenAI-compatible endpoint.

> **Get an API key:** Visit [OpenRouter Keys](https://openrouter.ai/keys) to
> create an account and generate an API key.

### Configuration

Unlike most providers, OpenRouter has **no built-in default model** -- it
aggregates thousands of models, so janito cannot pick one for you. Its
provider config uses the `custom` placeholder as the default model, which is
**not** a real model name: you must supply the model explicitly, either per
call with `--model` or persistently in the config. As one of the two
providers without a built-in model list (`custom` is the other), OpenRouter
accepts **any** model name — the model-selection restriction that applies to
other providers (see the note at the top of this page) does not apply here:

```bash
# Step 1: Set provider and store the API key
janito --set provider=openrouter
janito --set-api-key="your-openrouter-api-key" --provider openrouter
# Step 2: Set a model (required -- no default)
janito --provider openrouter --set model=openrouter/auto
# Step 3: Run prompt
janito "Explain quantum computing"
```

If you try to start a session without a model, janito stops with an
actionable message instead of silently sending the placeholder to the API:

```
Error: No model configured for provider 'openrouter'. Pass --model <name> or set it with: janito --provider openrouter --set model=<name>
```

You can also pass a model per call without configuring one:

```bash
janito --provider openrouter --model anthropic/claude-3.5-sonnet "Hello"
```

OpenRouter model IDs use the `vendor/model` form (e.g.
`openrouter/auto`, `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`); the
`openrouter/auto` route picks the cheapest available model for your prompt.

### API Type

The `openrouter` provider talks to OpenRouter's OpenAI-compatible endpoint
(`https://openrouter.ai/api/v1`) through the standard **Chat Completions**
API, so its built-in API type is `Completions`.

## Provider Comparison

| Feature | OpenAI | Custom | Third-Party Providers |
|---------|--------|--------|-----------------------|
| Function Calling | ✅ | Depends on API | Depends on provider |
| Streaming | ✅ | Depends on API | Depends on provider |
| Vision | ✅ | Depends on API | Depends on provider |
| Context Window | Model-dependent (built-ins list exact limits) | Varies | Varies by model |

## Troubleshooting

### Connection Errors

- Verify the endpoint URL is correct (including `/v1` suffix)
- Check firewall settings
- Ensure the server is running (for local servers)

### Authentication Errors

- Verify your API key is correct
- Check if the API key has the necessary permissions
- Some local servers don't require an API key - try `--set-api-key="not-needed"`
