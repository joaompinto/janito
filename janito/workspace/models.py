from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Set, Tuple
from sys import maxsize
from janito.config import config
from enum import auto, Enum

@dataclass
class FileInfo:
    """Represents a file's basic information"""
    name: str  # Relative path from workspace root
    content: str
    seconds_ago: int = 0  # Seconds since last modification

    def __lt__(self, other: 'FileInfo') -> bool:
        """Enable sorting by filepath."""
        if not isinstance(other, FileInfo):
            return NotImplemented
        return self.name < other.name

    def __eq__(self, other: object) -> bool:
        """Enable equality comparison by filepath."""
        if not isinstance(other, FileInfo):
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        """Enable using FileInfo in sets by using filepath as hash."""
        return hash(self.name)

class ScanType(Enum):
    """Type of path scanning"""
    PLAIN = auto()
    RECURSIVE = auto()

@dataclass
class ScanPath:
    """Represents a path to be scanned"""
    path: Path
    scan_type: ScanType = ScanType.PLAIN

    @property
    def is_recursive(self) -> bool:
        return self.scan_type == ScanType.RECURSIVE

    @classmethod
    def validate(cls, path: Path) -> None:
        """Validate path is relative and exists"""
        if path.is_absolute():
            raise ValueError(f"Path must be relative: {path}")
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")

@dataclass
class WorksetContent:
    """Represents workset content and statistics."""
    files: List[FileInfo] = field(default_factory=list)
    scanned_paths: Set[Path] = field(default_factory=set)
    dir_counts: Dict[str, int] = field(default_factory=dict)
    dir_sizes: Dict[str, int] = field(default_factory=dict)
    file_types: Dict[str, int] = field(default_factory=dict)
    scan_completed: bool = False
    analyzed: bool = False

    def clear(self) -> None:
        """Reset all content"""
        self.files = []
        self.scanned_paths = set()
        self.dir_counts = {}
        self.dir_sizes = {}
        self.file_types = {}
        self.scan_completed = False
        self.analyzed = False

    def add_file(self, file_info: FileInfo) -> None:
        """Add a file to the content and update statistics"""
        self.files.append(file_info)
        
        # Update file type stats
        suffix = Path(file_info.name).suffix.lower() or 'no_ext'
        self.file_types[suffix] = self.file_types.get(suffix, 0) + 1
        
        # Update directory stats
        dir_path = str(Path(file_info.name).parent)
        self.dir_counts[dir_path] = self.dir_counts.get(dir_path, 0) + 1
        self.dir_sizes[dir_path] = self.dir_sizes.get(dir_path, 0) + len(file_info.content.encode('utf-8'))


    @property
    def content_size(self) -> int:
        """Get total content size in bytes"""
        return sum(len(f.content.encode('utf-8')) for f in self.files)

    @property
    def file_count(self) -> int:
        """Get total number of files"""
        return len(self.files)
