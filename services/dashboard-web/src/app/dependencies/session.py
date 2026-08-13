"""DASH-002: in-memory session store, `session_id -> raw gateway-api API key`.

Deliberately **not** a `Repository` (implementation-plan.md section 7's
table) -- this service persists nothing of its own (README.md's "Does not
own"); this is a transient in-process cache, not a data-access layer over an
owned schema. Interim/PoC-scoped: a module-level dict means sessions don't
survive a process restart and don't work across multiple `dashboard-web`
replicas -- acceptable for this sprint's single-instance PoC, disclosed in
README.md's "Authentication (DASH-002)" section, not silently presented as
production-grade.

The raw API key held here is never logged/printed/rendered anywhere in this
module or any caller -- only the opaque `session_id` (`secrets.token_urlsafe`)
ever leaves this store's boundary (e.g. into a cookie).
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends


class SessionStore:
    """Opaque `session_id` -> raw API key, held server-side only."""

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create(self, api_key: str) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = api_key
        return session_id

    def get(self, session_id: str) -> str | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


_store = SessionStore()


def get_session_store() -> SessionStore:
    """FastAPI `Depends()` provider -- module-level singleton so every
    request shares the same in-process store (DASH-002's PoC scope; a real
    multi-replica deployment would need a shared backing store instead, see
    README.md's disclosed limitation).
    """
    return _store


SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
