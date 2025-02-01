from rich.table import Table
from rich.console import Console
from rich.text import Text
from typing import List, Dict

def show_changes_summary(changes_summary: List[Dict], console: Console) -> None:
    """Show summary table of all changes."""
    table = Table(title="Changes Summary")
    table.add_column("ID", style="blue", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("File", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Line Changes", justify="right", style="green")
    table.add_column("Reason")
    for change in changes_summary:
        lines_changed = abs(change['lines_modified'] - change['lines_original'])
        delta = change['lines_modified'] - change['lines_original']
        if change['type'] == "CREATE":
            delta_str = f"({lines_changed} added)"
        elif change['type'] in ("DELETE", "CLEAN"):
            delta_str = f"({lines_changed} removed)"
        else:
            delta_str = f"({lines_changed} changed) {'' if delta == 0 else ('+' if delta > 0 else '')}{delta}"
        if change.get('has_error', False):
            status = Text("❌", style="red")
            if error_msg := change.get('error_message'):
                status.append(f" {error_msg[:30]}...")
        else:
            status = Text("✓", style="green")
        table.add_row(
            str(change['block_id']),
            status,
            str(change['file']),
            change['type'],
            delta_str,
            change['reason']
        )
    console.print("\n")
    console.print(table, justify="center")
    console.print("\n")