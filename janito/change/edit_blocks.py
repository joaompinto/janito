from dataclasses import dataclass
from pathlib import Path
from enum import Enum, auto
from typing import List, Tuple, Dict
import string

class EditType(Enum):
    CREATE = auto()
    EDIT = auto()
    DELETE = auto()
    CLEAN = auto()

@dataclass
class CodeChange:
    filename: Path
    reason: str
    original: List[str]  # Changed from 'before'
    modified: List[str]  # Changed from 'after'
    edit_type: EditType = EditType.EDIT
    block_marker: str = None  # Track which code block this change came from

def parse_edit_command(line: str, command: str) -> tuple[Path, str]:
    """Parse an Edit or Create command line to extract filename and reason.
    Expected format: Command filename "reason" or Command `filename` "reason"
    Examples: 
        Edit path/to/file.py "Add new feature"
        Create `moving_ball.py` "Create main script"
    """
    if not line or not line.startswith(command):
        raise ValueError(f"Invalid command format in line:\n{line}\nExpected: {command} filename \"reason\"")
        
    # Split by quote to separate filename from reason
    parts = line.split('"')
    if len(parts) < 2:
        raise ValueError(f"Missing reason in quotes in line:\n{line}")
        
    # Extract and clean filename - handle both normal and markdown backtick formats
    filename_part = parts[0].replace(f"{command} ", "").strip()
    if filename_part.startswith('`') and filename_part.endswith('`'):
        filename_part = filename_part[1:-1]  # Remove backticks
    
    filename = Path(filename_part)
    reason = parts[1].strip()
    
    return filename, reason

def get_edit_blocks(response: str) -> Tuple[List[CodeChange], str]:
    """Parse response text into a list of CodeChange objects and annotated response.
    
    The format expected from the response follows the system prompt:
    
    Edit file "reason"
    <<<< original
    {original code}
    >>>> modified
    {modified code}
    ====
    
    Clean file "reason"
    <<<< starting
    {start marker lines}
    >>>> ending
    {end marker lines}
    ====
    """
    edit_blocks = []
    modified_response = []
    current_block = []
    original_content = None
    current_command = None
    marker_index = 0
    in_block = False

    for line in response.splitlines():
        # Handle command lines
        if line.startswith(("Edit ", "Create ", "Delete ", "Clean ")):
            command = line.split(" ")[0]
            filename, reason = parse_edit_command(line, command)
            current_command = command
            # Reset state for new command
            original_content = None
            current_block = []
            # Add marker for this edit block
            current_marker = string.ascii_uppercase[marker_index]
            modified_response.append(f"[Edit Block {current_marker}]")
            marker_index += 1
            continue
            
        # Add the line to modified_response unless we're in a code block or it's a block marker
        if not in_block and not line.startswith(("<<<< ", ">>>> ", "====")):
            modified_response.append(line)
            
        # Handle block markers - Update to match system prompt
        if line.startswith("<<<< original") or line.startswith("<<<< starting"):
            current_block = []
            in_block = True
            if current_command == "Clean":
                original_content = None
        elif line.startswith(">>>> modified") or line.startswith(">>>> ending"):
            if current_command == "Clean":
                original_content = current_block
            elif not original_content and current_block:
                original_content = current_block
            current_block = []
            in_block = True
        elif line == "====":  # End of edit block
            # Trim empty lines at start and end of blocks
            def trim_block(block: List[str]) -> List[str]:
                if not block:
                    return []
                # Remove empty lines at start and end
                while block and not block[0].strip():
                    block.pop(0)
                while block and not block[-1].strip():
                    block.pop()
                return block

            if current_command == "Delete":
                edit_blocks.append(CodeChange(filename, reason, [], [], EditType.DELETE, current_marker))
            elif current_command == "Clean":
                edit_blocks.append(CodeChange(
                    filename, reason,
                    trim_block(original_content or []),
                    trim_block(current_block),
                    EditType.CLEAN,
                    current_marker
                ))
            elif current_command == "Create":
                edit_blocks.append(CodeChange(
                    filename, reason,
                    [],
                    trim_block(current_block),
                    EditType.CREATE,
                    current_marker
                ))
            elif current_command == "Edit":
                original = trim_block(original_content or [])
                modified = trim_block(current_block)
                edit_blocks.append(CodeChange(
                    filename, reason,
                    original,
                    modified,
                    EditType.EDIT,
                    current_marker
                ))
            
            # Reset state after block is completed
            current_block = []
            in_block = False
            current_command = None
            original_content = None
        elif in_block:
            current_block.append(line)

    return edit_blocks, "\n".join(modified_response)