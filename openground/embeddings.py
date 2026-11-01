import os
import subprocess
import sys
from collections.abc import Iterable
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

from tqdm import tqdm

from openground.config import get_settings
from openground.console import error, hint, warning


@lru_cache(maxsize=1)
def get_st_model(model_name: str):
    """Get a cached instance of SentenceTransformer."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is not installed (it is a base dependency of "
            "openground): reinstall openground."
        ) from None

    return SentenceTransformer(model_name)


def is_gpu_hardware_available() -> bool:
    """Check if NVIDIA GPU hardware is detected on the system."""
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, check=True, timeout=5)
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        # Fallback for Linux: check /dev/nvidia0
        if sys.platform != "win32" and os.path.exists("/dev/nvidia0"):
            return True
    return False


def check_gpu_compatibility() -> None:
    """Check for GPU compatibility and provide optimization tips or warnings."""
    gpu_hardware = is_gpu_hardware_available()

    # Check if fastembed-gpu is installed
    has_gpu_pkg = False
    try:
        version("fastembed-gpu")
        has_gpu_pkg = True
    except PackageNotFoundError:
        pass

    # Check for functional GPU via onnxruntime
    functional_gpu = False
    try:
        import onnxruntime as ort

        functional_gpu = "CUDAExecutionProvider" in ort.get_available_providers()
    except ImportError:
        pass

    if gpu_hardware and not has_gpu_pkg:
        hint("GPU detected! Install the GPU version for faster performance:")
        hint("   uv tool install 'openground[fastembed-gpu]'\n")

    elif not gpu_hardware and has_gpu_pkg:
        warning(
            "\nWarning: openground[fastembed-gpu] is installed but no NVIDIA GPU was detected."
        )
        warning("   You may want to switch to the CPU version:")
        warning("   uv tool install 'openground[fastembed-cpu]'\n")

    elif gpu_hardware and has_gpu_pkg and not functional_gpu:
        error(
            "\nError: GPU package is installed but CUDA is not functional. Your options are:"
        )
        error(
            "  1. Ensure your CUDA drivers and cuDNN match the requirements for onnxruntime-gpu."
        )
        error(
            "   See: https://oliviajain.github.io/onnxruntime/docs/execution-providers/CUDA-ExecutionProvider.html\n"
        )
        error(
            "  2. Install the CPU version: uv tool install 'openground[fastembed-cpu]'"
        )
        error(
            "  3. Or use the sentence-transformers backend (installed by default): "
            'set "embedding_backend": "sentence-transformers" in config.json.'
        )


@lru_cache(maxsize=1)
def get_fastembed_model(model_name: str, use_cuda: bool = True):
    """Get a cached instance of TextEmbedding (fastembed)."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        raise ImportError(
            "The 'fastembed' backend is not installed. "
            "Please install it with: pip install fastembed"
        ) from None

    if use_cuda:
        try:
            return TextEmbedding(
                model_name=model_name,
                providers=["CUDAExecutionProvider"],
            )
        except ValueError:
            check_gpu_compatibility()

    return TextEmbedding(
        model_name=model_name,
        providers=["CPUExecutionProvider"],
    )


def _generate_embeddings_sentence_transformers(
    texts: Iterable[str],
    show_progress: bool = True,
) -> list[list[float]]:
    """Embed texts with sentence-transformers."""
    config = get_settings()
    batch_size = config.batch_size
    model_name = config.embedding_model
    model = get_st_model(model_name)

    texts_list = list(texts)
    all_embeddings = []

    with tqdm(
        total=len(texts_list),
        desc="Generating embeddings",
        unit="text",
        unit_scale=True,
        disable=(not show_progress),
        file=sys.stderr,
    ) as pbar:
        for i in range(0, len(texts_list), batch_size):
            batch = texts_list[i : i + batch_size]
            batch_embeddings = model.encode(
                sentences=batch,
                batch_size=len(batch),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            all_embeddings.extend(list(batch_embeddings))
            pbar.update(len(batch))

    return all_embeddings


def _generate_embeddings_fastembed(
    texts: Iterable[str],
    show_progress: bool = True,
) -> list[list[float]]:
    """Embed passages with fastembed."""
    config = get_settings()
    batch_size = config.batch_size
    model_name = config.embedding_model

    texts_list = list(texts)
    all_embeddings = []

    model = get_fastembed_model(model_name)

    with tqdm(
        total=len(texts_list),
        desc="Generating embeddings",
        unit="text",
        unit_scale=True,
        disable=not show_progress,
        file=sys.stderr,
    ) as pbar:
        for i in range(0, len(texts_list), batch_size):
            batch = texts_list[i : i + batch_size]
            batch_embeddings = list(model.passage_embed(batch))
            all_embeddings.extend([emb.tolist() for emb in batch_embeddings])
            pbar.update(len(batch))

    return all_embeddings


def generate_embeddings(
    texts: Iterable[str],
    show_progress: bool = True,
) -> list[list[float]]:
    """Embed texts with the configured backend."""
    backend = get_settings().embedding_backend

    if backend == "fastembed":
        return _generate_embeddings_fastembed(texts, show_progress=show_progress)
    elif backend == "sentence-transformers":
        return _generate_embeddings_sentence_transformers(
            texts, show_progress=show_progress
        )
    else:
        raise ValueError(
            f"Invalid embedding backend: {backend}. Must be 'sentence-transformers' "
            "or 'fastembed'."
        )
