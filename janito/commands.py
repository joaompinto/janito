from typing import Optional, List
from pathlib import Path
import ast
import os
import sys
import subprocess
from rich.syntax import Syntax
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text
from threading import Event
from janito.workspace import Workspace
from janito.claude import ClaudeAPIAgent
from janito.change import FileChangeHandler
from janito.prompts import build_general_prompt, build_info_prompt, build_change_prompt, build_fix_error_prompt, SYSTEM_PROMPT

class JanitoCommands:
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
            self.workspace = Workspace()
        except Exception as e:
            raise ValueError(f"Failed to initialize Janito: {e}")

    def missing_files(self, args):
        """Show files in workspace that are not included based on patterns"""
        default_exclude = self.workspace.default_exclude
        default_patterns = self.workspace.default_patterns
        gitignore_paths = list(self.workspace.base_path.rglob(".gitignore"))
        gitignore_content = []

        for p in gitignore_paths:
            with open(p) as f:
                gitignore_content.extend([line.strip() for line in f if line.strip() and not line.strip().startswith("#")])

        tree = self.workspace.generate_file_structure()
        self.console.print("[bold]Files excluded from workspace:[/]")
        for pattern in default_exclude + gitignore_content:
            self.console.print(f"Pattern: {pattern} (from {'.gitignore' if pattern in gitignore_content else 'default excludes'})")
            # Check each path in the tree against the pattern
            for path in list(tree.keys()):
                if any(part.startswith(pattern) for part in Path(path).parts):
                    self.console.print(f"  {path}")

        self.console.print("\n[bold]Files included based on patterns:[/]") 
        for pattern in default_patterns:
            self.console.print(f"Pattern: {pattern} (default include pattern)")
            # Check each path in the tree against the pattern
            import fnmatch
            for path in list(tree.keys()):
                if fnmatch.fnmatch(str(path), pattern):
                    self.console.print(f"  {path}")

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
        """Send message with interruptible progress bar"""
        try:
            if self.debug:
                print("\n[Debug] Sending request to Claude")
            
            # Reset the stop event
            self.stop_progress.clear()
            
            # Build general context prompt
            prompt = build_general_prompt(
                self.get_workspace_status(),
                self._get_files_content(),
                message
            )
            
            from rich.progress import Progress, SpinnerColumn, TextColumn
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                disable=False
            ) as progress:
                # Add a simple spinner task
                task = progress.add_task("Waiting for response...", total=None)
                
                try:
                    # Start Claude request without waiting
                    import threading
                    response_ready = threading.Event()
                    response_text = [""]  # Use list to allow modification in thread
                    
                    def claude_request():
                        try:
                            response_text[0] = self.claude.send_message(prompt, stop_event=self.stop_progress)
                        finally:
                            response_ready.set()
                    
                    # Start request in background
                    request_thread = threading.Thread(target=claude_request)
                    request_thread.daemon = True
                    request_thread.start()
                    
                    # Wait for response with interruption check
                    while not response_ready.is_set():
                        if self.stop_progress.is_set():
                            progress.stop()
                            return "Operation cancelled by user."
                        response_ready.wait(0.1)  # Check every 100ms
                    
                    if self.stop_progress.is_set():
                        return "Operation cancelled by user."
                        
                    if not response_text[0]:
                        return "No response received."
                        
                    self.last_response = response_text[0]
                    return response_text[0]
                    
                except KeyboardInterrupt:
                    progress.stop()
                    self.stop_progress.set()
                    return "Operation cancelled by user."
                    
        except Exception as e:
            if self.stop_progress.is_set():
                return "Operation cancelled by user."
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

    def clear_console(self) -> str:
        """Clear the console"""
        try:
            os.system('clear' if os.name == 'posix' else 'cls')
            return "Console cleared"
        except Exception as e:
            return f"Error clearing console: {str(e)}"

    def get_workspace_status(self) -> str:
        return self.workspace.get_workspace_status()

    def show_workspace(self, show_missing: bool = False) -> str:
        """Show directory structure and Python files in current workspace"""
        try:
            self.workspace.print_workspace_structure()
            
            if show_missing:
                excluded_files = self.workspace.get_excluded_files()
                if excluded_files:
                    print("\nExcluded files and directories:")
                    print("=" * 80)
                    for path in excluded_files:
                        print(f"  {path}")
                else:
                    print("\nNo excluded files or directories found.")
                    
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

    def _attempt_fix_error(self, filepath: str, error_output: str) -> str:
        """Attempt to fix Python errors by consulting Claude"""
        try:
            self.console.print("\n[yellow]Would you like me to attempt to fix this error automatically? (y/N)[/]")
            if input().lower() != 'y':
                return "Fix attempt cancelled by user."

            # Get file content for context
            with open(filepath) as f:
                file_content = f.read()
                
            # Build context using the proper prompt builder
            prompt = build_fix_error_prompt(
                self.get_workspace_status(),
                file_content,
                filepath,
                error_output
            )
            
            # Get and process response
            response = self.claude.send_message(prompt)
            success = self.change_handler.process_changes(response)
            
            if success:
                return "Changes applied. Try running the file again."
            return "Failed to apply fixes. Manual intervention required."
            
        except Exception as e:
            return f"Error attempting fix: {str(e)}"

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
                
            if result.returncode != 0:
                self.console.print("\n[red]Execution failed with errors:[/red]")
                print(result.stderr)
                return self._attempt_fix_error(filepath, result.stderr)
            elif result.stderr:
                self.console.print("\n[yellow]Warnings:[/yellow]")
                print(result.stderr)
                
            return ""
        except Exception as e:
            return f"Error running file: {str(e)}"

    def edit_file(self, filepath: str) -> str:
        """Open file in system editor"""
        try:
            path = Path(filepath)
            if not path.exists():
                # Create the file if it doesn't exist for .gitignore and similar files
                if filepath in ['.gitignore', '.env', 'README.md']:
                    path.touch()
                else:
                    return f"Error: File not found - {filepath}"
            if not path.is_file():
                return f"Error: Not a file - {filepath}"

            # Get system editor - try VISUAL then EDITOR then fallback to nano
            editor = os.getenv('VISUAL') or os.getenv('EDITOR') or 'nano'
            
            try:
                result = subprocess.run([editor, str(path)])
                if result.returncode != 0:
                    return f"Editor exited with error code {result.returncode}"
                return f"Finished editing {filepath}"
            except FileNotFoundError:
                return f"Error: Editor '{editor}' not found"
                
        except Exception as e:
            return f"Error editing file: {str(e)}"