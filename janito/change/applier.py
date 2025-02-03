from typing import List, Dict, Optional
from pathlib import Path
from janito.config import config
from .finder import find_range, EditContentNotFoundError
from .instructions_parser import EditType, CodeChange
from .applied_blocks import AppliedBlock, AppliedBlocks
from rich.console import Console
import shutil
import os

class ChangeApplier:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.edits: List[CodeChange] = []
        self._last_changed_line = 0
        self.current_file = None
        self.current_content: List[str] = []
        self.applied_blocks = AppliedBlocks(blocks=[])
        self.console = Console()

    def _handle_find_error(self, content: List[str], edit: CodeChange, error: Exception) -> str:
        """Centralized error handling for find_range failures"""
        debug_file = self.target_dir / f"failed_debug_{edit.filename.name}"
        
        # Format debug content with clear sections
        debug_content = [
            "FIND:",
            *edit.original,
            "",  # Add blank line between sections
            "ORIGINAL:",
            *content,
            "",  # Add blank line before error
            "ERROR:",  # Add error section header
            str(error)  # Add error message in its own section
        ]
        
        debug_file.write_text('\n'.join(debug_content), encoding='utf-8')
        
        # Always print debug info with absolute path
        self.console.print("\n[red]Failed to find matching content[/red]")
        self.console.print(f"[yellow]Debug information saved to:[/yellow] {debug_file.absolute()}")
        if config.debug:
            self.console.print("[dim]Use the finder tool to analyze the failed match[/dim]")
        
        return f"Failed to find edit section in {edit.filename}: {str(error)}"

    def _create_applied_block(
        self,
        edit: CodeChange,
        original_content: List[str],
        modified_content: List[str],
        range_start: int,
        range_end: int,
        error_message: str = None,
        new_filename: str = None
    ) -> AppliedBlock:
        """Create an AppliedBlock with common parameters."""
        return AppliedBlock(
            filename=edit.filename,
            edit_type=edit.edit_type,
            reason=edit.reason,
            original_content=original_content,
            modified_content=modified_content,
            range_start=range_start,
            range_end=range_end,
            block_id=edit.block_id,
            lines_changed=abs(len(modified_content) - len(original_content)),
            error_message=error_message,
            has_error=bool(error_message),
            new_filename=new_filename
        )

    def _handle_move(self, edit: CodeChange) -> AppliedBlock:
        """Handle MOVE operation."""
        source_path = self.target_dir / edit.filename
        target_path = self.target_dir / edit.new_filename
        
        if not source_path.exists():
            error_msg = f"Cannot move non-existent file: {source_path}"
            return self._create_applied_block(
                edit=edit,
                original_content=[],
                modified_content=[],
                range_start=1,
                range_end=1,
                error_message=error_msg
            )
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(target_path)
        return self._create_applied_block(
            edit=edit,
            original_content=[],
            modified_content=[],
            range_start=1,
            range_end=1,
            new_filename=edit.new_filename
        )

    def _handle_create(self, edit: CodeChange) -> AppliedBlock:
        """Handle CREATE operation."""
        self.current_content = edit.modified
        return self._create_applied_block(
            edit=edit,
            original_content=[],
            modified_content=edit.modified,
            range_start=1,
            range_end=len(edit.modified)
        )

    def _handle_delete(self, edit: CodeChange) -> AppliedBlock:
        """Handle DELETE operation."""
        applied_block = self._create_applied_block(
            edit=edit,
            original_content=self.current_content,
            modified_content=[],
            range_start=1,
            range_end=len(self.current_content)
        )
        self.current_content = []
        return applied_block

    def _debug_log_find_result(self, edit: CodeChange, start_pos: int, found_range: tuple) -> None:
        """Log debug information about where content was found."""
        if config.debug:
            search_lines = len(edit.original)
            total_lines = len(self.current_content)
            lines_searched = total_lines - start_pos
            
            self.console.print(f"\n[dim]Finding in {edit.filename}:[/dim]")
            self.console.print(f"[dim]  Looking for {search_lines} line(s) in {lines_searched} remaining line(s)[/dim]")
            self.console.print(f"[dim]  Searched from line {start_pos + 1} to {total_lines}[/dim]")
            self.console.print(f"[dim]  Found at lines {found_range[0] + 1}-{found_range[1]} ({found_range[1] - found_range[0]} lines)[/dim]")
            if len(edit.original) > 1:
                self.console.print("[dim]  Content:[/dim]")
                for i, line in enumerate(edit.original):
                    self.console.print(f"[dim]    {found_range[0] + i + 1}: {line}[/dim]")

    def _handle_clean(self, edit: CodeChange) -> AppliedBlock:
        """Handle CLEAN operation."""
        try:
            start_range = find_range(self.current_content, edit.original, 0)
            self._debug_log_find_result(edit, 0, start_range)
            
            try:
                end_range = find_range(self.current_content, edit.modified, start_range[1])
                self._debug_log_find_result(edit, start_range[1], end_range)
            except EditContentNotFoundError:
                end_range = (start_range[1], start_range[1])
            
            section = self.current_content[start_range[0]:end_range[1]]
            applied_block = self._create_applied_block(
                edit=edit,
                original_content=section,
                modified_content=[],
                range_start=start_range[0] + 1,
                range_end=end_range[1]
            )
            self.current_content[start_range[0]:end_range[1]] = []
            self._last_changed_line = start_range[0]
            return applied_block
        except EditContentNotFoundError as e:
            error_msg = self._handle_find_error(self.current_content, edit, e)
            return self._create_applied_block(
                edit=edit,
                original_content=self.current_content,
                modified_content=[],
                range_start=1,
                range_end=len(self.current_content),
                error_message=error_msg
            )

    def _handle_edit(self, edit: CodeChange) -> AppliedBlock:
        """Handle EDIT operation."""
        try:
            if not edit.original:
                return self._handle_append(edit)
            edit_range = find_range(self.current_content, edit.original, 0)
            self._debug_log_find_result(edit, 0, edit_range)
            
            modified_content = self._adjust_indentation(edit, edit_range)
            original_content = self.current_content[edit_range[0]:edit_range[1]]
            
            applied_block = self._create_applied_block(
                edit=edit,
                original_content=original_content,
                modified_content=modified_content,
                range_start=edit_range[0] + 1,
                range_end=edit_range[0] + len(edit.original)
            )
            
            self._last_changed_line = edit_range[0] + len(edit.original)
            self.current_content[edit_range[0]:edit_range[1]] = modified_content
            return applied_block
            
        except EditContentNotFoundError as e:
            error_msg = self._handle_find_error(self.current_content, edit, e)
            return self._create_applied_block(
                edit=edit,
                original_content=edit.original,
                modified_content=edit.modified,
                range_start=self._last_changed_line + 1,
                range_end=self._last_changed_line + len(edit.original),
                error_message=error_msg
            )

    def _handle_append(self, edit: CodeChange) -> AppliedBlock:
        """Handle appending content to the end of file."""
        start_pos = len(self.current_content)
        self.current_content.extend(edit.modified)
        return self._create_applied_block(
            edit=edit,
            original_content=[],
            modified_content=edit.modified,
            range_start=start_pos + 1,
            range_end=start_pos + len(edit.modified)
        )

    def _adjust_indentation(self, edit: CodeChange, edit_range: tuple) -> List[str]:
        """Adjust indentation of modified content to match original."""
        original_section = self.current_content[edit_range[0]:edit_range[1]]
        first_line_original = original_section[0] if original_section else ""
        first_line_edit = edit.original[0] if edit.original else ""
        
        original_indent = len(first_line_original) - len(first_line_original.lstrip())
        edit_indent = len(first_line_edit) - len(first_line_edit.lstrip())
        
        if original_indent != edit_indent:
            indent_diff = original_indent - edit_indent
            if indent_diff > 0:
                return [" " * indent_diff + line for line in edit.modified]
        return edit.modified

    def _apply_and_collect_change(self, edit: CodeChange) -> AppliedBlock:
        """Apply a single edit and collect its change information."""
        handlers = {
            EditType.MOVE: self._handle_move,
            EditType.CREATE: self._handle_create,
            EditType.DELETE: self._handle_delete,
            EditType.CLEAN: self._handle_clean,
            EditType.EDIT: self._handle_edit
        }
        
        applied_block = handlers[edit.edit_type](edit)
        self.applied_blocks.blocks.append(applied_block)
        return applied_block

    def add_edit(self, edit: CodeChange) -> None:
        """Add an edit to be applied later."""
        self.edits.append(edit)

    def _save_debug_info(self, file_content: List[str], edit: CodeChange, error: Exception) -> None:
        """Save debug information when find_range fails."""
        debug_file = self.target_dir / 'failed_debug.txt'
        debug_content = [
            "FIND:",
            *edit.original,
            "\nORIGINAL:",
            *file_content,
            f"\nERROR: {str(error)}"
        ]
        debug_file.write_text('\n'.join(debug_content), encoding='utf-8')

    def apply(self) -> AppliedBlocks:
        """Apply all recorded edits and return the results."""
        self.current_file = None
        self.current_content = []
        self._last_changed_line = 0
        self.applied_blocks = AppliedBlocks(blocks=[])

        for edit in self.edits:
            # Handle file changes
            if self.current_file != edit.filename:
                # Save current file if it exists
                if self.current_file and self.current_content:
                    file_path = self.target_dir / self.current_file
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text('\n'.join(self.current_content) + '\n', encoding='utf-8')
                
                # Load new file
                self.current_file = edit.filename
                self._last_changed_line = 0
                
                if edit.edit_type not in [EditType.CREATE, EditType.MOVE]:
                    file_path = self.target_dir / edit.filename
                    if file_path.exists():
                        self.current_content = file_path.read_text(encoding='utf-8').splitlines()
                    else:
                        self.current_content = []
            
            # Apply the edit and collect change information
            self._apply_and_collect_change(edit)
            
            # Save file immediately for certain edit types
            if edit.edit_type in [EditType.CREATE, EditType.DELETE]:
                file_path = self.target_dir / edit.filename
                if edit.edit_type == EditType.CREATE:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                if self.current_content:
                    file_path.write_text('\n'.join(self.current_content) + '\n', encoding='utf-8')
                else:
                    if file_path.exists():
                        file_path.unlink()
        
        # Save the last file if there's content
        if self.current_file and self.current_content:
            file_path = self.target_dir / self.current_file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text('\n'.join(self.current_content) + '\n', encoding='utf-8')
        
        return self.applied_blocks