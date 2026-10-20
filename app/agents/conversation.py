
"""In-memory conversation sessions for MtgSage."""

from collections import deque
from dataclasses import dataclass
from uuid import uuid4

from app.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A completed user-assistant exchange."""

    question: str
    answer: str


class ConversationStore:
    """Keep bounded conversation histories, isolated by session."""

    def __init__(
        self,
        max_turns: int = 6,
        max_sessions: int = 100,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")

        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")

        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self._sessions: dict[str, deque[ConversationTurn]] = {}

    def create_session(self) -> str:
        """Create an independent conversation session."""
        if len(self._sessions) >= self.max_sessions:
            raise RuntimeError("Conversation session limit reached")

        session_id = uuid4().hex

        self._sessions[session_id] = deque(
            maxlen=self.max_turns,
        )

        logger.info(
            "Conversation session created | active_sessions=%d",
            len(self._sessions),
        )

        return session_id

    def history(self, session_id: str) -> tuple[ConversationTurn, ...]:
        """Return a read-only snapshot of completed turns."""
        return tuple(self._get_session(session_id))

    def add_turn(
        self,
        session_id: str,
        question: str,
        answer: str,
    ) -> None:
        """Store an exchange only after a successful agent response."""
        if not question.strip():
            raise ValueError("Question cannot be empty")

        if not answer.strip():
            raise ValueError("Answer cannot be empty")

        self._get_session(session_id).append(
            ConversationTurn(
                question=question.strip(),
                answer=answer.strip(),
            )
        )

    def clear(self, session_id: str) -> None:
        """Reset a conversation without changing its session ID."""
        self._get_session(session_id).clear()

        logger.info("Conversation history cleared")

    def delete_session(self, session_id: str) -> None:
        """Release an entire conversation session."""
        self._get_session(session_id)
        del self._sessions[session_id]

        logger.info(
            "Conversation session deleted | active_sessions=%d",
            len(self._sessions),
        )

    def _get_session(
        self,
        session_id: str,
    ) -> deque[ConversationTurn]:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise ValueError(
                "Unknown conversation session"
            ) from None
