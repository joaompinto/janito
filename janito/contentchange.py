import re
from pathlib import Path
from typing import Dict, Any, List
import tempfile
import shutil
import ast
from rich.console import Console

def apply_file_changes(workdir: Path, change: Dict[str, Any]) -> None:
    """Apply a single file change from a block format"""
    filepath = workdir / change["filename"]
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Handle new file creation
    if "content" in change:
        if filepath.exists():
            raise FileExistsError(f"Cannot create file {filepath}: File already exists")
        filepath.write_text(change["content"])
        print(f"Created file: {filepath}")
        return
        
    # Handle modifications to existing files
    if filepath.exists():
        content = filepath.read_text()
    else:
        content = ""
        
    for c in change.get("changes", []):
        if c["type"] == "insert_after_content":
            content = content.replace(c["original"], c["original"] + "\n" + c["text"])
        elif c["type"] == "insert_before_content":
            content = content.replace(c["original"], c["text"] + "\n" + c["original"])
        elif c["type"] == "replace_content":
            content = content.replace(c["original"], c["text"])
        elif c["type"] == "delete_content":
            content = content.replace(c["original"], "")
            
    filepath.write_text(content)

def parse_block_changes(content: str) -> List[Dict[str, Any]]:
    """Parse block-format changes into the changes format"""
    # First check for error tags
    error_match = re.search(r'<error>(.*?)</error>', content, re.DOTALL)
    if error_match:
        raise ValueError(f"Error in changes: {error_match.group(1).strip()}")
    
    changes = []
    # Match blocks with UUID capture: ## <uuid> filename:operation ##
    block_pattern = r'##\s*([\w-]+)\s+(.*?):(.*?)\s*##(.*?)##\s*\1\s+end\s*##'
    blocks = re.finditer(block_pattern, content, re.DOTALL)
    
    for block in blocks:
        uuid = block.group(1)
        filename, operation = block.group(2).strip(), block.group(3).strip()
        block_content = block.group(4).strip()
        
        if operation == 'create_file':
            # For create_file, only look for new content
            new = re.search(
                fr'##\s*{uuid}\s+new\s*##(.*?)$',
                block_content,
                re.DOTALL
            )
            if new:
                changes.append({
                    "filename": filename,
                    "content": new.group(1).strip()
                })
        else:
            # For modifications, require both original and new
            original = re.search(
                fr'##\s*{uuid}\s+original\s*##(.*?)##\s*{uuid}\s+new\s*##',
                block_content,
                re.DOTALL
            )
            new = re.search(
                fr'##\s*{uuid}\s+new\s*##(.*?)$',
                block_content,
                re.DOTALL
            )
            if original and new:
                changes.append({
                    "filename": filename,
                    "changes": [{
                        "type": operation,
                        "original": original.group(1).strip(),
                        "text": new.group(1).strip()
                    }]
                })
    
    return changes

def validate_python_syntax(filepath: Path) -> tuple[bool, str]:
    """Validate Python file syntax using ast"""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read(), filename=str(filepath))
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in {filepath}: {str(e)}"
    except Exception as e:
        return False, f"Error validating {filepath}: {str(e)}"

def handle_changes_file(filepath: Path, workdir: Path) -> None:
    """Handle response file parsing and application"""
    try:
        content = filepath.read_text()
        
        try:
            changes = parse_block_changes(content)
        except ValueError as e:
            console = Console()
            console.print(f"\n[red]⚠️ {str(e)}[/red]")
            return
            
        console = Console()
        
        # Create preview directory and show changes
        with tempfile.TemporaryDirectory(prefix='preview_') as preview_dir:
            preview_path = Path(preview_dir)
            
            # Copy workdir contents to preview directory, excluding .git
            if workdir.exists():
                for item in workdir.iterdir():
                    if item.name != '.git':
                        if item.is_dir():
                            shutil.copytree(item, preview_path / item.name)
                        else:
                            shutil.copy2(item, preview_path / item.name)
            
            print(f"\nApplying changes to preview: {preview_path}")
            
            # Track modified/created files
            changed_files = set()
            for change in changes:
                changed_files.add(preview_path / change["filename"])
                apply_file_changes(preview_path, change)
            
            # Validate only modified/created Python files
            console.print("\n[bold]Validating modified Python files:[/bold]")
            has_errors = False
            for file_path in changed_files:
                if file_path.suffix == '.py':
                    is_valid, error = validate_python_syntax(file_path)
                    rel_path = file_path.relative_to(preview_path)
                    if is_valid:
                        console.print(f"[green]✓[/green] {rel_path}")
                    else:
                        console.print(f"[red]✗[/red] {rel_path}")
                        console.print(f"  [red]{error}[/red]")
                        has_errors = True
            
            if has_errors:
                console.print("\n[red]⚠️  Syntax errors found. Please check the preview directory and fix the issues.[/red]")
                return
                
            console.print("\n[green]✓ All modified Python files passed syntax validation[/green]")
            
            # Ask for confirmation with y/n prompt
            while True:
                response = input("\nApply changes to workspace? [y/n]: ").lower().strip()
                if response in ('y', 'n'):
                    break
                console.print("[yellow]Please answer 'y' or 'n'[/yellow]")
            
            if response == 'n':
                console.print("[yellow]Changes aborted[/yellow]")
                return
            
            # Only copy modified/created files back to workspace
            for file_path in changed_files:
                rel_path = file_path.relative_to(preview_path)
                target_path = workdir / rel_path
                
                # Create parent directories if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy the file
                shutil.copy2(file_path, target_path)
                console.print(f"[green]Updated:[/green] {rel_path}")
            
            console.print(f"[green]Changes applied to workspace:[/green] {workdir}")
            
    except Exception as e:
        print(f"Error applying changes: {e}")

def get_file_type(filepath: Path) -> str:
    """Determine the type of saved file based on its prefix"""
    name = filepath.name
    if name.startswith('changes_'):
        return 'changes'
    elif name.startswith('analysis_'):
        return 'analysis'
    elif name.startswith('selected_'):
        return 'selected'
    else:
        return 'unknown'