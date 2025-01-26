from pathlib import Path
from typing import Set
import ast
import yaml
import subprocess
import sys
import os

class Validator:
    def __init__(self, preview_dir: Path):
        self.preview_dir = preview_dir
        self.validated_files: Set[Path] = set()

    def validate_python_syntax(self, filepath: Path):
        """Validate Python file syntax using ast."""
        try:
            with open(filepath, 'r', encoding="utf-8") as file:
                content = file.read()
            ast.parse(content, filename=str(filepath))
        except SyntaxError as e:
            raise ValueError(f"Python syntax error in {filepath}: {e}")
        except Exception as e:
            raise ValueError(f"Error validating {filepath}: {e}")

    def validate_files(self, files: Set[Path]):
        """Validate all modified files."""
        for filepath in files:
            full_path = self.preview_dir / filepath
            if not full_path.exists():
                raise ValueError(f"File not found after changes: {filepath}")
                
            if filepath.suffix == '.py':
                self.validate_python_syntax(full_path)
            
            self.validated_files.add(filepath)
            from rich import print as rprint
            rprint(f"[green]✓[/green] Validated [cyan]{filepath}[/cyan]")

    def run_tests(self):
        """Run tests if configured in janito.yaml."""
        config_file = self.preview_dir / 'janito.yaml'
        if not config_file.exists():
            print("No test configuration found")
            return

        try:
            with open(config_file) as f:
                config = yaml.safe_load(f)
            
            test_cmd = config.get('test_cmd')
            if not test_cmd:
                print("No test_cmd found in configuration")
                return

            print(f"Running test command: {test_cmd}")
            
            # Save current directory
            original_dir = Path.cwd()
            try:
                # Change to preview directory
                os.chdir(self.preview_dir)
                # Run the test command
                exit_code = os.system(test_cmd)
            finally:
                # Restore original directory
                os.chdir(original_dir)
            
            if exit_code != 0:
                raise ValueError(f"Test command failed with exit code {exit_code}")
            
            from rich.panel import Panel
            from rich import print as rprint
            
            # Create a summary panel
            validated_files_list = "\n".join([f"[cyan]• {f}[/cyan]" for f in sorted(self.validated_files)])
            summary = Panel(
                f"[green]✓[/green] All files validated successfully:\n\n{validated_files_list}",
                title="[bold green]Validation Summary[/bold green]",
                border_style="green"
            )
            rprint("\n" + summary + "\n")
            print("Tests completed successfully")

        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing janito.yaml: {e}")
        except Exception as e:
            raise ValueError(f"Error running tests: {e}")