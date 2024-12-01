from pathlib import Path
from typing import List, Dict
import ast
import re

class Workspace:
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path().absolute()
        self.default_exclude = [".janito", "__pycache__", ".git", ".janito/history"]  # Added .janito/history
        self.default_patterns = ["*.py", "*.txt", "*.md", "*.toml", "**/.gitignore"]
        self.history_file = self.base_path / ".janito" / "history"
        # Create .janito directory if it doesn't exist
        (self.base_path / ".janito").mkdir(exist_ok=True)

    def generate_file_structure(self, pattern: str = None, exclude_patterns: List[str] = None) -> Dict:
        """Generate a tree structure of files in the workspace directory."""
        exclude_patterns = exclude_patterns or self.default_exclude
        patterns = [pattern] if pattern else self.default_patterns
        
        tree = {}
        try:
            base_path = self.base_path.resolve()
            
            for pattern in patterns:
                for file in sorted(base_path.rglob(pattern)):
                    try:
                        import fnmatch

                        if any(fnmatch.fnmatch(str(file), pat) for pat in exclude_patterns):
                            continue
                        
                        try:
                            file.relative_to(base_path)
                        except ValueError:
                            continue
                        
                        rel_path = file.relative_to(base_path)
                        current = tree
                        
                        for part in rel_path.parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[rel_path.parts[-1]] = None
                        
                    except Exception as e:
                        print(f"Error processing file {file}: {e}")
                        continue
                
        except Exception as e:
            print(f"Error generating file structure: {e}")
            return {}
            
        return tree

    def get_files_content(self, exclude_patterns: List[str] = None) -> str:
        """Get content of files in workspace directory"""
        content = []
        exclude_patterns = exclude_patterns or self.default_exclude
        base_path = self.base_path.resolve()
        
        for pattern in self.default_patterns:
            for file in sorted(base_path.rglob(pattern)):
                if any(pat in str(file) for pat in exclude_patterns):
                    continue
                
                try:
                    rel_path = file.relative_to(base_path)
                except ValueError:
                    continue
                
                content.append(f"### {rel_path} ###\n{file.read_text()}\n")
                    
        return "\n".join(content)

    def format_tree(self, tree: Dict, prefix: str = "", is_last: bool = True) -> List[str]:
        """Format a tree dictionary into a list of strings showing the structure."""
        lines = []
        
        if not tree:
            return lines
            
        for i, (name, subtree) in enumerate(tree.items()):
            is_last_item = i == len(tree) - 1
            connector = "└── " if is_last_item else "├── "
            
            if subtree is None:  # File
                lines.append(f"{prefix}{connector}{name}")
            else:  # Directory
                lines.append(f"{prefix}{connector}{name}/")
                next_prefix = prefix + ("    " if is_last_item else "│   ")
                lines.extend(self.format_tree(subtree, next_prefix))
                
        return lines

    def get_workspace_status(self) -> str:
        """Get a formatted string of the workspace structure"""
        tree = self.generate_file_structure()
        if not tree:
            return "No files found in the current workspace."
        tree_lines = self.format_tree(tree)
        return "Files in workspace:\n" + "\n".join(tree_lines)

    def get_excluded_files(self) -> List[str]:
        """Get a list of files and directories that are excluded from the workspace"""
        exclude_patterns = self.default_exclude
        gitignore_paths = list(self.base_path.rglob(".gitignore"))
        for p in gitignore_paths:
            with open(p) as f:
                ignore_patterns = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            exclude_patterns.extend(ignore_patterns)
        
        excluded_files = []
        base_path = self.base_path.resolve()
        
        for file in base_path.rglob('*'):
            if any(fnmatch.fnmatch(str(file), pat) for pat in exclude_patterns):
                try:
                    rel_path = file.relative_to(base_path)
                    excluded_files.append(str(rel_path))
                except ValueError:
                    continue
        
        return excluded_files

    def print_excluded_files(self):
        """Print files and patterns excluded from workspace"""
        excluded_files = self.get_excluded_files()
        if not excluded_files:
            self.console.print("No excluded files or directories found.")
            return
        
        self.console.print("\nExcluded files and directories:")
        for path in excluded_files:
            self.console.print(f"  {path}")

    def calculate_stats(self) -> Dict[str, int]:
        """Calculate statistics about the current directory contents."""
        stats = {
            "total_files": 0,
            "total_dirs": 0,
            "total_size": 0
        }
        for path in self.base_path.rglob('*'):
            if path.is_file():
                stats["total_files"] += 1
                stats["total_size"] += path.stat().st_size
            elif path.is_dir():
                stats["total_dirs"] += 1
        return stats


    def print_workspace_structure(self):
        """Print the workspace structure with statistics"""
        stats = self.calculate_stats()
        tree = self.generate_file_structure()
        if not tree:
            print("No files found in the current workspace.")
            return
        tree_lines = self.format_tree(tree)
        print("Workspace structure:")
        print("=" * 80)
        print(f"Total files: {stats['total_files']}")
        print(f"Total directories: {stats['total_dirs']}")
        print(f"Total size: {stats['total_size']} bytes")
        print("=" * 80)
        print("\n".join(tree_lines))