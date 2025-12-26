# Embedding Backends

Openground supports multiple embedding backends for generating vector embeddings. Each backend has different characteristics in terms of speed, quality, and hardware requirements.

## Available Backends

### fastembed (Default)

**Default backend** - Fast and efficient, optimized for production use.

- **Library**: [fastembed](https://github.com/qdrant/fastembed)
- **Default Model**: `BAAI/bge-small-en-v1.5` (384 dimensions)
- **Speed**: Very fast, optimized C++ implementation
- **GPU Support**: CUDA support via ONNX Runtime
- **Best for**: Production use, large-scale embedding tasks

### sentence-transformers

Traditional Python-based backend with extensive model support.

- **Library**: [sentence-transformers](https://www.sbert.net/)
- **Default Model**: `BAAI/bge-small-en-v1.5` (384 dimensions)
- **Speed**: Moderate, pure Python implementation
- **GPU Support**: CUDA and MPS (Apple Silicon) via PyTorch
- **Best for**: Experimentation, access to HuggingFace model hub

## Switching Backends

To change the embedding backend:

```bash
# Switch to sentence-transformers
openground config set ingestion.embedding_backend sentence-transformers

# Switch to fastembed (default)
openground config set ingestion.embedding_backend fastembed
```

!!! warning "Backend Compatibility"
    Each backend stores embeddings with specific metadata. If you switch backends, you must re-embed all libraries:
    
    ```bash
    # Remove existing embeddings
    openground nuke embeddings -y
    
    # Re-embed with new backend
    openground embed LIBRARY_NAME
    ```

## Model Compatibility

### fastembed Models

Fastembed supports models optimized for ONNX Runtime. Common models:

- `BAAI/bge-small-en-v1.5` (default) - 384 dims, fast, good quality
- `BAAI/bge-base-en-v1.5` - 768 dims, better quality, slower
- `sentence-transformers/all-MiniLM-L6-v2` - 384 dims, widely compatible

### sentence-transformers Models

Supports any model from the HuggingFace model hub. Popular choices:

- `BAAI/bge-small-en-v1.5` (default) - 384 dims
- `sentence-transformers/all-MiniLM-L6-v2` - 384 dims, lightweight
- `sentence-transformers/all-mpnet-base-v2` - 768 dims, high quality

## Choosing a Backend

**Use fastembed if:**
- You want maximum speed
- You're embedding large amounts of data
- You need production-ready performance

**Use sentence-transformers if:**
- You want to experiment with different models
- You need access to the full HuggingFace model hub
- You're on Apple Silicon (MPS support)

## Configuration

Set the backend and model in your config:

```bash
# Set backend
openground config set ingestion.embedding_backend fastembed

# Set model (must be compatible with chosen backend)
openground config set ingestion.embedding_model BAAI/bge-small-en-v1.5

# Set dimensions (must match model)
openground config set ingestion.embedding_dimensions 384
```

See [Configuration](configuration.md) for all available settings.

## See Also

- [embed](commands/embed.md) - How to embed documentation
- [Configuration](configuration.md) - All configuration options
- [nuke](commands/nuke.md) - Removing data when switching backends

