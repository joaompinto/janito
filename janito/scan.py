from pathlib import Path
from typing import List
from rich.console import Console
from rich.columns import Columns

def collect_files_content(paths: List[Path], workdir: Path) -> str:
    """Collect content from specified paths in XML format (non-recursive)"""
    content_parts = []
    file_items = []
    console = Console()
    
    def scan_path(path: Path) -> None:
        """Scan a single path and collect its contents (no recursion)"""
        try:
            try:
                display_path = path.relative_to(workdir)
            except ValueError:
                display_path = path

            # Add the file to analysis directly if it's a file
            if path.is_file():
                file_items.append(f"[cyan]•[/cyan] {display_path}")
                file_content = path.read_text()
                content_parts.append(f"<file>\n<path>{display_path}</path>\n<content>\n{file_content}\n</content>\n</file>")
                return

            # Handle directory scanning - skip only dot directories
            if path.is_dir() and not path.name.startswith('.'):
                file_items.append(f"[blue]•[/blue] {display_path}/")
                content_parts.append(f"<directory>{display_path}</directory>")
                
                # List immediate directory contents
                for item in path.iterdir():
                    try:
                        item_path = item.relative_to(workdir)
                    except ValueError:
                        item_path = item
                        
                    if item.is_file():
                        # Include all files, including dotfiles
                        file_items.append(f"[cyan]•[/cyan] {item_path}")
                        file_content = item.read_text()
                        content_parts.append(f"<file>\n<path>{item_path}</path>\n<content>\n{file_content}\n</content>\n</file>")
                    elif item.is_dir() and not item.name.startswith('.'):
                        file_items.append(f"[blue]•[/blue] {item_path}/")
                        content_parts.append(f"<directory>{item_path}</directory>")
                        
        except Exception as e:
            console = Console()
            console.print(f"[red]Warning: Could not read {path}: {e}[/red]")
    
    # Scan all provided paths
    for path in paths:
        scan_path(path)
    
    if file_items:
        console.print("\n[bold blue]Contents being analyzed:[/bold blue]")
        console.print(Columns(file_items, padding=(0, 4), expand=True))
    
    return "\n".join(content_parts)

def is_dir_empty(path: Path) -> bool:
    """Check if directory is empty, ignoring hidden files"""
    return not any(item for item in path.iterdir() if not item.name.startswith('.'))