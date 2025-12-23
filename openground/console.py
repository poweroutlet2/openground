"""Console output helpers for colored CLI messages."""

from rich.console import Console

_console = Console()


def success(message: str) -> None:
    """Print a success message in green."""
    _console.print(f"[green]{message}[/green]")


def error(message: str) -> None:
    """Print an error message in red."""
    _console.print(f"[red]{message}[/red]")


def hint(message: str) -> None:
    """Print a tip/hint message in blue."""
    _console.print(f"[cyan1]{message}[/cyan1]")


def warning(message: str) -> None:
    """Print a warning message in yellow."""
    _console.print(f"[yellow]{message}[/yellow]")
