"""agent_uat: evidence-capture driver for an agent-run user test of dashboard-web.

Runs against a REAL stack (docker compose up), not tests/e2e's stub gateway-api --
see scripts/agent_uat/README.md for why this is a separate tool from tests/e2e/.

Not a test: makes no assertions. For each scenario step it saves a screenshot, the
rendered HTML, and (when the step names `verify_against`) the matching raw
gateway-api JSON plus a mechanical field-by-field diff, so an agent reviewing the
evidence directory afterward doesn't have to eyeball every number by hand.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"


def _build_driver(headful: bool) -> webdriver.Chrome:
    options = Options()
    if not headful:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    return webdriver.Chrome(options=options)


def _substitute(value: str, context: dict[str, str]) -> str:
    for key, replacement in context.items():
        value = value.replace(f"{{{key}}}", replacement)
    return value


def _extract_run_id(current_url: str) -> str | None:
    # This platform mints run ids as uuid4().hex -- 32 hex chars, no dashes --
    # but accept the dashed 36-char form too rather than depend on that.
    match = re.search(r"/runs/([0-9a-fA-F]{32}|[0-9a-fA-F-]{36})", current_url)
    return match.group(1) if match else None


def _fetch_api_json(
    gateway_url: str,
    path: str,
    context: dict[str, str],
    api_key: str | None,
    operator_token: str | None,
) -> Any:
    resolved_path = _substitute(path, context)
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if operator_token:
        headers["X-Operator-Token"] = operator_token
    response = httpx.get(f"{gateway_url}{resolved_path}", headers=headers, timeout=10.0)
    response.raise_for_status()
    return response.json()


def _dig(payload: Any, field: str) -> Any:
    """Best-effort field lookup: top-level key, or first list item's key."""
    if isinstance(payload, dict):
        if field in payload:
            return payload[field]
        if "items" in payload and isinstance(payload["items"], list) and payload["items"]:
            first = payload["items"][0]
            if isinstance(first, dict) and field in first:
                return first[field]
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict) and field in first:
            return first[field]
    return None


_NUMBER_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def _rendered_text_contains(html: str, value: Any) -> bool:
    """Is `value` faithfully represented somewhere in the rendered HTML?

    Floats need numeric comparison, not substring matching: the UI rounds for
    display (model_mae 0.000133356 renders as "0.0001"), so a raw substring
    check reports a mismatch on essentially every float and buries the real
    ones. A rendered number counts as faithful when the API value rounds to it
    at the precision that number was displayed to.
    """
    if value is None:
        return True  # nothing to check
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value) in html

    for candidate in _NUMBER_RE.findall(html):
        try:
            rendered = float(candidate)
        except ValueError:
            continue
        decimals = len(candidate.split(".")[1]) if "." in candidate and "e" not in candidate.lower() else 0
        tolerance = 0.5 * (10 ** -decimals)
        if abs(rendered - float(value)) <= tolerance:
            return True
    return False


def run_step(
    driver: webdriver.Chrome,
    step: dict[str, Any],
    base_url: str,
    gateway_url: str,
    context: dict[str, str],
    out_dir: Path,
    api_key: str | None,
    operator_token: str | None,
) -> dict[str, Any]:
    name = step["name"]
    action = step["action"]

    if action == "get":
        driver.get(base_url + _substitute(step["path"], context))
    elif action == "post":
        # Plain POST-only routes (e.g. /logout) have no form to submit via the UI;
        # drive them with a same-session XHR instead of a second browser action type.
        driver.execute_script(
            "fetch(arguments[0], {method: 'POST', credentials: 'same-origin'})",
            base_url + _substitute(step["path"], context),
        )
        time.sleep(0.5)
    elif action == "fill_and_submit":
        missing_fields: list[str] = []
        form = driver.find_element(By.CSS_SELECTOR, step["form_selector"])
        for field_name, raw_value in step.get("fields", {}).items():
            value = _substitute(raw_value, context)
            try:
                field = form.find_element(By.NAME, field_name)
            except Exception:
                missing_fields.append(field_name)
                continue
            if field.tag_name == "select":
                Select(field).select_by_value(value)
            else:
                field.clear()
                field.send_keys(value)
        # Click the submit button rather than calling the DOM form.submit() method:
        # the latter does not fire the "submit" event per spec, which several of
        # this app's forms (HTMX hx-post) rely on to intercept the request.
        form.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()
        if step.get("follow_redirect"):
            time.sleep(0.5)
        else:
            time.sleep(0.3)  # give an HTMX fragment swap a moment to land before the screenshot
    elif action == "click":
        try:
            driver.find_element(By.CSS_SELECTOR, step["selector"]).click()
            time.sleep(0.5)
        except Exception:
            pass  # missing element is itself a finding; recorded via the screenshot, not a hard failure
    elif action == "current_page":
        pass
    else:
        raise ValueError(f"unknown action {action!r}")

    # Opportunistically pick up a run_id once we land on a run detail page, so later
    # steps (splits, report generation) can reference it without the caller supplying one.
    found_run_id = _extract_run_id(driver.current_url)
    if found_run_id:
        context.setdefault("run_id", found_run_id)

    screenshot_path = out_dir / f"{name}.png"
    html_path = out_dir / f"{name}.html"
    if step.get("screenshot", True):
        driver.save_screenshot(str(screenshot_path))
    html_path.write_text(driver.page_source, encoding="utf-8")

    record: dict[str, Any] = {
        "step": name,
        "action": action,
        "fields_not_found": missing_fields if action == "fill_and_submit" else None,
        "url": driver.current_url,
        "screenshot": screenshot_path.name if step.get("screenshot", True) else None,
        "html": html_path.name,
    }

    verify = step.get("verify_against")
    if verify:
        api_path = verify["path"]
        api_json_path = out_dir / f"{name}.api.json"
        try:
            payload = _fetch_api_json(gateway_url, api_path, context, api_key, operator_token)
        except Exception as exc:  # transport failure is itself evidence, not a script crash
            record["verify_error"] = str(exc)
        else:
            api_json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            record["api_json"] = api_json_path.name
            html = html_path.read_text(encoding="utf-8")
            diffs = []
            for field in verify.get("extract_fields", []):
                api_value = _dig(payload, field)
                if not _rendered_text_contains(html, api_value):
                    diffs.append({"field": field, "api_value": api_value, "found_in_rendered_html": False})
            record["field_diffs"] = diffs

    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--operator-token", default=None)
    parser.add_argument("--dataset-source", default=None, help="Stored dataset source name for the tenant scenario's run-submit step")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = EVIDENCE_ROOT / f"{timestamp}-{scenario['name']}"
    out_dir.mkdir(parents=True, exist_ok=True)

    context: dict[str, str] = {}
    if args.api_key:
        context["api_key"] = args.api_key
    if args.operator_token:
        context["operator_token"] = args.operator_token
    if args.dataset_source:
        context["dataset_source"] = args.dataset_source

    driver = _build_driver(args.headful)
    records = []
    try:
        for step in scenario["steps"]:
            records.append(
                run_step(
                    driver,
                    step,
                    args.base_url,
                    args.gateway_url,
                    context,
                    out_dir,
                    args.api_key,
                    args.operator_token,
                )
            )
    finally:
        driver.quit()

    manifest = {
        "scenario": scenario["name"],
        "description": scenario.get("description"),
        "base_url": args.base_url,
        "gateway_url": args.gateway_url,
        "ran_at": timestamp,
        "steps": records,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"evidence written to {out_dir}")


if __name__ == "__main__":
    main()
