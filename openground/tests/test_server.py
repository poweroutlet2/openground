import asyncio
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
    from openground.server import MCPRequestValidation, mcp

    run = Mock()
    monkeypatch.setattr(mcp, "run", run)
    monkeypatch.setattr(mcp_cli, "configure_thread_env", Mock())
    model = Mock(side_effect=AssertionError("Model loaded during startup"))
    monkeypatch.setattr(embeddings, "generate_embeddings", model)

    mcp_cli.main(args)

    run.assert_called_once()
    kwargs = run.call_args.kwargs
    if expected["transport"] == "http":
        (middleware,) = kwargs.pop("middleware")
        assert middleware.cls is MCPRequestValidation
        assert middleware.kwargs == {"host": expected["host"], "port": expected["port"]}
    assert kwargs == expected
    model.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host", "headers", "status"),
    [
        ("127.0.0.1", {"Host": "127.0.0.1:8765"}, 200),
        ("::1", {"Host": "[::1]:8765", "Origin": "http://[::1]:8765"}, 200),
        (
            "192.0.2.10",
            {"Host": "192.0.2.10:8765", "Origin": "http://192.0.2.10:8765"},
            200,
        ),
        ("127.0.0.1", {"Host": "invalid.example:8765"}, 421),
        ("127.0.0.1", {"Host": "localhost:9876"}, 421),
        ("0.0.0.0", {"Host": "0.0.0.0:8765"}, 421),
        ("127.0.0.1", {"Host": "localhost:8765", "Origin": "null"}, 403),
        (
            "127.0.0.1",
            {"Host": "localhost:8765", "Origin": "https://invalid.example"},
            403,
        ),
    ],
)
async def test_http_request_validation(host, headers, status, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from openground.server import mcp, run_server

    run = Mock()
    monkeypatch.setattr(mcp, "run", run)
    run_server(transport="http", host=host)
    app = mcp.http_app(
        path="/mcp", middleware=run.call_args.kwargs["middleware"], json_response=True
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost:8765"
        ) as client,
    ):
        response = await client.post(
            "/mcp",
            headers={**headers, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
    assert response.status_code == status
    assert ("mcp-session-id" in response.headers) == (status == 200)


@pytest.mark.asyncio
async def test_mcp_search_sees_config_edits_without_restart(fake_source):
    from fastmcp import Client

    from openground.config import get_config_path, get_settings
    from openground.server import mcp
    from openground.service import add_library
    from openground.tests.test_config import write_config

    await asyncio.to_thread(
        add_library, "lib", "https://github.com/example/example.git"
    )
    write_config({"embedding_model": "sentence-transformers/all-MiniLM-L6-v2"})
    cached = get_settings()
    path = get_config_path()
    args = {"query": "page", "library_name": "lib", "version": "latest"}
    async with Client(mcp) as client:
        result = await client.call_tool("search_documents_tool", args)
        assert "Embedding config mismatch" in result.content[0].text

        path.write_text("{", encoding="utf-8")
        result = await client.call_tool("search_documents_tool", args)
        assert "Invalid config file" in result.content[0].text

        path.write_text('{"top_k": 1}', encoding="utf-8")
        result = await client.call_tool("search_documents_tool", args)
        assert result.content[0].text.startswith("Found 1 match.")

        path.unlink()
        result = await client.call_tool("search_documents_tool", args)
        assert result.content[0].text.startswith("Found 2 matches.")
    assert get_settings() is cached


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
    assert os.environ["TRANSFORMERS_VERBOSITY"] == "error"
    assert os.environ["FAST_EMBED_IGNORE_TRANSFORMERS_LOGS"] == "1"


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


@pytest.mark.asyncio
async def test_searches_share_a_loaded_model_without_serializing(
    fake_source, monkeypatch
):
    from fastmcp import Client

    from openground import query
    from openground.server import mcp
    from openground.service import add_library

    await asyncio.to_thread(
        add_library, "lib", "https://github.com/example/example.git"
    )
    requests = Barrier(2)

    def encode(**kwargs):
        requests.wait(timeout=5)
        return [[0.1] * 384 for _ in kwargs["sentences"]]

    model = SimpleNamespace(encode=encode)
    constructor = Mock(return_value=model)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=constructor),
    )
    monkeypatch.setattr(query, "generate_embeddings", embeddings.generate_embeddings)
    try:
        assert embeddings.get_st_model("BAAI/bge-small-en-v1.5") is model
        async with Client(mcp) as client:
            results = await asyncio.gather(
                *(
                    client.call_tool(
                        "search_documents_tool",
                        {"query": term, "library_name": "lib", "version": "latest"},
                    )
                    for term in ("guide", "intro")
                )
            )
        assert all("Found" in result.content[0].text for result in results)
        constructor.assert_called_once_with("BAAI/bge-small-en-v1.5")
    finally:
        embeddings._load_st_model.cache_clear()
