"""DASH-009: Selenium browser-level E2E suite for the core PoC loop.

Drives a real `dashboard-web` subprocess (`live_server` fixture) via a real
Chrome session (`driver` fixture) against the `stub_gateway_api` fixture
(`conftest.py`, same directory) -- not `fastapi.testclient.TestClient`, per
the backlog's explicit "not in-process TestClient" wording.

Three flows, each with one already-specified backlog negative/edge case (not
invented here, see ticket Analysis section):
1. Login (DASH-002's own AC): valid key authenticates; invalid key redirects
   back to `/login` with an error and no session cookie.
2. Submit a run (DASH-006's own AC): a valid payload redirects to the new
   run's detail page; an invalid payload (`horizon=0`, DASH-006's own
   Pydantic `ValidationError` example) redisplays the form with an error, no
   redirect.
3. View a run (DASH-004's own AC / DASH-005-GAP fallback): the id from flow
   2's own redirect is used directly -- no runs-list page exists this sprint
   and none is built here, so this is "navigate to the id flow 2 just
   created," not a separate lookup. A syntactically valid but nonexistent id
   renders the not-found page.

`test_submit_run_valid_payload_redirects_and_shows_completed_results` is
where flow 2's valid case and flow 3's valid case are exercised together --
this is the DASH-005-GAP fallback exactly as the ticket's Design section
describes it ("effectively the same navigation"), not two independent tests
that would otherwise need a second way to reach a run id.
"""

from __future__ import annotations

import re

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.e2e.stub_gateway_api import VALID_API_KEY

pytestmark = pytest.mark.e2e

_WAIT_SECONDS = 15
_NONEXISTENT_RUN_ID = "99999999-9999-9999-9999-999999999999"

_VALID_RUN_FORM = {
    "dataset_id": "e2e-dataset",
    "dataset_reference_path": "e2e-sample.csv",
    "horizon": "24",
    "purge_gap_hours": "1",
    "train_window": "50",
    "test_window": "10",
    "step": "10",
}


def _wait(driver):
    return WebDriverWait(driver, _WAIT_SECONDS)


@pytest.fixture(autouse=True)
def _clean_browser_state(driver, live_server):
    """Every test starts from a logged-out, cookie-free browser -- prevents a
    session cookie set by one test from leaking into the next (the `driver`
    fixture is session-scoped for speed, so this is the isolation seam).
    """
    driver.get(f"{live_server}/login")
    driver.delete_all_cookies()
    yield


def _fill(driver, field_id: str, value: str) -> None:
    element = driver.find_element(By.ID, field_id)
    element.clear()
    element.send_keys(value)


def _login(driver, live_server: str, api_key: str) -> None:
    driver.get(f"{live_server}/login")
    _fill(driver, "api_key", api_key)
    driver.find_element(By.CSS_SELECTOR, "form[action='/login'] button[type='submit']").click()


def test_login_valid_key_authenticates(driver, live_server) -> None:
    _login(driver, live_server, VALID_API_KEY)

    _wait(driver).until(EC.url_contains("/runs/new"))

    assert driver.current_url == f"{live_server}/runs/new"
    assert driver.get_cookie("session_id") is not None


def test_login_invalid_key_rejected(driver, live_server) -> None:
    _login(driver, live_server, "not-the-valid-key")

    _wait(driver).until(EC.presence_of_element_located((By.CLASS_NAME, "error")))

    assert driver.current_url == f"{live_server}/login"
    assert "Invalid API key" in driver.find_element(By.CLASS_NAME, "error").text
    assert driver.get_cookie("session_id") is None


def test_submit_run_valid_payload_redirects_and_shows_completed_results(driver, live_server) -> None:
    _login(driver, live_server, VALID_API_KEY)
    _wait(driver).until(EC.url_contains("/runs/new"))

    for field_id, value in _VALID_RUN_FORM.items():
        _fill(driver, field_id, value)
    driver.find_element(By.CSS_SELECTOR, "form[action='/runs/new'] button[type='submit']").click()

    _wait(driver).until(EC.url_matches(r"/runs/[0-9a-f-]{36}$"))

    run_id_match = re.search(r"/runs/([0-9a-f-]{36})$", driver.current_url)
    assert run_id_match is not None, f"unexpected post-submit URL {driver.current_url!r}"
    run_id = run_id_match.group(1)

    # Bounded poll for `status` no longer being "running" (Design section's
    # allowance) -- the stub fixture marks a run "completed" synchronously at
    # creation time, so this loop is expected to exit on its first iteration,
    # not an indefinite wait.
    status_cell = None
    for _ in range(10):
        status_cell = driver.find_element(
            By.XPATH, "//tr[th[text()='Status']]/td"
        )
        if status_cell.text.strip() != "running":
            break
        driver.get(f"{live_server}/runs/{run_id}")
    assert status_cell is not None
    assert status_cell.text.strip() == "completed"

    assert run_id in driver.find_element(By.TAG_NAME, "h2").text
    splits_table_header = driver.find_element(By.XPATH, "//th[text()='Model MAE']")
    assert splits_table_header is not None
    assert "no significant difference" in driver.page_source


def test_submit_run_invalid_payload_redisplays_form(driver, live_server) -> None:
    _login(driver, live_server, VALID_API_KEY)
    _wait(driver).until(EC.url_contains("/runs/new"))

    invalid_form = {**_VALID_RUN_FORM, "horizon": "0"}
    for field_id, value in invalid_form.items():
        _fill(driver, field_id, value)
    submit_form = driver.find_element(By.CSS_SELECTOR, "form[action='/runs/new']")
    # The horizon field's min="1" mirrors DASH-006's server-side constraint client-side
    # (correct, per that ticket's own AC), so the browser's native HTML5 validation
    # blocks this deliberately-invalid submit before it ever reaches the server. This
    # test exists to prove the *server-side* validation path (DASH-006's real
    # enforcement, not the client-side mirror), so it disables native validation here
    # to force the round trip through, exactly as a client with JS disabled or a
    # non-browser caller would exercise it.
    driver.execute_script("arguments[0].noValidate = true;", submit_form)
    submit_form.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    _wait(driver).until(EC.presence_of_element_located((By.CLASS_NAME, "error")))

    assert driver.current_url == f"{live_server}/runs/new"
    assert driver.find_element(By.ID, "dataset_id").get_attribute("value") == "e2e-dataset"


def test_view_nonexistent_run_shows_not_found(driver, live_server) -> None:
    _login(driver, live_server, VALID_API_KEY)
    _wait(driver).until(EC.url_contains("/runs/new"))

    driver.get(f"{live_server}/runs/{_NONEXISTENT_RUN_ID}")

    _wait(driver).until(EC.presence_of_element_located((By.TAG_NAME, "h2")))
    assert driver.find_element(By.TAG_NAME, "h2").text == "Not found"
