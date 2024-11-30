
A Language-Driven Software Development Assistant powered by Claude AI that helps developers understand, modify, and improve their code through natural language interaction.

## Features

- Natural language code interactions
- File system monitoring and auto-reload
- Smart caching of responses
- Interactive command-line interface
- Workspace management and visualization
- History and session management
- Debug mode for troubleshooting

## Installation

```bash
# Install package
pip install janito
```

## Usage

Start Janito in your project directory:

```bash
python -m janito
```

Or launch with options:

```bash 
python -m janito --debug  # Enable debug mode
python -m janito --no-watch  # Disable file watching
```

### Commands

- `.help` - Show help information
- `.exit` - Exit the console
- `.clear` - Clear conversation history
- `.save` - Save history to file
- `.load` - Load history from file
- `.debug` - Toggle debug mode
- `.cache` - Clear response cache
- `.content` - Show current workspace content

### Input Formats

- `!request` - Request file changes (e.g. '!add logging to utils.py')
- `request?` - Get information without changes
- `request` - General queries to Janito

## Configuration

Requires an Anthropic API key set via environment variable:

```bash
export ANTHROPIC_API_KEY='your_api_key_here'
```

## Development

The package consists of several modules:

- `janito.py` - Core functionality and CLI interface
- `change.py` - File modification and change tracking
- `claude.py` - Claude API interaction and caching
- `error.py` - Error handling system
- `watcher.py` - File system monitoring

## License

MIT License