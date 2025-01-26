from rich.console import Console
from ..applied_blocks import AppliedBlocks
from .panels import create_diff_columns
from .summary import show_changes_summary
from .content import create_content_preview
from rich.text import Text

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
            # Create header
            header = Text()
            header_text = f"Create: {block.filename}"
            padding = (self.console.width - len(header_text)) // 2
            full_line = " " * padding + header_text + " " * (self.console.width - len(header_text) - padding)
            header.append(full_line, style="white on dark_green")
            header.append("\n")
            header.append("─" * self.console.width, style="dim")
            
            # Create content preview
            content = create_content_preview(
                block.filename,
                "\n".join(block.modified_content),
                is_new=True
            )
            
            self.console.print(header)
            self.console.print(content)
            
        elif block.edit_type.name == "DELETE":
            # Create header
            header = Text()
            header_text = f"Delete: {block.filename}"
            padding = (self.console.width - len(header_text)) // 2
            full_line = " " * padding + header_text + " " * (self.console.width - len(header_text) - padding)
            header.append(full_line, style="white on dark_red")
            header.append("\n")
            header.append("─" * self.console.width, style="dim")
            
            self.console.print(header)
            
        elif block.edit_type.name == "CLEAN":
            header, columns = create_diff_columns(
                block.original_content,
                [],  # No modified content for clean
                str(block.filename),
                block.range_start - 1,
                self.console.width,
                edit_command="Clean",
                reason=block.reason,
                is_removal=True
            )
            self.console.print(header)
            self.console.print(columns)
            
        else:  # EDIT operation
            header, columns = create_diff_columns(
                block.original_content,
                block.modified_content,
                str(block.filename),
                block.range_start - 1,
                self.console.width,
                edit_command="Edit",
                reason=block.reason
            )
            self.console.print(header)
            self.console.print(columns)