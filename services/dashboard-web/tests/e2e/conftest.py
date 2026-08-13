"""DASH-009: fixtures for the Selenium browser-level E2E suite.

Nothing here is reusable from `tests/test_*.py` (DASH-002/003/004/006/007/008's
own suites) -- they all wire in `httpx.MockTransport` around an in-process
`fastapi.testclient.TestClient`; this suite needs a real subprocess serving
`dashboard-web` on a real socket (the backlog's own "not in-process TestClient"
wording) plus a real browser driving it, so a live-server/WebDriver fixture had
to be built from scratch (DRY check note in this ticket's Design section --
grepped `tests/` first, confirmed no existing fixture of this shape exists
anywhere in this repo).

Two subprocesses per test session (both `scope="session"` -- restarting either
per test would make an already-slow browser suite far slower for no benefit,
since neither holds cross-test state that matters: `dashboard-web`'s own
`SessionStore` is keyed by opaque `session_id`, and the stub gateway-api's
`_runs` dict is keyed by fresh `uuid4()` per created run):

- `stub_gateway_api`: the Design section's option (a) fixture gateway-api
  (`stub_gateway_api.py`, same directory), run via `python -m uvicorn`.
- `live_server`: a real `dashboard-web` instance, `GATEWAY_API_URL` pointed at
  `stub_gateway_api`'s own base URL, also run via `python -m uvicorn` (same
  invocation shape as this service's own README.md "Local setup" section, not
  a different one).

`driver`: a Selenium Chrome WebDriver, headless by default (Selenium Manager,
bundled since selenium>=4.6, resolves a matching chromedriver automatically --
no manual driver install needed as long as Chrome itself is installed). Set
`E2E_HEADFUL=true` to watch the browser locally; `E2E_BROWSER` is reserved for
a future non-Chrome driver but only `"chrome"` (the default) is wired up today
-- documented in README.md's "Tests" section rather than silently supported.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
_READY_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.25


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = _READY_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
        except Exception as exc:  # connection refused while uvicorn is still starting
            last_error = exc
        else:
            if response.status_code < 500:
                return
            last_error = RuntimeError(f"{url} returned {response.status_code}")
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"{url} did not become ready within {timeout}s: {last_error}")


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def stub_gateway_api() -> str:
    """Starts `stub_gateway_api.py` as its own subprocess, real HTTP, real
    socket -- imported by module path (`tests.e2e.stub_gateway_api:app`), not
    executed in-process, so `dashboard-web`'s own outbound `httpx` calls hit a
    real server exactly as they would hit a real `gateway-api`.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.e2e.stub_gateway_api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(SERVICE_ROOT),
    )
    try:
        _wait_until_ready(f"{base_url}/health")
        yield base_url
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def live_server(stub_gateway_api: str) -> str:
    """Starts a real `dashboard-web` `uvicorn` process (subprocess, not
    `TestClient`), `GATEWAY_API_URL` pointed at the `stub_gateway_api` fixture
    -- same `uvicorn app.main:app --app-dir src` invocation shape as
    README.md's "Local setup" section, just on a test port with an env var
    override, not a second/different way of starting this service.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "GATEWAY_API_URL": stub_gateway_api,
        "DASHBOARD_COOKIE_SECURE": "false",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "src",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(SERVICE_ROOT),
        env=env,
    )
    try:
        # dashboard-web's own /health (DASH-008) calls out to
        # GATEWAY_API_URL/health, so this also proves connectivity to the
        # stub fixture before any test runs, not just that uvicorn bound a
        # socket.
        _wait_until_ready(f"{base_url}/health")
        yield base_url
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    browser = os.environ.get("E2E_BROWSER", "chrome").strip().lower()
    if browser != "chrome":
        raise RuntimeError(
            f"unsupported E2E_BROWSER={browser!r} -- only 'chrome' is wired up in this suite"
        )

    options = Options()
    if os.environ.get("E2E_HEADFUL", "").strip().lower() != "true":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1024")

    drv = webdriver.Chrome(options=options)
    drv.implicitly_wait(0)
    try:
        yield drv
    finally:
        drv.quit()
