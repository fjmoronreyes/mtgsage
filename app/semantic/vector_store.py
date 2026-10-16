
"""Persistent vector storage for MtgSage knowledge documents."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import chromadb
from chromadb.config import Settings

from app.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from app.parsers.general_parser import IndexDocument

from .embedder import OllamaEmbedder


@dataclass(frozen=True, slots=True)
class SyncResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0


@dataclass(frozen=True, slots=True)
class SearchHit:
    source_id: str
    content: str
    distance: float
    metadata: dict[str, Any]


class ChromaVectorStore:
    """Manage a persistent, idempotent vector collection."""

    def __init__(
        self,
        path: Path = CHROMA_DIR,
        collection_name: str = CHROMA_COLLECTION,
        model: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = 32,
        recreate: bool = False,
    ) -> None:
        if dimensions < 1 or batch_size < 1:
            raise ValueError("Dimensions and batch size must be positive")

        self.path = Path(path)
        self.collection_name = collection_name
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

        self._collection_metadata = {
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "schema_version": 1,
            "distance_metric": "cosine",
        }

        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=Settings(anonymized_telemetry=False),
        )

        if recreate:
            existing = {
                collection.name
                for collection in self._client.list_collections()
            }
            if self.collection_name in existing:
                self._client.delete_collection(
                    name=self.collection_name
                )

        self._collection = self._open_collection()
        self._validate_collection()

    def _open_collection(self):
        return self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
            metadata=self._collection_metadata,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def _validate_collection(self) -> None:
        """Reject indexes built with incompatible settings."""
        stored = self._collection.metadata or {}

        if any(
            stored.get(key) != value
            for key, value in self._collection_metadata.items()
        ):
            raise ValueError(
                "Incompatible vector collection configuration. "
                "Use recreate=True to rebuild it explicitly."
            )

    @staticmethod
    def _document_metadata(
        document: IndexDocument,
    ) -> dict[str, str | int | float | bool]:
        """Convert domain metadata to Chroma-compatible values."""
        metadata: dict[str, str | int | float | bool] = {}

        for key, value in document.metadata.items():
            if value is None:
                continue

            if isinstance(value, (list, tuple)):
                metadata[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                )
            elif isinstance(value, (str, int, float, bool)):
                metadata[key] = value
            else:
                raise TypeError(
                    f"Unsupported metadata type for {key}"
                )

        metadata["content_sha256"] = sha256(
            document.content.encode("utf-8")
        ).hexdigest()

        return metadata

    def count(self) -> int:
        """Return the number of stored documents."""
        return self._collection.count()

    def clear(self) -> None:
        """Delete and recreate only this collection."""
        self._client.delete_collection(
            name=self.collection_name
        )
        self._collection = self._open_collection()

    def sync(
        self,
        documents: Sequence[IndexDocument],
        embedder: OllamaEmbedder,
        *,
        prune: bool = False,
    ) -> SyncResult:
        """Synchronize documents without embedding unchanged content.

        With prune=True, documents absent from the supplied corpus
        are also deleted. Supply the complete corpus in that case.
        """
        if embedder.model != self.model:
            raise ValueError("Embedder model does not match collection")

        if embedder.dimensions != self.dimensions:
            raise ValueError("Embedder dimensions do not match collection")

        ids = [document.source_id for document in documents]

        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source IDs in input documents")

        if any(
            not document.source_id or not document.content.strip()
            for document in documents
        ):
            raise ValueError("Documents must have an ID and content")

        if prune and not documents:
            raise ValueError("Refusing to prune with an empty corpus")

        added = updated = unchanged = removed = 0

        for offset in range(0, len(documents), self.batch_size):
            batch = documents[offset:offset + self.batch_size]

            existing = self._collection.get(
                ids=[document.source_id for document in batch],
                include=["metadatas"],
            )

            stored = dict(
                zip(
                    existing["ids"],
                    existing["metadatas"] or [],
                )
            )

            to_embed: list[IndexDocument] = []
            embed_metadata: list[dict] = []

            metadata_ids: list[str] = []
            metadata_updates: list[dict] = []

            for document in batch:
                metadata = self._document_metadata(document)
                previous = stored.get(document.source_id)

                if previous is None:
                    added += 1
                    to_embed.append(document)
                    embed_metadata.append(metadata)

                elif (
                    previous.get("content_sha256")
                    != metadata["content_sha256"]
                ):
                    updated += 1
                    to_embed.append(document)
                    embed_metadata.append(metadata)

                elif previous != metadata:
                    updated += 1
                    metadata_ids.append(document.source_id)
                    metadata_updates.append(metadata)

                else:
                    unchanged += 1

            if to_embed:
                vectors = embedder.embed_documents(
                    [document.content for document in to_embed]
                )

                self._collection.upsert(
                    ids=[
                        document.source_id
                        for document in to_embed
                    ],
                    documents=[
                        document.content
                        for document in to_embed
                    ],
                    metadatas=embed_metadata,
                    embeddings=vectors,
                )

            if metadata_ids:
                self._collection.update(
                    ids=metadata_ids,
                    metadatas=metadata_updates,
                )

        if prune:
            stored_ids = set(
                self._collection.get(include=[])["ids"]
            )
            stale_ids = sorted(stored_ids - set(ids))

            for offset in range(
                0, len(stale_ids), self.batch_size
            ):
                batch = stale_ids[offset:offset + self.batch_size]
                self._collection.delete(ids=batch)

            removed = len(stale_ids)

        return SyncResult(
            added=added,
            updated=updated,
            unchanged=unchanged,
            removed=removed,
        )

    def search(
        self,
        vector: Sequence[float],
        limit: int = 5,
        kind: Literal["rule", "glossary"] | None = None,
    ) -> list[SearchHit]:
        """Retrieve the nearest documents using cosine distance."""
        if limit < 1:
            raise ValueError("Search limit must be positive")

        if len(vector) != self.dimensions:
            raise ValueError("Invalid query embedding dimensions")

        if self.count() == 0:
            return []

        results = self._collection.query(
            query_embeddings=[list(vector)],
            n_results=min(limit, self.count()),
            where={"kind": kind} if kind else None,
            include=["documents", "metadatas", "distances"],
        )

        contents = results["documents"]
        metadatas = results["metadatas"]
        distances = results["distances"]

        if contents is None or metadatas is None or distances is None:
            raise ValueError("Incomplete vector search response")

        return [
            SearchHit(
                source_id=source_id,
                content=content,
                distance=float(distance),
                metadata=dict(metadata or {}),
            )
            for source_id, content, metadata, distance in zip(
                results["ids"][0],
                contents[0],
                metadatas[0],
                distances[0],
            )
        ]
