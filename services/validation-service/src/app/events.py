"""`EventPublisher` Observer interface (implementation-plan.md section 7) +
interim in-process implementation + durable Redis Streams implementation
(VS-014).

Single responsibility: give route handlers a `publish(event_name, payload)`
seam for domain events (starting with `run.completed`, VS-009) without
coupling them to a transport.

Interim: `InProcessLogEventPublisher` neither persists nor delivers anywhere
outside this process -- it logs a structured line and appends to an
in-memory list, sufficient to prove a handler's publish call happens at the
right point without a live broker.

Durable: `RedisStreamsEventPublisher` (VS-014) writes to a Redis Stream keyed
by `event_name` via `XADD`, one flattened string field per payload key (per
grooming binding decision #9 -- no nested JSON blob), so a consumer can
`XRANGE`/`XREAD` without deserializing a sub-document. `reporting-service`'s
eventual subscription to `run.completed` is not yet wired end-to-end; see
this service's README for the documented payload contract.
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


class RedisStreamsEventPublisher:
    """Durable `EventPublisher` (VS-014): `publish(event_name, payload)` calls
    `XADD event_name <flattened payload>` on a `redis` client.

    The stream key is `event_name` itself (binding decision #9) -- there is
    no separate topic-naming scheme. Payload values are coerced to `str`
    before `XADD`, since Redis Streams field values are strings/bytes; `None`
    becomes `""` rather than the literal string `"None"`, so a consumer sees
    an empty field instead of a value that would parse as a truthy string.
    """

    def __init__(self, redis_client: typing.Any) -> None:
        self._redis = redis_client

    def publish(self, event_name: str, payload: dict) -> None:
        fields = {key: ("" if value is None else str(value)) for key, value in payload.items()}
        self._redis.xadd(event_name, fields)
