"""
Local path documentation extractor.

Processes documentation files from a local directory path.
Supports the same file types as git.py: .md, .rst, .txt, .mdx, .ipynb, .html, .htm
"""

from pathlib import Path

from openground.extract.common import (
    save_results,
    filter_documentation_files,
    process_documentation_files,
)
from openground.console import error


async def extract_local_path(
    local_path: Path,
    output_dir: Path,
    library_name: str,
    version: str,
) -> None:
    """
    Extract documentation files from a local directory path.

    Args:
        local_path: Path to the local directory containing documentation files
        output_dir: Directory to save the processed JSON files
        library_name: Name of the library
        version: Version string (e.g., "local-2025-02-02")
    """
    # Expand and resolve the path
    local_path = local_path.expanduser().resolve()

    if not local_path.exists():
        error(f"Path does not exist: {local_path}")
        return

    if not local_path.is_dir():
        error(f"Path is not a directory: {local_path}")
        return

    # Get all documentation files
    doc_files = filter_documentation_files(local_path)

    if not doc_files:
        error(f"No documentation files found in {local_path}")
        return

    print(f"Processing {len(doc_files)} files...")

    def make_file_url(file_path: Path) -> str:
        return f"file://{file_path}"

    results = await process_documentation_files(
        doc_files=doc_files,
        url_generator=make_file_url,
        library_name=library_name,
        version=version,
        default_description=f"Documentation file from {local_path}",
        base_path=local_path,
    )

    if not results:
        error("No documentation files found after processing.")
        return

    print(f"Found {len(results)} valid documentation pages. Saving...")
    await save_results(results, output_dir)
