from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple
from .models import FileInfo

def collect_file_stats(files: List[FileInfo]) -> Tuple[Dict[str, List[int]], Dict[str, int]]:
    """Collect directory and file type statistics from files.

    Args:
        files: List of FileInfo objects to analyze

    Returns:
        Tuple containing:
            - Dictionary of directory stats [count, size]
            - Dictionary of file type counts
    """
    dir_counts = defaultdict(lambda: [0, 0])  # [count, size]
    file_types = defaultdict(int)

    for file_info in files:
        path = Path(file_info.name)
        dir_path = str(path.parent)
        file_size = len(file_info.content.encode('utf-8'))

        # Update directory stats
        dir_counts[dir_path][0] += 1
        dir_counts[dir_path][1] += file_size

        # Update file type stats
        file_types[path.suffix.lower() or 'no_ext'] += 1

    return dir_counts, file_types

def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format."""
    size = size_bytes
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            break
        size //= 1024
    return f"{size} {unit}"

