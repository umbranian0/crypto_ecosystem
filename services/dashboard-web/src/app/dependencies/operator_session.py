"""DASH-113: operator-session store + `require_operator_session` gate.

Structurally separate from DASH-002/003's tenant-session mechanism, on
purpose (ticket Design section, Review acceptance criteria): a different
cookie name (`operator_session_id`, not `session_id`), a different
module-level store instance/namespace (`OperatorSessionStore`, not
`SessionStore`), and a different dependency (`require_operator_session`,
not `get_session_headers`). No shared function, no shared dict -- a
tenant's own session id is never looked up in this store and vice versa,
so neither session can ever satisfy the other's gate.

Pattern/mechanism reused, not reinvented (ticket Design section: "same
session mechanism DASH-002's tenant login already established"): an opaque
server-side-only token (`secrets.token_urlsafe(32)`) held in a process-local
dict, set as an `httponly`/`samesite=lax` cookie -- the same "cookie carries
only an opaque id, never the credential itself" discipline DASH-002's
`SessionStore` established for tenant sessions, applied here to the operator
token instead of a tenant's raw API key. `DASHBOARD_COOKIE_SECURE` (same env
var DASH-002 already reads) gates `secure=True` the same way.

`require_operator_session` mirrors DASH-003's `get_session_headers`
redirect-not-401 precedent (this backs HTML-rendering routes, not a JSON
API): a missing/unresolvable operator-session cookie raises
`HTTPException(303, headers={"Location": "/operator-login"})` before any
route body that depends on it executes. Unlike `get_session_headers`, there
is no downstream header to resolve -- gateway-api's operator-gated routes
take `X-Operator-Token` directly (GW-021), a header this dependency does not
construct or carry (no future `/settings/*` route exists yet in this ticket
to consume one).

DASH-112: `get_operator_token_header`/`OperatorTokenHeaderDep` (below) is
that anticipated header seam's first real consumer, added by this ticket.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request

_OPERATOR_SESSION_COOKIE_NAME = "operator_session_id"
_COOKIE_SECURE_ENV_VAR = "DASHBOARD_COOKIE_SECURE"


class OperatorSessionStore:
    """Opaque `operator_session_id` -> submitted operator token, held
    server-side only -- a distinct namespace from DASH-002's `SessionStore`,
    never sharing its dict or its cookie name.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create(self, token: str) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = token
        return session_id

    def get(self, session_id: str) -> str | None:
        return self._sessions.get(session_id)


_operator_store = OperatorSessionStore()


def get_operator_session_store() -> OperatorSessionStore:
    """FastAPI `Depends()` provider -- module-level singleton, same PoC scope
    (single-instance, no cross-restart persistence) DASH-002's `SessionStore`
    already discloses, applied here to the operator store instead.
    """
    return _operator_store


OperatorSessionStoreDep = Annotated[OperatorSessionStore, Depends(get_operator_session_store)]


def cookie_secure() -> bool:
    return os.environ.get(_COOKIE_SECURE_ENV_VAR, "false").strip().lower() == "true"


def require_operator_session(request: Request, store: OperatorSessionStoreDep) -> None:
    """Rejects (redirect to `/operator-login`) a request with no resolvable
    operator-session cookie -- the gate any future `/settings/*` route
    depends on (`DASH-112` is its first real consumer). A tenant's own
    `session_id` cookie is never read here, so it can never satisfy this
    gate (the cross-boundary case this ticket exists to close).
    """
    session_id = request.cookies.get(_OPERATOR_SESSION_COOKIE_NAME)
    token = store.get(session_id) if session_id is not None else None

    if token is None:
        raise HTTPException(status_code=303, headers={"Location": "/operator-login"})


RequireOperatorSessionDep = Annotated[None, Depends(require_operator_session)]


def get_operator_token_header(request: Request, store: OperatorSessionStoreDep) -> dict[str, str]:
    """DASH-112: the `X-Operator-Token` header seam this module's own
    docstring anticipated ("no future header to resolve... no future
    `/settings/*` route exists yet in this ticket to consume one") --
    `/settings/connectors` is that first real consumer. Mirrors
    `app.dependencies.downstream.get_session_headers`'s "gate, then resolve
    the outbound header" shape one hop over: calls `require_operator_session`
    directly (the exact same gate `/settings/connectors` is required to use,
    ticket Design section) rather than re-deriving the missing-cookie/
    unknown-session-id check a second time, then re-reads the now-known-valid
    cookie/store entry to build the header gateway-api's `get_authenticated_
    operator` (GW-021) expects.
    """
    require_operator_session(request, store)

    session_id = request.cookies.get(_OPERATOR_SESSION_COOKIE_NAME)
    token = store.get(session_id)
    return {"X-Operator-Token": token}


OperatorTokenHeaderDep = Annotated[dict[str, str], Depends(get_operator_token_header)]
