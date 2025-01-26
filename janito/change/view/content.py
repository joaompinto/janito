from typing import Optional
from pathlib import Path
from rich.syntax import Syntax


# Mapping of file extensions to syntax lexer names
FILE_EXTENSION_MAP = {
    '.py': 'python',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.html': 'html',
    '.css': 'css',
    '.json': 'json',
    '.md': 'markdown',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.sh': 'bash',
    '.bash': 'bash',
    '.sql': 'sql',
    '.xml': 'xml',
    '.cpp': 'cpp',
    '.c': 'c',
    '.h': 'cpp',
    '.hpp': 'cpp',
    '.java': 'java',
    '.go': 'go',
    '.rs': 'rust',
}

def get_file_syntax(filepath: Path) -> Optional[str]:
    """Get syntax lexer name based on file extension.
    
    Args:
        filepath: Path object containing the file path
        
    Returns:
        String containing the syntax lexer name or None if not found
    """
    return FILE_EXTENSION_MAP.get(filepath.suffix.lower())

def create_content_preview(filepath: Path, content: str, is_new: bool = False) -> Syntax:
    """Create a preview with syntax highlighting using consistent styling

    Args:
        filepath: Path to the file being previewed
        content: Content to preview
        is_new: Whether this is a new file preview

    Returns:
        Syntax highlighted content
    """
    # Get file info
    syntax_type = get_file_syntax(filepath)

    # Create syntax highlighted content
    return Syntax(
        content,
        syntax_type or "text",
        theme="monokai",
        line_numbers=True,
        word_wrap=True,
        tab_size=4
    )