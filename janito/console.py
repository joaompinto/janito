from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.document import Document
from prompt_toolkit.completion.base import CompleteEvent
from pathlib import Path
import os
import sys
import readline
import signal
import subprocess
import traceback
from rich.markdown import Markdown
from typing import Optional, Iterable, AsyncGenerator
from janito.commands import JanitoCommands  # Add this import
from janito.watcher import FileWatcher  # Add this import

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

class JanitoConsole:
    """Interactive console for Janito with command handling and REPL"""
    def __init__(self):
        self.commands = {
            '.help': self.help,
            '.exit': self.exit,
            '.clear': lambda _: self.janito.clear_console() if self.janito else "Janito not initialized",
            '.debug': lambda _: self.janito.toggle_debug() if self.janito else "Janito not initialized",
            '.workspace': lambda _: self.janito.show_workspace() if self.janito else "Janito not initialized",
            '.last': lambda _: self.janito.get_last_response() if self.janito else "Janito not initialized",
            '.show': lambda args: self.janito.show_file(args[0]) if args and self.janito else "File path required",
            '.check': lambda _: self.janito.check_syntax() if self.janito else "Janito not initialized",
            '.p': lambda args: self.janito.run_python(args[0]) if args and self.janito else "File path required",
            '.python': lambda args: self.janito.run_python(args[0]) if args and self.janito else "File path required",
            '.edit': lambda args: self.janito.edit_file(args[0]) if args and self.janito else "File path required",
        }
        
        try:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable is required")
            self.janito = JanitoCommands(api_key=api_key)
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
        self.package_dir = os.path.dirname(os.path.dirname(__file__))
        self.workspace = None
        self._setup_file_watcher()
        self._setup_signal_handlers()
        self._load_history()

    def _load_history(self):
        """Load command history from file"""
        try:
            if self.janito and self.janito.workspace.history_file.exists():
                with open(self.janito.workspace.history_file) as f:
                    # Clear existing history first
                    readline.clear_history()
                    for line in f:
                        line = line.strip()
                        if line:  # Only add non-empty lines
                            readline.add_history(line)
        except Exception as e:
            print(f"Warning: Could not load command history: {e}")

    def _save_history(self, new_command: str = None):
        """Save command history to file, optionally adding a new command first"""
        try:
            if self.janito:
                # Add new command to history if provided
                if new_command and new_command.strip():
                    readline.add_history(new_command)

                history_path = self.janito.workspace.history_file
                history_path.parent.mkdir(exist_ok=True)
                
                # Get all history items
                history = []
                for i in range(readline.get_current_history_length()):
                    item = readline.get_history_item(i + 1)
                    if item and item.strip():  # Only save non-empty commands
                        history.append(item)
                
                # Write to file
                with open(history_path, 'w') as f:
                    f.write('\n'.join(history) + '\n')
                    
        except Exception as e:
            print(f"Warning: Could not save command history: {e}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for clean terminal state"""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals"""
        self.cleanup_terminal()
        # Signal any waiting operations to stop
        if self.janito:
            self.janito.stop_progress.set()
        if not self.restart_requested:
            print("\nOperation cancelled.")

    def cleanup_terminal(self):
        """Restore terminal settings"""
        try:
            # Save history before cleaning up
            self._save_history()
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

    def get_prompt(self, cwd=None):
        """Generate the command prompt"""
        return HTML('🤖 ')

    def render_status_bar(self):
        """Render the persistent status bar"""
        cwd = os.getcwd()
        # Combine the HTML strings before creating HTML object
        return HTML(
            '<path>{}</path>'
            ' <hint>(!modify, ?info, normal, $shell_cmd)</hint>'.format(cwd)  
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
            print("  .help      - Show this help")
            print("  .exit      - End session")
            print("  .clear     - Clear console")
            print("  .debug     - Toggle debug mode")
            print("  .workspace - Show workspace structure")
            print("  .last      - Show last Claude response")
            print("  .show      - Show file content with syntax highlighting")
            print("  .check     - Check workspace Python files for syntax errors")
            print("  .p         - Run a Python file")
            print("  .python    - Run a Python file (alias for .p)")
            print("  .edit      - Open file in system editor")
            print("\nMessage Modes:")
            print("  1. Regular message:")
            print("     Example: how does the file watcher work")
            print("     Use for: General discussion and questions about code")
            print("\n  2. Question mode (ends with ?):")
            print("     Example: what are the main classes in utils.py?")
            print("     Use for: Deep analysis and explanations without changes")
            print("\n  3. Change mode (starts with !):")
            print("     Example: !add error handling to get_files_content")
            print("     Use for: Requesting code modifications")
            print("\n  4. Shell commands (starts with $):")
            print("     Example: $ls -la")
            print("     Use for: Executing shell commands")

    def exit(self, args):
        """Exit the console"""
        self._save_history()  # Save history before exiting
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
                    command = self.session.prompt(
                        self.get_prompt(),
                        bottom_toolbar=self.render_status_bar()
                    ).strip()
                    
                    if not command:
                        continue

                    # Save history after each command
                    self._save_history(command)
                        
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
            # Save history one final time before cleanup
            self._save_history()
            if self.restart_requested:
                self.restart_process()
            else:
                self.cleanup_terminal()

    # Print welcome message after file watcher setup
    print("\nWelcome to Janito - your friendly AI coding assistant!")
    print("Type '.help' to see available commands.")
    print("")