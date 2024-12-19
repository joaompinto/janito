from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple
from .types import FileInfo

def collect_file_stats(files: List[FileInfo]) -> Tuple[Dict, Dict]:
    """Collect directory and file type statistics from files."""
    dir_counts = defaultdict(lambda: [0, 0])  # [count, size]
    file_types = defaultdict(int)
    
    for file_info in files:
        path = Path(file_info.name)
        dir_path = str(path.parent)
        
        dir_counts[dir_path][0] += 1
        dir_counts[dir_path][1] += len(file_info.content.encode('utf-8'))
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

# Remove _group_files_by_time function as it's now handled by Workset