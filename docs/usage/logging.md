# Logging

janito provides logging options for debugging and troubleshooting.

## Enabling Logging

Use the `--log` flag to enable logging:

```bash
janito --log=info "Your prompt"
janito --log=debug "Your prompt"
janito --log=info,debug "Your prompt"
```

## Log Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `info` | General information | Show progress, tool usage |
| `debug` | Detailed debugging | Troubleshooting, development |
| `error` | Error messages only | Minimal output |
| `warning` | Warnings and errors | Catching issues |

## Multiple Levels

Enable multiple log levels by separating with commas:

```bash
janito --log=info,debug "Your prompt"
```

## Log Output

Logs are written to stderr, so they don't interfere with tool output or responses.

Example output:

```
[INFO] Initializing janito...
[DEBUG] Loading configuration from ~/.janito/config.json
[INFO] Using provider: openai
[DEBUG] API request: model=gpt-6-luna, tokens=150
[INFO] Processing tools...
```

## Debugging Tips

### Enable Full Debug Output

```bash
janito --log=debug "Your prompt" 2>&1 | head -100
```

### Save Logs to File

```bash
janito --log=debug "Your prompt" > output.txt 2> debug.log
```

### View Recent Logs

```bash
janito --log=info "Your prompt" | tee output.txt
```

## Common Issues to Debug

1. **API errors**: Use `--log=debug` to see request/response details
2. **Tool execution**: Use `--log=info` to see which tools are called
3. **Configuration issues**: Check if settings are loaded correctly
4. **MCP connections**: Enable debug logging to see MCP traffic
