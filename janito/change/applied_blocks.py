from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from .instructions_parser import EditType

@dataclass
class AppliedBlock:
    """Represents a block of code that has been modified by an edit operation.
    
    Attributes:
        filename: Path to the file that was edited
        edit_type: Type of edit operation performed (e.g. modify, move, delete)
        reason: Description of why this edit was made
        original_content: List of strings containing the original code lines
        modified_content: List of strings containing the modified code lines
        range_start: Line number in the original file where original_content starts (1-based,
                    converted from 0-based index returned by find_range).
                    Represents where the block was found in the full file before editing.
        range_end: Line number in the original file where original_content ends (1-based).
                  Together with range_start, defines the exact location where the block
                  was matched in the original file.
        error_message: Optional error message if the edit failed
        has_error: Boolean indicating if there was an error applying this edit
        new_filename: Optional new path for move operations
        block_id: Unique identifier for this edit block
        lines_changed: Number of lines that were modified in this edit
    """
    filename: Path
    edit_type: EditType
    reason: str
    original_content: List[str]
    modified_content: List[str]
    range_start: int
    range_end: int
    error_message: Optional[str] = None
    has_error: bool = False
    new_filename: Optional[Path] = None  # For move operations
    block_id: int = 0
    lines_changed: int = 0  # New field to store the number of lines changed

@dataclass
class AppliedBlocks:
    """Collection of AppliedBlock instances representing all edits in a change.
    
    Attributes:
        blocks: List of AppliedBlock instances
    """
    blocks: List[AppliedBlock]

    def __iter__(self):
        """Make AppliedBlocks iterable."""
        return iter(self.blocks)

    def get_changes_summary(self):
        """Get summary information for all applied blocks.
        
        Returns:
            List of dictionaries containing summary info for each block including:
            - file: Path to the edited file
            - type: Name of the edit type
            - reason: Reason for the edit
            - lines_original: Number of lines in original content
            - lines_modified: Number of lines in modified content 
            - range_start: Starting line number
            - range_end: Ending line number
            - block_id: Block identifier
            - new_filename: New path for move operations
            - has_error: Whether there was an error
            - error_message: Error message if any
            - lines_changed: Number of lines changed
        """
        return [{
            'file': block.filename,
            'type': block.edit_type.name,
            'reason': block.reason,
            'lines_original': len(block.original_content),
            'lines_modified': len(block.modified_content),
            'range_start': block.range_start,
            'range_end': block.range_end,
            'block_id': block.block_id,
            'new_filename': block.new_filename if block.edit_type == EditType.MOVE else None,
            'has_error': block.has_error,
            'error_message': block.error_message,
            'lines_changed': block.lines_changed
        } for block in self.blocks]