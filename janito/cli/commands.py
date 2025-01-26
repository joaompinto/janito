from pathlib import Path
from rich.console import Console
from janito.agents import agent

from janito.workspace import workset
from janito.config import config
from janito.qa import ask_question, display_answer
from janito.change.request import request_change, replay_saved_response


console = Console()

def handle_ask(question: str):
    """Process a question about the codebase

    Args:
        question: The question to ask about the codebase
        workset: Optional Workset instance for scoped operations
    """
    answer = ask_question(question)
    display_answer(answer)

def handle_scan():
    """Preview files that would be analyzed"""
    workset.show()



def is_dir_empty(path: Path) -> bool:
    """Check if directory is empty or only contains empty directories."""
    if not path.is_dir():
        return False

    for item in path.iterdir():
        if item.name.startswith(('.', '__pycache__')):
            continue
        if item.is_file():
            return False
        if item.is_dir() and not is_dir_empty(item):
            return False
    return True

def handle_request(request: str = None, replay: bool = False):
    """Process modification request
    
    Args:
        request: The modification request to process
        replay: If True, triggers the replay response flow
    """
    if not request and not replay:
        return
    
    is_empty = is_dir_empty(config.workspace_dir)
    if is_empty:
        console.print("\n[bold blue]Empty directory - will create new files as needed[/bold blue]")

    if replay:
        replay_saved_response()
    else:
        request_change(request)


# Command handler functions
COMMANDS = {
    'ask': handle_ask,
    'scan': handle_scan,
    'request': handle_request
}