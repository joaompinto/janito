# Tool: run_bash_command

**Description:**
Execute a non-interactive command using the bash shell and capture live output. Requires bash to be installed and available in the system PATH.

| Argument   | Type | Description |
|------------|------|-------------|
| command    | str  | The bash command to execute. |
| timeout    | int, optional | Timeout in seconds for the command. Defaults to 60. |
| require_confirmation | bool, optional | If True, require user confirmation before running. Defaults to False. |
| requires_user_input | bool, optional | If True, warns that the command may require user input and might hang. Defaults to False. |
| **Returns**| str  | File paths and line counts for stdout and stderr, or warning if command is empty. |

**Example usage:**
run_bash_command(command="ls -l", timeout=30)

---
_generated by janito.dev_