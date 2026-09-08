# syntax=docker/dockerfile:1
#
# SETUP-030: packaging/wiring only -- builds dashboard-web per its existing
# uv-managed pyproject.toml and starts the FastAPI app via uvicorn. No
# change to services/dashboard-web/src/.
#
# pyproject.toml declares naive_first_common as an editable path dependency
# at "../../libs/common" (relative to this service dir), so this image
# mirrors that monorepo layout under /repo, same as gateway-api's/
# validation-service's Dockerfiles. Because this Dockerfile's own build
# context is the service directory (see infra/docker-compose.yml),
# libs/common is pulled in from the "libs" additional build context defined
# there. Like gateway-api, dashboard-web does not depend on
# naive_first_engine at runtime, so only libs/common is copied in.
#
# Unlike gateway-api, dashboard-web has no scripts/ directory (no
# provision_tenant.py/revoke_api_key.py-style operator tooling) -- that
# COPY line is intentionally omitted, not replaced with an empty one.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /repo

COPY --from=libs common ./libs/common

WORKDIR /repo/services/dashboard-web

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Run as a non-root user (same OPS-004-verified precedent as
# validation-service/gateway-api/reporting-service): the process has no
# need for root inside the container.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /repo
USER appuser

ENV PATH="/repo/services/dashboard-web/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
