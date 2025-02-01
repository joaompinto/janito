from rich.console import Console
from rich.markdown import Markdown
from ..applied_blocks import AppliedBlocks
from .panels import create_diff_columns, create_header
from .summary import show_changes_summary
from .content import create_content_preview
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
from ..applied_blocks import AppliedBlock
from ..instructions_parser import EditType, CodeChange
from typing import List, Union

class ChangeViewer:
    def __init__(self):
        self.console = Console()
        
    def show(self, instructions: List[Union[str, CodeChange]], applied_blocks: AppliedBlocks):
        """Show instructions with their applied results.
        
        For each element in instructions:
        - If it's a string, show it as markdown
        - If it's a CodeChange, find and show the corresponding AppliedBlock
        """
        # Create lookup dict for applied blocks by block_id
        blocks_by_id = {block.block_id: block for block in applied_blocks.blocks}
        total_blocks = len(applied_blocks.blocks)
        shown_blocks = 0
        
        for item in instructions:
            if isinstance(item, str):
                # Show text as markdown
                self.console.print(Markdown(item))
            elif isinstance(item, CodeChange):
                # Find and show corresponding applied block
                if applied_block := blocks_by_id.get(item.block_id):
                    shown_blocks += 1
                    self._show_block(applied_block, shown_blocks, total_blocks)
                else:
                    # Show warning if no matching applied block found
                    self.console.print(Panel(
                        Text(f"⚠️ No result found for {item.edit_type.name} to {item.filename}", style="yellow"),
                        border_style="yellow"
                    ))
        
        # Show summary table at the end
        show_changes_summary(applied_blocks.get_changes_summary(), self.console)
        
    def _show_block(self, block: AppliedBlock, current_block: int, total_blocks: int):
        """Display a single change block with its details."""
        if block.has_error:
            # Show error message in red panel
            self.console.print(Panel(
                Text(f"❌ {block.error_message}", style="red"),
                title=f"Error applying changes to {block.filename}",
                border_style="red"
            ))
            return

        # Show the edit type
        edit_type_str = f"[bold]{block.edit_type.name}[/bold]"
        
        if block.edit_type == EditType.MOVE:
            self.console.print(f"\n{edit_type_str}: {block.filename} → {block.new_filename}")
            return
            
        if block.edit_type == EditType.DELETE:
            self.console.print(f"\n{edit_type_str}: {block.filename}")
            return

        if block.original_content and block.modified_content:
            # Show side-by-side diff for edits
            header, diff_columns = create_diff_columns(
                block.original_content,
                block.modified_content,
                filename=block.filename,
                start=block.range_start - 1,
                term_width=self.console.width,
                current_change=current_block,
                total_changes=total_blocks,
                edit_command=block.edit_type.name,
                reason=block.reason
            )
            self.console.print(header)
            self.console.print(diff_columns)
        else:
            # Show single panels for create/clean operations
            if block.original_content:
                self.console.print(Panel(
                    Syntax("\n".join(block.original_content), "python", theme="monokai"),
                    title="Original",
                    border_style="red"
                ))
            
            if block.modified_content:
                self.console.print(Panel(
                    Syntax("\n".join(block.modified_content), "python", theme="monokai"),
                    title="Modified",
                    border_style="green"
                ))
