"""
Applies file changes to preview directory and runs tests

The following situations should result in error:
- Creating a file that already exists
- Replace operation on a non-existent file
- Rename operation on a non-existent file
- Modify operation with search text not found
- Invalid regex pattern in modification
- No changes applied to a file
"""

from pathlib import Path
from typing import Tuple, Optional, List, Set
from rich.console import Console
from rich.panel import Panel
from rich import box
import subprocess
import re
import difflib
from .viewer import show_change_preview, preview_all_changes
from .parser import FileChange
from typing import Dict
import tempfile
import time

from janito.config import config
from .parser import FileChange
from .parser import Modification
from .validator import validate_python_syntax
from .position import find_text_positions
from .viewer import preview_all_changes
from .workdir import apply_changes as apply_to_workdir_impl

class ChangeApplier:
    def __init__(self, preview_dir: Path):
        self.preview_dir = preview_dir
        self.console = Console() if config.debug else None
        self.debug_counter = 0  # Add counter for unique filenames

    def validate_change(self, change: FileChange) -> Tuple[bool, Optional[str]]:
        """Validate a FileChange object before applying it"""
        if not change.path:
            return False, "File path is required"

        if change.operation not in ['create_file', 'replace_file', 'remove_file', 'rename_file', 'modify_file']:
            return False, f"Invalid operation: {change.operation}"

        if change.operation == 'rename_file' and not change.new_path:
            return False, "New file path is required for rename operation"

        if change.operation in ['create_file', 'replace_file']:
            if not change.content:
                return False, f"Content is required for {change.operation} operation"

        if change.operation == 'modify_file':
            if not change.modifications:
                return False, "Modifications are required for modify operation"
            for mod in change.modifications:
                if not mod.search_content:
                    return False, "Search content is required for modifications"

        return True, None

    def run_test_command(self, test_cmd: str) -> Tuple[bool, str, Optional[str]]:
        """Run test command in preview directory.
        Returns (success, output, error)"""
        try:
            result = subprocess.run(
                test_cmd,
                shell=True,
                cwd=self.preview_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            return (
                result.returncode == 0,
                result.stdout,
                result.stderr if result.returncode != 0 else None
            )
        except subprocess.TimeoutExpired:
            return False, "", "Test command timed out after 5 minutes"
        except Exception as e:
            return False, "", f"Error running test: {str(e)}"

    def apply_changes(self, changes: List[FileChange]) -> tuple[bool, Set[Path]]:
        """Apply changes in preview directory, runs tests if specified.
        Returns (success, modified_files)"""
        console = Console()
        
        # Validate all changes first
        for change in changes:
            is_valid, error = self.validate_change(change)
            if not is_valid:
                console.print(f"\n[red]Invalid change for {change.path}: {error}[/red]")
                return False, set()
        
        # Track modified files and apply changes
        modified_files: Set[Path] = set()
        for change in changes:
            if config.verbose:
                console.print(f"[dim]Previewing changes for {change.path}...[/dim]")
            success, error = self.apply_single_change(change)
            if not success:
                console.print(f"\n[red]Error previewing {change.path}: {error}[/red]")
                return False, modified_files
            if not change.operation == 'remove_file':
                modified_files.add(change.path)
            elif change.operation == 'rename_file':
                modified_files.add(change.new_path)

        # Validate Python syntax
        python_files = {f for f in modified_files if f.suffix == '.py'}
        for path in python_files:
            preview_path = self.preview_dir / path
            is_valid, error_msg = validate_python_syntax(preview_path.read_text(), preview_path)
            if not is_valid:
                console.print(f"\n[red]Python syntax validation failed for {path}:[/red]")
                console.print(f"[red]{error_msg}[/red]")
                return False, modified_files

        # Show success message with syntax validation status
        console.print("\n[cyan]Changes applied successfully.[/cyan]")
        if python_files:
            console.print(f"[green]✓ Python syntax validated for {len(python_files)} file(s)[/green]")
        
        # Run tests if specified
        if config.test_cmd:
            console.print(f"\n[cyan]Testing changes in preview directory:[/cyan] {config.test_cmd}")
            success, output, error = self.run_test_command(test_cmd)
            if output:
                console.print("\n[bold]Test Output:[/bold]")
                console.print(Panel(output, box=box.ROUNDED))
            if not success:
                console.print("\n[red bold]Tests failed in preview.[/red bold]")
                if error:
                    console.print(Panel(error, title="Error", border_style="red"))
                return False, modified_files

        return True, modified_files

    def apply_single_change(self, change: FileChange) -> Tuple[bool, Optional[str]]:
        """Apply a single file change to preview directory"""
        path = self.preview_dir / change.path
        
        # Ensure preview directory exists and file is copied before modifications
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy original file to preview directory if it doesn't exist and it's not a create operation
        if not path.exists() and change.operation != 'create_file':
            original_path = Path(change.path)
            if original_path.exists():
                if self.console:
                    self.console.print(f"[dim]Copying {original_path} to preview directory {path}[/dim]")
                path.write_text(original_path.read_text())
            else:
                if self.console:
                    self.console.print(f"[red]Original file not found: {original_path}[/red]")
                return False, f"Original file not found: {original_path}"

        # For replace operations, get original content before replacing
        if change.operation == 'replace_file': 
            if not path.exists():
                return False, f"Cannot replace non-existent file {path}"
            # Store original content in the change object for preview purposes
            current_content = path.read_text()
            change.original_content = current_content
            if change.content is not None:
                self._save_debug_content('replace.pre', path, current_content)
                self._save_debug_content('replace.post', path, change.content)
                path.write_text(change.content)
            return True, None
            
        # Handle preview-only operations
        if change.operation == 'remove_file':
            if path.exists():
                current_content = path.read_text()
                if self.console:
                    self._save_debug_content('remove.pre', path, current_content)
                path.unlink()
            return True, None

        if change.operation in ('create_file', 'replace_file'):
            path.parent.mkdir(parents=True, exist_ok=True)
            if change.operation == 'create_file' and path.exists():
                return False, f"Cannot create file {path} - already exists"
            if change.content is not None:
                path.write_text(change.content)
                self._save_debug_content('create.post', path, change.content)
            return True, None

        if change.operation == 'rename_file':
            new_preview_path = self.preview_dir / change.new_path
            new_preview_path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                return False, f"Cannot rename non-existent file {path}"
            current_content = path.read_text()
            if path.exists():
                self._save_debug_content('rename.pre', path, current_content)
                path.rename(new_preview_path)
                self._save_debug_content('rename.post', new_preview_path, current_content)
            return True, None

        # Handle modify operation
        if not path.exists():
            return False, f"Cannot modify non-existent file {path}"

        current_content = path.read_text()
        modified = current_content
        self._save_debug_content('modify.pre', path, current_content)  # Save initial state

        for mod in change.modifications:
            if self.console:
                self._print_modification_debug(mod)

            if mod.is_regex:
                try:
                    pattern = re.compile(mod.search_content, re.MULTILINE)
                except re.error as e:
                    return False, f"Invalid regex pattern: {str(e)}"
                found_text = pattern.search(modified)
                if not found_text:
                    content_with_ws = modified.replace(' ', '·').replace('\n', '↵\n')
                    line_count = len(modified.splitlines())
                    self.console.print(f"\n[yellow]File content ({line_count} lines, with whitespace):[/yellow]")
                    self.console.print(Panel(content_with_ws))
                    return False, f"Could not find search text in {path}, using regex pattern: {mod.search_content}"
                found_content = found_text.group(0)
            else:
                if mod.search_content not in modified:
                    content_with_ws = modified.replace(' ', '·').replace('\n', '↵\n')
                    line_count = len(modified.splitlines())
                    self.console.print(f"\n[yellow]File content ({line_count} lines, with whitespace):[/yellow]")
                    self.console.print(Panel(content_with_ws))
                    return False, f"Could not find search text in {path}"
                found_content = mod.search_content

            if mod.replace_content:
                # Update modified content without rereading from disk
                start, end = find_text_positions(modified, found_content)
                modified = modified[:start] + mod.replace_content + modified[end:]
                self._save_debug_content('modify.post', path, modified)
            else:
                # Delete case - Update modified content without rereading from disk
                start, end = find_text_positions(modified, found_content)
                self._save_debug_content('modify_delete.pre', path, modified)
                modified = modified[:start] + modified[end:]
                self._save_debug_content('modify_delete.post', path, modified)
                
        if modified == current_content:
            if self.console:
                self.console.print("\n[yellow]No changes were applied to the file[/yellow]")
            return False, "No changes were applied"
            
        if self.console:
            self.console.print("\n[green]Changes applied successfully[/green]")
            
        # Write final modified content only once at the end
        path.write_text(modified)
        return True, None

    def _print_modification_debug(self, mod: Modification) -> None:
        """Print debug information for a modification"""
        self.console.print("\n[cyan]Processing modification[/cyan]")
        search_text = mod.search_content.replace(' ', '·').replace('\n', '↵\n')
        line_count = len(mod.search_content.splitlines())
        self.console.print(f"[yellow]Search text ({line_count} lines, · for space, ↵ for newline):[/yellow]")
        self.console.print(Panel(search_text))
        
        if mod.replace_content is not None:
            replace_text = mod.replace_content.replace(' ', '·').replace('\n', '↵\n')
            replace_line_count = len(mod.replace_content.splitlines())
            self.console.print(f"[yellow]Replace with ({replace_line_count} lines, · for space, ↵ for newline):[/yellow]")
            self.console.print(Panel(replace_text))
        else:
            self.console.print("[yellow]Action:[/yellow] Delete text")

    def apply_to_workdir(self, changes: List[FileChange]) -> bool:
        """Apply changes from preview to working directory"""
        return apply_to_workdir_impl(changes, self.preview_dir, Console())

    def _save_debug_content(self, operation: str, filepath: Path, content: str) -> None:
        """Save content to temporary file for debugging"""
        if not self.console:
            return
            
        timestamp = int(time.time())
        self.debug_counter += 1
        temp_path = Path(tempfile.gettempdir()) / f"janito_debug_{timestamp}_{self.debug_counter}_{operation}_{filepath.name}"
        temp_path.write_text(content)
        self.console.print(f"[dim]Debug content saved to: {temp_path}[/dim]")

