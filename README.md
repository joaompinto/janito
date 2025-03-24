# 🤖 Janito

Janito is a powerful AI-assisted command-line interface (CLI) tool built with Python, leveraging Anthropic's Claude for intelligent code and file management.

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/joaompinto/janito)

## ✨ Features

- 🧠 Intelligent AI assistant powered by Claude
- 📁 File management capabilities with real-time output
- 🔍 Smart code search and editing
- 💻 Interactive terminal interface with rich formatting
- 📊 Detailed token usage tracking and cost reporting with cache savings analysis
- 🌐 Web page fetching with content extraction capabilities
- 🔄 Parameter profiles for optimizing Claude's behavior for different tasks
- 📋 Line delta tracking to monitor net changes in files
- 💬 Conversation history with ability to resume previous conversations
- 🔇 Trust mode for concise output without tool details

## 🛠️ System Requirements

- **Python 3.8+** - Janito requires Python 3.8 or higher
- **Operating Systems**:
  - Linux/macOS: Native support
  - Windows: Requires Git Bash for proper operation of CLI tools
- **Anthropic API Key** - Required for Claude AI integration

## 🛠️ Installation

```bash
# Install directly from PyPI
pip install janito
```

### Setting up your API Key

Janito requires an Anthropic API key to function. You can:
1. Set the API key: `janito --set-api-key your_api_key`

For development or installation from source, please see [README_DEV.md](README_DEV.md).

## 🚀 Usage Tutorial

After installation, you can start using Janito right away. Let's walk through a simple tutorial:

### Getting Started

First, let's check that everything is working:

```bash
# Get help and see available commands
janito --help
```

### Tutorial: Creating a Simple Project

Let's create a simple HTML project with Janito's help:

After installing Janito, using your prefered editor and/or terminal, go to a new empty folder.

Use the janito command to create a new project.

```bash
# Step 1: Create a new project structure
janito "Create a simple HTML page with a calculator and 3 columns with text for the 3 main activities of the Kazakh culture"
```
Browse the resulting html page.

### Tutorial: Adding Features

Now, let's enhance our example

```bash
# Step 2: Add multiplication and division features
janito "Add some svg icons and remove the calculator"

```

Refresh the page

### Exploring More Features

Janito offers many more capabilities:

```bash
# Show detailed token usage and cost information
janito --show-tokens "Explain what is in the project"

# Use a specific parameter profile for creative tasks
janito --profile creative "Write a fun description for our project"

# Use trust mode for concise output without tool details
janito --trust "Optimize the HTML code"
# Or use the short alias
janito -t "Optimize the HTML code"

# Continue the most recent conversation
janito --continue "Please add one more line"

# Continue a specific conversation using its message ID
# (Janito displays the message ID after each conversation)
janito --continue 'abc123def' 'Let's refine that code'

# Alternative way to continue a specific conversation
janito --continue-id abc123def "Let's refine that code"

# Show current configuration and available profiles
janito --show-config

# You can press Ctrl+C at any time to interrupt a query
# Interrupted conversations can be continued with --continue
```

## 🔧 Available Tools

Janito comes with several built-in tools:
- 📄 `str_replace_editor` - View, create, and edit files
- 🔎 `find_files` - Find files matching patterns
- 🗑️ `delete_file` - Delete files
- 🔍 `search_text` - Search for text patterns in files
- 🌐 `fetch_webpage` - Fetch and extract content from web pages
- 📋 `move_file` - Move files from one location to another
- 💻 `bash` - Execute bash commands with real-time output display

## 📊 Usage Tracking

Janito includes a comprehensive token usage tracking system that helps you monitor API costs:

- **Basic tracking**: By default, Janito displays a summary of token usage and cost after each query
- **Detailed reporting**: Use the `--show-tokens` flag to see detailed breakdowns including:
  - Input and output token counts
  - Per-tool token usage statistics
  - Precise cost calculations
  - Cache performance metrics with savings analysis
  - Line delta tracking for file modifications

```bash
# Show detailed token usage and cost information
janito --show-tokens "Write a Python function to sort a list"

# Basic usage (shows simplified token usage summary)
janito "Explain Docker containers"

# Use trust mode for concise output without tool details
janito --trust "Create a simple Python script"
# Or use the short alias
janito -t "Create a simple Python script"
```

The usage tracker automatically calculates cache savings, showing you how much you're saving by reusing previous responses.

## 📋 Parameter Profiles

Janito offers predefined parameter profiles to optimize Claude's behavior for different tasks:

- **precise**: Factual answers, documentation, structured data (temperature: 0.2)
- **balanced**: Professional writing, summarization, everyday tasks (temperature: 0.5)
- **conversational**: Natural dialogue, educational content (temperature: 0.7)
- **creative**: Storytelling, brainstorming, marketing copy (temperature: 0.9)
- **technical**: Code generation, debugging, technical problem-solving (temperature: 0.3)

```bash
# Use a specific profile
janito --profile creative "Write a poem about coding"

# View available profiles
janito --show-config
```

## 🔇 Trust Mode

Janito offers a trust mode that suppresses tool outputs for a more concise execution experience:

### How It Works

- When enabled with `--trust` or `-t`, Janito suppresses informational and success messages from tools
- Only essential output and error messages are displayed
- The final result from Claude is still shown in full
- Trust mode is a per-session setting and not saved to your configuration

### Using Trust Mode

```bash
# Enable trust mode with the full flag
janito --trust "Create a Python script that reads a CSV file"

# Or use the short alias
janito -t "Create a Python script that reads a CSV file"
```

This feature is particularly useful for:
- Experienced users who don't need to see every step of the process
- Batch processing or scripting where concise output is preferred
- Focusing on results rather than the process
- Creating cleaner output for documentation or sharing

## 💬 Conversation History

Janito automatically saves your conversation history, allowing you to continue previous discussions:

### How It Works

- Each conversation is saved with a unique message ID in `.janito/last_messages/`
- The most recent conversation is also saved as `.janito/last_message.json` for backward compatibility
- After each conversation, Janito displays the command to continue that specific conversation

### Using the Continue Feature

```bash
# Continue the most recent conversation
janito --continue "Add more details to your previous response"

# Continue a specific conversation using its ID
janito --continue abc123def "Let's modify that code you suggested"
```

The `--continue` flag (or `-c` for short) allows you to:
- Resume the most recent conversation when used without an ID
- Resume a specific conversation when provided with a message ID
- Maintain context across multiple interactions for complex tasks

This feature is particularly useful for:
- Multi-step development tasks
- Iterative code improvements
- Continuing discussions after system interruptions
- Maintaining context when working on complex problems

## ⚙️ Dependencies

Janito automatically installs the following dependencies:
- typer (>=0.9.0) - For CLI interface
- rich (>=13.0.0) - For rich text formatting
- claudine - For Claude AI integration
- Additional packages for file handling and web content extraction

## 🛠️ Command-Line Options

Janito offers a variety of command-line options to customize its behavior:

```
--verbose, -v                 Enable verbose mode with detailed output
--show-tokens                 Show detailed token usage and pricing information
--workspace, -w TEXT          Set the workspace directory
--set-config TEXT             Configuration string in format 'key=value', e.g., 'temperature=0.7'
--show-config                 Show current configuration
--reset-config                Reset configuration by removing the config file
--set-api-key TEXT            Set the Anthropic API key globally in the user's home directory
--ask                         Enable ask mode which disables tools that perform changes
--trust, -t                   Enable trust mode which suppresses tool outputs for concise execution
--temperature FLOAT           Set the temperature for model generation (0.0 to 1.0)
--profile TEXT                Use a predefined parameter profile (precise, balanced, conversational, creative, technical)
--role TEXT                   Set the assistant's role (default: 'software engineer')
--version                     Show the version and exit
--continue, -c TEXT           Continue a previous conversation, optionally with a specific message ID
--help                        Show the help message and exit
```

## 🔑 API Key Configuration

You can configure your Anthropic API key in several ways:

```bash
# Option 1: Set as environment variable
export ANTHROPIC_API_KEY=your_api_key

# Option 2: Configure globally within Janito
janito --set-api-key your_api_key

# Option 3: Let Janito prompt you on first use
janito "Hello, I'm new to Janito!"
```

Your API key is securely stored and used for all future sessions.

## 💻 Development

For development instructions, please refer to [README_DEV.md](README_DEV.md).

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.