from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from janito.config import config

def analyze_workspace_content(content: str) -> None:
    """Show statistics about the scanned content"""
    if not content:
        return

    # Collect include paths
    paths = []
    if config.include:
        for path in config.include:
            is_recursive = path in config.recursive
            path_str = str(path.relative_to(config.workspace_dir))
            paths.append(f"{path_str}/*" if is_recursive else f"{path_str}/")
    else:
        # Use workspace_dir as fallback when no include paths specified
        paths.append("./")

    console = Console()

    dir_counts: Dict[str, int] = defaultdict(int)
    dir_sizes: Dict[str, int] = defaultdict(int)
    file_types: Dict[str, int] = defaultdict(int)
    current_path = None
    current_content = []

    for line in content.split('\n'):
        if line.startswith('<path>'):
            path = Path(line.replace('<path>', '').replace('</path>', '').strip())
            current_path = str(path.parent)
            dir_counts[current_path] += 1
            file_types[path.suffix.lower() or 'no_ext'] += 1
        elif line.startswith('<content>'):
            current_content = []
        elif line.startswith('</content>'):
            content_size = sum(len(line.encode('utf-8')) for line in current_content)
            if current_path:
                dir_sizes[current_path] += content_size
            current_content = []
        elif current_content is not None:
            current_content.append(line)

    console = Console()

    # Directory statistics
    dir_stats = [
        f"📁 {directory}/ [{count} file(s), {_format_size(size)}]"
        for directory, (count, size) in (
            (d, (dir_counts[d], dir_sizes[d]))
            for d in sorted(dir_counts.keys())
        )
    ]

    # File type statistics
    type_stats = [
        f"📄 .{ext.lstrip('.')} [{count} file(s)]" if ext != 'no_ext' else f"📄 {ext} [{count} file(s)]"
        for ext, count in sorted(file_types.items())
    ]

    # Create grouped content with styled separators
    content_sections = []

    if paths:
        # Group paths with their stats
        path_stats = []
        for path in sorted(set(paths)):
            base_path = Path(path.rstrip("/*"))
            total_files = sum(1 for d, count in dir_counts.items()
                             if Path(d).is_relative_to(base_path))
            total_size = sum(size for d, size in dir_sizes.items()
                            if Path(d).is_relative_to(base_path))
            path_stats.append(f"{path} [{total_files} file(s), {_format_size(total_size)}]")

        content_sections.extend([
            "[bold yellow]📌 Included Paths[/bold yellow]",
            Rule(style="yellow"),
            Columns(path_stats, equal=True, expand=True),
            "\n"
        ])

    # Add directory structure section only in verbose mode
    if config.verbose:
        content_sections.extend([
            "[bold magenta]📂 Directory Structure[/bold magenta]",
            Rule(style="magenta"),
            Columns(dir_stats, equal=True, expand=True),
            "\n"
        ])

    # Always show file types section
    content_sections.extend([
        "[bold cyan]📑 File Types[/bold cyan]",
        Rule(style="cyan"),
        Columns(type_stats, equal=True, expand=True)
    ])

    content = Group(*content_sections)

    # Display workset analysis in panel
    console.print("\n")
    console.print(Panel(
        content,
        title="[bold blue]Workset Analysis[/bold blue]",
        title_align="center"
    ))

def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            break
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} {unit}"