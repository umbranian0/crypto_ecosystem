# syntax=docker/dockerfile:1
#
# INF-004: packaging/wiring only -- builds gateway-api per its existing
# uv-managed pyproject.toml and starts the FastAPI app via uvicorn. No
# change to services/gateway-api/src/.
#
# pyproject.toml declares naive_first_common as an editable path dependency
# at "../../libs/common" (relative to this service dir), so this image
# mirrors that monorepo layout under /repo, same as validation-service's
# Dockerfile (INF-003). Because this Dockerfile's own build context is the
# service directory (see infra/docker-compose.yml), libs/common is pulled in
# from the "libs" additional build context defined there. Unlike
# validation-service, gateway-api does not depend on naive_first_engine, so
# only libs/common is copied in.
#
# `scripts/` (GW-005's provision_tenant.py) is copied in too, so the
# full-stack smoke test this ticket requires can be run via `docker compose
# exec gateway-api ...` against the same in-container venv/gateway.db the
# app itself uses -- it is a fixture/operator tool, not part of the app
# package, but needs to exist inside the image for that.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /repo

COPY --from=libs common ./libs/common

WORKDIR /repo/services/gateway-api

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts

RUN uv sync --frozen --no-dev

ENV PATH="/repo/services/gateway-api/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
