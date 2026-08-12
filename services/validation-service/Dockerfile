# syntax=docker/dockerfile:1
#
# INF-003: packaging/wiring only -- builds validation-service per its
# existing uv-managed pyproject.toml and starts the FastAPI app via
# uvicorn. No change to services/validation-service/src/.
#
# pyproject.toml declares naive_first_engine/naive_first_common as editable
# path dependencies at "../../libs/..." (relative to this service dir), so
# this image mirrors that monorepo layout under /repo. Because this
# Dockerfile's own build context is the service directory (see
# infra/docker-compose.yml), libs/common and libs/naive_first_engine are
# pulled in from the "libs" additional build context defined there.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /repo

COPY --from=libs common ./libs/common
COPY --from=libs naive_first_engine ./libs/naive_first_engine

WORKDIR /repo/services/validation-service

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Run as a non-root user (operability finding, 2026-08-09 review): the
# process has no need for root inside the container.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /repo
USER appuser

ENV PATH="/repo/services/validation-service/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
