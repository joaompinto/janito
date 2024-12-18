from pathlib import Path
import shutil
import tempfile
from typing import List, Set, Tuple
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

from janito.config import config

def create_backup() -> Path:
    """Create backup directory and restore script.
    Returns the path to the backup directory."""
    backup_dir = config.workspace_dir / '.janito' / 'backups' / datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir.parent.mkdir(parents=True, exist_ok=True)

    # Copy existing files to backup directory
    if config.workspace_dir.exists():
        shutil.copytree(config.workspace_dir, backup_dir, ignore=shutil.ignore_patterns('.janito', '.git'))
        
        # Create restore script
        restore_script = config.workspace_dir / '.janito' / 'restore.sh'
        restore_script.parent.mkdir(parents=True, exist_ok=True)
        script_content = f"""#!/bin/bash
# Restore script generated by Janito
# Restores files from backup created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# Exit on error
set -e

# Get backup directory from argument or use latest
BACKUP_DIR="$1"
if [ -z "$BACKUP_DIR" ]; then
    BACKUP_DIR="{backup_dir}"
    echo "No backup directory specified, using latest: $BACKUP_DIR"
fi

# Show usage if --help is provided
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [backup_directory]"
    echo ""
    echo "If no backup directory is provided, uses the latest backup at:"
    echo "{backup_dir}"
    exit 0
fi

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Error: Backup directory not found at $BACKUP_DIR"
    exit 1
fi

# Restore files from backup
echo "Restoring files from backup..."
cp -r "$BACKUP_DIR"/* "{config.workspace_dir}/"

echo "Files restored successfully from $BACKUP_DIR"
"""
        restore_script.write_text(script_content)
        restore_script.chmod(0o755)

    return backup_dir

def setup_preview_directory() -> Path:
    """Creates and sets up preview directory with working directory contents.
    Returns the path to the preview directory."""
    preview_dir = Path(tempfile.mkdtemp())
    
    # Copy existing files to preview directory if workspace_dir exists
    if config.workspace_dir.exists():
        shutil.copytree(config.workspace_dir, preview_dir, dirs_exist_ok=True, 
                       ignore=shutil.ignore_patterns('.janito', '.git'))
        
    return preview_dir

def setup_workspace_dir_preview() -> tuple[Path, Path]:
    """Sets up both backup and preview directories.
    Returns (backup_dir, preview_dir) tuple."""
    backup_dir = create_backup()
    preview_dir = setup_preview_directory()
    return backup_dir, preview_dir

