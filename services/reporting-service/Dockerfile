# syntax=docker/dockerfile:1
#
# RS-001: packaging/wiring only -- builds reporting-service per its
# uv-managed pyproject.toml and starts the FastAPI app via uvicorn, matching
# the non-root pattern already established by validation-service/gateway-api
# (INF-003/OPS-004 precedent). NOT yet wired into infra/docker-compose.yml
# (RS-GAP) -- this Dockerfile exists so that follow-up is a Compose-file
# edit only, not a packaging project.
#
# pyproject.toml declares naive_first_common as an editable path dependency
# at "../../libs/common" (relative to this service dir), so this image
# mirrors that monorepo layout under /repo. Because this Dockerfile's own
# build context is the service directory (matching validation-service's own
# convention), libs/common is pulled in from the "libs" additional build
# context, the same shape infra/docker-compose.yml already defines for the
# other services.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /repo

COPY --from=libs common ./libs/common

WORKDIR /repo/services/reporting-service

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Run as a non-root user (matches validation-service/gateway-api's own
# non-root Dockerfile finding, INF-003/OPS-004 precedent).
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /repo
USER appuser

ENV PATH="/repo/services/reporting-service/.venv/bin:${PATH}"

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
