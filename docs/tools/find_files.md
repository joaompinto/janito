# Tool: find_files

**Description:**
Find files in one or more directories matching a pattern. Respects .gitignore.

| Argument     | Type           | Description |
|--------------|----------------|-------------|
| paths        | str            | String of one or more paths (space-separated) to search in. Each path can be a directory. |
| pattern      | str            | File pattern to match. Uses Unix shell-style wildcards. |
| max_depth    | int, optional  | Maximum directory depth to search. If None, unlimited recursion. If 0, only the top-level directory. If 1, only the root directory (matches 'find . -maxdepth 1'). |
| **Returns**  | str            | Newline-separated list of matching file paths, or warning if pattern is empty. |

**Example usage:**
find_files(paths="src tests", pattern="*.py", max_depth=2)

---
_generated by janito.dev_