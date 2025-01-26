from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from .edit_blocks import EditType

@dataclass
class AppliedBlock:
    filename: Path
    edit_type: EditType
    reason: str
    original_content: List[str]
    modified_content: List[str]
    range_start: int
    range_end: int
    block_marker: Optional[str] = None
    error_message: Optional[str] = None
    has_error: bool = False

@dataclass
class AppliedBlocks:
    blocks: List[AppliedBlock]
    
    def get_changes_summary(self):
        """Get summary info for all applied blocks"""
        return [{
            'file': block.filename,
            'type': block.edit_type.name,
            'reason': block.reason,
            'lines_original': len(block.original_content),
            'lines_modified': len(block.modified_content),
            'range_start': block.range_start,
            'range_end': block.range_end,
            'block_marker': block.block_marker
        } for block in self.blocks]