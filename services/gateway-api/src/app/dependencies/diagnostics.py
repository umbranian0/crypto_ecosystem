"""SETUP-021: `RecentErrorsHandler` provider.

Mirrors `dashboard-web`'s `operator_session.py` module-level-singleton-
behind-a-provider pattern: one `RecentErrorsHandler` instance is created here
and attached to the root logger by `app.main` at import time; this module's
provider exposes that exact same instance to route handlers, never a fresh
one, so `/diagnostics/recent-errors` reads the buffer the root logger is
actually writing into.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from naive_first_common import RecentErrorsHandler

recent_errors_handler = RecentErrorsHandler()


def get_recent_errors_handler() -> RecentErrorsHandler:
    return recent_errors_handler


RecentErrorsHandlerDep = Annotated[RecentErrorsHandler, Depends(get_recent_errors_handler)]
