# Tools Documentation

Tools provide a structured way to influence the model's behavior, enabling workflows that follow typical engineering patterns. By exposing explicit operations—such as file manipulation, code execution, or data retrieval—tools allow users to guide the assistant’s actions in a predictable and auditable manner.

# 🧰 Tools Reference

Janito uses these tools automatically based on your prompt and context. This table is for transparency and to help you understand what the agent can do.

| 🛠️ Tool              | 📝 Description                                                  | 🗝️ Key Arguments                                                                                       | 🔁 Returns                                  | 🗂️ Notes                                                                                   |
|-----------------------|------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|------------------------------------------|-----------------------------------------------------------------------------------------|
| **create_file**       | Create a new file, or overwrite if specified.                   | `path` (str): file path<br>`content` (str): file content<br>`overwrite` (bool, optional)<br>`backup` (bool, optional) | Success or error message                  | If `overwrite=True`, updates file if it exists. Can create backup before overwriting.   |
| **create_directory**  | Create a new directory at the specified path.                    | `path` (str): directory path<br>`overwrite` (bool, optional)                                       | Success or error message                  | Fails if directory exists unless overwrite is True.                                      |
| **fetch_url**         | Fetch and extract text from a web page.                          | `url` (str): web page URL<br>`search_strings` (list of str, optional)                               | Extracted text or warning                 | Useful for research or referencing online resources.                                    |
| **run_bash_command**  | Run a bash command and capture output.                           | `command` (str): bash command<br>`timeout` (int, optional)<br>`require_confirmation` (bool, opt.)   | File paths and line counts for output     | Requires bash (e.g., WSL or Git Bash on Windows). Use with caution.                     |
| **find_files**        | Search for files matching a pattern.                             | `directories` (list)<br>`pattern` (str)<br>`recursive` (bool, optional)                            | List of matching file paths               | Respects .gitignore.                                                                  |
| **get_file_outline**  | Get outline of a file's structure (classes, functions, etc.).    | `file_path` (str)                                                                                   | Outline summary                           | Useful for code navigation and analysis.                                               |
| **get_lines**         | Read lines or full content from a file.                          | `file_path` (str)<br>`from_line` (int, optional)<br>`to_line` (int, optional)                      | File content                              | Specify line range or omit for full content.                                              |
| **move_file**         | Move a file to a new location.                                   | `src_path` (str)<br>`dest_path` (str)<br>`overwrite` (bool, optional)<br>`backup` (bool, optional) | Success or error message                  | Can create backup before moving.                                                       |
| **remove_file**       | Remove a file.                                                   | `file_path` (str)<br>`backup` (bool, optional)                                                     | Success or error message                  | Can create backup before removing.                                                     |
| **remove_directory**  | Remove a directory (optionally recursively).                     | `directory` (str)<br>`recursive` (bool, optional)<br>`backup` (bool, optional)                     | Success or error message                  | Use recursive for non-empty dirs.                                                      |
| **replace_text_in_file** | Replace exact text in a file.                                 | `file_path` (str)<br>`search_text` (str)<br>`replacement_text` (str)<br>`replace_all` (bool, opt.) | Success or warning message                | Can replace all or first occurrence.                                                   |
| **validate_file_syntax** | Validate a file for syntax issues (Python, JSON, YAML).         | `file_path` (str): file path to validate                                                            | Syntax status or error message            | Supports .py/.pyw (Python), .json (JSON), .yml/.yaml (YAML). Returns error details.     |
| **run_python_command**| Execute Python code in a subprocess and capture output.          | `code` (str)<br>`timeout` (int, optional)                                                          | Output or file paths for output           | Useful for automation and testing.                                                     |
| **search_files**      | Search for a text pattern in files.                              | `directories` (list)<br>`pattern` (str)<br>`recursive` (bool, optional)                            | Matching lines from files                 | Respects .gitignore.                                                                  |
| **search_outline**    | Search for function/class/header names in file outlines.          | `directories` (list)<br>`pattern` (str)<br>`file_types` (list, optional)<br>`regex` (bool, optional)<br>`recursive` (bool, optional) | Summary of outline matches                | Fast context search for code and docs. Supports substring and regex.                   |
| **ask_user**          | Request clarification or input from the user interactively.      | `question` (str)                                                                                   | User response as a string                 | Used when agent needs explicit user input.                                              |
| **present_choices**   | Present a list of options to the user and return the selection.  | `prompt` (str)<br>`choices` (list)<br>`multi_select` (bool, optional)                              | Selected option(s)                        | Useful for interactive workflows.                                                      |
| **retrieve_memory**   | Retrieve a value previously stored using a key.                  | `key` (str)                                                                                        | Stored value or warning                   | Used for session memory and recall.                                                    |
| **store_memory**      | Store a value for later retrieval using a key.                   | `key` (str)<br>`value` (str)                                                                        | Success message or error                  | Used for session memory and recall.                                                    |
| **run_powershell_command** | Run a PowerShell command and capture output.                  | `command` (str)<br>`timeout` (int, optional)<br>`require_confirmation` (bool, optional)            | Output or file paths for output           | Windows only.                                                                         |

---

## Individual Tool Documentation

| Tool | Purpose |
|------|---------|
| [Ask User](ask_user.md) | Interactive user input |
| [Create Directory](create_directory.md) | Create a new directory |
| [Create File](create_file.md) | Create or overwrite a file |
| [Fetch URL](fetch_url.md) | Fetch and extract web page text |
| [Find Files](find_files.md) | Search for files matching a pattern |
| [Get File Outline](get_file_outline.md) | Outline of file structure |
| [Get Lines](get_lines.md) | Read lines or full content content |
| [Move File](move_file.md) | Move a file |
| [Present Choices](present_choices.md) | Present options to user |
| [Remove Directory](remove_directory.md) | Remove a directory |
| [Remove File](remove_file.md) | Remove a file |
| [Replace Text In File](replace_text_in_file.md) | Replace exact text in a file |
| [Retrieve Memory](retrieve_memory.md) | Retrieve stored value |
| [Run Bash Command](run_bash_command.md) | Run a bash command |
| [Run PowerShell Command](run_powershell_command.md) | Run a PowerShell command |
| [Run Python Command](run_python_command.md) | Run Python code |
| [Search Files](search_files.md) | Search for text in files |
| [Search Outline](search_outline.md) | Search for function/class/header names in outlines |
| [Search Text](search_text.md) | Search for text (deprecated/alias) |
| [Store Memory](store_memory.md) | Store a value for later |
| [Validate File Syntax](validate_file_syntax.md) | Validate file syntax |

---

For more details, see the codebase or tool docstrings.

# User-Level Control

Tools add a layer of user-level control over both the context and the actions performed by the model. This means users can:
- Directly specify which operations are available to the model.
- Constrain or extend the assistant’s capabilities to match project or organizational requirements.
- Observe and audit the assistant’s workflow, increasing transparency and trust.

# Limitations

While tools provide an extra level of control, the invocation of tools and their parameters are still delegated to the model’s inference process. This means:
- The model decides when and how to use tools, and may still make mistakes or select incorrect parameters.
- Tools do not prevent errors, but they do provide a framework for catching, constraining, or correcting them.

Tools are a key mechanism for aligning AI assistants with engineering best practices, offering both flexibility and oversight.

# Tools vs. Web Chat Agents

For a detailed comparison of how tool-based AI assistants like Janito differ from typical web chat agents, see [Janito vs Web Chat Agents](../about/vs_webchats.md). This page explains the interface, control, and transparency advantages of using tools for structured, auditable workflows.

---
_generated by janito.dev_
