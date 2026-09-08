"""SETUP-003: Selenium E2E extension of DASH-009's suite -- the wizard's
full browser flow: fresh stub `gateway-api` (zero tenants) -> `/` shows the
wizard -> submit a tenant name -> the raw API key is displayed exactly once
-> follow the `/login` link -> log in successfully with that same key.

Relies on `stub_gateway_api.py`'s `_initialized` flag starting `False` for
the whole (session-scoped) fixture -- this module must run before anything
else in the session calls `/setup/initialize`, which is why it is the only
e2e module touching `/setup/*` at all (see that fixture's own module
docstring note).
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.e2e.stub_gateway_api import VALID_API_KEY

pytestmark = pytest.mark.e2e

_WAIT_SECONDS = 10


def test_fresh_install_wizard_flow_ends_in_a_working_login(driver, live_server) -> None:
    driver.get(live_server)
    WebDriverWait(driver, _WAIT_SECONDS).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "form[action='/setup']"))
    )
    assert driver.current_url == f"{live_server}/setup"

    driver.find_element(By.ID, "tenant_name").send_keys("E2E Wizard Tenant")
    driver.find_element(By.CSS_SELECTOR, "form[action='/setup'] button[type=submit]").click()

    WebDriverWait(driver, _WAIT_SECONDS).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "pre.api-key"))
    )
    revealed_key = driver.find_element(By.CSS_SELECTOR, "pre.api-key").text.strip()
    assert revealed_key == VALID_API_KEY
    assert "E2E Wizard Tenant" in driver.page_source

    driver.find_element(By.LINK_TEXT, "Continue to log in").click()
    WebDriverWait(driver, _WAIT_SECONDS).until(EC.url_to_be(f"{live_server}/login"))

    driver.find_element(By.ID, "api_key").send_keys(revealed_key)
    driver.find_element(By.CSS_SELECTOR, "form[action='/login'] button[type=submit]").click()

    WebDriverWait(driver, _WAIT_SECONDS).until(EC.url_to_be(f"{live_server}/runs/new"))
    assert driver.get_cookie("session_id") is not None


def test_visiting_setup_after_initialization_redirects_straight_to_login(driver, live_server) -> None:
    """Runs after the flow above, so the stub is already initialized --
    proves SETUP-003's "no error surfaced, no form re-render" AC.
    """
    driver.get(f"{live_server}/setup")
    WebDriverWait(driver, _WAIT_SECONDS).until(EC.url_to_be(f"{live_server}/login"))
    assert "error" not in driver.page_source.lower()
