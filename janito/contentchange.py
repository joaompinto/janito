from pathlib import Path
from typing import Dict, Tuple
from rich.console import Console
from datetime import datetime
from janito.fileparser import FileChange, parse_block_changes
from janito.changeapplier import preview_and_apply_changes

def get_file_type(filepath: Path) -> str:
    """Determine the type of saved file based on its name"""
    name = filepath.name.lower()
    if 'changes' in name:
        return 'changes'
    elif 'selected' in name:
        return 'selected'
    elif 'analysis' in name:
        return 'analysis'
    elif 'response' in name:
        return 'response'
    return 'unknown'

def save_changes_to_history(content: str, request: str, workdir: Path) -> Path:
    """Save change content to history folder with timestamp and request info"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # Already in the correct format
    history_dir = workdir / '.janito' / 'history'
    history_dir.mkdir(parents=True, exist_ok=True)
    
    # Create history entry with request and changes
    history_file = history_dir / f"changes_{timestamp}.txt"
    
    history_content = f"""Request: {request}
Timestamp: {timestamp}

Changes:
{content}
"""
    history_file.write_text(history_content)
    return history_file

def process_and_save_changes(content: str, request: str, workdir: Path) -> Tuple[Dict[Path, Tuple[str, str]], Path]:
    """Parse changes and save to history, returns (changes_dict, history_file)"""
    changes = parse_block_changes(content)
    history_file = save_changes_to_history(content, request, workdir)
    return changes, history_file

def validate_python_syntax(content: str, filepath: Path) -> Tuple[bool, str]:
    """Validate Python syntax and return (is_valid, error_message)"""
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"

def format_parsed_changes(changes: Dict[Path, Tuple[str, str]]) -> str:
    """Format parsed changes to show only file change descriptions"""
    result = []
    for filepath, (_, description) in changes.items():  # Updated tuple unpacking
        result.append(f"=== {filepath} ===\n{description}\n")
    return "\n".join(result)

def apply_content_changes(content: str, request: str, workdir: Path, test_cmd: str = None) -> Tuple[bool, Path]:
    """Regular flow: Parse content, save to history, and apply changes."""
    console = Console()
    changes = parse_block_changes(content)
    
    if not changes:
        console.print("\n[yellow]No file changes were found in the response[/yellow]")
        return False, None

    history_file = save_changes_to_history(content, request, workdir)
    success = preview_and_apply_changes(changes, workdir, test_cmd)
    return success, history_file

def handle_changes_file(filepath: Path, workdir: Path, test_cmd: str = None) -> Tuple[bool, Path]:
    """Replay flow: Load changes from file and apply them."""
    content = filepath.read_text()
    changes = parse_block_changes(content)
    
    if not changes:
        console = Console()
        console.print("\n[yellow]No file changes were found in the file[/yellow]")
        return False, None

    success = preview_and_apply_changes(changes, workdir, test_cmd)
    return success, filepath