import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from openground.extract.common import (
    save_results,
    filter_documentation_files,
    process_documentation_files,
)
from openground.console import UserError


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise UserError(
            "git is not installed or not on PATH. "
            "Install it from https://git-scm.com/downloads and retry."
        ) from None


def parse_git_web_url(url: str) -> tuple[str, str | None, str | None]:
    """Split a GitHub/GitLab tree/blob web URL into (repo_url, ref, path); other URLs pass through."""
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
    """Default branch of a remote repository (falls back to 'main')."""
    result = _git("ls-remote", "--symref", repo_url, "HEAD")
    for line in result.stdout.splitlines() if result.returncode == 0 else []:
        if line.startswith("ref: refs/heads/"):
            return line.split("\t")[0].replace("ref: refs/heads/", "").strip()
    return "main"


def resolve_remote_ref(repo_url: str, version: str) -> str | None:
    """Return the remote tag/branch matching version (also trying a 'v' prefix variant), or None."""
    result = _git("ls-remote", "--refs", repo_url)
    if result.returncode != 0:
        raise UserError(
            f"Could not list refs for {repo_url}: {result.stderr.strip() or 'git ls-remote failed'}"
        )

    remote_refs = set()
    for line in result.stdout.splitlines():
        if "\trefs/heads/" in line:
            remote_refs.add(line.split("\t")[-1].replace("refs/heads/", ""))
        elif "\trefs/tags/" in line:
            remote_refs.add(line.split("\t")[-1].replace("refs/tags/", ""))

    alternate = version[1:] if version.startswith("v") else f"v{version}"
    for candidate in (version, alternate):
        if candidate in remote_refs:
            return candidate
    return None


async def extract_repo(
    repo_url: str,
    docs_paths: list[str],
    output_dir: Path,
    library_name: str,
    version: str = "latest",
):
    """Shallow-clone a repo ref (default branch for 'latest') and extract its docs."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        default_branch = get_default_branch(repo_url)
        ref_to_checkout = default_branch if version == "latest" else version

        print(f"Cloning {repo_url} (shallow, no-checkout, ref: {ref_to_checkout})...")
        result = _git(
            "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
            "--branch", ref_to_checkout, repo_url, str(temp_path),
        )  # fmt: skip
        if result.returncode != 0:
            raise UserError(f"Failed to clone repository: {result.stderr.strip()}")

        # Empty docs_paths, "/" or "." mean the entire repo
        git_docs_paths = [p.strip("/") for p in docs_paths]
        wants_entire_repo = not git_docs_paths or any(
            p in ("", ".") for p in git_docs_paths
        )

        if wants_entire_repo:
            print("Checking out entire repository (no sparse-checkout)...")
        else:
            print(f"Setting sparse-checkout to: {', '.join(git_docs_paths)}")
            for step in (("init", "--cone"), ("set", *git_docs_paths)):
                result = _git("sparse-checkout", *step, cwd=temp_path)
                if result.returncode != 0:
                    raise UserError(
                        f"Failed to set sparse-checkout: {result.stderr.strip()}"
                    )

        print("Checking out files...")
        result = _git("checkout", cwd=temp_path)
        if result.returncode != 0:
            raise UserError(f"Failed to checkout files: {result.stderr.strip()}")

        search_dirs = (
            [temp_path]
            if wants_entire_repo
            else [temp_path / p for p in git_docs_paths]
        )
        doc_files = sorted(
            {
                f
                for d in search_dirs
                if d.exists()
                for f in filter_documentation_files(d)
            }
        )

        if not doc_files:
            path_msg = (
                "entire repository"
                if wants_entire_repo
                else f"paths: {', '.join(git_docs_paths)}"
            )
            raise UserError(f"No documentation files found in {path_msg}")

        print(f"Processing {len(doc_files)} files...")

        # Page URLs are web links (GitHub/GitLab /tree/ links work for files too)
        parsed_url = urlparse(repo_url)
        base_web_url = repo_url.replace(".git", "")
        if "github.com" in parsed_url.netloc or "gitlab.com" in parsed_url.netloc:
            base_web_url = f"{base_web_url}/tree/{default_branch}"

        def make_git_url(file_path: Path) -> str:
            relative_path = file_path.relative_to(temp_path)
            return f"{base_web_url}/{relative_path}"

        results = await process_documentation_files(
            doc_files=doc_files,
            url_generator=make_git_url,
            library_name=library_name,
            version=version,
            default_description=f"Documentation file from {repo_url}",
            base_path=temp_path,
        )

        if not results:
            raise UserError("No documentation files found after processing.")

        print(f"Found {len(results)} valid documentation pages. Saving...")
        await save_results(results, output_dir)
