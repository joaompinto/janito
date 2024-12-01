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
from janito.change import FileChangeHandler  # Remove unused imports
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
from janito.workspace import Workspace  # Update import
from janito.prompts import build_change_prompt, build_info_prompt, build_general_prompt, SYSTEM_PROMPT  # Add to imports

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
                '.debug', '.cache', '.content', '.show'  # Added .show
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
            self.claude = ClaudeAPIAgent(api_key=self.api_key)
            self.change_handler = FileChangeHandler()
            self.console = Console()
            self.debug = False
            self.stop_progress = Event()
            self.system_message = SYSTEM_PROMPT
            self.workspace = Workspace()  # Add workspace instance
        except Exception as e:
            raise ValueError(f"Failed to initialize Janito: {e}")

    def _get_files_content(self) -> str:
        return self.workspace.get_files_content()

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
            if self.debug:
                print("\n[Debug] Sending request to Claude")
            
            # Build general context prompt
            prompt = build_general_prompt(
                self.get_workspace_status(),
                self._get_files_content(),
                message
            )
            
            # Use claude agent to send message
            response_text = self.claude.send_message(prompt)
            self.last_response = response_text
            return response_text
            
        except Exception as e:
            raise RuntimeError(f"Failed to process message: {e}")

    def _display_file_content(self, filepath: Path) -> None:
        """Display file content with syntax highlighting"""
        try:
            with open(filepath) as f:
                content = f.read()
            syntax = Syntax(content, "python", theme="monokai", line_numbers=True)
            self.console.print("\nFile content:", style="bold red")
            self.console.print(syntax)
        except Exception as e:
            self.console.print(f"Could not read file {filepath}: {e}", style="bold red")

    def handle_file_change(self, request: str) -> str:
        """Handle file modification request starting with !"""
        try:
            # Build change context prompt
            prompt = build_change_prompt(
                self.get_workspace_status(), 
                self._get_files_content(),
                request
            )
            
            # Get response from Claude
            response = self.claude.send_message(prompt)
            
            # Process changes
            success = self.change_handler.process_changes(response)
            
            if not success:
                return "Failed to process file changes. Please check the response format."
            
            return "File changes applied successfully."
            
        except Exception as e:
            raise RuntimeError(f"Failed to process file changes: {e}")

            raise RuntimeError(f"Failed to load history: {e}")

    def clear_history(self) -> str:
        """Clear the conversation history"""
        self.conversation_history = []
        return "Conversation history cleared"

    def get_workspace_status(self) -> str:
        return self.workspace.get_workspace_status()

    def show_workspace(self) -> str:
        """Show directory structure and Python files in current workspace"""
        try:
            status = self.get_workspace_status()
            print("\nWorkspace structure:")
            print("=" * 80)
            print(status)
            return ""
        except Exception as e:
            raise RuntimeError(f"Failed to show workspace: {e}")

    def handle_info_request(self, request: str, workspace_status: str) -> str:
        """Handle information request ending with ?"""
        try:
            # Build info context prompt
            prompt = build_info_prompt(
                self._get_files_content(),
                request
            )
            
            # Get response and render markdown
            response = self.claude.send_message(prompt)
            md = Markdown(response)
            self.console.print(md)
            return ""
            
        except Exception as e:
            raise RuntimeError(f"Failed to process information request: {e}")

    def get_last_response(self) -> str:
        """Get the last sent and received message to/from Claude"""
        if not self.claude.last_response:
            return "No previous conversation available."

        output = []
        if self.claude.last_full_message:
            output.append(Text("\n=== Last Message Sent ===\n", style="bold yellow"))
            output.append(Text(self.claude.last_full_message + "\n"))
        output.append(Text("\n=== Last Response Received ===\n", style="bold green"))  
        output.append(Text(self.claude.last_response))
        
        self.console.print(*output)
        return ""

    def show_file(self, filepath: str) -> str:
        """Display file content with syntax highlighting"""
        try:
            path = Path(filepath)
            if not path.exists():
                return f"Error: File not found - {filepath}"
            if not path.is_file():
                return f"Error: Not a file - {filepath}"
            
            self._display_file_content(path)
            return ""
        except Exception as e:
            return f"Error displaying file: {str(e)}"

    def toggle_debug(self) -> str:
        """Toggle debug mode on/off"""
        self.debug = not self.debug
        # Also toggle debug on the Claude agent
        if hasattr(self, 'claude') and self.claude:
            self.claude.debug = self.debug
        return f"Debug mode {'enabled' if self.debug else 'disabled'}"

    def check_syntax(self) -> str:
        """Check all Python files in the workspace for syntax errors"""
        try:
            errors = []
            for file in self.workspace.base_path.rglob("*.py"):
                try:
                    with open(file, "r") as f:
                        content = f.read()
                    ast.parse(content)
                except SyntaxError as e:
                    errors.append(f"Syntax error in {file}: {e}")
            
            if errors:
                return "\n".join(errors)
            return "No syntax errors found."
        except Exception as e:
            return f"Error checking syntax: {e}"

    def run_python(self, filepath: str) -> str:
        """Run a Python file"""
        try:
            path = Path(filepath)
            if not path.exists():
                return f"Error: File not found - {filepath}"
            if not path.is_file():
                return f"Error: Not a file - {filepath}"
            if not filepath.endswith('.py'):
                return f"Error: Not a Python file - {filepath}"
                
            self.console.print(f"\n[cyan]Running Python file: {filepath}[/cyan]")
            self.console.print("=" * 80)
            
            result = subprocess.run([sys.executable, str(path)], 
                                  capture_output=True, 
                                  text=True)
            
            if result.stdout:
                self.console.print("\n[green]Output:[/green]")
                print(result.stdout)
            if result.stderr:
                self.console.print("\n[red]Errors:[/red]")
                print(result.stderr)
                
            return ""
        except Exception as e:
            return f"Error running file: {str(e)}"

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
                '.debug': lambda _: self.janito.toggle_debug(),
                '.workspace': lambda _: self.janito.show_workspace(),
                '.last': lambda _: self.janito.get_last_response(),  # Add last command
                '.show': lambda args: self.janito.show_file(args[0]) if args else "Error: File path required",
                '.check': lambda _: self.janito.check_syntax(),  # Add check command
                '.p': lambda args: self.janito.run_python(args[0]) if args else "Error: File path required",
                '.python': lambda args: self.janito.run_python(args[0]) if args else "Error: File path required",
                '.help': self.help  # Just point to the help method instead of a lambda
            }
            self.commands.update(janito_commands)
            # Remove '.cache' from command list
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
        self.package_dir = os.path.dirname(os.path.dirname(__file__))  # Only keep package_dir
        self.workspace = None  # Store workspace path if provided
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
            
            # Change to package directory for module import
            os.chdir(self.package_dir)
            
            python_exe = sys.executable
            args = [python_exe, "-m", "janito"]

            # Add workspace argument if it was provided, stripping any quotes
            if self.workspace:
                workspace_str = str(self.workspace).strip('"\'')
                args.append(workspace_str)
            
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
            '<sep>#</sep> '.format(current_dir)
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
            print("  .debug   - Toggle debug mode")
            print("  .content - Show current workspace content")
            print("  .last    - Show last Claude response")
            print("  .show    - Show file content with syntax highlighting")
            print("  .check   - Check workspace Python files for syntax errors")
            print("\nMessage Modes:")
            print("  1. Regular message:")
            print("     Example: how does the file watcher work")
            print("     Use for: General discussion and questions about the workspace content")
            print("\n  2. Question mode (ends with ?):")
            print("     Example: what are the main classes in utils.py?")
            print("     Use for: Deep analysis and explanations without making changes")
            print("\n  3. Change mode (starts with !):")
            print("     Example: !add error handling to get_files_content")
            print("     Use for: Requesting code modificationsn")

    def exit(self, args):
        """Exit the console"""
        self.running = False
        self.cleanup_terminal()

    def _execute_shell_command(self, command: str) -> None:
        """Execute a shell command and print output"""
        try:
            process = subprocess.run(
                command,
                shell=True,
                text=True,
                capture_output=True
            )
            if process.stdout:
                print(process.stdout.strip())
            if process.stderr:
                print(process.stderr.strip(), file=sys.stderr)
        except Exception as e:
            print(f"Error executing command: {e}", file=sys.stderr)

    def run(self):
        """Main command loop"""
        try:
            while self.running and self.session:  # Check session is valid
                try:
                    command = self.session.prompt(self.get_prompt()).strip()
                    
                    if not command:
                        continue
                        
                    if command.startswith('$'):
                        # Handle shell command
                        self._execute_shell_command(command[1:].strip())
                    elif command.startswith('.'):
                        parts = command.split()
                        cmd, args = parts[0], parts[1:]
                        if cmd in self.commands:
                            result = self.commands[cmd](args)
                            if result:
                                print(result)
                        else:
                            print(f"Unknown command: {cmd}")
                    elif command.startswith('!'):
                        # Handle file change request
                        print("\n[Using Change Request Prompt]")
                        result = self.janito.handle_file_change(command[1:])  # Remove ! prefix
                        print(f"\n{result}")
                    elif command.endswith('?'):
                        # Handle information request
                        print("\n[Using Information Request Prompt]")
                        workspace_status = self.janito.get_workspace_status()
                        result = self.janito.handle_info_request(command[:-1], workspace_status)  # Remove ? suffix
                        print(f"\n{result}")
                    else:
                        # Handle regular message with markdown rendering
                        print("\n[Using General Message Prompt]")
                        result = self.janito.send_message(command)
                        md = Markdown(result)
                        self.janito.console.print("\n")  # Add newline before response
                        self.janito.console.print(md)
                        print("")  # Add newline after response

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
            no_args_is_help=False,
        )
        self._setup_commands()

    def _setup_commands(self):
        """Setup Typer commands"""
        @self.app.command()
        def start(
            workspace: Optional[str] = typer.Argument(None, help="Optional workspace directory to change to"),
            debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
            no_watch: bool = typer.Option(False, "--no-watch", help="Disable file watching"),
        ):
            """Start Janito interactive console"""
            try:
                # Change to workspace directory if provided
                if workspace:
                    workspace_path = Path(workspace).resolve()
                    if not workspace_path.exists():
                        self.console.print(f"\nError: Workspace directory does not exist: {workspace_path}")
                        raise typer.Exit(1)
                    os.chdir(workspace_path)

                console = JanitoConsole()
                if workspace:
                    console.workspace = workspace_path  # Store workspace path
                if debug:
                    console.janito.debug = True
                if no_watch:
                    if console.watcher:
                        console.watcher.stop()
                        console.watcher = None
                
                # Print workspace info after file watcher setup
                if workspace:
                    print("\n" + "="*50)
                    print(f"🚀 Working on project: {workspace_path.name}")
                    print(f"📂 Path: {workspace_path}")
                    print("="*50 + "\n")
                    
                console.run()

            except Exception as e:
                print(f"\nFatal error: {str(e)}")
                print("\nTraceback:")
                traceback.print_exc()
                raise typer.Exit(1)

    def run(self):
        """Run the CLI application"""
        self.app()

def run_cli():
    """Main entry point"""
    cli = CLI()
    cli.run()