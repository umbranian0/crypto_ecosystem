"""`EventPublisher` Observer interface (implementation-plan.md section 7) +
interim in-process implementation.

Single responsibility: give route handlers a `publish(event_name, payload)`
seam for domain events (starting with `run.completed`, VS-009) without
coupling them to a transport. A durable, Redis Streams-backed implementation
(VS-014) is blocked on trigger #7 (implementation-plan.md section 4) and will
be a separate class behind this same interface -- this module owns no broker
connection/topic scheme in the meantime.

Interim only: `InProcessLogEventPublisher` neither persists nor delivers
anywhere outside this process -- it logs a structured line and appends to an
in-memory list, sufficient to prove a handler's publish call happens at the
right point without a live broker. `reporting-service`'s eventual
subscription to `run.completed` is not yet wired end-to-end; see this
service's README.
"""

from __future__ import annotations

import logging
import typing

logger = logging.getLogger(__name__)


@typing.runtime_checkable
class EventPublisher(typing.Protocol):
    """Adapter interface (implementation-plan.md section 7): one method, so a
    future broker-backed publisher can swap in without touching callers.
    """

    def publish(self, event_name: str, payload: dict) -> None: ...


class InProcessLogEventPublisher:
    """Interim `EventPublisher`: logs the event and records it on
    `self.published` (a list of `{"event_name": ..., "payload": ...}` dicts),
    retrievable in tests.
    """

    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish(self, event_name: str, payload: dict) -> None:
        logger.info("event published: %s", event_name, extra={"event_name": event_name, "payload": payload})
        self.published.append({"event_name": event_name, "payload": payload})
