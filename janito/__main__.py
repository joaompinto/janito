import typer
from typing import Optional, List, Set
from pathlib import Path
from rich.text import Text
from rich import print as rich_print
from rich.console import Console
from .version import get_version

from janito.config import config
from janito.workspace import workset
from janito.workspace.models import ScanType  # Add this import
from .cli.commands import (
    handle_request, handle_ask, 
    handle_scan
)


app = typer.Typer(pretty_exceptions_enable=False)

# Initialize console for CLI output
console = Console()



def typer_main(
    user_request: Optional[str] = typer.Argument(None, help="User request"),
    workspace_dir: Optional[Path] = typer.Option(None, "-w", "--workspace_dir", help="Working directory", file_okay=False, dir_okay=True),
    debug: bool = typer.Option(False, "--debug", help="Show debug information"),
    verbose: bool = typer.Option(False, "--verbose", help="Show verbose output"),
    include: Optional[List[Path]] = typer.Option(None, "-i", "--include", help="Additional paths to include"),
    ask: bool = typer.Option(False, "--ask", help="Treat the request as a question about the codebase"),
    play: Optional[Path] = typer.Option(None, "--play", help="Replay a saved prompt file"),
    replay: bool = typer.Option(False, "--replay", help="Trigger the replay response flow"),
    scan: bool = typer.Option(False, "--scan", help="Preview files that would be analyzed"),
    version: bool = typer.Option(False, "--version", help="Show version information"),
    test_cmd: Optional[str] = typer.Option(None, "--test", help="Command to run tests after changes"),
    auto_apply: bool = typer.Option(False, "--auto-apply", help="Apply changes without confirmation"),
    recursive: Optional[List[Path]] = typer.Option(None, "-r", "--recursive", help="Paths to scan recursively (directories only)"),
    skip_work: bool = typer.Option(False, "-s", "--skip-work", help="Skip scanning workspace_dir when using include paths"),
):
    """Janito - AI-powered code modification assistant"""
    if version:
        console.print(f"Janito version {get_version()}")
        return

    # Check if workspace directory exists and handle creation
    if workspace_dir and not workspace_dir.exists():
        create = typer.confirm(f"\nWorkspace directory '{workspace_dir}' does not exist. Create it?")
        if create:
            try:
                workspace_dir.mkdir(parents=True)
                console.print(f"[green]Created workspace directory: {workspace_dir}[/green]")
            except Exception as e:
                error_text = Text(f"\nError: Failed to create workspace directory: {e}", style="red")
                rich_print(error_text)
                raise typer.Exit(1)
        else:
            error_text = Text("\nError: Workspace directory does not exist and was not created", style="red")
            rich_print(error_text)
            raise typer.Exit(1)

    # Configure workspace
    config.set_workspace_dir(workspace_dir)
    config.set_debug(debug)
    config.set_verbose(verbose)
    config.set_auto_apply(auto_apply)

    # Configure workset with scan paths
    if include:
        if config.debug:
            Console(stderr=True).print("[cyan]Debug: Processing include paths...[/cyan]")
        for path in include:
            full_path = config.workspace_dir / path
            if not full_path.resolve().is_relative_to(config.workspace_dir):
                error_text = Text(f"\nError: Path must be within workspace: {path}", style="red")
                rich_print(error_text)
                raise typer.Exit(1)
            workset.add_scan_path(path, ScanType.PLAIN)

    if recursive:
        if config.debug:
            Console(stderr=True).print("[cyan]Debug: Processing recursive paths...[/cyan]")
        for path in recursive:
            full_path = config.workspace_dir / path
            if not path.is_dir():
                error_text = Text(f"\nError: Recursive path must be a directory: {path} ", style="red")
                rich_print(error_text)
                raise typer.Exit(1)
            if not full_path.resolve().is_relative_to(config.workspace_dir):
                error_text = Text(f"\nError: Path must be within workspace: {path}", style="red")
                rich_print(error_text)
                raise typer.Exit(1)
            workset.add_scan_path(path, ScanType.RECURSIVE)

    # Validate skip_work usage
    if skip_work:
        # Check if any include or recursive paths are provided
        if not include and not recursive:
            error_text = Text("\nError: --skip-work requires at least one include path (-i or -r)", style="red")
            rich_print(error_text)
            raise typer.Exit(1)
        # Remove root path from workset when skip_work is enabled
        workset._scan_paths = [p for p in workset._scan_paths if p.path != Path(".")]

    if test_cmd:
        config.set_test_cmd(test_cmd)

    # Refresh workset content before handling commands
    workset.refresh()

    if ask:
        if not user_request:
            error_text = Text("\nError: No question provided. Please provide a question as the main argument when using --ask", style="red")
            rich_print(error_text)
            raise typer.Exit(1)
        handle_ask(user_request)
    elif play:
        handle_play(play)
    elif scan:
        handle_scan()
    else:
        handle_request(user_request, replay=replay)

def main():
    typer.run(typer_main)

if __name__ == "__main__":
    main()