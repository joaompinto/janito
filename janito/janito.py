from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.document import Document
from prompt_toolkit.completion.base import CompleteEvent
import anthropic
import os
from pathlib import Path
import json
from typing import List, Optional, AsyncGenerator, Iterable, Tuple
import asyncio
from hashlib import sha256
from datetime import datetime, timedelta
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import traceback  # Add import at the top with other imports
from rich.markdown import Markdown
from rich.console import Console
import subprocess  # Add at the top with other imports
import re  # Add to imports at top
import ast  # Add to imports at top
import tempfile
from janito.change import FileChangeHandler, DeltaResult, DeltaType  # Change relative imports to absolute
from janito.watcher import FileWatcher
from janito.claude import ClaudeAPIAgent
from rich.progress import Progress, SpinnerColumn, TextColumn  # Add to imports at top
from threading import Event
import threading
from rich.syntax import Syntax
from rich.text import Text
import typer
from typing import Optional
import readline  # Add to imports at top
import signal   # Add to imports at top
from rich.traceback import install
from janito.utils import generate_file_structure, format_tree, get_files_content  # Add import at top

# Install rich traceback handler
install(show_locals=True)

"""
Main module for Janito - Language-Driven Software Development Assistant.
Provides the core CLI interface and command handling functionality.
Manages user interactions, file operations, and API communication with Claude.
"""

class PathCompleter(Completer):
    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        
        # Handle dot command completion
        if text.startswith('.') or text == '':
            commands = [
                '.help', '.exit', '.clear', '.save', '.load',
                '.debug', '.cache', '.content'
            ]
            word = text.lstrip('.')
            for cmd in commands:
                if cmd[1:].startswith(word):
                    yield Completion(
                        cmd, 
                        start_position=-len(text),
                        display=HTML(f'<cmd>{cmd}</cmd>')
                    )
            return
            
        # Handle path completion
        path = Path('.' if not text else text)
        
        try:
            if path.is_dir():
                directory = path
                prefix = ''
            else:
                directory = path.parent
                prefix = path.name

            for item in directory.iterdir():
                if item.name.startswith(prefix):
                    yield Completion(
                        str(item),
                        start_position=-len(prefix) if prefix else 0,
                        display=HTML(f'{"/" if item.is_dir() else ""}{item.name}')
                    )
        except Exception:
            pass

    async def get_completions_async(self, document: Document, complete_event: CompleteEvent) -> AsyncGenerator[Completion, None]:
        for completion in self.get_completions(document, complete_event):
            yield completion

class JanitoCommands:  # Renamed from ClaudeCommands
    def __init__(self, api_key: Optional[str] = None):
        try:
            self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable is required")
            self.client = anthropic.Client(api_key=self.api_key)
            self.conversation_history = []
            self.history_dir = Path.home() / '.janito' / 'history'  # Add history directory
            self.history_dir.mkdir(parents=True, exist_ok=True)
            self.debug = False
            self.stop_progress = Event()
            self.change_handler = FileChangeHandler()  # Add file change handler
            self.console = Console()  # Add console for rich output
            self.last_sent = None  # Add last sent message storage
            self.last_response = None  # Add last response storage
            self.system_message = """You are Janito, a Language-Driven Software Development Assistant.
Your role is to help users understand and modify their Python codebase.
For file changes, provide XML instructions using the <fileChanges> format.
For information requests, provide clear explanations using markdown formatting.
Always analyze the provided workspace context before responding."""
        except Exception as e:
            raise ValueError(f"Failed to initialize Janito: {e}")
        
    def _get_files_content(self) -> str:
        return get_files_content(Path().absolute())

    def _build_context(self, request: str, request_type: str = "general") -> str:
        """Build context with workspace status and files content"""
        workspace_status = self.get_workspace_status()
        files_content = self._get_files_content()
        
        return f"""=== WORKSPACE STRUCTURE ===
{workspace_status}

=== FILES CONTENT ===
{files_content}

=== {request_type.upper()} REQUEST ===
{request}"""

    def send_message(self, message: str) -> str:
        try:
            workspace_status = self.get_workspace_status()
            files_content = self._get_files_content()
            
            user_message = f"""=== WORKSPACE STRUCTURE ===
{workspace_status}

=== FILES CONTENT ===
{files_content}

=== USER REQUEST ===
{message}"""

            if self.debug:
                print("\n[Debug] Sending request to Claude:")
                print("=" * 80)
                print("[System prompt]:")
                print(self.system_message)
                print("-" * 40)
                print("[User message]:")
                print(user_message)
                print("=" * 80)
            
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                system=self.system_message,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            response_text = response.content[0].text
            self.last_response = response_text
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            return response_text
            
        except anthropic.APIError as e:
            raise RuntimeError(f"Failed to communicate with Claude API: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to process message: {e}")

    def handle_file_change(self, request: str) -> str:
        """Handle file modification request starting with !"""
        try:
            context = self._build_context(request, "change")
            response = self.send_message(context)
            
            # Process the changes
            success = self.change_handler.process_changes(response)
            
            if not success:
                return "Failed to process file changes. Please check the response format."
            
            return "File changes applied successfully."
            
        except Exception as e:
            raise RuntimeError(f"Failed to process file changes: {e}")

    def save_history(self, args) -> str:
        """Save conversation history to a file"""
        try:
            if not args:
                filename = f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            else:
                filename = args[0]
                
            filepath = self.history_dir / filename
            with open(filepath, 'w') as f:
                json.dump(self.conversation_history, f, indent=2)
            return f"History saved to {filepath}"
        except Exception as e:
            raise RuntimeError(f"Failed to save history: {e}")

    def load_history(self, args) -> str:
        """Load conversation history from a file"""
        try:
            if not args:
                return "Please specify a history file to load"
                
            filepath = self.history_dir / args[0]
            if not filepath.exists():
                return f"History file not found: {filepath}"
                
            with open(filepath) as f:
                self.conversation_history = json.load(f)
            return f"History loaded from {filepath}"
        except Exception as e:
            raise RuntimeError(f"Failed to load history: {e}")

    def clear_history(self) -> str:
        """Clear the conversation history"""
        self.conversation_history = []
        return "Conversation history cleared"

    def get_workspace_status(self) -> str:
        """Get a summary of Python files in current workspace"""
        try:
            base_path = Path().absolute()
            tree = generate_file_structure(base_path)
            
            if not tree:
                return "No Python files found in the current workspace."
                
            tree_lines = format_tree(tree)
            return "Python files in workspace:\n" + "\n".join(tree_lines)
            
        except Exception as e:
            raise RuntimeError(f"Failed to get workspace status: {e}")

    def show_content(self) -> str:
        """Show directory structure and Python files in current workspace"""
        try:
            status = self.get_workspace_status()
            print("\nWorkspace structure:")
            print("=" * 80)
            print(status)
            return ""
        except Exception as e:
            raise RuntimeError(f"Failed to show workspace content: {e}")

    def handle_info_request(self, request: str, workspace_status: str) -> str:
        """Handle information request ending with ?"""
        try:
            context = self._build_context(request, "info")
            
            # Get response from Claude
            response = self.send_message(context)
            
            # Render markdown
            md = Markdown(response)
            self.console.print(md)
            return ""  # Return empty since we printed directly
            
        except Exception as e:
            raise RuntimeError(f"Failed to process information request: {e}")

    def get_last_response(self) -> str:
        """Get the last sent and received message to/from Claude"""
        if not self.last_response or not self.last_sent:
            return "No previous conversation available."

        # Format the output with background colors
        sent = Text("\n=== Last Message Sent ===\n", style="black on yellow")
        sent.append(self.last_sent, style="yellow")

        received = Text("\n\n=== Last Response Received ===\n", style="black on green")
        received.append(self.last_response, style="green")

        return sent + received

    def clear_cache(self) -> str:
        """Command kept for compatibility but now just returns a message"""
        return "Cache system has been removed"

class JanitoConsole:
    """Interactive console for Janito with command handling and REPL"""
    def __init__(self):
        self.commands = {
            '.help': self.help,
            '.exit': self.exit
        }
        
        try:
            self.janito = JanitoCommands()
            janito_commands = {
                '.clear': lambda _: self.janito.clear_history(),
                '.save': self.janito.save_history,
                '.load': self.janito.load_history,
                '.debug': lambda _: self.janito.toggle_debug(),
                '.content': lambda _: self.janito.show_content(),
                '.last': lambda _: self.janito.get_last_response(),  # Add last command
                '.help': lambda _: (
                    "Janito commands:\n"
                    ".clear   - Clear conversation history\n"
                    ".save    - Save history to file\n"
                    ".load    - Load history from file\n"
                    ".debug   - Toggle debug mode\n"
                    ".content - Show current workspace content\n"
                    ".last    - Show last Claude response\n"
                    ".help    - Show this help"
                )
            }
            self.commands.update(janito_commands)
        except ValueError as e:
            print(f"Warning: Janito initialization failed - {str(e)}")
            self.janito = None
        
        self.session = PromptSession(
            completer=PathCompleter(),
            style=Style.from_dict({
                'ai': '#00aa00 bold',
                'path': '#3388ff bold',
                'sep': '#888888',
                'prompt': '#ff3333 bold',
                'cmd': '#00aa00',
            })
        )
        self.running = True
        self.restart_requested = False
        self._setup_file_watcher()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for clean terminal state"""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals"""
        self.cleanup_terminal()
        if not self.restart_requested:
            print("\nExiting...")
            sys.exit(0)

    def cleanup_terminal(self):
        """Restore terminal settings"""
        try:
            # Reset terminal state
            os.system('stty sane')
            # Clear readline state
            readline.set_startup_hook(None)
            readline.clear_history()
        except Exception as e:
            print(f"Warning: Error cleaning up terminal: {e}")

    def _setup_file_watcher(self):
        """Set up file watcher for auto-restart"""
        def on_file_change(path, content):
            print("\nJanito source file changed - restarting...")
            self.restart_requested = True
            self.running = False
            self.restart_process()

        try:
            package_dir = os.path.dirname(os.path.dirname(__file__))
            self.watcher = FileWatcher(on_file_change, package_dir)
            self.watcher.start()
        except Exception as e:
            print(f"Warning: Could not set up file watcher: {e}")

    def restart_process(self):
        """Restart the current process using module invocation"""
        try:
            if self.watcher:
                self.watcher.stop()
            print("\nRestarting Janito process...")
            self.cleanup_terminal()
            # Use -m to run as module and preserve original args
            python_exe = sys.executable
            args = [python_exe, '-m', 'janito'] + sys.argv[1:]
            os.execv(python_exe, args)
        except Exception as e:
            print(f"Error during restart: {e}")
            self.cleanup_terminal()
            sys.exit(1)

    def get_prompt(self):
        """Generate the command prompt"""
        current_dir = os.getcwd()
        return HTML(
            '<ai>🤖 janito</ai> '
            '<sep>in</sep> '  # Added "in" separator
            '<path>{}</path> '
            '<sep>></sep> '.format(current_dir)
        )

    def help(self, args):
        """Show help information"""
        if args:
            cmd = args[0]
            if cmd in self.commands:
                print(f"{cmd}: {self.commands[cmd].__doc__}")
            else:
                print(f"Unknown command: {cmd}")
        else:
            print("Available commands:")
            print("  .help    - Show this help")
            print("  .exit    - End session")
            print("  .clear   - Clear history")
            print("  .save    - Save history to file")
            print("  .load    - Load history from file")
            print("  .debug   - Toggle debug mode")
            print("  .content - Show current workspace content")
            print("  .last    - Show last Claude response")
            print("\nInput formats:")
            print("  !request - Request file changes (e.g. '!add logging to utils.py')")
            print("  request? - Get information without changes")
            print("  request  - General queries to Janito")

    def exit(self, args):
        """Exit the console"""
        self.running = False
        self.cleanup_terminal()

    def run(self):
        """Main command loop"""
        try:
            while self.running and self.session:  # Check session is valid
                try:
                    command = self.session.prompt(self.get_prompt()).strip()
                    
                    if not command:
                        continue
                        
                    if command.startswith('.'):
                        parts = command.split()
                        cmd, args = parts[0], parts[1:]
                        if cmd in self.commands:
                            result = self.commands[cmd](args)
                            if result:
                                print(result)
                        else:
                            print(f"Unknown command: {cmd}")
                    elif command.startswith('!') and self.janito:
                        # Handle file change request
                        result = self.janito.handle_file_change(command[1:])  # Remove ! prefix
                        print(f"\n{result}")
                    elif command.endswith('?') and self.janito:
                        # Handle information request
                        workspace_status = self.janito.get_workspace_status()
                        result = self.janito.handle_info_request(command[:-1], workspace_status)  # Remove ? suffix
                        print(f"\n{result}")
                    elif self.janito:
                        result = self.janito.send_message(command)
                        print(f"\n{result}")
                    else:
                        raise RuntimeError("Janito not initialized")
                except EOFError:
                    self.exit([])
                    break
                except (KeyboardInterrupt, SystemExit):
                    if self.restart_requested:
                        break
                    if not self.restart_requested:  # Only exit if not restarting
                        self.exit([])
                    break
        finally:
            if self.watcher:
                self.watcher.stop()
            if self.restart_requested:
                self.restart_process()
            else:
                self.cleanup_terminal()

class CLI:
    """Command-line interface handler for Janito using Typer"""
    def __init__(self):
        self.app = typer.Typer(
            help="Janito - Language-Driven Software Development Assistant",
            add_completion=False,
            no_args_is_help=False,  # Don't show help when no args
        )
        self._setup_commands()

    def _setup_commands(self):
        """Setup Typer commands"""
        @self.app.callback(invoke_without_command=True)
        def main(
            debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
            no_watch: bool = typer.Option(False, "--no-watch", help="Disable file watching"),
        ):
            """Language-Driven Software Development Assistant"""
            try:
                console = JanitoConsole()
                if debug:
                    console.janito.debug = True
                if no_watch:
                    if console.watcher:
                        console.watcher.stop()
                        console.watcher = None
                console.run()
            except KeyboardInterrupt:
                print("\nExiting...")
            except Exception as e:
                print(f"\nFatal error: {str(e)}")
                print("\nTraceback:")
                traceback.print_exc()

    def run(self, args=None):        
        """Run the CLI application"""
        try:
            console = JanitoConsole()
            console.run()
        except Exception as e:
            print(f"\nFatal error: {str(e)}")
            print("\nTraceback:")
            traceback.print_exc()

def run_cli():
    """Main entry point"""
    cli = CLI()
    cli.run()

