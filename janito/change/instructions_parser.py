from dataclasses import dataclass
from pathlib import Path
from enum import Enum, auto
from typing import List, Tuple, Dict, Optional, Union
import string
from janito.config import config
from rich.console import Console
import re

"""
This parser is used to parse the response from the AI to extract the code changes.
It is used to extract the code changes from the AI response and create a list of CodeChange objects.

Example:

```
Lets change the main function to print "Hello, Space!" instead of "Hello, World!"

#### Edit `path/to/file.py` "Add new feature"
<<<< original
    print("Hello, World!")
>>>> modified
    print("Hello, Space!")
====
```

parser = InstructionsParser()
result = parser.parse(response)
print(result)

# result is list of objects of type str or CodeChage, for the previous example:
result = [ 'Lets change the main function to print "Hello, Space!" instead of "Hello, World!"',
            CodeChange(Path('path/to/file.py'), 'Add new feature', ['    print("Hello, World!")'], ['    print("Hello, Space!")'])
        ]
"""

class EditType(Enum):
    CREATE = auto()
    EDIT = auto()
    DELETE = auto()
    CLEAN = auto()
    MOVE = auto() 
    
@dataclass
class CodeChange:
    filename: Path
    reason: str
    original: List[str]
    modified: List[str]
    edit_type: EditType = EditType.EDIT
    new_filename: Path = None
    block_id: int = 0  # Renamed from id to block_id

class InstructionsParser:
    """Parser for edit blocks in AI responses."""
    
    COMMAND_PATTERNS = {
        "Edit": r"^#### Edit `[^`]+` \".*\"$",
        "Create": r"^#### Create `[^`]+` \".*\"$",
        "Delete": r"^#### Delete `[^`]+` \".*\"$",
        "Move": r"^#### Move `[^`]+` to `[^`]+` \".*\"$",
        "Clean": r"^#### Clean `[^`]+` \".*\"$"  # Add pattern for Clean command
    }

    def __init__(self):
        self.console = Console()
        self.current_block: List[str] = []
        self.original_content: Optional[List[str]] = None
        self.current_command: Optional[str] = None
        self.in_block = False
        self.current_line = 0
        self.filename: Optional[Path] = None
        self.new_filename: Optional[Path] = None
        self.reason: Optional[str] = None
        self.next_id: int = 1  # Add counter for generating IDs
        self.expecting_fence = False  # Add state for expecting code fence

    def parse_edit_command(self, line: str, command: str) -> Tuple[Union[Path, Tuple[Path, Path]], str]:
        """Parse an Edit command line to extract filename and reason.
        Example: #### Edit `path/to/file.py` "Add new feature"
        """
        if command == "Move":
            match = re.match(r'^#### Move `([^`]+)` to `([^`]+)` \"(.*)\"$', line)
            if not match:
                raise ValueError(f"Invalid Move command format: {line}")
            return (Path(match.group(1)), Path(match.group(2))), match.group(3)
        else:
            match = re.match(r'^#### \w+ `([^`]+)` \"(.*)\"$', line)
            if not match:
                raise ValueError(f"Invalid {command} command format: {line}")
            return Path(match.group(1)), match.group(2)

    def handle_block_markers(self, line: str) -> bool:
        """Handle block markers for original/modified content."""
        if line == "<<<< original":
            # Next line should be a code fence
            self.current_block = []
            self.in_block = True
            self.expecting_fence = True
            return True
        elif line == ">>>> modified":
            self.original_content = self.current_block
            self.current_block = []
            self.expecting_fence = True
            return True
        elif line == "====":
            self.in_block = False
            self.expecting_fence = False
            return True
        elif self.expecting_fence and line.startswith("```"):
            self.expecting_fence = False
            return True
        elif line.startswith("```") and not self.expecting_fence:
            # End of code block
            return True
        return False

    def parse(self, response: str) -> List[Union[str, CodeChange]]:
        """Parse response text into a list of strings and CodeChange objects."""
        result: List[Union[str, CodeChange]] = []
        lines = response.splitlines()
        current_text = []
        start_line = 1
        self.expecting_fence = False
        
        for i, line in enumerate(lines, 1):
            self.current_line = i - 1

            # Check for command pattern first
            if any(re.match(pattern, line.strip()) for pattern in self.COMMAND_PATTERNS.values()):
                # Add any collected text before this command
                if current_text and any(l.strip() for l in current_text):
                    text_block = '\n'.join(current_text)
                    if config.debug:
                        self.console.print(f"[blue]Lines {start_line}-{i-1}:[/] String ({len(current_text)} lines)")
                    result.append(text_block)
                
                # Reset text collection and start command handling
                current_text = []
                start_line = i
                
                for cmd, pattern in self.COMMAND_PATTERNS.items():
                    if re.match(pattern, line.strip()):
                        self.current_command = cmd
                        if cmd == "Move":
                            (old_file, new_file), reason = self.parse_edit_command(line, cmd)
                            self.filename = old_file
                            self.new_filename = new_file
                        else:
                            self.filename, reason = self.parse_edit_command(line, cmd)
                        self.reason = reason
                        self.in_block = True  # Start block mode immediately after command
                        break
                continue

            # Handle block content
            if self.in_block:
                if self.handle_block_markers(line):
                    if line == "====":
                        # Remove the filtering of empty lines
                        original = self.original_content if self.original_content else []
                        modified = self.current_block
                        
                        change = CodeChange(
                            self.filename,
                            self.reason,
                            original,
                            modified,
                            EditType[self.current_command.upper()],
                            self.new_filename,
                            block_id=self.next_id
                        )
                        if config.debug:
                            orig_lines = len(original) if original else 0
                            mod_lines = len(modified) if modified else 0
                            first_line = original[0][:50] + "..." if original else "(empty)"
                            self.console.print(
                                f"[blue]Lines {start_line}-{i}:[/] {self.current_command} block "
                                f"(id={self.next_id}, original={orig_lines}, modified={mod_lines} lines)\n"
                                f"[dim]  First: {first_line}[/dim]"
                            )
                        result.append(change)
                        self.next_id += 1
                        self.original_content = None
                        self.current_block = []
                        start_line = i + 1
                        self.in_block = False  # End block mode
                    continue
                # Only collect lines when not expecting/handling a fence
                if not self.expecting_fence:
                    self.current_block.append(line)
                continue

            # Collect text only when not in a block
            current_text.append(line)

        # Add any remaining text
        if current_text and any(l.strip() for l in current_text):
            text_block = '\n'.join(current_text)
            if config.debug:
                self.console.print(f"[blue]Lines {start_line}-{len(lines)}:[/] String ({len(current_text)} lines)")
            result.append(text_block)

        return result

def get_edit_blocks(response: str) -> List[Union[str, CodeChange]]:
    """Parse response text into a list of strings and CodeChange objects."""
    parser = InstructionsParser()
    return parser.parse(response)