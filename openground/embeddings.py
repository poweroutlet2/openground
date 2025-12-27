from collections.abc import Iterable

from tqdm import tqdm

from openground.config import get_effective_config


def get_device() -> str:
    """Detect available hardware device (CUDA, MPS, or CPU)."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _generate_embeddings_sentence_transformers(
    texts: Iterable[str],
) -> list[list[float]]:
    """Generate embeddings using sentence-transformers backend.

    Args:
        texts: Iterable of text strings to embed.

    Returns:
        List of embedding vectors (each as a list of floats).
    """
    from sentence_transformers import SentenceTransformer

    config = get_effective_config()
    batch_size = config["ingestion"]["batch_size"]
    model_name = config["ingestion"]["embedding_model"]
    model = SentenceTransformer(model_name)

    texts_list = list(texts)
    all_embeddings = []

    with tqdm(
        total=len(texts_list),
        desc="Generating embeddings",
        unit="text",
        unit_scale=True,
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


def _generate_embeddings_fastembed(texts: Iterable[str]) -> list[list[float]]:
    """Generate embeddings using fastembed backend.

    Uses passage_embed for document embeddings.

    Args:
        texts: Iterable of text strings to embed.

    Returns:
        List of embedding vectors (each as a list of floats).
    """
    from fastembed import TextEmbedding

    config = get_effective_config()
    batch_size = config["ingestion"]["batch_size"]
    model_name = config["ingestion"]["embedding_model"]

    texts_list = list(texts)
    all_embeddings = []
    model = TextEmbedding(
        model_name=model_name,
        providers=[
            # "TensorrtExecutionProvider",
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ],
    )

    with tqdm(
        total=len(texts_list),
        desc="Generating embeddings",
        unit="text",
        unit_scale=True,
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
) -> list[list[float]]:
    """Generate embeddings for documents using the specified backend.

    Args:
        texts: Iterable of text strings to embed.

    Returns:
        List of embedding vectors (each as a list of floats).
    """

    config = get_effective_config()
    backend = config["ingestion"]["embedding_backend"]

    if backend == "fastembed":
        return _generate_embeddings_fastembed(texts)
    elif backend == "sentence-transformers":
        return _generate_embeddings_sentence_transformers(texts)
    else:
        raise ValueError(
            f"Invalid embedding backend: {backend}. Must be 'sentence-transformers' "
            "or 'fastembed'."
        )
