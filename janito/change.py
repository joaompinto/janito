import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Set, Union
import ast
import shutil
from rich.syntax import Syntax
from rich.console import Console
from rich.text import Text
from dataclasses import dataclass
from enum import Enum
import tempfile
from janito.utils import build_context_prompt  # Add import

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
    blocks: List[XMLBlock] = None  # Fixed type annotation syntax
    content: str = ""

    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []

class DeltaType(Enum):
    INSERT = 'insert'
    DELETE = 'delete'
    REPLACE = 'replace'
    KEEP = 'keep'
    BLOCK_INSERT = 'block_insert'
    BLOCK_DELETE = 'block_delete'
    BLOCK_REPLACE = 'block_replace'

@dataclass
class Delta:
    type: DeltaType
    start_line: int
    end_line: int
    content: List[str]
    new_content: Optional[List[str]] = None  # For BLOCK_REPLACE type

    @property
    def is_modification(self) -> bool:
        return self.type not in (DeltaType.KEEP,)

    def __str__(self) -> str:
        if self.type == DeltaType.BLOCK_INSERT:
            return f"Insert at line {self.start_line}:\n" + "\n".join(self.content)
        elif self.type == DeltaType.BLOCK_DELETE:
            return f"Delete lines {self.start_line}-{self.end_line}:\n" + "\n".join(self.content)
        elif self.type == DeltaType.BLOCK_REPLACE:
            return (f"Replace lines {self.start_line}-{self.end_line}:\n" +
                   "- " + "\n- ".join(self.content) + "\n" +
                   "+ " + "\n+ ".join(self.new_content or []))
        return f"Keep lines {self.start_line}-{self.end_line}"

@dataclass
class DeltaResult:
    filepath: Path
    content: str
    is_new_file: bool = False
    deltas: Optional[List[Delta]] = None
    metadata: Optional['ChangeMetadata'] = None

    def get_changes_summary(self) -> List[str]:
        """Get a human-readable summary of changes"""
        if not self.deltas:
            return []
        
        changes = []
        for delta in self.deltas:
            if delta.type == DeltaType.INSERT:
                changes.append(f"Added line {delta.line_number}: {delta.content}")
            elif delta.type == DeltaType.DELETE:
                changes.append(f"Removed line {delta.line_number}: {delta.content}")
            elif delta.type == DeltaType.REPLACE:
                changes.append(f"Modified line {delta.line_number}: {delta.content} → {delta.new_content}")
        return changes

@dataclass
class ChangeMetadata:
    operation: str
    filepath: Path
    expected_changes: Set[str] = None
    actual_changes: Set[str] = None
    
    def __post_init__(self):
        self.expected_changes = set() if self.expected_changes is None else self.expected_changes
        self.actual_changes = set() if self.actual_changes is None else self.actual_changes
    
    @property
    def is_valid(self) -> bool:
        return bool(self.expected_changes and self.actual_changes)

    @property
    def missing_changes(self) -> Set[str]:
        return self.expected_changes - self.actual_changes

    @property
    def unexpected_changes(self) -> Set[str]:
        return self.actual_changes - self.expected_changes

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
                # Remove strip() to preserve whitespace
                if not line:
                    continue

                # Match change start - strip only for matching
                if match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', line.strip()):
                    path, operation = match.groups()
                    current_change = XMLChange(Path(path), operation)
                    current_block = None
                    current_section = None
                
                # Match block start - strip only for matching
                elif match := re.match(r'<block\s+description="([^"]+)">', line.strip()):
                    if current_change:
                        current_block = XMLBlock(description=match.group(1))
                        current_section = None
                
                # Match content sections - strip only for matching
                elif line.strip() == "<oldContent>":
                    if current_block:
                        current_section = "old"
                        content_lines = []
                elif line.strip() == "<newContent>":
                    if current_block:
                        current_section = "new"
                        content_lines = []
                
                # Match section ends - strip only for matching
                elif line.strip() == "</oldContent>":
                    if current_block:
                        current_block.old_content = content_lines
                        content_lines = []
                elif line.strip() == "</newContent>":
                    if current_block:
                        current_block.new_content = content_lines
                        content_lines = []
                
                # Match block end - strip only for matching
                elif line.strip() == "</block>":
                    if current_change and current_block:
                        current_change.blocks.append(current_block)
                        current_block = None
                
                # Match change end - strip only for matching
                elif line.strip() == "</change>":
                    if current_change:
                        changes.append(current_change)
                        current_change = None
                
                # Collect content lines without stripping
                elif current_section and current_block:
                    content_lines.append(line)
                
                # Collect direct content for create operations without stripping
                elif current_change and not current_block and not line.strip().startswith("</"):
                    current_change.content += line + "\n"

            return changes
            
        except Exception as e:
            self.console.print(f"[red]Error parsing XML: {str(e)}[/]")
            return []

    def _preview_changes(self, changes: List[XMLChange]) -> bool:
        """Show preview of all changes and ask for confirmation"""
        self.console.print("\n[cyan]Preview of changes to be applied:[/]")
        self.console.print("=" * 80)

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
                    self.console.print("[green]Append to end of file:[/]")
                    syntax = Syntax("\n".join(block.new_content), "python", theme="monokai")
                    self.console.print(syntax)
                else:
                    self.console.print("[red]Remove:[/]")
                    syntax = Syntax("\n".join(block.old_content), "python", theme="monokai")
                    self.console.print(syntax)
                    self.console.print("\n[green]Replace with:[/]")
                    syntax = Syntax("\n".join(block.new_content), "python", theme="monokai")
                    self.console.print(syntax)

        self.console.print("\n" + "=" * 80)
        response = input("\nApply these changes? [y/N] ").lower().strip()
        return response == 'y'

    def process_changes(self, response: str) -> bool:
        try:
            # Extract content block using regex
            if match := re.search(r'<fileChanges>(.*?)</fileChanges>', response, re.DOTALL):
                xml_content = match.group(1)
                self.console.print("[cyan]Found change block, parsing...[/]")
            else:
                self.console.print("[red]No file changes found in response[/]")
                self.console.print("\nResponse content:")
                self.console.print(response)
                return False

            # Parse changes
            changes = self._parse_xml_response(xml_content)
            if not changes:
                self.console.print("[red]No valid changes found after parsing[/]")
                return False

            # Preview changes and get user confirmation
            if not self._preview_changes(changes):
                self.console.print("[yellow]Changes cancelled by user[/]")
                return False

            # Process each change
            for change in changes:
                if change.operation not in ('create', 'modify'):
                    self.console.print(f"[red]Invalid operation '{change.operation}' for {change.path}[/]")
                    continue

                if change.operation == 'create':
                    # Handle file creation
                    change.path.write_text(change.content)
                    self.console.print(f"[green]Created new file: {change.path}[/]")
                    continue

                # Handle file modifications
                if not change.path.exists():
                    self.console.print(f"[red]File not found: {change.path}[/]")
                    continue

                original_content = change.path.read_text().splitlines()
                modified_content = original_content.copy()

                # Process each block
                for block in change.blocks:
                    self.console.print(f"\n[cyan]Applying: {block.description}[/]")

                    # Handle empty oldContent as append operation
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        self.console.print("[cyan]Appending content to end of file[/]")
                        modified_content.extend(block.new_content)
                        continue

                    # Find and replace the block
                    start_idx = self._find_block_start(modified_content, block.old_content)
                    if start_idx is None:
                        self.console.print("[red]Could not find matching block in file:[/]")
                        self.console.print("\n[yellow]Looking for:[/]")
                        for line in block.old_content:
                            self.console.print(f"[yellow]{line}[/]")
                        continue

                    # Replace the block
                    modified_content[start_idx:start_idx + len(block.old_content)] = block.new_content

                # Write modified content back to file
                change.path.write_text('\n'.join(modified_content))
                self.console.print(f"[green]Updated file: {change.path}[/]")

            return True

        except Exception as e:
            self.console.print(f"[red]Failed to process file changes: {e}[/]")
            return False

    def _find_block_start(self, content: List[str], block: List[str]) -> Optional[int]:
        """Find the starting index of a block in the content, ignoring empty lines and whitespace"""
        if not block:
            return None

        # Filter out empty lines and normalize whitespace
        def normalize(lines: List[str]) -> List[str]:
            return [line.strip() for line in lines if line.strip()]

        normalized_content = normalize(content)
        normalized_block = normalize(block)

        if not normalized_block:
            return None

        # Try to find the block in normalized content
        for i in range(len(normalized_content) - len(normalized_block) + 1):
            if all(normalized_content[i + j] == normalized_block[j] for j in range(len(normalized_block))):
                # Find the actual line number in original content
                line_count = 0
                for idx, line in enumerate(content):
                    if line.strip():
                        if line_count == i:
                            return idx
                        line_count += 1
                return None

        return None

    def cleanup(self):
        try:
            shutil.rmtree(self.preview_dir)
        except Exception as e:
            print(f"Warning: Failed to clean up preview directory: {e}")

    def __del__(self):
        """Ensure cleanup on destruction"""
        self.cleanup()