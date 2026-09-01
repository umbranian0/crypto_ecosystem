# syntax=docker/dockerfile:1
#
# INGEST-007: packaging/wiring only -- builds ingestion-service per its
# uv-managed pyproject.toml and starts the FastAPI app via uvicorn, matching
# the non-root pattern already established by validation-service/gateway-api/
# reporting-service (INF-003/OPS-004 precedent). Wired into
# infra/docker-compose.yml as part of this same ticket.
#
# pyproject.toml declares naive_first_common as an editable path dependency
# at "../../libs/common" (relative to this service dir), so this image
# mirrors that monorepo layout under /repo. Because this Dockerfile's own
# build context is the service directory (matching validation-service's/
# reporting-service's own convention), libs/common is pulled in from the
# "libs" additional build context, the same shape infra/docker-compose.yml
# already defines for the other services.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /repo

COPY --from=libs common ./libs/common

WORKDIR /repo/services/ingestion-service

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# `connectors/` is this service's pre-existing standalone-script package
# (base.py/binance_price.py/etc, predates the src/ layout) -- src/app's
# routers/connectors.py imports from it directly (`from connectors.base
# import ...`). Locally, tests/conftest.py manually inserts this directory
# onto sys.path so pytest can import it without a pyproject.toml entry; that
# trick doesn't apply to `uvicorn app.main:app` at container runtime, so
# both copying the directory into the image AND putting it on PYTHONPATH are
# required -- omitting either previously produced a working test suite but a
# container that crashed on startup with ModuleNotFoundError: No module
# named 'connectors'.
COPY connectors ./connectors

RUN uv sync --frozen --no-dev

# Run as a non-root user (matches validation-service/gateway-api/
# reporting-service's own non-root Dockerfile finding, INF-003/OPS-004
# precedent).
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /repo
USER appuser

ENV PATH="/repo/services/ingestion-service/.venv/bin:${PATH}"
ENV PYTHONPATH="/repo/services/ingestion-service"

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
