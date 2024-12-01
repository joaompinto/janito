
Janito is an open source Language-Driven Software Development Assistant powered by Claude AI. It helps developers understand, modify, and improve their Python code through natural language interaction.

## Features

- Natural language code interactions
- File system monitoring and auto-restart
- Interactive command-line interface 
- Workspace management and visualization
- History and session management
- Debug mode for troubleshooting
- Syntax error detection and fixing
- Python file execution
- File editing with system editor

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
- `.clear` - Clear console output
- `.debug` - Toggle debug mode  
- `.workspace` - Show workspace structure
- `.last` - Show last Claude response
- `.show <file>` - Show file content with syntax highlighting
- `.check` - Check workspace Python files for syntax errors
- `.p <file>` - Run a Python file
- `.python <file>` - Run a Python file (alias for .p)
- `.edit <file>` - Open file in system editor

### Input Formats

- `!request` - Request file changes (e.g. '!add logging to utils.py')  
- `request?` - Get information and analysis without changes
- `request` - General discussion and queries
- `$command` - Execute shell commands

## Configuration

Requires an Anthropic API key set via environment variable:

```bash
export ANTHROPIC_API_KEY='your_api_key_here'
```

## Development

The package consists of several modules:

- `janito.py` - Core functionality and CLI interface
- `change.py` - File modification and change tracking 
- `claude.py` - Claude API interaction
- `console.py` - Interactive console and command handling
- `commands.py` - Command implementations
- `prompts.py` - Prompt templates and builders
- `watcher.py` - File system monitoring
- `workspace.py` - Workspace analysis and management
- `xmlchangeparser.py` - XML parser for file changes
- `watcher.py` - File system monitoring

## License

MIT License