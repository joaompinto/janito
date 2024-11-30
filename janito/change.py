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
from janito.error import handle_error, error_handler, JanitoError, FileOperationError
# Remove ET import since we're using line-by-line parsing

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
    blocks: List[XMLBlock] = None
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
        return """Current directory status:
{dir_status}

{files_content}

User request for file operation: {file_request}

Please provide file changes in the following format:

<fileChanges>
<change path="example.py" operation="modify">
<block description="Update database connection function">
<oldContent>
def connect_db():
    return sqlite3.connect('database.db')
</oldContent>
<newContent>
def connect_db():
    try:
        return sqlite3.connect('database.db')
    except sqlite3.Error as error:
        print('Failed to connect:', str(error))
        raise
</newContent>
</block>
</change>
</fileChanges>

Requirements:
1. Use <block> tags with descriptive comments
2. Provide both <oldContent> and <newContent> for changes
3. Include enough context in <oldContent> to uniquely identify the section
4. For new files, use operation="create" and only provide complete content
5. For new blocks in existing files, omit <oldContent>
""".format(
            dir_status=dir_status,
            files_content=files_content if files_content else "",
            file_request=file_request
        )

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
                line = line.strip()
                if not line:
                    continue

                # Match change start
                if match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', line):
                    path, operation = match.groups()
                    current_change = XMLChange(Path(path), operation)
                    current_block = None
                    current_section = None
                
                # Match block start
                elif match := re.match(r'<block\s+description="([^"]+)">', line):
                    if current_change:
                        current_block = XMLBlock(description=match.group(1))
                        current_section = None
                
                # Match content sections
                elif line == "<oldContent>":
                    if current_block:
                        current_section = "old"
                        content_lines = []
                elif line == "<newContent>":
                    if current_block:
                        current_section = "new"
                        content_lines = []
                
                # Match section ends
                elif line == "</oldContent>":
                    if current_block:
                        current_block.old_content = content_lines
                        content_lines = []
                elif line == "</newContent>":
                    if current_block:
                        current_block.new_content = content_lines
                        content_lines = []
                
                # Match block end
                elif line == "</block>":
                    if current_change and current_block:
                        current_change.blocks.append(current_block)
                        current_block = None
                
                # Match change end
                elif line == "</change>":
                    if current_change:
                        changes.append(current_change)
                        current_change = None
                
                # Collect content lines
                elif current_section and current_block:
                    content_lines.append(line)
                
                # Collect direct content for create operations
                elif current_change and not current_block and not line.startswith("</"):
                    current_change.content += line + "\n"

            return changes
            
        except Exception as e:
            self.console.print(f"[red]Error parsing XML: {str(e)}[/]")
            return []

    @error_handler(exit_on_error=False)
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

                    # Find and replace the block
                    start_idx = self._find_block_start(modified_content, block.old_content)
                    if start_idx is None:
                        self.console.print("[red]Could not find matching block in file[/]")
                        continue

                    # Replace the block
                    modified_content[start_idx:start_idx + len(block.old_content)] = block.new_content

                # Write modified content back to file
                change.path.write_text('\n'.join(modified_content))
                self.console.print(f"[green]Updated file: {change.path}[/]")

            return True

        except Exception as e:
            raise FileOperationError("Failed to process file changes", cause=e)

    def _find_block_start(self, content: List[str], block: List[str]) -> Optional[int]:
        """Find the starting index of a block in the content"""
        if not block:
            return None

        for i in range(len(content) - len(block) + 1):
            if all(content[i + j].strip() == block[j].strip() for j in range(len(block))):
                return i

        return None

    @error_handler(exit_on_error=False)
    def cleanup(self):
        """Clean up temporary files"""
        try:
            shutil.rmtree(self.preview_dir)
        except Exception as e:
            raise FileOperationError(f"Failed to clean up preview directory: {e}", cause=e)

    def __del__(self):
        """Ensure cleanup on destruction"""
        self.cleanup()