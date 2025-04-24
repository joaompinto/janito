# Tools Developer Guide

This guide explains how to add a new tool (functionality) to the project so it can be exposed to the agent and OpenAI-compatible APIs.

For a list of all built-in tools and their usage, see the [Tools Reference](../tools/tools-reference.md).
For a technical overview of the system, see the Architecture Guide in the documentation navigation.

## Requirements

- **Class-based tools:** All tools must be implemented as classes inheriting from `ToolBase` (see `janito/agent/tool_base.py`).
- **Type hints:** All parameters to the `call` method must have Python type hints.
- **Docstrings:**
  - The tool class must have a class-level docstring summarizing its purpose and behavior. This is user-facing.
  - The `call` method must have a Google-style docstring with a description for each parameter under an `Args:` section.
- **Parameter descriptions:** Every parameter must have a corresponding description in the docstring. If any are missing, registration will fail.

## Example: Creating a Tool

```python
from janito.agent.tool_base import ToolBase
from janito.agent.tool_registry import register_tool

@register_tool
class MyTool(ToolBase):
    """
    Processes a file a given number of times.
    """

    def call(self, filename: str, count: int) -> None:
        """
        Processes the specified file repeatedly.

        Args:
            filename (str): The path to the file to process.
            count (int): How many times to process the file.
        """
        # Implementation here
```

## Steps to Add a Tool

1. **Define your tool as a class** inheriting from `ToolBase`.
2. **Add a class-level docstring** summarizing the tool's purpose (user-facing).
3. **Implement the `call` method** with type hints and a Google-style docstring, including an `Args:` section describing every parameter.
4. **Register your tool** by decorating the class with `@register_tool` from `janito.agent.tool_registry`.
5. **Document your tool**: Update `janito/agent/tools/README.md` with a short description and usage for your new tool.

## Docstring Style

- Use the **Google style** for docstrings:

```python
"""
Function summary.

Args:
    param1 (type): Description of param1.
    param2 (type): Description of param2.
"""
```

- The `Args:` section must list each parameter, its type, and a description.
- The class docstring is prepended to the tool's description in the OpenAI schema and is user-facing.

## What Happens If You Omit a Description?

If you forget to document a parameter, you will see an error like:

```
ValueError: Parameter 'count' in tool 'MyTool' is missing a description in the docstring.
```

## Tool Reference

See the Tools Reference page in the documentation navigation for a list of built-in tools and their usage.

## Tool Call Limits

- You can use `--max-tools` to limit the total number of tool calls allowed in a chat session. If the limit is reached, further tool calls will be prevented.

## System Prompt Precedence

- If `--system-file` is provided, the file's content is used as the system prompt (highest priority).
- Otherwise, if `--system` or the config value is set, that string is used.
- Otherwise, a default prompt is used from the template at `janito/agent/templates/prompt_prompt_template.j2`.

## Interactive Shell Config Commands

Within the interactive chat shell, you can use special commands:
- `/config show` — Show effective configuration (local, global, defaults)
- `/config set local key=value` — Set a local config value
- `/config set global key=value` — Set a global config value
- `/continue` — Restore the last saved conversation
- `/start` — Reset conversation history
- `/prompt` — Show the current system prompt
- `/help` — Show help message

## Summary

- Always implement tools as classes inheriting from `ToolBase`.
- Provide type hints and parameter descriptions for the `call` method.
- Use Google-style docstrings for both the class and the `call` method.
- Registration will fail if any parameter is undocumented.
- Update the tools README after adding a new tool.

Happy coding!
