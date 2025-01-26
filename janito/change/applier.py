from typing import List
from pathlib import Path
from janito.config import config
from .finder import find_range, EditContentNotFoundError
from .edit_blocks import EditType, CodeChange
from .applied_blocks import AppliedBlock, AppliedBlocks

class ChangeApplier:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.edits: List[CodeChange] = []
        self._last_changed_line = 0
        self.current_file = None
        self.current_content: List[str] = []
        self.applied_blocks = AppliedBlocks(blocks=[])

    def add_edit(self, edit: CodeChange):
        self.edits.append(edit)

    def start_file_edit(self, filename: str, edit_type: EditType):
        if self.current_file:
            self.end_file_edit()
        self._last_changed_line = 0
        self.current_file = filename
        self.current_edit_type = edit_type  # Store edit type for end_file_edit
        
        if edit_type == EditType.CREATE:
            self.current_content = []
        elif edit_type == EditType.DELETE:
            if not (self.target_dir / filename).exists():
                raise FileNotFoundError(f"Cannot delete non-existent file: {filename}")
            self.current_content = []
        else:
            self.current_content = (self.target_dir / filename).read_text(encoding="utf-8").splitlines()
    
    def end_file_edit(self):
        if self.current_file:
            target_path = self.target_dir / self.current_file
            if hasattr(self, 'current_edit_type') and self.current_edit_type == EditType.DELETE:
                if target_path.exists():
                    target_path.unlink()
            else:
                # Create parent directories if they don't exist
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text("\n".join(self.current_content), encoding="utf-8")
        self.current_file = None

    def apply(self):
        """Apply all edits and show summary of changes."""
        # Ensure target directory exists
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        current_file = None
        
        # Process edits in order as they were added
        for edit in self.edits:
            if current_file != edit.filename:
                if current_file is not None:
                    self.end_file_edit()
                self.start_file_edit(str(edit.filename), edit.edit_type)
                current_file = edit.filename
            self._apply_and_collect_change(edit)
        
        # Close the final file if there was one
        if current_file is not None:
            self.end_file_edit()

    def _apply_and_collect_change(self, edit: CodeChange) -> AppliedBlock:
        """Apply a single edit and collect its change information."""
        if edit.edit_type == EditType.CREATE:
            self.current_content = edit.modified
            applied_block = AppliedBlock(
                filename=edit.filename,
                edit_type=edit.edit_type,
                reason=edit.reason,
                original_content=[],
                modified_content=edit.modified,
                range_start=1,
                range_end=len(edit.modified),
                block_marker=edit.block_marker
            )

        elif edit.edit_type == EditType.DELETE:
            applied_block = AppliedBlock(
                filename=edit.filename,
                edit_type=edit.edit_type,
                reason=edit.reason,
                original_content=self.current_content,
                modified_content=[],
                range_start=1,
                range_end=len(self.current_content),
                block_marker=edit.block_marker
            )
            self.current_content = []

        elif edit.edit_type == EditType.CLEAN:
            try:
                start_range = find_range(self.current_content, edit.original, self._last_changed_line)
                try:
                    end_range = find_range(self.current_content, edit.modified, start_range[1])
                except EditContentNotFoundError:
                    end_range = (start_range[1], start_range[1])
                
                section = self.current_content[start_range[0]:end_range[1]]
                applied_block = AppliedBlock(
                    filename=edit.filename,
                    edit_type=edit.edit_type,
                    reason=edit.reason,
                    original_content=section,
                    modified_content=[],
                    range_start=start_range[0] + 1,
                    range_end=end_range[1],
                    block_marker=edit.block_marker
                )
                
                self.current_content[start_range[0]:end_range[1]] = []
                self._last_changed_line = start_range[0]
                
            except EditContentNotFoundError as e:
                error_msg = f"Failed to find clean section in {self.current_file}: {e}"
                applied_block = AppliedBlock(
                    filename=edit.filename,
                    edit_type=edit.edit_type,
                    reason=edit.reason,
                    original_content=self.current_content,
                    modified_content=[],
                    range_start=1,
                    range_end=len(self.current_content),
                    block_marker=edit.block_marker,
                    error_message=error_msg,
                    has_error=True
                )

        else:  # EDIT operation
            try:
                edit_range = find_range(self.current_content, edit.original, self._last_changed_line)
                original_section = self.current_content[edit_range[0]:edit_range[1]]
                
                applied_block = AppliedBlock(
                    filename=edit.filename,
                    edit_type=edit.edit_type,
                    reason=edit.reason,
                    original_content=original_section,
                    modified_content=edit.modified,
                    range_start=edit_range[0] + 1,
                    range_end=edit_range[0] + len(edit.original),
                    block_marker=edit.block_marker
                )
                
                self._last_changed_line = edit_range[0] + len(edit.original)
                self.current_content[edit_range[0]:edit_range[1]] = edit.modified
            except EditContentNotFoundError as e:
                error_msg = f"Failed to find edit section in {self.current_file}: {e}"
                applied_block = AppliedBlock(
                    filename=edit.filename,
                    edit_type=edit.edit_type,
                    reason=edit.reason,
                    original_content=edit.original,
                    modified_content=edit.modified,
                    range_start=self._last_changed_line + 1,
                    range_end=self._last_changed_line + len(edit.original),
                    block_marker=edit.block_marker,
                    error_message=error_msg,
                    has_error=True
                )

        self.applied_blocks.blocks.append(applied_block)
        return applied_block