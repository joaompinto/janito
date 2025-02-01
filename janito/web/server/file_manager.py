import os
import logging
from dataclasses import dataclass
from typing import List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class FileItem:
    name: str
    type: str
    path: str

    def to_dict(self):
        return {
            "name": self.name,
            "type": self.type,
            "path": self.path
        }

class FileManager:
    def __init__(self, base_path: str = "."):
        self.base_path = os.path.abspath(base_path)

    def list_files(self, path: str = ".") -> List[FileItem]:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(self.base_path):
            raise PermissionError("Access denied")

        items = []
        for entry in os.scandir(abs_path):
            rel_path = os.path.relpath(entry.path, ".")
            items.append(FileItem(
                name=entry.name,
                type="directory" if entry.is_dir() else "file",
                path=rel_path.replace("\\", "/")
            ))

        items.sort(key=lambda x: (x.type != "directory", x.name.lower()))
        return items

    def get_file_content(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(self.base_path):
            raise PermissionError("Access denied")

        if not os.path.isfile(abs_path):
            raise FileNotFoundError("File not found")

        with open(abs_path, 'r', encoding='utf-8') as f:
            return f.read()

    def get_files_stats(self, paths: List[str], recursive: bool = False) -> dict:
        stats = {
            "total_items": 0,
            "total_files": 0,
            "total_folders": 0,
            "total_size": 0
        }

        for path in paths:
            abs_path = os.path.abspath(path)
            if not abs_path.startswith(self.base_path):
                continue

            if os.path.isfile(abs_path):
                stats["total_files"] += 1
                stats["total_items"] += 1
                stats["total_size"] += os.path.getsize(abs_path)
            elif os.path.isdir(abs_path):
                stats["total_folders"] += 1
                stats["total_items"] += 1

                if recursive:
                    for root, dirs, files in os.walk(abs_path):
                        stats["total_files"] += len(files)
                        stats["total_folders"] += len(dirs)
                        stats["total_items"] += len(files) + len(dirs)
                        for file in files:
                            file_path = os.path.join(root, file)
                            stats["total_size"] += os.path.getsize(file_path)
                else:
                    with os.scandir(abs_path) as it:
                        for entry in it:
                            if entry.is_file():
                                stats["total_files"] += 1
                                stats["total_items"] += 1
                                stats["total_size"] += entry.stat().st_size
                            elif entry.is_dir():
                                stats["total_folders"] += 1
                                stats["total_items"] += 1

        return stats