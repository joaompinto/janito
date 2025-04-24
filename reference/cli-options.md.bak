# 🏁 Runtime Command-Line Options

This page documents the command-line options that temporarily override configuration for a single session (do not persist changes to config files).

## 💡 Overview
These options are useful for one-off runs, scripting, or experimentation. They take precedence over config files for the current invocation only.

## ⚙️ Options

### --max-tokens
Set the maximum number of tokens for the model response.

```
janito "Your prompt here" --max-tokens 500
```

### --max-tools
Limit the number of tool calls allowed within a chat session.

```
janito "Prompt" --max-tools 3
```

### --model
Specify the model name for this session.

```
janito "Prompt" --model openai/gpt-4.1
```

### --max-rounds
Set the maximum number of agent rounds per prompt.

```
janito "Prompt" --max-rounds 10
```

### --system, --system-file, --role
Override the system prompt or role for this session.

```
janito "Prompt" --system "You are a helpful assistant."
janito "Prompt" --system-file my_prompt.txt
janito "Prompt" --role "expert Python developer"
```

### --temperature
Set the sampling temperature for the model.

```
janito "Prompt" --temperature 0.7
```

### --no-tools, --vanilla, --trust-tools
Control tool usage and output for the session.

```
janito "Prompt" --no-tools
janito "Prompt" --vanilla
janito "Prompt" --trust-tools
```

### --style
Set the interaction style for the system prompt template.

```
janito "Prompt" --style technical
```

### --stream, --verbose-stream
Enable streaming output from OpenAI and print raw chunks.

```
janito "Prompt" --stream
janito "Prompt" --verbose-stream
```

### --run-config
Set a runtime (in-memory only) config key-value pair. Can be repeated.

```
janito "Prompt" --run-config key1=val1 --run-config key2=val2
```

## 📝 Notes
- These options do NOT persist changes to your configuration files.
- For permanent changes, use `--set-local-config` or `--set-global-config`.
- See `--help` for the full list of options.
