from datetime import datetime
from rich.live import Live
from rich.text import Text
from rich.console import Console
from rich.rule import Rule
from threading import Thread
from janito.agents import agent
from .config import config
from typing import Optional, List
import importlib.resources
from pathlib import Path


console = Console()


def _get_system_prompt() -> str:
    """Get the system prompt from the package data or local file."""
    try:
        # First try to read from package data
        with importlib.resources.files('janito.data').joinpath('system_prompt.txt').open('r') as f:
            return f.read()
    except Exception:
        # Fallback to local file for development
        local_path = Path(__file__).parent / 'data' / 'system_prompt.txt'
        if local_path.exists():
            return local_path.read_text()
        raise FileNotFoundError("Could not find system_prompt.txt")


def progress_send_message(message: str) -> Optional[str]:
    """Send a message to the AI agent with progress indication.

    Displays a progress spinner while waiting for the agent's response and shows
    token usage statistics after receiving the response. Uses a background thread
    to update the elapsed time display.

    Args:
        system_message: The system message to send to the AI agent
        message: The message to send to the AI agent

    Returns:
        Optional[str]: The response text from the AI agent, or None if interrupted

    Note:
        - Returns None if the operation is cancelled via Ctrl+C
        - If the request fails, raises the original exception
    """
    system_message = _get_system_prompt()

    if config.debug:
        console.print(f"[yellow]======= Sending message via {agent.__class__.__name__.replace('AIAgent', '')}[/yellow]")
        print(system_message)
        print(message)
        console.print("[yellow]======= End of message[/yellow]")

    start_time = datetime.now()


    response = None
    error = None

    def agent_thread():
        nonlocal response, error
        try:
            response = agent.send_message(system_message=system_message, message=message)
        except Exception as e:
            error = e

    agent_thread = Thread(target=agent_thread, daemon=True)
    agent_thread.start()

    try:
        with Live(Text("Waiting for response from AI agent...", justify="center"), refresh_per_second=4) as live:
            while agent_thread.is_alive():
                elapsed = datetime.now() - start_time
                elapsed_seconds = elapsed.seconds
                elapsed_minutes = elapsed_seconds // 60
                remaining_seconds = elapsed_seconds % 60
                time_str = f"{elapsed_minutes}m{remaining_seconds}s" if elapsed_minutes > 0 else f"{elapsed_seconds}s"
                # Calculate message size in bytes
                message_bytes = len(message.encode('utf-8'))
                size_str = f"{message_bytes:,} bytes"
                live.update(Text.assemble(
                    f"Waiting for {agent.friendly_name} response... (",
                    (time_str, "magenta"),
                    f") • Message size: ",
                    (size_str, "cyan"),
                    justify="center"
                ))
                agent_thread.join(timeout=0.25)

            # Calculate final stats
            elapsed = datetime.now() - start_time
            elapsed_seconds = elapsed.seconds
            elapsed_minutes = elapsed_seconds // 60
            remaining_seconds = elapsed_seconds % 60
            time_str = f"{elapsed_minutes}m{remaining_seconds}s" if elapsed_minutes > 0 else f"{elapsed_seconds}s"

            if hasattr(response, 'usage'):
                usage = response.usage
                # Get total input tokens including cache if available
                total_input = (
                    getattr(usage, 'input_tokens', 0) +
                    getattr(usage, 'cache_creation_input_tokens', 0) +
                    getattr(usage, 'cache_read_input_tokens', 0)
                )
                output_tokens = getattr(usage, 'output_tokens', 0)

                # Update final message with stats
                stats_text = f"Got response from {agent.friendly_name} after {time_str} • [cyan]In:[/] [bold green]{total_input:,}[/] [cyan]Out:[/] [bold yellow]{output_tokens:,}[/]"
                live.update(Rule(stats_text))

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        return None

    if error:
        if isinstance(error, KeyboardInterrupt):
            console.print("\n[yellow]Operation cancelled[/yellow]")
            return None
        raise error

    if config.debug:
        console.print("[yellow]======= Received response[/yellow]")
        if isinstance(response, str):
            print(response)
        else:
            print(response.content[0].text)
        console.print("[yellow]======= End of response[/yellow]")
    
    # Extract response text based on response type
    if hasattr(response, 'choices'):
        response_text = response.choices[0].message.content
    elif hasattr(response, 'content'):
        response_text = response.content[0].text
    else:
        response_text = str(response)
    
    return response_text