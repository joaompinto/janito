from rich.table import Table
from rich.console import Console
from typing import List, Dict

def show_changes_summary(changes_summary: List[Dict], console: Console) -> None:
    """Show summary table of all changes."""
    table = Table(title="Changes Summary")
    table.add_column("File", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Lines Changed", justify="right", style="yellow")
    table.add_column("Delta", justify="right", style="green")
    table.add_column("Block", style="blue", justify="center")
    table.add_column("Reason")

    for change in changes_summary:
        delta = change['lines_modified'] - change['lines_original']
        delta_str = f"{'+' if delta > 0 else ''}{delta}"
        
        if change['type'] == "CREATE":
            lines_info = f"+{change['lines_modified']} lines"
        elif change['type'] in ("DELETE", "CLEAN"):
            lines_info = f"-{change['lines_original']} lines"
        else:
            lines_info = f"{change['lines_original']} → {change['lines_modified']} lines"

        table.add_row(
            str(change['file']),
            change['type'],
            lines_info,
            delta_str,
            change['block_marker'] or '-',
            change['reason']
        )

    console.print("\n")
    console.print(table, justify="center")
    console.print("\n")