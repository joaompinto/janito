import sys
import traceback
from typing import Optional, Type, Any
from rich.console import Console
from rich.traceback import Traceback
from functools import wraps

console = Console()

class JanitoError(Exception):
    """Base exception class for Janito-specific errors"""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause

class ConfigError(JanitoError):
    """Configuration related errors"""
    pass

class APIError(JanitoError):
    """API communication related errors"""
    pass

class FileOperationError(JanitoError):
    """File operation related errors"""
    pass

def handle_error(error: Exception, exit_code: int = 1) -> None:
    """Central error handler that displays rich formatted tracebacks"""
    console.print("\n[red bold]Error:[/] ", end="")
    
    # Always show the full exception chain
    current_error = error
    while current_error:
        console.print(Traceback.from_exception(
            type(current_error),
            current_error,
            current_error.__traceback__,
            show_locals=True,
            width=None  # Don't truncate lines
        ))
        
        if isinstance(current_error, JanitoError):
            current_error = current_error.cause
            if current_error:
                console.print("\n[yellow]Caused by:[/]")
        else:
            break
    
    if exit_code is not None:
        sys.exit(exit_code)

def error_handler(exit_on_error: bool = True):
    """Decorator for handling errors in functions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(e, 1 if exit_on_error else None)
                if not exit_on_error:
                    raise
        return wrapper
    return decorator