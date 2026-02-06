import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from openground.extract.common import (
    ParsedPage,
    save_results,
    filter_documentation_files,
    process_documentation_files,
)
from openground.console import error


def parse_git_web_url(url: str) -> tuple[str, str | None, str | None]:
    """
    Parse a GitHub/GitLab web URL into (repo_url, ref, path).

    Supports:
    - GitHub: https://github.com/owner/repo/tree/ref/path
    - GitHub: https://github.com/owner/repo/blob/ref/path
    - GitLab: https://gitlab.com/group/project/-/tree/ref/path
    - GitLab: https://gitlab.com/group/project/-/blob/ref/path

    Returns:
        tuple: (repo_url, ref, path)
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    # Detect GitHub
    if "github.com" in parsed.netloc:
        if len(path_parts) >= 4 and path_parts[2] in ("tree", "blob"):
            owner, repo = path_parts[0], path_parts[1]
            repo_url = f"https://github.com/{owner}/{repo}.git"
            ref = path_parts[3]
            doc_path = "/".join(path_parts[4:]) if len(path_parts) > 4 else None
            return repo_url, ref, doc_path

    # Detect GitLab
    elif "gitlab.com" in parsed.netloc:
        # GitLab URLs often have '-' before tree/blob
        if "-" in path_parts:
            dash_index = path_parts.index("-")
            if len(path_parts) > dash_index + 2 and path_parts[dash_index + 1] in (
                "tree",
                "blob",
            ):
                project_path = "/".join(path_parts[:dash_index])
                repo_url = f"https://gitlab.com/{project_path}.git"
                ref = path_parts[dash_index + 2]
                doc_path = (
                    "/".join(path_parts[dash_index + 3 :])
                    if len(path_parts) > dash_index + 3
                    else None
                )
                return repo_url, ref, doc_path

    return url, None, None


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


def resolve_remote_ref(repo_url: str, version: str) -> str | None:
    """
    Check if a ref (tag or branch) exists on the remote.
    Handles 'v' prefix variants for tags.

    Returns the actual ref name if found, None otherwise.
    """
    # Get all refs (heads and tags)
    result = subprocess.run(
        ["git", "ls-remote", "--refs", repo_url],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    lines = result.stdout.splitlines()
    remote_refs = set()
    for line in lines:
        if "\trefs/heads/" in line:
            remote_refs.add(line.split("\t")[-1].replace("refs/heads/", ""))
        elif "\trefs/tags/" in line:
            remote_refs.add(line.split("\t")[-1].replace("refs/tags/", ""))

    # 1. Check exact match
    if version in remote_refs:
        return version

    # 2. Check variants (with/without 'v') for potential tags
    if version.startswith("v"):
        variants = [version[1:]]
    else:
        variants = [f"v{version}"]

    for variant in variants:
        if variant in remote_refs:
            return variant

    return None


async def extract_repo(
    repo_url: str,
    docs_paths: list[str],
    output_dir: Path,
    library_name: str,
    version: str | None = None,
):
    """
    Clone repo and extract documentation files.

    Args:
        repo_url: URL of the git repository.
        docs_paths: Paths within the repo to extract (e.g., ['docs/', 'api/']).
        output_dir: Directory to save the processed JSON files.
        library_name: Name of the library.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Detect default branch for URL construction
        default_branch = get_default_branch(repo_url)

        # Resolve the actual ref name if version is provided
        version_to_store: str
        if version and version != "latest":
            if (resolved_ref := resolve_remote_ref(repo_url, version)) is None:
                alt_version = version[1:] if version.startswith("v") else f"v{version}"
                error(
                    f"Ref (tag or branch) '{version}' not found in repository (checked '{version}' and '{alt_version}')"
                )
                return
            ref_to_checkout = resolved_ref
            version_to_store = resolved_ref
        else:
            ref_to_checkout = default_branch
            version_to_store = "latest"

        print(f"Cloning {repo_url} (shallow, no-checkout, ref: {ref_to_checkout})...")

        # Clone with minimal depth and no checkout
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--no-checkout",
            "--branch",
            ref_to_checkout,
            repo_url,
            str(temp_path),
        ]

        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            error(f"Failed to clone repository: {result.stderr}")
            return

        # Sparse checkout configuration

        # Normalize docs_paths - detect if user wants the entire repo
        # Empty docs_paths means entire repo by default
        git_docs_paths = []
        wants_entire_repo = not docs_paths  # Empty list = entire repo
        for path in docs_paths:
            gp = path.strip("/")
            if not gp or path == "/" or gp == ".":
                wants_entire_repo = True
                break
            git_docs_paths.append(gp)

        # If entire repo is requested, skip sparse-checkout for full checkout
        if wants_entire_repo:
            print("Checking out entire repository (no sparse-checkout)...")
        else:
            print(f"Setting sparse-checkout to: {', '.join(git_docs_paths)}")

        try:
            # Only set up sparse-checkout if we're not getting the entire repo
            if not wants_entire_repo:
                subprocess.run(
                    ["git", "sparse-checkout", "init", "--cone"],
                    cwd=temp_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "sparse-checkout", "set"] + git_docs_paths,
                    cwd=temp_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
        except subprocess.CalledProcessError as e:
            error(f"Failed to set sparse-checkout: {e.stderr}")
            return

        print("Checking out files...")
        try:
            subprocess.run(
                ["git", "checkout"],
                cwd=temp_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            error(f"Failed to checkout files: {e.stderr}")
            return

        # Process files
        results: list[ParsedPage] = []

        # Collect all documentation files from all requested paths
        all_doc_files = []
        if wants_entire_repo:
            # Entire repo - search from temp_path root
            all_doc_files.extend(filter_documentation_files(temp_path))
        else:
            # Specific paths - search each path
            for gp in git_docs_paths:
                search_dir = temp_path / gp
                if search_dir.exists():
                    all_doc_files.extend(filter_documentation_files(search_dir))

        # De-duplicate files (in case paths overlap)
        doc_files = sorted(list(set(all_doc_files)))

        if not doc_files:
            path_msg = "entire repository" if wants_entire_repo else f"paths: {', '.join(git_docs_paths)}"
            error(f"No documentation files found in {path_msg}")
            return

        print(f"Processing {len(doc_files)} files...")

        # Construct base URL for file references
        # Try to make a helpful link (assuming GitHub/GitLab style)
        parsed_url = urlparse(repo_url)
        base_web_url = repo_url.replace(".git", "")
        if "github.com" in parsed_url.netloc or "gitlab.com" in parsed_url.netloc:
            # GitHub/GitLab: base/tree/branch/path (or /blob/ for files)
            # Use /tree/ as it works reasonably for both dirs and files as a base
            base_web_url = f"{base_web_url}/tree/{default_branch}"

        # Use shared file processing function
        def make_git_url(file_path: Path) -> str:
            relative_path = file_path.relative_to(temp_path)
            return f"{base_web_url}/{relative_path}"

        results = await process_documentation_files(
            doc_files=doc_files,
            url_generator=make_git_url,
            library_name=library_name,
            version=version_to_store,
            default_description=f"Documentation file from {repo_url}",
            base_path=temp_path,
        )

        if not results:
            error("No documentation files found after processing.")
            return

        print(f"Found {len(results)} valid documentation pages. Saving...")
        await save_results(results, output_dir)
