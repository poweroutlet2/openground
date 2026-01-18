"""Console output helpers for colored CLI messages."""

from rich.console import Console

_console = Console(stderr=True)


def success(message: str) -> None:
    """Print a success message in green."""
    _console.print(message, style="green", markup=False)


def error(message: str) -> None:
    """Print an error message in red."""
    _console.print(message, style="red", markup=False)


def hint(message: str) -> None:
    """Print a tip/hint message in blue."""
    _console.print(message, style="cyan1", markup=False)


def warning(message: str) -> None:
    """Print a warning message in yellow."""
    _console.print(message, style="yellow", markup=False)


def print(message: str) -> None:
    """Print a message."""
    _console.print(message, markup=False)
