from rich.traceback import install
install(show_locals=False)

from pathlib import Path
from typing import List, Set
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from janito.config import config
from .models import FileInfo, ScanPath
from .stats import collect_file_stats, _format_size 


def show_workset_analysis(
    files: List[FileInfo],
    scan_paths: List[ScanPath],
    cache_blocks: List[List[FileInfo]] = None
) -> None:
    """Display analysis of workspace content and configuration."""

    console = Console()
    content_sections = []

    # Get statistics
    dir_counts, file_types = collect_file_stats(files)

    # Calculate path stats using relative paths
    paths_stats = []
    total_files = 0
    total_size = 0

  
    # Process all paths uniformly
    for scan_path in sorted(scan_paths, key=lambda p: p.path):

        path = scan_path.path
        is_recursive = scan_path.is_recursive
        path_str = str(path)

        # Calculate stats based on scan type
        if is_recursive:
            path_files = sum(count for d, [count, _] in dir_counts.items()
                           if Path(d) == path or Path(d).is_relative_to(path))
            path_size = sum(size for d, [_, size] in dir_counts.items()
                          if Path(d) == path or Path(d).is_relative_to(path))
        else:
            path_files = dir_counts.get(path_str, [0, 0])[0]
            path_size = dir_counts.get(path_str, [0, 0])[1]

        total_files += path_files
        total_size += path_size

        paths_stats.append(
            f"[bold cyan]{path}[/bold cyan]"
            f"[yellow]{'/**' if is_recursive else '/'}[/yellow] "
            f"[[green]{path_files}[/green] "
            f"{'total ' if is_recursive else ''}file(s), "
            f"[blue]{_format_size(path_size)}[/blue]]"
        )

    # Build sections - Show paths first
    if paths_stats:
        content_sections.extend([
            "[bold yellow]📌 Included Paths[/bold yellow]",
            Rule(style="yellow"),
        ])

        content_sections.append(
            Text(" | ").join(Text.from_markup(path) for path in paths_stats)
        )

        # Add total summary if there are multiple paths
        if len(paths_stats) > 1:
            content_sections.extend([
                "",  # Empty line for spacing
                f"[bold yellow]Total:[/bold yellow] [green]{total_files}[/green] files, "
                f"[blue]{_format_size(total_size)}[/blue]"
            ])
        content_sections.append("\n")

    # Then show directory structure if verbose
    if config.verbose:
        dir_stats = [
            f"📁 {directory}/ [{count} file(s), {_format_size(size)}]"
            for directory, (count, size) in sorted(dir_counts.items())
        ]
        content_sections.extend([
            "[bold magenta]📂 Directory Structure[/bold magenta]",
            Rule(style="magenta"),
            Columns(dir_stats, equal=True, expand=True),
            "\n"
        ])

    type_stats = [
        f"[bold cyan].{ext.lstrip('.')}[/bold cyan] [[green]{count}[/green] file(s)]" 
        if ext != 'no_ext' 
        else f"[bold cyan]no ext[/bold cyan] [[green]{count}[/green] file(s)]"
        for ext, count in sorted(file_types.items())
    ]
    content_sections.extend([
        "[bold cyan]📑 File Types[/bold cyan]",
        Rule(style="cyan"),
        Text(" | ").join(Text.from_markup(stat) for stat in type_stats)
    ])


    # Display analysis
    console.print("\n")
    console.print(Panel(
        Group(*content_sections),
        title="[bold blue]Workset Analysis[/bold blue]",
        title_align="center"
    ))
