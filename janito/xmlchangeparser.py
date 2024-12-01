from typing import List
from pathlib import Path
import re
from dataclasses import dataclass
from rich.console import Console

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

class XMLChangeParser:
    """XML parser for file changes"""
    def __init__(self):
        self.console = Console()
        self.current_operation = None
        self.has_invalid_tags = False  # Track invalid tag occurrences

    def _validate_tag_format(self, line: str) -> bool:
        """Validate that a line contains only a single XML tag and nothing else"""
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith('<?xml'):
            return True
            
        # Allow empty content tags in one line
        if stripped in ('<oldContent></oldContent>', '<newContent></newContent>'):
            return True
            
        # Check if line contains exactly one XML tag and nothing else
        return bool(re.match(r'^\s*<[^>]+>\s*$', line))

    def _validate_path(self, path_str: str) -> bool:
        """Validate that path is relative and does not try to escape workspace"""
        try:
            path = Path(path_str)
            # Check if path is absolute
            if path.is_absolute():
                self.console.print(f"[red]Error: Path must be relative: {path_str}[/]")
                return False
            # Check for path traversal attempts
            if '..' in path.parts:
                self.console.print(f"[red]Error: Path cannot contain '..': {path_str}[/]")
                return False
            return True
        except Exception:
            self.console.print(f"[red]Error: Invalid path format: {path_str}[/]")
            return False

    def parse_response(self, response: str) -> List[XMLChange]:
        """Parse XML response according to format specification:
        <fileChanges>
            <change path="file.py" operation="create|modify">
                <block description="Description of changes">
                    <oldContent>
                        // Exact content to be replaced (empty for create/append)
                        // Must match existing indentation exactly
                    </oldContent>
                    <newContent>
                        // New content to replace the old content
                        // Must include desired indentation
                    </newContent>
                </block>
            </change>
        </fileChanges>
        """
        changes = []
        current_change = None
        current_block = None
        current_section = None
        content_buffer = []
        in_content = False
        self.current_operation = None
        self.has_invalid_tags = False  # Reset at start of parsing
        
        try:
            lines = response.splitlines()
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # Update operation tracking when encountering a change tag
                if match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', stripped):
                    _, operation = match.groups()
                    self.current_operation = operation
                    self.has_invalid_tags = False  # Reset for new change

                # Reset operation on change end
                elif stripped == '</change>':
                    if current_change and not self.has_invalid_tags:
                        changes.append(current_change)
                    current_change = None
                    self.current_operation = None
                    continue

                # Validate tag format
                if not self._validate_tag_format(line) and not in_content:
                    self.console.print(f"[red]Invalid tag format at line {i+1}: {line}[/]")
                    self.has_invalid_tags = True
                    continue

                if not stripped and not in_content:
                    continue

                if stripped.startswith('<fileChanges>'):
                    continue
                elif stripped.startswith('</fileChanges>'):
                    break
                    
                elif match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', stripped):
                    path, operation = match.groups()
                    # Validate path before creating change object
                    if not self._validate_path(path):
                        self.has_invalid_tags = True
                        continue
                    if operation not in ('create', 'modify'):
                        self.console.print(f"[red]Invalid operation '{operation}' - skipping change[/]")
                        continue
                    current_change = XMLChange(Path(path), operation)
                    current_block = None
                elif stripped == '</change>':
                    if current_change:
                        changes.append(current_change)
                        current_change = None
                    continue

                elif match := re.match(r'<block\s+description="([^"]+)">', stripped):
                    if current_change:
                        current_block = XMLBlock(description=match.group(1))
                elif stripped == '</block>':
                    if current_change and current_block:
                        current_change.blocks.append(current_block)
                        current_block = None
                    continue

                elif stripped in ('<oldContent>', '<newContent>'):
                    if current_block:
                        current_section = 'old' if 'old' in stripped else 'new'
                        content_buffer = []
                        in_content = True
                elif stripped in ('</oldContent>', '</newContent>'):
                    if current_block and in_content:
                        # Find the common indentation of non-empty lines
                        non_empty_lines = [line for line in content_buffer if line.strip()]
                        if non_empty_lines:
                            # Find minimal indent by looking at first real line
                            first_line = next(line for line in content_buffer if line.strip())
                            indent = len(first_line) - len(first_line.lstrip())
                            # Remove only the common indentation from XML
                            content = []
                            for line in content_buffer:
                                if line.strip():
                                    # Remove only the XML indentation
                                    content.append(line[indent:])
                                elif content:  # Keep empty lines only if we have previous content
                                    content.append('')
                        else:
                            content = []

                        if current_section == 'old':
                            current_block.old_content = content
                        else:
                            current_block.new_content = content
                        in_content = False
                        current_section = None
                    continue
                
                elif in_content:
                    # Store lines with their original indentation
                    content_buffer.append(line)
                elif current_change and not current_block and not stripped.startswith('<'):
                    if stripped:
                        current_change.content += line + '\n'

            return [c for c in changes if not self.has_invalid_tags]
            
        except Exception as e:
            self.console.print(f"[red]Error parsing XML: {str(e)}[/]")
            self.console.print(f"[red]Error occurred at line {i + 1}:[/]")
            self.console.print("\nOriginal response:")
            self.console.print(response)
            return []