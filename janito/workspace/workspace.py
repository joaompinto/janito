from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
import time
from rich.console import Console
from janito.config import config
from .models import WorksetContent, FileInfo, ScanPath  # Add ScanPath import
import tempfile
import shutil
import pathspec

class PathNotRelativeError(Exception):
    """Raised when a path is not relative."""
    pass

class Workspace:
    """Handles workspace scanning and content management."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._content = WorksetContent()
            self._root_dirs: Set[Path] = set()
            self._initialized = True

    def scan_files(self, paths: List[Path], recursive_paths: Set[Path]) -> None:
        """Scan files from given paths and update content.
        
        Args:
            paths: List of paths to scan
            recursive_paths: Set of paths to scan recursively
        """
        for path in paths:
            if path.is_absolute():
                raise PathNotRelativeError(f"Path must be relative: {path}")
        
        scan_time = time.time()
        
        if config.debug:
            console = Console(stderr=True)
            console.print(f"\n[cyan]Debug: Starting scan of {len(paths)} paths[/cyan]")

        # Find root directories if scanning workspace root
        if not config.skip_work and Path(".") in paths:
            self._root_dirs = {
                path.relative_to(config.workspace_dir) 
                for path in config.workspace_dir.iterdir() 
                if path.is_dir() and not path.name.startswith('.')
            }
            if config.debug:
                Console(stderr=True).print(f"[cyan]Debug: Found root directories: {self._root_dirs}[/cyan]")

        processed_files: Set[Path] = set()
        for path in paths:
            abs_path = config.workspace_dir / path
            # Skip workspace root if skip_work is enabled
            if config.skip_work and path == Path("."):
                if config.debug:
                    Console(stderr=True).print("[cyan]Debug: Skipping workspace root due to skip_work[/cyan]")
                continue
            self._scan_path(abs_path, processed_files, scan_time, recursive_paths)

        self._content.scan_completed = True
        self._content.analyzed = False
        self._content.scanned_paths = set(paths)

    def _scan_path(self, path: Path, processed_files: Set[Path], scan_time: float, 
                  recursive_paths: Set[Path]) -> None:
        """Scan a single path and process its contents."""
        if path in processed_files:
            return

        # Convert recursive_paths to absolute for comparison
        abs_recursive_paths = {config.workspace_dir / p for p in recursive_paths}

        path = path.resolve()
        processed_files.add(path)

        if path.is_dir():
            try:
                for item in path.iterdir():
                    if item.name.startswith(('.', '__pycache__')):
                        continue
                    if path in abs_recursive_paths:
                        self._scan_path(item, processed_files, scan_time, recursive_paths)
                    elif item.is_file():
                        self._scan_path(item, processed_files, scan_time, recursive_paths)
            except PermissionError:
                if config.debug:
                    Console(stderr=True).print(f"[red]Debug: Permission denied: {path}[/red]")
        elif path.is_file():
            self._process_file(path, scan_time)

    def _process_file(self, path: Path, scan_time: float, force_update: bool = False) -> None:
        """Process a single file and add it to the content."""
        try:
            # Check if file has supported extension or no extension
            supported_extensions = {
                '.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml',
                '.html', '.htm', '.css', '.js'
            }
            if path.suffix.lower() in supported_extensions or not path.suffix:
                content = path.read_text(encoding='utf-8')
                rel_path = path.relative_to(config.workspace_dir)
                
                # Check if file already exists in content
                existing_files = [f for f in self._content.files if f.name == str(rel_path)]
                if existing_files and not force_update:
                    if config.debug:
                        Console(stderr=True).print(f"[yellow]Debug: Skipping duplicate file: {rel_path}[/yellow]")
                    return
                elif existing_files:
                    # Update existing file content
                    existing_files[0].content = content
                    existing_files[0].seconds_ago = int(scan_time - path.stat().st_mtime)
                    if config.debug:
                        Console(stderr=True).print(f"[cyan]Debug: Updated content: {rel_path}[/cyan]")
                else:
                    # Add new file
                    seconds_ago = int(scan_time - path.stat().st_mtime)
                    file_info = FileInfo(
                        name=str(rel_path),
                        content=content,
                        seconds_ago=seconds_ago
                    )
                    self._content.add_file(file_info)
                    if config.debug:
                        Console(stderr=True).print(f"[cyan]Debug: Added file: {rel_path}[/cyan]")
                    
        except (UnicodeDecodeError, PermissionError) as e:
            if config.debug:
                Console(stderr=True).print(f"[red]Debug: Error reading file {path}: {str(e)}[/red]")

    def create_file(self, path: Path, content: str) -> None:
        """Create a new file in the workspace.
        
        Args:
            path: Relative path to the file to create
            content: Content to write to the file
            
        Raises:
            PathNotRelativeError: If path is absolute
            FileExistsError: If file already exists
            OSError: If parent directory creation fails
        """
        if path.is_absolute():
            raise PathNotRelativeError(f"Path must be relative: {path}")
        
        abs_path = config.workspace_dir / path
        
        if abs_path.exists():
            raise FileExistsError(f"File already exists: {path}")
        
        # Create parent directories if they don't exist
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the file
        abs_path.write_text(content, encoding='utf-8')
        
        if config.debug:
            Console(stderr=True).print(f"[green]Debug: Created file: {path}[/green]")
        
        # Add to workspace content
        scan_time = time.time()
        self._process_file(abs_path, scan_time)

    def clear(self) -> None:
        """Clear all workspace content and settings."""
        self._content = WorksetContent()

    @property
    def content(self) -> WorksetContent:
        """Get the workspace content."""
        return self._content

    @property
    def root_directories(self) -> Set[Path]:
        """Get the directories found at the workspace root."""
        return self._root_dirs

    def modify_file(self, path: Path, content: str) -> None:
        """Modify an existing file in the workspace.
        
        Args:
            path: Relative path to the file to modify
            content: New content for the file
            
        Raises:
            PathNotRelativeError: If path is absolute
            FileNotFoundError: If file doesn't exist
            OSError: If write fails
        """
        if path.is_absolute():
            raise PathNotRelativeError(f"Path must be relative: {path}")
        
        abs_path = config.workspace_dir / path
        
        if not abs_path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")
        
        # Write the file
        abs_path.write_text(content, encoding='utf-8')
        
        if config.debug:
            Console(stderr=True).print(f"[green]Debug: Modified file: {path}[/green]")
        
        # Update workspace content
        scan_time = time.time()
        self._process_file(abs_path, scan_time, force_update=True)

    def setup_preview_directory(self) -> None:
        """Setup the preview directory with workspace contents.
        
        Creates a copy of the current workspace contents in the preview directory.
        Respects .gitignore patterns and excludes .git directory.
        """
        self._preview_dir = Path(tempfile.mkdtemp(prefix='janito_preview_'))

        # Read .gitignore if it exists
        gitignore_path = config.workspace_dir / '.gitignore'
        if (gitignore_path.exists()):
            gitignore = gitignore_path.read_text().splitlines()
            # Always ignore .git directory
            gitignore.append('.git')
            spec = pathspec.PathSpec.from_lines('gitwildmatch', gitignore)
        else:
            # If no .gitignore exists, only ignore .git
            spec = pathspec.PathSpec.from_lines('gitwildmatch', ['.git'])

        # Copy workspace contents to preview directory
        for item in config.workspace_dir.iterdir():
            # Get relative path for gitignore matching
            rel_path = item.relative_to(config.workspace_dir)
            
            # Skip if matches gitignore patterns
            if spec.match_file(str(rel_path)):
                continue
            
            # Skip hidden files/directories except .gitignore
            if item.name.startswith('.') and item.name != '.gitignore':
                continue
                
            if item.is_dir():
                # For directories, we need to filter contents based on gitignore
                def copy_filtered(src, dst):
                    shutil.copytree(
                        src, 
                        dst,
                        ignore=lambda d, files: [
                            f for f in files 
                            if spec.match_file(str(Path(d).relative_to(config.workspace_dir) / f))
                        ]
                    )
                
                copy_filtered(item, self._preview_dir / item.name)
            else:
                shutil.copy2(item, self._preview_dir / item.name)

        return self._preview_dir


    def preview_create_file(self, path: Path, content: str) -> None:
        """Create a new file in the preview directory.
        
        Args:
            path: Relative path to the file to create
            content: Content to write to the file
        """
        preview_path = self.get_preview_path(path)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(content, encoding='utf-8')

    def preview_modify_file(self, path: Path, content: str) -> None:
        """Modify a file in the preview directory.
        
        Args:
            path: Relative path to the file to modify
            content: New content for the file
        """
        preview_path = self.get_preview_path(path)
        if not preview_path.exists():
            raise FileNotFoundError(f"File does not exist in preview: {path}")
        preview_path.write_text(content, encoding='utf-8')

    def get_preview_path(self, path: Path) -> Path:
        """Get the path to the preview directory."""
        return self._preview_dir / path

    def delete_file(self, path: Path) -> None:
        """Delete a file from the workspace.
        
        Args:
            path: Relative path to the file to delete
            
        Raises:
            PathNotRelativeError: If path is absolute
            FileNotFoundError: If file doesn't exist
        """
        if path.is_absolute():
            raise PathNotRelativeError(f"Path must be relative: {path}")
        
        abs_path = config.workspace_dir / path
        
        if not abs_path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")
        
        # Delete the file
        abs_path.unlink()
        
        if config.debug:
            Console(stderr=True).print(f"[green]Debug: Deleted file: {path}[/green]")

    def apply_changes(self, preview_dir: Path, created_files: List[Path], modified_files: Set[Path], deleted_files: Set[Path]):
        """Apply changes from preview directory to workspace."""
        for filename in created_files:
            content = (preview_dir / filename).read_text(encoding='utf-8')
            self.create_file(filename, content)
            print("Created workspace file: ", filename)

        for filename in modified_files:
            content = (preview_dir / filename).read_text(encoding='utf-8')
            self.modify_file(filename, content)
            print("Modified workspace file: ", filename)  # This will now include cleaned files

        for filename in deleted_files:
            self.delete_file(filename)
            print("Deleted workspace file: ", filename)


