from typing import Optional, List, Set  # Add Set to imports
import re
from pathlib import Path
from typing import Optional, List
import ast
import shutil
from rich.syntax import Syntax
from rich.console import Console
from dataclasses import dataclass
import tempfile
from janito.utils import build_context_prompt, get_files_content  # Simplify imports

"""
File modification system for Janito.
Handles parsing and applying code changes requested by users.
Provides XML-based change descriptions and safety checks for file modifications.
"""

@dataclass
class XMLBlock:
    """Simple container for parsed XML blocks"""
    description: str = ""
    old_content: List[str] = None
    new_content: List[str] = None
    indentation: int = 0
    
    def __post_init__(self):
        if self.old_content is None:
            self.old_content = []
        if self.new_content is None:
            self.new_content = []

@dataclass
class XMLChange:
    """Simple container for parsed XML changes"""
    path: Path
    operation: str
    blocks: List[XMLBlock] = None  # Fix brackets syntax
    content: str = ""

    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []

class FileChangeHandler:
    def __init__(self):
        self.preview_dir = Path(tempfile.mkdtemp(prefix='janito_preview_'))
        self.console = Console()

    def generate_changes_prompt(self, dir_status: str, files_content: str, file_request: str) -> str:
        return build_context_prompt(files_content, dir_status, file_request, "change")

    def _parse_xml_response(self, response: str) -> List[XMLChange]:
        """Parse XML response line by line"""
        changes = []
        current_change = None
        current_block = None
        current_section = None
        content_lines = []
        
        try:
            lines = response.splitlines()
            for line in lines:
                if not line:
                    continue

                # Match change start
                if match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', line.strip()):
                    path, operation = match.groups()
                    current_change = XMLChange(Path(path), operation)
                    current_block = None
                    current_section = None
                
                # Match block start with indentation
                elif match := re.match(r'<block\s+description="([^"]+)"\s+indentation="(\d+)">', line.strip()):
                    if current_change:
                        desc, indent = match.groups()
                        current_block = XMLBlock(description=desc, indentation=int(indent))
                        current_section = None
                elif match := re.match(r'<block\s+description="([^"]+)">', line.strip()):
                    if current_change:
                        current_block = XMLBlock(description=match.group(1))
                        current_section = None
                
                # Match content sections - removed indentation from oldContent
                elif line.strip() == "<oldContent>":
                    if current_block:
                        current_section = "old"
                        content_lines = []

                # Extract indentation from oldContent tag and skip the line
                if match := re.match(r'<oldContent\s+indentation="(\d+)">', line.strip()):
                    if current_block:
                        current_block.indentation = int(match.group(1))
                        current_section = "old"
                        content_lines = []
                    continue
                elif line.strip() == "<oldContent>":
                    if current_block:
                        current_section = "old"
                        content_lines = []
                    continue

                # Match change start
                if match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', line.strip()):
                    path, operation = match.groups()
                    current_change = XMLChange(Path(path), operation)
                    current_block = None
                    current_section = None
                
                # Match block start
                elif match := re.match(r'<block\s+description="([^"]+)">', line.strip()):
                    if current_change:
                        current_block = XMLBlock(description=match.group(1))
                        current_section = None
                
                # Match content sections
                elif line.strip() == "<oldContent>":
                    if current_block:
                        current_section = "old"
                        content_lines = []
                
                # Match section ends
                elif line.strip() == "</oldContent>":
                    if current_block:
                        current_block.old_content = content_lines
                        content_lines = []
                elif line.strip() == "<newContent>":
                    if current_block:
                        current_section = "new"
                        content_lines = []
                
                elif line.strip() == "</newContent>":
                    if current_block:
                        current_block.new_content = content_lines
                        content_lines = []
                
                # Match block end
                elif line.strip() == "</block>":
                    if current_change and current_block:
                        current_change.blocks.append(current_block)
                        current_block = None
                
                # Match change end
                elif line.strip() == "</change>":
                    if current_change:
                        changes.append(current_change)
                        current_change = None
                
                # Collect content lines
                elif current_section and current_block and not line.strip().startswith("</") and not line.strip().startswith("<"):
                    content_lines.append(line)
                
                # Collect direct content for create operations
                elif current_change and not current_block and not line.strip().startswith("</"):
                    current_change.content += line + "\n"

            return changes
            
        except Exception as e:
            self.console.print(f"[red]Error parsing XML: {str(e)}[/]")
            return []

    def _preview_changes(self, changes: List[XMLChange], raw_response: str = None) -> bool:
        """Show preview of all changes and ask for confirmation"""
        # Validate Python syntax before previewing
        invalid_files = self._validate_syntax(changes)
        if invalid_files:
            self.console.print(f"\n[red]Syntax errors detected in the following files:[/]")
            for file in invalid_files:
                self.console.print(f"- {file}")
            self.console.print("\n[red]Changes cannot be applied due to syntax errors.[/]")
            return False
            
        self.console.print("\n[cyan]Preview of changes to be applied:[/]")
        self.console.print("=" * 80)
        
        # Show changes preview
        for change in changes:
            if change.operation == 'create':
                self.console.print(f"\n[green]CREATE NEW FILE: {change.path}[/]")
                syntax = Syntax(change.content, "python", theme="monokai")
                self.console.print(syntax)
                continue
                
            if not change.path.exists():
                self.console.print(f"\n[red]SKIP: File not found - {change.path}[/]")
                continue
                
            self.console.print(f"\n[yellow]MODIFY FILE: {change.path}[/]")
            for block in change.blocks:
                self.console.print(f"\n[cyan]{block.description}[/]")
                
                if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                    if block.new_content:
                        self.console.print("[green]Append to end of file:[/]")
                        syntax = Syntax("\n".join(block.new_content), "python", theme="monokai")
                        self.console.print(syntax)
                else:
                    self.console.print("[red]Remove:[/]")
                    syntax = Syntax("\n".join(block.old_content), "python", theme="monokai")
                    self.console.print(syntax)
                    if block.new_content:  # Only show replacement if there is new content
                        self.console.print("\n[green]Replace with:[/]")
                        syntax = Syntax("\n".join(block.new_content), "python", theme="monokai")
                        self.console.print(syntax)
                    else:
                        self.console.print("[yellow](Content will be deleted)")

        self.console.print("\n" + "=" * 80)
        
        response = input("\nApply these changes? [y/N] ").lower().strip()
        
        return response == 'y'

    def _validate_syntax(self, changes: List[XMLChange]) -> Set[Path]:
        """Validate Python syntax for all files involved in the changes"""
        invalid_files = set()
        
        for change in changes:
            if change.operation == 'create':
                try:
                    ast.parse(change.content)
                except SyntaxError as e:
                    invalid_files.add(change.path)
                    self.console.print(f"[red]Syntax error in new file {change.path}: {e}[/]")
                    # Show content for new files
                    syntax = Syntax(change.content, "python", theme="monokai", line_numbers=True)
                    self.console.print(syntax)
                    
            elif change.operation == 'modify':
                if not change.path.exists():
                    continue
                
                original_content = change.path.read_text()
                modified_content = original_content
                
                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        modified_content += "\n".join(block.new_content)
                    else:
                        # Find and replace block content
                        lines = modified_content.splitlines()
                        start_idx = self._find_block_start(lines, block.old_content, block.indentation)
                        if start_idx is None:
                            continue
                        end_idx = start_idx + len(block.old_content)
                        lines[start_idx:end_idx] = block.new_content
                        modified_content = '\n'.join(lines)
                    
                try:
                    ast.parse(modified_content)
                except SyntaxError as e:
                    invalid_files.add(change.path)
                    self.console.print(f"[red]Syntax error in {change.path}: {e}[/]")
                    # Show the problematic modified content
                    syntax = Syntax(modified_content, "python", theme="monokai", line_numbers=True)
                    self.console.print(syntax)
                    
        return invalid_files

    def process_changes(self, response: str) -> bool:
        try:
            # Extract and validate XML content
            if not (match := re.search(r'<fileChanges>(.*?)</fileChanges>', response, re.DOTALL)):
                self.console.print("[red]No file changes found in response[/]")
                self.console.print("\nResponse content:")
                self.console.print(response)
                return False

            xml_content = match.group(1)
            self.console.print("[cyan]Found change block, parsing...[/]")

            # Parse changes
            changes = self._parse_xml_response(xml_content)
            if not changes:
                self.console.print("[red]No valid changes found after parsing[/]")
                return False

            # Preview and confirm changes
            if not self._preview_changes(changes, raw_response=response):
                self.console.print("[yellow]Changes cancelled by user[/]")
                return False

            # Process each change as a transaction
            for change in changes:
                if change.operation not in ('create', 'modify'):
                    self.console.print(f"[red]Invalid operation '{change.operation}' for {change.path}[/]")
                    continue

                # Handle file creation separately
                if change.operation == 'create':
                    change.path.write_text(change.content)
                    self.console.print(f"[green]Created new file: {change.path}[/]")
                    continue

                # Validate file exists for modifications
                if not change.path.exists():
                    self.console.print(f"[red]File not found: {change.path}[/]")
                    continue

                # Read file content once
                original_content = change.path.read_text().splitlines()
                modified_content = original_content.copy()

                # First pass: validate all blocks can be found
                blocks_to_process = []
                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        # Append operations are always valid
                        blocks_to_process.append((block, None))
                        continue

                    # Find the block location
                    start_idx = self._find_block_start(modified_content, block.old_content, block.indentation)
                    if start_idx is None:
                        self.console.print(f"[red]Could not find matching block in {change.path}:[/]")
                        self.console.print("\n[yellow]Looking for:[/]")
                        for line in block.old_content:
                            self.console.print(f"[yellow]{line}[/]")
                        blocks_to_process = None
                        break
                    blocks_to_process.append((block, start_idx))

                # Skip file if any block couldn't be found
                if blocks_to_process is None:
                    self.console.print(f"[red]Skipping modifications to {change.path} due to missing block[/]")
                    continue

                # Second pass: apply all changes now that we know they're all valid
                offset = 0
                for block, start_idx in reversed(blocks_to_process):
                    if start_idx is None:  # Append operation
                        if block.new_content:  # Only append if there is content
                            modified_content.extend(block.new_content)
                    else:
                        # Handle deletion (empty new_content) or replacement
                        end_idx = start_idx + len(block.old_content)
                        if block.new_content:
                            modified_content[start_idx:end_idx] = block.new_content
                        else:
                            del modified_content[start_idx:end_idx]  # Delete the block

                # Write all changes back to file
                change.path.write_text('\n'.join(modified_content))
                self.console.print(f"[green]Updated file: {change.path}[/]")

            return True

        except Exception as e:
            self.console.print(f"[red]Failed to process file changes: {e}[/]")
            return False

    def _find_block_start(self, content: List[str], block: List[str], indentation: int = 0) -> Optional[int]:
        """Find the starting index of a block in the content, handling indentation"""
        if not block:
            return None

        # Helper to get line without indentation
        def remove_indentation(line: str, indent: int) -> str:
            if line.startswith(" " * indent):
                return line[indent:]
            return line

        # Compare lines ignoring specified indentation
        for i in range(len(content) - len(block) + 1):
            matches = True
            for j, block_line in enumerate(block):
                content_line = content[i + j]
                # Remove specified indentation before comparing
                if remove_indentation(content_line, indentation) != remove_indentation(block_line, indentation):
                    matches = False
                    break
            if matches:
                return i

        return None

    def cleanup(self):
        try:
            shutil.rmtree(self.preview_dir)
        except Exception as e:
            print(f"Warning: Failed to clean up preview directory: {e}")

    def __del__(self):
        """Ensure cleanup on destruction"""
        self.cleanup()