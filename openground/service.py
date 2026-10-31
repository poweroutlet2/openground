"""Add / update / remove flows shared by the CLI and other front ends."""

import asyncio
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from openground.config import get_data_home, get_library_raw_data_dir
from openground.console import UserError
from openground.extract.common import ParsedPage
from openground.query import (
    clear_query_caches,
    delete_library,
    library_version_exists,
    list_libraries_with_versions,
)
from openground.sources import (
    LibrarySource,
    get_source,
    load_sources,
    remove_source,
    save_source,
)
from openground.update import UpdateSummary

GIT_HOSTS = {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com"}
PATH_PREFIXES = ("/", "~", "./", "../", ".\\", "..\\", "\\")


class ServiceError(UserError):
    pass


@dataclass
class SyncResult:
    library: str
    version: str
    pages: int = 0
    summary: UpdateSummary | None = None  # None means the version was newly added
    error: str | None = None


def detect_source_type(source: str) -> str:
    if Path(source).expanduser().exists():
        return "local_path"

    parsed = urlparse(source)
    if (
        parsed.hostname in GIT_HOSTS
        or parsed.scheme in ("git", "ssh")
        or source.startswith("git@")
        or source.endswith(".git")
    ):
        return "git_repo"
    if parsed.scheme in ("http", "https"):
        return "sitemap"
    if source.startswith(PATH_PREFIXES) or re.match(r"^[A-Za-z]:[\\/]", source):
        return "local_path"

    raise ServiceError(
        f"Could not tell what '{source}' is. Use a git repo URL, a sitemap URL, "
        "or a path to a local directory."
    )


def parse_source(source: str) -> tuple[LibrarySource, str | None]:
    """Normalize SOURCE into a LibrarySource plus a git ref implied by a web URL."""
    source_type = detect_source_type(source)

    if source_type == "git_repo":
        from openground.extract.git import parse_git_web_url

        repo_url, ref, docs_path = parse_git_web_url(source)
        spec: LibrarySource = {"type": "git_repo", "repo_url": repo_url}
        if docs_path:
            spec["docs_paths"] = [docs_path]
        return spec, ref
    if source_type == "sitemap":
        return {"type": "sitemap", "sitemap_url": source}, None
    local_path = str(Path(source).expanduser().resolve())
    return {"type": "local_path", "local_path": local_path}, None


def _default_version(spec: LibrarySource) -> str:
    if spec["type"] == "local_path":
        return date.today().strftime("local-%Y-%m-%d")
    return "latest"


async def _extract(spec: LibrarySource, library: str, version: str, out_dir: Path):
    source_type = spec["type"]
    if source_type == "git_repo":
        from openground.extract.git import extract_repo

        await extract_repo(
            repo_url=spec["repo_url"],
            docs_paths=spec.get("docs_paths", []),
            output_dir=out_dir,
            library_name=library,
            version=version,
        )
    elif source_type == "sitemap":
        from openground.extract.sitemap import extract_pages

        await extract_pages(
            sitemap_url=spec["sitemap_url"],
            library_name=library,
            output_dir=out_dir,
            filter_keywords=spec.get("filter_keywords", []),
            version=version,
        )
    else:
        from openground.extract.local_path import extract_local_path

        await extract_local_path(
            local_path=Path(spec["local_path"]),
            output_dir=out_dir,
            library_name=library,
            version=version,
        )


def _extract_pages(
    spec: LibrarySource, library: str, version: str, out_dir: Path
) -> list[ParsedPage]:
    from openground.ingest import load_parsed_pages

    asyncio.run(_extract(spec, library, version, out_dir))
    pages = load_parsed_pages(out_dir) if out_dir.exists() else []
    if not pages:
        raise ServiceError(
            f"Extraction produced no pages for '{library}'. Check the source."
        )
    return pages


def _sync(library: str, version: str, spec: LibrarySource) -> SyncResult:
    """Ingest a library version, or incrementally update it if already stored."""
    from openground.ingest import ingest_pages
    from openground.update import perform_update

    raw_dir = get_library_raw_data_dir(library, version)
    stored = library_version_exists(library, version) and any(raw_dir.glob("*.json"))

    if stored:
        with tempfile.TemporaryDirectory() as tmp:
            pages = _extract_pages(spec, library, version, Path(tmp))
            summary = perform_update(pages, library, version, raw_dir)
        return SyncResult(library, version, len(pages), summary)

    # Drop leftovers from a half-finished earlier run so nothing is duplicated
    delete_library(library, version)
    shutil.rmtree(raw_dir, ignore_errors=True)
    try:
        pages = _extract_pages(spec, library, version, raw_dir)
        ingest_pages(pages)
    except Exception:
        shutil.rmtree(raw_dir, ignore_errors=True)
        raise
    return SyncResult(library, version, len(pages))


def add_library(
    name: str,
    source: str | None = None,
    version: str | None = None,
    docs_paths: list[str] | None = None,
    filter_keywords: list[str] | None = None,
) -> SyncResult:
    """Extract and embed a library, then remember its source."""
    if source:
        spec, ref = parse_source(source)
        version = version or ref
    elif remembered := get_source(name):
        spec = remembered
    else:
        raise ServiceError(
            f"No remembered source for '{name}'. Run: openground add {name} SOURCE"
        )

    if docs_paths and spec["type"] == "git_repo":
        spec["docs_paths"] = docs_paths
    if filter_keywords and spec["type"] == "sitemap":
        spec["filter_keywords"] = filter_keywords
    if version and version != "latest" and spec["type"] != "git_repo":
        raise ServiceError("--version only applies to git repo sources.")

    try:
        result = _sync(name, version or _default_version(spec), spec)
    finally:
        clear_query_caches()
    save_source(name, spec)
    return result


def update_libraries(name: str | None = None) -> list[SyncResult]:
    """Refresh every stored version from the remembered source (one library, or all)."""
    sources = load_sources()
    stored = list_libraries_with_versions()

    if name:
        if name not in stored:
            raise ServiceError(f"Library '{name}' not found.")
        if name not in sources:
            raise ServiceError(
                f"No remembered source for '{name}'. Run: openground add {name} SOURCE"
            )
        targets = {name: stored[name]}
    else:
        targets = {lib: v for lib, v in stored.items() if lib in sources}

    results = []
    for library, versions in targets.items():
        for version in versions:
            try:
                results.append(_sync(library, version, sources[library]))
            except Exception as e:
                results.append(SyncResult(library, version, error=str(e)))
    clear_query_caches()
    return results


def resolve_version(name: str, version: str | None = None) -> str:
    versions = list_libraries_with_versions().get(name)
    if not versions:
        raise ServiceError(f"Library '{name}' not found.")
    if version is None:
        if len(versions) > 1:
            raise ServiceError(
                f"'{name}' has multiple versions: {', '.join(versions)}. "
                "Pick one with --version."
            )
        return versions[0]
    if version not in versions:
        raise ServiceError(
            f"Version '{version}' of '{name}' not found. Stored: {', '.join(versions)}."
        )
    return version


def remove_library(name: str, version: str) -> int:
    """Delete a stored version (rows and raw files); forget the source with the last one."""
    deleted = delete_library(name, version)
    shutil.rmtree(get_library_raw_data_dir(name, version), ignore_errors=True)
    clear_query_caches()
    if name not in list_libraries_with_versions():
        remove_source(name)
    return deleted


def list_libraries() -> list[tuple[str, list[str], bool]]:
    """(name, versions, has remembered source) for each stored library."""
    sources = load_sources()
    return [
        (name, versions, name in sources)
        for name, versions in list_libraries_with_versions().items()
    ]


def reset_data() -> None:
    """Delete all local data: embeddings, raw files and stats."""
    shutil.rmtree(get_data_home(), ignore_errors=True)
    clear_query_caches()
