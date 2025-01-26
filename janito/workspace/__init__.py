from .workset import Workset
from .workspace import Workspace

# Create and export singleton instance
workset = Workset()
workspace = Workspace()

__all__ = ['workset', 'workspace']