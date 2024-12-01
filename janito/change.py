from typing import Optional, List, Set
import re
from pathlib import Path
import ast
import shutil
from rich.syntax import Syntax
from rich.console import Console
from rich.markdown import Markdown
import tempfile
import os  # Add this import
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

    def _validate_syntax(self, filepath: Path) -> tuple[Optional[SyntaxError], bool]:
        """Validate file syntax
        Returns (error, supported):
            - (None, True) -> valid syntax
            - (SyntaxError, True) -> invalid syntax
            - (None, False) -> unsupported file type
        """
        # Add more file types as needed
        SUPPORTED_TYPES = {
            '.py': self._validate_python_syntax,
        }
        
        validator = SUPPORTED_TYPES.get(filepath.suffix)
        if not validator:
            return None, False
            
        try:
            error = validator(filepath)
            return error, True
        except Exception as e:
            return SyntaxError(str(e)), True

    def _validate_python_syntax(self, filepath: Path) -> Optional[SyntaxError]:
        """Validate Python syntax"""
        try:
            with open(filepath) as f:
                ast.parse(f.read())
            return None
        except SyntaxError as e:
            return e

    def _apply_indentation(self, new_content: List[str], base_indent: int, first_line_indent: Optional[int] = None) -> List[str]:
        """Apply consistent indentation to new content
        Args:
            new_content: List of lines to indent
            base_indent: Base indentation level to apply
            first_line_indent: Optional indentation of first line in original block for relative indenting
        Returns:
            List of indented lines
        """
        if not new_content:
            return []
            
        indented_content = []
        for i, line in enumerate(new_content):
            if not line.strip():
                indented_content.append('')
                continue
                
            # For first non-empty line, use base indentation
            if not indented_content or all(not l.strip() for l in indented_content):
                curr_indent = base_indent
            else:
                # Calculate relative indentation from first line
                if first_line_indent is None:
                    first_line_indent = len(new_content[0]) - len(new_content[0].lstrip())
                # Maintain relative indentation from first line
                curr_indent = base_indent + (len(line) - len(line.lstrip()) - first_line_indent)
            indented_content.append(' ' * max(0, curr_indent) + line.lstrip())
            
        return indented_content

    def _create_preview_files(self, changes: List[XMLChange]) -> dict[Path, Path]:
        """Create preview files for all changes"""
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
                original_text = change.path.read_text()
                original_content = original_text.splitlines()
                modified_content = original_content.copy()

                for block in change.blocks:
                    if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                        if block.new_content:
                            if modified_content and not original_text.endswith('\n'):
                                modified_content[-1] = modified_content[-1] + '\n'
                            # Get the last line's indentation for appends
                            base_indent = len(modified_content[-1]) - len(modified_content[-1].lstrip()) if modified_content else 0
                            indented_content = self._apply_indentation(block.new_content, base_indent)
                            modified_content.extend(indented_content)
                    else:
                        result = self._find_block_start(modified_content, block.old_content, preview_path)
                        if result is None:
                            continue
                        start_idx, base_indent = result
                        
                        # For single-line deletions/replacements
                        if len(block.old_content) == 1:
                            if block.new_content:
                                # Replace single line
                                indented_content = self._apply_indentation(block.new_content, base_indent)
                                modified_content[start_idx:start_idx + 1] = indented_content
                            else:
                                # Delete single line
                                del modified_content[start_idx]
                        else:
                            # Multi-line block handling
                            end_idx = start_idx + len([l for l in block.old_content if l.strip()])
                            if block.new_content:
                                indented_content = self._apply_indentation(block.new_content, base_indent)
                                modified_content[start_idx:end_idx] = indented_content
                            else:
                                del modified_content[start_idx:end_idx]
                
                preview_path.write_text('\n'.join(modified_content))
            
            preview_files[change.path] = preview_path
            
        return preview_files

    def _preview_changes(self, changes: List[XMLChange], raw_response: str = None) -> tuple[bool, bool]:
        """Show preview of all changes and ask for confirmation
        Returns: (success, has_syntax_errors)"""
        # Create preview files
        preview_files = self._create_preview_files(changes)
        
        # Validate syntax for all preview files
        validation_status = {}
        has_syntax_errors = False
        for orig_path, preview_path in preview_files.items():
            error, supported = self._validate_syntax(preview_path)
            if not supported:
                validation_status[orig_path] = "[yellow]? Syntax check not supported[/]"
            elif error:
                validation_status[orig_path] = f"[red]✗ {str(error)}[/]"
                has_syntax_errors = True
            else:
                validation_status[orig_path] = "[green]✓ Valid syntax[/]"

        self.console.print("\n[cyan]Preview of changes to be applied:[/]")
        self.console.print("=" * 80)

        for change in changes:
            if change.operation == 'create':
                preview_content = preview_files[change.path].read_text()
                status = validation_status.get(change.path, '')
                self.console.print(f"\n[green]CREATE NEW FILE: {change.path}[/] {status}")
                syntax = Syntax(preview_content, "python", theme="monokai")
                self.console.print(syntax)
                continue

            if not change.path.exists():
                self.console.print(f"\n[red]SKIP: File not found - {change.path}[/]")
                continue
                
            status = validation_status.get(change.path, '')
            self.console.print(f"\n[yellow]MODIFY FILE: {change.path}[/] {status}")
            for block in change.blocks:
                self.console.print(f"\n[cyan]{block.description}[/]")
                
                if not block.old_content or (len(block.old_content) == 1 and not block.old_content[0].strip()):
                    if block.new_content:
                        # Get the last line's indentation
                        file_lines = change.path.read_text().splitlines() if change.path.exists() else []
                        base_indent = len(file_lines[-1]) - len(file_lines[-1].lstrip()) if file_lines else 0
                        indented_content = self._apply_indentation(block.new_content, base_indent)
                        self.console.print("[green]Append to end of file:[/]")
                        syntax = Syntax("\n".join(indented_content), "python", theme="monokai")
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
        
        if has_syntax_errors:
            self.console.print("\n[red]⚠️  Error: Cannot apply changes - syntax errors detected![/]")
            return False, has_syntax_errors
            
        # Only ask for confirmation if interactive and no syntax errors    
        if self.interactive:
            try:
                response = input("\nApply these changes? [y/N] ").lower().strip()
                return response == 'y', has_syntax_errors
            except EOFError:
                self.console.print("\n[yellow]Changes cancelled (Ctrl-D)[/]")
                return False, has_syntax_errors
        return True, has_syntax_errors

    def process_changes(self, response: str) -> bool:
        try:
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

            try:
                # First phase: Create and validate all preview files
                preview_result, has_syntax_errors = self._preview_changes(changes, raw_response=response)
                if not preview_result:
                    if self.interactive and not has_syntax_errors:
                        self.console.print("[yellow]Changes cancelled by user[/]")
                    return False

                # Second phase: Pre-validate all files can be written to
                preview_files = self._create_preview_files(changes)
                for change in changes:
                    preview_path = preview_files.get(change.path)
                    if not preview_path or not preview_path.exists():
                        self.console.print(f"[red]Preview file missing for {change.path}[/]")
                        return False
                    
                    try:
                        # Validate write permissions and parent directory creation
                        change.path.parent.mkdir(parents=True, exist_ok=True)
                        # Test write permission without actually writing
                        if change.path.exists():
                            os.access(change.path, os.W_OK)
                        else:
                            change.path.parent.joinpath('test').touch()
                            change.path.parent.joinpath('test').unlink()
                    except (OSError, IOError) as e:
                        self.console.print(f"[red]Cannot write to {change.path}: {e}[/]")
                        return False

                # Final phase: Apply all changes in a batch
                self.console.print("\n[cyan]Applying changes...[/]")
                try:
                    # Copy all files in a single transaction-like batch
                    for change in changes:
                        preview_path = preview_files[change.path]
                        shutil.copy2(preview_path, change.path)
                        self.console.print(f"[green]{'Created' if change.operation == 'create' else 'Updated'} file: {change.path}[/]")
                    
                    self.console.print("\n[green]✓ All changes applied successfully[/]")
                    return True

                except (OSError, IOError) as e:
                    self.console.print(f"[red]Error applying changes: {e}[/]")
                    return False

            except KeyboardInterrupt:
                self.console.print("[yellow]Changes cancelled by user (Ctrl-C)[/]")
                return False

        except EOFError:
            self.console.print("\n[yellow]Changes cancelled (Ctrl-D)[/]")
            return False
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Changes cancelled (Ctrl-C)[/]")
            return False
        except Exception as e:
            self.console.print(f"\n[red]Error applying changes: {e}[/]")
            return False

    def _find_block_start(self, content: List[str], old_content: List[str], filepath: Path = None) -> Optional[tuple[int, int]]:
        """Find the start of the indentation block containing old_content"""
        try:
            if not old_content:
                return None
            
            # Convert string content to lines if needed
            lines = content if isinstance(content, list) else content.split('\n')
            
            # For single-line content, do exact string matching
            if len(old_content) == 1:
                for i, line in enumerate(lines):
                    if line.strip() == old_content[0].strip():
                        return (i, len(line) - len(line.lstrip()))
                self.console.print(f"[yellow]Warning: Line not found in {filepath.name if filepath else 'unknown file'}: {old_content[0]}[/]")
                return None

            # For multi-line blocks, use existing block matching logic
            first_line = next((line for line in old_content if line.strip()), '')
            target_indent = len(first_line) - len(first_line.lstrip())
            
            # Search for the block
            for i in range(len(lines) - len(old_content) + 1):
                # Check if block matches at this position
                matches = True
                for j, old_line in enumerate(old_content):
                    if not old_line.strip():  # Skip empty lines
                        continue
                    if i + j >= len(lines):
                        matches = False
                        break
                    if lines[i + j].lstrip() != old_line.lstrip():
                        matches = False
                        break
                if matches:
                    return (i, target_indent)

            self.console.print(f"[yellow]Warning: Block not found in {filepath.name if filepath else 'unknown file'}[/]")
            return None
            
        except Exception as e:
            self.console.print(f"[yellow]Error finding block in {filepath.name if filepath else 'unknown file'}: {e}[/]")
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