"""Incremental MTG corpus indexing, usable from the CLI or an application."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from app.config import RULES_PDF_PATH
from app.logger import configure_logging, get_logger
from app.parsers.general_parser import GeneralParser
from app.semantic.embedder import OllamaEmbedder
from app.semantic.vector_store import ChromaVectorStore, SyncResult


logger = get_logger("app.indexer")
PROGRESS_LOG_INTERVAL = 30.0


@dataclass(frozen=True, slots=True)
class IndexProgress:
    """Immutable progress snapshot; contains no UI or logging dependencies."""

    processed: int
    total: int
    added: int
    updated: int
    unchanged: int
    stored_before: int
    elapsed_seconds: float
    eta_seconds: float | None


ProgressCallback = Callable[[IndexProgress], None]
CancelCheck = Callable[[], bool]


def _duration(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


class CorpusIndexer:
    """Parse, incrementally embed, and store rules and glossary entries."""

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
        *,
        on_progress: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> SyncResult:
        """Synchronize the selected documents without pruning the collection.

        Cancellation is cooperative: a running batch finishes before stopping.
        Completed batches remain persisted, including after interruption.
        """
        if limit is not None and limit < 1:
            raise ValueError("Limit must be positive")
        if batch_size < 1:
            raise ValueError("Batch size must be positive")

        documents = self.parser.parse(source)
        if limit is not None:
            documents = documents[:limit]
        if not documents:
            raise ValueError("No documents to index")

        total = len(documents)
        stored_before = self.store.count()
        logger.info(
            "Indexing started | selected=%d | stored_before=%d | batch_size=%d",
            total, stored_before, batch_size,
        )

        started = last_log = perf_counter()
        processed = added = updated = unchanged = 0
        new_work_seconds = 0.0
        new_work_documents = 0

        def make_progress(now: float) -> IndexProgress:
            # Estimate from the cost of *new/changed* embeddings, not from
            # the very fast lookup of records already present in Chroma.
            remaining = total - processed
            eta = None
            if new_work_documents >= 8 and new_work_seconds > 0:
                # Conservative estimate: all unvisited documents need work.
                eta = remaining * new_work_seconds / new_work_documents
            return IndexProgress(
                processed=processed,
                total=total,
                added=added,
                updated=updated,
                unchanged=unchanged,
                stored_before=stored_before,
                elapsed_seconds=now - started,
                eta_seconds=eta,
            )

        if on_progress is not None:
            on_progress(make_progress(started))

        cancelled = False
        for offset in range(0, total, batch_size):
            if should_cancel is not None and should_cancel():
                cancelled = True
                break

            batch_started = perf_counter()
            result = self.store.sync(
                documents[offset:offset + batch_size],
                self.embedder,
            )
            now = perf_counter()

            processed = min(offset + batch_size, total)
            added += result.added
            updated += result.updated
            unchanged += result.unchanged
            changed = result.added + result.updated
            if changed:
                new_work_documents += changed
                new_work_seconds += now - batch_started

            progress = make_progress(now)
            if on_progress is not None:
                on_progress(progress)

            if offset == 0 or now - last_log >= PROGRESS_LOG_INTERVAL or processed == total:
                logger.info(
                    "Indexing progress | %d/%d (%.1f%%) | added=%d | "
                    "updated=%d | unchanged=%d | elapsed=%s | ETA=%s",
                    processed, total, processed / total * 100,
                    added, updated, unchanged,
                    _duration(progress.elapsed_seconds),
                    _duration(progress.eta_seconds)
                    if progress.eta_seconds is not None else "calculating",
                )
                last_log = now

        summary = SyncResult(
            added=added, updated=updated, unchanged=unchanged, removed=0,
        )
        if cancelled:
            logger.warning(
                "Indexing cancelled | processed=%d/%d | persisted=%d",
                processed, total, self.store.count(),
            )
        else:
            logger.info(
                "Indexing completed | duration=%s | stored=%d | "
                "added=%d | updated=%d | unchanged=%d",
                _duration(perf_counter() - started), self.store.count(),
                added, updated, unchanged,
            )
        return summary


def main() -> None:
    cli = argparse.ArgumentParser(description="Index MTG reference documents")
    cli.add_argument("--limit", type=int, default=None,
                     help="Maximum documents (default: all)")
    cli.add_argument("--batch-size", type=int, default=32)
    cli.add_argument("--recreate", action="store_true",
                     help="Delete and rebuild the MTG collection")
    args = cli.parse_args()

    if args.limit is not None and args.limit < 1:
        cli.error("--limit must be positive")
    if args.batch_size < 1:
        cli.error("--batch-size must be positive")
    if not RULES_PDF_PATH.is_file():
        cli.error(f"Rules PDF not found: {RULES_PDF_PATH}")

    store = ChromaVectorStore(recreate=args.recreate)
    with OllamaEmbedder() as embedder:
        CorpusIndexer(GeneralParser(), embedder, store).index(
            RULES_PDF_PATH, limit=args.limit, batch_size=args.batch_size,
        )


if __name__ == "__main__":
    configure_logging()
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Indexing interrupted by user; completed batches are saved")
        raise SystemExit(130) from None
    except Exception:
        logger.exception("Indexing failed")
        raise SystemExit(1) from None
