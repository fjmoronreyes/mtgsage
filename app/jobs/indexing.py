"""Thread-safe coordinator for one background corpus indexing job."""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import Iterator, Literal

from app.config import RULES_PDF_PATH
from app.indexer import CorpusIndexer, IndexProgress
from app.logger import get_logger
from app.parsers.general_parser import GeneralParser
from app.semantic.embedder import OllamaEmbedder
from app.semantic.vector_store import ChromaVectorStore


logger = get_logger(__name__)
JobStatus = Literal["idle", "running", "completed", "cancelled", "failed"]


@dataclass(frozen=True, slots=True)
class IndexJobSnapshot:
    status: JobStatus = "idle"
    processed: int = 0
    total: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    stored_before: int = 0
    stored_after: int | None = None
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None
    cancel_requested: bool = False
    error: str | None = None
    revision: int = 0


class IndexJobManager:
    """Run at most one index job and exclude concurrent chat operations.

    The worker never touches Streamlit or session state. UI consumers poll
    immutable snapshots. Each finished job increments the index revision.
    """

    def __init__(self, source: Path = RULES_PDF_PATH) -> None:
        self.source = source
        self._lock = Lock()
        self._cancel = Event()
        self._snapshot = IndexJobSnapshot()
        self._active_chats = 0
        self._started_at: float | None = None

    def snapshot(self) -> IndexJobSnapshot:
        with self._lock:
            result = self._snapshot
            if result.status == "running" and self._started_at is not None:
                result = replace(
                    result,
                    elapsed_seconds=monotonic() - self._started_at,
                )
            return result

    def start(
        self,
        *,
        limit: int | None = None,
        recreate: bool = False,
        batch_size: int = 16,
    ) -> None:
        if limit is not None and limit < 1:
            raise ValueError("Limit must be positive")
        if batch_size < 1:
            raise ValueError("Batch size must be positive")
        if not self.source.is_file():
            raise FileNotFoundError(f"Rules PDF not found: {self.source}")

        with self._lock:
            if self._snapshot.status == "running":
                raise RuntimeError("An indexing job is already running")
            if self._active_chats:
                raise RuntimeError("Wait for active chat requests to finish")

            self._cancel = Event()
            self._started_at = monotonic()
            self._snapshot = IndexJobSnapshot(
                status="running", revision=self._snapshot.revision,
            )
            worker = Thread(
                target=self._run,
                args=(limit, recreate, batch_size, self._cancel),
                name="mtgsage-indexer",
                daemon=True,
            )
            worker.start()

    def cancel(self) -> bool:
        """Ask the worker to stop after its current synchronization batch."""
        with self._lock:
            if self._snapshot.status != "running":
                return False
            self._cancel.set()
            self._snapshot = replace(self._snapshot, cancel_requested=True)
            return True

    @contextmanager
    def chat_slot(self) -> Iterator[None]:
        """Prevent a rebuild from starting during an in-flight chat request."""
        with self._lock:
            if self._snapshot.status == "running":
                raise RuntimeError("Chat is unavailable during indexing")
            self._active_chats += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_chats -= 1

    def _on_progress(self, progress: IndexProgress) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                processed=progress.processed,
                total=progress.total,
                added=progress.added,
                updated=progress.updated,
                unchanged=progress.unchanged,
                stored_before=progress.stored_before,
                elapsed_seconds=progress.elapsed_seconds,
                eta_seconds=progress.eta_seconds,
            )

    def _run(
        self,
        limit: int | None,
        recreate: bool,
        batch_size: int,
        stop: Event,
    ) -> None:
        store: ChromaVectorStore | None = None
        try:
            store = ChromaVectorStore(recreate=recreate)
            with OllamaEmbedder() as embedder:
                indexer = CorpusIndexer(GeneralParser(), embedder, store)
                indexer.index(
                    self.source,
                    limit=limit,
                    batch_size=batch_size,
                    on_progress=self._on_progress,
                    should_cancel=stop.is_set,
                )
            final_count = store.count()
            with self._lock:
                current = self._snapshot
                status: JobStatus = (
                    "cancelled"
                    if stop.is_set() and current.processed < current.total
                    else "completed"
                )
                self._snapshot = replace(
                    current,
                    status=status,
                    stored_after=final_count,
                    eta_seconds=None,
                    revision=current.revision + 1,
                )
            logger.info("Index job finished | status=%s", status)
        except Exception as exc:
            logger.exception("Background indexing failed")
            with self._lock:
                self._snapshot = replace(
                    self._snapshot,
                    status="failed",
                    error=str(exc),
                    eta_seconds=None,
                    revision=self._snapshot.revision + 1,
                )
