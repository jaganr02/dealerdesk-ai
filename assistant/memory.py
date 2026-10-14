"""
In-memory thread-safe conversation session memory for DealerDesk Assistant.
Keyed strictly by session_id with isolation and bounded turn retention.
"""

import threading
from collections import deque
from typing import Any, Dict, List, Optional


class SessionMemoryStore:
    """
    Thread-safe conversation memory store keyed by session_id.
    Maintains message history bounded to MAX_TURNS per session.
    """
    MAX_MESSAGES = 24  # Holds ~12 conversational turns

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str, dealer_id: int) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "dealer_id": dealer_id,
                    "messages": deque(maxlen=self.MAX_MESSAGES),
                }
            return self._sessions[session_id]

    def validate_and_get_history(self, session_id: str, dealer_id: int) -> List[Dict[str, Any]]:
        """
        Validate dealer isolation for session and return past messages as a list.
        """
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                # If dealer_id differs from session creator, keep session isolated to current dealer
                if session["dealer_id"] is not None and session["dealer_id"] != dealer_id:
                    # Reset memory if session_id is re-used by a different dealer
                    session["dealer_id"] = dealer_id
                    session["messages"].clear()
                elif session["dealer_id"] is None:
                    session["dealer_id"] = dealer_id
                return list(session["messages"])
            else:
                self._sessions[session_id] = {
                    "dealer_id": dealer_id,
                    "messages": deque(maxlen=self.MAX_MESSAGES),
                }
                return []

    def append_message(self, session_id: str, message_dict: Dict[str, Any], dealer_id: Optional[int] = None) -> None:
        """
        Append a message turn to the session history.
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "dealer_id": dealer_id,
                    "messages": deque(maxlen=self.MAX_MESSAGES),
                }
            self._sessions[session_id]["messages"].append(message_dict)

    def clear(self, session_id: Optional[str] = None) -> None:
        """
        Clear a single session or all sessions (useful for tests).
        """
        with self._lock:
            if session_id:
                if session_id in self._sessions:
                    del self._sessions[session_id]
            else:
                self._sessions.clear()


# Global singleton store
session_memory = SessionMemoryStore()
