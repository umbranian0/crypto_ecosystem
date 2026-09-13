"""SETUP-021: `RecentErrorsHandler` provider (mirrors `gateway-api`'s own
`app/dependencies/diagnostics.py` shape -- same module-level-singleton-
behind-a-provider pattern `operator_session.py` already established in this
service).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from naive_first_common import RecentErrorsHandler

recent_errors_handler = RecentErrorsHandler()


def get_recent_errors_handler() -> RecentErrorsHandler:
    return recent_errors_handler


RecentErrorsHandlerDep = Annotated[RecentErrorsHandler, Depends(get_recent_errors_handler)]
