import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from openground.extract.common import ParsedPage, save_results
from openground.console import success, error


def filter_documentation_files(
    docs_dir: Path, allowed_extensions: set[str] | None = None
) -> list[Path]:
    """
    Filter to relevant documentation files.
    """
    if allowed_extensions is None:
        # Default to most common doc formats
        allowed_extensions = {".md", ".rst", ".txt", ".mdx"}

    doc_files = []

    for root, dirs, files in os.walk(docs_dir):
        # Skip common non-doc directories
        dirs[:] = [
            d
            for d in dirs
            if d
            not in {
                "node_modules",
                "__pycache__",
                ".git",
                "images",
                "img",
                "assets",
                "static",
                "_build",
                "build",
                "dist",
                ".venv",
            }
        ]

        for file in files:
            file_path = Path(root) / file

            # Check if file has allowed extension
            if file_path.suffix.lower() in allowed_extensions:
                # Skip hidden files and common non-doc files
                if not file.startswith(".") and file not in {
                    "LICENSE",
                    "CHANGELOG",
                    "AUTHORS",
                }:
                    doc_files.append(file_path)

    return doc_files


def remove_front_matter(content: str) -> tuple[str, dict[str, str]]:
    """
    Parse YAML front matter and return (content_without_front_matter, metadata).
    """
    if not content.startswith("---"):
        return content, {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content, {}

    front_matter = parts[1]
    remaining_content = parts[2].strip()

    metadata = {}
    for line in front_matter.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip()

    return remaining_content, metadata


def get_default_branch(repo_url: str) -> str:
    """Get the default branch name of a remote repository."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--symref", repo_url, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                # line looks like "ref: refs/heads/main\tHEAD"
                return line.split("\t")[0].replace("ref: refs/heads/", "").strip()
    except Exception:
        pass
    return "main"


async def extract_repo(
    repo_url: str,
    docs_path: str,
    output_dir: Path,
    library_name: str,
):
    """
    Clone repo and extract documentation files.

    Args:
        repo_url: URL of the git repository.
        docs_path: Path within the repo to extract (e.g., 'docs/' or '/').
        output_dir: Directory to save the processed JSON files.
        library_name: Name of the library.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        print(f"Cloning {repo_url} (shallow, no-checkout)...")

        # Clone with minimal depth and no checkout
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--no-checkout",
            repo_url,
            str(temp_path),
        ]

        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            error(f"Failed to clone repository: {result.stderr}")
            return

        # Sparse checkout configuration

        # Normalize docs_path
        git_docs_path = docs_path.strip("/")
        if not git_docs_path or docs_path == "/":
            git_docs_path = "*"

        print(f"Setting sparse-checkout to: {git_docs_path}")

        subprocess.run(
            ["git", "sparse-checkout", "init", "--cone"], cwd=temp_path, check=True
        )
        subprocess.run(
            ["git", "sparse-checkout", "set", git_docs_path], cwd=temp_path, check=True
        )

        print("Checking out files...")
        subprocess.run(["git", "checkout"], cwd=temp_path, check=True)

        # Process files
        results: list[ParsedPage | None] = []

        # Resolve the actual directory to search
        search_dir = temp_path
        if git_docs_path != "*":
            search_dir = temp_path / git_docs_path

        if not search_dir.exists():
            error(f"Documentation path '{docs_path}' not found in repository.")
            return

        print(f"Processing files in {search_dir}...")

        # Detect default branch for URL construction
        branch = get_default_branch(repo_url)
        print(f"Detected default branch: {branch}")

        # Construct base URL for file references
        # Try to make a helpful link (assuming GitHub/GitLab style)
        parsed_url = urlparse(repo_url)
        base_web_url = repo_url.replace(".git", "")
        if "github.com" in parsed_url.netloc or "gitlab.com" in parsed_url.netloc:
            # GitHub/GitLab: base/tree/branch/path (or /blob/ for files)
            # Use /tree/ as it works reasonably for both dirs and files as a base
            base_web_url = f"{base_web_url}/tree/{branch}"

        doc_files = filter_documentation_files(search_dir)

        for file_path in doc_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()

                content, metadata = remove_front_matter(raw_content)

                relative_path = file_path.relative_to(temp_path)
                file_url = f"{base_web_url}/{relative_path}"

                # Use title from metadata if available, otherwise filename
                title = metadata.get("title")
                if not title:
                    title = file_path.stem.replace("-", " ").replace("_", " ").title()

                results.append(
                    ParsedPage(
                        url=file_url,
                        library_name=library_name,
                        version="latest",
                        title=title,
                        description=metadata.get("description")
                        or f"Documentation file from {repo_url}",
                        last_modified=None,
                        content=content,
                    )
                )
            except Exception as e:
                print(f"Warning: Could not process {file_path}: {e}")

        if not results:
            error("No documentation files found.")
            return

        print(f"Found {len(results)} text files. Saving...")
        await save_results(results, output_dir)
        success(f"Successfully extracted {len(results)} files to {output_dir}")
