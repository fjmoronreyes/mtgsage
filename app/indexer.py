
"""Orchestrate incremental indexing of MTG reference documents."""

import argparse
from pathlib import Path
from time import perf_counter

from app.config import RULES_PDF_PATH
from app.logger import configure_logging, get_logger
from app.parsers.general_parser import GeneralParser
from app.semantic.embedder import OllamaEmbedder
from app.semantic.vector_store import ChromaVectorStore, SyncResult


logger = get_logger("app.indexer")

PROGRESS_INTERVAL_SECONDS = 30


def _format_duration(seconds: float) -> str:
    """Format an elapsed or estimated duration."""
    total = max(0, round(seconds))

    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


class CorpusIndexer:
    """Coordinate parsing, embedding and vector storage."""

    def __init__(
        self,
        parser: GeneralParser,
        embedder: OllamaEmbedder,
        store: ChromaVectorStore,
    ) -> None:
        self.parser = parser
        self.embedder = embedder
        self.store = store

        logger.info(
            "Indexer ready | collection=%s | model=%s",
            store.collection_name,
            embedder.model,
        )

    def index(
        self,
        source: Path,
        limit: int | None = None,
        batch_size: int = 32,
    ) -> SyncResult:
        """Index documents incrementally and report progress with ETA."""
        if limit is not None and limit < 1:
            raise ValueError("Limit must be positive")

        if batch_size < 1:
            raise ValueError("Batch size must be positive")

        documents = self.parser.parse(source)

        if limit is not None:
            documents = documents[:limit]

        total = len(documents)

        if total == 0:
            raise ValueError("No documents to index")

        logger.info(
            "Indexing started | documents=%d | stored_before=%d | "
            "batch_size=%d",
            total,
            self.store.count(),
            batch_size,
        )

        added = 0
        updated = 0
        unchanged = 0

        started = perf_counter()
        last_report = started

        for offset in range(0, total, batch_size):
            batch = documents[offset:offset + batch_size]

            result = self.store.sync(
                documents=batch,
                embedder=self.embedder,
            )

            added += result.added
            updated += result.updated
            unchanged += result.unchanged

            processed = min(offset + batch_size, total)
            now = perf_counter()

            elapsed = now - started

            should_report = (
                offset == 0
                or now - last_report >= PROGRESS_INTERVAL_SECONDS
                or processed == total
            )

            if should_report:
                progress = processed / total * 100
                speed = processed / elapsed if elapsed > 0 else 0

                remaining = total - processed
                eta = remaining / speed if speed > 0 else 0

                logger.info(
                    "Indexing progress | %.1f%% (%d/%d) | "
                    "speed=%.2f docs/s | elapsed=%s | ETA=%s | "
                    "added=%d | updated=%d | unchanged=%d",
                    progress,
                    processed,
                    total,
                    speed,
                    _format_duration(elapsed),
                    _format_duration(eta),
                    added,
                    updated,
                    unchanged,
                )

                last_report = now

        elapsed = perf_counter() - started

        logger.info(
            "Indexing completed | duration=%s | stored=%d | "
            "added=%d | updated=%d | unchanged=%d",
            _format_duration(elapsed),
            self.store.count(),
            added,
            updated,
            unchanged,
        )

        return SyncResult(
            added=added,
            updated=updated,
            unchanged=unchanged,
        )


def main() -> None:
    cli = argparse.ArgumentParser(
        description="Index MTG rules and glossary into ChromaDB."
    )

    cli.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum documents to index (default: all).",
    )

    cli.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and rebuild the MTG collection.",
    )

    cli.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Documents per synchronization batch (default: 32).",
    )

    args = cli.parse_args()

    if args.limit is not None and args.limit < 1:
        cli.error("--limit must be positive")

    if args.batch_size < 1:
        cli.error("--batch-size must be positive")

    if not RULES_PDF_PATH.is_file():
        cli.error(f"Rules PDF not found: {RULES_PDF_PATH}")

    store = ChromaVectorStore(recreate=args.recreate)

    with OllamaEmbedder() as embedder:
        indexer = CorpusIndexer(
            parser=GeneralParser(),
            embedder=embedder,
            store=store,
        )

        indexer.index(
            source=RULES_PDF_PATH,
            limit=args.limit,
            batch_size=args.batch_size,
        )


if __name__ == "__main__":
    configure_logging()

    try:
        main()
    except Exception:
        logger.exception("Corpus indexing failed")
        raise SystemExit(1) from None
