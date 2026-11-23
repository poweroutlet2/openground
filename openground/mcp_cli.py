import argparse
import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def configure_thread_env() -> None:
    limit = os.environ.get("OPENGROUND_MATH_THREADS", "1")
    if not limit.isdecimal() or int(limit) < 1:
        raise SystemExit("OPENGROUND_MATH_THREADS must be a positive integer")
    os.environ.setdefault("OPENGROUND_MATH_THREADS", limit)
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(variable, limit)
    os.environ.setdefault("MKL_NUM_THREADS", os.environ["OMP_NUM_THREADS"])
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("FAST_EMBED_IGNORE_TRANSFORMERS_LOGS", "1")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="openground-mcp")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default=DEFAULT_HOST, help="HTTP bind address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP bind port")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    configure_thread_env()

    from openground.server import run_server

    run_server(transport=args.transport, host=args.host, port=args.port)
