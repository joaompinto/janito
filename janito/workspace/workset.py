from pathlib import Path
from typing import List, Set
from .show import show_workset_analysis
from rich.console import Console
from janito.config import config
from .models import WorksetContent, ScanPath, ScanType
from .workspace import Workspace

class PathNotRelativeError(Exception):
    """Raised when a path is not relative."""
    pass

class Workset:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._scan_paths: List[ScanPath] = []
        self._content = WorksetContent()
        self._workspace = Workspace()
        if not config.skip_work:
            self.add_scan_path(Path("."))

    def add_scan_path(self, path: Path, scan_type: ScanType = ScanType.PLAIN) -> None:
        """Add a path with specific scan type.

        Args:
            path: Relative path to add for scanning
            scan_type: Type of scanning (PLAIN or RECURSIVE)

        Raises:
            PathNotRelativeError: If path is absolute
        """
        if path.is_absolute():
            raise PathNotRelativeError(f"Path must be relative: {path}")

        scan_path = ScanPath(path, scan_type)
        ScanPath.validate(path)
        self._scan_paths.append(scan_path)

        if config.debug:
            Console(stderr=True).print(
                f"[cyan]Debug: Added {scan_type.name.lower()} scan path: {path}[/cyan]"
            )

    def refresh(self) -> None:
        """Refresh content by scanning configured paths"""
        self.clear()
        paths = self.get_scan_paths()
        
        if config.debug:
            Console(stderr=True).print(f"[cyan]Debug: Refreshing workset with paths: {paths}[/cyan]")
            
        self._workspace.scan_files(paths, self.get_recursive_paths())
        self._content = self._workspace.content

    def get_scan_paths(self) -> List[Path]:
        """Get effective scan paths based on configuration"""
        paths = set()
        paths.update(p.path for p in self._scan_paths)
        return sorted(paths)

    def get_recursive_paths(self) -> Set[Path]:
        """Get paths that should be scanned recursively"""
        return {p.path for p in self._scan_paths if p.is_recursive}

    def is_path_recursive(self, path: Path) -> bool:
        """Check if a path is configured for recursive scanning"""
        return any(scan_path.is_recursive and scan_path.path == path 
                  for scan_path in self._scan_paths)

    @property
    def paths(self) -> Set[Path]:
        return {p.path for p in self._scan_paths}

    @property
    def recursive_paths(self) -> Set[Path]:
        return self.get_recursive_paths()

    def clear(self) -> None:
        """Clear workspace settings while maintaining current directory in scan paths"""
        self._content = WorksetContent()


    def show(self) -> None:
        """Display analysis of current workset content."""
        show_workset_analysis(
            files=self._content.files,
            scan_paths=self._scan_paths,
            cache_blocks=None
        )

    @property
    def content(self) -> str:
        """Return the workset content as a string.
        
        Format:
        <workspace_base_directories>
        dirname1
        dirname2
        ...
        <workset_files>
        <file name=filename1>
        ```
        file1_content
        ```
        </file>
        <file name=filename2>
        ```
        file2_content
        ```
        </file>
        ...
        """
        content = "<workspace_base_directories>\n"
        # Only include root directories if not skipping workspace
        if not config.skip_work:
            for dir in sorted(self._workspace.root_directories):
                content += f"{dir}\n"
        
        content += "<workset_files>\n"
        for file in sorted(self._content.files):
            content += f"<file name={file.name}>\n"
            content += "```\n"
            content += file.content
            content += "\n```\n"
            content += "</file>\n"
        
        return content

