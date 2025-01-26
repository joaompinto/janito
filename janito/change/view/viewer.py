from rich.console import Console
from ..applied_blocks import AppliedBlocks
from .panels import create_diff_columns
from .summary import show_changes_summary

class ChangeViewer:
    def __init__(self):
        self.console = Console()
        
    def show_changes(self, applied_blocks: AppliedBlocks):
        """Show all changes with diffs and summary"""
        for block in applied_blocks.blocks:
            self._show_block(block)
            
        # Show summary table
        show_changes_summary(applied_blocks.get_changes_summary(), self.console)
        
    def _show_block(self, block):
        """Show a single change block with appropriate visualization"""
        if block.edit_type.name == "CREATE":
            header, columns = create_diff_columns(
                [],  # No original content
                block.modified_content,
                str(block.filename),
                0,
                self.console.width
            )
        elif block.edit_type.name == "DELETE":
            header, columns = create_diff_columns(
                block.original_content,
                [],  # No modified content
                str(block.filename),
                0,
                self.console.width,
                is_removal=True
            )
        elif block.edit_type.name == "CLEAN":
            header, columns = create_diff_columns(
                block.original_content,
                [],  # No modified content for clean
                str(block.filename),
                block.range_start - 1,
                self.console.width,
                operation="Clean",
                reason=block.reason,
                is_removal=True
            )
        else:  # EDIT operation
            header, columns = create_diff_columns(
                block.original_content,
                block.modified_content,
                str(block.filename),
                block.range_start - 1,
                self.console.width,
                reason=block.reason
            )
            
        self.console.print(header)
        self.console.print(columns)