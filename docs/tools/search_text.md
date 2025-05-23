# Tool: search_text

**Description:**
Search for a text pattern in all files within one or more directories or file paths and return matching lines. Respects .gitignore.

| Argument     | Type           | Description |
|--------------|----------------|-------------|
| paths        | str            | String of one or more paths (space-separated) to search in. Each path can be a directory or a file. |
| pattern      | str            | Regex pattern or plain text substring to search for in files. Must not be empty. |
| is_regex     | bool, optional | If True, treat pattern as a regular expression. If False, always treat as plain text. Default is False. |
| max_depth    | int, optional  | Maximum directory depth to search. If 0 (default), search is recursive with no depth limit. If >0, limits recursion to that depth. Setting max_depth=1 disables recursion (only top-level directory). Ignored for file paths. |
| max_results  | int, optional  | Maximum number of results to return. 0 means no limit (default). |
| ignore_utf8_errors | bool, optional | If True, ignore utf-8 decode errors. Defaults to True. |
| **Returns**  | str            | Matching lines from files as a newline-separated string, or warning if pattern is empty. |

**Example usage:**
search_text(paths="src", pattern="def ", is_regex=False, max_depth=2, max_results=10, ignore_utf8_errors=True)

---
_generated by janito.dev_
