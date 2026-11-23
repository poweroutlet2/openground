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
from openground.console import UserError


async def extract_local_path(
    local_path: Path,
    output_dir: Path,
    library_name: str,
    version: str,
) -> None:
    """Extract documentation files from a local directory."""
    local_path = local_path.expanduser().resolve()
    if not local_path.is_dir():
        raise UserError(f"Not a directory: {local_path}")

    doc_files = filter_documentation_files(local_path)

    if not doc_files:
        raise UserError(f"No documentation files found in {local_path}")

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
        raise UserError("No documentation files found after processing.")

    print(f"Found {len(results)} valid documentation pages. Saving...")
    await save_results(results, output_dir)
