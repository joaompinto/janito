# Janito Architecture Overview

## High-Level Structure

Janito is a modular, extensible agent framework designed for interactive command-line and web-based chat environments. It emphasizes reliability, clear output, and easy extensibility through a tool/plugin system.

---

## Main Components

- **Agent Core**: Manages conversation state, message handling, and tool invocation. The core logic is distributed among three main classes:
    - **ConversationHandler**: Handles the flow of conversation, manages state, and processes each turn.
    - **Agent**: Integrates with LLM providers (e.g., OpenAI), sends/receives messages, and tracks usage.
    - **AgentProfileManager**: Loads and manages agent profiles, prompt templates, and role configuration.
- **Tools System**: Tools are registered via decorators and implement a standard interface for agent calls (see the Tools Reference).
- **Message Handling**: All user and agent output is routed through a unified Rich-based message handler for consistent, styled output across CLI and web interfaces.
- **CLI Chat Shell**: Provides an interactive prompt using `prompt_toolkit`, with session management, command parsing, and real-time output.
- **Web App (optional)**: Shares the same agent and message handler logic for a consistent experience in browser-based chat.

---

## Message Flow

1. **User Input**: Captured via CLI or web UI.
2. **Agent Processing**: ConversationHandler receives input, updates conversation state, and determines if a tool should be invoked. The Agent class handles LLM communication, and AgentProfileManager provides prompt context.
3. **Tool Invocation**: If needed, the agent calls a registered tool, passing arguments and receiving output.
4. **Output Routing**: All outputs (including tool results, errors, and info) are sent through the Rich message handler, which formats and displays them appropriately.
5. **History & State**: Conversation and input history are saved for session continuity.

---

## Extensibility

- **Adding Tools**: Implement a subclass of `ToolBase` and register it with `@register_tool`. Tools can report info, success, error, stdout, and stderr via the message handler.
- **Output Customization**: The Rich message handler can be extended for new message types or output styles.

---

## Key Technologies

- **Python** (core language)
- **Rich** (for styled console output)
- **prompt_toolkit** (for advanced CLI interactivity)

---

## Notable Design Decisions

- Unified output handling with Rich for both CLI and web.
- Process tracking and robust error handling in tools (e.g., Bash tool).
- Simple, decorator-based tool registration for easy extensibility.

---

For more details, see the Developer Guide and janito/agent/ source files.
