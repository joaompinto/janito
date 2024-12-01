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
    def __init__(self):
        self.console = Console()

    def _validate_tag_format(self, line: str) -> bool:
        """Validate that a line contains only a single XML tag and nothing else"""
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith('<?xml'):
            return True
        # Check if line contains exactly one XML tag and nothing else
        return bool(re.match(r'^\s*<[^>]+>\s*$', line))

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
        
        try:
            lines = response.splitlines()
            for i, line in enumerate(lines):
                # Validate tag format
                if not self._validate_tag_format(line) and not in_content:
                    self.console.print(f"[red]Invalid tag format at line {i+1}: {line}[/]")
                    continue

                stripped = line.strip()
                
                if not stripped and not in_content:
                    continue

                if stripped.startswith('<fileChanges>'):
                    continue
                elif stripped.startswith('</fileChanges>'):
                    break
                    
                elif match := re.match(r'<change\s+path="([^"]+)"\s+operation="([^"]+)">', stripped):
                    path, operation = match.groups()
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
                        # Only trim empty lines at start/end, preserve content lines
                        content = content_buffer
                        # Remove leading empty lines
                        while content and not content[0].strip():
                            content.pop(0)
                        # Remove trailing empty lines    
                        while content and not content[-1].strip():
                            content.pop()
                        
                        if current_section == 'old':
                            current_block.old_content = [line.rstrip() for line in content]
                        else:
                            current_block.new_content = [line.rstrip() for line in content]
                        in_content = False
                        current_section = None
                    continue
                
                elif in_content:
                    # Add all lines within content tags without filtering
                    content_buffer.append(line)
                elif current_change and not current_block and not stripped.startswith('<'):
                    if stripped:
                        current_change.content += line.rstrip() + '\n'

            return changes
            
        except Exception as e:
            self.console.print(f"[red]Error parsing XML: {str(e)}[/]")
            self.console.print(f"[red]Error occurred at line {i + 1}:[/]")
            self.console.print("\nOriginal response:")
            self.console.print(response)
            return []