# Cloudflare Workers AI

Use Cloudflare Workers AI through Janito's existing `custom` provider and
the OpenAI-compatible **Chat Completions** API. No additional SDK or
first-class provider is required.

## Get an account ID and API token

1. Sign in to the [Cloudflare dashboard](https://dash.cloudflare.com/) and
   select your account.
2. Open **Workers AI → Use REST API**. Copy the **Account ID** (not a zone ID).
3. Select **Create a Workers AI API Token**, review the account scope, create
   the token and copy it. If you create a custom token instead, Cloudflare's
   REST guide requires **Workers AI – Read** and **Workers AI – Edit** permissions.

See Cloudflare's [REST API getting-started guide](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
for the current dashboard steps. Keep the token private: never commit it,
`auth.json`, or a populated configuration directory to source control.

## Configure Janito

The endpoint format is:

```text
https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
```

Replace `<ACCOUNT_ID>` below with your account ID. These commands change
the default provider to `custom` and replace its model and endpoint. If you
already use `custom` for another service, use a separate configuration
directory (`-c PATH` on **every** command) to keep that setup intact.

```bash
janito --set provider=custom --set model="@cf/openai/gpt-oss-20b"
janito --provider custom --set endpoint="https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1"
janito --provider custom --set api-type=Completions --set max-output-tokens=1024
```

Use `endpoint`, **not** `base-url`, as the Janito configuration key. Do not
append `/chat/completions` or use Cloudflare's native `/ai/run` endpoint;
Janito's OpenAI client appends the Chat Completions path itself.

Store the API token in a separate command. In Bash, read it without adding
the literal token to shell history:

```bash
read -r -s -p "Cloudflare API token: " CLOUDFLARE_API_TOKEN
janito --provider custom --set-api-key="$CLOUDFLARE_API_TOKEN"
unset CLOUDFLARE_API_TOKEN
```

Janito stores the token in `~/.janito/auth.json` and the provider settings
in `~/.janito/config.json` (or your `-c` directory). It does not automatically
read Cloudflare or OpenAI environment variables for authentication. As with
other `--set-api-key` commands, the expanded key is briefly a process argument;
run credential setup only on a trusted machine.

## Verify the setup

Inspect the non-secret settings, then make a minimal request without tools:

```bash
janito --provider custom --get endpoint model api-type
janito --provider custom --no-tools "Reply with a short greeting."
```

A streamed response verifies the configured route; a model's self-reported
identity is not proof of which provider served it. The request uses your
Workers AI allowance and may incur charges.

## Models and compatibility

- `@cf/openai/gpt-oss-20b` is an example text-generation model with function
  calling. Use the exact ID from the [Workers AI model catalog](https://developers.cloudflare.com/workers-ai/models/),
  including the `@cf/` prefix. Availability, limits and pricing can change.
- Janito streams responses, so use **Completions**. Cloudflare currently
  documents Responses only for GPT-OSS models and only with `stream: false`;
  that is not compatible with Janito's streaming Responses loop.
- OpenAI compatibility does not imply every OpenAI feature is supported.
  Streaming, tool/function calling, reasoning parameters and token limits
  depend on the model and endpoint. Start with `--no-tools`, then enable
  tools only for a model whose documented capabilities support them.
- A `401`/`403` usually calls for checking token permissions and account
  scope. A `404` can indicate an incorrect account ID, endpoint or model ID.
  For unsupported-parameter errors, check the model's capabilities and keep
  `api-type=Completions`; reduce `max-output-tokens` if necessary.

Official references:

- [OpenAI-compatible endpoints](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [GPT-OSS-20B model details](https://developers.cloudflare.com/workers-ai/models/gpt-oss-20b/)
- [Function calling](https://developers.cloudflare.com/workers-ai/function-calling/)
