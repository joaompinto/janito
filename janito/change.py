from typing import Optional, List, Set
import re
from pathlib import Path
import ast
import shutil
from rich.syntax import Syntax
from rich.console import Console
import tempfile
from janito.workspace import Workspace
from janito.xmlchangeparser import XMLChangeParser, XMLChange

class FileChangeHandler:
    def __init__(self):
        self.preview_dir = Path(tempfile.mkdtemp(prefix='janito_preview_'))
        self.console = Console()
        self.workspace = Workspace()
        self.xml_parser = XMLChangeParser()

    # Remove generate_changes_prompt method as it's not being used

    # Remove _parse_xml_response method as it's replaced by xml_parser

    def test_parse_empty_block(self) -> bool:
        """Test parsing of XML with empty content blocks"""
        test_xml = '''<fileChanges>
    <change path="hello.py" operation="create">
        <block description="Create new file hello.py">
            <oldContent></oldContent>
            <newContent></newContent>
        </block>
    </change>
</fileChanges>'''

        try:
            changes = self.xml_parser.parse_response(test_xml)
            if not changes:
                self.console.print("[red]Error: No changes parsed[/]")
                return False

            change = changes[0]
            if (change.path.name != "hello.py" or 
                change.operation != "create" or 
                not change.blocks or 
                change.blocks[0].description != "Create new file hello.py"):
                self.console.print("[red]Error: Parsed change does not match expected structure[/]")
                return False

            block = change.blocks[0]
            if block.old_content != [] or block.new_content != []:
                self.console.print("[red]Error: Content lists should be empty[/]")
                return False

            self.console.print("[green]Empty block parsing test passed[/]")
            return True

        except Exception as e:
            self.console.print(f"[red]Test failed with error: {e}[/]")
            return False

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
                # Check both direct content and block content
                has_content = bool(change.content.strip())
                has_block_content = any(block.new_content for block in change.blocks)
                
                if not (has_content or has_block_content):
                    self.console.print(f"\n[red]Error: Create operation for {change.path} has no content.[/]")
                    return False
                
                if has_content:
                    content_to_show = change.content
                else:
                    content_to_show = "\n".join(change.blocks[0].new_content)
                    
                self.console.print(f"\n[green]CREATE NEW FILE: {change.path}[/]")
                syntax = Syntax(content_to_show, "python", theme="monokai")
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
                        start_idx = self._find_block_start(lines, block.old_content)
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
            if not (match := re.search(r'<fileChanges>(.*?)</fileChanges>', response, re.DOTALL)):
                self.console.print("[red]No file changes found in response[/]")
                self.console.print("\nResponse content:")
                self.console.print(response)
                return False

            xml_content = f"<fileChanges>{match.group(1)}</fileChanges>"
            self.console.print("[cyan]Found change block, parsing...[/]")

            # Use the xml_parser instance
            changes = self.xml_parser.parse_response(xml_content)
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
                    content_to_write = change.content
                    if not content_to_write.strip() and change.blocks:
                        # If no direct content but we have blocks, use the new content from first block
                        content_to_write = "\n".join(change.blocks[0].new_content)
                    
                    if content_to_write.strip():
                        change.path.write_text(content_to_write)
                        self.console.print(f"[green]Created new file: {change.path}[/]")
                    else:
                        self.console.print(f"[red]Error: No content to write for {change.path}[/]")
                    continue

                # Validate file exists for modifications
                if not change.path.exists():
                    self.console.print(f"[red]File not found: {change.path}[/]")
                    continue

                # Read file content once - read as text to preserve exact endings
                original_text = change.path.read_text()
                original_content = original_text.splitlines()
                modified_content = original_content.copy()

                # First pass: validate all blocks can be found
                blocks_to_process = []
                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        # Append operations are always valid
                        blocks_to_process.append((block, None))
                        continue

                    # Find the block location
                    start_idx = self._find_block_start(modified_content, block.old_content)
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
                            # Ensure there's a newline before appending if file isn't empty and doesn't end with one
                            if modified_content and not original_text.endswith('\n'):
                                modified_content[-1] = modified_content[-1] + '\n'
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

    def _find_block_start(self, content: List[str], block: List[str]) -> Optional[int]:
        """Find the starting index of a block in the content with exact matching"""
        if not block:
            return None

        # Compare lines exactly including indentation
        for i in range(len(content) - len(block) + 1):
            matches = True
            for j, block_line in enumerate(block):
                if content[i + j] != block_line:
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