import sys
from collections.abc import Iterable
from functools import lru_cache

from tqdm import tqdm

from openground.config import get_effective_config


@lru_cache(maxsize=1)
def get_st_model(model_name: str):
    """Get a cached instance of SentenceTransformer."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "The 'sentence-transformers' backend is not installed. "
            "Please install it with: pip install 'openground[sentence-transformers]'"
        ) from None

    return SentenceTransformer(model_name)


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
            print("CUDA not available, using CPU instead.", file=sys.stderr)

    return TextEmbedding(
        model_name=model_name,
        providers=["CPUExecutionProvider"],
    )


def _generate_embeddings_sentence_transformers(
    texts: Iterable[str],
    show_progress: bool = True,
) -> list[list[float]]:
    """Generate embeddings using sentence-transformers backend.

    Args:
        texts: Iterable of text strings to embed.
        show_progress: Whether to show a progress bar.

    Returns:
        List of embedding vectors (each as a list of floats).
    """
    config = get_effective_config()
    batch_size = config["embeddings"]["batch_size"]
    model_name = config["embeddings"]["embedding_model"]
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
    """Generate embeddings using fastembed backend.

    Uses passage_embed for document embeddings.

    Args:
        texts: Iterable of text strings to embed.
        show_progress: Whether to show a progress bar.

    Returns:
        List of embedding vectors (each as a list of floats).
    """
    config = get_effective_config()
    batch_size = config["embeddings"]["batch_size"]
    model_name = config["embeddings"]["embedding_model"]

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
        # fastembed processes in batches internally, but we can control batching
        for i in range(0, len(texts_list), batch_size):
            batch = texts_list[i : i + batch_size]
            # passage_embed returns a generator of numpy arrays
            batch_embeddings = list(model.passage_embed(batch))
            # Convert numpy arrays to lists of floats
            all_embeddings.extend([emb.tolist() for emb in batch_embeddings])
            pbar.update(len(batch))

    return all_embeddings


def generate_embeddings(
    texts: Iterable[str],
    show_progress: bool = True,
) -> list[list[float]]:
    """Generate embeddings for documents using the specified backend.

    Args:
        texts: Iterable of text strings to embed.
        show_progress: Whether to show a progress bar.

    Returns:
        List of embedding vectors (each as a list of floats).
    """

    config = get_effective_config()
    backend = config["embeddings"]["embedding_backend"]

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
