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
    def __init__(self, interactive=True):
        self.preview_dir = Path(tempfile.mkdtemp(prefix='janito_preview_'))
        self.console = Console()
        self.workspace = Workspace()
        self.xml_parser = XMLChangeParser()
        self.interactive = interactive

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

    def _validate_syntax(self, filepath: Path) -> Optional[SyntaxError]:
        """Validate Python syntax only for .py files
        Returns None if syntax is valid, or SyntaxError if invalid"""
        if filepath.suffix != ".py":
            return None
        try:
            with open(filepath) as f:
                ast.parse(f.read())
            return None
        except SyntaxError as e:
            return e

    def _create_preview_files(self, changes: List[XMLChange]) -> dict[Path, Path]:
        """Create preview files for all changes
        Returns dict mapping original path to preview path"""
        preview_files = {}
        
        for change in changes:
            preview_path = self.preview_dir / change.path.name
            
            if change.operation == 'create':
                # For new files, use direct content or block content
                content = change.content
                if not content.strip() and change.blocks:
                    content = "\n".join(change.blocks[0].new_content)
                preview_path.write_text(content)
                
            elif change.operation == 'modify' and change.path.exists():
                # For modifications, apply changes to a copy
                original_text = change.path.read_text()
                original_content = original_text.splitlines()
                modified_content = original_content.copy()

                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        if block.new_content:
                            if modified_content and not original_text.endswith('\n'):
                                modified_content[-1] = modified_content[-1] + '\n'
                            indented_content = [line if not line.strip() else '    ' + line 
                                             for line in block.new_content]
                            modified_content.extend(indented_content)
                    else:
                        result = self._find_block_start(modified_content, block.old_content)
                        if result is None:
                            continue
                        start_idx, base_indent = result
                        end_idx = start_idx + len([l for l in block.old_content if l.strip()])
                        
                        if block.new_content:
                            # Use the base indentation of the original block
                            indented_content = []
                            for i, line in enumerate(block.new_content):
                                if not line.strip():
                                    indented_content.append('')
                                else:
                                    # First non-empty line gets base indentation
                                    # Subsequent lines maintain relative indentation
                                    if not indented_content or all(not l.strip() for l in indented_content):
                                        curr_indent = base_indent
                                    else:
                                        # Calculate relative indent from first line
                                        first_indent = len(block.new_content[0]) - len(block.new_content[0].lstrip())
                                        curr_indent = base_indent + (len(line) - len(line.lstrip()) - first_indent)
                                    indented_content.append(' ' * curr_indent + line.lstrip())
                            modified_content[start_idx:end_idx] = indented_content
                        else:
                            del modified_content[start_idx:end_idx]
                
                preview_path.write_text('\n'.join(modified_content))
            
            preview_files[change.path] = preview_path
            
        return preview_files

    def _preview_changes(self, changes: List[XMLChange], raw_response: str = None) -> bool:
        """Show preview of all changes and ask for confirmation"""
        # Create preview files
        preview_files = self._create_preview_files(changes)
        
        # Validate syntax for all preview files
        invalid_files = []
        for orig_path, preview_path in preview_files.items():
            if error := self._validate_syntax(preview_path):
                invalid_files.append((orig_path, error))
        
        if invalid_files:
            self.console.print(f"\n[red]Syntax errors detected in the following files:[/]")
            for path, error in invalid_files:
                self.console.print(f"- {path}: {error}")
                syntax = Syntax(preview_files[path].read_text(), "python", theme="monokai", line_numbers=True)
                self.console.print(syntax)
            self.console.print("\n[red]Changes cannot be applied due to syntax errors.[/]")
            return False

        if not self.interactive:
            return True

        # Rest of preview logic
        self.console.print("\n[cyan]Preview of changes to be applied:[/]")
        self.console.print("=" * 80)

        for change in changes:
            if change.operation == 'create':
                preview_content = preview_files[change.path].read_text()
                self.console.print(f"\n[green]CREATE NEW FILE: {change.path}[/]")
                syntax = Syntax(preview_content, "python", theme="monokai")
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

    def process_changes(self, response: str) -> bool:
        if not (match := re.search(r'<fileChanges>(.*?)</fileChanges>', response, re.DOTALL)):
            self.console.print("[red]No file changes found in response[/]")
            self.console.print("\nResponse content:")
            self.console.print(response)
            return False

        xml_content = f"<fileChanges>{match.group(1)}</fileChanges>"
        self.console.print("[cyan]Found change block, parsing...[/]")

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
                    content_to_write = "\n".join(change.blocks[0].new_content)
                
                if content_to_write.strip():
                    try:
                        change.path.write_text(content_to_write)
                        self.console.print(f"[green]Created new file: {change.path}[/]")
                    except (OSError, IOError) as e:
                        self.console.print(f"[red]Failed to create file {change.path}: {e}[/]")
                        return False
                else:
                    self.console.print(f"[red]Error: No content to write for {change.path}[/]")
                continue

            # Validate file exists for modifications
            if not change.path.exists():
                self.console.print(f"[red]File not found: {change.path}[/]")
                continue

            try:
                # Read file content once - read as text to preserve exact endings
                original_text = change.path.read_text()
                original_content = original_text.splitlines()
                modified_content = original_content.copy()

                # First pass: validate all blocks can be found
                blocks_to_process = []
                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        blocks_to_process.append((block, None))
                        continue

                    start_idx = self._find_block_start(modified_content, block.old_content)
                    if start_idx is None:
                        self.console.print(f"[red]Could not find matching block in {change.path}:[/]")
                        self.console.print("\n[yellow]Content to find:[/]")
                        for line in block.old_content:
                            self.console.print(f"[yellow]{line}[/]")
                        self.console.print("\n[yellow]File content:[/]")
                        for i, line in enumerate(modified_content):
                            self.console.print(f"[yellow]{i+1:4d}: {line}[/]")
                        blocks_to_process = None
                        break
                    blocks_to_process.append((block, start_idx))

                if blocks_to_process is None:
                    self.console.print(f"[red]Skipping modifications to {change.path} due to missing block[/]")
                    continue

                # Second pass: apply all changes
                for block, location in reversed(blocks_to_process):
                    if location is None:  # Append operation
                        if block.new_content:
                            if modified_content and not original_text.endswith('\n'):
                                modified_content[-1] = modified_content[-1] + '\n'
                            indented_content = [line if not line.strip() else '    ' + line 
                                             for line in block.new_content]
                            modified_content.extend(indented_content)
                    else:
                        start_idx, base_indent = location
                        end_idx = start_idx + len([l for l in block.old_content if l.strip()])
                        
                        if block.new_content:
                            # Use the base indentation of the original block
                            indented_content = []
                            for i, line in enumerate(block.new_content):
                                if not line.strip():
                                    indented_content.append('')
                                else:
                                    # First non-empty line gets base indentation
                                    # Subsequent lines maintain relative indentation
                                    if not indented_content or all(not l.strip() for l in indented_content):
                                        curr_indent = base_indent
                                    else:
                                        # Calculate relative indent from first line
                                        first_indent = len(block.new_content[0]) - len(block.new_content[0].lstrip())
                                        curr_indent = base_indent + (len(line) - len(line.lstrip()) - first_indent)
                                    indented_content.append(' ' * curr_indent + line.lstrip())
                            modified_content[start_idx:end_idx] = indented_content
                        else:
                            del modified_content[start_idx:end_idx]

                change.path.write_text('\n'.join(modified_content))
                self.console.print(f"[green]Updated file: {change.path}[/]")

            except (OSError, IOError) as e:
                self.console.print(f"[red]Failed to modify file {change.path}: {e}[/]")
                return False

        return True

    def _find_block_start(self, content: List[str], block: List[str]) -> Optional[tuple[int, int]]:
        """Find the starting index and indentation level of a block in the content
        Returns tuple of (start_index, indentation) or None if not found"""
        if not block:
            return None
            
        # Get normalized versions of block lines for comparison
        # Only normalize non-empty lines, preserve empty ones
        block_normalized = [(line.lstrip() if line.strip() else '') for line in block]
        if not any(line.strip() for line in block_normalized):
            return None

        # Find first non-empty line in block for initial match
        first_nonempty_idx = next((i for i, line in enumerate(block_normalized) if line.strip()), 0)
        first_pattern = block_normalized[first_nonempty_idx].lstrip()

        debug_info = {
            'partial_matches': [],
            'closest_match': None,
            'closest_match_line': -1,
            'closest_match_score': 0,
            'content': content  # Store content for debug output
        }

        # Compare lines, now preserving empty lines
        for i in range(len(content) - len(block_normalized) + 1):
            # Find where the first non-empty line matches
            if content[i].lstrip() != first_pattern:
                continue

            # Get indentation of first matching line
            indent = len(content[i]) - len(content[i].lstrip())
            
            matches = True
            matching_lines = 0
            mismatch_details = None

            # Check all lines, including empty ones
            for j, block_line in enumerate(block_normalized):
                content_idx = i + j
                content_line = content[content_idx]
                
                # For empty lines, just check if both are empty
                if not block_line.strip():
                    if content_line.strip():
                        matches = False
                        mismatch_details = {
                            'line_number': content_idx,
                            'expected': 'empty line',
                            'found': content_line
                        }
                        break
                else:
                    if content_line.lstrip() != block_line:
                        matches = False
                        mismatch_details = {
                            'line_number': content_idx,
                            'expected': block_line,
                            'found': content_line.lstrip()
                        }
                        break
                matching_lines += 1

            if matches:
                return (i, indent)
            
            # Store partial match info
            match_score = matching_lines / len(block_normalized)
            debug_info['partial_matches'].append({
                'start_line': i,
                'matched_lines': matching_lines,
                'total_lines': len(block_normalized),
                'score': match_score,
                'mismatch': mismatch_details
            })
            if match_score > debug_info['closest_match_score']:
                debug_info['closest_match_score'] = match_score
                debug_info['closest_match'] = content[i:i+len(block_normalized)]
                debug_info['closest_match_line'] = i

        # If we get here, no match was found - show debug info
        self.console.print(":warning: [yellow]Block not found in file. Debug information:[/]")
        self.console.print(f"[yellow]Looking for {len(block_normalized)} lines:[/]")
        for line in block_normalized:
            self.console.print(f"[yellow]  {line}[/]")

        self.console.print("\n[yellow]File content:[/]")
        syntax = Syntax("\n".join(debug_info['content']), "python", theme="monokai", line_numbers=True)
        self.console.print(syntax)

        if debug_info['partial_matches']:
            best_match = max(debug_info['partial_matches'], key=lambda x: x['score'])
            self.console.print("\n[yellow]Best partial match:[/]")
            self.console.print(f"[yellow]At line {best_match['start_line']+1}:[/]")
            for line in debug_info['closest_match']:
                self.console.print(f"[yellow]  {line}[/]")
            self.console.print(f"[yellow]Matched {best_match['matched_lines']}/{best_match['total_lines']} lines[/]")
            if best_match['mismatch']:
                self.console.print("\n[red]First mismatch:[/]")
                self.console.print(f"[red]At line {best_match['mismatch']['line_number']+1}:[/]")
                self.console.print(f"[red]Expected: {best_match['mismatch']['expected']}[/]")
                self.console.print(f"[red]Found:    {best_match['mismatch']['found']}[/]")

        return None

    def cleanup(self):
        """Clean up preview directory"""
        try:
            shutil.rmtree(self.preview_dir)
        except (OSError, IOError) as e:
            self.console.print(f"[yellow]Warning: Failed to clean up preview directory: {e}[/]")

    def __del__(self):
        """Ensure cleanup on destruction"""
        self.cleanup()