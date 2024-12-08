from pathlib import Path
from typing import List, Tuple, Optional
import tempfile
import shutil
import subprocess
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel
from rich import box
from datetime import datetime

from janito.fileparser import FileChange, validate_python_syntax
from janito.changeviewer import preview_all_changes
from janito.config import config
from janito.changehistory import get_history_file_path
from .applier import apply_single_change

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
            # Create backup before applying changes
            if config.verbose:
                console.print(f"[blue]Creating backup at:[/blue] {backup_dir}")
            shutil.copytree(workdir, backup_dir, ignore=shutil.ignore_patterns('.janito'))
            # Copy to preview directory, excluding .janito
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
            restore_script.chmod(0o755)  # Make script executable
            
            if config.verbose:
                console.print(f"[blue]Created restore script at:[/blue] {restore_script}")
        
    
    # Apply changes to preview directory
        any_errors = False
        for change in changes:
            console.print(f"[dim]Previewing changes for {change.path}...[/dim]")
            success, error = apply_single_change(change.path, change, workdir, preview_dir)
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

        # Validate Python syntax for all modified Python files
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

        # Final confirmation to apply to working directory
        if not Confirm.ask("\n[cyan bold]Apply previewed changes to working directory?[/cyan bold]"):
            console.print("\n[yellow]Changes were only previewed, not applied to working directory[/yellow]")
            console.print("[green]Changes are stored in the history directory and can be applied later using:[/green]")
            changes_file = get_history_file_path(workdir)
            console.print(f"[cyan]  {changes_file.relative_to(workdir)}[/cyan]")
            return False

        # Copy changes to actual files
        console.print("\n[blue]Applying changes to working directory...[/blue]")
        for change in changes:
            console.print(f"[dim]Applying changes to {change.path}...[/dim]")
            target_path = workdir / change.path
            
            if change.remove_file:
                if target_path.exists():
                    target_path.unlink()
                    console.print(f"[red]Removed {change.path}[/red]")
            else:
                preview_path = preview_dir / change.path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(preview_path, target_path)

        console.print("\n[green]Changes successfully applied to working directory![/green]")
        return True