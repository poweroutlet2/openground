import asyncio

import pytest

from openground.console import UserError
from openground.extract.local_path import extract_local_path


def run(path, out):
    return asyncio.run(extract_local_path(path, out, "lib", "latest"))


def test_local_path_extracts_markdown(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# A\n\nAlpha")

    run(docs, tmp_path / "out")

    assert len(list((tmp_path / "out").glob("*.json"))) == 1


def test_missing_directory_raises_specific_error(tmp_path):
    with pytest.raises(UserError, match="Not a directory"):
        run(tmp_path / "nope", tmp_path / "out")


def test_directory_without_docs_raises_specific_error(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "data.bin").write_bytes(b"\x00")

    with pytest.raises(UserError, match="No documentation files found"):
        run(tmp_path / "docs", tmp_path / "out")
