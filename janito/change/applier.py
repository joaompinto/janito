from pathlib import Path
from typing import Tuple, Optional, Set
from rich.console import Console
from rich import box
from rich.panel import Panel
from rich.prompt import Confirm
from datetime import datetime
import subprocess
import shutil
import tempfile

from janito.fileparser import FileChange
from janito.config import config
from .position import find_text_positions, format_whitespace_debug
from .indentation import adjust_indentation
from typing import List
from ..changeviewer import preview_all_changes
from ..fileparser import validate_python_syntax
from ..changehistory import get_history_file_path


def run_test_command(preview_dir: Path, test_cmd: str) -> Tuple[bool, str, Optional[str]]:
    """Run test command in preview directory.
    Returns (success, output, error)"""
    try:
        result = subprocess.run(
            test_cmd,
            shell=True,
            cwd=preview_dir,
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

def preview_and_apply_changes(changes: List[FileChange], workdir: Path, test_cmd: str = None) -> bool:
    """Preview changes and apply if confirmed"""
    console = Console()
    
    if not changes:
        console.print("\n[yellow]No changes were found to apply[/yellow]")
        return False

    # Show change preview
    preview_all_changes(console, changes)

    with tempfile.TemporaryDirectory() as temp_dir:
        preview_dir = Path(temp_dir)
        console.print("\n[blue]Creating preview in temporary directory...[/blue]")
        
        # Create backup directory
        backup_dir = workdir / '.janito' / 'backups' / datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy existing files to preview directory
        if workdir.exists():
            if config.verbose:
                console.print(f"[blue]Creating backup at:[/blue] {backup_dir}")
            shutil.copytree(workdir, backup_dir, ignore=shutil.ignore_patterns('.janito'))
            shutil.copytree(workdir, preview_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.janito'))
            
            # Create restore script
            restore_script = workdir / '.janito' / 'restore.sh'
            restore_script.parent.mkdir(parents=True, exist_ok=True)
            script_content = f"""#!/bin/bash
# Restore script generated by Janito
# Restores files from backup created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# Exit on error
set -e

# Check if backup directory exists
if [ ! -d "{backup_dir}" ]; then
    echo "Error: Backup directory not found at {backup_dir}"
    exit 1
fi

# Restore files from backup
echo "Restoring files from backup..."
cp -r "{backup_dir}"/* "{workdir}/"

echo "Files restored successfully from {backup_dir}"
"""
            restore_script.write_text(script_content)
            restore_script.chmod(0o755)
            
            if config.verbose:
                console.print(f"[blue]Created restore script at:[/blue] {restore_script}")

        # Track modified files and apply changes to preview directory
        modified_files: Set[Path] = set()
        any_errors = False
        for change in changes:
            if config.verbose:
                console.print(f"[dim]Previewing changes for {change.path}...[/dim]")
            success, error = apply_single_change(change.path, change, workdir, preview_dir)
            if success and not change.remove_file:
                modified_files.add(change.path)
            if not success:
                if "file already exists" in str(error):
                    console.print(f"\n[red]Error: Cannot create {change.path}[/red]")
                    console.print("[red]File already exists and overwriting is not allowed.[/red]")
                else:
                    console.print(f"\n[red]Error previewing changes for {change.path}:[/red]")
                    console.print(f"[red]{error}[/red]")
                any_errors = True
                continue
        
        if any_errors:
            console.print("\n[red]Some changes could not be previewed. Aborting.[/red]")
            return False

        # Validate Python syntax
        python_files = {change.path for change in changes if change.path.suffix == '.py'}
        for filepath in python_files:
            preview_path = preview_dir / filepath
            is_valid, error_msg = validate_python_syntax(preview_path.read_text(), preview_path)
            if not is_valid:
                console.print(f"\n[red]Python syntax validation failed for {filepath}:[/red]")
                console.print(f"[red]{error_msg}[/red]")
                return False

        # Run tests if specified
        if test_cmd:
            console.print(f"\n[cyan]Testing changes in preview directory:[/cyan] {test_cmd}")
            success, output, error = run_test_command(preview_dir, test_cmd)
            
            if output:
                console.print("\n[bold]Test Output:[/bold]")
                console.print(Panel(output, box=box.ROUNDED))
            
            if not success:
                console.print("\n[red bold]Tests failed in preview. Changes will not be applied.[/red bold]")
                if error:
                    console.print(Panel(error, title="Error", border_style="red"))
                return False

        # Final confirmation
        if not Confirm.ask("\n[cyan bold]Apply previewed changes to working directory?[/cyan bold]"):
            console.print("\n[yellow]Changes were only previewed, not applied to working directory[/yellow]")
            console.print("[green]Changes are stored in the history directory and can be applied later using:[/green]")
            changes_file = get_history_file_path(workdir)
            console.print(f"[cyan]  {changes_file.relative_to(workdir)}[/cyan]")
            return False

        # Apply changes - copy each modified file only once
        console.print("\n[blue]Applying changes to working directory...[/blue]")
        for file_path in modified_files:
            console.print(f"[dim]Applying changes to {file_path}...[/dim]")
            target_path = workdir / file_path
            preview_path = preview_dir / file_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preview_path, target_path)
            
        # Handle file removals separately
        for change in changes:
            if change.remove_file:
                target_path = workdir / change.path
                if target_path.exists():
                    target_path.unlink()
                    console.print(f"[red]Removed {change.path}[/red]")

        console.print("\n[green]Changes successfully applied to working directory![/green]")
        return True

def apply_single_change(filepath: Path, change: FileChange, workdir: Path, preview_dir: Path) -> Tuple[bool, Optional[str]]:
    """Apply a single file change"""
    preview_path = preview_dir / filepath
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    
    if change.remove_file:
        orig_path = workdir / filepath
        if not orig_path.exists():
            return False, f"Cannot remove non-existent file {filepath}"
        if config.debug:
            console = Console()
            console.print(f"\n[red]Removing file {filepath}[/red]")
        # For preview, we don't create the file in preview dir
        return True, None
    
    if config.debug:
        console = Console()
        console.print(f"\n[cyan]Processing change for {filepath}[/cyan]")
        console.print(f"[dim]Change type: {'new file' if change.is_new_file else 'modification'}[/dim]")
    
    if change.is_new_file or change.replace_file:
        if change.is_new_file and filepath.exists():
            return False, "Cannot create file - already exists"
        if config.debug:
            action = "Creating new" if change.is_new_file else "Replacing"
            console.print(f"[cyan]{action} file with content:[/cyan]")
            console.print(Panel(change.content, title="File Content"))
        preview_path.write_text(change.content)
        return True, None
        
    orig_path = workdir / filepath
    if not orig_path.exists():
        return False, f"Cannot modify non-existent file {filepath}"
        
    content = orig_path.read_text()
    modified = content
    
    for search, replace, description in change.search_blocks:
        if config.debug:
            console.print(f"\n[cyan]Processing search block:[/cyan] {description or 'no description'}")
            console.print("[yellow]Search text:[/yellow]")
            console.print(Panel(format_whitespace_debug(search)))
            if replace is not None:
                console.print("[yellow]Replace with:[/yellow]")
                console.print(Panel(format_whitespace_debug(replace)))
            else:
                console.print("[yellow]Action:[/yellow] Delete text")
                
        positions = find_text_positions(modified, search)
        
        if config.debug:
            console.print(f"[cyan]Found {len(positions)} matches[/cyan]")
        
        if not positions:
            error_context = f" ({description})" if description else ""
            debug_search = format_whitespace_debug(search)
            debug_content = format_whitespace_debug(modified)
            error_msg = (
                f"Could not find search text in {filepath}{error_context}:\n\n"
                f"[yellow]Search text (with whitespace markers):[/yellow]\n"
                f"{debug_search}\n\n"
                f"[yellow]File content (with whitespace markers):[/yellow]\n"
                f"{debug_content}"
            )
            return False, error_msg
            
        # Apply replacements from end to start to maintain position validity
        for start, end in reversed(positions):
            if config.debug:
                console.print(f"\n[cyan]Replacing text at positions {start}-{end}:[/cyan]")
                console.print("[yellow]Original segment:[/yellow]")
                console.print(Panel(format_whitespace_debug(modified[start:end])))
                if replace is not None:
                    console.print("[yellow]Replacing with:[/yellow]")
                    console.print(Panel(format_whitespace_debug(replace)))
            
            # Adjust replacement text indentation
            original_segment = modified[start:end]
            adjusted_replace = adjust_indentation(original_segment, replace) if replace else ""
            
            if config.debug and replace:
                console.print("[yellow]Adjusted replacement:[/yellow]")
                console.print(Panel(format_whitespace_debug(adjusted_replace)))
                    
            modified = modified[:start] + adjusted_replace + modified[end:]
    
    if modified == content:
        if config.debug:
            console.print("\n[yellow]No changes were applied to the file[/yellow]")
        return False, "No changes were applied"
        
    if config.debug:
        console.print("\n[green]Changes applied successfully[/green]")
        
    preview_path.write_text(modified)
    return True, None