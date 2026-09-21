# Provider Variants

A **provider variant** is a second configuration for an already-supported
provider, named `<provider>-<word>` (e.g. `alibaba-tokenplan`). It lets you
run the same provider with different models, endpoints and API keys — for
example one Alibaba account billed per-token and another with a prepaid
token plan — without reconfiguring anything each time.

A variant **inherits** its base provider's built-in defaults (model,
endpoint, API types, token limits, reasoning level, thinking mode) and keeps
its own:

- per-variant model / endpoint / API type / tokens (`providers.<name>.*` in
  `config.json`), and
- its own API key (`auth.json`, keyed by the variant name).

After creation the variant name behaves like any provider: it is accepted by
`-p`/`--provider`, `--set provider=`, `--set-api-key` and every other
command, and it shows up in the web UI's provider combo and Settings drawer.
`janito --show-providers` lists it alongside the built-in providers, marked
with its base provider (e.g. `alibaba-tokenplan (variant of alibaba)`).

## Creating a variant

```bash
janito --create-variant alibaba-tokenplan
```

The name must follow the syntax `<provider>-<word>`: the part before the
first `-` must be a supported provider (the *base*), and the word is
user-defined (it may itself contain hyphens, e.g. `alibaba-token-plan`).
The variant is registered in `config.json` — as an entry of the `providers`
map, where the dash in its name identifies it as a variant among the
provider keys:

```json
{
  "providers": {
    "alibaba-tokenplan": {}
  }
}
```

## Configuring a variant

Once registered, configure it like any provider — the values are stored
under the variant's own keys:

```bash
# Per-variant model
janito --provider alibaba-tokenplan --set model=qwen3.8-flash

# Per-variant endpoint (e.g. a proxy or regional URL)
janito --provider alibaba-tokenplan --set endpoint=https://my-proxy.example.com/v1

# Per-variant API key
janito --set-api-key sk-xxx --provider alibaba-tokenplan

# Per-variant API type / tokens / reasoning
janito --provider alibaba-tokenplan --set api-type=Responses
janito --provider alibaba-tokenplan --set max-output-tokens=65536
janito --provider alibaba-tokenplan --set effort=medium
```

Everything you don't set falls back to the **base provider's** built-in
defaults. For example, `alibaba-tokenplan` without an explicit model uses
`qwen3.8-flash`, the `alibaba` provider's default.

A variant's model must be valid for its base provider: only the base's
built-in models are accepted (model-scoped settings are likewise restricted
to them) -- except `custom` variants, which accept any model name.

### Using a variant

```bash
# Single call
janito -p alibaba-tokenplan "Explain quantum computing"

# Make it the default provider
janito --set provider=alibaba-tokenplan

# Verify the resolution
janito --info
```

`--info` / `--show-config` and the shell `/status` command show the variant
name, its effective model, endpoint and masked API key, so a variant using
the wrong endpoint or a missing key is immediately visible.

### Custom-provider variants

The `custom` provider (any OpenAI-compatible endpoint) can have variants
too, e.g. `custom-local` for a local server and `custom-proxy` for a
third-party gateway — each with its own endpoint and model:

```bash
janito --create-variant custom-local
janito --provider custom-local --set endpoint=http://localhost:1234/v1
janito --provider custom-local --set model=my-local-model
janito --set-api-key not-needed --provider custom-local
```

## Deleting a variant

```bash
janito --delete-variant alibaba-tokenplan
```

Deleting a variant removes:

- its `providers` entry in `config.json` — the `providers.<name>`
  registration marker plus every per-variant config key stored under it
  (provider-scoped keys `model`, `endpoint`, and model-scoped keys `api-type`,
  tokens, reasoning level, stateless-mode under
  `providers.<name>.models.<model>.<key>`) — and
- its API key in `auth.json`.

janito **refuses** to delete the variant that is currently the configured
default provider — switch the default first (`janito --set provider=<name>`).

## Web UI

The web UI (alpha) does not create or delete variants — those operations are
CLI-only (`--create-variant` / `--delete-variant`). Registered variants
appear in the chat page's provider combo and in the Settings drawer's
provider list, where they can be configured (model, endpoint, API key) like
any other provider.

## Resolution order

For a variant `<base>-<word>`, values resolve as follows (later overrides
earlier):

1. Base provider's built-in defaults (from the provider's config entry read
   via `janito.providers.get_provider_config`, e.g. the
   `alibaba` entry: its `default_model` and the per-model `models` dict)
2. Per-variant configuration file values — provider-scoped
   (`providers.<base>-<word>.model` / `.endpoint`) and model-scoped
   (`providers.<base>-<word>.models.<model>.{api-type, max-output-tokens,
   max-input-tokens, effort, stateless-mode}`)
3. Command-line arguments (`--model`, `--provider`, `--set endpoint=...`)

The API key comes from `auth.json` under the variant name. See
[Configuration Priority](index.md#configuration-priority) for the general
resolution model.
