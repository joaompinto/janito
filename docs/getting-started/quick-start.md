# Quick Start

This guide gets you up and running with janito in minutes.

## 1. Configure Your Settings

The first time you run janito, you'll need to configure your API settings. You can do this interactively or with command-line flags.

### Interactive Configuration

Run the configuration wizard:

```bash
janito --config
```

You'll be prompted for:

| Setting | Description | Example |
|---------|-------------|---------|
| **Provider** | Your API provider, selected from a list | `openai`, `custom` |
| **API Key** | Your API key (masked for security) | `sk-xxxxxxxxxxxxxxxx` |
| **Model** | Model name to use | `gpt-6-luna`, `claude-sonnet-5` |
| **Max Output Tokens** | Maximum output tokens (default: 65536) | `65536` |
| **Max Input Tokens** | Maximum input tokens / context window (default: 128000) | `128000` |

### Quick Configuration with Flags

Set options directly from the command line. Note that `--set` and `--set-api-key` must be used in **separate commands**:

```bash
# OpenAI example (two steps: config, then API key)
janito --set provider=openai --set model=gpt-6-luna
janito --set-api-key="sk-your-key" --provider openai

# Local LLM example (local servers use the `custom` provider + endpoint)
janito --set provider=custom --set endpoint="http://localhost:1234/v1" --set model="local-model"
janito --set-api-key="not-needed" --provider custom
```

## 2. Run Your First Prompt

### Single Prompt

```bash
janito "What is the capital of France?"
```

### Interactive Chat

```bash
janito
```

Type your messages and press Enter. Commands:

| Command | Description |
|---------|-------------|
| `/exit` | End the session |
| `clear` | Clear conversation and start a new one |
| `Ctrl+D` / `Ctrl+Z` | Exit the shell (EOF) |
| `/help` | List all commands (with descriptions), tool modes and shortcuts |

For the full list of chat commands, see [Interactive Mode](../usage/interactive-mode.md).

### Pipe Input

```bash
echo "Tell me a joke" | janito
```

## 3. View Your Configuration

```bash
janito --show-config
```

## Examples

### OpenAI

```bash
# Step 1: Set provider and model
janito --set provider=openai --set model=gpt-6-luna
# Step 2: Store API key
janito --set-api-key="sk-your-key" --provider openai
# Step 3: Run prompt
janito "Explain quantum computing"
```

### Local LLM (LM Studio, Ollama)

Local servers are reached through the `custom` provider, which requires an
endpoint (`--set endpoint=...`):

```bash
# Step 1: Set provider, endpoint, and model
janito --set provider=custom \
        --set endpoint="http://localhost:1234/v1" \
        --set model="local-model"
# Step 2: Store placeholder API key
janito --set-api-key="not-needed" --provider custom
# Step 3: Run prompt
janito "What is 2+2?"
```

### Custom Provider

```bash
# Step 1: Set provider, endpoint, and model
janito --set provider=custom --set endpoint="http://localhost:8000/v1" --set model="my-model"
# Step 2: Run prompt
janito "Hello"
```

## What's Next?

- Learn about [interactive chat mode](../usage/interactive-mode.md)
- Explore [built-in tools](../tools/index.md)
- Set up the [OneDrive plugin](../PLUGINS.md) or install the [Gmail plugin](../PLUGINS.md)
- Connect to [MCP servers](../tools/mcp.md)
