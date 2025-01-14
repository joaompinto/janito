from typing import Optional
from rich.console import Console
import readline
from janito.shell.user_prompt import prompt_user, display_history

console = Console()

def shell_loop():
    """Main shell loop for handling user requests.

    The shell can be exited using:
    - typing '/exit'
    - pressing Ctrl+D
    """
    while True:
        request = prompt_user("Enter change request (type '/exit' to quit, /help for assistance)").strip()
        if request.lower() == '/exit':
            break
        elif request.lower() == '/help':
            from janito.shell.help import show_help
            show_help()
        elif request.lower() == '/history':
            display_history(20)  # Show last 20 commands
        elif request:
            handle_request(request)
