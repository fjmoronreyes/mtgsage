
"""Generate semantic embeddings using a local Ollama model."""

from collections.abc import Sequence

import httpx

from app.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_QUERY_INSTRUCTION,
    OLLAMA_BASE_URL,
)


class OllamaEmbedder:
    """Convert documents and queries into semantic vectors."""

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        batch_size: int = EMBEDDING_BATCH_SIZE,
        dimensions: int = EMBEDDING_DIMENSIONS,
        client: httpx.Client | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("Batch size must be positive")

        if dimensions < 1:
            raise ValueError("Embedding dimensions must be positive")

        self.model = model
        self.batch_size = batch_size
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")

        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else httpx.Client(timeout=120.0)
        )

    def __enter__(self) -> "OllamaEmbedder":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client if owned by this instance."""
        if self._owns_client:
            self._client.close()

    def _embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Request embeddings for one batch of texts."""
        response = self._client.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.model,
                "input": texts,
                "truncate": False,
                "keep_alive": "1m",
            },
        )

        response.raise_for_status()
        embeddings = response.json().get("embeddings")

        if not isinstance(embeddings, list):
            raise ValueError("Invalid embedding response")

        if len(embeddings) != len(texts):
            raise ValueError(
                "Embedding count does not match input count"
            )

        if any(
            not isinstance(vector, list)
            or len(vector) != self.dimensions
            for vector in embeddings
        ):
            raise ValueError(
                "Unexpected embedding dimensions"
            )

        return embeddings

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Embed documents in batches, preserving input order."""
        if any(not text.strip() for text in texts):
            raise ValueError("Documents cannot be empty")

        embeddings: list[list[float]] = []

        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start:start + self.batch_size])
            embeddings.extend(self._embed_batch(batch))

        return embeddings

    def embed_query(self, question: str) -> list[float]:
        """Embed a search query with a retrieval instruction."""
        if not question.strip():
            raise ValueError("Query cannot be empty")

        query = (
            f"Instruct: {EMBEDDING_QUERY_INSTRUCTION}\n"
            f"Query: {question}"
        )

        return self._embed_batch([query])[0]
