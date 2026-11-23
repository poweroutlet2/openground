import os
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openground import embeddings, mcp_cli


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], {"transport": "stdio"}),
        (
            ["--transport", "http"],
            {"transport": "http", "host": "127.0.0.1", "port": 8765, "path": "/mcp"},
        ),
        (
            ["--transport", "http", "--host", "::1", "--port", "9000"],
            {"transport": "http", "host": "::1", "port": 9000, "path": "/mcp"},
        ),
    ],
)
def test_mcp_transport(args, expected, monkeypatch):
    from openground.server import mcp

    run = Mock()
    monkeypatch.setattr(mcp, "run", run)
    monkeypatch.setattr(mcp_cli, "configure_thread_env", Mock())
    model = Mock(side_effect=AssertionError("Model loaded during startup"))
    monkeypatch.setattr(embeddings, "generate_embeddings", model)

    mcp_cli.main(args)

    run.assert_called_once_with(**expected)
    model.assert_not_called()


@pytest.mark.parametrize("args", [["--transport", "sse"], ["--port", "65536"]])
def test_mcp_rejects_invalid_options(args):
    with pytest.raises(SystemExit) as exc:
        mcp_cli.main(args)
    assert exc.value.code == 2


@pytest.mark.parametrize("limit", [None, "2"])
def test_thread_env_defaults(limit, monkeypatch):
    for name in (
        "OPENGROUND_MATH_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "TOKENIZERS_PARALLELISM",
        "TRANSFORMERS_VERBOSITY",
        "FAST_EMBED_IGNORE_TRANSFORMERS_LOGS",
    ):
        monkeypatch.delenv(name, raising=False)
    if limit is not None:
        monkeypatch.setenv("OPENGROUND_MATH_THREADS", limit)

    mcp_cli.configure_thread_env()

    assert os.environ["OPENGROUND_MATH_THREADS"] == (limit or "1")
    assert os.environ["OMP_NUM_THREADS"] == (limit or "1")
    assert os.environ["MKL_NUM_THREADS"] == (limit or "1")
    assert os.environ["OPENBLAS_NUM_THREADS"] == (limit or "1")
    assert os.environ["TOKENIZERS_PARALLELISM"] == "false"


def test_thread_env_preserves_overrides(monkeypatch):
    values = {
        "OPENGROUND_MATH_THREADS": "1",
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "3",
        "OPENBLAS_NUM_THREADS": "4",
        "TOKENIZERS_PARALLELISM": "true",
        "TRANSFORMERS_VERBOSITY": "warning",
        "FAST_EMBED_IGNORE_TRANSFORMERS_LOGS": "0",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    mcp_cli.configure_thread_env()

    assert {name: os.environ[name] for name in values} == values


@pytest.mark.parametrize("backend", ["sentence-transformers", "fastembed"])
def test_concurrent_first_model_load(backend, monkeypatch):
    ready = Barrier(4)
    loading = Event()
    finish = Event()
    model = object()

    def load(*args, **kwargs):
        loading.set()
        assert finish.wait(timeout=5)
        return model

    constructor = Mock(side_effect=load)
    if backend == "sentence-transformers":
        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            SimpleNamespace(SentenceTransformer=constructor),
        )
        get_model = embeddings.get_st_model
        cache = embeddings._load_st_model
    else:
        monkeypatch.setitem(
            sys.modules, "fastembed", SimpleNamespace(TextEmbedding=constructor)
        )
        monkeypatch.setenv("OPENGROUND_MATH_THREADS", "2")
        get_model = embeddings.get_fastembed_model
        cache = embeddings._load_fastembed_model

    def request_model():
        ready.wait(timeout=5)
        return get_model("test-model")

    assert not constructor.called
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            requests = [pool.submit(request_model) for _ in range(4)]
            try:
                assert loading.wait(timeout=5)
            finally:
                finish.set()
            assert all(request.result(timeout=5) is model for request in requests)
        if backend == "sentence-transformers":
            constructor.assert_called_once_with("test-model")
        else:
            constructor.assert_called_once_with(
                model_name="test-model", threads=2, providers=["CUDAExecutionProvider"]
            )
    finally:
        cache.cache_clear()
